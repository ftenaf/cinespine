"""
Requirements, and the record of how they got where they are.

Two claims are tested here and they are different. That a requirement survives
the process is durability. That every transition survives is a record -- and it
is the part that was missing entirely: creating and resolving reached the spine,
while every handover and every block in between was an in-place overwrite, so
"who parked this" could not be answered five minutes later.

The requirement itself is not immutable. Its transitions are.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.spine import requirement_store
from backend.app.spine.requirement_store import UnknownRequirementValue
from backend.app.spine.clickhouse import database

client = TestClient(app)

PROD = "REQSTORE"


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


def trail(requirement_id: str):
    res = client.get(f"/api/requirements/{requirement_id}/history")
    assert res.status_code == 200, res.text
    return res.json()


# --------------------------------------------------------------------------- #
# It survives
# --------------------------------------------------------------------------- #

def test_a_requirement_is_stored_rather_than_remembered():
    """
    A requirement outlives the day it was raised on -- that is what raising one
    is for. Held in process memory, a restart wiped a production's outstanding
    work while the tags beside it survived.
    """
    req = raise_requirement()
    assert requirement_store.get(req["requirement_id"])["title"] == "Room tone missing"


def test_a_requirement_reads_back_the_same_way_it_went_in():
    req = raise_requirement(priority="critical", category="vfx")
    stored = requirement_store.get(req["requirement_id"])
    assert (stored["priority"], stored["category"], stored["target_label"]) == (
        "critical", "vfx", "Slate 27/7",
    )


def test_a_handle_is_stored_one_way_however_it_was_typed():
    """Two spellings of one person split their workload across two names."""
    req = raise_requirement(assigned_to="sound_supervisor")
    assert requirement_store.get(req["requirement_id"])["assigned_to"] == "@sound_supervisor"


def test_a_production_lists_its_requirements_across_every_day():
    raise_requirement(shoot_day="31")
    raise_requirement(shoot_day="39")
    days = {r["shoot_day"] for r in requirement_store.list_requirements(production_id=PROD)}
    assert {"31", "39"} <= days


@pytest.mark.parametrize("field,value", [
    ("status", "nearly"),
    ("priority", "urgent-ish"),
    ("category", "sound design"),
])
def test_a_value_outside_the_vocabulary_is_refused(field, value):
    """
    Free text makes the board's counts meaningless: blocked / Blocked / stuck
    are one state spelled three ways.
    """
    with pytest.raises(UnknownRequirementValue):
        requirement_store.create({"production_id": PROD, "title": "x", **{field: value}})


# --------------------------------------------------------------------------- #
# Every transition is kept
# --------------------------------------------------------------------------- #

def test_raising_a_requirement_is_itself_recorded():
    req = raise_requirement()
    entries = trail(req["requirement_id"])
    assert [e["action"] for e in entries] == ["created"]
    assert entries[0]["actor"] == "@director"


def test_a_block_is_recorded_with_who_did_it():
    """The question this exists for: who parked this, and when."""
    req = raise_requirement()
    client.patch(f"/api/requirements/{req['requirement_id']}", json={
        "status": "blocked", "updated_by": "@sound_supervisor",
    })

    entries = trail(req["requirement_id"])
    assert entries[0]["action"] == "status_changed"
    assert entries[0]["actor"] == "@sound_supervisor"
    assert entries[0]["changes"]["status"] == ["open", "blocked"]


def test_a_handover_is_recorded_as_a_handover():
    """
    Named for the change, not for the SQL. A reader looking for where a
    requirement went should not have to read every 'updated' row to find it.
    """
    req = raise_requirement()
    client.patch(f"/api/requirements/{req['requirement_id']}", json={
        "assigned_to": "@lead_editor", "updated_by": "@post_supervisor",
    })

    entries = trail(req["requirement_id"])
    assert entries[0]["action"] == "reassigned"
    assert entries[0]["changes"]["assigned_to"] == ["@sound_supervisor", "@lead_editor"]


def test_resolving_keeps_the_account_of_what_was_done():
    req = raise_requirement()
    client.post(f"/api/requirements/{req['requirement_id']}/resolve", json={
        "resolution_note": "Recorded on the pickup day.", "resolved_by": "@sound_supervisor",
    })

    entries = trail(req["requirement_id"])
    assert entries[0]["action"] == "resolved"
    assert entries[0]["note"] == "Recorded on the pickup day."


def test_re_opening_is_not_filed_as_an_ordinary_status_change():
    req = raise_requirement()
    client.post(f"/api/requirements/{req['requirement_id']}/resolve", json={
        "resolution_note": "Done.", "resolved_by": "@sound_supervisor",
    })
    client.patch(f"/api/requirements/{req['requirement_id']}", json={
        "status": "in_progress", "updated_by": "@director",
    })

    assert trail(req["requirement_id"])[0]["action"] == "reopened"


def test_the_trail_reads_newest_first():
    req = raise_requirement()
    client.patch(f"/api/requirements/{req['requirement_id']}", json={"status": "in_progress"})
    client.patch(f"/api/requirements/{req['requirement_id']}", json={"status": "blocked"})

    assert [e["action"] for e in trail(req["requirement_id"])] == [
        "status_changed", "status_changed", "created",
    ]


def test_an_edit_that_changes_nothing_writes_no_entry():
    """A trail of saves that did nothing buries the ones that did."""
    req = raise_requirement(priority="high")
    client.patch(f"/api/requirements/{req['requirement_id']}", json={"priority": "high"})
    assert len(trail(req["requirement_id"])) == 1


def test_deleting_a_requirement_keeps_the_fact_that_it_existed():
    """
    A board that can make work disappear without trace is a board nobody can
    audit. The row goes; the trail does not.
    """
    req = raise_requirement()
    client.delete(f"/api/requirements/{req['requirement_id']}", params={"deleted_by": "@director"})

    assert requirement_store.get(req["requirement_id"]) is None
    entries = trail(req["requirement_id"])
    assert entries[0]["action"] == "deleted"
    assert entries[0]["actor"] == "@director"


def test_a_change_and_its_record_are_written_together():
    """
    Written separately, a crash between them leaves a requirement whose history
    does not explain it -- a gap that looks like a record.
    """
    req = raise_requirement()
    requirement_store.update(req["requirement_id"], {"status": "blocked"}, actor="@ana")

    stored = requirement_store.get(req["requirement_id"])
    latest = trail(req["requirement_id"])[0]
    assert stored["status"] == latest["status"] == "blocked"


def test_a_production_wide_trail_shows_what_moved_across_it():
    first = raise_requirement(title="Room tone")
    second = raise_requirement(title="VFX plate")
    client.patch(f"/api/requirements/{second['requirement_id']}", json={"status": "blocked"})

    res = client.get("/api/requirements/activity", params={"production_id": PROD})
    assert res.status_code == 200
    ids = {e["requirement_id"] for e in res.json()}
    assert {first["requirement_id"], second["requirement_id"]} <= ids


def test_activity_is_not_read_as_a_requirement_id():
    """The static path is declared above the by-id read, and has to stay there."""
    assert client.get(
        "/api/requirements/activity", params={"production_id": PROD}
    ).status_code == 200


def test_a_trail_can_be_asked_for_by_neither_requirement_nor_production():
    with pytest.raises(UnknownRequirementValue):
        requirement_store.history()


def test_editing_a_field_that_identifies_the_requirement_is_refused():
    """
    production_id and created_at describe where a requirement belongs, not what
    it says. Moving them would relocate work rather than edit it.
    """
    req = raise_requirement()
    with pytest.raises(UnknownRequirementValue):
        requirement_store.update(req["requirement_id"], {"production_id": "SOMEWHERE_ELSE"})


def test_a_requirement_that_does_not_exist_has_an_empty_trail():
    assert trail("req_nope") == []


# --------------------------------------------------------------------------- #
# The analytical mirror, when there is one
# --------------------------------------------------------------------------- #

class FakeClickHouse:
    """Records what would have been inserted."""

    def __init__(self, fail=False):
        self.rows = []
        self.fail = fail

    def insert(self, table, rows, column_names):
        if self.fail:
            raise ConnectionError("clickhouse is down")
        self.rows.append((table, rows, column_names))


def _writer(fake):
    from backend.app.spine.writer import SpineWriter

    return SpineWriter(clickhouse_client=fake)


def _seed(writer, **over):
    return writer.create_requirement({
        "production_id": PROD, "shoot_day": "31", "target_type": "shot",
        "target_id": "27/7", "title": "Room tone missing", "priority": "high",
        "category": "sound", "created_by": "@director",
        "assigned_to": "@sound_supervisor", **over,
    })


def test_every_transition_is_mirrored_to_the_analytical_spine():
    fake = FakeClickHouse()
    writer = _writer(fake)
    req = _seed(writer)
    writer.update_requirement(req["requirement_id"], {"status": "blocked"}, actor="@ana")
    writer.resolve_requirement(req["requirement_id"], "Recorded on pickups.", "@ana")

    assert {table for table, _, _ in fake.rows} == {f"{database()}.requirement_events"}
    assert [dict(zip(c, r[0]))["action"] for _, r, c in fake.rows] == [
        "created", "status_changed", "resolved",
    ]


def test_the_mirrored_row_carries_what_moved():
    fake = FakeClickHouse()
    writer = _writer(fake)
    req = _seed(writer)
    writer.update_requirement(req["requirement_id"], {"assigned_to": "@lead_editor"}, actor="@ana")

    _, rows, columns = fake.rows[-1]
    row = dict(zip(columns, rows[0]))
    assert row["action"] == "reassigned"
    assert row["assigned_to"] == "@lead_editor"
    assert "sound_supervisor" in row["changes_json"]


def test_a_clickhouse_that_is_down_does_not_lose_the_requirement():
    """
    SQLite has already recorded it. Failing somebody's save because a reporting
    database is unreachable would be the wrong trade every time.
    """
    writer = _writer(FakeClickHouse(fail=True))
    req = _seed(writer)
    assert requirement_store.get(req["requirement_id"]) is not None
    assert trail(req["requirement_id"])[0]["action"] == "created"


def test_an_edit_that_changed_nothing_mirrors_nothing():
    fake = FakeClickHouse()
    writer = _writer(fake)
    req = _seed(writer, priority="high")
    before = len(fake.rows)
    writer.update_requirement(req["requirement_id"], {"priority": "high"}, actor="@ana")
    assert len(fake.rows) == before


def test_the_two_copies_of_the_trail_agree_on_the_order():
    """
    The mirrored timestamp is SQLite's own, not the server's clock at insert
    time: two copies that disagree on order make the trail useless for the one
    question it answers.
    """
    fake = FakeClickHouse()
    writer = _writer(fake)
    req = _seed(writer)
    writer.update_requirement(req["requirement_id"], {"status": "blocked"}, actor="@ana")

    stored = trail(req["requirement_id"])[0]
    _, rows, columns = fake.rows[-1]
    mirrored = dict(zip(columns, rows[0]))
    assert mirrored["event_id"] == stored["event_id"]
    assert mirrored["created_at"].isoformat().startswith(stored["created_at"][:19])
