---
type: findings
title: Defects found in this codebase
description: What was wrong, how it showed itself, and what it cost to find
tags: [findings, defects]
status: confirmed
evidence: each entry names its reproduction
---

# Defects found in this codebase

Each was paid for once. The point of writing them down is that the *shape* recurs even when the instance
does not; the shapes are named in
[constraints/failure-modes.md](../constraints/failure-modes.md).

## Ingestion and parsing

**The same defect in four parsers, found four separate times.** A contact block in a document became a
production fact, wearing a different field each time, and each was found only because somebody looked:

  * `camera_csv` -- a footer became a slate, reached the spine and the analytical mirror, and came back
    as the scene an analytics result was grouped under. Fixed with a slate-shape guard.
  * `sound_ale` -- the same thing in the sound report, still live after the first fix because only the
    parser that had failed was checked. Fixing it exposed a second defect underneath: `normalize_slate`
    keeps the `.WAV` on a filename, so a row taking its slate from the NAME column became the slate
    `49WTT01.WAV` -- truthy enough that the filename fallback below it never ran.
  * `silverstack_thumbnail` -- clip blocks are split on lines beginning `Name `, so a contact block
    written that way became an entire clip, with the address in `file_name`. A slate-shaped guard would
    never have caught it, because `file_name` is not a slate.
  * `scripte_tclog` -- every unrecognised line is appended to the previous take's note, so a footer
    became something the script supervisor supposedly wrote about that take. Refused rather than
    redacted: rewriting a note quietly alters what somebody said.

The lesson is in the count. Three fixes were applied believing each was the last, and the fourth was
found only by widening the field list on a sweep. `backend/tests/test_parser_pii_sweep.py` now runs the
same document through every parser at once, so a parser added later that skips the guard fails there.


**Every Silverstack clip reached the spine under a slate nobody wrote.** A thumbnail report states
`Scene 27` and `Shot 27/7`, and the `Shot` field is already the whole slate. All three Silverstack parsers
built `f"{scene}/{shot}"` anyway, giving `27/27/7`, which normalised to `27/27`. So DIT disagreed with
camera about every take of the day, and the board showed no conflict at all -- the two witnesses never met
on a common key, so there was nothing to compare. The same line appeared in the volume, clips and
thumbnail parsers; the other two take scene and shot from filenames, where the shot half is always bare,
so only the thumbnail path was wrong in practice. Found by the slate-range check on its first run against
real data. Reproduce with `Scene 27` / `Shot 27/7` through `parse_silverstack_thumbnail_text`.


**A compound slate reported three cards as a conflict.** `119/5` on card A046, `41+122A/4` on A068 and
`97+121/4` on A080 came back as "Camera A roll mismatch on 119/5". The slate pattern did not admit
compound scenes, so three separate setups folded into one.

**A facing page filed its rows under the wrong day.** See
[domain/shoot-days.md](../domain/shoot-days.md).

**A wild track stole the block's day.** Six takes filed under day 31 belonged to day 25.

**Part-takes were lost.** `2.1` and `2.2` are distinct takes; the take pattern read the first digit.

**A blank camera-roll column inherited the wrong roll**, until the block's roll was carried forward
explicitly and the inheritance marked on the record.

**A camera CSV row that was not a take became one.** A contact line ended up in the `slate` field and
reached the analytical mirror. Found on 2026-08-30 while writing a scene grouping; the query now requires
a scene to start with a digit, but the parser is where it should be caught. See
[open-questions.md](../open-questions.md).

## The spine and its stores

**An upload whose spine write failed returned 200 INGESTED.** `EventBus.publish` caught every handler
exception, logged it, and returned -- so `spine_writer.append_event` raising left the day holding a
stored document with no events in it, which is indistinguishable from a day that went fine. Found while
removing the Kafka producer that sat in the same method. Fixed by acknowledging after the write:
`publish` runs every handler, then raises `EventHandlerError` with all of them. Reproduce by patching
`append_event` to raise and posting to `/api/upload` -- it now answers 500 and names the doc_id so the
document can be retried or deleted.

The document itself is kept rather than rolled back. It is the evidence, and discarding it would mean
asking whoever sent it to send it again.

**A spine failure would have been filed as a rejected document.** The first cut let `EventHandlerError`
reach the dispatcher's broad `except Exception`, which emits a DLQ entry. The DLQ means "this paperwork
was refused", which sends someone to check a report that was fine; a disk error means the machinery
failed. Two different responses, so the dispatcher now re-raises rather than filing it.

**The failure path of `/api/upload/file` raised NameError.** Its handler named a variable that does not
exist in that function's scope, so the branch reporting the error would have failed with a different
error. It had no test -- the untested refusal, and the reason the falsification for this fix runs all
four call sites rather than one.


**Every event was inserted to ClickHouse separately.** A 72-event document went from 0.8s to 7.4s; a
1,991-event volume took minutes. Batching returned them to 0.86s and 2.0s.

**`DateTime` at second resolution lost the trail's order**, which is the one thing a trail is for.
`DateTime64(3)` and caller-supplied timestamps fixed it.

**A naive datetime was read as local time**, so mirrored rows landed an hour early on a machine offset
from UTC. The order stayed right, which is what makes that kind of mistake survive review.

**Clearing an editorial tag credited the wrong actor.** The board said `@ana removed the tag` when @ana
had only ever set it.

**Requirements lost every transition between created and resolved.** Handovers and blocks were in-place
overwrites, so "who parked this" could not be answered five minutes later.

**Deleting a document did not reach the mirror.** By design -- it is append-only -- but it means anything
that gets in stays in.

**Two of the four required detections were computed and thrown away.** `reconcile_existence` was called,
its result assigned to a local, and never read. `PAPERWORK_WITHOUT_MEDIA` and `MEDIA_WITHOUT_PAPERWORK`
had therefore never reached the API. Found 2026-08-30 while adding `AWAITING_OFFLOAD`, because the same
block held both mistakes.

**The clip matcher failed on a file extension.** The camera report writes `A120_C001_260728` and the
offload manifest writes `A120_C001_260728.MOV`; the comparison was raw, and its Silverstack-style fallback
expected `A_0120C001`, a different arrangement of underscores. Collecting the discarded results without
this fix would have reported nine clips as missing that were sitting in the manifest -- the false gap the
offload gate exists to prevent, arriving through a different door. With it fixed, six genuine findings
remain: the demo's manifest covers three clips and the camera reports log nine.

## Surfaces

**An editorial tag control looked like a display.** It had been interactive since it was built and
verified working; once tagged it rendered as bare chips beside genuinely read-only badges, so nobody
would think to click it. A test that clicks a button cannot tell you nobody would try.

**A camera remover was `opacity-0` until hover**, which is indistinguishable from absent.

**The recent-changes feed repeated identical saves** as two identical lines with nothing to tell them
apart.

**A generated character portrait was never saved.** The endpoint returned the image, the UI showed a green
tick claiming it had been stored, and a reload threw away both the likeness and the generation spent
making it.

**Shot breakdowns lived only in the tab's memory.** Generated once and then edited -- a focal length
nudged, a prompt rewritten and re-rendered -- and a reload discarded all of it.

## Process

**Verified against the wrong instance, twice.** Both times a console error was blamed on new code when the
browser held a module from between two edits.

**A compound-slate fix was verified against `pdfplumber` text while the pipeline uses `pypdf`.** The bug
was still fully present.

**A heredoc mangled escape sequences twice**, once turning `\b` into a literal backspace and once turning
a separator into a NUL that made git classify a source file as binary.
