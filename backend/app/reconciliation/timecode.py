"""
SMPTE Timecode Utilities and Frame Drift Calculations.
"""
import re
from typing import Optional


def timecode_to_frames(tc_str: Optional[str], fps: float = 24.0) -> Optional[int]:
    """
    Converts HH:MM:SS:FF string to total frame count.
    """
    if not tc_str or not isinstance(tc_str, str):
        return None

    cleaned = tc_str.strip()
    match = re.match(r"^(\d{2}):(\d{2}):(\d{2})[:;](\d{2})$", cleaned)
    if not match:
        return None

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    frames = int(match.group(4))

    total_seconds = (hours * 3600) + (minutes * 60) + seconds
    return int(round(total_seconds * fps)) + frames


def calculate_frame_drift(tc1: Optional[str], tc2: Optional[str], fps: float = 24.0) -> Optional[int]:
    """
    Returns absolute difference in frames between two SMPTE timecode strings.
    """
    f1 = timecode_to_frames(tc1, fps)
    f2 = timecode_to_frames(tc2, fps)

    if f1 is None or f2 is None:
        return None

    return abs(f1 - f2)
