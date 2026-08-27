"""
Shared pytest fixtures.
"""
import pytest


@pytest.fixture(autouse=True)
def isolated_character_db(tmp_path, monkeypatch):
    """
    Points the character profile store at a temporary database for every test.

    Without this, tests would read and write the developer's real spine.db,
    leaking state between runs and between tests.
    """
    monkeypatch.setenv("CINESPINE_DB_PATH", str(tmp_path / "test_spine.db"))
    yield


@pytest.fixture(autouse=True)
def isolated_ai_cache(tmp_path, monkeypatch):
    """
    Points the AI response cache at a temporary database for every test.

    Shares the reason above: without it a test run reads and writes the
    developer's real ai_cache.db, so one test can serve another a stale
    generated image and a cache hit can mask a broken generator.
    """
    monkeypatch.setenv("CINESPINE_CACHE_DB", str(tmp_path / "test_ai_cache.db"))
    yield


@pytest.fixture(autouse=True)
def no_live_ai_calls(monkeypatch):
    """
    Keeps the suite hermetic.

    backend/app/main.py loads .env, so once a developer has a real
    GEMINI_API_KEY every test touching /api/script/upload would make a live,
    billed call — roughly 25 seconds each, and failing offline. Tests that
    exercise inference opt back in by deleting this variable and stubbing
    _call_gemini.
    """
    monkeypatch.setenv("CINESPINE_DISABLE_AI_CHARACTER_INFERENCE", "1")
    yield


@pytest.fixture(autouse=True)
def reset_gcs_availability_cache():
    """
    The GCS integration caches "no credentials" for the life of the process to
    avoid a ~12s metadata-server probe per upload. Clear it between tests so one
    test's failure does not short-circuit another's client.
    """
    from backend.app.integrations import google_cloud

    google_cloud.reset_gcs_availability()
    yield
    google_cloud.reset_gcs_availability()
