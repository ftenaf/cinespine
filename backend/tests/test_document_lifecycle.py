"""
Deleting a document, and refusing the same file twice.

Both are places where the system can appear to work while doing nothing: a
delete that reports success without purging, and a re-ingest that silently
doubles the paperwork behind the spine.
"""
import io
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)

CSV = (
    "Slate,Take,CameraRoll,ClipName,FPS,ISO,Lens,Scene,Description\n"
    "77/1,1,A200,A200_C001_260728,24.0,800,50mm,77,{marker}\n"
)


@pytest.fixture
def prod():
    """A production of its own, so one test cannot dedupe against another."""
    return f"LIFECYCLE_{uuid.uuid4().hex[:8]}"


def upload(prod, content, filename="DemoProduction-2026-7-28_CAM_A.csv"):
    return client.post(
        "/api/upload/file",
        files={"file": (filename, io.BytesIO(content.encode()), "text/csv")},
        data={"production_id": prod, "shoot_day": "31"},
    )


def documents(prod):
    res = client.get(f"/api/documents?production_id={prod}&shoot_day=31")
    assert res.status_code == 200
    return res.json()


# --------------------------------------------------------------------------- #
# Delete
# --------------------------------------------------------------------------- #

def test_deleting_a_document_removes_it(prod):
    doc_id = upload(prod, CSV.format(marker=prod)).json()["doc_id"]
    assert len(documents(prod)) == 1

    res = client.delete(f"/api/documents/{doc_id}")
    assert res.status_code == 200
    assert res.json()["status"] == "DELETED"
    assert documents(prod) == []


def test_deleting_a_document_purges_its_takes(prod):
    """
    The point of the button is the spine, not the file listing. A delete that
    leaves the ingested takes behind has removed the evidence and kept the
    conclusions.
    """
    doc_id = upload(prod, CSV.format(marker=prod)).json()["doc_id"]
    takes = client.get(f"/api/takes?production_id={prod}&shoot_day=31").json()
    assert takes, "the upload should have produced takes to purge"

    client.delete(f"/api/documents/{doc_id}")
    after = client.get(f"/api/takes?production_id={prod}&shoot_day=31").json()
    assert after == []


def test_deleting_an_unknown_document_is_a_404_not_a_silent_success():
    res = client.delete(f"/api/documents/{uuid.uuid4()}")
    assert res.status_code == 404


def test_a_deleted_document_can_be_uploaded_again(prod):
    """Removal has to actually free the checksum, or delete is not undo."""
    content = CSV.format(marker=prod)
    doc_id = upload(prod, content).json()["doc_id"]
    client.delete(f"/api/documents/{doc_id}")

    again = upload(prod, content)
    assert again.status_code == 200


# --------------------------------------------------------------------------- #
# Refusing the same file twice
# --------------------------------------------------------------------------- #

def test_the_same_file_is_refused_the_second_time(prod):
    content = CSV.format(marker=prod)
    assert upload(prod, content).status_code == 200

    second = upload(prod, content)
    assert second.status_code == 409
    assert len(documents(prod)) == 1


def test_the_refusal_names_the_file_it_is_already_filed_under(prod):
    """
    The frontend shows this text verbatim. "Upload failed" is not actionable;
    the name it is already stored under is.
    """
    content = CSV.format(marker=prod)
    upload(prod, content, filename="ZoeLog_CAM_A_day31.csv")
    detail = upload(prod, content, filename="a_different_name.csv").json()["detail"]
    assert "ZoeLog_CAM_A_day31.csv" in detail


def test_a_different_file_is_still_accepted(prod):
    assert upload(prod, CSV.format(marker="first")).status_code == 200
    assert upload(prod, CSV.format(marker="second")).status_code == 200
    assert len(documents(prod)) == 2


def test_seeding_twice_does_not_double_the_paperwork(prod):
    """
    Seed bypassed the duplicate check the upload routes enforce, so a second
    click stored every document again under an identical checksum.
    """
    first = client.post("/api/seed", json={"production_id": prod, "shoot_day": "31"})
    assert first.status_code == 200
    count = len(documents(prod))
    assert count > 0

    second = client.post("/api/seed", json={"production_id": prod, "shoot_day": "31"})
    assert second.status_code == 200
    assert len(documents(prod)) == count, "a second seed must not re-store anything"
    assert second.json()["ingested_count"] == 0
    assert second.json()["skipped_count"] == count


def test_a_second_seed_reports_what_it_skipped(prod):
    client.post("/api/seed", json={"production_id": prod, "shoot_day": "31"})
    body = client.post("/api/seed", json={"production_id": prod, "shoot_day": "31"}).json()
    assert body["skipped_files"], "silently ingesting nothing looks the same as succeeding"
