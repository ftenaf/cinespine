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
