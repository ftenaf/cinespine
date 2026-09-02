import pytest
from backend.app.script.parser import parse_fountain_screenplay
from backend.app.script.character_agent import fallback_enrich_characters

SCRIPT = """THE LAST SIGNAL
Written by A. Writer

INT. RADIO STATION - NIGHT

Rain streaks the windows. MAYA CHEN, 30s, sits hunched over a console.

MAYA
(urgent)
Anyone out there? This is Kestrel Base.

DANIEL
(whispering to Maya)
They're jamming the north tower.
"""

def test_fallback_enrich_characters():
    screenplay = parse_fountain_screenplay(SCRIPT, title="fallback")
    
    # Assert defaults before fallback
    maya = next(c for c in screenplay.characters if c.name == "MAYA")
    daniel = next(c for c in screenplay.characters if c.name == "DANIEL")
    
    # Run fallback
    screenplay = fallback_enrich_characters(screenplay)
    
    # Check if traits were extracted from parentheticals
    assert "urgent" in maya.personality_traits
    assert "whispering to maya" in daniel.personality_traits
    
    # Check if appearance was extracted from action line
    assert "MAYA CHEN, 30s, sits hunched over a console." in maya.look_and_costume
    assert "Appearance inferred from context." in daniel.look_and_costume
