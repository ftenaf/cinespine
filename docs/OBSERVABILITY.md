# 📡 Observability

Four signals reach Grafana Cloud, from three places: OpenTelemetry traces and
logs from the backend, Prometheus metrics it exposes for scraping, OpenLIT
spans covering the agents and their model calls, and Faro RUM from the browser.

Everything here is verified against the deployed service rather than inferred
from configuration.

---

## 1. What ships where

| Signal | Source | Transport | Set by |
| :--- | :--- | :--- | :--- |
| Traces | FastAPI, httpx | OTLP HTTP | `OTEL_EXPORTER_OTLP_ENDPOINT` |
| Logs | Python `logging`, trace-correlated | OTLP HTTP | same endpoint |
| Metrics | `prometheus_client` at `/api/metrics` | scrape | always on |
| Agent / GenAI spans | OpenLIT | OTLP HTTP | inherits the OTel config |
| Browser RUM | `@grafana/faro-web-sdk` | Faro collector | `VITE_GRAFANA_FARO_URL` |

`backend/app/core/telemetry.py` wires the first four; `frontend/src/main.tsx`
initialises the fifth.

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

## 3. Agent observability, via OpenLIT

`openlit.init()` instruments the GenAI client libraries, which is what makes
the two agents legible: **Wrap Rescue** and the **Assistant Editor Queue** both
run on Google ADK and call Gemini, and without it a run is a single opaque HTTP
span.

### It must not run on the import path

`openlit.init()` takes **~34 seconds**. It patches the client library of every
provider it supports — which is why `anthropic` and `openai` appear in this
app's import profile despite being unused — and it does that work before
returning.

Called inline it ran at import time, ahead of uvicorn binding a socket, and a
45-second import is longer than a platform will wait for a port. Cloud Run
rejected the deployment with *"the application failed to open a port in time"*,
which reads like a crash and is not one: the process was healthy and still
importing.

It now runs on a daemon thread. The startup log shows the ordering, which is
the whole point:

```
06:14:58.408  Uvicorn running on http://0.0.0.0:8000   <- port open
06:14:58.588  openlit init begins                      <- 180ms later
```

The gap costs nothing real — it patches GenAI clients, and nothing calls one in
the first seconds after boot. `CINESPINE_DISABLE_OPENLIT=1` turns it off.

> Import went from 45.6s to 14.4s, and cold start on the Cloud Run image to
> ~2s. That is what made the platform accept the deployment at all, so this is
> a deployment fix as much as an observability one.

---

## 4. Metrics

`GET /api/metrics` serves the Prometheus exposition format. Verified live:

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
