"""
TDD Test Suite for Automatic Document Classifier and Ingestion Router.

Evidence:
- data/examples/
"""
import pytest
from backend.app.parsers.classifier import classify_document, DocumentClassification
from backend.app.streaming.models import AxisType, DepartmentType, DocumentType


class TestDocumentClassifier:
    def test_classify_sound_csv_by_filename_and_content(self):
        content = "SOUND REPORT\nProject:,GREAT HALL\nDate:,27/07/26\nFile Name,Scene,Take,Length,Start TC\n27-7T01.WAV,27-7,01,00:03:00,09:25:40:00"
        res: DocumentClassification = classify_document(filename="260728_Report.csv", content=content)
        
        assert res.doc_type == DocumentType.SOUND_ALE
        assert res.department == DepartmentType.SOUND
        assert res.axis == AxisType.BELIEF
        assert res.is_multimodal is False

    def test_classify_zoelog_camera_pdf(self):
        res = classify_document(filename="DemoProduction-2026-7-28_CAM_A.pdf")
        assert res.doc_type == DocumentType.CAMERA_CSV
        assert res.department == DepartmentType.CAMERA
        assert res.axis == AxisType.BELIEF
        assert res.is_multimodal is False

    def test_classify_facing_and_lined_handwritten_pdf(self):
        res = classify_document(filename="DEMO_Facing&Lined_D031_280726.pdf")
        assert res.doc_type == DocumentType.SCRIPT_LINED
        assert res.department == DepartmentType.SCRIPT
        assert res.axis == AxisType.BELIEF
        assert res.is_multimodal is True  # Needs Gemini Multimodal vision!

    def test_classify_silverstack_volume_report(self):
        res = classify_document(filename="Volume-664 SD-20260728-1927.pdf")
        assert res.doc_type == DocumentType.SILVERSTACK_XML
        assert res.department == DepartmentType.DIT
        assert res.axis == AxisType.EXISTENCE

    def test_classify_dpr_parte_produccion(self):
        res = classify_document(filename="DEMO_ParteProd_D031_280726.pdf")
        assert res.doc_type == DocumentType.DPR
        assert res.department == DepartmentType.OFFICE
        assert res.axis == AxisType.INTENT
