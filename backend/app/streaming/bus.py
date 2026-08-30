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

# Failure is reported, not swallowed

`publish` used to log a handler exception and return, so a spine write that
failed still produced a 200 INGESTED -- the confident nothing, in the ingest
path. It now raises `EventHandlerError` after running the handlers, which
keeps them isolated from each other while making the failure impossible to
miss.
"""
import logging
from typing import Callable, Dict, List, Any, Tuple

logger = logging.getLogger(__name__)


class EventHandlerError(Exception):
    """
    One or more subscribers on a topic failed.

    Raised after every handler has run, so it says what went wrong without
    having decided on the caller's behalf that the rest should be skipped.

    This is not a rejected document. A document the parsers refuse is a
    legitimate outcome and goes to the DLQ; this means the machinery underneath
    failed -- the spine write did not land, most likely -- and whoever uploaded
    must not be told INGESTED.
    """

    def __init__(self, topic: str, failures: List[Tuple[Callable[[Any], None], Exception]]):
        self.topic = topic
        self.failures = failures
        reasons = "; ".join(f"{type(e).__name__}: {e}" for _, e in failures)
        super().__init__(f"{len(failures)} handler(s) failed on '{topic}': {reasons}")

    @property
    def reasons(self) -> List[str]:
        return [f"{type(e).__name__}: {e}" for _, e in self.failures]


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
        """
        Runs every handler on the topic, then reports what failed.

        Two things have to be true at once, and they pull in opposite
        directions. One department's parser blowing up must not stop another
        department's document from being ingested -- so every handler runs,
        and one raising does not skip the rest. But a handler that failed
        means work that did not happen, and the caller has to be able to know
        that, or it will acknowledge an ingest that never landed.

        So: isolate, then raise. Failures are collected while the handlers run
        and reported together afterwards as `EventHandlerError`. A caller that
        wants the old behaviour has to catch it deliberately, which is the
        point -- silence should be a decision somebody made, not the default.
        """
        failures: List[Tuple[Callable[[Any], None], Exception]] = []

        for handler in self._subscribers.get(topic, []):
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in subscriber handler for topic {topic}: {e}")
                failures.append((handler, e))

        if failures:
            raise EventHandlerError(topic, failures)
