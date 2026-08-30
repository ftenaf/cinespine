"""
A character's personality, scored from the script, and the lines behind it.

Two things that only work together. The polygon is a reading; the lines are
what it rests on. A reading nobody can check against the script is an assertion
with a chart around it.

The hard part is the gap. Everywhere else in character inference the model is
told to decide and commit -- a costume has to be built and a face rendered, and
"unknown" cannot be photographed. A personality score is different: a character
with four lines does not contain five readings, and a confident number with
nothing behind it is worse than an empty axis.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.script.character_ai import (
    AXIS_KEYS,
    INFERRED_FIELDS,
    PERSONALITY_AXES,
    _coerce_personality_axes,
)

client = TestClient(app)

SCRIPT = """Title: The Cadence

INT. GREAT HALL - NAVE - DAY

Colossal gothic arches soar into the gloom.

LEAD (30s), haggard, sits at the pipe organ console.

LEAD
(whispering to himself)
If the cadence fails, the sanctuary falls with it.

He strikes a chord.

LEAD
Then let them hear what they came to destroy.

SILENT MONK watches from the transept and says nothing.

EXT. CLOISTER - NIGHT

LEAD
I will not play it again.
"""


# --------------------------------------------------------------------------- #
# The axes themselves
# --------------------------------------------------------------------------- #

def test_there_are_five_axes_and_they_are_fixed():
    """
    The point of a polygon is comparison, and two characters are only
    comparable at a glance if their axes sit in the same places.
    """
    assert len(PERSONALITY_AXES) == 5
    assert len(AXIS_KEYS) == 5
    assert len(set(AXIS_KEYS)) == 5


def test_the_axes_are_a_named_framework_not_invented_ones():
    """
    Five dimensions made up for this app would be pseudo-psychology with a
    chart around it, and nobody could say what a score meant.
    """
    assert set(AXIS_KEYS) == {
        "openness", "conscientiousness", "extraversion",
        "agreeableness", "emotional_volatility",
    }


def test_the_axes_are_an_inferred_field():
    assert "personality_axes" in INFERRED_FIELDS


def test_every_axis_carries_a_label_and_a_description():
    for key, label, blurb in PERSONALITY_AXES:
        assert key and label and blurb
        assert len(blurb) > 20, f"{key} has no usable description"


# --------------------------------------------------------------------------- #
# A score the script does not support stays empty
# --------------------------------------------------------------------------- #

def test_a_scored_axis_keeps_its_score_and_evidence():
    axes = _coerce_personality_axes({
        "openness": {"score": 72, "evidence": "improvises a new cadence"},
    })
    assert axes["openness"] == {"score": 72, "evidence": "improvises a new cadence"}


def test_an_axis_the_model_left_out_is_null_not_zero():
    """
    The whole point. Zero draws a point at the centre of the radar, which reads
    as "none of this trait" -- a claim nobody made. Absence rendered as
    presence.
    """
    axes = _coerce_personality_axes({"openness": {"score": 72, "evidence": "x"}})
    assert axes["agreeableness"]["score"] is None
    assert axes["agreeableness"]["score"] != 0


@pytest.mark.parametrize("bad", [140, -10, "high", None, True])
def test_a_score_that_is_not_a_score_is_dropped_rather_than_clamped(bad):
    """
    A model returning 140 has not understood the scale. Clamping to 100 turns
    a broken answer into a confident one.
    """
    axes = _coerce_personality_axes({
        "openness": {"score": bad, "evidence": "x"},
        "extraversion": {"score": 50, "evidence": "y"},
    })
    assert axes["openness"]["score"] is None


def test_evidence_is_dropped_with_the_score_it_explained():
    axes = _coerce_personality_axes({
        "openness": {"score": 999, "evidence": "improvises a new cadence"},
        "extraversion": {"score": 50, "evidence": "y"},
    })
    assert axes["openness"]["evidence"] is None, (
        "evidence survived for a score nobody can see"
    )


def test_nothing_scored_at_all_stores_nothing():
    """Five nulls say the same as no field, and no field is cheaper to reason about."""
    assert _coerce_personality_axes({k: {"score": None} for k in AXIS_KEYS}) is None
    assert _coerce_personality_axes({}) is None
    assert _coerce_personality_axes("high openness") is None


def test_the_prompt_tells_the_model_the_axes_may_be_empty():
    """
    Rule 2 of the character prompt says never say a detail is unknown, because
    a costume has to be built. The axes need the opposite instruction, and it
    has to be in the prompt or the model will obey the rule above it.
    """
    import inspect

    from backend.app.script import character_ai

    source = inspect.getsource(character_ai)
    assert "THE AXES ARE THE ONE EXCEPTION TO RULE 2" in source
    assert '{"score": null, "evidence": null}' in source


def test_the_prompt_scores_the_character_not_the_actor():
    import inspect

    from backend.app.script import character_ai

    source = inspect.getsource(character_ai)
    assert "never the actor who might play them" in source


# --------------------------------------------------------------------------- #
# The lines behind the reading
# --------------------------------------------------------------------------- #

@pytest.fixture
def script_id():
    res = client.post("/api/script/parse", json={"script_text": SCRIPT, "title": "The Cadence"})
    assert res.status_code == 200, res.text
    return res.json()["script_id"]


def lines_for(script_id, name):
    res = client.get(f"/api/script/{script_id}/characters/{name}/lines")
    assert res.status_code == 200, res.text
    return res.json()


def test_a_characters_lines_come_back_in_script_order(script_id):
    body = lines_for(script_id, "LEAD")
    assert body["line_count"] == 3
    assert [l["line"] for l in body["lines"]] == [
        "If the cadence fails, the sanctuary falls with it.",
        "Then let them hear what they came to destroy.",
        "I will not play it again.",
    ]


def test_each_line_says_where_to_find_it(script_id):
    """Without the scene a line is a quotation; with it, it is navigable."""
    first = lines_for(script_id, "LEAD")["lines"][0]
    assert first["scene_number"]
    assert "GREAT HALL" in first["heading"]


def test_a_parenthetical_is_kept_apart_from_the_line(script_id):
    """
    "(whispering to himself)" is a direction, not something the character says.
    Folding it into the line would put words in their mouth.
    """
    first = lines_for(script_id, "LEAD")["lines"][0]
    assert first["parenthetical"] == "whispering to himself"
    assert "whispering" not in first["line"]


def test_it_names_the_scenes_the_character_speaks_in(script_id):
    body = lines_for(script_id, "LEAD")
    assert len(body["scenes_present"]) == 2


def test_a_character_who_never_speaks_is_not_the_same_as_an_unknown_one(script_id):
    """
    Two different facts that an empty list cannot tell apart. Telling a
    director "no lines" about a character the script does not contain sends
    them looking for the wrong thing.
    """
    silent = lines_for(script_id, "SILENT MONK")
    assert silent["known_character"] is True, (
        "a character named in action but never speaking read as not in the script"
    )
    assert silent["has_profile"] is False, (
        "profiles come from dialogue cues, so a silent character has none"
    )
    assert silent["line_count"] == 0

    absent = lines_for(script_id, "NOBODY")
    assert absent["known_character"] is False
    assert absent["has_profile"] is False
    assert absent["line_count"] == 0


def test_a_lowercase_word_is_not_a_character(script_id):
    """
    Matching is case-sensitive because screenplays name people in action in
    caps. "the lead" in prose is the English word, and treating it as the
    character would say somebody appears in a scene they are not in.
    """
    assert lines_for(script_id, "gloom")["known_character"] is False
    assert lines_for(script_id, "arches")["known_character"] is False


def test_an_unknown_script_is_a_404():
    res = client.get("/api/script/nosuchscript/characters/LEAD/lines")
    assert res.status_code == 404
