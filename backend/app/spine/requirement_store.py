"""
Durable storage for requirements and how they got where they are.

A requirement is what one department is owed by another: room tone that was
never recorded, a plate that still needs shooting, a cue that is not cleared.
It outlives the day it was raised on -- that is the whole point of raising one
-- so keeping it in process memory meant a restart wiped the production's
outstanding work while the tags and the script link beside it survived.

Two tables, for two different questions:

  requirements        what is owed right now. A handful of mutable rows, read
                      one at a time and as a list per production.
  requirement_events  how it got there. Append-only, written in the same
                      transaction as the change.

The second is the one that was missing entirely. Creating and resolving used to
reach the spine; everything in between -- every handover, every time something
was declared blocked -- was an in-place overwrite, so "who blocked this, and
when" could not be answered five minutes later, let alone after a restart.

The requirement itself is not immutable. Its transitions are, and those are
what this file refuses to lose.

Uses the standard library only. The database file is resolved from
CINESPINE_DB_PATH at call time, the same as the other stores.
"""
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

DEFAULT_DB_PATH = "spine.db"

STATUSES = ("open", "in_progress", "blocked", "resolved")
PRIORITIES = ("low", "medium", "high", "critical")
CATEGORIES = ("sound", "vfx", "edit", "color", "reshoot", "legal", "general")
TARGET_TYPES = ("production", "scene", "shot", "take")

# What the trail can say happened. Named for what a reader wants to find rather
# than for the SQL that did it: "reassigned" and "status_changed" are separate
# from a plain "updated" because those are the two a person goes looking for.
ACTIONS = (
    "created",
    "updated",
    "reassigned",
    "status_changed",
    "resolved",
    "reopened",
    "deleted",
)

# Fields a caller may change after the fact. Not requirement_id, production_id
# or created_at: those identify the requirement rather than describe it.
EDITABLE_FIELDS = (
    "title",
    "description",
    "priority",
    "category",
    "status",
    "assigned_to",
    "target_label",
    "shoot_day",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS requirements (
    requirement_id  TEXT PRIMARY KEY,
    production_id   TEXT NOT NULL,
    shoot_day       TEXT NOT NULL DEFAULT '',
    target_type     TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    target_label    TEXT NOT NULL DEFAULT '',
    title           TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    priority        TEXT NOT NULL DEFAULT 'medium',
    category        TEXT NOT NULL DEFAULT 'general',
    created_by      TEXT NOT NULL DEFAULT '',
    assigned_to     TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'open',
    resolution_note TEXT,
    resolved_by     TEXT,
    resolved_at     TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_requirements_production
    ON requirements (production_id, status, created_at);

-- Every change, kept. The table above is what is owed now; this one is how it
-- came to be owed, which is the question asked when a blocker has been sitting
-- for three weeks and nobody remembers who parked it.
CREATE TABLE IF NOT EXISTS requirement_events (
    event_id       TEXT PRIMARY KEY,
    requirement_id TEXT NOT NULL,
    production_id  TEXT NOT NULL,
    action         TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT '',
    priority       TEXT NOT NULL DEFAULT '',
    assigned_to    TEXT NOT NULL DEFAULT '',
    -- What actually moved, as {field: [before, after]}. The row carries the
    -- state after the change; without this a reader has to diff against the
    -- row below and guess which of the differences the actor intended.
    changes        TEXT NOT NULL DEFAULT '{}',
    note           TEXT,
    actor          TEXT,
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_requirement_events_target
    ON requirement_events (requirement_id, created_at);

CREATE INDEX IF NOT EXISTS ix_requirement_events_production
    ON requirement_events (production_id, created_at);
"""


class UnknownRequirementValue(ValueError):
    """A value outside the vocabulary, named so the API can say which."""


def get_db_path() -> str:
    """Resolved at call time so tests can redirect it via the environment."""
    return os.environ.get("CINESPINE_DB_PATH", DEFAULT_DB_PATH)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(get_db_path(), timeout=10)
    try:
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_handle(raw: Optional[str]) -> str:
    """
    '@ana' however it was typed. Handles arrive from a form, from a seed and
    from an API caller, and two spellings of one person split their workload
    across two names.
    """
    handle = (raw or "").strip()
    if not handle:
        return ""
    return handle if handle.startswith("@") else f"@{handle}"


def _validate(field: str, value: Optional[str], allowed: tuple) -> None:
    if value is not None and value not in allowed:
        raise UnknownRequirementValue(
            f"{field} must be one of {', '.join(allowed)}, got {value!r}"
        )


def _row_to_requirement(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "requirement_id": row["requirement_id"],
        "production_id": row["production_id"],
        "shoot_day": row["shoot_day"],
        "target_type": row["target_type"],
        "target_id": row["target_id"],
        "target_label": row["target_label"],
        "title": row["title"],
        "description": row["description"],
        "priority": row["priority"],
        "category": row["category"],
        "created_by": row["created_by"],
        "assigned_to": row["assigned_to"],
        "status": row["status"],
        "resolution_note": row["resolution_note"],
        "resolved_by": row["resolved_by"],
        "resolved_at": row["resolved_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _append_event(
    conn: sqlite3.Connection,
    record: Dict[str, Any],
    action: str,
    actor: Optional[str],
    changes: Optional[Dict[str, Any]] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Records a change in the same transaction as the change itself.

    Writing the two separately would let a crash between them leave a
    requirement whose history does not explain it -- a gap that looks like a
    record, which is worse than no record at all.
    """
    event = {
        "event_id": f"rev_{uuid.uuid4().hex[:12]}",
        "requirement_id": record["requirement_id"],
        "production_id": record["production_id"],
        "action": action,
        "status": record.get("status") or "",
        "priority": record.get("priority") or "",
        "assigned_to": record.get("assigned_to") or "",
        "changes": changes or {},
        "note": note,
        "actor": normalize_handle(actor),
        "created_at": record.get("updated_at") or _now(),
    }
    conn.execute(
        """
        INSERT INTO requirement_events
            (event_id, requirement_id, production_id, action, status, priority,
             assigned_to, changes, note, actor, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event["event_id"], event["requirement_id"], event["production_id"],
            event["action"], event["status"], event["priority"],
            event["assigned_to"], json.dumps(event["changes"]),
            event["note"], event["actor"], event["created_at"],
        ),
    )
    return event


def create(requirement: Dict[str, Any]) -> Dict[str, Any]:
    """Raises a requirement, and records that it was raised."""
    _validate("status", requirement.get("status"), STATUSES)
    _validate("priority", requirement.get("priority"), PRIORITIES)
    _validate("category", requirement.get("category"), CATEGORIES)
    _validate("target_type", requirement.get("target_type"), TARGET_TYPES)

    timestamp = _now()
    target_type = requirement.get("target_type") or "take"
    target_id = str(requirement.get("target_id") or "")
    record = {
        "requirement_id": requirement.get("requirement_id") or f"req_{uuid.uuid4().hex[:10]}",
        "production_id": requirement.get("production_id") or "DEMO_PRODUCTION",
        "shoot_day": str(requirement.get("shoot_day") or "1"),
        "target_type": target_type,
        "target_id": target_id,
        "target_label": requirement.get("target_label") or f"{target_type.capitalize()} {target_id}",
        "title": requirement.get("title") or "",
        "description": requirement.get("description") or "",
        "priority": requirement.get("priority") or "medium",
        "category": requirement.get("category") or "general",
        "created_by": normalize_handle(requirement.get("created_by") or "@user"),
        "assigned_to": normalize_handle(requirement.get("assigned_to")),
        "status": requirement.get("status") or "open",
        "resolution_note": requirement.get("resolution_note"),
        "resolved_by": requirement.get("resolved_by"),
        "resolved_at": requirement.get("resolved_at"),
        "created_at": requirement.get("created_at") or timestamp,
        "updated_at": timestamp,
    }

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO requirements
                (requirement_id, production_id, shoot_day, target_type, target_id,
                 target_label, title, description, priority, category, created_by,
                 assigned_to, status, resolution_note, resolved_by, resolved_at,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(record[k] for k in (
                "requirement_id", "production_id", "shoot_day", "target_type",
                "target_id", "target_label", "title", "description", "priority",
                "category", "created_by", "assigned_to", "status",
                "resolution_note", "resolved_by", "resolved_at", "created_at",
                "updated_at",
            )),
        )
        event = _append_event(conn, record, "created", record["created_by"])

    record["_event"] = event
    return record


def get(requirement_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM requirements WHERE requirement_id = ?", (requirement_id,)
        ).fetchone()
    return _row_to_requirement(row) if row else None


def list_requirements(
    production_id: Optional[str] = None,
    shoot_day: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    assigned_to: Optional[str] = None,
    created_by: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Newest first, which is the order the boards read them in."""
    sql = "SELECT * FROM requirements WHERE 1=1"
    params: List[Any] = []
    if production_id:
        sql += " AND production_id = ?"
        params.append(production_id)
    if shoot_day:
        sql += " AND shoot_day = ?"
        params.append(str(shoot_day))
    if target_type:
        sql += " AND target_type = ?"
        params.append(target_type)
    if target_id:
        sql += " AND target_id = ?"
        params.append(str(target_id))
    if assigned_to:
        sql += " AND lower(assigned_to) = ?"
        params.append(normalize_handle(assigned_to).lower())
    if created_by:
        sql += " AND lower(created_by) = ?"
        params.append(normalize_handle(created_by).lower())
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY created_at DESC, rowid DESC"

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_requirement(r) for r in rows]


def update(
    requirement_id: str,
    updates: Dict[str, Any],
    actor: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Edits a requirement and records what moved.

    The action is named for the change rather than for the SQL: a handover is
    'reassigned' and a block is 'status_changed', because those are the two a
    person goes looking for. An edit that changes nothing writes no event --
    a trail of saves that did nothing buries the ones that did.
    """
    _validate("status", updates.get("status"), STATUSES)
    _validate("priority", updates.get("priority"), PRIORITIES)
    _validate("category", updates.get("category"), CATEGORIES)

    unknown = set(updates) - set(EDITABLE_FIELDS)
    if unknown:
        raise UnknownRequirementValue(
            f"cannot edit {', '.join(sorted(unknown))}; "
            f"editable fields are {', '.join(EDITABLE_FIELDS)}"
        )

    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM requirements WHERE requirement_id = ?", (requirement_id,)
        ).fetchone()
        if row is None:
            return None

        before = _row_to_requirement(row)
        wanted = dict(updates)
        if "assigned_to" in wanted:
            wanted["assigned_to"] = normalize_handle(wanted["assigned_to"])
        if "shoot_day" in wanted:
            wanted["shoot_day"] = str(wanted["shoot_day"])

        changes = {
            field: [before.get(field), value]
            for field, value in wanted.items()
            if value is not None and before.get(field) != value
        }
        if not changes:
            return before

        # Re-opening takes the resolution with it. A requirement that is open
        # again and still says "@editor resolved this: done" is two claims
        # that cannot both be true, and the board, the crew workload and the
        # analytics all read those columns as "is this done". The account of
        # what was done survives on the resolved event, which is where a trail
        # belongs.
        if "status" in changes and before.get("status") == "resolved" and changes["status"][1] != "resolved":
            for field in ("resolution_note", "resolved_by", "resolved_at"):
                if before.get(field) is not None:
                    changes[field] = [before.get(field), None]

        timestamp = _now()
        after = {**before, **{f: v[1] for f, v in changes.items()}, "updated_at": timestamp}

        assignments = ", ".join(f"{field} = ?" for field in changes)
        conn.execute(
            f"UPDATE requirements SET {assignments}, updated_at = ? WHERE requirement_id = ?",
            (*[v[1] for v in changes.values()], timestamp, requirement_id),
        )

        if "status" in changes:
            action = "reopened" if before["status"] == "resolved" else "status_changed"
        elif "assigned_to" in changes:
            action = "reassigned"
        else:
            action = "updated"

        event = _append_event(conn, after, action, actor, changes=changes)

    after["_event"] = event
    return after


def resolve(
    requirement_id: str,
    resolution_note: str,
    resolved_by: str,
) -> Optional[Dict[str, Any]]:
    """
    Marks a requirement dealt with, keeping the account of how.

    The note is stored on the row and on the event: the row answers "is this
    done", the event answers "what was done", and the second survives the
    requirement being re-opened and resolved again differently.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM requirements WHERE requirement_id = ?", (requirement_id,)
        ).fetchone()
        if row is None:
            return None

        before = _row_to_requirement(row)
        timestamp = _now()
        actor = normalize_handle(resolved_by)
        after = {
            **before,
            "status": "resolved",
            "resolution_note": resolution_note,
            "resolved_by": actor,
            "resolved_at": timestamp,
            "updated_at": timestamp,
        }

        conn.execute(
            "UPDATE requirements SET status = 'resolved', resolution_note = ?, "
            "resolved_by = ?, resolved_at = ?, updated_at = ? WHERE requirement_id = ?",
            (resolution_note, actor, timestamp, timestamp, requirement_id),
        )
        event = _append_event(
            conn, after, "resolved", actor,
            changes={"status": [before["status"], "resolved"]},
            note=resolution_note,
        )

    after["_event"] = event
    return after


def delete(requirement_id: str, actor: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Removes a requirement, and keeps the fact that it was removed.

    The row goes; the trail does not. A requirement that was raised and then
    deleted is a thing that happened, and a board that can make work disappear
    without trace is a board nobody can audit.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM requirements WHERE requirement_id = ?", (requirement_id,)
        ).fetchone()
        if row is None:
            return None

        record = _row_to_requirement(row)
        record["updated_at"] = _now()
        event = _append_event(conn, record, "deleted", actor)
        conn.execute("DELETE FROM requirements WHERE requirement_id = ?", (requirement_id,))

    record["_event"] = event
    return record


def _row_to_event(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "event_id": row["event_id"],
        "requirement_id": row["requirement_id"],
        "production_id": row["production_id"],
        "action": row["action"],
        "status": row["status"],
        "priority": row["priority"],
        "assigned_to": row["assigned_to"],
        "changes": json.loads(row["changes"]),
        "note": row["note"],
        "actor": row["actor"],
        "created_at": row["created_at"],
    }


def history(
    requirement_id: Optional[str] = None,
    production_id: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    What happened, newest first, to one requirement or across a production.

    Narrowing to one requirement is the common read -- "who blocked this, and
    when" -- and the production-wide read is what a board shows as activity.
    """
    if not requirement_id and not production_id:
        raise UnknownRequirementValue("requirement_id or production_id is required")

    sql = "SELECT * FROM requirement_events WHERE 1=1"
    params: List[Any] = []
    if requirement_id:
        sql += " AND requirement_id = ?"
        params.append(requirement_id)
    if production_id:
        sql += " AND production_id = ?"
        params.append(production_id)
    sql += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
    params.append(max(1, min(limit, 1000)))

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_event(r) for r in rows]
