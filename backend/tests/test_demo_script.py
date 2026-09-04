"""
The Load Demo button loads the repo's demo screenplay, not a bundled string.

`data/examples/demo_script.fountain` is the screenplay the demo paperwork
references; the studio must parse that same file so the two agree.
"""
from fastapi.testclient import TestClient

from backend.app.api import routes
from backend.app.main import app

client = TestClient(app)


def test_the_demo_script_is_served_from_data_examples():
    res = client.get("/api/script/demo")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["filename"] == "demo_script.fountain"
    assert body["script_text"].startswith("Title: THE ALGORITHM")


def test_the_served_text_parses_to_the_demo_scenes():
    text = client.get("/api/script/demo").json()["script_text"]
    parsed = client.post("/api/script/parse", json={"script_text": text}).json()
    assert parsed["title"] == "THE ALGORITHM"
    assert [s["scene_number"] for s in parsed["scenes"]] == ["1", "2", "3", "4", "5", "6"]
    assert len(parsed["characters"]) == 6


def test_a_missing_file_is_a_404_not_a_500(monkeypatch, tmp_path):
    monkeypatch.setattr(routes, "DEMO_SCRIPT_PATH", str(tmp_path / "absent.fountain"))
    res = client.get("/api/script/demo")
    assert res.status_code == 404
    assert "demo screenplay" in res.json()["detail"]


def test_demo_is_not_swallowed_by_the_script_id_route():
    """/script/demo must answer as the demo, not as 'no screenplay called demo'."""
    assert client.get("/api/script/demo").status_code == 200
    assert client.get("/api/script/not-demo").status_code == 404
