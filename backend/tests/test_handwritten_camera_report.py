"""
Reading a handwritten camera report.

The normalisation half runs without a model, which is what these cover. The
failure mode throughout is a form convention read as a fact: a blank cell means
"the same as the row above", not "no slate", and a cell holding an annotation is
not a shot by that name.
"""
import json

import pytest

from backend.app.agents.camera_report_vision import (
    CameraReportVisionReader,
    _clean_handwritten_roll,
    _looks_like_a_slate,
)
from backend.app.parsers.classifier import classify_document, is_handwritten_form


def read(payload):
    return CameraReportVisionReader(api_key=None).normalize(json.dumps(payload))


# --------------------------------------------------------------------------- #
# The ditto convention
# --------------------------------------------------------------------------- #

DITTO_PAGE = {
    "camera": "B", "fps": 24, "iso": 800, "shutter": "172.8",
    "rows": [
        {"camera_roll": "#B004 +1", "clip_name": "009", "slate": "73A/11", "take_id": "1", "lens": "75mm"},
        {"camera_roll": "#B004 +1", "clip_name": "010", "slate": "", "take_id": "2"},
        {"camera_roll": "#B004 +1", "clip_name": "011", "slate": None, "take_id": "3"},
        {"camera_roll": "#B004 +1", "clip_name": "013", "slate": "73A/12", "take_id": "1", "lens": "75mm"},
    ],
}


def test_a_blank_slate_cell_means_the_row_above():
    """
    The assistant writes the slate once. Read literally, every take after the
    first is detached from the shot it belongs to.
    """
    records = read(DITTO_PAGE)
    assert [r.slate for r in records] == ["73A/11", "73A/11", "73A/11", "73A/12"]
    assert [r.take_id for r in records] == ["1", "2", "3", "1"]


def test_the_header_applies_to_every_row():
    records = read(DITTO_PAGE)
    assert all(r.fps == 24.0 for r in records)
    assert all(r.iso == 800 for r in records)
    assert all(r.shutter == "172.8" for r in records)


def test_rows_are_marked_as_read_from_handwriting():
    """
    A value read off handwriting is weaker evidence than a typed export, and
    anything reconciling against it should be able to tell.
    """
    assert all(r.raw_payload["source"] == "handwritten_vision" for r in read(DITTO_PAGE))


# --------------------------------------------------------------------------- #
# A cell that is not a slate
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("value, expected", [
    ("73A/14", True), ("119/5", True), ("74B", True), ("27", True),
    ("CLIP FALSO", False), ("false clip", False), ("", False), ("n/a", False),
])
def test_only_slate_shaped_cells_become_slates(value, expected):
    assert _looks_like_a_slate(value) is expected


def test_an_annotation_does_not_become_a_shot():
    """
    Observed from the live model: a false-clip note sat in the slate column.
    Taken literally it invents a shot called CLIP FALSO that matches nothing.
    """
    records = read({
        "rows": [
            {"slate": "73A/14", "take_id": "1", "camera_roll": "B004", "clip_name": "015"},
            {"slate": "CLIP FALSO", "take_id": "1", "camera_roll": "B005", "clip_name": "001"},
        ]
    })
    assert "CLIP FALSO" not in [r.slate for r in records]
    # kept as what it is: a remark carried on the row
    assert any("CLIP FALSO" in (r.note or "") for r in records)


def test_a_row_naming_neither_slate_nor_take_is_dropped():
    records = read({"rows": [{"camera_roll": "B004", "clip_name": "001"}]})
    assert records == []


# --------------------------------------------------------------------------- #
# Rolls as written by hand
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("written, expected", [
    ("#B004 +1", "B004"), ("#B001", "B001"), ("B 004", "B004"),
    ("B004 mag 2", "B004"), ("B004", "B004"),
])
def test_a_roll_survives_the_shorthand_around_it(written, expected):
    assert _clean_handwritten_roll(written) == expected


def test_leading_zeros_are_preserved_through_the_reader():
    """B039 and B39 are written differently on different documents."""
    records = read({"rows": [{"slate": "27/7", "take_id": "1", "camera_roll": "#B039"}]})
    assert records[0].camera_roll == "B039"


# --------------------------------------------------------------------------- #
# Recognising that a document needs reading rather than parsing
# --------------------------------------------------------------------------- #

HANDWRITTEN_TEXT = (
    "LA PRODUCTION\nCAMERA REPORT\nB CAM DAY 39 7/9/2026\n"
    "Camera: ALEXA 35 Resolution: 4.6K FPS: 24\n"
    "Roll Card Clip Scene /Shot Take Lens T Int. Filters Comments"
)

MACHINE_TEXT = (
    "Camera Report\nGenerated using ZoeLog\nROLLA154 DATE7 Aug 2026 CAMERA Alexa 35\n"
    "SCENE TAKE\n73A/14 Lens(40mm) StopF4 FPS24fps\n1\n74B/2 Lens(50mm) StopF2.8\n2\n"
)


def test_a_form_with_no_readable_rows_is_handwritten():
    assert is_handwritten_form(HANDWRITTEN_TEXT) is True


def test_a_report_whose_rows_can_be_read_is_not():
    assert is_handwritten_form(MACHINE_TEXT) is False


def test_a_date_is_not_mistaken_for_a_slate():
    """7/9/2026 is a date. Counting it as a row would hide a handwritten form."""
    assert is_handwritten_form(HANDWRITTEN_TEXT) is True


def test_a_delimited_export_is_never_handwritten():
    assert is_handwritten_form("Camera Report\nROLL,SCENE,TAKE\nA120,27/7,1\n") is False


def test_an_unrelated_document_is_not_claimed():
    assert is_handwritten_form("Sound Report\nfield_delim TABS\n") is False
    assert is_handwritten_form("") is False


def test_the_classifier_routes_a_handwritten_report_to_vision():
    result = classify_document(filename="B_SD39_CAM_B.pdf", content=HANDWRITTEN_TEXT)
    assert result.department.value == "camera"
    assert result.is_multimodal is True


def test_the_classifier_leaves_a_machine_report_to_the_text_parser():
    result = classify_document(filename="Production-2026-8-08_CAM_A.pdf", content=MACHINE_TEXT)
    assert result.department.value == "camera"
    assert result.is_multimodal is False
