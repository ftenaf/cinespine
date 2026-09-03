# 📡 Observability

Telemetry reaches Grafana Cloud from three places: the backend exports
OpenTelemetry traces, logs and metrics, the GenAI instrumentation emits spans
and metrics for the agents' model calls, and the browser sends RUM through
Faro. The backend also serves `prometheus_client` metrics at `/api/metrics`,
and those reach nothing in production — nothing scrapes a Cloud Run service.
§4 is the split.

The agents' spans follow the OpenTelemetry **GenAI semantic conventions**, so
LLM calls, tool calls and token usage arrive in the standard shape and are
queryable as `gen_ai_*` traces and metrics.

That is **not** the same as being onboarded to [Grafana Cloud Agent
Observability](https://grafana.com/docs/grafana-cloud/observe-and-act/agent-observability/).
An earlier version of this document claimed the OTLP endpoint was the whole
integration. It is not — see [§3.1](#31-what-agent-observability-additionally-requires).

Everything here is verified against the deployed service rather than inferred
from configuration.

---

## 1. What ships where

| Signal | Source | Transport | Set by |
| :--- | :--- | :--- | :--- |
| Traces | FastAPI, httpx | OTLP HTTP | `OTEL_EXPORTER_OTLP_ENDPOINT` |
| Logs | Python `logging`, trace-correlated | OTLP HTTP | same endpoint |
| Metrics (OTel) | GenAI instrumentation, OTel meters | OTLP HTTP | same endpoint |
| Metrics (business) | `prometheus_client` at `/api/metrics` | scrape | always on |
| Agent / GenAI spans | `opentelemetry-instrumentation-google-genai` | OTLP HTTP | inherits the OTel config |
| Browser RUM | `@grafana/faro-web-sdk` | Faro collector | `VITE_GRAFANA_FARO_URL` |

`backend/app/core/telemetry.py` wires the first five; `frontend/src/main.tsx`
initialises the last.

None of it is required. With `OTEL_EXPORTER_OTLP_ENDPOINT` unset the exporter
logs one line and returns, and the app runs unchanged.

### Which deployment sent it

Every signal carries a resource built in `telemetry.py`: `service.name`,
`service.version` (the package version), `deployment.environment` and
`service.instance.id`. Cloud Run is recognised by the `K_SERVICE` variable it
sets on every container, so production is `cloudrun` with the revision name as
instance id and nothing to configure. Anything else is `local`, named after the
host, unless `CINESPINE_ENV` says otherwise.

The attribute exists because of one afternoon in which a laptop container
running with the production `.env` pushed 2,400 error lines about a missing
credentials file into Grafana Cloud, where nothing could tell them from Cloud
Run's. Two consequences:

- **A local process exports only to a local collector.** Pointed anywhere
  else, it disables export and logs why. `CINESPINE_TELEMETRY_REMOTE_OK=1`
  overrides that, and the data arrives labelled `local`.
- **Dashboards and alerts filter on the label.** The Cloud alert rules select
  `deployment_environment!="local"`, which also matches series from builds
  older than the label.

---

## 2. Traces and logs are correlated

`LoggingInstrumentor().instrument(set_logging_format=True)` stamps every log
record with the active span, so a log line in Cloud Logging carries the ids you
need to find the same request in Grafana:

```
2026-09-03 09:05:27,937 INFO [backend.app.streaming.broker] [broker.py:117]
  [trace_id=fce1e19da275642e23f36bf9bcc30604 span_id=1d1129ce90fb1e73
   resource.service.name=cinespine-backend trace_sampled=True]
  - Registered SSE subscriber sub_0d3aaee8 (prod=DEMO_PRODUCTION, day=31)
```

`trace_sampled=True` is the useful part: the trace that line belongs to was
exported, so pasting the `trace_id` into Grafana finds it.

Both a span exporter and a log exporter are installed, against the same
`Resource` (`service.name=cinespine-backend`), so traces and logs land under
one service rather than two.

---

## 3. Agent observability

`GoogleGenAiSdkInstrumentor().instrument()` traces the google-genai SDK, which
is the layer this app actually calls: `client.models.generate_content` in
character inference, the camera-report vision reader, the multimodal extractor
and the Wrap Rescue memo. Spans cover `generate_content` and `execute_tool`, so
an agent run reads as a tree rather than one opaque HTTP span.

It attaches in **0.00s** and runs inline in `setup_otlp()`.

### What it replaced, and why

This was OpenLIT. OpenLIT patches the client library of every provider it
supports and **hard-depends on `anthropic`, `openai`, `boto3` and `botocore` to
do it** — four vendor SDKs nothing in this codebase calls. `uv tree` shows them
as unconditional requirements, not extras.

That cost `openlit.init()` **~34 seconds**, which was too long to run inline: it
sat on the import path ahead of uvicorn binding a socket, and the deployment
platform's autoscaler gave up with *"the application failed to open a port in
time"* — which reads like a crash and was not one. The workaround was a daemon
thread, and it worked, but it left a ~34s window after boot where model calls
went unrecorded and it monkeypatched modules while the app was already serving.

Swapping to the google-genai instrumentation removes the cause rather than
managing it. Measured:

| | OpenLIT | google-genai |
| :--- | :--- | :--- |
| Init cost | ~34s, on a background thread | **0.00s, inline** |
| Unused vendor SDKs shipped | anthropic, openai, boto3, botocore | **none** |
| Cloud Run image | 257 MB | **218 MB** |
| Window with no instrumentation | ~34s after boot | **none** |

> **Not** a win: import time or cold start. Both Cloud Run images import in
> ~1.6s and answer `/health` in ~2s. The 45s import that broke the prior
> deployment platform was fixed earlier by backgrounding, and separately by
> dropping the `dev` and `hackathon` extras from the production image. Those
> two changes did
> the deployment work; this one is about what ships and when it attaches.

## 3.1. What Agent Observability additionally requires

**[Agent Observability](https://grafana.com/products/cloud/agent-observability/)
is not wired up here, and GenAI spans alone will not wire it up.** Verified
against the live stack:

```bash
gcx agento11y agents list          # => []
gcx agento11y conversations list   # => []
```

Empty, while `gen_ai_*` traces and metrics for the same runs are in Tempo and
Prometheus. The product takes **two channels**, and this deployment has one:

| Channel | Carries | Configured by | Here |
| :--- | :--- | :--- | :--- |
| OTel | traces, metrics | `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS` | **yes** |
| Generation ingest | generations, conversations, the agent catalog | `AGENTO11Y_ENDPOINT`, `AGENTO11Y_PROTOCOL=http`, `AGENTO11Y_AUTH_MODE=basic`, `AGENTO11Y_AUTH_TENANT_ID`, `AGENTO11Y_AUTH_TOKEN` | **no** |

The second channel needs the Agent Observability SDK making explicit generation
calls — it is not a span exporter, and no amount of OTel configuration produces
it. `AGENTO11Y_PROTOCOL=http` and `AGENTO11Y_AUTH_MODE=basic` are required
rather than optional against Cloud: the SDK defaults are grpc and no-auth,
which return a **silent 401**.

So conversation replay, per-agent cost attribution and evaluations are
unavailable here, and would be a real piece of work rather than a config flag.
What *is* available is everything in §4a. That includes
`gen_ai_invoke_agent_*`, with the limit §4a spells out: it describes the one
agent ADK actually invokes, and its tool-call count is 0 by construction
because the two agents that declare tools never run through ADK.

### What the product adds, if that work is done

The reason it might be worth doing:

- **Conversation replay.** Prompts, tool calls and responses in sequence, so a
  Wrap Rescue run can be read back as *how it reached that memo* rather than as
  a span tree to interpret.
- **Cost and token tracking** by agent and run. "Which model is this demo
  spending on" is already answered by `gen_ai_client_token_usage` on the AI
  cost dashboard (§4b); what the product adds is attribution to the agent and
  the conversation that spent it.
- **Evaluations and guards** on live traffic: hallucination and unsafe-output
  detection, and quality regression tracking across prompts, models and agent
  versions.

**None of this is configured here** — it all sits behind the generation-ingest
channel in §3.1, and the evaluators would additionally need defining against
real runs. Worth knowing the capability exists before building anything
equivalent by hand.

### Cost

The free tier is **30k generations and 25M tokens per month**, which this
project is nowhere near — a demo run makes a handful of Gemini calls. Beyond
it, Pro starts at $1.50 per 1k generations plus a $19/month platform fee, and
evaluations are billed separately at $2 per 1M tokens.

So the span export is free at this scale, and turning on evaluations is the
decision with a price attached, not the instrumentation.

### What was given up

OpenLIT's provider-agnostic enrichment, which was never used here — this app
calls one provider. Nothing in the agents' behaviour depends on it, and
`google-adk` reaches Gemini through `google-genai`, so the model calls inside an
agent run are still traced.

Message content is **not** captured by default, which is the right default when
prompts carry unreleased screenplay text. Set
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` deliberately if that
changes. `CINESPINE_DISABLE_GENAI_TELEMETRY=1` turns instrumentation off.

---

## 4. Metrics

There are **two metric systems here, and only one of them reaches Grafana.**
Worth stating plainly, because the names look alike and the distinction is
invisible from a dashboard that happens to be querying the half that works.

### 4a. OpenTelemetry metrics — exported

A `MeterProvider` with a `PeriodicExportingMetricReader` pushes over the same
OTLP endpoint as traces and logs, on a 60s interval. These are counters and
histograms read on dashboards, not alert inputs, so halving the default 30s
export volume costs nothing at that resolution.

This was missing until 2026-09-03. Spans and logs had exporters; metrics had
none, so everything this process measured stayed in the process. **The gap was
invisible precisely because the traces were arriving** — the pipeline looked
configured, and a Prometheus query for `gen_ai_*` returned an empty vector while
Tempo held the matching spans. Nothing was broken enough to log an error.

Push rather than scrape, because nothing scrapes a Cloud Run service: it has no
stable address to be scraped at, and a scaled-to-zero instance is not there to
answer. The exporter carries them out instead.

What arrives, verified in Grafana Cloud Prometheus under `job="cinespine-backend"`:

```
gen_ai_client_token_usage_{sum,count,bucket}              # by model
gen_ai_client_operation_duration_seconds_{sum,count,bucket}
gen_ai_invoke_agent_duration_seconds_{sum,count,bucket}
gen_ai_invoke_agent_inference_calls_{sum,count,bucket}
gen_ai_invoke_agent_tool_calls_{sum,count,bucket}
```

The `gen_ai_invoke_agent_*` family is the agent dimension rather than the model
one — duration, inference calls and tool calls **per agent run**, from ADK's own
instrumentation without extra wiring.

It would be the data behind "which agent is expensive, and whether it is the
model or the tool loop", except that **it describes one agent out of three**.
`WrapRescueAgent` and `AssistantEditorQueueAgent` construct an ADK `Runner` and
never call it, so ADK never invokes them and records nothing; the only name that
appears is `wrap_rescue_handoff_agent`, the inline agent that drafts the memo.
Confirmed against thirty days of Grafana Cloud, not inferred:

```bash
gcx metrics query 'count by (gen_ai_agent_name) (gen_ai_invoke_agent_duration_seconds_count)' --since 30d
# => one series: wrap_rescue_handoff_agent
```

The instrumentation is correct and is reporting the truth. See
[references/findings/agent-telemetry-coverage.md](../references/findings/agent-telemetry-coverage.md).

### 4b. Business metrics — served, not exported

`GET /api/metrics` serves the Prometheus exposition format. These are
`prometheus_client` objects, a **separate library from the OTel meter provider
above**, so the exporter in 4a does not carry them. They are reachable by
scrape or by hand and are currently absent from Grafana; closing that needs
either a scrape target or a prometheus→OTel bridge.

Verified live:

```
cinespine_active_discrepancies      # by production, shoot_day, severity, type
cinespine_ingested_events_total     # by department, axis
cinespine_parser_rejections_total   # by doc_type, error_type
cinespine_sse_active_connections    # by user_role
```

Also defined, and emitted once the paths that produce them run:
`cinespine_llm_tokens_consumed_total`, `cinespine_llm_inference_duration_seconds`,
`cinespine_ai_cache_hits_total`, `cinespine_department_sync_lag_seconds`. The
first two no longer have a reader anywhere — the dashboard that queried them
was moved onto `gen_ai_*` below — so they are emitted into nothing.

#### The dashboard that queried the wrong half

This is exactly the trap the split is written down to prevent, and the
`AI Cost & Observability (CineSpine)` dashboard fell into it: all four of its
original panels queried `cinespine_*` — tokens consumed, inference latency p95,
cache hit ratio — so every one returned an empty vector, and an empty
timeseries panel is indistinguishable from a quiet system.

**Fixed on 2026-09-03.** The dashboard now reads `gen_ai_client_token_usage`
and `gen_ai_client_operation_duration_seconds`, which are exported. Two things
that were not obvious while rewriting it:

- The hand-placed `cinespine_llm_tokens_consumed_total` counter exists at
  **two** call sites (`character_ai.py`, `google_cloud.py`) and records
  `total_token_count` only. `gen_ai_client_token_usage` covers every
  google-genai call and splits input from output. Output is priced far above
  input, so a dollar figure derived from a total-token counter is wrong by a
  factor that moves with the mix — precise-looking and unfalsifiable.
- Adding the two token types requires aggregating each side first. Written the
  obvious way, `rate(...{type="input"}) + rate(...{type="output"})` matches on
  every label including `gen_ai_token_type`, finds no partner, and returns an
  **empty vector** — the same silent failure the panels were just rescued from.
  Verified: the naive form returns 0 series against live data, the
  `sum by (gen_ai_request_model)` form returns the model.

Cost is an estimate — token counts times a dashboard variable. Nothing here
carries dollars. Grafana's packaged AI Observability dashboards do have cost
panels, but they query `gen_ai_usage_cost_USD_sum`, which is emitted by the
**OpenLIT SDK** (§3) computing spend in-process from a bundled pricing file.
Installing that integration against this stack lights up its latency panels and
leaves the cost and token ones empty.

The cache-hit-ratio panel still reads `cinespine_ai_cache_hits_total`, because
the GenAI conventions have no equivalent: a cache hit never reaches the SDK, so
instrumentation that wraps the SDK cannot see it.

**The latency panels are means, not p95, and that is deliberate.** p95 is the
better question and the wrong query at this volume. A demo makes a handful of
model calls and one agent run, so the bucket counters are flat across any
sensible rate window; `rate()` returns 0 for every bucket, and
`histogram_quantile` of all-zero buckets is `NaN`. The panel renders blank —
indistinguishable from no traffic, which is the failure this whole section
exists to prevent. Measured on a real Wrap Rescue run: the p95 form returned
`NaN` where `sum / count` returned 1.20s. Switch to p95 once calls are
continuous enough to move the buckets.

`gen_ai_invoke_agent_*` is recorded by ADK itself in
`google/adk/telemetry/_metrics.py`, not by the google-genai instrumentation.
Verified on a real run:

```
gen_ai_invoke_agent_duration_seconds_count{gen_ai_agent_name="wrap_rescue_handoff_agent"} 1
gen_ai_invoke_agent_duration_seconds_count{gen_ai_agent_name="wrap_rescue_handoff_agent",
                                           error_type="DefaultCredentialsError"} 1
```

Two things that read as a surprise and are not.

ADK adds `error_type` to failed invocations, which **splits the series** —
aggregating by `gen_ai_agent_name` alone folds failures back in, which is what
the panels do, since a run that died still took time.

And `gen_ai_invoke_agent_tool_calls` is **0**, for a larger reason than it first
appears. It is not that this one agent happens to have no tools: the two agents
that do have tools never execute through ADK at all, and the memo agent that
does is given none. Both `WrapRescueAgent` and `AssistantEditorQueueAgent`
declare tools in `super().__init__(tools=[...])` that ADK never dispatches —
their step loops call those methods directly. So the count is right, and will
stay 0 until tool use moves inside an agent that is actually invoked.

### 4c. The local stack needs both intakes

`docker compose --profile observability up -d` runs Prometheus and Grafana
locally, and the same split bites there in two ways that were both silently
broken until 2026-09-03:

- **Scrape path.** The config had no `metrics_path`, so it scraped
  `/metrics`. The app serves `/api/metrics` — the route is on a router with
  `prefix="/api"` and nothing is mounted at the root. The target reported
  healthy at the TCP level and 404'd on every scrape, so *no* `cinespine_*`
  series ever existed locally and every local dashboard was empty.
- **Push path.** `gen_ai_*` is pushed by the OTel meter provider and is never
  scraped, so a plain Prometheus never sees it. `--web.enable-otlp-receiver`
  opens `/api/v1/otlp/v1/metrics` to receive it. Point the backend at it with
  `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`. That overrides the metrics signal
  only, so traces and logs keep going wherever `OTEL_EXPORTER_OTLP_ENDPOINT`
  points. The `verify-observability` skill sets **both** to localhost on
  purpose: a laptop run then pushes nothing into the production stack, and the
  traces and logs 404 against local Prometheus, which is harmless.

A fresh process exposes **no** `cinespine_*` samples at all — every one of them
is labelled, and a labelled `prometheus_client` metric has no series until the
first `.labels(...)` call. Only the `# HELP` lines are there. So a scrape can be
genuinely working and still look identical to the 404 it replaced until demo
traffic runs:

```bash
curl -s http://localhost:8000/api/metrics | grep -c '^cinespine_'   # 0 on a cold process, ~50 after /api/events/demo
```

`cinespine_active_discrepancies` is labelled by production **and shoot day** on
purpose: without the day, the second day observed overwrites the first and the
board shows whichever day was opened last while looking like a total.

---

## 5. Browser telemetry, and the failure it hides

Faro initialises in `main.tsx` only when `VITE_GRAFANA_FARO_URL` is set. That
variable is inlined by Vite **at build time**, so it must be present in the
build — setting it on the Cloud Run service does nothing, because the bundle is
already written and `main.tsx` silently skips Faro when the URL is absent.

```dockerfile
ARG VITE_GRAFANA_FARO_URL
ENV VITE_GRAFANA_FARO_URL=$VITE_GRAFANA_FARO_URL
```

### Allowed origins are the thing that breaks

**Every origin serving the app must be in the collector's allowed-origins
list.** A rejected CORS preflight is invisible from both ends at once: the
frontend appears not to send, and Grafana appears not to receive. In the browser
it surfaces only as `TypeError: Failed to fetch`.

Cloud Run issues **two** hostnames for one service, and both serve the app:

```
https://cinespine-35447568692.europe-west4.run.app
https://cinespine-ncechpwcia-ez.a.run.app
```

A browser's `Origin` is whatever host the page was loaded from, so both need
allowlisting. With only the first added, loading the app on the second lost all
telemetry silently — same page, same SDK, same collector, one origin returning
`202` and the other throwing `Failed to fetch`.

Check an origin without opening a browser:

```bash
curl -s -i -X OPTIONS "$VITE_GRAFANA_FARO_URL" -H "Origin: https://your-app-origin" -H "Access-Control-Request-Method: POST" | grep -i access-control-allow-origin
```

An `Access-Control-Allow-Origin` line means it is allowed. **No line means
blocked** — the collector still answers `204`, so the status code tells you
nothing.

---

## 6. Verifying it end to end

Backend, from the logs: find any request line and confirm it carries
`trace_id=` and `trace_sampled=True`.

Metrics:

```bash
curl -s https://cinespine-35447568692.europe-west4.run.app/api/metrics | grep -c '^cinespine_'
```

Browser, from the app's own console — counts requests in the current document
only, so nothing historical leaks in:

```js
performance.getEntriesByType('resource')
  .filter(e => e.name.includes('faro-collector'))
  .map(e => e.responseStatus)   // expect [202, 202, ...]
```

A fresh page load produces two collector requests on its own, before any manual
push: the page-view and web-vitals instrumentation firing.

> Do not trust `read_console_messages` or a devtools console that has not been
> hard-reloaded when checking this. Both retain buffers across reloads and will
> replay CORS errors from before a fix, which reads as though nothing changed.
