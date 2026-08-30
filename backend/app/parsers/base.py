"""
Base Parser Definitions and Error Types.

Evidence:
- references/constraints/failure-modes.md ('The confident nothing')
"""
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


class ParserFailureError(Exception):
    """Raised when a parser fails validation, produces 0 rows, or detects unaligned data."""
    pass


@dataclass
class ParsedScriptRecord:
    scene: Optional[str]
    slate: Optional[str]
    take_id: Optional[str]
    camera_roll: Optional[str]
    timecode_in: Optional[str] = None
    timecode_out: Optional[str] = None
    recording_date: Optional[str] = None
    # The day this take was shot, when the document says so. A facing page files
    # a shot under every scene it plays in, so one page carries takes from
    # several days and the day the document was filed is not the day they were
    # shot. None means the document made no claim and the upload's day stands.
    shoot_day: Optional[str] = None
    is_starred: bool = False
    is_pickup: bool = False
    is_false_start: bool = False
    is_wild_track: bool = False
    is_vfx: bool = False
    is_mos: bool = False
    note: Optional[str] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)



@dataclass
class ParsedSoundRecord:
    scene: Optional[str]
    slate: Optional[str]
    take_id: Optional[str]
    sound_roll: Optional[str]
    timecode_in: Optional[str]
    timecode_out: Optional[str]
    file_name: Optional[str] = None
    duration: Optional[str] = None
    sample_rate: Optional[str] = None
    bit_depth: Optional[str] = None
    camera_roll: Optional[str] = None
    tracks: Optional[str] = None
    tape: Optional[str] = None
    is_starred: bool = False
    is_pickup: bool = False
    is_false_start: bool = False
    is_wild_track: bool = False
    is_vfx: bool = False
    is_mos: bool = False
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
    is_mos: bool = False
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
    reel_tape: Optional[str] = None
    scene: Optional[str] = None
    shot: Optional[str] = None
    take_id: Optional[str] = None
    codec: Optional[str] = None
    recording_date: Optional[str] = None
    camera: Optional[str] = None
    fps: Optional[float] = None
    iso: Optional[int] = None
    tstop: Optional[str] = None
    is_vfx: bool = False
    is_pickup: bool = False
    is_wild_track: bool = False
    card_type: Optional[str] = None
    thumbnail_b64: Optional[str] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)

# A clip is named by a file: `A120_C001_260728.MOV`, `27-7T01.WAV`,
# `A_0120C001_260728_091309_h1EIC`. One token, no spaces.
#
# This is the third shape guard on the same defect. A camera CSV footer became
# a slate; a sound report footer became a slate; a Silverstack thumbnail report
# splits its clips on lines beginning "Name ", so a contact block prefixed that
# way became an entire clip -- with an email address in `file_name`, which a
# slate-shaped test would never have caught because it is not a slate.
#
# `looks_like_a_take` in camera_csv.py is the sibling of this and belongs here
# beside it; moving it ripples through its tests, so it has not been moved yet.
_CLIP_NAME = re.compile(r"^\+?[A-Za-z0-9][A-Za-z0-9._+-]{0,119}$")


def looks_like_a_clip_name(value: Optional[str]) -> bool:
    """
    Whether this names a media file, rather than being prose that happened to
    sit under the right label.

    Tested on the shape of a filename instead of a list of things to exclude:
    a blocklist of footers is wrong the day a report carries one nobody
    anticipated -- the failure mode this project calls the keyed list that
    rots. A filename has no whitespace and no `@`; a contact line has both.
    """
    candidate = (value or "").strip()
    if not candidate:
        return False
    # Every real clip name carries a number -- a camera roll, a clip index, a
    # take. Requiring one is what separates a filename from a footer word:
    # `TOTAL` matches the character shape and is not a clip.
    if not any(c.isdigit() for c in candidate):
        return False
    return bool(_CLIP_NAME.match(candidate))

