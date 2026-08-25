"""
ClickHouse Model Context Protocol (MCP) Server & Discrepancy Assistant.

Evidence:
- references/constraints/safety.md ('Read-only analytical query tools')
"""
from typing import Dict, Any, List, Optional
from backend.app.spine.writer import SpineWriter
from backend.app.reconciliation.engine import ReconciliationEngine


class ClickHouseMCPServer:
    def __init__(self, spine_writer: SpineWriter, reconciler: ReconciliationEngine):
        self.spine_writer = spine_writer
        self.reconciler = reconciler

    def query_production_discrepancies(self, production_id: str, shoot_day: str) -> List[Dict[str, Any]]:
        """
        MCP Tool: Queries all active discrepancies for a given production and shoot day.
        """
        events = self.spine_writer.get_events(production_id=production_id, shoot_day=shoot_day)
        
        # Group take events by slate and take_id
        takes_map: Dict[str, List[Dict[str, Any]]] = {}
        for evt in events:
            if evt.get("entity_type") == "take":
                payload = evt.get("payload", {})
                slate = payload.get("slate")
                take_id = payload.get("take_id")
                if slate and take_id:
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

        # 2. Check Set Belief vs Post/DIT Existence
        media_files = [evt.get("payload", {}) for evt in events if evt.get("entity_type") == "media_file"]
        has_offload_report = len(media_files) > 0
        if has_offload_report:
            flat_takes = [w for witnesses in takes_map.values() for w in witnesses if w.get("axis") == "belief"]
            exist_discs = self.reconciler.reconcile_existence(
                production_id=production_id,
                shoot_day=shoot_day,
                logged_takes=flat_takes,
                media_files=media_files,
                has_offload_report=has_offload_report,
            )
        # 3. Apply stored resolutions
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
        for evt in events:
            if evt.get("entity_type") == "take":
                p = evt.get("payload", {})
                if p.get("slate") == slate and p.get("take_id") == take_id:
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
