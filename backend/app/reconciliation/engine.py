"""
3-Axis Discrepancy & Reconciliation Engine.

Evidence:
- references/domain/grain-and-entities.md ('Disagreement is the product')
- references/findings/defects-found.md
- references/constraints/failure-modes.md ('Absence rendered as presence')
"""
from typing import List, Dict, Any
from backend.app.reconciliation.models import Discrepancy, DiscrepancyType, Severity
from backend.app.reconciliation.timecode import calculate_frame_drift


class ReconciliationEngine:
    def __init__(self, max_allowed_tc_drift_frames: int = 1):
        self.max_allowed_tc_drift_frames = max_allowed_tc_drift_frames

    def reconcile_take_witnesses(
        self,
        production_id: str,
        shoot_day: str,
        slate: str,
        take_id: str,
        witnesses: List[Dict[str, Any]],
    ) -> List[Discrepancy]:
        """
        Cross-references multiple department witnesses for a single take.
        """
        discrepancies: List[Discrepancy] = []
        entity_id = f"{slate} Take {take_id}"

        # 1. Check Circled / Starred Take Mismatches
        starred_claims = [
            (w.get("author", "unknown"), w.get("is_starred"))
            for w in witnesses
            if "is_starred" in w and w.get("is_starred") is not None
        ]
        unique_starred_values = set(val for _, val in starred_claims)
        if len(unique_starred_values) > 1:
            desc = (
                f"Conflicting circled/starred status on {entity_id}: "
                + ", ".join(f"{author} says {val}" for author, val in starred_claims)
            )
            discrepancies.append(
                Discrepancy(
                    production_id=production_id,
                    shoot_day=shoot_day,
                    entity_type="take",
                    entity_id=entity_id,
                    discrepancy_type=DiscrepancyType.CIRCLED_TAKE_MISMATCH,
                    severity=Severity.CRITICAL,
                    description=desc,
                    witnesses=witnesses,
                )
            )

        # 2. Check Timecode In / Out Drift
        tc_in_claims = [
            (w.get("author", "unknown"), w.get("timecode_in"))
            for w in witnesses
            if w.get("timecode_in")
        ]
        if len(tc_in_claims) >= 2:
            author1, tc1 = tc_in_claims[0]
            author2, tc2 = tc_in_claims[1]
            drift = calculate_frame_drift(tc1, tc2)
            if drift is not None and drift > self.max_allowed_tc_drift_frames:
                desc = (
                    f"Timecode in drift of {drift} frames on {entity_id} "
                    f"({author1}: {tc1} vs {author2}: {tc2})"
                )
                discrepancies.append(
                    Discrepancy(
                        production_id=production_id,
                        shoot_day=shoot_day,
                        entity_type="take",
                        entity_id=entity_id,
                        discrepancy_type=DiscrepancyType.TIMECODE_DRIFT,
                        severity=Severity.WARNING,
                        description=desc,
                        witnesses=witnesses,
                    )
                )

        return discrepancies

    def reconcile_existence(
        self,
        production_id: str,
        shoot_day: str,
        logged_takes: List[Dict[str, Any]],
        media_files: List[Dict[str, Any]],
        has_offload_report: bool,
    ) -> List[Discrepancy]:
        """
        Reconciles Set belief (logged takes) with Post/DIT existence (media files).
        Gated strictly on whether an offload report exists for the shoot day.
        """
        discrepancies: List[Discrepancy] = []
        media_filenames = set(m.get("file_name") for m in media_files if m.get("file_name"))
        logged_filenames = set(t.get("clip_name") for t in logged_takes if t.get("clip_name"))

        # Case A: Paperwork without media (Only evaluate if offload report has arrived!)
        if has_offload_report:
            for take in logged_takes:
                clip = take.get("clip_name")
                if clip and clip not in media_filenames:
                    slate = take.get("slate", "unknown")
                    take_id = take.get("take_id", "unknown")
                    entity_id = f"{slate} Take {take_id} ({clip})"
                    discrepancies.append(
                        Discrepancy(
                            production_id=production_id,
                            shoot_day=shoot_day,
                            entity_type="take",
                            entity_id=entity_id,
                            discrepancy_type=DiscrepancyType.PAPERWORK_WITHOUT_MEDIA,
                            severity=Severity.CRITICAL,
                            description=f"Clip {clip} logged on set but missing from offload report.",
                            witnesses=[take],
                        )
                    )

            # Case B: Media without paperwork (Orphan media on disk)
            for media in media_files:
                file_name = media.get("file_name")
                if file_name and file_name not in logged_filenames:
                    discrepancies.append(
                        Discrepancy(
                            production_id=production_id,
                            shoot_day=shoot_day,
                            entity_type="media_file",
                            entity_id=file_name,
                            discrepancy_type=DiscrepancyType.MEDIA_WITHOUT_PAPERWORK,
                            severity=Severity.WARNING,
                            description=f"Media file {file_name} exists on volume but is unreferenced in camera/sound logs.",
                            witnesses=[media],
                        )
                    )

        return discrepancies
