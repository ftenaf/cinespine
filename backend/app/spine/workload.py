"""
Production crew workload summaries.

Requirements are already the work ledger: they know who owns a task, what it
targets, whether it is blocked or done, and the requirement_events table records
who moved it and when. This module shapes that ledger into a dashboard answer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.spine import requirement_store
from backend.app.spine.writer import SpineWriter

OPEN_STATUSES = {"open", "in_progress", "blocked"}


def _normalize_handle(handle: Optional[str]) -> str:
    value = (handle or "").strip()
    if not value:
        return "@unassigned"
    return value if value.startswith("@") else f"@{value}"


def _blank_member(handle: str) -> Dict[str, Any]:
    return {
        "handle": handle,
        "name": handle,
        "role": "Unassigned" if handle == "@unassigned" else "External collaborator",
        "department": "general",
        "active": handle != "@unassigned",
        "assigned": 0,
        "open": 0,
        "in_progress": 0,
        "blocked": 0,
        "completed": 0,
        "latest_activity_at": None,
        "latest_activity_actor": None,
        "latest_activity_action": None,
        "current": [],
    }


def crew_workload(spine_writer: SpineWriter, production_id: str) -> Dict[str, Any]:
    """
    Who is carrying what on a production, derived from crew and requirements.

    The shape is intentionally read-model only. Mutations keep going through the
    requirement APIs so the append-only audit trail remains the single account
    of who changed the work.
    """
    members: Dict[str, Dict[str, Any]] = {}
    for crew in spine_writer.list_production_crew(production_id, active_only=False):
        handle = _normalize_handle(crew.get("handle"))
        members[handle] = {
            "handle": handle,
            "name": crew.get("name") or handle,
            "role": crew.get("role") or "",
            "department": crew.get("department") or "general",
            "active": bool(crew.get("active")),
            "assigned": 0,
            "open": 0,
            "in_progress": 0,
            "blocked": 0,
            "completed": 0,
            "latest_activity_at": None,
            "latest_activity_actor": None,
            "latest_activity_action": None,
            "current": [],
        }

    requirements = spine_writer.list_requirements(production_id=production_id)
    latest_events: Dict[str, Dict[str, Any]] = {}
    for event in spine_writer.requirement_history(
        production_id=production_id,
        limit=max(1, min(1000, len(requirements) * 4)),
    ):
        latest_events.setdefault(event["requirement_id"], event)

    for req in requirements:
        handle = _normalize_handle(req.get("assigned_to"))
        member = members.setdefault(handle, _blank_member(handle))
        status = req.get("status") or "open"
        latest_event = latest_events.get(req["requirement_id"])
        latest_action = (latest_event or {}).get("action")
        latest_actor = (
            (latest_event or {}).get("actor")
            or (req.get("resolved_by") if status == "resolved" else None)
            or req.get("created_by")
        )
        latest_at = (
            (latest_event or {}).get("created_at")
            or req.get("resolved_at")
            or req.get("updated_at")
            or req.get("created_at")
        )
        member["assigned"] += 1
        if status in OPEN_STATUSES:
            member[status] += 1
            member["current"].append({
                "requirement_id": req["requirement_id"],
                "title": req["title"],
                "target_type": req["target_type"],
                "target_id": req["target_id"],
                "target_label": req["target_label"],
                "shoot_day": req["shoot_day"],
                "status": status,
                "priority": req["priority"],
                "category": req["category"],
                "updated_at": req["updated_at"],
                "created_by": req["created_by"],
                "created_at": req["created_at"],
                "last_action": latest_action or "created",
                "last_actor": latest_actor,
                "last_activity_at": latest_at,
            })
        elif status == "resolved":
            member["completed"] += 1

        if latest_at and (
            member["latest_activity_at"] is None
            or latest_at > member["latest_activity_at"]
        ):
            member["latest_activity_at"] = latest_at
            member["latest_activity_actor"] = latest_actor
            member["latest_activity_action"] = latest_action or (
                "resolved" if status == "resolved" else "created"
            )

    rows = []
    totals = {
        "crew": 0,
        "assigned": 0,
        "open": 0,
        "in_progress": 0,
        "blocked": 0,
        "completed": 0,
    }
    for member in members.values():
        member["current"].sort(
            key=lambda item: (
                requirement_store.PRIORITIES.index(item["priority"])
                if item["priority"] in requirement_store.PRIORITIES else -1,
                item["last_activity_at"],
            ),
            reverse=True,
        )
        totals["crew"] += 1
        for key in ("assigned", "open", "in_progress", "blocked", "completed"):
            totals[key] += int(member[key])
        rows.append(member)

    rows.sort(
        key=lambda row: (
            -(row["open"] + row["in_progress"] + row["blocked"]),
            row["department"],
            row["handle"].lower(),
        )
    )
    return {
        "total_open": totals["open"] + totals["in_progress"] + totals["blocked"],
        "totals": totals,
        "by_member": rows,
    }
