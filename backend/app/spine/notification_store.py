"""
Durable storage for the alerts sent to a person.

A notification says something happened and that somebody needs to know: a
requirement was handed to you, the blocker you raised was cleared. Held in
process memory it was the one part of that exchange that did not survive a
restart -- the requirement stayed, its trail stayed, and the alert telling the
sound supervisor it was now theirs quietly vanished. An alert nobody can be
shown is an alert that was never sent.

No separate event log here, unlike the requirements beside it. A notification
is not edited: it is written once, and the only thing that changes afterwards
is whether it has been read. The row is already the record.

What is stored is `read_at` rather than a bare flag. Knowing *when* somebody
saw an alert costs the same as knowing that they did, and answers the question
the flag cannot -- an alert opened within the minute and one opened after nine
days are not the same event, and only the second says the routing is wrong.

Uses the standard library only. The database file is resolved from
CINESPINE_DB_PATH at call time, the same as the other stores.
"""
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

DEFAULT_DB_PATH = "spine.db"

TYPES = ("ASSIGNED", "RESOLVED", "STATUS_CHANGED", "COMMENT")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
    notification_id   TEXT PRIMARY KEY,
    production_id     TEXT NOT NULL DEFAULT '',
    recipient_handle  TEXT NOT NULL,
    actor_handle      TEXT NOT NULL DEFAULT '',
    notification_type TEXT NOT NULL DEFAULT 'ASSIGNED',
    requirement_id    TEXT NOT NULL DEFAULT '',
    title             TEXT NOT NULL DEFAULT '',
    message           TEXT NOT NULL DEFAULT '',
    target_type       TEXT NOT NULL DEFAULT 'take',
    target_id         TEXT NOT NULL DEFAULT '',
    target_label      TEXT NOT NULL DEFAULT '',
    -- When it was read, not whether. The flag the API returns is derived from
    -- this, so the extra fact costs nothing and is there when it is wanted.
    read_at           TEXT,
    created_at        TEXT NOT NULL
);

-- The only read this table gets is one person's alerts, newest first.
CREATE INDEX IF NOT EXISTS ix_notifications_recipient
    ON notifications (recipient_handle, created_at);
"""


class UnknownNotificationValue(ValueError):
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
    """'@ana' however it was typed, so one person is not two inboxes."""
    handle = (raw or "").strip()
    if not handle:
        return ""
    return handle if handle.startswith("@") else f"@{handle}"


def _row_to_notification(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "notification_id": row["notification_id"],
        "production_id": row["production_id"],
        "recipient_handle": row["recipient_handle"],
        "actor_handle": row["actor_handle"],
        "notification_type": row["notification_type"],
        "requirement_id": row["requirement_id"],
        "title": row["title"],
        "message": row["message"],
        "target_type": row["target_type"],
        "target_id": row["target_id"],
        "target_label": row["target_label"],
        # Derived, so callers that only care whether it was read are unchanged
        # by the column underneath being a timestamp.
        "is_read": row["read_at"] is not None,
        "read_at": row["read_at"],
        "created_at": row["created_at"],
    }


def create(notification: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sends an alert to one person.

    A notification with no recipient is refused rather than stored: it would
    sit in the table forever, counted by nothing and shown to nobody.
    """
    kind = notification.get("notification_type") or "ASSIGNED"
    if kind not in TYPES:
        raise UnknownNotificationValue(
            f"notification_type must be one of {', '.join(TYPES)}, got {kind!r}"
        )

    recipient = normalize_handle(notification.get("recipient_handle"))
    if not recipient:
        raise UnknownNotificationValue("recipient_handle is required")

    record = {
        "notification_id": notification.get("notification_id") or f"notif_{uuid.uuid4().hex[:10]}",
        "production_id": notification.get("production_id") or "DEMO_PRODUCTION",
        "recipient_handle": recipient,
        "actor_handle": normalize_handle(notification.get("actor_handle")),
        "notification_type": kind,
        "requirement_id": notification.get("requirement_id") or "",
        "title": notification.get("title") or "",
        "message": notification.get("message") or "",
        "target_type": notification.get("target_type") or "take",
        "target_id": str(notification.get("target_id") or ""),
        "target_label": notification.get("target_label") or "",
        "read_at": None,
        "created_at": notification.get("created_at") or _now(),
    }

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO notifications
                (notification_id, production_id, recipient_handle, actor_handle,
                 notification_type, requirement_id, title, message, target_type,
                 target_id, target_label, read_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(record[k] for k in (
                "notification_id", "production_id", "recipient_handle",
                "actor_handle", "notification_type", "requirement_id", "title",
                "message", "target_type", "target_id", "target_label",
                "read_at", "created_at",
            )),
        )

    record["is_read"] = False
    return record


def get(notification_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM notifications WHERE notification_id = ?", (notification_id,)
        ).fetchone()
    return _row_to_notification(row) if row else None


def list_for(
    recipient_handle: str,
    unread_only: bool = False,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """One person's alerts, newest first."""
    recipient = normalize_handle(recipient_handle)
    sql = "SELECT * FROM notifications WHERE lower(recipient_handle) = ?"
    params: List[Any] = [recipient.lower()]
    if unread_only:
        sql += " AND read_at IS NULL"
    sql += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
    params.append(max(1, min(limit, 1000)))

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_notification(r) for r in rows]


def unread_count(recipient_handle: str) -> int:
    """
    Counted in SQL rather than by listing and measuring.

    The badge is read on every poll, and it does not need the messages.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM notifications "
            "WHERE lower(recipient_handle) = ? AND read_at IS NULL",
            (normalize_handle(recipient_handle).lower(),),
        ).fetchone()
    return int(row["n"])


def mark_read(notification_id: str) -> bool:
    """
    Records that an alert was seen, keeping the first time it was.

    Opening the same alert twice does not move the timestamp: the question it
    answers is how long the alert sat unread, and re-reading it does not change
    that.
    """
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE notifications SET read_at = ? "
            "WHERE notification_id = ? AND read_at IS NULL",
            (_now(), notification_id),
        )
        if cur.rowcount:
            return True
        # Already read is still success for the caller; only a missing
        # notification is a failure.
        row = conn.execute(
            "SELECT 1 FROM notifications WHERE notification_id = ?", (notification_id,)
        ).fetchone()
    return row is not None


def mark_all_read(recipient_handle: str) -> int:
    """Marks everything unread for one person as read, returning how many."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE notifications SET read_at = ? "
            "WHERE lower(recipient_handle) = ? AND read_at IS NULL",
            (_now(), normalize_handle(recipient_handle).lower()),
        )
    return cur.rowcount
