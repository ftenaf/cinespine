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

**REQ-15, deep-linking cleared the reader's search box.** `jumpToTarget` called `setSearchQuery('')`,
with a comment reasoning its way to the opposite of the requirement's negative. Closed 2026-08-30 -- and
the clearing was hiding a second defect: the jump found an index into `takes` while the navigator reads
`filteredTakes`, so it only landed correctly *because* the filters had just been emptied. The target is
now pinned by identity and stays reachable when the reader's filters exclude it, with the exception said
out loud rather than shown silently.

## Open

**REQ-08.4, `AWAITING_OFFLOAD`.** The gating works: a missing offload never renders as missing media. But
the requirement wants an explicit state and the code emits *nothing*, so an un-offloaded day looks
identical to a clean one. The string appears nowhere in the codebase.

**REQ-10, two gauges that can never fill.** `cinespine_department_sync_lag_seconds` and
`cinespine_active_discrepancies` are declared; `set_sync_lag` and `set_discrepancies_count` have no
callers. The falsification -- simulate a four-hour DIT delay, assert the matrix goes amber -- cannot pass.
The intent axis has since supplied the wrap time this needs.

**REQ-14, target levels.** The requirement names four (`production`, `scene`, `shot`, `take`);
`RequirementTargetType` has three, with no `production`. Editorial tags have two.

**REQ-13, `NOTIFICATION_ADDED`** is specified and never emitted. The other four event types are.

**REQ-09, naming.** `ClickHouseMCPServer` is neither ClickHouse-backed -- it reads the in-memory spine --
nor MCP: there is no protocol and no `query_clickhouse` tool. Its negative holds by construction, since
there is no SQL surface at all, but the name misleads.

**REQ-01, Kafka.** `EventBus` has a Confluent path and is only ever constructed `in_memory=True`.
Redpanda is in `docker-compose.yml` and unused.

## Deliberate divergences, not drift

**REQ-07 says the spine is ClickHouse.** It is SQLite with ClickHouse mirrored. Reasoned and recorded in
[architecture/analytical-mirror.md](../architecture/analytical-mirror.md). The append-only invariant
holds. This is a case for amending the requirement rather than the code.

**REQ-16 names 86 tests.** The suite is now an order of magnitude larger. The requirement's actual
falsification -- `pytest` with `CINESPINE_EXAMPLES_DIR` pointing nowhere -- passes.

## What holds

REQ-02 through REQ-06 -- zero-row rejection, strict parsing of machine-generated files, vision extraction
for lined pages, slate and take normalisation, roll key folding -- all hold, and are the best-tested area
of the repository.
