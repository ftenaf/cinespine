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
    assert b"cinespine_llm_tokens_consumed_total" in response.content
    assert b"cinespine_sse_active_connections" in response.content


def test_api_document_raw_pdf_streaming(client, monkeypatch):
    # Serving the material is gated by default; this test is about the
    # streaming itself, so it opens the gate deliberately. The gate has its
    # own tests in test_privacy_gate.py.
    monkeypatch.setenv("CINESPINE_SERVE_SOURCE_DOCUMENTS", "1")

    # Upload a dummy PDF file
    dummy_pdf_bytes = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
    files = {"file": ("DemoProduction_CAM_A.pdf", dummy_pdf_bytes, "application/pdf")}
    data = {"production_id": "PROD_PDF_TEST", "shoot_day": "31"}

    upload_res = client.post("/api/upload/file", files=files, data=data)
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["doc_id"]

    # 1. Fetch document metadata
    doc_meta_res = client.get(f"/api/documents/{doc_id}")
    assert doc_meta_res.status_code == 200
    doc_meta = doc_meta_res.json()
    assert doc_meta["is_pdf"] is True
    assert doc_meta["raw_url"] == f"/api/documents/{doc_id}/raw"

    # 2. Fetch raw document stream for visual PDF preview
    raw_res = client.get(f"/api/documents/{doc_id}/raw")
    assert raw_res.status_code == 200
    assert raw_res.headers["content-type"] == "application/pdf"
    assert "inline" in raw_res.headers["content-disposition"]
    assert raw_res.content == dummy_pdf_bytes


def test_api_seed_endpoint(client):
    res = client.post("/api/seed", json={"production_id": "DEMO_PRODUCTION_TEST", "shoot_day": "31"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SEEDED"
    assert data["ingested_count"] > 0

    # Fetch takes and verify thumbnails exist
    takes_res = client.get("/api/takes?production_id=DEMO_PRODUCTION_TEST&shoot_day=31")
    assert takes_res.status_code == 200
    takes = takes_res.json()
    assert len(takes) > 0
    takes_with_thumb = [t for t in takes if t.get("thumbnail_url")]
    assert len(takes_with_thumb) > 0

    # Verify multi-camera and audio grouping for Scene 27/7 Take 1
    t27_7_1 = next((t for t in takes if t.get("slate") == "27/7" and t.get("take_id") == "1"), None)
    assert t27_7_1 is not None
    assert len(t27_7_1.get("video_files", [])) >= 3
    assert len(t27_7_1.get("camera_angles", [])) >= 3
    assert len(t27_7_1.get("audio_files", [])) >= 1
    assert t27_7_1["audio_files"][0]["file_name"] == "27-7T01.WAV"
    assert "MixL" in t27_7_1["audio_files"][0]["tracks"]


def test_api_sequences_endpoint(client):
    client.post("/api/seed", json={"production_id": "DEMO_PRODUCTION_SEQ_TEST", "shoot_day": "31"})

    seq_res = client.get("/api/sequences?production_id=DEMO_PRODUCTION_SEQ_TEST&shoot_day=31")
    assert seq_res.status_code == 200
    seqs = seq_res.json()
    assert len(seqs) > 0

    # Verify Scene 27 sequence summary
    seq27 = next((s for s in seqs if s["sequence"] == "27"), None)
    assert seq27 is not None
    assert "ORGAN" in seq27["location"]
    assert "LEAD plays" in seq27["description"]
    assert len(seq27["camera_cards"]) > 0
    assert seq27["script_log_doc"] is not None
    assert "TCLog" in seq27["script_log_doc"]["filename"] or "Editor" in seq27["script_log_doc"]["filename"]
    assert seq27["camera_a_doc"] is not None
    assert "CAM_A" in seq27["camera_a_doc"]["filename"]
    assert seq27["silverstack_thumbnail_doc"] is not None
    assert "Thumbnail" in seq27["silverstack_thumbnail_doc"]["filename"]

    # Verify Wild Track detection
    seq_wt = next((s for s in seqs if s["is_wild_track"]), None)
    assert seq_wt is not None


def test_api_resolve_and_unresolve_discrepancy(client):
    # Seed data
    client.post("/api/seed", json={"production_id": "RESOLVE_TEST", "shoot_day": "31"})

    # Get discrepancies
    disc_res = client.get("/api/discrepancies?production_id=RESOLVE_TEST&shoot_day=31")
    assert disc_res.status_code == 200
    discs = disc_res.json()

    # Create / resolve a discrepancy
    test_disc_id = "test-disc-123"
    resolve_payload = {
        "production_id": "RESOLVE_TEST",
        "shoot_day": "31",
        "entity_id": "27/7 Take 1",
        "resolved_card": "A120",
        "resolution_note": "Confirmed with camera department: Card is A120",
        "resolved_by": "Assistant Editor Jane",
    }
    res = client.post(f"/api/discrepancies/{test_disc_id}/resolve", json=resolve_payload)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["status"] == "RESOLVED"
    assert res_data["resolution"]["resolved_card"] == "A120"
    assert res_data["resolution"]["is_resolved"] is True

    # Verify get_discrepancies returns resolved information
    disc_res2 = client.get("/api/discrepancies?production_id=RESOLVE_TEST&shoot_day=31")
    assert disc_res2.status_code == 200

    # Unresolve / re-open
    unres = client.post(f"/api/discrepancies/{test_disc_id}/unresolve")
    assert unres.status_code == 200
    assert unres.json()["status"] == "UNRESOLVED"





