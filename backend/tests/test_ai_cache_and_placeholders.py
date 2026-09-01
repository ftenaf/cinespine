"""
Covers the two behaviours that made AI generation misreport itself: a cache that
stored failures, and placeholder selection keyed on one production's vocabulary.
"""
import asyncio

import pytest

from backend.app.script import ai_image_service, cache_service
from backend.app.script.storyboard_generator import detect_setting


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #

def test_cache_roundtrips_a_payload():
    key = cache_service.generate_hash(prompt="a wide shot", model="test")
    assert cache_service.get_cached_response(key) is None

    cache_service.set_cached_response(key, {"image_url": "data:image/jpeg;base64,AAAA"})
    assert cache_service.get_cached_response(key) == {"image_url": "data:image/jpeg;base64,AAAA"}


def test_cache_key_depends_on_every_argument():
    a = cache_service.generate_hash(prompt="wide", model="x")
    b = cache_service.generate_hash(prompt="wide", model="y")
    c = cache_service.generate_hash(prompt="tight", model="x")
    assert len({a, b, c}) == 3


def test_cache_honours_the_environment_at_call_time(tmp_path, monkeypatch):
    """
    Reading the path at call time is what lets the test fixture redirect it. If
    it were captured at import, this write would land in the developer's real db.
    """
    first = tmp_path / "one.db"
    monkeypatch.setenv("CINESPINE_CACHE_DB", str(first))
    key = cache_service.generate_hash(prompt="scoped")
    cache_service.set_cached_response(key, {"text": "stored in one.db"})
    assert first.exists()

    monkeypatch.setenv("CINESPINE_CACHE_DB", str(tmp_path / "two.db"))
    assert cache_service.get_cached_response(key) is None


def test_cache_does_not_leak_connections():
    """
    `with sqlite3.connect(...)` commits but does not close. Reading many times
    must not accumulate open handles.
    """
    key = cache_service.generate_hash(prompt="handles")
    cache_service.set_cached_response(key, {"text": "x"})
    for _ in range(200):
        assert cache_service.get_cached_response(key) == {"text": "x"}


def test_generation_failure_is_not_cached(monkeypatch):
    """
    The placeholder means every generator was unreachable, which is transient.
    Caching it would freeze the outage: the retry that fixes it never runs.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    stored = {}
    monkeypatch.setattr(
        ai_image_service, "set_cached_response",
        lambda h, p: stored.__setitem__(h, p),
    )

    result = asyncio.run(ai_image_service.generate_ai_cinematic_image(
        prompt="INT. RECORDING BOOTH - NIGHT", camera_letter="A",
    ))

    assert result["image_url"].startswith("/previz/")
    assert stored == {}, "a fallback must never be written to the cache"


def test_a_placeholder_says_why_it_is_a_placeholder(monkeypatch):
    """
    The button says "Execute & Render AI Concept". When nothing rendered, the
    payload has to say so -- this fell through silently on any non-200 answer
    and served a bundled still with nothing anywhere marking it as one.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-used")
    monkeypatch.setattr(ai_image_service, "get_cached_response", lambda h: None)
    monkeypatch.setattr(ai_image_service, "image_models", lambda: ["model-x", "model-y"])

    async def refused(model, api_key, compiled_prompt):
        raise RuntimeError(f"429 from {model}")

    monkeypatch.setattr(ai_image_service, "_generate_with", refused)

    result = asyncio.run(ai_image_service.generate_ai_cinematic_image(
        prompt="INT. RECORDING BOOTH - NIGHT", camera_letter="A",
    ))

    assert result["image_url"].startswith("/previz/")
    assert "Placeholder" in result["provider"]
    assert [f.split(":")[0] for f in result["generator_failures"]] == ["model-x", "model-y"]


def test_the_second_model_is_tried_when_the_first_declines(monkeypatch):
    """A list of models nothing ever falls through is a longer way to name one."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-used")
    monkeypatch.setattr(ai_image_service, "get_cached_response", lambda h: None)
    monkeypatch.setattr(ai_image_service, "set_cached_response", lambda h, p: None)
    monkeypatch.setattr(ai_image_service, "image_models", lambda: ["first", "second"])

    async def only_second(model, api_key, compiled_prompt):
        if model == "first":
            raise ai_image_service._NoImageReturned("I can't draw that")
        return {
            "image_url": "data:image/png;base64,AAAA",
            "compiled_prompt": compiled_prompt,
            "provider": f"Google Gemini image ({model})",
        }

    monkeypatch.setattr(ai_image_service, "_generate_with", only_second)

    result = asyncio.run(ai_image_service.generate_ai_cinematic_image(
        prompt="INT. RECORDING BOOTH - NIGHT", camera_letter="A",
    ))

    assert result["provider"] == "Google Gemini image (second)"


def test_a_real_generation_is_cached(monkeypatch):
    """The complement: a genuine result must be stored, or the cache is useless."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-used")

    stored = {}
    monkeypatch.setattr(
        ai_image_service, "set_cached_response",
        lambda h, p: stored.__setitem__(h, p),
    )
    monkeypatch.setattr(ai_image_service, "get_cached_response", lambda h: None)

    # generate_content, not generate_images: the SDK refuses the latter outside
    # Gemini Enterprise Agent Platform mode, which is how this shipped serving
    # a bundled still under a button that claims to render one.
    class _Blob:
        mime_type = "image/png"
        data = b"\x89PNG fake"

    class _Part:
        inline_data = _Blob()
        text = None

    class _Candidate:
        content = type("C", (), {"parts": [_Part()]})()

    class _Models:
        def generate_content(self, **kwargs):
            return type("R", (), {"candidates": [_Candidate()]})()

    class _Client:
        def __init__(self, **kwargs):
            self.models = _Models()

    import google.genai as genai
    monkeypatch.setattr(genai, "Client", _Client)

    result = asyncio.run(ai_image_service.generate_ai_cinematic_image(
        prompt="INT. RECORDING BOOTH - NIGHT", camera_letter="A",
    ))

    assert result["image_url"].startswith("data:image/png;base64,")
    assert result["provider"].startswith("Google Gemini image (")
    assert len(stored) == 1


# --------------------------------------------------------------------------- #
# Placeholder selection
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("prompt, expected", [
    ("EXT. CITY SQUARE - DAY", "exterior"),
    ("INT. APARTMENT - NIGHT", "interior"),
    ("Exterior shot of a courtyard", "exterior"),
    ("Interior coverage of a dialogue scene", "interior"),
    ("Rain lashing a rooftop at sunset", "exterior"),
    ("Two people talking across a table", "interior"),
])
def test_setting_detection_uses_screenplay_convention(prompt, expected):
    assert detect_setting(prompt) == expected


def test_setting_detection_carries_no_production_vocabulary():
    """
    Selection previously keyed on one production's nouns and a character name,
    so any other script fell through to the same frame.
    """
    import inspect
    from backend.app.script import storyboard_generator

    source = inspect.getsource(storyboard_generator)
    for token in ("great_hall", "nave", "sanctuary", "vance", "commander", "organ"):
        assert token not in source.lower(), f"production-specific token {token!r} is back"


def test_placeholder_path_is_always_a_bundled_asset():
    for prompt in ["EXT. ROAD - DAY", "INT. VAN - NIGHT", "", "???"]:
        for cam in ["A", "B", "C", "D", "", "z"]:
            path = ai_image_service._placeholder_asset(prompt, cam)
            assert path.startswith("/previz/")
            assert path.endswith(".jpg")
            assert any(s in path for s in ("interior", "exterior"))
            assert path[-5] in "abc"
