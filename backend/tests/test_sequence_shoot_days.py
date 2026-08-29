"""
A sequence is shot over as many days as it takes.

Scene 119 covered on day 11 and finished on day 31 is ordinary, not an edge
case -- the second half of a scene is often shot weeks after the first. The
sequence matrix is a day's log and stays one, but a row that says only
"Day 31" reads as if the sequence began and ended there, and somebody
reconciling cards against it would never know to look at day 11.

Same mistake as two earlier ones, in a different place: a facing page filed on
the day it was handed over carries takes from across the schedule, and
projecting only the envelope's day left sixty takes out of the index.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)

# A production of its own per test. The spine is a process-wide cache, so two
# tests sharing an id would read each other's days.
@pytest.fixture
def prod(request):
    return f"MULTIDAY_{request.node.name.upper()}"

DAY_11 = (
    "Slate,Take,CameraRoll,ClipName,FPS,ISO,Lens,Scene,Description\n"
    "119/1,1,A012,A012_C001_0411.MOV,24,800,35mm,119,Master on the nave\n"
    "119/1,2,A012,A012_C002_0411.MOV,24,800,35mm,119,Master again\n"
)
DAY_31 = (
    "Slate,Take,CameraRoll,ClipName,FPS,ISO,Lens,Scene,Description\n"
    "119/5,1,A046,A046_C001_2807.MOV,24,800,50mm,119,Coverage on LEAD\n"
)
DAY_31_OTHER_SCENE = (
    "Slate,Take,CameraRoll,ClipName,FPS,ISO,Lens,Scene,Description\n"
    "27/7,1,A120,A120_C001_2807.MOV,24,800,35mm,27,Organ\n"
)


def upload(prod: str, content: str, shoot_day: str, filename: str):
    res = client.post("/api/upload", json={
        "raw_content": content,
        "filename": filename,
        "production_id": prod,
        "shoot_day": shoot_day,
    })
    assert res.status_code == 200, res.text


def sequences(prod: str, shoot_day: str):
    res = client.get("/api/sequences", params={"production_id": prod, "shoot_day": shoot_day})
    assert res.status_code == 200, res.text
    return {r["sequence"]: r for r in res.json()}


@pytest.fixture
def covered_over_two_days(prod):
    upload(prod, DAY_11, "11", "Probe-2026-4-11_CAM_A.csv")
    upload(prod, DAY_31, "31", "Probe-2026-7-28_CAM_A.csv")
    return prod


def test_a_sequence_shot_over_two_days_names_both(covered_over_two_days):
    assert sequences(covered_over_two_days, "11")["119"]["shoot_days"] == ["11", "31"]


def test_it_names_both_whichever_day_is_being_looked_at(covered_over_two_days):
    assert sequences(covered_over_two_days, "31")["119"]["shoot_days"] == ["11", "31"]


def test_the_row_is_still_about_the_day_that_was_asked_for(covered_over_two_days):
    """
    The matrix is a day's log. Knowing a sequence runs to other days must not
    turn every row into a summary of the whole schedule.
    """
    row = sequences(covered_over_two_days, "11")["119"]
    assert row["shoot_day"] == "Day 11"
    assert row["takes_count"] == 2  # day 11's takes, not day 31's as well


def test_a_sequence_shot_in_one_go_names_only_that_day(prod):
    upload(prod, DAY_31_OTHER_SCENE, "31", "Probe-2026-7-28_CAM_B.csv")
    assert sequences(prod, "31")["27"]["shoot_days"] == ["31"]


def test_the_days_read_in_shooting_order(covered_over_two_days):
    """
    Sorted as numbers, not as text: day 9 comes before day 11, and '11' < '9'
    as a string.
    """
    upload(covered_over_two_days, DAY_31, "9", "Probe-2026-2-01_CAM_A.csv")
    assert sequences(covered_over_two_days, "31")["119"]["shoot_days"] == ["9", "11", "31"]


def test_another_sequence_s_days_are_not_mixed_in(covered_over_two_days):
    upload(covered_over_two_days, DAY_31_OTHER_SCENE, "31", "Probe-2026-7-28_CAM_B.csv")
    rows = sequences(covered_over_two_days, "31")
    assert rows["119"]["shoot_days"] == ["11", "31"]
    assert rows["27"]["shoot_days"] == ["31"]
