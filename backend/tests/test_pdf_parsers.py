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
26Y06M18 5.29 GB
+99BDF-9T01.WAV
XXH64:202ab43613939de5 133.93 MB
71C-3T02.WAV
XXH64:b90cf1a98bb7db8e 59.62 MB
49WTT01.WAV
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
        # Script supervisor logs track camera cards and shoot date, not sound rolls
        assert r1.sound_roll is None

        r2 = records[1]
        assert r2.slate == "27/7"
        assert r2.take_id == "2"
        assert "NOT GOOD" in (r2.note or "")

    def test_parse_silverstack_volume_text(self):
        clips = parse_silverstack_volume_text(SAMPLE_SILVERSTACK_VOLUME_TEXT)
        assert len(clips) == 3
        
        c1 = clips[0]
        assert c1.file_name == "+99BDF-9T01.WAV"
        assert c1.scene == "+99BDF"
        assert c1.shot == "9"
        assert c1.take_id == "01"
        assert c1.reel_tape == "26Y06M18"
        assert c1.checksum == "202ab43613939de5"
        assert c1.checksum_type == "XXH64"
        assert c1.card_type == "sound"

        c2 = clips[1]
        assert c2.file_name == "71C-3T02.WAV"
        assert c2.scene == "71C"
        assert c2.shot == "3"
        assert c2.take_id == "02"

        c3 = clips[2]
        assert c3.file_name == "49WTT01.WAV"
        assert c3.scene == "49"
        assert c3.shot == "WT"
        assert c3.take_id == "01"
        assert c3.is_wild_track is True

    def test_parse_silverstack_clips_text(self):
        sample_clips_text = """
Clips Report 28/7/26, 19:27
Pomfort Silverstack XT 1/10
27-7T01 Sound Dev: Mix664 S#KA0513004007 3:00 min
49WTT01 Sound Dev: Mix664 S#KA0513004007 59 sec
A_0120C001_260728_091309_h1EIC A_ ARRI ALEXA 35 2:45 min 4608x3164 172.8° @ 24fps 50.0 mm 2 9/10 800 6000 K
B_0039C001_260728_102755_h1C9B B_ ARRI ALEXA 35 2:30 min 4608x3164 172.8° @ 24fps 50.0 mm 2.8 800 6000 K
        """
        from backend.app.parsers.pdf_parsers import parse_silverstack_clips_text
        clips = parse_silverstack_clips_text(sample_clips_text)
        assert len(clips) == 4

        # Sound 1
        s1 = clips[0]
        assert s1.file_name == "27-7T01.WAV"
        assert s1.scene == "27"
        assert s1.shot == "7"
        assert s1.take_id == "01"
        assert s1.card_type == "sound"

        # Sound 2 (Wild track)
        s2 = clips[1]
        assert s2.file_name == "49WTT01.WAV"
        assert s2.is_wild_track is True

        # Video 1
        v1 = clips[2]
        assert v1.file_name == "A_0120C001_260728_091309_h1EIC.mxf"
        assert v1.camera_roll == "A120"
        assert v1.camera == "A"
        assert v1.iso == 800
        assert v1.tstop == "2 9/10"
        assert v1.card_type == "camera"

        # Video 2
        v2 = clips[3]
        assert v2.file_name == "B_0039C001_260728_102755_h1C9B.mxf"
        assert v2.camera_roll == "B039"
        assert v2.camera == "B"


