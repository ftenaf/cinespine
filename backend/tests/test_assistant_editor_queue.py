from fastapi.testclient import TestClient

from backend.app.agents.editorial_queue import AssistantEditorQueueAgent
from backend.app.main import app
from backend.app.spine.writer import SpineWriter

client = TestClient(app)


class NoDiscrepancies:
    def query_production_discrepancies(self, production_id, shoot_day):
        return []


class SceneDiscrepancy:
    def query_production_discrepancies(self, production_id, shoot_day):
        return [{
            "entity_id": "27/7",
            "discrepancy_type": "TIMECODE_DRIFT",
            "description": "Camera and sound disagree.",
            "is_resolved": False,
        }]


def _take_event(production_id, shoot_day, department, axis="belief", **payload):
    return {
        "event_id": f"{department}-{payload.get('slate')}-{payload.get('take_id')}",
        "production_id": production_id,
        "shoot_day": shoot_day,
        "axis": axis,
        "department": department,
        "doc_type": f"{department}_report",
        "entity_type": "take",
        "payload": payload,
        "metadata": {"filename": f"{department}.txt"},
        "timestamp": "2026-07-28T10:00:00Z",
    }


def _clean_scene(writer, production_id="QUEUE", shoot_day="31", scene="27"):
    writer.append_event(_take_event(
        production_id, shoot_day, "script",
        slate=f"{scene}/7", take_id="1", is_starred=True,
    ))
    writer.append_event(_take_event(
        production_id, shoot_day, "camera",
        slate=f"{scene}/7", take_id="1", camera_roll="A120",
    ))
    writer.append_event(_take_event(
        production_id, shoot_day, "sound",
        slate=f"{scene}/7", take_id="1", sound_roll="S031",
    ))
    writer.append_event(_take_event(
        production_id, shoot_day, "dit", axis="existence",
        slate=f"{scene}/7", take_id="1", camera_roll="A120",
    ))


def test_production_crew_can_be_managed_while_active():
    response = client.post("/api/productions", json={
        "production_id": "CREWED",
        "name": "Crewed",
    })
    assert response.status_code == 200, response.text

    response = client.post("/api/productions/CREWED/crew", json={
        "handle": "@night_ae",
        "name": "Night AE",
        "role": "Assistant Editor",
        "department": "editorial",
    })
    assert response.status_code == 200, response.text

    crew = client.get("/api/productions/CREWED/crew").json()
    assert [member["handle"] for member in crew] == ["@night_ae"]

    from backend.app.api.routes import spine_writer

    events = spine_writer.get_events(production_id="CREWED")
    assert events[-1]["doc_type"] == "production_crew_event"
    assert events[-1]["metadata"]["action"] == "upserted"


def test_crew_cannot_be_changed_after_production_is_finished():
    client.post("/api/productions", json={"production_id": "WRAPPED_Q", "name": "Wrapped Queue"})
    client.patch("/api/productions/WRAPPED_Q", json={"status": "Wrapped"})

    response = client.post("/api/productions/WRAPPED_Q/crew", json={
        "handle": "@night_ae",
        "name": "Night AE",
        "role": "Assistant Editor",
        "department": "editorial",
    })

    assert response.status_code == 409
    assert "read-only after the production is finished" in response.json()["detail"]


def test_director_can_distribute_clean_scene_batch_to_all_assistant_editors():
    writer = SpineWriter(clickhouse_client=False)
    writer.register_production("QUEUE", "Queue")
    for handle in ("@day_ae", "@night_ae"):
        writer.upsert_production_crew_member({
            "production_id": "QUEUE",
            "handle": handle,
            "name": handle.lstrip("@").replace("_", " ").title(),
            "email": f"{handle.lstrip('@')}@example.com",
            "role": "Assistant Editor",
            "department": "editorial",
        })
    _clean_scene(writer, scene="27")
    _clean_scene(writer, scene="49")

    result = AssistantEditorQueueAgent(writer, NoDiscrepancies()).run(
        "QUEUE",
        "31",
        actor="@director",
        max_scenes=2,
    )

    assert result.assigned_to == "ALL"
    assert result.assignees == ["@day_ae", "@night_ae"]
    assert result.actor == "@director"
    assert {scene.scene for scene in result.scenes} == {"27", "49"}
    assert {scene.assigned_to for scene in result.scenes} == {"@day_ae", "@night_ae"}
    assert all(scene.requirement_id for scene in result.scenes)
    assert {action.action for action in result.requirement_actions} == {"created"}
    reqs = writer.list_requirements(production_id="QUEUE")
    assert len(reqs) == 2
    assert all(req["target_type"] == "scene" for req in reqs)


def test_all_days_plans_only_clean_scenes_that_are_not_already_assigned():
    writer = SpineWriter(clickhouse_client=False)
    writer.register_production("QUEUE_ALL", "Queue All")
    writer.upsert_production_crew_member({
        "production_id": "QUEUE_ALL",
        "handle": "@night_ae",
        "name": "Night AE",
        "role": "Assistant Editor",
        "department": "editorial",
    })
    _clean_scene(writer, production_id="QUEUE_ALL", shoot_day="31", scene="27")
    _clean_scene(writer, production_id="QUEUE_ALL", shoot_day="32", scene="49")

    agent = AssistantEditorQueueAgent(writer, NoDiscrepancies())
    first = agent.run("QUEUE_ALL", "31", actor="@director")
    assert [scene.scene for scene in first.scenes] == ["27"]

    second = agent.run("QUEUE_ALL", "ALL", actor="@director")
    assert second.shoot_day == "ALL"
    assert [scene.scene for scene in second.scenes] == ["49"]
    assert "Day 32" in writer.list_requirements(
        production_id="QUEUE_ALL",
        target_id="49",
    )[0]["description"]


def test_assistant_queue_agent_skips_scene_with_active_discrepancy():
    writer = SpineWriter(clickhouse_client=False)
    writer.register_production("QUEUE_BLOCKED", "Queue Blocked")
    writer.upsert_production_crew_member({
        "production_id": "QUEUE_BLOCKED",
        "handle": "@assistant_editor",
        "name": "Assistant Editor",
        "role": "Assistant Editor",
        "department": "editorial",
    })
    _clean_scene(writer, production_id="QUEUE_BLOCKED")

    result = AssistantEditorQueueAgent(writer, SceneDiscrepancy()).run(
        "QUEUE_BLOCKED",
        "31",
        actor="@assistant_editor",
    )

    assert result.scenes == []
    assert result.requirement_actions == []


def test_assistant_queue_requires_active_assistant_editors():
    writer = SpineWriter(clickhouse_client=False)
    writer.register_production("QUEUE_NO_CREW", "Queue No Crew")
    _clean_scene(writer, production_id="QUEUE_NO_CREW")

    try:
        AssistantEditorQueueAgent(writer, NoDiscrepancies()).run(
            "QUEUE_NO_CREW",
            "31",
            actor="@director",
            assignee="@night_ae",
        )
    except ValueError as exc:
        assert "not an active assistant editor" in str(exc)
    else:
        raise AssertionError("queue should require active assistant editors")


def test_api_completion_feeds_pre_editing_dashboard():
    response = client.post("/api/productions", json={
        "production_id": "QUEUE_DASH",
        "name": "Queue Dashboard",
    })
    assert response.status_code == 200, response.text
    for handle in ("@day_ae", "@night_ae"):
        response = client.post("/api/productions/QUEUE_DASH/crew", json={
            "handle": handle,
            "name": handle.lstrip("@").replace("_", " ").title(),
            "role": "Assistant Editor",
            "department": "editorial",
        })
        assert response.status_code == 200, response.text

    from backend.app.api.routes import spine_writer

    _clean_scene(spine_writer, production_id="QUEUE_DASH", scene="27")
    _clean_scene(spine_writer, production_id="QUEUE_DASH", scene="49")

    planned = client.post("/api/agents/assistant-editor-queue/run", json={
        "production_id": "QUEUE_DASH",
        "shoot_day": "ALL",
        "actor": "@director",
        "max_scenes": 2,
    })
    assert planned.status_code == 200, planned.text
    body = planned.json()
    assert body["assignees"] == ["@day_ae", "@night_ae"]
    assert len(body["scenes"]) == 2

    first_scene = body["scenes"][0]
    resolved = client.post(
        f"/api/requirements/{first_scene['requirement_id']}/resolve",
        json={
            "resolution_note": "Pre-edit complete.",
            "resolved_by": first_scene["assigned_to"],
        },
    )
    assert resolved.status_code == 200, resolved.text

    dashboard = client.get("/api/dashboard", params={"production_id": "QUEUE_DASH"}).json()
    assert dashboard["pre_editing"]["total"] == 2
    assert dashboard["pre_editing"]["completed"] == 1
    assert dashboard["pre_editing"]["pending"] == 1
    finisher = next(
        row for row in dashboard["pre_editing"]["by_assistant"]
        if row["handle"] == first_scene["assigned_to"]
    )
    assert finisher["completed"] == 1
    assert finisher["scenes_completed"] == 1
    assert dashboard["pre_editing"]["recent_completed"][0]["resolved_by"] == first_scene["assigned_to"]
