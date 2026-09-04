---
type: findings
title: Two of the three agents never run as agents
description: Why gen_ai_invoke_agent_* carries one agent name, verified against Grafana Cloud on 2026-09-03
tags: [findings, observability, agents, adk]
status: confirmed
evidence: gcx metrics query over 30d of Grafana Cloud, plus a local OTLP stack driven through both agent endpoints on 2026-09-03
---

# Two of the three agents never run as agents

The agent dimension of the AI dashboard describes memo drafting and nothing
else. Not a telemetry defect -- the instrumentation is reporting the truth.

## What the metric says

Against the live Grafana Cloud stack, thirty days:

```bash
gcx metrics query 'count by (gen_ai_agent_name) (gen_ai_invoke_agent_duration_seconds_count)' --since 30d
# => {"gen_ai_agent_name": "wrap_rescue_handoff_agent"}     one series
```

One name, one invocation. Reproduced locally by driving both agent endpoints
against a Prometheus with the OTLP receiver open: same single series.

## Three agents, one of them executed

| Agent | ADK `name` | Runner driven | Exports `gen_ai_invoke_agent_*` |
|---|---|---|---|
| memo agent, `wrap_rescue.py` `_draft_with_adk` | `wrap_rescue_handoff_agent` | yes, `runner.run_async()` | yes |
| `WrapRescueAgent` | `wrap_rescue_agent` | no | no |
| `AssistantEditorQueueAgent` | `assistant_editor_queue` | no | no |

Both of the missing two build a `Runner` into a local and never call it:

```python
if api_key:
    try:
        session = InMemorySessionService()
        runner = Runner(agent=self, session_service=session, app_name="agents")
    except Exception:
        pass
# ...then a hand-written deterministic step loop
```

`editorial_queue.py` states the intent in a comment -- *"or we just instantiate
it to prove usage for judges"*.

`gen_ai.invoke_agent.duration` is recorded by ADK in
`google/adk/telemetry/_metrics.py` when the Runner **invokes** the agent.
Constructing one records nothing.

## The two consequences that read as bugs

**`gen_ai_invoke_agent_tool_calls` is 0.** Both classes declare tools in
`super().__init__(tools=[...])` -- `_query_clickhouse_mcp`, `_candidate_scenes`,
`_assign_candidates` -- that ADK never dispatches. The step loops call them
directly as ordinary methods. The metric is correct: ADK saw no tool calls.

**`AssistantEditorQueueAgent` emits nothing at all**, not even model metrics.
It calls no LLM; a run takes 0.88s and adds nothing to `gen_ai_client_*`. It is
a deterministic scorer wearing an `LlmAgent` base class.

## What does export

The eight direct `client.models.generate_content` call sites --
`camera_report_vision.py`, `multimodal.py`, `google_cloud.py`,
`ai_image_service.py`, `breakdown_agent.py`, `character_ai.py`,
`dop_presets.py`, and the non-ADK branch of `wrap_rescue.py` -- all export
model, token and duration series, because the instrumentation wraps the SDK
rather than each call site. Confirmed by triggering `/api/script/parse`: model
calls 1 -> 2, tokens 2722 in / 873 out.

They carry no agent name, which is correct. They are not agents.

## What this constrains

"Which agent is expensive, and whether it is the model or the tool loop" is
answerable only for memo drafting, and will stay that way while the two working
agents do not execute through ADK. Forcing the Runner to produce metrics would
convert two deterministic, testable paths into LLM-driven ones for
observability's sake, which is the wrong trade.

The honest options are to say so on the dashboard, or -- if per-agent timing for
the deterministic agents is wanted -- to measure them in the `cinespine_*`
system. That system does not reach Grafana Cloud
([OBSERVABILITY.md](../../docs/OBSERVABILITY.md) §4b), so this argues for
closing that bridge rather than adding another unexported metric.

The discarded `Runner` blocks were dead code whose own comment admitted it.
**Decided 2026-09-04: deleted, not made real.** Both agents rank and write
requirements; an LLM choosing the tool order would make every mutation
nondeterministic and the exact-outcome tests meaningless, for a metric that a
custom `BaseAgent` through a `Runner` would still report as zero tool calls.
Each run now carries a `cinespine.agent.*` span (OBSERVABILITY.md §3.0) with
its blockers, actions and failed tool calls, which is the per-run record the
ADK metrics could not give. The one ADK agent that runs, the memo drafter, is
the place to add agentic behaviour if it is ever wanted: give it the read-only
MCP tools, and let a model drive something that cannot write.

## Also confirmed

`count by (__name__) ({__name__=~"cinespine_.*"})` over thirty days of Grafana
Cloud returns **empty**. The §4b claim that business metrics are served and not
exported holds against the deployed backend, not only by inference.
