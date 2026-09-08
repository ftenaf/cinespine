"""
One production, five questions: what is done, what is running, what is
blocking, what is left, what is missing.

Built for a browser agent asking on somebody's behalf, so it is one call and
the answer is ranked rather than exhaustive: every item carries a severity and
an age, and each bucket is sorted by severity first, then by how long it has
been sitting. The oldest critical thing is at the top of "blocking"; that is
the sentence the producer wants.

Where the facts come from, and what each bucket means:

  done      resolved requirements and resolved discrepancies
  running   requirements somebody has picked up (in_progress)
  blocking  blocked requirements, and unresolved discrepancies the reconciler
            found across every shoot day
  left      open requirements nobody has started, shots and scenes flagged as
            owing work by the editorial tags, and the count of shots nobody
            has tagged at all
  missing   paperwork that should exist and does not: a department that filed
            on other days of this production but not on this one, a
            production with no crew, no linked screenplay, or no events

"Missing" is inference, and the items say so. A department absent on one day
is a gap only if it filed on another; a production with sound paperwork on no
day at all may simply not record sound. The heuristic is named in the detail
so the reader can disagree with it.

Severity is `critical > high > medium > low`. Requirements carry their own
priority; a discrepancy maps its reconciler severity; the rest are fixed per
kind and documented at the constant.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from backend.app.spine import tag_store

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}
BUCKETS = ("done", "running", "blocking", "left", "missing")

# Fixed severities for items that do not carry their own.
SEVERITY_MISSING_PAPERWORK = "high"     # a day the reconciler cannot cross-check
SEVERITY_NO_CREW = "medium"             # nothing can be assigned to anybody
SEVERITY_NO_SCRIPT = "medium"           # the studio and scene lookups have no text
SEVERITY_NO_EVENTS = "high"             # the spine knows nothing about this production
SEVERITY_OUTSTANDING_TAG = "medium"     # an editor said this owes work
SEVERITY_UNTAGGED = "low"               # nobody has looked; volume, not urgency

# Spine events that record what people did to the tool, not paperwork about
# the shoot. Excluded when asking whether any paperwork exists.
AUDIT_DOC_TYPES = frozenset({"requirement_event", "production_crew_event", "discrepancy_resolution"})

# Every department seen anywhere in the spine for this production counts as
# expected on every shoot day. Named so the heuristic can be tightened later.
EXPECTED_DEPARTMENTS_RULE = "departments that filed on any other shoot day of this production"


def _parse(ts: Any) -> Optional[datetime]:
    if not ts:
        return None
    try:
        value = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _age_hours(since: Optional[datetime], now: datetime) -> Optional[float]:
    if since is None:
        return None
    return round(max(0.0, (now - since).total_seconds()) / 3600, 1)


def _severity(value: Any, default: str = "medium") -> str:
    key = str(value or "").strip().lower()
    return key if key in SEVERITY_RANK else default


def _item(
    bucket: str, kind: str, item_id: str, title: str, severity: str,
    since: Optional[datetime], now: datetime, **extra: Any,
) -> Dict[str, Any]:
    return {
        "bucket": bucket,
        "kind": kind,
        "id": item_id,
        "title": title,
        "severity": severity,
        "since": since.isoformat() if since else None,
        "age_hours": _age_hours(since, now),
        **extra,
    }


def _sort_key(item: Dict[str, Any]):
    # Severity first, then the oldest. An item with no age sorts after dated
    # ones of the same severity: unknown age is not evidence of urgency.
    age = item.get("age_hours")
    return (-SEVERITY_RANK.get(item["severity"], 0), -(age if age is not None else -1))


def _shoot_days(events: Iterable[Dict[str, Any]]) -> List[str]:
    days = {str(e.get("shoot_day")) for e in events if e.get("shoot_day")}
    return sorted(days, key=lambda d: (not d.isdigit(), int(d) if d.isdigit() else d))


def production_status(spine_writer: Any, mcp_server: Any, production_id: str, *, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    items: List[Dict[str, Any]] = []

    # ---------------------------------------------------------------- requirements
    for req in spine_writer.list_requirements(production_id=production_id):
        status = req.get("status") or "open"
        bucket = {"resolved": "done", "in_progress": "running", "blocked": "blocking"}.get(status, "left")
        since = _parse(req.get("resolved_at") if status == "resolved" else req.get("created_at"))
        items.append(_item(
            bucket, "requirement", req["requirement_id"], req.get("title") or req["requirement_id"],
            _severity(req.get("priority")), since, now,
            status=status, shoot_day=req.get("shoot_day"), target=req.get("target_label"),
            owner=req.get("assigned_to"), category=req.get("category"),
            detail=(f"resolved by {req.get('resolved_by')}" if status == "resolved"
                    else f"{status.replace('_', ' ')}, assigned to {req.get('assigned_to') or 'nobody'}"),
        ))

    # ---------------------------------------------------------------- spine facts
    # Paperwork only. Requirements, crew changes and resolutions are appended
    # to the spine as audit events too; a production that has those and no
    # camera, sound or script paperwork still has nothing to reconcile.
    events = [
        e for e in spine_writer.get_events(production_id=production_id)
        if str(e.get("doc_type") or "") not in AUDIT_DOC_TYPES
    ]
    days = _shoot_days(events)
    if not events:
        items.append(_item(
            "missing", "spine", f"{production_id}:events", "No paperwork in the spine",
            SEVERITY_NO_EVENTS, None, now,
            detail="No events at all for this production; nothing below can be cross-checked.",
        ))

    # ---------------------------------------------------------------- discrepancies
    for day in days:
        try:
            found = mcp_server.query_production_discrepancies(production_id=production_id, shoot_day=day)
        except Exception as exc:  # noqa: BLE001 - one day's failure must not empty the whole answer
            items.append(_item(
                "missing", "reconciler", f"{production_id}:{day}:reconcile", f"Day {day} could not be reconciled",
                "medium", None, now, shoot_day=day, detail=str(exc)[:200],
            ))
            continue
        latest = max((_parse(e.get("timestamp")) for e in events if str(e.get("shoot_day")) == day), default=None, key=lambda d: d or datetime.min.replace(tzinfo=timezone.utc))
        for d in found:
            resolved = bool(d.get("is_resolved"))
            since = _parse(d.get("resolved_at")) if resolved else (_parse(d.get("detected_at")) or latest)
            items.append(_item(
                "done" if resolved else "blocking", "discrepancy",
                str(d.get("discrepancy_id") or f"{day}:{d.get('entity_id')}"),
                str(d.get("description") or d.get("discrepancy_type") or "Discrepancy"),
                _severity(d.get("severity"), default="high"), since, now,
                shoot_day=day, target=d.get("entity_id"), discrepancy_type=d.get("discrepancy_type"),
                detail=("resolved" if resolved else "unresolved; the reconciler still sees the disagreement"),
            ))

    # ---------------------------------------------------------------- editorial tags
    known_shots, known_scenes = set(), set()
    for event in events:
        if event.get("entity_type") != "take":
            continue
        payload = event.get("payload") or {}
        slate = payload.get("slate")
        if slate:
            known_shots.add(str(slate))
            known_scenes.add(str(slate).split("/")[0])
        if payload.get("scene"):
            known_scenes.add(str(payload["scene"]))
    progress = tag_store.progress(production_id, sorted(known_shots), sorted(known_scenes))
    for need, targets in (progress.get("outstanding") or {}).items():
        for t in targets:
            items.append(_item(
                "left", "editorial_need", f"{t['target_type']}:{t['target_id']}:{need}",
                f"{'Scene' if t['target_type'] == 'scene' else 'Shot'} {t['target_id']} needs {need.replace('_', ' ')}",
                SEVERITY_OUTSTANDING_TAG, None, now,
                target=t["target_id"], target_type=t["target_type"], need=need, status=t.get("status"),
                detail="flagged by an editor on the tag",
            ))
    untagged = int((progress.get("shots") or {}).get("no_status") or 0)
    if untagged:
        items.append(_item(
            "left", "untagged_shots", f"{production_id}:untagged", f"{untagged} shot{'s' if untagged != 1 else ''} nobody has tagged",
            SEVERITY_UNTAGGED, None, now, count=untagged,
            detail="in the spine, no editorial status yet; volume, not urgency",
        ))

    # ---------------------------------------------------------------- missing paperwork
    by_day: Dict[str, set] = {}
    for e in events:
        day, dept = str(e.get("shoot_day") or ""), str(e.get("department") or "")
        if day and dept:
            by_day.setdefault(day, set()).add(dept)
    expected = set().union(*by_day.values()) if by_day else set()
    for day in days:
        for dept in sorted(expected - by_day.get(day, set())):
            latest = max((_parse(e.get("timestamp")) for e in events if str(e.get("shoot_day")) == day), default=None, key=lambda d: d or datetime.min.replace(tzinfo=timezone.utc))
            items.append(_item(
                "missing", "paperwork", f"{day}:{dept}", f"No {dept} paperwork for day {day}",
                SEVERITY_MISSING_PAPERWORK, latest, now, shoot_day=day, department=dept,
                detail=f"inferred: {EXPECTED_DEPARTMENTS_RULE}",
            ))

    # ---------------------------------------------------------------- setup gaps
    if not spine_writer.list_production_crew(production_id, active_only=True):
        items.append(_item("missing", "crew", f"{production_id}:crew", "No active crew on this production",
                           SEVERITY_NO_CREW, None, now, detail="requirements cannot be assigned to anybody"))
    if not spine_writer.get_production_script(production_id):
        items.append(_item("missing", "script", f"{production_id}:script", "No screenplay linked",
                           SEVERITY_NO_SCRIPT, None, now, detail="scene lookups and the studio have no text for this production"))

    # ---------------------------------------------------------------- shape
    buckets: Dict[str, List[Dict[str, Any]]] = {b: [] for b in BUCKETS}
    for item in items:
        buckets[item["bucket"]].append(item)
    for b in BUCKETS:
        buckets[b].sort(key=_sort_key)
    counts = {b: len(buckets[b]) for b in BUCKETS}
    urgent = sorted(buckets["blocking"] + buckets["missing"], key=_sort_key)[:5]
    return {
        "production_id": production_id,
        "generated_at": now.isoformat(),
        "shoot_days": days,
        "counts": counts,
        "headline": _headline(counts, urgent),
        "urgent": urgent,
        **buckets,
    }


def _headline(counts: Dict[str, int], urgent: List[Dict[str, Any]]) -> str:
    parts = [f"{counts['done']} done", f"{counts['running']} running", f"{counts['blocking']} blocking",
             f"{counts['left']} left", f"{counts['missing']} missing"]
    line = ", ".join(parts) + "."
    if urgent:
        top = urgent[0]
        age = f" for {top['age_hours']:.0f}h" if top.get("age_hours") is not None else ""
        line += f" Most urgent: {top['title']} ({top['severity']}{age})."
    return line
