"""
Who saw what, and when they took it on.

`handoffs.md` names the gap this fills: "No acknowledgement is recorded
anywhere." A blocker is raised, a notification goes out, and nothing in the
production can answer whether the person it was for ever saw it. The question a
production asks is not how many times the slate navigator was opened. It is
whether the sound supervisor saw the blocker, and when.

# Two kinds of event, and the difference matters

`viewed` is passive: a surface was opened with this entity on it. `acknowledged`
is deliberate: somebody pressed a control that says "I have seen this and it is
mine". They answer different questions and must never be conflated -- a view is
weak evidence about attention, an acknowledgement is a claim a person made.

Only acknowledgement can carry an obligation. "Nobody has opened this
requirement" is a prompt to go and ask; "nobody has acknowledged it" is a fact
about the production's handover.

# What this is not

It is not a performance record. It stores the `@handle` role token this project
uses in place of a crew member's name -- `@sound_supervisor`, not a person --
and it exists to answer where a handover stalled, not who is slow. The
distinction is worth keeping in mind when adding a query: "time to acknowledge,
by department" is about the handover. The same query grouped by individual and
sorted ascending is a different instrument.

# Shape

Append-only, like the tag and requirement trails beside it, and for the same
reason: when somebody saw something is a fact about a moment, and a row that
can be updated cannot answer "when". SQLite is the source of truth; ClickHouse
carries the copy the analytical questions are asked of.
"""
import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# What somebody did. Deliberately short: a vocabulary that grows on every call
# site becomes a list nobody can group by.
ACTIONS = ("viewed", "acknowledged")

# What they did it to. Mirrors the requirement target levels, plus the two
# surfaces that carry a day's work.
TARGET_TYPES = (
    "requirement", "discrepancy", "notification",
    "shoot_day", "scene", "shot", "take", "document", "production",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_activity (
    event_id      TEXT PRIMARY KEY,
    production_id TEXT NOT NULL,
    shoot_day     TEXT NOT NULL DEFAULT '',
    actor         TEXT NOT NULL,
    department    TEXT NOT NULL DEFAULT '',
    action        TEXT NOT NULL,
    target_type   TEXT NOT NULL,
    target_id     TEXT NOT NULL,
    target_label  TEXT NOT NULL DEFAULT '',
    -- How long the thing had existed when they saw it. Computed by the caller,
    -- because only the caller knows when the target was created, and storing it
    -- here means "time to acknowledge" is a column rather than a join.
    seconds_since_target_created REAL,
    context_json  TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS user_activity_by_target
    ON user_activity (production_id, target_type, target_id);
CREATE INDEX IF NOT EXISTS user_activity_by_actor
    ON user_activity (production_id, actor, created_at);
"""


class UnknownActivityValue(ValueError):
    """An action or target type nobody declared."""


_connections: Dict[str, sqlite3.Connection] = {}
_lock = threading.Lock()


def get_db_path() -> str:
    import os
    return os.environ.get("CINESPINE_DB_PATH", "spine.db")


def _conn() -> sqlite3.Connection:
    path = get_db_path()
    with _lock:
        conn = _connections.get(path)
        if conn is None:
            conn = sqlite3.connect(path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(_SCHEMA)
            conn.commit()
            _connections[path] = conn
        return conn


def close_all() -> None:
    with _lock:
        for conn in _connections.values():
            try:
                conn.close()
            except Exception:
                pass
        _connections.clear()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record(
    production_id: str,
    actor: str,
    action: str,
    target_type: str,
    target_id: str,
    shoot_day: str = "",
    department: str = "",
    target_label: str = "",
    seconds_since_target_created: Optional[float] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Appends one activity event and returns it.

    The vocabulary is closed. An action or target nobody declared is refused
    rather than stored, because a surface that invents its own verb produces
    rows no query will ever group with anything else -- present in the table,
    absent from every answer.
    """
    if action not in ACTIONS:
        raise UnknownActivityValue(
            f"action must be one of {', '.join(ACTIONS)}, got {action!r}"
        )
    if target_type not in TARGET_TYPES:
        raise UnknownActivityValue(
            f"target_type must be one of {', '.join(sorted(TARGET_TYPES))}, got {target_type!r}"
        )
    if not str(actor or "").strip():
        raise UnknownActivityValue("an activity event needs an actor")
    if not str(target_id or "").strip():
        raise UnknownActivityValue("an activity event needs a target_id")

    event = {
        "event_id": f"act_{uuid.uuid4().hex[:12]}",
        "production_id": production_id,
        "shoot_day": shoot_day or "",
        "actor": actor.strip(),
        "department": department or "",
        "action": action,
        "target_type": target_type,
        "target_id": str(target_id).strip(),
        "target_label": target_label or "",
        "seconds_since_target_created": seconds_since_target_created,
        "context_json": json.dumps(context or {}),
        "created_at": _now(),
    }

    conn = _conn()
    with _lock:
        conn.execute(
            "INSERT INTO user_activity (event_id, production_id, shoot_day, actor, department,"
            " action, target_type, target_id, target_label, seconds_since_target_created,"
            " context_json, created_at)"
            " VALUES (:event_id, :production_id, :shoot_day, :actor, :department, :action,"
            " :target_type, :target_id, :target_label, :seconds_since_target_created,"
            " :context_json, :created_at)",
            event,
        )
        conn.commit()
    return event


def for_target(production_id: str, target_type: str, target_id: str) -> List[Dict[str, Any]]:
    """Everything anybody did to one thing, oldest first."""
    rows = _conn().execute(
        "SELECT * FROM user_activity WHERE production_id = ? AND target_type = ?"
        " AND target_id = ? ORDER BY created_at",
        (production_id, target_type, str(target_id)),
    ).fetchall()
    return [dict(r) for r in rows]


def acknowledgement(production_id: str, target_type: str, target_id: str) -> Optional[Dict[str, Any]]:
    """
    The first acknowledgement of a thing, or None.

    The first rather than the latest: what a handover asks is when somebody
    took this on, and a later acknowledgement by a second person does not move
    that moment.
    """
    row = _conn().execute(
        "SELECT * FROM user_activity WHERE production_id = ? AND target_type = ?"
        " AND target_id = ? AND action = 'acknowledged' ORDER BY created_at LIMIT 1",
        (production_id, target_type, str(target_id)),
    ).fetchone()
    return dict(row) if row else None


def all_events(production_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Every event, for the mirror rebuild and for tests."""
    if production_id:
        rows = _conn().execute(
            "SELECT * FROM user_activity WHERE production_id = ? ORDER BY created_at",
            (production_id,),
        ).fetchall()
    else:
        rows = _conn().execute("SELECT * FROM user_activity ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]
