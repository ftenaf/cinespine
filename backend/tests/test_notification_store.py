"""
The alerts sent to a person.

Held in process memory, this was the one part of the exchange that did not
survive a restart: the requirement stayed and its trail stayed, while the alert
telling the sound supervisor it was now theirs quietly vanished. An alert
nobody can be shown was never sent.

Unlike a requirement there is no separate trail here. A notification is written
once and never edited; the only thing that changes is whether it has been read,
so the row is already the record.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.spine import notification_store
from backend.app.spine.notification_store import UnknownNotificationValue

client = TestClient(app)

PROD = "NOTIFSTORE"
ANA = "@ana_editor"
BEN = "@ben_sound"


def send(**over):
    return notification_store.create({
        "production_id": PROD,
        "recipient_handle": ANA,
        "actor_handle": "@director",
        "notification_type": "ASSIGNED",
        "requirement_id": "req_x",
        "title": "Slate 27/7",
        "message": "@director handed you this high requirement: Room tone missing",
        "target_type": "shot",
        "target_id": "27/7",
        "target_label": "Slate 27/7",
        **over,
    })


def inbox(handle=ANA, unread_only=False):
    res = client.get("/api/notifications", params={
        "user_handle": handle, "unread_only": unread_only,
    })
    assert res.status_code == 200, res.text
    return res.json()


# --------------------------------------------------------------------------- #
# It survives
# --------------------------------------------------------------------------- #

def test_an_alert_is_stored_rather_than_remembered():
    notif = send()
    assert notification_store.get(notif["notification_id"])["message"].startswith("@director")


def test_an_alert_reaches_the_person_it_was_addressed_to():
    send()
    assert len(inbox(ANA)["notifications"]) == 1


def test_an_alert_does_not_reach_anybody_else():
    send(recipient_handle=BEN)
    assert inbox(ANA)["notifications"] == []


@pytest.mark.parametrize("written", ["ana_editor", " @ana_editor ", "@ANA_EDITOR"])
def test_one_person_is_one_inbox_however_the_handle_was_typed(written):
    send(recipient_handle=written)
    assert len(inbox(ANA)["notifications"]) == 1


def test_an_alert_with_no_recipient_is_refused():
    """It would sit in the table forever, counted by nothing and shown to nobody."""
    with pytest.raises(UnknownNotificationValue):
        send(recipient_handle="")


def test_a_type_outside_the_vocabulary_is_refused():
    with pytest.raises(UnknownNotificationValue):
        send(notification_type="POKE")


def test_alerts_read_newest_first():
    send(title="first")
    send(title="second")
    assert [n["title"] for n in inbox(ANA)["notifications"]] == ["second", "first"]


# --------------------------------------------------------------------------- #
# Read and unread
# --------------------------------------------------------------------------- #

def test_a_new_alert_starts_unread():
    notif = send()
    assert notification_store.get(notif["notification_id"])["is_read"] is False
    assert inbox(ANA)["unread_count"] == 1


def test_reading_an_alert_records_when_it_was_read():
    """
    An alert opened within the minute and one opened after nine days are not
    the same event, and only the second says the routing is wrong.
    """
    notif = send()
    client.post(f"/api/notifications/{notif['notification_id']}/read")

    stored = notification_store.get(notif["notification_id"])
    assert stored["is_read"] is True
    assert stored["read_at"] is not None


def test_re_reading_does_not_move_the_moment_it_was_first_seen():
    notif = send()
    client.post(f"/api/notifications/{notif['notification_id']}/read")
    first = notification_store.get(notif["notification_id"])["read_at"]
    client.post(f"/api/notifications/{notif['notification_id']}/read")
    assert notification_store.get(notif["notification_id"])["read_at"] == first


def test_the_unread_filter_leaves_out_what_has_been_read():
    read_me = send(title="read")
    send(title="unread")
    client.post(f"/api/notifications/{read_me['notification_id']}/read")

    assert [n["title"] for n in inbox(ANA, unread_only=True)["notifications"]] == ["unread"]


def test_the_badge_counts_only_what_is_unread():
    first = send()
    send()
    client.post(f"/api/notifications/{first['notification_id']}/read")
    assert inbox(ANA)["unread_count"] == 1


def test_the_badge_counts_only_this_person_s_alerts():
    send(recipient_handle=ANA)
    send(recipient_handle=BEN)
    send(recipient_handle=BEN)
    assert inbox(ANA)["unread_count"] == 1
    assert inbox(BEN)["unread_count"] == 2


def test_marking_everything_read_clears_one_inbox_and_not_another():
    send(recipient_handle=ANA)
    send(recipient_handle=ANA)
    send(recipient_handle=BEN)

    res = client.post("/api/notifications/read-all", params={"user_handle": ANA})
    assert res.json()["updated_count"] == 2
    assert inbox(ANA)["unread_count"] == 0
    assert inbox(BEN)["unread_count"] == 1


def test_marking_everything_read_twice_reports_nothing_the_second_time():
    send()
    client.post("/api/notifications/read-all", params={"user_handle": ANA})
    assert client.post(
        "/api/notifications/read-all", params={"user_handle": ANA}
    ).json()["updated_count"] == 0


def test_reading_an_alert_that_does_not_exist_is_a_404():
    """
    It used to answer success for an id nobody had ever issued, so a client
    reading a stale notification was told it worked.
    """
    assert client.post("/api/notifications/nope/read").status_code == 404


def test_an_empty_inbox_is_an_empty_list_not_an_error():
    body = inbox("@nobody_at_all")
    assert (body["notifications"], body["unread_count"]) == ([], 0)


# --------------------------------------------------------------------------- #
# What it is sent about
# --------------------------------------------------------------------------- #

def test_a_handover_reaches_the_new_owner_and_survives_being_looked_up():
    """The end-to-end path: the board hands a requirement on, and the alert
    is still there afterwards to be shown."""
    created = client.post("/api/requirements", json={
        "production_id": PROD, "shoot_day": "31", "target_type": "shot",
        "target_id": "27/7", "title": "Room tone missing",
        "created_by": "@director", "assigned_to": ANA,
    }).json()

    client.patch(f"/api/requirements/{created['requirement_id']}", json={
        "assigned_to": BEN, "updated_by": "@post_supervisor",
    })

    alerts = inbox(BEN)["notifications"]
    assert alerts[0]["notification_type"] == "ASSIGNED"
    assert notification_store.get(alerts[0]["notification_id"]) is not None
