"""
TDD Test Suite for Slice 3: 3-Axis Discrepancy Reconciliation Engine.

Evidence:
- references/domain/grain-and-entities.md
- references/findings/defects-found.md
- references/constraints/failure-modes.md ('Absence rendered as presence')
"""
import pytest
from backend.app.reconciliation.engine import ReconciliationEngine
from backend.app.reconciliation.models import DiscrepancyType, Severity


class TestReconciliationEngine:
    def setup_method(self):
        self.engine = ReconciliationEngine()

    def test_detect_starred_take_conflict(self):
        # Two script documents conflict on starred status (e.g. Editor's Log starred=True, TC Log starred=False)
        script_doc1 = {"author": "script", "source_document": "DEMO_DetailedEditor'sLog.pdf", "slate": "27/7", "take_id": "3", "is_starred": True}
        script_doc2 = {"author": "script", "source_document": "DEMO_TCLog.pdf", "slate": "27/7", "take_id": "3", "is_starred": False}
        sound_witness = {"author": "sound", "source_document": "SoundReport.csv", "slate": "27/7", "take_id": "3", "is_starred": False}

        discrepancies = self.engine.reconcile_take_witnesses(
            production_id="PROD_01",
            shoot_day="31",
            slate="27/7",
            take_id="3",
            witnesses=[script_doc1, script_doc2, sound_witness],
        )

        assert len(discrepancies) == 1
        d = discrepancies[0]
        assert d.discrepancy_type == DiscrepancyType.CIRCLED_TAKE_MISMATCH
        assert d.severity == Severity.CRITICAL

    def test_sound_or_camera_unstarred_does_not_conflict_with_script(self):
        # Script is sole authority for circled takes; sound default is_starred=False is ignored
        script_witness = {"author": "script", "source_document": "DEMO_TCLog.pdf", "slate": "27/7", "take_id": "3", "is_starred": True}
        sound_witness = {"author": "sound", "source_document": "SoundReport.csv", "slate": "27/7", "take_id": "3", "is_starred": False}
        camera_witness = {"author": "camera", "source_document": "ZoeLog.csv", "slate": "27/7", "take_id": "3", "is_starred": False}

        discrepancies = self.engine.reconcile_take_witnesses(
            production_id="PROD_01",
            shoot_day="31",
            slate="27/7",
            take_id="3",
            witnesses=[script_witness, sound_witness, camera_witness],
        )

        # No circled take mismatch should be generated
        assert not any(d.discrepancy_type == DiscrepancyType.CIRCLED_TAKE_MISMATCH for d in discrepancies)

    def test_detect_timecode_drift(self):
        # 10:14:22:00 vs 10:14:22:05 (5 frame difference @ 24fps)
        script_witness = {
            "author": "script",
            "slate": "27/7",
            "take_id": "1",
            "timecode_in": "10:14:22:00",
            "timecode_out": "10:15:10:00",
        }
        sound_witness = {
            "author": "sound",
            "slate": "27/7",
            "take_id": "1",
            "timecode_in": "10:14:22:05",
            "timecode_out": "10:15:10:05",
        }

        discrepancies = self.engine.reconcile_take_witnesses(
            production_id="PROD_01",
            shoot_day="31",
            slate="27/7",
            take_id="1",
            witnesses=[script_witness, sound_witness],
        )

        assert len(discrepancies) == 1
        d = discrepancies[0]
        assert d.discrepancy_type == DiscrepancyType.TIMECODE_DRIFT
        assert d.severity == Severity.WARNING

    def test_paperwork_without_media_gated_on_offload_report(self):
        """
        Evidence: defects-found.md - False gaps on a production with no offload report.
        Absence of a report was rendered as absence of material.
        """
        logged_take = {"slate": "27/7", "take_id": "1", "clip_name": "A120_C001_260728.MOV"}
        media_files = []  # No media file found

        # Case A: NO offload report uploaded yet -> Must NOT flag missing media (False gap)
        res_no_offload = self.engine.reconcile_existence(
            production_id="PROD_01",
            shoot_day="31",
            logged_takes=[logged_take],
            media_files=media_files,
            has_offload_report=False,
        )
        assert len(res_no_offload) == 0

        # Case B: Offload report present but clip is missing -> REAL MISSING MEDIA
        res_with_offload = self.engine.reconcile_existence(
            production_id="PROD_01",
            shoot_day="31",
            logged_takes=[logged_take],
            media_files=media_files,
            has_offload_report=True,
        )
        assert len(res_with_offload) == 1
        assert res_with_offload[0].discrepancy_type == DiscrepancyType.PAPERWORK_WITHOUT_MEDIA
        assert res_with_offload[0].severity == Severity.CRITICAL

    def test_media_without_paperwork(self):
        # Clip on disk with no paperwork entry
        matched_clip = {"file_name": "A120_C001_260728.MOV", "camera_roll": "A120"}
        orphan_clip = {"file_name": "A120_C999_260728.MOV", "camera_roll": "A120"}
        logged_takes = [{"slate": "27/7", "take_id": "1", "clip_name": "A120_C001_260728.MOV"}]

        discrepancies = self.engine.reconcile_existence(
            production_id="PROD_01",
            shoot_day="31",
            logged_takes=logged_takes,
            media_files=[matched_clip, orphan_clip],
            has_offload_report=True,
        )

        assert len(discrepancies) == 1
        assert discrepancies[0].discrepancy_type == DiscrepancyType.MEDIA_WITHOUT_PAPERWORK
        assert discrepancies[0].severity == Severity.WARNING
        assert discrepancies[0].entity_id == "A120_C999_260728.MOV"

    def test_multi_camera_valid_rolls_no_discrepancy(self):
        """
        Verify that a multi-camera shoot with Cam A on A120, Cam B on B039, Cam C on C005,
        and Sound on 26Y07M27 does NOT trigger false roll mismatches.
        """
        w_cam_a = {"author": "camera", "camera": "A", "camera_roll": "A120", "clip_name": "A120_C001", "is_starred": True}
        w_cam_b = {"author": "camera", "camera": "B", "camera_roll": "B039", "clip_name": "B039_C001", "is_starred": True}
        w_cam_c = {"author": "camera", "camera": "C", "camera_roll": "C005", "clip_name": "C005_C001", "is_starred": True}
        w_script = {"author": "script", "camera_roll": "A120", "sound_roll": "SR280726", "is_starred": True}
        w_sound = {"author": "sound", "sound_roll": "26Y07M27", "card_type": "sound"}

        discrepancies = self.engine.reconcile_take_witnesses(
            production_id="PROD_01",
            shoot_day="31",
            slate="27/7",
            take_id="1",
            witnesses=[w_cam_a, w_cam_b, w_cam_c, w_script, w_sound],
        )
        assert len(discrepancies) == 0

    def test_multi_camera_specific_roll_conflict(self):
        """
        Verify that if ZoeLog Camera A says A120 and Scripte says Camera A was A121,
        a real ROLL_MISMATCH is detected for Camera A.
        """
        w_cam_a = {"author": "camera", "camera": "A", "camera_roll": "A120"}
        w_script_err = {"author": "script", "camera": "A", "camera_roll": "A121"}

        discrepancies = self.engine.reconcile_take_witnesses(
            production_id="PROD_01",
            shoot_day="31",
            slate="27/7",
            take_id="1",
            witnesses=[w_cam_a, w_script_err],
        )
        assert len(discrepancies) == 1
        assert discrepancies[0].discrepancy_type == DiscrepancyType.ROLL_MISMATCH
        assert "Camera A" in discrepancies[0].description

    def test_multi_camera_existence_regex_matching(self):
        """
        Verify that ZoeLog clip 'A120_C001' correctly matches Silverstack file 'A_0120C001_260728_091309_h1EIC.mxf'.
        """
        logged_takes = [
            {"slate": "27/7", "take_id": "1", "clip_name": "A120_C001"},
            {"slate": "27/7", "take_id": "1", "clip_name": "B039_C001"},
            {"slate": "27/7", "take_id": "1", "clip_name": "C005_C001"},
        ]
        media_files = [
            {"file_name": "A_0120C001_260728_091309_h1EIC.mxf"},
            {"file_name": "B_0039C001_260728_091309_h1EIC.mxf"},
            {"file_name": "C_0005C001_260728_091309_h1EIC.mxf"},
            {"file_name": "27-7T01.WAV"},
        ]

        discrepancies = self.engine.reconcile_existence(
            production_id="PROD_01",
            shoot_day="31",
            logged_takes=logged_takes,
            media_files=media_files,
            has_offload_report=True,
        )
        assert len(discrepancies) == 0

