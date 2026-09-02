"""
The router decides which model answers every AI request, and every caller turns
a model failure into a parse warning rather than an error. That combination is
why a wrong model id here is invisible: nothing breaks, the output just quietly
gets worse. These tests pin the parts that made it fail in practice.
"""
import pytest

from backend.app.script import llm_router
from backend.app.script.llm_router import (
    DEFAULT_FLASH_MODEL,
    FLASH_FALLBACK_MODELS,
    get_model_candidates,
    get_optimal_gemini_model,
)


@pytest.fixture(autouse=True)
def clean_model_env(monkeypatch):
    monkeypatch.delenv("CINESPINE_GEMINI_FLASH_MODEL", raising=False)
    monkeypatch.delenv("CINESPINE_GEMINI_PRO_MODEL", raising=False)


def test_no_candidate_is_an_id_vertex_cannot_serve():
    """
    The outage this fixes: the flash and pro defaults were pinned to a version
    that had never existed on the API, so every call 404'd into a warning.

    This once asserted the default ended in `-latest`, which was the right
    defence against a retired pin on the AI Studio endpoint. It is the wrong
    one here: this deployment runs against Vertex, which publishes no `-latest`
    alias for any Gemini model, so requiring the alias would have required an
    id that 404s. What the chain actually has to avoid is a generation that has
    left the catalogue -- 1.x, which is what it was pointed at.
    """
    for model in [DEFAULT_FLASH_MODEL, *FLASH_FALLBACK_MODELS]:
        assert "flash" in model, f"{model} is not a flash model"
        assert not model.endswith("-latest"), f"{model} does not resolve on Vertex"
        assert not model.startswith("gemini-1."), f"{model} is a retired generation"


def test_every_candidate_is_a_plausible_model_id():
    for model in [DEFAULT_FLASH_MODEL, *FLASH_FALLBACK_MODELS]:
        assert model.startswith("gemini-"), model
        assert " " not in model
        assert not model.endswith("-pro"), f"{model} is a pro model in the flash chain"


def test_simple_work_starts_on_the_primary_flash_model():
    assert get_model_candidates("a short prompt")[0] == DEFAULT_FLASH_MODEL
    assert get_optimal_gemini_model("a short prompt") == DEFAULT_FLASH_MODEL


def test_there_is_always_more_than_one_candidate():
    """
    Quota is metered per model and the newest model is the first to answer 503
    under load, so a single candidate means one bad day downgrades every
    profile the product produces.
    """
    for complexity in ("simple", "complex"):
        assert len(get_model_candidates("a prompt", complexity)) > 1


def test_candidates_are_unique_and_ordered_best_first():
    candidates = get_model_candidates("a prompt", "complex")
    assert len(candidates) == len(set(candidates)), "a repeat wastes a whole round trip"
    assert candidates[0] == DEFAULT_FLASH_MODEL


def test_pro_routing_is_off_by_default():
    """
    A free-tier key is quota'd at zero on pro models, not merely rate-limited,
    so routing complex work there fails on every request and costs ~25s per
    attempt before falling back.
    """
    assert all("pro" not in m for m in get_model_candidates("a prompt", "complex"))


def test_pro_routing_leads_when_configured(monkeypatch):
    monkeypatch.setenv("CINESPINE_GEMINI_PRO_MODEL", "gemini-pro-latest")
    candidates = get_model_candidates("a prompt", "complex")
    assert candidates[0] == "gemini-2.5-pro"
    # and still degrades to flash rather than giving up
    assert DEFAULT_FLASH_MODEL in candidates


def test_a_configured_pro_model_is_never_duplicated(monkeypatch):
    monkeypatch.setenv("CINESPINE_GEMINI_PRO_MODEL", DEFAULT_FLASH_MODEL)
    candidates = get_model_candidates("a prompt", "complex")
    assert len(candidates) == len(set(candidates))


def test_flash_override_is_honoured_and_leads(monkeypatch):
    monkeypatch.setenv("CINESPINE_GEMINI_FLASH_MODEL", "gemini-3.5-flash")
    candidates = get_model_candidates("a prompt")
    assert candidates[0] == "gemini-3.5-flash"
    assert len(candidates) == len(set(candidates))


def test_a_very_large_context_stays_on_flash(monkeypatch):
    monkeypatch.setenv("CINESPINE_GEMINI_PRO_MODEL", "gemini-pro-latest")
    huge = "x" * (llm_router.LARGE_CONTEXT_TOKENS * llm_router.CHARS_PER_TOKEN + 1000)
    assert all("pro" not in m for m in get_model_candidates(huge, "complex"))


def test_an_empty_prompt_still_yields_candidates():
    assert get_model_candidates("") == get_model_candidates("", "simple")
    assert len(get_model_candidates("")) > 1


# --------------------------------------------------------------------------- #
# The fallback loop in character_ai, which is what turns the chain into a fix
# --------------------------------------------------------------------------- #

def _stub_client(monkeypatch, behaviour):
    """Installs a genai.Client whose generate_content follows `behaviour(model)`."""
    calls = []

    class _Models:
        def generate_content(self, model, contents, config):
            calls.append(model)
            outcome = behaviour(model)
            if isinstance(outcome, Exception):
                raise outcome
            return type("R", (), {"text": outcome, "usage_metadata": None})()

    class _Client:
        def __init__(self, **kwargs):
            self.models = _Models()

    import google.genai as genai
    monkeypatch.setattr(genai, "Client", _Client)
    return calls


def test_a_quota_error_moves_to_the_next_model(monkeypatch):
    """The real failure: the first model is quota'd, an older one still works."""
    from backend.app.script import character_ai

    monkeypatch.delenv("CINESPINE_DISABLE_AI_CHARACTER_INFERENCE", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(character_ai, "TRANSIENT_BACKOFF_SECONDS", 0)

    def behaviour(model):
        if model == DEFAULT_FLASH_MODEL:
            raise RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded")
        return '{"ok": true}'

    calls = _stub_client(monkeypatch, behaviour)
    assert character_ai._call_gemini("a prompt") == '{"ok": true}'
    assert calls[0] == DEFAULT_FLASH_MODEL
    assert len(calls) >= 2, "a quota failure must fall through, not give up"


def test_a_transient_error_retries_the_same_model_first(monkeypatch):
    from backend.app.script import character_ai

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(character_ai, "TRANSIENT_BACKOFF_SECONDS", 0)

    state = {"n": 0}

    def behaviour(model):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("503 UNAVAILABLE high demand")
        return '{"ok": true}'

    calls = _stub_client(monkeypatch, behaviour)
    assert character_ai._call_gemini("a prompt") == '{"ok": true}'
    assert calls[:2] == [DEFAULT_FLASH_MODEL, DEFAULT_FLASH_MODEL]


def test_every_model_failing_raises_rather_than_returning_nothing(monkeypatch):
    """
    The caller converts an exception into an honest parse warning. Returning ""
    instead would look like a successful inference that found nothing to say.
    """
    from backend.app.script import character_ai

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(character_ai, "TRANSIENT_BACKOFF_SECONDS", 0)
    _stub_client(monkeypatch, lambda m: RuntimeError("429 RESOURCE_EXHAUSTED"))

    with pytest.raises(RuntimeError, match="No Gemini model available"):
        character_ai._call_gemini("a prompt")
