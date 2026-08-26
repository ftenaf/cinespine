"""
Durable storage for screenplays and their character profiles.

Character profiles are the one part of the Script Studio the user authors by
hand: they polish a character's look, wardrobe and personality so every
generated frame renders the same person. That work has to outlive a backend
restart, so it is kept in SQLite rather than in process memory.

Uses the standard library only. The database file is resolved from
CINESPINE_DB_PATH at call time (default: spine.db in the working directory), so
tests can point it at a temporary file.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

DEFAULT_DB_PATH = "spine.db"

# Fields the user owns once they have edited a character. Re-parsing the same
# screenplay refreshes structural data but must never clobber these.
USER_OWNED_CHARACTER_FIELDS = (
    "role",
    "actor_reference",
    "look_and_costume",
    "facial_features",
    "personality_traits",
    "avatar_url",
    "portrait_prompt",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS screenplays (
    script_id  TEXT PRIMARY KEY,
    title      TEXT,
    author     TEXT,
    filename   TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS character_profiles (
    script_id    TEXT NOT NULL,
    character_id TEXT NOT NULL,
    ordinal      INTEGER NOT NULL DEFAULT 0,
    edited       INTEGER NOT NULL DEFAULT 0,
    data         TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (script_id, character_id)
);
"""


def get_db_path() -> str:
    """Resolved at call time so tests can redirect it via the environment."""
    return os.environ.get("CINESPINE_DB_PATH", DEFAULT_DB_PATH)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """
    Opens a short-lived connection. One connection per operation keeps this safe
    under the threadpool FastAPI runs sync endpoints on, without sharing state.
    """
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


def _row_to_profile(row: sqlite3.Row) -> Dict[str, Any]:
    profile = json.loads(row["data"])
    profile["_edited"] = bool(row["edited"])
    profile["updated_at"] = row["updated_at"]
    return profile


def store_screenplay(
    script_id: str,
    title: str,
    filename: Optional[str],
    profiles: List[Dict[str, Any]],
    author: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Registers a screenplay and its characters, merging over anything previously
    saved for the same script.

    Structural fields (dialogue counts, scene presence, relationships) always
    come from the fresh parse. Fields the user has edited are preserved, so
    re-uploading a script does not discard their work.
    """
    timestamp = _now()

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO screenplays (script_id, title, author, filename, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(script_id) DO UPDATE SET
                title=excluded.title,
                author=excluded.author,
                filename=excluded.filename,
                updated_at=excluded.updated_at
            """,
            (script_id, title, author, filename, timestamp),
        )

        existing = {
            row["character_id"]: row
            for row in conn.execute(
                "SELECT * FROM character_profiles WHERE script_id = ?", (script_id,)
            )
        }

        seen: set = set()
        for ordinal, profile in enumerate(profiles):
            character_id = profile.get("id")
            if not character_id:
                continue
            seen.add(character_id)

            record = dict(profile)
            record.pop("_edited", None)
            prior_row = existing.get(character_id)
            was_edited = bool(prior_row["edited"]) if prior_row else False

            if was_edited:
                prior = json.loads(prior_row["data"])
                for field in USER_OWNED_CHARACTER_FIELDS:
                    if field in prior:
                        record[field] = prior[field]

            conn.execute(
                """
                INSERT INTO character_profiles
                    (script_id, character_id, ordinal, edited, data, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(script_id, character_id) DO UPDATE SET
                    ordinal=excluded.ordinal,
                    data=excluded.data,
                    updated_at=excluded.updated_at
                """,
                (
                    script_id,
                    character_id,
                    ordinal,
                    1 if was_edited else 0,
                    json.dumps(record),
                    timestamp,
                ),
            )

        # Drop characters that vanished from the latest parse, unless the user
        # edited them — their work is kept rather than thrown away.
        for character_id, row in existing.items():
            if character_id in seen:
                continue
            if row["edited"]:
                orphan = json.loads(row["data"])
                orphan["absent_from_latest_parse"] = True
                conn.execute(
                    "UPDATE character_profiles SET data = ?, updated_at = ? "
                    "WHERE script_id = ? AND character_id = ?",
                    (json.dumps(orphan), timestamp, script_id, character_id),
                )
            else:
                conn.execute(
                    "DELETE FROM character_profiles WHERE script_id = ? AND character_id = ?",
                    (script_id, character_id),
                )

    return get_character_profiles(script_id)


def get_screenplay(script_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM screenplays WHERE script_id = ?", (script_id,)
        ).fetchone()
    return dict(row) if row else None


def get_character_profiles(script_id: str) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM character_profiles WHERE script_id = ? ORDER BY ordinal",
            (script_id,),
        ).fetchall()
    return [_row_to_profile(r) for r in rows]


def get_character_profile(script_id: str, character_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM character_profiles WHERE script_id = ? AND character_id = ?",
            (script_id, character_id),
        ).fetchone()
    return _row_to_profile(row) if row else None


def update_character_profile(
    script_id: str,
    character_id: str,
    updates: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Applies a partial update to a stored character. Returns None when the script
    or character is unknown, so the caller can answer 404 instead of reporting a
    success that never happened.
    """
    timestamp = _now()

    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM character_profiles WHERE script_id = ? AND character_id = ?",
            (script_id, character_id),
        ).fetchone()
        if row is None:
            return None

        record = json.loads(row["data"])
        for field in USER_OWNED_CHARACTER_FIELDS:
            if field in updates and updates[field] is not None:
                record[field] = updates[field]

        conn.execute(
            "UPDATE character_profiles SET data = ?, edited = 1, updated_at = ? "
            "WHERE script_id = ? AND character_id = ?",
            (json.dumps(record), timestamp, script_id, character_id),
        )

    return get_character_profile(script_id, character_id)
