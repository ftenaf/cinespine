"""
ClickHouse Append-Only Event Writer, Multi-Production & Document Store.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Registered productions registry
DEFAULT_PRODUCTIONS = {
    "DEMO_PRODUCTION": {
        "production_id": "DEMO_PRODUCTION",
        "name": "La Cathédrale",
        "director": "Director",
        "status": "In Production",
        "description": "Historical drama shooting in Cremona & Madrid",
    },
    "DUNE_3": {
        "production_id": "DUNE_3",
        "name": "Dune: Messiah",
        "director": "Denis Villeneuve",
        "status": "Principal Photography",
        "description": "Sci-fi feature film",
    },
    "PROD_01": {
        "production_id": "PROD_01",
        "name": "Demo Production 01",
        "director": "Demo Unit",
        "status": "Active",
        "description": "Hackathon sandbox production",
    },
}


class SpineWriter:
    def __init__(self, clickhouse_client=None):
        self.client = clickhouse_client
        self._in_memory_spine: List[Dict[str, Any]] = []
        self._productions: Dict[str, Dict[str, Any]] = dict(DEFAULT_PRODUCTIONS)
        self._documents: Dict[str, Dict[str, Any]] = {}

    def store_document(
        self,
        production_id: str,
        shoot_day: str,
        filename: str,
        doc_type: str,
        department: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Stores raw document text/content with metadata for in-app previewing.
        """
        doc_id = str(uuid.uuid4())
        doc_record = {
            "doc_id": doc_id,
            "production_id": production_id,
            "shoot_day": shoot_day,
            "filename": filename,
            "doc_type": doc_type,
            "department": department,
            "content": content,
            "size_bytes": len(content.encode("utf-8")),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        self._documents[doc_id] = doc_record
        return doc_id

    def list_documents(self, production_id: Optional[str] = None, shoot_day: Optional[str] = None) -> List[Dict[str, Any]]:
        docs = list(self._documents.values())
        if production_id:
            docs = [d for d in docs if d.get("production_id") == production_id]
        if shoot_day:
            docs = [d for d in docs if d.get("shoot_day") == shoot_day]
        
        # Return summary without full heavy content
        return [
            {
                "doc_id": d["doc_id"],
                "production_id": d["production_id"],
                "shoot_day": d["shoot_day"],
                "filename": d["filename"],
                "doc_type": d["doc_type"],
                "department": d["department"],
                "size_bytes": d["size_bytes"],
                "uploaded_at": d["uploaded_at"],
            }
            for d in docs
        ]

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        return self._documents.get(doc_id)

    def append_event(self, event: Dict[str, Any]) -> None:
        """
        Appends an event to the immutable spine.
        """
        self._in_memory_spine.append(event)

        prod_id = event.get("production_id")
        if prod_id and prod_id not in self._productions:
            self._productions[prod_id] = {
                "production_id": prod_id,
                "name": prod_id.replace("_", " ").title(),
                "director": "Unknown",
                "status": "Active",
                "description": "Auto-registered production",
            }

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

    def list_productions(self) -> List[Dict[str, Any]]:
        """
        Summarizes all registered productions with active days, event counts, and take counts.
        """
        results = []
        for prod_id, info in self._productions.items():
            prod_events = [e for e in self._in_memory_spine if e.get("production_id") == prod_id]
            
            # Find unique shoot days
            days = sorted(
                list({e.get("shoot_day") for e in prod_events if e.get("shoot_day")}),
                key=lambda x: int(x) if x.isdigit() else 999
            )
            
            # Find unique takes
            takes = {
                f"{e.get('payload', {}).get('slate')}_{e.get('payload', {}).get('take_id')}"
                for e in prod_events
                if e.get("entity_type") == "take"
            }

            last_ts = prod_events[-1].get("timestamp") if prod_events else None

            results.append({
                **info,
                "shoot_days": days,
                "total_events": len(prod_events),
                "total_takes": len(takes),
                "last_activity": last_ts,
            })
        return results

    def register_production(self, production_id: str, name: str, director: Optional[str] = None, description: Optional[str] = None) -> Dict[str, Any]:
        info = {
            "production_id": production_id,
            "name": name,
            "director": director or "Main Unit",
            "status": "Active",
            "description": description or "",
        }
        self._productions[production_id] = info
        return info
