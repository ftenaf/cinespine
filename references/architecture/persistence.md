---
type: architecture
title: What is durable, and which store owns it
description: The stores, the split between them, and the benchmark that decided how events are written
tags: [architecture, persistence, sqlite]
status: confirmed
evidence: measured 2026-08-29; benchmark in backend/tests/test_spine_persistence.py
---

# What is durable, and which store owns it

Everything the app holds now survives a restart. It did not until 2026-08-29, and the order in which the
pieces were made durable left the app briefly stating, out loud, that a shot was mounted while having
forgotten the shot.

## The stores

One SQLite file, `spine.db`, holds all of it. Separate modules rather than one, because the questions are
different shapes.

| Module | Owns | Trail? |
|---|---|---|
| `event_store` | the spine, source documents, discrepancy resolutions, team users | the spine *is* the trail |
| `production_store` | the production registry | no |
| `character_store` | screenplays, scenes, character profiles | no |
| `breakdown_store` | shot breakdowns per scene | no |
| `requirement_store` | requirements | yes, `requirement_events` |
| `notification_store` | alerts, and when they were read | the row is the record |
| `tag_store` | editorial tags | yes, `editorial_tag_events` |

## Which of those keep a trail, and why

A trail is kept where the **transitions** are the product and a later reader will ask how something got
where it is.

- **Requirements** and **editorial tags** keep one. "Who parked this blocker, and when" is the question a
  three-week-old blocker raises, and an in-place overwrite cannot answer it.
- **Breakdowns** do not. A breakdown is a draft being iterated; the interesting version is the current
  one, and every intermediate state of a prompt somebody is still writing would bury it.
- **Notifications** do not need a separate log. They are written once and never edited; only `read_at`
  changes, so the row is already the record.

Stored as `read_at` rather than a boolean, incidentally, because an alert opened within the minute and one
opened after nine days are not the same event and only the second says the routing is wrong.

## Why events are written one at a time

Durability that depends on somebody remembering to call `flush()` is not durability. The question was
whether per-event writing was affordable. Measured on 2,000 events, which is what a single Silverstack
volume produces:

| Strategy | 2,000 events |
|---|---|
| Fresh connection per event | 9.4s |
| Held connection, default journal | 7.2s |
| **Held connection, WAL, `synchronous=NORMAL`** | **0.06s** |
| One `executemany` | 0.01s |

150x, so the buffer was not needed. `synchronous=NORMAL` gives up the last few transactions if the machine
loses power; it gives up nothing if the process dies, which is the failure this was for. A test guards the
number so the regression is visible.

WAL keeps two sidecar files beside the database. They hold committed data that has not been checkpointed,
so they are as local as the database and are ignored alongside it.

## The in-memory list is a cache, not the record

`SpineWriter._in_memory_spine` is loaded from the store at startup and appended to as events arrive. Every
request that builds takes, sequences or discrepancies walks a production's events in full, and turning
each of those passes into a query plus a few thousand JSON parses would be real cost for no gain.

Events reload **in arrival order**. Several reads take the last event as the most recent word, so a spine
restored out of order would answer differently after a restart than before one.

Source documents are deliberately **not** cached. They carry the original PDF bytes and a preview asks for
one at a time.

## One shape the schema had to respect

A document's rows all share the envelope's `event_id`, so `event_id` is **not unique** and cannot be the
key. Rows are ordered by arrival instead.
