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
    extract_report_date,
    parse_shoot_date,
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
        assert r1.recording_date == "28/07/2026"

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

    def test_parse_unpadded_card_concatenated_with_date_scene_49_9(self):
        # In scene 49 shot 9 take 1, the card was written as B41 and concatenated with date 280726 -> B412807261:1125
        # It must be parsed as canonical card B041, NOT B412
        sample_tclog_49_9 = """
DAILY TIMECODE LOG 28/07/2026
49/9 1* 13:52:08:10
13:51:40
13:53:19:13
13:52:51
Scene(s): 49
LEAD messes up -> Julian looks at him -> 
LEAD stops playing and exits the stage 
B412807261:1125
Lens: LH: D: Fltr: T:
"""
        recs = parse_scripte_tclog_text(sample_tclog_49_9)
        assert len(recs) == 1
        rec = recs[0]
        assert rec.slate == "49/9"
        assert rec.take_id == "1"
        assert rec.camera_roll == "B041"
        assert rec.is_starred is True
        assert rec.timecode_in == "13:52:08:10"
        assert rec.timecode_out == "13:53:19:13"


# --------------------------------------------------------------------------- #
# A shot that plays in more than one scene
# --------------------------------------------------------------------------- #

# Taken from the facing pages for scene 117: three consecutive shots, each with
# its own camera card. The middle and last slates name compound scenes.
FACING_PAGE_COMPOUND_SLATES = """
LAC - V31 Scene:117
Slate Take Description CR SR Time Camera Info Comments
119/5 1 Scene(s): 117 A046 300626 0:34 FrR: 48 WE DO NOT HAVE A
Shot on Day: Day 11 REVERSE SHOT TO
Sticks - cu. H/A CU Emily CUT TO.
41+122A/4 1 Scene(s): 38, 117 A068 060726 0:18
Shot on Day: Day 15
Dolly - cu. MC2s Julian/Emily, slide in
3 0:20
97+121/4 1 Scene(s): 93, 117 A080 090726 0:17 Tail Sticks
Shot on Day: Day 18
"""


class TestCompoundSceneSlates:
    """
    A slate's scene half can be a compound -- 41+122A/4 -- which is how one setup
    covering two scenes is filed. Read as a bare number it matched no header, so
    the row was absorbed into the shot above and handed it a card belonging to a
    different shot.
    """

    def _by_slate(self):
        recs = parse_scripte_detailed_editor_log_text(FACING_PAGE_COMPOUND_SLATES)
        return {(r.slate, r.take_id): r for r in recs}

    def test_a_compound_scene_slate_is_a_slate(self):
        found = self._by_slate()
        assert ("41+122A/4", "1") in found
        assert ("97+121/4", "1") in found

    def test_each_shot_keeps_its_own_card(self):
        found = self._by_slate()
        assert found[("119/5", "1")].camera_roll == "A046"
        assert found[("41+122A/4", "1")].camera_roll == "A068"
        assert found[("97+121/4", "1")].camera_roll == "A080"

    def test_a_shot_does_not_collect_the_cards_of_the_shots_below_it(self):
        """The reported symptom: 119/5 Take 1 claiming A046, A068 and A080."""
        rolls = {r.camera_roll for r in parse_scripte_detailed_editor_log_text(
            FACING_PAGE_COMPOUND_SLATES) if r.slate == "119/5"}
        assert rolls == {"A046"}

    def test_the_scene_is_the_whole_compound(self):
        assert self._by_slate()[("41+122A/4", "1")].scene == "41+122A"

    def test_a_row_whose_slate_cannot_be_read_is_dropped_not_reassigned(self):
        """
        An unplaceable header is worth losing. Attributing its card to whatever
        shot came before it is what turned one take into three conflicting ones.
        """
        text = """
Slate Take Description CR SR Time Camera Info Comments
119/5 1 Scene(s): 117 A046 300626 0:34
??? Scene(s): 93, 117 A080 090726 0:17
"""
        recs = parse_scripte_detailed_editor_log_text(text)
        assert [(r.slate, r.camera_roll) for r in recs] == [("119/5", "A046")]


# --------------------------------------------------------------------------- #
# When a row was actually shot
# --------------------------------------------------------------------------- #

class TestRecordingDate:
    """
    A facing page files a shot under every scene it plays in, so one page for
    scene 117 carries takes from Day 11, Day 15, Day 18 and today. Stamping
    every row with the report's date dated all of them to today.
    """

    def test_a_row_keeps_the_date_written_beside_its_card(self):
        recs = parse_scripte_detailed_editor_log_text(FACING_PAGE_COMPOUND_SLATES)
        dated = {(r.slate, r.camera_roll): r.recording_date for r in recs}
        assert dated[("119/5", "A046")] == "30/06/2026"
        assert dated[("41+122A/4", "A068")] == "06/07/2026"
        assert dated[("97+121/4", "A080")] == "09/07/2026"

    def test_a_row_with_no_date_of_its_own_falls_back_to_the_report(self):
        """The day-of logs write the card without a date column beside it."""
        recs = parse_scripte_tclog_text(SAMPLE_TCLOG_TEXT)
        assert all(r.recording_date == "28/07/2026" for r in recs)

    def test_the_report_date_comes_from_the_document_not_a_constant(self):
        """The fallback is whatever day this report covers, not a fixed day."""
        text = """
DETAILED EDITOR'S LOG 04/09/2026
Slate Take Description CR SR Time Camera Info Comments
27/7 1 Scene(s): 27 Sticks - xwide A120 2:46 1
"""
        recs = parse_scripte_detailed_editor_log_text(text)
        assert recs and all(r.recording_date == "04/09/2026" for r in recs)

    def test_an_undated_document_claims_no_date(self):
        """No date on the row and none in the header is not a reason to invent one."""
        text = """
Slate Take Description CR SR Time Camera Info Comments
27/7 1 Scene(s): 27 Sticks - xwide A120 2:46 1
"""
        recs = parse_scripte_detailed_editor_log_text(text)
        assert recs and all(r.recording_date is None for r in recs)

    @pytest.mark.parametrize("stamp, expected", [
        ("280726", "28/07/2026"), ("300626", "30/06/2026"), ("060726", "06/07/2026"),
        ("091226", "09/12/2026"),
    ])
    def test_a_ddmmyy_stamp_becomes_a_date(self, stamp, expected):
        assert parse_shoot_date(stamp) == expected

    @pytest.mark.parametrize("stamp", ["", None, "2807", "3207 26", "991326", "281326"])
    def test_something_that_is_not_a_date_is_not_read_as_one(self, stamp):
        assert parse_shoot_date(stamp) is None

    def test_a_report_header_date_is_found_and_a_bad_one_is_not(self):
        assert extract_report_date("DAILY TIMECODE LOG 28/07/2026") == "28/07/2026"
        assert extract_report_date("Page: 88 (2 of 2)") is None
        assert extract_report_date("") is None


# --------------------------------------------------------------------------- #
# Which day a take was shot on
# --------------------------------------------------------------------------- #

# Two setups from the facing pages for scene 117, each declaring its own day,
# followed by a setup shot today.
FACING_PAGE_MIXED_DAYS = """
DETAILED EDITOR'S LOG 28/07/2026
Slate Take Description CR SR Time Camera Info Comments
119/5 1 Scene(s): 117 A046 300626 0:34
Shot on Day: Day 11
Sticks - cu. H/A CU Emily
2 A046 0:22
41+122A/4 1 Scene(s): 38, 117 A068 060726 0:18
Shot on Day: Day 15
Dolly - cu. MC2s Julian/Emily
117/1 1 Scene(s): 117 A122 280726 3:39
Shot on Day: Day 31
Dolly - med. Thomas enters LR
"""


class TestShootDayAttribution:
    """
    A facing page is filed per scene across the whole schedule, so one page
    carries takes from several days. Filing them under the day the page was
    uploaded puts a Day 11 take among Day 31 witnesses, where it can only ever
    disagree with them.
    """

    def _rows(self):
        recs = parse_scripte_detailed_editor_log_text(FACING_PAGE_MIXED_DAYS)
        return {(r.slate, r.take_id): r for r in recs}

    def test_a_setup_is_filed_under_the_day_it_declares(self):
        rows = self._rows()
        assert rows[("119/5", "1")].shoot_day == "11"
        assert rows[("41+122A/4", "1")].shoot_day == "15"
        assert rows[("117/1", "1")].shoot_day == "31"

    def test_the_takes_beneath_a_header_share_its_day_and_date(self):
        """Only the header row carries the date column; take 2 is the same setup."""
        take2 = self._rows()[("119/5", "2")]
        assert take2.shoot_day == "11"
        assert take2.recording_date == "30/06/2026"

    def test_a_later_day_line_does_not_reassign_a_settled_setup(self):
        """
        A header this parser cannot read leaves the block open, and the day line
        under it used to reach back and reassign every row since the last header
        -- filing a Day 25 setup under Day 31.
        """
        text = """
DETAILED EDITOR'S LOG 28/07/2026
6/8 1 Scene(s): 6 B031 200726 0:27
Shot on Day: Day 25
S/C - med. MS to WS following
??? Scene(s): 6 B032 280726 0:31
Shot on Day: Day 31
"""
        recs = parse_scripte_detailed_editor_log_text(text)
        assert [(r.slate, r.shoot_day) for r in recs] == [("6/8", "25")]

    def test_a_setup_that_names_no_day_makes_no_claim(self):
        recs = parse_scripte_detailed_editor_log_text(SAMPLE_DETAILED_EDITOR_TEXT)
        assert recs and all(r.shoot_day is None for r in recs)

    def test_the_day_and_the_date_agree(self):
        """
        Two independent columns, read by different rules. Where both are known
        they should never contradict each other.
        """
        rows = self._rows().values()
        pairs = {(r.shoot_day, r.recording_date) for r in rows if r.shoot_day}
        assert pairs == {("11", "30/06/2026"), ("15", "06/07/2026"), ("31", "28/07/2026")}


# --------------------------------------------------------------------------- #
# The layout the application actually parses
# --------------------------------------------------------------------------- #

# extract_text_from_pdf uses pypdf, which lays a facing page out one field per
# line and puts a long slate on a line of its own, with its take number on the
# next. This is the text the upload route feeds the parser -- fixtures written
# in the one-row-per-line shape do not exercise it.
FACING_PAGE_PYPDF_LAYOUT = """
SCRIPT FACING PAGE28/07/2026
LAC - V31
Scene:117
Slate TakeDescription CR SR Time Camera Info Comments
119/5 1*  Scene(s): 117
Shot on Day: Day 11
Sticks - cu. H/A CU Emily
A0463006260:34FrR: 48 WE DO NOT HAVE A
41+122A/4
1 Scene(s): 38, 117
Shot on Day: Day 15
Dolly - cu. MC2s Julian/Emily, slide in
A0680607260:18
97+121/4
1 Scene(s): 93, 117
Shot on Day: Day 18
Sticks - cu. L/A CU Julian RL to Emily
A0800907260:17 Tail Sticks
"""


class TestSplitHeaderLayout:
    """
    A slate alone on a line matched no header, so the setup was missed, the
    previous slate stayed current, and the card below was filed against it.
    """

    def _rows(self):
        recs = parse_scripte_detailed_editor_log_text(FACING_PAGE_PYPDF_LAYOUT)
        return {r.camera_roll: r for r in recs}

    def test_a_slate_on_its_own_line_still_opens_a_setup(self):
        rows = self._rows()
        assert rows["A068"].slate == "41+122A/4"
        assert rows["A080"].slate == "97+121/4"

    def test_the_shot_above_does_not_collect_their_cards(self):
        assert self._rows()["A046"].slate == "119/5"
        assert {r.slate for r in
                parse_scripte_detailed_editor_log_text(FACING_PAGE_PYPDF_LAYOUT)
                if r.camera_roll == "A046"} == {"119/5"}

    def test_each_setup_keeps_its_own_day_and_date(self):
        rows = self._rows()
        assert (rows["A046"].shoot_day, rows["A046"].recording_date) == ("11", "30/06/2026")
        assert (rows["A068"].shoot_day, rows["A068"].recording_date) == ("15", "06/07/2026")
        assert (rows["A080"].shoot_day, rows["A080"].recording_date) == ("18", "09/07/2026")

    def test_a_bare_slate_with_no_take_beneath_it_opens_nothing(self):
        """
        The lined script pages print bare slates over camera labels. Treating
        those as setups would invent takes out of the script's own margin.
        """
        text = FACING_PAGE_PYPDF_LAYOUT + """
117/5
B-wide
119/1
A-wide
41+122A/1
A-wide
"""
        assert len(parse_scripte_detailed_editor_log_text(text)) == len(
            parse_scripte_detailed_editor_log_text(FACING_PAGE_PYPDF_LAYOUT))

    def test_a_wild_track_does_not_steal_the_day_of_the_setup_above_it(self):
        """
        A wild track opens its own setup. Left inside the one above, the day
        line beneath it reached back and refiled that setup's rows.
        """
        text = """
6/8 1*  Scene(s): 6
Shot on Day: Day 25
S/C - med. MS to WS following
B0312007260:27
6WT 1*  Scene(s): 6, 49
Shot on Day: Day 31
Wild Track: 6WT
n/a2807260:29 pasos de Thomas
"""
        recs = parse_scripte_detailed_editor_log_text(text)
        by_slate = {r.slate: r for r in recs}
        assert by_slate["6/8"].shoot_day == "25"
        assert by_slate["6/WT"].shoot_day == "31"
