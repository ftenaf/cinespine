"""
Automatic Document Type & Department Classifier.

Infuses domain intelligence from filename conventions and document contents,
eliminating the need for manual dropdown selection.
"""
import re
from dataclasses import dataclass
from typing import Optional, Union
from backend.app.streaming.models import AxisType, DepartmentType, DocumentType


@dataclass
class DocumentClassification:
    doc_type: DocumentType
    department: DepartmentType
    axis: AxisType
    is_multimodal: bool = False
    display_name: str = "Unknown Document"


def classify_document(
    filename: Optional[str] = None,
    content: Optional[Union[str, bytes]] = None,
) -> DocumentClassification:
    """
    Infers document type, department, and axis from filename and/or content signatures.
    """
    fn_upper = (filename or "").upper()
    text_sample = ""

    if isinstance(content, str):
        text_sample = content[:2000].upper()
    elif isinstance(content, bytes):
        # Sample first few KB as text if possible
        try:
            text_sample = content[:2000].decode("utf-8", errors="ignore").upper()
        except Exception:
            text_sample = ""

    # 1. Script Supervisor Facing & Lined Pages (Handwritten / Visual -> Multimodal)
    if "FACING" in fn_upper or "LINED" in fn_upper or "FACING&LINED" in fn_upper:
        return DocumentClassification(
            doc_type=DocumentType.SCRIPT_LINED,
            department=DepartmentType.SCRIPT,
            axis=AxisType.BELIEF,
            is_multimodal=True,
            display_name="Script Lined / Facing Pages (Handwritten Multimodal)",
        )

    # 2. Script Supervisor Editor's Logs & Timecode Logs
    if "EDITOR" in fn_upper or "TCLOG" in fn_upper or "DAILY EDITOR'S LOG" in text_sample:
        return DocumentClassification(
            doc_type=DocumentType.SCRIPT_TIMECODE,
            department=DepartmentType.SCRIPT,
            axis=AxisType.BELIEF,
            is_multimodal=False,
            display_name="Script Supervisor Editor's Log",
        )

    # 3. Camera Reports (ZoeLog, ARRI, RED, Sony)
    if (
        "CAM_" in fn_upper
        or "CAMERA" in fn_upper
        or "ZOELOG" in text_sample
        or ("ROLL" in text_sample and "SCENE TAKE CLIP" in text_sample)
    ):
        return DocumentClassification(
            doc_type=DocumentType.CAMERA_CSV,
            department=DepartmentType.CAMERA,
            axis=AxisType.BELIEF,
            is_multimodal=False,
            display_name="Camera Report",
        )

    # 4. Sound Reports (ALE, Sound Devices CSV)
    if (
        fn_upper.endswith(".ALE")
        or "SOUND" in fn_upper
        or "REPORT.CSV" in fn_upper
        or "SOUND REPORT" in text_sample
        or "B-WAV" in text_sample
        or "FIELD_DELIM" in text_sample
    ):
        return DocumentClassification(
            doc_type=DocumentType.SOUND_ALE,
            department=DepartmentType.SOUND,
            axis=AxisType.BELIEF,
            is_multimodal=False,
            display_name="Sound Report",
        )

    # 5. Silverstack Offload / Volume / Clips Reports
    if (
        "VOLUME" in fn_upper
        or "CLIPS" in fn_upper
        or "SILVERSTACK" in fn_upper
        or "THUMBNAIL" in fn_upper
        or "SILVERSTACK" in text_sample
        or "<SILVERSTACKREPORT" in text_sample
        or "VOLUME REPORT" in text_sample
    ):
        return DocumentClassification(
            doc_type=DocumentType.SILVERSTACK_XML,
            department=DepartmentType.DIT,
            axis=AxisType.EXISTENCE,
            is_multimodal=False,
            display_name="Silverstack DIT Offload Manifest",
        )

    # 6. Daily Production Report (Parte de producción / DPR)
    if "PARTEPROD" in fn_upper or "PARTE_PROD" in fn_upper or "DPR" in fn_upper or "PARTE DE PRODUCCION" in text_sample:
        return DocumentClassification(
            doc_type=DocumentType.DPR,
            department=DepartmentType.OFFICE,
            axis=AxisType.INTENT,
            is_multimodal=False,
            display_name="Daily Production Report (Office DPR)",
        )

    # Default fallback
    return DocumentClassification(
        doc_type=DocumentType.CAMERA_CSV,
        department=DepartmentType.CAMERA,
        axis=AxisType.BELIEF,
        is_multimodal=False,
        display_name="Generic Paperwork Drop",
    )
