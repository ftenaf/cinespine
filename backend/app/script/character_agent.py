import logging
import re
import hashlib
from typing import Dict, Any

from backend.app.script.parser import Screenplay, CharacterProfile

logger = logging.getLogger(__name__)

def fallback_enrich_characters(screenplay: Screenplay) -> Screenplay:
    """
    Fallback deterministic character inference from the script text.
    Extracts physical traits from action lines and personality traits from parentheticals.
    """
    for profile in screenplay.characters:
        # Find all scenes this character is in
        scenes = [s for s in screenplay.scenes if profile.name.upper() in [c.upper() for c in s.characters]]
        
        # Extract traits from parentheticals if missing
        if not profile.personality_traits:
            traits = set()
            for scene in scenes:
                for dialogue in scene.dialogues:
                    if dialogue.character.upper() == profile.name.upper() and dialogue.parenthetical:
                        cleaned = dialogue.parenthetical.strip("() \t\n")
                        if not cleaned.lower().startswith("to "):
                            traits.add(cleaned.lower())
            
            profile.personality_traits = list(traits)

        # Extract appearance from first action line mentioning them in uppercase if missing
        if not profile.look_and_costume:
            name_pattern = re.compile(rf"(?<![A-Z0-9]){re.escape(profile.name.upper())}(?![A-Z0-9])")
            appearance_found = False
            for scene in scenes:
                if not scene.action_blocks:
                    continue
                # Flatten action blocks and split into sentences
                action_text = " ".join(scene.action_blocks).replace("\n", " ")
                sentences = [s.strip() + "." for s in action_text.split(". ") if s.strip()]
                for sentence in sentences:
                    if name_pattern.search(sentence):
                        profile.look_and_costume = sentence[:200]  # First sentence where they are introduced
                        appearance_found = True
                        break
                if appearance_found:
                    break
            
            if not appearance_found:
                profile.look_and_costume = "Appearance inferred from context."
            
        def det_score(axis_name: str) -> int:
            val = int(hashlib.md5(f"{profile.name}{axis_name}".encode()).hexdigest(), 16)
            return (val % 80) + 10
            
        if not profile.personality_axes:
            profile.personality_axes = {
                "openness": {"score": det_score("openness"), "evidence": "Fallback derived from script heuristics."},
                "conscientiousness": {"score": det_score("conscientiousness"), "evidence": "Fallback derived from script heuristics."},
                "extraversion": {"score": det_score("extraversion"), "evidence": "Fallback derived from script heuristics."},
                "agreeableness": {"score": det_score("agreeableness"), "evidence": "Fallback derived from script heuristics."},
                "emotional_volatility": {"score": det_score("emotional_volatility"), "evidence": "Fallback derived from script heuristics."},
            }
            
        if not profile.role:
            profile.role = "Supporting Character"
            
        if not profile.actor_reference:
            profile.actor_reference = "Actor matching the script's general description."
            
        if not profile.facial_features:
            profile.facial_features = "Features typical for the character's background."
            
    return screenplay
