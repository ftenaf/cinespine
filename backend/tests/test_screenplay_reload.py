"""
A screenplay the backend stored can be asked for again, whole.

The Script Studio kept a loaded script only in the tab's memory: breakdowns
and profiles were restored per script, but nothing could fetch the script
itself, so a refresh emptied the studio.
"""
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)

SCRIPT = (
    "INT. KITCHEN - NIGHT\n\nMARA\nWe are out of time.\n\n"
    "EXT. STREET - DAY\n\nJONAS\nThen we walk.\n"
)


def test_a_stored_screenplay_comes_back_whole(isolated_character_db):
    parsed = client.post("/api/script/parse", json={"script_text": SCRIPT, "title": "Reload"}).json()
    script_id = parsed["script_id"]

    r = client.get(f"/api/script/{script_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["script_id"] == script_id
    assert body["title"] == "Reload"
    assert len(body["scenes"]) == len(parsed["scenes"]) == 2
    assert {c["name"] for c in body["characters"]} == {c["name"] for c in parsed["characters"]}
    assert body["parse_warnings"] == []


def test_an_unknown_script_is_a_404(isolated_character_db):
    assert client.get("/api/script/does-not-exist").status_code == 404


def test_the_static_script_routes_are_not_swallowed(isolated_character_db):
    """/script/{script_id} must not answer for /script/link or /script/presets."""
    assert "production_ids" in client.get("/api/script/link", params={"script_id": "x"}).json()
    assert "presets" in client.get("/api/script/presets").json()
