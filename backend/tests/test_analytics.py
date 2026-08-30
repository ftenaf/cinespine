"""
Product analytics, and what must never leave with them.

This app renders unreleased footage, crew names, and source documents carrying
phone numbers and email addresses. So the tests that matter here are not that
events are sent -- they are about what is refused, and about the app not
depending on the endpoint being up.
"""
import pytest

from backend.app.core import analytics


@pytest.fixture(autouse=True)
def _unconfigured(monkeypatch):
    """Every test starts from the default state: nothing configured."""
    monkeypatch.delenv("POSTHOG_API_KEY", raising=False)
    monkeypatch.delenv("POSTHOG_HOST", raising=False)
    analytics.reset()
    yield
    analytics.reset()


class FakePosthog:
    """Records what would have been sent."""

    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    def capture(self, distinct_id, event, properties):
        if self.fail:
            raise ConnectionError("posthog is down")
        self.sent.append((distinct_id, event, properties))


@pytest.fixture
def sent(monkeypatch):
    """A configured analytics client whose sends are captured, not posted."""
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_test")
    monkeypatch.setenv("POSTHOG_HOST", "http://localhost:8000")
    analytics.reset()
    fake = FakePosthog()
    monkeypatch.setattr(analytics, "_client", fake)
    monkeypatch.setattr(analytics, "_started", True)
    return fake


# --------------------------------------------------------------------------- #
# Off by default, and never required
# --------------------------------------------------------------------------- #

def test_nothing_is_sent_when_nothing_is_configured():
    assert analytics.is_configured() is False
    assert analytics.capture("@ana", "requirement_raised", {"priority": "high"}) is False


def test_a_key_without_a_host_is_not_configured(monkeypatch):
    """
    Both, or neither. A key alone would default to PostHog's cloud, and this
    product's telemetry must not leave the machine it is deployed on.
    """
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_test")
    analytics.reset()
    assert analytics.is_configured() is False


def test_a_host_without_a_key_is_not_configured(monkeypatch):
    monkeypatch.setenv("POSTHOG_HOST", "http://localhost:8000")
    analytics.reset()
    assert analytics.is_configured() is False


def test_an_endpoint_that_is_down_does_not_raise(monkeypatch, sent):
    """
    An editor's save must not fail because a telemetry endpoint is unreachable.
    """
    monkeypatch.setattr(analytics, "_client", FakePosthog(fail=True))
    assert analytics.capture("@ana", "requirement_raised", {}) is False


def test_a_configured_client_does_send(sent):
    assert analytics.capture("@ana", "requirement_raised", {"priority": "high"}) is True
    handle, event, props = sent.sent[0]
    assert (handle, event, props) == ("@ana", "requirement_raised", {"priority": "high"})


# --------------------------------------------------------------------------- #
# What must never leave
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("field", [
    "title", "description", "note", "resolution_note",
    "filename", "file_name", "content", "raw_content",
    "name", "email", "phone", "target_label", "prompt",
])
def test_a_property_carrying_content_is_dropped(field, sent):
    """
    A note is whatever somebody typed. A filename carries the production's
    name. Neither is a fact about usage.
    """
    analytics.capture("@ana", "requirement_raised", {field: "something real", "priority": "high"})
    _, _, props = sent.sent[0]
    assert field not in props
    assert props["priority"] == "high"


def test_the_blocklist_does_not_depend_on_capitalisation(sent):
    analytics.capture("@ana", "e", {"Title": "x", "FILENAME": "y", "shoot_day": "31"})
    _, _, props = sent.sent[0]
    assert list(props) == ["shoot_day"]


def test_a_long_string_is_dropped_even_if_it_was_not_named():
    """
    The blocklist cannot anticipate every name. Ids and enumerations are short;
    anything long is prose that called itself something else.
    """
    props = analytics.safe_properties({"summary": "x" * 200, "slate": "27/7"})
    assert props == {"slate": "27/7"}


def test_ids_counts_and_flags_do_go(sent):
    analytics.capture("@ana", "requirement_moved", {
        "production_id": "DEMO", "shoot_day": "31", "target_id": "27/7",
        "priority": "critical", "handed_over": True, "hours_owed": 4.5,
    })
    _, _, props = sent.sent[0]
    assert props == {
        "production_id": "DEMO", "shoot_day": "31", "target_id": "27/7",
        "priority": "critical", "handed_over": True, "hours_owed": 4.5,
    }


def test_a_missing_value_is_left_out_rather_than_sent_as_null():
    assert analytics.safe_properties({"assigned_to": None, "slate": "27/7"}) == {"slate": "27/7"}


def test_an_object_is_dropped_rather_than_stringified():
    """Stringifying a payload is how content leaks: it arrives as one long value."""
    assert analytics.safe_properties({"witnesses": [{"note": "x"}], "slate": "27/7"}) == {"slate": "27/7"}


def test_an_unnamed_actor_does_not_become_an_empty_identity(sent):
    analytics.capture(None, "document_ingested", {})
    assert sent.sent[0][0] == "@unknown"


# --------------------------------------------------------------------------- #
# Through the API
# --------------------------------------------------------------------------- #

def test_raising_a_requirement_sends_its_shape_and_not_its_words(sent):
    from fastapi.testclient import TestClient
    from backend.app.main import app

    client = TestClient(app)
    res = client.post("/api/requirements", json={
        "production_id": "ANALYTICS", "shoot_day": "31", "target_type": "shot",
        "target_id": "27/7", "target_label": "Slate 27/7",
        "title": "Room tone missing for the nave",
        "description": "No wild track was recorded.",
        "priority": "high", "category": "sound",
        "created_by": "@director", "assigned_to": "@sound_supervisor",
    })
    assert res.status_code == 200

    raised = [e for e in sent.sent if e[1] == "requirement_raised"]
    assert raised, "no requirement_raised event was sent"
    _, _, props = raised[0]
    assert props["category"] == "sound"
    assert props["target_id"] == "27/7"
    assert "title" not in props and "description" not in props and "target_label" not in props
