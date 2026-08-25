"""
Test Suite for Real-Time Events & SSE Subscriptions in CineSpine.
"""
import pytest
import asyncio
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.streaming.broker import LiveEventBroker, SpineLiveEvent, event_broker


@pytest.fixture
def client():
    return TestClient(app)


def test_live_event_broker_registration_and_filtering():
    """Verify broker registers subscribers and correctly filters by production/day."""
    broker = LiveEventBroker()
    
    # Sub 1: Day 31 of DEMO_PRODUCTION
    sub1 = broker.register_subscriber(production_id="DEMO_PRODUCTION", shoot_day="31")
    # Sub 2: Day 39 of DEMO_PRODUCTION
    sub2 = broker.register_subscriber(production_id="DEMO_PRODUCTION", shoot_day="39")
    # Sub 3: ALL
    sub3 = broker.register_subscriber(production_id=None, shoot_day=None)

    # Event on Day 31
    evt_d31 = SpineLiveEvent(
        event_type="DOCUMENT_INGESTED",
        production_id="DEMO_PRODUCTION",
        shoot_day="31",
        actor_handle="@director",
        summary="Ingested ZoeLog Day 31",
    )
    broker.publish_sync(evt_d31)

    # sub1 should have the event
    assert len(sub1.events) == 1
    assert sub1.events[0].event_type == "DOCUMENT_INGESTED"
    assert sub1.events[0].shoot_day == "31"

    # sub2 should NOT have the event
    assert len(sub2.events) == 0

    # sub3 (all) should have the event
    assert len(sub3.events) == 1
    assert sub3.events[0].event_type == "DOCUMENT_INGESTED"

    # Cleanup
    broker.unregister_subscriber(sub1.subscriber_id)
    broker.unregister_subscriber(sub2.subscriber_id)
    broker.unregister_subscriber(sub3.subscriber_id)


def test_upload_and_requirement_publish_live_events(client):
    """Test that creating requirement and uploading paperwork triggers live event publication."""
    # Register synchronous hook/subscriber for testing
    sub = event_broker.register_subscriber(production_id="DEMO_PRODUCTION", shoot_day="31")

    # 1. Ingest paperwork via upload
    upload_res = client.post("/api/upload", json={
        "raw_content": "Clip,Scene,Take,Card\nA120_C001,49,1,A120",
        "filename": "camera_live_test.csv",
        "production_id": "DEMO_PRODUCTION",
        "shoot_day": "31",
        "metadata": {"actor_handle": "@dit_operator"},
    })
    assert upload_res.status_code == 200

    # 2. Check broker received DOCUMENT_INGESTED
    assert len(sub.events) >= 1
    evt = sub.events[-1]
    assert evt.event_type == "DOCUMENT_INGESTED"
    assert evt.target_label == "camera_live_test.csv"
    assert evt.shoot_day == "31"

    # 3. Create a requirement
    req_res = client.post("/api/requirements", json={
        "production_id": "DEMO_PRODUCTION",
        "shoot_day": "31",
        "target_type": "take",
        "target_id": "49_1",
        "target_label": "Take 49 T1",
        "title": "Clean Foley bleed",
        "assigned_to": "@sound_supervisor",
        "created_by": "@director",
        "priority": "high",
        "category": "sound",
    })
    assert req_res.status_code == 200
    req_data = req_res.json()
    req_id = req_data["requirement_id"]

    # 4. Check broker received REQUIREMENT_CREATED
    req_evt = sub.events[-1]
    assert req_evt.event_type == "REQUIREMENT_CREATED"
    assert req_evt.actor_handle == "@director"
    assert req_evt.data["assigned_to"] == "@sound_supervisor"

    # 5. Resolve the requirement
    res_res = client.post(f"/api/requirements/{req_id}/resolve", json={
        "resolution_note": "Filtered audio 120Hz hum",
        "resolved_by": "@sound_supervisor",
    })
    assert res_res.status_code == 200

    # 6. Check broker received REQUIREMENT_RESOLVED
    res_evt = sub.events[-1]
    assert res_evt.event_type == "REQUIREMENT_RESOLVED"
    assert res_evt.actor_handle == "@sound_supervisor"

    # Cleanup
    event_broker.unregister_subscriber(sub.subscriber_id)

