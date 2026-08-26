import os
import re
import uuid
import hashlib
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Response, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from backend.app.streaming.models import EventEnvelope, AxisType, DepartmentType, DocumentType
from backend.app.streaming.bus import EventBus
from backend.app.streaming.dispatcher import IngestionDispatcher
from backend.app.streaming.broker import event_broker, SpineLiveEvent
from backend.app.spine.writer import SpineWriter
from backend.app.reconciliation.engine import ReconciliationEngine
from backend.app.agents.mcp_server import ClickHouseMCPServer, GeminiDiscrepancyAssistant
from backend.app.parsers.classifier import classify_document, infer_production_and_day
from backend.app.parsers.pdf_parsers import extract_text_from_pdf, extract_thumbnails_from_pdf
from backend.app.normalizers.takes import normalize_take
from backend.app.normalizers.slates import normalize_slate
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


class ResolveRequirementRequest(BaseModel):
    resolution_note: str
    resolved_by: str = "@user"



@router.get("/health")
def health_check():
    return {"status": "ok", "version": "0.1.0", "service": "cinespine"}


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


@router.post("/productions")
def create_production(req: CreateProductionRequest):
    return spine_writer.register_production(
        production_id=req.production_id,
        name=req.name,
        director=req.director,
        description=req.description,
    )


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
    
    filename = doc.get("filename", "")
    is_pdf = filename.lower().endswith(".pdf") or doc.get("doc_type") == "pdf"

    return {
        "doc_id": doc["doc_id"],
        "production_id": doc["production_id"],
        "shoot_day": doc["shoot_day"],
        "filename": filename,
        "doc_type": doc["doc_type"],
        "department": doc["department"],
        "content": doc.get("content", ""),
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
    
    raw_bytes = doc.get("raw_bytes")
    filename = doc.get("filename", "document")
    
    # If raw_bytes wasn't in memory (e.g. initial demo load), resolve from local example directory
    if not raw_bytes:
        examples_path = os.path.join("data/examples", filename)
        if os.path.exists(examples_path):
            try:
                with open(examples_path, "rb") as f:
                    raw_bytes = f.read()
            except Exception:
                pass
    
    if not raw_bytes:
        raw_bytes = doc.get("content", "").encode("utf-8")
    
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
    event_bus.publish(topic, envelope)

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

    final_prod = production_id or classification.inferred_production_id or "DEMO_PRODUCTION"
    final_day = shoot_day or classification.inferred_shoot_day or "31"

    # Check for duplicate document
    existing = spine_writer.get_document_by_checksum(final_prod, final_day, checksum)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate document: '{existing['filename']}' is already uploaded for {final_prod} Day {final_day} (SHA-256: {checksum[:8]}...).",
        )

    # Store for previewing
    doc_id = spine_writer.store_document(
        production_id=final_prod,
        shoot_day=final_day,
        filename=filename,
        doc_type=classification.doc_type.value,
        department=classification.department.value,
        content=raw_text,
        checksum=checksum,
        raw_bytes=content_bytes,
        metadata={"file_size": len(content_bytes), "content_type": file.content_type},
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
        },
    )

    topic = f"production.raw.{classification.department.value}"
    event_bus.publish(topic, envelope)

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
            if camera_roll and media_info.get("camera_roll") and camera_roll.upper() == media_info.get("camera_roll", "").upper():
                return True
            if sh and m_shot:
                if (
                    sh.upper() == m_shot.upper()
                    or m_shot.upper().endswith(f"/{sh.upper()}")
                    or m_shot.upper() == slate.upper()
                    or m_shot.upper() == f"{sc.upper()}/{sh.upper()}"
                    or m_shot.upper() == sc.upper()
                ):
                    return True
            else:
                return True

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
    examples_dir = os.environ.get("CINESPINE_EXAMPLES_DIR", "data/examples")
    ingested_files = []

    if os.path.exists(examples_dir):
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
            event_bus.publish(topic, envelope)
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
            event_bus.publish(topic, envelope)
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

    return {"status": "SEEDED", "ingested_count": len(ingested_files), "files": ingested_files}



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
    return mcp_server.query_production_discrepancies(production_id=production_id, shoot_day=shoot_day)


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


@router.get("/requirements/{requirement_id}")
def get_requirement(requirement_id: str):
    req = spine_writer.get_requirement(requirement_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return req


@router.patch("/requirements/{requirement_id}")
def update_requirement(requirement_id: str, updates: UpdateRequirementRequest):
    update_data = {k: v for k, v in updates.model_dump().items() if v is not None}
    updated = spine_writer.update_requirement(requirement_id, update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Requirement not found")
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
def delete_requirement(requirement_id: str):
    success = spine_writer.delete_requirement(requirement_id)
    if not success:
        raise HTTPException(status_code=404, detail="Requirement not found")
    event_broker.publish_sync(SpineLiveEvent(
        event_type="REQUIREMENT_DELETED",
        production_id="ALL",
        shoot_day="ALL",
        actor_handle="@user",
        target_type="requirement",
        target_id=requirement_id,
        target_label=requirement_id,
        summary=f"Requirement deleted ({requirement_id})",
    ))
    return {"status": "DELETED", "requirement_id": requirement_id}



# ==========================================
# Real-Time Alerts & Notification Routes
# ==========================================
@router.get("/notifications")
def get_notifications(user_handle: str, unread_only: bool = False):
    notifs = spine_writer.list_notifications(recipient_handle=user_handle, unread_only=unread_only)
    unread_all = spine_writer.list_notifications(recipient_handle=user_handle, unread_only=True)
    return {
        "recipient_handle": user_handle,
        "unread_count": len(unread_all),
        "notifications": notifs,
    }


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str):
    success = spine_writer.mark_notification_read(notification_id)
    return {"status": "READ", "notification_id": notification_id, "success": success}


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


@router.get("/metrics")
def get_prometheus_metrics():
    return Response(
        content=TelemetryExporter.get_metrics_payload(),
        media_type=TelemetryExporter.get_content_type(),
    )


# ---------------------------------------------------------------------------
# Script Breakdown, DoP Cinematography & Previz Storyboard Endpoints
# ---------------------------------------------------------------------------

from backend.app.script.parser import parse_fountain_screenplay, parse_screenplay_file, Screenplay, ScreenplayScene
from backend.app.script.dop_presets import DOP_MASTER_PRESETS, resolve_dop_specification
from backend.app.script.breakdown_engine import breakdown_scene_to_shots, ShotProposal
from backend.app.script.storyboard_generator import render_cinematic_storyboard_svg


class ScriptParseRequest(BaseModel):
    script_text: str
    title: str = "Screenplay"


class ScriptBreakdownRequest(BaseModel):
    scene: ScreenplayScene
    dop_preset: Optional[str] = "Roger Deakins"
    dop_overrides: Optional[Dict[str, Any]] = None
    custom_prompt: Optional[str] = None
    aspect_ratio: str = "2.39:1"


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


@router.get("/integrations/google-cloud")
def get_google_cloud_status():
    """
    Returns live Google Cloud & Gemini Enterprise Agent Platform runtime integration telemetry.
    """
    from backend.app.integrations.google_cloud import get_google_cloud_runtime_status
    return get_google_cloud_runtime_status()


@router.post("/script/parse", response_model=Screenplay)
def parse_script(req: ScriptParseRequest):
    """
    Parses raw Fountain / standard screenplay text into structured scenes.
    """
    return parse_fountain_screenplay(req.script_text, req.title)


@router.post("/script/upload", response_model=Screenplay)
async def upload_script_file(file: UploadFile = File(...)):
    """
    Uploads and parses a screenplay file (.fountain, .txt, .pdf, .fdx) into structured scenes,
    and archives the source document to Google Cloud Storage.
    """
    from backend.app.integrations.google_cloud import upload_media_to_google_cloud_storage

    file_bytes = await file.read()
    filename = file.filename or "Screenplay"

    # Archive original asset to Google Cloud Storage
    gcs_result = upload_media_to_google_cloud_storage(
        file_bytes=file_bytes,
        destination_blob_name=f"screenplays/{filename}",
        content_type="application/pdf" if filename.lower().endswith(".pdf") else "text/plain"
    )

    screenplay = parse_screenplay_file(file_bytes=file_bytes, filename=filename)
    return screenplay


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


@router.post("/script/breakdown")
def generate_shot_breakdown(req: ScriptBreakdownRequest):
    """
    Generates a cinematic multi-camera shot coverage list (Cameras A, B, C)
    with technical DoP parameters and synthesized generative image prompts.
    """
    shots = breakdown_scene_to_shots(
        scene=req.scene,
        dop_style_name=req.dop_preset,
        dop_overrides=req.dop_overrides,
        custom_mood_prompt=req.custom_prompt,
        aspect_ratio=req.aspect_ratio,
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

    return {
        "scene_number": req.scene.scene_number,
        "shots_count": len(shots),
        "shots": [s.model_dump() for s in shots],
    }


@router.post("/script/generate-storyboard")
async def generate_storyboard_frame(req: GenerateStoryboardRequest):
    """
    Executes real-time AI image generation taking into account the editable prompt,
    the active camera rig (Cam A/B/C), optics, and all DoP specifications.
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

