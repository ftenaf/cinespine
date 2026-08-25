"""
TDD Test Suite for Scripte PDF Parsers (TCLog & Detailed Editor's Log).

Evidence:
- data/examples/DEMO_TCLog_D031_280726.pdf
- data/examples/DEMO_DetailedEditor’sLog_D031_280726.pdf
"""
import pytest
from backend.app.parsers.pdf_parsers import (
    parse_scripte_tclog_text,
    parse_scripte_detailed_editor_log_text,
)


SAMPLE_TCLOG_TEXT = """
DAILY TIMECODE LOG 28/07/2026
LAC
Day: Day 31 - Main Unit
Date: 28/07/2026
Slate Take # Timecode In Actual Time In Timecode Out Actual Time Out Description CR SR Time SU
27/7 1 09:26:12:04 09:25:48 09:28:58:12 09:28:34 Scene(s): 27 LEAD plays -> He sees SUPPORT A120 280726 2:46 1
27/7 1 09:26:12:04 09:25:48 09:28:58:12 09:28:34 Scene(s): 27 LEAD plays -> He sees SUPPORT B039 280726 2:46 2
27/7 1 09:26:12:04 09:25:48 09:28:58:12 09:28:34 Scene(s): 27 LEAD plays -> He sees SUPPORT C005 280726 2:46 3
27/7 2 09:36:11:14 09:35:47 09:39:05:05 09:38:40 Scene(s): 27 LEAD plays -> He sees SUPPORT A120 280726 2:53 1
THIS TAKE IS NOT GOOD FOR DIRECTOR'S DIRECTING.
"""

SAMPLE_DETAILED_EDITOR_TEXT = """
DETAILED EDITOR'S LOG 28/07/2026
LAC - V31
Day: Day 31 - Main Unit
Date: 28/07/2026
Slate Take Description CR SR Time Camera Info Comments
6WT 1 Scene(s): 6, 49 Wild Track: 6WT n/a 280726 0:29 pasos de LEAD
27/7 1 Scene(s): 27 Sticks - xwide. Frontal VWS A120 280726 2:46 1
27/7 1 Dolly - wide B039 280726 2:46 2
27/7 1 Slider - wide C005 280726 2:46 3
49/4 1 Scene(s): 49 VFX Plate background B040 280726 2:33 NG FOR CAMERA
"""


class TestScripteParsers:
    def test_parse_scripte_tclog_text(self):
        records = parse_scripte_tclog_text(SAMPLE_TCLOG_TEXT)
        assert len(records) >= 2

        # Verify Take 1 across cameras
        r1 = records[0]
        assert r1.slate == "27/7"
        assert r1.take_id == "1"
        assert r1.timecode_in == "09:26:12:04"
        assert r1.timecode_out == "09:28:58:12"
        assert r1.camera_roll in ["A120", "B039", "C005"]
        # Script supervisor logs track camera cards and shoot date, sound_roll is None
        assert r1.sound_roll is None

        # Verify Take 2 comments
        r2 = [r for r in records if r.take_id == "2"][0]
        assert r2.timecode_in == "09:36:11:14"
        assert "NOT GOOD" in (r2.note or "")

    def test_parse_scripte_detailed_editor_log_text_wt_and_vfx(self):
        records = parse_scripte_detailed_editor_log_text(SAMPLE_DETAILED_EDITOR_TEXT)
        assert len(records) >= 3

        # Wild track verification
        wt_rec = [r for r in records if "6WT" in (r.slate or "") or r.is_wild_track][0]
        assert wt_rec.is_wild_track is True
        assert wt_rec.take_id == "1"
        assert "pasos de LEAD" in (wt_rec.note or "")

        # VFX verification
        vfx_rec = [r for r in records if "49/4" in (r.slate or "")][0]
        assert vfx_rec.is_vfx is True
        assert vfx_rec.camera_roll == "B040"

    def test_parse_real_tclog_vector_circles(self):
        import os
        from backend.app.parsers.pdf_parsers import extract_text_from_pdf
        pdf_path = "data/examples/DEMO_TCLog_D031_280726.pdf"
        if os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                txt = extract_text_from_pdf(f.read())
            recs = parse_scripte_tclog_text(txt)
            t27_7 = [r for r in recs if r.slate == "27/7"]
            t27_7_1 = [r for r in t27_7 if r.take_id == "1"]
            assert len(t27_7_1) == 3
            # All 3 cameras (A120, B039, C005) on 27/7 Take 1 must be starred / circled
            for r in t27_7_1:
                assert r.is_starred is True
            # Take 2 on 27/7 must not be starred
            t27_7_2 = [r for r in t27_7 if r.take_id == "2"]
            for r in t27_7_2:
                assert r.is_starred is False
