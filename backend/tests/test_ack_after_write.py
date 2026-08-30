"""
An upload that did not land must not report INGESTED.

`EventBus.publish` used to log a handler exception and return, so a spine write
that failed still produced a 200 with `"status": "INGESTED"`. The day then held
a stored document with no events in it -- which looks exactly like a day that
went fine. The confident nothing, in the ingest path.

The fix is acknowledging after the write. Handlers stay isolated from each
other; what changed is that their failures are reported instead of absorbed.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.streaming.bus import EventBus, EventHandlerError

client = TestClient(app)

CAMERA_CSV = (
    "Slate,Take,CameraRoll,ClipName,FPS,ISO,Lens,Scene,Description\n"
    "27/7,1,A120,A120_C001_260728.MOV,24,800,50mm,27,Organ\n"
)


def boom(_event):
    raise OSError("database or disk is full")


# --------------------------------------------------------------------------- #
# The bus reports rather than absorbs
# --------------------------------------------------------------------------- #

def test_a_failing_handler_is_reported_to_the_caller():
    bus = EventBus()
    bus.subscribe("production.events.spine", boom)
    with pytest.raises(EventHandlerError):
        bus.publish("production.events.spine", {"slate": "27/7"})


def test_the_error_says_what_failed_and_where():
    bus = EventBus()
    bus.subscribe("production.events.spine", boom)
    with pytest.raises(EventHandlerError) as caught:
        bus.publish("production.events.spine", {})

    exc = caught.value
    assert exc.topic == "production.events.spine"
    assert "disk is full" in str(exc)
    assert exc.reasons == ["OSError: database or disk is full"]


def test_every_handler_still_runs_before_it_raises():
    """
    Isolation and reporting are both required, and they pull opposite ways.
    Raising on the first failure would let one department's broken handler
    stop another department's document from being written at all.
    """
    bus = EventBus()
    ran = []
    bus.subscribe("t", boom)
    bus.subscribe("t", ran.append)
    bus.subscribe("t", boom)
    bus.subscribe("t", lambda e: ran.append("second"))

    with pytest.raises(EventHandlerError) as caught:
        bus.publish("t", {"x": 1})

    assert ran == [{"x": 1}, "second"], "a later handler was skipped"
    assert len(caught.value.failures) == 2


def test_a_publish_where_nothing_fails_raises_nothing():
    bus = EventBus()
    bus.subscribe("t", lambda e: None)
    bus.publish("t", {"x": 1})


# --------------------------------------------------------------------------- #
# A failed spine write is not a rejected document
# --------------------------------------------------------------------------- #

def test_a_spine_failure_does_not_become_a_dlq_entry():
    """
    The DLQ means "this paperwork was refused", which sends someone to check a
    report. A disk error means the machinery failed and the report was fine --
    filing it as a rejection would send that person to the wrong place.
    """
    from backend.app.streaming.dispatcher import IngestionDispatcher
    from backend.app.streaming.models import (
        EventEnvelope, AxisType, DepartmentType, DocumentType,
    )

    bus = EventBus()
    IngestionDispatcher(bus=bus)
    bus.subscribe("production.events.spine", boom)

    dlq = []
    bus.subscribe("production.events.dlq", dlq.append)

    envelope = EventEnvelope(
        production_id="ACK", shoot_day="31", axis=AxisType.BELIEF,
        department=DepartmentType.CAMERA, doc_type=DocumentType.CAMERA_CSV,
        raw_content=CAMERA_CSV, filename="CAM_A.csv",
    )

    with pytest.raises(EventHandlerError):
        bus.publish("production.raw.camera", envelope)

    assert dlq == [], "a spine failure was filed as a rejected document"


def test_a_genuinely_bad_document_still_goes_to_the_dlq():
    """
    The negative: making failures loud must not make refusals loud too. A
    document the parsers reject is a legitimate outcome, not a 500.
    """
    res = client.post("/api/upload", json={
        "raw_content": "this is not a camera report at all",
        "filename": "CAM_JUNK.csv",
        "production_id": "ACK_DLQ", "shoot_day": "31",
    })
    assert res.status_code == 200, res.text


# --------------------------------------------------------------------------- #
# Through the API
# --------------------------------------------------------------------------- #

def test_an_upload_whose_events_are_lost_does_not_report_ingested(monkeypatch):
    """
    The whole point. This request used to return 200 INGESTED.
    """
    from backend.app.api import routes

    monkeypatch.setattr(routes.spine_writer, "append_event", boom)

    res = client.post("/api/upload", json={
        "raw_content": CAMERA_CSV, "filename": "CAM_ACK_1.csv",
        "production_id": "ACK_API", "shoot_day": "31",
    })

    assert res.status_code == 500, res.text
    assert "INGESTED" not in res.text


def test_the_failure_says_what_to_do_about_it(monkeypatch):
    """
    The raw document is kept -- it is the evidence, and discarding it would
    mean asking whoever sent it to send it again. So the message has to name
    it, or the operator is left with a 500 and nothing to act on.
    """
    from backend.app.api import routes

    monkeypatch.setattr(routes.spine_writer, "append_event", boom)

    res = client.post("/api/upload", json={
        "raw_content": CAMERA_CSV, "filename": "CAM_ACK_2.csv",
        "production_id": "ACK_API", "shoot_day": "31",
    })

    detail = res.json()["detail"]
    assert "CAM_ACK_2.csv" in detail
    assert "doc_id" in detail
    assert "disk is full" in detail


def test_the_document_is_still_there_to_retry(monkeypatch):
    """
    Kept, not rolled back. The upload can be repeated once the cause is fixed.
    """
    from backend.app.api import routes

    monkeypatch.setattr(routes.spine_writer, "append_event", boom)
    res = client.post("/api/upload", json={
        "raw_content": CAMERA_CSV, "filename": "CAM_ACK_3.csv",
        "production_id": "ACK_KEEP", "shoot_day": "31",
    })
    assert res.status_code == 500

    # Deliberately no monkeypatch.undo(): the autouse fixtures in conftest take
    # the same function-scoped monkeypatch, so undoing here would also revert
    # CINESPINE_DB_PATH and read a different database than the one written to.
    # Listing documents does not go through append_event anyway.
    docs = client.get("/api/documents", params={
        "production_id": "ACK_KEEP", "shoot_day": "31",
    }).json()
    assert any(d["filename"] == "CAM_ACK_3.csv" for d in docs)


def test_a_healthy_upload_is_unaffected():
    res = client.post("/api/upload", json={
        "raw_content": CAMERA_CSV, "filename": "CAM_ACK_OK.csv",
        "production_id": "ACK_OK", "shoot_day": "31",
    })
    assert res.status_code == 200
    assert res.json()["status"] == "INGESTED"

    events = client.get("/api/takes", params={
        "production_id": "ACK_OK", "shoot_day": "31",
    }).json()
    assert events, "a successful upload produced no takes"

def test_the_file_drop_route_answers_for_a_failed_ingest_too(monkeypatch):
    """
    Four call sites publish to the bus and every one of them had to be given
    an answer. This route's was wrong when written -- it named a variable that
    does not exist in its scope, so the failure path raised NameError and hid
    the error it was meant to report. Untested refusals do not work.
    """
    from backend.app.api import routes

    monkeypatch.setattr(routes.spine_writer, "append_event", boom)

    res = client.post(
        "/api/upload/file",
        files={"file": ("CAM_DROP.csv", CAMERA_CSV.encode("utf-8"), "text/csv")},
        data={"production_id": "ACK_DROP", "shoot_day": "31"},
    )

    assert res.status_code == 500, res.text
    detail = res.json()["detail"]
    assert "CAM_DROP.csv" in detail
    assert "disk is full" in detail


def test_a_seed_counts_only_the_files_that_landed(monkeypatch, tmp_path):
    """
    In bulk, the old behaviour was worse: a seed reported every file as
    ingested while each one produced nothing. Failures are counted separately
    from skips -- skipped means "already here", failed means "chase this".
    """
    from backend.app.api import routes

    (tmp_path / "CAM_A.csv").write_text(CAMERA_CSV, encoding="utf-8")
    (tmp_path / "CAM_B.csv").write_text(
        CAMERA_CSV.replace("27/7,1", "27/8,1"), encoding="utf-8"
    )
    monkeypatch.setenv("CINESPINE_EXAMPLES_DIR", str(tmp_path))
    monkeypatch.setattr(routes.spine_writer, "append_event", boom)

    res = client.post("/api/seed", json={"production_id": "ACK_SEED", "shoot_day": "31"})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ingested_count"] == 0, "files that produced no events were counted as ingested"
    assert sorted(body["failed_files"]) == ["CAM_A.csv", "CAM_B.csv"]


def test_one_bad_file_does_not_abandon_the_rest_of_a_seed(monkeypatch, tmp_path):
    """
    The other half: a seed that stopped at the first failure would leave the
    day half-loaded with no indication of where it stopped.
    """
    from backend.app.api import routes

    (tmp_path / "CAM_A.csv").write_text(CAMERA_CSV, encoding="utf-8")
    (tmp_path / "CAM_B.csv").write_text(
        CAMERA_CSV.replace("27/7,1", "27/8,1"), encoding="utf-8"
    )

    real = routes.spine_writer.append_event

    def fail_only_the_first(event):
        if (event.get("payload") or {}).get("slate") == "27/7":
            raise OSError("database or disk is full")
        return real(event)

    monkeypatch.setenv("CINESPINE_EXAMPLES_DIR", str(tmp_path))
    monkeypatch.setattr(routes.spine_writer, "append_event", fail_only_the_first)

    body = client.post(
        "/api/seed", json={"production_id": "ACK_SEED_2", "shoot_day": "31"}
    ).json()

    assert body["failed_files"] == ["CAM_A.csv"]
    assert body["files"] == ["CAM_B.csv"]
