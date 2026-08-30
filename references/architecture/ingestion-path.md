---
type: architecture
title: How a document becomes events
description: The path from upload to spine, and the point where it can go silent
tags: [architecture, ingestion, parsers]
status: confirmed
evidence: office topic had no subscriber, found 2026-08-30
---

# How a document becomes events

    upload -> classify -> store document -> publish to production.raw.<department>
           -> a handler parses it -> events onto production.events.spine
           -> writer: SQLite, in-memory cache, ClickHouse mirror

## The step that can go quiet

Classification decides the topic. **A topic with no subscriber loses the document silently**, and the
upload still answers `INGESTED`.

That is exactly what happened to Office. `classify_document` correctly labelled a daily production report
as `department=office, axis=intent`, the upload published to `production.raw.office`, and nothing was
subscribed. A DPR ingested to zero events, zero takes, and no dead-letter entry either -- because no
parser ran, nothing failed, and nothing could report failing.

The subscriber list is in `IngestionDispatcher._wire_subscribers`. **A new department needs a line there
or its documents vanish politely.** That is the shape of mistake this domain keeps producing: the
confident nothing.

## Where the dead letter queue does and does not help

`REQ-02` requires a parser that extracts zero records from a non-empty document to reject rather than
report success. Every handler does that. But it protects **parsers that run** -- it cannot protect a
document that reaches no parser at all, which is a different hole in the same wall.

Each handler now also rejects on empty output for its own document type, so adding a handler does not
move the problem rather than fix it.

## The three axes, and who may write which

| Axis | Who | Means |
|---|---|---|
| intent | Office | what was planned |
| belief | Set: camera, sound, script -- **and Office** | what somebody says happened |
| existence | DIT, Silverstack | what is on the disk |

Office writes on **two** axes and keeping them apart is load-bearing. `Scenes Scheduled` is intent.
`Scenes Complete` is Office's belief about reality and not reality: Office does not observe what happened,
and writing that as existence would make the plan authoritative for something it cannot see.

`Scenes Part Complete` is a third state. `not_shot` is not the boolean complement of `shot`, and folding
three states into two loses the one the day actually ended in.

## Documents that are drawings, not fields

A lined page is handwriting: there is no text layer to parse, so slates and rolls on it are only reachable
through vision. That extraction runs **before** the event is published, so it travels with the document
rather than arriving as a later, separate fact.

A handwritten camera report has the same problem in reverse: the CSV parser finds nothing on it and
reports a clean, empty document.
