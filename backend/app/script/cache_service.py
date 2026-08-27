"""
Content-addressed cache for AI responses.

Image synthesis and character inference are the two slow, billed operations in
CineSpine. Both are deterministic enough that repeating an identical request is
pure waste, so successful responses are keyed by a hash of their inputs and kept
in SQLite.

Only successes belong here. A cached failure is worse than no cache at all: it
freezes a transient outage into a permanent one, because the retry that would
have fixed it never runs.

Uses the standard library only. The database file is resolved from
CINESPINE_CACHE_DB at call time (default: ai_cache.db in the working directory),
so tests can point it at a temporary file.
"""
import hashlib
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DB_PATH = "ai_cache.db"

# Bumped whenever a change to prompt construction or response shape makes
# previously stored entries wrong rather than merely stale.
CACHE_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_responses (
    request_hash     TEXT PRIMARY KEY,
    response_payload TEXT NOT NULL,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def get_cache_db_path() -> str:
    """Resolved at call time so tests can redirect it via the environment."""
    return os.environ.get("CINESPINE_CACHE_DB", DEFAULT_CACHE_DB_PATH)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """
    Opens a short-lived connection and closes it.

    `with sqlite3.connect(...)` commits the transaction but leaves the
    connection open, which leaks one handle per call; this closes it.
    """
    conn = sqlite3.connect(get_cache_db_path(), timeout=10)
    try:
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def generate_hash(*args: Any, **kwargs: Any) -> str:
    """Generates a deterministic SHA-256 hash from arguments."""
    payload = {
        "v": CACHE_VERSION,
        "args": args,
        "kwargs": {k: v for k, v in sorted(kwargs.items())},
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def get_cached_response(request_hash: str) -> Optional[Dict[str, Any]]:
    """Retrieves a cached JSON response if it exists."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT response_payload FROM ai_responses WHERE request_hash = ?",
                (request_hash,),
            ).fetchone()
            if row:
                return json.loads(row["response_payload"])
    except (sqlite3.Error, ValueError) as exc:
        logger.warning("Cache read failed for %s: %s", request_hash, exc)
    return None


def set_cached_response(request_hash: str, payload: Dict[str, Any]) -> None:
    """Stores a successful JSON response in the cache."""
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ai_responses (request_hash, response_payload) VALUES (?, ?)",
                (request_hash, json.dumps(payload)),
            )
    except (sqlite3.Error, TypeError, ValueError) as exc:
        logger.warning("Cache write failed for %s: %s", request_hash, exc)
