"""
Base Parser Definitions and Error Types.

Evidence:
- references/constraints/failure-modes.md ('The confident nothing')
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


class ParserFailureError(Exception):
    """Raised when a parser fails validation, produces 0 rows, or detects unaligned data."""
    pass


@dataclass
class ParsedSoundRecord:
    scene: Optional[str]
    slate: Optional[str]
    take_id: Optional[str]
    sound_roll: Optional[str]
    timecode_in: Optional[str]
    timecode_out: Optional[str]
    camera_roll: Optional[str] = None
    tracks: Optional[str] = None
    tape: Optional[str] = None
    is_starred: bool = False
    is_pickup: bool = False
    is_false_start: bool = False
    is_wild_track: bool = False
    note: Optional[str] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedCameraRecord:
    slate: Optional[str]
    take_id: Optional[str]
    camera_roll: Optional[str]
    clip_name: Optional[str]
    timecode_in: Optional[str]
    timecode_out: Optional[str]
    fps: float = 24.0
    lens: Optional[str] = None
    iso: Optional[int] = None
    shutter: Optional[str] = None
    is_starred: bool = False
    is_pickup: bool = False
    is_false_start: bool = False
    is_vfx: bool = False
    note: Optional[str] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedSilverstackClip:
    file_name: str
    camera_roll: Optional[str]
    file_size_bytes: int
    checksum: Optional[str] = None
    checksum_type: Optional[str] = None
    volume_name: Optional[str] = None
    duration_frames: Optional[int] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)
