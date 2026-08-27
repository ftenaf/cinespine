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
from backend.app.script.llm_router import get_optimal_gemini_model

logger = logging.getLogger(__name__)


class ExtractedTake(BaseModel):
    take_id: str
    camera_rolls: List[str] = Field(default_factory=list)
    is_starred: bool = False
    is_pickup: bool = False
    is_vfx: bool = False
    notes: Optional[str] = None


class ExtractedScriptPage(BaseModel):
    scene: str
    slates: List[str] = Field(default_factory=list)
    takes: List[ExtractedTake] = Field(default_factory=list)
    lining_notes: Optional[str] = None
    page_number: Optional[int] = None


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
            if not take_info.is_valid_take or not take_info.take_id:
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
