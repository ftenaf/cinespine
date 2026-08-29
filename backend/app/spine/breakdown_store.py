"""
Durable storage for a scene's shot breakdown.

A breakdown is the multi-camera coverage worked out for one scene: the setups,
each camera's optics and framing, the prompt behind every frame, and the frames
themselves. It is generated once and then worked on -- a focal length nudged, a
camera added, a prompt rewritten and re-rendered -- and all of that lived in the
Script Studio tab's memory, so a reload threw away both the work and the
generations it cost.

Stored whole, one row per scene, rather than a row per shot and another per
camera. The tab already holds it as "the shots for this scene" and edits it as
that; splitting it into three tables would buy a query nobody asks and cost a
transaction on every slider drag.

No trail here, unlike the requirements. A breakdown is a draft being iterated,
not a record of something that happened: the interesting version is the current
one, and keeping every intermediate state of a prompt someone is still writing
would bury it.

Uses the standard library only. The database file is resolved from
CINESPINE_DB_PATH at call time, the same as the other stores.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

DEFAULT_DB_PATH = "spine.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scene_breakdowns (
    script_id    TEXT NOT NULL,
    scene_number TEXT NOT NULL,
    -- The whole shot list as it stands, frames included. Those are data URIs
    -- of images a generation paid for, and dropping them to save space would
    -- lose exactly what a reload used to lose.
    shots        TEXT NOT NULL DEFAULT '[]',
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (script_id, scene_number)
);
"""


class UnknownBreakdownValue(ValueError):
    """A reference that does not name a scene, so the API can say which."""


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


def _key(script_id: str, scene_number: str) -> tuple:
    script = (script_id or "").strip()
    scene = str(scene_number or "").strip().upper()
    if not script:
        raise UnknownBreakdownValue("script_id is required")
    if not scene:
        raise UnknownBreakdownValue("scene_number is required")
    return script, scene


def save(script_id: str, scene_number: str, shots: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Replaces this scene's breakdown with the shot list as it now stands.

    Replacement, not merge: the caller is holding the whole list and has just
    changed part of it, so anything missing from what it sends is something it
    removed.
    """
    script, scene = _key(script_id, scene_number)
    timestamp = _now()

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO scene_breakdowns (script_id, scene_number, shots, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(script_id, scene_number) DO UPDATE SET
                shots=excluded.shots,
                updated_at=excluded.updated_at
            """,
            (script, scene, json.dumps(shots or []), timestamp),
        )

    return {
        "script_id": script,
        "scene_number": scene,
        "shots": shots or [],
        "updated_at": timestamp,
    }


def get(script_id: str, scene_number: str) -> Optional[Dict[str, Any]]:
    script, scene = _key(script_id, scene_number)
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM scene_breakdowns WHERE script_id = ? AND scene_number = ?",
            (script, scene),
        ).fetchone()
    if not row:
        return None
    return {
        "script_id": row["script_id"],
        "scene_number": row["scene_number"],
        "shots": json.loads(row["shots"]),
        "updated_at": row["updated_at"],
    }


def list_for_script(script_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Every scene's breakdown, keyed by scene number.

    The shape the Script Studio holds it in, so restoring is an assignment
    rather than a reduction.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT scene_number, shots FROM scene_breakdowns WHERE script_id = ? "
            "ORDER BY rowid",
            ((script_id or "").strip(),),
        ).fetchall()
    return {r["scene_number"]: json.loads(r["shots"]) for r in rows}


def delete(script_id: str, scene_number: str) -> bool:
    script, scene = _key(script_id, scene_number)
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM scene_breakdowns WHERE script_id = ? AND scene_number = ?",
            (script, scene),
        )
    return cur.rowcount > 0


def delete_for_script(script_id: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM scene_breakdowns WHERE script_id = ?",
            ((script_id or "").strip(),),
        )
    return cur.rowcount
