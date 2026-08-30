"""
A day nobody has offloaded is not a day with material missing.

START-HERE names this as one of three things that are the shape of the whole
domain: "Absence of a report is not absence of material. A day nobody has
offloaded and a day with material missing must never render the same way. They
need opposite responses."

The gate had one side of that. It refused to report missing media without an
offload report, which is the negative, and then said nothing at all -- so the
day rendered as a clean day, which is the same mistake pointing the other way.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.reconciliation.engine import ReconciliationEngine
from backend.app.reconciliation.models import DiscrepancyType, Severity

client = TestClient(app)

PROD = "OFFLOAD"

SCRIPT_LOG = (
    "27/7 1 09:26:12:04 09:28:58:12\n"
    "A120 280726 2:46\n"
    "27/7 2 09:30:00:00 09:32:00:00\n"
    "A120 280726 2:00\n"
)


@pytest.fixture
def engine():
    return ReconciliationEngine()


def kinds(discrepancies):
    return [d.discrepancy_type for d in discrepancies]


# --------------------------------------------------------------------------- #
# The two sides of the gate
# --------------------------------------------------------------------------- #

def test_a_day_with_no_offload_report_says_so(engine):
    found = engine.reconcile_existence(
        production_id=PROD, shoot_day="31",
        logged_takes=[{"slate": "27/7", "take_id": "1", "clip_name": "A120_C001.MOV"}],
        media_files=[], has_offload_report=False,
    )
    assert kinds(found) == [DiscrepancyType.AWAITING_OFFLOAD]


def test_it_is_never_reported_as_missing_material(engine):
    """The negative the requirement states, and the one that already held."""
    found = engine.reconcile_existence(
        production_id=PROD, shoot_day="31",
        logged_takes=[{"slate": "27/7", "take_id": "1", "clip_name": "A120_C001.MOV"}],
        media_files=[], has_offload_report=False,
    )
    assert DiscrepancyType.PAPERWORK_WITHOUT_MEDIA not in kinds(found)


def test_once_the_report_arrives_a_missing_clip_is_a_real_gap(engine):
    found = engine.reconcile_existence(
        production_id=PROD, shoot_day="31",
        logged_takes=[{"slate": "27/7", "take_id": "1", "clip_name": "A120_C001.MOV"}],
        media_files=[{"file_name": "A120_C999.MOV", "camera_roll": "A120"}],
        has_offload_report=True,
    )
    assert DiscrepancyType.PAPERWORK_WITHOUT_MEDIA in kinds(found)
    assert DiscrepancyType.AWAITING_OFFLOAD not in kinds(found)


# --------------------------------------------------------------------------- #
# One per day, not one per take
# --------------------------------------------------------------------------- #

def test_a_day_of_takes_produces_one_finding(engine):
    """
    Per take it would fire on every take of every day not yet offloaded, which
    is most of a shoot. A notice that appears three hundred times is a notice
    people filter out, which puts the day back where it started.
    """
    takes = [{"slate": "27/7", "take_id": str(n), "clip_name": f"A120_C{n:03d}.MOV"} for n in range(1, 40)]
    found = engine.reconcile_existence(
        production_id=PROD, shoot_day="31",
        logged_takes=takes, media_files=[], has_offload_report=False,
    )
    assert len(found) == 1
    assert found[0].entity_type == "shoot_day"
    assert found[0].entity_id == "31"


def test_it_says_how_much_is_waiting(engine):
    takes = [{"slate": "27/7", "take_id": str(n)} for n in range(1, 4)]
    found = engine.reconcile_existence(
        production_id=PROD, shoot_day="31",
        logged_takes=takes, media_files=[], has_offload_report=False,
    )
    assert "3 takes" in found[0].description
    assert found[0].witnesses[0]["takes"] == 3


def test_it_is_not_reported_as_a_conflict(engine):
    """
    Nothing has gone wrong. Nobody has looked yet, which is a question rather
    than a fault, and dressing it as a warning would train people to ignore it.
    """
    found = engine.reconcile_existence(
        production_id=PROD, shoot_day="31",
        logged_takes=[{"slate": "27/7", "take_id": "1"}],
        media_files=[], has_offload_report=False,
    )
    assert found[0].severity == Severity.INFO


def test_a_day_with_nothing_logged_says_nothing():
    """
    No takes and no offload report is a day that has not started, not a day
    awaiting anything.
    """
    found = ReconciliationEngine().reconcile_existence(
        production_id=PROD, shoot_day="31",
        logged_takes=[], media_files=[], has_offload_report=False,
    )
    assert found == []


# --------------------------------------------------------------------------- #
# Through the API
# --------------------------------------------------------------------------- #

def test_the_day_reports_awaiting_offload_end_to_end():
    """
    The requirement's own falsification: a take in script notes on a day with
    no Silverstack report reads as AWAITING_OFFLOAD, not as missing media.
    """
    res = client.post("/api/upload", json={
        "raw_content": SCRIPT_LOG, "filename": "DEMO_TCLog_D031.txt",
        "production_id": "OFFLOAD_E2E", "shoot_day": "31",
    })
    assert res.status_code == 200

    found = client.get("/api/discrepancies", params={
        "production_id": "OFFLOAD_E2E", "shoot_day": "31",
    }).json()
    found_kinds = [d["discrepancy_type"] for d in found]

    assert "AWAITING_OFFLOAD" in found_kinds
    assert "PAPERWORK_WITHOUT_MEDIA" not in found_kinds


def test_existence_findings_reach_the_api_at_all():
    """
    They used to be computed into a local and dropped, so two of the four
    detections REQ-08 asks for never reached anybody.
    """
    from backend.app.agents.mcp_server import ClickHouseMCPServer
    import inspect

    source = inspect.getsource(ClickHouseMCPServer.query_production_discrepancies)
    assert "reconcile_existence" in source
    assert "all_discrepancies.append" in source.split("reconcile_existence")[1], (
        "reconcile_existence is called and its results are not collected"
    )
