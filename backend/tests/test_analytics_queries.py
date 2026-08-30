"""
The read path to the analytical spine.

The mirror was write-only: thousands of events sat in it and nothing in the app
ever asked it anything. These tests cover the two things that decide whether
the read path is worth having -- that the app still works without it, and that
the one query making a claim about disagreement is not quietly counting
multi-camera setups as conflicts.

The SQL itself is exercised against a real ClickHouse where one is running;
without it these skip, because asserting SQL against a stub proves the stub.
"""
import os

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.spine import analytics

client = TestClient(app)

HAS_CLICKHOUSE = bool(os.environ.get("CLICKHOUSE_HOST", "").strip())
PROD = "ANALYTICS"


# --------------------------------------------------------------------------- #
# The app does not need it
# --------------------------------------------------------------------------- #

def test_every_query_answers_none_without_a_client():
    """
    None, not an empty list. "No analytical spine" and "asked, and the answer
    is nothing" are different, and a caller that cannot tell them apart draws
    an empty chart for both.
    """
    assert analytics.production_shape(None, PROD) is None
    assert analytics.department_arrivals(None, PROD) is None
    assert analytics.roll_disagreements(None, PROD) is None
    assert analytics.scene_coverage(None, PROD) is None
    assert analytics.editorial_state(None, PROD) is None
    assert analytics.requirement_ageing(None, PROD) is None
    assert analytics.table_sizes(None) is None


def test_a_query_that_fails_is_logged_and_not_raised():
    """
    An analytics panel must not be able to take a request down with it.
    """
    class Broken:
        def query(self, *_args, **_kwargs):
            raise ConnectionError("clickhouse went away mid-question")

    assert analytics.production_shape(Broken(), PROD) is None


@pytest.mark.skipif(HAS_CLICKHOUSE, reason="ClickHouse is configured in this environment")
def test_the_endpoint_says_so_rather_than_returning_empty_results():
    """
    An empty chart and an absent database look identical, which is the failure
    mode this project calls absence rendered as presence.
    """
    body = client.get("/api/analytics", params={"production_id": PROD}).json()
    assert body["available"] is False
    assert "CLICKHOUSE_HOST" in body["reason"]


# --------------------------------------------------------------------------- #
# The queries themselves, against a real instance
# --------------------------------------------------------------------------- #

@pytest.fixture
def live():
    if not HAS_CLICKHOUSE:
        pytest.skip("No CLICKHOUSE_HOST; the SQL is not exercised")
    from backend.app.spine import clickhouse

    connected = clickhouse.connect()
    if connected is None:
        pytest.skip("CLICKHOUSE_HOST is set but unreachable")
    return connected


def test_the_shape_query_runs(live):
    rows = analytics.production_shape(live, "DEMO_PRODUCTION")
    assert rows is not None
    assert all({"axis", "department", "events", "days"} <= set(r) for r in rows)


def test_the_arrivals_query_runs(live):
    rows = analytics.department_arrivals(live, "DEMO_PRODUCTION")
    assert rows is not None
    assert all({"shoot_day", "department", "first_filed"} <= set(r) for r in rows)


def test_a_multi_camera_take_is_not_reported_as_a_disagreement(live):
    """
    The trap this query exists to avoid. A take shot on cameras A, B and C
    carries three rolls and agrees with itself perfectly; asking only "more
    than one roll for this take" reports every multi-camera setup on the show
    as a conflict.

    The demo day is multi-camera throughout and every witness agrees, so the
    honest answer is nothing.
    """
    rows = analytics.roll_disagreements(live, "DEMO_PRODUCTION")
    assert rows == []


def test_scene_coverage_reads_whole_scenes(live):
    rows = analytics.scene_coverage(live, "DEMO_PRODUCTION")
    assert rows is not None
    assert all(r["scene"][:1].isdigit() for r in rows), "a scene number starts with a digit"


def test_the_editorial_state_is_derived_from_the_trail(live):
    """argMax over an append-only log, with no merge forced and no FINAL."""
    rows = analytics.editorial_state(live, "DEMO_PRODUCTION")
    assert rows is not None
    assert all({"status", "targets"} <= set(r) for r in rows)


def test_requirement_ageing_runs(live):
    rows = analytics.requirement_ageing(live, "DEMO_PRODUCTION")
    assert rows is not None
    assert all({"requirements", "avg_hours_open"} <= set(r) for r in rows)


def test_the_endpoint_answers_from_clickhouse(live):
    body = client.get("/api/analytics", params={"production_id": "DEMO_PRODUCTION"}).json()
    assert body["available"] is True
    assert body["shape"] is not None
    assert body["tables"] is not None
