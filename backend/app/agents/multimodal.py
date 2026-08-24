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
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.model_name = model_name
        self._client = None

        if api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                self._client = genai.GenerativeModel(model_name)
                logger.info(f"Initialized Gemini model {model_name}")
            except Exception as e:
                logger.warning(f"Could not initialize Google Generative AI: {e}")

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
