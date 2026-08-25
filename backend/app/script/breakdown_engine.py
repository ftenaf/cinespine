"""
AI Scene-to-Shot Breakdown Engine & Multi-Camera Previz Synthesizer for CineSpine.
Divides dramatic screenplay scenes into cinematic setups (Shot List)
with multi-camera angle coverage (Cameras A, B, C), technical DoP parameters,
dramatic beat analysis, and targeted generative image prompts.
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


class CameraAngleProposal(BaseModel):
    id: str = Field(default_factory=lambda: f"CAM-{uuid.uuid4().hex[:6].upper()}")
    camera_letter: str = "A"  # A, B, C
    camera_role: str = "Primary Master Setup"
    shot_size: str = "WS"  # EWS, WS, MWS, MS, MCU, CU, ECU, OTS, POV, INSERT
    focal_length: int = 35
    aperture: str = "T2.8"
    camera_angle: str = "EYE_LEVEL"  # EYE_LEVEL, HIGH_ANGLE, LOW_ANGLE, DUTCH_ANGLE, OVERHEAD, WORM_EYE
    camera_movement: str = "STATIC"  # STATIC, PAN_TILT, DOLLY_IN, DOLLY_OUT, SLIDER, HANDHELD, STEADICAM, CRANE
    coverage_description: str = ""
    prompt: str = ""
    image_url: Optional[str] = None
    status: str = "pending"


class ShotProposal(BaseModel):
    id: str = Field(default_factory=lambda: f"SHOT-{uuid.uuid4().hex[:8].upper()}")
    scene_number: str
    shot_number: str
    shot_name: str
    shot_size: str = "WS"  # Default Primary size
    camera_angle: str = "EYE_LEVEL"
    camera_movement: str = "STATIC"
    dramatic_beat: str = ""
    subject_description: str = ""
    dop_spec: DoPSpecification = Field(default_factory=DoPSpecification)
    cameras: List[CameraAngleProposal] = Field(default_factory=list)
    active_camera: str = "A"
    storyboard: StoryboardFrame = Field(default_factory=StoryboardFrame)


def synthesize_cinematic_prompt(
    scene: ScreenplayScene,
    camera_letter: str,
    shot_size: str,
    camera_angle: str,
    camera_movement: str,
    focal_length: int,
    aperture: str,
    subject_action: str,
    dop_spec: DoPSpecification,
    aspect_ratio: str = "2.39:1"
) -> str:
    """
    Synthesizes a high-fidelity photorealistic generative image prompt
    specifically tailored for a specific camera angle perspective (Camera A, B, or C).
    """
    shot_size_labels = {
        "EWS": "extreme wide panoramic master shot",
        "WS": "cinematic wide angle shot establishing environment and architecture",
        "MWS": "medium wide shot (cowboy framing) showing character waist-up in environment",
        "MS": "cinematic medium shot balancing character emotion and location background",
        "MCU": "medium close-up shot focused on character expressions",
        "CU": "intense cinematic close-up shot with shallow depth of field",
        "ECU": "extreme close-up macro detail shot with razor-thin focus",
        "OTS": "over-the-shoulder perspective shot looking past foreground character shoulder",
        "POV": "first-person point-of-view shot directly through character eyes",
        "INSERT": "cinematic macro insert cutaway detail shot"
    }
    size_str = shot_size_labels.get(shot_size, "cinematic shot")

    angle_labels = {
        "EYE_LEVEL": "eye-level camera angle with neutral perspective",
        "LOW_ANGLE": "low angle looking upward dramatically",
        "HIGH_ANGLE": "high angle looking downward from above",
        "DUTCH_ANGLE": "tilted dutch angle composition conveying psychological tension",
        "OVERHEAD": "top-down bird's-eye overhead bird view",
        "WORM_EYE": "extreme ground-level worm's eye perspective"
    }
    angle_str = angle_labels.get(camera_angle, "eye-level framing")

    cam_prefix = {
        "A": "Camera A (Primary Wide Master)",
        "B": "Camera B (Secondary Tighter Coverage / OTS)",
        "C": "Camera C (Profile / Detail / Accent Track)"
    }.get(camera_letter, f"Camera {camera_letter}")

    # Extract lighting keywords from preset
    preset_style = DOP_MASTER_PRESETS.get(dop_spec.dop_preset, {}).get("prompt_style_tag", "")
    if not preset_style:
        preset_style = f"{dop_spec.lighting_style}, {dop_spec.color_palette}, {dop_spec.lut_emulation} film look"

    # Assemble scene location and time
    env_str = "interior" if "INT" in scene.environment else "exterior"
    tod_str = scene.time_of_day.lower()

    # Core prompt construction
    prompt_parts = [
        f"Film still shot on {cam_prefix}: A {size_str}, {angle_str} in a {env_str} {scene.location.lower()} during {tod_str}",
        f"{subject_action}",
        f"{focal_length}mm {dop_spec.lens_type} at {aperture} aperture, {dop_spec.sensor_format}",
        f"{dop_spec.lighting_style} with {dop_spec.lighting_ratio} lighting contrast ratio, color temperature {dop_spec.color_temperature_k}K",
        f"{preset_style}",
        f"aspect ratio {aspect_ratio}, 35mm motion picture cinematography, 8k resolution, authentic film grain, masterpiece production still"
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
    Analyzes dramatic scene content and divides it into a professional multi-camera shot list (coverage plan)
    where each setup contains up to 3 simultaneous camera perspectives (Cameras A, B, C) with individual prompts.
    """
    shots: List[ShotProposal] = []
    base_dop = resolve_dop_specification(dop_style_name, dop_overrides, custom_mood_prompt)

    actions_text = " ".join(scene.action_blocks) if scene.action_blocks else "Action unfolding in scene."
    dialogue_count = len(scene.dialogues)
    characters = list({d.character for d in scene.dialogues})
    char_label = " & ".join(characters[:2]) if characters else "Lead characters"

    # -------------------------------------------------------------
    # SETUP 1: Master Scene Coverage (Synchronized 3-Camera Rig)
    # -------------------------------------------------------------
    # Camera A: Wide Master Frontal
    cam_a_action = f"Master establishing view of {scene.location}: {actions_text[:140]}"
    cam_a_focal = max(18, min(base_dop.focal_length, 35))
    cam_a_prompt = synthesize_cinematic_prompt(
        scene=scene, camera_letter="A", shot_size="WS", camera_angle="LOW_ANGLE" if "EXT" in scene.environment else "EYE_LEVEL",
        camera_movement="STATIC" if "Fincher" in base_dop.dop_preset else "DOLLY_IN",
        focal_length=cam_a_focal, aperture="T2.8", subject_action=cam_a_action, dop_spec=base_dop, aspect_ratio=aspect_ratio
    )
    cam_a_1 = CameraAngleProposal(
        camera_letter="A", camera_role="Primary Master Wide", shot_size="WS", focal_length=cam_a_focal,
        aperture="T2.8", camera_angle="LOW_ANGLE" if "EXT" in scene.environment else "EYE_LEVEL",
        camera_movement="DOLLY_IN", coverage_description="Full spatial architecture and blocking context", prompt=cam_a_prompt
    )

    # Camera B: Medium Two-Shot / Dolly Track
    cam_b_action = f"Medium framing on {char_label} within {scene.location}"
    cam_b_focal = 50
    cam_b_prompt = synthesize_cinematic_prompt(
        scene=scene, camera_letter="B", shot_size="MS", camera_angle="EYE_LEVEL",
        camera_movement="SLIDER", focal_length=cam_b_focal, aperture="T2.0",
        subject_action=cam_b_action, dop_spec=base_dop, aspect_ratio=aspect_ratio
    )
    cam_b_1 = CameraAngleProposal(
        camera_letter="B", camera_role="Secondary Medium Coverage", shot_size="MS", focal_length=cam_b_focal,
        aperture="T2.0", camera_angle="EYE_LEVEL", camera_movement="SLIDER",
        coverage_description="Character interaction and environmental mid-ground", prompt=cam_b_prompt
    )

    # Camera C: 90-Degree Profile / Architectural Accent
    cam_c_action = f"Low-angle profile cutaway accentuating lighting shafts and spatial depth in {scene.location}"
    cam_c_focal = 85
    cam_c_prompt = synthesize_cinematic_prompt(
        scene=scene, camera_letter="C", shot_size="MCU", camera_angle="LOW_ANGLE",
        camera_movement="STATIC", focal_length=cam_c_focal, aperture="T1.4",
        subject_action=cam_c_action, dop_spec=base_dop, aspect_ratio=aspect_ratio
    )
    cam_c_1 = CameraAngleProposal(
        camera_letter="C", camera_role="Profile Accent / Light Shafts", shot_size="MCU", focal_length=cam_c_focal,
        aperture="T1.4", camera_angle="LOW_ANGLE", camera_movement="STATIC",
        coverage_description="Dramatic profile silhouette and volumetric highlights", prompt=cam_c_prompt
    )

    shots.append(
        ShotProposal(
            id=f"SHOT-{scene.scene_number}-01",
            scene_number=scene.scene_number,
            shot_number="1",
            shot_name=f"Master Setup - {scene.location}",
            shot_size="WS",
            camera_angle="EYE_LEVEL",
            camera_movement="DOLLY_IN",
            dramatic_beat=f"Establish spatial orientation, mood, and architecture in {scene.location}",
            subject_description=cam_a_action,
            dop_spec=base_dop,
            cameras=[cam_a_1, cam_b_1, cam_c_1],
            active_camera="A",
            storyboard=StoryboardFrame(prompt=cam_a_prompt, aspect_ratio=aspect_ratio, status="pending")
        )
    )

    # -------------------------------------------------------------
    # SETUP 2: Dialogue & Reaction Coverage (Multi-Cam A, B, C)
    # -------------------------------------------------------------
    if dialogue_count > 0 or len(characters) > 0:
        first_diag = scene.dialogues[0].line if scene.dialogues else "Character contemplation"
        first_char = scene.dialogues[0].character if scene.dialogues else "Lead Actor"
        second_char = scene.dialogues[1].character if len(scene.dialogues) > 1 else "Responder"

        # Cam A: Over-The-Shoulder on Character 1
        ots_a_action = f"Over-the-shoulder shot looking past {second_char} onto {first_char} delivering line: \"{first_diag[:80]}\""
        ots_a_focal = 50
        ots_a_prompt = synthesize_cinematic_prompt(
            scene=scene, camera_letter="A", shot_size="OTS", camera_angle="EYE_LEVEL", camera_movement="STATIC",
            focal_length=ots_a_focal, aperture="T2.0", subject_action=ots_a_action, dop_spec=base_dop, aspect_ratio=aspect_ratio
        )
        cam_a_2 = CameraAngleProposal(
            camera_letter="A", camera_role=f"OTS looking at {first_char}", shot_size="OTS", focal_length=ots_a_focal,
            aperture="T2.0", camera_angle="EYE_LEVEL", camera_movement="STATIC",
            coverage_description=f"Direct dialogue line coverage on {first_char}", prompt=ots_a_prompt
        )

        # Cam B: Reverse OTS on Character 2
        ots_b_action = f"Reverse over-the-shoulder shot capturing {second_char} listening attentively in shadows"
        ots_b_focal = 50
        ots_b_prompt = synthesize_cinematic_prompt(
            scene=scene, camera_letter="B", shot_size="OTS", camera_angle="EYE_LEVEL", camera_movement="STATIC",
            focal_length=ots_b_focal, aperture="T2.0", subject_action=ots_b_action, dop_spec=base_dop, aspect_ratio=aspect_ratio
        )
        cam_b_2 = CameraAngleProposal(
            camera_letter="B", camera_role=f"Reverse OTS on {second_char}", shot_size="OTS", focal_length=ots_b_focal,
            aperture="T2.0", camera_angle="EYE_LEVEL", camera_movement="STATIC",
            coverage_description=f"Reverse reaction coverage on {second_char}", prompt=ots_b_prompt
        )

        # Cam C: Tight Profile Close-Up / Emotional Tension
        cu_c_action = f"Intense profile close-up on {first_char}'s eyes and trembling expression"
        cu_c_focal = 85
        cu_c_prompt = synthesize_cinematic_prompt(
            scene=scene, camera_letter="C", shot_size="CU", camera_angle="EYE_LEVEL", camera_movement="SLIDER",
            focal_length=cu_c_focal, aperture="T1.4", subject_action=cu_c_action, dop_spec=base_dop, aspect_ratio=aspect_ratio
        )
        cam_c_2 = CameraAngleProposal(
            camera_letter="C", camera_role=f"Tight Profile Close-Up on {first_char}", shot_size="CU", focal_length=cu_c_focal,
            aperture="T1.4", camera_angle="EYE_LEVEL", camera_movement="SLIDER",
            coverage_description="Intense psychological tension and eye light", prompt=cu_c_prompt
        )

        shots.append(
            ShotProposal(
                id=f"SHOT-{scene.scene_number}-02",
                scene_number=scene.scene_number,
                shot_number="2",
                shot_name=f"Dialogue Cross-Coverage - {char_label}",
                shot_size="OTS",
                camera_angle="EYE_LEVEL",
                camera_movement="STATIC",
                dramatic_beat=f"Emotional and verbal conflict exchange between {char_label}",
                subject_description=ots_a_action,
                dop_spec=base_dop,
                cameras=[cam_a_2, cam_b_2, cam_c_2],
                active_camera="A",
                storyboard=StoryboardFrame(prompt=ots_a_prompt, aspect_ratio=aspect_ratio, status="pending")
            )
        )

    # -------------------------------------------------------------
    # SETUP 3: Climactic Detail & Insert Coverage (Multi-Cam A, B, C)
    # -------------------------------------------------------------
    cu_action = f"Extreme close-up on key narrative action and tactile details in {scene.location}"
    
    # Cam A: Tight Frontal Close-Up
    cam_a_3_focal = 85
    cam_a_3_prompt = synthesize_cinematic_prompt(
        scene=scene, camera_letter="A", shot_size="CU", camera_angle="LOW_ANGLE", camera_movement="STATIC",
        focal_length=cam_a_3_focal, aperture="T1.4", subject_action=cu_action, dop_spec=base_dop, aspect_ratio=aspect_ratio
    )
    cam_a_3 = CameraAngleProposal(
        camera_letter="A", camera_role="Climactic Tight Close-Up", shot_size="CU", focal_length=cam_a_3_focal,
        aperture="T1.4", camera_angle="LOW_ANGLE", camera_movement="STATIC",
        coverage_description="High-contrast climactic facial focus", prompt=cam_a_3_prompt
    )

    # Cam B: Macro Detail / Hands / Instrument Insert
    cam_b_3_action = f"Macro insert detail of fingers / hands / tactile physical interaction in {scene.location}"
    cam_b_3_focal = 100
    cam_b_3_prompt = synthesize_cinematic_prompt(
        scene=scene, camera_letter="B", shot_size="INSERT", camera_angle="OVERHEAD", camera_movement="STATIC",
        focal_length=cam_b_3_focal, aperture="T2.8", subject_action=cam_b_3_action, dop_spec=base_dop, aspect_ratio=aspect_ratio
    )
    cam_b_3 = CameraAngleProposal(
        camera_letter="B", camera_role="Macro Physical Insert", shot_size="INSERT", focal_length=cam_b_3_focal,
        aperture="T2.8", camera_angle="OVERHEAD", camera_movement="STATIC",
        coverage_description="Tactile tactile prop and kinetic action insert", prompt=cam_b_3_prompt
    )

    # Cam C: Dutch Angle Kinetic Accent
    cam_c_3_action = f"Dutch angle tilted perspective capturing atmospheric shadows and environmental tension"
    cam_c_3_focal = 35
    cam_c_3_prompt = synthesize_cinematic_prompt(
        scene=scene, camera_letter="C", shot_size="MWS", camera_angle="DUTCH_ANGLE", camera_movement="HANDHELD",
        focal_length=cam_c_3_focal, aperture="T2.0", subject_action=cam_c_3_action, dop_spec=base_dop, aspect_ratio=aspect_ratio
    )
    cam_c_3 = CameraAngleProposal(
        camera_letter="C", camera_role="Dutch Angle Kinetic Accent", shot_size="MWS", focal_length=cam_c_3_focal,
        aperture="T2.0", camera_angle="DUTCH_ANGLE", camera_movement="HANDHELD",
        coverage_description="Off-kilter tension and kinetic handheld energy", prompt=cam_c_3_prompt
    )

    shots.append(
        ShotProposal(
            id=f"SHOT-{scene.scene_number}-03",
            scene_number=scene.scene_number,
            shot_number="3",
            shot_name="Climactic Detail & Inserts",
            shot_size="CU",
            camera_angle="LOW_ANGLE",
            camera_movement="STATIC",
            dramatic_beat="Climactic psychological crescendo and tactile focal point",
            subject_description=cu_action,
            dop_spec=base_dop,
            cameras=[cam_a_3, cam_b_3, cam_c_3],
            active_camera="A",
            storyboard=StoryboardFrame(prompt=cam_a_3_prompt, aspect_ratio=aspect_ratio, status="pending")
        )
    )

    return shots
