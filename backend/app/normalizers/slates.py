"""
Slate and Scene Compound Normalization.

Evidence:
- references/domain/identity-rules.md
- references/domain/script-and-scenes.md
"""
import re
from typing import List, Optional


def normalize_slate(raw_slate: Optional[str]) -> Optional[str]:
    """
    Normalizes slate variations (27/7, 27-7, 27-7T01) into canonical scene/shot format.
    
    Examples:
    - '27/7', '27-7', '27-7T01' -> '27/7'
    - '64A/1' -> '64A/1'
    """
    if not raw_slate or not isinstance(raw_slate, str):
        return None

    cleaned = raw_slate.strip().upper()
    if not cleaned:
        return None

    # Strip take suffix if attached (e.g. 27-7T01 -> 27-7)
    cleaned = re.sub(r"T\d+$", "", cleaned)

    # Convert dashes to slashes between scene and shot
    # e.g. 27-7 -> 27/7, 64A-1 -> 64A/1
    if "/" in cleaned:
        parts = cleaned.split("/", 1)
        scene = parts[0].strip()
        shot = parts[1].strip()
        return f"{scene}/{shot}"
    elif "-" in cleaned:
        parts = cleaned.split("-", 1)
        scene = parts[0].strip()
        shot = parts[1].strip()
        return f"{scene}/{shot}"

    return cleaned


def parse_scene_compound(raw_scene: str) -> List[str]:
    """
    Expands compound scene labels (e.g., '21+25', '73C-74AC') into discrete scenes.
    """
    if not raw_scene or not isinstance(raw_scene, str):
        return []

    cleaned = raw_scene.strip().upper()
    if "+" in cleaned:
        return [s.strip() for s in cleaned.split("+") if s.strip()]
    if "-" in cleaned and not cleaned.startswith("-"):
        # e.g. 73C-74AC
        parts = cleaned.split("-")
        if len(parts) == 2 and any(c.isdigit() for c in parts[0]) and any(c.isdigit() for c in parts[1]):
            return [parts[0].strip(), parts[1].strip()]

    return [cleaned]
