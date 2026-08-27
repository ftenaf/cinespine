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

    def unreachable(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(ai_image_service.httpx, "AsyncClient", unreachable)

    result = asyncio.run(ai_image_service.generate_ai_cinematic_image(
        prompt="INT. RECORDING BOOTH - NIGHT", camera_letter="A",
    ))

    assert result["image_url"].startswith("/previz/")
    assert stored == {}, "a fallback must never be written to the cache"


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

    class _Image:
        image_bytes = b"\xff\xd8\xff\xe0 fake jpeg"

    class _Generated:
        image = _Image()

    class _Models:
        def generate_images(self, **kwargs):
            return type("R", (), {"generated_images": [_Generated()]})()

    class _Client:
        def __init__(self, **kwargs):
            self.models = _Models()

    import google.genai as genai
    monkeypatch.setattr(genai, "Client", _Client)

    result = asyncio.run(ai_image_service.generate_ai_cinematic_image(
        prompt="INT. RECORDING BOOTH - NIGHT", camera_letter="A",
    ))

    assert result["image_url"].startswith("data:image/jpeg;base64,")
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
