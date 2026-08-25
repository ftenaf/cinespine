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
        self.queue: asyncio.Queue[SpineLiveEvent] = asyncio.Queue(maxsize=100)

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
        return cls._instance

    async def register_subscriber(
        self,
        production_id: Optional[str] = None,
        shoot_day: Optional[str] = None,
        user_handle: Optional[str] = None,
    ) -> SSESubscriber:
        sub_id = f"sub_{uuid.uuid4().hex[:8]}"
        subscriber = SSESubscriber(
            subscriber_id=sub_id,
            production_id=production_id,
            shoot_day=shoot_day,
            user_handle=user_handle,
        )
        self._subscribers[sub_id] = subscriber
        logger.info(f"Registered SSE subscriber {sub_id} for prod={production_id}, day={shoot_day}, user={user_handle}. Total: {len(self._subscribers)}")
        return subscriber

    async def unregister_subscriber(self, subscriber_id: str) -> None:
        if subscriber_id in self._subscribers:
            del self._subscribers[subscriber_id]
            logger.info(f"Unregistered SSE subscriber {subscriber_id}. Total: {len(self._subscribers)}")

    def publish_sync(self, event: SpineLiveEvent) -> None:
        """Synchronous wrapper to publish an event from synchronous endpoints or background threads."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(event))
        except RuntimeError:
            self._broadcast_nowait(event)

    async def publish(self, event: SpineLiveEvent) -> None:
        """Broadcasts event to all matching subscribers."""
        self._broadcast_nowait(event)

    def _broadcast_nowait(self, event: SpineLiveEvent) -> None:
        dead_subscribers = []
        for sub_id, sub in list(self._subscribers.items()):
            if sub.matches(event):
                try:
                    sub.queue.put_nowait(event)
                except asyncio.QueueFull:
                    try:
                        _ = sub.queue.get_nowait()
                        sub.queue.put_nowait(event)
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"Error publishing to subscriber {sub_id}: {e}")
                    dead_subscribers.append(sub_id)

        for sub_id in dead_subscribers:
            self._subscribers.pop(sub_id, None)

    async def stream_events(
        self,
        production_id: Optional[str] = None,
        shoot_day: Optional[str] = None,
        user_handle: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Async generator yielding SSE formatted strings."""
        subscriber = await self.register_subscriber(production_id, shoot_day, user_handle)
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
                    payload = event.model_dump()
                    yield f"event: message\ndata: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    # Yield heartbeat keep-alive ping
                    yield f": ping\n\n"
        except asyncio.CancelledError:
            logger.info(f"SSE client disconnected for {subscriber.subscriber_id}")
        finally:
            await self.unregister_subscriber(subscriber.subscriber_id)


# Global singleton broker instance
event_broker = LiveEventBroker()
