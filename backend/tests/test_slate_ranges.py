"""
The slate ranges Office states, used as the completeness check they are.

A daily production report says `Slates: 27/7 - 8, 49/1 - 9, 117/1 - 5`. That is
Office stating which slates the day produced, and it is the only expected
extent anything in the day carries -- so it is the only thing that can notice a
slate which should not exist. The ranges were parsed and on the spine, and
nothing read them.

The hard half is what must stay silent. Office not stating a range for a scene
says nothing about that scene, and turning that silence into a finding would be
the failure mode this project calls absence rendered as presence.
"""
import pytest

from backend.app.reconciliation.engine import ReconciliationEngine, _scene_and_shot, _shot_number
from backend.app.reconciliation.models import DiscrepancyType, Severity

PROD = "SLATES"

RANGES = [
    {"scene": "27", "first": "27/7", "last": "27/8", "raw": "27/7 - 8"},
    {"scene": "49", "first": "49/1", "last": "49/9", "raw": "49/1 - 9"},
    {"scene": "117", "first": "117/1", "last": "117/5", "raw": "117/1 - 5"},
]


@pytest.fixture
def engine():
    return ReconciliationEngine()


def found(engine, slates, ranges=RANGES):
    return engine.reconcile_slate_ranges(
        production_id=PROD, shoot_day="31", slate_ranges=ranges, logged_slates=slates,
    )


# --------------------------------------------------------------------------- #
# Reading a slate
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("slate,expected", [
    ("27/7", ("27", 7)),
    ("117/5", ("117", 5)),
    ("64A/1", ("64A", 1)),
    ("27-7", ("27", 7)),
    # A wild track has a scene and no shot number. That is an answer, not a
    # parse failure: it is not on the number line a range runs along.
    ("49/WT", ("49", None)),
    ("", (None, None)),
])
def test_a_slate_splits_into_a_scene_and_a_shot(slate, expected):
    assert _scene_and_shot(slate) == expected


@pytest.mark.parametrize("raw,expected", [("27/8", 8), ("8", 8), ("", None)])
def test_a_range_endpoint_reads_either_way(raw, expected):
    """`27/7 - 8` gives a full slate at one end and a bare number at the other."""
    assert _shot_number(raw) == expected


# --------------------------------------------------------------------------- #
# What is reported
# --------------------------------------------------------------------------- #

def test_a_slate_past_the_end_of_the_range_is_reported(engine):
    d = found(engine, ["27/9"])
    assert len(d) == 1
    assert d[0].discrepancy_type == DiscrepancyType.SLATE_OUTSIDE_STATED_RANGE
    assert d[0].entity_id == "27/9"
    assert d[0].entity_type == "shot"


def test_a_slate_before_the_start_is_reported_too(engine):
    assert [x.entity_id for x in found(engine, ["27/3"])] == ["27/3"]


def test_it_names_both_witnesses(engine):
    """
    Either the slate is wrong or the range is short, and the finding cannot say
    which. It carries what each side said so a person can.
    """
    d = found(engine, ["27/9"])[0]
    claims = {w["claim"] for w in d.witnesses}
    assert claims == {"slate_range", "slate_recorded"}
    assert d.severity == Severity.WARNING


def test_a_slate_inside_the_range_says_nothing(engine):
    assert found(engine, ["27/7", "27/8", "49/1", "49/9", "117/3"]) == []


def test_each_slate_is_reported_once(engine):
    assert len(found(engine, ["27/9", "27/9", "27/9"])) == 1


# --------------------------------------------------------------------------- #
# What must stay silent
# --------------------------------------------------------------------------- #

def test_a_scene_with_no_stated_range_is_not_judged(engine):
    """
    The important negative. Office writing no range for scene 64 says nothing
    whatever about scene 64's slates; reading it as "no slates expected" would
    turn silence into denial and make every slate of an unlisted scene a
    finding.
    """
    assert found(engine, ["64A/1", "64A/2", "72/1"]) == []


def test_a_wild_track_is_not_outside_anything(engine):
    """A range runs between two numbers and a wild track is not one."""
    assert found(engine, ["49/WT", "49WT"]) == []


def test_a_report_with_no_ranges_makes_no_findings(engine):
    """
    A Slates field that was missing or unreadable must not turn every slate on
    the day into a discrepancy.
    """
    assert found(engine, ["27/9", "49/12", "117/8"], ranges=[]) == []
    assert found(engine, ["27/9"], ranges=None) == []


def test_an_unreadable_range_is_skipped_rather_than_guessed(engine):
    """
    One range that did not parse must not take the others down with it, and
    must not be filled in with a default.
    """
    ranges = [
        {"scene": "27", "first": "27/7", "last": "27/8"},
        {"scene": "49", "first": "", "last": ""},
    ]
    assert [x.entity_id for x in found(engine, ["27/9", "49/50"], ranges)] == ["27/9"]


def test_a_reversed_range_still_reads_correctly(engine):
    ranges = [{"scene": "27", "first": "27/8", "last": "27/7"}]
    assert found(engine, ["27/7", "27/8"], ranges) == []
    assert [x.entity_id for x in found(engine, ["27/9"], ranges)] == ["27/9"]


def test_a_compound_slate_is_not_matched_to_a_plain_scene(engine):
    """
    `41+122A/4` is its own scene reference, not scene 41. Treating it as 41
    would judge it against a range nobody stated for it.
    """
    ranges = [{"scene": "41", "first": "41/1", "last": "41/2"}]
    assert found(engine, ["41+122A/4"], ranges) == []
