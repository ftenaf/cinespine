"""
Silverstack states the slate twice, and the parsers read it three times over.

A thumbnail report writes:

    Scene 27
    Shot 27/7

`Shot` is already the whole slate, not the shot half of one. All three
Silverstack parsers built `f"{scene}/{shot}"` anyway, giving `27/27/7`, which
normalised to `27/27` -- a slate nobody wrote. Every clip on the day reached
the spine under it, so DIT disagreed with camera about every take while the
board showed no conflict at all, because the two never met on a common key.

Found by the slate-range check: `27/27` was outside the range Office stated for
scene 27, which is exactly the sort of thing that check exists to notice.
"""
import pytest

from backend.app.parsers.pdf_parsers import (
    parse_silverstack_clips_text,
    parse_silverstack_thumbnail_text,
    parse_silverstack_volume_text,
)

THUMBNAIL = """Pomfort Silverstack Thumbnail Report
Production: DEMO PRODUCTION
260728_SD31

Name A120_C001_260728.MOV
Reel/Tape A_0120_1EIC
Scene {scene}
Shot {shot}
Take 1
Duration 00:02:46:00
Camera A
Sensor FPS 24.0
EI/ISO (clip) 800
"""


def thumbnail(scene, shot):
    return parse_silverstack_thumbnail_text(THUMBNAIL.format(scene=scene, shot=shot))


# --------------------------------------------------------------------------- #
# The slate stated whole
# --------------------------------------------------------------------------- #

def test_a_shot_that_is_already_a_slate_is_not_prefixed_again():
    """The defect. `Scene 27` + `Shot 27/7` must be 27/7, never 27/27."""
    clip = thumbnail("27", "27/7")[0]
    assert (clip.scene, clip.shot) == ("27", "7")


def test_it_agrees_with_what_camera_filed():
    """
    The point of the fix. Camera files A120_C001_260728 under 27/7; DIT filed
    the same clip under 27/27, so the two witnesses could never be compared.
    """
    clip = thumbnail("27", "27/7")[0]
    assert f"{clip.scene}/{clip.shot}" == "27/7"


@pytest.mark.parametrize("shot", ["27/7", "27-7"])
def test_any_separator_marks_a_whole_slate(shot):
    clip = thumbnail("27", shot)[0]
    assert (clip.scene, clip.shot) == ("27", "7")


# --------------------------------------------------------------------------- #
# The slate stated in halves, which also happens
# --------------------------------------------------------------------------- #

def test_a_bare_shot_number_still_gets_its_scene():
    """
    Both shapes occur in real reports, so this cannot simply trust the Shot
    field: `Scene 49` + `Shot 9` is 49/9 and needs the scene in front.
    """
    clip = thumbnail("49", "9")[0]
    assert (clip.scene, clip.shot) == ("49", "9")


def test_a_letter_suffix_survives():
    clip = thumbnail("64A", "1")[0]
    assert (clip.scene, clip.shot) == ("64A", "1")


def test_a_wild_track_keeps_its_marker():
    clip = thumbnail("49", "49/WT")[0]
    assert clip.scene == "49"
    assert "WT" in str(clip.shot).upper()


# --------------------------------------------------------------------------- #
# The other two parsers had the same line, and must not have moved
# --------------------------------------------------------------------------- #

def test_the_volume_report_still_reads_its_slates():
    """
    The same line appeared in all three Silverstack parsers and all three were
    changed. These two take scene and shot from a filename rather than from
    `Scene`/`Shot` lines, so the shot half is always bare and the new branch
    should never fire -- this is what proves it did not.
    """
    clips = parse_silverstack_volume_text("""
Volume Report 28/7/26, 19:27
Pomfort Silverstack XT
664 SD
26Y06M18 5.29 GB
+99BDF-9T01.WAV
XXH64:202ab43613939de5 133.93 MB
71C-3T02.WAV
XXH64:b90cf1a98bb7db8e 59.62 MB
""")
    assert clips
    assert {f"{c.scene}/{c.shot}" for c in clips} == {"+99BDF/9", "71C/3"}


def test_the_clips_report_still_reads_its_slates():
    clips = parse_silverstack_clips_text("""
Clips Report 28/7/26, 19:27
Pomfort Silverstack XT 1/10
27-7T01 Sound Dev: Mix664 S#KA0513004007 3:00 min
""")
    assert clips
    assert f"{clips[0].scene}/{clips[0].shot}" == "27/7"
