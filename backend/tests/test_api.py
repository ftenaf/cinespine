"""
TDD Test Suite for Slice 6: FastAPI REST API & Anonymization Gates.

Evidence:
- references/constraints/safety.md ('Never expose PII on public endpoints')
"""
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.tests.test_parsers import SAMPLE_CAMERA_CSV, SAMPLE_SOUND_ALE


@pytest.fixture
def client():
    return TestClient(app)


def test_api_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_api_upload_document(client):
    payload = {
        "production_id": "PROD_01",
        "shoot_day": "SD31",
        "axis": "belief",
        "department": "camera",
        "doc_type": "camera_csv",
        "raw_content": SAMPLE_CAMERA_CSV,
        "filename": "camera_day31.csv",
    }
    response = client.post("/api/upload", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "INGESTED"
    assert data["shoot_day"] == "31"  # Normalized


def test_api_get_takes_and_discrepancies(client):
    # 1. Ingest camera CSV
    client.post("/api/upload", json={
        "production_id": "PROD_01",
        "shoot_day": "31",
        "axis": "belief",
        "department": "camera",
        "doc_type": "camera_csv",
        "raw_content": SAMPLE_CAMERA_CSV,
        "filename": "camera_day31.csv",
    })
    # 2. Ingest sound ALE
    client.post("/api/upload", json={
        "production_id": "PROD_01",
        "shoot_day": "31",
        "axis": "belief",
        "department": "sound",
        "doc_type": "sound_ale",
        "raw_content": SAMPLE_SOUND_ALE,
        "filename": "sound_day31.ale",
    })

    # Fetch takes
    response_takes = client.get("/api/takes?production_id=PROD_01&shoot_day=31")
    assert response_takes.status_code == 200
    takes = response_takes.json()
    assert len(takes) >= 3

    # Fetch discrepancies
    response_disc = client.get("/api/discrepancies?production_id=PROD_01&shoot_day=31")
    assert response_disc.status_code == 200


def test_api_upload_multipart_file(client):
    file_bytes = b"Slate,Take,CameraRoll,ClipName,FPS,ISO\n27/7,1,B039,B039_C001,24.0,800\n"
    files = {"file": ("DemoProduction-2026-7-28_CAM_B.csv", file_bytes, "text/csv")}
    data = {"production_id": "PROD_01", "shoot_day": "31"}
    
    response = client.post("/api/upload/file", files=files, data=data)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "INGESTED"
    assert res_data["detected_department"] == "camera"
    assert "checksum" in res_data

    # Attempting to upload the exact same file again must return 409 Conflict
    dup_response = client.post("/api/upload/file", files=files, data=data)
    assert dup_response.status_code == 409
    assert "Duplicate document" in dup_response.json()["detail"]

    # Delete the uploaded document
    doc_id = res_data["doc_id"]
    del_response = client.delete(f"/api/documents/{doc_id}")
    assert del_response.status_code == 200
    assert del_response.json()["status"] == "DELETED"


def test_api_metrics_endpoint(client):
    response = client.get("/api/metrics")
    assert response.status_code == 200
    assert b"cinespine_ingested_events_total" in response.content

