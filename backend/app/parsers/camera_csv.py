"""
Deterministic Parser for Camera CSV Reports.
"""
import csv
import re
import io
from typing import List, Optional
from backend.app.parsers.base import ParsedCameraRecord, ParserFailureError
from backend.app.normalizers.rolls import normalize_camera_roll
from backend.app.normalizers.slates import normalize_slate
from backend.app.normalizers.takes import normalize_take


# A slate is a scene and a shot: `27/7`, `64A/1`, `49WT`, `6WT`. It begins with
# a digit, because a scene number does, and it is short -- the longest real one
# on the productions seen here is a compound like `41+122A/4`.
_SLATE_SHAPE = re.compile(r"^\+?\d+[A-Za-z]{0,3}(?:[+-]\d+[A-Za-z]{0,3})*\s*[-/_ ]?\s*(?:\d+[A-Za-z]?|WT|WILD)?(?:T\d+)?$", re.IGNORECASE)


def looks_like_a_take(raw_slate: Optional[str]) -> bool:
    """
    Whether this row is a take at all.

    Camera reports are not only takes. They carry headers, footers, totals and
    contact blocks, and `normalize_slate` canonicalises whatever it is given --
    so a line reading "Contact: someone@example.com Tel: 600 123 456" became a
    slate, reached the spine and the analytical mirror, and surfaced in an
    analytics result as a scene.

    The test is the shape of a slate rather than a list of things to exclude.
    A blocklist of junk lines is the failure mode this project calls the keyed
    list that rots: the next report has a footer nobody thought of.
    """
    candidate = (raw_slate or "").strip()
    if not candidate or len(candidate) > 20:
        return False
    return bool(_SLATE_SHAPE.match(candidate))


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
    skipped_rows: List[str] = []

    # Takes the row as an argument rather than closing over the loop variable:
    # a closure defined inside the loop reads whatever `row` holds when it is
    # called, which is correct only for as long as nobody defers the call.
    def get_col(row: List[str], *names: str) -> Optional[str]:
        for n in names:
            if n.upper() in col_map:
                idx = col_map[n.upper()]
                if idx < len(row) and row[idx].strip():
                    return row[idx].strip()
        return None

    for row in rows[1:]:
        if not row or not any(row):
            continue

        raw_slate = get_col(row, "SLATE", "SCENE/SHOT", "SCENE")
        raw_take = get_col(row, "TAKE")
        raw_roll = get_col(row, "ROLL", "CAMERA ROLL", "CAMERAROLL", "REEL")
        clip_name = get_col(row, "CLIP NAME", "CLIPNAME", "CLIP", "FILE NAME", "FILENAME")
        tc_in = get_col(row, "START TC", "START", "TC IN", "TIMECODE IN")
        tc_out = get_col(row, "END TC", "END", "TC OUT", "TIMECODE OUT")
        lens = get_col(row, "LENS", "FOCAL LENGTH")
        raw_fps = get_col(row, "FPS", "FRAME RATE")
        raw_iso = get_col(row, "ISO", "EI/ISO", "EI")
        shutter = get_col(row, "SHUTTER", "ANGLE")

        if not looks_like_a_take(raw_slate):
            # A row that is not a take at all. Camera reports carry footers,
            # contact blocks and totals, and normalize_slate will happily
            # canonicalise any of them into something that looks like a slate:
            # a contact line once reached the spine, the analytical mirror and
            # an analytics result as the "scene" it was grouped under.
            #
            # Skipped rather than rejected, because one junk row does not make
            # the document unparseable and refusing the whole report over a
            # footer would lose the takes above it. The empty-result guard
            # below still catches a document that is *entirely* junk.
            skipped_rows.append(raw_slate or "(blank)")
            continue

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
