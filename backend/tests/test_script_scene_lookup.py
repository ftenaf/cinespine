"""
Reading the script behind a slate.

Two claims are made here and they are not equally strong. Which scene a slate
belongs to is read straight off the slate and is exact. Where inside the scene
a shot sits is inferred from the words the script supervisor wrote, and the
tests below are as much about what that inference refuses to claim as about
what it finds.
"""
import pytest

from backend.app.script.scene_lookup import (
    build_scene_context,
    locate_passage,
    scene_heading_span,
    scene_numbers_for_target,
)

SCENE_BODY = """119 INT. GREAT HALL - NAVE - DAY

Colossal gothic arches soar into the gloom. Dust hangs in the light.

LEAD sits at the pipe organ console, hands hovering over the stops.

LEAD
If the cadence fails, the sanctuary falls with it.

He strikes a heavy C-minor chord that reverberates through the columns.

From the narthex, SUPPORT emerges clutching a leather dossier.
"""


# --------------------------------------------------------------------------- #
# Which scene a target belongs to
# --------------------------------------------------------------------------- #

def test_a_shots_scene_is_the_half_of_the_slate_before_the_shot():
    assert scene_numbers_for_target("shot", "119/5") == ["119"]


def test_a_compound_slate_belongs_to_every_scene_it_covers():
    """
    41+122A/4 is one setup that plays in two scenes. An editor needs both
    pages, and picking one would quietly hide the other.
    """
    assert scene_numbers_for_target("shot", "41+122A/4") == ["41", "122A"]


def test_a_wild_track_belongs_to_its_scene():
    assert scene_numbers_for_target("shot", "27WT") == ["27"]


def test_a_scene_target_is_already_the_scene():
    assert scene_numbers_for_target("scene", "119") == ["119"]


def test_a_compound_scene_target_splits_the_same_way():
    assert scene_numbers_for_target("scene", "41+122A") == ["41", "122A"]


def test_a_slate_with_a_take_suffix_still_resolves():
    assert scene_numbers_for_target("shot", "119/5T03") == ["119"]


def test_a_scene_number_keeps_its_leading_zeros():
    """'007' and '7' are different labels; the script decides which it uses."""
    assert scene_numbers_for_target("scene", "007") == ["007"]


@pytest.mark.parametrize("target_id", ["", "   ", "???"])
def test_an_unreadable_target_resolves_to_no_scene(target_id):
    assert scene_numbers_for_target("shot", target_id) == []


# --------------------------------------------------------------------------- #
# Where inside the scene a shot sits
# --------------------------------------------------------------------------- #

def test_a_description_finds_the_passage_it_describes():
    match = locate_passage(SCENE_BODY, "LEAD at the organ console")
    assert match is not None
    assert "console" in SCENE_BODY[match["start"]:match["end"]]


def test_a_match_reports_the_words_it_matched_on():
    """
    The match is a guess, so it has to show its evidence. A highlight nobody
    can check is a highlight nobody should trust.
    """
    match = locate_passage(SCENE_BODY, "LEAD strikes the C-minor chord")
    assert match is not None
    assert "chord" in match["terms"]
    assert 0 < match["score"] <= 1


def test_a_description_of_something_not_in_the_scene_matches_nothing():
    match = locate_passage(SCENE_BODY, "helicopter lands on the motorway bridge")
    assert match is None


def test_camera_shorthand_alone_never_locates_a_passage():
    """
    'CU on take 3' says how it was shot, not what it was. Anchoring on those
    words would point at whichever line happened to share one.
    """
    assert locate_passage(SCENE_BODY, "CU take 3 circled, tail slate") is None


def test_a_note_of_only_stopwords_matches_nothing():
    assert locate_passage(SCENE_BODY, "and then the with of it") is None


def test_one_distinctive_word_is_enough_to_anchor():
    """A word that appears once in a scene points at one place in it."""
    match = locate_passage(SCENE_BODY, "narthex")
    assert match is not None
    assert "narthex" in SCENE_BODY[match["start"]:match["end"]]


def test_a_long_noisy_note_still_places_the_passage_it_names():
    """
    A real note is mostly card numbers, timecodes and running times, and the
    handful of words that describe the shot are a small fraction of it.
    Requiring the passage to cover most of the note's wording would reject
    every note the reports actually contain.
    """
    note = (
        "Slider - wide C005 280726 2:46 3 09:38:40 Scene(s): 27 "
        "ORGAN - LEAD plays -> He sees SUPPORT A120 280726 2:53 1"
    )
    match = locate_passage(SCENE_BODY, note)
    assert match is not None
    assert "organ" in match["terms"]
    assert "organ" in SCENE_BODY[match["start"]:match["end"]].lower()


def test_two_words_that_are_everywhere_do_not_add_up_to_a_match():
    """
    Weight, not count: words that appear all over the scene say nothing about
    where in it to look, however many of them there are.
    """
    body = (
        "LEAD walks and SUPPORT waits.\n"
        "LEAD stops and SUPPORT waits.\n"
        "LEAD turns and SUPPORT waits.\n"
    )
    assert locate_passage(body, "LEAD and SUPPORT") is None


def test_one_word_that_is_everywhere_anchors_nothing():
    match = locate_passage("LEAD walks.\nLEAD stops.\nLEAD turns.\n", "LEAD")
    assert match is None


def test_an_empty_scene_matches_nothing():
    assert locate_passage("", "LEAD at the organ") is None


# --------------------------------------------------------------------------- #
# The context handed to the reader
# --------------------------------------------------------------------------- #

def test_a_scene_highlights_all_of_itself():
    context = build_scene_context({"body": SCENE_BODY, "scene_number": "119"}, "scene")
    assert context["highlight_basis"] == "scene"
    assert context["highlight"]["end"] == len(SCENE_BODY)


def test_a_scene_highlight_starts_below_the_slug_line():
    """The heading labels the scene; it is not what happens in it."""
    context = build_scene_context({"body": SCENE_BODY, "scene_number": "119"}, "scene")
    highlighted = SCENE_BODY[context["highlight"]["start"]:]
    assert "INT. GREAT HALL" not in highlighted


def test_scene_heading_span_leaves_an_unheaded_scene_alone():
    body = "Rain falls on the plaza.\n"
    assert scene_heading_span(body) == 0


def test_a_shot_with_no_description_shows_the_whole_scene_and_says_why():
    context = build_scene_context({"body": SCENE_BODY, "scene_number": "119"}, "shot", hint=None)
    assert context["highlight"] is None
    assert context["highlight_basis"] == "none"
    assert "no description" in context["note"]


def test_a_shot_whose_description_matches_nothing_says_so_rather_than_guessing():
    context = build_scene_context(
        {"body": SCENE_BODY, "scene_number": "119"},
        "shot",
        hint="helicopter lands on the motorway bridge",
    )
    assert context["highlight"] is None
    assert "matched" in context["note"]


def test_a_shot_whose_description_matches_is_highlighted_on_that_basis():
    context = build_scene_context(
        {"body": SCENE_BODY, "scene_number": "119"},
        "shot",
        hint="SUPPORT enters with the dossier",
    )
    assert context["highlight_basis"] == "description"
    assert "dossier" in SCENE_BODY[context["highlight"]["start"]:context["highlight"]["end"]]


def test_a_scene_present_in_the_script_but_empty_is_reported_as_empty():
    context = build_scene_context({"body": "   ", "scene_number": "119"}, "scene")
    assert context["highlight"] is None
    assert "no text" in context["note"]
