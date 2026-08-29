"""
Durable storage for the spine itself: the events, the documents they were read
out of, and the calls a person made about them.

This is the last thing that lived only in memory. Everything hanging off it had
already been made to survive a restart -- productions, editorial tags,
requirements and their trail, notifications -- which left the app in the odd
state of remembering that a shot was mounted while forgetting the shot.

The spine is append-only. An event is a witness statement: this camera report
says take 3 of 27/7 is on card A120. It is never edited, because a report does
not change its mind; a later report that disagrees is another event, and the
disagreement is the product. So the table only grows, and nothing here updates
a row it has written.

Two things it deliberately does not do:

  It does not replace the writer's in-memory list. That list is read on every
  request that builds takes, sequences or discrepancies -- a full pass over a
  production's events each time -- and turning each of those passes into a
  query plus a few thousand JSON parses would be a real cost for no gain. The
  list is a cache, loaded once from here at startup and appended to as events
  arrive. This file is what makes it survivable, not what makes it readable.

  It does not hold documents in memory. Those carry the original PDF bytes, and
  a preview asks for one at a time. Reading them on demand costs a query and
  saves holding every uploaded file in the process for the life of it.

Uses the standard library only. The database file is resolved from
CINESPINE_DB_PATH at call time, the same as the other stores.
"""
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DEFAULT_DB_PATH = "spine.db"

_SCHEMA = """
-- The spine. Append-only: an event is what one department said, and a later
-- contradiction is another event rather than a correction of this one.
CREATE TABLE IF NOT EXISTS spine_events (
    -- Ordering is by arrival, not by event_id: a document's rows all share the
    -- envelope's id, so event_id is not unique and cannot be the key.
    seq           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT NOT NULL DEFAULT '',
    production_id TEXT NOT NULL DEFAULT '',
    shoot_day     TEXT NOT NULL DEFAULT '',
    axis          TEXT NOT NULL DEFAULT '',
    department    TEXT NOT NULL DEFAULT '',
    doc_type      TEXT NOT NULL DEFAULT '',
    entity_type   TEXT NOT NULL DEFAULT '',
    payload       TEXT NOT NULL DEFAULT '{}',
    metadata      TEXT NOT NULL DEFAULT '{}',
    timestamp     TEXT NOT NULL DEFAULT '',
    doc_id        TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS ix_spine_events_production
    ON spine_events (production_id, shoot_day, seq);

-- Deleting a document takes its readings out of the spine with it, so the
-- events have to be findable by the document they came from.
CREATE INDEX IF NOT EXISTS ix_spine_events_doc
    ON spine_events (doc_id);

-- The paperwork itself, kept so a reading can be checked against the page it
-- was read from. raw_bytes is the original file: a PDF preview shows the page,
-- not our transcription of it.
CREATE TABLE IF NOT EXISTS source_documents (
    doc_id        TEXT PRIMARY KEY,
    production_id TEXT NOT NULL DEFAULT '',
    shoot_day     TEXT NOT NULL DEFAULT '',
    filename      TEXT NOT NULL DEFAULT '',
    doc_type      TEXT NOT NULL DEFAULT '',
    department    TEXT NOT NULL DEFAULT '',
    content       TEXT NOT NULL DEFAULT '',
    raw_bytes     BLOB,
    checksum      TEXT,
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    metadata      TEXT NOT NULL DEFAULT '{}',
    uploaded_at   TEXT NOT NULL
);

-- The same file uploaded twice is one document, and the check runs on every
-- upload.
CREATE INDEX IF NOT EXISTS ix_source_documents_checksum
    ON source_documents (production_id, shoot_day, checksum);

-- A person's call on a disagreement: which card was right, and why. Not a
-- reading, so it is not an event -- and hand-authored, so losing it loses
-- somebody's work rather than something that can be re-derived.
CREATE TABLE IF NOT EXISTS discrepancy_resolutions (
    resolution_key TEXT PRIMARY KEY,
    discrepancy_id TEXT NOT NULL DEFAULT '',
    production_id  TEXT NOT NULL DEFAULT '',
    shoot_day      TEXT NOT NULL DEFAULT '',
    entity_id      TEXT NOT NULL DEFAULT '',
    data           TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS team_users (
    handle       TEXT PRIMARY KEY,
    name         TEXT NOT NULL DEFAULT '',
    email        TEXT NOT NULL DEFAULT '',
    role         TEXT NOT NULL DEFAULT '',
    avatar_color TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL
);
"""

# One connection per database file, held open.
#
# Measured on a 2000-event ingestion, which is what a single Silverstack volume
# produces: a fresh connection per event took 9.4s and a held connection on the
# default journal 7.2s, both of them paying an fsync per event. In WAL with
# synchronous=NORMAL the same 2000 events cost 0.06s, which is cheap enough to
# do on every append and so cheap enough not to need a buffer that a crash
# could empty.
#
# What NORMAL gives up is the last few transactions if the machine loses power.
# It does not give up anything if the process dies, which is the failure this
# file exists for.
_connections: Dict[str, sqlite3.Connection] = {}
_lock = threading.Lock()


def get_db_path() -> str:
    """Resolved at call time so tests can redirect it via the environment."""
    return os.environ.get("CINESPINE_DB_PATH", DEFAULT_DB_PATH)


def _conn() -> sqlite3.Connection:
    """
    The connection for the current database file, opened once.

    check_same_thread is off because FastAPI runs sync endpoints on a
    threadpool, and every write below takes the lock.
    """
    path = get_db_path()
    with _lock:
        conn = _connections.get(path)
        if conn is None:
            conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(_SCHEMA)
            conn.commit()
            _connections[path] = conn
        return conn


def close_all() -> None:
    """Closes every open connection. For tests and for a clean shutdown."""
    with _lock:
        for conn in _connections.values():
            try:
                conn.close()
            except sqlite3.Error:
                pass
        _connections.clear()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# The spine
# --------------------------------------------------------------------------- #

_EVENT_COLUMNS = (
    "event_id", "production_id", "shoot_day", "axis", "department",
    "doc_type", "entity_type", "payload", "metadata", "timestamp", "doc_id",
)

_INSERT_EVENT = (
    "INSERT INTO spine_events "
    f"({', '.join(_EVENT_COLUMNS)}) VALUES ({', '.join('?' * len(_EVENT_COLUMNS))})"
)


def _event_row(event: Dict[str, Any]) -> tuple:
    metadata = event.get("metadata") or {}
    return (
        str(event.get("event_id") or ""),
        str(event.get("production_id") or ""),
        str(event.get("shoot_day") or ""),
        str(event.get("axis") or ""),
        str(event.get("department") or ""),
        str(event.get("doc_type") or ""),
        str(event.get("entity_type") or ""),
        json.dumps(event.get("payload") or {}),
        json.dumps(metadata),
        str(event.get("timestamp") or ""),
        str(metadata.get("doc_id") or ""),
    )


def append_event(event: Dict[str, Any]) -> None:
    """Records one reading. Never fails the caller silently: it raises."""
    conn = _conn()
    with _lock:
        conn.execute(_INSERT_EVENT, _event_row(event))
        conn.commit()


def append_events(events: List[Dict[str, Any]]) -> int:
    """Records several readings in one transaction."""
    if not events:
        return 0
    conn = _conn()
    with _lock:
        conn.executemany(_INSERT_EVENT, [_event_row(e) for e in events])
        conn.commit()
    return len(events)


def _row_to_event(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "event_id": row["event_id"],
        "production_id": row["production_id"],
        "shoot_day": row["shoot_day"],
        "axis": row["axis"],
        "department": row["department"],
        "doc_type": row["doc_type"],
        "entity_type": row["entity_type"],
        "payload": json.loads(row["payload"]),
        "metadata": json.loads(row["metadata"]),
        "timestamp": row["timestamp"],
    }


def load_events() -> List[Dict[str, Any]]:
    """
    Every event, in the order it arrived.

    Read once at startup to warm the in-memory spine. Order matters: several
    reads take the last event as the most recent word, and a spine reloaded out
    of order would answer differently after a restart than before one.
    """
    rows = _conn().execute("SELECT * FROM spine_events ORDER BY seq").fetchall()
    return [_row_to_event(r) for r in rows]


def count_events() -> int:
    return int(_conn().execute("SELECT COUNT(*) AS n FROM spine_events").fetchone()["n"])


def delete_events_for_document(doc_id: str) -> int:
    """Takes a document's readings out of the spine along with the document."""
    conn = _conn()
    with _lock:
        cur = conn.execute("DELETE FROM spine_events WHERE doc_id = ?", (doc_id,))
        conn.commit()
    return cur.rowcount


# --------------------------------------------------------------------------- #
# The paperwork
# --------------------------------------------------------------------------- #

def _row_to_document(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "doc_id": row["doc_id"],
        "production_id": row["production_id"],
        "shoot_day": row["shoot_day"],
        "filename": row["filename"],
        "doc_type": row["doc_type"],
        "department": row["department"],
        "content": row["content"],
        "raw_bytes": row["raw_bytes"],
        "checksum": row["checksum"],
        "size_bytes": row["size_bytes"],
        "metadata": json.loads(row["metadata"]),
        "uploaded_at": row["uploaded_at"],
    }


def store_document(record: Dict[str, Any]) -> str:
    conn = _conn()
    with _lock:
        conn.execute(
            """
            INSERT INTO source_documents
                (doc_id, production_id, shoot_day, filename, doc_type, department,
                 content, raw_bytes, checksum, size_bytes, metadata, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                content=excluded.content,
                raw_bytes=excluded.raw_bytes,
                metadata=excluded.metadata
            """,
            (
                record["doc_id"], record.get("production_id") or "",
                record.get("shoot_day") or "", record.get("filename") or "",
                record.get("doc_type") or "", record.get("department") or "",
                record.get("content") or "", record.get("raw_bytes"),
                record.get("checksum"), int(record.get("size_bytes") or 0),
                json.dumps(record.get("metadata") or {}),
                record.get("uploaded_at") or _now(),
            ),
        )
        conn.commit()
    return record["doc_id"]


def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    row = _conn().execute(
        "SELECT * FROM source_documents WHERE doc_id = ?", (doc_id,)
    ).fetchone()
    return _row_to_document(row) if row else None


def list_documents(
    production_id: Optional[str] = None,
    shoot_day: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    The documents, without their bytes.

    A listing shows names and sizes; loading every uploaded PDF to render a
    list of filenames is what holding them in memory used to cost.
    """
    sql = (
        "SELECT doc_id, production_id, shoot_day, filename, doc_type, department, "
        "checksum, size_bytes, metadata, uploaded_at FROM source_documents WHERE 1=1"
    )
    params: List[Any] = []
    if production_id:
        sql += " AND production_id = ?"
        params.append(production_id)
    if shoot_day:
        sql += " AND shoot_day = ?"
        params.append(str(shoot_day))
    sql += " ORDER BY uploaded_at, rowid"

    rows = _conn().execute(sql, params).fetchall()
    return [
        {
            "doc_id": r["doc_id"],
            "production_id": r["production_id"],
            "shoot_day": r["shoot_day"],
            "filename": r["filename"],
            "doc_type": r["doc_type"],
            "department": r["department"],
            "checksum": r["checksum"],
            "size_bytes": r["size_bytes"],
            "metadata": json.loads(r["metadata"]),
            "uploaded_at": r["uploaded_at"],
        }
        for r in rows
    ]


def find_document_by_checksum(
    production_id: str, shoot_day: str, checksum: str
) -> Optional[Dict[str, Any]]:
    row = _conn().execute(
        "SELECT * FROM source_documents "
        "WHERE production_id = ? AND shoot_day = ? AND checksum = ?",
        (production_id, str(shoot_day), checksum),
    ).fetchone()
    return _row_to_document(row) if row else None


def delete_document(doc_id: str) -> bool:
    conn = _conn()
    with _lock:
        cur = conn.execute("DELETE FROM source_documents WHERE doc_id = ?", (doc_id,))
        conn.commit()
    return cur.rowcount > 0


# --------------------------------------------------------------------------- #
# Calls a person made
# --------------------------------------------------------------------------- #

def save_resolution(key: str, record: Dict[str, Any]) -> None:
    conn = _conn()
    with _lock:
        conn.execute(
            """
            INSERT INTO discrepancy_resolutions
                (resolution_key, discrepancy_id, production_id, shoot_day, entity_id, data)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(resolution_key) DO UPDATE SET data=excluded.data
            """,
            (
                key,
                record.get("discrepancy_id") or "",
                record.get("production_id") or "",
                str(record.get("shoot_day") or ""),
                str(record.get("entity_id") or ""),
                json.dumps(record),
            ),
        )
        conn.commit()


def load_resolutions() -> Dict[str, Dict[str, Any]]:
    rows = _conn().execute("SELECT resolution_key, data FROM discrepancy_resolutions").fetchall()
    return {r["resolution_key"]: json.loads(r["data"]) for r in rows}


def delete_resolutions(keys: List[str]) -> int:
    if not keys:
        return 0
    conn = _conn()
    with _lock:
        cur = conn.executemany(
            "DELETE FROM discrepancy_resolutions WHERE resolution_key = ?",
            [(k,) for k in keys],
        )
        conn.commit()
    return cur.rowcount


# --------------------------------------------------------------------------- #
# The team
# --------------------------------------------------------------------------- #

def save_user(user: Dict[str, Any]) -> None:
    conn = _conn()
    with _lock:
        conn.execute(
            """
            INSERT INTO team_users (handle, name, email, role, avatar_color, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(handle) DO UPDATE SET
                name=excluded.name, email=excluded.email, role=excluded.role,
                avatar_color=excluded.avatar_color, updated_at=excluded.updated_at
            """,
            (
                user["handle"], user.get("name") or "", user.get("email") or "",
                user.get("role") or "", user.get("avatar_color") or "", _now(),
            ),
        )
        conn.commit()


def load_users() -> Dict[str, Dict[str, Any]]:
    rows = _conn().execute("SELECT * FROM team_users ORDER BY rowid").fetchall()
    return {
        r["handle"]: {
            "handle": r["handle"],
            "name": r["name"],
            "email": r["email"],
            "role": r["role"],
            "avatar_color": r["avatar_color"],
        }
        for r in rows
    }
