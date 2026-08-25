"""
Deterministic Parser for Sound ALE and Sound CSV logs.
"""
import csv
import io
import re
from typing import List, Optional
from backend.app.parsers.base import ParsedSoundRecord, ParserFailureError
from backend.app.normalizers.rolls import normalize_sound_roll
from backend.app.normalizers.slates import normalize_slate
from backend.app.normalizers.takes import normalize_take


def parse_sound_ale(content: str) -> List[ParsedSoundRecord]:
    """
    Parses Avid Log Exchange (ALE) or Sound CSV content into normalized sound records with multi-track support.
    """
    if not content or not content.strip():
        raise ParserFailureError("Empty sound log content")

    lines = content.strip().splitlines()
    records: List[ParsedSoundRecord] = []

    # Extract top metadata key-values (e.g. Sample Rate, Bit Depth, File Type, Sound Mixer)
    top_meta: dict = {}
    for line in lines[:20]:
        if ":" in line and "," in line:
            parts = line.split(":", 1)
            k = parts[0].replace('"', '').strip()
            v = parts[1].replace('"', '').replace(',', '').strip()
            if k and v:
                top_meta[k.upper()] = v

    sample_rate = top_meta.get("SAMPLE RATE")
    bit_depth = top_meta.get("BIT DEPTH")

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

    # Detect multi-track column indices (e.g. TRK 1, TRK 2, TRK 3...)
    track_cols = []
    for h, idx in col_map.items():
        if h.startswith("TRK ") or h.startswith("TRACK ") or h.startswith("CH "):
            track_cols.append((h, idx))
    track_cols.sort(key=lambda x: int(''.join(filter(str.isdigit, x[0])) or 0))

    for row in data_rows:
        if len(row) < 2 or not any(row):
            continue

        def get_col(*names: str) -> Optional[str]:
            for n in names:
                if n.upper() in col_map:
                    idx = col_map[n.upper()]
                    if idx < len(row) and row[idx]:
                        val = row[idx].strip()
                        if val:
                            return val
            return None

        raw_slate = get_col("SCENE", "SLATE", "NAME")
        raw_take = get_col("TAKE")
        file_name = get_col("FILE NAME", "FILENAME", "CLIP NAME")
        raw_sr = get_col("SOUND ROLL", "TAPE", "ROLL", "SOUND_ROLL")
        tc_in = get_col("START", "START TC", "TC IN", "TIMECODE IN")
        tc_out = get_col("END", "END TC", "TC OUT", "TIMECODE OUT")
        duration = get_col("LENGTH", "DURATION")
        row_note = get_col("NOTES", "NOTE", "COMMENTS")
        explicit_tracks = get_col("TRACKS", "CHANNELS")

        # Collect channel names from Trk 1, Trk 2... columns
        active_tracks = []
        for trk_name, trk_idx in track_cols:
            if trk_idx < len(row) and row[trk_idx] and row[trk_idx].strip():
                trk_val = row[trk_idx].strip()
                active_tracks.append(f"{trk_name.title()}: {trk_val}")

        combined_tracks = explicit_tracks
        if active_tracks:
            combined_tracks = ", ".join(active_tracks)

        norm_slate = normalize_slate(raw_slate)
        take_info = normalize_take(raw_take)
        norm_sr = normalize_sound_roll(raw_sr)

        # Detect wild track from take box, slate, or file name (e.g. 49WT, WT 01, 49WTT01.WAV)
        is_wild = (
            take_info.is_wild_track
            or "WT" in (raw_slate or "").upper()
            or "WILD" in (raw_slate or "").upper()
            or bool(file_name and ("WT" in file_name.upper() or "WILD" in file_name.upper()))
        )

        # If it's a wild track and slate does not already have /WT (e.g. raw_slate was '49' with take 'WT 01' or file '49WTT01.WAV')
        if is_wild and norm_slate and "/" not in norm_slate and norm_slate != "WT":
            norm_slate = f"{norm_slate}/WT"

        # If raw_slate was missing but file_name is available (e.g. 49WTT01.WAV or 27-7T01.WAV)
        if not norm_slate and file_name:
            m_fn_wt = re.match(r"^(.+?)WTT?(\d+)\.WAV$", file_name, re.IGNORECASE)
            if m_fn_wt:
                norm_slate = f"{m_fn_wt.group(1)}/WT"
                if not take_info.take_id:
                    take_info = normalize_take(m_fn_wt.group(2))
                is_wild = True
            else:
                m_fn = re.match(r"^([A-Za-z0-9+]+)-([A-Za-z0-9]+)T?(\d+)\.WAV$", file_name, re.IGNORECASE)
                if m_fn:
                    norm_slate = f"{m_fn.group(1)}/{m_fn.group(2)}"
                    if not take_info.take_id:
                        take_info = normalize_take(m_fn.group(3))

        # Extract scene number from slate (e.g. 27/7 -> scene 27, 49/WT -> scene 49)
        scene = norm_slate.split("/")[0] if norm_slate and "/" in norm_slate else norm_slate

        final_note = row_note or take_info.note

        record = ParsedSoundRecord(
            scene=scene,
            slate=norm_slate,
            take_id=take_info.take_id,
            sound_roll=norm_sr,
            timecode_in=tc_in,
            timecode_out=tc_out,
            file_name=file_name,
            duration=duration,
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            tracks=combined_tracks,
            tape=raw_sr,
            is_starred=take_info.is_starred,
            is_pickup=take_info.is_pickup,
            is_false_start=take_info.is_false_start,
            is_wild_track=is_wild,
            note=final_note,
            raw_payload={
                "raw_slate": raw_slate,
                "raw_take": raw_take,
                "raw_sound_roll": raw_sr,
                "file_name": file_name,
                "duration": duration,
                "active_tracks": active_tracks,
                "top_meta": top_meta,
            },
        )
        records.append(record)

    if not records:
        raise ParserFailureError("Parsed sound log produced zero valid records (anti-confident-nothing)")

    return records

