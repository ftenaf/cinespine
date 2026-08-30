"""
What calendar date a shoot day was, and whether the departments agree.

A shoot day is a number. A date is a date. Nothing bound the two, so the
department sync lag could not be computed and the gauge for it was removed
rather than left permanently empty.

Francisco, 2026-08-30, answering `open-questions.md`:

> You can find the shooting date in the daily production report on the top of
> the page... but you can find it also in the Thumbnail Report (260728_SD31 ->
> 28 July - 2026). Also on every script report on the header (Date:
> 28/07/2026). Also on the sound csv header... So to find the shooting date you
> should look at the Thumbnail Report, because it's the most reliable one.

Five witnesses to one fact, which is the shape this whole product is built
around. They can disagree, and when they do a document is filed under the wrong
day -- taking every take on it along.
"""
import pytest

from backend.app.normalizers.shoot_days import extract_shoot_date
from backend.app.reconciliation.engine import ReconciliationEngine
from backend.app.reconciliation.models import DiscrepancyType, Severity

THUMBNAIL = (
    "Pomfort Silverstack Thumbnail Report\n"
    "Production: DEMO PRODUCTION\n"
    "260728_SD31\n"
)


# --------------------------------------------------------------------------- #
# Reading the date
# --------------------------------------------------------------------------- #

def test_the_volume_stamp_gives_the_date_and_the_day_together():
    """
    Named as the most reliable source, and this is why: it is the only place
    the date and the shoot day are written together, so the two cannot be
    paired wrongly.
    """
    found = extract_shoot_date(THUMBNAIL, "Thumbnail-260728_SD31-20260728-1927.pdf")
    assert found == {"date": "2026-07-28", "source": "volume_stamp", "shoot_day": "31"}


def test_the_stamp_reads_year_month_day():
    """`260728` is 2026-07-28, not 26 July 2028."""
    found = extract_shoot_date("", "Thumbnail-260728_SD31.pdf")
    assert found["date"] == "2026-07-28"


@pytest.mark.parametrize("header,expected", [
    ("Script / Continuity Report\nDate: 28/07/2026\n", "2026-07-28"),
    ("PARTE DE PRODUCCION\nDATE: 28/07/26\n", "2026-07-28"),
    ("Sound Report\nDate:\t27/07/26\n", "2026-07-27"),
])
def test_a_labelled_header_is_read(header, expected):
    assert extract_shoot_date(header, "report.txt")["date"] == expected


def test_a_camera_report_carries_it_only_in_the_filename():
    found = extract_shoot_date("Slate,Take,CameraRoll\n27/7,1,A120\n",
                               "DemoProduction-2026-7-28_CAM_A.csv")
    assert found == {"date": "2026-07-28", "source": "filename", "shoot_day": None}


def test_the_volume_stamp_wins_over_a_header():
    """
    His order of reliability, not ours. A thumbnail report carries both, and
    the stamp is the one that cannot have been paired with the wrong day.
    """
    found = extract_shoot_date(THUMBNAIL + "Date: 01/01/2020\n", "Thumbnail-260728_SD31.pdf")
    assert found["source"] == "volume_stamp"
    assert found["date"] == "2026-07-28"


def test_a_document_that_states_no_date_says_so():
    """
    None rather than a guess. A document that does not say what day it covers
    has not said it, and inventing one puts every take on the wrong date.
    """
    assert extract_shoot_date("Slate,Take\n27/7,1\n", "untitled.csv") is None
    assert extract_shoot_date("", "") is None


def test_only_the_header_is_read():
    """
    A date further down belongs to a row, not to the report. A facing page
    carries dates from across the schedule, and the last one on it is not the
    day the page was filed.
    """
    body = "Sound Report\n" + ("filler line\n" * 400) + "Date: 01/01/2020\n"
    assert extract_shoot_date(body, "report.txt") is None


@pytest.mark.parametrize("bad", ["Date: 45/13/2026", "Date: 00/00/0000"])
def test_numbers_that_cannot_be_a_date_are_refused(bad):
    assert extract_shoot_date(bad, "report.txt") is None


# --------------------------------------------------------------------------- #
# Whether the departments agree
# --------------------------------------------------------------------------- #

def claim(department, date, source="labelled_header", filename="doc.txt"):
    return {
        "department": department,
        "payload": {"date": date, "source": source, "filename": filename},
    }


@pytest.fixture
def engine():
    return ReconciliationEngine()


def test_agreement_is_silent(engine):
    found = engine.reconcile_shoot_date("P", "31", [
        claim("dit", "2026-07-28", "volume_stamp"),
        claim("script", "2026-07-28"),
        claim("camera", "2026-07-28", "filename"),
    ])
    assert found == []


def test_a_disagreement_is_reported(engine):
    found = engine.reconcile_shoot_date("P", "31", [
        claim("dit", "2026-07-28", "volume_stamp"),
        claim("sound", "2026-07-27"),
    ])
    assert len(found) == 1
    assert found[0].discrepancy_type == DiscrepancyType.SHOOT_DATE_DISAGREEMENT
    assert found[0].severity == Severity.WARNING
    assert "2026-07-27" in found[0].description
    assert "2026-07-28" in found[0].description


def test_it_names_every_witness_and_what_each_said(engine):
    """
    The finding cannot say which document is wrong -- that is a question for
    the people who wrote them -- so it carries what each one said.
    """
    found = engine.reconcile_shoot_date("P", "31", [
        claim("dit", "2026-07-28", "volume_stamp", "Thumbnail.pdf"),
        claim("sound", "2026-07-27", "labelled_header", "Report.csv"),
    ])
    witnesses = found[0].witnesses
    assert {w["department"] for w in witnesses} == {"dit", "sound"}
    assert {w["document"] for w in witnesses} == {"Thumbnail.pdf", "Report.csv"}
    assert {w["source"] for w in witnesses} == {"volume_stamp", "labelled_header"}


def test_it_does_not_pick_a_winner(engine):
    """
    The volume stamp is the most reliable source and that still does not make
    it the answer. Resolving the disagreement here would hide the thing worth
    seeing.
    """
    found = engine.reconcile_shoot_date("P", "31", [
        claim("dit", "2026-07-28", "volume_stamp"),
        claim("sound", "2026-07-27"),
    ])
    assert len(found) == 1, "the disagreement was resolved rather than reported"


def test_one_claim_is_not_a_disagreement(engine):
    assert engine.reconcile_shoot_date("P", "31", [claim("dit", "2026-07-28")]) == []


def test_no_claims_is_not_a_clean_day(engine):
    """
    A day whose paperwork states no date has not agreed about anything. It is
    silence, and reporting agreement would be absence rendered as presence.
    """
    assert engine.reconcile_shoot_date("P", "31", []) == []
    assert engine.reconcile_shoot_date("P", "31", [{"department": "dit", "payload": {}}]) == []


def test_several_documents_saying_the_same_wrong_thing_is_still_one_finding(engine):
    found = engine.reconcile_shoot_date("P", "31", [
        claim("dit", "2026-07-28"), claim("camera", "2026-07-28"),
        claim("script", "2026-07-28"), claim("sound", "2026-07-27"),
    ])
    assert len(found) == 1
    assert len(found[0].witnesses) == 4
