"""
Event Envelope and Streaming Domain Models.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional
from uuid import uuid4
from pydantic import BaseModel, Field
from backend.app.normalizers.shoot_days import normalize_shoot_day


class AxisType(str, Enum):
    INTENT = "intent"
    BELIEF = "belief"
    EXISTENCE = "existence"
    DISAGREEMENT = "disagreement"


class DepartmentType(str, Enum):
    OFFICE = "office"
    CAMERA = "camera"
    SOUND = "sound"
    SCRIPT = "script"
    DIT = "dit"
    EDITORIAL = "editorial"
    VFX = "vfx"


class DocumentType(str, Enum):
    CALL_SHEET = "call_sheet"
    DPR = "dpr"
    CAMERA_CSV = "camera_csv"
    SOUND_ALE = "sound_ale"
    SCRIPT_LINED = "script_lined"
    SCRIPT_TIMECODE = "script_timecode"
    SILVERSTACK_XML = "silverstack_xml"
    SILVERSTACK_CLIPS = "silverstack_clips"


class EventEnvelope(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    production_id: str
    shoot_day: str
    axis: AxisType
    department: DepartmentType
    doc_type: DocumentType
    raw_content: str
    filename: Optional[str] = None
    author: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        # Normalize shoot day on envelope creation
        normalized = normalize_shoot_day(self.shoot_day)
        if normalized:
            self.shoot_day = normalized
