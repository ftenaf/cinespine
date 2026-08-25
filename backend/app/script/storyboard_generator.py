"""
Generative Storyboard & Previz Visual Renderer for CineSpine.
Produces high-fidelity cinematic concept frames with aspect ratio letterboxing,
camera HUD overlays, lens metadata tags, and base64 proxy frame delivery.
"""
import base64
import html
from typing import Optional, Dict, Any


def render_cinematic_storyboard_svg(
    prompt: str,
    scene_number: str,
    shot_number: str,
    shot_size: str,
    focal_length: int,
    aperture: str,
    dop_preset: str,
    aspect_ratio: str = "2.39:1"
) -> str:
    """
    Renders a crisp cinematic concept art SVG frame with DoP camera HUD metadata.
    """
    # Aspect Ratio Canvas Calculations
    if aspect_ratio == "2.39:1":
        width, height = 956, 400
    elif aspect_ratio == "1.85:1":
        width, height = 740, 400
    elif aspect_ratio == "4:3":
        width, height = 533, 400
    else:  # 16:9
        width, height = 711, 400

    # Determine aesthetic color palette based on DoP preset
    if "Fincher" in dop_preset:
        bg_dark, bg_mid, accent = "#04090A", "#0C1F20", "#14B8A6"
        atmosphere_tone = "Low-Key Neo-Noir • Teal & Amber"
    elif "Fraser" in dop_preset:
        bg_dark, bg_mid, accent = "#120B04", "#2B1A0A", "#F59E0B"
        atmosphere_tone = "Atmospheric Silhouette • Anamorphic Warmth"
    elif "Willis" in dop_preset:
        bg_dark, bg_mid, accent = "#0D0804", "#1E120A", "#D97706"
        atmosphere_tone = "Top-Lit Chiaroscuro • Vintage Sepia"
    elif "Lubezki" in dop_preset:
        bg_dark, bg_mid, accent = "#040E14", "#0C2E3D", "#38BDF8"
        atmosphere_tone = "Golden Hour Natural Light • Ultra-Wide"
    elif "Anderson" in dop_preset:
        bg_dark, bg_mid, accent = "#2D1B28", "#59364F", "#F472B6"
        atmosphere_tone = "Symmetrical Planar • Pastel Warmth"
    else:  # Deakins default
        bg_dark, bg_mid, accent = "#080F18", "#13253B", "#60A5FA"
        atmosphere_tone = "Motivated Daylight • Spherical Clarity"

    clean_prompt = html.escape(prompt[:110] + ("..." if len(prompt) > 110 else ""))

    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">
  <defs>
    <linearGradient id="frame-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{bg_dark}" />
      <stop offset="50%" stop-color="{bg_mid}" />
      <stop offset="100%" stop-color="{bg_dark}" />
    </linearGradient>

    <radialGradient id="vignette" cx="50%" cy="50%" r="60%">
      <stop offset="40%" stop-color="#000000" stop-opacity="0" />
      <stop offset="100%" stop-color="#000000" stop-opacity="0.85" />
    </radialGradient>

    <filter id="glow">
      <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
      <feMerge>
        <feMergeNode in="coloredBlur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>

  <!-- Cinema Frame Background -->
  <rect width="{width}" height="{height}" fill="url(#frame-grad)" />

  <!-- Volumetric Atmosphere & Silhouette Grid -->
  <g opacity="0.15">
    <line x1="0" y1="{height//2}" x2="{width}" y2="{height//2}" stroke="{accent}" stroke-width="1" stroke-dasharray="4,8" />
    <line x1="{width//3}" y1="0" x2="{width//3}" y2="{height}" stroke="{accent}" stroke-width="1" stroke-dasharray="4,8" />
    <line x1="{2*width//3}" y1="0" x2="{2*width//3}" y2="{height}" stroke="{accent}" stroke-width="1" stroke-dasharray="4,8" />
  </g>

  <!-- Motivated Light Beam -->
  <polygon points="{width//4},0 {3*width//4},0 {width},{height} {width//6},{height}" fill="{accent}" fill-opacity="0.06" />

  <!-- Atmospheric Vignette -->
  <rect width="{width}" height="{height}" fill="url(#vignette)" />

  <!-- Cinematic Framing Crosshairs (Camera HUD) -->
  <g stroke="{accent}" stroke-width="1.5" opacity="0.65">
    <!-- Top-Left Corner -->
    <path d="M 20 35 L 20 20 L 35 20" fill="none" />
    <!-- Top-Right Corner -->
    <path d="M {width-35} 20 L {width-20} 20 L {width-20} 35" fill="none" />
    <!-- Bottom-Left Corner -->
    <path d="M 20 {height-35} L 20 {height-20} L 35 {height-20}" fill="none" />
    <!-- Bottom-Right Corner -->
    <path d="M {width-35} {height-20} L {width-20} {height-20} L {width-20} {height-35}" fill="none" />
    <!-- Center Framing Cross -->
    <line x1="{width//2-10}" y1="{height//2}" x2="{width//2+10}" y2="{height//2}" />
    <line x1="{width//2}" y1="{height//2-10}" x2="{width//2}" y2="{height//2+10}" />
  </g>

  <!-- Top Metadata HUD Banner -->
  <g font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="11" font-weight="700">
    <rect x="25" y="15" width="110" height="22" rx="4" fill="#0F172A" fill-opacity="0.85" stroke="#334155" stroke-width="1" />
    <text x="35" y="30" fill="#F8FAFC">SCENE {scene_number} / SHOT {shot_number}</text>

    <rect x="145" y="15" width="60" height="22" rx="4" fill="{accent}" fill-opacity="0.2" stroke="{accent}" stroke-width="1" />
    <text x="157" y="30" fill="{accent}">{shot_size}</text>

    <!-- Lens & DoP Metadata Right -->
    <rect x="{width-215}" y="15" width="190" height="22" rx="4" fill="#0F172A" fill-opacity="0.85" stroke="#334155" stroke-width="1" />
    <text x="{width-205}" y="30" fill="#CBD5E1">{focal_length}mm • {aperture} • {aspect_ratio}</text>
  </g>

  <!-- Center Concept Visual Subject Silhouette -->
  <g transform="translate({width//2 - 60}, {height//2 - 40})" opacity="0.85">
    <circle cx="60" cy="30" r="18" fill="{accent}" fill-opacity="0.4" filter="url(#glow)" />
    <ellipse cx="60" cy="65" rx="28" ry="20" fill="#0F172A" stroke="{accent}" stroke-width="1.2" />
  </g>

  <!-- Bottom Prompt & Tone Subtitle Bar -->
  <g font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif">
    <rect x="25" y="{height-42}" width="{width-50}" height="28" rx="4" fill="#020617" fill-opacity="0.88" stroke="#1E293B" stroke-width="1" />
    <circle cx="38" cy="{height-28}" r="4" fill="{accent}" />
    <text x="50" y="{height-24}" font-size="10" font-weight="600" fill="#E2E8F0">{clean_prompt}</text>
    <text x="{width-230}" y="{height-24}" font-size="9" font-weight="500" fill="#94A3B8">{dop_preset}</text>
  </g>
</svg>"""

    b64_svg = base64.b64encode(svg_content.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{b64_svg}"
