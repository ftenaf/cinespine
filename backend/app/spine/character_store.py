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

-- The scene text itself. An editor cutting a shot needs to read what the
-- scene was written to be, and until now the parsed screenplay lived only in
-- the Script Studio tab's memory: it was gone on reload and invisible to
-- everyone working the reconciliation side.
CREATE TABLE IF NOT EXISTS screenplay_scenes (
    script_id    TEXT NOT NULL,
    ordinal      INTEGER NOT NULL,
    scene_number TEXT NOT NULL,
    heading      TEXT NOT NULL DEFAULT '',
    body         TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (script_id, ordinal)
);

CREATE INDEX IF NOT EXISTS screenplay_scenes_by_number
    ON screenplay_scenes (script_id, scene_number);

-- Which screenplay a production is shooting. One script per production: a
-- production with two scripts has no answer to "what is scene 119", and
-- guessing between them would be worse than saying nothing.
CREATE TABLE IF NOT EXISTS production_scripts (
    production_id TEXT PRIMARY KEY,
    script_id     TEXT NOT NULL,
    linked_at     TEXT NOT NULL
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


# --------------------------------------------------------------------------- #
# Scene text
# --------------------------------------------------------------------------- #

def store_screenplay_scenes(script_id: str, scenes: List[Dict[str, Any]]) -> int:
    """
    Replaces the stored scenes for a script with a fresh parse.

    Replacement, not merge: unlike character profiles, nobody hand-edits scene
    text here, so the newest parse of the screenplay is always the truth. A
    scene that has disappeared from the script must disappear from the store
    too, or an editor would read a passage that is no longer in the film.
    """
    timestamp = _now()

    with _connect() as conn:
        conn.execute("DELETE FROM screenplay_scenes WHERE script_id = ?", (script_id,))
        rows = []
        for ordinal, scene in enumerate(scenes):
            # Upper-cased on the way in so '122a' and '122A' are one scene, the
            # same way a slate is normalized before it becomes a tag target.
            scene_number = str(scene.get("scene_number") or "").strip().upper()
            if not scene_number:
                continue
            rows.append(
                (
                    script_id,
                    ordinal,
                    scene_number,
                    str(scene.get("heading") or ""),
                    str(scene.get("raw_content") or scene.get("body") or ""),
                    timestamp,
                )
            )
        conn.executemany(
            "INSERT INTO screenplay_scenes "
            "(script_id, ordinal, scene_number, heading, body, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )

    return len(rows)


def get_screenplay_scenes(script_id: str) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM screenplay_scenes WHERE script_id = ? ORDER BY ordinal",
            (script_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def find_screenplay_scenes(script_id: str, scene_number: str) -> List[Dict[str, Any]]:
    """
    Every scene filed under this number, in script order.

    A list rather than one row because a screenplay can carry the same number
    twice -- omitted-and-reinstated scenes, A/B revisions typed by hand. Showing
    both and letting the reader choose is honest; picking one silently is not.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM screenplay_scenes WHERE script_id = ? AND scene_number = ? "
            "ORDER BY ordinal",
            (script_id, str(scene_number).strip().upper()),
        ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Which script a production is shooting
# --------------------------------------------------------------------------- #

def link_production_script(production_id: str, script_id: str) -> Dict[str, Any]:
    timestamp = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO production_scripts (production_id, script_id, linked_at)
            VALUES (?, ?, ?)
            ON CONFLICT(production_id) DO UPDATE SET
                script_id=excluded.script_id,
                linked_at=excluded.linked_at
            """,
            (production_id, script_id, timestamp),
        )
    return {"production_id": production_id, "script_id": script_id, "linked_at": timestamp}


def get_production_script(production_id: str) -> Optional[Dict[str, Any]]:
    """The screenplay linked to a production, with its title, or None."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT ps.production_id, ps.script_id, ps.linked_at,
                   s.title, s.author, s.filename
            FROM production_scripts ps
            LEFT JOIN screenplays s ON s.script_id = ps.script_id
            WHERE ps.production_id = ?
            """,
            (production_id,),
        ).fetchone()
    return dict(row) if row else None


def unlink_production_script(production_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM production_scripts WHERE production_id = ?", (production_id,)
        )
    return cur.rowcount > 0


def find_productions_for_script(script_id: str) -> List[str]:
    """
    Which productions are shooting this script.

    The link is stored per production, so the Script Studio -- which knows only
    the script it has loaded -- needs it read the other way round to show that
    the script is already attached rather than offering to attach it again.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT production_id FROM production_scripts WHERE script_id = ? "
            "ORDER BY production_id",
            (script_id,),
        ).fetchall()
    return [r["production_id"] for r in rows]
