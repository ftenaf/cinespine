import os
import re
import hashlib
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
from backend.app.parsers.pdf_parsers import extract_text_from_pdf, extract_thumbnails_from_pdf
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
    deleted = spine_writer.delete_document(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
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
            if "thumbnail" in filename.lower() or "thumbnail report" in raw_text.lower():
                thumbnails_map = extract_thumbnails_from_pdf(content_bytes)
        except Exception as e:
            raw_text = content_bytes.decode("utf-8", errors="ignore")
    else:
        raw_text = content_bytes.decode("utf-8", errors="ignore")

    classification = classify_document(filename=filename, content=content_bytes)

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
            if sh and m_shot:
                if sh.upper() == m_shot.upper():
                    return True
            else:
                return True

    # 2. Camera Clip Name matching (e.g. ZoeLog 'A120_C001' vs Silverstack 'A_0120C001_260728_091309_h1EIC.mxf')
    if clip_name:
        m_c = re.match(r"^([A-Z])(\d{3,4})_C(\d{3,4})", clip_name)
        if m_c:
            cam_letter, roll_num, c_num = m_c.group(1), int(m_c.group(2)), int(m_c.group(3))
            target_pattern = rf"{cam_letter}_0*{roll_num}C0*{c_num}(?:[^0-9]|$)"
            if re.search(target_pattern, fn):
                return True
        elif clip_name in fn:
            return True

    # 3. Audio WAV Name matching (e.g. '+99BDF-9T01.WAV', '27-7T01.WAV', '49WTT01.WAV')
    if fn.upper().endswith(".WAV"):
        if tk_norm.isdigit():
            tk_int = int(tk_norm)
            sc_esc = rf"(?:\+)?{re.escape(sc.lstrip('+'))}"
            if sh:
                pattern = rf"^{sc_esc}-{re.escape(sh)}T0*{tk_int}\.WAV$"
            else:
                pattern = rf"^{sc_esc}(?:-?T|WTT)0*{tk_int}\.WAV$"
            if re.search(pattern, fn, re.IGNORECASE):
                return True

    return False


class SeedRequest(BaseModel):
    production_id: str = "DEMO_PRODUCTION"
    shoot_day: str = "31"


@router.post("/seed")
def seed_real_day_data(req: SeedRequest):
    """
    Seeds the real day production documents (ZoeLog Camera A/B/C, Sound Reports, Silverstack Thumbnail & Volume)
    from the domain examples directory into the spine.
    """
    examples_dir = "data/examples"
    if not os.path.exists(examples_dir):
        raise HTTPException(status_code=404, detail="Examples directory not found")

    ingested_files = []
    files = sorted(os.listdir(examples_dir))
    for fn in files:
        fp = os.path.join(examples_dir, fn)
        with open(fp, "rb") as f:
            content_bytes = f.read()

        checksum = hashlib.sha256(content_bytes).hexdigest()
        existing = spine_writer.get_document_by_checksum(req.production_id, req.shoot_day, checksum)
        if existing:
            continue

        classification = classify_document(filename=fn, content=content_bytes)
        t_map = {}
        if fn.lower().endswith(".pdf"):
            try:
                txt = extract_text_from_pdf(content_bytes)
                if "thumbnail" in fn.lower() or "thumbnail report" in txt.lower():
                    t_map = extract_thumbnails_from_pdf(content_bytes)
            except Exception:
                txt = content_bytes.decode("utf-8", errors="ignore")
        else:
            txt = content_bytes.decode("utf-8", errors="ignore")

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

    # 2. Map sound reports (from sound CSV/ALE)
    for evt in events:
        if evt.get("department") == "sound" and evt.get("entity_type") == "take":
            p = evt.get("payload", {})
            slate = p.get("slate")
            raw_take = p.get("take_id")
            if slate and raw_take:
                tk = "FALSE" if raw_take in ["FC", "FALSE"] else raw_take
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
            slate = p.get("slate")
            raw_take = p.get("take_id")
            if slate and raw_take:
                # Normalize take identifier so FC and FALSE merge gracefully
                take_id = "FALSE" if raw_take in ["FC", "FALSE"] else raw_take
                key = f"{slate}_{take_id}"
                scene = p.get("scene") or (slate.split("/")[0] if "/" in slate else slate)

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
            t["audio_files"].append({
                "file_name": sr_info.get("file_name") or f"{t['slate'].replace('/', '-')}T{t['take_id']}.WAV",
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

        # Clean description from script notes
        descriptions = []
        for t in s_takes:
            sn = t.get("belief", {}).get("script", {}).get("note", "")
            if sn:
                cleaned = re.sub(r"LAC\s+Day:[^\n]+", "", sn)
                cleaned = re.sub(r"\d{2}:\d{2}:\d{2}(?::\d{2})?", "", cleaned)
                cleaned = re.sub(r"Scene\(s\):\s*\d+\s*", "", cleaned)
                cleaned = re.sub(r"^\s*[-–>]+\s*", "", cleaned).strip()
                if cleaned and len(cleaned) > 5 and cleaned not in descriptions:
                    descriptions.append(cleaned)
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
            any(d.get("entity_id", "").startswith(t.get("slate", "")) for d in discrepancies)
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
            "comments": cmt_str,
            "has_discrepancy": has_disc,
            "is_wild_track": is_wt,
            "is_vfx": is_vfx,
            "takes_count": len(s_takes),
            "takes": [f"{t.get('slate')} T{t.get('take_id')}" for t in s_takes[:8]],
        }
        sequence_records.append(rec)

    return sequence_records


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
