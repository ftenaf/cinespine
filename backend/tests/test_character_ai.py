"""
Tests for AI-inferred character profiles.

The Gemini call itself is faked. What matters here is that evidence is gathered
from the right places, that a model response is parsed and validated safely, and
that every failure path leaves the screenplay usable rather than raising.
"""
import asyncio
import json

import pytest

from backend.app.script import character_ai
from backend.app.script.parser import parse_fountain_screenplay

SCRIPT = """THE LAST SIGNAL
Written by A. Writer

INT. RADIO STATION - NIGHT

Rain streaks the windows. MAYA CHEN, 30s, sits hunched over a console.

MAYA
(urgent)
Anyone out there? This is Kestrel Base.

DANIEL
Maya? Is that you?

EXT. ROOFTOP - CONTINUOUS

DANIEL crouches behind a vent.

DANIEL
They're jamming the north tower.
"""


@pytest.fixture
def screenplay():
    return parse_fountain_screenplay(SCRIPT, title="fallback")


def test_evidence_is_gathered_from_the_script(screenplay):
    evidence = character_ai.collect_character_evidence("MAYA", screenplay.scenes)

    assert evidence["name"] == "MAYA"
    assert any("Kestrel Base" in line for line in evidence["dialogue"])
    # Parentheticals carry performance intent and should reach the model.
    assert any("urgent" in line for line in evidence["dialogue"])
    # The introducing action line is the richest visual evidence available.
    assert any("MAYA CHEN, 30s" in line for line in evidence["action_lines"])
    assert any("RADIO STATION" in s for s in evidence["scenes"])

    # Another character's dialogue must not bleed into this one.
    assert not any("north tower" in line for line in evidence["dialogue"])


def test_prompt_covers_every_character(screenplay):
    prompt = character_ai.build_prompt(screenplay)
    for name in ("MAYA", "DANIEL"):
        assert name in prompt
    assert "THE LAST SIGNAL" in prompt
    assert "personality_traits" in prompt


def test_parses_a_well_formed_response():
    raw = """[
      {"name": "MAYA", "role": "Lead / Reluctant Operator",
       "actor_reference": "Early 30s woman, wiry build, dark cropped hair",
       "look_and_costume": "Oil-stained field jacket over wool sweater",
       "facial_features": "Angular face, grey eyes, rain-slick skin",
       "personality_traits": ["Tenacious", "Wry", "Guarded"]}
    ]"""
    parsed = character_ai.parse_ai_response(raw)

    assert parsed["MAYA"]["role"] == "Lead / Reluctant Operator"
    assert parsed["MAYA"]["personality_traits"] == ["Tenacious", "Wry", "Guarded"]


def test_parses_a_fenced_response():
    raw = '```json\n[{"name": "DANIEL", "role": "Ally"}]\n```'
    assert character_ai.parse_ai_response(raw)["DANIEL"]["role"] == "Ally"


def test_parses_an_array_wrapped_in_an_object():
    raw = '{"characters": [{"name": "DANIEL", "role": "Ally"}]}'
    assert character_ai.parse_ai_response(raw)["DANIEL"]["role"] == "Ally"


@pytest.mark.parametrize("raw", ["", "   ", "not json at all", "{}", "[]", '[{"role": "no name"}]'])
def test_unusable_responses_yield_nothing(raw):
    assert character_ai.parse_ai_response(raw) == {}


def test_unknown_keys_and_wrong_types_are_dropped():
    raw = """[{"name": "MAYA", "role": "Lead", "personality_traits": "not a list",
               "look_and_costume": 42, "injected_field": "ignore me"}]"""
    parsed = character_ai.parse_ai_response(raw)

    assert parsed["MAYA"] == {"role": "Lead"}
    assert "injected_field" not in parsed["MAYA"]
    assert "personality_traits" not in parsed["MAYA"]


def test_applies_only_to_matching_characters(screenplay):
    applied = character_ai.apply_inferred_profiles(
        screenplay,
        {
            "MAYA": {"role": "Lead", "facial_features": "Angular face, grey eyes"},
            "SOMEONE_ELSE": {"role": "Ghost"},
        },
    )
    assert applied == 1

    maya = next(c for c in screenplay.characters if c.name == "MAYA")
    daniel = next(c for c in screenplay.characters if c.name == "DANIEL")
    assert maya.role == "Lead"
    assert maya.facial_features == "Angular face, grey eyes"
    # Untouched characters keep their parser-derived profile.
    assert daniel.role != "Lead" or daniel.facial_features != "Angular face, grey eyes"


GOOD_ACTOR_REF = "Early 30s woman, wiry build, dark cropped hair, restless bearing"
GOOD_COSTUME = (
    "Navy quilted donkey jacket with cracked shoulder patches, oil-darkened cuffs, "
    "fingerless wool gloves, steel-toed boots worn white at the caps"
)
GOOD_FACE = (
    "Broad flat cheekbones, deep-set brown eyes under heavy lids, wind-chapped skin, "
    "a white scar through the left eyebrow"
)


@pytest.mark.parametrize("field,text", [
    ("actor_reference", "Late 40s woman with a distinctive, expressive screen presence"),
    ("actor_reference", "A striking, memorable figure"),
    ("look_and_costume", "Practical workwear suited to the dockside setting"),
    ("facial_features", "Striking features with cinematic catchlights"),
    ("facial_features", "Distinguishing facial features to be defined"),
    ("look_and_costume", "Wardrobe for Maya, consistent across 2 scene(s); refine to lock continuity"),
    ("actor_reference", ""),
    ("actor_reference", "   "),
])
def test_vague_descriptions_are_rejected(field, text):
    assert character_ai.is_vague(field, text) is True


@pytest.mark.parametrize("field,text", [
    ("actor_reference", GOOD_ACTOR_REF),
    ("actor_reference", "Late 40s, 5'6\", thickset shoulders, grey-streaked black hair in a short tail"),
    ("look_and_costume", GOOD_COSTUME),
    ("facial_features", GOOD_FACE),
    # role has no minimum: a short archetype is legitimate.
    ("role", "Lead / Reluctant Operator"),
])
def test_specific_descriptions_are_accepted(field, text):
    assert character_ai.is_vague(field, text) is False


def test_weak_characters_are_identified_per_field():
    weak = character_ai.find_vague_characters({
        "MAYA": {
            "actor_reference": GOOD_ACTOR_REF,
            "look_and_costume": "Practical clothing",
            "facial_features": GOOD_FACE,
        },
        "DANIEL": {
            "actor_reference": GOOD_ACTOR_REF,
            "look_and_costume": GOOD_COSTUME,
            "facial_features": GOOD_FACE,
        },
    })
    assert weak == {"MAYA": ["look_and_costume"]}
    assert "MAYA: look_and_costume" in character_ai.build_retry_feedback(weak)


def test_vague_output_triggers_one_targeted_retry(screenplay, monkeypatch):
    """A generic first response must be challenged, not accepted."""
    monkeypatch.delenv("CINESPINE_DISABLE_AI_CHARACTER_INFERENCE", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    calls = []

    def responder(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            return json.dumps([{
                "name": "MAYA",
                "actor_reference": "A striking, mysterious presence",
                "look_and_costume": "Suitable attire",
                "facial_features": "Expressive features",
            }])
        return json.dumps([{
            "name": "MAYA",
            "actor_reference": GOOD_ACTOR_REF,
            "look_and_costume": GOOD_COSTUME,
            "facial_features": GOOD_FACE,
        }])

    monkeypatch.setattr(character_ai, "_call_gemini", responder)
    result = asyncio.run(character_ai.enrich_screenplay_characters(screenplay))

    assert len(calls) == 2, "a vague first response should be retried once"
    assert "CORRECTION REQUIRED" in calls[1]
    assert "MAYA" in calls[1]

    maya = next(c for c in result.characters if c.name == "MAYA")
    assert maya.look_and_costume == GOOD_COSTUME
    assert maya.facial_features == GOOD_FACE


def test_specific_output_is_not_retried(screenplay, monkeypatch):
    """A good first response must not cost a second call."""
    monkeypatch.delenv("CINESPINE_DISABLE_AI_CHARACTER_INFERENCE", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    calls = []

    def responder(prompt):
        calls.append(prompt)
        return json.dumps([
            {"name": name, "actor_reference": GOOD_ACTOR_REF,
             "look_and_costume": GOOD_COSTUME, "facial_features": GOOD_FACE}
            for name in ("MAYA", "DANIEL")
        ])

    monkeypatch.setattr(character_ai, "_call_gemini", responder)
    result = asyncio.run(character_ai.enrich_screenplay_characters(screenplay))

    assert len(calls) == 1
    assert result.parse_warnings == []


def test_a_still_vague_retry_is_reported_not_silently_accepted(screenplay, monkeypatch):
    monkeypatch.delenv("CINESPINE_DISABLE_AI_CHARACTER_INFERENCE", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    monkeypatch.setattr(
        character_ai,
        "_call_gemini",
        lambda _p: json.dumps([{
            "name": "MAYA",
            "actor_reference": "A striking presence",
            "look_and_costume": "Suitable attire",
            "facial_features": "Expressive features",
        }]),
    )
    result = asyncio.run(character_ai.enrich_screenplay_characters(screenplay))

    assert any("stayed generic" in w and "MAYA" in w for w in result.parse_warnings)


def test_retry_failure_keeps_the_first_pass(screenplay, monkeypatch):
    """If the retry call blows up, the original answer is still used."""
    monkeypatch.delenv("CINESPINE_DISABLE_AI_CHARACTER_INFERENCE", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    calls = []

    def responder(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            return json.dumps([{
                "name": "MAYA",
                "role": "Lead / Operator",
                "actor_reference": "A striking presence",
            }])
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(character_ai, "_call_gemini", responder)
    result = asyncio.run(character_ai.enrich_screenplay_characters(screenplay))

    maya = next(c for c in result.characters if c.name == "MAYA")
    assert maya.role == "Lead / Operator"


def test_prompt_states_the_specificity_contract(screenplay):
    prompt = character_ai.build_prompt(screenplay)
    assert "Banned words" in prompt
    assert "cinematic" in prompt
    # A worked example is the strongest lever on output quality.
    assert "TOO VAGUE" in prompt and "CORRECT" in prompt
    assert "Differentiate the cast" in prompt


def test_prompt_pins_facts_stated_in_dialogue(screenplay):
    """
    Regression guard. Against the live model, an age stated in an action line
    ("INES MARCHETTI, 52") was honoured but one stated in dialogue ("He's
    twenty-three") came back as 24 on every run. The prompt has to say that
    dialogue is evidence too.
    """
    prompt = character_ai.build_prompt(screenplay)
    assert "stated in dialogue" in prompt
    assert "twenty-three" in prompt and "23" in prompt


def test_timeout_leaves_headroom_over_a_typical_call():
    """
    A timeout discards the entire inference. Measured round trips on a
    five-scene script were 22-27s, so the default must sit well clear of that.
    """
    assert character_ai.TIMEOUT_SECONDS >= 45


def test_disabled_inference_leaves_profiles_intact_and_says_so(screenplay, monkeypatch):
    monkeypatch.setenv("CINESPINE_DISABLE_AI_CHARACTER_INFERENCE", "1")
    before = screenplay.characters[0].actor_reference

    result = asyncio.run(character_ai.enrich_screenplay_characters(screenplay))

    assert result.characters[0].actor_reference == before
    assert any("script text only" in w for w in result.parse_warnings)


def test_inference_failure_never_breaks_the_upload(screenplay, monkeypatch):
    monkeypatch.delenv("CINESPINE_DISABLE_AI_CHARACTER_INFERENCE", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def explode(_prompt):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(character_ai, "_call_gemini", explode)
    before = screenplay.characters[0].actor_reference

    result = asyncio.run(character_ai.enrich_screenplay_characters(screenplay))

    assert result.characters[0].actor_reference == before
    assert any("unavailable" in w for w in result.parse_warnings)


def test_successful_inference_fills_the_four_profile_fields(screenplay, monkeypatch):
    monkeypatch.delenv("CINESPINE_DISABLE_AI_CHARACTER_INFERENCE", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def fake(_prompt):
        return json.dumps([
            {"name": "MAYA", "role": "Lead / Reluctant Operator",
             "actor_reference": GOOD_ACTOR_REF,
             "look_and_costume": GOOD_COSTUME,
             "facial_features": GOOD_FACE,
             "personality_traits": ["Tenacious", "Wry"]},
            {"name": "DANIEL", "role": "Ally / Field Contact",
             "actor_reference": "Late 30s man, broad through the shoulders, close-cropped ginger hair",
             "look_and_costume": "Soaked olive canvas parka with a torn hood seam, "
                                 "grey wool scarf doubled at the throat, cracked leather gloves",
             "facial_features": "Heavy brow, three-day stubble, chapped lips, pale blue eyes "
                                "set close together, a nose broken and badly reset",
             "personality_traits": ["Loyal"]},
        ])

    monkeypatch.setattr(character_ai, "_call_gemini", fake)
    result = asyncio.run(character_ai.enrich_screenplay_characters(screenplay))

    maya = next(c for c in result.characters if c.name == "MAYA")
    assert maya.role == "Lead / Reluctant Operator"
    assert maya.actor_reference == GOOD_ACTOR_REF
    assert maya.look_and_costume == GOOD_COSTUME
    assert maya.facial_features == GOOD_FACE
    assert maya.personality_traits == ["Tenacious", "Wry"]
    # Specific enough on the first pass: no retry, no warnings.
    assert result.parse_warnings == []


def test_user_edits_survive_reupload_with_inference(monkeypatch, tmp_path):
    """
    Inference runs before persistence, so a character the user has already
    polished keeps their edits when the script is uploaded again.
    """
    from starlette.testclient import TestClient
    from backend.app.main import app

    monkeypatch.setenv("CINESPINE_DISABLE_AI_CHARACTER_INFERENCE", "1")
    client = TestClient(app)
    files = {"file": ("plain.txt", SCRIPT.encode("utf-8"), "text/plain")}

    first = client.post("/api/script/upload", files=files).json()
    script_id = first["script_id"]
    maya = next(c for c in first["characters"] if c["name"] == "MAYA")

    client.post("/api/script/characters/update", json={
        "id": maya["id"], "name": "MAYA", "script_id": script_id,
        "look_and_costume": "Red raincoat, silver locket",
    })

    # Now enable inference and re-upload; the edit must still win.
    monkeypatch.delenv("CINESPINE_DISABLE_AI_CHARACTER_INFERENCE", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        character_ai,
        "_call_gemini",
        lambda _p: '[{"name": "MAYA", "look_and_costume": "AI suggested trench coat"}]',
    )

    again = client.post("/api/script/upload", files=files).json()
    maya_again = next(c for c in again["characters"] if c["name"] == "MAYA")
    assert maya_again["look_and_costume"] == "Red raincoat, silver locket"
