"""
Screenplay & Fountain Parser Module for CineSpine.
Parses standard Screenplay formatting, Markdown (.md), Plaintext (.txt), and Fountain syntax into structured scenes,
headings, action blocks, dialogues, Character Profiles, and Character Relationship networks.
"""
import logging
import hashlib
import re
from typing import List, Optional, Dict, Any, Tuple, Set
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def compute_script_id(script_text: str) -> str:
    """
    Stable identity for a screenplay, derived from its text. Re-uploading the
    same script yields the same id, so previously saved character profiles are
    reattached instead of being regenerated from scratch.
    """
    normalized = "\n".join(line.rstrip() for line in (script_text or "").strip().splitlines())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


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
    # Five scored axes, or absent. A score may be null where the script does
    # not support one -- see character_ai.PERSONALITY_AXES. Kept as a plain
    # dict rather than a model so an axis the inference did not fill stays
    # null instead of acquiring a default.
    personality_axes: Optional[Dict[str, Any]] = None
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
    # Stable identity derived from the script text, so re-uploading the same
    # screenplay resolves to the same stored character profiles.
    script_id: str = ""
    author: Optional[str] = None
    scenes_count: int = 0
    characters_count: int = 0
    characters: List[CharacterProfile] = Field(default_factory=list)
    scenes: List[ScreenplayScene] = Field(default_factory=list)
    raw_text: str = ""
    # Non-fatal parse observations, so the UI can say what looked wrong instead
    # of silently presenting a bad parse as success.
    parse_warnings: List[str] = Field(default_factory=list)


# Tokens that look like character cues but are structural screenplay elements.
NON_CHARACTER_TOKENS = {
    "INT", "EXT", "DAY", "NIGHT", "POV", "CU", "WS", "CLOSE", "ANGLE", "THE", "AND",
    "WITH", "CUT TO", "FADE IN", "FADE OUT", "FADE TO", "DISSOLVE TO", "SMASH CUT",
    "MATCH CUT", "BACK TO", "CONTINUED", "SCENE", "TITLE", "SUPER", "INSERT",
    "MONTAGE", "END MONTAGE", "INTERCUT", "THE END", "OMITTED", "LATER",
    "CONTINUOUS", "MOMENTS LATER", "WRITTEN BY", "BY", "CUT TO BLACK", "FADE TO BLACK",
    "SMASH CUT TO", "MATCH CUT TO", "JUMP CUT TO", "QUICK CUT TO", "HARD CUT TO",
    "TIME CUT TO", "FLASH CUT TO", "CROSS CUT TO", "DISSOLVE TO",
}

# Regex for standard screenplay / fountain transitions (e.g. "CUT TO:", "> SMASH CUT TO:", "DISSOLVE TO:")
TRANSITION_REGEX = re.compile(
    r"^(?:>|>\s*)?(?:(?:SMASH|MATCH|DISSOLVE|JUMP|QUICK|HARD|TIME|FLASH|CROSS)?\s*CUT\s+TO(?:\s+BLACK|\s+WHITE)?|FADE\s+(?:IN|OUT|TO\s+BLACK|TO\s+WHITE)|DISSOLVE\s+TO|INTERCUT)(?:\:|\.|\s*<)?$",
    re.IGNORECASE
)


def is_transition_cue(line: str) -> bool:
    """
    Identifies whether a line is a screenplay transition slug (e.g., 'CUT TO:', '> SMASH CUT TO:', 'DISSOLVE TO:').
    Transitions signal shot/scene boundary shifts and must never be treated as characters.
    """
    clean = re.sub(r"^[#*_\s>]+|[#*_\s<]+$", "", line).strip()
    if not clean:
        return False
    if TRANSITION_REGEX.match(clean):
        return True
    if clean.isupper() and (clean.endswith("TO:") or clean.endswith("TO BLACK.") or clean.endswith("TO WHITE.") or clean == "CUT TO"):
        return True
    return False


# Metadata keys that may appear in a title block before the first scene heading.
TITLE_BLOCK_KEYS = (
    "title:", "author:", "authors:", "written by:", "draft:", "date:", "contact:",
    "copyright:", "source:", "credit:", "notes:", "revision:",
)

# Descriptor mined from an action line, e.g. "MAYA CHEN, 30s, sits hunched over a console."
DESCRIPTOR_RE = re.compile(
    r"\b([A-Z][A-Z0-9'\-]*(?:\s+[A-Z][A-Z0-9'\-]*){0,3})\s*,\s*([^.;]{3,120})"
)
AGE_RE = re.compile(
    r"\b((?:early|mid|late)[\s-]+\d{2}s|\d{2}s|\d{1,2}\s*(?:years old|yo)|aged?\s*\d{1,2})\b",
    re.IGNORECASE,
)


VALID_TOD = {"DAY", "NIGHT", "DUSK", "DAWN", "MAGIC HOUR", "MAGIC_HOUR", "CONTINUOUS", "LATER", "SAME TIME", "MORNING", "EVENING", "AFTERNOON"}

# Scene heading, e.g. "INT. RADIO STATION - NIGHT", "## 12. EXT. ROOF - DAY".
SCENE_REGEX = re.compile(
    r"^(?:#+\s*)?(?:(?:SCENE\s+)?(\d+[A-Z]?)(?:\.|\:)?\s+)?(INT\./EXT\.|INT/EXT\.|INT\.|EXT\.|I/E\.)\s+([^\n\r]+)",
    re.IGNORECASE,
)


def parse_title_block(block_lines: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Reads the metadata block that precedes the first scene heading.

    Handles both Fountain key/value form ("Title: The Last Signal") and the
    common plain form where the title is simply the first line, optionally
    followed by a "Written by ..." credit.
    """
    title: Optional[str] = None
    author: Optional[str] = None

    for raw in block_lines:
        line = re.sub(r"^[#*_>\s]+|[*_\s]+$", "", raw).strip()
        if not line:
            continue

        lowered = line.lower()
        if lowered.startswith("title:"):
            title = line.split(":", 1)[1].strip() or title
            continue
        if lowered.startswith(("author:", "authors:", "written by:", "credit:")):
            author = line.split(":", 1)[1].strip() or author
            continue
        if lowered.startswith(("written by", "by ", "screenplay by", "story by")):
            candidate = re.sub(
                r"^(written by|screenplay by|story by|by)\s*", "", line, flags=re.IGNORECASE
            ).strip()
            if candidate and not author:
                author = candidate
            continue
        if any(lowered.startswith(k) for k in TITLE_BLOCK_KEYS):
            continue
        if title is None:
            # First substantive line of the block is the title.
            title = line

    return title, author


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
    cleaned = cleaned.strip().upper()
    # A cue typed with a trailing period ("DR. SCHLECHT.") or as a voice
    # ("CHEW'S VOICE") is the same person as the plain cue. Blade Runner alone
    # produced three SCHLECHTs and a CHEW'S VOICE beside CHEW, and each one
    # became a profile the model was asked to invent a face for.
    cleaned = re.sub(r"[.:,;]+$", "", cleaned).strip()
    cleaned = re.sub(r"['’]S\s+VOICE$", "", cleaned).strip()
    return cleaned


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
            # Relationship strength is derived from the script itself: how often the two
            # trade dialogue turns, and how many scenes they share.
            if interaction_turns >= 6:
                rel_type = "Principal Dialogue Counterpart"
            elif interaction_turns > 0:
                rel_type = "Key Dialogue Counterpart"
            else:
                rel_type = "Shared Scene Presence"
            dyn_desc = (
                f"Interacts in {len(shared_scenes)} scene(s) "
                f"with {interaction_turns} direct dialogue turn(s)."
            )

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


def extract_character_descriptors(
    scenes: List[ScreenplayScene],
    known_names: Set[str],
) -> Dict[str, Dict[str, str]]:
    """
    Mines action lines for how the screenplay introduces each character.

    Screenplays conventionally introduce a character in caps with an appositive
    description, e.g. "MAYA CHEN, 30s, sits hunched over a console." The cue is
    usually the first name only ("MAYA"), so a full name in the action line is
    matched back to the shorter cue.

    Returns {cue_name: {"full_name", "description", "age"}}.
    """
    found: Dict[str, Dict[str, str]] = {}

    for sc in scenes:
        for action in sc.action_blocks:
            for match in DESCRIPTOR_RE.finditer(action):
                raw_name = match.group(1).strip()
                description = match.group(2).strip().rstrip(",")
                if not raw_name or raw_name in NON_CHARACTER_TOKENS:
                    continue

                # Resolve "MAYA CHEN" in the action back to the "MAYA" cue.
                cue = None
                if raw_name in known_names:
                    cue = raw_name
                else:
                    for known in known_names:
                        if raw_name.startswith(known + " ") or known.startswith(raw_name + " "):
                            cue = known
                            break
                if cue is None or cue in found:
                    continue

                age_match = AGE_RE.search(description)
                found[cue] = {
                    "full_name": raw_name,
                    "description": description,
                    "age": age_match.group(1) if age_match else "",
                }

    return found


# Dialogue cues that hint at a character's disposition. Deliberately small and
# transparent: these are starting points for the user to edit, not a claim to
# have understood the character.
TRAIT_HINTS = (
    ("Commanding", ("must", "now", "order", "stand", "step", "move", "stop")),
    ("Inquisitive", ("who", "what", "why", "where", "how", "?")),
    ("Guarded", ("careful", "listen", "wait", "quiet", "don't")),
    ("Urgent", ("hurry", "quick", "run", "late", "!")),
)


def infer_personality_traits(name: str, scenes: List[ScreenplayScene]) -> List[str]:
    """
    Derives a small set of starting personality traits from the character's own
    dialogue. Returns an empty list when the script gives nothing to go on,
    rather than inventing the same three adjectives for everyone.
    """
    spoken = " ".join(
        d.line.lower()
        for sc in scenes
        for d in sc.dialogues
        if clean_character_name(d.character) == name
    )
    if not spoken.strip():
        return []

    traits = [trait for trait, hints in TRAIT_HINTS if any(h in spoken for h in hints)]
    return traits[:4]


def infer_character_gender(name: str, scenes: List[ScreenplayScene], description: str = "") -> str:
    """
    Infers gender characteristics from introduction descriptions or action line pronouns.
    Returns 'woman', 'man', 'non-binary', or '' if ambiguous.
    """
    desc_lower = description.lower()
    if any(w in desc_lower for w in ("woman", "female", "girl", "lady", "she", "her", "actress", "mother", "sister", "daughter")):
        return "woman"
    if any(w in desc_lower for w in ("man", "male", "guy", "boy", "gentleman", "he", "his", "him", "actor", "father", "brother", "son")):
        return "man"
    if any(w in desc_lower for w in ("non-binary", "androgynous", "gender-non-conforming")):
        return "non-binary"

    # Scan action lines in scenes where this character appears for pronouns
    she_count = 0
    he_count = 0
    they_count = 0
    name_upper = name.upper()

    for sc in scenes:
        if name in sc.characters:
            for action in sc.action_blocks:
                if name_upper in action.upper():
                    act_lower = action.lower()
                    she_count += len(re.findall(r"\b(she|her|hers)\b", act_lower))
                    he_count += len(re.findall(r"\b(he|him|his)\b", act_lower))
                    they_count += len(re.findall(r"\b(they|them|their)\b", act_lower))

    if she_count > he_count and she_count > they_count and she_count >= 1:
        return "woman"
    elif he_count > she_count and he_count > they_count and he_count >= 1:
        return "man"
    elif they_count > she_count and they_count > he_count and they_count >= 1:
        return "non-binary"
    return ""


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
            if not name or len(name) < 2 or is_transition_cue(name) or name in NON_CHARACTER_TOKENS:
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
                if word in NON_CHARACTER_TOKENS or is_transition_cue(word):
                    continue
                if word in char_stats:
                    char_stats[word]["scenes"].add(sc.scene_number)
                    if word not in sc.characters:
                        sc.characters.append(word)

    profiles: List[CharacterProfile] = []
    all_names = set(char_stats.keys())

    # Mine the action lines once for how the script describes each character.
    descriptors = extract_character_descriptors(scenes, all_names)

    # Sort characters by dialogue frequency
    sorted_chars = sorted(char_stats.values(), key=lambda c: c["dialogue_count"], reverse=True)

    for rank, c in enumerate(sorted_chars):
        name = c["name"]
        char_id = f"char_{name.lower().replace(' ', '_')}"
        scenes_list = sorted(list(c["scenes"]), key=lambda s: int(re.sub(r'\D', '', s) or '0'))

        # Extract relationships with other cast members
        relationships = extract_character_relationships(name, all_names, scenes)

        # Seed the profile from what the screenplay itself says about this
        # character, so each one starts visually distinct rather than every
        # character sharing one generic placeholder description.
        seed = descriptors.get(name, {})
        described_as = seed.get("description")
        age = seed.get("age")
        full_name = seed.get("full_name", name)
        gender = infer_character_gender(name, scenes, described_as or "")

        if rank == 0 and c["dialogue_count"] > 0:
            role_desc = "Lead"
        elif c["dialogue_count"] >= 3:
            role_desc = "Principal Cast"
        elif c["dialogue_count"] > 0:
            role_desc = "Supporting Character"
        else:
            role_desc = "Background / Non-Speaking"

        if described_as:
            actor_reference = f"{full_name.title()}, {described_as}"
        elif age:
            if gender:
                actor_reference = f"{full_name.title()}, {age} {gender}"
            else:
                actor_reference = f"{full_name.title()}, {age}"
        else:
            if gender:
                actor_reference = (
                    f"{full_name.title()} ({gender}) — appearance not described in the screenplay; "
                    f"set a reference to lock this character's look"
                )
            else:
                actor_reference = (
                    f"{full_name.title()} — appearance not described in the screenplay; "
                    f"set a reference to lock this character's look"
                )

        profile = CharacterProfile(
            id=char_id,
            name=name,
            role=role_desc,
            actor_reference=actor_reference,
            look_and_costume=(
                f"Wardrobe for {full_name.title()}, consistent across "
                f"{len(scenes_list)} scene(s); refine to lock continuity"
            ),
            facial_features=(
                f"{age}, distinguishing features to be defined" if age
                else "Distinguishing facial features to be defined"
            ),
            personality_traits=infer_personality_traits(name, scenes),
            relationships=relationships,
            dialogue_count=c["dialogue_count"],
            scenes_present=scenes_list,
            avatar_url=None,
        )
        profiles.append(profile)

    return profiles


def parse_fountain_screenplay(script_text: str, title: str = "Screenplay") -> Screenplay:
    """
    Parses Fountain, Markdown (.md), Plaintext (.txt), or standard screenplay text into structured scenes.
    """
    if not script_text or not script_text.strip():
        return Screenplay(title=title, scenes_count=0, characters_count=0, characters=[], scenes=[], raw_text=script_text)

    all_lines = script_text.strip().splitlines()
    parse_warnings: List[str] = []

    # Everything before the first scene heading is a title block, not content.
    # Parsing it as scene body is what previously turned a plain title line into
    # a speaking character with the author credit as its dialogue.
    first_heading_idx = next(
        (i for i, ln in enumerate(all_lines) if SCENE_REGEX.match(ln.strip())),
        None,
    )
    if first_heading_idx is None:
        # No headings at all: treat the leading paragraph as the title block so a
        # bare title line still does not get read as dialogue.
        split_at = next(
            (i for i, ln in enumerate(all_lines) if not ln.strip()),
            0,
        )
        title_block, lines = all_lines[:split_at], all_lines[split_at:]
        parse_warnings.append(
            "No INT./EXT. scene headings found; the whole file was treated as a single scene."
        )
    else:
        title_block = all_lines[:first_heading_idx]
        lines = all_lines[first_heading_idx:]

    detected_title, detected_author = parse_title_block(title_block)
    if not detected_title:
        # Fall back to the caller's title (usually the filename).
        detected_title = title
        if title_block:
            parse_warnings.append(
                "Could not identify a title in the text; used the file name instead."
            )

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

    for line in lines:
        stripped = line.strip()
        
        # Check for Scene Headings
        match = SCENE_REGEX.match(stripped)
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
            is_trans = is_transition_cue(stripped)
            is_char_cue = (
                not is_trans and
                clean_cue.isupper() and
                len(clean_cue) > 1 and
                len(clean_cue) < 35 and
                not clean_cue.endswith(":") and
                clean_cue not in NON_CHARACTER_TOKENS and
                not any(clean_cue.startswith(x) for x in ["INT.", "EXT.", "CUT TO", "FADE", "SCENE", "MATCH CUT", "SMASH CUT", "DISSOLVE"])
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
                if not is_trans:
                    current_actions.append(stripped)

    # Save final scene
    save_current_scene()

    # Extract & Profile all Characters and their relationships
    characters = extract_character_profiles(scenes, script_text)

    if not characters:
        parse_warnings.append(
            "No character cues were detected. Character names should sit on their own "
            "line in capitals, above their dialogue."
        )
    if not scenes:
        parse_warnings.append("No scenes could be extracted from this file.")

    return Screenplay(
        title=detected_title,
        script_id=compute_script_id(script_text),
        author=detected_author,
        scenes_count=len(scenes),
        characters_count=len(characters),
        characters=characters,
        scenes=scenes,
        raw_text=script_text,
        parse_warnings=parse_warnings,
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
    except Exception as exc:
        # First of three extraction strategies; the next is tried below.
        logger.debug("pdfplumber extraction failed: %s", exc)

    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            t = page.extract_text()
            if t:
                extracted_text.append(t)
        if extracted_text:
            return "\n\n".join(extracted_text)
    except Exception as exc:
        # Falls through to a raw decode, which always returns something.
        logger.debug("pypdf extraction failed: %s", exc)

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
