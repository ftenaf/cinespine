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

**Are the slate ranges usable as a completeness check?** The daily production report states
`Slates: 27/7 - 8, 49/1 - 9, 117/1 - 5`. `dept-office.md` says a slate outside every stated range was
never scheduled, which is a check nothing else in the day provides. The ranges are parsed and on the
spine; nothing uses them yet.

**Does the editorial vocabulary need the rest of the chain?** "Complete" runs to seven stages and the tag
statuses cover three of them; `finished` currently claims "no further work expected" when four stages
follow it. See [domain/completion.md](domain/completion.md). Adding picture lock, conforming and DCP is a
migration of stored tags, not a rename, so it needs deciding rather than doing.

**Sync lag has a baseline and no consumer.** The intent axis supplies the wrap time; nothing computes the
lag from it. Wrap is a time of day and an ingest is a timestamp, so the report's own date is needed before
the subtraction means anything.

**Two Grafana gauges have no callers.** `cinespine_department_sync_lag_seconds` and
`cinespine_active_discrepancies` are declared and never set, so a metric that can never fill looks like a
production with nothing happening.

## Answered, and what came of it

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
