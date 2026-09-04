"""
Every mutation the API accepts leaves a row in user_activity.

Until now the activity ledger had one writer, the Requirements board, and only
for views and acknowledgements. "Who did what today" needs the changes too,
recorded server-side where the write happens, so no surface can forget to.
"""
import json

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.spine import activity_store

client = TestClient(app)

PROD = "ACTIVITY_PROD"


def activity(target_type: str, target_id: str, production_id: str = PROD):
    body = client.get("/api/activity", params={
        "production_id": production_id, "target_type": target_type, "target_id": target_id,
    }).json()
    return body["events"]


def only(target_type: str, target_id: str, action: str, production_id: str = PROD):
    rows = [e for e in activity(target_type, target_id, production_id) if e["action"] == action]
    assert len(rows) == 1, f"expected one {action} row on {target_type} {target_id}, got {rows}"
    return rows[0]


def make_production(production_id: str = PROD):
    res = client.post("/api/productions", json={"production_id": production_id, "name": "Activity"})
    assert res.status_code == 200, res.text
    return res.json()


def raise_requirement(**overrides):
    body = {
        "production_id": PROD, "shoot_day": "31", "target_type": "scene",
        "target_id": "27", "title": "Needs a re-record",
        "created_by": "@script_supervisor", "assigned_to": "@sound_supervisor",
    }
    body.update(overrides)
    res = client.post("/api/requirements", json=body)
    assert res.status_code == 200, res.text
    return res.json()


# --------------------------------------------------------------------------- #
# The vocabulary
# --------------------------------------------------------------------------- #

def test_views_and_mutations_are_distinct_sets():
    assert not set(activity_store.VIEW_ACTIONS) & set(activity_store.MUTATION_ACTIONS)
    assert set(activity_store.ACTIONS) == set(activity_store.VIEW_ACTIONS) | set(activity_store.MUTATION_ACTIONS)


def test_a_verb_nobody_declared_is_still_refused():
    res = client.post("/api/activity", json={
        "production_id": PROD, "actor": "@x", "action": "pondered",
        "target_type": "requirement", "target_id": "R",
    })
    assert res.status_code == 400


# --------------------------------------------------------------------------- #
# Productions and crew: no actor field, so the row says the actor is a default
# --------------------------------------------------------------------------- #

def test_a_production_lifecycle_is_recorded_with_a_defaulted_actor():
    make_production()
    row = only("production", PROD, "created")
    assert row["actor"] == "@director"
    assert json.loads(row["context_json"])[activity_store.ACTOR_SOURCE_KEY] == activity_store.ACTOR_SOURCE_DEFAULT

    assert client.patch(f"/api/productions/{PROD}", json={"name": "Renamed"}).status_code == 200
    assert json.loads(only("production", PROD, "updated")["context_json"])["fields"] == "name"

    assert client.delete(f"/api/productions/{PROD}").status_code == 200
    only("production", PROD, "deleted")


def test_crew_changes_are_recorded():
    make_production()
    res = client.post(f"/api/productions/{PROD}/crew", json={
        "handle": "@night_ae", "name": "Night AE", "department": "editorial",
    })
    assert res.status_code == 200, res.text
    assert only("crew", "@night_ae", "created")["department"] == "editorial"

    assert client.patch(f"/api/productions/{PROD}/crew/@night_ae", json={"role": "Editor"}).status_code == 200
    only("crew", "@night_ae", "updated")

    assert client.delete(f"/api/productions/{PROD}/crew/@night_ae").status_code == 200
    only("crew", "@night_ae", "deleted")


# --------------------------------------------------------------------------- #
# Requirements: the body names who acted, so the row credits them
# --------------------------------------------------------------------------- #

def test_the_requirement_lifecycle_credits_the_named_actor():
    make_production()
    created = raise_requirement()
    rid = created["requirement_id"]

    row = only("requirement", rid, "created")
    assert row["actor"] == "@script_supervisor"
    assert row["shoot_day"] == "31"
    assert activity_store.ACTOR_SOURCE_KEY not in json.loads(row["context_json"])

    res = client.patch(f"/api/requirements/{rid}", json={"status": "in_progress", "updated_by": "@sound_supervisor"})
    assert res.status_code == 200, res.text
    row = only("requirement", rid, "updated")
    assert row["actor"] == "@sound_supervisor"
    assert json.loads(row["context_json"])["fields"] == "status"

    res = client.post(f"/api/requirements/{rid}/resolve", json={"resolution_note": "done", "resolved_by": "@sound_supervisor"})
    assert res.status_code == 200, res.text
    assert only("requirement", rid, "resolved")["actor"] == "@sound_supervisor"

    assert client.delete(f"/api/requirements/{rid}", params={"deleted_by": "@director"}).status_code == 200
    assert only("requirement", rid, "deleted")["actor"] == "@director"


def test_an_update_without_updated_by_is_marked_defaulted():
    make_production()
    rid = raise_requirement()["requirement_id"]
    assert client.patch(f"/api/requirements/{rid}", json={"priority": "high"}).status_code == 200
    row = only("requirement", rid, "updated")
    assert row["actor"] == "@user"
    assert json.loads(row["context_json"])[activity_store.ACTOR_SOURCE_KEY] == "default"


def test_context_never_carries_free_text():
    """The title goes through the same filter product analytics applies."""
    make_production()
    rid = raise_requirement(title="The colorist's phone number is 555-0100")["requirement_id"]
    context = json.loads(only("requirement", rid, "created")["context_json"])
    assert "title" not in context
    assert "555-0100" not in json.dumps(context)


# --------------------------------------------------------------------------- #
# Tags, notifications, discrepancies, scripts, agents
# --------------------------------------------------------------------------- #

def test_setting_and_clearing_a_tag_is_recorded():
    res = client.put("/api/tags", json={
        "production_id": PROD, "target_type": "scene", "target_id": "27",
        "status": "finished", "updated_by": "@editor",
    })
    assert res.status_code == 200, res.text
    row = only("tag", "scene:27", "tagged")
    assert row["actor"] == "@editor"
    assert json.loads(row["context_json"])["status"] == "finished"

    res = client.delete("/api/tags", params={
        "production_id": PROD, "target_type": "scene", "target_id": "27", "cleared_by": "@editor",
    })
    assert res.status_code == 200, res.text
    assert only("tag", "scene:27", "deleted")["actor"] == "@editor"


def test_reading_a_notification_is_an_acknowledgement():
    make_production()
    raise_requirement()
    notes = client.get("/api/notifications", params={"user_handle": "@sound_supervisor"}).json()
    items = notes["notifications"]
    assert items, notes
    note_id = items[0]["notification_id"]
    assert client.post(f"/api/notifications/{note_id}/read").status_code == 200
    assert only("notification", note_id, "acknowledged")["actor"] == "@sound_supervisor"


def test_resolving_and_reopening_a_discrepancy_is_recorded():
    res = client.post("/api/discrepancies/DISC-1/resolve", json={
        "production_id": PROD, "shoot_day": "31", "entity_id": "27/7",
        "resolved_card": "A001", "resolution_note": "camera roll wins", "resolved_by": "@assistant_editor",
    })
    assert res.status_code == 200, res.text
    row = only("discrepancy", "DISC-1", "resolved")
    assert row["actor"] == "@assistant_editor"
    assert "camera roll wins" not in row["context_json"]

    res = client.post("/api/discrepancies/DISC-1/unresolve", params={
        "reopened_by": "@assistant_editor", "production_id": PROD, "shoot_day": "31",
    })
    assert res.status_code == 200, res.text
    assert only("discrepancy", "DISC-1", "reopened")["actor"] == "@assistant_editor"


def test_linking_a_script_and_saving_a_breakdown_are_recorded():
    make_production()
    parsed = client.post("/api/script/parse", json={
        "script_text": "INT. KITCHEN - NIGHT\n\nMARA\nWe are out of time.\n", "title": "Ledger",
    }).json()
    script_id = parsed["script_id"]

    assert client.post("/api/script/link", json={"production_id": PROD, "script_id": script_id}).status_code == 200
    only("script", script_id, "linked")

    res = client.put(f"/api/script/{script_id}/breakdowns/1", json={"shots": []})
    assert res.status_code == 200, res.text
    row = only("breakdown", f"{script_id}:1", "updated")
    assert row["production_id"] == PROD, "a breakdown is filed under the production shooting the script"

    assert client.delete("/api/script/link", params={"production_id": PROD}).status_code == 200
    only("script", script_id, "unlinked")


def test_running_the_assistant_editor_queue_is_recorded():
    make_production()
    crewed = client.post(f"/api/productions/{PROD}/crew", json={
        "handle": "@assistant_editor", "name": "AE", "role": "Assistant Editor", "department": "editorial",
    })
    assert crewed.status_code == 200, crewed.text
    res = client.post("/api/agents/assistant-editor-queue/run", json={
        "production_id": PROD, "shoot_day": "31", "actor": "@assistant_editor",
    })
    assert res.status_code == 200, res.text
    row = only("agent", "assistant_editor_queue", "ran_agent")
    assert row["actor"] == "@assistant_editor"
    assert "requirement_actions" in json.loads(row["context_json"])
