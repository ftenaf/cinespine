"""
The event bus after the broker was removed.

Kafka and Redpanda went on 2026-08-30 -- the producer branch was unreachable
and the container accepted no connections. What is left has to keep doing the
work that was actually running through it, and the removal has to stay removed:
a dependency that creeps back would put the architecture diagram back to
claiming something the running system does not do.
"""
import inspect
from pathlib import Path

import pytest

from backend.app.parsers import classifier
from backend.app.streaming.bus import EventBus, EventHandlerError
from backend.app.streaming.dispatcher import IngestionDispatcher
from backend.app.streaming.models import DepartmentType

REPO = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# The broker is gone and stays gone
# --------------------------------------------------------------------------- #

def test_the_bus_has_no_broker_left_in_it():
    source = inspect.getsource(EventBus)
    assert "confluent" not in source.lower()
    assert "producer" not in source.lower()


def test_constructing_a_bus_takes_no_transport_argument():
    """
    `in_memory` had exactly one value at every call site, and the parameter
    invited the belief that the other value did something.
    """
    params = inspect.signature(EventBus.__init__).parameters
    assert list(params) == ["self"]


def test_confluent_kafka_is_not_a_dependency():
    for name in ("backend/requirements.txt", "pyproject.toml"):
        assert "confluent-kafka" not in (REPO / name).read_text(encoding="utf-8"), name


def test_no_broker_container_is_started():
    compose_yaml = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    import yaml
    data = yaml.safe_load(compose_yaml)
    core_services = {k: v for k, v in data.get("services", {}).items() if "posthog" not in v.get("profiles", [])}
    core_str = str(core_services).lower()
    assert "redpanda" not in core_str
    assert "kafka" not in core_str



# --------------------------------------------------------------------------- #
# What the bus still has to do
# --------------------------------------------------------------------------- #

def test_a_published_event_reaches_its_subscribers():
    bus = EventBus()
    seen = []
    bus.subscribe("production.events.spine", seen.append)
    bus.publish("production.events.spine", {"slate": "27/7"})
    assert seen == [{"slate": "27/7"}]


def test_the_event_arrives_as_it_was_sent():
    """
    The Kafka path serialised through `model_dump`; the in-process path never
    did, and handlers read attributes off the envelope.
    """
    bus = EventBus()
    seen = []
    bus.subscribe("t", seen.append)
    sentinel = object()
    bus.publish("t", sentinel)
    assert seen[0] is sentinel


def test_one_failing_handler_does_not_stop_the_others():
    """
    One department's parser raising must not take down the ingest of another's.
    The failure is still reported afterwards -- see test_ack_after_write.py.
    """
    bus = EventBus()
    seen = []
    bus.subscribe("t", lambda e: (_ for _ in ()).throw(ValueError("parser blew up")))
    bus.subscribe("t", seen.append)
    with pytest.raises(EventHandlerError):
        bus.publish("t", {"x": 1})
    assert seen == [{"x": 1}]


def test_publishing_to_a_topic_nobody_listens_on_is_not_an_error():
    EventBus().publish("production.raw.nobody", {"x": 1})


# --------------------------------------------------------------------------- #
# The confident nothing, in the wiring
# --------------------------------------------------------------------------- #

def test_every_department_the_classifier_can_emit_has_a_subscriber():
    """
    The bug this guards against already happened once: office documents were
    classified, published to `production.raw.office`, and produced nothing --
    while the upload reported INGESTED. Publishing to a topic with no listener
    is silent, so the only defence is checking the wiring.

    Two departments in the enum (`editorial`, `vfx`) have no handler. That is
    latent rather than live, because no classification rule emits them; this
    test fails the moment one does.
    """
    bus = EventBus()
    IngestionDispatcher(bus=bus)
    wired = set(bus.topics())

    source = inspect.getsource(classifier)
    emitted = {
        d for d in DepartmentType
        if f"DepartmentType.{d.name}" in source
    }
    assert emitted, "no department found in the classifier at all"

    missing = sorted(d.value for d in emitted if f"production.raw.{d.value}" not in wired)
    assert not missing, (
        f"the classifier can emit {missing} and nothing subscribes to those topics: "
        "such a document would report INGESTED and produce nothing"
    )


@pytest.mark.parametrize("department", ["editorial", "vfx"])
def test_the_departments_with_no_handler_are_the_ones_we_know_about(department):
    """
    Pinned deliberately. If a handler is added, this fails and the note above
    gets corrected rather than quietly going stale.
    """
    bus = EventBus()
    IngestionDispatcher(bus=bus)
    assert f"production.raw.{department}" not in bus.topics()
