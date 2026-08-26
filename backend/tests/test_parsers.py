"""
TDD Test Suite for Slice 1: Deterministic Parsers (Sound ALE/CSV, Camera CSV, Silverstack XML).

Evidence:
- references/domain/documents.md
- references/findings/defects-found.md
- references/constraints/failure-modes.md ('The confident nothing')
"""
import pytest
from backend.app.parsers.sound_ale import parse_sound_ale
from backend.app.parsers.camera_csv import parse_camera_csv
from backend.app.parsers.silverstack_xml import parse_silverstack_xml
from backend.app.parsers.base import ParserFailureError


SAMPLE_SOUND_ALE = """Heading
FIELD_DELIM	TABS
VIDEO_FORMAT	1080
FILM_FORMAT	35mm
FPS	24

Column
Name	Tracks	Start	End	Tape	Scene	Take	Sound Roll

Data
27-7_T01	1,2,3,4	10:14:22:00	10:15:10:00	SR01	27/7	1	SR01
27-7_T02	1,2,3,4	10:16:05:00	10:17:00:00	SR01	27/7	2PK	SR01
27-7_T03	1,2,3,4	10:18:12:00	10:19:30:00	SR01	27/7	3*	SR01
"""


SAMPLE_CAMERA_CSV = """Slate,Take,Roll,FPS,Lens,ISO,Start TC,End TC,Clip Name
27/7,1,A120,24,50mm,800,10:14:22:00,10:15:10:00,A120_C001_260728.MOV
27/7,2PK,A120,24,50mm,800,10:16:05:00,10:17:00:00,A120_C002_260728.MOV
27/7,3 VFX,A120,24,50mm,800,10:18:12:00,10:19:30:00,A120_C003_260728.MOV
"""


SAMPLE_SILVERSTACK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<SilverstackReport version="1.0">
    <Volume name="MAG_A_120">
        <Clip>
            <FileName>A120_C001_260728.MOV</FileName>
            <Reel>A_0120</Reel>
            <Bytes>4294967296</Bytes>
            <Hash type="MD5">e99a18c428cb38d5f260853678922e03</Hash>
            <DurationFrames>1152</DurationFrames>
        </Clip>
        <Clip>
            <FileName>A120_C002_260728.MOV</FileName>
            <Reel>A_0120</Reel>
            <Bytes>5368709120</Bytes>
            <Hash type="MD5">9e107d9d372bb6826bd81d3542a419d6</Hash>
            <DurationFrames>1320</DurationFrames>
        </Clip>
    </Volume>
</SilverstackReport>
"""


class TestSoundALEParser:
    def test_parse_valid_sound_ale(self):
        records = parse_sound_ale(SAMPLE_SOUND_ALE)
        assert len(records) == 3
        
        # Take 1
        r1 = records[0]
        assert r1.scene == "27"
        assert r1.slate == "27/7"
        assert r1.take_id == "1"
        assert r1.sound_roll == "SR01"
        assert r1.timecode_in == "10:14:22:00"
        assert r1.timecode_out == "10:15:10:00"

        # Take 2 (Pickup)
        r2 = records[1]
        assert r2.take_id == "2PK"
        assert r2.is_pickup is True

        # Take 3 (Starred)
        r3 = records[2]
        assert r3.take_id == "3"
        assert r3.is_starred is True

    def test_parse_real_sound_report_csv(self):
        real_style_csv = """SOUND REPORT
Project:,"DEMO PRODUCTION"
Director:,"DIRECTOR"
Date:,"27/07/26"
Sound Mixer:,"SOUND MIXER"

File Name,Scene,Take,Length,Start TC,Trk 1,Trk 2,Notes
27-7T01.WAV,27-7,01,00:03:00,09:25:40:00,"MixL","MixR",""
49WTT01.WAV,49WT,01,00:00:58,13:59:20:00,"MixL","MixR","wildtrack_exit"
117-1T01.WAV,117-1,01,00:04:36,16:19:49:00,"MixL","MixR","DOBLE DE LEAD"
"""
        records = parse_sound_ale(real_style_csv)
        assert len(records) == 3
        
        # Check standard take
        assert records[0].slate == "27/7"
        assert records[0].take_id == "1"
        assert records[0].timecode_in == "09:25:40:00"

        # Check wild track isolation and canonical slate/scene format
        assert records[1].is_wild_track is True
        assert records[1].slate == "49/WT"
        assert records[1].scene == "49"
        assert records[1].take_id == "1"
        assert records[1].note == "wildtrack_exit"

        # Check scene 117 take 1
        assert records[2].slate == "117/1"
        assert records[2].take_id == "1"

    def test_parse_sound_csv_wild_track_variations(self):
        csv_variations = """File Name,Scene,Take,Length,Start TC,Trk 1,Notes
49WTT01.WAV,49,WT 01,00:00:58,13:59:20:00,"MixL","wild track take in take col"
6WT_T01.WAV,6WT,1,00:00:45,14:00:00:00,"MixL","6WT in scene col"
WT49_01.WAV,WT 49,01,00:01:00,14:05:00:00,"MixL","WT 49 prefix"
"""
        records = parse_sound_ale(csv_variations)
        assert len(records) == 3
        assert records[0].slate == "49/WT"
        assert records[0].scene == "49"
        assert records[0].take_id == "1"
        assert records[0].is_wild_track is True

        assert records[1].slate == "6/WT"
        assert records[1].scene == "6"
        assert records[1].take_id == "1"
        assert records[1].is_wild_track is True

        assert records[2].slate == "49/WT"
        assert records[2].scene == "49"
        assert records[2].take_id == "1"
        assert records[2].is_wild_track is True

    def test_reject_empty_or_corrupt_sound_ale(self):
        with pytest.raises(ParserFailureError):
            parse_sound_ale("Heading\nCorrupt garbage with no Column/Data")


class TestCameraCSVParser:
    def test_parse_valid_camera_csv(self):
        records = parse_camera_csv(SAMPLE_CAMERA_CSV)
        assert len(records) == 3
        
        r1 = records[0]
        assert r1.slate == "27/7"
        assert r1.take_id == "1"
        assert r1.camera_roll == "A120"
        assert r1.fps == 24.0
        assert r1.iso == 800
        assert r1.clip_name == "A120_C001_260728.MOV"

        r3 = records[2]
        assert r3.take_id == "3"
        assert r3.is_vfx is True
        assert r3.note == "VFX"

    def test_reject_empty_camera_csv(self):
        with pytest.raises(ParserFailureError):
            parse_camera_csv("")


class TestSilverstackXMLParser:
    def test_parse_valid_silverstack_xml(self):
        records = parse_silverstack_xml(SAMPLE_SILVERSTACK_XML)
        assert len(records) == 2
        
        c1 = records[0]
        assert c1.file_name == "A120_C001_260728.MOV"
        assert c1.camera_roll == "A120"  # Normalized from A_0120
        assert c1.file_size_bytes == 4294967296
        assert c1.checksum == "e99a18c428cb38d5f260853678922e03"
        assert c1.checksum_type == "MD5"

    def test_reject_invalid_silverstack_xml(self):
        with pytest.raises(ParserFailureError):
            parse_silverstack_xml("<InvalidRoot><Empty/></InvalidRoot>")
