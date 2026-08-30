"""
ClickHouse Model Context Protocol (MCP) Server & Discrepancy Assistant.

Evidence:
- references/constraints/safety.md ('Read-only analytical query tools')
"""
from typing import Dict, Any, List, Optional
from backend.app.spine.writer import SpineWriter
from backend.app.reconciliation.engine import ReconciliationEngine
from backend.app.normalizers.takes import normalize_take


class ClickHouseMCPServer:
    def __init__(self, spine_writer: SpineWriter, reconciler: ReconciliationEngine):
        self.spine_writer = spine_writer
        self.reconciler = reconciler

    def query_production_discrepancies(self, production_id: str, shoot_day: str) -> List[Dict[str, Any]]:
        """
        MCP Tool: Queries all active discrepancies for a given production and shoot day.
        """
        events = self.spine_writer.get_events(production_id=production_id, shoot_day=shoot_day)
        
        # Group take events by slate and canonical take_id
        takes_map: Dict[str, List[Dict[str, Any]]] = {}
        for evt in events:
            if evt.get("entity_type") == "take":
                payload = evt.get("payload", {})
                slate = payload.get("slate")
                raw_take = payload.get("take_id")
                if slate and raw_take:
                    take_res = normalize_take(raw_take)
                    take_id = take_res.take_id or raw_take
                    key = f"{slate}_{take_id}"
                    if key not in takes_map:
                        takes_map[key] = []
                    witness = dict(payload)
                    dept = evt.get("department", "unknown")
                    fname = evt.get("metadata", {}).get("filename")

                    if dept == "script":
                        author_name = "Script Supervisor"
                    elif dept == "sound":
                        author_name = "Sound Department"
                    elif dept == "camera":
                        cam_letter = (payload.get("raw_payload", {}).get("camera") or payload.get("camera") or (payload.get("camera_roll")[:1] if payload.get("camera_roll") else "A")).upper().replace("_", "")
                        author_name = f"Camera {cam_letter}" if len(cam_letter) == 1 else "Camera Department"
                    elif dept == "dit":
                        author_name = "DIT / Silverstack"
                    else:
                        author_name = dept.capitalize()

                    witness["author"] = author_name
                    witness["department"] = dept
                    witness["doc_type"] = evt.get("doc_type")
                    witness["source_document"] = fname
                    witness["axis"] = evt.get("axis", "belief")
                    takes_map[key].append(witness)

        all_discrepancies = []
        for key, witnesses in takes_map.items():
            slate, take_id = key.split("_", 1)
            discs = self.reconciler.reconcile_take_witnesses(
                production_id=production_id,
                shoot_day=shoot_day,
                slate=slate,
                take_id=take_id,
                witnesses=witnesses,
            )
            for d in discs:
                all_discrepancies.append(d.model_dump())

        # 2. Check Set Belief vs Post/DIT Existence.
        #
        # Called whichever way the gate falls: with an offload report a logged
        # take with no file is a real gap, and without one the day is awaiting
        # offload, which is a different thing that also has to be said. The
        # engine decides which; this used to skip the call entirely when there
        # was no report, so the day rendered as clean.
        #
        # Its results are now used. They were assigned to a local and dropped,
        # so two of the four detections REQ-08 asks for -- paperwork without
        # media, and media without paperwork -- were computed on every request
        # and never reached anybody.
        media_files = [evt.get("payload", {}) for evt in events if evt.get("entity_type") == "media_file"]
        has_offload_report = len(media_files) > 0
        flat_takes = [w for witnesses in takes_map.values() for w in witnesses if w.get("axis") == "belief"]
        for d in self.reconciler.reconcile_existence(
            production_id=production_id,
            shoot_day=shoot_day,
            logged_takes=flat_takes,
            media_files=media_files,
            has_offload_report=has_offload_report,
        ):
            all_discrepancies.append(d.model_dump())
        # 3. Office's plan and belief against what every other department filed.
        #    Scene events come off the DPR; material is anything the other axes
        #    said about a scene, whatever shape it arrived in.
        scene_events = [e for e in events if e.get("entity_type") == "scene"]
        if scene_events:
            scenes_with_material = set()
            for evt in events:
                if evt.get("entity_type") == "scene":
                    continue
                payload = evt.get("payload") or {}
                scene = payload.get("scene")
                if not scene:
                    slate = str(payload.get("slate") or "")
                    scene = slate.split("/")[0] if "/" in slate else (slate or None)
                if scene:
                    scenes_with_material.add(str(scene))

            for d in self.reconciler.reconcile_intent(
                production_id=production_id,
                shoot_day=shoot_day,
                scene_events=scene_events,
                scenes_with_material=scenes_with_material,
            ):
                all_discrepancies.append(d.model_dump())

        # 3b. Office's stated slate ranges against the slates anyone recorded.
        #     The day's own completeness check: nothing else states an expected
        #     extent, so nothing else can notice a slate that should not exist.
        #     Comes off the shoot_day event rather than the scene events, which
        #     is why it is not folded into the block above.
        slate_ranges: List[Dict[str, Any]] = []
        for evt in events:
            if evt.get("entity_type") == "shoot_day":
                slate_ranges.extend((evt.get("payload") or {}).get("slate_ranges") or [])
        if slate_ranges:
            logged_slates = [
                str(w.get("slate")) for witnesses in takes_map.values()
                for w in witnesses if w.get("slate")
            ]
            for d in self.reconciler.reconcile_slate_ranges(
                production_id=production_id,
                shoot_day=shoot_day,
                slate_ranges=slate_ranges,
                logged_slates=logged_slates,
            ):
                all_discrepancies.append(d.model_dump())

        # 4. Apply stored resolutions
        resolutions = self.spine_writer.get_discrepancy_resolutions(production_id=production_id, shoot_day=shoot_day)
        for d in all_discrepancies:
            d_id = d.get("discrepancy_id")
            ent_id = d.get("entity_id")
            ent_k = f"{production_id}_{shoot_day}_{ent_id}"

            res = resolutions.get(d_id) or resolutions.get(ent_k)
            if res:
                d["is_resolved"] = True
                d["resolved_card"] = res.get("resolved_card")
                d["resolution_note"] = res.get("resolution_note")
                d["resolved_at"] = res.get("resolved_at")
                d["resolved_by"] = res.get("resolved_by")

        return all_discrepancies

    def get_take_witnesses(self, production_id: str, shoot_day: str, slate: str, take_id: str) -> List[Dict[str, Any]]:
        """
        MCP Tool: Retrieves all department witness claims for a specific take.
        """
        events = self.spine_writer.get_events(production_id=production_id, shoot_day=shoot_day)
        witnesses = []
        norm_req_take = normalize_take(take_id).take_id or take_id
        for evt in events:
            if evt.get("entity_type") == "take":
                p = evt.get("payload", {})
                p_take = normalize_take(p.get("take_id")).take_id or p.get("take_id")
                if p.get("slate") == slate and p_take == norm_req_take:
                    witnesses.append({
                        "department": evt.get("department"),
                        "axis": evt.get("axis"),
                        "doc_type": evt.get("doc_type"),
                        "payload": p,
                        "timestamp": evt.get("timestamp"),
                    })
        return witnesses


class GeminiDiscrepancyAssistant:
    def __init__(self, mcp_server: ClickHouseMCPServer):
        self.mcp_server = mcp_server

    def explain_take(self, production_id: str, shoot_day: str, slate: str, take_id: str) -> str:
        """
        Generates a plain-English explanation of witness claims and discrepancies for a take.
        """
        witnesses = self.mcp_server.get_take_witnesses(production_id, shoot_day, slate, take_id)
        if not witnesses:
            return f"No records found for {slate} Take {take_id} on Day {shoot_day}."

        lines = [f"### Witness Report for {slate} Take {take_id} (Day {shoot_day}):"]
        for w in witnesses:
            dept = w["department"].capitalize()
            p = w["payload"]
            details = []
            if p.get("camera_roll"):
                details.append(f"Camera Roll: {p['camera_roll']}")
            if p.get("sound_roll"):
                details.append(f"Sound Roll: {p['sound_roll']}")
            if p.get("timecode_in"):
                details.append(f"TC: {p['timecode_in']} - {p.get('timecode_out', '')}")
            if p.get("is_starred"):
                details.append("Circled: YES")

            lines.append(f"- **{dept}** ({w['axis']}): {', '.join(details)}")

        return "\n".join(lines)
