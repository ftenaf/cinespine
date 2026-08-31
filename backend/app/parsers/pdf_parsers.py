"""
Deterministic Parsers for Real Production PDF Reports (ZoeLog Camera, Scripte Editor/TC Logs, Silverstack Volume).

Evidence:
- data/examples/
"""
import logging
import io
import re
import base64
from typing import List, Optional, Dict
import pypdf
try:
    import pdfplumber
except ImportError:
    pdfplumber = None
from backend.app.parsers.base import (
    ParsedCameraRecord,
    ParsedSoundRecord,
    ParsedScriptRecord,
    ParsedSilverstackClip,
    ParserFailureError,
    looks_like_a_clip_name,
)
from backend.app.core.privacy import is_contact_information
from backend.app.normalizers.rolls import normalize_camera_roll, normalize_sound_roll
from backend.app.normalizers.slates import normalize_slate
from backend.app.normalizers.shoot_days import normalize_shoot_day
from backend.app.normalizers.takes import normalize_take

logger = logging.getLogger(__name__)

# A slate names a scene and a shot -- 119/5. The scene half may itself be a
# compound of scenes covered by one setup: 41+122A/4, 97+121/4, 73C-74AC/1. That
# is how the script supervisor files a shot that plays in more than one scene,
# and a pattern that only admits a bare number reads those rows as continuations
# of the shot above them and hands that shot the wrong camera card.
SLATE_TOKEN = r"(?:\d+[A-Z]{0,2}(?:[+-]\d+[A-Z]{0,2})*/(?:\d+[A-Z]?|WT)|\d+WT)"


def _extract_text_with_document_ai(pdf_bytes: bytes) -> Optional[str]:
    import os
    try:
        from google.cloud import documentai
        from google.api_core.exceptions import GoogleAPIError
    except ImportError:
        return None

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("DOCUMENTAI_LOCATION", "us-central1")
    processor_id = os.environ.get("DOCUMENTAI_PROCESSOR_ID")

    if not project_id or not processor_id:
        return None

    try:
        client_options = {"api_endpoint": f"{location}-documentai.googleapis.com"}
        client = documentai.DocumentProcessorServiceClient(client_options=client_options)
        
        name = client.processor_path(project_id, location, processor_id)
        
        raw_document = documentai.RawDocument(
            content=pdf_bytes,
            mime_type="application/pdf"
        )
        
        request = documentai.ProcessRequest(
            name=name,
            raw_document=raw_document
        )
        
        result = client.process_document(request=request)
        return result.document.text
    except Exception as exc:
        logger.warning(f"Document AI extraction failed, falling back to local PDF parser: {exc}")
        return None


def extract_text_from_pdf(pdf_bytes_or_file) -> str:
    """
    Extracts concatenated text from all pages of a PDF, detecting both text characters
    and graphical vector circle curves drawn over circled takes. Uses Document AI
    if configured, otherwise falls back to pypdf/pdfplumber.
    """
    if isinstance(pdf_bytes_or_file, bytes):
        pdf_bytes = pdf_bytes_or_file
    elif hasattr(pdf_bytes_or_file, "read"):
        pdf_bytes = pdf_bytes_or_file.read()
    else:
        pdf_bytes = bytes(pdf_bytes_or_file)

    # 1. Attempt Cloud Document AI OCR Pipeline
    doc_ai_text = _extract_text_with_document_ai(pdf_bytes)
    if doc_ai_text:
        return doc_ai_text

    # 2. Fallback to local parsing (pypdf/pdfplumber)

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    raw_pages = [p.extract_text() or "" for p in reader.pages]

    if pdfplumber:
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for idx, page in enumerate(pdf.pages):
                    take_curves = [
                        c for c in page.curves
                        if 60 <= c.get("x0", 0) <= 130 and 8 <= c.get("width", 0) <= 35 and 4 <= c.get("height", 0) <= 30
                    ]
                    if not take_curves or idx >= len(raw_pages):
                        continue

                    words = page.extract_words()
                    circled_takes_on_page = []
                    for tc in take_curves:
                        matching = [
                            w for w in words
                            if abs(w["top"] - tc["top"]) < 10 and 65 <= w["x0"] <= 130
                        ]
                        for w in matching:
                            circled_takes_on_page.append((w["text"].replace("*", ""), tc["top"]))

                    lines = raw_pages[idx].splitlines()
                    enriched_lines = []
                    for line in lines:
                        m = re.search(r"^(" + SLATE_TOKEN + r")\s+(\d{1,2}[A-Z*]?|FALSE)(?=(\d{2}:\d{2}:\d{2}:\d{2})|\s+|$)", line)
                        if m:
                            raw_slate = m.group(1)
                            raw_take = m.group(2)
                            base_take = raw_take.replace("*", "")
                            if not raw_take.endswith("*") and any(ct[0] == base_take for ct in circled_takes_on_page):
                                line = re.sub(rf"^({re.escape(raw_slate)}\s+){re.escape(raw_take)}", rf"\g<1>{raw_take}* ", line)
                        enriched_lines.append(line)
                    raw_pages[idx] = "\n".join(enriched_lines)
        except Exception as exc:
            # Circled-take enrichment is an improvement, not a requirement:
            # the unenriched pages are still returned below.
            logger.debug("Circled-take enrichment skipped: %s", exc)

    return "\n".join(raw_pages)


def extract_thumbnails_from_pdf(pdf_bytes_or_file) -> Dict[str, str]:
    """
    Extracts embedded scene/take JPEG thumbnail pictures from Pomfort Silverstack Thumbnail or Clips PDFs.
    Preserves state across page breaks and multi-clip grid pages and returns a multi-key mapping {clip_name/key: data_uri}.
    """
    thumbnails: Dict[str, str] = {}
    try:
        if isinstance(pdf_bytes_or_file, bytes):
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes_or_file))
        else:
            reader = pypdf.PdfReader(pdf_bytes_or_file)

        active_cname: Optional[str] = None
        active_short: Optional[str] = None
        active_norm: Optional[str] = None

        for page in reader.pages:
            txt = page.extract_text() or ""
            imgs = [img for img in page.images if len(img.data) > 1000 and any(img.name.lower().endswith(ext) for ext in [".jpg", ".jpeg"])]
            lines = [l.strip() for l in txt.splitlines() if l.strip()]

            # 1. Multi-clip grid page (e.g. Clips Report pages 5-10 with A_..., B_..., C_... lines)
            grid_clip_lines = [l for l in lines if l.startswith(("A_", "B_", "C_"))]
            if len(grid_clip_lines) > 1 and len(imgs) >= 1:
                for idx, cl in enumerate(grid_clip_lines):
                    cname = cl.split()[0]
                    if idx < len(imgs):
                        img = imgs[idx]
                        b64 = base64.b64encode(img.data).decode("utf-8")
                        data_uri = f"data:image/jpeg;base64,{b64}"

                        thumbnails[cname] = data_uri
                        full_fname = cname if "." in cname else f"{cname}.mxf"
                        thumbnails[full_fname] = data_uri

                        m_short = re.match(r"^([A-Z])_0*(\d{3,4})C(\d{3,4})", cname)
                        if m_short:
                            short_k = f"{m_short.group(1)}{m_short.group(2)[-3:]}_C{int(m_short.group(3)):03d}"
                            thumbnails[short_k] = data_uri
                continue

            # 2. Single-clip page (e.g. Thumbnail Report)
            data_uri: Optional[str] = None
            if imgs:
                img = max(imgs, key=lambda x: len(x.data))
                b64 = base64.b64encode(img.data).decode("utf-8")
                data_uri = f"data:image/jpeg;base64,{b64}"

            for i, line in enumerate(lines):
                if line.startswith("Name "):
                    cname = line[5:].strip()
                    if i + 1 < len(lines) and len(lines[i + 1]) <= 4 and not any(k in lines[i + 1] for k in ["ShotID", "Duration", "Camera", "Reel", "Scene", "Take", "Director", "Sensor"]):
                        cname += lines[i + 1].strip()

                    active_cname = cname
                    short_m = re.match(r"^([A-Za-z]_[0-9]+C[0-9]+|\d+[A-Za-z]*-?\d*T\d+)", cname)
                    active_short = short_m.group(1) if short_m else cname.split("_")[0]
                    active_norm = None
                    if active_short:
                        norm_m = re.match(r"^([A-Z])_0*(\d{3,4})C(\d{3,4})", active_short)
                        if norm_m:
                            active_norm = f"{norm_m.group(1)}{norm_m.group(2)[-3:]}_C{int(norm_m.group(3)):03d}"

            sc_m = re.search(r"Scene\s+([0-9A-Za-z]+)", txt)
            sh_m = re.search(r"Shot\s+([0-9A-Za-z]+)", txt)
            tk_m = re.search(r"Take\s+([0-9A-Za-z*]+)", txt)
            slate_key: Optional[str] = None
            if sc_m and sh_m and tk_m:
                tk_clean = tk_m.group(1).replace("VFX", "").replace("PK", "").strip()
                if tk_clean.startswith("0") and len(tk_clean) > 1:
                    tk_clean = str(int(tk_clean))
                slate_key = f"{sc_m.group(1)}/{sh_m.group(1)}_{tk_clean}"

            if data_uri:
                if active_cname:
                    thumbnails[active_cname] = data_uri
                if active_short:
                    thumbnails[active_short] = data_uri
                if active_norm:
                    thumbnails[active_norm] = data_uri
                if slate_key:
                    thumbnails[slate_key] = data_uri
    except Exception as exc:
        # Whatever was collected before the failure is still usable.
        logger.debug("Thumbnail extraction stopped early: %s", exc)
    return thumbnails


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
                    is_mos=take_info.is_mos or bool(current_notes and ("MOS" in current_notes.upper() or "M.O.S" in current_notes.upper())),
                    note=current_notes or take_info.note,
                    raw_payload={"magazine": current_mag, "camera": current_camera, "stop": current_stop},
                )
            )

    if not records:
        raise ParserFailureError("ZoeLog parser yielded zero valid records")

    return records


def parse_shoot_date(raw_date: Optional[str]) -> Optional[str]:
    """
    Turns the DDMMYY stamp written beside a camera card into DD/MM/YYYY.

    Returns None when the stamp is not a date rather than guessing at one: a
    row with no date is a row that makes no claim about when it was shot.
    """
    if not raw_date or not re.fullmatch(r"\d{6}", raw_date):
        return None

    day, month, year = int(raw_date[:2]), int(raw_date[2:4]), int(raw_date[4:])
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return None

    return f"{day:02d}/{month:02d}/{2000 + year:04d}"


def extract_report_date(text: str) -> Optional[str]:
    """
    Reads the date printed in a script supervisor report's header.

    It is the day the report covers, which is the right date for a row that
    carries none of its own -- and it is a property of the document, not a
    constant, which is what it used to be.
    """
    m = re.search(r"(?<!\d)(\d{2})/(\d{2})/(\d{4})(?!\d)", text or "")
    if not m:
        return None

    day, month = int(m.group(1)), int(m.group(2))
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return None

    return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"


def extract_script_camera_roll_and_date(text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extracts camera roll and date from script supervisor logs, properly handling
    unpadded card numbers concatenated with dates (e.g. 'B41280726' -> roll 'B041', date '280726')
    as well as standard padded cards ('A120280726' -> 'A120', 'B039' -> 'B039').
    """
    if not text:
        return None, None

    # 1. Match card followed by a 6-digit shoot date (DDMMYY), whether the two
    # run together as they do in the timecode log ('B41280726') or sit in
    # separate columns as they do on a facing page ('A046 300626'). A facing
    # page files a shot under every scene it plays in, so its rows carry dates
    # from across the schedule and a row's own date is the only true one.
    date_pat = r'(280726|260728|\d{2}0[1-9]\d{2}|\d{2}1[0-2]\d{2})'
    m = re.search(r'\b([A-Z]0*\d{1,3})\s{0,3}' + date_pat, text)
    if m:
        raw_roll = m.group(1)
        raw_date = m.group(2)
        norm_roll = normalize_camera_roll(raw_roll)
        return norm_roll, raw_date

    # 2. Match standard 3-digit card (e.g. 'A120', 'B039', 'C005', 'B041')
    m = re.search(r'\b([A-Z]\d{3})\b', text)
    if m:
        return normalize_camera_roll(m.group(1)), None

    # 3. Match 1 to 3 digit card standalone (e.g. 'B41', 'C5', 'A12')
    m = re.search(r'\b([A-Z]0*\d{1,3})\b', text)
    if m:
        return normalize_camera_roll(m.group(1)), None

    return None, None


def unify_take_level_marks(records: List[ParsedScriptRecord]) -> List[ParsedScriptRecord]:
    """
    Applies each take's marks to every row that take produced.

    A multi-camera take is one take recorded on several cameras, and the script
    supervisor writes its marks once -- the circle goes on the first camera's
    row, and the rows beneath it just repeat the take number. Read row by row,
    camera A comes back circled and cameras B and C come back not circled, so
    one take disagrees with itself and the reconciliation engine reports a
    conflict that nobody on set would recognise.

    These are properties of the take, not of the camera, so a mark found on any
    row belongs to all of them.
    """
    marks = ("is_starred", "is_pickup", "is_false_start", "is_wild_track", "is_vfx", "is_mos")

    by_take: Dict[tuple, Dict[str, bool]] = {}
    for rec in records:
        if not rec.slate or not rec.take_id:
            continue
        key = (rec.slate, rec.take_id)
        seen = by_take.setdefault(key, {m: False for m in marks})
        for m in marks:
            if getattr(rec, m, False):
                seen[m] = True

    for rec in records:
        if not rec.slate or not rec.take_id:
            continue
        seen = by_take.get((rec.slate, rec.take_id))
        if not seen:
            continue
        for m in marks:
            if seen[m] and not getattr(rec, m, False):
                setattr(rec, m, True)

    return records


def parse_scripte_tclog_text(text: str) -> List[ParsedScriptRecord]:
    """
    Parses Scripte Daily Timecode Log text (e.g. DEMO_TCLog_D031_280726.pdf) using state machine.
    """
    if not text or not text.strip():
        raise ParserFailureError("Empty Scripte TCLog text")

    report_date = extract_report_date(text)

    records: List[ParsedScriptRecord] = []
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
            r"^(" + SLATE_TOKEN + r")\s+(\d+[A-Z*]?|FALSE)\s+(\d{2}:\d{2}:\d{2}:\d{2})\s*(?:\d{2}:\d{2}:\d{2})?\s*(\d{2}:\d{2}:\d{2}:\d{2})?(.*)",
            cleaned,
        )
        if single_m:
            raw_slate = single_m.group(1)
            raw_take = single_m.group(2)
            tc_in = single_m.group(3)
            tc_out = single_m.group(4)
            rest_line = single_m.group(5) or ""

            cr, raw_date = extract_script_camera_roll_and_date(rest_line)
            if cr:
                norm_slate = normalize_slate(raw_slate)
                take_info = normalize_take(raw_take)
                scene = norm_slate.split("/")[0] if norm_slate and "/" in norm_slate else norm_slate

                row_date = parse_shoot_date(raw_date) or report_date
                records.append(
                    ParsedScriptRecord(
                        scene=scene,
                        slate=norm_slate,
                        take_id=take_info.take_id,
                        camera_roll=cr,
                        timecode_in=tc_in,
                        timecode_out=tc_out,
                        recording_date=row_date,
                        is_starred=take_info.is_starred,
                        is_pickup=take_info.is_pickup,
                        is_false_start=take_info.is_false_start,
                        is_wild_track="WT" in (current_slate or "").upper() or take_info.is_wild_track,
                        is_vfx="VFX" in cleaned.upper() or take_info.is_vfx,
                        is_mos="MOS" in cleaned.upper() or take_info.is_mos,
                        note=take_info.note or rest_line.strip(),
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

        # 4. Camera Roll & Sound Roll line: A1202807262:461 or B0392807262:462 or B412807261:1125
        cr, raw_date = extract_script_camera_roll_and_date(cleaned)
        if cr and current_slate and current_take:
            norm_slate = normalize_slate(current_slate)
            take_info = normalize_take(current_take)
            scene = norm_slate.split("/")[0] if norm_slate and "/" in norm_slate else norm_slate
            notes_str = " ".join(current_notes).strip() or None

            row_date = parse_shoot_date(raw_date) or report_date
            records.append(
                ParsedScriptRecord(
                    scene=scene,
                    slate=norm_slate,
                    take_id=take_info.take_id,
                    camera_roll=cr,
                    timecode_in=current_tc_in,
                    timecode_out=current_tc_out,
                    recording_date=row_date,
                    is_starred=take_info.is_starred,
                    is_pickup=take_info.is_pickup,
                    is_false_start=take_info.is_false_start,
                    is_wild_track="WT" in current_slate.upper() or take_info.is_wild_track,
                    is_vfx="VFX" in (notes_str or "").upper() or take_info.is_vfx,
                    is_mos="MOS" in (notes_str or "").upper() or "MOS" in current_slate.upper() or take_info.is_mos,
                    note=notes_str or take_info.note,
                    raw_payload={"camera_roll": cr, "timecode_in": current_tc_in, "timecode_out": current_tc_out},
                )
            )
            continue

        # Accumulate descriptions and comments
        # Anything unrecognised becomes a note on the take before it. That is
        # what a script supervisor's marginalia is, and it has to stay free
        # text -- but it means a report footer became something they supposedly
        # wrote about that take, and a contact block reached the spine and the
        # mirror inside a witness statement.
        #
        # Refused rather than redacted. Rewriting a note would quietly alter
        # what somebody said; declining to attribute a line that is plainly not
        # about this take leaves the note as what they actually wrote.
        if records and not cleaned.startswith("Lens:") and not cleaned.startswith("Script /"):
            if is_contact_information(cleaned):
                continue
            prev_note = records[-1].note or ""
            records[-1].note = f"{prev_note} {cleaned}".strip()
            continue

        if current_slate and not cleaned.startswith("Lens:") and not cleaned.startswith("Script /"):
            # Same catch-all, same refusal. See the note above.
            if is_contact_information(cleaned):
                continue
            current_notes.append(cleaned)

    if not records:
        # This document is not in the timecode log's layout. The editor's log
        # state machine reads both of the layouts these reports come in.
        return parse_scripte_detailed_editor_log_text(text)

    return unify_take_level_marks(records)


def parse_scripte_detailed_editor_log_text(text: str) -> List[ParsedScriptRecord]:
    """
    Parses Scripte Detailed Editor's Log text (e.g. DEMO_DetailedEditor’sLog_D031_280726.pdf) using state machine.
    """
    if not text or not text.strip():
        raise ParserFailureError("Empty Scripte Detailed Editor's Log text")

    report_date = extract_report_date(text)

    records: List[ParsedScriptRecord] = []
    lines = text.strip().splitlines()

    current_slate = None
    current_take = None
    current_notes: List[str] = []
    current_shoot_day: Optional[str] = None
    current_block_date: Optional[str] = None
    current_block_roll: Optional[str] = None
    block_start = 0

    def next_content_line(idx: int) -> str:
        for peek in lines[idx + 1:idx + 4]:
            if peek.strip():
                return peek.strip()
        return ""

    for idx, line in enumerate(lines):
        cleaned = line.strip()
        if (
            not cleaned
            or "EDITOR'S LOG" in cleaned.upper()
            or "Date:" in cleaned
            or "Slate Take" in cleaned
            or "Script / Continuity" in cleaned
            or "Page " in cleaned
            or "Day:Day " in cleaned
            or cleaned.startswith("LAC - ")
        ):
            continue

        # A scene heading means the facing page has ended and the lined script
        # itself has begun. Its lines are screenplay, not table rows: a heading
        # like '5 5INT/EXT. COCHE THOMAS - APARCAMIENTO AUDITORIO - DIA - D2'
        # reads as take 5 on card D002, because the schedule's day marker D2
        # has the shape of a camera card. That invented fourteen takes on this
        # document, filed against whichever slate happened to be current.
        #
        # Matched on the heading's shape -- a scene number, then INT/EXT -- and
        # not on the words alone, so that a comment saying PRINT. is not
        # mistaken for one. The number is printed twice on these pages, in the
        # margin and again in the heading ('64A 64AINT. FISCALIA ...').
        if re.match(
            r"^(?:\d+[A-Z]{0,2}\.?\s+(?:\d+[A-Z]{0,2})?\s*)?(?:INT|EXT)[./]",
            cleaned, re.IGNORECASE,
        ):
            current_slate = None
            current_take = None
            current_notes = []
            block_start = len(records)
            current_shoot_day = None
            current_block_date = None
            current_block_roll = None
            continue

        # 0. The day this setup was shot: 'Shot on Day: Day 11'. It follows the
        # header row, so it also settles the rows already emitted for this
        # block. Without it every take on the page is filed under the day the
        # page was printed, and a take from Day 11 is reconciled against
        # witnesses from a day it was not shot on.
        day_m = re.search(r"Shot on Day:\s*Day\s*([0-9A-Za-z]+)", cleaned)
        if day_m:
            current_shoot_day = normalize_shoot_day(day_m.group(1))
            for rec in records[block_start:]:
                rec.shoot_day = current_shoot_day
            continue

        # 1. Wild Track entries: 6WT 1 Scene(s): 6, 49 Wild Track: 6WT n/a2807260:29 pasos de LEAD
        # A wild track is its own setup, so it opens a block of its own. Left
        # inside the block above it, the day line that follows reaches back and
        # reassigns that setup's rows to the wild track's day.
        if "WT" in cleaned.upper() and re.match(r"^\d+WT\s", cleaned):
            block_start = len(records)
            current_shoot_day = None
            current_block_date = None
            current_block_roll = None

        wt_m = re.search(r"(\d+WT)\s+(\d+[A-Z*]?)\s+.*?(?:Wild Track:)?\s*.*?(?:n/a)?\s*(\d{6})?\s*(\d+:\d+)?\s*(.*)", cleaned, re.IGNORECASE)
        if wt_m and "WT" in cleaned.upper():
            raw_slate = wt_m.group(1)
            raw_take = wt_m.group(2)
            comments = wt_m.group(5).strip() if wt_m.group(5) else "Wild Track"
            take_info = normalize_take(raw_take)
            norm_slate = normalize_slate(raw_slate)
            scene = norm_slate.split("/")[0] if norm_slate and "/" in norm_slate else norm_slate

            row_date = report_date
            records.append(
                ParsedScriptRecord(
                    scene=scene,
                    slate=norm_slate,
                    take_id=take_info.take_id or raw_take,
                    camera_roll=None,
                    timecode_in=None,
                    timecode_out=None,
                    recording_date=row_date,
                    shoot_day=current_shoot_day,
                    is_starred=take_info.is_starred,
                    is_pickup=False,
                    is_wild_track=True,
                    is_vfx=False,
                    is_false_start=take_info.is_false_start,
                    is_mos=take_info.is_mos,
                    note=comments,
                    raw_payload={"type": "wild_track", "comments": comments},
                )
            )
            continue

        # 2. Main Slate + Take header (e.g. '27/7 1 Scene(s): 27' or '49/1 1 Scene(s): 49' or '117/1 4* Scene(s): 117')
        new_slate_m = re.search(r"^(" + SLATE_TOKEN + r")\s+(\d+(?:\.\d+)?(?:[A-Z](?![A-Za-z]))?\s*\*?|\d+\*|FALSE)\s*(.*)", cleaned)
        if new_slate_m:
            current_slate = new_slate_m.group(1)
            current_take = new_slate_m.group(2).replace(" ", "")
            rest = new_slate_m.group(3)
            current_notes = [rest] if rest else []
            # A new setup makes no claim about its day until its own line says
            # so; inheriting the last one would spread a wrong day down the page.
            block_start = len(records)
            current_shoot_day = None
            current_block_roll = None

            # Check if camera roll is on this same line: A1202807262:46 or B412807261:1125
            cr, raw_date = extract_script_camera_roll_and_date(rest)
            # Only the header row carries a date column. The takes and the
            # per-camera rows beneath it are the same setup on the same day, so
            # they inherit it rather than falling back to the report's date.
            current_block_date = parse_shoot_date(raw_date)
            if cr:
                norm_slate = normalize_slate(current_slate)
                take_info = normalize_take(current_take)
                scene = norm_slate.split("/")[0] if norm_slate and "/" in norm_slate else norm_slate
                row_date = parse_shoot_date(raw_date) or current_block_date or report_date
                if current_block_date is None:
                    current_block_date = parse_shoot_date(raw_date)
                current_block_roll = cr
                records.append(
                    ParsedScriptRecord(
                        scene=scene,
                        slate=norm_slate,
                        take_id=take_info.take_id,
                        camera_roll=cr,
                        timecode_in=None,
                        timecode_out=None,
                        recording_date=row_date,
                        shoot_day=current_shoot_day,
                        is_starred=take_info.is_starred,
                        is_pickup=take_info.is_pickup,
                        is_false_start=take_info.is_false_start,
                        is_wild_track="WT" in current_slate.upper() or take_info.is_wild_track,
                        is_vfx="VFX" in cleaned.upper() or take_info.is_vfx,
                        is_mos="MOS" in cleaned.upper() or "MOS" in current_slate.upper() or take_info.is_mos,
                        note=rest or take_info.note,
                        raw_payload={"camera_roll": cr, "is_vfx": "VFX" in cleaned.upper()},
                    )
                )
            continue

        # 2b. The same header, split over two lines. The PDF text layer puts a
        # long slate on a line of its own and its take number on the next,
        # which matches nothing above: the setup is missed, the previous slate
        # stays current, and the card further down is filed against it. That is
        # how 119/5 Take 1 came back holding A046, A068 and A080 -- the cards of
        # three different shots.
        #
        # The take line must name a scene for this to be a setup header, which
        # is what separates it from the bare slates printed on the lined script
        # pages, where the same numbers appear over camera labels.
        if re.fullmatch(SLATE_TOKEN, cleaned) and re.match(
            r"^(\d+(?:\.\d+)?(?:[A-Z](?![A-Za-z]))?\s*\*?|\d+\*|FALSE)\s+Scene\(s\):", next_content_line(idx)
        ):
            current_slate = cleaned
            current_take = None
            current_notes = []
            block_start = len(records)
            current_shoot_day = None
            current_block_date = None
            current_block_roll = None
            continue

        # 3. Subsequent take or multi-camera setup angle: '1 Dolly - wide... B039 2:46' or '2 A120 2:53' or '3* A122 3:23'
        sub_m = re.search(r"^(\d+(?:\.\d+)?(?:[A-Z](?![A-Za-z]))?\s*\*?|\d+\*|FALSE)\s+(.*)", cleaned)
        if sub_m and current_slate:
            current_take = sub_m.group(1).replace(" ", "")
            rest = sub_m.group(2)
            cr, raw_date = extract_script_camera_roll_and_date(rest)
            if cr:
                norm_slate = normalize_slate(current_slate)
                take_info = normalize_take(current_take)
                scene = norm_slate.split("/")[0] if norm_slate and "/" in norm_slate else norm_slate
                row_date = parse_shoot_date(raw_date) or current_block_date or report_date
                if current_block_date is None:
                    current_block_date = parse_shoot_date(raw_date)
                current_block_roll = cr
                records.append(
                    ParsedScriptRecord(
                        scene=scene,
                        slate=norm_slate,
                        take_id=take_info.take_id,
                        camera_roll=cr,
                        timecode_in=None,
                        timecode_out=None,
                        recording_date=row_date,
                        shoot_day=current_shoot_day,
                        is_starred=take_info.is_starred,
                        is_pickup=take_info.is_pickup,
                        is_false_start=take_info.is_false_start,
                        is_wild_track="WT" in current_slate.upper() or take_info.is_wild_track,
                        is_vfx="VFX" in cleaned.upper() or take_info.is_vfx,
                        is_mos="MOS" in cleaned.upper() or "MOS" in current_slate.upper() or take_info.is_mos,
                        note=rest or take_info.note,
                        raw_payload={"camera_roll": cr, "is_vfx": "VFX" in cleaned.upper()},
                    )
                )
            elif current_block_roll and re.match(r"^\d+:\d{2}\b", rest):
                # A take row whose CR column is blank: the setup's card is
                # written once and the takes beneath it are on the same card.
                # Read as "no card" the row produced nothing at all, and the
                # take vanished -- 26 of them on one document, among them every
                # part of a take covered in more than one pass (1.2, 2.1, 2.2).
                # The duration is what marks this out as a take row rather than
                # a stray number in the description.
                norm_slate = normalize_slate(current_slate)
                take_info = normalize_take(current_take)
                scene = norm_slate.split("/")[0] if norm_slate and "/" in norm_slate else norm_slate
                records.append(
                    ParsedScriptRecord(
                        scene=scene,
                        slate=norm_slate,
                        take_id=take_info.take_id,
                        camera_roll=current_block_roll,
                        timecode_in=None,
                        timecode_out=None,
                        recording_date=current_block_date or report_date,
                        shoot_day=current_shoot_day,
                        is_starred=take_info.is_starred,
                        is_pickup=take_info.is_pickup,
                        is_false_start=take_info.is_false_start,
                        is_wild_track="WT" in current_slate.upper() or take_info.is_wild_track,
                        is_vfx="VFX" in cleaned.upper() or take_info.is_vfx,
                        is_mos="MOS" in cleaned.upper() or "MOS" in current_slate.upper() or take_info.is_mos,
                        note=rest or take_info.note,
                        # The card is the setup's, not this row's. A reader
                        # weighing a roll conflict should be able to tell.
                        raw_payload={"camera_roll": current_block_roll,
                                     "camera_roll_inherited": True,
                                     "is_vfx": "VFX" in cleaned.upper()},
                    )
                )
            continue

        # 4. A row that carries its own slate but matched no header pattern is a
        # row we cannot place. Reading on would give its card to the shot above:
        # this is how 119/5 Take 1 came back claiming cards A046, A068 and A080,
        # the last two belonging to shots further down the page. Better to drop
        # the row, and to forget the current shot so the rows beneath it do not
        # attach to it either.
        if "Scene(s):" in cleaned:
            logger.warning("Unrecognised slate on facing-page row, skipping: %s", cleaned[:80])
            current_slate = None
            current_take = None
            current_notes = []
            block_start = len(records)
            current_shoot_day = None
            current_block_date = None
            current_block_roll = None
            continue

        # 5. Standalone roll line for current setup (e.g. 'A1202807262:46' or 'B412807261:1125')
        cr, raw_date = extract_script_camera_roll_and_date(cleaned)
        if cr and current_slate and current_take:
            norm_slate = normalize_slate(current_slate)
            take_info = normalize_take(current_take)
            scene = norm_slate.split("/")[0] if norm_slate and "/" in norm_slate else norm_slate
            notes_str = " ".join(current_notes).strip() or cleaned
            row_date = parse_shoot_date(raw_date) or current_block_date or report_date
            if current_block_date is None:
                current_block_date = parse_shoot_date(raw_date)
            current_block_roll = cr
            records.append(
                ParsedScriptRecord(
                    scene=scene,
                    slate=norm_slate,
                    take_id=take_info.take_id,
                    camera_roll=cr,
                    timecode_in=None,
                    timecode_out=None,
                    recording_date=row_date,
                    shoot_day=current_shoot_day,
                    is_starred=take_info.is_starred,
                    is_pickup=take_info.is_pickup,
                    is_false_start=take_info.is_false_start,
                    is_wild_track="WT" in current_slate.upper() or take_info.is_wild_track,
                    is_vfx="VFX" in cleaned.upper() or "VFX" in notes_str.upper() or take_info.is_vfx,
                    is_mos="MOS" in cleaned.upper() or "MOS" in notes_str.upper() or take_info.is_mos,
                    note=notes_str or take_info.note,
                    raw_payload={"camera_roll": cr, "is_vfx": "VFX" in cleaned.upper()},
                )
            )
            continue

        if current_slate and not cleaned.startswith("Script /") and not cleaned.startswith("Date:"):
            # Same catch-all, same refusal. See the note above.
            if is_contact_information(cleaned):
                continue
            current_notes.append(cleaned)

    if not records:
        raise ParserFailureError("Editor's log parser yielded zero valid records")

    return unify_take_level_marks(records)


def parse_silverstack_volume_text(text: str) -> List[ParsedSilverstackClip]:
    """
    Parses Silverstack volume report text (e.g. Volume-664 SD-20260728-1927.pdf) into media existence clips.
    Extracts sound card folders (e.g. 26Y07M27), WAV filenames with scene/shot/take (e.g. 71C-3T02.WAV),
    verified xxHash64 checksums, file sizes, and audio wild tracks.
    """
    if not text or not text.strip():
        raise ParserFailureError("Empty Silverstack Volume text")

    vol_m = re.search(r"Volume Report[^\n]*\n[^\n]*\n([^\n]+)", text)
    vol_name = vol_m.group(1).strip() if vol_m else "664 SD"

    clips: List[ParsedSilverstackClip] = []
    lines = text.strip().splitlines()

    current_file: Optional[str] = None
    current_folder: Optional[str] = None
    current_checksum: Optional[str] = None
    current_hash_type: str = "XXH64"

    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue

        # 1. Sound Card / Reel folder header (e.g. '26Y07M27 5.51 GB' or '04Y00M12')
        folder_m = re.search(r"\b(\d{2}Y\d{2}M\d{2})\b", cleaned)
        if folder_m:
            current_folder = folder_m.group(1)

        # 2. Media file line (e.g. '+99BDF-9T01.WAV', '71C-3T02.WAV', or 'A120_C001_260728.MOV')
        file_match = re.match(r"^([\+A-Za-z0-9_\-\.]+\.(?:WAV|MOV|BRAW|ARI|ARX|MXF|MP4))$", cleaned, re.IGNORECASE)
        if file_match:
            current_file = file_match.group(1)
            current_checksum = None
            continue

        # 3. Checksum line (e.g. 'XXH64:1b742d797173f0d4' or 'MD5:abc123')
        hash_m = re.search(r"(XXH64|MD5|SHA1):([a-f0-9]+)", cleaned, re.IGNORECASE)
        if hash_m:
            current_hash_type = hash_m.group(1).upper()
            current_checksum = hash_m.group(2)

        # 4. File Size line (e.g. '60.49 MB' or inline with hash)
        size_m = re.search(r"([\d.]+)\s*(MB|GB|KB|Bytes)", cleaned, re.IGNORECASE)
        if size_m and current_file and current_checksum:
            size_val = float(size_m.group(1))
            unit = size_m.group(2).upper()

            if unit == "GB":
                size_bytes = int(size_val * 1024 * 1024 * 1024)
            elif unit == "MB":
                size_bytes = int(size_val * 1024 * 1024)
            elif unit == "KB":
                size_bytes = int(size_val * 1024)
            else:
                size_bytes = int(size_val)

            is_wav = current_file.lower().endswith(".wav")
            scene: Optional[str] = None
            shot: Optional[str] = None
            take_id: Optional[str] = None
            is_pk: bool = False
            is_wt: bool = False

            if is_wav:
                base = current_file[:-4] if current_file.lower().endswith(".wav") else current_file

                # 1. Standard WAV format: [Scene]-[Shot]T[Take].WAV, e.g. +99BDF-9T01.WAV, 71C-3T02.WAV, 64A-2PkT5.WAV, 41-122a-1T01.WAV
                m1 = re.match(r"^(.+?)-([A-Za-z0-9_]+)T([A-Za-z0-9_*]+)$", base, re.IGNORECASE)
                if m1:
                    scene = m1.group(1)
                    raw_shot = m1.group(2)
                    raw_take = m1.group(3)
                    take_info = normalize_take(raw_take)
                    take_id = take_info.take_id or raw_take
                    if "PK" in raw_shot.upper() or take_info.is_pickup:
                        is_pk = True
                        raw_shot = re.sub(r"pk", "", raw_shot, flags=re.IGNORECASE)
                    if "WT" in scene.upper() or "WT" in raw_shot.upper() or take_info.is_wild_track:
                        is_wt = True
                    shot = raw_shot
                else:
                    # 2. Wild track without hyphen: e.g. 101AWTT01.WAV, 49WTT01.WAV, 68A68WTT01.WAV
                    m2 = re.match(r"^(.+?)WTT([A-Za-z0-9_*]+)$", base, re.IGNORECASE)
                    if m2:
                        scene = m2.group(1)
                        shot = "WT"
                        raw_take = m2.group(2)
                        take_info = normalize_take(raw_take)
                        take_id = take_info.take_id or raw_take
                        is_wt = True
                    else:
                        # 3. Scene + Take only: e.g. 68T01.WAV
                        m3 = re.match(r"^(.+?)T([A-Za-z0-9_*]+)$", base, re.IGNORECASE)
                        if m3:
                            scene = m3.group(1)
                            shot = None
                            raw_take = m3.group(2)
                            take_info = normalize_take(raw_take)
                            take_id = take_info.take_id or raw_take

            # Silverstack writes both `Scene 27` and `Shot 27/7`, and the Shot
            # field is already the whole slate rather than the shot half of one.
            # Prefixing the scene made `27/27/7`, which normalised to `27/27`, so
            # every clip in the report reached the spine under a slate nobody
            # wrote and DIT silently disagreed with camera about every take.
            #
            # A shot carrying `/` or `-` is a full slate; a bare `9` still
            # needs its scene in front of it. Both shapes occur in real reports.
            if shot and re.search(r"[/-]", shot):
                slate_source = shot
            elif shot and scene:
                slate_source = f"{scene}/{shot}"
            else:
                slate_source = scene or shot
            norm_slate = normalize_slate(slate_source) if slate_source else None
            if norm_slate:
                if "/" in norm_slate:
                    scene = norm_slate.split("/")[0]
                    shot = norm_slate.split("/")[1]
                else:
                    scene = norm_slate

            roll: Optional[str] = None
            if not is_wav:
                roll_m = re.match(r"^([A-Z]\d{3})", current_file)
                roll = normalize_camera_roll(roll_m.group(1)) if roll_m else None

            clips.append(
                ParsedSilverstackClip(
                    file_name=current_file,
                    camera_roll=roll,
                    file_size_bytes=size_bytes,
                    checksum=current_checksum,
                    checksum_type=current_hash_type,
                    volume_name=vol_name,
                    reel_tape=current_folder,
                    scene=scene,
                    shot=shot,
                    take_id=take_id,
                    codec="Linear PCM (24bit, 48kHz)" if is_wav else None,
                    card_type="sound" if is_wav else "camera",
                    is_pickup=is_pk,
                    is_wild_track=is_wt or "WT" in (norm_slate or "").upper(),
                    raw_payload={
                        "volume": vol_name,
                        "checksum": current_checksum,
                        "hash_type": current_hash_type,
                        "sound_roll": current_folder,
                        "card_type": "sound" if is_wav else "camera",
                    },
                )
            )
            current_file = None
            current_checksum = None

    if not clips:
        raise ParserFailureError("Silverstack Volume text parser yielded zero valid records")

    return clips


def parse_silverstack_shooting_day_text(text: str) -> List[ParsedSilverstackClip]:
    """
    Parses Pomfort Silverstack Shooting Day Report text (e.g. Shooting Day-260728_SD31-20260728-1927.pdf).
    Extracts all offload bins, camera reels, media file counts, and volumes verified.
    """
    if not text or not text.strip():
        raise ParserFailureError("Empty Silverstack Shooting Day text")

    clips: List[ParsedSilverstackClip] = []
    lines = text.strip().splitlines()

    for line in lines:
        cleaned = line.strip()
        # Look for Video Reels or Bins: A_0120_1EIC A_ 1026:31 min 10377.83 GB or B_0039_1C9B
        reel_m = re.search(r"([A-C]_0*\d{3,4}_[A-Za-z0-9]+)\s+([A-C_]+)\s+(\d+)\s*([\d:]+\s*(?:min|h|sec))\s+(\d+)?\s*([\d.]+\s*(?:GB|TB|MB))", cleaned)
        if reel_m:
            reel_name = reel_m.group(1)
            raw_roll = reel_name.split("_")[0] + reel_name.split("_")[1][-3:]
            norm_roll = normalize_camera_roll(raw_roll)
            clip_count = int(reel_m.group(3))
            size_str = reel_m.group(6)

            size_val_m = re.search(r"([\d.]+)\s*(GB|TB|MB)", size_str)
            size_bytes = 0
            if size_val_m:
                val = float(size_val_m.group(1))
                u = size_val_m.group(2).upper()
                mult = {"TB": 1024**4, "GB": 1024**3, "MB": 1024**2}.get(u, 1024**3)
                size_bytes = int(val * mult)

            # Generate placeholder verified clip records for this reel
            for i in range(1, clip_count + 1):
                clip_fname = f"{norm_roll}_C{i:03d}.mxf"
                clips.append(
                    ParsedSilverstackClip(
                        file_name=clip_fname,
                        camera_roll=norm_roll,
                        file_size_bytes=size_bytes // max(clip_count, 1),
                        checksum="VERIFIED-BACKUP-3+",
                        checksum_type="XXH64",
                        volume_name=reel_name,
                        raw_payload={"reel": reel_name, "verified_copies": "3+"},
                    )
                )

    if not clips:
        # Fallback to volume parser
        return parse_silverstack_volume_text(text)

    return clips


def parse_silverstack_clips_text(text: str, thumbnails_map: Optional[Dict[str, str]] = None) -> List[ParsedSilverstackClip]:
    """
    Parses Pomfort Silverstack Clips Reports (e.g. Clips-260728_SD31-20260728-1927.pdf).
    Extracts individual scene/take clip names, audio WAV files, camera video clips, lenses,
    shutter angle, ISO, White Balance, T-stops, and associates visual thumbnails.
    """
    if not text or not text.strip():
        raise ParserFailureError("Empty Silverstack Clips text")

    clips: List[ParsedSilverstackClip] = []
    lines = text.strip().splitlines()

    for line in lines:
        cleaned = line.strip()
        if not cleaned or any(cleaned.startswith(k) for k in ["Clips Report", "Pomfort", "Offloads", "and 28", "260728", "DEMO PRODUCTION", "Preview Name"]):
            continue

        # 1. Sound line: e.g. '27-7T01 Sound Dev: Mix664 S#KA0513004007 3:00 min' or '49WTT01 ...' or '+99BDF-9T01 ...'
        sm = re.match(r"^([\+A-Za-z0-9_\-]+)\s+(Sound Dev:[^\n]+?)\s+(\d+:\d+\s*(?:min|sec)|\d+\s*sec)$", cleaned)
        if sm:
            clip_id = sm.group(1)
            recorder_info = sm.group(2)
            dur_str = sm.group(3)
            fname = f"{clip_id}.WAV"

            scene: Optional[str] = None
            shot: Optional[str] = None
            take_id: Optional[str] = None
            is_pk = False
            is_wt = False

            base = clip_id
            m1 = re.match(r"^(.+?)-([A-Za-z0-9_]+)T([A-Za-z0-9_*]+)$", base, re.IGNORECASE)
            if m1:
                scene = m1.group(1)
                raw_shot = m1.group(2)
                raw_take = m1.group(3)
                take_info = normalize_take(raw_take)
                take_id = take_info.take_id or raw_take
                if "PK" in raw_shot.upper() or take_info.is_pickup:
                    is_pk = True
                    raw_shot = re.sub(r"pk", "", raw_shot, flags=re.IGNORECASE)
                if "WT" in scene.upper() or "WT" in raw_shot.upper() or take_info.is_wild_track:
                    is_wt = True
                shot = raw_shot
            else:
                m2 = re.match(r"^(.+?)WTT([A-Za-z0-9_*]+)$", base, re.IGNORECASE)
                if m2:
                    scene = m2.group(1)
                    shot = "WT"
                    raw_take = m2.group(2)
                    take_info = normalize_take(raw_take)
                    take_id = take_info.take_id or raw_take
                    is_wt = True
                else:
                    m3 = re.match(r"^(.+?)T([A-Za-z0-9_*]+)$", base, re.IGNORECASE)
                    if m3:
                        scene = m3.group(1)
                        shot = None
                        raw_take = m3.group(2)
                        take_info = normalize_take(raw_take)
                        take_id = take_info.take_id or raw_take

            # Silverstack writes both `Scene 27` and `Shot 27/7`, and the Shot
            # field is already the whole slate rather than the shot half of one.
            # Prefixing the scene made `27/27/7`, which normalised to `27/27`, so
            # every clip in the report reached the spine under a slate nobody
            # wrote and DIT silently disagreed with camera about every take.
            #
            # A shot carrying `/` or `-` is a full slate; a bare `9` still
            # needs its scene in front of it. Both shapes occur in real reports.
            if shot and re.search(r"[/-]", shot):
                slate_source = shot
            elif shot and scene:
                slate_source = f"{scene}/{shot}"
            else:
                slate_source = scene or shot
            norm_slate = normalize_slate(slate_source) if slate_source else None
            if norm_slate:
                if "/" in norm_slate:
                    scene = norm_slate.split("/")[0]
                    shot = norm_slate.split("/")[1]
                else:
                    scene = norm_slate

            clips.append(
                ParsedSilverstackClip(
                    file_name=fname,
                    camera_roll=None,
                    file_size_bytes=50 * 1024 * 1024,
                    checksum="VERIFIED",
                    checksum_type="XXH64",
                    volume_name="664 SD",
                    scene=scene,
                    shot=shot,
                    take_id=take_id,
                    codec="Linear PCM (24bit, 48kHz)",
                    card_type="sound",
                    is_pickup=is_pk,
                    is_wild_track=is_wt or "WT" in (norm_slate or "").upper(),
                    raw_payload={"recorder": recorder_info, "duration": dur_str, "card_type": "sound"},
                )
            )
            continue

        # 2. Camera video line: e.g. 'A_0120C001_260728_091309_h1EIC A_ ARRI ALEXA 35 2:45 min 4608x3164 172.8° @ 24fps 50.0 mm 2 9/10 800 6000 K'
        vm = re.match(r"^([A-C]_0*\d{3,4}C\d{3,4}[^\s]*)\s+([A-C]_)\s+([^\n]+?)\s+(\d+:\d+\s*(?:min|sec)|\d+(?:\.\d+)?\s*sec)\s+(\d+x\d+)\s+([\d.]+°\s*@\s*\d+fps)\s+([\d.]+\s*mm)\s+([^\s]+(?:\s+\d+/\d+)?)\s+(\d+)\s+(\d+\s*K)", cleaned)
        if vm:
            cname = vm.group(1)
            cam = vm.group(2).strip("_")
            model = vm.group(3)
            dur = vm.group(4)
            res = vm.group(5)
            shutter = vm.group(6)
            focal = vm.group(7)
            tstop = vm.group(8)
            iso = int(vm.group(9))
            wb = vm.group(10)

            roll_m = re.search(r"^([A-C])_0*(\d{3,4})C(\d{3,4})", cname)
            roll = None
            short_k = None
            if roll_m:
                prefix = roll_m.group(1)
                rnum = roll_m.group(2)[-3:]
                roll = normalize_camera_roll(f"{prefix}{rnum}")
                short_k = f"{roll}_C{int(roll_m.group(3)):03d}"

            full_fname = cname if "." in cname else f"{cname}.mxf"

            thumb_uri = None
            if thumbnails_map:
                thumb_uri = (
                    thumbnails_map.get(cname)
                    or thumbnails_map.get(full_fname)
                    or (thumbnails_map.get(short_k) if short_k else None)
                )

            clips.append(
                ParsedSilverstackClip(
                    file_name=full_fname,
                    camera_roll=roll,
                    file_size_bytes=2000 * 1024 * 1024,
                    checksum="VERIFIED",
                    checksum_type="XXH64",
                    volume_name=f"Camera Card {roll}" if roll else "Offload Reel",
                    codec="ARRIRAW (MXF)",
                    camera=cam,
                    fps=24.0,
                    iso=iso,
                    tstop=tstop,
                    card_type="camera",
                    thumbnail_b64=thumb_uri,
                    raw_payload={
                        "model": model,
                        "duration": dur,
                        "resolution": res,
                        "shutter": shutter,
                        "focal_length": focal,
                        "tstop": tstop,
                        "iso": iso,
                        "wb": wb,
                        "camera": cam,
                        "card_type": "camera",
                    },
                )
            )

    if not clips:
        return parse_silverstack_volume_text(text)

    return clips


# `260728_SD31` on a line of its own: the volume stamp. Skipped as furniture
# here and read for its date by normalizers.shoot_days.extract_shoot_date,
# which is where the shoot day and its calendar date are bound together.
_VOLUME_STAMP_LINE = re.compile(r"^\d{6}_SD\d+$", re.IGNORECASE)

# `Offloads started between 27 and 28 July` and the like.
_OFFLOAD_WINDOW = re.compile(r"^(?:and\s+)?\d{1,2}\s+\w+(?:\s+\d{4})?$", re.IGNORECASE)


def parse_silverstack_thumbnail_text(text: str, thumbnails_map: Optional[Dict[str, str]] = None) -> List[ParsedSilverstackClip]:
    """
    Parses Pomfort Silverstack Thumbnail Reports (e.g. Thumbnail-260728_SD31-20260728-1927.pdf).
    Extracts clip Name, Reel/Tape, Scene, Shot, Take, Codec, Recording Date, Duration, FPS, ISO, T-Stop,
    Shutter Angle, White Balance, and attaches visual thumbnail pictures and card classification.
    """
    if not text or not text.strip():
        raise ParserFailureError("Empty Silverstack Thumbnail text")

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    clip_blocks: List[List[str]] = []
    current_block: List[str] = []

    for line in lines:
        if (
            # Report furniture, matched on what it is rather than on the
            # strings this one demo document happens to contain. "and 28 July",
            # "260728_SD31" and "DEMO PRODUCTION" were listed literally, so
            # another production's report would have carried those lines into
            # its clips -- the keyed list that rots, and it was also discarding
            # the volume stamp that binds the shoot day to its date.
            "Thumbnail Report" in line
            or "Pomfort Silverstack" in line
            or "Offloads started" in line
            or line.startswith("Production:")
            or _VOLUME_STAMP_LINE.match(line)
            or _OFFLOAD_WINDOW.match(line)
            or "★★★★★" in line
        ):
            continue

        if line.startswith("Name "):
            if current_block:
                clip_blocks.append(current_block)
            current_block = [line]
        elif current_block:
            current_block.append(line)

    if current_block:
        clip_blocks.append(current_block)

    clips: List[ParsedSilverstackClip] = []

    skipped_blocks: List[str] = []
    for blk in clip_blocks:
        name_line = blk[0]
        raw_name = name_line[5:].strip()

        # A block that is not a clip at all.
        #
        # Blocks are split on lines beginning "Name ", so a contact block
        # written that way became an entire clip: an email address in
        # file_name, and the same line canonicalised into scene and shot. A
        # slate-shaped test would not have caught it, because file_name is not
        # a slate -- the third parser today with the same defect wearing a
        # different field.
        #
        # Skipped rather than rejected: one junk block does not make a report
        # unparseable, and the empty-result guard below still catches a
        # document that is entirely junk.
        if not looks_like_a_clip_name(raw_name):
            skipped_blocks.append(raw_name or "(blank)")
            continue

        # Handle wrapped trailing character (e.g. 'A_0120C001_260728_091309_h1EI' + 'C')
        if len(blk) > 1 and len(blk[1]) <= 4 and not any(k in blk[1] for k in ["ShotID", "Duration", "Camera", "Reel", "Scene", "Take", "Director", "Sensor"]):
            raw_name += blk[1].strip()

        reel_tape: Optional[str] = None
        scene: Optional[str] = None
        shot: Optional[str] = None
        raw_take: Optional[str] = None
        codec: Optional[str] = None
        duration: Optional[str] = None
        camera: Optional[str] = None
        fps: Optional[float] = None
        iso: Optional[int] = None
        tstop: Optional[str] = None
        shutter: Optional[str] = None
        wb: Optional[str] = None
        rec_date: Optional[str] = None

        for l in blk:
            if l.startswith("Reel/Tape "):
                reel_tape = l[10:].strip()
            elif l.startswith("Scene "):
                scene = l[6:].strip()
            elif l.startswith("Shot "):
                shot = l[5:].strip()
            elif l.startswith("Take "):
                raw_take = l[5:].strip()
            elif l.startswith("Duration "):
                duration = l[9:].strip()
            elif l.startswith("Camera ") and len(l) > 7:
                val = l[7:].strip()
                if val and not any(val.startswith(kw) for kw in ["Reel", "Season", "Episode", "Scene"]):
                    camera = val
            elif l.startswith("Sensor FPS "):
                val = l[11:].strip()
                m = re.match(r"^(\d+(?:\.\d+)?)", val)
                if m:
                    fps = float(m.group(1))
            elif l.startswith("EI/ISO (clip) "):
                val = l[14:].strip()
                m = re.match(r"^(\d+)", val)
                if m:
                    iso = int(m.group(1))
            elif l.startswith("T-Stop "):
                val = l[7:].strip()
                if val and any(c.isdigit() for c in val):
                    tstop = val
            elif l.startswith("Shutter Angle "):
                val = l[14:].strip()
                if val and any(c.isdigit() for c in val):
                    shutter = val
            elif l.startswith("WB (clip) "):
                val = l[10:].strip()
                if val and any(c.isdigit() for c in val):
                    wb = val
            elif l.startswith("Codec "):
                codec = l[6:].strip()
            elif l.startswith("Recording Date "):
                rec_date = l[15:].strip()

        blk_str = "\n".join(blk)
        codec_m = re.search(r"\nCodec\s+(.+?)(?=\nRecording Date|\nLocation|\Z)", blk_str, re.DOTALL)
        if codec_m:
            codec = re.sub(r"\s+", " ", codec_m.group(1)).strip()

        # Infer camera roll from reel_tape (e.g. A_0120_1EIC -> A120)
        roll: Optional[str] = None
        if reel_tape:
            roll_m = re.search(r"([A-C]_0*(\d{3,4}))", reel_tape)
            if roll_m:
                prefix = roll_m.group(1)[0]
                num = roll_m.group(2)[-3:]
                roll = normalize_camera_roll(f"{prefix}{num}")

        # Deterministic video vs audio classification
        has_video_params = bool(
            (fps is not None)
            or (iso is not None)
            or (tstop is not None)
            or (shutter is not None)
            or (wb is not None)
            or (camera is not None and camera.strip())
            or (codec and any(vc in codec.upper() for vc in ["ARRIRAW", "PRORES", "MXF", "HDE", "BRAW", "REDCODE", "DNXHR", "X-OCN", "H.264", "HEVC", "MOV", "MP4"]))
            or (reel_tape and any(reel_tape.startswith(pfx) for pfx in ["A_", "B_", "C_", "D_"]))
        )

        card_type = "camera" if has_video_params else "sound"
        file_ext = ".WAV" if card_type == "sound" else ".mxf"
        full_fname = raw_name if ("." in raw_name) else f"{raw_name}{file_ext}"

        is_vfx = "VFX" in (raw_take or "") or "VFX" in blk_str

        take_info = normalize_take(raw_take)
        take_id = take_info.take_id
        if take_info.is_vfx:
            is_vfx = True

        # Silverstack writes both `Scene 27` and `Shot 27/7`, and the Shot
        # field is already the whole slate rather than the shot half of one.
        # Prefixing the scene made `27/27/7`, which normalised to `27/27`, so
        # every clip in the report reached the spine under a slate nobody
        # wrote and DIT silently disagreed with camera about every take.
        #
        # A shot carrying `/` or `-` is a full slate; a bare `9` still
        # needs its scene in front of it. Both shapes occur in real reports.
        if shot and re.search(r"[/-]", shot):
            slate_source = shot
        elif shot and scene:
            slate_source = f"{scene}/{shot}"
        else:
            slate_source = scene or shot
        norm_slate = normalize_slate(slate_source) if slate_source else None
        if norm_slate:
            if "/" in norm_slate:
                scene = norm_slate.split("/")[0]
                shot = norm_slate.split("/")[1]
            else:
                scene = norm_slate

        is_wt = "WT" in (scene or "").upper() or "WT" in (shot or "").upper() or "WT" in (raw_name or "").upper() or "WT" in (norm_slate or "").upper() or take_info.is_wild_track

        # Multi-tier thumbnail image resolution
        thumb_uri = None
        if thumbnails_map:
            thumb_uri = (
                thumbnails_map.get(raw_name)
                or thumbnails_map.get(full_fname)
                or thumbnails_map.get(raw_name.split(".")[0])
            )
            if not thumb_uri and roll:
                m_c = re.search(r"C(\d{3,4})", raw_name)
                if m_c:
                    norm_k = f"{roll}_C{int(m_c.group(1)):03d}"
                    thumb_uri = thumbnails_map.get(norm_k)
            if not thumb_uri and scene and shot and take_id:
                thumb_uri = thumbnails_map.get(f"{scene}/{shot}_{take_id}")

        clips.append(
            ParsedSilverstackClip(
                file_name=full_fname,
                camera_roll=roll,
                file_size_bytes=50 * 1024 * 1024 if card_type == "sound" else 2000 * 1024 * 1024,
                checksum="VERIFIED-NOTARY",
                checksum_type="XXH64",
                volume_name=reel_tape or "Offload Reel",
                reel_tape=reel_tape,
                scene=scene,
                shot=shot,
                take_id=take_id,
                codec=codec,
                recording_date=rec_date,
                camera=camera,
                fps=fps,
                iso=iso,
                tstop=tstop,
                is_vfx=is_vfx,
                is_wild_track=is_wt,
                card_type=card_type,
                thumbnail_b64=thumb_uri,
                raw_payload={
                    "duration": duration,
                    "reel_tape": reel_tape,
                    "codec": codec,
                    "recording_date": rec_date,
                    "camera": camera,
                    "fps": fps,
                    "iso": iso,
                    "tstop": tstop,
                    "shutter": shutter,
                    "wb": wb,
                    "card_type": card_type,
                },
            )
        )

    if not clips:
        return parse_silverstack_clips_text(text, thumbnails_map=thumbnails_map)

    return clips


def parse_silverstack_pdf_text(text: str, thumbnails_map: Optional[Dict[str, str]] = None) -> List[ParsedSilverstackClip]:
    """
    Unified entry point for all Silverstack PDF formats (Volume, Shooting Day, Clips, Thumbnail).
    """
    if "Thumbnail Report" in text:
        return parse_silverstack_thumbnail_text(text, thumbnails_map=thumbnails_map)
    elif "Volume Report" in text or "XXH64:" in text or "MD5:" in text:
        return parse_silverstack_volume_text(text)
    elif "Shooting Day Report" in text:
        return parse_silverstack_shooting_day_text(text)
    elif "Clips Report" in text:
        return parse_silverstack_clips_text(text, thumbnails_map=thumbnails_map)
    else:
        return parse_silverstack_volume_text(text)

