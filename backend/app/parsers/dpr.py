"""
The daily production report: Office's page, and the intent axis.

Office is authoritative for **intent** and never for what happened. That
boundary is load-bearing and easy to lose: the DPR also states what Office
believes was achieved, and promoting that to fact makes Office authoritative
for something it does not observe. So `Scenes Scheduled` is intent, and
`Scenes Complete` is a witness statement like any other -- one that can be
contradicted by a camera report.

`dept-office.md` calls this the most information-dense document in the domain,
and the reason is the named negatives:

    Scenes Scheduled          the intent, stated rather than inferred
    Scenes Complete           Office's belief about reality. Not reality
    Scenes Part Complete      a third state; not_shot is not the complement of shot
    Scenes Scheduled Not Shot the negative fact, written down at source
    Scenes Shot Not Scheduled the other negative, the one first models miss

Both negatives are recorded every day, on a PDF, and die there: no department
is notified and nothing can be queried. Reading them is the whole point.

Also carried, and worth more than it looks: the day's **slate ranges**. A slate
outside every stated range was never scheduled, which is a completeness check
nothing else in the day provides. And the **wrap time**, which is the baseline
a department's handover lag is measured from.

# What this does not claim to know

Scene tokens arrive with suffixes -- `27pt`, `6WT`. The scene number is
extracted and the token kept exactly as written, because what `pt` means on
this production has not been confirmed, and a parser that quietly decides is
how a guess becomes a fact.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app.parsers.base import ParserFailureError

# The five scene fields, in the order the page states them, mapped to the state
# each one asserts. Kept as data: a sixth field on another production's report
# is a line here, not a new branch.
SCENE_FIELDS = (
    ("scenes_scheduled", "Scenes Scheduled"),
    ("scenes_complete", "Scenes Complete"),
    ("scenes_part_complete", "Scenes Part Complete"),
    ("scenes_scheduled_not_shot", "Scenes Scheduled Not Shot"),
    ("scenes_shot_not_scheduled", "Scenes Shot Not Scheduled"),
)

# Times the day is bracketed by. Spanish labels: these reports are bilingual,
# and the wrap time is what a handover lag is measured from.
TIME_FIELDS = (
    ("general_call", r"CITACI\w*N\s+GENERAL"),
    ("first_shot_morning", r"PRIMER\s+MOTOR\s+MA\w*ANA"),
    ("snack", r"BOCATA"),
    ("lunch", r"COMIDA"),
    ("first_shot_afternoon", r"PRIMER\s+MOTOR\s+TARDE"),
    ("wrap", r"WRAP"),
)

# An en-dash comes out of the text layer as a replacement character often
# enough that treating it as a dash is not a guess, it is the common case.
_RANGE_SEPARATOR = r"[-–—�]"
_TIME = r"(\d{1,2}:\d{2})"

# A scene token: digits, then whatever the production suffixes it with.
_SCENE_TOKEN = re.compile(r"^(\d+)([A-Za-z]*)$")


@dataclass
class SceneRef:
    """One scene as the report writes it, and the number underneath."""
    scene: str
    raw: str


@dataclass
class SlateRange:
    """`27/7 - 8`: the slates of scene 27 that were scheduled, first to last."""
    scene: str
    first: str
    last: str
    raw: str


@dataclass
class SceneTiming:
    """How long a scene was expected to take against how long it took."""
    scene: str
    read: str
    shoot: str
    difference: str


@dataclass
class DailyProductionReport:
    """
    One day, as Office states it.

    Every list may be empty, and an empty `scenes_scheduled_not_shot` is a
    positive fact: Office wrote the field and left it blank because nothing
    went unshot. That is different from the field being absent, which is why
    `fields_present` records which ones the page actually stated.
    """
    scenes_scheduled: List[SceneRef] = field(default_factory=list)
    scenes_complete: List[SceneRef] = field(default_factory=list)
    scenes_part_complete: List[SceneRef] = field(default_factory=list)
    scenes_scheduled_not_shot: List[SceneRef] = field(default_factory=list)
    scenes_shot_not_scheduled: List[SceneRef] = field(default_factory=list)
    fields_present: List[str] = field(default_factory=list)

    times: Dict[str, str] = field(default_factory=dict)
    set_ups: Optional[int] = None
    total_pages: Optional[str] = None
    camera_card_range: Optional[str] = None
    sound_card_range: Optional[str] = None
    slate_ranges: List[SlateRange] = field(default_factory=list)
    scene_timings: List[SceneTiming] = field(default_factory=list)

    def as_payload(self) -> Dict[str, Any]:
        """The day's own facts, for the event that carries the whole day."""
        return {
            "times": dict(self.times),
            "set_ups": self.set_ups,
            "total_pages": self.total_pages,
            "camera_card_range": self.camera_card_range,
            "sound_card_range": self.sound_card_range,
            "slate_ranges": [
                {"scene": r.scene, "first": r.first, "last": r.last, "raw": r.raw}
                for r in self.slate_ranges
            ],
            "scene_timings": [
                {"scene": t.scene, "read": t.read, "shoot": t.shoot, "difference": t.difference}
                for t in self.scene_timings
            ],
            "fields_present": list(self.fields_present),
        }


def _scene_refs(value: str) -> List[SceneRef]:
    """
    The scenes in a comma-separated field, in the order written.

    A token that carries no digits is not a scene and is dropped rather than
    stored under a name that cannot be joined to anything.
    """
    refs: List[SceneRef] = []
    for token in re.split(r"[,;]", value or ""):
        raw = token.strip()
        if not raw:
            continue
        match = _SCENE_TOKEN.match(raw)
        if not match:
            continue
        refs.append(SceneRef(scene=match.group(1), raw=raw))
    return refs


def _field_value(text: str, label: str, stop_labels: List[str]) -> Optional[str]:
    """
    What follows a label, up to the next label on the same line.

    Labels and values share lines on this page -- `BOCATA: 11:07 Camera Cards:
    A120 - A123` -- so reading to the end of the line would swallow the next
    field whole.
    """
    pattern = re.compile(rf"{label}\s*:", re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return None

    rest = text[match.end():]
    # Cut at the next label, wherever it starts.
    cuts = [
        m.start() for other in stop_labels
        for m in [re.search(rf"{other}\s*:", rest, re.IGNORECASE)] if m
    ]
    newline = rest.find("\n")
    if newline >= 0:
        cuts.append(newline)
    if cuts:
        rest = rest[:min(cuts)]
    return rest.strip()


def parse_daily_production_report(text: str) -> DailyProductionReport:
    """
    Reads a DPR into the states it asserts.

    Raises rather than returning an empty report when none of the named fields
    are present: a document that produced nothing while reporting success is
    the failure this project spends most of its effort on, and Office's page
    was reaching no parser at all before this one.
    """
    if not text or not text.strip():
        raise ParserFailureError("Empty daily production report")

    report = DailyProductionReport()

    # Every label, so a value stops where the next field begins.
    all_labels = [re.escape(label) for _, label in SCENE_FIELDS]
    all_labels += [pattern for _, pattern in TIME_FIELDS]
    all_labels += [r"Set-?Ups", r"Total\s+P\w*ginas", r"Camera\s+Cards", r"Sound\s+Cards", r"Slates"]

    for attribute, label in SCENE_FIELDS:
        value = _field_value(text, re.escape(label), all_labels)
        if value is None:
            continue
        report.fields_present.append(attribute)
        setattr(report, attribute, _scene_refs(value))

    for name, pattern in TIME_FIELDS:
        value = _field_value(text, pattern, all_labels)
        if value:
            found = re.search(_TIME, value)
            if found:
                report.times[name] = found.group(1)

    set_ups = _field_value(text, r"Set-?Ups", all_labels)
    if set_ups:
        digits = re.search(r"\d+", set_ups)
        if digits:
            report.set_ups = int(digits.group(0))

    pages = _field_value(text, r"Total\s+P\w*ginas", all_labels)
    if pages:
        report.total_pages = pages.strip() or None

    report.camera_card_range = _field_value(text, r"Camera\s+Cards", all_labels) or None
    report.sound_card_range = _field_value(text, r"Sound\s+Cards", all_labels) or None

    slates = _field_value(text, r"Slates", all_labels)
    if slates:
        report.slate_ranges = _slate_ranges(slates)

    report.scene_timings = _scene_timings(text)

    if not report.fields_present and not report.times and not report.slate_ranges:
        raise ParserFailureError(
            "No daily production report fields found. Expected at least one of: "
            + ", ".join(label for _, label in SCENE_FIELDS)
        )

    return report


def _slate_ranges(value: str) -> List[SlateRange]:
    """
    `27/7 - 8, 49/1 - 9` into the first and last slate of each scene.

    A slate outside every range was never scheduled, which is a completeness
    check nothing else in the day provides.
    """
    ranges: List[SlateRange] = []
    for part in re.split(r"[,;]", value):
        raw = part.strip()
        if not raw:
            continue
        match = re.match(
            rf"^(\d+[A-Za-z]*)\s*/\s*(\w+)\s*(?:{_RANGE_SEPARATOR}\s*(\w+))?$", raw
        )
        if not match:
            continue
        scene, first, last = match.group(1), match.group(2), match.group(3)
        ranges.append(SlateRange(
            scene=scene, first=f"{scene}/{first}",
            # A range with no end is one slate, not an open range.
            last=f"{scene}/{last or first}", raw=raw,
        ))
    return ranges


def _scene_timings(text: str) -> List[SceneTiming]:
    """
    The read-versus-shoot table, when the page carries one.

    Read loosely on purpose: the columns are minutes and seconds written with
    prime marks that the text layer mangles, and the useful fact is which scene
    ran over, not the exact seconds.
    """
    timings: List[SceneTiming] = []
    started = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.search(r"(?i)individual\s+scene\s+timings", stripped):
            started = True
            continue
        if not started or not stripped:
            continue
        if re.match(r"(?i)^scene\s+read\s+shoot", stripped):
            continue
        match = re.match(r"^(\d+[A-Za-z]*)\s+(\S+)\s+(\S+)\s+(\S+)", stripped)
        if match:
            timings.append(SceneTiming(
                scene=match.group(1), read=match.group(2),
                shoot=match.group(3), difference=match.group(4),
            ))
    return timings
