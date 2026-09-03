import os
import logging
from typing import List, Dict, Any, Optional

from google.api_core.client_options import ClientOptions
from google.cloud import documentai

from backend.app.parsers.base import ParsedCameraRecord
from backend.app.agents.multimodal import ExtractedScriptPage, ExtractedTake
from backend.app.normalizers.takes import normalize_take
from backend.app.normalizers.rolls import normalize_camera_roll
from backend.app.normalizers.slates import normalize_slate

logger = logging.getLogger(__name__)

# Defaults for Document AI Form Parser
DOCAI_PROCESSOR_VERSION = "pretrained-form-parser-v2.1-2023-06-26"

def get_docai_client(location: str = "us") -> Optional[documentai.DocumentProcessorServiceClient]:
    """Initialize the Document AI Client."""
    if os.environ.get("CINESPINE_DISABLE_DOCAI", "").strip().lower() in ("1", "true", "yes"):
        return None
        
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logger.warning("GOOGLE_CLOUD_PROJECT not set, Document AI disabled.")
        return None
        
    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
    try:
        return documentai.DocumentProcessorServiceClient(client_options=opts)
    except Exception as e:
        logger.error("Failed to initialize Document AI client: %s", e)
        return None

def process_document(
    document_bytes: bytes,
    mime_type: str,
    project_id: str,
    location: str = "us",
    processor_id: str = "pretrained-form-parser-v2.1-2023-06-26"
) -> Optional[documentai.Document]:
    """Process a document using the Document AI API."""
    client = get_docai_client(location)
    if not client:
        return None

    try:
        # Note: Usually a processor needs to be created in GCP.
        # But we are instructed to use pretrained-form-parser-v2.1-2023-06-26.
        # The correct name format for a pretrained processor without an explicit ID is often a custom processor ID.
        # Assuming the user has set up a processor or we use the processor_id provided by environment.
        actual_processor_id = os.getenv("DOCAI_PROCESSOR_ID", processor_id)
        
        name = client.processor_version_path(
            project_id, location, actual_processor_id, DOCAI_PROCESSOR_VERSION
        )
        # If the user provides just a processor ID:
        if "processor_version" not in name:
            name = client.processor_path(project_id, location, actual_processor_id)

        raw_document = documentai.RawDocument(content=document_bytes, mime_type=mime_type)
        request = documentai.ProcessRequest(name=name, raw_document=raw_document)
        result = client.process_document(request=request)
        return result.document
    except Exception as e:
        logger.error("Document AI processing failed: %s", e)
        return None

def _get_text(page_content: str, segments) -> str:
    """Extract text from segments."""
    text = ""
    for segment in segments:
        text += page_content[int(segment.start_index) : int(segment.end_index)]
    return text.strip()

def extract_camera_report_grid(pdf_bytes: bytes, mime_type: str = "application/pdf") -> List[ParsedCameraRecord]:
    """Extracts a camera report grid using Document AI Form Parser."""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        return []

    doc = process_document(pdf_bytes, mime_type, project_id)
    if not doc:
        return []

    records = []
    text = doc.text
    
    # Simple extraction heuristic based on Document AI entities/tables
    for page in doc.pages:
        for table in page.tables:
            header = []
            if table.header_rows:
                for cell in table.header_rows[0].cells:
                    header.append(_get_text(text, cell.layout.text_anchor.text_segments).lower())
            
            # Map columns by heuristic
            col_map = {}
            for i, h in enumerate(header):
                if "roll" in h: col_map["roll"] = i
                elif "clip" in h: col_map["clip"] = i
                elif "slate" in h or "scene" in h: col_map["slate"] = i
                elif "take" in h: col_map["take"] = i
                elif "lens" in h: col_map["lens"] = i
                elif "stop" in h or "t" == h: col_map["t_stop"] = i
                elif "comment" in h or "note" in h: col_map["note"] = i

            for row in table.body_rows:
                cells = row.cells
                def get_cell(key, col_map=col_map, cells=cells):
                    idx = col_map.get(key)
                    if idx is not None and idx < len(cells):
                        return _get_text(text, cells[idx].layout.text_anchor.text_segments)
                    return ""

                raw_slate = get_cell("slate")
                raw_take = get_cell("take")
                raw_roll = get_cell("roll")

                if not raw_slate and not raw_take:
                    continue

                take_info = normalize_take(raw_take)
                roll = normalize_camera_roll(raw_roll) or None
                slate = normalize_slate(raw_slate) if raw_slate else None

                note = get_cell("note")
                if take_info.note:
                    note = f"{note} {take_info.note}".strip()

                records.append(ParsedCameraRecord(
                    slate=slate,
                    take_id=take_info.take_id,
                    camera_roll=roll,
                    clip_name=get_cell("clip") or None,
                    lens=get_cell("lens") or None,
                    is_starred=take_info.is_starred,
                    is_pickup=take_info.is_pickup,
                    is_false_start=take_info.is_false_start,
                    is_vfx=take_info.is_vfx,
                    is_mos=take_info.is_mos,
                    note=note,
                    fps=24.0, # default or extracted from form key-value pairs
                    raw_payload={"source": "document_ai_form_parser"}
                ))
    
    return records

def extract_lined_page(pdf_bytes: bytes, mime_type: str = "application/pdf") -> Optional[ExtractedScriptPage]:
    """Extracts a script lined page using Document AI."""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        return None

    doc = process_document(pdf_bytes, mime_type, project_id)
    if not doc:
        return None

    text = doc.text
    takes = []
    slates = set()
    scene = ""
    
    # We will look through the entities to find form fields
    for entity in doc.entities:
        type_ = entity.type_
        val = entity.mention_text
        if "scene" in type_.lower():
            scene = val
        elif "slate" in type_.lower() or "shot" in type_.lower():
            slates.add(val)
        elif "take" in type_.lower():
            # Minimal mapping for unstructured handwriting
            take_info = normalize_take(val)
            if take_info.take_id:
                takes.append(ExtractedTake(
                    take_id=take_info.take_id,
                    is_starred=take_info.is_starred,
                    is_pickup=take_info.is_pickup,
                    is_false_start=take_info.is_false_start,
                    is_vfx=take_info.is_vfx,
                    is_wild_track=take_info.is_wild_track,
                    notes=take_info.note
                ))

    # Fallback if no specific entities matched, just return what we got
    return ExtractedScriptPage(
        scene=scene.upper(),
        slates=list(slates),
        takes=takes,
        lining_notes=None
    )
