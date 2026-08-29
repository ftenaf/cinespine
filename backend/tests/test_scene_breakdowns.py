"""
A scene's shot breakdown, kept.

The coverage is generated once and then worked on -- a focal length nudged, a
camera added, a prompt rewritten and re-rendered -- and all of it lived in the
Script Studio tab's memory, so a reload threw away the work and the generations
it cost. Same complaint as the character portraits, one level up.

Stored whole, one row per scene. The tab holds it as "the shots for this scene"
and edits it as that; splitting it into a table of shots and a table of cameras
would buy a query nobody asks and cost a transaction on every slider drag.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.spine import breakdown_store
from backend.app.spine.breakdown_store import UnknownBreakdownValue

client = TestClient(app)

SCRIPT = "script-breakdown-01"


def shot(**over):
    return {
        "id": "SHOT-A1",
        "scene_number": "27",
        "shot_number": "1",
        "shot_name": "LEAD at the organ",
        "shot_size": "WS",
        "active_camera": "A",
        "cameras": [
            {
                "camera_letter": "A",
                "shot_size": "WS",
                "focal_length": 35,
                "aperture": "T2.8",
                "prompt": "wide of the nave",
                "image_url": "data:image/jpeg;base64,AAAA",
                "status": "generated",
            },
        ],
        "storyboard": {"image_url": "data:image/jpeg;base64,AAAA", "status": "generated"},
        **over,
    }


def save(scene_number="27", shots=None, script_id=SCRIPT):
    res = client.put(
        f"/api/script/{script_id}/breakdowns/{scene_number}",
        json={"shots": shots if shots is not None else [shot()]},
    )
    assert res.status_code == 200, res.text
    return res.json()


def restored(script_id=SCRIPT):
    res = client.get(f"/api/script/{script_id}/breakdowns")
    assert res.status_code == 200, res.text
    return res.json()["breakdowns"]


# --------------------------------------------------------------------------- #
# It survives
# --------------------------------------------------------------------------- #

def test_a_breakdown_outlives_the_process_that_made_it():
    save()
    assert breakdown_store.get(SCRIPT, "27")["shots"][0]["shot_name"] == "LEAD at the organ"


def test_a_breakdown_comes_back_in_the_shape_the_studio_holds_it_in():
    """Restoring should be an assignment, not a reduction."""
    save(scene_number="27")
    save(scene_number="49", shots=[shot(id="SHOT-B1", scene_number="49")])
    assert sorted(restored().keys()) == ["27", "49"]
    assert restored()["49"][0]["id"] == "SHOT-B1"


def test_the_frames_are_kept_rather_than_dropped_to_save_room():
    """
    Those are images a generation paid for. Storing the coverage without them
    would lose exactly what a reload used to lose.
    """
    save()
    camera = breakdown_store.get(SCRIPT, "27")["shots"][0]["cameras"][0]
    assert camera["image_url"].startswith("data:image/jpeg;base64,")


def test_a_scene_number_is_read_the_same_way_however_it_was_written():
    save(scene_number="27a")
    assert breakdown_store.get(SCRIPT, "27A") is not None


def test_another_screenplay_s_breakdowns_are_not_mixed_in():
    save(script_id=SCRIPT)
    save(script_id="some-other-script")
    assert list(restored(SCRIPT).keys()) == ["27"]


def test_a_screenplay_with_no_breakdowns_yet_reads_as_empty_not_as_an_error():
    assert restored("never-broken-down") == {}


# --------------------------------------------------------------------------- #
# Editing it
# --------------------------------------------------------------------------- #

def test_saving_again_replaces_the_scene_s_shots():
    """
    The caller holds the whole list, so anything missing from what it sends is
    something it removed.
    """
    save(shots=[shot(id="SHOT-A1"), shot(id="SHOT-A2")])
    save(shots=[shot(id="SHOT-A2")])
    kept = breakdown_store.get(SCRIPT, "27")["shots"]
    assert [s["id"] for s in kept] == ["SHOT-A2"]


def test_an_edited_camera_is_what_comes_back():
    save()
    edited = shot()
    edited["cameras"][0]["focal_length"] = 85
    save(shots=[edited])
    assert breakdown_store.get(SCRIPT, "27")["shots"][0]["cameras"][0]["focal_length"] == 85


def test_a_scene_s_breakdown_can_be_thrown_away():
    save()
    assert client.delete(f"/api/script/{SCRIPT}/breakdowns/27").json()["deleted"] is True
    assert breakdown_store.get(SCRIPT, "27") is None


def test_deleting_a_breakdown_that_is_not_there_is_not_a_deletion():
    assert client.delete(f"/api/script/{SCRIPT}/breakdowns/999").json()["deleted"] is False


def test_saving_an_empty_list_is_a_scene_with_no_coverage_not_a_failure():
    save(shots=[])
    assert breakdown_store.get(SCRIPT, "27")["shots"] == []


@pytest.mark.parametrize("script_id,scene", [("", "27"), (SCRIPT, "   ")])
def test_a_breakdown_that_names_no_scene_is_refused(script_id, scene):
    with pytest.raises(UnknownBreakdownValue):
        breakdown_store.save(script_id, scene, [])


# --------------------------------------------------------------------------- #
# Generating one
# --------------------------------------------------------------------------- #

SCENE = {
    "scene_number": "27",
    "heading": "INT. GREAT HALL - NAVE - DAY",
    "environment": "INT",
    "location": "GREAT HALL - NAVE",
    "time_of_day": "DAY",
    "action_blocks": ["LEAD sits at the pipe organ console."],
    "dialogues": [],
    "characters": ["LEAD"],
    "raw_content": "27 INT. GREAT HALL - NAVE - DAY\n\nLEAD sits at the pipe organ console.\n",
}


def test_generating_a_breakdown_keeps_it_against_the_scene():
    res = client.post("/api/script/breakdown", json={"scene": SCENE, "script_id": SCRIPT})
    assert res.status_code == 200, res.text
    assert res.json()["saved"] is True
    assert breakdown_store.get(SCRIPT, "27")["shots"], "nothing was stored"


def test_generating_against_no_screenplay_still_returns_the_shots():
    """
    There is nothing to file it under, so it is not saved -- but the work was
    done and the caller gets it.
    """
    res = client.post("/api/script/breakdown", json={"scene": SCENE})
    body = res.json()
    assert body["saved"] is False
    assert body["shots_count"] >= 1


def test_the_stored_breakdown_matches_what_was_handed_back():
    res = client.post("/api/script/breakdown", json={"scene": SCENE, "script_id": SCRIPT})
    returned = res.json()["shots"]
    assert breakdown_store.get(SCRIPT, "27")["shots"] == returned
