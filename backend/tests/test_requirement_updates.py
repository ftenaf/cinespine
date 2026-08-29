"""
Editing a requirement from a board somebody else is looking at.

Requirements can now be reassigned and blocked from a production-wide view,
where the person doing it is usually neither the one who raised the
requirement nor the one holding it. Creating and resolving already sent word;
everything in between reached nobody, which meant a requirement could be handed
over or declared blocked in silence.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)

PROD = "REQTEST"


def raise_requirement(**over):
    payload = {
        "production_id": PROD,
        "shoot_day": "31",
        "target_type": "shot",
        "target_id": "27/7",
        "target_label": "Slate 27/7",
        "title": "Room tone missing",
        "description": "No wild track for this setup.",
        "priority": "high",
        "category": "sound",
        "created_by": "@director",
        "assigned_to": "@sound_supervisor",
        **over,
    }
    res = client.post("/api/requirements", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def notifications_for(handle: str):
    res = client.get("/api/notifications", params={"user_handle": handle})
    assert res.status_code == 200
    return res.json()["notifications"]


def test_reassigning_tells_the_person_it_was_handed_to():
    """Handing someone a requirement they are never told about drops it."""
    req = raise_requirement()
    before = len(notifications_for("@lead_editor"))

    client.patch(f"/api/requirements/{req['requirement_id']}", json={
        "assigned_to": "@lead_editor", "updated_by": "@post_supervisor",
    })

    fresh = notifications_for("@lead_editor")
    assert len(fresh) == before + 1
    assert fresh[0]["notification_type"] == "ASSIGNED"
    assert "@post_supervisor" in fresh[0]["message"]


def test_blocking_tells_the_person_who_raised_it():
    """A requirement moving to blocked is the news its author most needs."""
    req = raise_requirement(created_by="@director")
    before = len(notifications_for("@director"))

    client.patch(f"/api/requirements/{req['requirement_id']}", json={
        "status": "blocked", "updated_by": "@sound_supervisor",
    })

    fresh = notifications_for("@director")
    assert len(fresh) == before + 1
    assert fresh[0]["notification_type"] == "STATUS_CHANGED"
    assert "blocked" in fresh[0]["message"]


def test_nobody_is_notified_about_their_own_change():
    req = raise_requirement(created_by="@director")
    before = len(notifications_for("@director"))

    client.patch(f"/api/requirements/{req['requirement_id']}", json={
        "status": "in_progress", "updated_by": "@director",
    })

    assert len(notifications_for("@director")) == before


def test_an_edit_that_changes_neither_owner_nor_status_notifies_nobody():
    """A typo fix is not news."""
    req = raise_requirement()
    before = len(notifications_for("@sound_supervisor")) + len(notifications_for("@director"))

    client.patch(f"/api/requirements/{req['requirement_id']}", json={
        "description": "No wild track for this setup; ask on the next unit day.",
        "updated_by": "@post_supervisor",
    })

    after = len(notifications_for("@sound_supervisor")) + len(notifications_for("@director"))
    assert after == before


def test_reassigning_to_the_same_person_is_not_a_handover():
    req = raise_requirement(assigned_to="@sound_supervisor")
    before = len(notifications_for("@sound_supervisor"))

    client.patch(f"/api/requirements/{req['requirement_id']}", json={
        "assigned_to": "@sound_supervisor", "updated_by": "@post_supervisor",
    })

    assert len(notifications_for("@sound_supervisor")) == before


def test_the_edit_itself_still_lands():
    req = raise_requirement()
    res = client.patch(f"/api/requirements/{req['requirement_id']}", json={
        "status": "blocked", "priority": "critical", "updated_by": "@post_supervisor",
    })
    assert res.status_code == 200
    assert (res.json()["status"], res.json()["priority"]) == ("blocked", "critical")


def test_editing_a_requirement_that_does_not_exist_is_a_404():
    assert client.patch("/api/requirements/req_nope", json={"status": "blocked"}).status_code == 404


# --------------------------------------------------------------------------- #
# What the board reads
# --------------------------------------------------------------------------- #

def test_a_production_can_be_asked_for_every_requirement_across_its_days():
    """
    The board answers "what is outstanding on this production", which no single
    shoot day can.
    """
    raise_requirement(shoot_day="31", title="Room tone missing")
    raise_requirement(shoot_day="39", title="VFX plate needed", category="vfx")

    listed = client.get("/api/requirements", params={"production_id": PROD}).json()
    days = {r["shoot_day"] for r in listed}
    assert {"31", "39"} <= days
