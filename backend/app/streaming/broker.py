"""
Live Event Broker & SSE Subscription Manager for Real-Time CineSpine Collaboration.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, Optional, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SpineLiveEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:10]}")
    event_type: str  # e.g., "DOCUMENT_INGESTED", "DOCUMENT_DELETED", "REQUIREMENT_CREATED", "REQUIREMENT_RESOLVED", "DISCREPANCY_RESOLVED", "DISCREPANCY_UNRESOLVED"
    production_id: str
    shoot_day: str
    actor_handle: str = "@system"
    target_type: Optional[str] = None  # "document", "take", "shot", "scene", "discrepancy"
    target_id: Optional[str] = None
    target_label: Optional[str] = None
    summary: str
    data: Optional[Dict[str, Any]] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())



class SSESubscriber:
    def __init__(
        self,
        subscriber_id: str,
        production_id: Optional[str] = None,
        shoot_day: Optional[str] = None,
        user_handle: Optional[str] = None,
    ):
        self.subscriber_id = subscriber_id
        self.production_id = production_id
        self.shoot_day = shoot_day
        self.user_handle = user_handle
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.events: list = []

    def matches(self, event: SpineLiveEvent) -> bool:
        # If subscriber specified a production_id, check match
        if self.production_id and self.production_id != "ALL" and event.production_id != "ALL":
            if self.production_id != event.production_id:
                return False
        # If subscriber specified a shoot_day, check match
        if self.shoot_day and self.shoot_day != "ALL" and event.shoot_day != "ALL":
            if self.shoot_day != event.shoot_day:
                return False
        return True


class LiveEventBroker:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LiveEventBroker, cls).__new__(cls)
            cls._instance._subscribers = {}
            cls._instance._setup_pubsub()
        return cls._instance

    def _setup_pubsub(self):
        import os
        self.project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.topic_id = os.environ.get("PUBSUB_TOPIC_ID")
        self.subscription_id = os.environ.get("PUBSUB_SUBSCRIPTION_ID")
        self.publisher = None
        self.subscriber = None
        self.topic_path = None
        
        if self.project_id and self.topic_id:
            try:
                from google.cloud import pubsub_v1
                self.publisher = pubsub_v1.PublisherClient()
                self.topic_path = self.publisher.topic_path(self.project_id, self.topic_id)
                logger.info(f"Pub/Sub initialized for topic: {self.topic_path}")
                
                if self.subscription_id:
                    self.subscriber = pubsub_v1.SubscriberClient()
                    subscription_path = self.subscriber.subscription_path(self.project_id, self.subscription_id)
                    self.subscriber.subscribe(subscription_path, callback=self._pubsub_callback)
                    logger.info(f"Pub/Sub subscriber listening on: {subscription_path}")
            except Exception as e:
                logger.warning(f"Failed to initialize Pub/Sub (fallback to local): {e}")
                self.publisher = None

    def _pubsub_callback(self, message):
        try:
            payload = message.data.decode("utf-8")
            event_data = json.loads(payload)
            event = SpineLiveEvent(**event_data)
            self._broadcast_nowait(event)
            message.ack()
        except Exception as exc:
            logger.error(f"Error processing Pub/Sub message: {exc}")
            message.nack()

    def register_subscriber(
        self,
        production_id: Optional[str] = None,
        shoot_day: Optional[str] = None,
        user_handle: Optional[str] = None,
    ) -> SSESubscriber:
        from backend.app.core.telemetry import TelemetryExporter
        sub_id = f"sub_{uuid.uuid4().hex[:8]}"
        subscriber = SSESubscriber(sub_id, production_id, shoot_day, user_handle)
        self._subscribers[sub_id] = subscriber
        
        role = user_handle or "anonymous"
        TelemetryExporter.record_sse_connection(role, +1)
        
        logger.info(f"Registered SSE subscriber {sub_id} (prod={production_id}, day={shoot_day}). Total: {len(self._subscribers)}")
        return subscriber

    def unregister_subscriber(self, subscriber_id: str) -> None:
        from backend.app.core.telemetry import TelemetryExporter
        if subscriber_id in self._subscribers:
            sub = self._subscribers[subscriber_id]
            role = sub.user_handle or "anonymous"
            TelemetryExporter.record_sse_connection(role, -1)
            
            del self._subscribers[subscriber_id]
            logger.info(f"Unregistered SSE subscriber {subscriber_id}. Total: {len(self._subscribers)}")

    def publish_sync(self, event: SpineLiveEvent) -> None:
        """Synchronous wrapper to publish an event from synchronous endpoints or background threads."""
        if self.publisher and self.topic_path:
            try:
                data = event.model_dump_json().encode("utf-8")
                self.publisher.publish(self.topic_path, data)
            except Exception as exc:
                logger.warning(f"Failed to publish to Pub/Sub: {exc}")
                self._broadcast_nowait(event)
        else:
            self._broadcast_nowait(event)

    async def publish(self, event: SpineLiveEvent) -> None:
        """Broadcasts event to all matching subscribers."""
        if self.publisher and self.topic_path:
            loop = asyncio.get_running_loop()
            try:
                data = event.model_dump_json().encode("utf-8")
                # Fire and forget over Pub/Sub
                await loop.run_in_executor(None, self.publisher.publish, self.topic_path, data)
            except Exception as exc:
                logger.warning(f"Failed to publish to Pub/Sub: {exc}")
                self._broadcast_nowait(event)
        else:
            self._broadcast_nowait(event)

    def _broadcast_nowait(self, event: SpineLiveEvent) -> None:
        dead_subscribers = []
        for sub_id, sub in list(self._subscribers.items()):
            if sub.matches(event):
                sub.events.append(event)
                try:
                    sub.queue.put_nowait(event)
                except asyncio.QueueFull:
                    try:
                        _ = sub.queue.get_nowait()
                        sub.queue.put_nowait(event)
                    except Exception as exc:
                        logger.debug("Subscriber queue drop failed: %s", exc)
                except Exception as e:
                    logger.debug(f"Queue push notice for subscriber {sub_id}: {e}")

        for sub_id in dead_subscribers:
            self._subscribers.pop(sub_id, None)

    async def stream_events(
        self,
        production_id: Optional[str] = None,
        shoot_day: Optional[str] = None,
        user_handle: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Async generator yielding SSE formatted strings."""
        subscriber = self.register_subscriber(production_id, shoot_day, user_handle)
        # Ensure queue is bound to current running event loop in Python 3.10/3.11
        subscriber.queue = asyncio.Queue(maxsize=100)
        try:
            # Yield initial connection confirmation event
            init_payload = {
                "event_type": "CONNECTED",
                "subscriber_id": subscriber.subscriber_id,
                "production_id": production_id,
                "shoot_day": shoot_day,
                "user_handle": user_handle,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"event: connected\ndata: {json.dumps(init_payload)}\n\n"

            while True:
                try:
                    # Wait for next event or timeout for ping
                    event = await asyncio.wait_for(subscriber.queue.get(), timeout=15.0)
                    data_str = json.dumps(event.model_dump())
                    yield f"event: message\ndata: {data_str}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat ping every 15s
                    ping_payload = {"ping": datetime.now(timezone.utc).isoformat()}
                    yield f"event: ping\ndata: {json.dumps(ping_payload)}\n\n"
        finally:
            self.unregister_subscriber(subscriber.subscriber_id)


# Global singleton broker instance
event_broker = LiveEventBroker()
