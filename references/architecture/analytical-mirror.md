---
type: architecture
title: ClickHouse is a mirror, and now it is read
description: Why the analytical spine is not the source of truth, and what it is asked
tags: [architecture, clickhouse, analytics]
status: confirmed
evidence: REQ-07 divergence; read path added 2026-08-30; measured batching regression 2026-08-28
---

# ClickHouse is a mirror, and now it is read

REQ-07 in the design workspace says the spine **is** ClickHouse. Here it is not, and that divergence was
deliberate. It is recorded rather than hidden, per the convention that a broken rule is written down.

## Why it is a mirror

Three reasons, in order of weight:

1. **A reporting database must be allowed to be down.** The circuit breaker exists precisely so an
   ingestion cannot fail because ClickHouse is unhappy. If the spine were ClickHouse, stopping the
   container would take the app offline -- and that has already happened once in normal use.
2. **The read shapes are wrong for it.** Point lookups by id, per-take reads, transactional edits. A
   columnar store answers those badly, and its deletes are asynchronous mutations.
3. **The events are immutable either way.** Append-only is a property of the model, not of the engine.

So: SQLite is OLTP, ClickHouse is OLAP. That is a stronger position than "we used it for everything",
because each store is doing what it is good at and the reason is stateable.

## What it was missing until 2026-08-30

It was **write-only**. Every `SELECT` in the codebase went to SQLite while 5,090 events sat in ClickHouse
that nothing ever asked anything. A database nobody queries cannot answer anything, whatever is in it --
and that, rather than the source-of-truth question, was what made the investment invisible.

## What it is asked

`backend/app/spine/analytics.py`, surfaced at `GET /api/analytics` and in the Productions section. Six
questions, all of them "every day of a production at once, grouped and counted":

- what each department has said, by axis
- when each department filed, per day
- where witnesses disagree on a roll
- what each scene cost, across every day it was shot on
- where every shot has got to
- how long work sits before somebody deals with it

## Two decisions inside those queries

**`argMax`, not `FINAL`.** Deriving the current answer from an append-only log is what `argMax` is for. It
needs no merge to have happened, so the answer does not depend on when ClickHouse last compacted.

**JSON functions, not materialized columns.** Materialized columns would be faster and are the right
answer at real volume, but they only populate for rows inserted after the `ALTER`. The existing five
thousand would come back empty until a `MATERIALIZE` mutation had run over them, and a query that is fast
and silently wrong about history is the worse trade.

## Absent is not empty

No ClickHouse means every query returns `None`, the endpoint answers `available: false` with the reason,
and the panel prints it. `None` and `[]` are kept distinct throughout: "could not be asked" and "asked,
and the answer is nothing". A panel that cannot fill looks exactly like a production with nothing in it,
and those need opposite responses.

## Two properties worth knowing

**Writes are batched.** One insert per event turned a 72-event document from 0.8s into 7.4s and a
1,991-event volume into minutes: each insert is a round trip and a new part on the server.

**Deleting a document does not reach the mirror.** It is append-only and nothing deletes from it, so
events purged from SQLite live on here. That is by design, and it means anything that gets in stays in --
which matters more than it sounds. See [open-questions.md](../open-questions.md).
