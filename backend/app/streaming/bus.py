"""
Event Bus Abstraction for Confluent Kafka and In-Memory Testing.
"""
import json
import logging
from typing import Callable, Dict, List, Any, Optional
from backend.app.streaming.models import EventEnvelope

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self, in_memory: bool = True, kafka_bootstrap_servers: Optional[str] = None):
        self.in_memory = in_memory
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}
        self._kafka_producer = None

        if not in_memory and kafka_bootstrap_servers:
            try:
                from confluent_kafka import Producer
                self._kafka_producer = Producer({"bootstrap.servers": kafka_bootstrap_servers})
                logger.info(f"Connected to Kafka broker at {kafka_bootstrap_servers}")
            except Exception as e:
                logger.warning(f"Kafka unavailable ({e}), falling back to in-memory event bus")
                self.in_memory = True

    def subscribe(self, topic: str, handler: Callable[[Any], None]) -> None:
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)

    def publish(self, topic: str, event: Any) -> None:
        # Convert Pydantic models to dict if necessary
        payload = event.model_dump() if hasattr(event, "model_dump") else event

        # 1. Deliver to in-memory subscribers
        if topic in self._subscribers:
            for handler in self._subscribers[topic]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Error in subscriber handler for topic {topic}: {e}")

        # 2. Publish to Kafka if connected
        if not self.in_memory and self._kafka_producer:
            try:
                msg_bytes = json.dumps(payload).encode("utf-8")
                self._kafka_producer.produce(topic, value=msg_bytes)
                self._kafka_producer.poll(0)
            except Exception as e:
                logger.error(f"Failed to publish message to Kafka topic {topic}: {e}")
