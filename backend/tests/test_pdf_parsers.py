"""
TDD Test Suite for Deterministic PDF Parsers (ZoeLog Camera, Script Editor Log, Silverstack Volume).

Evidence:
- data/examples/
"""
import pytest
from backend.app.parsers.pdf_parsers import (
    parse_zoelog_camera_text,
    parse_editors_log_text,
    parse_silverstack_volume_text,
)


SAMPLE_ZOELOG_TEXT = """
La DemoProduction Camera Report
Generated using ZoeLog
ROLL A120 DATE 28 Jul 2026 CAMERA Arri Alexa 35 MAGAZINE #5
SCENE TAKE CLIP
27/7 Lens(Cooke Anamorphic/i 50mm) StopF2 7/10 Color Temp6000K FPS24fps
Shutter172.8 ISO800EI
1 001
2 002
49/1 Lens(Cooke Anamorphic/i 50mm) StopF2 7/10 Color Temp6000K FPS24fps
Shutter172.8 ISO800EI
1 003
2 004
3 005
"""

SAMPLE_EDITORS_LOG_TEXT = """
DAILY EDITOR'S LOG 28/07/2026
Day: Day 31 - Main Unit
Slate Take # Description CR SR Time Lens Comments
27/7 1 LEAD plays -> He sees SUPPORT A120 280726 2:46 1
27/7 2 A120 2:53 THIS TAKE IS NOT GOOD 1
49/1 1 The concert has already started A120 280726 2:18 4
"""

SAMPLE_SILVERSTACK_VOLUME_TEXT = """
Volume Report 28/7/26, 19:27
Pomfort Silverstack XT
664 SD
128-1T01.WAV
XXH64:1b742d797173f0d4 60.49 MB
128-1T02.WAV
XXH64:b90cf1a98bb7db8e 59.62 MB
64A-1T01.WAV
XXH64:50324f3038cb6e4b 143.43 MB
"""


class TestPDFParsers:
    def test_parse_zoelog_camera_text(self):
        records = parse_zoelog_camera_text(SAMPLE_ZOELOG_TEXT)
        assert len(records) == 5
        
        r1 = records[0]
        assert r1.slate == "27/7"
        assert r1.take_id == "1"
        assert r1.camera_roll == "A120"
        assert r1.clip_name == "A120_C001"
        assert r1.fps == 24.0
        assert r1.iso == 800

        r3 = records[2]
        assert r3.slate == "49/1"
        assert r3.take_id == "1"
        assert r3.clip_name == "A120_C003"

    def test_parse_editors_log_text(self):
        records = parse_editors_log_text(SAMPLE_EDITORS_LOG_TEXT)
        assert len(records) == 3
        
        r1 = records[0]
        assert r1.slate == "27/7"
        assert r1.take_id == "1"
        assert r1.camera_roll == "A120"
        assert r1.sound_roll == "SR280726" or r1.sound_roll is not None

        r2 = records[1]
        assert r2.slate == "27/7"
        assert r2.take_id == "2"
        assert "NOT GOOD" in (r2.note or "")

    def test_parse_silverstack_volume_text(self):
        clips = parse_silverstack_volume_text(SAMPLE_SILVERSTACK_VOLUME_TEXT)
        assert len(clips) == 3
        
        c1 = clips[0]
        assert c1.file_name == "128-1T01.WAV"
        assert c1.checksum == "1b742d797173f0d4"
        assert c1.checksum_type == "XXH64"
        assert c1.file_size_bytes == int(60.49 * 1024 * 1024)
