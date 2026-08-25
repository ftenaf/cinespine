"""
Screenplay & Fountain Parser Module for CineSpine.
Parses standard Screenplay formatting and Fountain syntax into structured scenes,
headings, action blocks, characters, and dialogues.
"""
import re
from typing import List, Optional
from pydantic import BaseModel, Field


class DialogueLine(BaseModel):
    character: str
    parenthetical: Optional[str] = None
    line: str


class ScreenplayScene(BaseModel):
    scene_number: str
    heading: str
    environment: str = "INT"  # INT, EXT, INT/EXT
    location: str
    time_of_day: str = "DAY"  # DAY, NIGHT, DUSK, DAWN, MAGIC_HOUR
    action_blocks: List[str] = Field(default_factory=list)
    dialogues: List[DialogueLine] = Field(default_factory=list)
    raw_content: str = ""


class Screenplay(BaseModel):
    title: str = "Untitled Screenplay"
    scenes_count: int = 0
    scenes: List[ScreenplayScene] = Field(default_factory=list)
    raw_text: str = ""


# Scene Heading Regex (Fountain standard and standard screenplay)
SCENE_HEADING_REGEX = re.compile(
    r"^(?:\.?\s*)?(INT\./EXT\.|INT/EXT\.|INT\.|EXT\.|I/E\.)\s+([^-]+)(?:-\s*([^\n\r]+))?",
    re.IGNORECASE | re.MULTILINE
)

# Numbered scene prefix e.g. "27 INT. GREAT HALL - DAY" or "SCENE 27 - INT. GREAT HALL"
NUMBERED_SCENE_REGEX = re.compile(
    r"^(?:SCENE\s+)?(\d+[A-Z]?)\.?\s+(INT\./EXT\.|INT/EXT\.|INT\.|EXT\.|I/E\.)\s+([^-]+)(?:-\s*([^\n\r]+))?",
    re.IGNORECASE | re.MULTILINE
)


def parse_fountain_screenplay(script_text: str, title: str = "Screenplay") -> Screenplay:
    """
    Parses Fountain format or standard screenplay text into structured scenes.
    """
    if not script_text or not script_text.strip():
        return Screenplay(title=title, scenes_count=0, scenes=[], raw_text=script_text)

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

    def flush_scene():
        nonlocal current_scene, current_actions, current_dialogues, current_raw_lines, scenes
        flush_dialogue()
        if current_scene:
            current_scene.action_blocks = [a for a in current_actions if a.strip()]
            current_scene.dialogues = current_dialogues
            current_scene.raw_content = "\n".join(current_raw_lines)
            scenes.append(current_scene)
            current_scene = None
            current_actions = []
            current_dialogues = []
            current_raw_lines = []

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        line_clean = line.strip()

        if not line_clean:
            flush_dialogue()
            if current_raw_lines:
                current_raw_lines.append("")
            idx += 1
            continue

        # Check for Scene Heading
        numbered_match = NUMBERED_SCENE_REGEX.match(line_clean)
        standard_match = SCENE_HEADING_REGEX.match(line_clean)

        if numbered_match or standard_match:
            flush_scene()
            if numbered_match:
                sc_num = numbered_match.group(1).strip()
                env = numbered_match.group(2).replace(".", "").strip().upper()
                rem = line_clean[numbered_match.end(2):].strip().lstrip(".- ")
            else:
                current_scene_num += 1
                sc_num = str(current_scene_num)
                env = standard_match.group(1).replace(".", "").strip().upper()
                rem = line_clean[standard_match.end(1):].strip().lstrip(".- ")

            # Split on last dash for time of day (e.g. "GREAT HALL - NAVE - DAY" -> loc="GREAT HALL - NAVE", tod="DAY")
            if " - " in rem:
                p_loc, p_tod = rem.rsplit(" - ", 1)
                loc = p_loc.strip()
                tod = p_tod.strip().upper()
            elif "-" in rem:
                p_loc, p_tod = rem.rsplit("-", 1)
                loc = p_loc.strip()
                tod = p_tod.strip().upper()
            else:
                loc = rem.strip()
                tod = "DAY"

            current_scene = ScreenplayScene(
                scene_number=sc_num,
                heading=line_clean,
                environment=env,
                location=loc,
                time_of_day=tod,
                action_blocks=[],
                dialogues=[],
                raw_content=""
            )
            current_raw_lines.append(line)
            idx += 1
            continue

        # Check for Fountain Top Title Page Metadata
        if not current_scene and ":" in line_clean and any(line_clean.lower().startswith(k) for k in ["title:", "author:", "authors:", "credit:", "source:", "draft:", "date:", "contact:", "copyright:"]):
            k, v = line_clean.split(":", 1)
            if k.lower().strip() == "title" and v.strip():
                title = v.strip()
            idx += 1
            continue

        # If no scene header encountered yet, create a default Scene 1
        if not current_scene:
            current_scene_num += 1
            current_scene = ScreenplayScene(
                scene_number=str(current_scene_num),
                heading=f"INT. LOCATION - DAY",
                environment="INT",
                location="LOCATION",
                time_of_day="DAY"
            )

        current_raw_lines.append(line)

        # Check for Character Name (All Uppercase, centered or without lowercase letters, not ending in punctuation)
        is_all_caps = line_clean.isupper() and len(line_clean) < 35 and not line_clean.endswith((".", ":", ";"))
        is_character = (
            is_all_caps
            and not standard_match
            and not any(line_clean.startswith(pfx) for pfx in ["INT.", "EXT.", "CUT TO:", "FADE IN:", "FADE OUT:"])
        )

        if is_character:
            flush_dialogue()
            # Clean character name from Fountain indicators e.g. "LEAD (V.O.)" -> "LEAD"
            char_name = re.sub(r"\(.*?\)", "", line_clean).strip()
            parenthetical_inline = None
            if "(" in line_clean:
                p_match = re.search(r"\((.*?)\)", line_clean)
                if p_match:
                    parenthetical_inline = p_match.group(1)

            pending_character = char_name or line_clean
            pending_parenthetical = parenthetical_inline
            idx += 1
            continue

        # Check for Parenthetical e.g. "(whispering)"
        if pending_character and line_clean.startswith("(") and line_clean.endswith(")"):
            pending_parenthetical = line_clean.strip("()")
            idx += 1
            continue

        # Check for Dialogue line
        if pending_character:
            pending_dialogue_lines.append(line_clean)
            idx += 1
            continue

        # Otherwise it is an Action Block
        current_actions.append(line_clean)
        idx += 1

    flush_scene()

    return Screenplay(
        title=title,
        scenes_count=len(scenes),
        scenes=scenes,
        raw_text=script_text
    )
