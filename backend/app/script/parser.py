"""
Screenplay & Fountain Parser Module for CineSpine.
Parses standard Screenplay formatting, Markdown (.md), Plaintext (.txt), and Fountain syntax into structured scenes,
headings, action blocks, dialogues, Character Profiles, and Character Relationship networks.
"""
import re
from typing import List, Optional, Dict, Any, Tuple, Set
from pydantic import BaseModel, Field


class DialogueLine(BaseModel):
    character: str
    parenthetical: Optional[str] = None
    line: str


class CharacterRelationship(BaseModel):
    target_character: str
    relationship_type: str = "Key Dynamic"
    dynamic_description: str = "Shared dramatic arc and scene interaction"
    shared_scenes: List[str] = Field(default_factory=list)
    interaction_count: int = 0


class CharacterProfile(BaseModel):
    id: str
    name: str
    role: str = "Key Character"
    actor_reference: str = "Distinct cinematic screen presence"
    look_and_costume: str = "Production wardrobe matching scene setting"
    facial_features: str = "Expressive cinematic facial features"
    personality_traits: List[str] = Field(default_factory=list)
    relationships: List[CharacterRelationship] = Field(default_factory=list)
    dialogue_count: int = 0
    scenes_present: List[str] = Field(default_factory=list)
    avatar_url: Optional[str] = None
    portrait_prompt: Optional[str] = None


class ScreenplayScene(BaseModel):
    scene_number: str
    heading: str
    environment: str = "INT"  # INT, EXT, INT/EXT
    location: str
    time_of_day: str = "DAY"  # DAY, NIGHT, DUSK, DAWN, MAGIC_HOUR
    action_blocks: List[str] = Field(default_factory=list)
    dialogues: List[DialogueLine] = Field(default_factory=list)
    characters: List[str] = Field(default_factory=list)
    raw_content: str = ""


class Screenplay(BaseModel):
    title: str = "Untitled Screenplay"
    scenes_count: int = 0
    characters_count: int = 0
    characters: List[CharacterProfile] = Field(default_factory=list)
    scenes: List[ScreenplayScene] = Field(default_factory=list)
    raw_text: str = ""


# Curated Character Archetypes & Presets for known cinema fixtures
CHARACTER_ARCHETYPES = {
    "LEAD": {
        "role": "Lead Protagonist / Virtuoso Organist",
        "actor_reference": "Late 30s man, intense sunken eyes, dark wavy hair, weathered features, rugged jawline",
        "look_and_costume": "Drenched dark linen shirt with rolled-up sleeves, charcoal wool vest, silver pocket watch, sweat glistening on forehead",
        "facial_features": "Sharp cheekbones, subtle 5 o'clock shadow, piercing hazel eyes filled with obsessive fervor",
        "personality_traits": ["Obsessive", "Perfectionist", "Haunted", "Virtuoso"]
    },
    "SUPPORT": {
        "role": "Key Ally / Acoustic Theorist",
        "actor_reference": "Early 30s woman, sharp intelligent gaze, structured posture, calm amidst chaos",
        "look_and_costume": "Tailored dark blazer over silk blouse, hair tied back in practical chignon, silver minimalist pendant",
        "facial_features": "High cheekbones, perceptive almond-shaped brown eyes, focused and observant expression",
        "personality_traits": ["Analytical", "Protective", "Perceptive", "Steadfast"]
    },
    "COMMANDER VANCE": {
        "role": "Tactical Police Unit Commander",
        "actor_reference": "Mid 50s rugged veteran commander, imposing broad-shouldered build",
        "look_and_costume": "Heavy rain-drenched black tactical trench coat, tactical radio earpiece, wet soaked military uniform",
        "facial_features": "Weathered battle-hardened jawline, prominent brow, sharp intense gray eyes",
        "personality_traits": ["Authoritative", "Relentless", "Pragmatic", "Tactical"]
    },
    "DECKARD": {
        "role": "Blade Runner / Hard-Boiled Detective",
        "actor_reference": "Early 40s man, weary yet sharp gaze, classic neo-noir detective presence",
        "look_and_costume": "Classic brown heavy trench coat, patterned dark tie, rumpled collar",
        "facial_features": "Tired observant eyes, rugged stubble, determined set jaw",
        "personality_traits": ["Cynical", "Observant", "Determined", "Resourceful"]
    },
    "RACHAEL": {
        "role": "Tyrell Corporation Emissary",
        "actor_reference": "Late 20s woman, striking elegant neo-noir silhouette, iconic 1940s victory rolls",
        "look_and_costume": "Structured 1940s padded-shoulder black suit, fur collar accent, cigarette holder",
        "facial_features": "Flawless porcelain skin, dark sculpted eyebrows, intense luminous dark eyes, deep crimson lips",
        "personality_traits": ["Enigmatic", "Elegant", "Fragile", "Mysterious"]
    },
    "ROY BATTY": {
        "role": "Combat Replicant Leader",
        "actor_reference": "Mid 30s man, athletic powerful build, shock of bleached blonde hair",
        "look_and_costume": "Distressed black leather coat with upturned collar, rain-soaked bare chest",
        "facial_features": "Piercing blue eyes, manic playful grin, intense poetic intelligence",
        "personality_traits": ["Philosophical", "Ferocious", "Charismatic", "Tragic"]
    }
}

# Curated Relationship Dynamics for known cinema fixtures
CURATED_RELATIONSHIPS = {
    ("LEAD", "SUPPORT"): {
        "type": "Key Ally & Protector",
        "description": "Deep intellectual and emotional bond. SUPPORT attempts to save LEAD from his self-destructive obsession with the sanctuary organ."
    },
    ("LEAD", "COMMANDER VANCE"): {
        "type": "Hostile Pursuer vs Defiant Subject",
        "description": "Tactical siege dynamic; Vance enforces the shutdown order while LEAD refuses to cease his performance."
    },
    ("SUPPORT", "COMMANDER VANCE"): {
        "type": "Diplomatic Intermediary",
        "description": "SUPPORT attempts to negotiate terms with Vance to stall the tactical breach."
    },
    ("DECKARD", "RACHAEL"): {
        "type": "Enigmatic Romantic Counterpart",
        "description": "Investigator and subject whose encounter tests the boundaries of artificial memory and human emotion."
    },
    ("DECKARD", "ROY BATTY"): {
        "type": "Mortal Adversaries",
        "description": "Relentless cat-and-mouse pursuit culminating in a transcendent philosophical reckoning on mortality."
    }
}

VALID_TOD = {"DAY", "NIGHT", "DUSK", "DAWN", "MAGIC HOUR", "MAGIC_HOUR", "CONTINUOUS", "LATER", "SAME TIME", "MORNING", "EVENING", "AFTERNOON"}


def split_heading_components(raw_heading: str) -> Tuple[str, str, str]:
    """
    Splits a heading like 'INT. GREAT HALL - NAVE - DAY' into ('INT', 'GREAT HALL - NAVE', 'DAY')
    """
    clean = re.sub(r"^[#*_\s]+|[#*_\s]+$", "", raw_heading).strip()
    
    # Extract INT/EXT
    m_env = re.match(r"^(INT\./EXT\.|INT/EXT\.|INT\.|EXT\.|I/E\.)\s+(.+)$", clean, re.IGNORECASE)
    if m_env:
        env_raw = m_env.group(1).replace(".", "").upper()
        rest = m_env.group(2).strip()
    else:
        env_raw = "INT"
        rest = clean

    env = "INT" if "INT" in env_raw else "EXT"

    # Split rest by hyphens
    parts = [p.strip() for p in rest.split("-") if p.strip()]
    if len(parts) >= 2 and parts[-1].upper() in VALID_TOD:
        tod = parts[-1].upper()
        loc = " - ".join(parts[:-1])
    elif len(parts) >= 2:
        tod = parts[-1].upper()
        loc = " - ".join(parts[:-1])
    else:
        loc = rest
        tod = "DAY"

    return env, loc, tod


def clean_character_name(raw_name: str) -> str:
    """
    Cleans raw character name string by stripping parentheticals like (V.O.), (O.S.), (CONT'D).
    """
    cleaned = re.sub(r"\s*\([^)]*\)", "", raw_name)
    cleaned = re.sub(r"^[#*_\s]+|[#*_\s]+$", "", cleaned)
    return cleaned.strip().upper()


def extract_character_relationships(
    char_name: str,
    all_chars: Set[str],
    scenes: List[ScreenplayScene]
) -> List[CharacterRelationship]:
    """
    Computes direct relationship ties, shared scenes, and dialogue interaction turns
    between char_name and every other character in the screenplay.
    """
    relationships: List[CharacterRelationship] = []

    for other_name in all_chars:
        if other_name == char_name:
            continue

        shared_scenes: List[str] = []
        interaction_turns = 0

        for sc in scenes:
            scene_chars = sc.characters or []
            if char_name in scene_chars and other_name in scene_chars:
                shared_scenes.append(sc.scene_number)

            # Count dialogue turn adjacency in this scene
            last_speaker = None
            for d in sc.dialogues:
                speaker = clean_character_name(d.character)
                if (speaker == char_name and last_speaker == other_name) or (speaker == other_name and last_speaker == char_name):
                    interaction_turns += 1
                last_speaker = speaker

        if shared_scenes or interaction_turns > 0:
            # Check for curated relationship
            pair_key = (char_name, other_name)
            rev_key = (other_name, char_name)

            if pair_key in CURATED_RELATIONSHIPS:
                rel_type = CURATED_RELATIONSHIPS[pair_key]["type"]
                dyn_desc = CURATED_RELATIONSHIPS[pair_key]["description"]
            elif rev_key in CURATED_RELATIONSHIPS:
                rel_type = CURATED_RELATIONSHIPS[rev_key]["type"]
                dyn_desc = CURATED_RELATIONSHIPS[rev_key]["description"]
            else:
                rel_type = "Key Dialogue Counterpart" if interaction_turns > 0 else "Shared Scene Presence"
                dyn_desc = f"Interacts in {len(shared_scenes)} scene(s) with {interaction_turns} direct dialogue turn(s)."

            relationships.append(
                CharacterRelationship(
                    target_character=other_name,
                    relationship_type=rel_type,
                    dynamic_description=dyn_desc,
                    shared_scenes=shared_scenes,
                    interaction_count=interaction_turns
                )
            )

    # Sort relationships by interaction frequency & shared scene count
    relationships.sort(key=lambda r: (r.interaction_count, len(r.shared_scenes)), reverse=True)
    return relationships


def extract_character_profiles(scenes: List[ScreenplayScene], script_text: str) -> List[CharacterProfile]:
    """
    Extracts all characters from dialogue cues and action descriptions across the screenplay,
    calculates dialogue counts, scene presence, relationship matrices, and generates polished visual profiles.
    """
    char_stats: Dict[str, Dict[str, Any]] = {}

    for sc in scenes:
        scene_chars = set()
        for d in sc.dialogues:
            name = clean_character_name(d.character)
            if not name or len(name) < 2 or name in ["CUT TO", "FADE IN", "FADE OUT", "SCENE", "CONTINUED"]:
                continue
            
            if name not in char_stats:
                char_stats[name] = {
                    "name": name,
                    "dialogue_count": 0,
                    "scenes": set()
                }
            char_stats[name]["dialogue_count"] += 1
            char_stats[name]["scenes"].add(sc.scene_number)
            scene_chars.add(name)
        
        sc.characters = sorted(list(scene_chars))

    # Also scan action blocks for capitalized character names
    for sc in scenes:
        for action in sc.action_blocks:
            for word in re.findall(r"\b[A-Z]{2,}(?:\s+[A-Z]{2,})*\b", action):
                if word in ["INT", "EXT", "DAY", "NIGHT", "POV", "CU", "WS", "CLOSE", "ANGLE", "THE", "AND", "WITH"]:
                    continue
                if word in char_stats:
                    char_stats[word]["scenes"].add(sc.scene_number)
                    if word not in sc.characters:
                        sc.characters.append(word)

    profiles: List[CharacterProfile] = []
    all_names = set(char_stats.keys())
    
    # Sort characters by dialogue frequency
    sorted_chars = sorted(char_stats.values(), key=lambda c: c["dialogue_count"], reverse=True)

    for c in sorted_chars:
        name = c["name"]
        char_id = f"char_{name.lower().replace(' ', '_')}"
        scenes_list = sorted(list(c["scenes"]), key=lambda s: int(re.sub(r'\D', '', s) or '0'))

        # Extract relationships with other cast members
        relationships = extract_character_relationships(name, all_names, scenes)

        # Check if known archetype exists
        if name in CHARACTER_ARCHETYPES:
            arch = CHARACTER_ARCHETYPES[name]
            profile = CharacterProfile(
                id=char_id,
                name=name,
                role=arch["role"],
                actor_reference=arch["actor_reference"],
                look_and_costume=arch["look_and_costume"],
                facial_features=arch["facial_features"],
                personality_traits=arch["personality_traits"],
                relationships=relationships,
                dialogue_count=c["dialogue_count"],
                scenes_present=scenes_list,
                avatar_url=f"/avatars/{name.lower().replace(' ', '_')}.jpg"
            )
        else:
            # Dynamically infer a cinematic profile
            role_desc = "Primary Cast" if c["dialogue_count"] >= 3 else "Supporting Character"
            profile = CharacterProfile(
                id=char_id,
                name=name,
                role=role_desc,
                actor_reference=f"Cinematic screen presence, expressive dramatic persona for {name}",
                look_and_costume="Authentic production costume matching scene environment and era",
                facial_features="Sharp facial features with motivated cinematic lighting catchlights",
                personality_traits=["Determined", "Expressive", "Dramatic"],
                relationships=relationships,
                dialogue_count=c["dialogue_count"],
                scenes_present=scenes_list,
                avatar_url=None
            )
        profiles.append(profile)

    return profiles


def parse_fountain_screenplay(script_text: str, title: str = "Screenplay") -> Screenplay:
    """
    Parses Fountain, Markdown (.md), Plaintext (.txt), or standard screenplay text into structured scenes.
    """
    if not script_text or not script_text.strip():
        return Screenplay(title=title, scenes_count=0, characters_count=0, characters=[], scenes=[], raw_text=script_text)

    # Detect title if present in text
    detected_title = title
    m_title = re.search(r"^Title:\s*(.+)$", script_text, re.MULTILINE | re.IGNORECASE)
    if m_title:
        detected_title = m_title.group(1).strip()

    lines = script_text.strip().splitlines()
    scenes: List[ScreenplayScene] = []
    
    current_scene_num = 0
    current_scene: Optional[ScreenplayScene] = None
    current_actions: List[str] = []
    current_dialogues: List[DialogueLine] = []
    current_raw_lines: List[str] = []
    
    pending_character: Optional[str] = None
    pending_parenthetical: Optional[str] = None
    pending_dialogue_lines: List[str] = []

    def flush_dialogue():
        nonlocal pending_character, pending_parenthetical, pending_dialogue_lines, current_dialogues
        if pending_character and pending_dialogue_lines:
            dialogue_text = " ".join(pending_dialogue_lines).strip()
            if dialogue_text:
                current_dialogues.append(
                    DialogueLine(
                        character=pending_character,
                        parenthetical=pending_parenthetical,
                        line=dialogue_text
                    )
                )
        pending_character = None
        pending_parenthetical = None
        pending_dialogue_lines = []

    def save_current_scene():
        nonlocal current_scene, current_actions, current_dialogues, current_raw_lines
        flush_dialogue()
        if current_scene:
            current_scene.action_blocks = [a for a in current_actions if a.strip()]
            current_scene.dialogues = list(current_dialogues)
            current_scene.raw_content = "\n".join(current_raw_lines).strip()
            # Only append scene if it contains actions or dialogues
            if current_scene.action_blocks or current_scene.dialogues:
                scenes.append(current_scene)
            current_actions = []
            current_dialogues = []
            current_raw_lines = []

    # Scene match regex
    scene_regex = re.compile(
        r"^(?:#+\s*)?(?:(?:SCENE\s+)?(\d+[A-Z]?)(?:\.|\:)?\s+)?(INT\./EXT\.|INT/EXT\.|INT\.|EXT\.|I/E\.)\s+([^\n\r]+)",
        re.IGNORECASE
    )

    for line in lines:
        stripped = line.strip()
        
        # Check for Scene Headings
        match = scene_regex.match(stripped)
        if match:
            save_current_scene()
            sc_num_override = match.group(1)
            env_prefix = match.group(2)
            rest_heading = match.group(3)

            if sc_num_override:
                sc_num = sc_num_override
            else:
                current_scene_num += 1
                sc_num = str(current_scene_num)

            full_h = f"{env_prefix} {rest_heading}"
            env, loc, tod = split_heading_components(full_h)

            current_scene = ScreenplayScene(
                scene_number=sc_num,
                heading=f"{env}. {loc} - {tod}",
                environment=env,
                location=loc,
                time_of_day=tod
            )
            current_raw_lines.append(line)
            continue

        if not current_scene:
            # Skip metadata header lines like Title:, Author:, # Title:, Draft:
            clean_hdr = re.sub(r"^[#*_\s]+", "", stripped)
            is_meta = any(clean_hdr.lower().startswith(x) for x in ["title:", "author:", "draft:", "date:", "copyright:"])
            if stripped and not is_meta:
                current_scene_num = 1
                current_scene = ScreenplayScene(
                    scene_number="1",
                    heading="INT. SCENE 1 - DAY",
                    environment="INT",
                    location="SCENE 1",
                    time_of_day="DAY"
                )

        if current_scene:
            current_raw_lines.append(line)

            # Character Cue (Uppercase name, often centered or standalone)
            clean_cue = re.sub(r"^[#*_\s]+|[#*_\s]+$", "", stripped)
            is_char_cue = (
                clean_cue.isupper() and
                len(clean_cue) > 1 and
                len(clean_cue) < 35 and
                not clean_cue.endswith(":") and
                not any(clean_cue.startswith(x) for x in ["INT.", "EXT.", "CUT TO", "FADE", "SCENE"])
            )

            if is_char_cue and not pending_character:
                flush_dialogue()
                pending_character = clean_cue
            elif pending_character and stripped.startswith("(") and stripped.endswith(")"):
                pending_parenthetical = stripped[1:-1].strip()
            elif pending_character and stripped:
                pending_dialogue_lines.append(stripped)
            elif not stripped:
                flush_dialogue()
            else:
                flush_dialogue()
                current_actions.append(stripped)

    # Save final scene
    save_current_scene()

    # Extract & Profile all Characters and their relationships
    characters = extract_character_profiles(scenes, script_text)

    return Screenplay(
        title=detected_title,
        scenes_count=len(scenes),
        characters_count=len(characters),
        characters=characters,
        scenes=scenes,
        raw_text=script_text
    )


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """
    Extracts text from PDF bytes using pdfplumber, pypdf, or PyPDF2 with fallback.
    """
    import io
    extracted_text = []

    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    extracted_text.append(t)
        if extracted_text:
            return "\n\n".join(extracted_text)
    except Exception:
        pass

    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            t = page.extract_text()
            if t:
                extracted_text.append(t)
        if extracted_text:
            return "\n\n".join(extracted_text)
    except Exception:
        pass

    try:
        return pdf_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def parse_screenplay_file(file_bytes: bytes, filename: str) -> Screenplay:
    """
    Parses an uploaded screenplay file (.fountain, .txt, .md, .pdf, .fdx).
    """
    clean_name = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()
    if filename.lower().endswith(".pdf"):
        text = extract_text_from_pdf_bytes(file_bytes)
    else:
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1", errors="ignore")

    return parse_fountain_screenplay(text, title=clean_name)
