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
    # Office planned a scene and says it was shot; no other department has
    # filed anything for it. Office does not observe what happened, so this is
    # two witnesses disagreeing rather than a scene that is missing.
    SCENE_COMPLETE_WITHOUT_MATERIAL = "SCENE_COMPLETE_WITHOUT_MATERIAL"
    # Set shot a scene Office never scheduled. The DPR states this itself, in
    # a named field, and it has always died on the page.
    SCENE_SHOT_NOT_SCHEDULED = "SCENE_SHOT_NOT_SCHEDULED"
    # A scene Office planned and states was not shot. A negative fact, and one
    # nothing downstream could previously ask about.
    SCENE_SCHEDULED_NOT_SHOT = "SCENE_SCHEDULED_NOT_SHOT"
    # Takes were logged on this day and no offload report has arrived, so
    # whether the material exists is unknown. Not the same as missing, and the
    # two need opposite responses: this one is chased with DIT.
    AWAITING_OFFLOAD = "AWAITING_OFFLOAD"
    # A slate some department recorded that falls outside every range Office
    # stated for that scene. Either the slate is wrong or Office's list is
    # short, and both are worth someone looking at.
    SLATE_OUTSIDE_STATED_RANGE = "SLATE_OUTSIDE_STATED_RANGE"
    # Two documents disagree about what calendar date this shoot day was. Every
    # department states it and they should all say the same thing; when they do
    # not, one of them is filed under the wrong day.
    SHOOT_DATE_DISAGREEMENT = "SHOOT_DATE_DISAGREEMENT"


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

