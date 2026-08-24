"""
FastAPI Route Handlers for CineSpine.
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Response, UploadFile, File, Form
from pydantic import BaseModel, Field
from backend.app.streaming.models import EventEnvelope, AxisType, DepartmentType, DocumentType
from backend.app.streaming.bus import EventBus
from backend.app.streaming.dispatcher import IngestionDispatcher
from backend.app.spine.writer import SpineWriter
from backend.app.reconciliation.engine import ReconciliationEngine
from backend.app.agents.mcp_server import ClickHouseMCPServer, GeminiDiscrepancyAssistant
from backend.app.parsers.classifier import classify_document, infer_production_and_day
from backend.app.parsers.pdf_parsers import extract_text_from_pdf
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


class CreateProductionRequest(BaseModel):
    production_id: str
    name: str
    director: Optional[str] = None
    description: Optional[str] = None


class UploadRequest(BaseModel):
    raw_content: str
    filename: Optional[str] = None
    production_id: Optional[str] = None
    shoot_day: Optional[str] = None
    axis: Optional[AxisType] = None
    department: Optional[DepartmentType] = None
    doc_type: Optional[DocumentType] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AskAssistantRequest(BaseModel):
    production_id: str
    shoot_day: str
    slate: str
    take_id: str


@router.get("/health")
def health_check():
    return {"status": "ok", "version": "0.1.0", "service": "cinespine"}


@router.get("/productions")
def get_productions():
    """
    Lists all registered studio productions with metrics and active shoot days.
    """
    return spine_writer.list_productions()


@router.post("/productions")
def create_production(req: CreateProductionRequest):
    """
    Registers a new production into the studio workspace.
    """
    return spine_writer.register_production(
        production_id=req.production_id,
        name=req.name,
        director=req.director,
        description=req.description,
    )


@router.post("/upload")
def upload_document(req: UploadRequest):
    """
    Ingests document with automatic type, department, production, and shoot day inference.
    """
    classification = classify_document(filename=req.filename, content=req.raw_content)
    
    # Infer or fallback
    production_id = req.production_id or classification.inferred_production_id or "DEMO_PRODUCTION"
    shoot_day = req.shoot_day or classification.inferred_shoot_day or "31"
    axis = req.axis or classification.axis
    department = req.department or classification.department
    doc_type = req.doc_type or classification.doc_type

    envelope = EventEnvelope(
        production_id=production_id,
        shoot_day=shoot_day,
        axis=axis,
        department=department,
        doc_type=doc_type,
        raw_content=req.raw_content,
        filename=req.filename,
        metadata=req.metadata,
    )

    topic = f"production.raw.{department.value}"
    event_bus.publish(topic, envelope)
    return {
        "status": "INGESTED",
        "event_id": envelope.event_id,
        "production_id": envelope.production_id,
        "shoot_day": envelope.shoot_day,
        "detected_doc_type": doc_type.value,
        "detected_department": department.value,
        "detected_axis": axis.value,
    }


@router.post("/upload/file")
async def upload_document_file(
    file: UploadFile = File(...),
    production_id: Optional[str] = Form(None),
    shoot_day: Optional[str] = Form(None),
):
    """
    Accepts binary PDF, CSV, ALE, or XML file drops and extracts/routes automatically.
    """
    content_bytes = await file.read()
    filename = file.filename or "unknown_drop"

    # Extract text if PDF
    if filename.lower().endswith(".pdf"):
        try:
            raw_text = extract_text_from_pdf(content_bytes)
        except Exception as e:
            raw_text = content_bytes.decode("utf-8", errors="ignore")
    else:
        raw_text = content_bytes.decode("utf-8", errors="ignore")

    classification = classify_document(filename=filename, content=content_bytes)

    # Inferred production & shoot day
    final_prod = production_id or classification.inferred_production_id or "DEMO_PRODUCTION"
    final_day = shoot_day or classification.inferred_shoot_day or "31"

    envelope = EventEnvelope(
        production_id=final_prod,
        shoot_day=final_day,
        axis=classification.axis,
        department=classification.department,
        doc_type=classification.doc_type,
        raw_content=raw_text,
        filename=filename,
        metadata={"file_size": len(content_bytes), "content_type": file.content_type},
    )

    topic = f"production.raw.{classification.department.value}"
    event_bus.publish(topic, envelope)

    return {
        "status": "INGESTED",
        "filename": filename,
        "event_id": envelope.event_id,
        "production_id": final_prod,
        "shoot_day": final_day,
        "detected_doc_type": classification.doc_type.value,
        "detected_department": classification.department.value,
        "detected_axis": classification.axis.value,
        "is_multimodal": classification.is_multimodal,
    }


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
