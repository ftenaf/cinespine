"""
Discrepancy Models and Severity Enums.
"""
from enum import Enum
from typing import Dict, Any, List, Optional
from uuid import uuid4
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class DiscrepancyType(str, Enum):
    CIRCLED_TAKE_MISMATCH = "CIRCLED_TAKE_MISMATCH"
    TIMECODE_DRIFT = "TIMECODE_DRIFT"
    ROLL_MISMATCH = "ROLL_MISMATCH"
    PAPERWORK_WITHOUT_MEDIA = "PAPERWORK_WITHOUT_MEDIA"
    MEDIA_WITHOUT_PAPERWORK = "MEDIA_WITHOUT_PAPERWORK"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class Discrepancy(BaseModel):
    discrepancy_id: str = Field(default_factory=lambda: str(uuid4()))
    production_id: str
    shoot_day: str
    entity_type: str  # 'take', 'media_file', 'slate'
    entity_id: str    # e.g. '27/7 Take 3' or 'A120_C001_260728.MOV'
    discrepancy_type: DiscrepancyType
    severity: Severity
    description: str
    witnesses: List[Dict[str, Any]] = Field(default_factory=list)
    is_resolved: bool = False
    resolved_card: Optional[str] = None
    resolution_note: Optional[str] = None
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

