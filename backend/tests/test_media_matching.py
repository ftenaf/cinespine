"""
Matching a DIT media file to a take.

The failure mode here is over-matching, which does not look like an error: a
clip attached to the wrong take renders exactly like a clip attached to the
right one, so a take card fills up with clips that are not its own.
"""
import pytest

from backend.app.api.routes import is_take_media_match


def clip(**overrides):
    base = {
        "file_name": "A_0121C004_260728_131831_h1EIC.mxf",
        "scene": "49",
        "shot": "49/6",
        "take_id": "1",
        "camera_roll": "A121",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# A camera roll is necessary, never sufficient
# --------------------------------------------------------------------------- #

def test_a_clip_belongs_only_to_its_own_shot():
    assert is_take_media_match(clip(), "49/6", "1", "A121", None) is True


@pytest.mark.parametrize("slate", ["49/1", "49/5", "49/7", "49/99"])
def test_a_shared_roll_does_not_attach_a_clip_to_every_slate(slate):
    """
    One roll spans many slates and takes, so roll agreement cannot stand in for
    a shot match. It used to, which put the same twelve clips on 49/5 and 49/6.
    """
    assert is_take_media_match(clip(), slate, "1", "A121", None) is False


def test_a_different_roll_disqualifies_an_otherwise_perfect_match():
    assert is_take_media_match(clip(), "49/6", "1", "B040", None) is False


# --------------------------------------------------------------------------- #
# A shot that merely repeats the scene identifies nothing
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("slate", ["49/1", "49/5", "49/6", "49/9"])
def test_a_bare_scene_as_shot_does_not_claim_every_slate(slate):
    """
    Silverstack frequently writes the shot as the bare scene number. Treated as
    a shot match, one clip attached to every slate in the scene.
    """
    assert is_take_media_match(clip(shot="49"), slate, "1", "A121", None) is False


def test_a_clip_named_by_the_camera_report_is_still_claimed():
    """
    Declining to guess must not lose a clip the paperwork names outright: the
    camera report's clip name is direct evidence, not an inference.
    """
    assert is_take_media_match(clip(shot="49"), "49/5", "1", "A121", "A121_C004") is True


def test_scene_and_take_suffice_when_neither_side_names_a_shot():
    """Nothing is being guessed: it is all the evidence either side carries."""
    assert is_take_media_match(clip(shot=None), "49", "1", "A121", None) is True
    assert is_take_media_match(clip(shot="49"), "49", "1", "A121", None) is True


# --------------------------------------------------------------------------- #
# Shot notations that do identify a slate still match
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("recorded_shot", ["49/6", "6", "49-49/6"])
def test_shot_notations_that_name_the_slate_are_honoured(recorded_shot):
    assert is_take_media_match(clip(shot=recorded_shot), "49/6", "1", "A121", None) is True


def test_a_different_take_never_matches():
    assert is_take_media_match(clip(), "49/6", "2", "A121", None) is False
