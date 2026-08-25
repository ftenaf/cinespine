"""
Automated Test Suite for Script Breakdown, DoP Cinematography & Previz Storyboard Studio.
"""
import pytest
from starlette.testclient import TestClient
from backend.app.main import app
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
    assert svg_data_cam_a.startswith("data:image/svg+xml;base64,")

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
    assert svg_data_cam_b.startswith("data:image/svg+xml;base64,")


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
        "prompt": "Test cinematic frame",
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
    assert data["image_url"].startswith("data:image/svg+xml;base64,")


def test_api_script_upload_endpoint(client):
    # Upload Fountain script file
    files = {"file": ("DemoProduction_Draft1.fountain", SAMPLE_FOUNTAIN_SCRIPT.encode("utf-8"), "text/plain")}
    res = client.post("/api/script/upload", files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "La DemoProduction"
    assert data["scenes_count"] == 2
    assert len(data["scenes"]) == 2

