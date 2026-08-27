"""
Chooses which Gemini model answers a given prompt.

Model ids churn. Pinning a specific version means the day it is retired every
AI feature starts returning 404, and because each caller degrades gracefully the
only visible symptom is that the answers quietly get worse. So the defaults here
are the floating `-latest` aliases, and callers are given an ordered list of
candidates rather than a single name.
"""
import os
from typing import List

# A floating alias rather than a pinned version: it follows the current model
# and cannot 404 when a version is retired. Override per deployment if a
# specific version is required.
DEFAULT_FLASH_MODEL = "gemini-flash-latest"

# Older flash models, tried in turn when the newest is not usable. Two separate
# reasons make this worth more than a retry against a single model:
#
#   * quota is metered per model, so a key exhausted on one still has budget on
#     another;
#   * the newest model carries the most traffic and is the first to answer 503
#     "high demand", while the previous generation stays available.
#
# Ordered newest first, since capability degrades gently and availability
# improves as you go down the list.
FLASH_FALLBACK_MODELS = (
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
)

# Pro routing is opt-in, and deliberately off by default. A free-tier key is
# not merely rate-limited on pro models, it is quota'd at zero, so routing
# complex work there fails on every request and costs ~25s per attempt before
# falling back. Set CINESPINE_GEMINI_PRO_MODEL on a billed project to enable it.
DEFAULT_PRO_MODEL = ""

# Beyond roughly this size, Flash is the better answer regardless of complexity:
# it handles very large contexts cheaply without degrading much.
LARGE_CONTEXT_TOKENS = 100_000

# Rough estimation: 4 characters is about 1 token.
CHARS_PER_TOKEN = 4


def _flash_model() -> str:
    return os.environ.get("CINESPINE_GEMINI_FLASH_MODEL", DEFAULT_FLASH_MODEL)


def _pro_model() -> str:
    return os.environ.get("CINESPINE_GEMINI_PRO_MODEL", DEFAULT_PRO_MODEL)


def estimated_tokens(prompt_text: str) -> int:
    return len(prompt_text) // CHARS_PER_TOKEN


def get_optimal_gemini_model(prompt_text: str, task_complexity: str = "simple") -> str:
    """
    The single best model for this prompt.

    Prefer `get_model_candidates` where the caller can retry: this returns only
    the first choice, and a first choice can be unavailable.
    """
    return get_model_candidates(prompt_text, task_complexity)[0]


def _flash_chain() -> List[str]:
    """The flash model, then the older ones, without repeats."""
    chain = [_flash_model()]
    for model in FLASH_FALLBACK_MODELS:
        if model not in chain:
            chain.append(model)
    return chain


def get_model_candidates(prompt_text: str, task_complexity: str = "simple") -> List[str]:
    """
    Models to try in order, best first, ending in ones that are cheap and
    widely available.

    The fallback is not theoretical. A model is routinely unusable for reasons
    that have nothing to do with the request -- retired, quota'd at zero for
    this key's tier, or answering 503 under load -- and each caller turns a
    failure into a parse warning rather than an error. With a single candidate
    that means the feature silently produces worse output instead of failing.
    """
    chain = _flash_chain()

    if estimated_tokens(prompt_text) > LARGE_CONTEXT_TOKENS:
        return chain

    if task_complexity == "complex":
        pro = _pro_model().strip()
        if pro and pro not in chain:
            return [pro, *chain]

    return chain
