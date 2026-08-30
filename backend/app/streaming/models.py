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


class UserProfile(BaseModel):
    handle: str  # e.g. "@director" (always starts with @)
    name: str  # e.g. "Director"
    email: str  # e.g. "director@example.com"
    role: str  # e.g. "Director", "Sound Mixer", "Assistant Editor"
    avatar_color: str = "#8b5cf6"

    def model_post_init(self, __context: Any) -> None:
        if self.handle and not self.handle.startswith("@"):
            self.handle = f"@{self.handle}"


class RequirementPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RequirementCategory(str, Enum):
    SOUND = "sound"
    VFX = "vfx"
    EDIT = "edit"
    COLOR = "color"
    RESHOOT = "reshoot"
    LEGAL = "legal"
    GENERAL = "general"


class RequirementStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    BLOCKED = "blocked"


class RequirementTargetType(str, Enum):
    # Four levels, coarsest first. A requirement can be about the whole
    # production -- a delivery obligation, a legal clearance, a format
    # decision -- and not about any one scene in it.
    PRODUCTION = "production"
    SCENE = "scene"
    SHOT = "shot"
    TAKE = "take"


class Requirement(BaseModel):
    requirement_id: str = Field(default_factory=lambda: f"req_{uuid4().hex[:10]}")
    production_id: str
    shoot_day: str
    target_type: RequirementTargetType
    target_id: str  # e.g. "49", "49/WT", "49/WT_1"
    target_label: str  # e.g. "Scene 49", "Slate 49/WT", "Take 49/WT T1"
    title: str
    description: str = ""
    priority: RequirementPriority = RequirementPriority.MEDIUM
    category: RequirementCategory = RequirementCategory.GENERAL
    created_by: str  # e.g. "@director"
    assigned_to: str  # e.g. "@sound_supervisor"
    status: RequirementStatus = RequirementStatus.OPEN
    resolution_note: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class NotificationType(str, Enum):
    ASSIGNED = "ASSIGNED"
    RESOLVED = "RESOLVED"
    STATUS_CHANGED = "STATUS_CHANGED"
    COMMENT = "COMMENT"


class Notification(BaseModel):
    notification_id: str = Field(default_factory=lambda: f"notif_{uuid4().hex[:10]}")
    production_id: str
    recipient_handle: str  # e.g. "@sound_supervisor"
    actor_handle: str  # e.g. "@director"
    notification_type: NotificationType
    requirement_id: str
    title: str
    message: str
    target_type: RequirementTargetType
    target_id: str
    target_label: str
    is_read: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


DEFAULT_TEAM_USERS: Dict[str, Dict[str, str]] = {
    "@director": {
        "handle": "@director",
        "name": "Director",
        "email": "director@example.com",
        "role": "Director",
        "avatar_color": "#8b5cf6",
    },
    "@sound_supervisor": {
        "handle": "@sound_supervisor",
        "name": "Sound Supervisor",
        "email": "sound.supervisor@example.com",
        "role": "Sound Mixer / Sound Supervisor",
        "avatar_color": "#10b981",
    },
    "@assistant_editor": {
        "handle": "@assistant_editor",
        "name": "Assistant Editor",
        "email": "assistant.editor@example.com",
        "role": "Assistant Editor",
        "avatar_color": "#3b82f6",
    },
    "@lead_editor": {
        "handle": "@lead_editor",
        "name": "Lead Editor",
        "email": "lead.editor@example.com",
        "role": "Lead Editor",
        "avatar_color": "#ec4899",
    },
    "@vfx_supervisor": {
        "handle": "@vfx_supervisor",
        "name": "VFX Supervisor",
        "email": "vfx.supervisor@example.com",
        "role": "VFX Supervisor",
        "avatar_color": "#f59e0b",
    },
    "@dit_operator": {
        "handle": "@dit_operator",
        "name": "DIT Operator",
        "email": "dit.operator@example.com",
        "role": "DIT / Data Manager",
        "avatar_color": "#06b6d4",
    },
    "@script_supervisor": {
        "handle": "@script_supervisor",
        "name": "Script Supervisor",
        "email": "script.supervisor@example.com",
        "role": "Script Supervisor",
        "avatar_color": "#e11d48",
    },
    "@post_supervisor": {
        "handle": "@post_supervisor",
        "name": "Post Production Supervisor",
        "email": "post.supervisor@example.com",
        "role": "Post Production Supervisor",
        "avatar_color": "#6366f1",
    },
}

