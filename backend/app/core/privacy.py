"""
What may be served, and what must not.

A parsed fact is a slate, a roll, a timecode. A source document is the page
those were read off, and it carries what the parsers were written to leave
behind: a script supervisor's phone number and email in the footer, crew and
cast names, locations, and unreleased plot. `failure-modes.md` names the
mistake this file exists to prevent -- "raw material treated as a derived
fact": parsers are written to leave that behind, and serving the file serves
all of it.

# Gate, do not scrub

The instinct is to redact PII out of the text and serve it anyway. On
production paperwork that is actively dangerous, and this project already has
the proof. The scrubber that was here before this file matched a phone-shaped
run of digits, so:

    'A120 280726 2:46'    ->  'A[REDACTED_PHONE] 2:46'
    'Sound Cards: 280726' ->  'Sound Cards: [REDACTED_PHONE]'

A camera card and its shoot date read as a phone number. That is the "helpful
correction" failure mode: the repair is invisible and the original is
destroyed. Production paperwork is made of number strings that look like
phone numbers, so a broad pattern cannot be safe here.

So the control is the gate. Serving source documents is off unless the
operator turns it on. Redaction below is defence in depth on top of that, and
is deliberately narrow: an email address cannot be confused with a camera
roll, and a phone number is only redacted where the document says it is one.

# What is not gated

The parsed facts. Takes, slates, rolls, timecodes and cards are derived, carry
no contact details, and are the product. Gating those would gate the app.
"""
import os
import re
from typing import Any, Dict

# Turning this on is a deliberate act by whoever deployed it, and it should be
# off wherever the paperwork is real. Absent means off.
SERVE_FLAG = "CINESPINE_SERVE_SOURCE_DOCUMENTS"

_TRUE = {"1", "true", "yes", "on"}

# An email address. Precise enough to be safe on production paperwork: no
# camera roll, timecode, checksum or card range contains an @ between two
# labelled parts.
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# A phone number, only where the document says it is one. Either an explicit
# international prefix, or a label in English or Spanish -- these documents are
# bilingual -- immediately before the digits.
#
# Deliberately narrow. The alternative is matching bare digit runs, which is
# what turned 'A120 280726' into a redacted phone number.
_PHONE_LABELLED = re.compile(
    r"(?i)\b(tel|tlf|phone|mobile|m[oó]vil|movil|cel|celular|whatsapp)\b\s*[:.]?\s*[+()\d][\d\s().-]{6,}"
)
_PHONE_INTERNATIONAL = re.compile(r"\+\d{1,3}[\s.-]?(?:\(?\d{2,4}\)?[\s.-]?){2,}\d{2,4}")

EMAIL_PLACEHOLDER = "[email removed]"
PHONE_PLACEHOLDER = "[phone removed]"


def may_serve_source_documents() -> bool:
    """
    Whether the material itself may be served over the API.

    Off unless explicitly enabled. The demo runs against synthetic fixtures,
    which are exempt below, so the default costs nothing there and refuses
    everywhere the paperwork is real.
    """
    return os.environ.get(SERVE_FLAG, "").strip().lower() in _TRUE


def is_synthetic(document: Dict[str, Any]) -> bool:
    """
    Whether this document is one of the embedded demo fixtures.

    Marked at the point it is stored, not guessed from its name. Seeding from
    a local examples directory reads real production paperwork, so "it came
    from the seed endpoint" is not the same question and would answer wrong.
    """
    return bool((document.get("metadata") or {}).get("synthetic"))


def may_serve(document: Dict[str, Any]) -> bool:
    return is_synthetic(document) or may_serve_source_documents()


def refusal_detail(document: Dict[str, Any]) -> str:
    """Why it was refused, and what to do about it, in one sentence."""
    return (
        f"Source documents are not served by default: {document.get('filename') or 'this file'} "
        "is production paperwork, which carries crew contact details, cast names and "
        f"unreleased material. Set {SERVE_FLAG}=1 to serve it, having decided that is safe "
        "for this deployment. The parsed facts remain available."
    )


def redact(text: str) -> str:
    """
    Removes contact details from document text, and nothing else.

    Narrow on purpose: only an email, or a number the document itself labels as
    a phone. Everything that makes production paperwork useful -- rolls, cards,
    dates, timecodes, checksums, slate ranges -- is left exactly as written,
    because a silent repair destroys the disagreement the whole product exists
    to find.
    """
    if not text:
        return text

    cleaned = _EMAIL.sub(EMAIL_PLACEHOLDER, text)
    cleaned = _PHONE_LABELLED.sub(
        lambda m: f"{m.group(1)}: {PHONE_PLACEHOLDER}", cleaned
    )
    cleaned = _PHONE_INTERNATIONAL.sub(PHONE_PLACEHOLDER, cleaned)
    return cleaned
