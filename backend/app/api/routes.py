"""
FastAPI Route Handlers for CineSpine.
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from backend.app.streaming.models import EventEnvelope, AxisType, DepartmentType, DocumentType
from backend.app.streaming.bus import EventBus
from backend.app.streaming.dispatcher import IngestionDispatcher
from backend.app.spine.writer import SpineWriter
from backend.app.reconciliation.engine import ReconciliationEngine
from backend.app.agents.mcp_server import ClickHouseMCPServer, GeminiDiscrepancyAssistant
from backend.app.core.telemetry import TelemetryExporter

router = APIRouter(prefix="/api")

# Singletons for service components
event_bus = EventBus(in_memory=True)
dispatcher = IngestionDispatcher(bus=event_bus)
spine_writer = SpineWriter()
reconciler = ReconciliationEngine()
mcp_server = ClickHouseMCPServer(spine_writer=spine_writer, reconciler=reconciler)
assistant = GeminiDiscrepancyAssistant(mcp_server=mcp_server)

# Forward spine events to writer & telemetry
event_bus.subscribe("production.events.spine", lambda e: (
    spine_writer.append_event(e),
    TelemetryExporter.record_ingest(e.get("department", "unknown"), e.get("axis", "unknown"))
))
event_bus.subscribe("production.events.dlq", lambda e: (
    TelemetryExporter.record_rejection(e.get("doc_type", "unknown"), e.get("error_type", "unknown"))
))


class UploadRequest(BaseModel):
    production_id: str
    shoot_day: str
    axis: AxisType
    department: DepartmentType
    doc_type: DocumentType
    raw_content: str
    filename: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AskAssistantRequest(BaseModel):
    production_id: str
    shoot_day: str
    slate: str
    take_id: str


@router.get("/health")
def health_check():
    return {"status": "ok", "version": "0.1.0", "service": "cinespine"}


@router.post("/upload")
def upload_document(req: UploadRequest):
    envelope = EventEnvelope(
        production_id=req.production_id,
        shoot_day=req.shoot_day,
        axis=req.axis,
        department=req.department,
        doc_type=req.doc_type,
        raw_content=req.raw_content,
        filename=req.filename,
        metadata=req.metadata,
    )
    # Route topic based on department
    topic = f"production.raw.{req.department.value}"
    event_bus.publish(topic, envelope)
    return {"status": "INGESTED", "event_id": envelope.event_id, "shoot_day": envelope.shoot_day}


@router.get("/takes")
def get_takes(production_id: str, shoot_day: str) -> List[Dict[str, Any]]:
    events = spine_writer.get_events(production_id=production_id, shoot_day=shoot_day)
    takes_map: Dict[str, Dict[str, Any]] = {}

    for evt in events:
        if evt.get("entity_type") == "take":
            p = evt.get("payload", {})
            slate = p.get("slate")
            take_id = p.get("take_id")
            if slate and take_id:
                key = f"{slate}_{take_id}"
                if key not in takes_map:
                    takes_map[key] = {
                        "slate": slate,
                        "take_id": take_id,
                        "intent": None,
                        "belief": {},
                        "existence": {},
                        "is_starred": False,
                        "is_pickup": False,
                    }
                dept = evt.get("department", "unknown")
                takes_map[key]["belief"][dept] = p
                if p.get("is_starred"):
                    takes_map[key]["is_starred"] = True
                if p.get("is_pickup"):
                    takes_map[key]["is_pickup"] = True

    return list(takes_map.values())


@router.get("/discrepancies")
def get_discrepancies(production_id: str, shoot_day: str) -> List[Dict[str, Any]]:
    return mcp_server.query_production_discrepancies(production_id=production_id, shoot_day=shoot_day)


@router.post("/assistant/explain")
def explain_take(req: AskAssistantRequest):
    explanation = assistant.explain_take(
        production_id=req.production_id,
        shoot_day=req.shoot_day,
        slate=req.slate,
        take_id=req.take_id,
    )
    return {"explanation": explanation}


@router.get("/metrics")
def get_prometheus_metrics():
    return Response(
        content=TelemetryExporter.get_metrics_payload(),
        media_type=TelemetryExporter.get_content_type(),
    )
