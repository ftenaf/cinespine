import base64
import logging
import os
import random
import urllib.parse
from typing import Dict, Any, Optional

import httpx

from backend.app.script.cache_service import get_cached_response, set_cached_response, generate_hash

logger = logging.getLogger(__name__)

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
    If economy_mode=True, it skips paid APIs and uses FLUX.1.
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

    # 2. Paid APIs (DALL-E 3, Imagen 3) - Skip if economy_mode is True
    if not economy_mode:
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    res = await client.post(
                        "https://api.openai.com/v1/images/generations",
                        headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                        json={
                            "model": "dall-e-3",
                            "prompt": compiled_prompt[:950],
                            "n": 1,
                            "size": "1792x1024" if aspect_ratio in ["2.39:1", "16:9"] else "1024x1024",
                            "quality": "hd",
                            "response_format": "b64_json"
                        }
                    )
                    if res.status_code == 200:
                        data = res.json()
                        b64_img = data["data"][0]["b64_json"]
                        return _finalize({
                            "image_url": f"data:image/jpeg;base64,{b64_img}",
                            "compiled_prompt": compiled_prompt,
                            "provider": "OpenAI DALL-E 3 (HD)"
                        })
            except Exception as e:
                logger.warning("OpenAI DALL-E 3 error: %s", e)

        gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)
                result = client.models.generate_images(
                    model="imagen-3.0-generate-002",
                    prompt=compiled_prompt[:950],
                    config=dict(
                        number_of_images=1,
                        aspect_ratio="16:9" if aspect_ratio in ["2.39:1", "16:9", "1.85:1"] else "4:3",
                        person_generation="ALLOW_ADULT"
                    )
                )
                if result.generated_images:
                    img_bytes = result.generated_images[0].image.image_bytes
                    b64_img = base64.b64encode(img_bytes).decode("utf-8")
                    return _finalize({
                        "image_url": f"data:image/jpeg;base64,{b64_img}",
                        "compiled_prompt": compiled_prompt,
                        "provider": "Google Cloud Imagen 3 (google.genai SDK)"
                    })
            except Exception as e:
                logger.warning("google.genai Imagen 3 SDK error (falling back to REST): %s", e)
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        # The key goes in a header, never the query string: httpx
                        # embeds the request URL in its exception messages, so a
                        # key in the URL ends up in the logs on any failure.
                        url = "https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict"
                        res = await client.post(
                            url,
                            headers={
                                "Content-Type": "application/json",
                                "x-goog-api-key": gemini_key,
                            },
                            json={
                                "instances": [{"prompt": compiled_prompt[:950]}],
                                "parameters": {
                                    "sampleCount": 1,
                                    "aspectRatio": "16:9" if aspect_ratio in ["2.39:1", "16:9", "1.85:1"] else "4:3",
                                    "personGeneration": "ALLOW_ADULT"
                                }
                            }
                        )
                        if res.status_code == 200:
                            data = res.json()
                            b64_img = data["predictions"][0]["bytesBase64Encoded"]
                            return _finalize({
                                "image_url": f"data:image/jpeg;base64,{b64_img}",
                                "compiled_prompt": compiled_prompt,
                                "provider": "Google Cloud Imagen 3 (Gemini Enterprise)"
                            })
                except Exception as e2:
                    logger.warning("Google Imagen 3 REST error: %s", e2)

    # 3. Real-Time Cloud Flux.1 / SD Engine (Economy Mode / Fallback)
    try:
        clean_encoded_prompt = urllib.parse.quote(compiled_prompt[:600])
        if aspect_ratio == "2.39:1":
            w, h = 1152, 480
        elif aspect_ratio == "1.85:1":
            w, h = 960, 520
        elif aspect_ratio == "4:3":
            w, h = 800, 600
        else:
            w, h = 960, 540

        seed = random.randint(1000, 999999)
        flux_url = f"https://image.pollinations.ai/prompt/{clean_encoded_prompt}?width={w}&height={h}&model=flux&nologo=true&seed={seed}"

        async with httpx.AsyncClient(timeout=35.0) as client:
            res = await client.get(
                flux_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CineSpine/0.1.0"}
            )
            if res.status_code == 200 and len(res.content) > 5000:
                b64_img = base64.b64encode(res.content).decode("utf-8")
                provider = "FLUX.1 Cinematic Diffusion (Economy Mode)" if economy_mode else "FLUX.1 Cinematic Diffusion (Real-Time)"
                return _finalize({
                    "image_url": f"data:image/jpeg;base64,{b64_img}",
                    "compiled_prompt": compiled_prompt,
                    "provider": provider
                })
    except Exception as e:
        logger.warning("Cloud Flux.1 engine error: %s", e)

    # 4. Local placeholder. Deliberately NOT cached: it means every generator
    #    was unavailable, which is a transient condition the next request should
    #    be free to retry.
    return {
        "image_url": _placeholder_asset(prompt, camera_letter),
        "compiled_prompt": compiled_prompt,
        "provider": "CineSpine Previz Placeholder (no generator available)"
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
