"""
Unit & Integration Tests for Google Cloud & Gemini Enterprise Agent Platform.
Verifies runtime import, SDK readiness, GCS media archival, and telemetry endpoints.
"""
import pytest
from starlette.testclient import TestClient
from backend.app.main import app
from backend.app.integrations.google_cloud import (
    get_google_cloud_runtime_status,
    upload_media_to_google_cloud_storage,
    run_gemini_screenplay_analysis,
    GENAI_AVAILABLE,
    GCS_AVAILABLE
)


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
    assert status["gemini_model"] == "gemini-2.0-flash"
    assert status["imagen_model"] == "imagen-3.0-generate-002"
    assert "google.genai SDK (Gemini 2.0 & Imagen 3)" in status["active_features"]


def test_google_cloud_status_endpoint(client):
    """Verifies GET /api/integrations/google-cloud endpoint."""
    res = client.get("/api/integrations/google-cloud")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert data["genai_sdk_installed"] is True
    assert data["gcs_sdk_installed"] is True
    assert data["gemini_model"] == "gemini-2.0-flash"


def test_gcs_media_upload_pipeline():
    """Verifies Google Cloud Storage media upload handler."""
    sample_bytes = b"%PDF-1.4 sample screenplay content for GCS"
    res = upload_media_to_google_cloud_storage(
        file_bytes=sample_bytes,
        destination_blob_name="test/sample_script.pdf",
        content_type="application/pdf"
    )
    assert res["success"] is True
    assert "gs://" in res["gcs_uri"]
    assert res["bytes_uploaded"] == len(sample_bytes)


@pytest.mark.anyio
async def test_gemini_screenplay_analysis_runtime():
    """Verifies Gemini screenplay analysis pipeline."""
    res = await run_gemini_screenplay_analysis(
        scene_text="INT. GREAT HALL - NAVE - DAY\nThomas plays the organ with intense focus.",
        dop_style="Roger Deakins"
    )
    assert res["success"] is True
    assert res["model"] is not None
    assert "analysis" in res
