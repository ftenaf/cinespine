"""
AI Scene-to-Shot Breakdown Engine & Multi-Camera Previz Synthesizer for CineSpine.
Divides dramatic screenplay scenes into cinematic setups (Shot List)
with multi-camera angle coverage (Cameras A, B, C), technical DoP parameters,
character visual consistency, and targeted generative image prompts.
"""
import uuid
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from backend.app.script.parser import ScreenplayScene, CharacterProfile, CHARACTER_ARCHETYPES
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
    characters: List[str] = Field(default_factory=list)
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
    aspect_ratio: str = "2.39:1",
    characters_in_shot: Optional[List[str]] = None,
    character_profiles_map: Optional[Dict[str, CharacterProfile]] = None
) -> str:
    """
    Synthesizes a high-fidelity photorealistic generative image prompt
    specifically tailored for Camera A, B, or C perspective, incorporating
    exact DoP optical/lighting parameters and persistent character visual profiles.
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
    angle_str = angle_labels.get(camera_angle, "cinematic angle")

    cam_prefix = {
        "A": "Camera A (Primary Wide Master):",
        "B": "Camera B (Secondary Coverage):",
        "C": "Camera C (Profile / Detail / Accent):"
    }.get(camera_letter, f"Camera {camera_letter}:")

    # Character visual profile synthesis
    char_visuals = []
    if characters_in_shot and character_profiles_map:
        for char_name in characters_in_shot:
            p = character_profiles_map.get(char_name)
            if p:
                char_visuals.append(f"{p.name} ({p.actor_reference}, wearing {p.look_and_costume}, facial features: {p.facial_features})")
            elif char_name in CHARACTER_ARCHETYPES:
                arch = CHARACTER_ARCHETYPES[char_name]
                char_visuals.append(f"{char_name} ({arch['actor_reference']}, wearing {arch['look_and_costume']}, facial features: {arch['facial_features']})")

    char_str = "; ".join(char_visuals) if char_visuals else ""

    tokens = [
        cam_prefix,
        f"Cinematic film still, 35mm motion picture camera, {focal_length}mm lens at {aperture}, {aspect_ratio} aspect ratio",
        size_str,
        angle_str,
        f"Location: {scene.environment}. {scene.location} - {scene.time_of_day}",
        f"Subject Action: {subject_action}",
    ]

    if char_str:
        tokens.append(f"Character Visuals: {char_str}")

    tokens.extend([
        f"Cinematography Style: {dop_spec.dop_preset}",
        f"Color Temperature: {dop_spec.color_temperature_k}K, Lighting Contrast Ratio: {dop_spec.lighting_ratio}",
        f"Film Stock Grade: {dop_spec.lut_emulation}",
        f"Lighting Style: {dop_spec.lighting_style}",
        f"Mood Notes: {dop_spec.mood_notes}",
        "8k resolution, authentic 35mm film grain, masterpiece cinema production still"
    ])

    return ", ".join(t.strip() for t in tokens if t.strip())


def generate_multi_cam_prompts(
    scene: ScreenplayScene,
    shot_number: str,
    action_text: str,
    dop_spec: DoPSpecification,
    aspect_ratio: str = "2.39:1",
    characters_in_shot: Optional[List[str]] = None,
    character_profiles_map: Optional[Dict[str, CharacterProfile]] = None
) -> List[CameraAngleProposal]:
    """
    Generates 3 synchronized camera angle proposals (Camera A, B, C)
    customized for spatial coverage, character visual consistency, and DoP optics.
    """
    chars = characters_in_shot or scene.characters
    is_dialogue_or_character = bool(scene.dialogues) or bool(chars)

    # 1. Camera A - Primary Wide Master Setup
    cam_a_focal = 28 if "EXT" in scene.environment else 35
    cam_a_aperture = "T2.8"
    cam_a_prompt = synthesize_cinematic_prompt(
        scene=scene,
        camera_letter="A",
        shot_size="WS",
        camera_angle="EYE_LEVEL",
        camera_movement="STATIC",
        focal_length=cam_a_focal,
        aperture=cam_a_aperture,
        subject_action=f"Wide master coverage establishing spatial architecture and character blocking for {action_text}",
        dop_spec=dop_spec,
        aspect_ratio=aspect_ratio,
        characters_in_shot=chars,
        character_profiles_map=character_profiles_map
    )
    cam_a = CameraAngleProposal(
        camera_letter="A",
        camera_role="Primary Master Setup (Wide Spatial Coverage)",
        shot_size="WS",
        focal_length=cam_a_focal,
        aperture=cam_a_aperture,
        camera_angle="EYE_LEVEL",
        camera_movement="STATIC",
        coverage_description="Wide master shot capturing complete environmental architecture, spatial geometry, and character blocking.",
        prompt=cam_a_prompt,
        status="pending"
    )

    # 2. Camera B - Secondary Over-the-Shoulder / Medium Coverage
    cam_b_focal = 50 if is_dialogue_or_character else 65
    cam_b_size = "OTS" if is_dialogue_or_character else "MS"
    cam_b_aperture = "T2.0"
    cam_b_prompt = synthesize_cinematic_prompt(
        scene=scene,
        camera_letter="B",
        shot_size=cam_b_size,
        camera_angle="EYE_LEVEL",
        camera_movement="HANDHELD" if "Handheld" in dop_spec.dop_preset else "STATIC",
        focal_length=cam_b_focal,
        aperture=cam_b_aperture,
        subject_action=f"Medium character coverage and reaction angle focusing on {action_text}",
        dop_spec=dop_spec,
        aspect_ratio=aspect_ratio,
        characters_in_shot=chars,
        character_profiles_map=character_profiles_map
    )
    cam_b = CameraAngleProposal(
        camera_letter="B",
        camera_role="Secondary Coverage (Medium / Over-The-Shoulder)",
        shot_size=cam_b_size,
        focal_length=cam_b_focal,
        aperture=cam_b_aperture,
        camera_angle="EYE_LEVEL",
        camera_movement="STATIC",
        coverage_description="Medium coverage focused on character performance, dialogue cadence, and emotional subtext.",
        prompt=cam_b_prompt,
        status="pending"
    )

    # 3. Camera C - Profile / Macro / Tactile Insert Setup
    cam_c_focal = 85 if is_dialogue_or_character else 100
    cam_c_size = "CU" if is_dialogue_or_character else "INSERT"
    cam_c_aperture = "T1.4"
    cam_c_prompt = synthesize_cinematic_prompt(
        scene=scene,
        camera_letter="C",
        shot_size=cam_c_size,
        camera_angle="DUTCH_ANGLE" if "Fincher" in dop_spec.dop_preset else "EYE_LEVEL",
        camera_movement="SLIDER",
        focal_length=cam_c_focal,
        aperture=cam_c_aperture,
        subject_action=f"Tight macro close-up insert capturing tactile physical tension and intense details of {action_text}",
        dop_spec=dop_spec,
        aspect_ratio=aspect_ratio,
        characters_in_shot=chars,
        character_profiles_map=character_profiles_map
    )
    cam_c = CameraAngleProposal(
        camera_letter="C",
        camera_role="Tertiary Accent Setup (Macro / Intense Close-Up)",
        shot_size=cam_c_size,
        focal_length=cam_c_focal,
        aperture=cam_c_aperture,
        camera_angle="EYE_LEVEL",
        camera_movement="SLIDER",
        coverage_description="Intimate macro close-up isolating character eyes, expressive hands, or critical set props in razor-thin focus.",
        prompt=cam_c_prompt,
        status="pending"
    )

    return [cam_a, cam_b, cam_c]


def breakdown_scene_to_shots(
    scene: ScreenplayScene,
    dop_style_name: str = "Roger Deakins",
    dop_overrides: Optional[Dict[str, Any]] = None,
    custom_mood_prompt: Optional[str] = None,
    aspect_ratio: str = "2.39:1",
    character_profiles: Optional[List[CharacterProfile]] = None
) -> List[ShotProposal]:
    """
    Decomposes a ScreenplayScene into multi-camera shot coverage proposals (Shot List)
    with persistent character visual consistency and DoP specifications.
    """
    dop_spec = resolve_dop_specification(
        preset_name=dop_style_name,
        custom_prompt=custom_mood_prompt,
        overrides=dop_overrides
    )

    char_map: Dict[str, CharacterProfile] = {}
    if character_profiles:
        for p in character_profiles:
            char_map[p.name.upper()] = p

    shots: List[ShotProposal] = []
    
    # 1. Establishing / Master Shot
    master_action = scene.action_blocks[0] if scene.action_blocks else f"Establishing coverage of {scene.location}"
    master_cameras = generate_multi_cam_prompts(
        scene=scene,
        shot_number="1",
        action_text=master_action,
        dop_spec=dop_spec,
        aspect_ratio=aspect_ratio,
        characters_in_shot=scene.characters,
        character_profiles_map=char_map
    )
    shot_1 = ShotProposal(
        scene_number=scene.scene_number,
        shot_number="1",
        shot_name=f"SCENE {scene.scene_number} - SHOT 1 (Master Setup)",
        shot_size="WS",
        camera_angle="EYE_LEVEL",
        camera_movement="STATIC",
        dramatic_beat="Scene Establishment & Spatial Architecture",
        subject_description=master_action,
        characters=scene.characters,
        dop_spec=dop_spec,
        cameras=master_cameras,
        active_camera="A",
        storyboard=StoryboardFrame(
            prompt=master_cameras[0].prompt,
            aspect_ratio=aspect_ratio,
            status="pending"
        )
    )
    shots.append(shot_1)

    # 2. Dialogue / Dynamic Action Coverage Setups
    if scene.dialogues:
        # Group dialogues by character interactions
        shot_idx = 2
        for d in scene.dialogues[:3]:  # Top key character interactions
            clean_char = d.character.split("(")[0].strip().upper()
            action_snippet = f"{clean_char} speaks: \"{d.line[:60]}...\""
            dialogue_cameras = generate_multi_cam_prompts(
                scene=scene,
                shot_number=str(shot_idx),
                action_text=action_snippet,
                dop_spec=dop_spec,
                aspect_ratio=aspect_ratio,
                characters_in_shot=[clean_char],
                character_profiles_map=char_map
            )
            
            shot_dialogue = ShotProposal(
                scene_number=scene.scene_number,
                shot_number=str(shot_idx),
                shot_name=f"SCENE {scene.scene_number} - SHOT {shot_idx} ({clean_char} Coverage)",
                shot_size="MS",
                camera_angle="EYE_LEVEL",
                camera_movement="STATIC",
                dramatic_beat=f"Key Dialogue Cadence for {clean_char}",
                subject_description=action_snippet,
                characters=[clean_char],
                dop_spec=dop_spec,
                cameras=dialogue_cameras,
                active_camera="A",
                storyboard=StoryboardFrame(
                    prompt=dialogue_cameras[0].prompt,
                    aspect_ratio=aspect_ratio,
                    status="pending"
                )
            )
            shots.append(shot_dialogue)
            shot_idx += 1

    # 3. Dramatic Climax / Tactile Insert Shot
    if len(scene.action_blocks) > 1 or len(shots) == 1:
        climax_action = scene.action_blocks[-1] if len(scene.action_blocks) > 1 else f"Close-up intense detail of {master_action}"
        climax_idx = len(shots) + 1
        climax_cameras = generate_multi_cam_prompts(
            scene=scene,
            shot_number=str(climax_idx),
            action_text=climax_action,
            dop_spec=dop_spec,
            aspect_ratio=aspect_ratio,
            characters_in_shot=scene.characters,
            character_profiles_map=char_map
        )
        shot_climax = ShotProposal(
            scene_number=scene.scene_number,
            shot_number=str(climax_idx),
            shot_name=f"SCENE {scene.scene_number} - SHOT {climax_idx} (Climax Accent)",
            shot_size="CU",
            camera_angle="DUTCH_ANGLE" if "Fincher" in dop_style_name else "EYE_LEVEL",
            camera_movement="SLIDER",
            dramatic_beat="Dramatic Climax & Sensory Detail",
            subject_description=climax_action,
            characters=scene.characters,
            dop_spec=dop_spec,
            cameras=climax_cameras,
            active_camera="A",
            storyboard=StoryboardFrame(
                prompt=climax_cameras[0].prompt,
                aspect_ratio=aspect_ratio,
                status="pending"
            )
        )
        shots.append(shot_climax)

    return shots
