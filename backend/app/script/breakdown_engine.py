"""
AI Scene-to-Shot Breakdown Engine & Multi-Camera Previz Synthesizer for CineSpine.
Divides dramatic screenplay scenes into cinematic setups (Shot List)
with multi-camera angle coverage (Cameras A, B, C), technical DoP parameters,
character visual consistency, and targeted generative image prompts.
"""
import uuid
import re
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
from backend.app.script.parser import ScreenplayScene, CharacterProfile
from backend.app.script.dop_presets import DoPSpecification, resolve_dop_specification, DOP_MASTER_PRESETS
from backend.app.script.breakdown_agent import run_dop_agent, is_agent_enabled


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
            else:
                # Name the character anyway so the frame is at least cast-correct,
                # rather than silently dropping them from the prompt.
                char_visuals.append(char_name)

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


def infer_shot_size_and_dynamics(text: str, has_dialogue: bool = False, is_first_shot: bool = False) -> Tuple[str, str, str]:
    """
    Infers the shot size, camera angle, and camera movement from screenplay action/dialogue descriptions.
    """
    lower = text.lower()
    
    # 1. Shot Size (using word boundaries for short acronyms like ECU, CU, MS to avoid matching words like 'security')
    if any(k in lower for k in ["extreme close-up", "extreme close up", "macro"]) or re.search(r"\b(ecu)\b", lower):
        size = "ECU"
    elif any(k in lower for k in ["close-up", "close up", "tight on"]) or re.search(r"\b(cu)\b", lower):
        size = "CU"
    elif any(k in lower for k in ["medium close-up", "medium close up"]) or re.search(r"\b(mcu)\b", lower):
        size = "MCU"
    elif any(k in lower for k in ["over-the-shoulder", "over the shoulder"]) or re.search(r"\b(ots)\b", lower):
        size = "OTS"
    elif any(k in lower for k in ["extreme wide", "panoramic"]) or re.search(r"\b(ews)\b", lower):
        size = "EWS"
    elif any(k in lower for k in ["wide shot", "wide angle", "master shot", "establishing"]) or re.search(r"\b(ws)\b", lower):
        size = "WS"
    elif any(k in lower for k in ["medium wide", "cowboy"]) or re.search(r"\b(mws)\b", lower):
        size = "MWS"
    elif any(k in lower for k in ["point of view"]) or re.search(r"\b(pov)\b", lower):
        size = "POV"
    elif any(k in lower for k in ["insert", "cutaway", "detail"]):
        size = "INSERT"
    elif is_first_shot and not has_dialogue:
        size = "WS"
    elif has_dialogue:
        size = "MS"
    else:
        size = "MS"

    # 2. Camera Angle
    if any(k in lower for k in ["low angle", "looking up", "worm's eye"]):
        angle = "LOW_ANGLE"
    elif any(k in lower for k in ["high angle", "looking down", "overhead", "bird's eye", "bird view"]):
        angle = "HIGH_ANGLE"
    elif any(k in lower for k in ["dutch", "tilted", "canted"]):
        angle = "DUTCH_ANGLE"
    else:
        angle = "EYE_LEVEL"

    # 3. Camera Movement
    if any(k in lower for k in ["handheld", "shaky"]):
        movement = "HANDHELD"
    elif any(k in lower for k in ["dolly in", "push in", "tracking"]):
        movement = "DOLLY_IN"
    elif any(k in lower for k in ["dolly out", "pull back", "pull out"]):
        movement = "DOLLY_OUT"
    elif any(k in lower for k in ["slider", "glide"]):
        movement = "SLIDER"
    elif any(k in lower for k in ["steadicam"]):
        movement = "STEADICAM"
    elif any(k in lower for k in ["crane", "jib"]):
        movement = "CRANE"
    elif any(k in lower for k in ["pan", "tilt"]):
        movement = "PAN_TILT"
    else:
        movement = "STATIC"

    return size, angle, movement


def parse_scene_into_shot_segments(scene: ScreenplayScene) -> List[Dict[str, Any]]:
    """
    Parses a scene's raw text and dialogues into distinct shot segments
    demarcated by explicit screenplay transition cuts (e.g. 'CUT TO:', '> SMASH CUT TO:', 'DISSOLVE TO:').
    Returns a list of segments if cuts exist, or empty list if the scene has no explicit cut transitions.
    """
    from backend.app.script.parser import is_transition_cue, clean_character_name, NON_CHARACTER_TOKENS

    raw_text = scene.raw_content or ""
    if not raw_text.strip():
        return []

    lines = raw_text.splitlines()
    has_cut = any(is_transition_cue(line) for line in lines)
    if not has_cut:
        return []

    segments: List[Dict[str, Any]] = []
    current_actions: List[str] = []
    current_dialogues: List[Tuple[str, Optional[str], str]] = []
    current_transition: Optional[str] = None
    
    pending_character: Optional[str] = None
    pending_parenthetical: Optional[str] = None
    pending_dialogue_lines: List[str] = []

    def flush_seg_dialogue():
        nonlocal pending_character, pending_parenthetical, pending_dialogue_lines, current_dialogues
        if pending_character and pending_dialogue_lines:
            d_text = " ".join(pending_dialogue_lines).strip()
            if d_text:
                current_dialogues.append((pending_character, pending_parenthetical, d_text))
        pending_character = None
        pending_parenthetical = None
        pending_dialogue_lines = []

    def commit_segment():
        nonlocal current_actions, current_dialogues, current_transition
        flush_seg_dialogue()
        if current_actions or current_dialogues:
            # Extract characters present in this segment
            seg_chars = set()
            for d in current_dialogues:
                c_name = clean_character_name(d[0])
                if c_name:
                    seg_chars.add(c_name)
            for a in current_actions:
                for sc_char in (scene.characters or []):
                    if re.search(rf"\b{re.escape(sc_char)}\b", a, re.IGNORECASE):
                        seg_chars.add(sc_char)
            
            segments.append({
                "transition": current_transition,
                "actions": list(current_actions),
                "dialogues": list(current_dialogues),
                "characters": sorted(list(seg_chars))
            })
        current_actions = []
        current_dialogues = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_seg_dialogue()
            continue

        if is_transition_cue(stripped):
            # A transition like "CUT TO:" completes the current shot and begins the next shot
            commit_segment()
            current_transition = re.sub(r"^[#*_\s>]+|[#*_\s<]+$", "", stripped).strip()
            continue

        # Check character cue
        clean_cue = re.sub(r"^[#*_\s]+|[#*_\s]+$", "", stripped)
        is_char_cue = (
            not is_transition_cue(stripped) and
            clean_cue.isupper() and
            1 < len(clean_cue) < 35 and
            not clean_cue.endswith(":") and
            clean_cue not in NON_CHARACTER_TOKENS and
            not any(clean_cue.startswith(x) for x in ["INT.", "EXT.", "CUT TO", "FADE", "SCENE", "MATCH CUT", "SMASH CUT", "DISSOLVE"])
        )

        if is_char_cue and not pending_character:
            flush_seg_dialogue()
            pending_character = clean_cue
        elif pending_character and stripped.startswith("(") and stripped.endswith(")"):
            pending_parenthetical = stripped[1:-1].strip()
        elif pending_character and stripped:
            pending_dialogue_lines.append(stripped)
        else:
            flush_seg_dialogue()
            current_actions.append(stripped)

    # Commit final segment
    commit_segment()
    return segments


def generate_multi_cam_prompts(
    scene: ScreenplayScene,
    shot_number: str,
    action_text: str,
    dop_spec: DoPSpecification,
    aspect_ratio: str = "2.39:1",
    characters_in_shot: Optional[List[str]] = None,
    character_profiles_map: Optional[Dict[str, CharacterProfile]] = None,
    primary_shot_size: str = "WS",
    primary_camera_angle: str = "EYE_LEVEL",
    primary_camera_movement: str = "STATIC"
) -> List[CameraAngleProposal]:
    """
    Generates synchronized multi-camera angle proposals (Camera A, B, C)
    customized for spatial coverage, character visual consistency, and DoP optics.
    """
    chars = characters_in_shot or scene.characters
    is_dialogue_or_character = bool(scene.dialogues) or bool(chars)

    # Calculate camera rig parameters based on primary shot size
    if primary_shot_size in ["EWS", "WS", "MWS"]:
        cam_a_focal = 28 if "EXT" in scene.environment else 35
        cam_a_aperture = "T2.8"
        cam_a_size = primary_shot_size

        cam_b_focal = 50 if is_dialogue_or_character else 65
        cam_b_size = "OTS" if is_dialogue_or_character else "MS"
        cam_b_aperture = "T2.0"

        cam_c_focal = 85 if is_dialogue_or_character else 100
        cam_c_size = "CU" if is_dialogue_or_character else "INSERT"
        cam_c_aperture = "T1.4"
    elif primary_shot_size in ["CU", "ECU", "INSERT"]:
        cam_a_focal = 85
        cam_a_aperture = "T1.8"
        cam_a_size = primary_shot_size

        cam_b_focal = 50
        cam_b_size = "MCU" if is_dialogue_or_character else "MS"
        cam_b_aperture = "T2.0"

        cam_c_focal = 100
        cam_c_size = "ECU" if primary_shot_size == "CU" else "INSERT"
        cam_c_aperture = "T1.4"
    else:  # MS, MCU, OTS, POV
        cam_a_focal = 50
        cam_a_aperture = "T2.0"
        cam_a_size = primary_shot_size

        cam_b_focal = 65
        cam_b_size = "MCU" if is_dialogue_or_character else "MS"
        cam_b_aperture = "T2.0"

        cam_c_focal = 85
        cam_c_size = "CU"
        cam_c_aperture = "T1.4"

    # 1. Camera A - Primary Setup
    cam_a_prompt = synthesize_cinematic_prompt(
        scene=scene,
        camera_letter="A",
        shot_size=cam_a_size,
        camera_angle=primary_camera_angle,
        camera_movement=primary_camera_movement,
        focal_length=cam_a_focal,
        aperture=cam_a_aperture,
        subject_action=f"Primary coverage capturing {action_text}",
        dop_spec=dop_spec,
        aspect_ratio=aspect_ratio,
        characters_in_shot=chars,
        character_profiles_map=character_profiles_map
    )
    cam_a = CameraAngleProposal(
        camera_letter="A",
        camera_role=f"Primary Setup ({cam_a_size} Coverage)",
        shot_size=cam_a_size,
        focal_length=cam_a_focal,
        aperture=cam_a_aperture,
        camera_angle=primary_camera_angle,
        camera_movement=primary_camera_movement,
        coverage_description=f"Primary angle capturing {cam_a_size} composition with {cam_a_focal}mm lens.",
        prompt=cam_a_prompt,
        status="pending"
    )

    # 2. Camera B - Secondary Coverage / Over-the-Shoulder / Medium
    cam_b_prompt = synthesize_cinematic_prompt(
        scene=scene,
        camera_letter="B",
        shot_size=cam_b_size,
        camera_angle="EYE_LEVEL",
        camera_movement="HANDHELD" if "Handheld" in dop_spec.dop_preset else "STATIC",
        focal_length=cam_b_focal,
        aperture=cam_b_aperture,
        subject_action=f"Secondary reaction and dialogue coverage focusing on {action_text}",
        dop_spec=dop_spec,
        aspect_ratio=aspect_ratio,
        characters_in_shot=chars,
        character_profiles_map=character_profiles_map
    )
    cam_b = CameraAngleProposal(
        camera_letter="B",
        camera_role=f"Secondary Coverage ({cam_b_size})",
        shot_size=cam_b_size,
        focal_length=cam_b_focal,
        aperture=cam_b_aperture,
        camera_angle="EYE_LEVEL",
        camera_movement="STATIC",
        coverage_description=f"Secondary coverage focused on character performance and dialogue reaction in {cam_b_size}.",
        prompt=cam_b_prompt,
        status="pending"
    )

    # 3. Camera C - Profile / Macro / Tactile Insert Setup
    cam_c_prompt = synthesize_cinematic_prompt(
        scene=scene,
        camera_letter="C",
        shot_size=cam_c_size,
        camera_angle="DUTCH_ANGLE" if "Fincher" in dop_spec.dop_preset else "EYE_LEVEL",
        camera_movement="SLIDER",
        focal_length=cam_c_focal,
        aperture=cam_c_aperture,
        subject_action=f"Tight macro close-up insert capturing tactile details and intensity of {action_text}",
        dop_spec=dop_spec,
        aspect_ratio=aspect_ratio,
        characters_in_shot=chars,
        character_profiles_map=character_profiles_map
    )
    cam_c = CameraAngleProposal(
        camera_letter="C",
        camera_role=f"Tertiary Accent Setup ({cam_c_size})",
        shot_size=cam_c_size,
        focal_length=cam_c_focal,
        aperture=cam_c_aperture,
        camera_angle="EYE_LEVEL",
        camera_movement="SLIDER",
        coverage_description=f"Intimate {cam_c_size} isolating expressive eyes, hands, or critical set props in razor-thin focus.",
        prompt=cam_c_prompt,
        status="pending"
    )

    return [cam_a, cam_b, cam_c]


def _deterministic_breakdown_scene_to_shots(
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
    
    If the screenplay includes explicit 'CUT TO:' or transition markers, the scene is divided
    directly into sequential shot setups demarcated by those cuts.
    Otherwise, generates master establishing, key dialogue coverage, and climax insert setups.
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

    # Check if the scene contains explicit 'CUT TO:' transition markers
    cut_segments = parse_scene_into_shot_segments(scene)

    if len(cut_segments) > 1:
        # Generate shot setups directly from the screenplay's explicit cut boundaries
        for idx, seg in enumerate(cut_segments):
            shot_num = str(idx + 1)
            trans = seg.get("transition")
            actions = seg.get("actions", [])
            dialogues = seg.get("dialogues", [])
            chars = seg.get("characters", [])

            # Build subject action description
            action_desc = " ".join(actions) if actions else ""
            dialogue_desc = ""
            if dialogues:
                dialogue_snippets = [f"{d[0]} speaks: \"{d[2][:50]}\"" for d in dialogues[:2]]
                dialogue_desc = "; ".join(dialogue_snippets)
            
            full_subject = f"{action_desc} {dialogue_desc}".strip() or f"Scene coverage for {scene.location}"

            # Infer shot dynamics
            has_dial = bool(dialogues)
            is_first = (idx == 0)
            inferred_size, inferred_angle, inferred_move = infer_shot_size_and_dynamics(
                text=full_subject,
                has_dialogue=has_dial,
                is_first_shot=is_first
            )

            # Naming and dramatic beat
            if trans:
                clean_trans = trans.rstrip(":")
                summary = actions[0][:30] if actions else (dialogues[0][0] if dialogues else "Cut")
                shot_name = f"SCENE {scene.scene_number} - SHOT {shot_num} ({clean_trans}: {summary})"
                dramatic_beat = f"Transition: {clean_trans} & Visual Beat Shift"
            elif is_first:
                shot_name = f"SCENE {scene.scene_number} - SHOT {shot_num} (Master Establishing)"
                dramatic_beat = "Scene Establishment & Spatial Geometry"
            else:
                summary = actions[0][:30] if actions else "Action Beat"
                shot_name = f"SCENE {scene.scene_number} - SHOT {shot_num} ({summary})"
                dramatic_beat = "Dynamic Narrative Coverage"

            # Generate multi-camera proposals for this cut setup
            cameras = generate_multi_cam_prompts(
                scene=scene,
                shot_number=shot_num,
                action_text=full_subject,
                dop_spec=dop_spec,
                aspect_ratio=aspect_ratio,
                characters_in_shot=chars or scene.characters,
                character_profiles_map=char_map,
                primary_shot_size=inferred_size,
                primary_camera_angle=inferred_angle,
                primary_camera_movement=inferred_move
            )

            shot = ShotProposal(
                scene_number=scene.scene_number,
                shot_number=shot_num,
                shot_name=shot_name,
                shot_size=inferred_size,
                camera_angle=inferred_angle,
                camera_movement=inferred_move,
                dramatic_beat=dramatic_beat,
                subject_description=full_subject,
                characters=chars or scene.characters,
                dop_spec=dop_spec,
                cameras=cameras,
                active_camera="A",
                storyboard=StoryboardFrame(
                    prompt=cameras[0].prompt if cameras else "",
                    aspect_ratio=aspect_ratio,
                    status="pending"
                )
            )
            shots.append(shot)

        return shots

    # Fallback / Standard Breakdown when no explicit CUT TO: markers are present
    
    # 1. Establishing / Master Shot
    master_action = scene.action_blocks[0] if scene.action_blocks else f"Establishing coverage of {scene.location}"
    master_cameras = generate_multi_cam_prompts(
        scene=scene,
        shot_number="1",
        action_text=master_action,
        dop_spec=dop_spec,
        aspect_ratio=aspect_ratio,
        characters_in_shot=scene.characters,
        character_profiles_map=char_map,
        primary_shot_size="WS",
        primary_camera_angle="EYE_LEVEL",
        primary_camera_movement="STATIC"
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
                character_profiles_map=char_map,
                primary_shot_size="MS",
                primary_camera_angle="EYE_LEVEL",
                primary_camera_movement="STATIC"
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
            character_profiles_map=char_map,
            primary_shot_size="CU",
            primary_camera_angle="DUTCH_ANGLE" if "Fincher" in dop_style_name else "EYE_LEVEL",
            primary_camera_movement="SLIDER"
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


async def breakdown_scene_to_shots(
    scene: ScreenplayScene,
    dop_style_name: str = "Roger Deakins",
    dop_overrides: Optional[Dict[str, Any]] = None,
    custom_mood_prompt: Optional[str] = None,
    aspect_ratio: str = "2.39:1",
    character_profiles: Optional[List[CharacterProfile]] = None
) -> List[ShotProposal]:
    dop_spec = resolve_dop_specification(
        preset_name=dop_style_name,
        custom_prompt=custom_mood_prompt,
        overrides=dop_overrides
    )
    
    char_map = {}
    if character_profiles:
        for p in character_profiles:
            char_map[p.name.upper()] = p

    cut_segments = parse_scene_into_shot_segments(scene)
    
    if is_agent_enabled():
        agent_data = await run_dop_agent(scene, dop_spec, cut_segments)
        if agent_data:
            shots = []
            for idx, setup in enumerate(agent_data):
                shot_num = str(idx + 1)
                
                cameras = []
                for cam_data in setup.get("cameras", []):
                    # Safely handle missing keys by providing defaults
                    c_letter = cam_data.get("camera_letter", "A")
                    c_size = cam_data.get("shot_size", "WS")
                    c_focal = cam_data.get("focal_length", 35)
                    c_angle = cam_data.get("camera_angle", "EYE_LEVEL")
                    c_move = cam_data.get("camera_movement", "STATIC")
                    
                    # Synthesize prompt
                    prompt = synthesize_cinematic_prompt(
                        scene=scene,
                        camera_letter=c_letter,
                        shot_size=c_size,
                        camera_angle=c_angle,
                        camera_movement=c_move,
                        focal_length=c_focal,
                        aperture=cam_data.get("aperture", "T2.8"),
                        dop_spec=dop_spec,
                        aspect_ratio=aspect_ratio,
                        characters_in_shot=setup.get("characters", scene.characters),
                        character_profiles_map=char_map,
                        # The parameter is subject_action. This said action_text
                        # and raised TypeError on every run where Gemini answered,
                        # so the agent path 500'd and only the deterministic
                        # fallback ever reached the screen (2026-09-08).
                        subject_action=setup.get("subject_description", ""),
                    )
                    
                    cam_prop = CameraAngleProposal(
                        camera_letter=c_letter,
                        camera_role=cam_data.get("camera_role", "Coverage"),
                        shot_size=c_size,
                        focal_length=c_focal,
                        aperture=cam_data.get("aperture", "T2.8"),
                        camera_angle=c_angle,
                        camera_movement=c_move,
                        coverage_description=cam_data.get("coverage_description", ""),
                        prompt=prompt
                    )
                    cameras.append(cam_prop)
                
                # Ensure at least Camera A exists
                if not cameras:
                    continue
                    
                active_cam = cameras[0]
                shot = ShotProposal(
                    scene_number=scene.scene_number,
                    shot_number=shot_num,
                    shot_name=f"SCENE {scene.scene_number} - SHOT {shot_num} ({setup.get('setup_name', 'Setup')})",
                    shot_size=active_cam.shot_size,
                    camera_angle=active_cam.camera_angle,
                    camera_movement=active_cam.camera_movement,
                    dramatic_beat=setup.get("dramatic_beat", ""),
                    subject_description=setup.get("subject_description", ""),
                    characters=setup.get("characters", scene.characters),
                    dop_spec=dop_spec,
                    cameras=cameras,
                    active_camera=active_cam.camera_letter,
                    storyboard=StoryboardFrame(
                        prompt=active_cam.prompt,
                        aspect_ratio=aspect_ratio,
                        status="pending"
                    )
                )
                shots.append(shot)
            
            if shots:
                return shots

    # Fallback to deterministic logic
    return _deterministic_breakdown_scene_to_shots(
        scene, dop_style_name, dop_overrides, custom_mood_prompt, aspect_ratio, character_profiles
    )
