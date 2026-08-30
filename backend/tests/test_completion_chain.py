"""
"Complete" is a chain of seven stages, not a state.

The editorial vocabulary used to stop at the third of them and call it the end:
`finished`, described as "No further work expected", when picture lock,
colour/sound/VFX, conforming and DCP all follow. A board telling a colourist a
scene is finished, when what is meant is that the editor has stopped, says
something untrue.

Recorded in references/domain/completion.md from Francisco, 2026-08-30.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.spine import tag_store

client = TestClient(app)

# Francisco's chain, in his order.
CHAIN = [
    "finished_shooting", "covered_per_script",   # the script says it is shot
    "ready_to_edit", "mounted",                  # the assistant mounted it
    "finished",                                  # the editor finished
    "picture_lock",                              # the Director settled the cut
    "colour_sound_vfx",                          # colour, sound (SFX), VFX
    "conformed",                                 # the conforming process
    "dcp",                                       # the Digital Cinema Package
]


def statuses():
    return {s["key"]: s for s in tag_store.STATUSES}


# --------------------------------------------------------------------------- #
# The chain is all there, in order
# --------------------------------------------------------------------------- #

def test_every_stage_of_the_chain_exists():
    assert [s["key"] for s in tag_store.STATUSES] == CHAIN


def test_the_ordinals_run_in_the_order_work_happens():
    """
    Ordinal is what a progress bar sorts on, so a stage in the wrong place
    would render the board in the wrong order rather than fail.
    """
    ordinals = [s["ordinal"] for s in tag_store.STATUSES]
    assert ordinals == sorted(ordinals)
    assert len(set(ordinals)) == len(ordinals), "two stages share an ordinal"


def test_editing_finished_is_no_longer_the_end():
    """
    The defect this closes. `finished` was the highest ordinal, so a progress
    bar showed a scene as complete when four stages were still to come.
    """
    by_key = statuses()
    assert by_key["finished"]["ordinal"] < by_key["dcp"]["ordinal"]
    assert max(s["ordinal"] for s in tag_store.STATUSES) == by_key["dcp"]["ordinal"]


def test_it_no_longer_claims_no_further_work():
    finished = statuses()["finished"]
    assert "No further work expected" not in finished["description"]
    assert finished["label"] == "Editing finished"
    # Says what actually follows, rather than only what it is not.
    for stage in ("picture lock", "conforming", "DCP"):
        assert stage.lower() in finished["description"].lower()


# --------------------------------------------------------------------------- #
# Nothing stored had to move
# --------------------------------------------------------------------------- #

def test_the_existing_keys_are_untouched():
    """
    Renaming would mean rewriting the status on stored tags and on
    editorial_tag_events -- and that trail is append-only, so rewriting it
    would falsify what people recorded at the time. The keys stay; only the
    label and description, which are never stored on a tag, were corrected.
    """
    for key in ("finished_shooting", "covered_per_script", "ready_to_edit",
                "mounted", "finished"):
        assert key in statuses(), f"{key} was renamed; stored tags now point at nothing"


def test_a_tag_saved_before_the_change_still_validates():
    res = client.put("/api/tags", json={
        "production_id": "CHAIN", "target_type": "scene", "target_id": "27",
        "status": "finished", "updated_by": "@editor",
    })
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "finished"


# --------------------------------------------------------------------------- #
# The new stages work end to end
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("status", ["picture_lock", "colour_sound_vfx", "conformed", "dcp"])
def test_each_new_stage_can_be_set(status):
    res = client.put("/api/tags", json={
        "production_id": "CHAIN", "target_type": "scene", "target_id": f"s_{status}",
        "status": status, "updated_by": "@post_supervisor",
    })
    assert res.status_code == 200, res.text
    assert res.json()["status"] == status


def test_picture_lock_is_a_status_on_coverage_not_a_production_milestone():
    """
    The Director decides when, and may decide it for one scene while the rest
    are still being cut. A date the whole production passes through would be
    the wrong shape.
    """
    for target in ("27", "28"):
        client.put("/api/tags", json={
            "production_id": "CHAIN_LOCK", "target_type": "scene", "target_id": target,
            "status": "picture_lock" if target == "27" else "mounted",
            "updated_by": "@director",
        })
    tags = client.get("/api/tags", params={"production_id": "CHAIN_LOCK"}).json()
    by_target = {t["target_id"]: t["status"] for t in tags}
    assert by_target["27"] == "picture_lock"
    assert by_target["28"] == "mounted"


def test_a_stage_nobody_named_is_still_refused():
    """
    The vocabulary stays closed. A board that answers "what is left" can only
    count what everyone spells the same way.
    """
    res = client.put("/api/tags", json={
        "production_id": "CHAIN", "target_type": "scene", "target_id": "99",
        "status": "nearly_done", "updated_by": "@editor",
    })
    assert res.status_code >= 400


def test_the_vocabulary_endpoint_serves_the_whole_chain():
    """
    The interface reads the vocabulary rather than hardcoding it, so this is
    what puts the new stages on the board.
    """
    served = client.get("/api/tags/vocabulary").json()
    assert [s["key"] for s in served["statuses"]] == CHAIN


def test_the_summary_counts_every_stage():
    counts = client.get("/api/tags/summary", params={"production_id": "CHAIN"}).json()
    by_status = counts.get("by_status", counts)
    for key in CHAIN:
        assert key in by_status, f"{key} is missing from the summary; the board cannot show it"
