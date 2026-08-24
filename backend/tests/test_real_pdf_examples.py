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
    parse_silverstack_shooting_day_text,
    parse_silverstack_clips_text,
    parse_silverstack_thumbnail_text,
    parse_silverstack_pdf_text,
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
        for cam, expected_roll in [("CAM_A", "A120"), ("CAM_B", "B039"), ("CAM_C", "C005")]:
            cam_path = os.path.join(EXAMPLES_DIR, f"DemoProduction-2026-7-28_{cam}.pdf")
            with open(cam_path, "rb") as f:
                text = extract_text_from_pdf(f.read())
            
            records = parse_zoelog_camera_text(text)
            assert len(records) > 0
            rolls = {r.camera_roll for r in records}
            assert expected_roll in rolls
            assert records[0].clip_name is not None

    def test_parse_real_silverstack_volume_pdf(self):
        vol_path = os.path.join(EXAMPLES_DIR, "Volume-664 SD-20260728-1927.pdf")
        with open(vol_path, "rb") as f:
            text = extract_text_from_pdf(f.read())
        
        records = parse_silverstack_volume_text(text)
        assert len(records) > 900
        assert records[0].checksum is not None
        assert records[0].volume_name == "664 SD"

        # Verify WAV clip parsing with scene/shot/take and sound roll folder
        wav_clip = next(r for r in records if "117-1T01" in r.file_name)
        assert wav_clip.card_type == "sound"
        assert wav_clip.reel_tape == "26Y07M27"
        assert wav_clip.scene == "117"
        assert wav_clip.shot == "1"
        assert wav_clip.take_id == "1"
        assert wav_clip.checksum is not None
        assert "PCM" in (wav_clip.codec or "")

    def test_parse_real_silverstack_shooting_day_pdf(self):
        day_path = os.path.join(EXAMPLES_DIR, "Shooting Day-260728_SD31-20260728-1927.pdf")
        with open(day_path, "rb") as f:
            text = extract_text_from_pdf(f.read())
        
        records = parse_silverstack_shooting_day_text(text)
        assert len(records) > 0
        rolls = {r.camera_roll for r in records if r.camera_roll}
        assert "A120" in rolls or "B039" in rolls or "C005" in rolls

    def test_parse_real_silverstack_clips_pdf(self):
        clips_path = os.path.join(EXAMPLES_DIR, "Clips-260728_SD31-20260728-1927.pdf")
        with open(clips_path, "rb") as f:
            text = extract_text_from_pdf(f.read())
        
        records = parse_silverstack_clips_text(text)
        assert len(records) > 0
        assert "27-7T01.WAV" in [r.file_name for r in records]

    def test_parse_real_silverstack_thumbnail_pdf(self):
        thumb_path = os.path.join(EXAMPLES_DIR, "Thumbnail-260728_SD31-20260728-1927.pdf")
        with open(thumb_path, "rb") as f:
            pdf_bytes = f.read()
            text = extract_text_from_pdf(pdf_bytes)
        
        # Test thumbnail extraction
        from backend.app.parsers.pdf_parsers import extract_thumbnails_from_pdf
        thumbnails_map = extract_thumbnails_from_pdf(pdf_bytes)
        assert len(thumbnails_map) > 50

        records = parse_silverstack_pdf_text(text, thumbnails_map=thumbnails_map)
        assert len(records) > 100

        # Verify Audio clip fields: Name, Reel/Tape, Scene/Shot/Take, Codec, Recording Date, card_type
        audio_clip = next(r for r in records if "27-7T01" in r.file_name)
        assert audio_clip.reel_tape == "26Y07M27"
        assert audio_clip.scene == "27"
        assert audio_clip.shot == "7"
        assert audio_clip.take_id == "1"
        assert "PCM" in (audio_clip.codec or "")
        assert audio_clip.card_type == "sound"
        assert audio_clip.recording_date is not None

        # Verify Camera clip fields: Name, Reel/Tape, Scene/Shot/Take, Codec, Recording Date, FPS, ISO, card_type, thumbnail
        camera_clip = next(r for r in records if "A_0120C001" in r.file_name)
        assert camera_clip.camera_roll == "A120"
        assert camera_clip.reel_tape == "A_0120_1EIC"
        assert camera_clip.scene == "27"
        assert camera_clip.shot == "7"
        assert camera_clip.take_id == "1"
        assert "ARRIRAW" in (camera_clip.codec or "")
        assert camera_clip.fps == 24.0
        assert camera_clip.iso == 800
        assert camera_clip.card_type == "camera"
        assert camera_clip.thumbnail_b64 is not None
        assert camera_clip.thumbnail_b64.startswith("data:image/jpeg;base64,")
        assert "28/7/26" in (camera_clip.recording_date or "")
