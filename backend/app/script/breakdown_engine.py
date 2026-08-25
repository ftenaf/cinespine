"""
AI Scene-to-Shot Breakdown Engine & Previz Synthesizer for CineSpine.
Divides dramatic screenplay scenes into cinematic setups (Shot List)
with technical DoP parameters, dramatic beat analysis, and image prompts.
"""
import uuid
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from backend.app.script.parser import ScreenplayScene
from backend.app.script.dop_presets import DoPSpecification, resolve_dop_specification, DOP_MASTER_PRESETS


class StoryboardFrame(BaseModel):
    image_url: Optional[str] = None
    prompt: str = ""
    aspect_ratio: str = "2.39:1"  # 2.39:1, 1.85:1, 16:9, 4:3
    status: str = "pending"  # pending, generating, generated, failed


class ShotProposal(BaseModel):
    id: str = Field(default_factory=lambda: f"SHOT-{uuid.uuid4().hex[:8].upper()}")
    scene_number: str
    shot_number: str
    shot_name: str
    shot_size: str = "WS"  # EWS, WS, MWS, MS, MCU, CU, ECU, OTS, POV, INSERT
    camera_angle: str = "EYE_LEVEL"  # EYE_LEVEL, HIGH_ANGLE, LOW_ANGLE, DUTCH_ANGLE, OVERHEAD, WORM_EYE
    camera_movement: str = "STATIC"  # STATIC, PAN_TILT, DOLLY_IN, DOLLY_OUT, SLIDER, HANDHELD, STEADICAM, CRANE
    dramatic_beat: str = ""
    subject_description: str = ""
    dop_spec: DoPSpecification = Field(default_factory=DoPSpecification)
    storyboard: StoryboardFrame = Field(default_factory=StoryboardFrame)


def synthesize_cinematic_prompt(
    scene: ScreenplayScene,
    shot_size: str,
    camera_angle: str,
    camera_movement: str,
    subject_action: str,
    dop_spec: DoPSpecification,
    aspect_ratio: str = "2.39:1"
) -> str:
    """
    Synthesizes a high-fidelity photorealistic generative image prompt
    adhering to technical cinematography parameters.
    """
    shot_size_labels = {
        "EWS": "extreme wide master shot",
        "WS": "cinematic wide shot",
        "MWS": "medium wide shot (cowboy framing)",
        "MS": "cinematic medium shot",
        "MCU": "medium close-up shot",
        "CU": "intense cinematic close-up shot",
        "ECU": "extreme close-up macro detail shot",
        "OTS": "over-the-shoulder perspective shot",
        "POV": "first-person point-of-view shot",
        "INSERT": "cinematic insert detail shot"
    }
    size_str = shot_size_labels.get(shot_size, "cinematic shot")

    angle_labels = {
        "EYE_LEVEL": "eye-level camera angle",
        "LOW_ANGLE": "low angle looking upward dramatically",
        "HIGH_ANGLE": "high angle looking downward",
        "DUTCH_ANGLE": "tilted dutch angle composition",
        "OVERHEAD": "top-down bird's-eye overhead angle",
        "WORM_EYE": "extreme ground-level worm's eye perspective"
    }
    angle_str = angle_labels.get(camera_angle, "eye-level framing")

    # Extract lighting keywords from preset
    preset_style = DOP_MASTER_PRESETS.get(dop_spec.dop_preset, {}).get("prompt_style_tag", "")
    if not preset_style:
        preset_style = f"{dop_spec.lighting_style}, {dop_spec.color_palette}, {dop_spec.lut_emulation} film look"

    # Assemble scene location and time
    env_str = "interior" if "INT" in scene.environment else "exterior"
    tod_str = scene.time_of_day.lower()

    # Core prompt construction
    prompt_parts = [
        f"A {size_str}, {angle_str} in a {env_str} {scene.location.lower()} during {tod_str}",
        f"{subject_action}",
        f"{dop_spec.focal_length}mm {dop_spec.lens_type} at {dop_spec.aperture} aperture, {dop_spec.sensor_format}",
        f"{dop_spec.lighting_style} with {dop_spec.lighting_ratio} lighting ratio, color temperature {dop_spec.color_temperature_k}K",
        f"{preset_style}",
        f"aspect ratio {aspect_ratio}, 35mm motion picture still, 8k resolution, authentic film grain, cinematography award winning"
    ]

    return ", ".join(p.strip() for p in prompt_parts if p.strip())


def breakdown_scene_to_shots(
    scene: ScreenplayScene,
    dop_style_name: Optional[str] = "Roger Deakins",
    dop_overrides: Optional[Dict[str, Any]] = None,
    custom_mood_prompt: Optional[str] = None,
    aspect_ratio: str = "2.39:1"
) -> List[ShotProposal]:
    """
    Analyzes dramatic scene content and divides it into a professional shot list (coverage plan)
    with technical DoP parameters and generative image prompts.
    """
    shots: List[ShotProposal] = []
    base_dop = resolve_dop_specification(dop_style_name, dop_overrides, custom_mood_prompt)

    actions_text = " ".join(scene.action_blocks) if scene.action_blocks else "Action unfolding in scene."
    dialogue_count = len(scene.dialogues)
    characters = list({d.character for d in scene.dialogues})

    # 1. Master Establishing Setup (Wide Shot)
    master_focal = max(18, min(base_dop.focal_length, 35))
    master_dop = base_dop.model_copy(update={"focal_length": master_focal, "aperture": "T2.8"})
    master_action = f"Master establishing shot of {scene.location}: {actions_text[:120]}..." if len(actions_text) > 120 else actions_text
    
    master_prompt = synthesize_cinematic_prompt(
        scene=scene,
        shot_size="WS",
        camera_angle="EYE_LEVEL" if "INT" in scene.environment else "LOW_ANGLE",
        camera_movement="STATIC" if "Fincher" in base_dop.dop_preset else "DOLLY_IN",
        subject_action=master_action,
        dop_spec=master_dop,
        aspect_ratio=aspect_ratio
    )

    shots.append(
        ShotProposal(
            id=f"SHOT-{scene.scene_number}-01",
            scene_number=scene.scene_number,
            shot_number="1",
            shot_name=f"Master Setup - {scene.location}",
            shot_size="WS",
            camera_angle="EYE_LEVEL" if "INT" in scene.environment else "LOW_ANGLE",
            camera_movement="DOLLY_IN",
            dramatic_beat=f"Establish spatial orientation and atmosphere in {scene.location}",
            subject_description=master_action,
            dop_spec=master_dop,
            storyboard=StoryboardFrame(
                prompt=master_prompt,
                aspect_ratio=aspect_ratio,
                status="pending"
            )
        )
    )

    # 2. Character Medium / Two-Shot Coverage
    if dialogue_count > 0 or len(characters) > 0:
        char_label = " & ".join(characters[:2]) if characters else "Lead characters"
        first_diag = scene.dialogues[0].line if scene.dialogues else "Character contemplation"
        
        m_focal = 50
        m_dop = base_dop.model_copy(update={"focal_length": m_focal, "aperture": "T2.0"})
        m_action = f"Medium shot focusing on {char_label} engaging in scene: \"{first_diag[:80]}\""
        
        m_prompt = synthesize_cinematic_prompt(
            scene=scene,
            shot_size="MCU" if len(characters) == 1 else "MWS",
            camera_angle="EYE_LEVEL",
            camera_movement="SLIDER" if "Fincher" in base_dop.dop_preset else "STATIC",
            subject_action=m_action,
            dop_spec=m_dop,
            aspect_ratio=aspect_ratio
        )

        shots.append(
            ShotProposal(
                id=f"SHOT-{scene.scene_number}-02",
                scene_number=scene.scene_number,
                shot_number="2",
                shot_name=f"Coverage - {char_label}",
                shot_size="MCU" if len(characters) == 1 else "MWS",
                camera_angle="EYE_LEVEL",
                camera_movement="SLIDER",
                dramatic_beat=f"Emotional connection with {char_label}",
                subject_description=m_action,
                dop_spec=m_dop,
                storyboard=StoryboardFrame(
                    prompt=m_prompt,
                    aspect_ratio=aspect_ratio,
                    status="pending"
                )
            )
        )

    # 3. Emotional Climax / Close-Up or Dramatic Action Insert
    cu_focal = 85
    cu_dop = base_dop.model_copy(update={"focal_length": cu_focal, "aperture": "T1.4"})
    
    if dialogue_count > 1:
        last_diag = scene.dialogues[-1]
        cu_action = f"Intense close-up on {last_diag.character} as emotion crests: \"{last_diag.line[:80]}\""
    else:
        cu_action = f"Close-up focal point on key action detail and subject tension in {scene.location}"

    cu_prompt = synthesize_cinematic_prompt(
        scene=scene,
        shot_size="CU",
        camera_angle="LOW_ANGLE" if "Noir" in base_dop.lighting_style else "EYE_LEVEL",
        camera_movement="STATIC",
        subject_action=cu_action,
        dop_spec=cu_dop,
        aspect_ratio=aspect_ratio
    )

    shots.append(
        ShotProposal(
            id=f"SHOT-{scene.scene_number}-03",
            scene_number=scene.scene_number,
            shot_number="3",
            shot_name=f"Close-Up Climax",
            shot_size="CU",
            camera_angle="LOW_ANGLE",
            camera_movement="STATIC",
            dramatic_beat="Climactic dramatic shift and psychological resonance",
            subject_description=cu_action,
            dop_spec=cu_dop,
            storyboard=StoryboardFrame(
                prompt=cu_prompt,
                aspect_ratio=aspect_ratio,
                status="pending"
            )
        )
    )

    # 4. If long dramatic scene with multiple actions, add Macro Insert / Dutch Angle Setup
    if len(scene.action_blocks) > 2:
        ins_focal = 100
        ins_dop = base_dop.model_copy(update={"focal_length": ins_focal, "aperture": "T2.8"})
        ins_action = f"Macro insert detail: {scene.action_blocks[-1][:90]}"
        ins_prompt = synthesize_cinematic_prompt(
            scene=scene,
            shot_size="INSERT",
            camera_angle="OVERHEAD",
            camera_movement="STATIC",
            subject_action=ins_action,
            dop_spec=ins_dop,
            aspect_ratio=aspect_ratio
        )

        shots.append(
            ShotProposal(
                id=f"SHOT-{scene.scene_number}-04",
                scene_number=scene.scene_number,
                shot_number="4",
                shot_name="Insert Detail",
                shot_size="INSERT",
                camera_angle="OVERHEAD",
                camera_movement="STATIC",
                dramatic_beat="Tactile physical detail anchoring dramatic reality",
                subject_description=ins_action,
                dop_spec=ins_dop,
                storyboard=StoryboardFrame(
                    prompt=ins_prompt,
                    aspect_ratio=aspect_ratio,
                    status="pending"
                )
            )
        )

    return shots
