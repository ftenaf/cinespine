"""
Editorial tags on a scene or a shot.

The three axes are kept apart on purpose. Folding them into one list of free
text would make the only question a progress board exists to answer -- how much
is left, and what is it waiting on -- unanswerable.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.spine import tag_store
from backend.app.spine.tag_store import UnknownTagValue

client = TestClient(app)

PROD = "TAGTEST"


@pytest.fixture(autouse=True)
def _clean_slate():
    """conftest already points CINESPINE_DB_PATH at a temporary file."""
    for tag in tag_store.list_tags(PROD):
        tag_store.clear_tag(PROD, tag["target_type"], tag["target_id"])
    yield


# --------------------------------------------------------------------------- #
# What a tag hangs on
# --------------------------------------------------------------------------- #

def test_a_shot_is_identified_by_its_slate():
    tag = tag_store.set_tag(PROD, "shot", "27/7", status="mounted")
    assert (tag["target_type"], tag["target_id"]) == ("shot", "27/7")


@pytest.mark.parametrize("written", ["27/7", "27-7", "27/7T01", " 27/7 "])
def test_the_same_shot_spelled_differently_is_one_tag(written):
    """
    Two spellings landing on two rows would show one shot twice on the board,
    at two different stages.
    """
    tag_store.set_tag(PROD, "shot", "27/7", status="mounted")
    tag_store.set_tag(PROD, "shot", written, status="finished")
    tags = tag_store.list_tags(PROD, target_type="shot")
    assert len(tags) == 1
    assert tags[0]["status"] == "finished"


def test_tagging_a_slate_as_a_scene_tags_its_scene():
    """'27/7' names shot 7 of scene 27; as a scene target that is scene 27."""
    tag = tag_store.set_tag(PROD, "scene", "27/7", status="covered_per_script")
    assert tag["target_id"] == "27"


def test_a_scene_and_a_shot_are_separate_targets():
    tag_store.set_tag(PROD, "scene", "27", status="finished_shooting")
    tag_store.set_tag(PROD, "shot", "27/7", status="mounted")
    assert len(tag_store.list_tags(PROD)) == 2


def test_a_take_cannot_be_tagged():
    """A take is one attempt; what an editor tracks is the coverage."""
    with pytest.raises(UnknownTagValue):
        tag_store.set_tag(PROD, "take", "27/7", status="mounted")


# --------------------------------------------------------------------------- #
# The three axes
# --------------------------------------------------------------------------- #

def test_a_shot_carries_a_status_its_needs_and_its_kind_at_once():
    tag = tag_store.set_tag(
        PROD, "shot", "49/1",
        status="mounted",
        needs=["sfx", "subtitles"],
        descriptors=["establishment"],
    )
    assert tag["status"] == "mounted"
    assert tag["needs"] == ["sfx", "subtitles"]
    assert tag["descriptors"] == ["establishment"]


def test_a_mounted_shot_can_still_owe_work():
    """The axes are independent: progress does not clear what is outstanding."""
    tag = tag_store.set_tag(PROD, "shot", "49/1", status="finished", needs=["translation"])
    assert tag["status"] == "finished" and tag["needs"] == ["translation"]


def test_only_one_status_at_a_time():
    tag_store.set_tag(PROD, "shot", "49/1", status="ready_to_edit")
    tag_store.set_tag(PROD, "shot", "49/1", status="mounted")
    assert tag_store.get_tag(PROD, "shot", "49/1")["status"] == "mounted"


def test_a_need_recorded_twice_is_recorded_once():
    tag = tag_store.set_tag(PROD, "shot", "49/1", needs=["sfx", "sfx"])
    assert tag["needs"] == ["sfx"]


# --------------------------------------------------------------------------- #
# The vocabulary is closed
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("bad", ["Mounted", "montado", "in_progress", ""])
def test_a_status_outside_the_vocabulary_is_refused(bad):
    """
    'sfx' and 'SFX' and 'sound fx' would each be counted separately, so the
    board would under-report every one of them.
    """
    with pytest.raises(UnknownTagValue):
        tag_store.set_tag(PROD, "shot", "49/1", status=bad)


def test_a_need_outside_the_vocabulary_is_refused():
    with pytest.raises(UnknownTagValue):
        tag_store.set_tag(PROD, "shot", "49/1", needs=["colour grade"])


def test_no_status_at_all_is_allowed():
    """A shot can be flagged as needing subtitles before anyone rates progress."""
    tag = tag_store.set_tag(PROD, "shot", "49/1", needs=["subtitles"])
    assert tag["status"] is None


def test_the_vocabulary_is_served_with_its_labels_and_order():
    vocab = tag_store.vocabulary()
    assert [s["key"] for s in vocab["statuses"]] == [
        "finished_shooting", "covered_per_script", "ready_to_edit", "mounted", "finished",
    ]
    assert [s["ordinal"] for s in vocab["statuses"]] == [1, 2, 3, 4, 5]
    assert {n["key"] for n in vocab["needs"]} == {"sfx", "subtitles", "translation"}


# --------------------------------------------------------------------------- #
# Writing replaces, so a flag can be taken off
# --------------------------------------------------------------------------- #

def test_a_need_can_be_taken_off_again():
    """With merge semantics a client could only ever add."""
    tag_store.set_tag(PROD, "shot", "49/1", status="mounted", needs=["sfx", "subtitles"])
    tag = tag_store.set_tag(PROD, "shot", "49/1", status="mounted", needs=["subtitles"])
    assert tag["needs"] == ["subtitles"]


def test_clearing_removes_the_target_entirely():
    tag_store.set_tag(PROD, "shot", "49/1", status="mounted")
    assert tag_store.clear_tag(PROD, "shot", "49/1") is True
    assert tag_store.get_tag(PROD, "shot", "49/1") is None


def test_clearing_a_target_that_was_never_tagged_says_so():
    assert tag_store.clear_tag(PROD, "shot", "99/9") is False


def test_who_set_it_is_recorded():
    tag = tag_store.set_tag(PROD, "shot", "49/1", status="mounted", updated_by="ana")
    assert tag["updated_by"] == "@ana"
    assert tag["updated_at"]


# --------------------------------------------------------------------------- #
# Reading it back for a board
# --------------------------------------------------------------------------- #

def _populate():
    tag_store.set_tag(PROD, "shot", "27/7", status="mounted", needs=["sfx"])
    tag_store.set_tag(PROD, "shot", "49/1", status="mounted", needs=["sfx", "subtitles"])
    tag_store.set_tag(PROD, "shot", "49/2", status="ready_to_edit")
    tag_store.set_tag(PROD, "scene", "117", status="finished", descriptors=["establishment"])
    tag_store.set_tag(PROD, "shot", "6/1", needs=["translation"])


def test_tags_can_be_narrowed_by_each_axis():
    _populate()
    assert len(tag_store.list_tags(PROD, status="mounted")) == 2
    assert len(tag_store.list_tags(PROD, need="sfx")) == 2
    assert len(tag_store.list_tags(PROD, need="subtitles")) == 1
    assert len(tag_store.list_tags(PROD, target_type="scene")) == 1
    assert len(tag_store.list_tags(PROD, descriptor="establishment")) == 1


def test_a_need_is_matched_whole_not_as_a_substring():
    """'sfx' must not match a longer key that happens to contain it."""
    _populate()
    assert tag_store.list_tags(PROD, need="sf") == []


def test_the_summary_counts_progress_and_what_is_outstanding():
    _populate()
    summary = tag_store.summarize(PROD)
    assert summary["tagged_targets"] == 5
    assert summary["by_status"]["mounted"] == 2
    assert summary["by_status"]["finished"] == 1
    assert summary["no_status"] == 1
    assert summary["by_need"] == {"sfx": 2, "subtitles": 1, "translation": 1}
    assert summary["by_descriptor"] == {"establishment": 1}


def test_one_production_does_not_see_another_s_tags():
    _populate()
    tag_store.set_tag("OTHER", "shot", "27/7", status="finished")
    try:
        assert len(tag_store.list_tags(PROD)) == 5
        assert len(tag_store.list_tags("OTHER")) == 1
    finally:
        tag_store.clear_tag("OTHER", "shot", "27/7")


def test_a_tag_outlives_the_process_that_wrote_it():
    """
    These are hand-authored, like the character profiles next door. Holding them
    in process memory would lose an editor's afternoon to a restart.
    """
    tag_store.set_tag(PROD, "shot", "27/7", status="mounted", needs=["sfx"])
    import importlib
    reloaded = importlib.reload(tag_store)
    try:
        survived = reloaded.get_tag(PROD, "shot", "27/7")
        assert survived is not None
        assert survived["status"] == "mounted" and survived["needs"] == ["sfx"]
    finally:
        importlib.reload(tag_store)


# --------------------------------------------------------------------------- #
# Over the API
# --------------------------------------------------------------------------- #

def test_the_api_writes_reads_and_clears_a_tag():
    body = {
        "production_id": PROD, "target_type": "shot", "target_id": "27/7",
        "status": "mounted", "needs": ["sfx"], "descriptors": [],
        "note": "watch the join at the end", "updated_by": "ana",
    }
    written = client.put("/api/tags", json=body)
    assert written.status_code == 200
    assert written.json()["status"] == "mounted"
    assert written.json()["updated_by"] == "@ana"

    listed = client.get("/api/tags", params={"production_id": PROD})
    assert [t["target_id"] for t in listed.json()] == ["27/7"]

    cleared = client.delete(
        "/api/tags",
        params={"production_id": PROD, "target_type": "shot", "target_id": "27/7"},
    )
    assert cleared.status_code == 200
    assert client.get("/api/tags", params={"production_id": PROD}).json() == []


def test_the_api_refuses_a_word_outside_the_vocabulary():
    response = client.put("/api/tags", json={
        "production_id": PROD, "target_type": "shot", "target_id": "27/7",
        "status": "nearly_there",
    })
    assert response.status_code == 400
    assert "nearly_there" in response.json()["detail"]


def test_the_api_serves_the_vocabulary():
    vocab = client.get("/api/tags/vocabulary").json()
    assert vocab["target_types"] == ["scene", "shot"]
    assert {n["key"] for n in vocab["needs"]} == {"sfx", "subtitles", "translation"}


def test_the_api_summarises_a_production():
    client.put("/api/tags", json={
        "production_id": PROD, "target_type": "shot", "target_id": "27/7",
        "status": "mounted", "needs": ["sfx", "translation"],
    })
    summary = client.get("/api/tags/summary", params={"production_id": PROD}).json()
    assert summary["by_status"]["mounted"] == 1
    assert summary["by_need"]["sfx"] == 1
    assert summary["by_need"]["subtitles"] == 0


def test_clearing_a_target_that_was_never_tagged_is_a_404():
    response = client.delete(
        "/api/tags",
        params={"production_id": PROD, "target_type": "shot", "target_id": "99/9"},
    )
    assert response.status_code == 404
