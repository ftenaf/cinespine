"""
Tests for AI-inferred character profiles.

The Gemini call itself is faked. What matters here is that evidence is gathered
from the right places, that a model response is parsed and validated safely, and
that every failure path leaves the screenplay usable rather than raising.
"""
import asyncio

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
        return """[
          {"name": "MAYA", "role": "Lead / Reluctant Operator",
           "actor_reference": "Early 30s woman, wiry build",
           "look_and_costume": "Oil-stained field jacket",
           "facial_features": "Angular face, grey eyes",
           "personality_traits": ["Tenacious", "Wry"]},
          {"name": "DANIEL", "role": "Ally / Field Contact",
           "actor_reference": "Late 30s man, broad shoulders",
           "look_and_costume": "Soaked canvas parka",
           "facial_features": "Heavy brow, three-day stubble",
           "personality_traits": ["Loyal"]}
        ]"""

    monkeypatch.setattr(character_ai, "_call_gemini", fake)
    result = asyncio.run(character_ai.enrich_screenplay_characters(screenplay))

    maya = next(c for c in result.characters if c.name == "MAYA")
    assert maya.role == "Lead / Reluctant Operator"
    assert maya.actor_reference == "Early 30s woman, wiry build"
    assert maya.look_and_costume == "Oil-stained field jacket"
    assert maya.facial_features == "Angular face, grey eyes"
    assert maya.personality_traits == ["Tenacious", "Wry"]
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
