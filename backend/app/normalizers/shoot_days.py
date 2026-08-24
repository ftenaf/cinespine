"""
Shoot Day Code Normalization.

Evidence:
- references/domain/identity-rules.md
- references/domain/grain-and-entities.md
"""
import re
from typing import Optional


def normalize_shoot_day(raw_day: Optional[str]) -> Optional[str]:
    """
    Folds shoot day representations (SD31, D031, #31, 260728_SD31) into canonical integer string.
    
    Examples:
    - 'SD31', 'D031', '#31', '260728_SD31', '31' -> '31'
    """
    if not raw_day or not isinstance(raw_day, str):
        return None

    cleaned = raw_day.strip().upper()
    if not cleaned:
        return None

    # 1. Prioritize explicit shoot day prefixes: SD31, D031, #31, _SD31_
    match = re.search(r"(?:SD|D|#)0*(\d+)", cleaned)
    if match:
        return str(int(match.group(1)))

    # 2. Fall back to standalone numeric day
    if cleaned.isdigit():
        return str(int(cleaned))

    match_digits = re.search(r"\b0*(\d+)\b", cleaned)
    if match_digits:
        return str(int(match_digits.group(1)))

    return cleaned
