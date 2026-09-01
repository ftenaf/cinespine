"""
Unit & Integration Tests for Google Cloud & Gemini Enterprise Agent Platform.
Verifies runtime import, SDK readiness, GCS media archival, and telemetry endpoints.
"""
import pytest
from types import SimpleNamespace
from starlette.testclient import TestClient
from backend.app.main import app
from backend.app.integrations import google_cloud
from backend.app.script.ai_image_service import image_models
from backend.app.script.llm_router import get_optimal_gemini_model
from backend.app.integrations.google_cloud import (
    get_google_cloud_runtime_status,
    upload_media_to_google_cloud_storage,
    run_gemini_screenplay_analysis,
    GENAI_AVAILABLE,
    GCS_AVAILABLE
)

SAMPLE_PDF_BYTES = b"%PDF-1.4 sample screenplay content for GCS"
SAMPLE_SCENE = "INT. GREAT HALL - NAVE - DAY\nLEAD plays the organ with intense focus."


@pytest.fixture
def client():
    return TestClient(app)


def test_google_cloud_runtime_sdks_installed():
    """Verifies that Google GenAI and Google Cloud Storage SDKs are imported at runtime."""
    assert GENAI_AVAILABLE is True, "google-genai SDK must be installed and importable at runtime"
    assert GCS_AVAILABLE is True, "google-cloud-storage SDK must be installed and importable at runtime"


def test_google_cloud_status_function():
    """Verifies runtime status function returns structured telemetry."""
    status = get_google_cloud_runtime_status()
    assert status["status"] == "online"
    assert status["genai_sdk_installed"] is True
    assert status["gcs_sdk_installed"] is True
    # The status endpoint must name the model the code would actually call.
    assert status["gemini_model"] == get_optimal_gemini_model("", "simple")
    # Whatever ai_image_service would actually call, never a name pinned here:
    # this field claimed Imagen 3 for the whole of the run in which no Imagen
    # model was reachable on the key at all.
    assert status["image_model"] == image_models()[0]
    assert "google.genai SDK (Gemini text and image models)" in status["active_features"]


def test_google_cloud_status_endpoint(client):
    """Verifies GET /api/integrations/google-cloud endpoint."""
    res = client.get("/api/integrations/google-cloud")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert data["genai_sdk_installed"] is True
    assert data["gcs_sdk_installed"] is True
    assert data["gemini_model"] == get_optimal_gemini_model("", "simple")


def test_gcs_upload_uses_sdk_when_available(monkeypatch):
    """
    The SDK branch must actually drive the storage client.

    `success` is True on both the SDK and the fallback path, so it cannot
    distinguish them. `storage_class` can: the SDK branch reports "STANDARD".
    """
    captured = {}

    class FakeBlob:
        def upload_from_string(self, data, content_type=None):
            captured["data"] = data
            captured["content_type"] = content_type

    class FakeBucket:
        def blob(self, name):
            captured["blob"] = name
            return FakeBlob()

    class FakeClient:
        def __init__(self, project=None):
            captured["project"] = project

        def bucket(self, name):
            captured["bucket"] = name
            return FakeBucket()

    monkeypatch.setattr(google_cloud, "GCS_AVAILABLE", True)
    monkeypatch.setattr(google_cloud, "gcs_storage", SimpleNamespace(Client=FakeClient))

    res = upload_media_to_google_cloud_storage(
        file_bytes=SAMPLE_PDF_BYTES,
        destination_blob_name="test/sample_script.pdf",
        content_type="application/pdf"
    )

    assert res["success"] is True
    assert res["storage_class"] == "STANDARD"
    assert res["public_url"].startswith("https://storage.googleapis.com/")
    assert res["bytes_uploaded"] == len(SAMPLE_PDF_BYTES)

    # The bytes must have reached the client, not just been counted.
    assert captured["data"] == SAMPLE_PDF_BYTES
    assert captured["content_type"] == "application/pdf"
    assert captured["blob"] == "test/sample_script.pdf"


def test_gcs_upload_falls_back_when_sdk_unavailable(monkeypatch):
    """Without the SDK the handler still returns an auditable GCS reference."""
    monkeypatch.setattr(google_cloud, "GCS_AVAILABLE", False)

    res = upload_media_to_google_cloud_storage(
        file_bytes=SAMPLE_PDF_BYTES,
        destination_blob_name="test/sample_script.pdf",
        content_type="application/pdf"
    )

    assert res["success"] is True
    assert res["storage_class"] == "STANDARD (GCS Managed Pipeline)"
    assert res["public_url"] == "/storage/test/sample_script.pdf"
    assert res["gcs_uri"].startswith("gs://")
    assert res["bytes_uploaded"] == len(SAMPLE_PDF_BYTES)


def test_gcs_upload_falls_back_when_client_raises(monkeypatch):
    """
    The CI-equivalent path: SDK installed, no credentials. Client construction
    raises and the handler must degrade rather than propagate.
    """
    class ExplodingClient:
        def __init__(self, project=None):
            raise RuntimeError("could not determine default credentials")

    monkeypatch.setattr(google_cloud, "GCS_AVAILABLE", True)
    monkeypatch.setattr(google_cloud, "gcs_storage", SimpleNamespace(Client=ExplodingClient))

    res = upload_media_to_google_cloud_storage(
        file_bytes=SAMPLE_PDF_BYTES,
        destination_blob_name="test/sample_script.pdf",
        content_type="application/pdf"
    )

    assert res["success"] is True
    assert res["storage_class"] == "STANDARD (GCS Managed Pipeline)"


@pytest.mark.anyio
async def test_gemini_analysis_uses_sdk_when_configured(monkeypatch):
    """
    With SDK and API key present, the real Gemini branch must run. `provider`
    and `model` distinguish it from the emulated fallback.
    """
    captured = {}

    class FakeModels:
        def generate_content(self, model=None, contents=None):
            captured["model"] = model
            captured["contents"] = contents
            return SimpleNamespace(text="FAKE GEMINI ANALYSIS")

    class FakeClient:
        def __init__(self, api_key=None):
            captured["api_key"] = api_key
            self.models = FakeModels()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
    monkeypatch.setattr(google_cloud, "GENAI_AVAILABLE", True)
    monkeypatch.setattr(google_cloud, "genai", SimpleNamespace(Client=FakeClient))

    res = await run_gemini_screenplay_analysis(
        scene_text=SAMPLE_SCENE,
        dop_style="Roger Deakins"
    )

    assert res["success"] is True
    assert res["provider"] == "Google Cloud Gemini Enterprise"
    # Asserted against the router rather than a literal: hardcoding the model id
    # here is what let a non-existent one ship green in the first place.
    expected_model = get_optimal_gemini_model(SAMPLE_SCENE, task_complexity="simple")
    assert res["model"] == expected_model
    assert res["analysis"] == "FAKE GEMINI ANALYSIS"

    assert captured["api_key"] == "test-key-123"
    assert captured["model"] == expected_model
    assert "Roger Deakins" in captured["contents"]
    assert "LEAD plays the organ" in captured["contents"]


@pytest.mark.anyio
async def test_gemini_analysis_falls_back_without_api_key(monkeypatch):
    """Without a key the emulated breakdown runs, and says so."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    res = await run_gemini_screenplay_analysis(
        scene_text=SAMPLE_SCENE,
        dop_style="Roger Deakins"
    )

    assert res["success"] is True
    assert res["provider"] == "Google Cloud Agent Builder Pipeline"
    # With no key nothing was called, so the reported model must not name a real
    # one: a heuristic answer labelled "gemini-..." reads as a genuine inference.
    assert "gemini" not in res["model"].lower()
    assert "no model called" in res["model"]
    assert "Roger Deakins" in res["analysis"]
