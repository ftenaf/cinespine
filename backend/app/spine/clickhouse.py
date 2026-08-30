"""
The optional ClickHouse connection for the analytical event spine.

Everything for this existed already -- the DDL, the compose service, the driver,
the environment variables -- except the line that connects. SpineWriter was
always built with clickhouse_client=None, so the insert in append_event had
never run once.

Local or hosted. `CLICKHOUSE_SECURE` chooses the protocol and the port follows
it -- 8443 for TLS, 8123 for plain -- so a managed instance needs a host, a
password and one flag. The protocol is stated rather than guessed from the
hostname, because guessing means keeping a list of what managed endpoints look
like and that list is wrong the day a provider adds a domain.

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
import re
from typing import Any, Optional

from backend.app.spine.schema import schema_ddl, statements

logger = logging.getLogger(__name__)


# Plain HTTP and TLS listen on different ports, and getting that pairing wrong
# is the whole failure mode this module has to avoid: a managed instance only
# ever answers on the TLS one, so a secure connection aimed at 8123 does not
# fail with "wrong protocol" -- it fails as unreachable, which reads like the
# host being down.
DEFAULT_PORT = 8123
DEFAULT_SECURE_PORT = 8443

_TRUE = frozenset({"1", "true", "yes", "on"})


def _flag(name: str, default: bool = False) -> bool:
    """
    An environment variable read as a boolean.

    Anything unrecognised is the default rather than an error: a connection
    setting is not worth refusing to start over, and the connection itself is
    already optional.
    """
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in _TRUE


def use_tls() -> bool:
    """
    Whether to speak TLS. Off unless asked.

    Stated, never inferred from the hostname. Guessing would mean a list of
    what managed endpoints look like, and that list is wrong the day a provider
    adds a domain -- the failure mode this project calls the keyed list that
    rots. A local container wants plain HTTP and a hosted instance wants TLS,
    and only the person deploying it knows which they have.
    """
    return _flag("CLICKHOUSE_SECURE")


def port() -> int:
    """
    The port, defaulting to whichever one matches the protocol.

    Explicit CLICKHOUSE_PORT always wins. Without it, TLS means 8443 and plain
    means 8123, so `CLICKHOUSE_SECURE=1` on its own is a complete answer rather
    than half of one.
    """
    raw = os.environ.get("CLICKHOUSE_PORT", "").strip()
    if raw:
        return int(raw)
    return DEFAULT_SECURE_PORT if use_tls() else DEFAULT_PORT


# Where the mirror's tables live. Configurable for one reason: the test suite
# must not write into the database a demo reads from. When CLICKHOUSE_HOST was
# set, running the suite put 5355 rows of fixtures -- CHTEST, HEAVY, BATCH1,
# INTENT_DISAGREE -- into the same tables as the production's 475, so the
# analytics panel was 92% test data and nobody could tell by looking.
DEFAULT_DATABASE = "cinespine"

# Interpolated into SQL, so it is checked rather than trusted. The value comes
# from the environment and not from a request, but a name that cannot be a name
# should fail here rather than somewhere further in.
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def database() -> str:
    """The database the tables live in. `cinespine` unless told otherwise."""
    name = os.environ.get("CLICKHOUSE_DATABASE", "").strip() or DEFAULT_DATABASE
    if not _NAME.match(name):
        raise ValueError(
            f"CLICKHOUSE_DATABASE={name!r} is not a usable database name; "
            "letters, digits and underscores only."
        )
    return name


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
    secure = use_tls()
    chosen_port = port()
    try:
        client = clickhouse_connect.get_client(
            host=host,
            port=chosen_port,
            username=os.environ.get("CLICKHOUSE_USER", "default"),
            password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
            secure=secure,
            # Certificates are verified unless someone turns it off, which is
            # for a self-hosted instance with its own certificate authority.
            # A managed endpoint has a public certificate and needs nothing.
            verify=_flag("CLICKHOUSE_VERIFY", default=True),
            connect_timeout=int(os.environ.get("CLICKHOUSE_CONNECT_TIMEOUT", "5")),
        )
        # Applied on every connect. The statements are all IF NOT EXISTS, so this
        # is how a fresh container gets its tables without a migration step.
        for statement in statements(database()):
            client.command(statement)
        logger.info(
            "ClickHouse connected at %s:%s (%s); the analytical spine is live",
            host, chosen_port, "TLS" if secure else "plain HTTP",
        )
        return client
    except Exception as exc:
        # Names the protocol and port it tried. A TLS mismatch surfaces as an
        # unreachable host, which sends people to check whether the server is
        # up when the answer is on this side.
        logger.warning(
            "ClickHouse at %s:%s over %s is unreachable (%s); using the in-memory spine only",
            host, chosen_port, "TLS" if secure else "plain HTTP", exc,
        )
        return None
