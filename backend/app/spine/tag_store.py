"""
Durable storage for the editorial tags an assistant editor puts on a scene or a
shot.

Three separate questions get asked about a piece of coverage, and they are kept
apart because they are answered by different people at different times and read
differently on a progress board:

- how far along it is  -> one status, a progression
- what work it still needs -> any number of needs
- what kind of shot it is  -> any number of descriptors

Mixing the three would make "how much is left to do" unanswerable: an
establishing shot is not a stage of completion, and needing subtitles is not
either.

Like the character profiles next door, these are authored by hand and have to
outlive a backend restart, so they live in SQLite rather than in process memory.
The database file is resolved from CINESPINE_DB_PATH at call time so tests can
point it at a temporary file.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple

DEFAULT_DB_PATH = "spine.db"

# A tag hangs on a scene or on a shot, never on a take. A take is one attempt;
# what an editor tracks is the coverage, which outlives any single attempt.
TARGET_TYPES: Tuple[str, ...] = ("scene", "shot")

# The progression, in order. Ordinal is what a progress bar sorts on, so it is
# stored with the vocabulary rather than inferred from the list's order later.
STATUSES: Tuple[Dict[str, Any], ...] = (
    {"key": "finished_shooting", "label": "Finished shooting", "ordinal": 1,
     "description": "Nothing further is planned on the floor for this coverage."},
    {"key": "covered_per_script", "label": "Covered per script", "ordinal": 2,
     "description": "Every angle the script calls for exists."},
    {"key": "ready_to_edit", "label": "Ready to edit", "ordinal": 3,
     "description": "Synced, marked and handed to the cutting room."},
    {"key": "mounted", "label": "Mounted", "ordinal": 4,
     "description": "Assembled into the cut."},
    {"key": "finished", "label": "Finished", "ordinal": 5,
     "description": "No further work expected."},
)

# Work still owed on this coverage. Independent of each other and of the status:
# a mounted scene can still be waiting on subtitles.
NEEDS: Tuple[Dict[str, str], ...] = (
    {"key": "sfx", "label": "Sound effects",
     "description": "Needs sound effects laid in."},
    {"key": "subtitles", "label": "Subtitles",
     "description": "Needs subtitles authored."},
    {"key": "translation", "label": "Translation",
     "description": "Needs dialogue translated."},
)

# What the coverage is, rather than how far along it is or what it still needs.
DESCRIPTORS: Tuple[Dict[str, str], ...] = (
    {"key": "establishment", "label": "Establishing",
     "description": "Establishes a place or a situation rather than playing a beat."},
)

_STATUS_KEYS = {s["key"] for s in STATUSES}
_NEED_KEYS = {n["key"] for n in NEEDS}
_DESCRIPTOR_KEYS = {d["key"] for d in DESCRIPTORS}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS editorial_tags (
    production_id TEXT NOT NULL,
    target_type   TEXT NOT NULL,
    target_id     TEXT NOT NULL,
    status        TEXT,
    needs         TEXT NOT NULL DEFAULT '[]',
    descriptors   TEXT NOT NULL DEFAULT '[]',
    note          TEXT,
    updated_by    TEXT,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (production_id, target_type, target_id)
);
"""


class UnknownTagValue(ValueError):
    """
    Raised for a value outside the vocabulary.

    The vocabulary is closed on purpose. A board that answers "what is left to
    do" can only count what everyone spells the same way, and free text drifts
    into sfx / SFX / sound fx within a week.
    """


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


def vocabulary() -> Dict[str, Any]:
    """
    The whole controlled vocabulary, served to the client so that labels live in
    one place rather than being spelled again in the interface.
    """
    return {
        "target_types": list(TARGET_TYPES),
        "statuses": [dict(s) for s in STATUSES],
        "needs": [dict(n) for n in NEEDS],
        "descriptors": [dict(d) for d in DESCRIPTORS],
    }


def normalize_target(target_type: str, target_id: str) -> Tuple[str, str]:
    """
    Settles how a target is spelled, so the same shot tagged from two places is
    one row and not two.

    A shot is its slate -- scene and shot together, '27/7'. A scene is the bare
    number. Both are upper-cased and stripped of the take suffix a slate may
    arrive with.
    """
    kind = (target_type or "").strip().lower()
    if kind not in TARGET_TYPES:
        raise UnknownTagValue(
            f"target_type must be one of {', '.join(TARGET_TYPES)}, got {target_type!r}"
        )

    # Imported here: the normalizers import nothing from the spine, and keeping
    # the edge one-way avoids a cycle if that ever changes.
    from backend.app.normalizers.slates import normalize_slate

    raw = (target_id or "").strip()
    if not raw:
        raise UnknownTagValue("target_id is required")

    if kind == "shot":
        slate = normalize_slate(raw)
        if not slate:
            raise UnknownTagValue(f"{raw!r} is not a slate")
        return kind, slate

    # A scene is the half of a slate before the shot, so that tagging '27/7' as
    # a scene and tagging '27' as a scene land on the same row.
    scene = raw.upper().split("/")[0].strip()
    if not scene:
        raise UnknownTagValue(f"{raw!r} is not a scene")
    return kind, scene


def _validate(status: Optional[str], needs: List[str], descriptors: List[str]) -> None:
    if status is not None and status not in _STATUS_KEYS:
        raise UnknownTagValue(
            f"status must be one of {', '.join(sorted(_STATUS_KEYS))}, got {status!r}"
        )
    for value in needs:
        if value not in _NEED_KEYS:
            raise UnknownTagValue(
                f"need must be one of {', '.join(sorted(_NEED_KEYS))}, got {value!r}"
            )
    for value in descriptors:
        if value not in _DESCRIPTOR_KEYS:
            raise UnknownTagValue(
                f"descriptor must be one of {', '.join(sorted(_DESCRIPTOR_KEYS))}, "
                f"got {value!r}"
            )


def _row_to_tag(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "production_id": row["production_id"],
        "target_type": row["target_type"],
        "target_id": row["target_id"],
        "status": row["status"],
        "needs": json.loads(row["needs"]),
        "descriptors": json.loads(row["descriptors"]),
        "note": row["note"],
        "updated_by": row["updated_by"],
        "updated_at": row["updated_at"],
    }


def set_tag(
    production_id: str,
    target_type: str,
    target_id: str,
    status: Optional[str] = None,
    needs: Optional[List[str]] = None,
    descriptors: Optional[List[str]] = None,
    note: Optional[str] = None,
    updated_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Writes the whole tag for one target, replacing whatever was there.

    Replacing rather than merging keeps "clear the SFX flag" expressible: with
    merge semantics the client can only ever add.
    """
    kind, ident = normalize_target(target_type, target_id)
    needs = sorted(set(needs or []))
    descriptors = sorted(set(descriptors or []))
    _validate(status, needs, descriptors)

    handle = (updated_by or "").strip()
    if handle and not handle.startswith("@"):
        handle = f"@{handle}"

    record = {
        "production_id": production_id,
        "target_type": kind,
        "target_id": ident,
        "status": status,
        "needs": needs,
        "descriptors": descriptors,
        "note": (note or "").strip() or None,
        "updated_by": handle or None,
        "updated_at": _now(),
    }

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO editorial_tags
                (production_id, target_type, target_id, status, needs,
                 descriptors, note, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (production_id, target_type, target_id) DO UPDATE SET
                status      = excluded.status,
                needs       = excluded.needs,
                descriptors = excluded.descriptors,
                note        = excluded.note,
                updated_by  = excluded.updated_by,
                updated_at  = excluded.updated_at
            """,
            (
                production_id, kind, ident, status,
                json.dumps(needs), json.dumps(descriptors),
                record["note"], record["updated_by"], record["updated_at"],
            ),
        )
    return record


def get_tag(production_id: str, target_type: str, target_id: str) -> Optional[Dict[str, Any]]:
    kind, ident = normalize_target(target_type, target_id)
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM editorial_tags
             WHERE production_id = ? AND target_type = ? AND target_id = ?
            """,
            (production_id, kind, ident),
        ).fetchone()
    return _row_to_tag(row) if row else None


def list_tags(
    production_id: str,
    target_type: Optional[str] = None,
    status: Optional[str] = None,
    need: Optional[str] = None,
    descriptor: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Every tag in a production, narrowed by any of the axes.

    Production-scoped rather than day-scoped on purpose: a shot is covered
    across whatever days it took, and its place in the edit is a property of the
    shot, not of the day a page happened to be filed under.
    """
    sql = "SELECT * FROM editorial_tags WHERE production_id = ?"
    params: List[Any] = [production_id]
    if target_type:
        kind = target_type.strip().lower()
        if kind not in TARGET_TYPES:
            raise UnknownTagValue(f"unknown target_type {target_type!r}")
        sql += " AND target_type = ?"
        params.append(kind)
    if status:
        if status not in _STATUS_KEYS:
            raise UnknownTagValue(f"unknown status {status!r}")
        sql += " AND status = ?"
        params.append(status)

    with _connect() as conn:
        rows = [_row_to_tag(r) for r in conn.execute(sql, params).fetchall()]

    # The list columns are JSON, so they are filtered in Python rather than with
    # a LIKE that would match 'sfx' inside a longer key.
    if need:
        rows = [r for r in rows if need in r["needs"]]
    if descriptor:
        rows = [r for r in rows if descriptor in r["descriptors"]]

    return sorted(rows, key=lambda r: (r["target_type"], r["target_id"]))


def clear_tag(production_id: str, target_type: str, target_id: str) -> bool:
    """Removes a target's tag entirely. Untagged and 'tagged with nothing' read
    the same on a board, and keeping an empty row would only confuse the count
    of what has been looked at."""
    kind, ident = normalize_target(target_type, target_id)
    with _connect() as conn:
        cur = conn.execute(
            """
            DELETE FROM editorial_tags
             WHERE production_id = ? AND target_type = ? AND target_id = ?
            """,
            (production_id, kind, ident),
        )
        return cur.rowcount > 0


def summarize(production_id: str) -> Dict[str, Any]:
    """
    Counts for a progress board: how many targets sit at each status, and how
    many are waiting on each kind of work.

    Deliberately thin -- it answers "how far along" and "what is outstanding"
    and nothing else. The board itself is not built here.
    """
    tags = list_tags(production_id)
    by_status = {s["key"]: 0 for s in STATUSES}
    by_need = {n["key"]: 0 for n in NEEDS}
    by_descriptor = {d["key"]: 0 for d in DESCRIPTORS}

    untagged_status = 0
    for tag in tags:
        if tag["status"]:
            by_status[tag["status"]] += 1
        else:
            untagged_status += 1
        for need in tag["needs"]:
            if need in by_need:
                by_need[need] += 1
        for descriptor in tag["descriptors"]:
            if descriptor in by_descriptor:
                by_descriptor[descriptor] += 1

    return {
        "production_id": production_id,
        "tagged_targets": len(tags),
        "by_status": by_status,
        "no_status": untagged_status,
        "by_need": by_need,
        "by_descriptor": by_descriptor,
    }
