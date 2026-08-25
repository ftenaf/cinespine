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
    Folds sound rolls into canonical SR## form or preserves Sound Devices reel tape folders (e.g. '26Y07M27').
    Filters out dates (e.g. '280726') and non-sound indicators (e.g. 'n/a', 'MOS').
    
    Examples:
    - 'SR01', 'SR_001', 'R01', '01' -> 'SR01'
    - '26Y07M27' -> '26Y07M27'
    - '280726', '20260728' -> None (shoot date, not sound roll)
    - 'n/a', 'NONE', 'MOS' -> None
    """
    if not raw_roll or not isinstance(raw_roll, str):
        return None
    
    cleaned = raw_roll.strip().upper()
    if not cleaned or cleaned in ["N/A", "NONE", "NO", "MOS", "-", "FALSE"]:
        return None

    # Preserve Sound Devices folder formats like 26Y07M27
    if re.match(r"^\d{2}Y\d{2}M\d{2}$", cleaned):
        return cleaned

    # 6 or 8-digit date strings (e.g. 280726, 20260728) are shoot dates, not sound rolls
    if re.match(r"^\d{6,8}$", cleaned):
        return None

    # Match SR## or 1-3 digit roll number
    m = re.match(r"^(?:SR|R|SOUND)?[\-_]?0*(\d{1,3})$", cleaned)
    if m:
        num = int(m.group(1))
        return f"SR{num:02d}"

    return cleaned if "SR" in cleaned else None
