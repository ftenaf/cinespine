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
import os
from typing import Any, Dict, List, Optional

from backend.app.script.parser import Screenplay, ScreenplayScene

MODEL = "gemini-2.0-flash"
TIMEOUT_SECONDS = float(os.environ.get("CINESPINE_AI_CHARACTER_TIMEOUT", "30"))

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
)


def is_enabled() -> bool:
    """AI inference runs only when configured and not explicitly disabled."""
    if os.environ.get("CINESPINE_DISABLE_AI_CHARACTER_INFERENCE", "").strip().lower() in (
        "1", "true", "yes",
    ):
        return False
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


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


def build_prompt(screenplay: Screenplay) -> str:
    """Builds a single grounded prompt covering the whole cast."""
    cast = [
        collect_character_evidence(profile.name, screenplay.scenes)
        for profile in screenplay.characters
    ]

    return (
        "You are a film production's casting director, costume designer and "
        "director of photography working from a screenplay.\n\n"
        f"TITLE: {screenplay.title}\n"
        f"AUTHOR: {screenplay.author or 'unknown'}\n\n"
        "For each character below, infer a production profile from the evidence "
        "given. Base every claim on the dialogue, action lines and settings "
        "provided. Where the screenplay does not state something, choose a "
        "specific option that is consistent with the character's role, the "
        "period and the setting, rather than being vague.\n\n"
        "These descriptions are fed directly to a photorealistic image model, so "
        "they must be concrete and visual. Do not mention the screenplay, the "
        "camera, or the fact that anything was inferred.\n\n"
        "Return ONLY a JSON array. One object per character, with exactly these keys:\n"
        '  "name": the character name exactly as given\n'
        '  "role": role and narrative archetype, at most 8 words\n'
        '  "actor_reference": age, build, height, hair, bearing and screen presence\n'
        '  "look_and_costume": specific garments, fabrics, colours, wear and props\n'
        '  "facial_features": face shape, eyes, complexion, distinguishing marks, '
        "typical expression\n"
        '  "personality_traits": array of 3 to 5 single-word traits\n\n'
        "CHARACTERS:\n"
        f"{json.dumps(cast, ensure_ascii=False, indent=1)}"
    )


def _call_gemini(prompt: str) -> str:
    """Blocking Gemini call; run off the event loop by the caller."""
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"response_mime_type": "application/json", "temperature": 0.4},
    )
    return response.text or ""


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
            if key == "personality_traits":
                if isinstance(value, list):
                    traits = [str(t).strip() for t in value if str(t).strip()]
                    if traits:
                        fields[key] = traits[:5]
            elif isinstance(value, str) and value.strip():
                fields[key] = value.strip()
        if fields:
            parsed[name] = fields

    return parsed


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
            "to have appearance, wardrobe and facial features inferred by AI."
        )
        return screenplay

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
        return screenplay
    except Exception as exc:  # noqa: BLE001 - inference must never fail an upload
        print(f"[Character AI] inference failed: {exc}")
        screenplay.parse_warnings.append(
            "AI character inference was unavailable; showing details derived from "
            "the script text."
        )
        return screenplay

    inferred = parse_ai_response(raw)
    if not inferred:
        screenplay.parse_warnings.append(
            "AI character inference returned nothing usable; showing details derived "
            "from the script text."
        )
        return screenplay

    applied = apply_inferred_profiles(screenplay, inferred)
    missed = len(screenplay.characters) - applied
    if missed > 0:
        screenplay.parse_warnings.append(
            f"AI inferred details for {applied} of {len(screenplay.characters)} characters."
        )
    return screenplay
