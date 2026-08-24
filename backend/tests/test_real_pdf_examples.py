"""
Real Production PDF Ingestion & Parsing Integration Tests.

Validates that real Scripte TCLogs, Detailed Editor's Logs, ZoeLog Camera PDFs,
and Silverstack Volume PDFs parse 100% cleanly without errors.
"""
import os
import pytest
from backend.app.parsers.pdf_parsers import (
    extract_text_from_pdf,
    parse_scripte_tclog_text,
    parse_scripte_detailed_editor_log_text,
    parse_zoelog_camera_text,
    parse_silverstack_volume_text,
)

EXAMPLES_DIR = r"data/examples"


@pytest.mark.skipif(not os.path.exists(EXAMPLES_DIR), reason="Example PDFs not present locally")
class TestRealPDFExamples:
    def test_parse_real_scripte_tclog(self):
        tclog_path = os.path.join(EXAMPLES_DIR, "DEMO_TCLog_D031_280726.pdf")
        with open(tclog_path, "rb") as f:
            text = extract_text_from_pdf(f.read())
        
        records = parse_scripte_tclog_text(text)
        assert len(records) > 0

        # Check for card extraction (e.g. A120, B039, C005)
        cards = {r.camera_roll for r in records if r.camera_roll}
        assert "A120" in cards or "B039" in cards or "C005" in cards

        # Check for timecodes
        takes_with_tc = [r for r in records if r.timecode_in]
        assert len(takes_with_tc) > 0

    def test_parse_real_scripte_detailed_editors_log(self):
        detailed_path = os.path.join(EXAMPLES_DIR, "DEMO_DetailedEditor’sLog_D031_280726.pdf")
        with open(detailed_path, "rb") as f:
            text = extract_text_from_pdf(f.read())
        
        records = parse_scripte_detailed_editor_log_text(text)
        assert len(records) > 0

        # Verify Wild Track detection (e.g. 6WT)
        wt_records = [r for r in records if r.is_wild_track or "WT" in (r.slate or "")]
        assert len(wt_records) > 0
        assert wt_records[0].is_wild_track is True

    def test_parse_real_zoelog_camera_pdf(self):
        cam_path = os.path.join(EXAMPLES_DIR, "DemoProduction-2026-7-28_CAM_A.pdf")
        with open(cam_path, "rb") as f:
            text = extract_text_from_pdf(f.read())
        
        records = parse_zoelog_camera_text(text)
        assert len(records) > 0
        assert records[0].camera_roll == "A120"

    def test_parse_real_silverstack_volume_pdf(self):
        vol_path = os.path.join(EXAMPLES_DIR, "Volume-664 SD-20260728-1927.pdf")
        with open(vol_path, "rb") as f:
            text = extract_text_from_pdf(f.read())
        
        records = parse_silverstack_volume_text(text)
        assert len(records) > 0
        assert records[0].checksum is not None
