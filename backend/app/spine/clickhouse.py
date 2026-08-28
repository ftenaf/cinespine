"""
The optional ClickHouse connection for the analytical event spine.

Everything for this existed already -- the DDL, the compose service, the driver,
the environment variables -- except the line that connects. SpineWriter was
always built with clickhouse_client=None, so the insert in append_event had
never run once.

Connecting is opt-in and never fatal. CineSpine has to keep working on a laptop
with no Docker running, so a ClickHouse that is absent, unreachable or broken
degrades to exactly the behaviour there was before: the in-memory spine serves
every read, and the analytical copy simply is not made.

What belongs here and what does not: ingestion events are high-volume,
append-only and read in aggregate, which is what a column store is for. The tags
themselves are not -- they are a few hundred mutable rows read one at a time --
so they stay in SQLite and are only mirrored here for the history, where the
question is analytical ("what moved this week") rather than transactional.
"""
import logging
import os
from typing import Any, Optional

from backend.app.spine.schema import CLICKHOUSE_SCHEMA_DDL

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    """
    Connecting takes an explicit CLICKHOUSE_HOST.

    Defaulting to localhost would mean every developer without the container
    running pays a connection timeout on startup for a feature they did not ask
    for.
    """
    return bool(os.environ.get("CLICKHOUSE_HOST", "").strip())


def connect() -> Optional[Any]:
    """
    Returns a client with the schema applied, or None.

    None is a supported outcome, not a failure: the caller keeps its in-memory
    spine either way. The reason is logged once, at startup, so a misconfigured
    host is visible without making it fatal.
    """
    if not is_configured():
        logger.info("ClickHouse not configured (no CLICKHOUSE_HOST); using the in-memory spine only")
        return None

    try:
        import clickhouse_connect
    except ImportError:
        logger.warning("CLICKHOUSE_HOST is set but clickhouse-connect is not installed")
        return None

    host = os.environ["CLICKHOUSE_HOST"].strip()
    try:
        client = clickhouse_connect.get_client(
            host=host,
            port=int(os.environ.get("CLICKHOUSE_PORT", "8123")),
            username=os.environ.get("CLICKHOUSE_USER", "default"),
            password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
            connect_timeout=int(os.environ.get("CLICKHOUSE_CONNECT_TIMEOUT", "5")),
        )
        # Applied on every connect. The statements are all IF NOT EXISTS, so this
        # is how a fresh container gets its tables without a migration step.
        for statement in CLICKHOUSE_SCHEMA_DDL.split(";"):
            if statement.strip():
                client.command(statement)
        logger.info("ClickHouse connected at %s; the analytical spine is live", host)
        return client
    except Exception as exc:
        logger.warning("ClickHouse at %s is unreachable (%s); using the in-memory spine only", host, exc)
        return None
