---
type: findings
title: Where this build and its requirements disagree
description: Audit against agentic-cinema-design, 2026-08-30, with what has since closed
tags: [findings, requirements, audit]
status: partial
evidence: audited against stages/02-requirements/output/requirements.md on 2026-08-30
---

# Where this build and its requirements disagree

All sixteen requirements in `agentic-cinema-design` were checked against the running code on 2026-08-30.
Six gaps were found. Two have since closed; the rest are open and listed with what they would cost.

## Closed since the audit

**REQ-11, the intent axis.** Office documents were classified and reached no handler, so one of the three
axes the architecture is named for carried no data at all. The live spine held
`{belief: 24, existence: 6}` and no intent. Closed 2026-08-30: the daily production report is now parsed
and lands, and the first thing it surfaced was a real disagreement -- Office reports scenes 117 and 6WT
shot on day 31 and no other department has filed anything for either.

**REQ-12, the privacy gate.** Both document endpoints served the original paperwork ungated. Closed
2026-08-30; see [constraints/privacy.md](../constraints/privacy.md).

**REQ-08.4, `AWAITING_OFFLOAD`.** The gate refused to report missing media without an offload report,
which is the negative, and then said nothing at all -- so a day nobody had offloaded rendered as a clean
day. Closed 2026-08-30 with one finding per day rather than one per take, and it uncovered two larger
defects behind it. See [defects-found.md](defects-found.md).

**REQ-15, deep-linking cleared the reader's search box.** `jumpToTarget` called `setSearchQuery('')`,
with a comment reasoning its way to the opposite of the requirement's negative. Closed 2026-08-30 -- and
the clearing was hiding a second defect: the jump found an index into `takes` while the navigator reads
`filteredTakes`, so it only landed correctly *because* the filters had just been emptied. The target is
now pinned by identity and stays reachable when the reader's filters exclude it, with the exception said
out loud rather than shown silently.

## Open

**REQ-10, two gauges that can never fill.** `cinespine_department_sync_lag_seconds` and
`cinespine_active_discrepancies` are declared; `set_sync_lag` and `set_discrepancies_count` have no
callers. The falsification -- simulate a four-hour DIT delay, assert the matrix goes amber -- cannot pass.
The intent axis has since supplied the wrap time this needs.

**REQ-14, target levels.** Closed on 2026-08-30. `RequirementTargetType` now has all four
(`production`, `scene`, `shot`, `take`). Editorial tags still have two, which is a narrower gap
than the one recorded here originally.

**REQ-13, `NOTIFICATION_ADDED`** is specified and never emitted. The other four event types are.

**REQ-09, naming.** `ClickHouseMCPServer` is neither ClickHouse-backed -- it reads the in-memory spine --
nor MCP: there is no protocol and no `query_clickhouse` tool. Its negative holds by construction, since
there is no SQL surface at all, but the name misleads.

## Deliberate divergences, not drift

**REQ-01 asks for Kafka. There is no broker, and this is now a choice.**
Removed on 2026-08-30 along with the Redpanda container. It had been drift --
`EventBus` carried a Confluent producer that was unreachable, because the bus
was only ever constructed `in_memory=True`, and the container in
`docker-compose.yml` accepted no connections from this app. Wiring it up was
the obvious fix until the ingest path was traced end to end:

    POST /api/upload -> publish "production.raw.camera"
                     -> dispatcher handler parses, inline
                     -> publish "production.events.spine"
                     -> spine_writer.append_event -> SQLite + ClickHouse
                     -> 200

One synchronous call stack in one process. A broker would have sat between two
functions in it. None of the usual arguments survive contact with that shape:
there is one consumer process, the upload response carries the parse result
back to the caller, and a shoot day is a few hundred documents rather than a
throughput problem. The durability argument inverts -- the spine *is* an
append-only log, in SQLite, and the analytical mirror already rebuilds from it,
so Kafka would have been a second log with weaker retention guarding the log of
record.

**The gap this leaves.** A reader of the requirements will find no broker, no
partitioning, and no replay from a topic. If REQ-01 is read as "the system must
be able to fan out to independent consumers," that capability is absent and
adding it later means a real change, not a config flag. The judgement made here
is that a container nothing connects to is a worse answer to REQ-01 than an
honest absence, because it makes the architecture diagram claim something the
running system does not do.

**What was kept.** `EventBus` itself, which is load-bearing: ingestion reaches
the spine writer through it and rejected documents reach telemetry through it.
Only the broker went.

**REQ-07 says the spine is ClickHouse.** It is SQLite with ClickHouse mirrored. Reasoned and recorded in
[architecture/analytical-mirror.md](../architecture/analytical-mirror.md). The append-only invariant
holds. This is a case for amending the requirement rather than the code.

**REQ-16 names 86 tests.** The suite is now an order of magnitude larger. The requirement's actual
falsification -- `pytest` with `CINESPINE_EXAMPLES_DIR` pointing nowhere -- passes.

## What holds

REQ-02 through REQ-06 -- zero-row rejection, strict parsing of machine-generated files, vision extraction
for lined pages, slate and take normalisation, roll key folding -- all hold, and are the best-tested area
of the repository.
