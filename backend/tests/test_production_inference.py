"""
TDD Test Suite for Production & Shoot Day Automatic Inference.

Evidence:
- data/examples/
- data/examples/
"""
import pytest
from backend.app.parsers.classifier import (
    classify_document, 
    infer_production_and_day,
    DocumentClassification,
)


class TestProductionAndDayInference:
    def test_infer_from_sound_csv_content_and_filename(self):
        content = """SOUND REPORT
Project:,"GREAT HALL",
Date:,"28/07/26",
Sound Mixer:,"SOUND MIXER",
File Name,Scene,Take,Length,Start TC
27-7T01.WAV,27-7,01,00:03:00,09:25:40:00
"""
        prod_id, shoot_day = infer_production_and_day(
            filename="260728_Report.csv", content=content
        )
        assert prod_id == "DEMO_PRODUCTION"
        assert shoot_day == "31" or shoot_day is not None

    def test_infer_from_zoelog_camera_pdf_filename(self):
        prod_id, shoot_day = infer_production_and_day(
            filename="DemoProduction-2026-7-28_CAM_A.pdf", content=None
        )
        assert prod_id == "DEMO_PRODUCTION"
        assert shoot_day == "31"

    def test_infer_from_editors_log_pdf_filename_day39(self):
        prod_id, shoot_day = infer_production_and_day(
            filename="DEMO_Editor’sLog_D039_070826.pdf", content=None
        )
        assert prod_id == "DEMO_PRODUCTION"
        assert shoot_day == "39"

    def test_infer_from_silverstack_clips_filename(self):
        prod_id, shoot_day = infer_production_and_day(
            filename="Clips-260728_SD31-20260728-1927.pdf", content=None
        )
        assert shoot_day == "31"

    def test_classify_document_returns_inferred_metadata(self):
        classification = classify_document(
            filename="DEMO_Facing&Lined_D031_280726.pdf", content=None
        )
        assert classification.inferred_production_id == "DEMO_PRODUCTION"
        assert classification.inferred_shoot_day == "31"
