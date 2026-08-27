"""
Gemini Multimodal Vision Extractor for Handwritten Script Lining Pages.

Evidence:
- references/domain/documents.md ('Facing and lined pages')
- references/constraints/safety.md ('Never commit raw confidential material / PII')
"""
import json
import logging
import re
from typing import List, Optional
from pydantic import BaseModel, Field
from backend.app.normalizers.takes import normalize_take
from backend.app.normalizers.rolls import normalize_camera_roll
from backend.app.script.llm_router import get_model_candidates, get_optimal_gemini_model

logger = logging.getLogger(__name__)


class ExtractedTake(BaseModel):
    take_id: str
    camera_rolls: List[str] = Field(default_factory=list)
    is_starred: bool = False
    is_pickup: bool = False
    is_vfx: bool = False
    # A false start is not a failed read, it is a fact about the shoot, and one
    # this system exists to reconcile: the script supervisor marking a take
    # False Start while sound files it Good is the discrepancy, not noise.
    is_false_start: bool = False
    is_wild_track: bool = False
    notes: Optional[str] = None


class ExtractedScriptPage(BaseModel):
    scene: str
    slates: List[str] = Field(default_factory=list)
    takes: List[ExtractedTake] = Field(default_factory=list)
    lining_notes: Optional[str] = None
    page_number: Optional[int] = None


# What Gemini will accept inline. A lining page arrives either as a scan or as a
# page of the facing-pages PDF, so both matter.
SUPPORTED_MIME_TYPES = (
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/heic",
    "application/pdf",
)

# Guards a pointless round trip on an empty or absurd upload.
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024

# The domain facts a general-purpose model cannot infer from the picture, drawn
# from the paperwork itself: lining marks are a drawing rather than a field, the
# take notation is a convention, and camera rolls from other shooting days are
# correct here rather than mistakes.
EXTRACTION_PROMPT = """You are reading a script supervisor's lined script page (also called a
facing page) from a film production. Return JSON only.

WHAT THIS DOCUMENT IS
The vertical or diagonal lines drawn down the script text are coverage marks: each line
runs through the dialogue and action covered by one camera setup, and is annotated at its
head or foot with a slate and take reference. The marks are a drawing, not a form. Read
the annotations, not the geometry.

WHAT TO RETURN
{
  "scene": "the scene number this page belongs to, e.g. 64A",
  "slates": ["every distinct slate on the page, e.g. 21/1"],
  "takes": [
    {
      "take_id": "the take exactly as written, including any suffix or mark",
      "camera_rolls": ["camera rolls annotated for that take, e.g. A120, B039"],
      "is_starred": true if the take is circled or marked with an asterisk,
      "notes": "any handwritten remark about that take, verbatim"
    }
  ],
  "lining_notes": "handwritten remarks not tied to a single take, verbatim",
  "page_number": the script page number printed on the page, as an integer
}

RULES
1. Transcribe take ids exactly as written. Do not tidy them. `3*`, `2PK`, `3 VFX`,
   `FALSE`, `WT 01` all carry meaning that is lost if you normalise them, and the
   normalisation happens after you.
2. A circled take is the one editorial will look for. Set is_starred for a take that is
   circled, ticked, or asterisked, and say which in its notes.
3. Transcribe camera rolls exactly, including leading zeros: `B039` and `B39` are written
   differently on different documents and the difference is resolved later, not by you.
4. These pages are filed per scene across every day that scene was shot, so camera rolls
   from other shooting days belong here. Do not omit a roll because it looks out of place.
5. If a value is not on the page, omit the field or use null. Never invent a plausible
   one: a guessed slate is worse than a missing slate, because nothing downstream can
   tell them apart.
6. If the page is illegible or is not a lined script page at all, return
   {"scene": "", "takes": []} rather than guessing."""


class GeminiScriptLiningExtractor:
    """
    Reads handwritten lining pages, then normalises what the model returned.

    The validation half runs without any model at all, which is how the parsers
    use it today: `validate_and_normalize` and `sanitize_pii` are pure.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key
        # No pinned default. A pinned id 404s the day that version is retired,
        # and every caller here degrades quietly, so the failure would be
        # invisible. The router owns the choice; see llm_router.
        self.model_name = model_name or get_optimal_gemini_model("", task_complexity="simple")
        self._client = None

        if api_key:
            try:
                from google import genai

                self._client = genai.Client(api_key=api_key)
                logger.info("Initialised Gemini client for model %s", self.model_name)
            except Exception as exc:  # noqa: BLE001 - extraction is optional
                logger.warning("Could not initialise the Google GenAI client: %s", exc)

    @property
    def is_available(self) -> bool:
        """Whether a model can actually be called, as opposed to only validated."""
        return self._client is not None

    def extract_page(
        self,
        document_bytes: bytes,
        mime_type: str,
        page_number: Optional[int] = None,
    ) -> ExtractedScriptPage:
        """
        Reads one lined script page and returns its normalised contents.

        Blocking, like the other model calls in this codebase: run it off the
        event loop with `asyncio.to_thread` from an async caller.

        Raises rather than returning an empty page when it cannot do the work.
        An empty ExtractedScriptPage is a real answer -- it means a page that
        genuinely carried no takes -- and returning one on failure would make an
        outage indistinguishable from a blank page, which is precisely how the
        earlier failures in this project stayed invisible.
        """
        if self._client is None:
            raise RuntimeError(
                "No Gemini client: GeminiScriptLiningExtractor was constructed without "
                "an API key, so lined pages cannot be read."
            )
        if not document_bytes:
            raise ValueError("No document bytes to extract from.")
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

        raw = self._call_model(document_bytes, mime_type)
        page = self.validate_and_normalize(raw)

        # The printed page number is what the model read; the caller's is where
        # the page sat in the file. Prefer the caller's, which cannot be misread.
        if page_number is not None:
            page.page_number = page_number
        return page

    def _call_model(self, document_bytes: bytes, mime_type: str) -> str:
        """
        Sends the page to the first model that will take it.

        Candidates rather than one model, for the reason llm_router documents:
        quota is metered per model and the newest one is the first to answer 503.
        """
        from google.genai import types

        part = types.Part.from_bytes(data=document_bytes, mime_type=mime_type)
        last_error: Optional[Exception] = None

        for model in get_model_candidates(EXTRACTION_PROMPT, task_complexity="complex"):
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=[part, EXTRACTION_PROMPT],
                    config={"response_mime_type": "application/json", "temperature": 0.0},
                )
            except Exception as exc:  # noqa: BLE001 - any failure means try the next
                last_error = exc
                logger.warning("Model %s could not read the page: %s", model, exc)
                continue

            text = (response.text or "").strip()
            if text:
                logger.info("Lined page read by %s", model)
                return text
            last_error = ValueError(f"{model} returned an empty response")
            logger.warning("Model %s returned nothing for this page", model)

        raise RuntimeError(
            "No Gemini model could read this lined page"
        ) from last_error

    def sanitize_pii(self, text: str) -> str:
        """
        Redacts personal phone numbers and email addresses found in document headers/footers.
        """
        if not text:
            return ""

        # Redact emails
        email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
        sanitized = re.sub(email_pattern, "[REDACTED_EMAIL]", text)

        # Redact phone numbers (international and local formats)
        phone_pattern = r"(?:\+\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}"
        sanitized = re.sub(phone_pattern, "[REDACTED_PHONE]", sanitized)

        return sanitized

    def validate_and_normalize(self, raw_json_str: str) -> ExtractedScriptPage:
        """
        Validates raw JSON extracted by Gemini and applies canonical normalizations.
        """
        try:
            data = json.loads(raw_json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from multimodal extraction: {e}")

        raw_takes = data.get("takes", [])
        normalized_takes: List[ExtractedTake] = []

        for t in raw_takes:
            raw_take_id = t.get("take_id", "")
            take_info = normalize_take(raw_take_id)
            # Dropped only when nothing identifiable was written. A take that
            # normalises to "not a valid take" is still a record of something
            # that happened on set, and discarding it here would lose the very
            # annotation the page was read for.
            if not take_info.take_id:
                continue

            raw_rolls = t.get("camera_rolls", [])
            norm_rolls = [normalize_camera_roll(r) for r in raw_rolls if normalize_camera_roll(r)]

            is_starred = t.get("is_starred", False) or take_info.is_starred

            normalized_takes.append(
                ExtractedTake(
                    take_id=take_info.take_id,
                    camera_rolls=norm_rolls,
                    is_starred=is_starred,
                    is_pickup=take_info.is_pickup,
                    is_vfx=take_info.is_vfx,
                    is_false_start=take_info.is_false_start,
                    is_wild_track=take_info.is_wild_track,
                    notes=t.get("notes") or take_info.note,
                )
            )

        return ExtractedScriptPage(
            scene=data.get("scene", "").strip().upper(),
            slates=data.get("slates", []),
            takes=normalized_takes,
            lining_notes=self.sanitize_pii(data.get("lining_notes", "")),
            page_number=data.get("page_number"),
        )
