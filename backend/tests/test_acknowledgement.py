"""
Who saw what, and when they took it on.

`handoffs.md` names the gap: "No acknowledgement is recorded anywhere." A
blocker is raised, a notification goes out, and nothing in the production can
answer whether the person it was for ever saw it.

The distinction the whole axis rests on is `viewed` against `acknowledged`. A
view is weak evidence about attention; an acknowledgement is a claim somebody
made. Only the second can carry an obligation, and conflating them would turn
"three people happened to have this on screen" into "three people took this on".
"""
import os

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.spine import activity_store
from backend.app.spine.activity_store import UnknownActivityValue

client = TestClient(app)
PROD = "ACK"


def record(**kwargs):
    body = {
        "production_id": PROD, "actor": "@sound_supervisor", "action": "viewed",
        "target_type": "requirement", "target_id": "REQ-1",
    }
    body.update(kwargs)
    return client.post("/api/activity", json=body)


# --------------------------------------------------------------------------- #
# The two kinds of event
# --------------------------------------------------------------------------- #

def test_a_view_is_recorded():
    res = record(action="viewed", target_id="REQ-VIEW")
    assert res.status_code == 200, res.text
    assert res.json()["action"] == "viewed"


def test_an_acknowledgement_is_recorded():
    res = record(action="acknowledged", target_id="REQ-ACK")
    assert res.status_code == 200, res.text
    assert res.json()["action"] == "acknowledged"


def test_a_view_is_not_an_acknowledgement():
    """
    The distinction the axis exists for. Somebody having a requirement on
    screen is not somebody taking it on, and only the second is a claim that
    can carry an obligation.
    """
    record(action="viewed", target_id="REQ-SEEN")
    body = client.get("/api/activity", params={
        "production_id": PROD, "target_type": "requirement", "target_id": "REQ-SEEN",
    }).json()

    assert body["viewed_by"] == ["@sound_supervisor"]
    assert body["acknowledged_by"] is None
    assert body["acknowledged_at"] is None


def test_unacknowledged_is_null_rather_than_false():
    """
    "Nobody has acknowledged this" and "this needs no acknowledgement" are
    different, and a boolean cannot tell them apart.
    """
    record(action="viewed", target_id="REQ-NULL")
    body = client.get("/api/activity", params={
        "production_id": PROD, "target_type": "requirement", "target_id": "REQ-NULL",
    }).json()
    assert body["acknowledged_at"] is None
    assert body["acknowledged_at"] is not False


def test_the_first_acknowledgement_is_the_one_that_counts():
    """
    What a handover asks is when somebody took this on. A second person
    acknowledging later does not move that moment.
    """
    record(action="acknowledged", actor="@editor", target_id="REQ-FIRST")
    record(action="acknowledged", actor="@dop", target_id="REQ-FIRST")
    body = client.get("/api/activity", params={
        "production_id": PROD, "target_type": "requirement", "target_id": "REQ-FIRST",
    }).json()
    assert body["acknowledged_by"] == "@editor"


# --------------------------------------------------------------------------- #
# The vocabulary is closed
# --------------------------------------------------------------------------- #

def test_an_action_nobody_declared_is_refused():
    """
    A surface inventing its own verb produces rows no query groups with
    anything else: present in the table, absent from every answer.
    """
    assert record(action="glanced-at").status_code == 400


def test_a_target_nobody_declared_is_refused():
    assert record(target_type="mood").status_code == 400


@pytest.mark.parametrize("missing", [{"actor": ""}, {"target_id": ""}])
def test_an_event_without_an_actor_or_a_target_is_refused(missing):
    assert record(**missing).status_code == 400


def test_the_store_refuses_the_same_things_directly():
    with pytest.raises(UnknownActivityValue):
        activity_store.record(
            production_id=PROD, actor="@a", action="skimmed",
            target_type="requirement", target_id="X",
        )


# --------------------------------------------------------------------------- #
# Time to acknowledge
# --------------------------------------------------------------------------- #

def test_the_age_of_the_target_is_measured_here_not_sent_by_the_client():
    """
    A browser clock is not a witness, and time-to-acknowledge is the whole
    point of the record.
    """
    raised = client.post("/api/requirements", json={
        "production_id": PROD, "shoot_day": "31", "target_type": "scene",
        "target_id": "27", "title": "Needs a re-record",
        "created_by": "@script_supervisor", "assigned_to": "@sound_supervisor",
    })
    assert raised.status_code == 200, raised.text
    requirement_id = raised.json()["requirement_id"]

    res = record(action="acknowledged", target_id=requirement_id,
                 department="sound", context={"seconds_since_target_created": 99999})
    assert res.status_code == 200
    age = res.json()["seconds_since_target_created"]
    assert age is not None
    assert age < 60, "the age was taken from the client rather than measured"


def test_a_target_with_no_creation_time_records_no_age():
    """
    None rather than zero. Zero would say it was acknowledged instantly, which
    is a claim, and it would drag every average it appears in towards a number
    nobody measured.
    """
    res = record(action="acknowledged", target_type="scene", target_id="27")
    assert res.json()["seconds_since_target_created"] is None


# --------------------------------------------------------------------------- #
# It reaches the mirror
# --------------------------------------------------------------------------- #

class FakeClickHouse:
    def __init__(self):
        self.rows = []

    def insert(self, table, rows, column_names):
        self.rows.append((table, rows, column_names))

    def command(self, sql, parameters=None):
        pass


def test_an_activity_event_is_mirrored():
    from backend.app.spine.clickhouse import database
    from backend.app.spine.writer import SpineWriter

    fake = FakeClickHouse()
    writer = SpineWriter(clickhouse_client=fake)
    writer.record_activity(
        production_id=PROD, actor="@editor", action="acknowledged",
        target_type="requirement", target_id="REQ-MIRROR", department="editorial",
    )
    tables = [t for t, _, _ in fake.rows]
    assert f"{database()}.user_activity" in tables


def test_a_mirror_that_is_down_does_not_fail_the_acknowledgement():
    """
    Somebody taking on a blocker must not fail because a reporting database is
    unreachable. Same contract as the tag and requirement trails.
    """
    from backend.app.spine.writer import SpineWriter

    class Broken(FakeClickHouse):
        def insert(self, table, rows, column_names):
            raise ConnectionError("clickhouse went away")

    writer = SpineWriter(clickhouse_client=Broken())
    event = writer.record_activity(
        production_id=PROD, actor="@editor", action="acknowledged",
        target_type="requirement", target_id="REQ-DOWN",
    )
    assert event["event_id"]
    assert writer.acknowledgement_of(PROD, "requirement", "REQ-DOWN") is not None


# --------------------------------------------------------------------------- #
# The queries, against a real ClickHouse when there is one
# --------------------------------------------------------------------------- #

HAS_CLICKHOUSE = bool(os.environ.get("CLICKHOUSE_HOST", "").strip())


@pytest.fixture
def live():
    if not HAS_CLICKHOUSE:
        pytest.skip("No CLICKHOUSE_HOST; the SQL is not exercised")
    from backend.app.spine import clickhouse

    connected = clickhouse.connect()
    if connected is None:
        pytest.skip("CLICKHOUSE_HOST is set but unreachable")
    return connected


def test_every_activity_query_answers_none_without_a_client():
    """
    None, not an empty list. "No analytical spine" and "asked, and the answer
    is nothing" are different, and a caller that cannot tell them apart draws
    an empty chart for both.
    """
    from backend.app.spine import analytics

    assert analytics.time_to_acknowledge(None, PROD) is None
    assert analytics.unacknowledged_requirements(None, PROD) is None
    assert analytics.unreviewed_days(None, PROD) is None
    assert analytics.department_attention(None, PROD) is None


@pytest.mark.parametrize("query", [
    "time_to_acknowledge", "unacknowledged_requirements",
    "unreviewed_days", "department_attention",
])
def test_the_query_runs(live, query):
    from backend.app.spine import analytics

    rows = getattr(analytics, query)(live, "DEMO_PRODUCTION")
    assert rows is not None, f"{query} failed against ClickHouse"


def test_the_analytics_endpoint_carries_the_acknowledgement_axis():
    body = client.get("/api/analytics", params={"production_id": "DEMO_PRODUCTION"}).json()
    if not body.get("available"):
        pytest.skip("No analytical spine connected")
    for key in ("time_to_acknowledge", "unacknowledged_requirements",
                "unreviewed_days", "department_attention"):
        assert key in body, f"{key} is missing from the analytics surface"
