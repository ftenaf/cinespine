import os
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional

from backend.app.script.parser import ScreenplayScene, CharacterProfile
from backend.app.script.dop_presets import DoPSpecification
from backend.app.script.cache_service import generate_hash, get_cached_response, set_cached_response

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 60.0

def is_agent_enabled() -> bool:
    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in ("1", "true", "yes")
    return use_vertex or bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))

def _call_dop_agent(prompt: str) -> str:
    from google import genai
    from backend.app.script.llm_router import get_model_candidates
    
    candidates = get_model_candidates(prompt, task_complexity="complex")
    
    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in ("1", "true", "yes")
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    
    if use_vertex:
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        client = genai.Client(vertexai=True, project=project_id, location=location)
    else:
        client = genai.Client(api_key=api_key)

    last_error = None
    for model in candidates:
        req_hash = generate_hash(prompt=prompt, model=model)
        cached = get_cached_response(req_hash)
        if cached:
            return cached["text"]

        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={"response_mime_type": "application/json", "temperature": 0.4},
            )
            text = response.text or ""
            if text:
                set_cached_response(req_hash, {"text": text})
            return text
        except Exception as exc:
            last_error = exc
            logger.warning("DoP Agent model %s failed: %s", model, exc)
            continue
            
    raise RuntimeError(f"No Gemini model available for DoP Agent") from last_error

def build_dop_prompt(
    scene: ScreenplayScene,
    dop_spec: DoPSpecification,
    cut_segments: List[Dict[str, Any]]
) -> str:
    scene_text = scene.raw_content
    prompt = (
        "You are an elite Director of Photography planning the multi-camera coverage for a cinematic scene.\n"
        f"You must design the shot list to match the visual style of: {dop_spec.dop_preset}.\n"
        f"Lighting style: {dop_spec.lighting_style} | Contrast: {dop_spec.lighting_ratio} | Color: {dop_spec.color_temperature_k}K\n\n"
        "Here is the screenplay text for the scene:\n"
        "=====================\n"
        f"{scene_text}\n"
        "=====================\n\n"
        "I have divided the scene into chronological segments. For each segment, you must design a Setup that covers it.\n"
        "Each Setup must include 3 synchronized camera angles (Camera A, Camera B, Camera C):\n"
        "- Camera A is the primary master angle for the segment.\n"
        "- Camera B is secondary coverage (e.g., OTS, reaction, alternate angle).\n"
        "- Camera C is the tertiary accent setup (e.g., insert, extreme close up, specialized movement).\n\n"
        "For each camera, you must pick:\n"
        "- shot_size: EWS, WS, MWS, MS, MCU, CU, ECU, OTS, POV, INSERT\n"
        "- focal_length: e.g. 24, 35, 50, 85, 100\n"
        "- aperture: e.g. T1.4, T2.0, T2.8, T4.0, T5.6\n"
        "- camera_angle: EYE_LEVEL, HIGH_ANGLE, LOW_ANGLE, DUTCH_ANGLE, OVERHEAD, WORM_EYE\n"
        "- camera_movement: STATIC, PAN_TILT, DOLLY_IN, DOLLY_OUT, SLIDER, HANDHELD, STEADICAM, CRANE\n\n"
        "Return ONLY a JSON array. Each element in the array represents one Setup. The array length must exactly match the number of segments below.\n\n"
    )
    
    for idx, seg in enumerate(cut_segments):
        prompt += f"Segment {idx+1}:\n"
        if seg.get("transition"): prompt += f"- Transition: {seg['transition']}\n"
        if seg.get("actions"): prompt += f"- Actions: {' '.join(seg['actions'])}\n"
        if seg.get("dialogues"): 
            for d in seg['dialogues']:
                prompt += f"- Dialogue ({d[0]}): {d[2]}\n"
        prompt += "\n"

    prompt += (
        "Output JSON Format:\n"
        "[\n"
        "  {\n"
        '    "setup_name": "Short descriptive name (e.g. Master Establishing)",\n'
        '    "dramatic_beat": "Narrative purpose of this setup",\n'
        '    "subject_description": "What is happening in this segment",\n'
        '    "cameras": [\n'
        '      {\n'
        '        "camera_letter": "A",\n'
        '        "camera_role": "Primary Setup (WS Coverage)",\n'
        '        "shot_size": "WS",\n'
        '        "focal_length": 35,\n'
        '        "aperture": "T2.8",\n'
        '        "camera_angle": "EYE_LEVEL",\n'
        '        "camera_movement": "STATIC",\n'
        '        "coverage_description": "Explanation of what Camera A is framing"\n'
        '      },\n'
        '      // Repeat for Camera B and Camera C\n'
        '    ]\n'
        "  }\n"
        "]\n"
    )
    return prompt

async def run_dop_agent(
    scene: ScreenplayScene,
    dop_spec: DoPSpecification,
    cut_segments: List[Dict[str, Any]]
) -> Optional[List[Dict[str, Any]]]:
    if not is_agent_enabled():
        return None
        
    prompt = build_dop_prompt(scene, dop_spec, cut_segments)
    
    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(_call_dop_agent, prompt),
            timeout=TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning("DoP Agent failed: %s", exc)
        return None
        
    if raw.startswith("```"):
        raw = raw.split("```")[1] if "```" in raw[3:] else raw.strip("`")
        raw = raw.removeprefix("json").strip()
        
    try:
        data = json.loads(raw)
        if isinstance(data, list) and len(data) == len(cut_segments):
            return data
    except json.JSONDecodeError:
        pass
        
    return None
