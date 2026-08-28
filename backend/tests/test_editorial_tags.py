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
