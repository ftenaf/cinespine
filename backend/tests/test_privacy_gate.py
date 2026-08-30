"""
What may be served, and what must not.

A parsed fact is a slate, a roll, a timecode. A source document is the page
those were read off, and it carries what the parsers were written to leave
behind: a script supervisor's phone number and email in the footer, cast
names, unreleased material. failure-modes.md names it -- "raw material treated
as a derived fact" -- and the refusal below is run rather than read, because
the other named mistake is "the untested refusal".
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.core import privacy
from backend.app.main import app

client = TestClient(app)

PROD = "PRIVACY"

# A page shaped like the real thing: production data that must survive intact,
# and contact details that must not.
PAPERWORK = (
    "LAC DAILY PRODUCTION REPORT - DAY 31\n"
    "Camera Cards: A120 - A123    Sound Cards: 280726\n"
    "Slates: 27/7 - 8, 49/1 - 9, 117/1 - 5\n"
    "WRAP: 18:55    Set-Ups: 35    TC 09:26:12:04\n"
    "Script Supervisor  Tel: 600 123 456  supervisor@example.com\n"
)


@pytest.fixture(autouse=True)
def _gate_closed(monkeypatch):
    """The default everywhere: source documents are not served."""
    monkeypatch.delenv(privacy.SERVE_FLAG, raising=False)
    yield


def stored(**over) -> str:
    """Stores a document the way an upload does, and returns its id."""
    from backend.app.api.routes import spine_writer

    return spine_writer.store_document(
        production_id=PROD, shoot_day="31", filename="LAC_ParteProd_D031.pdf",
        doc_type="dpr", department="office", content=PAPERWORK,
        checksum=None, raw_bytes=b"%PDF-1.7 the original page",
        metadata=over.get("metadata", {}),
    )


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #

def test_the_text_of_a_document_is_refused_by_default():
    res = client.get(f"/api/documents/{stored()}")
    assert res.status_code == 403


def test_the_original_bytes_are_refused_by_default():
    """
    A PDF cannot be redacted without re-rendering it, so the gate is the only
    control over this one.
    """
    res = client.get(f"/api/documents/{stored()}/raw")
    assert res.status_code == 403


def test_the_refusal_says_why_and_what_to_do():
    detail = client.get(f"/api/documents/{stored()}").json()["detail"]
    assert "crew contact details" in detail
    assert privacy.SERVE_FLAG in detail


def test_turning_the_gate_on_serves_the_document(monkeypatch):
    monkeypatch.setenv(privacy.SERVE_FLAG, "1")
    res = client.get(f"/api/documents/{stored()}")
    assert res.status_code == 200
    assert "Camera Cards: A120 - A123" in res.json()["content"]


def test_an_embedded_fixture_is_served_without_the_gate():
    """
    The demo runs against synthetic fixtures, so the default costs nothing
    there and refuses everywhere the paperwork is real.
    """
    doc_id = stored(metadata={"synthetic": True})
    assert client.get(f"/api/documents/{doc_id}").status_code == 200
    assert client.get(f"/api/documents/{doc_id}/raw").status_code == 200


def test_seeding_from_an_examples_directory_is_not_treated_as_synthetic():
    """
    The seed endpoint reads real production paperwork when a local examples
    directory exists, so "it came from the seed" answers the wrong question.
    """
    assert privacy.is_synthetic({"metadata": {"file_size": 12}}) is False


def test_a_document_that_does_not_exist_is_still_a_404():
    assert client.get("/api/documents/nope").status_code == 404


def test_the_parsed_facts_are_not_gated():
    """
    Takes, slates, rolls and timecodes are derived, carry no contact details,
    and are the product. Gating those would gate the app.
    """
    assert client.get(
        "/api/takes", params={"production_id": PROD, "shoot_day": "31"}
    ).status_code == 200
    assert client.get(
        "/api/documents", params={"production_id": PROD, "shoot_day": "31"}
    ).status_code == 200


def test_the_listing_never_carried_the_material_anyway():
    stored()
    listed = client.get("/api/documents", params={"production_id": PROD}).json()
    assert listed
    assert all("content" not in d and "raw_bytes" not in d for d in listed)


# --------------------------------------------------------------------------- #
# Redaction: narrow on purpose
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("line", [
    "A120 280726 2:46",
    "Sound Cards: 280726",
    "Camera Cards: A120 - A123",
    "Slates: 27/7 - 8, 49/1 - 9, 117/1 - 5",
    "09:26:12:04",
    "checksum 9f2a41b7c3",
    "WRAP: 18:55  Set-Ups: 35",
    "Scenes Scheduled: 27pt, 49pt, 117pt, 6WT",
])
def test_production_data_is_left_exactly_as_written(line):
    """
    The scrubber this replaced turned 'A120 280726' into 'A[REDACTED_PHONE]'.
    A camera card and its shoot date read as a phone number, which is the
    "helpful correction" failure mode: the repair is invisible and the original
    is destroyed.
    """
    assert privacy.redact(line) == line


def test_an_email_is_removed():
    assert "supervisor@example.com" not in privacy.redact(PAPERWORK)


@pytest.mark.parametrize("line", [
    "Tel: 600 123 456",
    "Móvil: 600 123 456",
    "phone 600 123 456",
    "call +34 600 123 456",
])
def test_a_number_the_document_calls_a_phone_is_removed(line):
    assert "600" not in privacy.redact(line)


def test_redaction_does_not_run_on_a_bare_run_of_digits():
    """Only labelled, or an explicit country code. Never a digit run alone."""
    assert privacy.redact("600123456 is a sound roll here") == "600123456 is a sound roll here"


def test_the_served_text_is_redacted_even_once_the_gate_is_open(monkeypatch):
    monkeypatch.setenv(privacy.SERVE_FLAG, "1")
    content = client.get(f"/api/documents/{stored()}").json()["content"]
    assert "supervisor@example.com" not in content
    assert "Camera Cards: A120 - A123" in content


def test_empty_text_survives_redaction():
    assert privacy.redact("") == ""


# --------------------------------------------------------------------------- #
# The bypass that used to exist
# --------------------------------------------------------------------------- #

def test_the_examples_directory_is_no_longer_read_by_filename(monkeypatch, tmp_path):
    """
    get_document_raw used to fall back to CINESPINE_EXAMPLES_DIR/<filename>
    when the stored bytes were absent. That reached the real paperwork by name
    and would have walked straight around the gate.
    """
    from backend.app.api.routes import spine_writer

    planted = tmp_path / "planted.pdf"
    planted.write_bytes(b"%PDF-1.7 THE REAL PAPERWORK")
    monkeypatch.setenv("CINESPINE_EXAMPLES_DIR", str(tmp_path))
    monkeypatch.setenv(privacy.SERVE_FLAG, "1")

    doc_id = spine_writer.store_document(
        production_id=PROD, shoot_day="31", filename="planted.pdf",
        doc_type="dpr", department="office", content="parsed text only",
        checksum=None, raw_bytes=None, metadata={},
    )

    res = client.get(f"/api/documents/{doc_id}/raw")
    assert res.status_code == 200
    assert b"THE REAL PAPERWORK" not in res.content
