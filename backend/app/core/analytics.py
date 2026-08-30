"""
Product analytics, sent to a self-hosted PostHog.

What this answers that the spine cannot: the spine records what a production
did. This records what the *tool* did -- which surfaces get used, how long a
requirement sits before anyone opens it, which department is slowest to
acknowledge. `handoffs.md` names the gap it exists for: "No acknowledgement is
recorded anywhere."

# What is deliberately not sent

This app renders unreleased footage, crew names, and source documents carrying
phone numbers and email addresses. So nothing here captures content:

  * No autocapture and no session replay. Those would record the slate
    navigator mid-frame and the document previewer showing a facing page.
  * No free text. Titles, descriptions, notes, resolution notes and filenames
    never leave: a filename carries the production's name, and a note carries
    whatever somebody typed into it.
  * Identity is the `@handle` -- a role token like `@sound_supervisor`, which is
    what this project uses in place of a crew member's name.

Properties are ids and enumerations: which production, which day, which slate,
which department, which status. Enough to count and group; not enough to
reconstruct anything.

# Never fatal, never required

Same contract as the ClickHouse mirror beside it. Unconfigured means every call
is a no-op, so the app runs on a laptop with nothing else installed. A PostHog
that is unreachable costs the analytics and nothing else -- an editor's save
must never fail because a telemetry endpoint is down.
"""
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_client: Optional[Any] = None
_started = False

# Properties that must never be sent, whatever a caller passes. A blocklist
# rather than trust: these names are the ones that carry typed text or a
# filename, and a new call site should not be able to add one by accident.
FORBIDDEN_PROPERTIES = frozenset({
    "title", "description", "note", "resolution_note", "comment",
    "filename", "file_name", "content", "raw_content", "message",
    "name", "email", "phone", "target_label", "prompt", "body",
})


def is_configured() -> bool:
    """
    Sending takes an explicit key and host.

    Both, not either: a key with no host would default to PostHog's cloud, and
    this product's telemetry must not leave the machine it is deployed on.
    """
    return bool(
        os.environ.get("POSTHOG_API_KEY", "").strip()
        and os.environ.get("POSTHOG_HOST", "").strip()
    )


def start() -> Optional[Any]:
    """
    Prepares the client once, or returns None when nothing is configured.

    None is a supported outcome and the common one in development.
    """
    global _client, _started
    if _started:
        return _client
    _started = True

    if not is_configured():
        logger.info("PostHog not configured (POSTHOG_API_KEY / POSTHOG_HOST); analytics disabled")
        return None

    try:
        from posthog import Posthog
    except ImportError:
        logger.warning("POSTHOG_API_KEY is set but the posthog package is not installed")
        return None

    host = os.environ["POSTHOG_HOST"].strip()
    try:
        _client = Posthog(
            project_api_key=os.environ["POSTHOG_API_KEY"].strip(),
            host=host,
            # Failures are logged, never raised: see the module docstring.
            on_error=lambda e, batch: logger.warning("PostHog delivery failed: %s", e),
        )
        logger.info("PostHog analytics enabled against %s", host)
    except Exception as e:
        logger.warning("PostHog unavailable (%s); analytics disabled", e)
        _client = None

    return _client


def reset() -> None:
    """Drops the client so a test can change the environment and start again."""
    global _client, _started
    _client = None
    _started = False


def safe_properties(properties: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    The properties that may be sent, with anything carrying content removed.

    Applied to every event rather than trusted at each call site, because the
    call sites are spread across the API and the next one will be written by
    somebody who has not read this file.
    """
    clean: Dict[str, Any] = {}
    for key, value in (properties or {}).items():
        if key.lower() in FORBIDDEN_PROPERTIES:
            continue
        if value is None:
            continue
        # Ids and enumerations are short. Anything long is prose that named
        # itself something this blocklist did not anticipate.
        if isinstance(value, str) and len(value) > 64:
            continue
        if isinstance(value, (str, int, float, bool)):
            clean[key] = value
    return clean


def capture(
    distinct_id: Optional[str],
    event: str,
    properties: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Records one thing a person did. Returns whether it was sent.

    Never raises. An editor's save must not fail because a telemetry endpoint
    is unreachable.
    """
    client = start()
    if client is None:
        return False

    try:
        client.capture(
            distinct_id=(distinct_id or "@unknown").strip() or "@unknown",
            event=event,
            properties=safe_properties(properties),
        )
        return True
    except Exception as e:
        logger.warning("PostHog capture failed for %r: %s", event, e)
        return False


def shutdown() -> None:
    """Flushes anything queued. Safe to call when nothing was ever configured."""
    if _client is not None:
        try:
            _client.shutdown()
        except Exception as e:
            logger.debug("PostHog shutdown: %s", e)
