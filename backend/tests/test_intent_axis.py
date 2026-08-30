"""
Office's page, and the axis the architecture is named for.

Before this, an Office document was classified, published to
`production.raw.office`, and consumed by nobody. The upload answered INGESTED
and the spine gained nothing -- the confident nothing, on the intent axis.

Two things are tested here and they are different. That the fields are read is
parsing. That intent and Office's *belief* stay apart is the domain: Office is
authoritative for what was planned and never for what happened, and writing
`Scenes Complete` as reality would make the plan authoritative for something
Office does not observe.
"""
import os

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.parsers.base import ParserFailureError
from backend.app.parsers.dpr import parse_daily_production_report

client = TestClient(app)

REAL_DPR = (
    "E:/projects/agentic-cinema/docs/domain/examples/20260728/LAC_ParteProd_D031_280726.pdf"
)

# Shaped like the real page, including the two negatives filled in -- the real
# day 31 left them blank, and a parser that only ever sees blanks is a parser
# nobody has tested on the interesting case.
FIXTURE = """LAC DAILY PRODUCTION REPORT
Shooting Day: 31

Scenes Scheduled: 27pt, 49pt, 117pt, 6WT
Scenes Complete: 27pt, 49pt
Scenes Part Complete: 117pt
Scenes Scheduled Not Shot: 6WT
Scenes Shot Not Scheduled: 88

CITACION GENERAL: 08:00 Total Paginas: 1 6/8
PRIMER MOTOR MANANA: 09:25 Set-Ups: 35
BOCATA: 11:07 Camera Cards: A120 - A123
COMIDA: 14:00 Sound Cards: 280726
PRIMER MOTOR TARDE: 16:20 Slates: 27/7 - 8, 49/1 - 9, 117/1 - 5
WRAP: 18:55

INDIVIDUAL SCENE TIMINGS
Scene Read Shoot +/- PC
27 1'45" 2'30" +45" 1
49 55" 2'30" +1'35" 3/8
"""


# --------------------------------------------------------------------------- #
# Reading the page
# --------------------------------------------------------------------------- #

def test_the_five_named_scene_fields_are_read():
    report = parse_daily_production_report(FIXTURE)
    assert [s.scene for s in report.scenes_scheduled] == ["27", "49", "117", "6"]
    assert [s.scene for s in report.scenes_complete] == ["27", "49"]
    assert [s.scene for s in report.scenes_part_complete] == ["117"]
    assert [s.scene for s in report.scenes_scheduled_not_shot] == ["6"]
    assert [s.scene for s in report.scenes_shot_not_scheduled] == ["88"]


def test_part_complete_is_a_third_state_not_the_absence_of_complete():
    """
    dept-office.md: not_shot is not the boolean complement of shot. Folding
    three states into two loses the one the day actually ended in.
    """
    report = parse_daily_production_report(FIXTURE)
    assert "117" not in [s.scene for s in report.scenes_complete]
    assert "117" in [s.scene for s in report.scenes_part_complete]


def test_a_scene_keeps_the_suffix_the_report_wrote():
    """
    What `pt` means on this production has not been confirmed. The number is
    extracted so it can be joined; the token is kept so nothing is invented.
    """
    scheduled = parse_daily_production_report(FIXTURE).scenes_scheduled
    assert [s.raw for s in scheduled] == ["27pt", "49pt", "117pt", "6WT"]


def test_a_field_stated_and_left_blank_is_not_a_field_that_is_absent():
    """
    Office wrote 'Scenes Scheduled Not Shot:' and left it empty because
    nothing went unshot. That is a positive fact, and different from a report
    that does not carry the field at all.
    """
    blank = FIXTURE.replace("Scenes Scheduled Not Shot: 6WT", "Scenes Scheduled Not Shot:")
    report = parse_daily_production_report(blank)
    assert report.scenes_scheduled_not_shot == []
    assert "scenes_scheduled_not_shot" in report.fields_present


def test_the_wrap_time_is_read_because_lag_is_measured_from_it():
    assert parse_daily_production_report(FIXTURE).times["wrap"] == "18:55"


def test_the_day_is_bracketed_by_its_call_and_meal_times():
    times = parse_daily_production_report(FIXTURE).times
    assert times["general_call"] == "08:00"
    assert times["lunch"] == "14:00"


def test_a_value_stops_where_the_next_label_starts():
    """
    Labels share lines: 'BOCATA: 11:07 Camera Cards: A120 - A123'. Reading to
    the end of the line would swallow the next field whole.
    """
    report = parse_daily_production_report(FIXTURE)
    assert report.times["snack"] == "11:07"
    assert report.camera_card_range == "A120 - A123"
    assert report.set_ups == 35


def test_the_slate_ranges_give_a_completeness_check_nothing_else_provides():
    """A slate outside every stated range was never scheduled."""
    ranges = {r.scene: (r.first, r.last) for r in parse_daily_production_report(FIXTURE).slate_ranges}
    assert ranges == {"27": ("27/7", "27/8"), "49": ("49/1", "49/9"), "117": ("117/1", "117/5")}


def test_the_scene_timings_are_read():
    timings = parse_daily_production_report(FIXTURE).scene_timings
    assert [t.scene for t in timings] == ["27", "49"]


# --------------------------------------------------------------------------- #
# The confident nothing
# --------------------------------------------------------------------------- #

def test_an_empty_report_is_a_failure_not_an_empty_result():
    with pytest.raises(ParserFailureError):
        parse_daily_production_report("")


def test_a_document_with_none_of_the_fields_is_a_failure():
    """
    A page that produced nothing while reporting success is the failure this
    project spends most of its effort on. Adding a handler that does it on the
    intent axis would move the problem rather than fix it.
    """
    with pytest.raises(ParserFailureError):
        parse_daily_production_report("A shopping list\nMilk\nBread\n")


def test_the_failure_names_what_it_was_looking_for():
    with pytest.raises(ParserFailureError, match="Scenes Scheduled"):
        parse_daily_production_report("Not a production report at all.")


# --------------------------------------------------------------------------- #
# On to the spine
# --------------------------------------------------------------------------- #

def upload(production_id: str, content: str = FIXTURE, filename: str = "ParteProd_D031.txt"):
    res = client.post("/api/upload", json={
        "raw_content": content, "filename": filename,
        "production_id": production_id, "shoot_day": "31",
    })
    assert res.status_code == 200, res.text
    return res.json()


def events_for(production_id: str):
    from backend.app.api.routes import spine_writer

    return spine_writer.get_events(production_id=production_id, shoot_day="31")


def test_an_office_document_now_reaches_the_spine():
    """It used to publish to a topic nobody listened on."""
    body = upload("INTENT_LANDS")
    assert body["detected_department"] == "office"
    assert events_for("INTENT_LANDS"), "the DPR produced no events"


def test_the_plan_lands_on_the_intent_axis():
    upload("INTENT_PLAN")
    scheduled = [
        e["payload"]["scene"] for e in events_for("INTENT_PLAN")
        if e["axis"] == "intent" and e["payload"].get("state") == "scheduled"
    ]
    assert scheduled == ["27", "49", "117", "6"]


def test_what_office_believes_happened_is_not_written_as_reality():
    """
    Office does not observe what happened. Writing 'Scenes Complete' as
    existence would make the plan authoritative for something it cannot see --
    the boundary dept-office.md calls load-bearing.
    """
    upload("INTENT_BELIEF")
    events = events_for("INTENT_BELIEF")
    complete = [e for e in events if e["payload"].get("office_state") == "complete"]
    assert complete, "Scenes Complete produced nothing"
    assert all(e["axis"] == "belief" for e in complete)
    assert not any(e["axis"] == "existence" for e in events)


def test_both_negatives_leave_the_page():
    """They are stated in named fields every day and have always died there."""
    upload("INTENT_NEGATIVES")
    states = {
        e["payload"].get("office_state"): e["payload"]["scene"]
        for e in events_for("INTENT_NEGATIVES") if e["payload"].get("office_state")
    }
    assert states.get("scheduled_not_shot") == "6"
    assert states.get("shot_not_scheduled") == "88"


def test_the_day_itself_is_recorded_with_its_wrap_time():
    upload("INTENT_DAY")
    day = [e for e in events_for("INTENT_DAY") if e["entity_type"] == "shoot_day"]
    assert len(day) == 1
    assert day[0]["payload"]["times"]["wrap"] == "18:55"
    assert day[0]["payload"]["set_ups"] == 35


def test_a_report_that_parses_to_nothing_is_rejected_rather_than_ingested():
    """
    The handler must not repeat the mistake it was written to fix. A document
    that reaches it and yields no fields goes to the dead letter queue.
    """
    from backend.app.api.routes import event_bus

    seen = []
    event_bus.subscribe("production.events.dlq", lambda e: seen.append(e))
    upload("INTENT_DLQ", content="PARTE DE PRODUCCION\nnothing else at all\n")

    assert not events_for("INTENT_DLQ"), "a report with no fields produced events"
    assert any(e.get("error_type") == "PARSER_FAILURE" for e in seen)


# --------------------------------------------------------------------------- #
# The disagreement it makes visible
# --------------------------------------------------------------------------- #

def test_a_scene_office_calls_shot_with_no_material_is_a_disagreement():
    """
    The case sitting in the real day 31: Office reports 117 and 6WT complete,
    and no camera, sound or offload paperwork mentions either.
    """
    prod = "INTENT_DISAGREE"
    upload(prod)
    client.post("/api/upload", json={
        "raw_content": (
            "Slate,Take,CameraRoll,ClipName,FPS,ISO,Lens,Scene,Description\n"
            "27/7,1,A120,A120_C001_260728.MOV,24,800,50mm,27,Organ\n"
        ),
        "filename": "Probe-2026-7-28_CAM_A.csv",
        "production_id": prod, "shoot_day": "31",
    })

    found = client.get("/api/discrepancies", params={
        "production_id": prod, "shoot_day": "31",
    }).json()
    claimed = [d for d in found if d["discrepancy_type"] == "SCENE_COMPLETE_WITHOUT_MATERIAL"]
    # 49 was called complete and 117 part complete; only 27 has any material.
    # Part complete counts: some of the scene was shot, so something should
    # have been filed for it.
    assert {d["entity_id"] for d in claimed} == {"49", "117"}


def test_nothing_is_claimed_before_any_department_has_filed():
    """
    A day nobody has offloaded is not a day that went wrong. Same gate the
    existence check uses.
    """
    prod = "INTENT_NO_MATERIAL"
    upload(prod)
    found = client.get("/api/discrepancies", params={
        "production_id": prod, "shoot_day": "31",
    }).json()
    assert not [d for d in found if d["discrepancy_type"] == "SCENE_COMPLETE_WITHOUT_MATERIAL"]


# --------------------------------------------------------------------------- #
# The real page
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not os.path.exists(REAL_DPR), reason="Example PDFs not present locally")
def test_the_real_day_31_report_parses():
    """
    Built against the page, not against the field table in the design doc. A
    parser written from a description and never run on the document is how the
    first version returns zero rows on the real thing.
    """
    from backend.app.parsers.pdf_parsers import extract_text_from_pdf

    with open(REAL_DPR, "rb") as f:
        report = parse_daily_production_report(extract_text_from_pdf(f.read()))

    assert [s.raw for s in report.scenes_scheduled] == ["27pt", "49pt", "117pt", "6WT"]
    assert [s.raw for s in report.scenes_complete] == ["27pt", "49pt", "117pt", "6WT"]
    assert report.times["wrap"] == "18:55"
    assert report.set_ups == 35
    assert {r.scene for r in report.slate_ranges} == {"27", "49", "117"}
