"""
No parser turns somebody's contact details into a production fact.

This defect was found three times in one day, wearing a different field each
time, and each time only because somebody looked:

  * `camera_csv` — a footer became a slate, reached the spine and the
    analytical mirror, and came back as the scene an analytics result was
    grouped under.
  * `sound_ale` — the same thing in the sound report, still live after the
    first fix because only the parser that failed had been checked.
  * `silverstack_thumbnail` — blocks split on lines beginning "Name ", so a
    contact block written that way became an entire clip. A slate-shaped guard
    would not have caught it: the address landed in `file_name`.
  * `scripte_tclog` — every unrecognised line is appended to the previous
    take's note, so a footer became something the script supervisor supposedly
    wrote about that take.

So this file sweeps all of them at once rather than testing each fix in place.
A parser added later that skips the guard fails here, which is the only way a
fourth instance does not happen the same way as the first three.

The mirror is hosted, so anything that reaches a parsed fact leaves the machine.
"""
import pytest

from backend.app.core.privacy import is_contact_information
from backend.app.parsers.base import ParserFailureError, looks_like_a_clip_name
from backend.app.parsers.camera_csv import parse_camera_csv
from backend.app.parsers.pdf_parsers import (
    parse_scripte_tclog_text,
    parse_silverstack_clips_text,
    parse_silverstack_thumbnail_text,
    parse_silverstack_volume_text,
    parse_zoelog_camera_text,
)
from backend.app.parsers.silverstack_xml import parse_silverstack_xml
from backend.app.parsers.sound_ale import parse_sound_ale

CONTACT = "Contact: supervisor@example.com Tel: 600 123 456"

# Every field a parsed record can carry that reaches the spine.
FIELDS = (
    "slate", "scene", "shot", "clip_name", "file_name", "camera_roll",
    "sound_roll", "take_id", "reel_tape", "note", "volume_name", "checksum",
)

DOCUMENTS = {
    "camera_csv": (parse_camera_csv,
        "Slate,Take,CameraRoll,ClipName,FPS,ISO,Lens,Scene,Description\n"
        "27/7,1,A120,A120_C001.MOV,24,800,50mm,27,Organ\n"
        f"{CONTACT},,,,,,,,\n"),
    "sound_ale": (parse_sound_ale,
        "Heading\nFIELD_DELIM\tTABS\n\nColumn\n"
        "Name\tScene\tTake\tSound Roll\tStart\tEnd\n\nData\n"
        "27_7T01\t27/7\t1\tSR01\t09:26:12:04\t09:28:58:12\n"
        f"{CONTACT}\t{CONTACT}\t1\tSR01\t09:30:00:00\t09:32:00:00\n"),
    "zoelog_camera": (parse_zoelog_camera_text,
        "ZOELOG CAMERA REPORT\n"
        "SCENE 27/7 TAKE 1 ROLL A120 CLIP A120_C001 24fps 800 ISO\n"
        f"{CONTACT}\n"),
    "scripte_tclog": (parse_scripte_tclog_text,
        "27/7 1 09:26:12:04 09:28:58:12\nA120 280726 2:46\n"
        f"{CONTACT}\n"),
    "silverstack_thumbnail": (parse_silverstack_thumbnail_text,
        "Pomfort Silverstack Thumbnail Report\n\n"
        "Name A120_C001.MOV\nReel/Tape A_0120\nScene 27\nShot 27/7\nTake 1\nCamera A\n\n"
        f"Name {CONTACT}\nReel/Tape {CONTACT}\nScene {CONTACT}\nShot {CONTACT}\nTake 1\nCamera A\n"),
    "silverstack_volume": (parse_silverstack_volume_text,
        "Volume Report 28/7/26\nPomfort Silverstack XT\n664 SD\n"
        f"27-7T01.WAV\nXXH64:abc 1 MB\n{CONTACT}\nXXH64:def 1 MB\n"),
    "silverstack_clips": (parse_silverstack_clips_text,
        "Clips Report 28/7/26\nPomfort Silverstack XT 1/10\n"
        f"27-7T01 Sound Dev: Mix664 3:00 min\n{CONTACT}\n"),
    "silverstack_xml": (parse_silverstack_xml,
        '<?xml version="1.0"?><clips>'
        '<clip><name>A120_C001.MOV</name><scene>27</scene><shot>27/7</shot><take>1</take></clip>'
        f'<clip><name>{CONTACT}</name><scene>{CONTACT}</scene>'
        f'<shot>{CONTACT}</shot><take>1</take></clip></clips>'),
}


def contact_in(records):
    return [
        (getattr(r, "__class__").__name__, field, str(getattr(r, field))[:60])
        for r in records for field in FIELDS
        if getattr(r, field, None) and is_contact_information(str(getattr(r, field)))
    ]


# --------------------------------------------------------------------------- #
# The sweep
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", sorted(DOCUMENTS))
def test_no_parser_turns_contact_details_into_a_fact(name):
    """
    The whole point. A document carrying a contact block must produce no record
    with those details in any field that reaches the spine.
    """
    parser, text = DOCUMENTS[name]
    try:
        records = parser(text)
    except ParserFailureError:
        # Refusing the document outright is a fine answer: nothing reached the
        # spine. What must never happen is accepting it and keeping the line.
        return

    leaked = contact_in(records)
    assert not leaked, f"{name} carried contact details into {leaked}"


@pytest.mark.parametrize("name", sorted(DOCUMENTS))
def test_the_real_row_beside_it_still_parses(name):
    """
    The negative that keeps the guards honest. Every document above has one
    genuine take in it, and a guard that threw the good row away with the bad
    would pass the test above while making the parser useless.
    """
    parser, text = DOCUMENTS[name]
    try:
        records = parser(text)
    except ParserFailureError:
        pytest.skip(f"{name} refuses this document shape entirely")

    assert records, f"{name} kept nothing at all"
    joined = " ".join(
        str(getattr(r, f, "")) for r in records for f in FIELDS if getattr(r, f, None)
    )
    assert "27" in joined, f"{name} dropped the genuine take along with the junk"


# --------------------------------------------------------------------------- #
# The shape guards themselves
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", [
    "A120_C001_260728.MOV", "B039_C001.MOV", "27-7T01.WAV", "49WTT01.WAV",
    "+99BDF-9T01.WAV", "71C-3T02.WAV", "A_0120C001_260728_091309_h1EIC",
])
def test_a_real_clip_name_is_one(name):
    assert looks_like_a_clip_name(name) is True


@pytest.mark.parametrize("line", [
    CONTACT, "TOTAL", "Camera Report Day 31", "DEMO PRODUCTION",
    "Notes: LEAD plays organ", "", None,
])
def test_prose_is_not_a_clip_name(line):
    assert looks_like_a_clip_name(line) is False


def test_a_footer_word_is_refused_even_though_it_has_no_spaces():
    """
    `TOTAL` matches the character shape of a filename. Every real clip name
    carries a number -- a roll, a clip index, a take -- and that is what
    separates the two.
    """
    assert looks_like_a_clip_name("TOTAL") is False
    assert looks_like_a_clip_name("A120") is True


# --------------------------------------------------------------------------- #
# Notes are refused, never rewritten
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text", [
    "Contact: supervisor@example.com",
    "Tel: 600 123 456",
    "+34 600 123 456",
])
def test_contact_information_is_recognised(text):
    assert is_contact_information(text) is True


@pytest.mark.parametrize("text", [
    "LEAD plays the organ, take is soft on the ending",
    "A120 280726 2:46",
    "Slates: 27/7 - 8, 49/1 - 9",
    "Lens: 50mm T2.8",
    "",
])
def test_a_real_note_is_not_contact_information(text):
    """
    The cost of getting this wrong is a script supervisor's note being thrown
    away. `A120 280726 2:46` is a roll, a date and a duration -- it has been
    mistaken for a phone number before, by a scrubber that was removed for it.
    """
    assert is_contact_information(text) is False


def test_a_note_is_refused_rather_than_rewritten():
    """
    Not redaction. Rewriting a note quietly alters what somebody said -- the
    failure this project calls the helpful correction. Declining to attribute a
    line that is plainly not about this take leaves the note as written.
    """
    records = parse_scripte_tclog_text(
        "27/7 1 09:26:12:04 09:28:58:12\n"
        "A120 280726 2:46\n"
        "Organ is flat on the second phrase\n"
        f"{CONTACT}\n"
    )
    assert records
    note = records[0].note or ""
    assert "Organ is flat on the second phrase" in note
    assert "supervisor@example.com" not in note
    assert "[REDACTED" not in note, "the note was rewritten rather than left alone"
