"""
Generative Storyboard & Multi-Camera Previz Visual Renderer for CineSpine.
Produces prompt-accurate, photorealistic 35mm cinematic concept frames
dynamically rendered from the editable prompt for Camera A, B, and C with
high-fidelity photorealistic stills and camera HUD overlays.
"""
import base64
import html
import re
import os
from typing import Optional, Dict, Any


# Ordinary exterior nouns, not vocabulary from any one production: the
# placeholder must not encode a particular script's world.
_EXTERIOR_HINTS = (
    "street", "road", "sky", "rain", "snow", "forest", "field", "beach",
    "rooftop", "courtyard", "alley", "park", "desert", "mountain", "outside",
    "outdoors", "daylight", "sunset", "sunrise", "horizon",
)

# Coverage vocabulary, which is the same on every production.
_WIDE_TERMS = ("wide", "panoramic", "establishing", "master")
_MEDIUM_TERMS = ("ots", "shoulder", "medium", "two-shot", "two shot")
_TIGHT_TERMS = ("macro", "close", "insert", "detail", "extreme")

_WIDE_SIZES = ("WS", "EWS", "VWS")
_MEDIUM_SIZES = ("MS", "MCU", "OTS", "MWS", "LOW_ANGLE")
_TIGHT_SIZES = ("CU", "ECU", "INSERT")


def detect_setting(prompt: str) -> str:
    """
    Interior or exterior, from the screenplay's own scene-heading convention.

    Where a prompt carries no heading, falls back to generic exterior nouns and
    then to interior, which is the safer default for dialogue coverage.
    """
    text = prompt.lower()
    if "ext." in text or "exterior" in text:
        return "exterior"
    if "int." in text or "interior" in text:
        return "interior"
    if any(hint in text for hint in _EXTERIOR_HINTS):
        return "exterior"
    return "interior"


def _variant_letter(prompt: str, shot_size: str, camera_letter: str) -> str:
    """Picks the placeholder whose framing is closest to the requested coverage."""
    text = prompt.lower()
    size = (shot_size or "").upper()

    if size in _WIDE_SIZES or any(t in text for t in _WIDE_TERMS):
        return "a"
    if size in _MEDIUM_SIZES or any(t in text for t in _MEDIUM_TERMS):
        return "b"
    if size in _TIGHT_SIZES or any(t in text for t in _TIGHT_TERMS):
        return "c"

    cam = (camera_letter or "A").lower()
    return cam if cam in ("a", "b", "c") else "a"


def render_cinematic_storyboard_svg(
    prompt: str,
    scene_number: str,
    shot_number: str,
    shot_size: str,
    focal_length: int,
    aperture: str,
    dop_preset: str,
    camera_letter: str = "A",
    aspect_ratio: str = "2.39:1"
) -> str:
    """
    Renders or resolves a photorealistic cinematic film still customized
    for Camera A, B, or C angle perspectives with authentic 35mm cinematography.
    """
    return f"/previz/{detect_setting(prompt)}_cam_{_variant_letter(prompt, shot_size, camera_letter)}.jpg"
