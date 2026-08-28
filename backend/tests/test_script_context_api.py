"""
Opening the script from a slate.

The endpoint's job is to answer "what is this scene about" for someone holding
a shot number, and to be honest when it cannot: an unattached script, a scene
the draft does not contain, and a shot that cannot be placed inside its scene
are three different answers, and each has to say which one it is.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.spine import character_store

client = TestClient(app)

PROD = "SCRIPTCTX"
SCRIPT = "script-ctx-0001"

SCENE_119 = """119 INT. GREAT HALL - NAVE - DAY

LEAD sits at the pipe organ console, hands hovering over the stops.

He strikes a heavy C-minor chord that reverberates through the columns.

From the narthex, SUPPORT emerges clutching a leather dossier.
"""

SCENE_41 = """41 EXT. PLAZA - NIGHT

Rain lashes the cobblestones. Sedans halt around the bronze doors.
"""


@pytest.fixture(autouse=True)
def _stored_script():
    """conftest already points CINESPINE_DB_PATH at a temporary file."""
    character_store.store_screenplay(
        script_id=SCRIPT, title="LA CATHEDRALE", filename="lac.fountain", profiles=[]
    )
    character_store.store_screenplay_scenes(
        SCRIPT,
        [
            {"scene_number": "41", "heading": "EXT. PLAZA - NIGHT", "raw_content": SCENE_41},
            {"scene_number": "119", "heading": "INT. GREAT HALL - NAVE - DAY", "raw_content": SCENE_119},
        ],
    )
    yield
    character_store.unlink_production_script(PROD)


def context(target_type: str, target_id: str, production_id: str = PROD):
    res = client.get(
        "/api/script/context",
        params={"production_id": production_id, "target_type": target_type, "target_id": target_id},
    )
    assert res.status_code == 200, res.text
    return res.json()


def link():
    res = client.post("/api/script/link", json={"production_id": PROD, "script_id": SCRIPT})
    assert res.status_code == 200, res.text
    return res.json()


# --------------------------------------------------------------------------- #
# Attaching a script to a production
# --------------------------------------------------------------------------- #

def test_a_production_starts_with_no_script_attached():
    assert client.get("/api/script/link", params={"production_id": PROD}).json() is None


def test_attaching_a_script_records_which_one():
    link()
    linked = client.get("/api/script/link", params={"production_id": PROD}).json()
    assert linked["script_id"] == SCRIPT
    assert linked["title"] == "LA CATHEDRALE"


def test_attaching_a_script_that_was_never_stored_is_refused():
    """Silently linking a script id nobody has uploaded would fail later, at
    the moment an editor asked to read a scene."""
    res = client.post("/api/script/link", json={"production_id": PROD, "script_id": "nope"})
    assert res.status_code == 404


def test_a_second_script_replaces_the_first():
    character_store.store_screenplay(
        script_id="other", title="Other Draft", filename=None, profiles=[]
    )
    link()
    client.post("/api/script/link", json={"production_id": PROD, "script_id": "other"})
    assert client.get("/api/script/link", params={"production_id": PROD}).json()["script_id"] == "other"


def test_a_script_can_be_detached():
    link()
    assert client.delete("/api/script/link", params={"production_id": PROD}).json()["unlinked"] is True
    assert client.get("/api/script/link", params={"production_id": PROD}).json() is None


# --------------------------------------------------------------------------- #
# Reading a scene
# --------------------------------------------------------------------------- #

def test_a_production_with_no_script_says_so_rather_than_returning_nothing():
    body = context("shot", "119/5")
    assert body["status"] == "no_script_linked"
    assert "Screenplay Studio" in body["message"]
    assert body["scenes"] == []


def test_a_shot_opens_the_scene_its_slate_names():
    link()
    body = context("shot", "119/5")
    assert body["status"] == "ok"
    assert [s["scene_number"] for s in body["scenes"]] == ["119"]
    assert "pipe organ console" in body["scenes"][0]["body"]


def test_a_scene_target_highlights_the_whole_scene():
    link()
    scene = context("scene", "119")["scenes"][0]
    assert scene["highlight_basis"] == "scene"
    assert scene["highlight"]["end"] == len(scene["body"])


def test_a_compound_slate_opens_every_scene_it_covers():
    link()
    body = context("shot", "41+119/4")
    assert [s["scene_number"] for s in body["scenes"]] == ["41", "119"]


def test_a_scene_missing_from_the_draft_is_named_rather_than_dropped():
    link()
    body = context("shot", "999/1")
    assert body["status"] == "scene_not_in_script"
    assert "999" in body["message"]


def test_a_compound_slate_half_in_the_draft_shows_what_it_has_and_says_what_it_lacks():
    link()
    body = context("shot", "119+999/4")
    assert [s["scene_number"] for s in body["scenes"]] == ["119"]
    assert "999" in body["message"]


def test_a_shot_with_no_logged_description_shows_the_whole_scene_unhighlighted():
    """
    Nothing in this production's spine describes 119/5, so there is nothing to
    match. The scene is still worth reading; the highlight is not invented.
    """
    link()
    scene = context("shot", "119/5")["scenes"][0]
    assert scene["highlight"] is None
    assert "no description" in scene["note"]


def test_an_unreadable_target_is_reported_as_unreadable():
    link()
    assert context("shot", "???")["status"] == "unreadable_target"


def test_a_target_type_that_is_neither_scene_nor_shot_is_refused():
    res = client.get(
        "/api/script/context",
        params={"production_id": PROD, "target_type": "take", "target_id": "119/5"},
    )
    assert res.status_code == 422


# --------------------------------------------------------------------------- #
# Storing the scenes in the first place
# --------------------------------------------------------------------------- #

def test_parsing_a_script_stores_its_scenes_for_later_reading():
    res = client.post(
        "/api/script/parse",
        json={
            "script_text": "Title: Test\n\nINT. KITCHEN - DAY\n\nA kettle boils.\n",
            "title": "Test",
        },
    )
    assert res.status_code == 200
    script_id = res.json()["script_id"]
    stored = character_store.get_screenplay_scenes(script_id)
    assert any("kettle" in s["body"] for s in stored)


def test_parsing_a_script_can_attach_it_to_a_production_in_one_step():
    res = client.post(
        "/api/script/parse",
        json={
            "script_text": "Title: Test\n\nINT. KITCHEN - DAY\n\nA kettle boils.\n",
            "title": "Test",
            "production_id": PROD,
        },
    )
    assert res.status_code == 200
    linked = client.get("/api/script/link", params={"production_id": PROD}).json()
    assert linked["script_id"] == res.json()["script_id"]


def test_re_parsing_a_changed_script_replaces_its_scenes():
    """
    A scene cut from the draft has to disappear from the store, or an editor
    would read a passage that is no longer in the film.
    """
    character_store.store_screenplay_scenes(
        SCRIPT, [{"scene_number": "7", "heading": "INT. X", "raw_content": "Gone next time.\n"}]
    )
    stored = character_store.get_screenplay_scenes(SCRIPT)
    assert [s["scene_number"] for s in stored] == ["7"]


# --------------------------------------------------------------------------- #
# Placing a shot inside its scene
# --------------------------------------------------------------------------- #

def _log_shot(slate: str, note: str):
    """Records what the script supervisor wrote beside a shot."""
    from backend.app.api.routes import spine_writer

    spine_writer.append_event(
        {
            "event_id": f"evt-{slate}-{len(note)}",
            "production_id": PROD,
            "shoot_day": "31",
            "axis": "belief",
            "department": "script",
            "doc_type": "scripte_tclog",
            "entity_type": "take",
            "payload": {"scene": slate.split("/")[0], "slate": slate, "take_id": "1", "note": note},
            "metadata": {},
            "timestamp": "2026-07-28T10:00:00Z",
        }
    )


def test_a_shots_description_places_it_inside_the_scene():
    link()
    _log_shot("119/5", "SUPPORT enters from the narthex with the dossier")
    scene = context("shot", "119/5")["scenes"][0]
    assert scene["highlight_basis"] == "description"
    assert "dossier" in scene["body"][scene["highlight"]["start"]:scene["highlight"]["end"]]


def test_a_placed_shot_shows_the_words_the_placement_rests_on():
    """
    The passage is inferred, not recorded. Handing over the matched words is
    what lets the editor see the reasoning and overrule it.
    """
    link()
    _log_shot("119/6", "LEAD strikes the C-minor chord on the organ")
    scene = context("shot", "119/6")["scenes"][0]
    assert "chord" in scene["highlight"]["terms"]


def test_a_description_that_matches_nothing_leaves_the_scene_unhighlighted():
    link()
    _log_shot("119/7", "helicopter lands on the motorway bridge")
    scene = context("shot", "119/7")["scenes"][0]
    assert scene["highlight"] is None
    assert "matched" in scene["note"]


def test_a_script_can_be_asked_which_productions_are_shooting_it():
    """
    The Script Studio knows only the script it has loaded. Without this reading
    it would offer to attach a script that is attached already.
    """
    link()
    res = client.get("/api/script/link", params={"script_id": SCRIPT})
    assert res.status_code == 200
    assert res.json()["production_ids"] == [PROD]


def test_an_unattached_script_is_shooting_nowhere():
    res = client.get("/api/script/link", params={"script_id": SCRIPT})
    assert res.json()["production_ids"] == []


def test_asking_for_a_link_without_naming_either_side_is_refused():
    assert client.get("/api/script/link").status_code == 422


def test_a_camera_reports_note_does_not_place_a_shot():
    """
    A camera note is about the take -- lens, filter, a reslate -- not about
    what the shot is of, so it must not drag the highlight around the scene.
    """
    from backend.app.api.routes import spine_writer

    spine_writer.append_event(
        {
            "event_id": "evt-cam-119-8",
            "production_id": PROD,
            "shoot_day": "31",
            "axis": "belief",
            "department": "camera",
            "doc_type": "camera_report",
            "entity_type": "take",
            "payload": {"slate": "119/8", "take_id": "1", "note": "narthex dossier organ"},
            "metadata": {},
            "timestamp": "2026-07-28T10:00:00Z",
        }
    )
    link()
    scene = context("shot", "119/8")["scenes"][0]
    assert scene["highlight"] is None
    assert "no description" in scene["note"]
