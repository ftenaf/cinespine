"""
Editorial tags on a scene or a shot.

The three axes are kept apart on purpose. Folding them into one list of free
text would make the only question a progress board exists to answer -- how much
is left, and what is it waiting on -- unanswerable.
"""
import json

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
    """
    The whole chain, in the order work happens. This pinned five statuses until
    2026-08-30 and caught the change that added the four after the cutting room
    -- see test_completion_chain.py for what they mean.
    """
    vocab = tag_store.vocabulary()
    assert [s["key"] for s in vocab["statuses"]] == [
        "finished_shooting", "covered_per_script", "ready_to_edit", "mounted", "finished",
        "picture_lock", "colour_sound_vfx", "conformed", "dcp",
    ]
    assert [s["ordinal"] for s in vocab["statuses"]] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
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

    # Read straight off the file with a connection this module never opened:
    # nothing in process memory can make this pass.
    import sqlite3
    conn = sqlite3.connect(tag_store.get_db_path())
    try:
        row = conn.execute(
            "SELECT status, needs FROM editorial_tags"
            " WHERE production_id = ? AND target_type = ? AND target_id = ?",
            (PROD, "shot", "27/7"),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == "mounted" and json.loads(row[1]) == ["sfx"]


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


# --------------------------------------------------------------------------- #
# How a target got to where it is
# --------------------------------------------------------------------------- #

def test_every_change_is_kept():
    tag_store.set_tag(PROD, "shot", "27/7", status="ready_to_edit", updated_by="ana")
    tag_store.set_tag(PROD, "shot", "27/7", status="mounted", updated_by="ben")
    trail = tag_store.history(PROD, "shot", "27/7")
    assert [e["status"] for e in trail] == ["mounted", "ready_to_edit"]
    assert [e["actor"] for e in trail] == ["@ben", "@ana"]


def test_the_newest_change_comes_first():
    """A trail is read from the present backwards."""
    for status in ("finished_shooting", "ready_to_edit", "mounted"):
        tag_store.set_tag(PROD, "shot", "27/7", status=status)
    assert tag_store.history(PROD, "shot", "27/7")[0]["status"] == "mounted"


def test_clearing_is_recorded_with_what_was_cleared():
    """
    A tag that vanished still has to be accounted for, so the history keeps the
    state it was in when it went.
    """
    tag_store.set_tag(PROD, "shot", "27/7", status="mounted", needs=["sfx"])
    tag_store.clear_tag(PROD, "shot", "27/7")
    latest = tag_store.history(PROD, "shot", "27/7")[0]
    assert latest["action"] == "cleared"
    assert latest["status"] == "mounted" and latest["needs"] == ["sfx"]


def test_history_survives_the_tag_it_describes():
    tag_store.set_tag(PROD, "shot", "27/7", status="mounted")
    tag_store.clear_tag(PROD, "shot", "27/7")
    assert tag_store.get_tag(PROD, "shot", "27/7") is None
    assert len(tag_store.history(PROD, "shot", "27/7")) == 2


def test_a_production_s_whole_trail_can_be_read():
    tag_store.set_tag(PROD, "shot", "27/7", status="mounted")
    tag_store.set_tag(PROD, "scene", "117", status="finished")
    assert len(tag_store.history(PROD)) == 2


def test_the_trail_of_one_target_excludes_the_others():
    tag_store.set_tag(PROD, "shot", "27/7", status="mounted")
    tag_store.set_tag(PROD, "shot", "49/1", status="mounted")
    assert len(tag_store.history(PROD, "shot", "27/7")) == 1


def test_a_target_is_matched_however_it_is_spelled():
    tag_store.set_tag(PROD, "shot", "27/7", status="mounted")
    assert len(tag_store.history(PROD, "shot", "27-7")) == 1


def test_naming_a_target_id_without_a_type_is_refused():
    with pytest.raises(UnknownTagValue):
        tag_store.history(PROD, target_id="27/7")


def test_the_api_serves_a_target_s_history():
    client.put("/api/tags", json={
        "production_id": PROD, "target_type": "shot", "target_id": "27/7",
        "status": "mounted", "updated_by": "ana",
    })
    trail = client.get("/api/tags/history", params={
        "production_id": PROD, "target_type": "shot", "target_id": "27/7",
    }).json()
    assert len(trail) == 1
    assert trail[0]["actor"] == "@ana" and trail[0]["action"] == "set"


# --------------------------------------------------------------------------- #
# Other editors are told
# --------------------------------------------------------------------------- #

def _published(fn):
    """Runs fn and returns the live events it published."""
    from backend.app.streaming.broker import event_broker
    seen = []
    original = event_broker.publish_sync
    event_broker.publish_sync = lambda e: seen.append(e)
    try:
        fn()
    finally:
        event_broker.publish_sync = original
    return seen


def test_setting_a_tag_tells_the_other_editors():
    events = _published(lambda: client.put("/api/tags", json={
        "production_id": PROD, "target_type": "shot", "target_id": "27/7",
        "status": "mounted", "needs": ["sfx"],
    }))
    assert [e.event_type for e in events] == ["EDITORIAL_TAG_SET"]
    assert events[0].data["status"] == "mounted"
    assert events[0].production_id == PROD


def test_clearing_a_tag_tells_them_too():
    """
    Publishing only the set left every other board showing a tag that had
    already been taken off.
    """
    client.put("/api/tags", json={
        "production_id": PROD, "target_type": "shot", "target_id": "27/7",
        "status": "mounted",
    })
    events = _published(lambda: client.delete("/api/tags", params={
        "production_id": PROD, "target_type": "shot", "target_id": "27/7",
    }))
    assert [e.event_type for e in events] == ["EDITORIAL_TAG_CLEARED"]


def test_a_tag_event_reaches_a_subscriber_on_any_day():
    """
    A tag belongs to the production, not to a day, so it is published against
    every day rather than against one -- otherwise an editor looking at day 31
    never hears about it.
    """
    from backend.app.streaming.broker import SpineLiveEvent, SSESubscriber

    subscriber = SSESubscriber("s1", production_id=PROD, shoot_day="31")
    event = SpineLiveEvent(
        event_type="EDITORIAL_TAG_SET", production_id=PROD, shoot_day="ALL",
        summary="Tagged shot 27/7",
    )
    assert subscriber.matches(event) is True


# --------------------------------------------------------------------------- #
# The analytical spine, when there is one
# --------------------------------------------------------------------------- #

class FakeClickHouse:
    """Records what would have been inserted."""

    def __init__(self, fail=False):
        self.rows = []
        self.fail = fail

    def insert(self, table, rows, column_names):
        if self.fail:
            raise ConnectionError("clickhouse is down")
        self.rows.append((table, rows, column_names))


def test_a_tag_change_is_mirrored_to_the_analytical_spine():
    from backend.app.spine.writer import SpineWriter

    fake = FakeClickHouse()
    writer = SpineWriter(clickhouse_client=fake)
    writer.set_editorial_tag(
        production_id=PROD, target_type="shot", target_id="27/7",
        status="mounted", needs=["sfx"], updated_by="ana",
    )
    assert len(fake.rows) == 1
    table, rows, columns = fake.rows[0]
    assert table == "cinespine.editorial_tag_events"
    assert dict(zip(columns, rows[0]))["status"] == "mounted"
    assert dict(zip(columns, rows[0]))["action"] == "set"


def test_a_clearing_is_mirrored_too():
    from backend.app.spine.writer import SpineWriter

    fake = FakeClickHouse()
    writer = SpineWriter(clickhouse_client=fake)
    writer.set_editorial_tag(
        production_id=PROD, target_type="shot", target_id="27/7", status="mounted")
    writer.clear_editorial_tag(PROD, "shot", "27/7")
    assert [dict(zip(c, r[0]))["action"] for _, r, c in fake.rows] == ["set", "cleared"]


def test_a_clickhouse_that_is_down_does_not_lose_the_editor_s_change():
    """
    SQLite has already recorded it. Failing an editor's save because a reporting
    database is unreachable would be the wrong trade every time.
    """
    from backend.app.spine.writer import SpineWriter

    writer = SpineWriter(clickhouse_client=FakeClickHouse(fail=True))
    tag = writer.set_editorial_tag(
        production_id=PROD, target_type="shot", target_id="27/7", status="mounted")
    assert tag["status"] == "mounted"
    assert tag_store.get_tag(PROD, "shot", "27/7")["status"] == "mounted"


def test_no_clickhouse_configured_is_not_an_error(monkeypatch):
    from backend.app.spine import clickhouse

    monkeypatch.delenv("CLICKHOUSE_HOST", raising=False)
    assert clickhouse.is_configured() is False
    assert clickhouse.connect() is None


def test_an_unreachable_clickhouse_degrades_rather_than_raising(monkeypatch):
    """A laptop with no Docker running must still serve the whole application."""
    from backend.app.spine import clickhouse

    monkeypatch.setenv("CLICKHOUSE_HOST", "203.0.113.1")  # reserved, never routes
    monkeypatch.setenv("CLICKHOUSE_CONNECT_TIMEOUT", "1")
    assert clickhouse.connect() is None


def test_the_writer_works_with_no_analytical_spine_at_all(monkeypatch):
    from backend.app.spine.writer import SpineWriter

    monkeypatch.delenv("CLICKHOUSE_HOST", raising=False)
    writer = SpineWriter()
    assert writer.client is None
    tag = writer.set_editorial_tag(
        production_id=PROD, target_type="shot", target_id="27/7", status="mounted")
    assert tag["status"] == "mounted"


# --------------------------------------------------------------------------- #
# What running it against a real ClickHouse taught
# --------------------------------------------------------------------------- #

def test_events_are_sent_together_not_one_at_a_time():
    """
    One insert per event turned a 72-event ingestion from 0.8s into 7.4s and a
    1991-event one into over two minutes: each insert is a round trip and a new
    part on the server.
    """
    from backend.app.spine.writer import SpineWriter

    fake = FakeClickHouse()
    writer = SpineWriter(clickhouse_client=fake)
    for i in range(72):
        writer.append_event({"event_id": f"e{i}", "production_id": PROD,
                             "shoot_day": "31", "entity_type": "take", "payload": {}})

    assert fake.rows == [], "nothing should go until the ingestion is done"
    assert writer.flush_events() == 72
    assert len(fake.rows) == 1, "one insert, not seventy-two"
    assert len(fake.rows[0][1]) == 72


def test_a_runaway_ingestion_flushes_before_memory_grows():
    from backend.app.spine.writer import SpineWriter, EVENT_BATCH_SIZE

    fake = FakeClickHouse()
    writer = SpineWriter(clickhouse_client=fake)
    for i in range(EVENT_BATCH_SIZE + 10):
        writer.append_event({"event_id": f"e{i}", "production_id": PROD,
                             "shoot_day": "31", "entity_type": "take", "payload": {}})
    assert len(fake.rows) == 1
    assert len(writer._pending_rows) == 10


def test_every_event_still_reaches_the_in_memory_spine_unbuffered():
    """Buffering is for the analytical copy only; reads must not wait on it."""
    from backend.app.spine.writer import SpineWriter

    writer = SpineWriter(clickhouse_client=FakeClickHouse())
    writer.append_event({"event_id": "e1", "production_id": PROD, "shoot_day": "31",
                         "entity_type": "take", "payload": {}})
    assert len(writer.get_events(production_id=PROD)) == 1


def test_a_failed_flush_does_not_grow_the_buffer_forever():
    """
    The in-memory spine already has every event. A reporting copy is not worth
    growing memory without bound to protect.
    """
    from backend.app.spine.writer import SpineWriter

    writer = SpineWriter(clickhouse_client=FakeClickHouse(fail=True))
    writer.append_event({"event_id": "e1", "production_id": PROD, "shoot_day": "31",
                         "entity_type": "take", "payload": {}})
    assert writer.flush_events() == 0
    assert writer._pending_rows == []


def test_flushing_with_no_analytical_spine_is_a_no_op(monkeypatch):
    from backend.app.spine.writer import SpineWriter

    monkeypatch.delenv("CLICKHOUSE_HOST", raising=False)
    writer = SpineWriter()
    writer.append_event({"event_id": "e1", "production_id": PROD, "shoot_day": "31",
                         "entity_type": "take", "payload": {}})
    assert writer.flush_events() == 0


@pytest.mark.parametrize("iso, expected", [
    ("2026-08-28T16:35:45.789378+00:00", "2026-08-28 16:35:45.789378+00:00"),
    ("2026-08-28T16:35:45.789378",       "2026-08-28 16:35:45.789378+00:00"),
])
def test_a_mirrored_timestamp_stays_in_utc(iso, expected):
    """
    Sent naive, the driver read it as local time: on a machine an hour off UTC
    every row landed an hour before it happened. The order was still right,
    which is what makes that kind of mistake survive a review.
    """
    from backend.app.spine.writer import _clickhouse_datetime

    converted = _clickhouse_datetime(iso)
    assert converted.tzinfo is not None
    assert str(converted) == expected


def test_an_unreadable_timestamp_falls_back_to_now():
    from backend.app.spine.writer import _clickhouse_datetime

    assert _clickhouse_datetime("not a date").tzinfo is not None
    assert _clickhouse_datetime(None).tzinfo is not None


def test_the_mirrored_tag_event_carries_its_own_time():
    from backend.app.spine.writer import SpineWriter

    fake = FakeClickHouse()
    writer = SpineWriter(clickhouse_client=fake)
    writer.set_editorial_tag(production_id=PROD, target_type="shot",
                             target_id="27/7", status="mounted")
    _, rows, columns = fake.rows[0]
    assert "created_at" in columns
    assert dict(zip(columns, rows[0]))["created_at"].tzinfo is not None


def test_the_trail_names_whoever_removed_the_tag():
    """
    The clear used to copy the previous tag's actor, so the trail credited the
    removal to whoever last set it -- the wrong person for the one question the
    trail exists to answer.
    """
    tag_store.set_tag(PROD, "shot", "27/7", status="mounted", updated_by="ana")
    tag_store.clear_tag(PROD, "shot", "27/7", cleared_by="ben")
    latest = tag_store.history(PROD, "shot", "27/7")[0]
    assert latest["action"] == "cleared"
    assert latest["actor"] == "@ben"


def test_a_removal_by_nobody_in_particular_names_nobody():
    tag_store.set_tag(PROD, "shot", "27/7", status="mounted", updated_by="ana")
    tag_store.clear_tag(PROD, "shot", "27/7")
    assert tag_store.history(PROD, "shot", "27/7")[0]["actor"] is None


def test_the_api_carries_the_clearing_actor_through():
    client.put("/api/tags", json={
        "production_id": PROD, "target_type": "shot", "target_id": "27/7",
        "status": "mounted", "updated_by": "ana",
    })
    client.delete("/api/tags", params={
        "production_id": PROD, "target_type": "shot", "target_id": "27/7",
        "cleared_by": "ben",
    })
    trail = client.get("/api/tags/history", params={
        "production_id": PROD, "target_type": "shot", "target_id": "27/7",
    }).json()
    assert trail[0]["actor"] == "@ben" and trail[1]["actor"] == "@ana"


# --------------------------------------------------------------------------- #
# The board
# --------------------------------------------------------------------------- #

SHOTS = ["27/7", "27/8", "49/1", "49/2", "117/1"]
SCENES = ["27", "49", "117"]


def test_progress_is_measured_against_what_the_production_contains():
    """
    Counting only tagged things cannot express progress: three mounted shots
    reads the same in a production of three as in one of two hundred.
    """
    tag_store.set_tag(PROD, "shot", "27/7", status="mounted")
    board = tag_store.progress(PROD, SHOTS, SCENES)
    assert board["shots"]["known"] == 5
    assert board["shots"]["by_status"]["mounted"] == 1
    assert board["shots"]["no_status"] == 4


def test_what_nobody_has_tagged_is_counted():
    board = tag_store.progress(PROD, SHOTS, SCENES)
    assert board["shots"]["no_status"] == 5
    assert board["scenes"]["no_status"] == 3


def test_scenes_and_shots_are_counted_apart():
    """
    A scene marked finished says nothing about the shots inside it. Merging the
    two would invent a number nobody asserted.
    """
    tag_store.set_tag(PROD, "scene", "117", status="finished")
    board = tag_store.progress(PROD, SHOTS, SCENES)
    assert board["scenes"]["by_status"]["finished"] == 1
    assert board["shots"]["by_status"]["finished"] == 0


def test_a_tag_on_something_the_spine_has_never_seen_is_kept_apart():
    """
    A shot tagged before its paperwork arrived would otherwise inflate the
    denominator, or vanish. Neither is honest, so it is listed.
    """
    tag_store.set_tag(PROD, "shot", "999/1", status="mounted")
    board = tag_store.progress(PROD, SHOTS, SCENES)
    assert board["shots"]["known"] == 5
    assert board["shots"]["tagged_but_unknown"] == ["999/1"]
    assert board["shots"]["by_status"]["mounted"] == 0


def test_outstanding_work_lists_the_targets_not_just_a_count():
    """A number cannot be worked from; a list is a job to pick up."""
    tag_store.set_tag(PROD, "shot", "27/7", status="mounted", needs=["sfx", "subtitles"])
    tag_store.set_tag(PROD, "shot", "49/1", needs=["sfx"])
    board = tag_store.progress(PROD, SHOTS, SCENES)
    assert [t["target_id"] for t in board["outstanding"]["sfx"]] == ["27/7", "49/1"]
    assert [t["target_id"] for t in board["outstanding"]["subtitles"]] == ["27/7"]
    assert board["outstanding"]["translation"] == []


def test_a_finished_shot_can_still_be_outstanding():
    tag_store.set_tag(PROD, "shot", "27/7", status="finished", needs=["translation"])
    board = tag_store.progress(PROD, SHOTS, SCENES)
    assert board["shots"]["by_status"]["finished"] == 1
    assert len(board["outstanding"]["translation"]) == 1


def test_the_board_reads_every_shoot_day():
    """
    A shot is covered across whatever days it took, so a per-day board would
    split one shot's story in two.
    """
    from backend.app.streaming.bus import EventBus
    from backend.app.spine.writer import SpineWriter

    writer = SpineWriter(clickhouse_client=None)
    for day, slate in (("11", "119/5"), ("31", "27/7")):
        writer.append_event({
            "event_id": f"e{day}", "production_id": "BOARD", "shoot_day": day,
            "entity_type": "take", "payload": {"slate": slate, "scene": slate.split("/")[0]},
        })
    days = {e["shoot_day"] for e in writer.get_events(production_id="BOARD")}
    assert days == {"11", "31"}


def test_the_api_serves_a_board():
    client.put("/api/tags", json={
        "production_id": PROD, "target_type": "shot", "target_id": "27/7",
        "status": "mounted", "needs": ["sfx"],
    })
    board = client.get("/api/dashboard", params={"production_id": PROD}).json()
    assert "shots" in board and "scenes" in board and "outstanding" in board
    assert board["vocabulary"]["statuses"][0]["key"] == "finished_shooting"
    assert board["recent"] and board["recent"][0]["target_id"] == "27/7"


def test_a_production_with_no_paperwork_yet_is_an_empty_board_not_an_error():
    board = client.get("/api/dashboard", params={"production_id": "NOTHING_HERE"}).json()
    assert board["shots"]["known"] == 0
    assert board["outstanding"]["sfx"] == []
    assert board["recent"] == []


# --------------------------------------------------------------------------- #
# The analytical indexes
# --------------------------------------------------------------------------- #

def _writer_with(fake):
    from backend.app.spine.writer import SpineWriter
    return SpineWriter(clickhouse_client=fake)


def _take_event(slate, take_id, roll, **payload):
    return {
        "event_id": f"e_{slate}_{take_id}_{roll}", "production_id": "IDX",
        "shoot_day": "31", "entity_type": "take",
        "payload": {"slate": slate, "take_id": take_id, "camera_roll": roll,
                    "scene": slate.split("/")[0], **payload},
    }


def test_a_take_is_indexed_once_per_camera_roll():
    """
    One row per roll, not per take: that is what the table's key says, and a
    take shot on three cameras is three witnesses.
    """
    fake = FakeClickHouse()
    writer = _writer_with(fake)
    for roll in ("A120", "B039", "C005"):
        writer.append_event(_take_event("27/7", "1", roll))
    assert writer.project_takes("IDX", "31") == 3


def test_the_latest_event_for_a_row_wins():
    fake = FakeClickHouse()
    writer = _writer_with(fake)
    writer.append_event(_take_event("27/7", "1", "A120", timecode_in="09:00:00:00"))
    writer.append_event(_take_event("27/7", "1", "A120", timecode_in="10:00:00:00"))
    assert writer.project_takes("IDX", "31") == 1
    table, rows, columns = fake.rows[-1]
    assert table == "cinespine.takes_meta"
    assert dict(zip(columns, rows[0]))["timecode_in"] == "10:00:00:00"


def test_no_claim_about_a_circle_is_indexed_as_no_claim():
    """
    A lined page may assert that a take was circled and may not assert that it
    was not. Writing that silence as 0 would make the index state something no
    witness said.
    """
    fake = FakeClickHouse()
    writer = _writer_with(fake)
    writer.append_event(_take_event("27/7", "1", "A120", is_starred=None))
    writer.append_event(_take_event("27/8", "1", "A120", is_starred=True))
    writer.append_event(_take_event("49/1", "1", "A120", is_starred=False))
    writer.project_takes("IDX", "31")
    _, rows, columns = fake.rows[-1]
    starred = {dict(zip(columns, r))["slate"]: dict(zip(columns, r))["is_starred"] for r in rows}
    assert starred == {"27/7": None, "27/8": 1, "49/1": 0}


def test_an_event_without_a_slate_or_take_is_not_indexed():
    fake = FakeClickHouse()
    writer = _writer_with(fake)
    writer.append_event(_take_event("27/7", "1", "A120"))
    writer.append_event({"event_id": "x", "production_id": "IDX", "shoot_day": "31",
                         "entity_type": "take", "payload": {"camera_roll": "A120"}})
    assert writer.project_takes("IDX", "31") == 1


def test_media_events_are_not_takes():
    fake = FakeClickHouse()
    writer = _writer_with(fake)
    writer.append_event({"event_id": "m", "production_id": "IDX", "shoot_day": "31",
                         "entity_type": "media_file", "payload": {"file_name": "A_001.mxf"}})
    assert writer.project_takes("IDX", "31") == 0


def test_discrepancies_are_indexed_as_they_stand():
    fake = FakeClickHouse()
    writer = _writer_with(fake)
    written = writer.project_discrepancies([{
        "discrepancy_id": "d1", "production_id": "IDX", "shoot_day": "31",
        "entity_type": "take", "entity_id": "49/1 Take 1",
        "discrepancy_type": "CIRCLED_TAKE_MISMATCH", "severity": "CRITICAL",
        "description": "conflicting", "witnesses": [{"a": 1}], "is_resolved": False,
    }])
    assert written == 1
    table, rows, columns = fake.rows[-1]
    assert table == "cinespine.audit_discrepancies"
    row = dict(zip(columns, rows[0]))
    assert row["entity_id"] == "49/1 Take 1" and row["is_resolved"] == 0
    assert json.loads(row["witnesses_json"]) == [{"a": 1}]


def test_a_resolved_discrepancy_is_written_as_resolved():
    fake = FakeClickHouse()
    written = _writer_with(fake).project_discrepancies([{
        "discrepancy_id": "d1", "production_id": "IDX", "shoot_day": "31",
        "is_resolved": True, "witnesses": [],
    }])
    assert written == 1
    _, rows, columns = fake.rows[-1]
    assert dict(zip(columns, rows[0]))["is_resolved"] == 1


def test_projecting_without_an_analytical_spine_is_a_no_op(monkeypatch):
    monkeypatch.delenv("CLICKHOUSE_HOST", raising=False)
    from backend.app.spine.writer import SpineWriter

    writer = SpineWriter()
    writer.append_event(_take_event("27/7", "1", "A120"))
    assert writer.project_takes("IDX", "31") == 0
    assert writer.project_discrepancies([{"discrepancy_id": "d"}]) == 0


def test_a_failed_projection_does_not_raise():
    """An ingestion must not fail because a reporting database is unhappy."""
    fake = FakeClickHouse(fail=True)
    writer = _writer_with(fake)
    writer.append_event(_take_event("27/7", "1", "A120"))
    assert writer.project_takes("IDX", "31") == 0
    assert writer.project_discrepancies([{"discrepancy_id": "d", "witnesses": []}]) == 0


def test_takes_from_every_day_are_indexed_not_just_the_upload_s():
    """
    A facing page is filed under the day it is handed over but carries takes
    from every day the scene was covered. Projecting only the envelope's day
    left sixty takes in the spine and out of the index.
    """
    fake = FakeClickHouse()
    writer = _writer_with(fake)
    writer.append_event({**_take_event("119/5", "1", "A046"), "shoot_day": "11"})
    writer.append_event({**_take_event("41+122A/4", "1", "A068"), "shoot_day": "15"})
    writer.append_event(_take_event("27/7", "1", "A120"))  # day 31

    assert writer.project_takes("IDX") == 3
    _, rows, columns = fake.rows[-1]
    days = {dict(zip(columns, r))["shoot_day"] for r in rows}
    assert days == {"11", "15", "31"}


def test_a_row_keeps_the_day_its_take_was_shot_on():
    fake = FakeClickHouse()
    writer = _writer_with(fake)
    writer.append_event({**_take_event("119/5", "1", "A046"), "shoot_day": "11"})
    writer.project_takes("IDX")
    _, rows, columns = fake.rows[-1]
    assert dict(zip(columns, rows[0]))["shoot_day"] == "11"


def test_the_same_slate_on_two_days_is_two_rows():
    """Collapsing them by slate and roll alone would lose one of the days."""
    fake = FakeClickHouse()
    writer = _writer_with(fake)
    writer.append_event({**_take_event("27/7", "1", "A120"), "event_id": "a", "shoot_day": "30"})
    writer.append_event({**_take_event("27/7", "1", "A120"), "event_id": "b", "shoot_day": "31"})
    assert writer.project_takes("IDX") == 2


def test_narrowing_to_one_day_still_works():
    fake = FakeClickHouse()
    writer = _writer_with(fake)
    writer.append_event({**_take_event("119/5", "1", "A046"), "shoot_day": "11"})
    writer.append_event(_take_event("27/7", "1", "A120"))
    assert writer.project_takes("IDX", "11") == 1


# --------------------------------------------------------------------------- #
# When ClickHouse dies after connecting
# --------------------------------------------------------------------------- #

class CountingClickHouse(FakeClickHouse):
    """Counts attempts as well as recording them, so a skip is visible."""

    def __init__(self, fail=False):
        super().__init__(fail=fail)
        self.attempts = 0

    def insert(self, table, rows, column_names):
        self.attempts += 1
        super().insert(table, rows, column_names)


def test_a_failed_insert_shuts_the_mirror():
    """
    A server absent at startup costs nothing -- connect returns None. One that
    dies after connecting is the expensive case: the driver retries with backoff
    on every call, which took an ingestion from 0.9s to 16.7s and a single tag
    save from instant to 8.2s.
    """
    from backend.app.spine.writer import SpineWriter

    fake = CountingClickHouse(fail=True)
    writer = SpineWriter(clickhouse_client=fake)
    writer.set_editorial_tag(production_id=PROD, target_type="shot",
                             target_id="27/7", status="mounted")
    assert fake.attempts == 1
    assert writer.mirror_available() is False

    # Everything after this is skipped outright rather than attempted again.
    writer.set_editorial_tag(production_id=PROD, target_type="shot",
                             target_id="49/1", status="mounted")
    writer.set_editorial_tag(production_id=PROD, target_type="shot",
                             target_id="49/2", status="mounted")
    assert fake.attempts == 1


def test_the_editor_s_change_still_lands_while_the_mirror_is_shut():
    from backend.app.spine.writer import SpineWriter

    writer = SpineWriter(clickhouse_client=CountingClickHouse(fail=True))
    writer.set_editorial_tag(production_id=PROD, target_type="shot",
                             target_id="27/7", status="mounted")
    writer.set_editorial_tag(production_id=PROD, target_type="shot",
                             target_id="49/1", status="finished")
    assert tag_store.get_tag(PROD, "shot", "49/1")["status"] == "finished"
    assert len(tag_store.history(PROD, "shot", "49/1")) == 1


def test_the_mirror_opens_again_after_the_cooldown(monkeypatch):
    from backend.app.spine import writer as writer_module
    from backend.app.spine.writer import SpineWriter

    clock = [1000.0]
    monkeypatch.setattr(writer_module.time, "monotonic", lambda: clock[0])

    fake = CountingClickHouse(fail=True)
    w = SpineWriter(clickhouse_client=fake)
    w.set_editorial_tag(production_id=PROD, target_type="shot",
                        target_id="27/7", status="mounted")
    assert w.mirror_available() is False

    clock[0] += writer_module.MIRROR_COOLDOWN_SECONDS - 1
    assert w.mirror_available() is False, "still inside the cooldown"

    clock[0] += 2
    assert w.mirror_available() is True, "one probe is allowed through"


def test_a_probe_that_succeeds_reopens_the_mirror(monkeypatch):
    from backend.app.spine import writer as writer_module
    from backend.app.spine.writer import SpineWriter

    clock = [1000.0]
    monkeypatch.setattr(writer_module.time, "monotonic", lambda: clock[0])

    fake = CountingClickHouse(fail=True)
    w = SpineWriter(clickhouse_client=fake)
    w.set_editorial_tag(production_id=PROD, target_type="shot",
                        target_id="27/7", status="mounted")

    clock[0] += writer_module.MIRROR_COOLDOWN_SECONDS + 1
    fake.fail = False   # the server came back
    w.set_editorial_tag(production_id=PROD, target_type="shot",
                        target_id="49/1", status="mounted")
    assert w._mirror_blocked_until == 0.0
    assert w.mirror_available() is True


def test_the_take_projection_is_not_computed_while_the_mirror_is_shut():
    """The walk over every event is most of the cost, not the insert."""
    from backend.app.spine.writer import SpineWriter

    fake = CountingClickHouse(fail=True)
    w = SpineWriter(clickhouse_client=fake)
    for i in range(5):
        w.append_event(_take_event("27/7", str(i), "A120"))
    w.flush_events()              # fails, shutting the mirror
    assert w.mirror_available() is False
    before = fake.attempts
    assert w.project_takes("IDX") == 0
    assert fake.attempts == before, "no attempt should have been made"


def test_events_are_not_buffered_while_the_mirror_is_shut():
    """Holding them across an outage would grow memory to protect a copy."""
    from backend.app.spine.writer import SpineWriter

    w = SpineWriter(clickhouse_client=CountingClickHouse(fail=True))
    w.append_event(_take_event("27/7", "1", "A120"))
    w.flush_events()
    for i in range(20):
        w.append_event(_take_event("49/1", str(i), "A120"))
    assert w._pending_rows == []


def test_the_spine_still_answers_with_the_mirror_shut():
    from backend.app.spine.writer import SpineWriter

    w = SpineWriter(clickhouse_client=CountingClickHouse(fail=True))
    for i in range(3):
        w.append_event(_take_event("27/7", str(i), "A120"))
    w.flush_events()
    assert len(w.get_events(production_id="IDX")) == 3
