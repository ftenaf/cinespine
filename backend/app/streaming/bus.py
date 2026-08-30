"""
In-process event bus: publish a document to a topic, and the handlers
subscribed to that topic run.

# Why there is no broker behind this

There was a Kafka producer here, and a Redpanda container in docker-compose
that nothing ever connected to -- `EventBus` was only ever constructed
`in_memory=True`, so the producer branch was unreachable. Removed on
2026-08-30 rather than wired up, because tracing the ingest path showed a
broker would sit between two functions in the same Python process:

    POST /api/upload -> publish "production.raw.camera"
                     -> dispatcher handler parses, inline
                     -> publish "production.events.spine"
                     -> spine_writer.append_event -> SQLite + ClickHouse
                     -> 200

The durability argument does not hold either: the spine *is* an append-only
log, in SQLite, and the analytical mirror already rebuilds from it. Kafka
would have been a second log with weaker retention guarding the log of record.

This leaves a known gap against REQ-01, recorded in
references/findings/spec-drift.md. It is a decision, not an oversight.

# What this is still for

Real work goes through here. Ingestion reaches the spine writer via
`production.events.spine`, and rejected documents reach telemetry via
`production.events.dlq`. Removing the bus would break ingestion; only the
broker went.
"""
import logging
from typing import Callable, Dict, List, Any

logger = logging.getLogger(__name__)


class EventBus:
    """
    Topic-keyed synchronous dispatch.

    A handler that raises is logged and does not stop the others, so one
    department's parser failing cannot take down the ingest of another's.
    Note that this also means a failed handler is invisible to the caller --
    see the note on `publish`.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}

    def subscribe(self, topic: str, handler: Callable[[Any], None]) -> None:
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)

    def topics(self) -> List[str]:
        """
        The topics that actually have a listener.

        Publishing to a topic nobody subscribed to is silent, and that has
        already caused a bug once: office documents were classified, published
        to `production.raw.office`, and produced nothing while the upload
        reported INGESTED. This makes the wiring inspectable.
        """
        return sorted(self._subscribers)

    def publish(self, topic: str, event: Any) -> None:
        # A handler that raises is logged and swallowed, so the caller still
        # sees success. That is a real hole in the ingest path -- a spine
        # write that fails returns 200 -- and the fix is to acknowledge after
        # the write, not to put a queue in front of it.
        for handler in self._subscribers.get(topic, []):
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in subscriber handler for topic {topic}: {e}")
