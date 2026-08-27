"""
Reads a handwritten camera report.

A camera report (parte de camara) is a printed form the camera assistant fills
in by hand, one row per clip. Only the printed headings survive text
extraction -- roughly four hundred characters of production and camera setup --
while every roll, clip, slate, take and lens is ink. Parsed as text it yields
nothing, and a parser that yields nothing reports a clean document rather than
an unread one.

So it is read the way a lined page is: as a picture, through the model candidate
chain in llm_router, with the result put through the same slate, take and roll
normalisers every other camera document uses.
"""
import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from backend.app.agents.multimodal import (
    MAX_DOCUMENT_BYTES,
    SUPPORTED_MIME_TYPES,
    _coerce_page_list,
    resolve_mime_type,
    split_slate_take,
)
from backend.app.normalizers.rolls import normalize_camera_roll
from backend.app.normalizers.slates import normalize_slate
from backend.app.normalizers.takes import normalize_take
from backend.app.parsers.base import ParsedCameraRecord
from backend.app.script.llm_router import get_model_candidates

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = float(os.environ.get("CINESPINE_CAMERA_REPORT_TIMEOUT", "120"))

TRANSIENT_RETRIES = 1
TRANSIENT_BACKOFF_SECONDS = 3.0
_TRANSIENT_MARKERS = ("503", "UNAVAILABLE", "high demand", "overloaded", "500", "INTERNAL")


def is_enabled() -> bool:
    """Reading camera reports runs only when configured and not explicitly disabled."""
    if os.environ.get("CINESPINE_DISABLE_CAMERA_REPORT_VISION", "").strip().lower() in (
        "1", "true", "yes",
    ):
        return False
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


EXTRACTION_PROMPT = """You are reading a film camera report, a printed form filled in by
hand by the camera assistant. Return JSON only.

WHAT THIS DOCUMENT IS
The headings are printed; everything under them is handwriting. Each row is one recorded
clip. The columns are usually Roll, Card, Clip, Scene/Shot, Take, Lens, T (T-stop), Int.,
Filters and Comments. Column order and headings vary by production, so read the headings
printed on this page rather than assuming that order.

WHAT TO RETURN
{
  "camera": "the camera letter this report is for, such as A, B or C",
  "shoot_day": "the day number printed on the form, digits only",
  "camera_body": "the camera model in the header, such as ALEXA 35",
  "fps": the frame rate in the header, as a number,
  "iso": the EI or ISO in the header, as a number,
  "shutter": "the shutter angle in the header",
  "rows": [
    {
      "camera_roll": "the roll, such as B041",
      "card": "the card or magazine, if written",
      "clip_name": "the clip, such as B041_C003, or just C003",
      "slate": "the scene and shot exactly as written, such as 119/5",
      "take_id": "the take alone. Keep any mark on the take itself, such as 3*, 2PK or FALSE",
      "lens": "focal length, such as 32mm",
      "t_stop": "the T number, such as T2.8",
      "filters": "any filter written on the row",
      "comments": "the remark on that row, verbatim",
      "is_circled": true if the take number is circled, ticked or asterisked
    }
  ]
}

RULES
1. One object per written row. Do not merge rows, and do not invent a row to fill a column.
2. Transcribe exactly. 3*, 2PK, FALSE and WT all carry meaning that is lost if you tidy
   them, and the tidying happens after you.
3. Keep leading zeros in rolls and clips. B039 and B39 are written differently on different
   documents, and which is correct is resolved later, not by you.
4. Put only the take in take_id. A cell reading 119/5 is the scene and shot, and belongs in
   slate.
5. A circled or ticked take is the one editorial will look for. Set is_circled for it.
6. Where a cell is empty or illegible use null. Never guess a plausible value: a guessed
   roll and a missing roll are indistinguishable downstream, and one of them is wrong.
7. If this page is not a camera report, return {"rows": []}."""


# A slate as a camera report writes it: 73A/14, 119/5, 74B. Anything else in
# that cell is an annotation the assistant wrote there, not a shot.
_SLATE_SHAPE = re.compile(r"^\d{1,3}[A-Z]?(?:\s*/\s*\d{1,3}[A-Z]?)?$", re.IGNORECASE)


def _looks_like_a_slate(value: str) -> bool:
    return bool(value) and bool(_SLATE_SHAPE.match(value.strip()))


# A roll as written by hand: "#B004 +1", "B 004", "B004 mag2". The token is a
# camera letter and its number; the rest is the assistant's shorthand.
_ROLL_TOKEN = re.compile(r"([A-Z])\s*_?\s*(\d{2,4})", re.IGNORECASE)


def _clean_handwritten_roll(value: str) -> str:
    """
    The roll token out of a hand-written cell, before canonical normalisation.

    normalize_camera_roll expects something already roll-shaped; a cell reading
    "#B004 +1" passes through it untouched and then matches no roll anywhere.
    """
    if not value:
        return ""
    match = _ROLL_TOKEN.search(value)
    if not match:
        return value.strip()
    return f"{match.group(1).upper()}{match.group(2)}"


def _is_transient(exc: Exception) -> bool:
    """Whether retrying the same model in a moment is worth trying."""
    text = str(exc)
    return any(marker in text for marker in _TRANSIENT_MARKERS)


class CameraReportVisionReader:
    """Reads handwritten camera reports. Normalisation works without a model."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self._client = None
        if api_key:
            try:
                from google import genai

                self._client = genai.Client(api_key=api_key)
            except Exception as exc:  # noqa: BLE001 - reading is optional
                logger.warning("Could not initialise the Google GenAI client: %s", exc)

    @property
    def is_available(self) -> bool:
        """Whether a model can be called, as opposed to only normalising."""
        return self._client is not None

    def read(self, document_bytes: bytes, mime_type: str) -> List[ParsedCameraRecord]:
        """
        Returns one record per written row.

        Blocking; run it off the event loop from an async caller. Raises rather
        than returning an empty list when it cannot do the work: an empty report
        is a real answer, and returning one on failure would make an outage
        indistinguishable from a blank page.
        """
        if self._client is None:
            raise RuntimeError(
                "No Gemini client: CameraReportVisionReader was constructed without an "
                "API key, so handwritten camera reports cannot be read."
            )
        if not document_bytes:
            raise ValueError("No document bytes to read.")
        if len(document_bytes) > MAX_DOCUMENT_BYTES:
            raise ValueError(
                f"Document is {len(document_bytes)} bytes, over the "
                f"{MAX_DOCUMENT_BYTES} byte limit."
            )
        if mime_type not in SUPPORTED_MIME_TYPES:
            raise ValueError(
                f"Unsupported mime type {mime_type!r}; expected one of "
                f"{', '.join(SUPPORTED_MIME_TYPES)}."
            )
        return self.normalize(self._call_model(document_bytes, mime_type))

    def _call_model(self, document_bytes: bytes, mime_type: str) -> str:
        from google.genai import types

        part = types.Part.from_bytes(data=document_bytes, mime_type=mime_type)
        last_error: Optional[Exception] = None

        for model in get_model_candidates(EXTRACTION_PROMPT, task_complexity="complex"):
            for attempt in range(TRANSIENT_RETRIES + 1):
                try:
                    response = self._client.models.generate_content(
                        model=model,
                        contents=[part, EXTRACTION_PROMPT],
                        config={"response_mime_type": "application/json", "temperature": 0.0},
                    )
                except Exception as exc:  # noqa: BLE001 - retry, then the next model
                    last_error = exc
                    if attempt < TRANSIENT_RETRIES and _is_transient(exc):
                        logger.info("Model %s busy, retrying: %s", model, exc)
                        time.sleep(TRANSIENT_BACKOFF_SECONDS)
                        continue
                    logger.warning("Model %s could not read the report: %s", model, exc)
                    break

                text = (response.text or "").strip()
                if text:
                    logger.info("Camera report read by %s", model)
                    return text
                last_error = ValueError(f"{model} returned an empty response")
                break

        raise RuntimeError("No Gemini model could read this camera report") from last_error

    def normalize(self, raw_json_str: str) -> List[ParsedCameraRecord]:
        """Puts the model's rows through the normalisers the other camera paths use."""
        try:
            data = json.loads(raw_json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON from camera report extraction: {exc}")

        records: List[ParsedCameraRecord] = []
        # A camera report writes the slate once and leaves the cell empty for the
        # takes beneath it. Read row by row that reads as "no slate", which
        # detaches every take after the first from the shot it belongs to.
        last_slate: Optional[str] = None

        for page in _coerce_page_list(data):
            header_fps = page.get("fps")
            header_iso = page.get("iso")
            shutter = page.get("shutter")
            camera = (str(page.get("camera") or "").strip().upper()[:1]) or None

            for row in page.get("rows") or []:
                if not isinstance(row, dict):
                    continue

                raw_slate = str(row.get("slate") or "").strip()
                embedded_slate, raw_take = split_slate_take(str(row.get("take_id") or ""))
                if embedded_slate and not raw_slate:
                    raw_slate = embedded_slate

                take_info = normalize_take(raw_take)
                roll = normalize_camera_roll(_clean_handwritten_roll(str(row.get("camera_roll") or ""))) or None

                # Only a value shaped like a slate becomes one. A cell reading
                # "CLIP FALSO" is the assistant annotating a false clip, and
                # taking it literally invents a shot by that name.
                slate = normalize_slate(raw_slate) if _looks_like_a_slate(raw_slate) else None
                annotation = None if slate else (raw_slate or None)

                if slate:
                    last_slate = slate
                elif take_info.take_id:
                    # Blank cell under a slate: the ditto convention, not absence.
                    slate = last_slate

                note = row.get("comments") or take_info.note
                if annotation:
                    note = f"{annotation} {note}".strip() if note else annotation

                # A row naming neither a slate nor a take identifies nothing, and
                # storing it would add a clip that matches no take anywhere.
                if not slate and not take_info.take_id:
                    continue

                records.append(
                    ParsedCameraRecord(
                        slate=slate,
                        take_id=take_info.take_id,
                        camera_roll=roll,
                        clip_name=row.get("clip_name") or None,
                        timecode_in=None,
                        timecode_out=None,
                        fps=_as_float(header_fps, 24.0),
                        lens=row.get("lens") or None,
                        iso=_as_int(header_iso),
                        shutter=shutter,
                        is_starred=bool(row.get("is_circled")) or take_info.is_starred,
                        is_pickup=take_info.is_pickup,
                        is_false_start=take_info.is_false_start,
                        is_vfx=take_info.is_vfx,
                        is_mos=take_info.is_mos,
                        note=note,
                        raw_payload={
                            "camera": camera,
                            "card": row.get("card"),
                            "t_stop": row.get("t_stop"),
                            "filters": row.get("filters"),
                            # Marked at the source, because a value read off
                            # handwriting is weaker evidence than a typed export
                            # and anything reconciling against it should know.
                            "source": "handwritten_vision",
                        },
                    )
                )
        return records


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


async def read_camera_report_if_enabled(
    document_bytes: bytes,
    filename: str,
    content_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Reads a handwritten camera report during upload, if it can.

    Returns {"records": [...], "warnings": [str]}. Never raises: ingesting the
    document is what the user asked for and must not fail because a model was
    unavailable. Every reason for coming back empty is reported, because an
    unread report and an empty one are otherwise indistinguishable.
    """
    mime_type = resolve_mime_type(filename, content_type)
    if mime_type is None:
        return {
            "records": [],
            "warnings": [
                f"{filename} looks like a handwritten camera report but is not an image "
                "or PDF, so nothing could be read from it."
            ],
        }

    if not is_enabled():
        return {
            "records": [],
            "warnings": [
                "Handwritten camera report reading is off; set GEMINI_API_KEY to have "
                "its rolls, clips, slates and takes read from the page."
            ],
        }

    reader = CameraReportVisionReader(
        api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    )
    try:
        records = await asyncio.wait_for(
            asyncio.to_thread(reader.read, document_bytes, mime_type),
            timeout=TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("Camera report reading timed out on %s", filename)
        return {
            "records": [],
            "warnings": [
                f"Reading {filename} timed out after {TIMEOUT_SECONDS:.0f}s; the document "
                "was ingested but its rows were not read."
            ],
        }
    except Exception as exc:  # noqa: BLE001 - ingestion must survive any of these
        logger.warning("Camera report reading failed on %s: %s", filename, exc)
        return {
            "records": [],
            "warnings": [
                f"Could not read {filename}: {exc}. The document was ingested, but its "
                "rows were not extracted."
            ],
        }

    warnings: List[str] = []
    if not records:
        warnings.append(
            f"No rows were read from {filename}. Either the report is blank, or the "
            "handwriting could not be read; check the page before relying on this."
        )
    return {"records": records, "warnings": warnings}
