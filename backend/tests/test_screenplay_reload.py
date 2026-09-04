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
    # The same shape the parse gave, not the table's: the breakdown endpoint
    # takes a scene as the parser defines it, and the studio renders those
    # fields. Served as rows, both buttons on a reloaded script were dead.
    for reloaded, fresh in zip(body["scenes"], parsed["scenes"]):
        assert set(reloaded) == set(fresh), set(reloaded) ^ set(fresh)
        assert reloaded["scene_number"] == fresh["scene_number"]
        assert reloaded["action_blocks"] == fresh["action_blocks"]
        assert reloaded["characters"] == fresh["characters"]
        assert reloaded["environment"] == fresh["environment"]
    assert {c["name"] for c in body["characters"]} == {c["name"] for c in parsed["characters"]}
    assert body["parse_warnings"] == []


def test_an_unknown_script_is_a_404(isolated_character_db):
    assert client.get("/api/script/does-not-exist").status_code == 404


def test_the_static_script_routes_are_not_swallowed(isolated_character_db):
    """/script/{script_id} must not answer for /script/link or /script/presets."""
    assert "production_ids" in client.get("/api/script/link", params={"script_id": "x"}).json()
    assert "presets" in client.get("/api/script/presets").json()


def test_a_reloaded_scene_can_be_broken_down(isolated_character_db):
    """The two buttons: a reloaded scene must be accepted by /script/breakdown."""
    parsed = client.post("/api/script/parse", json={"script_text": SCRIPT, "title": "Reload"}).json()
    reloaded = client.get(f"/api/script/{parsed['script_id']}").json()
    res = client.post("/api/script/breakdown", json={
        "scene": reloaded["scenes"][0], "script_id": parsed["script_id"],
        "character_profiles": reloaded["characters"],
    })
    assert res.status_code == 200, res.text
    assert res.json()["shots"]
