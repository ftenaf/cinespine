"""
Demo Production PDF Ingestion & Parsing Integration Tests.

Validates that the synthetic TCLog parses cleanly without errors,
ensuring we can run a full demo of the ingestion pipeline.
"""
import os
import pytest
from backend.app.parsers.pdf_parsers import (
    extract_text_from_pdf,
    parse_scripte_tclog_text,
)

EXAMPLES_DIR = os.environ.get("CINESPINE_EXAMPLES_DIR", "data/examples")

class TestDemoPDFIngestion:
    def test_parse_synthetic_scripte_tclog(self):
        tclog_path = os.path.join(EXAMPLES_DIR, "DEMO_TCLog_Synthetic.pdf")
        if not os.path.exists(tclog_path):
            pytest.skip("Synthetic PDF not generated. Run scripts/generate_synthetic_fixtures.py first.")
            
        with open(tclog_path, "rb") as f:
            text = extract_text_from_pdf(f.read())
        
        records = parse_scripte_tclog_text(text)
        assert len(records) > 0

        # Check for card extraction 
        cards = {r.camera_roll for r in records if r.camera_roll}
        assert "A120" in cards or "B039" in cards or "C005" in cards

        # Check for timecodes
        takes_with_tc = [r for r in records if r.timecode_in]
        assert len(takes_with_tc) > 0
