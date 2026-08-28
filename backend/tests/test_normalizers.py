"""
TDD Test Suite for Slice 1: Identity Normalization and Key Folding Engine.

Ground truth derived from domain evidence:
- references/domain/identity-rules.md
- references/findings/defects-found.md
"""
import pytest
from backend.app.normalizers.rolls import normalize_camera_roll, normalize_sound_roll
from backend.app.normalizers.slates import normalize_slate, parse_scene_compound
from backend.app.normalizers.takes import normalize_take, TakeResult
from backend.app.normalizers.shoot_days import normalize_shoot_day


class TestCameraRollNormalization:
    """
    Evidence: references/findings/defects-found.md
    'Roll normalisation split one take across two rolls. Stripping all leading zeros
    folds A_0120 to A120 correctly and B_0039 to B39 incorrectly, because paperwork
    writes B039. Invisible on A camera, wrong on B and C.'
    """

    def test_camera_roll_a_folding(self):
        # A camera roll 120 variations
        assert normalize_camera_roll("A120") == "A120"
        assert normalize_camera_roll("A_0120") == "A120"
        assert normalize_camera_roll("A_0120_1EIC") == "A120"
        assert normalize_camera_roll("a120") == "A120"

    def test_camera_roll_b_preserves_significant_zero(self):
        # B camera roll 39 standard 3-digit form (B039)
        assert normalize_camera_roll("B039") == "B039"
        assert normalize_camera_roll("B_0039") == "B039"
        assert normalize_camera_roll("B_0039_2EIC") == "B039"
        assert normalize_camera_roll("B39") == "B039"

    def test_camera_roll_c_single_digit(self):
        assert normalize_camera_roll("C001") == "C001"
        assert normalize_camera_roll("C_0001") == "C001"
        assert normalize_camera_roll("C1") == "C001"

    def test_camera_roll_empty_or_invalid(self):
        assert normalize_camera_roll("") is None
        assert normalize_camera_roll(None) is None


class TestSoundRollNormalization:
    def test_sound_roll_folding(self):
        assert normalize_sound_roll("SR01") == "SR01"
        assert normalize_sound_roll("SR_001") == "SR01"
        assert normalize_sound_roll("R01") == "SR01"
        assert normalize_sound_roll("01") == "SR01"

    def test_sound_roll_filters_dates_and_preserves_sd_folders(self):
        # Dates (like 280726 = 28 Jul 2026) are not sound rolls
        assert normalize_sound_roll("280726") is None
        assert normalize_sound_roll("20260728") is None
        assert normalize_sound_roll("n/a") is None
        assert normalize_sound_roll("MOS") is None
        # Sound Devices reel tape folder format
        assert normalize_sound_roll("26Y07M27") == "26Y07M27"


class TestSlateNormalization:
    """
    Evidence: references/domain/identity-rules.md
    'Written 27/7 by camera and script, 27-7 by sound recorder, 27-7T01 inside Silverstack clip name.'
    """

    def test_standard_slash_and_dash_slates(self):
        assert normalize_slate("27/7") == "27/7"
        assert normalize_slate("27-7") == "27/7"
        assert normalize_slate("27-7T01") == "27/7"
        assert normalize_slate("27/7T01") == "27/7"
        assert normalize_slate("64A/1") == "64A/1"
        assert normalize_slate("64A-1") == "64A/1"

    def test_wild_track_slate_folding(self):
        # 49WT vs 49/WT vs 49-WT vs 49 WT vs 49WTT01 all fold to 49/WT
        assert normalize_slate("49WT") == "49/WT"
        assert normalize_slate("49/WT") == "49/WT"
        assert normalize_slate("49-WT") == "49/WT"
        assert normalize_slate("49 WT") == "49/WT"
        assert normalize_slate("49_WT") == "49/WT"
        assert normalize_slate("49WTT01") == "49/WT"
        assert normalize_slate("6WT") == "6/WT"
        assert normalize_slate("6/WT") == "6/WT"
        assert normalize_slate("WT49") == "49/WT"
        assert normalize_slate("WT/49") == "49/WT"
        assert normalize_slate("WT") == "WT"
        assert normalize_slate("WILD") == "WT"

    def test_compound_scene_expansion(self):
        assert parse_scene_compound("21+25") == ["21", "25"]
        assert parse_scene_compound("73C-74AC") == ["73C", "74AC"]
        assert parse_scene_compound("64A") == ["64A"]


class TestTakeNormalization:
    """
    Evidence: references/domain/identity-rules.md
    '1, 01 -> Take one (same take)
     3* -> Take 3 (starred note flag)
     2PK -> Pickup (distinct take)
     3 VFX -> Take 3 (VFX flag)
     FALSE -> False start (not a valid take)'
    """

    def test_standard_and_padded_takes(self):
        res1 = normalize_take("1")
        res2 = normalize_take("01")
        res3 = normalize_take("T1")
        res4 = normalize_take("T01")
        res5 = normalize_take("TK01")
        res6 = normalize_take("TAKE 01")
        assert res1.take_id == "1"
        assert res2.take_id == "1"
        assert res3.take_id == "1"
        assert res4.take_id == "1"
        assert res5.take_id == "1"
        assert res6.take_id == "1"
        assert res1.is_starred is False

    def test_starred_or_marked_take(self):
        res = normalize_take("3*")
        res_t = normalize_take("T03*")
        assert res.take_id == "3"
        assert res.is_starred is True
        assert res_t.take_id == "3"
        assert res_t.is_starred is True

    def test_free_text_notes_in_take_box(self):
        res = normalize_take("3 VFX")
        res_t = normalize_take("T03 VFX")
        assert res.take_id == "3"
        assert res.note == "VFX"
        assert res.is_vfx is True
        assert res_t.take_id == "3"
        assert res_t.is_vfx is True

    def test_pickup_take_is_distinct(self):
        res = normalize_take("2PK")
        res_t = normalize_take("T02PK")
        assert res.take_id == "2PK"
        assert res.is_pickup is True
        assert res_t.take_id == "2PK"
        assert res_t.is_pickup is True

    def test_false_start_is_not_a_take(self):
        res = normalize_take("FALSE")
        res_fc = normalize_take("FC")
        assert res.is_false_start is True
        assert res.is_valid_take is False
        assert res.take_id == "FALSE"
        assert res_fc.is_false_start is True
        assert res_fc.is_valid_take is False
        assert res_fc.take_id == "FALSE"

    def test_wild_track_isolation(self):
        res = normalize_take("WT 01")
        res_t = normalize_take("WTT01")
        assert res.is_wild_track is True
        assert res.take_id == "1"
        assert res_t.is_wild_track is True
        assert res_t.take_id == "1"


class TestShootDayNormalization:
    """
    Evidence: references/domain/identity-rules.md
    'Written SD31, D031, #31, and embedded in filenames as _D031_, 260728_SD31.'
    """

    def test_shoot_day_folding(self):
        assert normalize_shoot_day("SD31") == "31"
        assert normalize_shoot_day("D031") == "31"
        assert normalize_shoot_day("#31") == "31"
        assert normalize_shoot_day("260728_SD31") == "31"
        assert normalize_shoot_day("31") == "31"


class TestPartTakes:
    """
    A take covered in more than one pass is numbered in parts. The parts are
    distinct takes, not a decimal quantity to be rounded into one.
    """

    def test_the_parts_are_kept_apart(self):
        assert normalize_take("1.1").take_id == "1.1"
        assert normalize_take("1.2").take_id == "1.2"
        assert normalize_take("2.10").take_id == "2.10"

    def test_padding_is_still_stripped(self):
        assert normalize_take("01.2").take_id == "1.2"

    def test_a_part_take_can_be_circled(self):
        result = normalize_take("2.1*")
        assert result.take_id == "2.1"
        assert result.is_starred is True

    def test_a_whole_take_is_unchanged(self):
        assert normalize_take("2").take_id == "2"
        assert normalize_take("2PK").take_id == "2PK"
