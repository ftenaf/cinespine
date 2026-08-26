"""
Automatic Document Type, Department, Production & Shoot Day Classifier.

Infuses domain intelligence from filename conventions, calendar date maps, and document contents,
eliminating manual input.
"""
import re
from dataclasses import dataclass
from typing import Optional, Union, Tuple
from backend.app.streaming.models import AxisType, DepartmentType, DocumentType
from backend.app.normalizers.shoot_days import normalize_shoot_day


@dataclass
class DocumentClassification:
    doc_type: DocumentType
    department: DepartmentType
    axis: AxisType
    is_multimodal: bool = False
    display_name: str = "Unknown Document"
    inferred_production_id: Optional[str] = None
    inferred_shoot_day: Optional[str] = None


# Known production date-to-day mappings (from production calendar / DPRs)
CALENDAR_MAP = {
    "280726": "31",
    "260728": "31",
    "20260728": "31",
    "2026-7-28": "31",
    "2026-07-28": "31",
    "28/07/26": "31",
    "27/07/26": "31",
    "070826": "39",
    "260807": "39",
    "08-07-26": "39",
    "20260807": "39",
    "2026-8-07": "39",
    "2026-8-08": "39",
    "7-AGOSTO-2026": "39",
}


def infer_production_and_day(
    filename: Optional[str] = None,
    content: Optional[Union[str, bytes]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Infers production_id and shoot_day from filename patterns, calendar dates, and content.
    """
    fn = filename or ""
    fn_upper = fn.upper()
    text_sample = ""

    if isinstance(content, str):
        text_sample = content[:3000].upper()
    elif isinstance(content, bytes):
        try:
            text_sample = content[:3000].decode("utf-8", errors="ignore").upper()
        except Exception:
            text_sample = ""

    # 1. Infer Production ID
    inferred_prod = None
    if (
        "DEMO" in fn_upper
        or "DEMOPRODUCTION" in fn_upper
        or "DEMO PRODUCTION" in text_sample
        or 'PROJECT:,"DEMO PRODUCTION"' in text_sample
    ):
        inferred_prod = "DEMO_PRODUCTION"

    # 2. Infer Shoot Day from Filename (e.g. SD31, D031, D039, #39)
    inferred_day = None

    # Check for SD31, SD39
    sd_match = re.search(r"SD(\d+)", fn_upper)
    if sd_match:
        inferred_day = str(int(sd_match.group(1)))

    # Check for D031, D039
    if not inferred_day:
        d_match = re.search(r"[_\-]D0*(\d+)", fn_upper)
        if d_match:
            inferred_day = str(int(d_match.group(1)))

    # Check for #39
    if not inferred_day:
        hash_match = re.search(r"#(\d+)", fn_upper)
        if hash_match:
            inferred_day = str(int(hash_match.group(1)))

    # Check for Date in Filename (e.g. 260728, 070826, 2026-7-28)
    if not inferred_day:
        for date_key, day_val in CALENDAR_MAP.items():
            if date_key.upper() in fn_upper:
                inferred_day = day_val
                break

    # 3. Infer Shoot Day from Content (e.g. Day 31 - Main Unit, Date: 28/07/2026)
    if not inferred_day and text_sample:
        # Check Day: Day 31
        day_content_match = re.search(r"DAY\s*:\s*DAY\s*(\d+)", text_sample)
        if day_content_match:
            inferred_day = str(int(day_content_match.group(1)))
        
        if not inferred_day:
            for date_key, day_val in CALENDAR_MAP.items():
                if date_key.upper() in text_sample:
                    inferred_day = day_val
                    break

    return inferred_prod, inferred_day


def classify_document(
    filename: Optional[str] = None,
    content: Optional[Union[str, bytes]] = None,
) -> DocumentClassification:
    """
    Infers document type, department, axis, production_id, and shoot_day.
    """
    fn_upper = (filename or "").upper()
    text_sample = ""

    if isinstance(content, str):
        text_sample = content[:2000].upper()
    elif isinstance(content, bytes):
        try:
            text_sample = content[:2000].decode("utf-8", errors="ignore").upper()
        except Exception:
            text_sample = ""

    inferred_prod, inferred_day = infer_production_and_day(filename, content)

    # 1. Script Supervisor Facing & Lined Pages (Handwritten / Visual -> Multimodal)
    if "FACING" in fn_upper or "LINED" in fn_upper or "FACING&LINED" in fn_upper:
        return DocumentClassification(
            doc_type=DocumentType.SCRIPT_LINED,
            department=DepartmentType.SCRIPT,
            axis=AxisType.BELIEF,
            is_multimodal=True,
            display_name="Script Lined / Facing Pages (Handwritten Multimodal)",
            inferred_production_id=inferred_prod,
            inferred_shoot_day=inferred_day,
        )

    # 2. Script Supervisor Editor's Logs & Timecode Logs
    if (
        "EDITOR" in fn_upper
        or "TCLOG" in fn_upper
        or "DETAILED" in fn_upper
        or "DAILY EDITOR'S LOG" in text_sample
        or "TIMECODE LOG" in text_sample
        or "DETAILED EDITOR'S LOG" in text_sample
    ):
        return DocumentClassification(
            doc_type=DocumentType.SCRIPT_TIMECODE,
            department=DepartmentType.SCRIPT,
            axis=AxisType.BELIEF,
            is_multimodal=False,
            display_name="Script Supervisor Editor's / Timecode Log",
            inferred_production_id=inferred_prod,
            inferred_shoot_day=inferred_day,
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
            inferred_production_id=inferred_prod,
            inferred_shoot_day=inferred_day,
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
            inferred_production_id=inferred_prod,
            inferred_shoot_day=inferred_day,
        )

    # 5. Silverstack Offload / Volume / Clips / Shooting Day Reports
    if (
        "VOLUME" in fn_upper
        or "CLIPS" in fn_upper
        or "SILVERSTACK" in fn_upper
        or "THUMBNAIL" in fn_upper
        or "SHOOTING DAY" in fn_upper
        or "SHOOTING_DAY" in fn_upper
        or "OFFLOAD" in fn_upper
        or "POMFORT" in text_sample
        or "SILVERSTACK" in text_sample
        or "<SILVERSTACKREPORT" in text_sample
        or "VOLUME REPORT" in text_sample
        or "SHOOTING DAY REPORT" in text_sample
    ):
        return DocumentClassification(
            doc_type=DocumentType.SILVERSTACK_XML,
            department=DepartmentType.DIT,
            axis=AxisType.EXISTENCE,
            is_multimodal=False,
            display_name="Silverstack DIT Offload Manifest",
            inferred_production_id=inferred_prod,
            inferred_shoot_day=inferred_day,
        )

    # 6. Daily Production Report (Parte de producción / DPR)
    if "PARTEPROD" in fn_upper or "PARTE_PROD" in fn_upper or "DPR" in fn_upper or "PARTE DE PRODUCCION" in text_sample:
        return DocumentClassification(
            doc_type=DocumentType.DPR,
            department=DepartmentType.OFFICE,
            axis=AxisType.INTENT,
            is_multimodal=False,
            display_name="Daily Production Report (Office DPR)",
            inferred_production_id=inferred_prod,
            inferred_shoot_day=inferred_day,
        )

    # Default fallback
    return DocumentClassification(
        doc_type=DocumentType.CAMERA_CSV,
        department=DepartmentType.CAMERA,
        axis=AxisType.BELIEF,
        is_multimodal=False,
        display_name="Generic Paperwork Drop",
        inferred_production_id=inferred_prod,
        inferred_shoot_day=inferred_day,
    )
