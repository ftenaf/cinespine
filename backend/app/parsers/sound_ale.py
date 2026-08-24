"""
Deterministic Parser for Sound ALE and Sound CSV logs.
"""
import csv
import io
from typing import List, Optional
from backend.app.parsers.base import ParsedSoundRecord, ParserFailureError
from backend.app.normalizers.rolls import normalize_sound_roll
from backend.app.normalizers.slates import normalize_slate
from backend.app.normalizers.takes import normalize_take


def parse_sound_ale(content: str) -> List[ParsedSoundRecord]:
    """
    Parses Avid Log Exchange (ALE) or Sound CSV content into normalized sound records.
    """
    if not content or not content.strip():
        raise ParserFailureError("Empty sound log content")

    lines = content.strip().splitlines()
    records: List[ParsedSoundRecord] = []

    # Check if ALE format (contains 'Column' and 'Data' blocks)
    in_columns = False
    in_data = False
    headers: List[str] = []
    data_rows: List[List[str]] = []

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        if line_clean.upper() == "COLUMN":
            in_columns = True
            in_data = False
            continue
        elif line_clean.upper() == "DATA":
            in_columns = False
            in_data = True
            continue

        if in_columns and not headers:
            headers = [h.strip().upper() for h in line.split("\t") if h.strip()]
        elif in_data:
            row = [cell.strip() for cell in line.split("\t")]
            if row and any(row):
                data_rows.append(row)

    # Fallback to standard CSV if not structured as ALE (e.g. Sound Devices CSV reports)
    if not headers or not data_rows:
        reader = csv.reader(io.StringIO(content))
        all_rows = list(reader)
        for idx, row in enumerate(all_rows):
            upper_row = [c.strip().upper() for c in row if c.strip()]
            # Detect header row containing standard sound report columns
            if any(h in upper_row for h in ["SCENE", "SLATE", "FILE NAME", "FILENAME", "TAKE", "START TC"]):
                headers = [c.strip().upper() for c in row]
                data_rows = all_rows[idx + 1:]
                break

    if not headers or not data_rows:
        raise ParserFailureError("Failed to extract valid column headers or data rows from sound log")

    # Map column headers to index
    col_map = {h: idx for idx, h in enumerate(headers)}

    for row in data_rows:
        if len(row) < 2:
            continue

        def get_col(*names: str) -> Optional[str]:
            for n in names:
                if n.upper() in col_map:
                    idx = col_map[n.upper()]
                    if idx < len(row) and row[idx]:
                        return row[idx]
            return None

        raw_slate = get_col("SCENE", "SLATE", "NAME")
        raw_take = get_col("TAKE")
        raw_sr = get_col("SOUND ROLL", "TAPE", "ROLL", "SOUND_ROLL")
        tc_in = get_col("START", "START TC", "TC IN", "TIMECODE IN")
        tc_out = get_col("END", "END TC", "TC OUT", "TIMECODE OUT")
        tracks = get_col("TRACKS", "CHANNELS")
        tape = get_col("TAPE")

        norm_slate = normalize_slate(raw_slate)
        take_info = normalize_take(raw_take)
        norm_sr = normalize_sound_roll(raw_sr)

        # Extract scene number from slate (e.g. 27/7 -> scene 27)
        scene = norm_slate.split("/")[0] if norm_slate and "/" in norm_slate else norm_slate

        # Detect wild track from take box or slate (e.g. 49WT, WT 01)
        is_wild = take_info.is_wild_track or "WT" in (raw_slate or "").upper() or "WILD" in (raw_slate or "").upper()

        record = ParsedSoundRecord(
            scene=scene,
            slate=norm_slate,
            take_id=take_info.take_id,
            sound_roll=norm_sr,
            timecode_in=tc_in,
            timecode_out=tc_out,
            tracks=tracks,
            tape=tape,
            is_starred=take_info.is_starred,
            is_pickup=take_info.is_pickup,
            is_false_start=take_info.is_false_start,
            is_wild_track=is_wild,
            note=take_info.note,
            raw_payload={"raw_slate": raw_slate, "raw_take": raw_take, "raw_sound_roll": raw_sr},
        )
        records.append(record)

    if not records:
        raise ParserFailureError("Parsed sound log produced zero valid records (anti-confident-nothing)")

    return records
