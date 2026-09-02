"""
AI inference of character profiles from screenplay text.

The parser can only extract what the script literally states, which for most
characters is very little. This module asks Gemini to read each character's
dialogue and the action lines that mention them, and to propose the four
production fields the Cast profiler exposes:

    Role / Narrative Archetype
    Actor Screen Reference & Physical Appearance
    Costume, Wardrobe & Props
    Facial Features & Catchlights

These feed the image prompts, so descriptions must be concrete and renderable.

Inference is best-effort. Without an API key, on error, or on timeout, the
screenplay is returned with its parser-derived profiles untouched: enrichment
must never be the reason an upload fails.
"""
import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from backend.app.script.cache_service import (
    generate_hash,
    get_cached_response,
    set_cached_response,
)
from backend.app.script.parser import Screenplay, ScreenplayScene
from backend.app.script.character_agent import fallback_enrich_characters

logger = logging.getLogger(__name__)

MODEL = os.environ.get("CINESPINE_GEMINI_MODEL", "gemini-3.6-flash")
# A timeout discards the whole inference, so the default is generous: measured
# round trips on a five-scene script run ~23s, which left too little headroom
# at the previous 30s.
TIMEOUT_SECONDS = float(os.environ.get("CINESPINE_AI_CHARACTER_TIMEOUT", "60"))

# Per character, how much evidence to send. Keeps the prompt bounded on
# feature-length scripts.
MAX_DIALOGUE_LINES = 12
MAX_ACTION_LINES = 6

# Fields the model is allowed to fill.
INFERRED_FIELDS = (
    "role",
    "actor_reference",
    "look_and_costume",
    "facial_features",
    "personality_traits",
    "personality_axes",
)

# The five axes a character is scored on, in the order they are drawn.
#
# These are the Big Five (five-factor model), named rather than invented: five
# axes made up for this app would be pseudo-psychology with a chart around it,
# and nobody could say what a score meant. Neuroticism is labelled "Emotional
# volatility" because that is what it describes and the clinical word reads
# wrong on a call sheet.
#
# This scores a CHARACTER -- a person written in a screenplay -- and never an
# actor. Nothing here is about a real human being.
PERSONALITY_AXES = (
    ("openness", "Openness",
     "Curiosity and imagination; appetite for the unfamiliar."),
    ("conscientiousness", "Conscientiousness",
     "Order, diligence, follow-through."),
    ("extraversion", "Extraversion",
     "Energy directed outward; how much they take up a room."),
    ("agreeableness", "Agreeableness",
     "Warmth and accommodation towards others."),
    ("emotional_volatility", "Emotional volatility",
     "How readily feeling breaks the surface and swings."),
)

AXIS_KEYS = tuple(key for key, _, _ in PERSONALITY_AXES)


def _coerce_personality_axes(value: Any) -> Optional[Dict[str, Dict[str, Any]]]:
    """
    The five axes, or None if the model returned nothing usable.

    A score is an integer 0-100 or null, and null is a real answer: it means
    the script does not support one, and it has to survive all the way to the
    chart rather than becoming a zero. Zero draws a point at the centre of a
    radar, which reads as "none of this trait" -- a claim nobody made. Absence
    rendered as presence.

    A score outside the range is dropped rather than clamped. A model returning
    140 has not understood the scale, and clamping to 100 would turn a broken
    answer into a confident one.
    """
    if not isinstance(value, dict):
        return None

    axes: Dict[str, Dict[str, Any]] = {}
    for key in AXIS_KEYS:
        entry = value.get(key)
        score, evidence = None, None
        if isinstance(entry, dict):
            raw = entry.get("score")
            if isinstance(raw, bool):
                raw = None
            if isinstance(raw, (int, float)) and 0 <= raw <= 100:
                score = int(round(raw))
            text = entry.get("evidence")
            if isinstance(text, str) and text.strip():
                evidence = text.strip()[:200]
        # No score means no evidence either: evidence for a number that was
        # thrown away would explain something nobody can see.
        axes[key] = {"score": score, "evidence": evidence if score is not None else None}

    if all(a["score"] is None for a in axes.values()):
        # Nothing scored. Five nulls say the same as no field at all, and no
        # field is cheaper to reason about.
        return None
    return axes


def is_enabled() -> bool:
    """AI inference runs only when configured and not explicitly disabled."""
    if os.environ.get("CINESPINE_DISABLE_AI_CHARACTER_INFERENCE", "").strip().lower() in (
        "1", "true", "yes",
    ):
        return False
        
    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in ("1", "true", "yes")
    return use_vertex or bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def collect_character_evidence(
    name: str,
    scenes: List[ScreenplayScene],
) -> Dict[str, Any]:
    """Gathers what the screenplay actually shows about one character."""
    dialogue: List[str] = []
    actions: List[str] = []
    settings: List[str] = []

    for scene in scenes:
        present = name in (scene.characters or [])
        for line in scene.dialogues:
            if line.character.strip().upper().startswith(name):
                if len(dialogue) < MAX_DIALOGUE_LINES:
                    prefix = f"({line.parenthetical}) " if line.parenthetical else ""
                    dialogue.append(f"{prefix}{line.line}")
                present = True
        for block in scene.action_blocks:
            if name in block.upper() and len(actions) < MAX_ACTION_LINES:
                actions.append(block)
        if present and scene.heading not in settings:
            settings.append(scene.heading)

    return {
        "name": name,
        "dialogue": dialogue,
        "action_lines": actions,
        "scenes": settings[:8],
    }


WORKED_EXAMPLE = """EXAMPLE OF THE REQUIRED STANDARD

Evidence: "ELENA VASS, 40s, hauls a crate across the dock. Her hands are raw."
Dialogue: "Third shipment this month. Someone's counting."

TOO VAGUE - never write anything like this:
  "actor_reference": "40s woman with a distinctive, expressive screen presence"
  "look_and_costume": "Practical workwear suited to the dockside setting"
  "facial_features": "Striking, characterful features with cinematic catchlights"

CORRECT - this level of specificity is required:
  "actor_reference": "Late 40s woman, 5'6\\", thickset through the shoulders from manual work,
    grey-streaked black hair scraped into a short tail, stands squared and still"
  "look_and_costume": "Navy quilted donkey jacket with cracked PVC shoulder patches,
    oil-darkened cuffs, fingerless wool gloves, steel-toed boots worn white at the caps,
    brass tally counter on a lanyard"
  "facial_features": "Broad flat cheekbones, deep-set brown eyes under heavy lids,
    wind-chapped skin, a white scar through the left eyebrow, mouth set flat"
"""


def build_prompt(screenplay: Screenplay, retry_feedback: Optional[str] = None) -> str:
    """
    Builds a single grounded prompt covering the whole cast.

    `retry_feedback` names characters whose first response was too vague, so the
    correction is targeted rather than a blind re-ask.
    """
    cast = [
        collect_character_evidence(profile.name, screenplay.scenes)
        for profile in screenplay.characters
    ]
    settings = [scene.heading for scene in screenplay.scenes][:12]

    prompt = (
        "You are a casting director, costume designer and director of photography "
        "preparing a lookbook from a screenplay.\n\n"
        f"TITLE: {screenplay.title}\n"
        f"AUTHOR: {screenplay.author or 'unknown'}\n"
        f"SETTINGS: {'; '.join(settings) or 'unspecified'}\n\n"
        "Write a production profile for each character below.\n\n"
        "These descriptions are fed verbatim to a photorealistic image model. It "
        "cannot render an abstraction. Every clause must name something a camera "
        "could photograph: a garment, a fabric, a colour, a measurement, a mark on "
        "skin, a way of standing.\n\n"
        "RULES\n"
        "1. Ground every choice in the evidence. What a character says, how they "
        "say it, what they do and where they are all constrain how they look.\n"
        "1a. Any fact the evidence states is fixed. Use it exactly, never an "
        "approximation. This includes facts stated in dialogue rather than in an "
        "action line: if a character is called twenty-three, they are 23, not 24. "
        "The same holds for names, ages, injuries, and objects they carry.\n"
        "2. Where the screenplay is silent, decide. Commit to one specific "
        "option consistent with the role, period and setting. Never hedge, never "
        "offer alternatives, never say a detail is unknown or to be determined.\n"
        "3. Banned words, because they describe nothing: cinematic, expressive, "
        "distinctive, striking, mysterious, intense, rugged, appropriate, "
        "suitable, typical, generic, various, certain, undefined, presence.\n"
        "4. actor_reference must explicitly state gender characteristics / physical presentation (e.g., woman, man, female, male, non-binary / androgynous presentation), along with age, height or build, hair, and bearing.\n"
        "5. look_and_costume must name at least three specific garments or props, "
        "with fabric, colour and condition. Say how the clothes are worn or "
        "damaged, not just what they are.\n"
        "6. facial_features must give face shape, eye colour, complexion, and at "
        "least one distinguishing mark or habitual expression.\n"
        "7. Differentiate the cast. No two characters may share a description.\n"
        "8. Never mention the screenplay, the script, the camera, or that you "
        "inferred anything. Write as settled fact.\n\n"
        f"{WORKED_EXAMPLE}\n"
        "Return ONLY a JSON array. One object per character, with exactly these keys:\n"
        '  "name": the character name exactly as given\n'
        '  "role": role and narrative archetype, at most 8 words\n'
        '  "actor_reference": one sentence (15-40 words) specifying gender presentation, age, physique, hair, and bearing\n'
        '  "look_and_costume": one sentence, 20-50 words\n'
        '  "facial_features": one sentence, 15-40 words\n'
        '  "personality_traits": array of 3 to 5 single-word traits, each specific '
        "to this character\n"
        '  "personality_axes": an object with exactly these five keys: '
        + ", ".join(AXIS_KEYS)
        + ".\n"
        '     Each value is {"score": 0-100, "evidence": one short clause '
        "naming what in the script supports it}.\n\n"
        "THE AXES ARE THE ONE EXCEPTION TO RULE 2.\n"
        "Everywhere else you must decide and commit, because a costume has to "
        "be built and a face has to be rendered and 'unknown' cannot be "
        "photographed. A personality score is different: it is a reading of "
        "evidence, and a character with four lines does not contain five of "
        "them. Where the script will not support an axis, return "
        '{"score": null, "evidence": null} for it. A confident number with '
        "nothing behind it is worse than a gap, because the gap is true.\n"
        "Score the CHARACTER as written, never the actor who might play them.\n\n"
    )

    if retry_feedback:
        prompt += (
            "CORRECTION REQUIRED\n"
            f"{retry_feedback}\n"
            "Rewrite every character listed below to the standard shown above. "
            "Replace vague phrasing with concrete, photographable detail.\n\n"
        )

    prompt += "CHARACTERS:\n" + json.dumps(cast, ensure_ascii=False, indent=1)
    return prompt


# A model reporting overload is not a reason to downgrade the whole cast: the
# spikes are short, and one retry costs far less than a generic profile.
TRANSIENT_RETRIES = 1
TRANSIENT_BACKOFF_SECONDS = 3.0

# Matched on the message because the SDK raises one exception type for all of
# these, and the status code is only present in the text.
_TRANSIENT_MARKERS = ("503", "UNAVAILABLE", "high demand", "overloaded", "500", "INTERNAL")


def _is_transient(exc: Exception) -> bool:
    """Whether retrying the same model in a moment is worth trying."""
    text = str(exc)
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _call_gemini(prompt: str) -> str:
    """
    Blocking Gemini call; run off the event loop by the caller. Uses SQLite cache.

    Tries each candidate model in turn. A model being unavailable to this key --
    retired, over quota, temporarily overloaded -- is an ordinary condition, and
    the caller above turns any exception into a parse warning, so without this
    loop one bad first choice silently downgrades every character profile.
    """
    from google import genai
    from backend.app.script.llm_router import get_model_candidates
    from backend.app.core.telemetry import LLM_TOKENS_CONSUMED, AI_CACHE_HITS, LLM_LATENCY

    # Rich narrative descriptions are the 'complex' end of the routing.
    candidates = get_model_candidates(prompt, task_complexity="complex")

    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in ("1", "true", "yes")
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    
    if use_vertex:
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        client = genai.Client(vertexai=True, project=project_id, location=location)
    else:
        client = genai.Client(api_key=api_key)

    last_error: Optional[Exception] = None
    for model in candidates:
        req_hash = generate_hash(prompt=prompt, model=model)
        cached = get_cached_response(req_hash)
        if cached:
            logger.info("Character inference cache hit for %s (%s)", req_hash, model)
            AI_CACHE_HITS.labels(model=model, status="hit").inc()
            return cached["text"]

        logger.info("Character inference cache miss for %s (%s)", req_hash, model)
        AI_CACHE_HITS.labels(model=model, status="miss").inc()

        response = None
        for attempt in range(TRANSIENT_RETRIES + 1):
            try:
                with LLM_LATENCY.labels(model=model).time():
                    response = client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config={"response_mime_type": "application/json", "temperature": 0.4},
                    )
                break
            except Exception as exc:  # noqa: BLE001 - any failure means try again or move on
                last_error = exc
                if attempt < TRANSIENT_RETRIES and _is_transient(exc):
                    logger.info(
                        "Model %s temporarily unavailable, retrying in %.0fs: %s",
                        model, TRANSIENT_BACKOFF_SECONDS, exc,
                    )
                    time.sleep(TRANSIENT_BACKOFF_SECONDS)
                    continue
                logger.warning("Model %s unavailable, trying next candidate: %s", model, exc)
                break

        if response is None:
            continue

        text = response.text or ""
        if text:
            set_cached_response(req_hash, {"text": text})

        usage = getattr(response, "usage_metadata", None)
        if usage and usage.total_token_count:
            LLM_TOKENS_CONSUMED.labels(
                model=model, task_complexity="complex"
            ).inc(usage.total_token_count)

        return text

    raise RuntimeError(
        f"No Gemini model available; tried {', '.join(candidates)}"
    ) from last_error


def parse_ai_response(raw: str) -> Dict[str, Dict[str, Any]]:
    """
    Parses the model's JSON into {NAME: fields}. Tolerates a fenced code block
    or an object wrapping the array. Returns {} on anything unusable.
    """
    if not raw or not raw.strip():
        return {}

    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text.strip("`")
        text = text.removeprefix("json").strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}

    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                data = value
                break
        else:
            return {}
    if not isinstance(data, list):
        return {}

    parsed: Dict[str, Dict[str, Any]] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip().upper()
        if not name:
            continue

        fields: Dict[str, Any] = {}
        for key in INFERRED_FIELDS:
            value = entry.get(key)
            if key == "personality_axes":
                axes = _coerce_personality_axes(value)
                if axes:
                    fields[key] = axes
            elif key == "personality_traits":
                if isinstance(value, list):
                    traits = [str(t).strip() for t in value if str(t).strip()]
                    if traits:
                        fields[key] = traits[:5]
            elif isinstance(value, str) and value.strip():
                fields[key] = value.strip()
        if fields:
            parsed[name] = fields

    return parsed


# Words that fill space without describing anything a camera could capture.
# Matched case-insensitively on word boundaries.
VAGUE_TERMS = frozenset({
    "cinematic", "expressive", "distinctive", "distinguishing", "striking",
    "mysterious", "intense", "rugged", "appropriate", "suitable", "typical",
    "generic", "various", "certain", "undefined", "unspecified", "presence",
    "characterful", "compelling", "memorable", "interesting", "unique",
    "somewhat", "perhaps", "possibly", "likely", "maybe", "tbd",
})

# Concrete signals: something a camera could actually resolve. Colours,
# materials, garments, anatomy, condition, and ages like "30s" or "5'6".
CONCRETE_HINTS = re.compile(
    r"(\b\d+s?\b|'\d|"
    r"\b(black|white|grey|gray|brown|blue|green|red|amber|navy|olive|tan|blonde|"
    r"charcoal|cream|rust|ochre|auburn|ginger|silver|gold|"
    r"wool|cotton|linen|leather|denim|silk|canvas|tweed|velvet|corduroy|nylon|"
    r"suede|rubber|brass|steel|plastic|fur|"
    r"scar|freckle|stubble|mole|tattoo|beard|braid|ponytail|moustache|"
    r"hair|eyes|eye|cheekbone|cheekbones|jaw|jawline|brow|chin|nose|lips|mouth|"
    r"skin|complexion|shoulders|build|frame|hands|posture|"
    r"collar|cuff|cuffs|button|buttons|zip|lapel|hem|seam|pocket|"
    r"boot|boots|glove|gloves|coat|jacket|shirt|dress|trousers|skirt|vest|"
    r"scarf|belt|hat|cap|apron|uniform|tie|watch|ring|chain|"
    r"frayed|torn|patched|stained|faded|worn|creased|cracked|scuffed|bleached)\b)",
    re.IGNORECASE,
)

# Phrases that admit the description is a placeholder rather than a decision.
PLACEHOLDER_RE = re.compile(
    r"(to be (defined|determined|decided)|not (described|specified|stated)|"
    r"refine to lock|consistent across|set a reference|tbd|unknown|n/a|"
    r"placeholder|lorem ipsum)",
    re.IGNORECASE,
)

# Minimum words expected in each free-text field before it counts as described.
MIN_WORDS = {
    "actor_reference": 10,
    "look_and_costume": 12,
    "facial_features": 10,
}


def is_vague(field: str, text: str) -> bool:
    """
    True when a field is too generic to render.

    Three independent failures: it uses a banned filler word, it is too short to
    carry real detail, or it contains no concrete noun at all.
    """
    if not isinstance(text, str) or not text.strip():
        return True

    words = set(re.findall(r"[a-z]+", text.lower()))
    if words & VAGUE_TERMS:
        return True
    if PLACEHOLDER_RE.search(text):
        return True
    if len(text.split()) < MIN_WORDS.get(field, 0):
        return True
    if field in MIN_WORDS and not CONCRETE_HINTS.search(text):
        return True
    return False


def find_vague_characters(inferred: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    """Returns {NAME: [weak field names]} for anything needing a rewrite."""
    weak: Dict[str, List[str]] = {}
    for name, fields in inferred.items():
        bad = [
            key for key in ("actor_reference", "look_and_costume", "facial_features")
            if key in fields and is_vague(key, fields[key])
        ]
        if bad:
            weak[name] = bad
    return weak


def build_retry_feedback(weak: Dict[str, List[str]]) -> str:
    """Names exactly what was too vague, so the retry is targeted."""
    lines = [
        f"- {name}: {', '.join(fields)} " f"{'was' if len(fields) == 1 else 'were'} too vague."
        for name, fields in sorted(weak.items())
    ]
    return "\n".join(lines)


def apply_inferred_profiles(
    screenplay: Screenplay,
    inferred: Dict[str, Dict[str, Any]],
) -> int:
    """Applies inferred fields onto the parsed profiles. Returns how many matched."""
    applied = 0
    for profile in screenplay.characters:
        fields = inferred.get(profile.name.upper())
        if not fields:
            continue
        for key, value in fields.items():
            setattr(profile, key, value)
        applied += 1
    return applied


async def enrich_screenplay_characters(screenplay: Screenplay) -> Screenplay:
    """
    Fills in each character's production profile using AI, in place.

    Returns the screenplay unchanged (with a parse warning) whenever inference
    is unavailable or fails, so callers never need to handle an error path.
    """
    if not screenplay.characters:
        return screenplay

    if not is_enabled():
        screenplay.parse_warnings.append(
            "Character details were derived from the script text only. Set GEMINI_API_KEY "
            "or GOOGLE_GENAI_USE_VERTEXAI to have appearance, wardrobe and facial features inferred by AI."
        )
        return fallback_enrich_characters(screenplay)

    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(_call_gemini, build_prompt(screenplay)),
            timeout=TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        screenplay.parse_warnings.append(
            f"AI character inference timed out after {TIMEOUT_SECONDS:.0f}s; "
            "showing details derived from the script text."
        )
        return fallback_enrich_characters(screenplay)
    except Exception as exc:  # noqa: BLE001 - inference must never fail an upload
        logger.warning("Character inference failed: %s", exc)
        screenplay.parse_warnings.append(
            "AI character inference was unavailable; showing details derived from "
            "the script text."
        )
        return fallback_enrich_characters(screenplay)

    inferred = parse_ai_response(raw)
    if not inferred:
        screenplay.parse_warnings.append(
            "AI character inference returned nothing usable; showing details derived "
            "from the script text."
        )
        return fallback_enrich_characters(screenplay)

    # A prompt cannot guarantee specificity, so check the output and ask once
    # more for whatever came back too generic to render.
    weak = find_vague_characters(inferred)
    if weak:
        try:
            retry_raw = await asyncio.wait_for(
                asyncio.to_thread(
                    _call_gemini,
                    build_prompt(screenplay, retry_feedback=build_retry_feedback(weak)),
                ),
                timeout=TIMEOUT_SECONDS,
            )
            retried = parse_ai_response(retry_raw)
        except Exception as exc:  # noqa: BLE001 - the first pass is still usable
            logger.warning("Character specificity retry failed: %s", exc)
            retried = {}

        # Keep a retried field only when it is actually better than what it replaces.
        for name, fields in retried.items():
            if name not in inferred:
                continue
            for key in weak.get(name, []):
                candidate = fields.get(key)
                if candidate and not is_vague(key, candidate):
                    inferred[name][key] = candidate

        still_weak = find_vague_characters(inferred)
        if still_weak:
            screenplay.parse_warnings.append(
                "AI descriptions for "
                f"{', '.join(sorted(still_weak))} stayed generic; "
                "edit those characters to lock a specific look."
            )

    applied = apply_inferred_profiles(screenplay, inferred)
    missed = len(screenplay.characters) - applied
    if missed > 0:
        screenplay.parse_warnings.append(
            f"AI inferred details for {applied} of {len(screenplay.characters)} characters."
        )
    return fallback_enrich_characters(screenplay)
