"""
Deterministic Parsers for Real Production PDF Reports (ZoeLog Camera, Scripte Editor/TC Logs, Silverstack Volume).

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
    Parses ZoeLog camera report text (e.g. DemoProduction-2026-7-28_CAM_A.pdf) into normalized camera records.
    Captures roll, magazine, camera model, clip name, lens, stop, FPS, shutter, ISO, VFX, and technical notes.
    """
    if not text or not text.strip():
        raise ParserFailureError("Empty ZoeLog text")

    records: List[ParsedCameraRecord] = []
    lines = text.strip().splitlines()

    current_roll = None
    current_camera = "Arri Alexa 35"
    current_mag = None
    current_slate = None
    current_lens = None
    current_stop = None
    current_fps = 24.0
    current_iso = 800
    current_shutter = "172.8"
    current_notes = None

    for line in lines:
        cleaned = line.strip()
        if (
            not cleaned
            or "La DemoProduction Camera Report" in cleaned
            or "Generated using ZoeLog" in cleaned
            or "zoelog.io" in cleaned
            or "Page " in cleaned
            or "SCENE TAKE CLIP" in cleaned
            or "Continued on next page" in cleaned
        ):
            continue

        # 1. Match Roll / Camera / Magazine header
        # e.g.: ROLLA120 DATE28 Jul 2026 CAMERAArri Alexa 35 MAGAZINE #5 or ROLL B039
        roll_m = re.search(r"ROLL\s*([A-Z]\d{3})", cleaned)
        if roll_m:
            current_roll = normalize_camera_roll(roll_m.group(1))
            mag_m = re.search(r"MAGAZINE\s*(#[A-Za-z0-9]+)", cleaned)
            if mag_m:
                current_mag = mag_m.group(1)
            cam_m = re.search(r"CAMERA\s*([A-Za-z0-9 ]+?)(?:MAGAZINE|$)", cleaned)
            if cam_m:
                current_camera = cam_m.group(1).strip()
            continue

        # 2. Match Scene / Setup Header
        # e.g.: 27/7 Lens(Cooke Anamorphic/i 50mm) StopF2 7/10 Color Temp6000K FPS24fps
        # or: 27/7 Lens65mmStopT2.8?Color Temp6000KFPS24fpsShutter172.8?ISO800EI1 001
        scene_m = re.search(r"^(\d+[A-Z]?/\d+)", cleaned)
        if scene_m:
            current_slate = normalize_slate(scene_m.group(1))
            current_notes = None

            # Extract Lens
            lens_m = re.search(r"Lens(?:\((.*?)\)|([0-9A-Za-z/ ]+?)(?:Stop|Filters|Color|FPS|$))", cleaned)
            if lens_m:
                current_lens = (lens_m.group(1) or lens_m.group(2) or "").strip()

            # Extract Stop
            stop_m = re.search(r"Stop([A-Za-z0-9 ./?]+?)(?:Color|FPS|Shutter|Filters|$)", cleaned)
            if stop_m:
                current_stop = stop_m.group(1).strip().replace("?", "")

            # Extract FPS
            fps_m = re.search(r"FPS\s*(\d+(?:\.\d+)?)fps", cleaned, re.IGNORECASE)
            if fps_m:
                current_fps = float(fps_m.group(1))

            # Extract ISO
            iso_m = re.search(r"ISO\s*(\d+)", cleaned, re.IGNORECASE)
            if iso_m:
                current_iso = int(iso_m.group(1))

            # Extract Shutter
            shutter_m = re.search(r"Shutter([0-9.]+)", cleaned)
            if shutter_m:
                current_shutter = shutter_m.group(1)

            # Check for inline trailing take (e.g. ISO800EI1 001)
            inline_take = re.search(r"(?:EI|ISO\d+)(\d+[A-Z*]?|FC|FALSE)\s+(\d{3,4})$", cleaned)
            if inline_take and current_roll and current_slate:
                raw_take = inline_take.group(1)
                clip_num = int(inline_take.group(2))
                take_info = normalize_take(raw_take)
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
                        shutter=current_shutter,
                        is_starred=take_info.is_starred,
                        is_pickup=take_info.is_pickup,
                        is_false_start=take_info.is_false_start or raw_take in ["FC", "FALSE"],
                        is_vfx="VFX" in cleaned.upper(),
                        note=take_info.note,
                        raw_payload={"magazine": current_mag, "camera": current_camera, "stop": current_stop},
                    )
                )
            continue

        # 3. Notes line (Header or Take note)
        if "Notes" in cleaned:
            extracted_note = cleaned[cleaned.find("Notes") + 5 :].strip()
            current_notes = extracted_note
            continue

        # 4. Standard Take line (e.g. '1 001' or '2PK 002' or 'FC 004')
        take_m = re.match(r"^(\d+[A-Z*]?|FC|FALSE)\s+(\d{3,4})$", cleaned)
        if take_m and current_slate and current_roll:
            raw_take = take_m.group(1)
            clip_num = int(take_m.group(2))
            take_info = normalize_take(raw_take)
            clip_name = f"{current_roll}_C{clip_num:03d}"

            # Check if VFX applies to this specific take
            take_is_vfx = take_info.is_vfx
            if current_notes and "VFX" in current_notes.upper():
                # Check for explicit take restrictions (e.g. 'VFX EN TOMAS 3 y 4')
                tomas_m = re.search(r"tomas?\s*([\d\s,yeANDand]+)", current_notes, re.IGNORECASE)
                if tomas_m:
                    vfx_take_nums = re.findall(r"\d+", tomas_m.group(1))
                    take_is_vfx = take_info.take_id in vfx_take_nums
                else:
                    # Generic VFX note for this setup block (e.g. CAM_A/CAM_C setup 2 for 117/1)
                    take_is_vfx = True

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
                    shutter=current_shutter,
                    is_starred=take_info.is_starred,
                    is_pickup=take_info.is_pickup,
                    is_false_start=take_info.is_false_start or raw_take in ["FC", "FALSE"],
                    is_vfx=take_is_vfx,
                    note=current_notes or take_info.note,
                    raw_payload={"magazine": current_mag, "camera": current_camera, "stop": current_stop},
                )
            )

    if not records:
        raise ParserFailureError("ZoeLog parser yielded zero valid records")

    return records


def parse_scripte_tclog_text(text: str) -> List[ParsedSoundRecord]:
    """
    Parses Scripte Daily Timecode Log text (e.g. DEMO_TCLog_D031_280726.pdf) using state machine.
    """
    if not text or not text.strip():
        raise ParserFailureError("Empty Scripte TCLog text")

    records: List[ParsedSoundRecord] = []
    lines = text.strip().splitlines()

    current_slate = None
    current_take = None
    current_tc_in = None
    current_tc_out = None
    current_notes: List[str] = []

    for line in lines:
        cleaned = line.strip()
        if not cleaned or "DAILY TIMECODE LOG" in cleaned or "Date:" in cleaned or "Page " in cleaned:
            continue

        # 1. Check for single-line format: 27/7 1 09:26:12:04 ... A120 280726 2:46
        single_m = re.search(
            r"^(\d+[A-Z]?/\d+|\d+WT)\s+(\d+[A-Z*]?|FALSE)\s+(\d{2}:\d{2}:\d{2}:\d{2})\s*(?:\d{2}:\d{2}:\d{2})?\s*(\d{2}:\d{2}:\d{2}:\d{2})?.*?\b([A-Z]\d{3})\s*(\d{6})?",
            cleaned,
        )
        if single_m:
            raw_slate = single_m.group(1)
            raw_take = single_m.group(2)
            tc_in = single_m.group(3)
            tc_out = single_m.group(4)
            cr = normalize_camera_roll(single_m.group(5))
            sr = normalize_sound_roll(single_m.group(6)) if single_m.group(6) else None

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
                    timecode_in=tc_in,
                    timecode_out=tc_out,
                    is_starred=take_info.is_starred,
                    is_pickup=take_info.is_pickup,
                    is_false_start=take_info.is_false_start,
                    is_wild_track="WT" in current_slate.upper() if current_slate else take_info.is_wild_track,
                    is_vfx="VFX" in cleaned.upper() or take_info.is_vfx,
                    note=take_info.note,
                    raw_payload={"camera_roll": cr, "timecode_in": tc_in, "timecode_out": tc_out},
                )
            )
            continue

        # 2. Multi-line Header line matching Slate, Take, and TC In: 27/7 109:26:12:04 or 27/7 1 09:26:12:04
        header_m = re.search(r"^(\d+[A-Z]?/\d+|\d+WT)\s+(\d+[A-Z*]?|FALSE)(?:(?=\d{2}:\d{2}:\d{2})|\s+)(\d{2}:\d{2}:\d{2}:\d{2})?", cleaned)
        if header_m:
            current_slate = header_m.group(1)
            current_take = header_m.group(2)
            current_tc_in = header_m.group(3)
            current_tc_out = None
            current_notes = []
            continue

        # 3. Timecode out line: 09:28:58:12
        tc_m = re.match(r"^(\d{2}:\d{2}:\d{2}:\d{2})$", cleaned)
        if tc_m and current_tc_in and not current_tc_out:
            current_tc_out = tc_m.group(1)
            continue

        # 4. Camera Roll & Sound Roll line: A1202807262:461 or B0392807262:462 or A120 280726 2:46 1
        roll_m = re.search(r"\b([A-Z]\d{3})\s*(\d{6})?(?:\s*\d+:\d+)?", cleaned)
        if roll_m and current_slate and current_take:
            cr = normalize_camera_roll(roll_m.group(1))
            sr = normalize_sound_roll(roll_m.group(2)) if roll_m.group(2) else None

            norm_slate = normalize_slate(current_slate)
            take_info = normalize_take(current_take)
            scene = norm_slate.split("/")[0] if norm_slate and "/" in norm_slate else norm_slate
            notes_str = " ".join(current_notes).strip() or None

            records.append(
                ParsedSoundRecord(
                    scene=scene,
                    slate=norm_slate,
                    take_id=take_info.take_id,
                    sound_roll=sr,
                    camera_roll=cr,
                    timecode_in=current_tc_in,
                    timecode_out=current_tc_out,
                    is_starred=take_info.is_starred,
                    is_pickup=take_info.is_pickup,
                    is_false_start=take_info.is_false_start,
                    is_wild_track="WT" in current_slate.upper() or take_info.is_wild_track,
                    is_vfx="VFX" in (notes_str or "").upper() or take_info.is_vfx,
                    note=notes_str or take_info.note,
                    raw_payload={"camera_roll": cr, "timecode_in": current_tc_in, "timecode_out": current_tc_out},
                )
            )
            continue

        # Accumulate descriptions and comments
        if records and not cleaned.startswith("Lens:") and not cleaned.startswith("Script /"):
            prev_note = records[-1].note or ""
            records[-1].note = f"{prev_note} {cleaned}".strip()
            continue

        if current_slate and not cleaned.startswith("Lens:") and not cleaned.startswith("Script /"):
            current_notes.append(cleaned)

    if not records:
        # Fallback to general editor log parser
        return parse_editors_log_text(text)

    return records


def parse_scripte_detailed_editor_log_text(text: str) -> List[ParsedSoundRecord]:
    """
    Parses Scripte Detailed Editor's Log text (e.g. DEMO_DetailedEditor’sLog_D031_280726.pdf).
    Captures multi-camera cards, WildTrack (WT) tags, and VFX markers.
    """
    if not text or not text.strip():
        raise ParserFailureError("Empty Scripte Detailed Editor's Log text")

    records: List[ParsedSoundRecord] = []
    lines = text.strip().splitlines()

    current_slate = None
    current_take = None
    current_notes: List[str] = []

    for line in lines:
        cleaned = line.strip()
        if not cleaned or "DETAILED EDITOR'S LOG" in cleaned or "Date:" in cleaned or "Slate TakeDescription" in cleaned:
            continue

        # 1. Wild Track entries: 6WT 1 Scene(s): 6, 49 Wild Track: 6WT n/a2807260:29 pasos de LEAD
        wt_m = re.search(r"(\d+WT)\s+(\d+[A-Z*]?)\s+.*?(?:Wild Track:)?\s*.*?(?:n/a)?\s*(\d{6})?\s*(\d+:\d+)?\s*(.*)", cleaned, re.IGNORECASE)
        if wt_m and "WT" in cleaned.upper():
            raw_slate = wt_m.group(1)
            raw_take = wt_m.group(2)
            sr = normalize_sound_roll(wt_m.group(3)) if wt_m.group(3) else None
            comments = wt_m.group(5).strip() if wt_m.group(5) else "Wild Track"

            records.append(
                ParsedSoundRecord(
                    scene=raw_slate,
                    slate=raw_slate,
                    take_id=raw_take,
                    sound_roll=sr,
                    camera_roll=None,
                    timecode_in=None,
                    timecode_out=None,
                    is_starred=False,
                    is_pickup=False,
                    is_wild_track=True,
                    is_vfx=False,
                    note=comments,
                    raw_payload={"type": "wild_track", "comments": comments},
                )
            )
            continue

        # 2. Main Slate + Take header (e.g. '27/7 1 Scene(s): 27' or '49/1 1 Scene(s): 49')
        new_slate_m = re.search(r"^(\d+[A-Z]?/\d+|\d+WT)\s+(\d+[A-Z*]?|FALSE)\s*(.*)", cleaned)
        if new_slate_m:
            current_slate = new_slate_m.group(1)
            current_take = new_slate_m.group(2)
            rest = new_slate_m.group(3)
            current_notes = [rest] if rest else []

            # Check if camera roll is on this same line: A1202807262:46
            roll_m = re.search(r"\b([A-Z]\d{3})\s*(\d{6})?", rest)
            if roll_m:
                cr = normalize_camera_roll(roll_m.group(1))
                sr = normalize_sound_roll(roll_m.group(2)) if roll_m.group(2) else None
                norm_slate = normalize_slate(current_slate)
                take_info = normalize_take(current_take)
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
                        is_wild_track="WT" in current_slate.upper() or take_info.is_wild_track,
                        is_vfx="VFX" in cleaned.upper() or take_info.is_vfx,
                        note=rest or take_info.note,
                        raw_payload={"camera_roll": cr, "is_vfx": "VFX" in cleaned.upper()},
                    )
                )
            continue

        # 3. Subsequent take or multi-camera setup angle: '1 Dolly - wide... B039 2:46' or '2 A120 2:53'
        sub_m = re.search(r"^(\d+[A-Z*]?|FALSE)\s+(.*)", cleaned)
        if sub_m and current_slate:
            current_take = sub_m.group(1)
            rest = sub_m.group(2)
            roll_m = re.search(r"\b([A-Z]\d{3})\s*(\d{6})?", rest)
            if roll_m:
                cr = normalize_camera_roll(roll_m.group(1))
                sr = normalize_sound_roll(roll_m.group(2)) if roll_m.group(2) else None
                norm_slate = normalize_slate(current_slate)
                take_info = normalize_take(current_take)
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
                        is_wild_track="WT" in current_slate.upper() or take_info.is_wild_track,
                        is_vfx="VFX" in cleaned.upper() or take_info.is_vfx,
                        note=rest or take_info.note,
                        raw_payload={"camera_roll": cr, "is_vfx": "VFX" in cleaned.upper()},
                    )
                )
            continue

        # 4. Standalone roll line for current setup (e.g. 'A1202807262:46' after a multi-line description)
        roll_standalone = re.search(r"\b([A-Z]\d{3})\s*(\d{6})?", cleaned)
        if roll_standalone and current_slate and current_take:
            cr = normalize_camera_roll(roll_standalone.group(1))
            sr = normalize_sound_roll(roll_standalone.group(2)) if roll_standalone.group(2) else None
            norm_slate = normalize_slate(current_slate)
            take_info = normalize_take(current_take)
            scene = norm_slate.split("/")[0] if norm_slate and "/" in norm_slate else norm_slate
            notes_str = " ".join(current_notes).strip() or cleaned
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
                    is_wild_track="WT" in current_slate.upper() or take_info.is_wild_track,
                    is_vfx="VFX" in cleaned.upper() or "VFX" in notes_str.upper() or take_info.is_vfx,
                    note=notes_str or take_info.note,
                    raw_payload={"camera_roll": cr, "is_vfx": "VFX" in cleaned.upper()},
                )
            )
            continue

        if current_slate and not cleaned.startswith("Script /") and not cleaned.startswith("Date:"):
            current_notes.append(cleaned)

    if not records:
        return parse_editors_log_text(text)

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
                    is_vfx=take_info.is_vfx or "VFX" in cleaned.upper(),
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

        file_match = re.match(r"^([A-Za-z0-9_\-]+\.(?:WAV|MOV|BRAW|ARI|MP4|MXF))$", cleaned, re.IGNORECASE)
        if file_match:
            current_file = file_match.group(1)
            continue

        hash_match = re.search(r"([A-Za-z0-9]+):([a-f0-9]+)\s+([\d.]+)\s+(MB|GB|KB|Bytes)", cleaned, re.IGNORECASE)
        if hash_match and current_file:
            hash_type = hash_match.group(1).upper()
            checksum = hash_match.group(2)
            size_val = float(hash_match.group(3))
            unit = hash_match.group(4).upper()

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
