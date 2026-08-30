"""
The department sync matrix REQ-10 asks for.

It could not be computed for most of this project's life. Wrap is stated as a
time of day -- `18:55` -- and nothing bound a shoot day to a calendar date, so
there was no moment to subtract from. The gauge was removed rather than left
permanently empty, because a flat zero reads as "no lag" and not as "not
known". The date reached the spine on 2026-08-30 and the subtraction is real.

# The thing these tests are really about

The lag being computable does not make every lag a handover. Paperwork loaded
into the system a month after the shoot has a correct lag that says nothing
about the night it was filed, and 780 hours in a matrix a reader expects to be
hours tells them something false in a form that looks true -- which is worse
than the empty gauge it replaces. So every measurement says which kind it is,
and nothing here decides a backfill is uninteresting: only that it is not the
same measurement.
"""
from datetime import datetime, timezone

import pytest

from backend.app.core import sync_lag
from backend.app.core.sync_lag import BACKFILL, HANDOVER

WRAP = "18:55"
DATE = "2026-07-28"


def moment(*args):
    return datetime(*args, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# The baseline
# --------------------------------------------------------------------------- #

def test_wrap_and_date_make_a_moment():
    assert sync_lag.wrap_moment(DATE, WRAP) == moment(2026, 7, 28, 18, 55)


@pytest.mark.parametrize("date,wrap", [
    (DATE, None), (None, WRAP), (None, None), ("", ""), ("not-a-date", WRAP), (DATE, "nonsense"),
])
def test_half_a_fact_is_not_a_baseline(date, wrap):
    """
    Completing either half by assuming the other would invent the baseline
    every number in the matrix is measured from.
    """
    assert sync_lag.wrap_moment(date, wrap) is None


def test_a_wrap_after_midnight_belongs_to_the_night_of_the_shoot():
    """
    `02:30` on a day that called at 08:00 is the small hours of the following
    date, not a wrap sixteen hours before the call.
    """
    assert sync_lag.wrap_moment(DATE, "02:30") == moment(2026, 7, 29, 2, 30)


# --------------------------------------------------------------------------- #
# The measurement
# --------------------------------------------------------------------------- #

def test_the_lag_is_the_gap_between_wrap_and_filing():
    wrapped = sync_lag.wrap_moment(DATE, WRAP)
    assert sync_lag.lag_seconds(wrapped, moment(2026, 7, 28, 23, 10)) == pytest.approx(4.25 * 3600)


def test_paperwork_filed_before_wrap_keeps_its_negative():
    """
    A camera report closed at lunch is a real thing. Clamping it to zero would
    hide it, and what it is not is a fast handover.
    """
    wrapped = sync_lag.wrap_moment(DATE, WRAP)
    assert sync_lag.lag_seconds(wrapped, moment(2026, 7, 28, 14, 0)) < 0


def test_nothing_to_measure_is_none_rather_than_zero():
    assert sync_lag.lag_seconds(None, moment(2026, 7, 28, 23, 10)) is None
    assert sync_lag.lag_seconds(sync_lag.wrap_moment(DATE, WRAP), None) is None


def test_a_naive_timestamp_is_read_as_utc():
    """ClickHouse hands back naive datetimes; treating them as local would move
    every lag by the machine's offset."""
    wrapped = sync_lag.wrap_moment(DATE, WRAP)
    naive = datetime(2026, 7, 28, 23, 10)
    assert sync_lag.lag_seconds(wrapped, naive) == pytest.approx(4.25 * 3600)


# --------------------------------------------------------------------------- #
# Handover or backfill -- the distinction the whole design rests on
# --------------------------------------------------------------------------- #

def test_filing_on_the_night_is_a_handover():
    assert sync_lag.classify(4.25 * 3600) == HANDOVER


def test_filing_a_month_later_is_a_backfill():
    """
    The real demo data: every department filed 780-odd hours after wrap because
    the paperwork was imported, not because anybody was slow.
    """
    assert sync_lag.classify(780 * 3600) == BACKFILL


def test_the_boundary_is_inclusive():
    window = sync_lag.handover_window_hours() * 3600
    assert sync_lag.classify(window) == HANDOVER
    assert sync_lag.classify(window + 1) == BACKFILL


def test_nothing_measured_is_classified_as_nothing():
    """Not "handover" by default. An unmeasured day has not been fast."""
    assert sync_lag.classify(None) is None


def test_the_window_is_configurable(monkeypatch):
    """
    48 hours is a judgement, not a domain fact -- a day's paperwork is expected
    before the next shooting day and a weekend can sit between. A production
    that works differently should not inherit this one's habits.
    """
    monkeypatch.setenv("CINESPINE_HANDOVER_WINDOW_HOURS", "6")
    assert sync_lag.handover_window_hours() == 6
    assert sync_lag.classify(10 * 3600) == BACKFILL


@pytest.mark.parametrize("bad", ["banana", "", "  ", "-5", "0"])
def test_an_unusable_window_falls_back_rather_than_breaking(monkeypatch, bad):
    monkeypatch.setenv("CINESPINE_HANDOVER_WINDOW_HOURS", bad)
    assert sync_lag.handover_window_hours() == sync_lag.DEFAULT_HANDOVER_WINDOW_HOURS


# --------------------------------------------------------------------------- #
# What reaches Prometheus
# --------------------------------------------------------------------------- #

def series():
    from backend.app.core import telemetry

    out = {}
    for metric in telemetry.DEPARTMENT_SYNC_LAG.collect():
        for sample in metric.samples:
            lb = sample.labels
            out[(lb["production_id"], lb["shoot_day"], lb["department"], lb["measurement"])] = sample.value
    return out


def test_a_measured_row_reaches_the_gauge():
    from backend.app.core.telemetry import TelemetryExporter

    TelemetryExporter.record_sync_lag("LAGP", [{
        "shoot_day": "31", "department": "sound",
        "lag_seconds": 4.25 * 3600, "measurement": HANDOVER,
    }])
    assert series()[("LAGP", "31", "sound", HANDOVER)] == pytest.approx(4.25 * 3600)


def test_a_backfill_is_published_under_its_own_label():
    """
    Published, not hidden -- but never as a handover. A dashboard can show both
    and cannot add them together by accident.
    """
    from backend.app.core.telemetry import TelemetryExporter

    TelemetryExporter.record_sync_lag("LAGP", [{
        "shoot_day": "31", "department": "dit",
        "lag_seconds": 780 * 3600, "measurement": BACKFILL,
    }])
    assert ("LAGP", "31", "dit", BACKFILL) in series()
    assert ("LAGP", "31", "dit", HANDOVER) not in series()


def test_a_row_with_no_baseline_publishes_nothing():
    """
    Writing zero would claim the department filed at the moment of a wrap
    nobody recorded.
    """
    from backend.app.core.telemetry import TelemetryExporter

    TelemetryExporter.record_sync_lag("LAGQ", [{
        "shoot_day": "31", "department": "camera",
        "lag_seconds": None, "measurement": None,
    }])
    assert not [k for k in series() if k[0] == "LAGQ"]


# --------------------------------------------------------------------------- #
# The matrix
# --------------------------------------------------------------------------- #

def test_the_matrix_is_none_without_a_client():
    from backend.app.spine import analytics

    assert analytics.sync_matrix(None, "ANY") is None


def test_a_row_with_no_wrap_keeps_its_place(monkeypatch):
    """
    The department filed; what is missing is the baseline. Dropping the row
    would make the day look emptier than it is.
    """
    from backend.app.spine import analytics

    monkeypatch.setattr(analytics, "department_sync_lag", lambda c, p: [
        {"shoot_day": "31", "department": "camera", "events": 9,
         "first_filed": datetime(2026, 8, 30, 9, 9), "shoot_date": "", "wrap_time": ""},
    ])
    rows = analytics.sync_matrix(object(), "ANY")
    assert len(rows) == 1
    assert rows[0]["measurable"] is False
    assert rows[0]["lag_hours"] is None
    assert rows[0]["measurement"] is None


def test_the_matrix_classifies_each_row(monkeypatch):
    from backend.app.spine import analytics

    monkeypatch.setattr(analytics, "department_sync_lag", lambda c, p: [
        {"shoot_day": "31", "department": "sound", "events": 4,
         "first_filed": datetime(2026, 7, 28, 23, 10), "shoot_date": DATE, "wrap_time": WRAP},
        {"shoot_day": "31", "department": "dit", "events": 6,
         "first_filed": datetime(2026, 8, 30, 18, 4), "shoot_date": DATE, "wrap_time": WRAP},
    ])
    rows = {r["department"]: r for r in analytics.sync_matrix(object(), "ANY")}
    assert rows["sound"]["measurement"] == HANDOVER
    assert rows["sound"]["lag_hours"] == pytest.approx(4.25)
    assert rows["dit"]["measurement"] == BACKFILL
    assert rows["dit"]["lag_hours"] > 700
