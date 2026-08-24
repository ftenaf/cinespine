"""
Deterministic Parsers for Real Production PDF Reports (ZoeLog Camera, Editor Logs, Silverstack Volume).

Evidence:
- data/examples/
"""
import io
import re
from typing import List, Optional
import pypdf
from backend.app.parsers.base import (
    ParsedCameraRecord,
    ParsedSoundRecord,
    ParsedSilverstackClip,
    ParserFailureError,
)
from backend.app.normalizers.rolls import normalize_camera_roll, normalize_sound_roll
from backend.app.normalizers.slates import normalize_slate
from backend.app.normalizers.takes import normalize_take


def extract_text_from_pdf(pdf_bytes_or_file) -> str:
    """
    Extracts concatenated text from all pages of a PDF.
    """
    if isinstance(pdf_bytes_or_file, bytes):
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes_or_file))
    else:
        reader = pypdf.PdfReader(pdf_bytes_or_file)

    pages_text = []
    for page in reader.pages:
        txt = page.extract_text()
        if txt:
            pages_text.append(txt)

    return "\n".join(pages_text)


def parse_zoelog_camera_text(text: str) -> List[ParsedCameraRecord]:
    """
    Parses ZoeLog camera report text into normalized camera records.
    """
    if not text or not text.strip():
        raise ParserFailureError("Empty ZoeLog text")

    records: List[ParsedCameraRecord] = []
    lines = text.strip().splitlines()

    current_roll = None
    current_slate = None
    current_fps = 24.0
    current_iso = 800
    current_lens = None

    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue

        # 1. Match Roll header: ROLL A120 or ROLLA120
        roll_match = re.search(r"ROLL\s*([A-Z]_?0*\d+)", cleaned, re.IGNORECASE)
        if roll_match:
            current_roll = normalize_camera_roll(roll_match.group(1))

        # 2. Match Scene / Setup header: 27/7 Lens(...) FPS24fps ISO800EI
        scene_match = re.search(r"^(\d+[A-Z]?/\d+)", cleaned)
        if scene_match:
            current_slate = normalize_slate(scene_match.group(1))

            # Extract Lens
            lens_match = re.search(r"Lens\((.*?)\)", cleaned)
            if lens_match:
                current_lens = lens_match.group(1)

            # Extract FPS
            fps_match = re.search(r"FPS\s*(\d+(?:\.\d+)?)fps", cleaned, re.IGNORECASE)
            if fps_match:
                current_fps = float(fps_match.group(1))

            # Extract ISO
            iso_match = re.search(r"ISO\s*(\d+)", cleaned, re.IGNORECASE)
            if iso_match:
                current_iso = int(iso_match.group(1))
            continue

        # 3. Match Take + Clip line (e.g. '1 001' or '2PK 002' or '3* 003')
        take_match = re.match(r"^(\d+[A-Z*]?|\bFALSE\b)\s+(\d{3,4})$", cleaned)
        if take_match and current_slate and current_roll:
            raw_take = take_match.group(1)
            clip_num = int(take_match.group(2))
            take_info = normalize_take(raw_take)

            # Construct canonical clip name (e.g. A120_C001)
            clip_name = f"{current_roll}_C{clip_num:03d}"

            records.append(
                ParsedCameraRecord(
                    slate=current_slate,
                    take_id=take_info.take_id,
                    camera_roll=current_roll,
                    clip_name=clip_name,
                    timecode_in=None,
                    timecode_out=None,
                    fps=current_fps,
                    lens=current_lens,
                    iso=current_iso,
                    is_starred=take_info.is_starred,
                    is_pickup=take_info.is_pickup,
                    is_false_start=take_info.is_false_start,
                    is_vfx=take_info.is_vfx,
                    note=take_info.note,
                )
            )

    if not records:
        raise ParserFailureError("ZoeLog parser yielded zero valid records")

    return records


def parse_editors_log_text(text: str) -> List[ParsedSoundRecord]:
    """
    Parses Script Supervisor Editor's Log text into sound/editorial records.
    """
    if not text or not text.strip():
        raise ParserFailureError("Empty Editor's Log text")

    records: List[ParsedSoundRecord] = []
    lines = text.strip().splitlines()

    for line in lines:
        cleaned = line.strip()
        if not cleaned or "DAILY EDITOR'S LOG" in cleaned or "Slate Take #" in cleaned:
            continue

        # Pattern: Slate Take (Description)? CR (SR)? Time (Comments)?
        # e.g. 27/7 1 LEAD plays -> He sees SUPPORT A120 280726 2:46 1
        # e.g. 27/7 2 A120 2:53 THIS TAKE IS NOT GOOD 1
        m = re.search(r"^(\d+[A-Z]?/\d+)\s+(\d+[A-Z*]?)\s*(.*?)\s*([A-Z]\d{3})\s*(\d{4,8})?\s*(\d+:\d+)?\s*(.*)$", cleaned)
        if m:
            raw_slate = m.group(1)
            raw_take = m.group(2)
            desc = m.group(3).strip() if m.group(3) else None
            cr = normalize_camera_roll(m.group(4))
            sr = normalize_sound_roll(m.group(5)) if m.group(5) else None
            comments = m.group(7).strip() if m.group(7) else None

            norm_slate = normalize_slate(raw_slate)
            take_info = normalize_take(raw_take)
            scene = norm_slate.split("/")[0] if norm_slate and "/" in norm_slate else norm_slate

            records.append(
                ParsedSoundRecord(
                    scene=scene,
                    slate=norm_slate,
                    take_id=take_info.take_id,
                    sound_roll=sr,
                    camera_roll=cr,
                    timecode_in=None,
                    timecode_out=None,
                    is_starred=take_info.is_starred,
                    is_pickup=take_info.is_pickup,
                    note=comments or desc,
                    raw_payload={"camera_roll": cr, "description": desc},
                )
            )

    if not records:
        raise ParserFailureError("Editor's Log parser yielded zero valid records")

    return records


def parse_silverstack_volume_text(text: str) -> List[ParsedSilverstackClip]:
    """
    Parses Silverstack volume report text into media existence clips.
    """
    if not text or not text.strip():
        raise ParserFailureError("Empty Silverstack Volume text")

    clips: List[ParsedSilverstackClip] = []
    lines = text.strip().splitlines()

    current_file = None

    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue

        # 1. Match Filename (e.g. 128-1T01.WAV or A120_C001_260728.MOV)
        file_match = re.match(r"^([A-Za-z0-9_\-]+\.(?:WAV|MOV|BRAW|ARI|MP4|MXF))$", cleaned, re.IGNORECASE)
        if file_match:
            current_file = file_match.group(1)
            continue

        # 2. Match Checksum + Size line: XXH64:1b742d797173f0d4 60.49 MB
        hash_match = re.search(r"([A-Za-z0-9]+):([a-f0-9]+)\s+([\d.]+)\s+(MB|GB|KB|Bytes)", cleaned, re.IGNORECASE)
        if hash_match and current_file:
            hash_type = hash_match.group(1).upper()
            checksum = hash_match.group(2)
            size_val = float(hash_match.group(3))
            unit = hash_match.group(4).upper()

            # Convert to bytes
            if unit == "GB":
                size_bytes = int(size_val * 1024 * 1024 * 1024)
            elif unit == "MB":
                size_bytes = int(size_val * 1024 * 1024)
            elif unit == "KB":
                size_bytes = int(size_val * 1024)
            else:
                size_bytes = int(size_val)

            clips.append(
                ParsedSilverstackClip(
                    file_name=current_file,
                    camera_roll=None,
                    file_size_bytes=size_bytes,
                    checksum=checksum,
                    checksum_type=hash_type,
                )
            )
            current_file = None

    if not clips:
        raise ParserFailureError("Silverstack Volume text parser yielded zero valid records")

    return clips
