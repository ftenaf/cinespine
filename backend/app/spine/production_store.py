"""
Durable storage for the production registry.

A production used to exist only in the writer's memory, which was fine while
the only way to get one was to be one of the three built-in demos. It stopped
being fine once productions became something a user creates: registering one,
restarting the backend, and finding it gone is not a registry.

It also left the app inconsistent with itself. Editorial tags and the script
link are both keyed by production id and both persisted, so a restart could
leave tags and a linked screenplay hanging off a production that no longer
appeared anywhere.

The events, takes and documents of a production still live in memory and still
go when the process does. What survives here is the production's identity and
the metadata somebody typed.

Uses the standard library only. The database file is resolved from
CINESPINE_DB_PATH at call time, the same as the other stores.
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

DEFAULT_DB_PATH = "spine.db"

# How a production came to exist. A production somebody filled a form in for
# and one conjured out of a filename during an ingest are not the same thing,
# and the difference is worth keeping: a typo in a filename should be
# recognisable as such rather than sitting in the list looking deliberate.
ORIGINS = ("registered", "auto")

# What a production may be called at each stage. Free text would make the list
# unsortable and the same state spelled three ways.
STATUSES = ("Active", "In Production", "Principal Photography", "Wrapped", "Archived")

# Fields a user may edit after the fact. production_id is not among them: it is
# the key every event, tag and script link is filed under, and renaming it
# would orphan all of them.
EDITABLE_FIELDS = ("name", "director", "status", "description")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS productions (
    production_id TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    director      TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'Active',
    description   TEXT NOT NULL DEFAULT '',
    origin        TEXT NOT NULL DEFAULT 'registered',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
"""


class UnknownProductionField(ValueError):
    """A value the registry does not accept, named so the API can say which."""


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


def normalize_production_id(raw: str) -> str:
    """
    The form a production id is stored and looked up in.

    Upper case with underscores for spaces, because it is typed by hand in one
    place and read out of filenames in another, and 'Night Watch' arriving as
    NIGHT_WATCH from an ingest must land on the same production as the one
    somebody registered.
    """
    cleaned = "_".join((raw or "").strip().upper().split())
    if not cleaned:
        raise UnknownProductionField("production_id is required")
    return cleaned


def upsert(
    production_id: str,
    name: str,
    director: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    origin: str = "registered",
) -> Dict[str, Any]:
    """
    Registers a production, or refreshes the one already under that id.

    An id first seen during an ingest and registered properly later keeps its
    original creation time but stops being marked auto: somebody has now said
    what it is.
    """
    key = normalize_production_id(production_id)
    if origin not in ORIGINS:
        raise UnknownProductionField(f"origin must be one of {', '.join(ORIGINS)}")
    if status is not None and status not in STATUSES:
        raise UnknownProductionField(
            f"status must be one of {', '.join(STATUSES)}, got {status!r}"
        )

    timestamp = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO productions
                (production_id, name, director, status, description, origin,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(production_id) DO UPDATE SET
                name=excluded.name,
                director=excluded.director,
                status=excluded.status,
                description=excluded.description,
                -- A production only ever moves from auto to registered, never
                -- back: a later ingest must not undo what a person typed.
                origin=CASE WHEN productions.origin = 'registered'
                            THEN 'registered' ELSE excluded.origin END,
                updated_at=excluded.updated_at
            """,
            (
                key,
                name or key.replace("_", " ").title(),
                director or "",
                status or "Active",
                description or "",
                origin,
                timestamp,
                timestamp,
            ),
        )
    return get(key)  # type: ignore[return-value]


def register_if_absent(production_id: str, origin: str = "auto") -> Dict[str, Any]:
    """
    Records a production seen for the first time, leaving an existing one alone.

    Used by the ingest path, where the production id comes off a filename. It
    must never overwrite what somebody has already filled in about a production
    just because another document arrived for it.
    """
    key = normalize_production_id(production_id)
    existing = get(key)
    if existing:
        return existing
    return upsert(
        production_id=key,
        name=key.replace("_", " ").title(),
        director="",
        description="",
        origin=origin,
    )


def get(production_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM productions WHERE production_id = ?",
            (normalize_production_id(production_id),),
        ).fetchone()
    return dict(row) if row else None


def list_all() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM productions ORDER BY created_at, production_id"
        ).fetchall()
    return [dict(r) for r in rows]


def update(production_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Edits a production's metadata, or returns None when there is no such
    production, so the caller answers 404 rather than reporting a success that
    never happened.
    """
    key = normalize_production_id(production_id)
    existing = get(key)
    if not existing:
        return None

    changes = {f: updates[f] for f in EDITABLE_FIELDS if updates.get(f) is not None}
    unknown = set(updates) - set(EDITABLE_FIELDS)
    if unknown:
        raise UnknownProductionField(
            f"cannot edit {', '.join(sorted(unknown))}; "
            f"editable fields are {', '.join(EDITABLE_FIELDS)}"
        )
    if "status" in changes and changes["status"] not in STATUSES:
        raise UnknownProductionField(
            f"status must be one of {', '.join(STATUSES)}, got {changes['status']!r}"
        )
    if not changes:
        return existing

    assignments = ", ".join(f"{field} = ?" for field in changes)
    with _connect() as conn:
        conn.execute(
            f"UPDATE productions SET {assignments}, updated_at = ? WHERE production_id = ?",
            (*changes.values(), _now(), key),
        )
    return get(key)


def delete(production_id: str) -> bool:
    """
    Removes a production from the registry.

    Whether it is safe to remove is not decided here -- this store cannot see
    the events or tags filed under it. The caller checks that first; see the
    productions API.
    """
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM productions WHERE production_id = ?",
            (normalize_production_id(production_id),),
        )
    return cur.rowcount > 0
