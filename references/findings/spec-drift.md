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

**REQ-14, target levels.** Editorial tags carry `scene` and `shot` and not `take`. Requirements were
closed on 2026-08-30 and now carry all four. A tag hangs on coverage rather than on one attempt, so this
may be right as it stands -- recorded as open because nobody has confirmed it either way.

## Deliberate divergences, not drift

**REQ-10's two gauges, one filled and one removed.** Closed on 2026-08-30, in opposite directions.
`cinespine_active_discrepancies` is now written wherever discrepancies are computed, labelled by
production and day so one day cannot overwrite another, with every severity and kind written on each
observation -- zeros included, because a gauge keeps its last value and a resolved discrepancy would
otherwise show its old count.

`cinespine_department_sync_lag_seconds` was removed rather than wired. It cannot be computed: a daily
production report states wrap as a time of day with no date on it, and the only other timestamp available
is when the document reached this system, which for day 31 is months after it was shot. Subtracting one
from the other invents a number neither witness supports. What REQ-10 actually asks for -- a department
sync matrix -- is answered instead by the acknowledgement axis added the same day, which measures from a
fact the product records: how long between something being raised and somebody saying they have it. See
`analytics.time_to_acknowledge`.

**REQ-13's `NOTIFICATION_ADDED` is not emitted, and adding it would change nothing.** The specified event
does not exist. The behaviour it is for does: notifications are created alongside `REQUIREMENT_CREATED`,
`REQUIREMENT_UPDATED` and `REQUIREMENT_RESOLVED`, all of which are emitted, and the SSE handler refreshes
notifications on any live event -- so the bell updates without a page reload. Emitting a dedicated event
would fire a second time for the same fact. Recorded here rather than built.

**REQ-09's naming is wrong and staying.** `ClickHouseMCPServer` is neither ClickHouse-backed -- it reads
the in-memory spine -- nor MCP: there is no protocol and no `query_clickhouse` tool. The requirement's own
negative holds by construction, since there is no SQL surface at all. The name misleads and a rename
touches every call site and test for cosmetic gain, so it is written down instead of done.

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
