---
type: open-questions
title: What is not known
description: Questions written down rather than guessed at, with who can answer each
tags: [open-questions]
status: open
---

# What is not known

A plausible guess written as fact is the expensive failure in this domain. These are recorded instead.

Answered questions leave this file. Where the answer is a domain fact it moves into `domain/`; where it
was a decision, what was done with it is noted below.

## Still open

Nothing. Every question written here has been answered.

## Answered, and what came of it

**The shooting date is on the paperwork, and the Thumbnail Report states it most reliably.** Francisco,
2026-08-30:

> You can find the shooting date in the daily production report on the top of the page... but you can find
> it also in the Thumbnail Report (260728_SD31 -> 28 July - 2026). Also on every script report on the
> header (Date: 28/07/2026). Also on the sound csv header... So to find the shooting date you should look
> at the Thumbnail Report, because it's the most reliable one.

`normalizers.shoot_days.extract_shoot_date` reads all four in his order, and returns which document said
so alongside the date -- a date with no source is a number nobody can check. The volume stamp comes first
because it is the only place the date and the shoot day are written together, so the two cannot be paired
wrongly.

Every document now emits its own date claim onto the spine, from a subscriber on every raw topic rather
than from inside the parsers: every department states the date, and a document whose parser refuses it has
still said what day it covers. `SHOOT_DATE_DISAGREEMENT` reports when two of them differ, and does not
resolve it -- the most reliable source is still not the answer, and which document is wrong is a question
for the people who wrote them.

Against the real data all eight documents for day 31 agree on 2026-07-28, from three different kinds of
source, and the check is silent. Finding it also turned up a hardcoded skip list in the thumbnail parser:
`"and 28 July"`, `"260728_SD31"` and `"DEMO PRODUCTION"` were matched literally, so another production's
report would have carried those lines into its clips -- and it was discarding the volume stamp that
carries the answer.

**The department sync lag is now computable and still not built.** The date was the missing input, so the
subtraction is possible. On historical paperwork it is also useless: the only other timestamp is when the
document reached this system, months after the day was shot, so the number would be correct and mean
nothing. What REQ-10 actually asks for -- where a handover stalls -- is answered by the acknowledgement
axis instead, which measures from a fact the product records. Recorded rather than done.

**The slate ranges are usable as a completeness check, and the first thing they caught was ours.**
Implemented 2026-08-30 as `SLATE_OUTSIDE_STATED_RANGE`. Run against the real day it produced one finding:
slate `27/27`, which no department ever wrote. It came from all three Silverstack parsers building
`scene + "/" + shot` when Silverstack's `Shot` field is already the whole slate -- so every clip in a
thumbnail report reached the spine under a slate that did not exist, and DIT disagreed with camera about
every take while the board showed nothing, because the two witnesses never met on a common key. With the
parsers fixed the check is silent on that day, which is the right answer.

Three things it deliberately does not report, because the page is silent rather than denying: a scene with
no stated range, a slate whose shot half is not a number (`49/WT`), and anything at all when no ranges
parsed.

**The editorial vocabulary did need the rest of the chain, and adding it migrated nothing.** Francisco,
2026-08-30. `picture_lock`, `colour_sound_vfx`, `conformed` and `dcp` now follow `finished`, whose label
and description were corrected -- it claimed "No further work expected" while holding the highest ordinal.
Listed here as a migration when it was first written down; it was not. A rename would have been, and would
also have meant rewriting an append-only trail. Keys are untouched, so every stored tag and every trail
row still validates. See [domain/completion.md](domain/completion.md).

**`pt` on a scene token means *part*: the script notes it was not fully shot.** Francisco, 2026-08-30.
Recorded in [domain/scene-tokens.md](domain/scene-tokens.md). The parser already kept the token verbatim,
which turned out to be right, so nothing changed but the docstring that called it unconfirmed.

**"Complete" is a chain of seven stages, not a state.** Francisco, 2026-08-30. Recorded in
[domain/completion.md](domain/completion.md), which also sets out how far the code represents it. The
remaining decision is listed above.

**Reject rows that do not look like takes.** Francisco, 2026-08-30. `parse_camera_csv` now tests the shape
of a slate before accepting a row, so a footer or a contact block cannot become a scene. Skipped rather
than rejected -- one junk row does not make a report unparseable -- and the empty-result guard still
catches a document that is entirely junk.

**Deleting a document should remove it from ClickHouse too.** Francisco, 2026-08-30. It now does, by
mutation, and that is the one thing permitted to delete from the append-only mirror. Never fatal: the
document is already gone from the store the app reads.

**Requirements should have a `production` target level.** Francisco, 2026-08-30. Added, alongside scene,
shot and take.

**The demo should run on real paperwork, anonymised and scrambled.** Francisco, 2026-08-30. Not yet done,
and it is a piece of work rather than a setting: it needs a pass that replaces crew names, contact details
and any unreleased content with plausible substitutes while keeping every slate, roll, timecode and
checksum intact -- because those are what the parsers and the reconciliation are being demonstrated on. A
scramble that alters a roll number breaks the thing it is meant to show. Until it exists the demo runs on
the embedded synthetic fixtures, which the privacy gate serves and which carry no real material.
