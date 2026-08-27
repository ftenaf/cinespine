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
