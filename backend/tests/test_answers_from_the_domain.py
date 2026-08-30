"""
Three answers from the domain source, made real in code.

Recorded in references/open-questions.md on 2026-08-30 and acted on here. Each
had been guessed at, deferred, or left as an assumption nothing enforced.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.parsers.camera_csv import looks_like_a_take, parse_camera_csv
from backend.app.parsers.base import ParserFailureError

client = TestClient(app)


# --------------------------------------------------------------------------- #
# "Reject rows that do not look like takes"
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("slate", [
    "27/7", "64A/1", "49WT", "6WT", "41+122A/4", "27-7T01", "+99BDF/1", "49/WT",
])
def test_a_real_slate_is_a_take(slate):
    assert looks_like_a_take(slate) is True


@pytest.mark.parametrize("line", [
    "Contact: supervisor@example.com  Tel: 600 123 456",
    "TOTAL",
    "Camera Report Day 31",
    "Notes: LEAD plays organ",
    "",
    None,
])
def test_a_row_that_is_not_a_take_is_not_one(line):
    assert looks_like_a_take(line) is False


def test_a_contact_line_never_becomes_a_slate():
    """
    The defect this answers: a camera CSV footer reached the spine, the
    analytical mirror, and an analytics result as the scene it was grouped
    under. normalize_slate canonicalises whatever it is given.
    """
    csv = (
        "Slate,Take,CameraRoll,ClipName,FPS,ISO,Lens,Scene,Description\n"
        "27/7,1,A120,A120_C001_260728.MOV,24,800,50mm,27,Organ\n"
        "Contact: supervisor@example.com  Tel: 600 123 456,,,,,,,,\n"
    )
    records = parse_camera_csv(csv)
    assert [r.slate for r in records] == ["27/7"]
    assert not any("supervisor@example.com" in str(r.slate) for r in records)


def test_the_takes_above_a_junk_row_are_kept():
    """
    Skipped, not rejected. One footer does not make the document unparseable,
    and refusing the whole report would lose the takes above it.
    """
    csv = (
        "Slate,Take,CameraRoll,ClipName,FPS,ISO,Lens,Scene,Description\n"
        "27/7,1,A120,A120_C001.MOV,24,800,50mm,27,Organ\n"
        "TOTAL,,,,,,,,\n"
        "27/8,1,A120,A120_C002.MOV,24,800,50mm,27,Nave\n"
    )
    assert [r.slate for r in parse_camera_csv(csv)] == ["27/7", "27/8"]


def test_a_document_that_is_entirely_junk_still_fails():
    """
    The empty-result guard has to survive the new filter, or skipping rows
    becomes a way to produce the confident nothing.
    """
    csv = (
        "Slate,Take,CameraRoll,ClipName,FPS,ISO,Lens,Scene,Description\n"
        "TOTAL,,,,,,,,\n"
        "Contact: someone@example.com,,,,,,,,\n"
    )
    with pytest.raises(ParserFailureError):
        parse_camera_csv(csv)


# --------------------------------------------------------------------------- #
# "Yes" -- requirements should have a production target level
# --------------------------------------------------------------------------- #

def test_a_requirement_can_be_about_the_whole_production():
    """
    A delivery obligation, a legal clearance, a format decision: about the
    production and not about any one scene in it.
    """
    res = client.post("/api/requirements", json={
        "production_id": "ANSWERS", "shoot_day": "31",
        "target_type": "production", "target_id": "ANSWERS",
        "target_label": "Whole production",
        "title": "Deliver DCP by the 12th",
        "priority": "high", "category": "legal",
        "created_by": "@post_supervisor", "assigned_to": "@post_supervisor",
    })
    assert res.status_code == 200, res.text
    assert res.json()["target_type"] == "production"


def test_the_other_three_levels_still_work():
    for target_type, target_id in (("scene", "27"), ("shot", "27/7"), ("take", "27/7_1")):
        res = client.post("/api/requirements", json={
            "production_id": "ANSWERS", "shoot_day": "31",
            "target_type": target_type, "target_id": target_id,
            "title": f"A {target_type} requirement",
            "created_by": "@director", "assigned_to": "@director",
        })
        assert res.status_code == 200, f"{target_type}: {res.text}"


def test_a_level_nobody_named_is_still_refused():
    from backend.app.spine import requirement_store

    with pytest.raises(requirement_store.UnknownRequirementValue):
        requirement_store.create({
            "production_id": "ANSWERS", "title": "x", "target_type": "department",
        })


# --------------------------------------------------------------------------- #
# "We should remove it also from clickhouse"
# --------------------------------------------------------------------------- #

class FakeClickHouse:
    """Records the commands it was asked to run."""

    def __init__(self):
        self.commands = []
        self.rows = []

    def insert(self, table, rows, column_names):
        self.rows.append((table, rows, column_names))

    def command(self, sql, parameters=None):
        self.commands.append((sql, parameters or {}))


def test_deleting_a_document_purges_it_from_the_mirror_too():
    """
    The mirror is append-only and this is the one thing allowed to delete from
    it. Without this a row that should never have been ingested could not be
    got rid of at all.
    """
    from backend.app.spine.writer import SpineWriter

    fake = FakeClickHouse()
    writer = SpineWriter(clickhouse_client=fake)
    doc_id = writer.store_document(
        production_id="ANSWERS", shoot_day="31", filename="CAM_A.csv",
        doc_type="camera_csv", department="camera", content="x", raw_bytes=None,
    )

    assert writer.delete_document(doc_id) is True
    purges = [c for c in fake.commands if "ALTER TABLE" in c[0] and "DELETE" in c[0]]
    assert purges, "the deleted document was not purged from the mirror"
    assert purges[0][1]["doc_id"] == doc_id


def test_a_mirror_that_is_down_does_not_fail_the_delete():
    """
    The document is already gone from the store the app reads, so a mirror
    that is unreachable costs the tidying and nothing else.
    """
    from backend.app.spine.writer import SpineWriter

    class Broken(FakeClickHouse):
        def command(self, sql, parameters=None):
            raise ConnectionError("clickhouse went away")

    writer = SpineWriter(clickhouse_client=Broken())
    doc_id = writer.store_document(
        production_id="ANSWERS", shoot_day="31", filename="CAM_B.csv",
        doc_type="camera_csv", department="camera", content="x", raw_bytes=None,
    )
    assert writer.delete_document(doc_id) is True
    assert writer.get_document(doc_id) is None
