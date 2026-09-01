import base64
import logging
import os
from typing import Dict, Any, Optional

from backend.app.script.cache_service import get_cached_response, set_cached_response, generate_hash

logger = logging.getLogger(__name__)

# Tried in order until one returns an image.
#
# Imagen is not among them any more. `imagen-3.0-generate-002` was called two
# ways here and neither could ever have worked on a Gemini Developer API key:
# the SDK refuses `generate_images` outside Gemini Enterprise Agent Platform
# mode, and the REST `:predict` endpoint 404s because ListModels does not offer
# any Imagen model to this key at all. Google's own deprecation notice points
# the same way -- image generation goes through `generate_content` now.
#
# Overridable because the right model is a deployment question, not a fact
# about this code: a Vertex-backed deployment may have models this list does
# not name, and a preview name can be retired between hackathons.
DEFAULT_IMAGE_MODELS = "gemini-3.1-flash-image,gemini-3-pro-image,gemini-2.5-flash-image"


def image_models() -> list[str]:
    """The image models to try, fastest first."""
    raw = os.getenv("CINESPINE_IMAGE_MODELS") or DEFAULT_IMAGE_MODELS
    return [m.strip() for m in raw.split(",") if m.strip()]


class _NoImageReturned(Exception):
    """The model answered, but with no image in it."""


async def _generate_with(model: str, api_key: str, compiled_prompt: str) -> Dict[str, Any]:
    """One generate_content call, returning the first inline image part."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=compiled_prompt,
        # TEXT stays in the list because some image models refuse an
        # IMAGE-only response and answer with an error instead of a picture.
        config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
    )

    for candidate in response.candidates or []:
        for part in (getattr(candidate.content, "parts", None) or []):
            blob = getattr(part, "inline_data", None)
            if blob is not None and blob.data:
                mime = blob.mime_type or "image/png"
                b64_img = base64.b64encode(blob.data).decode("utf-8")
                return {
                    "image_url": f"data:{mime};base64,{b64_img}",
                    "compiled_prompt": compiled_prompt,
                    "provider": f"Google Gemini image ({model})",
                }

    # A text-only answer is usually the model explaining a refusal, and that
    # sentence is worth more in the log than "no image".
    said = " ".join(
        (part.text or "").strip()
        for candidate in (response.candidates or [])
        for part in (getattr(candidate.content, "parts", None) or [])
        if getattr(part, "text", None)
    )
    raise _NoImageReturned(said[:200] or "no image part in the response")

def build_cinematic_prompt(
    prompt: str,
    shot_size: str,
    focal_length: int,
    aperture: str,
    dop_preset: str,
    lighting_ratio: str,
    color_temp_k: int,
    lut_emulation: str,
    character_details: Optional[str] = None
) -> str:
    """Constructs the highly specific cinematic prompt token block."""
    prompt_tokens = [
        f"Cinematic 35mm motion picture film still",
        f"Shot Size: {shot_size}",
        f"{focal_length}mm anamorphic prime lens",
        f"Aperture: {aperture} (shallow depth of field, creamy bokeh)" if aperture in ["T1.3", "T1.4", "T2.0", "T2.8"] else f"Aperture: {aperture}",
        f"Cinematography by {dop_preset}",
        f"Lighting: {lighting_ratio} contrast ratio, {color_temp_k}K color temperature",
        f"Film Stock: {lut_emulation}",
    ]
    if character_details:
        prompt_tokens.append(f"Subject: {character_details}")
    prompt_tokens.append(f"Action/Scene: {prompt}")
    prompt_tokens.append("8k resolution, photorealistic, authentic 35mm film grain, anamorphic lens flares, masterpiece")
    return ", ".join(t.strip() for t in prompt_tokens if t.strip())


def _placeholder_asset(prompt: str, camera_letter: str) -> str:
    """Picks a bundled placeholder still when no generator is reachable."""
    from backend.app.script.storyboard_generator import detect_setting

    cam = (camera_letter or "A").lower()
    if cam not in ("a", "b", "c"):
        cam = "a"
    return f"/previz/{detect_setting(prompt)}_cam_{cam}.jpg"


async def generate_ai_cinematic_image(
    prompt: str,
    scene_number: str = "1",
    shot_number: str = "1",
    shot_size: str = "WS",
    focal_length: int = 35,
    aperture: str = "T2.8",
    dop_preset: str = "Roger Deakins",
    camera_letter: str = "A",
    lighting_ratio: str = "4:1",
    color_temp_k: int = 5600,
    lut_emulation: str = "Kodak Vision3 500T 5219",
    aspect_ratio: str = "2.39:1",
    character_details: Optional[str] = None,
    economy_mode: bool = False
) -> Dict[str, Any]:
    """
    Main router for generating images. It caches identical requests using SQLite.
    If economy_mode=True, it skips external generation and uses a bundled still.
    """
    compiled_prompt = build_cinematic_prompt(
        prompt, shot_size, focal_length, aperture, dop_preset,
        lighting_ratio, color_temp_k, lut_emulation, character_details
    )

    # 1. Check SQLite Cache
    req_hash = generate_hash(
        compiled_prompt=compiled_prompt,
        aspect_ratio=aspect_ratio,
        camera_letter=camera_letter,
        economy_mode=economy_mode
    )
    cached = get_cached_response(req_hash)
    if cached:
        logger.info("Cache hit for %s", req_hash)
        return cached

    logger.info("Cache miss for %s (economy_mode=%s)", req_hash, economy_mode)

    # Caches and returns. Only real generations go through this: caching a
    # fallback would freeze a transient outage into a permanent one, because
    # the retry that would have fixed it never runs.
    def _finalize(result: Dict[str, Any]) -> Dict[str, Any]:
        set_cached_response(req_hash, result)
        return result

    # 2. Google's image models, tried in order.
    failures: list[str] = []
    if not economy_mode:
        gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if gemini_key:
            for model in image_models():
                try:
                    return _finalize(await _generate_with(model, gemini_key, compiled_prompt))
                except _NoImageReturned as e:
                    failures.append(f"{model}: {e}")
                except Exception as e:
                    failures.append(f"{model}: {type(e).__name__}: {e}")
        else:
            failures.append("no GEMINI_API_KEY or GOOGLE_API_KEY in the environment")

    # 3. Local placeholder. Deliberately NOT cached: it means every generator
    #    was unavailable, which is a transient condition the next request should
    #    be free to retry.
    #
    # Logged at ERROR and named in the payload. The previous version fell
    # through here silently whenever the REST call answered anything but 200,
    # so a bundled still was served under a button that says "Execute & Render
    # AI Concept" with nothing anywhere saying it had not been rendered.
    if not economy_mode:
        logger.error(
            "No image generator answered; serving a bundled placeholder. Tried: %s",
            "; ".join(failures) or "nothing",
        )
    return {
        "image_url": _placeholder_asset(prompt, camera_letter),
        "compiled_prompt": compiled_prompt,
        "provider": (
            "CineSpine Previz Placeholder (economy mode)" if economy_mode
            else "CineSpine Previz Placeholder (no generator available)"
        ),
        "generator_failures": failures,
    }


async def generate_character_portrait_image(
    character_name: str,
    actor_reference: str,
    look_and_costume: str,
    facial_features: str,
    role: str = "Key Character",
    dop_preset: str = "Roger Deakins",
    lighting_ratio: str = "4:1",
    color_temp_k: int = 5600,
    lut_emulation: str = "Kodak Vision3 500T 5219",
    custom_mood: Optional[str] = None,
    economy_mode: bool = False
) -> Dict[str, Any]:
    """
    Generates a high-fidelity 35mm motion picture character portrait / headshot
    locking the actor appearance, facial features, costume, and DoP portrait lighting.
    """
    tokens = [
        f"Extremely photorealistic and highly detailed cinematic 35mm portrait headshot of {character_name}",
        f"Role / Archetype: {role}",
        f"Actor Appearance / Casting Reference: {actor_reference}",
        f"Detailed Facial Features: {facial_features}",
        f"Costume, Wardrobe, and Texture: {look_and_costume}",
        f"Hyper-realistic textures, visible skin pores, natural imperfections, lifelike portrait",
        f"85mm portrait prime lens at T1.4 aperture, creamy bokeh background",
        f"Cinematography Style: {dop_preset} portrait lighting",
        f"Color Temperature: {color_temp_k}K, {lighting_ratio} lighting contrast ratio",
        f"{lut_emulation} film stock grade",
        f"8k resolution, perfectly exposed eye catchlights, authentic 35mm film grain, cinematic masterpiece portrait still"
    ]
    if custom_mood:
        tokens.append(f"Mood: {custom_mood}")

    raw_portrait_prompt = ", ".join(t.strip() for t in tokens if t.strip())

    return await generate_ai_cinematic_image(
        prompt=raw_portrait_prompt,
        scene_number="PORTRAIT",
        shot_number="1",
        shot_size="CU",
        focal_length=85,
        aperture="T1.4",
        dop_preset=dop_preset,
        camera_letter="C",
        lighting_ratio=lighting_ratio,
        color_temp_k=color_temp_k,
        lut_emulation=lut_emulation,
        aspect_ratio="16:9",
        character_details=f"{character_name} ({actor_reference}, {look_and_costume}, {facial_features})",
        economy_mode=economy_mode
    )
