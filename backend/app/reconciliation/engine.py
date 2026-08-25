import re
from typing import List, Dict, Any, Optional
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
        Cross-references multiple department witnesses for a single take,
        natively supporting multi-camera setups (Cam A, Cam B, Cam C) and multi-track audio.
        """
        discrepancies: List[Discrepancy] = []
        entity_id = f"{slate} Take {take_id}"

        # 1. Check Circled / Starred Take Mismatches
        # In film production, only the Script Supervisor (Editorial/Continuity) marks takes as circled (⭐) / chosen for the director.
        # Sound reports (ALE/CSV) and Camera logs do not track director's editorial circle choices (or default to unstarred).
        # Therefore, a circled take mismatch only exists if multiple Script Supervisor documents conflict on whether a take is circled.
        starred_by_script_doc: Dict[str, tuple[str, bool]] = {}
        for idx, w in enumerate(witnesses):
            dept = (w.get("department") or w.get("author") or "").lower()
            dtype = str(w.get("doc_type", "")).lower()
            is_script_witness = "script" in dept or "scripte" in dept or "script" in dtype or "scripte" in dtype

            if is_script_witness and "is_starred" in w and w.get("is_starred") is not None:
                doc = w.get("source_document") or w.get("doc_type") or f"Script Doc #{idx+1}"
                val = bool(w.get("is_starred"))
                doc_key = doc
                label = f"Script Supervisor ({doc})" if doc else "Script Supervisor"
                starred_by_script_doc[doc_key] = (label, val)

        unique_starred_values = set(val for _, val in starred_by_script_doc.values())
        if True in unique_starred_values and False in unique_starred_values:
            claims_formatted = [
                f"{label} says {'Circled (⭐)' if val else 'Not Circled'}"
                for label, val in starred_by_script_doc.values()
            ]
            desc = (
                f"Conflicting circled/starred status on {entity_id}: "
                + ", ".join(claims_formatted)
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
                    witnesses=[w for w in witnesses if ("script" in (w.get("department") or w.get("author") or "").lower() or "script" in str(w.get("doc_type", "")).lower())],
                )
            )

        # 2. Check Timecode In / Out Drift between Witnesses
        tc_in_claims = [
            (w.get("author", "unknown"), w.get("timecode_in"), w.get("card_type") or w.get("author"))
            for w in witnesses
            if w.get("timecode_in")
        ]
        if len(tc_in_claims) >= 2:
            author1, tc1, type1 = tc_in_claims[0]
            author2, tc2, type2 = tc_in_claims[1]
            drift = calculate_frame_drift(tc1, tc2)
            # Flag drift if it exceeds allowed threshold and is within typical sync boundary (drift > 240 frames is sound pre-roll)
            if drift is not None and self.max_allowed_tc_drift_frames < drift <= 240:
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

        # 3. Multi-Camera Roll Verification
        # Group camera roll claims by camera unit (e.g. 'A', 'B', 'C')
        # Having A120 for Cam A, B039 for Cam B, C005 for Cam C is VALID multi-camera!
        # A roll mismatch only occurs if two witnesses for the SAME camera unit disagree
        rolls_by_cam: Dict[str, List[tuple]] = {}
        for w in witnesses:
            cr = w.get("camera_roll")
            if not cr or w.get("card_type") == "sound":
                continue
            
            cam_letter = (w.get("camera") or (cr[:1] if cr and cr[0].isalpha() else "A")).upper().strip()
            if cam_letter not in rolls_by_cam:
                rolls_by_cam[cam_letter] = []
            rolls_by_cam[cam_letter].append((w.get("author", "unknown"), cr))

        for cam_letter, claims in rolls_by_cam.items():
            unique_cr = set(r for _, r in claims)
            if len(unique_cr) > 1:
                desc = (
                    f"Camera {cam_letter} roll mismatch on {entity_id}: "
                    + ", ".join(f"{author} says Card {r}" for author, r in claims)
                )
                discrepancies.append(
                    Discrepancy(
                        production_id=production_id,
                        shoot_day=shoot_day,
                        entity_type="take",
                        entity_id=entity_id,
                        discrepancy_type=DiscrepancyType.ROLL_MISMATCH,
                        severity=Severity.CRITICAL,
                        description=desc,
                        witnesses=witnesses,
                    )
                )

        # 4. Sound Roll Verification
        sound_roll_claims = []
        for w in witnesses:
            sr = w.get("sound_roll") or (w.get("reel_tape") if w.get("card_type") == "sound" else None)
            if sr and (w.get("card_type") == "sound" or w.get("author") == "sound"):
                sound_roll_claims.append((w.get("author", "unknown"), sr))

        if len(sound_roll_claims) > 1:
            raw_rolls = set(r for _, r in sound_roll_claims)
            has_sr_date = any(r.startswith("SR") or r.isdigit() for r in raw_rolls)
            has_sd_folder = any("Y" in r and "M" in r for r in raw_rolls)
            if not (has_sr_date and has_sd_folder):
                if len(raw_rolls) > 1:
                    desc = (
                        f"Sound roll mismatch on {entity_id}: "
                        + ", ".join(f"{author} says Sound {r}" for author, r in sound_roll_claims)
                    )
                    discrepancies.append(
                        Discrepancy(
                            production_id=production_id,
                            shoot_day=shoot_day,
                            entity_type="take",
                            entity_id=entity_id,
                            discrepancy_type=DiscrepancyType.ROLL_MISMATCH,
                            severity=Severity.WARNING,
                            description=desc,
                            witnesses=witnesses,
                        )
                    )

        return discrepancies

    def is_clip_matched(self, logged_clip: str, media_files: List[Dict[str, Any]]) -> bool:
        for mf in media_files:
            fn = mf.get("file_name", "")
            if logged_clip == fn:
                return True
            m = re.match(r"^([A-Za-z])(\d{3,4})_C(\d{3,4})", logged_clip)
            if m:
                cam_letter, roll_num, c_num = m.group(1), int(m.group(2)), int(m.group(3))
                pattern = re.compile(rf"{cam_letter}_0*{roll_num}C0*{c_num}(?:[^0-9]|$)", re.IGNORECASE)
                if pattern.search(fn):
                    return True
        return False

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

        if has_offload_report:
            # Case A: Paperwork without media
            for take in logged_takes:
                clip = take.get("clip_name")
                if clip and not self.is_clip_matched(clip, media_files):
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
                file_name = media.get("file_name", "")
                if not file_name:
                    continue

                matched = False
                for take in logged_takes:
                    clip = take.get("clip_name")
                    if clip and self.is_clip_matched(clip, [media]):
                        matched = True
                        break
                    # Also check audio WAV files
                    if file_name.upper().endswith(".WAV"):
                        slate = take.get("slate", "")
                        take_id = str(take.get("take_id", ""))
                        sc = slate.split("/")[0] if "/" in slate else slate
                        sh = slate.split("/")[1] if "/" in slate else None
                        tk_int = int(take_id) if take_id.isdigit() else 0
                        if sh and sh != "WT":
                            pat = rf"^(?:\+)?{re.escape(sc.lstrip('+'))}(?:-|\/)?{re.escape(sh)}T0*{tk_int}\.WAV$"
                        else:
                            pat = rf"^(?:\+)?{re.escape(sc.lstrip('+'))}(?:-|\/)?(?:WTT|-?WTT?|-?T)0*{tk_int}\.WAV$"
                        if re.search(pat, file_name, re.IGNORECASE):
                            matched = True
                            break

                if not matched and not file_name.startswith("."):
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

