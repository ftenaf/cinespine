"""
ClickHouse Append-Only Event Writer.
"""
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class SpineWriter:
    def __init__(self, clickhouse_client=None):
        self.client = clickhouse_client
        self._in_memory_spine: List[Dict[str, Any]] = []

    def append_event(self, event: Dict[str, Any]) -> None:
        """
        Appends an event to the immutable spine.
        """
        self._in_memory_spine.append(event)

        if self.client:
            try:
                row = [
                    event.get("event_id"),
                    event.get("production_id"),
                    event.get("shoot_day"),
                    event.get("axis"),
                    event.get("department"),
                    event.get("doc_type"),
                    event.get("entity_type"),
                    json.dumps(event.get("payload", {})),
                    json.dumps(event.get("metadata", {})),
                ]
                self.client.insert(
                    "cinespine.production_events",
                    [row],
                    column_names=[
                        "event_id",
                        "production_id",
                        "shoot_day",
                        "axis",
                        "department",
                        "doc_type",
                        "entity_type",
                        "payload_json",
                        "metadata_json",
                    ],
                )
            except Exception as e:
                logger.error(f"Failed to append event to ClickHouse: {e}")

    def get_events(self, production_id: Optional[str] = None, shoot_day: Optional[str] = None) -> List[Dict[str, Any]]:
        events = self._in_memory_spine
        if production_id:
            events = [e for e in events if e.get("production_id") == production_id]
        if shoot_day:
            events = [e for e in events if e.get("shoot_day") == shoot_day]
        return events
