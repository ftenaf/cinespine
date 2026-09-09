"""
The active-discrepancy gauge, which was declared and never set.

REQ-10 asks for it. It existed as a declaration with no caller, so it could
never fill -- and a metric that can never fill renders as a flat zero, which
reads as "nothing wrong" rather than "nothing measured". That is the failure
mode this project calls absence rendered as presence.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.core import telemetry
from backend.app.core.telemetry import TelemetryExporter
from backend.app.main import app
from backend.app.reconciliation.models import DiscrepancyType, Severity
from backend.tests.otel_metrics import metric_points

client = TestClient(app)


def series():
    """The gauge's current points, keyed by its four attributes."""
    return {
        (a["production_id"], a["shoot_day"], a["severity"], a["discrepancy_type"]): v
        for a, v in metric_points("cinespine.active_discrepancies")
    }


def a_discrepancy(severity=Severity.CRITICAL, kind=DiscrepancyType.ROLL_MISMATCH, resolved=False):
    d = {"severity": severity.value, "discrepancy_type": kind.value}
    if resolved:
        d["is_resolved"] = True
    return d


# --------------------------------------------------------------------------- #
# It fills
# --------------------------------------------------------------------------- #

def test_a_discrepancy_reaches_the_gauge():
    TelemetryExporter.record_discrepancies("GAUGE_A", "31", [a_discrepancy()])
    assert series()[("GAUGE_A", "31", "CRITICAL", "ROLL_MISMATCH")] == 1


def test_it_counts_rather_than_flags():
    TelemetryExporter.record_discrepancies("GAUGE_B", "31", [a_discrepancy()] * 3)
    assert series()[("GAUGE_B", "31", "CRITICAL", "ROLL_MISMATCH")] == 3


def test_every_kind_is_written_even_at_zero():
    """
    Explicit zeros say something silence does not: "no critical missing media
    on day 31" is a fact, and it differs from never having looked -- which
    stays absent from the metric entirely.
    """
    TelemetryExporter.record_discrepancies("GAUGE_C", "31", [a_discrepancy()])
    written = {k for k in series() if k[0] == "GAUGE_C"}
    assert len(written) == len(list(Severity)) * len(list(DiscrepancyType))
    assert series()[("GAUGE_C", "31", "INFO", "AWAITING_OFFLOAD")] == 0


def test_a_day_nobody_opened_has_no_series_at_all():
    """
    Absent, not zero. Zero would claim the day is clean.
    """
    assert not [k for k in series() if k[0] == "GAUGE_NEVER_OPENED"]


# --------------------------------------------------------------------------- #
# It empties again, which is the harder half
# --------------------------------------------------------------------------- #

def test_a_resolved_discrepancy_stops_being_counted():
    TelemetryExporter.record_discrepancies("GAUGE_D", "31", [a_discrepancy()])
    assert series()[("GAUGE_D", "31", "CRITICAL", "ROLL_MISMATCH")] == 1

    TelemetryExporter.record_discrepancies("GAUGE_D", "31", [a_discrepancy(resolved=True)])
    assert series()[("GAUGE_D", "31", "CRITICAL", "ROLL_MISMATCH")] == 0, (
        "a gauge keeps its last value, so a fixed problem would stay on the board"
    )


def test_a_kind_that_has_gone_away_drops_to_zero():
    TelemetryExporter.record_discrepancies("GAUGE_E", "31", [
        a_discrepancy(kind=DiscrepancyType.ROLL_MISMATCH),
        a_discrepancy(kind=DiscrepancyType.TIMECODE_DRIFT),
    ])
    TelemetryExporter.record_discrepancies("GAUGE_E", "31", [
        a_discrepancy(kind=DiscrepancyType.ROLL_MISMATCH),
    ])
    assert series()[("GAUGE_E", "31", "CRITICAL", "TIMECODE_DRIFT")] == 0


def test_one_day_does_not_overwrite_another():
    """
    Why the gauge carries production and shoot_day. Without them the second day
    somebody opened would replace the first while still looking like a total.
    """
    TelemetryExporter.record_discrepancies("GAUGE_F", "31", [a_discrepancy()] * 2)
    TelemetryExporter.record_discrepancies("GAUGE_F", "32", [a_discrepancy()])

    assert series()[("GAUGE_F", "31", "CRITICAL", "ROLL_MISMATCH")] == 2
    assert series()[("GAUGE_F", "32", "CRITICAL", "ROLL_MISMATCH")] == 1


def test_a_kind_nobody_declared_is_ignored_rather_than_invented():
    TelemetryExporter.record_discrepancies("GAUGE_G", "31", [
        {"severity": "CRITICAL", "discrepancy_type": "SOMETHING_NEW"},
    ])
    assert not [k for k in series() if k[0] == "GAUGE_G" and k[3] == "SOMETHING_NEW"]


# --------------------------------------------------------------------------- #
# Through the API, and out of the exporter
# --------------------------------------------------------------------------- #

def test_asking_for_a_day_publishes_its_count():
    client.post("/api/upload", json={
        "raw_content": "27/7 1 09:26:12:04 09:28:58:12\nA120 280726 2:46\n",
        "filename": "GAUGE_TCLog_D031.txt",
        "production_id": "GAUGE_API", "shoot_day": "31",
    })
    client.get("/api/discrepancies", params={"production_id": "GAUGE_API", "shoot_day": "31"})

    written = {k: v for k, v in series().items() if k[0] == "GAUGE_API"}
    assert written, "querying a day published nothing"


def test_the_gauge_leaves_through_the_otel_exporter():
    """
    It used to be served at /api/metrics for a scraper that, on Cloud Run,
    never came. Now it is an OTel gauge and goes out with gen_ai_*.
    """
    TelemetryExporter.record_discrepancies("GAUGE_EXPORT", "31", [a_discrepancy()])
    assert any(a["production_id"] == "GAUGE_EXPORT"
               for a, _ in metric_points("cinespine.active_discrepancies"))
    assert "cinespine_" not in client.get("/api/metrics").text


# --------------------------------------------------------------------------- #
# The one that was removed, and came back
# --------------------------------------------------------------------------- #

def test_the_sync_lag_gauge_is_back_and_measurable():
    """
    This asserted the gauge was *gone*, and that was right while it was: wrap
    is a time of day, nothing bound a shoot day to a date, and a gauge that can
    never fill renders as a flat zero -- "no lag" rather than "not known".

    The date reached the spine the same afternoon, so the subtraction is real
    and the gauge is back. What keeps it honest now is the `measurement` label:
    see test_sync_lag.py. Kept rather than deleted, because the reason it went
    is worth as much as the reason it returned.
    """
    assert hasattr(telemetry, "DEPARTMENT_SYNC_LAG")
    assert hasattr(TelemetryExporter, "record_sync_lag")

    TelemetryExporter.record_sync_lag("GAUGE_MEASURED", [
        {"shoot_day": "31", "department": "camera", "lag_seconds": 120.0, "measurement": "handover"},
    ])
    points = [a for a, _ in metric_points("cinespine.department_sync_lag")
              if a["production_id"] == "GAUGE_MEASURED"]
    assert points and points[0]["measurement"] == "handover", (
        "without it a backfill and a handover are one number on a dashboard"
    )


def test_it_still_publishes_nothing_it_cannot_measure():
    """
    The half of the original decision that survives. A day with no wrap or no
    date has no baseline, and a zero would claim the department filed at the
    moment of a wrap nobody recorded.
    """
    TelemetryExporter.record_sync_lag("GAUGE_UNMEASURED", [
        {"shoot_day": "31", "department": "camera", "lag_seconds": None, "measurement": None},
    ])
    assert not [a for a, _ in metric_points("cinespine.department_sync_lag")
                if a["production_id"] == "GAUGE_UNMEASURED"]


def test_enum_members_count_the_same_as_their_values():
    """model_dump() hands the gauge enum members, not strings; both must count."""
    TelemetryExporter.record_discrepancies("GAUGE_E", "31", [
        {"severity": Severity.WARNING, "discrepancy_type": DiscrepancyType.TIMECODE_DRIFT, "is_resolved": False},
        {"severity": "WARNING", "discrepancy_type": "TIMECODE_DRIFT", "is_resolved": False},
    ])
    assert series()[("GAUGE_E", "31", "WARNING", "TIMECODE_DRIFT")] == 2
