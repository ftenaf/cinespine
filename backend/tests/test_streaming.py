"""
TDD Test Suite for Slice 2: Event Bus & Ingestion Stream.

Evidence:
- references/domain/handoffs.md
- references/domain/documents.md
"""
import pytest
from backend.app.streaming.models import EventEnvelope, AxisType, DepartmentType, DocumentType
from backend.app.streaming.bus import EventBus
from backend.app.streaming.dispatcher import IngestionDispatcher
from backend.tests.test_parsers import SAMPLE_SOUND_ALE, SAMPLE_CAMERA_CSV, SAMPLE_SILVERSTACK_XML


class TestEventBusAndEnvelope:
    def test_create_valid_event_envelope(self):
        envelope = EventEnvelope(
            production_id="PROD_TEST_01",
            shoot_day="SD31",
            axis=AxisType.BELIEF,
            department=DepartmentType.SOUND,
            doc_type=DocumentType.SOUND_ALE,
            raw_content=SAMPLE_SOUND_ALE,
        )
        assert envelope.shoot_day == "31"  # Normalized
        assert envelope.axis == "belief"
        assert envelope.event_id is not None
        assert envelope.timestamp is not None

    def test_in_memory_event_bus_publish_and_subscribe(self):
        bus = EventBus()
        received_events = []

        def handler(event: EventEnvelope):
            received_events.append(event)

        bus.subscribe("production.raw.sound", handler)

        event = EventEnvelope(
            production_id="PROD_TEST_01",
            shoot_day="31",
            axis=AxisType.BELIEF,
            department=DepartmentType.SOUND,
            doc_type=DocumentType.SOUND_ALE,
            raw_content=SAMPLE_SOUND_ALE,
        )
        bus.publish("production.raw.sound", event)

        assert len(received_events) == 1
        assert received_events[0].event_id == event.event_id


class TestIngestionDispatcher:
    def test_dispatch_sound_ale_to_spine_events(self):
        bus = EventBus()
        dispatcher = IngestionDispatcher(bus=bus)

        spine_events = []
        dlq_events = []

        bus.subscribe("production.events.spine", lambda e: spine_events.append(e))
        bus.subscribe("production.events.dlq", lambda e: dlq_events.append(e))

        # Publish raw sound ALE
        raw_event = EventEnvelope(
            production_id="PROD_TEST_01",
            shoot_day="SD31",
            axis=AxisType.BELIEF,
            department=DepartmentType.SOUND,
            doc_type=DocumentType.SOUND_ALE,
            raw_content=SAMPLE_SOUND_ALE,
        )
        bus.publish("production.raw.sound", raw_event)

        assert len(dlq_events) == 0
        assert len(spine_events) == 3  # 3 takes in SAMPLE_SOUND_ALE
        assert spine_events[0]["payload"]["slate"] == "27/7"
        assert spine_events[0]["payload"]["take_id"] == "1"

    def test_dispatch_malformed_to_dlq(self):
        bus = EventBus()
        dispatcher = IngestionDispatcher(bus=bus)

        spine_events = []
        dlq_events = []

        bus.subscribe("production.events.spine", lambda e: spine_events.append(e))
        bus.subscribe("production.events.dlq", lambda e: dlq_events.append(e))

        raw_event = EventEnvelope(
            production_id="PROD_TEST_01",
            shoot_day="SD31",
            axis=AxisType.BELIEF,
            department=DepartmentType.SOUND,
            doc_type=DocumentType.SOUND_ALE,
            raw_content="Corrupt empty content",
        )
        bus.publish("production.raw.sound", raw_event)

        assert len(spine_events) == 0
        assert len(dlq_events) == 1
        assert dlq_events[0]["error_type"] == "PARSER_FAILURE"
