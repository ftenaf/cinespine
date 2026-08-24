"""
Deterministic Parser for Pomfort Silverstack Volume & Clip Reports (XML).
"""
import xml.etree.ElementTree as ET
from typing import List
from backend.app.parsers.base import ParsedSilverstackClip, ParserFailureError
from backend.app.normalizers.rolls import normalize_camera_roll


def parse_silverstack_xml(content: str) -> List[ParsedSilverstackClip]:
    """
    Parses Silverstack XML reports into normalized clip existence records.
    """
    if not content or not content.strip():
        raise ParserFailureError("Empty Silverstack XML content")

    try:
        root = ET.fromstring(content.strip())
    except ET.ParseError as e:
        raise ParserFailureError(f"Malformed Silverstack XML: {e}")

    clips: List[ParsedSilverstackClip] = []

    # Iterate over Volume / Clip nodes
    for volume_node in root.findall(".//Volume"):
        volume_name = volume_node.get("name")
        for clip_node in volume_node.findall(".//Clip"):
            filename_node = clip_node.find("FileName")
            if filename_node is None or not filename_node.text:
                continue

            file_name = filename_node.text.strip()
            reel_node = clip_node.find("Reel")
            raw_reel = reel_node.text.strip() if reel_node is not None and reel_node.text else None
            norm_cr = normalize_camera_roll(raw_reel)

            bytes_node = clip_node.find("Bytes")
            file_size_bytes = int(bytes_node.text.strip()) if bytes_node is not None and bytes_node.text and bytes_node.text.isdigit() else 0

            hash_node = clip_node.find("Hash")
            checksum = hash_node.text.strip() if hash_node is not None and hash_node.text else None
            checksum_type = hash_node.get("type", "MD5") if hash_node is not None else None

            duration_node = clip_node.find("DurationFrames")
            duration_frames = int(duration_node.text.strip()) if duration_node is not None and duration_node.text and duration_node.text.isdigit() else None

            clip = ParsedSilverstackClip(
                file_name=file_name,
                camera_roll=norm_cr,
                file_size_bytes=file_size_bytes,
                checksum=checksum,
                checksum_type=checksum_type,
                volume_name=volume_name,
                duration_frames=duration_frames,
                raw_payload={"raw_reel": raw_reel, "file_name": file_name},
            )
            clips.append(clip)

    if not clips:
        raise ParserFailureError("Silverstack XML produced zero valid clip records (anti-confident-nothing)")

    return clips
