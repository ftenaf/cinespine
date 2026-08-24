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
        # Script marked starred=True, Camera marked starred=False
        script_witness = {"author": "script", "slate": "27/7", "take_id": "3", "is_starred": True}
        camera_witness = {"author": "camera", "slate": "27/7", "take_id": "3", "is_starred": False}

        discrepancies = self.engine.reconcile_take_witnesses(
            production_id="PROD_01",
            shoot_day="31",
            slate="27/7",
            take_id="3",
            witnesses=[script_witness, camera_witness],
        )

        assert len(discrepancies) == 1
        d = discrepancies[0]
        assert d.discrepancy_type == DiscrepancyType.CIRCLED_TAKE_MISMATCH
        assert d.severity == Severity.CRITICAL

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
