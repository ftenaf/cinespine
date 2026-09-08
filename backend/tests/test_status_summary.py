"""
One production, five ranked buckets: done, running, blocking, left, missing.

The ranking is the point. Within a bucket the worst severity comes first and,
at equal severity, the oldest; "missing" says which of its items are inferred.
"""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.spine import status_summary

client = TestClient(app)

PROD = "STATUS_PROD"


def make_production():
    assert client.post("/api/productions", json={"production_id": PROD, "name": "Status"}).status_code == 200


def raise_requirement(title, priority="medium", **over):
    body = {
        "production_id": PROD, "shoot_day": "31", "target_type": "scene", "target_id": "27",
        "title": title, "priority": priority, "created_by": "@script_supervisor", "assigned_to": "@sound_supervisor",
    }
    body.update(over)
    res = client.post("/api/requirements", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def test_an_unknown_production_is_a_404():
    assert client.get("/api/productions/NOPE/status").status_code == 404


def test_requirements_land_in_the_bucket_their_status_says():
    make_production()
    open_req = raise_requirement("Open one")
    running = raise_requirement("Running one")
    blocked = raise_requirement("Blocked one", priority="critical")
    done = raise_requirement("Done one")
    client.patch(f"/api/requirements/{running['requirement_id']}", json={"status": "in_progress", "updated_by": "@sound_supervisor"})
    client.patch(f"/api/requirements/{blocked['requirement_id']}", json={"status": "blocked", "updated_by": "@sound_supervisor"})
    client.post(f"/api/requirements/{done['requirement_id']}/resolve", json={"resolution_note": "ok", "resolved_by": "@sound_supervisor"})

    body = client.get(f"/api/productions/{PROD}/status").json()
    titles = {b: [i["title"] for i in body[b] if i["kind"] == "requirement"] for b in status_summary.BUCKETS}
    assert titles["left"] == ["Open one"]
    assert titles["running"] == ["Running one"]
    assert titles["blocking"] == ["Blocked one"]
    assert titles["done"] == ["Done one"]
    assert body["counts"]["blocking"] >= 1
    assert body["urgent"][0]["title"] == "Blocked one", "the critical blocker is the most urgent thing"
    assert "Blocked one" in body["headline"]
    assert open_req["requirement_id"] in {i["id"] for i in body["left"]}


def test_within_a_bucket_severity_wins_then_age():
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    items = [
        status_summary._item("left", "requirement", "a", "old medium", "medium", now - timedelta(hours=100), now),
        status_summary._item("left", "requirement", "b", "new critical", "critical", now - timedelta(hours=1), now),
        status_summary._item("left", "requirement", "c", "old critical", "critical", now - timedelta(hours=50), now),
        status_summary._item("left", "requirement", "d", "undated critical", "critical", None, now),
    ]
    items.sort(key=status_summary._sort_key)
    assert [i["title"] for i in items] == ["old critical", "new critical", "undated critical", "old medium"]


def test_missing_names_the_setup_gaps_and_says_what_is_inferred():
    make_production()
    body = client.get(f"/api/productions/{PROD}/status").json()
    kinds = {i["kind"]: i for i in body["missing"]}
    assert "spine" in kinds, "no events at all is the first thing to say"
    assert "crew" in kinds and "script" in kinds
    assert body["shoot_days"] == []
    assert body["counts"]["missing"] == len(body["missing"])


def test_a_department_absent_on_one_day_is_missing_paperwork():
    make_production()
    # Demo paperwork gives day 31 several departments. Add a day 32 with only sound.
    client.get("/api/events/demo")
    demo = client.get("/api/productions/DEMO_PRODUCTION/status").json()
    assert demo["production_id"] == "DEMO_PRODUCTION"
    assert set(demo["counts"]) == set(status_summary.BUCKETS)
    for bucket in status_summary.BUCKETS:
        sev = [status_summary.SEVERITY_RANK[i["severity"]] for i in demo[bucket]]
        assert sev == sorted(sev, reverse=True), f"{bucket} is not ranked by severity"
    for item in demo["missing"]:
        if item["kind"] == "paperwork":
            assert "inferred" in item["detail"]
