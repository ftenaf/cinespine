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


def test_assistant_queue_agent_assigns_clean_scene_to_logged_editor():
    writer = SpineWriter(clickhouse_client=False)
    writer.register_production("QUEUE", "Queue")
    writer.upsert_production_crew_member({
        "production_id": "QUEUE",
        "handle": "@night_ae",
        "name": "Night AE",
        "email": "night.ae@example.com",
        "role": "Assistant Editor",
        "department": "editorial",
    })
    _clean_scene(writer)

    result = AssistantEditorQueueAgent(writer, NoDiscrepancies()).run(
        "QUEUE",
        "31",
        actor="@night_ae",
    )

    assert result.assigned_to == "@night_ae"
    assert result.scenes[0].scene == "27"
    assert result.requirement_actions[0].action == "created"
    reqs = writer.list_requirements(production_id="QUEUE", assigned_to="@night_ae")
    assert reqs[0]["target_type"] == "scene"
    assert "AssistantQueueSource: scene:27:day:31" in reqs[0]["description"]


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


def test_assistant_queue_requires_logged_editor_to_be_active_crew():
    writer = SpineWriter(clickhouse_client=False)
    writer.register_production("QUEUE_NO_CREW", "Queue No Crew")
    _clean_scene(writer, production_id="QUEUE_NO_CREW")

    try:
        AssistantEditorQueueAgent(writer, NoDiscrepancies()).run(
            "QUEUE_NO_CREW",
            "31",
            actor="@night_ae",
        )
    except ValueError as exc:
        assert "not active editorial crew" in str(exc)
    else:
        raise AssertionError("queue should require the logged editor to be crewed")
