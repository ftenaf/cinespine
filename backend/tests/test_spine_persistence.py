"""
The spine itself, kept.

This was the last thing that lived only in memory, which left the app in the
odd state of remembering that a shot was mounted while forgetting the shot: the
tag survived a restart and the take it hung on did not.

An event is a witness statement -- this camera report says take 3 of 27/7 is on
card A120 -- so the table only grows. A later report that disagrees is another
event, and the disagreement is the product.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.spine import event_store
from backend.app.spine.writer import SpineWriter

client = TestClient(app)

PROD = "SPINEPERSIST"


def event(**over):
    return {
        "event_id": "evt-1",
        "production_id": PROD,
        "shoot_day": "31",
        "axis": "belief",
        "department": "camera",
        "doc_type": "camera_csv",
        "entity_type": "take",
        "payload": {"slate": "27/7", "take_id": "1", "camera_roll": "A120"},
        "metadata": {"doc_id": "doc-1"},
        "timestamp": "2026-07-28T10:00:00Z",
        **over,
    }


def reopened() -> SpineWriter:
    """A fresh writer over the same database -- what a restart amounts to."""
    return SpineWriter(clickhouse_client=None)


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #

def test_an_event_outlives_the_process_that_recorded_it():
    writer = SpineWriter(clickhouse_client=None)
    writer.append_event(event())
    assert len(reopened().get_events(production_id=PROD)) == 1


def test_an_event_comes_back_whole():
    writer = SpineWriter(clickhouse_client=None)
    writer.append_event(event())
    restored = reopened().get_events(production_id=PROD)[0]
    assert restored["payload"]["camera_roll"] == "A120"
    assert restored["metadata"]["doc_id"] == "doc-1"
    assert restored["department"] == "camera"


def test_events_come_back_in_the_order_they_arrived():
    """
    Several reads take the last event as the most recent word. A spine reloaded
    out of order would answer differently after a restart than before one.
    """
    writer = SpineWriter(clickhouse_client=None)
    for i in range(5):
        writer.append_event(event(payload={"slate": "27/7", "take_id": str(i)}))
    assert [
        e["payload"]["take_id"] for e in reopened().get_events(production_id=PROD)
    ] == ["0", "1", "2", "3", "4"]


def test_a_document_s_rows_share_an_event_id_and_are_still_separate_events():
    """
    The dispatcher stamps every row of a document with the envelope's id, so
    event_id is not unique and cannot be the key.
    """
    writer = SpineWriter(clickhouse_client=None)
    writer.append_event(event(event_id="same", payload={"take_id": "1"}))
    writer.append_event(event(event_id="same", payload={"take_id": "2"}))
    assert len(reopened().get_events(production_id=PROD)) == 2


def test_the_spine_of_another_production_is_not_mixed_in():
    writer = SpineWriter(clickhouse_client=None)
    writer.append_event(event())
    writer.append_event(event(production_id="SOMEWHERE_ELSE"))
    assert len(reopened().get_events(production_id=PROD)) == 1


def test_a_day_can_be_asked_for_on_its_own():
    writer = SpineWriter(clickhouse_client=None)
    writer.append_event(event(shoot_day="31"))
    writer.append_event(event(shoot_day="39"))
    assert len(reopened().get_events(production_id=PROD, shoot_day="39")) == 1


def test_an_empty_spine_reopens_empty_rather_than_failing():
    assert reopened().get_events(production_id=PROD) == []


# --------------------------------------------------------------------------- #
# The paperwork
# --------------------------------------------------------------------------- #

def test_an_uploaded_document_outlives_the_process():
    writer = SpineWriter(clickhouse_client=None)
    doc_id = writer.store_document(
        production_id=PROD, shoot_day="31", filename="CAM_A.csv",
        doc_type="camera_csv", department="camera", content="scene,take\n27/7,1\n",
        checksum="abc123",
    )
    restored = reopened().get_document(doc_id)
    assert restored["filename"] == "CAM_A.csv"
    assert "27/7" in restored["content"]


def test_the_original_bytes_are_kept_so_a_page_can_be_shown_not_transcribed():
    writer = SpineWriter(clickhouse_client=None)
    doc_id = writer.store_document(
        production_id=PROD, shoot_day="31", filename="facing.pdf",
        doc_type="script_lined", department="script", content="text",
        raw_bytes=b"%PDF-1.7 fake bytes",
    )
    assert reopened().get_document(doc_id)["raw_bytes"] == b"%PDF-1.7 fake bytes"


def test_the_same_file_uploaded_twice_is_still_recognised_after_a_restart():
    writer = SpineWriter(clickhouse_client=None)
    writer.store_document(
        production_id=PROD, shoot_day="31", filename="CAM_A.csv",
        doc_type="camera_csv", department="camera", content="x", checksum="dup",
    )
    assert reopened().get_document_by_checksum(PROD, "31", "dup") is not None


def test_a_listing_does_not_carry_the_bytes():
    """
    Loading every uploaded PDF to render a list of filenames is what holding
    them in memory used to cost.
    """
    writer = SpineWriter(clickhouse_client=None)
    writer.store_document(
        production_id=PROD, shoot_day="31", filename="facing.pdf",
        doc_type="script_lined", department="script", content="text",
        raw_bytes=b"%PDF-1.7 fake bytes",
    )
    listed = reopened().list_documents(production_id=PROD)
    assert listed[0]["filename"] == "facing.pdf"
    assert "raw_bytes" not in listed[0]


def test_deleting_a_document_takes_its_readings_with_it_for_good():
    writer = SpineWriter(clickhouse_client=None)
    doc_id = writer.store_document(
        production_id=PROD, shoot_day="31", filename="CAM_A.csv",
        doc_type="camera_csv", department="camera", content="x",
    )
    writer.append_event(event(metadata={"doc_id": doc_id}))
    writer.append_event(event(metadata={"doc_id": "another"}))

    assert writer.delete_document(doc_id) is True

    after = reopened()
    assert after.get_document(doc_id) is None
    assert len(after.get_events(production_id=PROD)) == 1


def test_deleting_a_document_that_is_not_there_is_not_a_deletion():
    assert SpineWriter(clickhouse_client=None).delete_document("nope") is False


# --------------------------------------------------------------------------- #
# Calls a person made
# --------------------------------------------------------------------------- #

def test_a_resolution_outlives_the_process():
    """
    Somebody decided which card was right. That is hand-authored work, and
    losing it loses the decision rather than something re-derivable.
    """
    writer = SpineWriter(clickhouse_client=None)
    writer.store_discrepancy_resolution(
        production_id=PROD, shoot_day="31", discrepancy_id="disc-1",
        entity_id="27/7", resolved_card="A120", resolution_note="Card A120 is right.",
        resolved_by="@director",
    )
    restored = reopened().get_discrepancy_resolutions(PROD, "31")
    assert restored["disc-1"]["resolved_card"] == "A120"


def test_a_resolution_is_still_findable_by_the_take_it_settled():
    writer = SpineWriter(clickhouse_client=None)
    writer.store_discrepancy_resolution(
        production_id=PROD, shoot_day="31", discrepancy_id="disc-1",
        entity_id="27/7", resolved_card="A120",
    )
    assert f"{PROD}_31_27/7" in reopened().get_discrepancy_resolutions(PROD, "31")


def test_re_opening_a_discrepancy_forgets_the_resolution_for_good():
    writer = SpineWriter(clickhouse_client=None)
    writer.store_discrepancy_resolution(
        production_id=PROD, shoot_day="31", discrepancy_id="disc-1",
        entity_id="27/7", resolved_card="A120",
    )
    assert writer.delete_discrepancy_resolution("disc-1") is True
    assert reopened().get_discrepancy_resolutions(PROD, "31") == {}


def test_a_registered_user_outlives_the_process():
    writer = SpineWriter(clickhouse_client=None)
    writer.register_user(
        handle="ana", name="Ana", email="ana@example.com",
        role="Assistant Editor", avatar_color="#fff",
    )
    assert reopened().get_user("@ana")["name"] == "Ana"


def test_the_built_in_team_is_there_without_being_registered():
    assert reopened().get_user("@director") is not None


# --------------------------------------------------------------------------- #
# What it costs
# --------------------------------------------------------------------------- #

def test_a_volume_sized_ingestion_stays_quick():
    """
    A single Silverstack volume is about 2000 events. A fresh connection per
    event took 9.4s and a held connection on the default journal 7.2s, both
    paying an fsync each time; in WAL with synchronous=NORMAL it is a fraction
    of a second. This is the guard on that not quietly regressing.
    """
    import time

    writer = SpineWriter(clickhouse_client=None)
    started = time.perf_counter()
    for i in range(2000):
        writer.append_event(event(payload={"slate": "27/7", "take_id": str(i)}))
    elapsed = time.perf_counter() - started

    assert event_store.count_events() == 2000
    assert elapsed < 3.0, f"2000 appends took {elapsed:.2f}s"


# --------------------------------------------------------------------------- #
# End to end
# --------------------------------------------------------------------------- #

def test_a_seeded_production_still_has_its_takes_after_a_restart():
    """The whole point: the tag survived and the take it hung on did not."""
    assert client.post("/api/seed", json={}).status_code == 200
    before = client.get(
        "/api/takes", params={"production_id": "DEMO_PRODUCTION", "shoot_day": "31"}
    ).json()
    assert before, "seeding produced no takes"

    after = reopened().get_events(production_id="DEMO_PRODUCTION", shoot_day="31")
    assert after, "the seeded spine did not survive being reopened"
