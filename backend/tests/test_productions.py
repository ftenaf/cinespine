"""
The production registry.

A production is the key everything else is filed under -- events, editorial
tags, the linked screenplay -- so the two things that matter here are that it
outlives the process, and that its id never moves once work is hanging off it.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.spine import production_store
from backend.app.spine.production_store import UnknownProductionField

client = TestClient(app)

PROD = "NIGHT_WATCH"


@pytest.fixture(autouse=True)
def _clean_slate():
    """conftest already points CINESPINE_DB_PATH at a temporary file."""
    yield
    production_store.delete(PROD)


def create(**over):
    payload = {"production_id": PROD, "name": "Night Watch", **over}
    return client.post("/api/productions", json=payload)


# --------------------------------------------------------------------------- #
# Registering
# --------------------------------------------------------------------------- #

def test_a_registered_production_is_stored_not_just_remembered():
    """
    The registry used to live in the writer's memory. Registering a production,
    restarting, and finding it gone is not a registry -- and its tags and
    script link, which are stored, would have outlived it.
    """
    create()
    assert production_store.get(PROD)["name"] == "Night Watch"


def test_a_registered_production_appears_in_the_list():
    create()
    listed = client.get("/api/productions").json()
    assert PROD in [p["production_id"] for p in listed]


def test_a_new_production_starts_empty_rather_than_absent():
    """An empty production is a real state: registered, nothing shot yet."""
    create()
    row = next(p for p in client.get("/api/productions").json() if p["production_id"] == PROD)
    assert (row["total_events"], row["total_takes"], row["shoot_days"]) == (0, 0, [])


@pytest.mark.parametrize("written", ["night_watch", " Night Watch ", "NIGHT WATCH"])
def test_the_same_production_spelled_differently_is_one_production(written):
    """
    The id is typed by hand in one place and read out of a filename in another.
    Two spellings landing on two rows would split a production's work in half.
    """
    create()
    assert production_store.get(written)["production_id"] == PROD


def test_a_production_is_marked_as_registered_by_a_person():
    create()
    assert production_store.get(PROD)["origin"] == "registered"


def test_the_built_in_demos_are_there_without_being_registered():
    listed = [p["production_id"] for p in client.get("/api/productions").json()]
    assert "DEMO_PRODUCTION" in listed


# --------------------------------------------------------------------------- #
# Seen during an ingest
# --------------------------------------------------------------------------- #

def test_a_production_first_seen_in_a_filename_is_marked_as_a_guess():
    """
    An id read off a filename is a guess about what a document belongs to. A
    typo should be recognisable as one rather than sitting in the list looking
    deliberate.
    """
    production_store.register_if_absent(PROD)
    assert production_store.get(PROD)["origin"] == "auto"


def test_a_later_ingest_does_not_overwrite_what_somebody_typed():
    create(director="Director", description="Second unit, winter block")
    production_store.register_if_absent(PROD)
    stored = production_store.get(PROD)
    assert stored["description"] == "Second unit, winter block"
    assert stored["origin"] == "registered"


def test_registering_a_production_that_was_guessed_makes_it_deliberate():
    production_store.register_if_absent(PROD)
    create(name="Night Watch")
    assert production_store.get(PROD)["origin"] == "registered"


# --------------------------------------------------------------------------- #
# Editing
# --------------------------------------------------------------------------- #

def test_a_production_can_be_renamed():
    create()
    res = client.patch(f"/api/productions/{PROD}", json={"name": "Night Watch (2026)"})
    assert res.status_code == 200
    assert res.json()["name"] == "Night Watch (2026)"


def test_an_edit_leaves_the_fields_it_did_not_mention_alone():
    create(director="Director", description="Winter block")
    client.patch(f"/api/productions/{PROD}", json={"status": "Wrapped"})
    stored = production_store.get(PROD)
    assert (stored["director"], stored["description"]) == ("Director", "Winter block")


def test_a_status_outside_the_vocabulary_is_refused():
    """Free text would make the list unsortable and one state spelled three ways."""
    create()
    res = client.patch(f"/api/productions/{PROD}", json={"status": "kind of done"})
    assert res.status_code == 422


def test_the_status_vocabulary_is_published_so_the_ui_offers_exactly_these():
    statuses = client.get("/api/productions/vocabulary").json()["statuses"]
    assert "Wrapped" in statuses and "Active" in statuses


def test_a_production_id_cannot_be_edited():
    """
    Every event, tag and script link is filed under the id. Moving it would
    orphan all of them while looking like a rename.
    """
    create()
    with pytest.raises(UnknownProductionField):
        production_store.update(PROD, {"production_id": "SOMETHING_ELSE"})


def test_editing_a_production_that_does_not_exist_is_a_404():
    assert client.patch("/api/productions/NOBODY", json={"name": "x"}).status_code == 404


# --------------------------------------------------------------------------- #
# Deleting
# --------------------------------------------------------------------------- #

def test_an_empty_production_can_be_deleted():
    create()
    assert client.delete(f"/api/productions/{PROD}").status_code == 200
    assert production_store.get(PROD) is None


def test_a_production_holding_work_is_not_deleted():
    """
    Deleting it here would not delete its events or tags -- it would hide them,
    leaving work nobody can reach.
    """
    create()
    client.put("/api/tags", json={
        "production_id": PROD, "target_type": "scene", "target_id": "27", "status": "mounted",
    })
    res = client.delete(f"/api/productions/{PROD}")
    assert res.status_code == 409
    assert "editorial tag" in res.json()["detail"]
    assert production_store.get(PROD) is not None


def test_the_refusal_names_what_is_holding_the_production():
    from backend.app.api.routes import spine_writer

    create()
    spine_writer.append_event({
        "event_id": "evt-nw-1", "production_id": PROD, "shoot_day": "1",
        "axis": "belief", "department": "script", "doc_type": "scripte_tclog",
        "entity_type": "take", "payload": {"slate": "1/1", "take_id": "1"},
        "metadata": {}, "timestamp": "2026-07-28T10:00:00Z",
    })
    detail = client.delete(f"/api/productions/{PROD}").json()["detail"]
    assert "1 event" in detail


def test_deleting_a_production_that_does_not_exist_is_a_404():
    assert client.delete("/api/productions/NOBODY").status_code == 404


def test_a_built_in_demo_named_on_an_event_is_not_marked_as_a_guess():
    """
    An ingest naming DEMO_PRODUCTION is not guessing at what the production is
    -- that id is known. Marking it auto put a warning on the demo saying
    nobody had registered it.
    """
    from backend.app.api.routes import spine_writer

    spine_writer.append_event({
        "event_id": "evt-demo-origin", "production_id": "DEMO_PRODUCTION", "shoot_day": "31",
        "axis": "belief", "department": "script", "doc_type": "scripte_tclog",
        "entity_type": "take", "payload": {"slate": "27/7", "take_id": "1"},
        "metadata": {}, "timestamp": "2026-07-28T10:00:00Z",
    })
    stored = production_store.get("DEMO_PRODUCTION")
    assert stored["origin"] == "registered"
    assert stored["name"] == "Demo Production"


def test_an_unknown_id_on_an_event_is_still_recorded_as_a_guess():
    from backend.app.api.routes import spine_writer

    spine_writer.append_event({
        "event_id": "evt-nw-origin", "production_id": PROD, "shoot_day": "1",
        "axis": "belief", "department": "script", "doc_type": "scripte_tclog",
        "entity_type": "take", "payload": {"slate": "1/1", "take_id": "1"},
        "metadata": {}, "timestamp": "2026-07-28T10:00:00Z",
    })
    assert production_store.get(PROD)["origin"] == "auto"
