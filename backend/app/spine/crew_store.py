"""
Production crew roster storage.

Global users answer "who can log in"; this table answers "who is on this
production and can own work here". The two deliberately overlap but are not the
same, because a person can exist in CineSpine without being crewed on every
show.
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from backend.app.spine.event_store import DEFAULT_DB_PATH
from backend.app.spine.requirement_store import normalize_handle

DEPARTMENTS = ("editorial", "camera", "sound", "dit", "vfx", "production", "general")

EDITABLE_FIELDS = ("name", "email", "role", "department", "active")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS production_crew (
    production_id TEXT NOT NULL,
    handle        TEXT NOT NULL,
    name          TEXT NOT NULL DEFAULT '',
    email         TEXT NOT NULL DEFAULT '',
    role          TEXT NOT NULL DEFAULT '',
    department    TEXT NOT NULL DEFAULT 'general',
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (production_id, handle)
);

CREATE INDEX IF NOT EXISTS ix_production_crew_production
    ON production_crew (production_id, active, department, handle);
"""


class UnknownCrewValue(ValueError):
    """A roster field value the store refuses to persist."""


def get_db_path() -> str:
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


def _department(value: Optional[str]) -> str:
    normalized = (value or "general").strip().lower().replace(" ", "_")
    if normalized not in DEPARTMENTS:
        raise UnknownCrewValue(
            f"department must be one of {', '.join(DEPARTMENTS)}, got {value!r}"
        )
    return normalized


def _row(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "production_id": row["production_id"],
        "handle": row["handle"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "department": row["department"],
        "active": bool(row["active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def upsert(member: Dict[str, Any]) -> Dict[str, Any]:
    production_id = str(member.get("production_id") or "").strip()
    if not production_id:
        raise UnknownCrewValue("production_id is required")
    handle = normalize_handle(member.get("handle"))
    if not handle:
        raise UnknownCrewValue("handle is required")

    timestamp = _now()
    record = {
        "production_id": production_id,
        "handle": handle,
        "name": (member.get("name") or handle.lstrip("@").replace("_", " ").title()).strip(),
        "email": (member.get("email") or "").strip().lower(),
        "role": (member.get("role") or "Crew").strip(),
        "department": _department(member.get("department")),
        "active": 1 if member.get("active", True) else 0,
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO production_crew
                (production_id, handle, name, email, role, department, active,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(production_id, handle) DO UPDATE SET
                name=excluded.name, email=excluded.email, role=excluded.role,
                department=excluded.department, active=excluded.active,
                updated_at=excluded.updated_at
            """,
            (
                record["production_id"], record["handle"], record["name"], record["email"],
                record["role"], record["department"], record["active"], record["created_at"],
                record["updated_at"],
            ),
        )
    stored = get(production_id, handle)
    if stored is None:
        raise UnknownCrewValue(f"crew member {handle} was not stored")
    return stored


def get(production_id: str, handle: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM production_crew WHERE production_id = ? AND lower(handle) = ?",
            (production_id, normalize_handle(handle).lower()),
        ).fetchone()
    return _row(row) if row else None


def list_for(production_id: str, active_only: bool = False) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM production_crew WHERE production_id = ?"
    params: List[Any] = [production_id]
    if active_only:
        sql += " AND active = 1"
    sql += " ORDER BY active DESC, department, handle"
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row(r) for r in rows]


def update(production_id: str, handle: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    current = get(production_id, handle)
    if not current:
        return None
    unknown = set(updates) - set(EDITABLE_FIELDS)
    if unknown:
        raise UnknownCrewValue(
            f"cannot edit {', '.join(sorted(unknown))}; editable fields are {', '.join(EDITABLE_FIELDS)}"
        )

    changes = {field: updates[field] for field in EDITABLE_FIELDS if field in updates}
    if "department" in changes:
        changes["department"] = _department(changes["department"])
    if "active" in changes:
        changes["active"] = 1 if changes["active"] else 0
    if not changes:
        return current

    assignments = ", ".join(f"{field} = ?" for field in changes)
    with _connect() as conn:
        conn.execute(
            f"UPDATE production_crew SET {assignments}, updated_at = ? "
            "WHERE production_id = ? AND lower(handle) = ?",
            (*changes.values(), _now(), production_id, normalize_handle(handle).lower()),
        )
    return get(production_id, handle)


def delete(production_id: str, handle: str) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM production_crew WHERE production_id = ? AND lower(handle) = ?",
            (production_id, normalize_handle(handle).lower()),
        )
    return cur.rowcount > 0
