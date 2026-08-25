"""
Cinematography DoP Presets & Technical Matrix for CineSpine.
Provides curated Director of Photography aesthetic profiles,
technical lens/lighting parameters, and override resolvers.
"""
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class DoPSpecification(BaseModel):
    dop_preset: str = "Roger Deakins"
    focal_length: int = 35  # in mm
    lens_type: str = "Spherical Prime"  # Spherical Prime, Anamorphic 2x, Vintage Super Baltar, Cooke S4
    aperture: str = "T2.8"  # T1.3, T1.8, T2.0, T2.8, T4.0, T5.6, T8.0
    sensor_format: str = "Large Format 35mm"  # Super 35, Full Frame 35mm, Large Format 65mm
    camera_body: str = "ARRI ALEXA 35"
    fps: float = 24.0
    lighting_style: str = "Natural Motivated Diffused"
    lighting_ratio: str = "3:1 (Natural Contrast)"  # 1:1 (Flat), 2:1, 3:1, 4:1 (Dramatic), 8:1 (Chiaroscuro), 16:1 (Noir)
    color_temperature_k: int = 5600  # 3200 (Warm Tungsten), 4300 (Neutral), 5600 (Daylight), 6500 (Overcast Cool)
    color_palette: str = "Naturalist organic tones, warm skin highlights, deep muted shadow roll-off"
    lut_emulation: str = "Kodak 5219 Vision3 500T"
    mood_notes: str = "Soft motivated side lighting with deep natural shadows"


DOP_MASTER_PRESETS: Dict[str, Dict[str, Any]] = {
    "Roger Deakins": {
        "name": "Roger Deakins (Natural Motivated)",
        "tagline": "Organic Motivated Light & Spherical Mastery",
        "description": "Characterized by practical source lighting, clean spherical Arri Master Primes, deep organic shadow details, and patient camera framing.",
        "focal_length": 35,
        "lens_type": "Spherical Prime (ARRI Master Prime)",
        "aperture": "T2.8",
        "sensor_format": "Large Format 35mm",
        "camera_body": "ARRI ALEXA Mini LF",
        "lighting_style": "Natural Motivated Diffused",
        "lighting_ratio": "4:1 (Organic Depth)",
        "color_temperature_k": 5600,
        "color_palette": "Earthy ochres, deep stone greys, golden motivated sunlight shafts",
        "lut_emulation": "Kodak 5219 Vision3",
        "prompt_style_tag": "cinematic still in the style of Roger Deakins, natural motivated lighting, volumetric daylight, master prime clarity, 35mm lens, 2.39:1 scope, 8k photorealistic film still"
    },
    "David Fincher": {
        "name": "David Fincher / Jeff Cronenweth (Low-Key Neo-Noir)",
        "tagline": "Clinical Precision, Cold Low-Key Chiaroscuro",
        "description": "Controlled studio environments, deep contrast ratios, subtle greenish-amber undertones, locked-off or fluid tracking, and razor-sharp digital sensors.",
        "focal_length": 28,
        "lens_type": "Leica Summilux-C",
        "aperture": "T2.0",
        "sensor_format": "Full Frame 35mm",
        "camera_body": "RED V-Raptor 8K",
        "lighting_style": "Low-Key Chiaroscuro Noir",
        "lighting_ratio": "8:1 (Deep Contrast)",
        "color_temperature_k": 4300,
        "color_palette": "Desaturated teal, olive green, warm tungsten edge light against pitch blacks",
        "lut_emulation": "Bleach Bypass Custom LUT",
        "prompt_style_tag": "cinematic film still in the style of David Fincher, low-key lighting, deep shadows, controlled amber and green undertones, 28mm wide angle, neo-noir atmosphere, ultra-sharp 8k film capture"
    },
    "Greig Fraser": {
        "name": "Greig Fraser (Soft Atmospheric Anamorphic)",
        "tagline": "Tactile Texture, Heavy Silhouettes & Haze",
        "description": "Tactile cinematic atmosphere with soft high contrast, anamorphic oval bokeh, volumetric haze, atmospheric smoke, and bold expressive silhouettes.",
        "focal_length": 40,
        "lens_type": "Anamorphic 2x (Atlas Orion / Panavision C-Series)",
        "aperture": "T1.8",
        "sensor_format": "Large Format 65mm",
        "camera_body": "ARRI ALEXA 65",
        "lighting_style": "Atmospheric Backlit Silhouette",
        "lighting_ratio": "6:1 (Soft Heavy Contrast)",
        "color_temperature_k": 3200,
        "color_palette": "Monochromatic amber, heavy charcoal shadows, saturated sodium-vapor practicals",
        "lut_emulation": "Film Print Kodak 2383",
        "prompt_style_tag": "cinematic film still in the style of Greig Fraser, atmospheric haze, heavy silhouette lighting, soft 2x anamorphic lens flare, deep tactile texture, 2.39:1 anamorphic scope, 8k masterpiece"
    },
    "Gordon Willis": {
        "name": "Gordon Willis (Prince of Shadows)",
        "tagline": "Top-Lit Practicals & Underexposed Warmth",
        "description": "Bold underexposure, top-lit amber practical lamps, warm Rembrandt lighting, and dignified classical staging (The Godfather, Manhattan).",
        "focal_length": 50,
        "lens_type": "Vintage Super Baltar",
        "aperture": "T2.8",
        "sensor_format": "Super 35",
        "camera_body": "Panavision Panaflex Gold II (35mm)",
        "lighting_style": "Top-Lit Rembrandt Chiaroscuro",
        "lighting_ratio": "16:1 (Extreme Low-Key)",
        "color_temperature_k": 3000,
        "color_palette": "Deep sepia, dark espresso shadows, warm golden skin highlights",
        "lut_emulation": "Kodak 5254 35mm Vintage",
        "prompt_style_tag": "cinematic still in the style of Gordon Willis, top-lit warm practical light, underexposed rich dark shadows, classic 35mm film grain, 50mm vintage lens perspective, dramatic portrait"
    },
    "Emmanuel Lubezki": {
        "name": "Emmanuel Lubezki (Fluid Naturalist)",
        "tagline": "Ultra-Wide Natural Light & Continuous Motion",
        "description": "Expansive ultra-wide lenses (14mm-24mm) positioned close to actors, natural golden hour sky light, and long continuous fluid Steadicam/Gimbal movements.",
        "focal_length": 21,
        "lens_type": "Master Prime Ultra-Wide",
        "aperture": "T1.4",
        "sensor_format": "Large Format 35mm",
        "camera_body": "ARRI ALEXA Mini LF",
        "lighting_style": "Available Golden Hour Natural",
        "lighting_ratio": "2:1 (Gentle Wrap)",
        "color_temperature_k": 6000,
        "color_palette": "Vibrant natural greens, azure blue skies, luminous golden backlight",
        "lut_emulation": "Arri LogC4 Naturalist",
        "prompt_style_tag": "cinematic still in the style of Emmanuel Lubezki, ultra-wide 21mm lens perspective close to subject, magical golden hour natural light, expansive sky, fluid motion feel, 8k photorealistic"
    },
    "Wes Anderson": {
        "name": "Wes Anderson / Robert Yeoman (Symmetrical Pastel)",
        "tagline": "Symmetrical 1-Point Perspective & Pastel Palette",
        "description": "Obsessive planar symmetry, flat high-key fill lighting, whimsical pastel color schemes, and crisp deep-focus theatrical framing.",
        "focal_length": 40,
        "lens_type": "Anamorphic Primo (Symmetrical)",
        "aperture": "T5.6",
        "sensor_format": "Super 35 (3-perf)",
        "camera_body": "Arricam ST 35mm",
        "lighting_style": "High-Key Evenly Diffused Studio",
        "lighting_ratio": "1.5:1 (Flat Bright)",
        "color_temperature_k": 5000,
        "color_palette": "Mustard yellow, pastel pink, soft mint green, symmetrical saturated warmth",
        "lut_emulation": "Fujifilm Eterna 250D",
        "prompt_style_tag": "cinematic still in the style of Wes Anderson, perfectly symmetrical composition, pastel color palette, soft flat high-key lighting, whimsical retro details, 2.39:1 scope, 8k crisp film capture"
    }
}


def resolve_dop_specification(
    preset_name: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
    custom_prompt: Optional[str] = None
) -> DoPSpecification:
    """
    Resolves DoP parameters by combining a Master Preset with optional manual overrides
    and natural language prompt annotations.
    """
    preset_key = preset_name if preset_name in DOP_MASTER_PRESETS else "Roger Deakins"
    preset_data = DOP_MASTER_PRESETS[preset_key]

    spec = DoPSpecification(
        dop_preset=preset_key,
        focal_length=preset_data.get("focal_length", 35),
        lens_type=preset_data.get("lens_type", "Spherical Prime"),
        aperture=preset_data.get("aperture", "T2.8"),
        sensor_format=preset_data.get("sensor_format", "Large Format 35mm"),
        camera_body=preset_data.get("camera_body", "ARRI ALEXA 35"),
        fps=24.0,
        lighting_style=preset_data.get("lighting_style", "Natural Motivated Diffused"),
        lighting_ratio=preset_data.get("lighting_ratio", "3:1"),
        color_temperature_k=preset_data.get("color_temperature_k", 5600),
        color_palette=preset_data.get("color_palette", "Naturalist"),
        lut_emulation=preset_data.get("lut_emulation", "Kodak 5219"),
        mood_notes=custom_prompt or preset_data.get("description", "")
    )

    if overrides:
        for k, v in overrides.items():
            if hasattr(spec, k) and v is not None:
                setattr(spec, k, v)

    return spec
