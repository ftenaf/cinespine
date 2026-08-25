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
    is_mos: bool = False
    note: Optional[str] = None


def normalize_take(raw_take: Optional[str]) -> TakeResult:
    """
    Parses free-text take fields to extract canonical take ID and semantic flags.
    Canonical take ID is always an unpadded integer string (e.g. '1', '2', '12'),
    or with standard suffix (e.g. '1PK', 'FALSE'). Strips redundant 'T', 'TK', 'TAKE' prefixes
    and leading zeros to prevent mismatch between T1, T01, and 1.
    
    Examples:
    - '1', '01', '001' -> take_id='1'
    - 'T1', 'T01', 'T001', 'TK01', 'TAKE 1', 'TAKE 01' -> take_id='1'
    - '3*', 'T03*' -> take_id='3', is_starred=True
    - '3 VFX' -> take_id='3', is_vfx=True, note='VFX'
    - '2PK', 'T02PK' -> take_id='2PK', is_pickup=True
    - '1 MOS' -> take_id='1', is_mos=True
    - 'FALSE', 'FC', 'FALSE START' -> take_id='FALSE', is_valid_take=False, is_false_start=True
    - 'WT 01', 'WTT01' -> take_id='1', is_valid_take=True, is_wild_track=True
    """
    if not raw_take or not isinstance(raw_take, str):
        return TakeResult(take_id=None, is_valid_take=False)

    cleaned = raw_take.strip().upper()
    if not cleaned:
        return TakeResult(take_id=None, is_valid_take=False)

    # 1. Check for False Start
    if cleaned in ["FC", "FALSE"] or "FALSE" in cleaned:
        return TakeResult(take_id="FALSE", is_valid_take=False, is_false_start=True)

    # 2. Check for Wild Track
    if cleaned.startswith("WT") or cleaned.startswith("WILD"):
        m_wt = re.search(r"(?:WT|WILD)\s*T?0*(\d+)", cleaned)
        wt_tk = str(int(m_wt.group(1))) if m_wt else "1"
        return TakeResult(take_id=wt_tk, is_valid_take=True, is_wild_track=True)

    # 3. Check for Star / Circled / Chosen / Print take indicator
    is_starred = "*" in cleaned or "CIRCLED" in cleaned or "CHOSEN" in cleaned or "PRINT" in cleaned or "STAR" in cleaned
    is_mos = "MOS" in cleaned or "M.O.S" in cleaned or "MUTE" in cleaned or "SILENT" in cleaned
    cleaned = (
        cleaned.replace("*", " ")
        .replace("CIRCLED", " ")
        .replace("CHOSEN", " ")
        .replace("PRINT", " ")
        .replace("STAR", " ")
        .replace("MOS", " ")
        .replace("M.O.S", " ")
        .replace("MUTE", " ")
        .replace("SILENT", " ")
        .strip()
    )

    # 4. Strip TAKE / TK / T prefix (e.g. TAKE 01 -> 01, T01 -> 01, TK1 -> 1)
    cleaned = re.sub(r"^(?:TAKE|TK)\s*", "", cleaned, flags=re.IGNORECASE).strip()
    if re.match(r"^T0*\d", cleaned, re.IGNORECASE):
        cleaned = re.sub(r"^T", "", cleaned, flags=re.IGNORECASE).strip()

    # 5. Check for Pickup and VFX
    is_vfx = "VFX" in cleaned
    is_pickup = "PK" in cleaned or "P/U" in cleaned or "PICKUP" in cleaned

    # 6. Tokenize to separate take from notes (e.g. '3 VFX')
    tokens = cleaned.split()
    first_token = tokens[0] if tokens else ""
    remaining_note = " ".join(tokens[1:]) if len(tokens) > 1 else None

    if not first_token:
        return TakeResult(take_id=None, is_valid_take=False)

    # 7. Normalize take numbers (e.g., '01' -> '1', 'T02PK' -> '2PK')
    if first_token.isdigit():
        take_id = str(int(first_token))
    elif re.match(r"^0*(\d+)(?:PK|P/U|PICKUP)?$", first_token, re.IGNORECASE):
        m = re.match(r"^0*(\d+)(?:PK|P/U|PICKUP)?$", first_token, re.IGNORECASE)
        num = int(m.group(1))
        take_id = f"{num}PK" if is_pickup else str(num)
    elif re.match(r"^0*(\d+)([A-Z]+)$", first_token, re.IGNORECASE):
        m = re.match(r"^0*(\d+)([A-Z]+)$", first_token, re.IGNORECASE)
        num = int(m.group(1))
        sfx = m.group(2).upper()
        take_id = f"{num}{sfx}"
    else:
        take_id = first_token

    return TakeResult(
        take_id=take_id,
        is_valid_take=True,
        is_starred=is_starred,
        is_pickup=is_pickup,
        is_vfx=is_vfx,
        is_mos=is_mos,
        note=remaining_note,
    )
