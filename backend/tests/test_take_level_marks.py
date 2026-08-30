"""
A take's marks belong to the take, not to one camera's row.

A multi-camera take is one take recorded on several cameras. The script
supervisor circles it once, on the first camera's row; the rows beneath repeat
the take number without the circle. Read row by row, camera A comes back
circled and B and C do not, so the take contradicts itself and the
reconciliation engine reports a conflict nobody on set would recognise.
"""
from backend.app.parsers.pdf_parsers import (
    parse_scripte_detailed_editor_log_text,
    unify_take_level_marks,
)

# The shape of a real facing-and-lined page: the circle appears once, and each
# camera's row restates the take number plainly.
THREE_CAMERA_TAKE = """Slate TakeDescription CR SR Time Camera Info Comments
27/7 1*  Scene(s): 27
Shot on Day: Day 31
Sticks - xwide. Frontal VWS
A1202807262:46
1 Dolly - wide. WS track RL/LR
B039 2:46
1 Slider - wide. Side WS
C005 2:46
2 A120 2:53 second take, not circled
2 B039 2:53
2 C005 2:53
"""


def records_for(text, slate, take):
    return [
        r for r in parse_scripte_detailed_editor_log_text(text)
        if r.slate == slate and r.take_id == take
    ]


def test_a_circled_take_is_circled_on_every_camera():
    rows = records_for(THREE_CAMERA_TAKE, "27/7", "1")
    assert len(rows) == 3, "one take on three cameras should produce three rows"
    assert {r.camera_roll for r in rows} == {"A120", "B039", "C005"}
    assert all(r.is_starred for r in rows), "the circle belongs to the take, not to camera A"


def test_a_take_that_was_not_circled_stays_uncircled():
    """The unification must not spread a mark to takes that never carried it."""
    rows = records_for(THREE_CAMERA_TAKE, "27/7", "2")
    assert len(rows) == 3
    assert not any(r.is_starred for r in rows)


def test_no_take_disagrees_with_itself():
    """
    The condition the reconciliation engine actually reacts to: the same take
    described twice with different marks, inside a single document.
    """
    by_take = {}
    for r in parse_scripte_detailed_editor_log_text(THREE_CAMERA_TAKE):
        by_take.setdefault((r.slate, r.take_id), set()).add(r.is_starred)
    conflicted = {k: v for k, v in by_take.items() if len(v) > 1}
    assert conflicted == {}


# --------------------------------------------------------------------------- #
# The helper on its own
# --------------------------------------------------------------------------- #

class FakeRecord:
    def __init__(self, slate, take_id, **flags):
        self.slate = slate
        self.take_id = take_id
        for name in ("is_starred", "is_pickup", "is_false_start",
                     "is_wild_track", "is_vfx", "is_mos"):
            setattr(self, name, flags.get(name, False))


def test_marks_spread_across_rows_of_one_take():
    rows = [
        FakeRecord("27/7", "1", is_starred=True),
        FakeRecord("27/7", "1"),
        FakeRecord("27/7", "1", is_vfx=True),
    ]
    unify_take_level_marks(rows)
    assert all(r.is_starred for r in rows)
    assert all(r.is_vfx for r in rows)


def test_marks_do_not_leak_between_different_takes():
    rows = [FakeRecord("27/7", "1", is_starred=True), FakeRecord("27/7", "2")]
    unify_take_level_marks(rows)
    assert rows[0].is_starred and not rows[1].is_starred


def test_marks_do_not_leak_between_different_slates():
    rows = [FakeRecord("27/7", "1", is_starred=True), FakeRecord("27/8", "1")]
    unify_take_level_marks(rows)
    assert rows[0].is_starred and not rows[1].is_starred


def test_records_without_an_identity_are_left_alone():
    rows = [FakeRecord(None, None, is_starred=True), FakeRecord("27/7", None)]
    unify_take_level_marks(rows)
    assert rows[0].is_starred and not rows[1].is_starred


# --------------------------------------------------------------------------- #
# A lined page may assert circled, never uncircled
# --------------------------------------------------------------------------- #

def _take_events(filename, text, doc_type):
    """Runs one document through the dispatcher and returns its take payloads."""
    from backend.app.streaming.bus import EventBus
    from backend.app.streaming.dispatcher import IngestionDispatcher
    from backend.app.streaming.models import AxisType, DepartmentType, EventEnvelope

    bus = EventBus()
    captured = []
    bus.subscribe("production.events.spine", lambda e: captured.append(e))
    IngestionDispatcher(bus=bus).handle_script_drop(
        EventEnvelope(
            production_id="P", shoot_day="31",
            axis=AxisType.BELIEF, department=DepartmentType.SCRIPT,
            doc_type=doc_type, raw_content=text, filename=filename,
        )
    )
    return [e["payload"] for e in captured if e.get("entity_type") == "take"]


def test_a_lined_page_reports_a_circle_it_can_see():
    from backend.app.streaming.models import DocumentType

    payloads = _take_events("LAC_Facing&Lined_D031.pdf", THREE_CAMERA_TAKE, DocumentType.SCRIPT_LINED)
    take1 = [p for p in payloads if p["slate"] == "27/7" and p["take_id"] == "1"]
    assert take1, "the circled take should still be reported"
    assert all(p["is_starred"] is True for p in take1)


def test_a_lined_page_makes_no_claim_about_an_unmarked_take():
    """
    The circles are ink. No asterisk in the text layer means the drawing did
    not reach us, not that the supervisor left the take uncircled. None is
    "no claim", and the reconciliation engine skips it.
    """
    from backend.app.streaming.models import DocumentType

    payloads = _take_events("LAC_Facing&Lined_D031.pdf", THREE_CAMERA_TAKE, DocumentType.SCRIPT_LINED)
    take2 = [p for p in payloads if p["slate"] == "27/7" and p["take_id"] == "2"]
    assert take2
    assert all(p["is_starred"] is None for p in take2), "silence must not read as a denial"
    assert not any(p["is_starred"] is False for p in take2)


def test_other_script_documents_still_deny_a_circle():
    """
    A timecode log is a typed record: it lists every take, so an unmarked take
    there is a genuine statement that the take was not circled. Only the lined
    page abstains.
    """
    from backend.app.streaming.models import DocumentType

    # An editor's log filename, so the same parser runs and only the document
    # kind differs from the lined-page case above.
    payloads = _take_events("LAC_DetailedEditorsLog_D031.pdf", THREE_CAMERA_TAKE, DocumentType.SCRIPT_TIMECODE)
    take2 = [p for p in payloads if p["slate"] == "27/7" and p["take_id"] == "2"]
    assert take2
    assert all(p["is_starred"] is False for p in take2)


def test_an_abstaining_witness_raises_no_conflict():
    """The end the user sees: no discrepancy between a claim and a non-claim."""
    from backend.app.reconciliation.engine import ReconciliationEngine

    witnesses = [
        {"department": "script", "doc_type": "script_timecode",
         "source_document": "TCLog.pdf", "is_starred": True},
        {"department": "script", "doc_type": "script_lined",
         "source_document": "Facing&Lined.pdf", "is_starred": None},
    ]
    discs = ReconciliationEngine().reconcile_take_witnesses(
        production_id="P", shoot_day="31", slate="27/7", take_id="1", witnesses=witnesses,
    )
    assert not [d for d in discs if "circled" in d.description.lower()]


def test_two_documents_that_both_deny_still_conflict_with_one_that_asserts():
    """Abstention must not disable the check for documents that do testify."""
    from backend.app.reconciliation.engine import ReconciliationEngine

    witnesses = [
        {"department": "script", "doc_type": "script_timecode",
         "source_document": "TCLog.pdf", "is_starred": True},
        {"department": "script", "doc_type": "script_timecode",
         "source_document": "EditorsLog.pdf", "is_starred": False},
    ]
    discs = ReconciliationEngine().reconcile_take_witnesses(
        production_id="P", shoot_day="31", slate="27/7", take_id="1", witnesses=witnesses,
    )
    assert [d for d in discs if "circled" in d.description.lower()]


# --------------------------------------------------------------------------- #
# The day a take is filed under
# --------------------------------------------------------------------------- #

FACING_PAGE_OTHER_DAY = """
DETAILED EDITOR'S LOG 28/07/2026
119/5 1 Scene(s): 117 A046 300626 0:34
Shot on Day: Day 11
Sticks - cu. H/A CU Emily
117/1 1 Scene(s): 117 A122 280726 3:39
Shot on Day: Day 31
Dolly - med. Thomas enters LR
"""


def test_a_take_is_filed_under_the_day_the_document_says_it_was_shot():
    """
    Uploaded against day 31, but the page says 119/5 was shot on Day 11. Filed
    under 31 it would be reconciled against witnesses from a day it was never
    shot on, and could only disagree with them.
    """
    from backend.app.streaming.bus import EventBus
    from backend.app.streaming.dispatcher import IngestionDispatcher
    from backend.app.streaming.models import AxisType, DepartmentType, DocumentType, EventEnvelope

    bus = EventBus()
    captured = []
    bus.subscribe("production.events.spine", lambda e: captured.append(e))
    IngestionDispatcher(bus=bus).handle_script_drop(
        EventEnvelope(
            production_id="P", shoot_day="31",
            axis=AxisType.BELIEF, department=DepartmentType.SCRIPT,
            doc_type=DocumentType.SCRIPT_LINED,
            raw_content=FACING_PAGE_OTHER_DAY,
            filename="LAC_Facing&Lined_D031.pdf",
        )
    )
    filed = {(e["payload"]["slate"], e["shoot_day"]) for e in captured}
    assert ("119/5", "11") in filed
    assert ("119/5", "31") not in filed
    assert ("117/1", "31") in filed


def test_a_take_whose_day_is_unstated_keeps_the_day_it_was_uploaded_against():
    from backend.app.streaming.bus import EventBus
    from backend.app.streaming.dispatcher import IngestionDispatcher
    from backend.app.streaming.models import AxisType, DepartmentType, DocumentType, EventEnvelope

    bus = EventBus()
    captured = []
    bus.subscribe("production.events.spine", lambda e: captured.append(e))
    IngestionDispatcher(bus=bus).handle_script_drop(
        EventEnvelope(
            production_id="P", shoot_day="31",
            axis=AxisType.BELIEF, department=DepartmentType.SCRIPT,
            doc_type=DocumentType.SCRIPT_TIMECODE,
            raw_content=THREE_CAMERA_TAKE, filename="LAC_TCLog_D031.pdf",
        )
    )
    assert captured and all(e["shoot_day"] == "31" for e in captured)
