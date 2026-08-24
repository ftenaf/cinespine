"""
Camera and Sound Roll Normalization & Key Folding.

Evidence:
- references/domain/identity-rules.md
- references/findings/defects-found.md
"""
import re
from typing import Optional


def normalize_camera_roll(raw_roll: Optional[str]) -> Optional[str]:
    """
    Folds camera rolls into a single canonical key while avoiding naive zero-stripping.
    
    Examples:
    - 'A120', 'A_0120', 'A_0120_1EIC' -> 'A120'
    - 'B039', 'B_0039', 'B39' -> 'B039'
    - 'C001', 'C_0001', 'C1' -> 'C001'
    """
    if not raw_roll or not isinstance(raw_roll, str):
        return None
    
    cleaned = raw_roll.strip().upper()
    if not cleaned:
        return None

    # Match Unit Letter + Digits (ignoring separators like _ and trailing reel info)
    # Examples: A_0120, B039, C_0001_1EIC, A-120
    match = re.match(r"^([A-Z])[\-_]?0*(\d+)", cleaned)
    if not match:
        return cleaned

    unit_letter = match.group(1)
    roll_num = int(match.group(2))

    # Standard production 3-digit roll formatting:
    # 1 -> 001, 39 -> 039, 120 -> 120
    if roll_num < 100:
        return f"{unit_letter}{roll_num:03d}"
    return f"{unit_letter}{roll_num}"


def normalize_sound_roll(raw_roll: Optional[str]) -> Optional[str]:
    """
    Folds sound rolls into canonical SR## form.
    
    Examples:
    - 'SR01', 'SR_001', 'R01', '01' -> 'SR01'
    """
    if not raw_roll or not isinstance(raw_roll, str):
        return None
    
    cleaned = raw_roll.strip().upper()
    if not cleaned:
        return None

    # Extract all digits
    digits = re.findall(r"\d+", cleaned)
    if not digits:
        return cleaned
    
    num = int(digits[0])
    return f"SR{num:02d}"
