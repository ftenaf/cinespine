"""
Covers the upload route's lined-page path.

The failure mode this guards is not a crash: extraction runs inside an upload
that must succeed regardless, so a page that was never read looks exactly like a
page with nothing on it unless the route says which happened.
"""
import io

import pytest
from fastapi.testclient import TestClient

from backend.app.agents import multimodal
from backend.app.main import app

client = TestClient(app)

PAGE_JSON = (
    '{"scene": "64A", "slates": ["21/1"], "page_number": 42, "takes": ['
    '{"take_id": "3*", "camera_rolls": ["A120", "B039"]},'
    '{"take_id": "2PK", "camera_rolls": ["A120"]}]}'
)


def _upload(name: str, content: bytes, content_type: str = "application/pdf"):
    return client.post(
        "/api/upload/file",
        files={"file": (name, io.BytesIO(content), content_type)},
        data={"production_id": "TEST_PROD", "shoot_day": "31"},
    )


@pytest.fixture
def unique():
    """Uploads are checksum-deduplicated, so each test needs its own bytes."""
    import uuid
    return lambda: f"%PDF-1.4 lined page {uuid.uuid4()}".encode()


def _stub_model(monkeypatch, behaviour):
    class _Models:
        def generate_content(self, model, contents, config):
            outcome = behaviour(model)
            if isinstance(outcome, Exception):
                raise outcome
            return type("R", (), {"text": outcome})()

    class _Client:
        def __init__(self, **kwargs):
            self.models = _Models()

    import google.genai as genai
    monkeypatch.setattr(genai, "Client", _Client)


# --------------------------------------------------------------------------- #
# The default: no key, no call
# --------------------------------------------------------------------------- #

def test_a_lined_page_upload_makes_no_model_call_by_default(unique, monkeypatch):
    """
    Adding a key to .env must not turn every upload into a billed request. This
    is the mistake the character inference path already made once.
    """
    def explode(**kwargs):
        raise AssertionError("a live client was constructed during a test")

    import google.genai as genai
    monkeypatch.setattr(genai, "Client", explode)

    res = _upload("FACING_AND_LINED_day31.pdf", unique())
    assert res.status_code == 200
    body = res.json()
    assert body["is_multimodal"] is True
    assert body["lined_page"] is None
    assert body["lining_warnings"], "an unread page must say it was unread"


def test_an_ordinary_document_is_untouched(unique):
    """Only pages the classifier calls multimodal go near a model."""
    res = client.post(
        "/api/upload/file",
        files={"file": ("ZoeLog_camera_day31.csv", io.BytesIO(b"SLATE,TAKE\n101,1\n"), "text/csv")},
        data={"production_id": "TEST_PROD", "shoot_day": "31"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["is_multimodal"] is False
    assert body["lined_page"] is None
    assert body["lining_warnings"] == []


# --------------------------------------------------------------------------- #
# With extraction enabled
# --------------------------------------------------------------------------- #

def test_a_read_page_reaches_the_response_and_the_document(unique, monkeypatch):
    # This asserts the extraction travels with the stored document, which
    # means reading the document back. Serving the material is gated by
    # default; the gate has its own tests in test_privacy_gate.py.
    monkeypatch.setenv("CINESPINE_SERVE_SOURCE_DOCUMENTS", "1")
    monkeypatch.delenv("CINESPINE_DISABLE_LINING_EXTRACTION", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _stub_model(monkeypatch, lambda m: PAGE_JSON)

    res = _upload("FACING_AND_LINED_day31.pdf", unique())
    assert res.status_code == 200
    body = res.json()

    page = body["lined_page"]
    assert page is not None
    assert page["scene"] == "64A"
    assert body["lining_warnings"] == []

    starred = [t for t in page["takes"] if t["is_starred"]]
    assert [t["take_id"] for t in starred] == ["3"]
    assert starred[0]["camera_rolls"] == ["A120", "B039"]

    # and it is stored with the document, not only returned once
    stored = client.get(f"/api/documents/{body['doc_id']}")
    assert stored.status_code == 200
    assert stored.json()["metadata"]["lined_page"]["scene"] == "64A"


def test_a_failed_read_still_ingests_and_says_so(unique, monkeypatch):
    """
    Ingestion is what the user asked for; it must survive an unavailable model.
    But an empty result has to be distinguishable from an empty page.
    """
    monkeypatch.delenv("CINESPINE_DISABLE_LINING_EXTRACTION", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _stub_model(monkeypatch, lambda m: RuntimeError("503 UNAVAILABLE"))

    res = _upload("FACING_AND_LINED_day31.pdf", unique())
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "INGESTED"
    assert body["doc_id"]
    assert body["lined_page"] is None
    assert any("could not read" in w.lower() for w in body["lining_warnings"])


def test_a_page_with_no_takes_is_flagged_rather_than_reported_as_clean(unique, monkeypatch):
    monkeypatch.delenv("CINESPINE_DISABLE_LINING_EXTRACTION", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _stub_model(monkeypatch, lambda m: '{"scene": "", "takes": []}')

    body = _upload("FACING_AND_LINED_day31.pdf", unique()).json()
    assert body["lined_page"] is not None
    assert any("no takes" in w.lower() for w in body["lining_warnings"])


def test_a_lined_page_that_is_not_an_image_is_reported(unique, monkeypatch):
    monkeypatch.delenv("CINESPINE_DISABLE_LINING_EXTRACTION", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    res = client.post(
        "/api/upload/file",
        files={"file": ("LINED_pages_day31.csv", io.BytesIO(b"not,a,page\n1,2,3\n"), "text/csv")},
        data={"production_id": "TEST_PROD", "shoot_day": "31"},
    )
    body = res.json()
    assert body["is_multimodal"] is True
    assert body["lined_page"] is None
    assert any("not an image or pdf" in w.lower() for w in body["lining_warnings"])


def test_extraction_never_propagates_an_exception(monkeypatch):
    """The entry point the route depends on must not raise, whatever happens."""
    monkeypatch.delenv("CINESPINE_DISABLE_LINING_EXTRACTION", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    import asyncio

    def boom(**kwargs):
        raise RuntimeError("client construction exploded")

    import google.genai as genai
    monkeypatch.setattr(genai, "Client", boom)

    out = asyncio.run(multimodal.extract_lined_page_if_enabled(b"x", "LINED.pdf", "application/pdf"))
    assert out["page"] is None
    assert out["warnings"]


@pytest.mark.parametrize("filename, content_type, expected", [
    ("LINED.pdf", "application/pdf", "application/pdf"),
    ("scan.PNG", "application/octet-stream", "image/png"),
    ("scan.jpeg", None, "image/jpeg"),
    ("page.heic", "application/octet-stream", "image/heic"),
    ("notes.csv", "text/csv", None),
    ("noext", "image/webp", "image/webp"),
])
def test_mime_resolution_trusts_the_extension(filename, content_type, expected):
    """A dragged-in scan usually arrives as application/octet-stream."""
    assert multimodal.resolve_mime_type(filename, content_type) == expected
