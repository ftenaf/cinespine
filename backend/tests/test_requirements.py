"""
Comprehensive Test Suite for Collaborative Requirements, User Identity & Real-Time Alerts.
"""
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.spine.writer import SpineWriter
from backend.app.streaming.models import DEFAULT_TEAM_USERS


@pytest.fixture
def client():
    return TestClient(app)


def test_list_team_users(client):
    """Test retrieving predefined and registered production team members."""
    res = client.get("/api/users")
    assert res.status_code == 200
    users = res.json()
    assert len(users) >= len(DEFAULT_TEAM_USERS)
    handles = [u["handle"] for u in users]
    assert "@director" in handles
    assert "@sound_supervisor" in handles
    assert "@assistant_editor" in handles


def test_passwordless_login(client):
    """Test passwordless authentication with handle or email."""
    # 1. Login by handle
    res1 = client.post("/api/auth/login", json={"handle_or_email": "@sound_supervisor"})
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["user"]["handle"] == "@sound_supervisor"
    assert data1["user"]["role"] == "Sound Mixer / Sound Supervisor"

    # 2. Login by email
    res2 = client.post("/api/auth/login", json={"handle_or_email": "director@example.com"})
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["user"]["handle"] == "@director"

    # 3. Login with custom/new handle (auto-creates profile)
    res3 = client.post("/api/auth/login", json={"handle_or_email": "@colorist_lead"})
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["user"]["handle"] == "@colorist_lead"


def test_create_and_query_requirements(client):
    """Test creating requirements on Take, Shot, and Scene."""
    # 1. Create requirement on Take 49/WT_1
    req_payload = {
        "production_id": "DEMO_PRODUCTION",
        "shoot_day": "31",
        "target_type": "take",
        "target_id": "49/WT_1",
        "target_label": "Take 49/WT T1",
        "title": "Clean Foley footsteps bleed",
        "description": "Noticeable floor creak during actor entrance at 00:00:15.",
        "priority": "high",
        "category": "sound",
        "created_by": "@director",
        "assigned_to": "@sound_supervisor",
    }
    res = client.post("/api/requirements", json=req_payload)
    assert res.status_code == 200
    req = res.json()
    req_id = req["requirement_id"]
    assert req_id.startswith("req_")
    assert req["status"] == "open"
    assert req["assigned_to"] == "@sound_supervisor"
    assert req["created_by"] == "@director"

    # 2. Verify assignee (@sound_supervisor) received an alert notification
    notif_res = client.get("/api/notifications?user_handle=@sound_supervisor")
    assert notif_res.status_code == 200
    notifs = notif_res.json()["notifications"]
    assert len(notifs) >= 1
    found_alert = next((n for n in notifs if n["requirement_id"] == req_id), None)
    assert found_alert is not None
    assert found_alert["notification_type"] == "ASSIGNED"
    assert found_alert["actor_handle"] == "@director"
    assert "Clean Foley footsteps" in found_alert["message"]

    # 3. Filter requirements by target_id
    filter_res = client.get("/api/requirements?production_id=DEMO_PRODUCTION&target_id=49/WT_1")
    assert filter_res.status_code == 200
    assert len(filter_res.json()) >= 1
    assert filter_res.json()[0]["requirement_id"] == req_id


def test_requirement_resolution_lifecycle(client):
    """Test full cycle: Assignee resolves requirement -> Caller gets notified."""
    # 1. Create requirement assigned to @assistant_editor by @lead_editor
    req_res = client.post("/api/requirements", json={
        "production_id": "DEMO_PRODUCTION",
        "shoot_day": "31",
        "target_type": "scene",
        "target_id": "27",
        "target_label": "Scene 27",
        "title": "Check camera sync between A & B cameras",
        "description": "Slight 1-frame drift reported in wide angle shot.",
        "priority": "critical",
        "category": "edit",
        "created_by": "@lead_editor",
        "assigned_to": "@assistant_editor",
    })
    assert req_res.status_code == 200
    req = req_res.json()
    req_id = req["requirement_id"]

    # 2. Assistant editor resolves requirement with note
    resolve_res = client.post(f"/api/requirements/{req_id}/resolve", json={
        "resolution_note": "Re-synced audio slate with visual clapper; aligned 24.0fps TC offset.",
        "resolved_by": "@assistant_editor",
    })
    assert resolve_res.status_code == 200
    resolved_req = resolve_res.json()
    assert resolved_req["status"] == "resolved"
    assert resolved_req["resolved_by"] == "@assistant_editor"
    assert "Re-synced audio slate" in resolved_req["resolution_note"]
    assert resolved_req["resolved_at"] is not None

    # 3. Original caller (@lead_editor) should receive a RESOLVED notification
    lead_notif_res = client.get("/api/notifications?user_handle=@lead_editor")
    assert lead_notif_res.status_code == 200
    lead_notifs = lead_notif_res.json()["notifications"]
    res_alert = next((n for n in lead_notifs if n["requirement_id"] == req_id), None)
    assert res_alert is not None
    assert res_alert["notification_type"] == "RESOLVED"
    assert res_alert["actor_handle"] == "@assistant_editor"
    assert "marked resolved" in res_alert["message"]


def test_notification_read_actions(client):
    """Test marking notifications as read individually and in bulk."""
    user = "@vfx_supervisor"
    # Create requirement for VFX
    client.post("/api/requirements", json={
        "production_id": "DEMO_PRODUCTION",
        "shoot_day": "31",
        "target_type": "shot",
        "target_id": "49/9",
        "target_label": "Slate 49/9",
        "title": "Paint out boom mic shadow on stone column",
        "priority": "medium",
        "category": "vfx",
        "created_by": "@director",
        "assigned_to": user,
    })

    # Query unread
    notif_res = client.get(f"/api/notifications?user_handle={user}&unread_only=true")
    assert notif_res.status_code == 200
    unread_data = notif_res.json()
    assert unread_data["unread_count"] >= 1
    notif_id = unread_data["notifications"][0]["notification_id"]

    # Mark single read
    read_res = client.post(f"/api/notifications/{notif_id}/read")
    assert read_res.status_code == 200

    # Mark all read
    read_all_res = client.post(f"/api/notifications/read-all?user_handle={user}")
    assert read_all_res.status_code == 200


def test_takes_enriched_with_requirements(client):
    """Verify that /api/takes returns attached requirements and counts."""
    # Seed data
    client.post("/api/seed", json={"production_id": "DEMO_PRODUCTION_REQ_TEST", "shoot_day": "31"})

    # Attach requirement to 49/WT_1
    client.post("/api/requirements", json={
        "production_id": "DEMO_PRODUCTION_REQ_TEST",
        "shoot_day": "31",
        "target_type": "take",
        "target_id": "49/WT_1",
        "target_label": "Take 49/WT T1",
        "title": "EQ bass resonance on wild track",
        "priority": "medium",
        "category": "sound",
        "created_by": "@director",
        "assigned_to": "@sound_supervisor",
    })

    takes_res = client.get("/api/takes?production_id=DEMO_PRODUCTION_REQ_TEST&shoot_day=31")
    assert takes_res.status_code == 200
    takes = takes_res.json()
    take_49wt = next((t for t in takes if t.get("slate") == "49/WT" and t.get("take_id") == "1"), None)
    assert take_49wt is not None
    assert "requirements" in take_49wt
    assert take_49wt["open_requirements_count"] >= 1
