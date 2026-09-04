"""
The workload queries: what people did, not what they own.

Three rules the SQL must hold to, each with a row built to break it:
views and mutations are never summed, rows with a fallback actor never
credit a person, and a requirement the assignee never touched counts as
waiting rather than vanishing.

Exercised against a real ClickHouse where one is running (the isolated
cinespine_test database); without it the SQL tests skip, because asserting
SQL against a stub proves the stub.
"""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.spine import activity_store, analytics
from backend.app.spine.clickhouse import database

HAS_CLICKHOUSE = bool(os.environ.get("CLICKHOUSE_HOST", "").strip())

COLUMNS = [
    "event_id", "production_id", "shoot_day", "actor", "department", "action",
    "target_type", "target_id", "target_label", "seconds_since_target_created",
    "context_json", "created_at",
]


def test_every_workload_query_answers_none_without_a_client():
    assert analytics.actions_by_actor_and_day(None, "P") is None
    assert analytics.actions_by_department_and_hour(None, "P") is None
    assert analytics.first_touch_lag(None, "P") is None


@pytest.fixture
def live():
    if not HAS_CLICKHOUSE:
        pytest.skip("No CLICKHOUSE_HOST; the SQL is not exercised")
    from backend.app.spine import clickhouse

    connected = clickhouse.connect()
    if connected is None:
        pytest.skip("CLICKHOUSE_HOST is set but unreachable")
    return connected


def _row(production_id, actor, action, target_type, target_id, at, shoot_day="31",
         department="", context=None):
    return [
        f"act_{uuid.uuid4().hex[:12]}", production_id, shoot_day, actor, department, action,
        target_type, target_id, "", None, json.dumps(context or {}), at,
    ]


@pytest.fixture
def ledger(live):
    """
    One production's worth of activity, inserted synchronously so the queries
    see it at once. A unique production id keeps runs from reading each other.
    """
    production_id = f"WORKLOAD_{uuid.uuid4().hex[:8]}"
    t0 = datetime(2026, 9, 4, 20, 0, 0, tzinfo=timezone.utc)
    m = lambda minutes: t0 + timedelta(minutes=minutes)  # noqa: E731
    defaulted = {activity_store.ACTOR_SOURCE_KEY: activity_store.ACTOR_SOURCE_DEFAULT}
    rows = [
        # @sound raises two requirements for @editor and one for @colorist.
        _row(production_id, "@sound", "created", "requirement", "R1", m(0),
             context={"assigned_to": "@editor"}),
        _row(production_id, "@sound", "created", "requirement", "R2", m(0),
             context={"assigned_to": "@editor"}),
        _row(production_id, "@sound", "created", "requirement", "R3", m(0),
             context={"assigned_to": "@colorist"}),
        # @editor looks at R1 after 10 minutes, takes it on at 30, resolves at 60.
        _row(production_id, "@editor", "viewed", "requirement", "R1", m(10), department="editorial"),
        _row(production_id, "@editor", "acknowledged", "requirement", "R1", m(30), department="editorial"),
        _row(production_id, "@editor", "resolved", "requirement", "R1", m(60), department="editorial"),
        # R2 is touched by somebody else, not its assignee: no first touch for @editor.
        _row(production_id, "@sound", "viewed", "requirement", "R2", m(5)),
        # R3 is never touched.
        # A rename nobody can be credited with.
        _row(production_id, "@director", "updated", "production", production_id, m(90),
             shoot_day="", context=defaulted),
    ]
    live.insert(f"{database()}.user_activity", rows, column_names=COLUMNS)
    return production_id


def test_views_and_mutations_stay_apart(ledger, live):
    rows = analytics.actions_by_actor_and_day(live, ledger)
    assert rows is not None
    by_actor = {(r["actor"], r["shoot_day"]): r for r in rows}
    editor = by_actor[("@editor", "31")]
    assert editor["mutations"] == 1, "resolved is the only mutation"
    assert editor["views"] == 2, "viewed and acknowledged are both views"
    assert editor["distinct_targets"] == 1
    sound = by_actor[("@sound", "31")]
    assert (sound["mutations"], sound["views"]) == (3, 1)


def test_a_fallback_actor_never_credits_a_person(ledger, live):
    rows = analytics.actions_by_actor_and_day(live, ledger)
    assert "@director" not in {r["actor"] for r in rows}

    # ...but the change still counts for the department's hour.
    hours = analytics.actions_by_department_and_hour(live, ledger)
    assert hours is not None
    general = [r for r in hours if r["department"] == "" and r["hour"] == 21]
    assert general and general[0]["mutations"] == 1


def test_department_hours_are_utc_hours(ledger, live):
    rows = analytics.actions_by_department_and_hour(live, ledger)
    editorial = {r["hour"]: r for r in rows if r["department"] == "editorial"}
    assert set(editorial) == {20, 21}
    assert editorial[20]["views"] == 2 and editorial[20]["mutations"] == 0
    assert editorial[21]["mutations"] == 1


def test_first_touch_counts_the_untouched(ledger, live):
    rows = analytics.first_touch_lag(live, ledger)
    assert rows is not None
    lag = {r["actor"]: r for r in rows}

    editor = lag["@editor"]
    assert editor["requirements"] == 2
    assert editor["touched"] == 1, "R2 was seen by @sound, which is not @editor touching it"
    assert editor["median_minutes"] == 10.0, "the view at +10 is the first touch, not the acknowledgement"

    colorist = lag["@colorist"]
    assert (colorist["requirements"], colorist["touched"]) == (1, 0)
    assert colorist["median_minutes"] is None or colorist["median_minutes"] != colorist["median_minutes"]  # NULL or NaN


def test_the_endpoint_carries_the_three_keys(ledger):
    from fastapi.testclient import TestClient

    from backend.app.main import app

    body = TestClient(app).get("/api/analytics", params={"production_id": ledger}).json()
    assert body["available"] is True, body
    for key in ("actions_by_actor_and_day", "actions_by_department_and_hour", "first_touch_lag"):
        assert body[key] is not None, key
