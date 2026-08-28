"""
Finding the script behind a slate.

An editor cutting shot 119/5 wants to read scene 119 -- what the scene was
written to be, not just what the camera reports say was recorded. Two separate
jobs live here:

1. Which scene(s) a target belongs to. A slate carries its scene in its left
   half, and a compound slate ('41+122A/4') is one setup covering two scenes,
   so it belongs to both.

2. Where inside the scene a shot sits. Nothing in the paperwork states this --
   a lined script draws it as a vertical line down the page, and we do not read
   those lines. What we do have is the description the script supervisor wrote
   beside the shot. Matching that text against the scene finds the passage
   often enough to be worth offering, and never confidently enough to present
   as fact: every match comes back with the words it matched on, so the reader
   can see the evidence and judge it.
"""
import re
from typing import Any, Dict, List, Optional

# Words too common to anchor a match. Matching a note to a passage on "the" or
# "with" would land anywhere in the scene, which is the same as landing nowhere.
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "had", "has", "have", "he", "her", "hers", "him", "his", "how", "in",
    "into", "is", "it", "its", "of", "on", "onto", "or", "our", "out", "over",
    "she", "so", "that", "the", "their", "them", "then", "there", "these",
    "they", "this", "to", "up", "was", "we", "were", "what", "when", "where",
    "which", "who", "will", "with", "you", "your",
}

# Camera-department shorthand. These say how the shot was taken, never what
# the scene is about, so they cannot locate a passage inside it.
_LOG_SHORTHAND = {
    "abandoned", "again", "alt", "angle", "camera", "cam", "circled", "close",
    "complete", "cont", "contd", "continued", "cover", "coverage", "cu",
    "cut", "day", "ecu", "end", "ext", "false", "good", "insert", "int",
    "lens", "mcu", "mos", "ms", "mws", "night", "note", "ots", "pickup",
    "pov", "printed", "reset", "roll", "scene", "scenes", "series", "setup",
    "shot", "shots", "slate", "sound", "start", "tail", "take", "takes",
    "top", "vfx", "wide", "wild", "wt", "ws",
}

_TOKEN = re.compile(r"[A-Za-z][A-Za-z'’-]{2,}")

# The bar a match has to clear, in words weighted by how much each narrows the
# scene down: one word found exactly once, or several commoner ones together.
# Below this the passage is not distinguishable from the rest of the scene, and
# a highlight would be pointing at nothing in particular.
_MIN_MATCH_WEIGHT = 1.0


def _terms(text: str) -> List[str]:
    """
    The words in a piece of text that could anchor a match, in order.

    Three letters minimum, and neither a stopword nor camera shorthand.
    """
    out: List[str] = []
    for raw in _TOKEN.findall(text or ""):
        word = raw.lower().replace("’", "'").strip("'-")
        if len(word) < 3:
            continue
        if word in _STOPWORDS or word in _LOG_SHORTHAND:
            continue
        out.append(word)
    return out


def scene_numbers_for_target(target_type: str, target_id: str) -> List[str]:
    """
    The scene number(s) a tag target belongs to, in the order they are written.

    A shot's scene is the half of its slate before the shot number. A compound
    slate is one setup that plays in more than one scene, and returns all of
    them -- an editor looking at 41+122A/4 needs both pages, and choosing one
    for them would hide the other.
    """
    kind = (target_type or "").strip().lower()
    raw = (target_id or "").strip().upper()
    if not raw:
        return []

    if kind == "shot":
        # Reuse the same normalization that decides how a tag is spelled, so
        # the scene we look up is the scene the tag hangs on.
        from backend.app.spine.tag_store import UnknownTagValue, normalize_target

        try:
            _, raw = normalize_target("shot", raw)
        except UnknownTagValue:
            return []

    # Drop the shot half, then the wild-track marker, which is a kind of
    # recording rather than a scene of its own.
    head = raw.split("/")[0].strip()
    head = re.sub(r"WT$", "", head).strip()
    if not head:
        return []

    numbers: List[str] = []
    for part in head.split("+"):
        # Left as written, leading zeros and all: a scene number is a label the
        # production chose, and '007' and '7' are not interchangeable in every
        # script.
        scene = part.strip()
        # A scene number carries a digit. Without one there is nothing to look
        # up, and passing the text through would search the script for junk.
        if not any(ch.isdigit() for ch in scene):
            continue
        if scene not in numbers:
            numbers.append(scene)
    return numbers


def _line_spans(body: str) -> List[Dict[str, Any]]:
    """Each line of the scene with the character offsets it occupies."""
    spans: List[Dict[str, Any]] = []
    offset = 0
    for line in (body or "").splitlines(keepends=True):
        text = line.rstrip("\r\n")
        spans.append({"start": offset, "end": offset + len(text), "text": text})
        offset += len(line)
    return spans


def locate_passage(body: str, needle: str, max_window: int = 3) -> Optional[Dict[str, Any]]:
    """
    The passage in a scene that best matches a description, or None.

    Returns the character span, the words it matched on, and the share of the
    description's words that were found. None when nothing matched well enough
    -- an unanchored guess pointed at the wrong half of a scene is worse for an
    editor than being told plainly that we could not place it.
    """
    wanted = list(dict.fromkeys(_terms(needle)))
    if not wanted:
        return None

    lines = [ln for ln in _line_spans(body) if ln["text"].strip()]
    if not lines:
        return None

    per_line = [set(_terms(ln["text"])) for ln in lines]

    # How many lines each word appears on. A word found once in the whole scene
    # is a real anchor on its own; a word on every line is not.
    spread = {word: sum(1 for terms in per_line if word in terms) for word in wanted}

    wanted_set = set(wanted)
    best: Optional[Dict[str, Any]] = None
    best_weight = 0.0

    for size in range(1, max_window + 1):
        for i in range(0, len(lines) - size + 1):
            found: set = set()
            for terms in per_line[i:i + size]:
                found |= terms & wanted_set
            if not found:
                continue

            # A word is worth what it narrows down. One that appears once in
            # the scene points at a passage; one that appears on every line
            # points at the scene, which the reader already has.
            weight = sum(1 / spread[word] for word in found if spread.get(word))
            if weight < _MIN_MATCH_WEIGHT:
                continue

            # Window sizes run shortest first, so a wider window has to beat
            # the narrower one outright to replace it.
            if weight > best_weight:
                best_weight = weight
                best = {
                    "start": lines[i]["start"],
                    "end": lines[i + size - 1]["end"],
                    "terms": sorted(found),
                    # How much of the description was found here. Reported for
                    # the reader, not used to accept or reject: a long note
                    # full of timecodes and card numbers can describe a passage
                    # exactly while covering little of its own wording.
                    "score": round(len(found) / len(wanted), 3),
                }

    return best


def scene_heading_span(body: str) -> int:
    """
    Where the scene's body starts, past the heading line it opens with.

    The heading is the scene's label, not its content: highlighting a whole
    scene should light up what happens in it, not repeat the slug line.
    """
    lines = _line_spans(body)
    if lines and re.match(r"^\s*(?:\d+[A-Z]*\.?\s+)?(?:INT|EXT|I/E)[./ ]", lines[0]["text"], re.IGNORECASE):
        return min(lines[0]["end"] + 1, len(body))
    return 0


def build_scene_context(
    scene: Dict[str, Any],
    target_type: str,
    hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    One scene, ready to render: its text plus where to highlight in it.

    A scene target highlights the whole scene, which is exactly true. A shot
    target highlights the passage its description matched, and says what it
    matched on; when nothing matched, the scene comes back unhighlighted with a
    reason rather than with a guess.
    """
    body = scene.get("body") or scene.get("raw_content") or ""
    context: Dict[str, Any] = {
        "scene_number": scene.get("scene_number") or "",
        "heading": scene.get("heading") or "",
        "body": body,
        "highlight": None,
        "highlight_basis": "none",
        "note": None,
    }

    if not body.strip():
        context["note"] = "This scene is in the script but has no text under its heading."
        return context

    if (target_type or "").strip().lower() == "scene":
        start = scene_heading_span(body)
        context["highlight"] = {"start": start, "end": len(body), "terms": [], "score": 1.0}
        context["highlight_basis"] = "scene"
        return context

    if not (hint or "").strip():
        context["note"] = (
            "The whole scene is shown: this shot has no description in the "
            "script supervisor's log to match against."
        )
        return context

    match = locate_passage(body, hint)
    if not match:
        context["note"] = (
            "The whole scene is shown: nothing in the shot's description "
            "matched a passage closely enough to point at one."
        )
        return context

    context["highlight"] = match
    context["highlight_basis"] = "description"
    return context
