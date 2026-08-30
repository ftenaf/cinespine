---
type: open-questions
title: What is not known
description: Questions written down rather than guessed at, with who can answer each
tags: [open-questions]
status: open
---

# What is not known

A plausible guess written as fact is the expensive failure in this domain. These are recorded instead.

## For Francisco

**What does `pt` mean on a scene token?** The daily production report writes `Scenes Scheduled: 27pt,
49pt, 117pt, 6WT`. `WT` is a wild track. `pt` is probably "part", but that has not been confirmed. The
parser extracts the number so it can be joined and keeps the token verbatim, so nothing rides on the
answer -- but a later reader will assume something.

**Are the slate ranges usable as a completeness check?** The report states `Slates: 27/7 - 8, 49/1 - 9,
117/1 - 5`. `dept-office.md` says a slate outside every stated range was never scheduled, which is a
check nothing else in the day provides. The ranges are parsed and on the spine; nothing uses them yet.

**Does `Scenes Complete` on the DPR mean Office watched it happen, or that Set told them?** It is treated
as Office's belief either way, which is safe. But if it is Set's word relayed, then Office and Set
agreeing is one witness photocopied rather than two agreeing -- the "corroboration by one author" problem.

## For the team to decide

**Parsed facts are assumed to carry no contact details, and nothing enforces it.** A camera CSV row that
was not a take at all left a contact line in a `slate` field, which reached ClickHouse and surfaced in an
analytics result. The privacy gate rests on this assumption. Options: validate slate shape at the parser,
reject rows that do not look like takes, or accept that the derived side needs its own filter.

**Anything that reaches the mirror stays there.** Deleting a document purges its events from SQLite and
not from ClickHouse, which is correct for an append-only store and wrong if what got in should never have.
There is no procedure for this.

**Should requirements have a `production` target level?** The requirements document names four; the code
has three. Nobody has asked for a production-level requirement, so this may be spec drift in the other
direction.

**Is the demo running on real paperwork or fixtures?** The privacy gate refuses real documents by default.
If the demo shows the document previewer against the real day 31, the flag has to be set and crew contact
details are then on screen. Which documents are being shown is a decision, not a default.

## Unresolved in the code

**`AWAITING_OFFLOAD` has no representation.** The gate suppresses rather than states, so an un-offloaded
day and a clean day render identically.

**Sync lag has a baseline now and no consumer.** The intent axis supplies the wrap time; nothing computes
the lag from it. Note that wrap is a time of day and ingest is a timestamp, so the report's own date is
needed before the subtraction means anything.
