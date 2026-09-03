# 📡 Observability

Telemetry reaches Grafana Cloud from three places: the backend exports
OpenTelemetry traces and logs and exposes Prometheus metrics for scraping, the
GenAI instrumentation emits spans for the agents' model calls, and the browser
sends RUM through Faro.

The agents' spans follow the OpenTelemetry **GenAI semantic conventions**, which
is what [Grafana Cloud Agent
Observability](https://grafana.com/docs/grafana-cloud/observe-and-act/agent-observability/)
consumes — it is built on OpenTelemetry and reads LLM generations, tool calls,
token usage and cost from exactly that shape. No separate SDK or exporter: the
same OTLP endpoint carries it.

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
sat on the import path ahead of uvicorn binding a socket, and Replit autoscale
gave up on the deployment with *"the application failed to open a port in
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
> ~1.6s and answer `/health` in ~2s. The 45s import that broke the Replit
> deployment was fixed earlier by backgrounding, and separately by dropping the
> `dev` and `hackathon` extras from the production image. Those two changes did
> the deployment work; this one is about what ships and when it attaches.

### What [Agent Observability](https://grafana.com/products/cloud/agent-observability/) adds on top of the spans

Emitting GenAI semantic-convention spans is the whole integration — but the
product does more with them than draw a trace:

- **Conversation replay.** Prompts, tool calls and responses in sequence, so a
  Wrap Rescue run can be read back as *how it reached that memo* rather than as
  a span tree to interpret.
- **Cost and token tracking** by agent, run and model — the natural home for
  "which model is this demo actually spending on", which the
  `cinespine_llm_tokens_consumed_total` metric only answers in aggregate.
- **Evaluations and guards** on live traffic: hallucination and unsafe-output
  detection, and quality regression tracking across prompts, models and agent
  versions.

**None of the evaluation features are configured here.** They are opt-in and
would need evaluators defined against real runs; this deployment sends spans
and nothing more. Worth knowing the capability exists before building anything
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
one — duration, inference calls and tool calls **per agent run**. That is the
data behind "which agent is expensive, and whether it is the model or the tool
loop", and it comes from ADK's own `invoke_agent` spans without extra wiring.

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
`cinespine_ai_cache_hits_total`, `cinespine_department_sync_lag_seconds`.

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
