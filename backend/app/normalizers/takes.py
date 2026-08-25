"""
Take Normalization and Semantic Flagging.

Evidence:
- references/domain/identity-rules.md
- references/findings/defects-found.md
"""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class TakeResult:
    take_id: Optional[str]
    is_valid_take: bool = True
    is_starred: bool = False
    is_pickup: bool = False
    is_false_start: bool = False
    is_wild_track: bool = False
    is_vfx: bool = False
    note: Optional[str] = None


def normalize_take(raw_take: Optional[str]) -> TakeResult:
    """
    Parses free-text take fields to extract canonical take ID and semantic flags.
    
    Examples:
    - '1', '01' -> take_id='1'
    - '3*' -> take_id='3', is_starred=True
    - '3 VFX' -> take_id='3', is_vfx=True, note='VFX'
    - '2PK' -> take_id='2PK', is_pickup=True
    - 'FALSE' -> is_valid_take=False, is_false_start=True
    - 'WT 01' -> is_valid_take=False, is_wild_track=True
    """
    if not raw_take or not isinstance(raw_take, str):
        return TakeResult(take_id=None, is_valid_take=False)

    cleaned = raw_take.strip().upper()
    if not cleaned:
        return TakeResult(take_id=None, is_valid_take=False)

    # 1. Check for False Start
    if "FALSE" in cleaned:
        return TakeResult(take_id=None, is_valid_take=False, is_false_start=True)

    # 2. Check for Wild Track
    if cleaned.startswith("WT") or cleaned.startswith("WILD"):
        return TakeResult(take_id=None, is_valid_take=False, is_wild_track=True)

    # 3. Check for Star / Circled / Chosen / Print take indicator
    is_starred = "*" in cleaned or "CIRCLED" in cleaned or "CHOSEN" in cleaned or "PRINT" in cleaned or "STAR" in cleaned
    cleaned = (
        cleaned.replace("*", " ")
        .replace("CIRCLED", " ")
        .replace("CHOSEN", " ")
        .replace("PRINT", " ")
        .replace("STAR", " ")
        .strip()
    )

    # 4. Tokenize to separate take from notes (e.g. '3 VFX')
    tokens = cleaned.split()
    first_token = tokens[0] if tokens else ""
    remaining_note = " ".join(tokens[1:]) if len(tokens) > 1 else None

    is_vfx = "VFX" in cleaned
    is_pickup = "PK" in first_token or "P/U" in cleaned

    # Normalize take numbers (e.g., '01' -> '1', '2PK' -> '2PK')
    if first_token.isdigit():
        take_id = str(int(first_token))
    elif is_pickup and re.match(r"^(\d+)PK$", first_token):
        m = re.match(r"^(\d+)PK$", first_token)
        take_id = f"{int(m.group(1))}PK"
    elif first_token:
        take_id = first_token
    else:
        return TakeResult(take_id=None, is_valid_take=False)

    return TakeResult(
        take_id=take_id,
        is_valid_take=True,
        is_starred=is_starred,
        is_pickup=is_pickup,
        is_vfx=is_vfx,
        note=remaining_note,
    )
