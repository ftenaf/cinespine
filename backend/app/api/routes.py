import logging
import asyncio
import os
import re
import uuid
from datetime import datetime, timezone
import hashlib
from dataclasses import asdict
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Response, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from backend.app.streaming.models import EventEnvelope, AxisType, DepartmentType, DocumentType
from backend.app.streaming.bus import EventBus, EventHandlerError
from backend.app.streaming.dispatcher import IngestionDispatcher
from backend.app.streaming.broker import event_broker, SpineLiveEvent
from backend.app.spine.writer import SpineWriter
from backend.app.spine import activity_store, analytics as spine_analytics
from backend.app.spine import production_store
from backend.app.spine import crew_store
from backend.app.spine import requirement_store
from backend.app.spine import workload
from backend.app.spine import breakdown_store
from backend.app.spine import tag_store
from backend.app.reconciliation.engine import ReconciliationEngine
from backend.app.agents.mcp_server import ClickHouseMCPServer, GeminiDiscrepancyAssistant
from backend.app.agents.editorial_queue import (
    ACTIVE_PRODUCTION_STATUSES,
    ASSISTANT_QUEUE_ACTOR,
    AssistantEditorQueueAgent,
    assistant_queue_requirements,
    pre_editing_progress,
)
from backend.app.agents.wrap_rescue import WRAP_RESCUE_ACTOR, WrapRescueAgent
from backend.app.parsers.classifier import classify_document, infer_production_and_day
from backend.app.agents.multimodal import extract_lined_page_if_enabled
from backend.app.agents.camera_report_vision import read_camera_report_if_enabled
from backend.app.parsers.pdf_parsers import extract_text_from_pdf, extract_thumbnails_from_pdf
from backend.app.normalizers.takes import normalize_take
from backend.app.normalizers.slates import normalize_slate
from backend.app.script.scene_lookup import build_scene_context, scene_numbers_for_target
from backend.app.core.telemetry import SPAN_INGEST, TelemetryExporter, app_version, set_attributes, span
from backend.app.core import analytics
from backend.app.core import privacy
from backend.app.storage.gcs_client import gcs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Singletons for service components
event_bus = EventBus()
dispatcher = IngestionDispatcher(bus=event_bus)
spine_writer = SpineWriter()
reconciler = ReconciliationEngine()
mcp_server = ClickHouseMCPServer(spine_writer=spine_writer, reconciler=reconciler)
assistant = GeminiDiscrepancyAssistant(mcp_server=mcp_server)

def _hours_between(started: Optional[str], ended: Optional[str]) -> Optional[float]:
    """
    Hours from one ISO timestamp to another, or to now when the second is None.

    Rounded to one decimal: the question is "did this sit for a day or a week",
    and a full float would imply a precision the timestamps do not have.
    """
    from datetime import datetime, timezone

    if not started:
        return None
    try:
        begin = datetime.fromisoformat(started)
        if begin.tzinfo is None:
            begin = begin.replace(tzinfo=timezone.utc)
        finish = datetime.now(timezone.utc)
        if ended:
            finish = datetime.fromisoformat(ended)
            if finish.tzinfo is None:
                finish = finish.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return round(max(0.0, (finish - begin).total_seconds() / 3600), 1)


def _project_analytics(production_id: str, shoot_day: str) -> None:
    """
    Refreshes the analytical indexes after an ingestion.

    Only when a ClickHouse is connected, and never fatal: these are indexes for
    querying, and an ingestion must not fail because a reporting database is
    unhappy. Done once per document rather than per event, for the same reason
    the event insert is batched.
    """
    if not spine_writer.client:
        return
    try:
        # Every day, not the one the document arrived under. A facing page is
        # filed on the day it is handed over and carries takes from every day
        # the scene was covered; projecting only the envelope's day left sixty
        # takes in the spine and out of the index.
        spine_writer.project_takes(production_id)
        days = {
            e.get("shoot_day") for e in spine_writer.get_events(production_id=production_id)
            if e.get("shoot_day")
        }
        for day in sorted(days or {shoot_day}):
            spine_writer.project_discrepancies(
                mcp_server.query_production_discrepancies(
                    production_id=production_id, shoot_day=day)
            )
    except Exception as exc:
        logger.warning("Could not refresh the analytical indexes: %s", exc)


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
    status: Optional[str] = None


class UpdateProductionRequest(BaseModel):
    """
    Every field optional: a rename must not require restating the description.

    production_id is absent on purpose. It is the key every event, tag and
    script link is filed under, so changing it would orphan all of them.
    """
    name: Optional[str] = None
    director: Optional[str] = None
    status: Optional[str] = None
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


class ResolveDiscrepancyRequest(BaseModel):
    production_id: str = "DEMO_PRODUCTION"
    shoot_day: str = "31"
    entity_id: Optional[str] = None
    resolved_card: Optional[str] = None
    resolution_note: Optional[str] = None
    resolved_by: Optional[str] = "Assistant Editor"


class LoginRequest(BaseModel):
    handle_or_email: str


class CreateRequirementRequest(BaseModel):
    production_id: str = "DEMO_PRODUCTION"
    shoot_day: str = "31"
    target_type: str = "take"  # "scene", "shot", "take"
    target_id: str
    target_label: Optional[str] = None
    title: str
    description: Optional[str] = ""
    priority: Optional[str] = "medium"
    category: Optional[str] = "general"
    created_by: Optional[str] = "@director"
    assigned_to: str


class UpdateRequirementRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Optional[str] = None
    target_label: Optional[str] = None
    # Who is making the change. Requirements can now be reassigned and blocked
    # from a production-wide board, where the person doing it is usually not
    # the person who raised the requirement or the one it is assigned to.
    updated_by: Optional[str] = None


class ResolveRequirementRequest(BaseModel):
    resolution_note: str
    resolved_by: str = "@user"


class UpsertCrewMemberRequest(BaseModel):
    handle: str
    name: str
    email: Optional[str] = ""
    role: str = "Assistant Editor"
    department: str = "editorial"
    active: bool = True


class UpdateCrewMemberRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    active: Optional[bool] = None


class RunWrapRescueRequest(BaseModel):
    production_id: str = "DEMO_PRODUCTION"
    shoot_day: str = "31"
    actor: str = WRAP_RESCUE_ACTOR
    max_blockers: int = Field(default=5, ge=1, le=12)


class RunAssistantQueueRequest(BaseModel):
    production_id: str = "DEMO_PRODUCTION"
    shoot_day: Optional[str] = None
    actor: str = ASSISTANT_QUEUE_ACTOR
    assignee: Optional[str] = None
    max_scenes: int = Field(default=6, ge=1, le=20)


def _require_active_production(production_id: str) -> Dict[str, Any]:
    production = spine_writer.get_production(production_id)
    if not production:
        raise HTTPException(status_code=404, detail=f"No production {production_id}")
    status = production.get("status") or "Active"
    if status not in ACTIVE_PRODUCTION_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{production['production_id']} is {status}; production crew and assistant "
                "editor batches are read-only after the production is finished."
            ),
        )
    return production


def _record_crew_change(
    production: Dict[str, Any],
    action: str,
    actor: str,
    member: Optional[Dict[str, Any]] = None,
    handle: Optional[str] = None,
) -> None:
    target_handle = handle or (member or {}).get("handle") or ""
    payload = member or {"handle": target_handle}
    spine_writer.append_event({
        "event_id": str(uuid.uuid4()),
        "production_id": production["production_id"],
        "shoot_day": "ALL",
        "axis": "intent",
        "department": "production",
        "doc_type": "production_crew_event",
        "entity_type": "production_crew",
        "payload": payload,
        "metadata": {
            "action": action,
            "actor": actor,
            "handle": target_handle,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    event_broker.publish_sync(SpineLiveEvent(
        event_type="PRODUCTION_CREW_UPDATED",
        production_id=production["production_id"],
        shoot_day="ALL",
        actor_handle=actor,
        target_type="production",
        target_id=production["production_id"],
        target_label=production["name"],
        summary=f"Crew {action}: {target_handle}",
        data={"action": action, "member": member, "handle": target_handle},
    ))


@router.get("/health")
def health_check():
    """Is the process up. Cloud Run's startup probe; it checks nothing else."""
    return {"status": "ok", "version": app_version(), "service": "cinespine"}


@router.get("/health/deep")
async def deep_health_check(mcp: bool = False):
    """
    Can the service do its job: SQLite takes a write, ClickHouse answers,
    and -- only when asked, because it scales to zero -- the MCP server
    speaks. 503 when the spine is down, 200 otherwise, with each check
    named and timed. See backend/app/core/health.py.
    """
    from backend.app.agents.wrap_rescue import HTTPClickHouseMCPClient
    from backend.app.core import health

    report = await health.deep_health(
        spine_writer,
        mcp_client=HTTPClickHouseMCPClient(timeout=25.0) if mcp else None,  # cold start is ~21s
        version=app_version(),
    )
    return JSONResponse(report, status_code=503 if report["status"] == "down" else 200)


@router.get("/events/subscribe")
async def subscribe_events(
    production_id: Optional[str] = "ALL",
    shoot_day: Optional[str] = "ALL",
    user_handle: Optional[str] = None,
):
    """
    Server-Sent Events (SSE) stream endpoint for real-time collaboration.
    Clients receive instant broadcasts when paperwork is ingested, requirements are updated,
    or discrepancies are resolved.
    """
    return StreamingResponse(
        event_broker.stream_events(
            production_id=production_id if production_id != "ALL" else None,
            shoot_day=shoot_day if shoot_day != "ALL" else None,
            user_handle=user_handle,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )



@router.get("/productions")
def get_productions():
    return spine_writer.list_productions()


@router.get("/productions/vocabulary")
def get_production_vocabulary():
    """The statuses a production may be in, so the UI offers exactly these."""
    return {"statuses": list(production_store.STATUSES)}


@router.post("/productions")
def create_production(req: CreateProductionRequest):
    try:
        return spine_writer.register_production(
            production_id=req.production_id,
            name=req.name,
            director=req.director,
            description=req.description,
            status=req.status,
        )
    except production_store.UnknownProductionField as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/productions/{production_id}")
def get_production(production_id: str):
    production = spine_writer.get_production(production_id)
    if not production:
        raise HTTPException(status_code=404, detail=f"No production {production_id}")
    return production


@router.patch("/productions/{production_id}")
def update_production(production_id: str, req: UpdateProductionRequest):
    """Edits a production's metadata. Its id, and so its data, are untouched."""
    try:
        updated = spine_writer.update_production(
            production_id, req.model_dump(exclude_unset=True)
        )
    except production_store.UnknownProductionField as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail=f"No production {production_id}")
    return updated


@router.delete("/productions/{production_id}")
def delete_production(production_id: str):
    """
    Removes an empty production from the registry.

    Refused while anything is filed under it. Deleting a production here would
    not delete its events, tags or script link -- it would only hide them,
    leaving work nobody can reach and a day's paperwork that belongs to no
    production. A mistyped registration is the case this exists for.
    """
    key = production_store.normalize_production_id(production_id)
    if not spine_writer.get_production(key):
        raise HTTPException(status_code=404, detail=f"No production {key}")

    holding = []
    event_count = spine_writer.count_production_events(key)
    if event_count:
        holding.append(f"{event_count} event{'s' if event_count != 1 else ''}")
    tag_count = len(spine_writer.list_editorial_tags(key))
    if tag_count:
        holding.append(f"{tag_count} editorial tag{'s' if tag_count != 1 else ''}")
    if spine_writer.get_production_script(key):
        holding.append("a linked screenplay")

    if holding:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{key} still holds {', '.join(holding)}. Deleting the production "
                "would hide that work rather than remove it."
            ),
        )

    return {"deleted": spine_writer.delete_production(key), "production_id": key}


# ==========================================
# Production Crew
# ==========================================
@router.get("/productions/{production_id}/crew")
def list_production_crew(production_id: str, active_only: bool = False):
    production = spine_writer.get_production(production_id)
    if not production:
        raise HTTPException(status_code=404, detail=f"No production {production_id}")
    return spine_writer.list_production_crew(production["production_id"], active_only=active_only)


@router.post("/productions/{production_id}/crew")
def upsert_production_crew_member(production_id: str, req: UpsertCrewMemberRequest):
    production = _require_active_production(production_id)
    try:
        member = spine_writer.upsert_production_crew_member({
            **req.model_dump(),
            "production_id": production["production_id"],
        })
    except crew_store.UnknownCrewValue as e:
        raise HTTPException(status_code=422, detail=str(e))

    _record_crew_change(production, "upserted", member["handle"], member=member)
    return member


@router.patch("/productions/{production_id}/crew/{handle}")
def update_production_crew_member(
    production_id: str,
    handle: str,
    req: UpdateCrewMemberRequest,
):
    production = _require_active_production(production_id)
    try:
        member = spine_writer.update_production_crew_member(
            production["production_id"],
            handle,
            req.model_dump(exclude_unset=True),
        )
    except crew_store.UnknownCrewValue as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not member:
        raise HTTPException(status_code=404, detail=f"No crew member {handle} on {production_id}")
    _record_crew_change(production, "updated", member["handle"], member=member)
    return member


@router.delete("/productions/{production_id}/crew/{handle}")
def delete_production_crew_member(production_id: str, handle: str):
    production = _require_active_production(production_id)
    deleted = spine_writer.delete_production_crew_member(production["production_id"], handle)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No crew member {handle} on {production_id}")
    _record_crew_change(production, "deleted", handle, handle=handle)
    return {"deleted": True, "production_id": production["production_id"], "handle": handle}


@router.get("/documents")
def list_documents(production_id: Optional[str] = None, shoot_day: Optional[str] = None):
    """
    Returns list of all source documents uploaded for previewing.
    """
    return spine_writer.list_documents(production_id=production_id, shoot_day=shoot_day)


@router.get("/documents/{doc_id}")
def get_document_content(doc_id: str):
    """
    Retrieves full content and metadata of a raw document for in-app preview.
    """
    doc = spine_writer.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # The page, not the facts read off it. It carries what the parsers were
    # written to leave behind: crew contact details, cast names, unreleased
    # material. Refused unless somebody deployed this having decided otherwise.
    if not privacy.may_serve(doc):
        raise HTTPException(status_code=403, detail=privacy.refusal_detail(doc))

    filename = doc.get("filename", "")
    is_pdf = filename.lower().endswith(".pdf") or doc.get("doc_type") == "pdf"

    return {
        "doc_id": doc["doc_id"],
        "production_id": doc["production_id"],
        "shoot_day": doc["shoot_day"],
        "filename": filename,
        "doc_type": doc["doc_type"],
        "department": doc["department"],
        # Narrow redaction on top of the gate. Only an email, or a number the
        # document labels as a phone -- never a bare run of digits, which is
        # how a camera card and its shoot date became a redacted phone number.
        "content": privacy.redact(doc.get("content", "")),
        "checksum": doc.get("checksum"),
        "size_bytes": doc.get("size_bytes", 0),
        "uploaded_at": doc.get("uploaded_at"),
        "is_pdf": is_pdf,
        "raw_url": f"/api/documents/{doc_id}/raw",
        "metadata": doc.get("metadata", {}),
    }


@router.get("/documents/{doc_id}/raw")
def get_document_raw(doc_id: str):
    """
    Streams the raw binary document (e.g. actual visual PDF file or text) inline for PDF viewer embedding.
    """
    doc = spine_writer.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # The original file: a PDF cannot be redacted without re-rendering it, so
    # this is the strictest thing the API serves and the gate is the only
    # control over it.
    if not privacy.may_serve(doc):
        raise HTTPException(status_code=403, detail=privacy.refusal_detail(doc))

    raw_bytes = doc.get("raw_bytes")
    filename = doc.get("filename", "document")

    # No disk fallback. It used to read CINESPINE_EXAMPLES_DIR/<filename> when
    # the stored bytes were absent, which reached the real paperwork by name
    # and would have walked straight around the gate above. Documents are
    # stored with their bytes now, so the fallback answered nothing anyway.

    # Check if the file is in GCS first
    gcs_uri = doc.get("metadata", {}).get("gcs_uri")
    if gcs_uri and gcs.is_enabled:
        signed_url = gcs.generate_signed_url(gcs_uri)
        if signed_url:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=signed_url, status_code=302)

    if not raw_bytes:
        raw_bytes = privacy.redact(doc.get("content", "")).encode("utf-8")

    is_pdf = filename.lower().endswith(".pdf") or doc.get("doc_type") == "pdf"
    media_type = "application/pdf" if is_pdf else "text/plain; charset=utf-8"

    return Response(
        content=raw_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Content-Type": media_type,
        },
    )


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    """
    Deletes an uploaded document and removes its ingested events from the spine.
    """
    doc = spine_writer.get_document(doc_id)
    deleted = spine_writer.delete_document(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")

    prod = doc.get("production_id", "DEMO_PRODUCTION") if doc else "DEMO_PRODUCTION"
    s_day = doc.get("shoot_day", "31") if doc else "31"
    fn = doc.get("filename", doc_id) if doc else doc_id
    event_broker.publish_sync(SpineLiveEvent(
        event_type="DOCUMENT_DELETED",
        production_id=prod,
        shoot_day=s_day,
        actor_handle="@user",
        target_type="document",
        target_id=doc_id,
        target_label=fn,
        summary=f"Deleted document '{fn}'",
    ))
    return {"status": "DELETED", "doc_id": doc_id}


def _ingest_failed(exc: EventHandlerError, doc_id: str, filename: str) -> HTTPException:
    """
    The spine write did not land, so the upload must not claim it did.

    The raw document is already stored and is kept: it is the evidence, and
    losing it would mean asking whoever sent it to send it again. What is
    missing is everything derived from it, which is why this cannot be
    reported as INGESTED -- a day that silently holds a document with no
    events in it looks exactly like a day that went fine.
    """
    logger.error("Ingest of %s (%s) failed: %s", filename, doc_id, exc)
    return HTTPException(
        status_code=500,
        detail=(
            f"'{filename}' was stored but its events did not reach the spine, so nothing "
            f"was ingested from it. The document is kept as doc_id {doc_id}: upload it "
            f"again once the cause is fixed, or delete it. Cause: {'; '.join(exc.reasons)}"
        ),
    )


@router.post("/upload")
def upload_document(req: UploadRequest):
    """
    Ingests document with automatic type, department, production, shoot day inference, and duplicate prevention.
    """
    classification = classify_document(filename=req.filename, content=req.raw_content)

    production_id = req.production_id or classification.inferred_production_id or "DEMO_PRODUCTION"
    shoot_day = req.shoot_day or classification.inferred_shoot_day or "31"
    axis = req.axis or classification.axis
    department = req.department or classification.department
    doc_type = req.doc_type or classification.doc_type

    filename = req.filename or f"{doc_type.value}_{shoot_day}.txt"
    content_bytes = req.raw_content.encode("utf-8")
    checksum = hashlib.sha256(content_bytes).hexdigest()

    # Check for duplicate document
    existing = spine_writer.get_document_by_checksum(production_id, shoot_day, checksum)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate document: content is already uploaded under '{existing['filename']}' for {production_id} Day {shoot_day} (SHA-256: {checksum[:8]}...).",
        )

    # Store raw document for in-app preview
    doc_id = spine_writer.store_document(
        production_id=production_id,
        shoot_day=shoot_day,
        filename=filename,
        doc_type=doc_type.value,
        department=department.value,
        content=req.raw_content,
        checksum=checksum,
        metadata=req.metadata,
    )

    metadata = dict(req.metadata)
    metadata["doc_id"] = doc_id
    metadata["filename"] = filename
    metadata["checksum"] = checksum

    envelope = EventEnvelope(
        production_id=production_id,
        shoot_day=shoot_day,
        axis=axis,
        department=department,
        doc_type=doc_type,
        raw_content=req.raw_content,
        filename=filename,
        metadata=metadata,
    )

    topic = f"production.raw.{department.value}"
    with span(
        SPAN_INGEST,
        production_id=envelope.production_id, shoot_day=envelope.shoot_day,
        department=department.value, axis=axis.value, doc_type=doc_type.value,
        doc_id=doc_id, bytes=len(req.raw_content),
    ) as ingest:
        try:
            event_bus.publish(topic, envelope)
        except EventHandlerError as exc:
            raise _ingest_failed(exc, doc_id, filename)
        # The document is ingested; send its events on together rather than
        # leaving them buffered until the next upload.
        set_attributes(ingest, mirrored_rows=spine_writer.flush_events())
        _project_analytics(envelope.production_id, envelope.shoot_day)

    event_broker.publish_sync(SpineLiveEvent(
        event_type="DOCUMENT_INGESTED",
        production_id=envelope.production_id,
        shoot_day=envelope.shoot_day,
        actor_handle=req.metadata.get("actor_handle", "@user"),
        target_type="document",
        target_id=doc_id,
        target_label=filename,
        summary=f"Ingested {filename} [{department.value.upper()}]",
        data={"filename": filename, "department": department.value, "doc_type": doc_type.value},
    ))

    return {
        "status": "INGESTED",
        "doc_id": doc_id,
        "checksum": checksum,
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
    Accepts binary PDF, CSV, ALE, or XML file drops, prevents duplicate uploads via checksum, and routes automatically.
    """
    content_bytes = await file.read()
    filename = file.filename or "unknown_drop"
    checksum = hashlib.sha256(content_bytes).hexdigest()

    # Extract text if PDF
    thumbnails_map = {}
    if filename.lower().endswith(".pdf"):
        try:
            raw_text = extract_text_from_pdf(content_bytes)
        except Exception as e:
            raw_text = content_bytes.decode("utf-8", errors="ignore")

        if any(k in filename.lower() or (raw_text and k in raw_text.lower()) for k in ["thumbnail", "clips", "thumbnail report", "clips report"]):
            try:
                thumbnails_map = extract_thumbnails_from_pdf(content_bytes)
            except Exception:
                thumbnails_map = {}
    else:
        raw_text = content_bytes.decode("utf-8", errors="ignore")

    classification = classify_document(filename=filename, content=raw_text)

    # A lined page is handwriting: there is no text layer to parse, so the takes,
    # slates and camera rolls on it are only reachable through vision. Runs before
    # the event is published so the extraction travels with the document rather
    # than arriving as a later, separate fact.
    lining_warnings: List[str] = []
    lined_page = None
    handwritten_rows: List[Dict[str, Any]] = []
    if classification.is_multimodal:
        if classification.department == DepartmentType.CAMERA:
            # A handwritten camera report carries its rows as ink, so the CSV
            # parser finds nothing on it and reports a clean, empty document.
            outcome = await read_camera_report_if_enabled(
                content_bytes, filename, file.content_type
            )
            handwritten_rows = [asdict(r) for r in outcome["records"]]
            lining_warnings = outcome["warnings"]
        else:
            outcome = await extract_lined_page_if_enabled(
                content_bytes, filename, file.content_type
            )
            lined_page = outcome["page"]
            lining_warnings = outcome["warnings"]

    final_prod = production_id or classification.inferred_production_id or "DEMO_PRODUCTION"
    final_day = shoot_day or classification.inferred_shoot_day or "31"

    # Check for duplicate document
    existing = spine_writer.get_document_by_checksum(final_prod, final_day, checksum)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate document: '{existing['filename']}' is already uploaded for {final_prod} Day {final_day} (SHA-256: {checksum[:8]}...).",
        )

    # Optional GCS Upload
    gcs_uri = None
    if gcs.is_enabled:
        object_name = f"{final_prod}/day_{final_day}/{filename}_{checksum[:8]}"
        gcs_uri = gcs.upload_file(object_name, content_bytes, file.content_type)
        if gcs_uri:
            logger.info("Uploaded %s to GCS at %s", filename, gcs_uri)

    # Store for previewing
    doc_id = spine_writer.store_document(
        production_id=final_prod,
        shoot_day=final_day,
        filename=filename,
        doc_type=classification.doc_type.value,
        department=classification.department.value,
        content=raw_text,
        checksum=checksum,
        # Only store the heavy bytes in sqlite if we didn't upload to GCS
        raw_bytes=None if gcs_uri else content_bytes,
        metadata={
            "file_size": len(content_bytes),
            "content_type": file.content_type,
            "lined_page": lined_page.model_dump() if lined_page else None,
            "handwritten_rows": handwritten_rows,
            "gcs_uri": gcs_uri,
        },
    )

    envelope = EventEnvelope(
        production_id=final_prod,
        shoot_day=final_day,
        axis=classification.axis,
        department=classification.department,
        doc_type=classification.doc_type,
        raw_content=raw_text,
        filename=filename,
        metadata={
            "doc_id": doc_id,
            "file_size": len(content_bytes),
            "checksum": checksum,
            "content_type": file.content_type,
            "thumbnails": thumbnails_map,
            "lined_page": lined_page.model_dump() if lined_page else None,
            "handwritten_rows": handwritten_rows,
            "gcs_uri": gcs_uri,
        },
    )

    # Which departments file, and when. No filename: it carries the production's
    # name. The doc type says what arrived without saying whose it is.
    analytics.capture("@upload", "document_ingested", {
        "production_id": final_prod,
        "shoot_day": final_day,
        "department": classification.department.value,
        "doc_type": classification.doc_type.value,
        "axis": classification.axis.value,
    })

    topic = f"production.raw.{classification.department.value}"
    try:
        event_bus.publish(topic, envelope)
    except EventHandlerError as exc:
        raise _ingest_failed(exc, doc_id, filename)
    # The document is ingested; send its events on together rather than
    # leaving them buffered until the next upload.
    spine_writer.flush_events()
    _project_analytics(envelope.production_id, envelope.shoot_day)

    event_broker.publish_sync(SpineLiveEvent(
        event_type="DOCUMENT_INGESTED",
        production_id=final_prod,
        shoot_day=final_day,
        actor_handle="@user",
        target_type="document",
        target_id=doc_id,
        target_label=filename,
        summary=f"Ingested file {filename} [{classification.department.value.upper()}]",
        data={"filename": filename, "department": classification.department.value, "doc_type": classification.doc_type.value},
    ))

    return {
        "status": "INGESTED",
        "doc_id": doc_id,
        "checksum": checksum,
        "filename": filename,
        "event_id": envelope.event_id,
        "production_id": final_prod,
        "shoot_day": final_day,
        "detected_doc_type": classification.doc_type.value,
        "detected_department": classification.department.value,
        "detected_axis": classification.axis.value,
        "is_multimodal": classification.is_multimodal,
        # Named separately from the classification flag: is_multimodal says the
        # page needs vision, this says whether vision actually read it.
        "lined_page": lined_page.model_dump() if lined_page else None,
        "lining_warnings": lining_warnings,
    }


def is_take_media_match(media_info: Dict[str, Any], slate: str, take_id: str, camera_roll: Optional[str], clip_name: Optional[str]) -> bool:
    """
    Precise matching between a take slate/take_id and a DIT media file (Camera MXF or Sound WAV).
    """
    fn = media_info.get("file_name", "")
    m_scene = media_info.get("scene")
    m_shot = media_info.get("shot")
    m_take = media_info.get("take_id")

    slate_parts = slate.split("/")
    sc = slate_parts[0]
    sh = slate_parts[1] if len(slate_parts) > 1 else None

    tk_norm = take_id.replace("VFX", "").replace("PK", "").replace("FC", "FALSE").strip()

    # 1. Parsed scene/shot/take from Silverstack (Thumbnail or Volume report)
    if m_scene and m_take:
        m_tk_norm = m_take.replace("VFX", "").replace("PK", "").replace("FC", "FALSE").strip()
        if tk_norm.isdigit() and m_tk_norm.isdigit():
            tk_match = int(tk_norm) == int(m_tk_norm)
        else:
            tk_match = tk_norm.upper() == m_tk_norm.upper()

        sc_clean = sc.lstrip("+").upper()
        m_sc_clean = m_scene.lstrip("+").upper()

        if (sc.upper() == m_scene.upper() or sc_clean == m_sc_clean) and tk_match:
            # A camera roll is the least specific identifier on the page: one roll
            # spans many slates and many takes. Roll agreement therefore cannot
            # stand in for a shot match -- doing so attached every clip on a roll
            # to every take on it, so slate 49/5 and 49/6 showed the same twelve
            # clips. Disagreement, however, is disqualifying.
            m_roll = media_info.get("camera_roll") or ""
            roll_conflict = bool(camera_roll and m_roll and camera_roll.upper() != m_roll.upper())

            # Silverstack often writes the shot as the bare scene number, which
            # identifies no particular slate. Treated as a match it attached every
            # clip in a scene to every slate in that scene, so 49/1 through 49/9
            # all showed the same clips.
            shot_is_informative = bool(m_shot) and m_shot.upper() not in (
                sc.upper(), sc_clean.upper()
            )

            if not roll_conflict:
                if sh and shot_is_informative:
                    if (
                        sh.upper() == m_shot.upper()
                        or m_shot.upper().endswith(f"/{sh.upper()}")
                        or m_shot.upper() == slate.upper()
                        or m_shot.upper() == f"{sc.upper()}/{sh.upper()}"
                    ):
                        return True
                elif not sh:
                    # The slate names no shot either, so scene and take are all
                    # the evidence either side has. This is as precise as it gets.
                    return True
                # Otherwise the slate distinguishes a shot and the media does not.
                # Which slate this clip belongs to is unknown, and attaching it to
                # all of them would invent an answer. Clip-name matching below can
                # still claim it where the camera report names it explicitly.

    # 2. Camera Clip Name matching (e.g. ZoeLog 'A120_C001' vs Silverstack 'A_0120C001_260728_091309_h1EIC.mxf' or 'A120_C001_260728.MOV')
    if clip_name:
        m_c = re.match(r"^([A-Z])_?(\d{3,4})_?C(\d{3,4})", clip_name)
        if m_c:
            cam_letter, roll_num, c_num = m_c.group(1), int(m_c.group(2)), int(m_c.group(3))
            target_pattern = rf"{cam_letter}_?0*{roll_num}_?C0*{c_num}(?:[^0-9]|$)"
            if re.search(target_pattern, fn):
                return True
        if clip_name in fn or fn.startswith(clip_name):
            return True

    # 3. Audio WAV Name matching (e.g. '+99BDF-9T01.WAV', '27-7T01.WAV', '49WTT01.WAV')
    if fn.upper().endswith(".WAV"):
        if tk_norm.isdigit():
            tk_int = int(tk_norm)
            sc_esc = rf"(?:\+)?{re.escape(sc.lstrip('+'))}"
            if sh and sh != "WT":
                pattern = rf"^{sc_esc}(?:-|\/)?{re.escape(sh)}T0*{tk_int}\.WAV$"
            else:
                pattern = rf"^{sc_esc}(?:-|\/)?(?:WTT|-?WTT?|-?T)0*{tk_int}\.WAV$"
            if re.search(pattern, fn, re.IGNORECASE):
                return True

    return False


class SeedRequest(BaseModel):
    production_id: str = "DEMO_PRODUCTION"
    shoot_day: str = "31"


FALLBACK_SEED_FILES: Dict[str, str] = {
    "DemoProduction-2026-7-28_CAM_A.csv": """Slate,Take,CameraRoll,ClipName,FPS,ISO,Lens,Scene,Description
27/7,1,A120,A120_C001_260728,24.0,800,50mm,27,ORGAN - LEAD plays -> He sees SUPPORT
27/7,2,A120,A120_C002_260728,24.0,800,50mm,27,ORGAN - LEAD plays -> He sees SUPPORT
49/WT,1,A121,A121_C001_260728,24.0,800,50mm,49,Wild track footsteps
49/9,1,A121,A121_C002_260728,24.0,800,50mm,49,LEAD messes up
""",
    "DemoProduction-2026-7-28_CAM_B.csv": """Slate,Take,CameraRoll,ClipName,FPS,ISO,Lens,Scene,Description
27/7,1,B039,B039_C001_260728,24.0,800,35mm,27,ORGAN - LEAD plays -> He sees SUPPORT
27/7,2,B039,B039_C002_260728,24.0,800,35mm,27,ORGAN - LEAD plays -> He sees SUPPORT
49/9,1,B041,B041_C001_260728,24.0,800,35mm,49,LEAD messes up
""",
    "DemoProduction-2026-7-28_CAM_C.csv": """Slate,Take,CameraRoll,ClipName,FPS,ISO,Lens,Scene,Description
27/7,1,C005,C005_C001_260728,24.0,800,85mm,27,ORGAN - LEAD plays -> He sees SUPPORT
27/7,2,C005,C005_C002_260728,24.0,800,85mm,27,ORGAN - LEAD plays -> He sees SUPPORT
""",
    "260728_Report.csv": """Heading
FIELD_DELIM	TABS
VIDEO_FORMAT	1080
FILM_FORMAT	35mm
FPS	24

Column
Name	Tracks	Start	End	Tape	Scene	Take	Notes	Sound Roll

Data
27-7T01.WAV	MixL,MixR,Boom,Lav1	09:25:40:00	09:28:40:00	26Y07M27	27/7	1	Good sound	26Y07M27
27-7T02.WAV	MixL,MixR,Boom,Lav1	09:35:40:00	09:38:40:00	26Y07M27	27/7	2	Director directing take	26Y07M27
49-WTT01.WAV	MixL,MixR,Boom	10:15:00:00	10:16:00:00	26Y07M27	49/WT	1	Wild Track footsteps	26Y07M27
49-9T01.WAV	MixL,MixR,Boom,Lav1	13:51:40:00	13:53:19:00	26Y07M27	49/9	1	LEAD dialog	26Y07M27
""",
    "DEMO_TCLog_D031_280726.txt": """DAILY TIMECODE LOG 28/07/2026
LAC
Day: Day 31 - Main Unit
Date: 28/07/2026
Slate Take # Timecode In Actual Time In Timecode Out Actual Time Out Description CR SR Time SU
27/7 1 09:26:12:04 09:25:48 09:28:58:12 09:28:34 Scene(s): 27 ORGAN - LEAD plays -> He sees SUPPORT A120 280726 2:46 1
27/7 1 09:26:12:04 09:25:48 09:28:58:12 09:28:34 Scene(s): 27 ORGAN - LEAD plays -> He sees SUPPORT B039 280726 2:46 2
27/7 1 09:26:12:04 09:25:48 09:28:58:12 09:28:34 Scene(s): 27 ORGAN - LEAD plays -> He sees SUPPORT C005 280726 2:46 3
27/7 2 09:36:11:14 09:35:47 09:39:05:05 09:38:40 Scene(s): 27 ORGAN - LEAD plays -> He sees SUPPORT A120 280726 2:53 1
49/WT 1 10:15:10:00 10:15:00 10:16:10:00 10:16:00 Scene(s): 49 Wild Track: 49/WT pasos de LEAD n/a 280726 1:00 1
49/9 1 13:52:08:10 13:51:40 13:53:19:13 13:52:51 Scene(s): 49 LEAD messes up -> exits B041 280726 1:11 1
""",
    "DEMO_DetailedEditor’sLog_D031_280726.txt": """DETAILED EDITOR'S LOG 28/07/2026
LAC - V31
Day: Day 31 - Main Unit
Date: 28/07/2026
Slate Take Description CR SR Time Camera Info Comments
27/7 1 Scene(s): 27 ORGAN - Sticks - xwide. Frontal VWS - LEAD plays -> He sees SUPPORT A120 280726 2:46 1
27/7 1 Dolly - wide B039 280726 2:46 2
27/7 1 Slider - wide C005 280726 2:46 3
49/WT 1 Scene(s): 49 Wild Track: 49/WT n/a 280726 0:29 pasos de LEAD
""",
    "Thumbnail-260728_SD31-20260728-1927.pdf": """Pomfort Silverstack Thumbnail Report
Production: DEMO PRODUCTION
260728_SD31

Name A120_C001_260728.MOV
Reel/Tape A_0120_1EIC
Scene 27
Shot 27/7
Take 1
Duration 00:02:46:00
Camera A
Sensor FPS 24.0
EI/ISO (clip) 800
T-Stop 2.8
Codec Apple ProRes 4444 XQ
Recording Date 28/07/2026 09:25:48

Name B039_C001_260728.MOV
Reel/Tape B_0039_1EIC
Scene 27
Shot 27/7
Take 1
Duration 00:02:46:00
Camera B
Sensor FPS 24.0
EI/ISO (clip) 800
T-Stop 2.8
Codec Apple ProRes 4444 XQ
Recording Date 28/07/2026 09:25:48

Name C005_C001_260728.MOV
Reel/Tape C_0005_1EIC
Scene 27
Shot 27/7
Take 1
Duration 00:02:46:00
Camera C
Sensor FPS 24.0
EI/ISO (clip) 800
T-Stop 2.8
Codec Apple ProRes 4444 XQ
Recording Date 28/07/2026 09:25:48
"""
}


@router.post("/seed")
def seed_real_day_data(req: SeedRequest):
    """
    Seeds production documents (ZoeLog Camera A/B/C, Sound Reports, Silverstack & Script Logs)
    from local examples directory or embedded fallback demo dataset into the spine.
    """
    custom_dir = os.environ.get("CINESPINE_EXAMPLES_DIR")
    if custom_dir:
        examples_dir = custom_dir
        use_dir = os.path.exists(examples_dir)
    else:
        examples_dir = "data/examples"
        use_dir = (
            os.path.exists(examples_dir)
            and any(f.startswith("DemoProduction") for f in os.listdir(examples_dir))
        )

    ingested_files = []
    skipped_files: List[str] = []
    # Files whose events did not reach the spine. Distinct from skipped, which
    # means "already here": these are failures, and they need chasing.
    failed_files: List[str] = []

    if use_dir:
        files = sorted(os.listdir(examples_dir))
        for fn in files:
            fp = os.path.join(examples_dir, fn)
            with open(fp, "rb") as f:
                content_bytes = f.read()

            checksum = hashlib.sha256(content_bytes).hexdigest()
            t_map = {}
            if fn.lower().endswith(".pdf"):
                try:
                    txt = extract_text_from_pdf(content_bytes)
                except Exception:
                    txt = content_bytes.decode("utf-8", errors="ignore")

                if any(k in fn.lower() or (txt and k in txt.lower()) for k in ["thumbnail", "clips", "thumbnail report", "clips report"]):
                    try:
                        t_map = extract_thumbnails_from_pdf(content_bytes)
                    except Exception:
                        t_map = {}
            else:
                txt = content_bytes.decode("utf-8", errors="ignore")

            classification = classify_document(filename=fn, content=txt)

            # Same rule the upload routes enforce. Seeding twice used to store
            # every document again under the same checksum, so a second click
            # doubled the paperwork behind the spine.
            if spine_writer.get_document_by_checksum(req.production_id, req.shoot_day, checksum):
                skipped_files.append(fn)
                continue

            doc_id = spine_writer.store_document(
                production_id=req.production_id,
                shoot_day=req.shoot_day,
                filename=fn,
                doc_type=classification.doc_type.value,
                department=classification.department.value,
                content=txt,
                checksum=checksum,
                raw_bytes=content_bytes,
                metadata={"file_size": len(content_bytes)},
            )

            envelope = EventEnvelope(
                production_id=req.production_id,
                shoot_day=req.shoot_day,
                axis=classification.axis,
                department=classification.department,
                doc_type=classification.doc_type,
                raw_content=txt,
                filename=fn,
                metadata={"doc_id": doc_id, "checksum": checksum, "thumbnails": t_map},
            )
            topic = f"production.raw.{classification.department.value}"
            try:
                event_bus.publish(topic, envelope)
            except EventHandlerError as exc:
                # One file failing does not abandon the rest of the seed, but
                # it is never counted as ingested: a seed that reports every
                # file while half of them produced no events is the same lie
                # the upload route used to tell, in bulk.
                logger.error("Seed of %s failed: %s", fn, exc)
                failed_files.append(fn)
                continue
            # The document is ingested; send its events on together rather than
            # leaving them buffered until the next upload.
            spine_writer.flush_events()
            _project_analytics(envelope.production_id, envelope.shoot_day)
            ingested_files.append(fn)
    else:
        # Graceful fallback: seed from built-in sample paperwork documents
        for fn, txt in FALLBACK_SEED_FILES.items():
            content_bytes = txt.encode("utf-8")
            checksum = hashlib.sha256(content_bytes).hexdigest()
            classification = classify_document(filename=fn, content=txt)
            t_map = {}
            if "Thumbnail" in fn:
                # Add default placeholder thumbnails for scene 27
                b64_img = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                t_map = {
                    "A120_C001_260728.MOV": b64_img,
                    "B039_C001_260728.MOV": b64_img,
                    "C005_C001_260728.MOV": b64_img,
                    "A120_C001_260728": b64_img,
                    "27_27/7_1_A120": b64_img,
                    "27/7_1": b64_img,
                }

            # Same rule the upload routes enforce. Seeding twice used to store
            # every document again under the same checksum, so a second click
            # doubled the paperwork behind the spine.
            if spine_writer.get_document_by_checksum(req.production_id, req.shoot_day, checksum):
                skipped_files.append(fn)
                continue

            doc_id = spine_writer.store_document(
                production_id=req.production_id,
                shoot_day=req.shoot_day,
                filename=fn,
                doc_type=classification.doc_type.value,
                department=classification.department.value,
                content=txt,
                checksum=checksum,
                raw_bytes=content_bytes,
                metadata={"file_size": len(content_bytes), "synthetic": True},
            )

            envelope = EventEnvelope(
                production_id=req.production_id,
                shoot_day=req.shoot_day,
                axis=classification.axis,
                department=classification.department,
                doc_type=classification.doc_type,
                raw_content=txt,
                filename=fn,
                metadata={"doc_id": doc_id, "checksum": checksum, "thumbnails": t_map},
            )
            topic = f"production.raw.{classification.department.value}"
            try:
                event_bus.publish(topic, envelope)
            except EventHandlerError as exc:
                # One file failing does not abandon the rest of the seed, but
                # it is never counted as ingested: a seed that reports every
                # file while half of them produced no events is the same lie
                # the upload route used to tell, in bulk.
                logger.error("Seed of %s failed: %s", fn, exc)
                failed_files.append(fn)
                continue
            # The document is ingested; send its events on together rather than
            # leaving them buffered until the next upload.
            spine_writer.flush_events()
            _project_analytics(envelope.production_id, envelope.shoot_day)
            ingested_files.append(fn)

    event_broker.publish_sync(SpineLiveEvent(
        event_type="DOCUMENT_INGESTED",
        production_id=req.production_id,
        shoot_day=req.shoot_day,
        actor_handle="@system",
        target_type="document",
        target_id=f"seed_{req.shoot_day}",
        target_label=f"Day {req.shoot_day} Demo Data",
        summary=f"Seeded {len(ingested_files)} paperwork files for Day {req.shoot_day}",
        data={"files": ingested_files},
    ))

    return {
        "status": "SEEDED",
        "ingested_count": len(ingested_files),
        "files": ingested_files,
        # Reported rather than hidden: a second seed that ingests nothing should
        # say so, not look identical to the first.
        "skipped_count": len(skipped_files),
        "skipped_files": skipped_files,
        # A seed that reported only what worked would look identical to a
        # clean one. These produced no events and need chasing.
        "failed_count": len(failed_files),
        "failed_files": failed_files,
    }



@router.get("/takes")
def get_takes(production_id: str, shoot_day: str) -> List[Dict[str, Any]]:
    """
    Returns aggregated take records with multi-camera video clips, audio tracks, physical card/roll locations, and volume breakdown.
    """
    events = spine_writer.get_events(production_id=production_id, shoot_day=shoot_day)
    takes_map: Dict[str, Dict[str, Any]] = {}
    media_files_map: Dict[str, Dict[str, Any]] = {}
    sound_reports_map: Dict[str, Dict[str, Any]] = {}
    resolutions = spine_writer.get_discrepancy_resolutions(production_id=production_id, shoot_day=shoot_day)

    # 1. Map media files from DIT existence events
    for evt in events:
        if evt.get("entity_type") == "media_file":
            p = evt.get("payload", {})
            fn = p.get("file_name", "")
            if fn:
                media_files_map[fn] = {
                    "file_name": fn,
                    "camera_roll": p.get("camera_roll"),
                    "reel_tape": p.get("reel_tape"),
                    "scene": p.get("scene"),
                    "shot": p.get("shot"),
                    "take_id": p.get("take_id"),
                    "codec": p.get("codec"),
                    "recording_date": p.get("recording_date"),
                    "camera": p.get("camera"),
                    "fps": p.get("fps"),
                    "iso": p.get("iso"),
                    "tstop": p.get("tstop"),
                    "card_type": p.get("card_type"),
                    "thumbnail_b64": p.get("thumbnail_b64"),
                    "volume_name": p.get("volume_name") or "Offload Drive",
                    "file_size_bytes": p.get("file_size_bytes", 0),
                    "checksum": p.get("checksum"),
                    "source_doc": evt.get("metadata", {}).get("filename"),
                }

    # 2. Sound reports lookup
    for evt in events:
        if evt.get("department") == "sound" and evt.get("entity_type") == "take":
            p = evt.get("payload", {})
            raw_slate = p.get("slate")
            raw_take = p.get("take_id")
            if raw_slate and raw_take:
                slate = normalize_slate(raw_slate) or raw_slate
                tk_res = normalize_take(raw_take)
                tk = tk_res.take_id or raw_take
                s_key = f"{slate}_{tk}"
                sound_reports_map[s_key] = {
                    "file_name": p.get("file_name"),
                    "sound_roll": p.get("sound_roll"),
                    "timecode_in": p.get("timecode_in"),
                    "timecode_out": p.get("timecode_out"),
                    "duration": p.get("duration"),
                    "sample_rate": p.get("sample_rate"),
                    "bit_depth": p.get("bit_depth"),
                    "tracks": p.get("tracks"),
                    "note": p.get("note"),
                    "raw_payload": p.get("raw_payload", {}),
                    "source_document": evt.get("metadata", {}).get("filename"),
                }

    # 3. Aggregate takes
    for evt in events:
        if evt.get("entity_type") == "take":
            p = evt.get("payload", {})
            raw_slate = p.get("slate")
            raw_take = p.get("take_id")
            if raw_slate and raw_take:
                # Canonicalize slate and take identifier so T1, T01, 1, 49WT, 49/WT merge seamlessly
                slate = normalize_slate(raw_slate) or raw_slate
                take_res = normalize_take(raw_take)
                take_id = take_res.take_id or raw_take
                key = f"{slate}_{take_id}"
                scene = slate.split("/")[0] if "/" in slate else (p.get("scene") or slate)

                if key not in takes_map:
                    takes_map[key] = {
                        "scene": scene,
                        "slate": slate,
                        "take_id": take_id,
                        "intent": None,
                        "belief": {},
                        "existence": {},
                        "camera_cards": set(),
                        "sound_cards": set(),
                        "storage_volumes": set(),
                        "video_files": [],
                        "audio_files": [],
                        "camera_angles": [],
                        "matched_media_files": [],
                        "source_documents": [],
                        "is_starred": False,
                        "is_pickup": False,
                        "is_wild_track": False,
                        "is_vfx": False,
                        "is_mos": False,
                        "codec": None,
                        "recording_date": None,
                        "thumbnail_url": None,
                    }

                axis = evt.get("axis", "belief")
                dept = evt.get("department", "unknown")
                doc_name = evt.get("metadata", {}).get("filename") or evt.get("doc_type")
                doc_id = evt.get("metadata", {}).get("doc_id")

                # Record witness payload
                witness_payload = dict(p)
                witness_payload["source_document"] = doc_name
                witness_payload["source_doc_id"] = doc_id

                if axis == "existence" or dept == "dit":
                    takes_map[key]["existence"]["dit"] = witness_payload
                else:
                    takes_map[key]["belief"][dept] = witness_payload

                if p.get("codec") and (not takes_map[key].get("codec") or p.get("card_type") == "camera"):
                    takes_map[key]["codec"] = p.get("codec")
                if p.get("recording_date") and not takes_map[key].get("recording_date"):
                    takes_map[key]["recording_date"] = p.get("recording_date")
                if p.get("thumbnail_b64") and (not takes_map[key].get("thumbnail_url") or p.get("card_type") == "camera"):
                    takes_map[key]["thumbnail_url"] = p.get("thumbnail_b64")

                if doc_name and doc_name not in [d.get("filename") for d in takes_map[key]["source_documents"]]:
                    takes_map[key]["source_documents"].append({
                        "doc_id": doc_id,
                        "filename": doc_name,
                        "department": dept,
                    })

                # Extract Physical Cards / Rolls
                cr = p.get("camera_roll")
                if cr:
                    takes_map[key]["camera_cards"].add(f"Card {cr}")

                sr = p.get("sound_roll") or (p.get("reel_tape") if p.get("card_type") == "sound" else None)
                if sr:
                    takes_map[key]["sound_cards"].add(f"Sound {sr}")

                if p.get("is_starred"):
                    takes_map[key]["is_starred"] = True
                if p.get("is_pickup"):
                    takes_map[key]["is_pickup"] = True
                if p.get("is_wild_track") or "WT" in slate.upper():
                    takes_map[key]["is_wild_track"] = True
                if p.get("is_vfx") or "VFX" in slate.upper():
                    takes_map[key]["is_vfx"] = True
                if p.get("is_mos") or "MOS" in slate.upper():
                    takes_map[key]["is_mos"] = True

                # Match with DIT Media Files (both video and audio WAV clips)
                clip_name = p.get("clip_name")

                for fn, media_info in media_files_map.items():
                    if is_take_media_match(media_info, slate, take_id, cr, clip_name):
                        vol = media_info.get("volume_name") or "Offload Drive"
                        takes_map[key]["storage_volumes"].add(vol)
                        if media_info.get("card_type") == "sound" and media_info.get("reel_tape"):
                            takes_map[key]["sound_cards"].add(f"Sound {media_info['reel_tape']}")

                        # Prefer camera frame picture
                        if media_info.get("thumbnail_b64") and (not takes_map[key].get("thumbnail_url") or media_info.get("card_type") == "camera"):
                            takes_map[key]["thumbnail_url"] = media_info.get("thumbnail_b64")

                        if media_info.get("codec") and (not takes_map[key].get("codec") or media_info.get("card_type") == "camera"):
                            takes_map[key]["codec"] = media_info.get("codec")

                        if media_info.get("recording_date") and not takes_map[key].get("recording_date"):
                            takes_map[key]["recording_date"] = media_info.get("recording_date")

                        if media_info not in takes_map[key]["matched_media_files"]:
                            takes_map[key]["matched_media_files"].append(media_info)

    # 4. Structure video & audio files per take
    results = []
    for key, t in takes_map.items():
        sr_info = sound_reports_map.get(key)
        if sr_info and not t["belief"].get("sound"):
            t["belief"]["sound"] = sr_info

        for mf in t["matched_media_files"]:
            fn = mf.get("file_name", "")
            is_sound = mf.get("card_type") == "sound" or fn.upper().endswith(".WAV")
            if is_sound:
                audio_entry = {
                    "file_name": fn,
                    "sound_roll": mf.get("reel_tape") or (sr_info.get("sound_roll") if sr_info else None) or "Sound Roll",
                    "codec": mf.get("codec") or "Linear PCM (24bit, 48kHz)",
                    "timecode_in": (sr_info.get("timecode_in") if sr_info else None) or t.get("belief", {}).get("script", {}).get("timecode_in"),
                    "duration": (sr_info.get("duration") if sr_info else None) or "00:03:00",
                    "tracks": (sr_info.get("tracks") if sr_info else None) or "MixL, MixR, BOOM 1, BOOM 2, LINE OUT, AMBI MIX",
                    "sample_rate": (sr_info.get("sample_rate") if sr_info else None) or "48kHz",
                    "bit_depth": (sr_info.get("bit_depth") if sr_info else None) or "24-bit",
                    "note": (sr_info.get("note") if sr_info else None) or "",
                    "volume_name": mf.get("volume_name") or "664 SD",
                    "file_size_bytes": mf.get("file_size_bytes", 0),
                    "checksum": mf.get("checksum"),
                }
                if audio_entry["file_name"] not in [a["file_name"] for a in t["audio_files"]]:
                    t["audio_files"].append(audio_entry)
            else:
                cam_letter = mf.get("camera") or (fn[0] if fn and fn[0] in "ABCD" else "A")
                cam_clean = cam_letter.upper().replace("_", "")
                video_entry = {
                    "camera": cam_clean,
                    "file_name": fn,
                    "camera_roll": mf.get("camera_roll") or f"Card {cam_clean}",
                    "reel_tape": mf.get("reel_tape"),
                    "codec": mf.get("codec") or "ARRIRAW (13bit, HDE)",
                    "recording_date": mf.get("recording_date"),
                    "fps": mf.get("fps") or 24.0,
                    "iso": mf.get("iso") or 800,
                    "tstop": mf.get("tstop") or "T2.8",
                    "thumbnail_url": mf.get("thumbnail_b64"),
                    "volume_name": mf.get("volume_name") or "Offload Drive",
                    "file_size_bytes": mf.get("file_size_bytes", 0),
                    "checksum": mf.get("checksum"),
                }
                if video_entry["file_name"] not in [v["file_name"] for v in t["video_files"]]:
                    t["video_files"].append(video_entry)

                if video_entry["thumbnail_url"]:
                    angle_entry = {
                        "camera": video_entry["camera"],
                        "camera_roll": video_entry["camera_roll"],
                        "file_name": video_entry["file_name"],
                        "thumbnail_url": video_entry["thumbnail_url"],
                    }
                    if angle_entry["camera"] not in [ca["camera"] for ca in t["camera_angles"]]:
                        t["camera_angles"].append(angle_entry)

        # Fallback audio entry if sound report parsed without DIT matching
        if not t["audio_files"] and sr_info:
            default_fn = f"{t['slate'].replace('/', '-')}T{int(t['take_id']):02d}.WAV" if t['take_id'].isdigit() else f"{t['slate'].replace('/', '-')}T{t['take_id']}.WAV"
            t["audio_files"].append({
                "file_name": sr_info.get("file_name") or default_fn,
                "sound_roll": sr_info.get("sound_roll") or "Sound Roll",
                "codec": "Linear PCM (24bit, 48kHz)",
                "timecode_in": sr_info.get("timecode_in"),
                "duration": sr_info.get("duration"),
                "tracks": sr_info.get("tracks"),
                "sample_rate": sr_info.get("sample_rate") or "48kHz",
                "bit_depth": sr_info.get("bit_depth") or "24-bit",
                "note": sr_info.get("note"),
                "volume_name": "Sound Devices 664",
                "file_size_bytes": 0,
                "checksum": None,
            })

        # 4. Check for resolved discrepancy assignments
        for res in resolutions.values():
            ent_id = res.get("entity_id", "")
            if (t["slate"] in ent_id and t["take_id"] in ent_id) or (ent_id == f"{t['slate']}_{t['take_id']}"):
                rc = res.get("resolved_card")
                if rc:
                    if any(rc.upper().startswith(pfx) for pfx in ["A", "B", "C", "D"]) and not rc.startswith("26"):
                        t["camera_cards"].add(rc if rc.startswith("Card") else f"Card {rc}")
                    else:
                        t["sound_cards"].add(rc if rc.startswith("Sound") else f"Sound {rc}")
                t["resolution"] = res

        # 5. Attach contextual requirements
        all_reqs = spine_writer.list_requirements(production_id=production_id, shoot_day=shoot_day)
        take_k = f"{t['slate']}_{t['take_id']}"
        take_reqs = [
            r for r in all_reqs
            if (r.get("target_type") == "take" and r.get("target_id") == take_k)
            or (r.get("target_type") == "shot" and r.get("target_id") == t["slate"])
            or (r.get("target_type") == "scene" and r.get("target_id") == t.get("scene"))
        ]
        t["requirements"] = take_reqs
        t["open_requirements_count"] = sum(1 for r in take_reqs if r.get("status") in ["open", "in_progress", "blocked"])
        t["resolved_requirements_count"] = sum(1 for r in take_reqs if r.get("status") == "resolved")

        t["camera_angles"].sort(key=lambda x: x["camera"])
        t["video_files"].sort(key=lambda x: x["camera"])
        t["camera_cards"] = sorted(list(t["camera_cards"]))
        t["sound_cards"] = sorted(list(t["sound_cards"]))
        t["storage_volumes"] = sorted(list(t["storage_volumes"]))
        results.append(t)

    # Sort takes by scene and slate
    return sorted(results, key=lambda x: (x.get("scene", ""), x.get("slate", ""), x.get("take_id", "")))



@router.get("/discrepancies")
def get_discrepancies(production_id: str, shoot_day: str) -> List[Dict[str, Any]]:
    found = mcp_server.query_production_discrepancies(production_id=production_id, shoot_day=shoot_day)
    # Observed where they are computed rather than on the metrics scrape:
    # reconciling every day of a shoot on every scrape would cost far more than
    # the number is worth. So the gauge covers the days somebody has opened,
    # which is what "how is the day looking" means in practice.
    TelemetryExporter.record_discrepancies(production_id, shoot_day, found)
    return found


@router.post("/discrepancies/{discrepancy_id}/resolve")
def resolve_discrepancy(discrepancy_id: str, req: ResolveDiscrepancyRequest):
    """
    Resolves an active discrepancy by assigning the clip/sound to a chosen or manual card,
    recording resolution notes and timestamp.
    """
    resolution = spine_writer.store_discrepancy_resolution(
        production_id=req.production_id,
        shoot_day=req.shoot_day,
        discrepancy_id=discrepancy_id,
        entity_id=req.entity_id,
        resolved_card=req.resolved_card,
        resolution_note=req.resolution_note,
        resolved_by=req.resolved_by or "Assistant Editor",
    )
    # Append audit event to spine
    spine_writer.append_event({
        "event_id": str(uuid.uuid4()),
        "production_id": req.production_id,
        "shoot_day": req.shoot_day,
        "axis": "belief",
        "department": "editorial",
        "doc_type": "discrepancy_resolution",
        "entity_type": "discrepancy_resolution",
        "payload": resolution,
        "metadata": {"discrepancy_id": discrepancy_id, "entity_id": req.entity_id},
        "timestamp": resolution["resolved_at"],
    })

    event_broker.publish_sync(SpineLiveEvent(
        event_type="DISCREPANCY_RESOLVED",
        production_id=req.production_id,
        shoot_day=req.shoot_day,
        actor_handle=req.resolved_by or "@assistant_editor",
        target_type="discrepancy",
        target_id=discrepancy_id,
        target_label=f"Discrepancy on {req.entity_id}",
        summary=f"Resolved discrepancy on {req.entity_id}: Assigned to {req.resolved_card or 'manual'}",
        data={"discrepancy_id": discrepancy_id, "entity_id": req.entity_id, "resolved_card": req.resolved_card},
    ))

    return {
        "status": "RESOLVED",
        "discrepancy_id": discrepancy_id,
        "resolution": resolution,
    }


@router.post("/discrepancies/{discrepancy_id}/unresolve")
def unresolve_discrepancy(discrepancy_id: str):
    """
    Re-opens an active discrepancy by clearing its resolution record.
    """
    deleted = spine_writer.delete_discrepancy_resolution(discrepancy_id)
    event_broker.publish_sync(SpineLiveEvent(
        event_type="DISCREPANCY_UNRESOLVED",
        production_id="ALL",
        shoot_day="ALL",
        actor_handle="@assistant_editor",
        target_type="discrepancy",
        target_id=discrepancy_id,
        target_label=f"Discrepancy {discrepancy_id}",
        summary=f"Discrepancy re-opened ({discrepancy_id})",
    ))
    return {"status": "UNRESOLVED", "discrepancy_id": discrepancy_id, "success": deleted}



def _sequence_shoot_days(production_id: str) -> Dict[str, List[str]]:
    """
    Every day each sequence was shot, across the whole production.

    A scene is rarely finished in one go: it is covered over as many days as it
    takes, and the second half may be shot weeks after the first. The matrix is
    a day's log and stays one, but a row that says only "Day 31" reads as if
    the sequence began and ended there -- so each row also carries the other
    days it runs to, and someone reconciling it knows there is more to find.
    """
    days: Dict[str, set] = {}
    for event in spine_writer.get_events(production_id=production_id):
        day = event.get("shoot_day")
        if not day:
            continue
        payload = event.get("payload") or {}
        # The same key the rows are grouped under, so the two agree.
        sequence = payload.get("scene") or (
            str(payload.get("slate") or "").split("/")[0] or None
        )
        if not sequence:
            continue
        days.setdefault(str(sequence), set()).add(str(day))

    return {
        sequence: sorted(found, key=lambda d: (not d.isdigit(), int(d) if d.isdigit() else d))
        for sequence, found in days.items()
    }


@router.get("/sequences")
def get_sequences(production_id: str = "DEMO_PRODUCTION", shoot_day: str = "31") -> List[Dict[str, Any]]:
    """
    Returns aggregated sequence-level table rows with:
    - sequence (e.g. 27, 49, 117, +99BDF)
    - location (e.g. INT. GREAT HALL - DAY)
    - description (synopsis / scene description from script supervisor)
    - shoot_day (e.g. Day 31)
    - date (e.g. 28/07/2026)
    - cards (All unique Camera cards & Sound rolls)
    - camera_cards
    - sound_cards
    - script_log_doc (filename & doc_id)
    - camera_a_doc (filename & doc_id)
    - camera_b_doc (filename & doc_id)
    - camera_c_doc (filename & doc_id)
    - sound_log_doc (filename & doc_id)
    - silverstack_thumbnail_doc (filename & doc_id)
    - silverstack_volume_doc (filename & doc_id)
    - comments (aggregated notes across takes)
    - has_discrepancy (boolean)
    - is_wild_track (boolean)
    - is_vfx (boolean)
    - takes_count (number of takes)
    - takes (list of slates/takes in this sequence)
    """
    takes = get_takes(production_id=production_id, shoot_day=shoot_day)
    docs = list_documents(production_id=production_id, shoot_day=shoot_day)
    discrepancies = get_discrepancies(production_id=production_id, shoot_day=shoot_day)
    days_by_sequence = _sequence_shoot_days(production_id)

    # Document map for quick resolution
    doc_map: Dict[str, Optional[Dict[str, str]]] = {
        "script_log_doc": None,
        "camera_a_doc": None,
        "camera_b_doc": None,
        "camera_c_doc": None,
        "sound_log_doc": None,
        "silverstack_thumbnail_doc": None,
        "silverstack_volume_doc": None,
        "silverstack_clips_doc": None,
    }

    for d in docs:
        fname = d.get("filename", "")
        dtype = d.get("doc_type", "")
        ref = {"filename": fname, "doc_id": d.get("doc_id", "")}
        if "CAM_A" in fname:
            doc_map["camera_a_doc"] = ref
        elif "CAM_B" in fname:
            doc_map["camera_b_doc"] = ref
        elif "CAM_C" in fname:
            doc_map["camera_c_doc"] = ref
        elif "TCLog" in fname or "Editor" in fname or "scripte" in dtype:
            doc_map["script_log_doc"] = ref
        elif fname.endswith(".csv") or "sound" in dtype:
            doc_map["sound_log_doc"] = ref
        elif "Thumbnail" in fname or dtype == "silverstack_thumbnail":
            doc_map["silverstack_thumbnail_doc"] = ref
        elif "Volume" in fname or dtype == "silverstack_volume":
            doc_map["silverstack_volume_doc"] = ref
        elif "Clips" in fname or dtype == "silverstack_clips":
            doc_map["silverstack_clips_doc"] = ref

    scenes_dict: Dict[str, List[Dict[str, Any]]] = {}
    for t in takes:
        seq = t.get("scene") or (t.get("slate", "").split("/")[0] if "/" in t.get("slate", "") else t.get("slate", "")) or "UNKNOWN"
        if seq not in scenes_dict:
            scenes_dict[seq] = []
        scenes_dict[seq].append(t)

    sequence_records = []
    for seq, s_takes in sorted(scenes_dict.items(), key=lambda item: (item[0].isdigit(), item[0])):
        cam_cards = sorted(list({c for t in s_takes for c in t.get("camera_cards", [])}))
        snd_cards = sorted(list({c for t in s_takes for c in t.get("sound_cards", [])}))
        all_cards = cam_cards + snd_cards

        # Clean description from script notes and camera notes
        descriptions = []
        for t in s_takes:
            for dept_key in ["script", "camera"]:
                sn = t.get("belief", {}).get(dept_key, {}).get("note", "") or t.get("belief", {}).get(dept_key, {}).get("description", "")
                if sn:
                    cleaned = re.sub(r"LAC\s+Day:[^\n]+", "", sn)
                    cleaned = re.sub(r"\d{2}:\d{2}:\d{2}(?::\d{2})?", "", cleaned)
                    cleaned = re.sub(r"Scene\(s\):\s*\d+\s*", "", cleaned)
                    cleaned = re.sub(r"^\s*[-–>]+\s*", "", cleaned).strip()
                    if cleaned and len(cleaned) > 5 and cleaned not in descriptions:
                        descriptions.append(cleaned)
        # Prioritize primary action descriptions (e.g. LEAD plays / ORGAN)
        descriptions.sort(key=lambda d: ("LEAD plays" in d or "ORGAN" in d, "Shot on Day" in d, len(d)), reverse=True)
        desc_str = " | ".join(descriptions[:2]) if descriptions else "Recorded sequence"

        # Infer sequence location
        loc = "INT. GREAT HALL - DAY"
        if seq == "27":
            loc = "INT. GREAT HALL (ORGAN & NAVE) - DAY"
        elif seq == "49":
            loc = "INT. GREAT HALL (MAIN CONCERT STAGE) - DAY"
        elif seq == "117":
            loc = "INT. GREAT HALL (SANCTUARY ALTAR) - DAY"
        elif "WT" in seq.upper():
            loc = "INT. GREAT HALL (WILD TRACK AMBIENCE)"

        has_disc = any(
            any(d.get("entity_id", "").startswith(t.get("slate", "")) and not d.get("is_resolved") for d in discrepancies)
            for t in s_takes
        )
        is_wt = any(t.get("is_wild_track") for t in s_takes) or "WT" in seq.upper()
        is_vfx = any(t.get("is_vfx") for t in s_takes)

        # Comments aggregation
        cmts = []
        for t in s_takes:
            cam_n = t.get("belief", {}).get("camera", {}).get("note")
            if cam_n and cam_n not in cmts:
                cmts.append(cam_n)
            for af in t.get("audio_files", []):
                if af.get("note") and af.get("note") not in cmts:
                    cmts.append(f"Mixer: {af.get('note')}")
        cmt_str = " ; ".join(cmts[:3]) if cmts else "All takes recorded and verified across camera and sound logs."

        rec = {
            "sequence": seq,
            "location": loc,
            "description": desc_str,
            "shoot_day": f"Day {shoot_day}",
            # Every day this sequence was shot, this one included. One entry is
            # the ordinary case; more than one means the row in front of you is
            # part of the sequence rather than all of it.
            "shoot_days": days_by_sequence.get(seq, [str(shoot_day)]),
            "date": s_takes[0].get("recording_date") or "28/07/2026",
            "cards": all_cards,
            "camera_cards": cam_cards,
            "sound_cards": snd_cards,
            "script_log_doc": doc_map.get("script_log_doc"),
            "camera_a_doc": doc_map.get("camera_a_doc"),
            "camera_b_doc": doc_map.get("camera_b_doc"),
            "camera_c_doc": doc_map.get("camera_c_doc"),
            "sound_log_doc": doc_map.get("sound_log_doc"),
            "silverstack_thumbnail_doc": doc_map.get("silverstack_thumbnail_doc"),
            "silverstack_volume_doc": doc_map.get("silverstack_volume_doc"),
            "silverstack_clips_doc": doc_map.get("silverstack_clips_doc"),
            "comments": cmt_str,
            "has_discrepancy": has_disc,
            "is_wild_track": is_wt,
            "is_vfx": is_vfx,
            "is_mos": any(t.get("is_mos") for t in s_takes),
            "takes_count": len(s_takes),
            "circled_takes": [f"{t.get('slate')} T{t.get('take_id')}" for t in s_takes if t.get("is_starred")],
            "circled_takes_count": len([t for t in s_takes if t.get("is_starred")]),
            "takes": [f"{t.get('slate')} T{t.get('take_id')}{' ⭐' if t.get('is_starred') else ''}" for t in s_takes[:8]],
        }

        # Attach sequence / scene level requirements
        all_reqs = spine_writer.list_requirements(production_id=production_id, shoot_day=shoot_day)
        seq_reqs = [
            r for r in all_reqs
            if (r.get("target_type") == "scene" and r.get("target_id") == seq)
            or any(r.get("target_id") == t.get("slate") or r.get("target_id") == f"{t.get('slate')}_{t.get('take_id')}" for t in s_takes)
        ]
        rec["requirements"] = seq_reqs
        rec["open_requirements_count"] = sum(1 for r in seq_reqs if r.get("status") in ["open", "in_progress", "blocked"])
        rec["resolved_requirements_count"] = sum(1 for r in seq_reqs if r.get("status") == "resolved")

        sequence_records.append(rec)

    return sequence_records


# ==========================================
# User Identity & Passwordless Auth Routes
# ==========================================
@router.get("/users")
def get_team_users():
    return spine_writer.list_users()


@router.post("/auth/login")
def login(req: LoginRequest):
    val = req.handle_or_email.strip()
    user = spine_writer.get_user(val)
    if not user:
        # Auto-create profile for new team member
        handle = val if val.startswith("@") else f"@{val}"
        name = handle.lstrip("@").replace(".", " ").replace("_", " ").title()
        user = spine_writer.register_user(
            handle=handle,
            name=name,
            email=f"{handle.lstrip('@')}@production.film" if "@" not in val else val,
            role="Editor / Contributor",
            avatar_color="#8b5cf6",
        )
    return {
        "status": "AUTHENTICATED",
        "user": user,
        "token": f"token_{user['handle']}",
    }


@router.get("/auth/me")
def get_current_user(handle: Optional[str] = None):
    if handle:
        user = spine_writer.get_user(handle)
        if user:
            return user
    # Fallback to default user
    users = spine_writer.list_users()
    return users[0] if users else {"handle": "@director", "name": "Director", "role": "Director"}


# ==========================================
# Wrap Rescue Agent
# ==========================================
@router.post("/agents/wrap-rescue/run")
async def run_wrap_rescue_agent(req: RunWrapRescueRequest):
    """
    Runs the hackathon-facing multi-step agent.

    The workflow first projects the analytical mirror, then queries ClickHouse
    through the official mcp-clickhouse server when configured. Requirement
    writes are schema-validated by the same store the UI uses.
    """
    agent = WrapRescueAgent(
        spine_writer=spine_writer,
        reconciler=reconciler,
        legacy_mcp_server=mcp_server,
    )
    result = await agent.run(
        production_id=req.production_id,
        shoot_day=req.shoot_day,
        actor=req.actor,
        max_blockers=req.max_blockers,
    )

    event_broker.publish_sync(SpineLiveEvent(
        event_type="WRAP_RESCUE_RUN",
        production_id=result.production_id,
        shoot_day=result.shoot_day,
        actor_handle=result.actor,
        target_type="production",
        target_id=result.production_id,
        target_label=result.production_id,
        summary=(
            f"Wrap Rescue ranked {len(result.blockers)} blockers and recorded "
            f"{len(result.requirement_actions)} requirement actions"
        ),
        data={
            "mcp_available": result.mcp_status.available,
            "tool_calls": len(result.tool_calls),
            "blockers": len(result.blockers),
            "requirement_actions": len(result.requirement_actions),
        },
    ))

    return result.model_dump()


@router.post("/agents/assistant-editor-queue/run")
def run_assistant_editor_queue(req: RunAssistantQueueRequest):
    """
    Plans a same-day assistant editor batch from clean scene groups.

    Clean is deterministic here: no active discrepancies or blocking
    requirements, with enough script/camera/sound/offload evidence to start
    turnover instead of investigation.
    """
    _require_active_production(req.production_id)
    agent = AssistantEditorQueueAgent(
        spine_writer=spine_writer,
        discrepancy_source=mcp_server,
    )
    try:
        result = agent.run(
            production_id=req.production_id,
            shoot_day=req.shoot_day,
            actor=req.actor,
            assignee=req.assignee,
            max_scenes=req.max_scenes,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    event_broker.publish_sync(SpineLiveEvent(
        event_type="ASSISTANT_QUEUE_RUN",
        production_id=result.production_id,
        shoot_day=result.shoot_day,
        actor_handle=result.actor,
        target_type="production",
        target_id=result.production_id,
        target_label=result.production_id,
        summary=result.summary,
        data={
            "assignees": result.assignees,
            "scenes": len(result.scenes),
            "requirement_actions": len(result.requirement_actions),
        },
    ))

    return result.model_dump()


@router.get("/agents/assistant-editor-queue/assignments")
def list_assistant_editor_queue_assignments(production_id: str, active_only: bool = False):
    production = spine_writer.get_production(production_id)
    if not production:
        raise HTTPException(status_code=404, detail=f"No production {production_id}")
    rows = assistant_queue_requirements(spine_writer, production["production_id"])
    if active_only:
        rows = [row for row in rows if row.get("status") != "resolved"]
    return rows


# ==========================================
# Requirements Management Routes
# ==========================================
@router.post("/requirements")
def create_requirement(req: CreateRequirementRequest):
    req_dict = req.model_dump()
    created = spine_writer.create_requirement(req_dict)

    # 1. Publish requirement creation event to spine
    spine_writer.append_event({
        "event_id": str(uuid.uuid4()),
        "production_id": created["production_id"],
        "shoot_day": created["shoot_day"],
        "axis": "intent",
        "department": "editorial",
        "doc_type": "requirement_event",
        "entity_type": "requirement",
        "payload": created,
        "metadata": {
            "requirement_id": created["requirement_id"],
            "action": "created",
            "assigned_to": created["assigned_to"],
            "created_by": created["created_by"],
        },
        "timestamp": created["created_at"],
    })

    # 2. Dispatch alert notification to the responsible assignee
    if created["assigned_to"]:
        spine_writer.create_notification({
            "production_id": created["production_id"],
            "recipient_handle": created["assigned_to"],
            "actor_handle": created["created_by"],
            "notification_type": "ASSIGNED",
            "requirement_id": created["requirement_id"],
            "title": f"New Requirement on {created['target_label']}",
            "message": f"{created['created_by']} assigned you ({created['priority'].upper()}): {created['title']}",
            "target_type": created["target_type"],
            "target_id": created["target_id"],
            "target_label": created["target_label"],
        })

    analytics.capture(created["created_by"], "requirement_raised", {
        "production_id": created["production_id"],
        "shoot_day": created["shoot_day"],
        "target_type": created["target_type"],
        "target_id": created["target_id"],
        "category": created["category"],
        "priority": created["priority"],
        "assigned_to": created["assigned_to"],
    })

    event_broker.publish_sync(SpineLiveEvent(
        event_type="REQUIREMENT_CREATED",
        production_id=created["production_id"],
        shoot_day=created["shoot_day"],
        actor_handle=created["created_by"],
        target_type=created["target_type"],
        target_id=created["target_id"],
        target_label=created["target_label"],
        summary=f"New requirement '{created['title']}' assigned to {created['assigned_to']}",
        data={"requirement_id": created["requirement_id"], "assigned_to": created["assigned_to"]},
    ))

    return created


@router.get("/requirements")
def list_requirements(
    production_id: Optional[str] = None,
    shoot_day: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    assigned_to: Optional[str] = None,
    created_by: Optional[str] = None,
    status: Optional[str] = None,
):
    return spine_writer.list_requirements(
        production_id=production_id,
        shoot_day=shoot_day,
        target_type=target_type,
        target_id=target_id,
        assigned_to=assigned_to,
        created_by=created_by,
        status=status,
    )


@router.get("/requirements/activity")
def requirement_activity(production_id: str, limit: int = 200):
    """
    Every requirement change on a production, newest first.

    Declared above the by-id read so that 'activity' is not taken for an id.
    """
    return spine_writer.requirement_history(production_id=production_id, limit=limit)


@router.get("/requirements/{requirement_id}/history")
def requirement_history(requirement_id: str, limit: int = 200):
    """
    How this requirement got where it is -- who blocked it, who handed it on.

    Kept even for a requirement that has since been deleted: a requirement that
    was raised and then removed is a thing that happened.
    """
    return spine_writer.requirement_history(requirement_id=requirement_id, limit=limit)


@router.get("/requirements/{requirement_id}")
def get_requirement(requirement_id: str):
    req = spine_writer.get_requirement(requirement_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return req


@router.patch("/requirements/{requirement_id}")
def update_requirement(requirement_id: str, updates: UpdateRequirementRequest):
    """
    Edits a requirement, and tells the people the edit is about.

    Handing a requirement to somebody who is never told about it is the same as
    dropping it, and a requirement moving to blocked is exactly the thing the
    person who raised it needs to hear. Neither used to reach anyone: only
    creating and resolving sent word, and both of those are done by someone
    already looking at the requirement.
    """
    before = spine_writer.get_requirement(requirement_id)
    if not before:
        raise HTTPException(status_code=404, detail="Requirement not found")

    was_assigned_to = before.get("assigned_to")
    was_status = before.get("status")

    update_data = {k: v for k, v in updates.model_dump().items() if v is not None}
    actor = update_data.pop("updated_by", None) or "@user"
    if not actor.startswith("@"):
        actor = f"@{actor}"

    try:
        updated = spine_writer.update_requirement(requirement_id, update_data, actor=actor)
    except requirement_store.UnknownRequirementValue as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Requirement not found")

    def notify(recipient: Optional[str], kind: str, message: str) -> None:
        # Never notify somebody about their own action: they just did it.
        if not recipient or recipient.lower() == actor.lower():
            return
        spine_writer.create_notification({
            "production_id": updated["production_id"],
            "recipient_handle": recipient,
            "actor_handle": actor,
            "notification_type": kind,
            "requirement_id": updated["requirement_id"],
            "title": f"{updated['target_label']}: {updated['title']}",
            "message": message,
            "target_type": updated["target_type"],
            "target_id": updated["target_id"],
            "target_label": updated["target_label"],
        })

    now_assigned_to = updated.get("assigned_to")
    if now_assigned_to and now_assigned_to != was_assigned_to:
        notify(
            now_assigned_to,
            "ASSIGNED",
            f"{actor} handed you this {updated['priority']} requirement: {updated['title']}",
        )

    now_status = updated.get("status")
    if now_status and now_status != was_status:
        notify(
            updated.get("created_by"),
            "STATUS_CHANGED",
            f"{actor} moved this from {was_status} to {now_status}: {updated['title']}",
        )

    if now_assigned_to != was_assigned_to or now_status != was_status:
        analytics.capture(actor, "requirement_moved", {
            "production_id": updated["production_id"],
            "shoot_day": updated["shoot_day"],
            "target_type": updated["target_type"],
            "target_id": updated["target_id"],
            "category": updated["category"],
            "priority": updated["priority"],
            "from_status": was_status,
            "to_status": now_status,
            "handed_over": now_assigned_to != was_assigned_to,
            "assigned_to": now_assigned_to,
        })

    event_broker.publish_sync(SpineLiveEvent(
        event_type="REQUIREMENT_UPDATED",
        production_id=updated["production_id"],
        shoot_day=updated["shoot_day"],
        actor_handle=actor,
        target_type=updated["target_type"],
        target_id=updated["target_id"],
        target_label=updated["target_label"],
        summary=f"Requirement '{updated['title']}' is now {now_status}, assigned to {now_assigned_to}",
        data={
            "requirement_id": updated["requirement_id"],
            "status": now_status,
            "assigned_to": now_assigned_to,
        },
    ))

    return updated


@router.post("/requirements/{requirement_id}/resolve")
def resolve_requirement(requirement_id: str, body: ResolveRequirementRequest):
    resolved = spine_writer.resolve_requirement(
        requirement_id=requirement_id,
        resolution_note=body.resolution_note,
        resolved_by=body.resolved_by,
    )
    if not resolved:
        raise HTTPException(status_code=404, detail="Requirement not found")

    # 1. Publish resolution event to spine
    spine_writer.append_event({
        "event_id": str(uuid.uuid4()),
        "production_id": resolved["production_id"],
        "shoot_day": resolved["shoot_day"],
        "axis": "belief",
        "department": "editorial",
        "doc_type": "requirement_event",
        "entity_type": "requirement",
        "payload": resolved,
        "metadata": {
            "requirement_id": resolved["requirement_id"],
            "action": "resolved",
            "resolved_by": resolved["resolved_by"],
        },
        "timestamp": resolved["resolved_at"],
    })

    # 2. Dispatch alert notification back to the original caller/creator
    creator = resolved.get("created_by")
    if creator and creator.lower() != resolved["resolved_by"].lower():
        spine_writer.create_notification({
            "production_id": resolved["production_id"],
            "recipient_handle": creator,
            "actor_handle": resolved["resolved_by"],
            "notification_type": "RESOLVED",
            "requirement_id": resolved["requirement_id"],
            "title": f"Requirement Resolved on {resolved['target_label']}",
            "message": f"{resolved['resolved_by']} marked resolved: '{resolved['title']}' — \"{body.resolution_note}\"",
            "target_type": resolved["target_type"],
            "target_id": resolved["target_id"],
            "target_label": resolved["target_label"],
        })

    analytics.capture(resolved["resolved_by"], "requirement_resolved", {
        "production_id": resolved["production_id"],
        "shoot_day": resolved["shoot_day"],
        "target_type": resolved["target_type"],
        "target_id": resolved["target_id"],
        "category": resolved["category"],
        "priority": resolved["priority"],
        "raised_by": resolved.get("created_by"),
        "hours_owed": _hours_between(resolved.get("created_at"), resolved.get("resolved_at")),
    })

    event_broker.publish_sync(SpineLiveEvent(
        event_type="REQUIREMENT_RESOLVED",
        production_id=resolved["production_id"],
        shoot_day=resolved["shoot_day"],
        actor_handle=resolved["resolved_by"],
        target_type=resolved["target_type"],
        target_id=resolved["target_id"],
        target_label=resolved["target_label"],
        summary=f"Requirement '{resolved['title']}' marked resolved by {resolved['resolved_by']}",
        data={"requirement_id": requirement_id, "created_by": resolved.get("created_by")},
    ))

    return resolved


@router.delete("/requirements/{requirement_id}")
def delete_requirement(requirement_id: str, deleted_by: str = "@user"):
    existing = spine_writer.get_requirement(requirement_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Requirement not found")

    spine_writer.delete_requirement(requirement_id, actor=deleted_by)
    event_broker.publish_sync(SpineLiveEvent(
        event_type="REQUIREMENT_DELETED",
        production_id=existing["production_id"],
        shoot_day=existing["shoot_day"],
        actor_handle=deleted_by,
        target_type="requirement",
        target_id=requirement_id,
        target_label=requirement_id,
        summary=f"Requirement deleted ({requirement_id})",
    ))
    return {"status": "DELETED", "requirement_id": requirement_id}



# ==========================================
# Editorial Tags
#
# What an assistant editor marks on a scene or a shot: how far along it is, what
# work it still needs, and what kind of shot it is. Production-scoped, not
# day-scoped -- a shot is covered across whatever days it took, and where it has
# got to in the edit is a property of the shot, not of the day a page was filed.
# ==========================================


class SetEditorialTagRequest(BaseModel):
    production_id: str
    target_type: str = Field(description="scene or shot")
    target_id: str = Field(description="a scene number ('117') or a slate ('27/7')")
    status: Optional[str] = None
    needs: List[str] = Field(default_factory=list)
    descriptors: List[str] = Field(default_factory=list)
    note: Optional[str] = None
    updated_by: Optional[str] = None


@router.get("/tags/vocabulary")
def get_tag_vocabulary():
    """
    The controlled vocabulary, so the interface spells these in one place only.

    It is closed on purpose: a board that answers "what is left to do" can only
    count what everyone spells the same way.
    """
    return tag_store.vocabulary()


@router.get("/dashboard")
def get_production_dashboard(production_id: str, recent_limit: int = 12):
    """
    Where a production has got to, and what it is waiting on.

    The denominator comes from the spine rather than from the tags: what nobody
    has tagged is the largest and most useful number on a board, and counting
    only tagged things would make three mounted shots read the same in a
    production of three as in a production of two hundred.

    Every shoot day is included. A shot is covered across whatever days it took,
    so a per-day view of progress would split one shot's story in two.
    """
    events = spine_writer.get_events(production_id=production_id)
    known_shots, known_scenes = set(), set()
    for event in events:
        if event.get("entity_type") != "take":
            continue
        payload = event.get("payload", {})
        slate = payload.get("slate")
        if slate:
            known_shots.add(slate)
            known_scenes.add(str(slate).split("/")[0])
        scene = payload.get("scene")
        if scene:
            known_scenes.add(str(scene))

    progress = tag_store.progress(production_id, sorted(known_shots), sorted(known_scenes))
    progress["vocabulary"] = tag_store.vocabulary()
    progress["recent"] = tag_store.history(production_id, limit=max(1, min(recent_limit, 50)))
    progress["pre_editing"] = pre_editing_progress(spine_writer, production_id)
    progress["crew_workload"] = workload.crew_workload(spine_writer, production_id)
    progress["shoot_days"] = sorted(
        {e.get("shoot_day") for e in events if e.get("shoot_day")},
        key=lambda d: int(d) if str(d).isdigit() else 9999,
    )
    return progress


@router.get("/tags/summary")
def get_tag_summary(production_id: str):
    """How many targets sit at each status, and how many await each kind of work."""
    return spine_writer.summarize_editorial_tags(production_id)


@router.get("/tags/history")
def get_tag_history(
    production_id: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    limit: int = 200,
):
    """
    How a target got to where it is, newest first.

    The tag itself says what is true now; this says who said so and when, which
    is the question asked when a board claims a scene is finished and somebody
    on the floor disagrees.
    """
    try:
        return tag_store.history(production_id, target_type, target_id, limit)
    except tag_store.UnknownTagValue as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/tags")
def list_tags(
    production_id: str,
    target_type: Optional[str] = None,
    status: Optional[str] = None,
    need: Optional[str] = None,
    descriptor: Optional[str] = None,
):
    try:
        return spine_writer.list_editorial_tags(
            production_id,
            target_type=target_type,
            status=status,
            need=need,
            descriptor=descriptor,
        )
    except tag_store.UnknownTagValue as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/tags")
def set_tag(request: SetEditorialTagRequest):
    """
    Writes the whole tag for one target, replacing what was there.

    Replacing rather than merging is what makes "this no longer needs SFX"
    expressible; with merge semantics a client could only ever add.
    """
    try:
        tag = spine_writer.set_editorial_tag(
            production_id=request.production_id,
            target_type=request.target_type,
            target_id=request.target_id,
            status=request.status,
            needs=request.needs,
            descriptors=request.descriptors,
            note=request.note,
            updated_by=request.updated_by,
        )
    except tag_store.UnknownTagValue as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Editorial progress: how a production moves through the stages, and who
    # moves it. The note somebody typed on the tag is not sent.
    analytics.capture(tag.get("updated_by"), "editorial_tag_set", {
        "production_id": tag["production_id"],
        "target_type": tag["target_type"],
        "target_id": tag["target_id"],
        "status": tag.get("status"),
        "needs_count": len(tag.get("needs") or []),
        "descriptor_count": len(tag.get("descriptors") or []),
    })

    event_broker.publish_sync(SpineLiveEvent(
        event_type="EDITORIAL_TAG_SET",
        production_id=request.production_id,
        shoot_day="ALL",
        actor_handle=tag.get("updated_by") or "@user",
        target_type=tag["target_type"],
        target_id=tag["target_id"],
        target_label=f"{tag['target_type'].capitalize()} {tag['target_id']}",
        summary=f"Tagged {tag['target_type']} {tag['target_id']}",
        data={"status": tag["status"], "needs": tag["needs"],
              "descriptors": tag["descriptors"]},
    ))
    return tag


@router.delete("/tags")
def clear_tag(
    production_id: str, target_type: str, target_id: str,
    cleared_by: Optional[str] = None,
):
    try:
        cleared = spine_writer.clear_editorial_tag(
            production_id, target_type, target_id, cleared_by)
    except tag_store.UnknownTagValue as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not cleared:
        raise HTTPException(status_code=404, detail="No tag on that target")

    # Clearing is as much a change as setting. Publishing only the set left the
    # other editors' boards showing a tag that had been taken off.
    event_broker.publish_sync(SpineLiveEvent(
        event_type="EDITORIAL_TAG_CLEARED",
        production_id=production_id,
        shoot_day="ALL",
        actor_handle=cleared_by or "@user",
        target_type=target_type,
        target_id=target_id,
        target_label=f"{target_type.capitalize()} {target_id}",
        summary=f"Cleared the tag on {target_type} {target_id}",
    ))
    return {"status": "CLEARED", "target_type": target_type, "target_id": target_id}



# ==========================================
# Real-Time Alerts & Notification Routes
# ==========================================
@router.get("/notifications")
def get_notifications(user_handle: str, unread_only: bool = False):
    return {
        "recipient_handle": user_handle,
        # Counted in SQL rather than by listing every alert and measuring the
        # list: the badge is polled and does not need the messages.
        "unread_count": spine_writer.count_unread_notifications(user_handle),
        "notifications": spine_writer.list_notifications(
            recipient_handle=user_handle, unread_only=unread_only
        ),
    }


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str):
    existing = spine_writer.get_notification(notification_id)
    if not existing or not spine_writer.mark_notification_read(notification_id):
        raise HTTPException(status_code=404, detail="Notification not found")

    # How long an alert sat before anybody opened it. handoffs.md: "No
    # acknowledgement is recorded anywhere." This is that record.
    analytics.capture(existing["recipient_handle"], "alert_acknowledged", {
        "production_id": existing["production_id"],
        "notification_type": existing["notification_type"],
        "target_type": existing["target_type"],
        "target_id": existing["target_id"],
        "raised_by": existing["actor_handle"],
        "hours_unread": _hours_between(existing.get("created_at"), None),
    })
    return {"status": "READ", "notification_id": notification_id, "success": True}


@router.post("/notifications/read-all")
def mark_all_notifications_read(user_handle: str):
    count = spine_writer.mark_all_notifications_read(user_handle)
    return {"status": "ALL_READ", "user_handle": user_handle, "updated_count": count}


@router.post("/assistant/explain")
def explain_take(req: AskAssistantRequest):
    explanation = assistant.explain_take(
        production_id=req.production_id,
        shoot_day=req.shoot_day,
        slate=req.slate,
        take_id=req.take_id,
    )
    return {"explanation": explanation}


@router.get("/analytics")
def get_production_analytics(production_id: str):
    """
    The questions the analytical spine is for.

    Every day of a production at once, grouped and counted -- the kind of
    question whose answer is a scan. The row store answers "this take, this
    day" and is the right shape for that; this is the other kind.

    `available` is false when there is no ClickHouse, and the client says so
    rather than drawing an empty chart. A panel that cannot fill looks exactly
    like a production with nothing in it.
    """
    client = spine_writer.client
    if client is None or not spine_writer.mirror_available():
        return {
            "production_id": production_id,
            "available": False,
            "reason": (
                "No analytical spine is connected. Set CLICKHOUSE_HOST to enable it; "
                "everything else in the app works without it."
            ),
        }

    # Computed before the response so it can also reach Prometheus: the gauge
    # and the panel must not be able to disagree about the same measurement.
    sync_matrix = spine_analytics.sync_matrix(client, production_id)
    TelemetryExporter.record_sync_lag(production_id, sync_matrix or [])

    return {
        "production_id": production_id,
        "available": True,
        "shape": spine_analytics.production_shape(client, production_id),
        "arrivals": spine_analytics.department_arrivals(client, production_id),
        "roll_disagreements": spine_analytics.roll_disagreements(client, production_id),
        "scene_coverage": spine_analytics.scene_coverage(client, production_id),
        "editorial_state": spine_analytics.editorial_state(client, production_id),
        "requirement_ageing": spine_analytics.requirement_ageing(client, production_id),
        # The acknowledgement axis. REQ-10 asks for a department sync matrix
        # and it was a gauge that could never fill; these answer the same
        # question from a fact the product records rather than a wrap time
        # with no date on it.
        # The department sync matrix REQ-10 asks for, computable since the
        # shoot day gained a calendar date. Every row says whether it measures
        # a handover or a backfill; they are different facts.
        "sync_matrix": sync_matrix,
        "time_to_acknowledge": spine_analytics.time_to_acknowledge(client, production_id),
        "unacknowledged_requirements": spine_analytics.unacknowledged_requirements(client, production_id),
        "unreviewed_days": spine_analytics.unreviewed_days(client, production_id),
        "department_attention": spine_analytics.department_attention(client, production_id),
        "tables": spine_analytics.table_sizes(client),
    }


def _seconds_since_target_created(
    production_id: str, target_type: str, target_id: str
) -> Optional[float]:
    """
    How long the target had existed when somebody saw it, or None.

    None where the creation time is not known -- a scene or a shoot day was
    never "created" at a moment. None rather than zero: zero would say it was
    acknowledged instantly, which is a claim, and it would drag every average
    it appears in towards a number nobody measured.
    """
    created_at: Optional[str] = None
    if target_type == "requirement":
        found = spine_writer.get_requirement(target_id)
        created_at = (found or {}).get("created_at")
    elif target_type == "notification":
        for note in spine_writer.get_notifications(None):
            if note.get("notification_id") == target_id:
                created_at = note.get("created_at")
                break

    if not created_at:
        return None
    try:
        started = datetime.fromisoformat(created_at)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return max((datetime.now(timezone.utc) - started).total_seconds(), 0.0)
    except (ValueError, TypeError):
        return None


class RecordActivityRequest(BaseModel):
    production_id: str
    actor: str = Field(description="a role token like @sound_supervisor, never a crew name")
    action: str = Field(description="viewed or acknowledged")
    target_type: str
    target_id: str
    shoot_day: str = ""
    department: str = ""
    target_label: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)


@router.post("/activity")
def record_activity(req: RecordActivityRequest):
    """
    Records that somebody saw something, or took it on.

    The gap `handoffs.md` names: "No acknowledgement is recorded anywhere." A
    blocker is raised, a notification goes out, and nothing can answer whether
    the person it was for ever saw it.

    `viewed` and `acknowledged` stay apart. A view is weak evidence about
    attention; an acknowledgement is a claim somebody made, and only the second
    can carry an obligation.

    How long the target had existed is computed here rather than sent by the
    client: a browser clock is not a witness, and time-to-acknowledge is the
    whole point of the record.
    """
    age = _seconds_since_target_created(
        req.production_id, req.target_type, req.target_id,
    )
    try:
        event = spine_writer.record_activity(
            production_id=req.production_id,
            actor=req.actor,
            action=req.action,
            target_type=req.target_type,
            target_id=req.target_id,
            shoot_day=req.shoot_day,
            department=req.department,
            target_label=req.target_label,
            seconds_since_target_created=age,
            context=req.context,
        )
    except activity_store.UnknownActivityValue as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    analytics.capture(req.actor, f"entity_{req.action}", {
        "production_id": req.production_id,
        "shoot_day": req.shoot_day,
        "department": req.department,
        "target_type": req.target_type,
    })
    return event


@router.get("/activity")
def get_activity(production_id: str, target_type: str, target_id: str):
    """
    Everything anybody did to one thing, and whether it was taken on.

    `acknowledged_at` is null when nobody has. Null rather than false: "nobody
    has acknowledged this" and "this needs no acknowledgement" are different,
    and a boolean cannot tell them apart.
    """
    events = spine_writer.activity_for_target(production_id, target_type, target_id)
    ack = spine_writer.acknowledgement_of(production_id, target_type, target_id)
    return {
        "production_id": production_id,
        "target_type": target_type,
        "target_id": target_id,
        "events": events,
        "viewed_by": sorted({e["actor"] for e in events if e["action"] == "viewed"}),
        "acknowledged_by": ack["actor"] if ack else None,
        "acknowledged_at": ack["created_at"] if ack else None,
    }


# ---------------------------------------------------------------------------
# Script Breakdown, DoP Cinematography & Previz Storyboard Endpoints
# ---------------------------------------------------------------------------

from backend.app.script.parser import parse_fountain_screenplay, parse_screenplay_file, clean_character_name, Screenplay, ScreenplayScene, CharacterProfile
from backend.app.script.dop_presets import DOP_MASTER_PRESETS, resolve_dop_specification, suggest_dop_preset_metadata
from backend.app.script.breakdown_engine import breakdown_scene_to_shots, ShotProposal
from backend.app.script.storyboard_generator import render_cinematic_storyboard_svg
from backend.app.script.character_ai import enrich_screenplay_characters


class SuggestDoPPresetRequest(BaseModel):
    focal_length: Optional[int] = 35
    aperture: Optional[str] = "T2.8"
    color_temperature_k: Optional[int] = 5600
    white_balance_k: Optional[int] = 5600
    lighting_ratio: Optional[str] = "4:1"
    sensor_format: Optional[str] = "Large Format 35mm"
    lut_emulation: Optional[str] = "Kodak 5219 Vision3 500T"
    custom_prompt: Optional[str] = ""
    aspect_ratio: Optional[str] = "2.39:1"


class ScriptParseRequest(BaseModel):
    script_text: str
    title: str = "Screenplay"
    # Attaching the script to a production is what lets an editor open the
    # scene behind a slate. Optional: the Script Studio is usable on its own.
    production_id: Optional[str] = None


class ScriptBreakdownRequest(BaseModel):
    scene: ScreenplayScene
    dop_preset: Optional[str] = "Roger Deakins"
    dop_overrides: Optional[Dict[str, Any]] = None
    custom_prompt: Optional[str] = None
    aspect_ratio: str = "2.39:1"
    character_profiles: Optional[List[CharacterProfile]] = None
    # Which screenplay this scene belongs to, so the breakdown can be kept.
    # Optional: a caller working against no stored screenplay still gets its
    # shots back.
    script_id: Optional[str] = None


class SaveBreakdownRequest(BaseModel):
    shots: List[Dict[str, Any]]


class GenerateStoryboardRequest(BaseModel):
    shot_id: str
    prompt: str
    scene_number: str = "1"
    shot_number: str = "1"
    shot_size: str = "WS"
    focal_length: int = 35
    aperture: str = "T2.8"
    dop_preset: str = "Roger Deakins"
    camera_letter: str = "A"
    lighting_ratio: str = "4:1"
    color_temp_k: int = 5600
    lut_emulation: str = "Kodak Vision3 500T 5219"
    aspect_ratio: str = "2.39:1"
    character_details: Optional[str] = None
    economy_mode: bool = False


class UpdateCharacterRequest(BaseModel):
    id: str
    name: str
    # Identifies which screenplay this character belongs to. Required so the
    # edit is stored against the right script rather than discarded.
    script_id: str
    role: Optional[str] = None
    actor_reference: Optional[str] = None
    look_and_costume: Optional[str] = None
    facial_features: Optional[str] = None
    personality_traits: Optional[List[str]] = None
    avatar_url: Optional[str] = None
    portrait_prompt: Optional[str] = None


class GeneratePortraitRequest(BaseModel):
    character_id: str
    character_name: str
    actor_reference: str
    look_and_costume: str
    facial_features: str
    role: str = "Key Character"
    dop_preset: str = "Roger Deakins"
    economy_mode: bool = False
    # Which screenplay this character belongs to, so the portrait can be kept.
    # Optional: a caller generating one ad hoc, against no stored screenplay,
    # still gets its image back.
    script_id: Optional[str] = None


@router.post("/script/characters/update")
def update_character_profile(req: UpdateCharacterRequest):
    """
    Persists edits to a character's look, facial appearance, costume, role and
    personality traits, against the screenplay they belong to.
    """
    updates = req.model_dump(exclude_none=True, exclude={"id", "name", "script_id"})
    saved = spine_writer.update_character_profile(
        script_id=req.script_id,
        character_id=req.id,
        updates=updates,
    )

    if saved is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No character '{req.id}' stored for script '{req.script_id}'. "
                "Upload or parse the screenplay before editing its characters."
            ),
        )

    return {"status": "updated", "script_id": req.script_id, "character": saved}


@router.get("/script/{script_id}/characters")
def list_character_profiles(script_id: str):
    """
    Returns the stored character profiles for a screenplay, including any edits.
    """
    screenplay = spine_writer.get_screenplay(script_id)
    if screenplay is None:
        raise HTTPException(status_code=404, detail=f"Unknown script '{script_id}'.")

    return {
        "script_id": script_id,
        "title": screenplay.get("title"),
        "characters": spine_writer.get_character_profiles(script_id),
    }


@router.get("/script/{script_id}/characters/{character_name}/lines")
def get_character_lines(script_id: str, character_name: str):
    """
    Every line this character speaks, in script order, with where to find it.

    The profile says who somebody is; this is the evidence for it. A director
    reading "guarded, evasive" has no way to check that against the script
    without paging through the whole thing, and a reading nobody can check is
    just an assertion with a chart around it.

    Lines are recovered by re-parsing each stored scene rather than from a
    dialogue table, because the scene body is what was persisted and the
    parser that produced it is the same one used here. A second extractor
    would drift from the first.
    """
    screenplay = spine_writer.get_screenplay(script_id)
    if screenplay is None:
        raise HTTPException(status_code=404, detail=f"Unknown script '{script_id}'.")

    wanted = clean_character_name(character_name).upper()
    scenes = spine_writer.get_screenplay_scenes(script_id)

    lines: List[Dict[str, Any]] = []
    scenes_present: List[str] = []
    for scene in scenes:
        body = scene.get("body") or ""
        if not body.strip():
            continue
        parsed = parse_fountain_screenplay(body, title=screenplay.get("title") or "Screenplay")
        spoke_here = False
        for parsed_scene in parsed.scenes:
            for index, dialogue in enumerate(parsed_scene.dialogues):
                if clean_character_name(dialogue.character).upper() != wanted:
                    continue
                spoke_here = True
                lines.append({
                    "ordinal": scene.get("ordinal"),
                    "scene_number": scene.get("scene_number"),
                    "heading": scene.get("heading"),
                    "index_in_scene": index,
                    "parenthetical": dialogue.parenthetical,
                    "line": dialogue.line,
                })
        if spoke_here:
            scenes_present.append(str(scene.get("scene_number")))

    has_profile = any(
        clean_character_name(c.get("name", "")).upper() == wanted
        for c in spine_writer.get_character_profiles(script_id)
    )

    # Character profiles are built from dialogue cues, so a character who never
    # speaks has no profile -- and without this, "appears and never speaks"
    # would be indistinguishable from "not in this script". They are different
    # facts, and telling a director the second when the first is true sends
    # them looking for the wrong thing.
    #
    # Matched on a whole-word uppercase occurrence, which is the screenplay
    # convention for naming someone in action. Case-sensitive on purpose: a
    # lowercase "lead" in prose is the English word, not the character.
    appears = has_profile
    if not appears and wanted:
        pattern = re.compile(rf"(?<![A-Z0-9]){re.escape(wanted)}(?![A-Z0-9])")
        appears = any(pattern.search(scene.get("body") or "") for scene in scenes)

    return {
        "script_id": script_id,
        "character": character_name,
        "known_character": appears,
        # Kept apart so a caller can tell why there are no lines.
        "has_profile": has_profile,
        "scenes_present": scenes_present,
        "line_count": len(lines),
        "lines": lines,
    }


@router.post("/script/characters/generate-portrait")
async def generate_character_portrait(req: GeneratePortraitRequest):
    """
    Generates a photorealistic 35mm motion picture portrait / headshot for a character.
    """
    from backend.app.script.ai_image_service import generate_character_portrait_image

    res = await generate_character_portrait_image(
        character_name=req.character_name,
        actor_reference=req.actor_reference,
        look_and_costume=req.look_and_costume,
        facial_features=req.facial_features,
        role=req.role,
        dop_preset=req.dop_preset,
        economy_mode=req.economy_mode
    )

    # Kept against the character, not just handed back. A portrait costs a
    # generation to make and is the whole point of the cast profiler -- the
    # same face in every frame -- so leaving it in the browser's memory meant
    # a reload threw away both the likeness and the credit spent on it.
    saved = False
    if req.script_id:
        saved = spine_writer.update_character_profile(
            script_id=req.script_id,
            character_id=req.character_id,
            updates={
                "avatar_url": res["image_url"],
                "portrait_prompt": res["compiled_prompt"],
            },
        ) is not None

    return {
        "character_id": req.character_id,
        "character_name": req.character_name,
        "image_url": res["image_url"],
        "compiled_prompt": res["compiled_prompt"],
        "provider": res.get("provider", "AI Generative Engine"),
        # False when there was no screenplay to file it under, so the client
        # does not report a save that did not happen.
        "saved": saved,
    }


@router.get("/integrations/google-cloud")
def get_google_cloud_status():
    """
    Returns live Google Cloud & Gemini Enterprise Agent Platform runtime integration telemetry.
    """
    from backend.app.integrations.google_cloud import get_google_cloud_runtime_status
    return get_google_cloud_runtime_status()


def _persist_screenplay(
    screenplay: Screenplay,
    filename: Optional[str] = None,
    production_id: Optional[str] = None,
) -> Screenplay:
    """
    Registers a parsed screenplay and reattaches any previously saved character
    edits for the same script.

    The scene text is stored too. It used to live only in the Script Studio
    tab's memory, which meant an editor working a shot on the reconciliation
    side had no way to read the scene it came from.
    """
    merged = spine_writer.store_screenplay(
        script_id=screenplay.script_id,
        title=screenplay.title,
        author=screenplay.author,
        filename=filename,
        profiles=[c.model_dump() for c in screenplay.characters],
    )
    spine_writer.store_screenplay_scenes(
        script_id=screenplay.script_id,
        scenes=[s.model_dump() for s in screenplay.scenes],
    )
    if production_id:
        spine_writer.link_production_script(production_id, screenplay.script_id)
    screenplay.characters = [CharacterProfile(**{k: v for k, v in m.items() if k in CharacterProfile.model_fields}) for m in merged]
    screenplay.characters_count = len(screenplay.characters)
    return screenplay


@router.post("/script/parse", response_model=Screenplay)
async def parse_script(req: ScriptParseRequest):
    """
    Parses raw Fountain / standard screenplay text into structured scenes, then
    infers each character's production profile with AI.
    """
    screenplay = parse_fountain_screenplay(req.script_text, req.title)
    await enrich_screenplay_characters(screenplay)
    return _persist_screenplay(screenplay, production_id=req.production_id)


@router.post("/script/upload", response_model=Screenplay)
async def upload_script_file(
    file: UploadFile = File(...),
    production_id: Optional[str] = Form(None),
):
    """
    Uploads and parses a screenplay file (.fountain, .txt, .md, .pdf, .fdx) into structured scenes,
    and archives the source document to Google Cloud Storage.
    """
    from backend.app.integrations.google_cloud import upload_media_to_google_cloud_storage

    file_bytes = await file.read()
    filename = file.filename or "Screenplay"

    # Archive original asset to Google Cloud Storage. The SDK call is blocking,
    # so keep it off the event loop rather than stalling every other request.
    gcs_result = await asyncio.to_thread(
        upload_media_to_google_cloud_storage,
        file_bytes=file_bytes,
        destination_blob_name=f"screenplays/{filename}",
        content_type="application/pdf" if filename.lower().endswith(".pdf") else "text/plain",
    )

    screenplay = parse_screenplay_file(file_bytes=file_bytes, filename=filename)

    # Infer appearance, wardrobe and facial detail before storing, so the merge
    # in _persist_screenplay still lets any existing user edits win.
    await enrich_screenplay_characters(screenplay)

    return _persist_screenplay(screenplay, filename=filename, production_id=production_id)


class LinkScriptRequest(BaseModel):
    production_id: str
    script_id: str


@router.get("/script/link")
def get_linked_script(production_id: Optional[str] = None, script_id: Optional[str] = None):
    """
    The screenplay a production is shooting, or -- asked the other way round,
    with script_id -- the productions shooting a given screenplay.

    The Script Studio knows only the script it has loaded, so without the
    reverse reading it would offer to attach a script that is already attached.
    """
    if script_id:
        return {"script_id": script_id, "production_ids": spine_writer.find_productions_for_script(script_id)}
    if not production_id:
        raise HTTPException(status_code=422, detail="production_id or script_id is required")
    return spine_writer.get_production_script(production_id)


@router.post("/script/link")
def link_script(req: LinkScriptRequest):
    """
    Attaches a screenplay to a production so its scenes can be opened from a
    slate. One script per production -- linking a second one replaces the first.
    """
    if not spine_writer.get_screenplay(req.script_id):
        raise HTTPException(status_code=404, detail=f"No screenplay stored under {req.script_id}")
    return spine_writer.link_production_script(req.production_id, req.script_id)


@router.delete("/script/link")
def unlink_script(production_id: str):
    return {"unlinked": spine_writer.unlink_production_script(production_id)}


# How many of the script supervisor's notes on one shot are worth reading
# together. Past a handful they stop describing the shot and start describing
# the day, and every extra word makes the passage match vaguer.
_MAX_SHOT_NOTES = 6


def _shot_description(production_id: str, slate: str) -> Optional[str]:
    """
    What the script supervisor wrote beside this shot, across every report.

    This is the only text in the system that describes what a shot contains, so
    it is the only thing we can match against the scene to place it.
    """
    notes: List[str] = []
    for event in spine_writer.get_events(production_id=production_id):
        # The script department only. A camera report's note is about the take
        # -- lens, filter, a reslate -- and would drag the match away from what
        # the shot is of.
        if event.get("department") != "script":
            continue
        payload = event.get("payload") or {}
        if normalize_slate(payload.get("slate")) != slate:
            continue
        note = (payload.get("note") or "").strip()
        if note and note not in notes:
            notes.append(note)
        if len(notes) >= _MAX_SHOT_NOTES:
            break
    return " ".join(notes) or None


@router.get("/script/context")
def get_script_context(production_id: str, target_type: str, target_id: str):
    """
    The script behind a scene or a shot.

    Returns the scene text with a highlight over the part that belongs to the
    target: all of it for a scene, and for a shot the passage its description
    matched, together with the words that match rests on. When the shot cannot
    be placed inside the scene, the whole scene comes back with a reason -- a
    highlight over the wrong half of a page is worse than no highlight.
    """
    kind = (target_type or "").strip().lower()
    if kind not in ("scene", "shot"):
        raise HTTPException(status_code=422, detail="target_type must be 'scene' or 'shot'")

    result: Dict[str, Any] = {
        "production_id": production_id,
        "target_type": kind,
        "target_id": target_id,
        "script_id": None,
        "script_title": None,
        "scenes": [],
        "status": "ok",
        "message": None,
    }

    link = spine_writer.get_production_script(production_id)
    if not link:
        result["status"] = "no_script_linked"
        result["message"] = (
            "No screenplay is attached to this production. Open the Screenplay "
            "Studio, load the script, and attach it to this production."
        )
        return result

    result["script_id"] = link.get("script_id")
    result["script_title"] = link.get("title")

    scene_numbers = scene_numbers_for_target(kind, target_id)
    if not scene_numbers:
        result["status"] = "unreadable_target"
        result["message"] = f"{target_id!r} does not name a scene."
        return result

    hint = None
    if kind == "shot":
        normalized = normalize_slate(target_id)
        if normalized:
            hint = _shot_description(production_id, normalized)

    missing: List[str] = []
    for number in scene_numbers:
        rows = spine_writer.find_screenplay_scenes(link["script_id"], number)
        if not rows:
            missing.append(number)
            continue
        for row in rows:
            result["scenes"].append(build_scene_context(row, kind, hint=hint))

    if not result["scenes"]:
        result["status"] = "scene_not_in_script"
        result["message"] = (
            f"Scene {', '.join(missing)} is not in {link.get('title') or 'the linked script'}. "
            "The scene numbers on set and in the script may not be the same draft."
        )
    elif missing:
        result["message"] = (
            f"Scene {', '.join(missing)} is not in the linked script; "
            "the other scene(s) of this slate are shown."
        )

    return result


@router.get("/script/presets")
def get_dop_presets():
    """
    Returns curated Master Director of Photography presets and styles.
    """
    return {
        "presets": DOP_MASTER_PRESETS,
        "aspect_ratios": ["2.39:1", "1.85:1", "16:9", "4:3"],
        "shot_sizes": ["EWS", "WS", "MWS", "MS", "MCU", "CU", "ECU", "OTS", "POV", "INSERT"],
        "camera_movements": ["STATIC", "PAN_TILT", "DOLLY_IN", "DOLLY_OUT", "SLIDER", "HANDHELD", "STEADICAM", "CRANE"],
    }


@router.post("/script/presets/suggest")
def suggest_dop_preset(req: SuggestDoPPresetRequest):
    """
    Generates an AI-suggested DoP preset name, tagline, description, and prompt style
    tag matching current optical and lighting parameters.
    """
    return suggest_dop_preset_metadata(
        focal_length=req.focal_length or 35,
        aperture=req.aperture or "T2.8",
        color_temperature_k=req.color_temperature_k or 5600,
        white_balance_k=req.white_balance_k or 5600,
        lighting_ratio=req.lighting_ratio or "4:1",
        sensor_format=req.sensor_format or "Large Format 35mm",
        lut_emulation=req.lut_emulation or "Kodak 5219 Vision3 500T",
        custom_prompt=req.custom_prompt,
        aspect_ratio=req.aspect_ratio or "2.39:1"
    )


@router.post("/script/breakdown")
async def generate_shot_breakdown(req: ScriptBreakdownRequest):
    """
    Generates a cinematic multi-camera shot coverage list (Cameras A, B, C)
    with technical DoP parameters, character visual consistency, and synthesized generative image prompts.
    """
    shots = await breakdown_scene_to_shots(
        scene=req.scene,
        dop_style_name=req.dop_preset,
        dop_overrides=req.dop_overrides,
        custom_mood_prompt=req.custom_prompt,
        aspect_ratio=req.aspect_ratio,
        character_profiles=req.character_profiles
    )

    # Pre-render prompt-accurate visual concept previews for each camera angle (A, B, C)
    for s in shots:
        # Pre-render individual camera angles
        for cam in s.cameras:
            cam.image_url = render_cinematic_storyboard_svg(
                prompt=cam.prompt,
                scene_number=s.scene_number,
                shot_number=s.shot_number,
                shot_size=cam.shot_size,
                focal_length=cam.focal_length,
                aperture=cam.aperture,
                dop_preset=s.dop_spec.dop_preset,
                camera_letter=cam.camera_letter,
                aspect_ratio=req.aspect_ratio,
            )
            cam.status = "generated"

        # Primary Storyboard preview corresponds to Camera A
        cam_a = next((c for c in s.cameras if c.camera_letter == "A"), s.cameras[0] if s.cameras else None)
        if cam_a:
            s.storyboard.image_url = cam_a.image_url
            s.storyboard.prompt = cam_a.prompt
            s.storyboard.status = "generated"

    rendered = [s.model_dump() for s in shots]

    # Kept against the scene, not just handed back. The frames cost a
    # generation each, and the coverage is worked on afterwards rather than
    # read once, so a reload used to throw away both.
    saved = False
    if req.script_id:
        spine_writer.save_scene_breakdown(req.script_id, req.scene.scene_number, rendered)
        saved = True

    return {
        "scene_number": req.scene.scene_number,
        "shots_count": len(shots),
        "shots": rendered,
        # False when there was no screenplay to file it under, so the client
        # does not report a save that did not happen.
        "saved": saved,
    }


@router.get("/script/{script_id}/breakdowns")
def list_scene_breakdowns(script_id: str):
    """
    Every scene's breakdown for a screenplay, keyed by scene number.

    The shape the Script Studio holds it in, so restoring what somebody was
    working on is an assignment rather than a reduction.
    """
    return {"script_id": script_id, "breakdowns": spine_writer.list_scene_breakdowns(script_id)}


@router.put("/script/{script_id}/breakdowns/{scene_number}")
def save_scene_breakdown(script_id: str, scene_number: str, req: SaveBreakdownRequest):
    """
    Records the shot list as it now stands, after an edit to a camera, a
    prompt, or a re-rendered frame.
    """
    try:
        return spine_writer.save_scene_breakdown(script_id, scene_number, req.shots)
    except breakdown_store.UnknownBreakdownValue as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/script/{script_id}/breakdowns/{scene_number}")
def delete_scene_breakdown(script_id: str, scene_number: str):
    return {"deleted": spine_writer.delete_scene_breakdown(script_id, scene_number)}


@router.post("/script/generate-storyboard")
async def generate_storyboard_frame(req: GenerateStoryboardRequest):
    """
    Executes real-time AI image generation taking into account the editable prompt,
    the active camera rig (Cam A/B/C), optics, character visual consistency, and all DoP specifications.
    """
    from backend.app.script.ai_image_service import generate_ai_cinematic_image

    res = await generate_ai_cinematic_image(
        prompt=req.prompt,
        scene_number=req.scene_number,
        shot_number=req.shot_number,
        shot_size=req.shot_size,
        focal_length=req.focal_length,
        aperture=req.aperture,
        dop_preset=req.dop_preset,
        camera_letter=req.camera_letter,
        lighting_ratio=req.lighting_ratio,
        color_temp_k=req.color_temp_k,
        lut_emulation=req.lut_emulation,
        aspect_ratio=req.aspect_ratio,
        character_details=req.character_details,
        economy_mode=req.economy_mode
    )

    return {
        "shot_id": req.shot_id,
        "camera_letter": req.camera_letter,
        "status": "generated",
        "image_url": res["image_url"],
        "prompt": req.prompt,
        "compiled_prompt": res["compiled_prompt"],
        "provider": res.get("provider", "AI Generative Engine"),
        "aspect_ratio": req.aspect_ratio,
    }

# --- Demo Endpoints ---

# Written into the description so re-injecting finds the requirement it raised
# last time instead of raising a second one. The demo endpoint is re-run freely
# during a walkthrough, and a board that grows a duplicate on every run is a
# board nobody trusts to be showing the day's real outstanding work.
DEMO_REQUIREMENT_MARKER = "DemoSeed: scene:2:day:31"


def _seed_demo_requirement() -> Dict[str, Any]:
    """
    Raises the one requirement the demo needs on the board, once.

    It names what Day 1 actually shows: A001C006_260831 is the circled take of
    Scene 2 in the camera report, and it is absent from the Silverstack offload
    -- the same gap the existence axis reports as a critical discrepancy. A
    requirement that named something no document mentions would be the one
    piece of the board that no amount of digging could explain.
    """
    existing = next(
        (
            r for r in spine_writer.list_requirements(production_id="DEMO_PRODUCTION")
            if DEMO_REQUIREMENT_MARKER in (r.get("description") or "")
        ),
        None,
    )
    if existing:
        return existing

    return spine_writer.create_requirement({
        "production_id": "DEMO_PRODUCTION",
        "shoot_day": "31",
        "title": "Scene 2 circled take is missing from the offload",
        "description": (
            f"{DEMO_REQUIREMENT_MARKER}\n"
            "Clip A001C006_260831 is the circled take of Scene 2 in the Day 1 camera "
            "report, and it does not appear in the Silverstack offload. Confirm with "
            "DIT whether the card was fully offloaded before the media is wiped."
        ),
        "category": "edit",
        "target_type": "scene",
        "target_id": "2",
        "target_label": "Scene 2",
        "status": "open",
        "priority": "high",
        "created_by": "@script_supervisor",
        "assigned_to": "@assistant_editor",
    })


@router.get("/events/demo")
async def demo_inject_events():
    """Injects sample events into the event spine for the end-to-end demo."""
    import os
    import hashlib
    from backend.app.parsers.classifier import classify_document
    from backend.app.parsers.pdf_parsers import extract_text_from_pdf

    # Ensure the DEMO_PRODUCTION and demo script are seeded before we inject events
    spine_writer.seed_defaults()

    EXAMPLES_DIR = os.environ.get("CINESPINE_EXAMPLES_DIR", "data/examples")

    demo_files = [
        "demo_script.fountain",
        "DEMO_TCLog_Synthetic.pdf",
        "DEMO_Day1_ScriptLog.txt",
        "DEMO_Day1_SoundLog.txt",
        "DEMO_Day1_CamReport.txt",
        "DEMO_Day1_Silverstack_Offload.txt",
        "DEMO_Day2_ScriptLog.txt",
        "DEMO_Day2_CamReport.txt",
        "DEMO_Day2_SoundLog.txt",
        "DEMO_Day2_Silverstack_Offload.txt",
    ]

    for filename in demo_files:
        filepath = os.path.join(EXAMPLES_DIR, filename)
        if not os.path.exists(filepath):
            continue

        with open(filepath, "rb") as f:
            content_bytes = f.read()
            try:
                if filename.endswith(".pdf"):
                    raw_text = extract_text_from_pdf(content_bytes)
                else:
                    raw_text = content_bytes.decode("utf-8", errors="ignore")
            except Exception:
                raw_text = content_bytes.decode("utf-8", errors="ignore")

            classification = classify_document(filename, raw_text)
            checksum = hashlib.sha256(content_bytes).hexdigest()
            shoot_day = "32" if "Day2" in filename else "31"

            doc_id = spine_writer.store_document(
                production_id="DEMO_PRODUCTION",
                shoot_day=shoot_day,
                filename=filename,
                doc_type=classification.doc_type.value,
                department=classification.department.value,
                content=raw_text,
                checksum=checksum,
                raw_bytes=content_bytes,
                metadata={"demo": True, "synthetic": True},
            )

            envelope = EventEnvelope(
                production_id="DEMO_PRODUCTION",
                shoot_day=shoot_day,
                axis=classification.axis,
                department=classification.department,
                doc_type=classification.doc_type,
                raw_content=raw_text,
                filename=filename,
                metadata={"doc_id": doc_id, "demo": True, "synthetic": True},
            )
            topic = f"production.raw.{classification.department.value}"
            event_bus.publish(topic, envelope)

    spine_writer.flush_events()

    _seed_demo_requirement()

    _project_analytics("DEMO_PRODUCTION", "31")
    _project_analytics("DEMO_PRODUCTION", "32")

    return {"status": "success", "message": "Demo events injected"}

@router.get("/wrap-rescue/demo")
async def demo_wrap_rescue():
    """Endpoint for a quick agent query."""
    agent = WrapRescueAgent(
        spine_writer=spine_writer,
        reconciler=reconciler,
        legacy_mcp_server=mcp_server,
    )
    result = await agent.run(production_id="DEMO_PRODUCTION", shoot_day="31")
    memo = result.final_memo or "Wrap Rescue evaluation complete. 0 critical blockers."
    return {
        "status": "success",
        "response": {
            "response": memo,
            "result": result.model_dump(),
        }
    }

@router.post("/demo/wipe")
def demo_wipe():
    """Factory reset the demo state across both SQLite and ClickHouse."""
    return spine_writer.wipe_all(seed=False)



