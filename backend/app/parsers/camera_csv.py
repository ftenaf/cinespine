"""
Deterministic Parser for Camera CSV Reports.
"""
import csv
import io
from typing import List, Optional
from backend.app.parsers.base import ParsedCameraRecord, ParserFailureError
from backend.app.normalizers.rolls import normalize_camera_roll
from backend.app.normalizers.slates import normalize_slate
from backend.app.normalizers.takes import normalize_take


def parse_camera_csv(content: str) -> List[ParsedCameraRecord]:
    """
    Parses camera report CSV exports into normalized camera records.
    """
    if not content or not content.strip():
        raise ParserFailureError("Empty camera report CSV content")

    reader = csv.reader(io.StringIO(content.strip()))
    rows = list(reader)

    if len(rows) < 2:
        raise ParserFailureError("Camera CSV must contain a header row and at least one data row")

    headers = [h.strip().upper() for h in rows[0]]
    col_map = {h: idx for idx, h in enumerate(headers)}

    records: List[ParsedCameraRecord] = []

    for row in rows[1:]:
        if not row or not any(row):
            continue

        def get_col(*names: str) -> Optional[str]:
            for n in names:
                if n.upper() in col_map:
                    idx = col_map[n.upper()]
                    if idx < len(row) and row[idx].strip():
                        return row[idx].strip()
            return None

        raw_slate = get_col("SLATE", "SCENE/SHOT", "SCENE")
        raw_take = get_col("TAKE")
        raw_roll = get_col("ROLL", "CAMERA ROLL", "CAMERAROLL", "REEL")
        clip_name = get_col("CLIP NAME", "CLIPNAME", "CLIP", "FILE NAME", "FILENAME")
        tc_in = get_col("START TC", "START", "TC IN", "TIMECODE IN")
        tc_out = get_col("END TC", "END", "TC OUT", "TIMECODE OUT")
        lens = get_col("LENS", "FOCAL LENGTH")
        raw_fps = get_col("FPS", "FRAME RATE")
        raw_iso = get_col("ISO", "EI/ISO", "EI")
        shutter = get_col("SHUTTER", "ANGLE")

        norm_slate = normalize_slate(raw_slate)
        take_info = normalize_take(raw_take)
        norm_cr = normalize_camera_roll(raw_roll)

        fps = float(raw_fps) if raw_fps and raw_fps.replace(".", "", 1).isdigit() else 24.0
        iso = int(raw_iso) if raw_iso and raw_iso.isdigit() else None

        record = ParsedCameraRecord(
            slate=norm_slate,
            take_id=take_info.take_id,
            camera_roll=norm_cr,
            clip_name=clip_name,
            timecode_in=tc_in,
            timecode_out=tc_out,
            fps=fps,
            lens=lens,
            iso=iso,
            shutter=shutter,
            is_starred=take_info.is_starred,
            is_pickup=take_info.is_pickup,
            is_false_start=take_info.is_false_start,
            is_vfx=take_info.is_vfx,
            note=take_info.note,
            raw_payload={"raw_slate": raw_slate, "raw_take": raw_take, "raw_roll": raw_roll},
        )
        records.append(record)

    if not records:
        raise ParserFailureError("Camera CSV produced zero valid records (anti-confident-nothing)")

    return records
