"""
Automated Test Suite for Script Breakdown, DoP Cinematography & Previz Storyboard Studio.
"""
import pathlib

import pytest
from starlette.testclient import TestClient
from backend.app.main import app

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
from backend.app.script.parser import parse_fountain_screenplay, ScreenplayScene
from backend.app.script.dop_presets import DOP_MASTER_PRESETS, resolve_dop_specification
from backend.app.script.breakdown_engine import breakdown_scene_to_shots, synthesize_cinematic_prompt
from backend.app.script.storyboard_generator import render_cinematic_storyboard_svg


SAMPLE_FOUNTAIN_SCRIPT = """Title: La DemoProduction
Author: Francisco

INT. GREAT HALL - NAVE - DAY

Sunlight slices through stained glass. LEAD (30s) sits at the colossal organ, trembling.

LEAD
(whispering)
The music cannot wait any longer.

SUPPORT enters from the shadows of the narthex.

SUPPORT
LEAD, they are already at the gates.

EXT. PLAZA - NIGHT

Rain pours over cobblestones. POLICE VEHICLES flash blue sirens in the darkness.
"""


@pytest.fixture
def client():
    return TestClient(app)


def test_fountain_parser_multi_scene():
    screenplay = parse_fountain_screenplay(SAMPLE_FOUNTAIN_SCRIPT, title="La DemoProduction")
    assert screenplay.title == "La DemoProduction"
    assert screenplay.scenes_count == 2
    
    # Scene 1 Assertions
    sc1 = screenplay.scenes[0]
    assert sc1.scene_number == "1"
    assert "GREAT HALL - NAVE" in sc1.heading
    assert sc1.environment == "INT"
    assert sc1.time_of_day == "DAY"
    assert len(sc1.action_blocks) >= 2
    assert len(sc1.dialogues) == 2
    assert sc1.dialogues[0].character == "LEAD"
    assert sc1.dialogues[0].parenthetical == "whispering"
    assert sc1.dialogues[0].line == "The music cannot wait any longer."
    assert sc1.dialogues[1].character == "SUPPORT"

    # Scene 2 Assertions
    sc2 = screenplay.scenes[1]
    assert sc2.scene_number == "2"
    assert sc2.environment == "EXT"
    assert sc2.time_of_day == "NIGHT"
    assert "PLAZA" in sc2.location


def test_dop_presets_and_overrides():
    # Test Deakins Default
    deakins_spec = resolve_dop_specification("Roger Deakins")
    assert deakins_spec.dop_preset == "Roger Deakins"
    assert deakins_spec.focal_length == 35
    assert deakins_spec.color_temperature_k == 5600

    # Test Fincher Override
    fincher_spec = resolve_dop_specification("David Fincher", overrides={"focal_length": 21, "aperture": "T1.4"})
    assert fincher_spec.dop_preset == "David Fincher"
    assert fincher_spec.focal_length == 21
    assert fincher_spec.aperture == "T1.4"
    assert "Neo-Noir" in fincher_spec.lighting_style or "Low-Key" in fincher_spec.lighting_style


def test_scene_to_shots_breakdown():
    sc = ScreenplayScene(
        scene_number="27",
        heading="INT. GREAT HALL - NAVE - DAY",
        environment="INT",
        location="GREAT HALL - NAVE",
        time_of_day="DAY",
        action_blocks=["LEAD plays the organ passionately."],
        dialogues=[]
    )

    shots = breakdown_scene_to_shots(sc, dop_style_name="Roger Deakins", aspect_ratio="2.39:1")
    assert len(shots) >= 2
    
    # Master setup with 3 simultaneous cameras (A, B, C)
    shot1 = shots[0]
    assert shot1.shot_size == "WS"
    assert shot1.scene_number == "27"
    assert "Deakins" in shot1.dop_spec.dop_preset
    assert len(shot1.cameras) == 3
    assert shot1.cameras[0].camera_letter == "A"
    assert shot1.cameras[1].camera_letter == "B"
    assert shot1.cameras[2].camera_letter == "C"
    assert "Camera A" in shot1.cameras[0].prompt
    assert "Camera B" in shot1.cameras[1].prompt
    assert "Camera C" in shot1.cameras[2].prompt


def test_storyboard_svg_renderer():
    svg_data_cam_a = render_cinematic_storyboard_svg(
        prompt="Dramatic organist playing in gothic great_hall nave",
        scene_number="27",
        shot_number="1",
        shot_size="WS",
        focal_length=35,
        aperture="T2.8",
        dop_preset="Roger Deakins",
        camera_letter="A",
        aspect_ratio="2.39:1"
    )
    assert svg_data_cam_a.startswith("/previz/") or svg_data_cam_a.startswith("data:image/")

    svg_data_cam_b = render_cinematic_storyboard_svg(
        prompt="Over-the-shoulder organist playing in gothic great_hall",
        scene_number="27",
        shot_number="1",
        shot_size="OTS",
        focal_length=50,
        aperture="T2.0",
        dop_preset="Roger Deakins",
        camera_letter="B",
        aspect_ratio="2.39:1"
    )
    assert svg_data_cam_b.startswith("/previz/") or svg_data_cam_b.startswith("data:image/")


def test_api_script_parse_endpoint(client):
    res = client.post("/api/script/parse", json={"script_text": SAMPLE_FOUNTAIN_SCRIPT, "title": "La DemoProduction"})
    assert res.status_code == 200
    data = res.json()
    assert data["scenes_count"] == 2
    assert len(data["scenes"]) == 2
    assert data["scenes"][0]["environment"] == "INT"


def test_api_script_presets_endpoint(client):
    res = client.get("/api/script/presets")
    assert res.status_code == 200
    data = res.json()
    assert "Roger Deakins" in data["presets"]
    assert "David Fincher" in data["presets"]
    assert "2.39:1" in data["aspect_ratios"]


def test_api_script_preset_suggest_endpoint(client):
    res = client.post("/api/script/presets/suggest", json={
        "focal_length": 24,
        "aperture": "T1.4",
        "color_temperature_k": 3200,
        "white_balance_k": 5600,
        "lighting_ratio": "8:1",
        "sensor_format": "Large Format 35mm",
        "lut_emulation": "Kodak 5219 Vision3 500T",
        "custom_prompt": "Neon alley rain reflexions",
        "aspect_ratio": "2.39:1"
    })
    assert res.status_code == 200
    data = res.json()
    assert "name" in data and len(data["name"]) > 0
    assert "tagline" in data and len(data["tagline"]) > 0
    assert "description" in data and len(data["description"]) > 0
    assert "prompt_style_tag" in data and len(data["prompt_style_tag"]) > 0


def test_api_script_breakdown_endpoint(client):
    sc_payload = {
        "scene_number": "27",
        "heading": "INT. GREAT HALL - NAVE - DAY",
        "environment": "INT",
        "location": "GREAT HALL - NAVE",
        "time_of_day": "DAY",
        "action_blocks": ["Sunlight hits the organ."],
        "dialogues": [{"character": "LEAD", "parenthetical": None, "line": "Listen to the harmony."}],
        "raw_content": ""
    }
    req = {
        "scene": sc_payload,
        "dop_preset": "David Fincher",
        "aspect_ratio": "2.39:1"
    }
    res = client.post("/api/script/breakdown", json=req)
    assert res.status_code == 200
    data = res.json()
    assert data["scene_number"] == "27"
    assert data["shots_count"] >= 2
    assert len(data["shots"]) >= 2
    assert data["shots"][0]["storyboard"]["image_url"] is not None


def test_api_generate_storyboard_endpoint(client):
    req = {
        "shot_id": "SHOT-27-01",
        "prompt": "Test cinematic great_hall organ frame",
        "scene_number": "27",
        "shot_number": "1",
        "shot_size": "CU",
        "focal_length": 85,
        "aperture": "T1.4",
        "dop_preset": "Greig Fraser",
        "camera_letter": "A",
        "aspect_ratio": "2.39:1"
    }
    res = client.post("/api/script/generate-storyboard", json=req)
    assert res.status_code == 200
    data = res.json()
    assert data["shot_id"] == "SHOT-27-01"
    assert data["image_url"].startswith("/previz/") or data["image_url"].startswith("data:image/")


def test_api_script_upload_endpoint(client):
    # Upload Fountain script file
    files = {"file": ("DemoProduction_Draft1.fountain", SAMPLE_FOUNTAIN_SCRIPT.encode("utf-8"), "text/plain")}
    res = client.post("/api/script/upload", files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "La DemoProduction"
    assert data["scenes_count"] == 2
    assert len(data["scenes"]) == 2
    assert len(data["characters"]) >= 2
    assert data["characters"][0]["name"] in ["LEAD", "SUPPORT"]


PLAINTEXT_SCRIPT = """THE LAST SIGNAL
Written by A. Writer

INT. RADIO STATION - NIGHT

Rain streaks the windows. MAYA CHEN, 30s, sits hunched over a console.

MAYA
Anyone out there?

DANIEL
Maya? Is that you?
"""


def test_markdown_and_txt_script_parsing():
    md_script = """# Title: Night Frequency

### Scene 1: INT. CONTROL ROOM - NIGHT

Banks of dead monitors line the wall.

OPERATOR
Tell me about the signal.

ANALYST
It repeats every twelve minutes.
"""
    screenplay = parse_fountain_screenplay(md_script, title="Fallback Title")
    assert screenplay.title == "Night Frequency"
    assert screenplay.scenes_count == 1
    assert screenplay.scenes[0].environment == "INT"
    assert "CONTROL ROOM" in screenplay.scenes[0].location
    assert screenplay.scenes[0].time_of_day == "NIGHT"

    char_names = [c.name for c in screenplay.characters]
    assert "OPERATOR" in char_names
    assert "ANALYST" in char_names


def test_plaintext_title_block_is_not_parsed_as_a_character():
    """
    A plain script's title and author credit sit above the first scene heading.
    They are metadata, not a speaking character, and must not create a phantom
    scene either.
    """
    screenplay = parse_fountain_screenplay(PLAINTEXT_SCRIPT, title="plain")

    assert screenplay.title == "THE LAST SIGNAL"
    assert screenplay.author == "A. Writer"

    char_names = [c.name for c in screenplay.characters]
    assert "THE LAST SIGNAL" not in char_names
    assert sorted(char_names) == ["DANIEL", "MAYA"]

    # Only the one real scene heading, no synthetic pre-heading scene.
    assert screenplay.scenes_count == 1
    assert "RADIO STATION" in screenplay.scenes[0].location


def test_character_profile_is_seeded_from_the_screenplay():
    """Descriptions come from the script's own action lines, not a fixed default."""
    screenplay = parse_fountain_screenplay(PLAINTEXT_SCRIPT, title="plain")
    maya = next(c for c in screenplay.characters if c.name == "MAYA")
    daniel = next(c for c in screenplay.characters if c.name == "DANIEL")

    assert "Maya Chen" in maya.actor_reference
    assert "30s" in maya.actor_reference
    # A character the script never describes must not borrow someone else's look.
    assert maya.actor_reference != daniel.actor_reference


def test_api_character_update_persists_and_survives_reparse(client):
    """Edits must be stored against the script and survive re-uploading it."""
    files = {"file": ("plain.txt", PLAINTEXT_SCRIPT.encode("utf-8"), "text/plain")}
    first = client.post("/api/script/upload", files=files).json()
    script_id = first["script_id"]
    maya = next(c for c in first["characters"] if c["name"] == "MAYA")

    res = client.post("/api/script/characters/update", json={
        "id": maya["id"],
        "name": "MAYA",
        "script_id": script_id,
        "role": "Lead",
        "look_and_costume": "Red raincoat, silver locket, soaked boots",
    })
    assert res.status_code == 200
    assert res.json()["character"]["look_and_costume"] == "Red raincoat, silver locket, soaked boots"

    # Readable back through the dedicated endpoint.
    listed = client.get(f"/api/script/{script_id}/characters").json()
    stored = next(c for c in listed["characters"] if c["name"] == "MAYA")
    assert stored["look_and_costume"] == "Red raincoat, silver locket, soaked boots"

    # And preserved when the same screenplay is uploaded again.
    again = client.post("/api/script/upload", files=files).json()
    maya_again = next(c for c in again["characters"] if c["name"] == "MAYA")
    assert maya_again["look_and_costume"] == "Red raincoat, silver locket, soaked boots"
    # Structural data is still refreshed from the new parse.
    assert maya_again["dialogue_count"] == maya["dialogue_count"]


def test_character_profiles_survive_a_backend_restart(client, tmp_path, monkeypatch):
    """
    Character edits are authored by hand and drive image consistency, so they
    must outlive the process. Simulates a restart by discarding every in-memory
    object and rebuilding the app against the same database file.
    """
    files = {"file": ("plain.txt", PLAINTEXT_SCRIPT.encode("utf-8"), "text/plain")}
    uploaded = client.post("/api/script/upload", files=files).json()
    script_id = uploaded["script_id"]
    maya = next(c for c in uploaded["characters"] if c["name"] == "MAYA")

    client.post("/api/script/characters/update", json={
        "id": maya["id"],
        "name": "MAYA",
        "script_id": script_id,
        "look_and_costume": "Red raincoat, silver locket, soaked boots",
    })

    # A real restart means a real new process: boot the app in a fresh
    # interpreter that shares nothing but the database file on disk.
    import json
    import os
    import subprocess
    import sys

    probe = (
        "import json;"
        "from starlette.testclient import TestClient;"
        "from backend.app.main import app;"
        "c=TestClient(app);"
        f"r=c.get('/api/script/{script_id}/characters');"
        "print('RESULT:' + json.dumps({'status': r.status_code, 'body': r.json()}))"
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO_ROOT),
        "CINESPINE_DB_PATH": os.environ["CINESPINE_DB_PATH"],
    }
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]

    payload = next(
        json.loads(line[len("RESULT:"):])
        for line in completed.stdout.splitlines()
        if line.startswith("RESULT:")
    )
    assert payload["status"] == 200, "screenplay should still be known after restart"
    revived = next(c for c in payload["body"]["characters"] if c["name"] == "MAYA")
    assert revived["look_and_costume"] == "Red raincoat, silver locket, soaked boots"
    assert revived["_edited"] is True


def test_api_character_update_rejects_unknown_character(client):
    """A save that cannot be stored must report failure, not a false success."""
    files = {"file": ("plain.txt", PLAINTEXT_SCRIPT.encode("utf-8"), "text/plain")}
    script_id = client.post("/api/script/upload", files=files).json()["script_id"]

    res = client.post("/api/script/characters/update", json={
        "id": "char_does_not_exist",
        "name": "NOBODY",
        "script_id": script_id,
        "role": "Ghost",
    })
    assert res.status_code == 404


def test_character_relationships_detection():
    screenplay = parse_fountain_screenplay(SAMPLE_FOUNTAIN_SCRIPT, title="La DemoProduction")
    assert len(screenplay.characters) >= 2
    
    lead = next(c for c in screenplay.characters if c.name == "LEAD")
    support = next(c for c in screenplay.characters if c.name == "SUPPORT")
    
    # Verify relationships are extracted
    assert len(lead.relationships) >= 1
    rel_to_support = next(r for r in lead.relationships if r.target_character == "SUPPORT")
    assert "Ally" in rel_to_support.relationship_type or "Key" in rel_to_support.relationship_type
    assert "1" in rel_to_support.shared_scenes
    assert rel_to_support.interaction_count >= 1

    # Check SUPPORT's inverse relationship to LEAD
    rel_to_lead = next(r for r in support.relationships if r.target_character == "LEAD")
    assert rel_to_lead.target_character == "LEAD"
    assert "1" in rel_to_lead.shared_scenes


def test_api_generate_character_portrait_endpoint(client):
    req = {
        "character_id": "char_lead",
        "character_name": "LEAD",
        "actor_reference": "Late 30s man, intense sunken eyes, dark wavy hair, weathered features",
        "look_and_costume": "Drenched dark linen shirt with rolled-up sleeves, charcoal wool vest",
        "facial_features": "Sharp cheekbones, subtle 5 o'clock shadow, piercing hazel eyes",
        "role": "Haunted Great Hall Organist",
        "dop_preset": "Roger Deakins"
    }
    res = client.post("/api/script/characters/generate-portrait", json=req)
    assert res.status_code == 200
    data = res.json()
    assert data["character_id"] == "char_lead"
    assert data["character_name"] == "LEAD"
    assert data["image_url"].startswith("data:image/") or data["image_url"].startswith("/previz/")
    assert "LEAD" in data["compiled_prompt"]
    assert "85mm" in data["compiled_prompt"] or "portrait" in data["compiled_prompt"].lower()


CUT_TO_SCRIPT_SAMPLE = """Title: The Heist Setup
Author: CineSpine

INT. VAULT ROOM - NIGHT

MARCUS (40s) crouches before the titanium safe, adjusting his optical stethoscope.

MARCUS
(whispering)
Three clicks left. Hold the frequency.

CUT TO:

Extreme close-up on the safe's dial tumblers shifting in slow motion.

CUT TO:

HELENA (30s) watches the security monitors in the surveillance van outside.

HELENA
Patrol team is turning the corner. You have forty seconds.

SMASH CUT TO:

Marcus yanks the heavy vault lever downward with a resounding metallic clang.
"""


def test_fountain_parser_with_cut_to_transitions():
    screenplay = parse_fountain_screenplay(CUT_TO_SCRIPT_SAMPLE, title="The Heist Setup")
    assert screenplay.scenes_count == 1
    sc = screenplay.scenes[0]
    
    # Verify CUT TO transitions do not become characters
    char_names = [c.name for c in screenplay.characters]
    assert "MARCUS" in char_names
    assert "HELENA" in char_names
    assert "CUT TO" not in char_names
    assert "CUT TO:" not in char_names
    assert "SMASH CUT TO" not in char_names
    assert "SMASH CUT TO:" not in char_names
    
    # Dialogues should be preserved cleanly
    assert len(sc.dialogues) == 2
    assert sc.dialogues[0].character == "MARCUS"
    assert sc.dialogues[1].character == "HELENA"


def test_ai_cam_breakdown_with_cut_to_transitions():
    screenplay = parse_fountain_screenplay(CUT_TO_SCRIPT_SAMPLE, title="The Heist Setup")
    sc = screenplay.scenes[0]
    
    shots = breakdown_scene_to_shots(
        scene=sc,
        dop_style_name="David Fincher",
        aspect_ratio="2.39:1",
        character_profiles=screenplay.characters
    )
    
    # The scene has 4 distinct cut segments:
    # 1. Master/Opening with Marcus at the safe
    # 2. CUT TO: Close-up on tumblers
    # 3. CUT TO: Helena at the monitors
    # 4. SMASH CUT TO: Marcus yanking vault lever
    assert len(shots) == 4
    
    # Shot 1: Opening
    assert shots[0].shot_number == "1"
    assert "MARCUS" in shots[0].characters
    
    # Shot 2: CUT TO dial tumblers (should infer ECU / CU / INSERT)
    assert shots[1].shot_number == "2"
    assert shots[1].shot_size in ["ECU", "CU", "INSERT"]
    assert "CUT TO" in shots[1].shot_name or "Cut" in shots[1].dramatic_beat
    
    # Shot 3: CUT TO Helena
    assert shots[2].shot_number == "3"
    assert "HELENA" in shots[2].characters
    assert shots[2].shot_size in ["MS", "MCU"]
    
    # Shot 4: SMASH CUT TO Marcus yanking lever
    assert shots[3].shot_number == "4"
    assert "SMASH CUT" in shots[3].shot_name or "SMASH CUT" in shots[3].dramatic_beat
    
    # Each shot must contain full multi-camera proposals (A, B, C)
    for shot in shots:
        assert len(shot.cameras) == 3
        assert shot.cameras[0].camera_letter == "A"
        assert shot.cameras[1].camera_letter == "B"
        assert shot.cameras[2].camera_letter == "C"
        assert shot.cameras[0].prompt != ""




