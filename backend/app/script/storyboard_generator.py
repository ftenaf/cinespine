"""
Generative Storyboard & Multi-Camera Previz Visual Renderer for CineSpine.
Produces prompt-accurate cinematic concept frames dynamically rendered
from the editable prompt for Camera A, B, and C with semantic keyword extraction,
volumetric lighting, anamorphic streaks, and camera HUD overlays.
"""
import base64
import html
import re
from typing import Optional, Dict, Any


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
    Renders a prompt-driven cinematic concept art SVG frame customized
    for Camera A, B, or C angle perspectives with scene-accurate visual elements
    and dynamic reactivity to user-edited prompt keywords.
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

    prompt_lower = prompt.lower()

    # Determine aesthetic color palette based on DoP preset & prompt keywords
    if any(k in prompt_lower for k in ["neon", "cyberpunk", "cyan", "magenta"]):
        bg_dark, bg_mid, accent, beam_color = "#030014", "#0D0A26", "#06B6D4", "#EC4899"
        atmosphere_tone = "Cyberpunk Neo-Noir • Cyan & Magenta"
    elif any(k in prompt_lower for k in ["fire", "flames", "sunset", "warm", "amber", "golden hour"]):
        bg_dark, bg_mid, accent, beam_color = "#140500", "#2D0D00", "#F97316", "#FBBF24"
        atmosphere_tone = "Volumetric Warmth • Golden Hour Flare"
    elif "Fincher" in dop_preset:
        bg_dark, bg_mid, accent, beam_color = "#020708", "#081C1D", "#14B8A6", "#2DD4BF"
        atmosphere_tone = "Low-Key Neo-Noir • Teal & Amber"
    elif "Fraser" in dop_preset:
        bg_dark, bg_mid, accent, beam_color = "#0C0702", "#241607", "#F59E0B", "#FBBF24"
        atmosphere_tone = "Atmospheric Silhouette • Anamorphic Warmth"
    elif "Willis" in dop_preset:
        bg_dark, bg_mid, accent, beam_color = "#0A0502", "#1C0E06", "#D97706", "#F59E0B"
        atmosphere_tone = "Top-Lit Chiaroscuro • Vintage Sepia"
    elif "Lubezki" in dop_preset:
        bg_dark, bg_mid, accent, beam_color = "#020B10", "#082536", "#38BDF8", "#7DD3FC"
        atmosphere_tone = "Golden Hour Natural Light • Ultra-Wide"
    elif "Anderson" in dop_preset:
        bg_dark, bg_mid, accent, beam_color = "#23141F", "#482B3E", "#F472B6", "#FBCFE8"
        atmosphere_tone = "Symmetrical Planar • Pastel Warmth"
    else:  # Deakins default
        bg_dark, bg_mid, accent, beam_color = "#050C16", "#0F2036", "#60A5FA", "#93C5FD"
        atmosphere_tone = "Motivated Daylight • Spherical Clarity"

    # Contextual Artwork Elements Based on Prompt & Camera Perspective
    is_great_hall_organ = any(k in prompt_lower for k in ["organ", "great_hall", "nave", "church", "gothic", "stained", "sanctuary"])
    is_rain_square = any(k in prompt_lower for k in ["rain", "square", "police", "vehicle", "street", "siren", "spotlight", "car"])
    is_eyes_face = any(k in prompt_lower for k in ["eye", "eyes", "face", "expression", "portrait", "stare", "tears", "trembling"])
    is_hands_detail = any(k in prompt_lower for k in ["hand", "hands", "finger", "fingers", "macro", "keys", "dossier", "stop", "knob"])
    is_anamorphic = any(k in prompt_lower for k in ["anamorphic", "streak", "horizontal flare", "oval bokeh"])
    is_haze = any(k in prompt_lower for k in ["haze", "fog", "smoke", "volumetric", "dust", "motes"])
    is_dutch = any(k in prompt_lower for k in ["dutch", "tilted", "off-kilter", "kinetic"])

    scene_artwork_svg = ""

    if is_great_hall_organ:
        if camera_letter == "A" or "wide" in prompt_lower or "panoramic" in prompt_lower:
            # CAMERA A: Wide Master Great Hall Architecture & Soaring Pipes
            scene_artwork_svg = f"""
            <!-- Vaulted Great Hall Arches -->
            <path d="M {width//6} {height} Q {width//6} {height//4} {width//2} 50 Q {5*width//6} {height//4} {5*width//6} {height}" fill="none" stroke="{accent}" stroke-width="2" stroke-opacity="0.35" />
            <path d="M {width//4} {height} Q {width//4} {height//3} {width//2} 80 Q {3*width//4} {height//3} {3*width//4} {height}" fill="none" stroke="{accent}" stroke-width="1.5" stroke-opacity="0.25" />
            
            <!-- Stained Glass Rose Window -->
            <circle cx="{width//2}" cy="110" r="45" fill="none" stroke="{beam_color}" stroke-width="2" stroke-opacity="0.6" />
            <circle cx="{width//2}" cy="110" r="30" fill="{accent}" fill-opacity="0.15" stroke="{beam_color}" stroke-width="1" stroke-dasharray="4,4" />
            
            <!-- Colossal Pipe Organ Facade -->
            <g transform="translate({width//2 - 90}, {height - 210})" stroke="{accent}" stroke-width="1.5" fill="#0A111E">
              <rect x="0" y="30" width="180" height="150" rx="4" />
              <!-- Organ Pipes Array -->
              <rect x="15" y="0" width="8" height="130" fill="{accent}" fill-opacity="0.3" />
              <rect x="30" y="-15" width="10" height="145" fill="{accent}" fill-opacity="0.4" />
              <rect x="45" y="-35" width="12" height="165" fill="{accent}" fill-opacity="0.5" />
              <rect x="62" y="-55" width="14" height="185" fill="{accent}" fill-opacity="0.6" />
              <rect x="83" y="-70" width="16" height="200" fill="{beam_color}" fill-opacity="0.7" />
              <rect x="104" y="-55" width="14" height="185" fill="{accent}" fill-opacity="0.6" />
              <rect x="123" y="-35" width="12" height="165" fill="{accent}" fill-opacity="0.5" />
              <rect x="140" y="-15" width="10" height="145" fill="{accent}" fill-opacity="0.4" />
              <rect x="155" y="0" width="8" height="130" fill="{accent}" fill-opacity="0.3" />
            </g>

            <!-- Organist Silhouette (LEAD) -->
            <g transform="translate({width//2 - 20}, {height - 85})" fill="#02060D">
              <circle cx="20" cy="15" r="10" />
              <path d="M 5 45 Q 20 25 35 45 Z" />
            </g>

            <!-- Volumetric Light Beam Shafts -->
            <polygon points="{width//2},110 {width//2 + 40},110 {width//2 + 180},{height} {width//2 - 60},{height}" fill="{beam_color}" fill-opacity="0.15" />
            <polygon points="{width//2},110 {width//2 - 30},110 {width//4},{height} {width//6},{height}" fill="{beam_color}" fill-opacity="0.10" />
            """
        elif camera_letter == "B" or "ots" in prompt_lower or "shoulder" in prompt_lower:
            # CAMERA B: Medium Over-The-Shoulder (OTS) onto Organ Console & Music
            scene_artwork_svg = f"""
            <!-- Vault background blur -->
            <path d="M 0 {height//3} Q {width//2} 20 {width} {height//3}" fill="none" stroke="{accent}" stroke-width="1.5" stroke-opacity="0.2" />
            
            <!-- Foreground Character Silhouette (Shoulder in Frame) -->
            <path d="M -40 {height+40} Q 60 {height//2} 160 {height+40} Z" fill="#02060D" stroke="{accent}" stroke-width="1" stroke-opacity="0.4" />
            <circle cx="70" cy="{height//2 + 40}" r="45" fill="#02060D" />

            <!-- LEAD at Keyboard (Facing Console) -->
            <g transform="translate({width//2 - 40}, {height//2 - 30})">
              <!-- Organ Console Tiers & Sheet Music -->
              <rect x="40" y="40" width="220" height="120" rx="4" fill="#0A111E" stroke="{accent}" stroke-width="1.5" />
              <rect x="60" y="20" width="60" height="40" rx="2" fill="#FFFFFF" fill-opacity="0.1" stroke="{beam_color}" stroke-width="1" />
              <!-- Keyboard Keys -->
              <line x1="50" y1="90" x2="250" y2="90" stroke="{accent}" stroke-width="2" />
              <line x1="50" y1="110" x2="250" y2="110" stroke="{accent}" stroke-width="2" />
              
              <!-- LEAD Head & Concentrated Profile -->
              <circle cx="110" cy="0" r="22" fill="#030712" stroke="{beam_color}" stroke-width="1" />
              <path d="M 90 40 Q 110 20 130 40 Z" fill="#030712" />
            </g>

            <!-- Warm Key Light Beam across face -->
            <polygon points="{width},0 {width - 120},0 {width//2 - 40},{height//2 + 50} {width//2 + 80},{height}" fill="{beam_color}" fill-opacity="0.18" />
            """
        else:
            # CAMERA C: Tight Macro / Profile Detail on Organ Stops & Hands
            scene_artwork_svg = f"""
            <!-- Extreme Close-Up Console & Hands Staging -->
            <g transform="translate({width//4}, {height//4})">
              <!-- Giant Organ Stop Knobs -->
              <circle cx="50" cy="50" r="28" fill="#0A111E" stroke="{beam_color}" stroke-width="2" />
              <circle cx="50" cy="50" r="16" fill="{accent}" fill-opacity="0.4" />
              <text x="35" y="55" font-family="sans-serif" font-size="10" font-weight="bold" fill="#FFFFFF">VOX</text>

              <circle cx="130" cy="40" r="24" fill="#0A111E" stroke="{accent}" stroke-width="2" />
              <circle cx="130" cy="40" r="14" fill="{accent}" fill-opacity="0.4" />

              <circle cx="210" cy="60" r="30" fill="#0A111E" stroke="{beam_color}" stroke-width="2" />
              <circle cx="210" cy="60" r="18" fill="{beam_color}" fill-opacity="0.5" />
              <text x="195" y="65" font-family="sans-serif" font-size="10" font-weight="bold" fill="#FFFFFF">PRIN</text>

              <!-- Ivory Keyboard Keys Macro Perspective -->
              <g transform="translate(0, 100)" stroke="{accent}" stroke-width="1.5">
                <rect x="0" y="0" width="450" height="70" rx="4" fill="#0F172A" />
                <line x1="40" y1="0" x2="40" y2="70" />
                <line x1="80" y1="0" x2="80" y2="70" />
                <line x1="120" y1="0" x2="120" y2="70" />
                <line x1="160" y1="0" x2="160" y2="70" />
                <line x1="200" y1="0" x2="200" y2="70" />
                <line x1="240" y1="0" x2="240" y2="70" />
                <line x1="280" y1="0" x2="280" y2="70" />
                <line x1="320" y1="0" x2="320" y2="70" />
                <!-- Black Sharps -->
                <rect x="25" y="0" width="16" height="42" fill="{beam_color}" fill-opacity="0.8" />
                <rect x="65" y="0" width="16" height="42" fill="{beam_color}" fill-opacity="0.8" />
                <rect x="145" y="0" width="16" height="42" fill="{beam_color}" fill-opacity="0.8" />
                <rect x="185" y="0" width="16" height="42" fill="{beam_color}" fill-opacity="0.8" />
                <rect x="225" y="0" width="16" height="42" fill="{beam_color}" fill-opacity="0.8" />
              </g>

              <!-- Expressive Hands Striking Keys (Silhouette) -->
              <path d="M 120 70 Q 160 40 210 90 Q 240 105 260 120 L 150 140 Z" fill="#030712" stroke="{beam_color}" stroke-width="1.5" />
            </g>

            <!-- Razor Shallow Depth of Field Highlight -->
            <ellipse cx="{width//2}" cy="{height//2 + 30}" rx="140" ry="30" fill="{beam_color}" fill-opacity="0.15" filter="url(#glow)" />
            """
    elif is_rain_square:
        if camera_letter == "A" or "wide" in prompt_lower:
            # CAMERA A: Wide Master of Rainy Square & Vehicle Sirens
            scene_artwork_svg = f"""
            <!-- Wet Reflective Cobblestone Horizon -->
            <line x1="0" y1="{2*height//3}" x2="{width}" y2="{2*height//3}" stroke="{accent}" stroke-width="2" stroke-opacity="0.4" />
            
            <!-- Rain Streaks Angle -->
            <g stroke="{beam_color}" stroke-width="1" stroke-opacity="0.35" stroke-dasharray="2,12">
              <line x1="100" y1="0" x2="60" y2="{height}" />
              <line x1="250" y1="0" x2="210" y2="{height}" />
              <line x1="400" y1="0" x2="360" y2="{height}" />
              <line x1="550" y1="0" x2="510" y2="{height}" />
              <line x1="700" y1="0" x2="660" y2="{height}" />
              <line x1="850" y1="0" x2="810" y2="{height}" />
            </g>

            <!-- Great Hall Facade in Background -->
            <path d="M {width//3} {2*height//3} L {width//3} 60 L {width//2} 10 L {2*width//3} 60 L {2*width//3} {2*height//3}" fill="none" stroke="{accent}" stroke-width="1.5" stroke-opacity="0.3" />

            <!-- Tactical Vehicles with Blinding Headlights -->
            <g transform="translate({width//5}, {2*height//3 - 35})" fill="#0A111E" stroke="{accent}" stroke-width="1">
              <rect x="0" y="10" width="120" height="40" rx="4" />
              <!-- Flashing Blue Siren -->
              <circle cx="60" cy="5" r="6" fill="#3B82F6" filter="url(#glow)" />
              <!-- Headlight Cones -->
              <polygon points="120,30 {width},80 {width},250 120,40" fill="#FFFFFF" fill-opacity="0.25" />
            </g>

            <g transform="translate({3*width//5}, {2*height//3 - 25})" fill="#0A111E" stroke="{accent}" stroke-width="1">
              <rect x="0" y="10" width="110" height="35" rx="4" />
              <circle cx="55" cy="5" r="5" fill="#EF4444" filter="url(#glow)" />
              <polygon points="0,25 -200,80 -200,220 0,35" fill="#FFFFFF" fill-opacity="0.2" />
            </g>
            """
        elif camera_letter == "B" or "vance" in prompt_lower or "commander" in prompt_lower:
            # CAMERA B: Low-Angle Medium on Commander Vance
            scene_artwork_svg = f"""
            <!-- Wet Asphalt Reflection Ground -->
            <rect x="0" y="{3*height//4}" width="{width}" height="{height//4}" fill="{bg_dark}" />
            <line x1="0" y1="{3*height//4}" x2="{width}" y2="{3*height//4}" stroke="{accent}" stroke-width="1.5" stroke-opacity="0.5" />

            <!-- Commander Vance Low-Angle Heroic Silhouette -->
            <g transform="translate({width//2 - 60}, {height//4})" fill="#030712" stroke="{beam_color}" stroke-width="1">
              <circle cx="60" cy="30" r="24" />
              <path d="M 15 80 L 105 80 L 120 220 L 0 220 Z" />
              <!-- Raised Tactical Flashlight / Spotlight -->
              <line x1="85" y1="80" x2="135" y2="40" stroke="{accent}" stroke-width="6" />
              <circle cx="138" cy="38" r="8" fill="#FFFFFF" filter="url(#glow)" />
            </g>

            <!-- Blinding Searchlight Beam Aimed at Facade -->
            <polygon points="{width//2 + 78},{height//4 + 38} {width},0 {width},{height//2} {width//2 + 85},{height//4 + 45}" fill="#FFFFFF" fill-opacity="0.35" />
            <polygon points="{width//2 + 78},{height//4 + 38} 0,0 0,{height//3} {width//2 + 70},{height//4 + 42}" fill="#38BDF8" fill-opacity="0.20" />
            """
        else:
            # CAMERA C: Dutch Angle Kinetic Macro of Sirens & Splashing Rain
            scene_artwork_svg = f"""
            <!-- Dutch Angle Horizon Line (Tilted 15 degrees) -->
            <line x1="0" y1="{height - 50}" x2="{width}" y2="100" stroke="{accent}" stroke-width="3" stroke-opacity="0.6" />

            <!-- Tactical Vehicle Grille & Flashing Strobe -->
            <g transform="translate({width//3}, {height//3}) rotate(12)" fill="#0F172A" stroke="{beam_color}" stroke-width="2">
              <rect x="0" y="0" width="260" height="120" rx="8" />
              <circle cx="60" cy="60" r="22" fill="#3B82F6" filter="url(#glow)" />
              <circle cx="200" cy="60" r="22" fill="#EF4444" filter="url(#glow)" />
              <line x1="0" y1="40" x2="260" y2="40" stroke="{accent}" stroke-width="2" />
              <line x1="0" y1="80" x2="260" y2="80" stroke="{accent}" stroke-width="2" />
            </g>

            <!-- Splashing Water Droplets -->
            <g fill="{beam_color}" opacity="0.6">
              <circle cx="{width//4}" cy="{height - 60}" r="3" />
              <circle cx="{width//4 + 15}" cy="{height - 85}" r="2" />
              <circle cx="{width//2 + 40}" cy="{height - 40}" r="4" />
              <circle cx="{3*width//4}" cy="{height - 70}" r="3" />
            </g>
            """
    elif is_eyes_face:
        # Prompt explicitly mentions eyes or emotional facial close-up
        scene_artwork_svg = f"""
        <!-- Intense Psychological Eye Level Portrait Silhouette -->
        <g transform="translate({width//2 - 140}, {height//4})" fill="#020617" stroke="{beam_color}" stroke-width="2">
          <!-- Left Eye -->
          <ellipse cx="70" cy="60" rx="42" ry="24" fill="#0A111E" />
          <circle cx="70" cy="60" r="16" fill="{accent}" />
          <circle cx="70" cy="60" r="7" fill="#000000" />
          <circle cx="65" cy="55" r="4" fill="#FFFFFF" filter="url(#glow)" />

          <!-- Right Eye -->
          <ellipse cx="210" cy="60" rx="42" ry="24" fill="#0A111E" />
          <circle cx="210" cy="60" r="16" fill="{accent}" />
          <circle cx="210" cy="60" r="7" fill="#000000" />
          <circle cx="205" cy="55" r="4" fill="#FFFFFF" filter="url(#glow)" />

          <!-- Eyebrows / Furrowed Expression -->
          <path d="M 30 35 Q 70 20 110 38" fill="none" stroke="{beam_color}" stroke-width="4" stroke-linecap="round" />
          <path d="M 170 38 Q 210 20 250 35" fill="none" stroke="{beam_color}" stroke-width="4" stroke-linecap="round" />
        </g>
        <!-- Razor-thin Eye-light slit -->
        <line x1="0" y1="{height//2 - 20}" x2="{width}" y2="{height//2 - 20}" stroke="{beam_color}" stroke-width="3" stroke-opacity="0.4" filter="url(#glow)" />
        """
    else:
        # Generic Composition
        if shot_size in ["WS", "EWS"] or "wide" in prompt_lower:
            scene_artwork_svg = f"""
            <line x1="0" y1="{2*height//3}" x2="{width}" y2="{2*height//3}" stroke="{accent}" stroke-width="1.5" stroke-opacity="0.4" />
            <polygon points="{width//4},0 {3*width//4},0 {width},{height} {width//6},{height}" fill="{beam_color}" fill-opacity="0.10" />
            <g transform="translate({width//2 - 20}, {2*height//3 - 35})" fill="#030712">
              <circle cx="20" cy="12" r="8" />
              <path d="M 5 35 Q 20 20 35 35 Z" />
            </g>
            """
        elif shot_size in ["CU", "ECU"] or "close-up" in prompt_lower:
            scene_artwork_svg = f"""
            <g transform="translate({width//2 - 70}, {height//2 - 60})" fill="#030712" stroke="{beam_color}" stroke-width="1.5">
              <circle cx="70" cy="45" r="38" fill="#0A111E" filter="url(#glow)" />
              <path d="M 30 110 Q 70 80 110 110 Z" fill="#030712" />
            </g>
            <polygon points="{width},0 {width//2 + 50},{height//2} {width//2 + 50},{height} {width},{height}" fill="{beam_color}" fill-opacity="0.15" />
            """
        else:
            scene_artwork_svg = f"""
            <g transform="translate({width//2 - 40}, {height//2 - 40})" fill="#030712" stroke="{accent}" stroke-width="1.2">
              <circle cx="40" cy="25" r="18" fill="#0A111E" filter="url(#glow)" />
              <path d="M 10 70 Q 40 45 70 70 Z" fill="#030712" />
            </g>
            <polygon points="{width//4},0 {3*width//4},0 {width},{height} {width//6},{height}" fill="{beam_color}" fill-opacity="0.10" />
            """

    # Add Anamorphic Horizontal Streak if requested in prompt or preset
    anamorphic_streak_svg = ""
    if is_anamorphic or "Fraser" in dop_preset:
        anamorphic_streak_svg = f"""
        <line x1="0" y1="{height//2}" x2="{width}" y2="{height//2}" stroke="{beam_color}" stroke-width="3" stroke-opacity="0.65" filter="url(#glow)" />
        <line x1="{width//4}" y1="{height//2}" x2="{3*width//4}" y2="{height//2}" stroke="#FFFFFF" stroke-width="1.5" stroke-opacity="0.85" />
        """

    # Add Atmospheric Fog / Dust Particles if requested
    haze_particles_svg = ""
    if is_haze:
        haze_particles_svg = f"""
        <g fill="{beam_color}" fill-opacity="0.3" filter="url(#glow)">
          <circle cx="{width//5}" cy="{height//3}" r="18" />
          <circle cx="{2*width//5}" cy="{2*height//3}" r="26" />
          <circle cx="{3*width//5}" cy="{height//4}" r="22" />
          <circle cx="{4*width//5}" cy="{height//2}" r="30" />
        </g>
        """

    clean_prompt = html.escape(prompt[:120] + ("..." if len(prompt) > 120 else ""))

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
      <feGaussianBlur stdDeviation="4" result="coloredBlur"/>
      <feMerge>
        <feMergeNode in="coloredBlur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>

  <!-- Cinema Frame Background -->
  <rect width="{width}" height="{height}" fill="url(#frame-grad)" />

  <!-- Volumetric Atmosphere & Silhouette Grid -->
  <g opacity="0.12">
    <line x1="0" y1="{height//2}" x2="{width}" y2="{height//2}" stroke="{accent}" stroke-width="1" stroke-dasharray="4,8" />
    <line x1="{width//3}" y1="0" x2="{width//3}" y2="{height}" stroke="{accent}" stroke-width="1" stroke-dasharray="4,8" />
    <line x1="{2*width//3}" y1="0" x2="{2*width//3}" y2="{height}" stroke="{accent}" stroke-width="1" stroke-dasharray="4,8" />
  </g>

  <!-- Prompt-Driven Scene Artwork -->
  {scene_artwork_svg}

  <!-- Atmospheric Haze & Particles -->
  {haze_particles_svg}

  <!-- Anamorphic Streak -->
  {anamorphic_streak_svg}

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
    <rect x="25" y="15" width="130" height="24" rx="4" fill="#0F172A" fill-opacity="0.9" stroke="#334155" stroke-width="1" />
    <text x="35" y="31" fill="#F8FAFC">SC {scene_number} / SH {shot_number} • CAM {camera_letter}</text>

    <rect x="165" y="15" width="60" height="24" rx="4" fill="{accent}" fill-opacity="0.2" stroke="{accent}" stroke-width="1" />
    <text x="177" y="31" fill="{accent}">{shot_size}</text>

    <!-- Lens & DoP Metadata Right -->
    <rect x="{width-235}" y="15" width="210" height="24" rx="4" fill="#0F172A" fill-opacity="0.9" stroke="#334155" stroke-width="1" />
    <text x="{width-223}" y="31" fill="#CBD5E1">{focal_length}mm • {aperture} • {aspect_ratio}</text>
  </g>

  <!-- Bottom Prompt & Tone Subtitle Bar -->
  <g font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif">
    <rect x="25" y="{height-42}" width="{width-50}" height="28" rx="4" fill="#020617" fill-opacity="0.9" stroke="#1E293B" stroke-width="1" />
    <circle cx="38" cy="{height-28}" r="4" fill="{beam_color}" />
    <text x="50" y="{height-24}" font-size="10" font-weight="600" fill="#E2E8F0">{clean_prompt}</text>
    <text x="{width-240}" y="{height-24}" font-size="9" font-weight="600" fill="{beam_color}">CAM {camera_letter} • {dop_preset}</text>
  </g>
</svg>"""

    b64_svg = base64.b64encode(svg_content.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{b64_svg}"
