---
type: log
title: What was learned, and when
description: Chronology of findings about this codebase, newest first
tags: [log]
---

# Log

Newest first. Each entry names what produced it.

## 2026-08-30

**Acknowledging after the write.** The hole found while removing Kafka is closed: `EventBus.publish`
now runs every handler and then raises `EventHandlerError` carrying all the failures, so handlers stay
isolated from each other while a failure becomes impossible to absorb. `/api/upload` and
`/api/upload/file` answer 500 and name the doc_id; `/api/seed` counts failures separately from skips,
because in bulk the old behaviour reported every file as ingested while each produced nothing. A failed
spine write is deliberately *not* a DLQ entry: the DLQ means the paperwork was refused, which sends
someone to check a report that was fine.

Falsified rather than assumed -- with the swallowing put back, 10 of the 13 new tests fail, and the
three that pass are the negative controls (a healthy upload, a legitimately rejected document, a publish
where nothing fails).

**Two things this turned up.** `/api/upload/file`'s failure branch named a variable not in its scope, so
it would have raised NameError instead of the error it was reporting -- untested, which is why it was
wrong. And `monkeypatch.undo()` is unsafe in this suite: the autouse fixtures in `backend/tests/conftest.py`
take the same function-scoped monkeypatch, so undoing a patch also reverts `CINESPINE_DB_PATH` and the
test then reads a different database than the one it wrote to.

**Kafka was never running, and has been removed rather than wired.** `EventBus` carried a Confluent
producer that could not execute -- the only construction passed `in_memory=True`, which short-circuits
the branch that builds it -- and `docker-compose.yml` started a Redpanda container that this app never
connected to. Tracing the ingest path settled it: upload, parse, spine write and mirror are one
synchronous call stack in one process, so the broker would have sat between two functions. The spine is
already an append-only log in SQLite that the mirror rebuilds from, so the durability argument runs the
other way. Container, `confluent-kafka` wheel and dead branch all gone; the bus stayed, because
ingestion and DLQ telemetry both run through it. The REQ-01 gap is now recorded as a decision in
[findings/spec-drift.md](findings/spec-drift.md).

**Publishing to a topic nobody listens on is silent, and the ingest path swallows handler failures.**
Two related holes found while removing the broker. The first already caused a bug once -- office
documents were classified, published to `production.raw.office`, and produced nothing while the upload
reported INGESTED -- and `EventBus.topics()` now makes the wiring inspectable. The second is open: a
handler that raises is logged and swallowed, so a spine write that fails still returns 200. The fix is
to acknowledge after the write, not to put a queue in front of it.

**Six questions answered by the domain source.** `pt` means part; "complete" is a chain of seven stages
rather than a state; reject rows that do not look like takes; delete from the mirror too; requirements
need a production level; the demo should run on anonymised real paperwork. The first two are now domain
documents, three are implemented, and the last is a piece of work nobody has started. See
[open-questions.md](open-questions.md).

**A camera CSV footer could become a scene.** normalize_slate canonicalises whatever it is given, so a
contact line became a slate and reached the spine, the mirror and an analytics result. The parser now
tests the shape of a slate before accepting a row.

**A day nobody had offloaded rendered as a clean day.** The gate had the negative -- never report missing
media without a report -- and then said nothing, which is the same mistake pointing the other way. Fixing
it surfaced two larger defects sharing the block: the existence findings were computed into a local and
dropped, and the clip matcher failed on a file extension.

**Clearing the search box was hiding a wrong-array bug.** Deep-linking emptied the reader's query, which
the requirement forbids -- and the emptying was load-bearing: the jump computed an index into `takes` and
the navigator reads `filteredTakes`, so it only ever landed correctly because the filters had just been
cleared. Fixed by pinning the target by identity.

**The analytical mirror was write-only.** Every `SELECT` in the codebase went to SQLite while 5,090 events
sat in ClickHouse unread. The cost of writing was paid and none of the use taken. Fixed by
[the read path](architecture/analytical-mirror.md).

**A multi-camera take is not a disagreement.** The obvious disagreement query -- more than one roll for
this take -- returned rows immediately, and every one was a take shot on three cameras agreeing with
itself perfectly. Grouping by camera returns nothing on the demo day, which is the honest answer.

**A parsed fact can carry contact details.** A camera CSV row that was not a take at all left a contact
line in the `slate` field, reached the mirror, and surfaced in a scene grouping. See
[open questions](open-questions.md).

**Office documents reached no handler.** `production.raw.office` had no subscriber. A daily production
report ingested to zero events, zero takes and no dead-letter entry, while the upload answered
`INGESTED`. See [findings/defects-found.md](findings/defects-found.md).

**Source documents were served ungated.** Both document endpoints returned the original paperwork,
including a script supervisor's phone number and email. See [constraints/privacy.md](constraints/privacy.md).

**The shipped PII scrubber destroyed production data.** `A120 280726` came back as `A[REDACTED_PHONE]`:
a camera card and its shoot date read as a phone number.

**An audit against the design workspace found six gaps.** See [findings/spec-drift.md](findings/spec-drift.md).

## 2026-08-29

**A sequence shot over several days claimed to belong to one.** Scene 119 covered on day 11 and finished
on day 31 came back as two unrelated rows. Third instance of the same mistake; see
[domain/shoot-days.md](domain/shoot-days.md).

**Per-event durability was affordable.** Measured before choosing: 2,000 events cost 9.4s with a
connection per event and 0.06s on a held connection in WAL. See
[architecture/persistence.md](architecture/persistence.md).

**Requirements lost their history.** Creating and resolving reached the spine; every handover and block in
between was an in-place overwrite.

## 2026-08-28 and earlier

**Ingestion slowed 9x when every event was inserted to ClickHouse separately.** A 72-event document went
from 0.8s to 7.4s and a 1,991-event volume to over two minutes. Fixed by batching.

**A facing page carries takes from across the schedule.** It is filed on the day it is handed over, not
the day its takes were shot. First instance of the shoot-day mistake.

**Silence is not denial.** A lined page that does not mark a take as circled has not said it was
uncircled. Recorded as `None` rather than `false`.
