"""
Assistant Editor Queue Agent.

This agent turns clean scene groups into same-day editorial work. It is
deterministic on purpose: the judgement call is not prose, it is whether the
scene has enough paperwork/media evidence and no active blockers.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, cast

from pydantic import BaseModel, Field

from backend.app.core import analytics
from backend.app.spine.writer import SpineWriter

ASSISTANT_QUEUE_ACTOR = "@assistant_queue_agent"
ASSISTANT_QUEUE_MARKER = "AssistantQueueSource:"
ACTIVE_PRODUCTION_STATUSES = {"Active", "In Production", "Principal Photography"}


class AssistantQueueScene(BaseModel):
    scene: str
    shoot_days: List[str]
    target_label: str
    assigned_to: str
    takes_count: int
    circled_takes_count: int
    document_count: int
    clean_score: float
    reasons: List[str] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)


class AssistantQueueAction(BaseModel):
    action: Literal["created", "updated", "unchanged"]
    requirement_id: str
    scene: str
    assigned_to: str
    status: str
    priority: str


class AssistantQueueResult(BaseModel):
    production_id: str
    shoot_day: str
    actor: str
    assigned_to: str
    production_status: str
    scenes: List[AssistantQueueScene]
    requirement_actions: List[AssistantQueueAction]
    summary: str
    generated_at: str


@dataclass
class _SceneEvidence:
    scene: str
    shoot_days: set[str] = field(default_factory=set)
    takes: set[str] = field(default_factory=set)
    circled_takes: set[str] = field(default_factory=set)
    docs: set[str] = field(default_factory=set)
    has_script: bool = False
    has_camera: bool = False
    has_sound: bool = False
    has_existence: bool = False
    has_vfx: bool = False
    has_wild_track: bool = False


def _normalize_handle(handle: Optional[str], fallback: str = "@assistant_editor") -> str:
    value = (handle or fallback).strip()
    if not value:
        value = fallback
    return value if value.startswith("@") else f"@{value}"


def _scene_from_payload(payload: Dict[str, Any]) -> str:
    if payload.get("scene"):
        return str(payload["scene"])
    slate = str(payload.get("slate") or "")
    if "/" in slate:
        return slate.split("/", 1)[0]
    return slate or "UNKNOWN"


def _take_key(payload: Dict[str, Any]) -> Optional[str]:
    slate = payload.get("slate")
    take_id = payload.get("take_id")
    if not slate or not take_id:
        return None
    return f"{slate}_{take_id}"


def _sort_day(day: str) -> tuple[bool, int | str]:
    return (not day.isdigit(), int(day) if day.isdigit() else day)


def _is_editorial_member(member: Dict[str, Any]) -> bool:
    text = f"{member.get('role', '')} {member.get('department', '')}".lower()
    return "editor" in text or member.get("department") == "editorial"


class AssistantEditorQueueAgent:
    def __init__(self, spine_writer: SpineWriter, discrepancy_source: Any):
        self.spine_writer = spine_writer
        self.discrepancy_source = discrepancy_source

    def run(
        self,
        production_id: str,
        shoot_day: Optional[str],
        actor: str = ASSISTANT_QUEUE_ACTOR,
        assignee: Optional[str] = None,
        max_scenes: int = 6,
    ) -> AssistantQueueResult:
        actor = _normalize_handle(actor, ASSISTANT_QUEUE_ACTOR)
        production = self.spine_writer.get_production(production_id)
        if not production:
            raise ValueError(f"No production {production_id}")
        production_id = production["production_id"]
        status = production.get("status") or "Active"
        if status not in ACTIVE_PRODUCTION_STATUSES:
            raise ValueError(
                f"{production_id} is {status}; assistant batches can only be planned while production is active."
            )

        selected_day = shoot_day or self._latest_shoot_day(production_id)
        assigned_to = self._choose_assignee(production_id, actor, assignee)
        candidates = self._candidate_scenes(production_id, selected_day, assigned_to)
        chosen = candidates[:max(1, max_scenes)]
        actions = self._apply_requirements(production_id, selected_day, chosen, actor)
        summary = self._summary(production_id, selected_day, assigned_to, chosen, actions)
        result = AssistantQueueResult(
            production_id=production_id,
            shoot_day=selected_day,
            actor=actor,
            assigned_to=assigned_to,
            production_status=status,
            scenes=chosen,
            requirement_actions=actions,
            summary=summary,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._record_agent_event(result)
        analytics.capture(actor, "assistant_editor_queue_run", {
            "production_id": production_id,
            "shoot_day": selected_day,
            "assigned_to": assigned_to,
            "scenes": len(chosen),
            "requirement_actions": len(actions),
        })
        return result

    def _latest_shoot_day(self, production_id: str) -> str:
        days = sorted(
            {str(e.get("shoot_day")) for e in self.spine_writer.get_events(production_id=production_id)
             if e.get("shoot_day")},
            key=_sort_day,
        )
        return days[-1] if days else "1"

    def _choose_assignee(
        self,
        production_id: str,
        actor: str,
        assignee: Optional[str],
    ) -> str:
        requested = _normalize_handle(assignee or actor, actor)
        if requested.lower() != actor.lower():
            raise ValueError("Assistant editor batches must be assigned to the logged editor.")
        crew = self.spine_writer.list_production_crew(production_id, active_only=True)
        by_handle = {m["handle"].lower(): m for m in crew}
        if requested.lower() in by_handle and _is_editorial_member(by_handle[requested.lower()]):
            return requested

        raise ValueError(
            f"{requested} is not active editorial crew on {production_id}. Add them to the production crew first."
        )

    def _candidate_scenes(
        self,
        production_id: str,
        shoot_day: str,
        assigned_to: str,
    ) -> List[AssistantQueueScene]:
        scenes = self._scene_evidence(production_id, shoot_day)
        discrepancies = self.discrepancy_source.query_production_discrepancies(
            production_id=production_id,
            shoot_day=shoot_day,
        )
        blocked_by_scene = self._blocking_requirements(production_id)
        active_discrepancies = self._active_discrepancies_by_scene(discrepancies)

        candidates: List[AssistantQueueScene] = []
        for scene, evidence in scenes.items():
            blockers = [
                *sorted(active_discrepancies.get(scene, [])),
                *sorted(blocked_by_scene.get(scene, [])),
            ]
            reasons = self._clean_reasons(evidence)
            if blockers or not reasons:
                continue
            candidates.append(AssistantQueueScene(
                scene=scene,
                shoot_days=sorted(evidence.shoot_days, key=_sort_day),
                target_label=f"Scene {scene}",
                assigned_to=assigned_to,
                takes_count=len(evidence.takes),
                circled_takes_count=len(evidence.circled_takes),
                document_count=len(evidence.docs),
                clean_score=self._clean_score(evidence),
                reasons=reasons,
                blockers=[],
            ))

        return sorted(
            candidates,
            key=lambda s: (-s.clean_score, -s.circled_takes_count, -s.takes_count, s.scene),
        )

    def _scene_evidence(self, production_id: str, shoot_day: str) -> Dict[str, _SceneEvidence]:
        scenes: Dict[str, _SceneEvidence] = {}
        for event in self.spine_writer.get_events(production_id=production_id, shoot_day=shoot_day):
            payload = event.get("payload") or {}
            if event.get("entity_type") not in {"take", "media_file"}:
                continue
            scene = _scene_from_payload(payload)
            evidence = scenes.setdefault(scene, _SceneEvidence(scene=scene))
            evidence.shoot_days.add(str(event.get("shoot_day") or shoot_day))
            take_key = _take_key(payload)
            if take_key:
                evidence.takes.add(take_key)
            doc = event.get("metadata", {}).get("filename") or event.get("metadata", {}).get("doc_id")
            if doc:
                evidence.docs.add(str(doc))

            department = str(event.get("department") or "").lower()
            axis = str(event.get("axis") or "").lower()
            if department == "script":
                evidence.has_script = True
            if department == "camera":
                evidence.has_camera = True
            if department == "sound":
                evidence.has_sound = True
            if department == "dit" or axis == "existence" or event.get("entity_type") == "media_file":
                evidence.has_existence = True
            if payload.get("is_starred"):
                if take_key:
                    evidence.circled_takes.add(take_key)
            if payload.get("is_vfx"):
                evidence.has_vfx = True
            if payload.get("is_wild_track"):
                evidence.has_wild_track = True
        return scenes

    def _active_discrepancies_by_scene(
        self, discrepancies: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        grouped: Dict[str, List[str]] = {}
        for discrepancy in discrepancies:
            if discrepancy.get("is_resolved"):
                continue
            entity = str(discrepancy.get("entity_id") or "")
            scene = entity.split("/", 1)[0] if "/" in entity else entity
            if not scene:
                continue
            grouped.setdefault(scene, []).append(
                str(discrepancy.get("description") or discrepancy.get("discrepancy_type") or "Active discrepancy")
            )
        return grouped

    def _blocking_requirements(self, production_id: str) -> Dict[str, List[str]]:
        grouped: Dict[str, List[str]] = {}
        for req in self.spine_writer.list_requirements(production_id=production_id):
            if req.get("status") == "resolved":
                continue
            description = req.get("description") or ""
            if ASSISTANT_QUEUE_MARKER in description:
                continue
            target_type = req.get("target_type")
            target_id = str(req.get("target_id") or "")
            scene = target_id if target_type == "scene" else target_id.split("/", 1)[0]
            if not scene:
                continue
            grouped.setdefault(scene, []).append(req.get("title") or "Outstanding requirement")
        return grouped

    def _clean_reasons(self, evidence: _SceneEvidence) -> List[str]:
        if not evidence.takes:
            return []
        reasons: List[str] = []
        if evidence.has_script:
            reasons.append("script log arrived")
        if evidence.has_camera:
            reasons.append("camera report arrived")
        if evidence.has_sound or evidence.has_wild_track:
            reasons.append("sound paperwork accounted for")
        if evidence.has_existence:
            reasons.append("offload evidence exists")
        if evidence.circled_takes:
            reasons.append("circled takes are identified")
        return reasons if len(reasons) >= 3 and evidence.has_existence else []

    def _clean_score(self, evidence: _SceneEvidence) -> float:
        score = len(evidence.takes) * 4 + len(evidence.docs) * 2
        score += len(evidence.circled_takes) * 18
        if evidence.has_script:
            score += 12
        if evidence.has_camera:
            score += 12
        if evidence.has_sound:
            score += 8
        if evidence.has_existence:
            score += 20
        if evidence.has_vfx:
            score -= 6
        return float(score)

    def _apply_requirements(
        self,
        production_id: str,
        shoot_day: str,
        scenes: List[AssistantQueueScene],
        actor: str,
    ) -> List[AssistantQueueAction]:
        actions: List[AssistantQueueAction] = []
        existing = [
            r for r in self.spine_writer.list_requirements(production_id=production_id)
            if r.get("status") != "resolved"
        ]
        for scene in scenes:
            source = f"{ASSISTANT_QUEUE_MARKER} scene:{scene.scene}:day:{shoot_day}"
            description = self._description(scene, source)
            current = next(
                (r for r in existing if source in (r.get("description") or "")),
                None,
            )
            if current:
                updates = {
                    "assigned_to": scene.assigned_to,
                    "description": description,
                    "target_label": scene.target_label,
                    "priority": "medium",
                    "category": "edit",
                    "status": "open",
                }
                updated = self.spine_writer.update_requirement(
                    current["requirement_id"], updates, actor=actor
                ) or current
                action: Literal["updated", "unchanged"] = "updated" if updated != current else "unchanged"
                if action == "updated" and updated.get("assigned_to") != current.get("assigned_to"):
                    self._notify_assignment(updated, actor)
            else:
                updated = self.spine_writer.create_requirement({
                    "production_id": production_id,
                    "shoot_day": shoot_day,
                    "target_type": "scene",
                    "target_id": scene.scene,
                    "target_label": scene.target_label,
                    "title": f"[Assistant Queue] Finish {scene.target_label} by EOD",
                    "description": description,
                    "priority": "medium",
                    "category": "edit",
                    "created_by": actor,
                    "assigned_to": scene.assigned_to,
                    "status": "open",
                })
                self._append_requirement_event(updated, actor)
                self._notify_assignment(updated, actor)
                existing.append(updated)
                action = "created"
            actions.append(AssistantQueueAction(
                action=cast(Literal["created", "updated", "unchanged"], action),
                requirement_id=updated["requirement_id"],
                scene=scene.scene,
                assigned_to=updated["assigned_to"],
                status=updated["status"],
                priority=updated["priority"],
            ))
        return actions

    def _description(self, scene: AssistantQueueScene, source: str) -> str:
        reasons = "; ".join(scene.reasons)
        days = ", ".join(f"Day {day}" for day in scene.shoot_days)
        return (
            f"{source}\n"
            f"{scene.target_label} is clean enough for assistant editor turnover: {reasons}.\n\n"
            f"Batch scope: {scene.takes_count} take(s), {scene.circled_takes_count} circled, "
            f"{scene.document_count} source document(s), shot on {days}."
        )

    def _append_requirement_event(self, requirement: Dict[str, Any], actor: str) -> None:
        self.spine_writer.append_event({
            "event_id": str(uuid.uuid4()),
            "production_id": requirement["production_id"],
            "shoot_day": requirement["shoot_day"],
            "axis": "intent",
            "department": "editorial",
            "doc_type": "requirement_event",
            "entity_type": "requirement",
            "payload": requirement,
            "metadata": {
                "requirement_id": requirement["requirement_id"],
                "action": "created_by_assistant_queue",
                "assigned_to": requirement["assigned_to"],
                "created_by": actor,
            },
            "timestamp": requirement["created_at"],
        })

    def _notify_assignment(self, requirement: Dict[str, Any], actor: str) -> None:
        if not requirement.get("assigned_to") or requirement["assigned_to"].lower() == actor.lower():
            return
        self.spine_writer.create_notification({
            "production_id": requirement["production_id"],
            "recipient_handle": requirement["assigned_to"],
            "actor_handle": actor,
            "notification_type": "ASSIGNED",
            "requirement_id": requirement["requirement_id"],
            "title": f"Assistant Queue: {requirement['target_label']}",
            "message": f"{actor} assigned an end-of-day scene turnover task.",
            "target_type": requirement["target_type"],
            "target_id": requirement["target_id"],
            "target_label": requirement["target_label"],
        })

    def _record_agent_event(self, result: AssistantQueueResult) -> None:
        self.spine_writer.append_event({
            "event_id": str(uuid.uuid4()),
            "production_id": result.production_id,
            "shoot_day": result.shoot_day,
            "axis": "intent",
            "department": "editorial",
            "doc_type": "agent_run",
            "entity_type": "assistant_editor_queue_run",
            "payload": result.model_dump(),
            "metadata": {
                "actor": result.actor,
                "assigned_to": result.assigned_to,
                "agent": "assistant_editor_queue",
            },
            "timestamp": result.generated_at,
        })
        self.spine_writer.flush_events()

    def _summary(
        self,
        production_id: str,
        shoot_day: str,
        assigned_to: str,
        scenes: List[AssistantQueueScene],
        actions: List[AssistantQueueAction],
    ) -> str:
        if not scenes:
            return f"No clean scenes were ready for {assigned_to} on {production_id} Day {shoot_day}."
        labels = ", ".join(scene.target_label for scene in scenes)
        created = sum(1 for action in actions if action.action == "created")
        updated = sum(1 for action in actions if action.action == "updated")
        return (
            f"{assigned_to} has {len(scenes)} clean scene(s) for end-of-day turnover on "
            f"{production_id} Day {shoot_day}: {labels}. "
            f"{created} requirement(s) created, {updated} updated."
        )
