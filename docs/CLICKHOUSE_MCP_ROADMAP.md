# 🗺️ Getting more out of the ClickHouse MCP path

Today exactly one thing in CineSpine speaks MCP: `WrapRescueAgent`, through
`HTTPClickHouseMCPClient`, which lives inside `wrap_rescue.py`. This document
plans the rest — what is worth building on that path, what it costs, and which
proposals rest on something the codebase does not actually have.

Everything below is checked against the code rather than inferred from the
architecture diagrams. Where a proposal assumes data that is not there, that is
said before the estimate, not after.

Read [CLICKHOUSE_MCP.md](CLICKHOUSE_MCP.md) first — its §4 (a failed call looks
like a successful one) is the single constraint that shapes every item here.

---

## 0. Four corrections that change the plan

**The MCP server cannot see `spine.db`.** `spine.db` is SQLite and is the
transactional store; `mcp-clickhouse` connects to ClickHouse and can only reach
the six tables in `backend/app/spine/schema.py`. Any assistant grounded on
"query spine.db" will answer confidently about tables that are not on the other
end of the connection. The reachable surface is: `production_events`,
`takes_meta`, `editorial_tag_events`, `requirement_events`, `user_activity`,
`audit_discrepancies`.

**There is no `setup` entity in the spine.** `breakdown_store` has setups as
*planned* multi-camera coverage for previz; nothing on the ingestion side
records a setup as completed. "Setups completed vs. planned" cannot be queried.
The honest equivalent that does exist is slates covered against the day's
declared `slate_ranges` — which `ReconciliationEngine.reconcile_slate_ranges`
already computes.

**`created_at` is ingestion time, not shoot time.** `production_events.created_at`
is `DEFAULT now()`, stamped when the document was uploaded. Every take from one
camera report therefore lands within milliseconds of every other. Any
"average time per setup" or "shooting pace" metric derived from it measures how
fast somebody uploaded a PDF. The only on-set clock in the analytical copy is
`takes_meta.timecode_in` / `timecode_out`. This is the trap most likely to ship
a plausible, precise, wrong number onto a producer's report.

**Agent latency and token spend are already answerable, and not from ClickHouse.**
`gen_ai_invoke_agent_duration_seconds`, `gen_ai_invoke_agent_tool_calls` and
`gen_ai_client_token_usage` are exported to Grafana Cloud Prometheus and
verified live ([OBSERVABILITY.md §4a](OBSERVABILITY.md)). "What was the average
latency of the Wrap Rescue agent yesterday" is a PromQL query today. This is
why proposal #5 below is ranked last.

---

## 1. Foundation — nothing else should start before this

Three consumers copy-pasting `_unwrap_mcp_result` is how the `ok=True, rows=0`
bug comes back in three places at once.

### 1.1 Extract the client (blocking)

Move `HTTPClickHouseMCPClient` and the correctness helpers that travel with it
— `_unwrap_mcp_result`, `_coerce_rows`, `_mcp_response_json`, `_literal`,
`_RUN_QUERY_TOOL` — out of `backend/app/agents/wrap_rescue.py` and into
`backend/app/integrations/clickhouse_mcp.py`. `wrap_rescue.py` imports them
back. No behaviour change.

Those helpers are not plumbing. Each one is a recorded failure: `isError` is
authoritative, columnar results must be zipped onto column names, an event
stream must be unwrapped. A second consumer that reimplements any of them
reintroduces a bug that reported success.

While there: `_post_rpc` builds a fresh `httpx.AsyncClient` per call. Acceptable
for a six-call agent run, wasteful for a chat making N calls per question. Hold
one client for the object's life.

### 1.2 Rename the thing that is not an MCP server (blocking)

`backend/app/agents/mcp_server.py` defines `ClickHouseMCPServer`. It is not an
MCP server, it does not touch ClickHouse, and it reads SQLite through
`SpineWriter`. `wrap_rescue.py` already calls it `legacy_mcp_server` in its own
constructor, which is the codebase noticing.

With three genuine MCP consumers arriving, this name stops being untidy and
starts being misleading. Rename to what it is — a reconciliation façade over
the event store — and keep the module docstring's evidence link.

### 1.3 A read-only user for anything the model writes SQL against (blocking §2)

The `mcp-clickhouse` service connects as `default`, which holds SELECT, INSERT
**and DDL** on every database. That is tolerable while every query is a literal
in `wrap_rescue.py`. It is not tolerable the moment a language model composes
the SQL.

`clickhouse/users.d/security.xml` already defines `read_only_role` with
`GRANT SELECT ON cinespine.*`. The work is to add a second MCP service (or
re-point the existing one for the assistant path) running as a user holding only
that role, plus a settings profile:

| Setting | Why |
| :--- | :--- |
| `readonly=2` | SELECT and settings changes only; no INSERT, no DDL |
| `max_execution_time` | an NL-to-SQL path will eventually write a cross join |
| `max_result_rows`, `max_memory_usage` | bound the blast radius of the one that gets through |

Note what this does **not** do: `_literal()` escapes CineSpine's own parameters
and is bypassed entirely by model-authored SQL, which is the design. The
read-only user is therefore the *only* boundary on that path, which is why it
blocks rather than accompanies.

### 1.4 A contract test the fake cannot pass on its own

[CLICKHOUSE_MCP.md §6](CLICKHOUSE_MCP.md) names the gap: `test_wrap_rescue_agent.py`
injects a fake that builds `ToolCallTrace(tool="run_query", …)` — a tool name
the real client has never sent — and stayed green through the entire period the
real transport returned nothing.

Add a test that asserts the real client's tool names against a live
`tools/list`, skipped when `CLICKHOUSE_MCP_URL` is unset. CI is unaffected; the
demo stack catches a version bump.

---

## 2. The use cases, ranked

Ranking is value per unit of work **given what the data supports**, not
enthusiasm.

### Rank 1 — Cross-day pattern detection *(new; not in the original list)*

Every query in the app is scoped to one shoot day. Scanning the whole history
is the reason a column store is here at all, and nothing currently does it.

Questions a single MCP call answers and no CineSpine surface asks:

- This camera-roll spelling has now diverged on four separate days.
- Sound rolls from one mixer mismatch at 3× the rate of the others.
- This discrepancy type has been raised 11 times and resolved 11 times the same
  way — it is a process defect, not eleven incidents.

`_sound_camera_agreement_query` in `wrap_rescue.py` is already this shape,
scoped down to a day. Widening the scope is a `WHERE` clause.

**Why first:** it is the smallest change with the largest new capability, and it
is the answer to *"why ClickHouse and not SQLite?"* — a question this project
should be able to answer with a query rather than a paragraph.

**Cost:** low. New query functions, one panel.

### Rank 2 — EOD Wrap Report agent *(proposal #2)*

Most of the queries exist. `spine/analytics.py` already has
`time_to_acknowledge`, `unacknowledged_requirements`, `department_attention`,
`scene_coverage`, `requirement_ageing`, `department_sync_lag`. A
`WrapReportingAgent` is largely narration over things that already compute.

What the report can honestly contain:

| Proposed line | Status |
| :--- | :--- |
| Setups completed vs. planned | **Not available** — no setup entity. Substitute slates covered vs. declared `slate_ranges` |
| Average time per setup | **Not available from `created_at`** (§0). Timecode-derived take duration is the only real version |
| Total media offloaded | **Available, and richer than proposed.** `streaming/dispatcher.py` writes `checksum`, `checksum_type`, `file_size_bytes`, `duration_frames`, `volume_name` and `camera_roll` into each `media_file` payload, and every event reaches `production_events.payload_json`. So verified-checksum counts, bytes offloaded, and total recorded duration per roll are all one `JSONExtract` away |
| Crew attendance | **Rename.** `user_activity.actor` is a role token (`@sound_supervisor`), never a person — deliberately, per the schema comment and `references/constraints/privacy.md`. This is *department activity*, and calling it attendance quietly breaks a stated privacy posture |

**Trade-off to decide:** `spine/analytics.py` uses the direct driver with bound
parameters. Routing the report through MCP means hand-built SQL strings and
losing parameterization. Recommendation — run the *report's* queries through MCP
(that is the partner-track story and the queries take no user input), and leave
`/api/analytics` on the driver.

**Cost:** medium-low. Reuses `WrapRescueAgent`'s whole shape: query, rank,
narrate with Gemini, degrade deterministically.

### Rank 3 — Agentic root-cause on discrepancy spikes *(proposal #3)*

The strongest of the five, and the one that fits the product thesis. The data
supports it: `audit_discrepancies.witnesses_json` carries each witness's
department and author, and `production_events.metadata_json` carries
`camera_roll` and `sound_roll`.

**Design constraint that makes it work:** do not let the agent free-form SQL.
Give it a fixed set of dimensions to cut by — camera roll, sound roll,
department, source document, discrepancy type, slate range — and let it choose
which to run and what to run next based on what came back. That is agentic in
the way that matters (multi-step, data-driven branching) without being
NL-to-SQL roulette, and it keeps §1.3 from being on the critical path.

Trigger from a threshold on the existing `cinespine_active_discrepancies`
metric, or on demand from the discrepancy panel.

**Cost:** medium. The loop is new; every query is a variant of one that exists.

### Rank 4 — IDE integration *(proposal #4)*

**There is no `.mcp.json` in this repository.** Adding one pointed at
`http://localhost:4200/mcp` gives Claude Code and Cursor the live schema during
development. Roughly fifteen minutes.

Two conditions: point it at the read-only service from §1.3, and keep
credentials out of the file — the local server needs none
(`CLICKHOUSE_MCP_AUTH_DISABLED=true`), and a hosted one takes its token from the
environment.

**Cost:** trivial. Do it during §1.

### Rank 5 — Natural-language Production BI chat *(proposal #1)*

The highest-ceiling item and the one most likely to be quietly wrong.

Grounding it correctly means the six tables from §0 in the system prompt, plus
an explicit instruction to refuse rather than improvise: a producer asking about
call sheets, crew or schedule is asking about data that is not in the analytical
copy, and the failure mode is a confident join across tables that do not relate.
"How many VFX shots today have unresolved discrepancies" does work —
`takes_meta.is_vfx` and `audit_discrepancies` are both real.

**The mitigation that actually matters:** show the SQL and the row count beside
every answer. `ToolCallTrace` already carries exactly this and
`WrapRescueAgentPanel.tsx` already renders it. An assistant that displays its
own query is falsifiable by the person reading it; one that returns only prose
is not. This is the same discipline as §4 of CLICKHOUSE_MCP.md, applied at the
UI instead of the transport.

**Blocked on §1.3.** This is the path where a model composes SQL.

**Cost:** medium-high. New route, an ADK `LlmAgent` with the MCP client as a
tool, a chat panel, and prompt work that is mostly about refusals.

### Rank 6 — OTel traces into ClickHouse *(proposal #5)* — recommend deferring

Two of the three questions this would answer are already answered, and the
third is answered by a setting that is off on purpose.

- *"Average latency of the Wrap Rescue agent yesterday"* — already exported as
  `gen_ai_invoke_agent_duration_seconds` (OBSERVABILITY.md §4a).
- *"Tool-call counts per agent run"* — already `gen_ai_invoke_agent_tool_calls`.
- *"Why did token usage spike"* — needs prompt and response content, which is
  **deliberately not captured**: `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`
  is unset because prompts carry unreleased screenplay text. Routing traces to
  ClickHouse does not change that; turning the flag on is the actual decision,
  and it is a privacy decision, not a storage one.

Doing it means a new OTel Collector service with the ClickHouse exporter, a
second telemetry schema, and a second copy of data that already has a home. The
self-diagnosis narrative is genuinely appealing — an agent querying its own
performance is a good demo. It is not worth a new service before ranks 1–3
exist.

---

## 3. Cross-cutting: make the MCP path visible

`WrapRescueAgentPanel.tsx` renders `ToolCallTrace` — tool name, arguments, row
count, error. That component is the partner integration made visible, and it
exists on exactly one screen.

Generalize it into a shared "MCP tool call" element that every new feature
renders. Cheap, and it turns one demonstrable runtime path into four.

It is also the honest-reporting mechanism from §2 rank 5, so it is worth
building once, properly, rather than per-feature.

---

## 4. Suggested order

| Stage | Items | Unblocks |
| :--- | :--- | :--- |
| 1 | §1.1 extract client · §1.2 rename · §1.4 contract test · rank 4 `.mcp.json` | everything |
| 2 | Rank 1 cross-day patterns · §3 shared trace component | the "why ClickHouse" answer |
| 3 | Rank 2 EOD report | reuses stage 2's queries |
| 4 | §1.3 read-only user · Rank 3 root-cause loop | |
| 5 | Rank 5 BI chat | needs §1.3 and §3 |
| — | Rank 6 | deferred; revisit if agent self-diagnosis becomes a goal in itself |

---

## 5. What to verify before committing to stage 3

One fact this plan asserts from reading and has not confirmed against running
data:

**Whether `takes_meta.timecode_in` is populated densely enough** to carry a
duration metric, or whether it is sparse in the demo data. If sparse, the EOD
report has no honest pace metric *for the belief axis* and should say so rather
than substitute an ingestion-time one.

Note that the existence axis is not affected: `media_file.duration_frames` is
recorded per clip, so "total recorded duration offloaded" stands on its own
regardless of how the take timecodes look. That is a real number about the day,
derived from the media rather than from when someone uploaded a report.

One query against the demo stack settles it. It does not block stage 1 or 2.
