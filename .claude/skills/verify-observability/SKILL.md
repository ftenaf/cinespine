---
name: verify-observability
description: Verify a CineSpine metrics, dashboard or telemetry change against a running stack rather than against configuration. Use when editing grafana/dashboards/*, grafana/prometheus.yml, backend/app/core/telemetry.py, any prometheus_client metric, OTel exporter settings, or when asked whether a metric "actually reaches Grafana". Covers the local OTLP loop and querying production with gcx.
---

# Verifying observability changes

Every defect found in this area was a configuration that read correctly. A
scrape target can be `up` and 404 every request; a panel can return an empty
vector that renders identically to a healthy, quiet system. **Do not report an
observability change as working on the strength of the diff.**

Read `docs/OBSERVABILITY.md` first. The split it describes — `gen_ai_*` pushed,
`cinespine_*` scraped — decides which half of this procedure you need.

## 1. Bring up the stack

Prometheus scrapes `host.docker.internal:8000`, so the **backend runs on the
host**, not in compose. Only the dependencies go in Docker.

```bash
docker compose up -d clickhouse mcp-clickhouse
docker compose --profile observability up -d prometheus
```

If compose fails with `network ... not found`, a container is holding a stale
network id. `docker rm -f cinespine-clickhouse cinespine-mcp-clickhouse` and
re-run; do not `docker compose down -v`, which discards the ClickHouse volume.

## 2. Start the backend with the overrides

`.env` is written for the container and `load_dotenv()` does **not** override
the process environment, so exporting these wins. Three of them are wrong for a
host run by construction:

```bash
export CLICKHOUSE_HOST=localhost CLICKHOUSE_PORT=8123 \
       CLICKHOUSE_USERNAME=default CLICKHOUSE_PASSWORD=password CLICKHOUSE_SECURE=false
# .env points this at ClickHouse Cloud, which 401s
export CLICKHOUSE_MCP_URL=http://localhost:4200/mcp
# .env points this at the container mount path /app/gcp-credentials.json
export GOOGLE_APPLICATION_CREDENTIALS="C:/Users/paco/AppData/Roaming/gcloud/application_default_credentials.json"
# metrics to the local receiver; traces/logs will 404 here, which is fine
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:9090/api/v1/otlp
export OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://localhost:9090/api/v1/otlp/v1/metrics

nohup .venv/Scripts/python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 > bv.log 2>&1 &
sleep 50   # import is slow; ~45s before it binds
grep -E "startup complete|bind" bv.log
```

**Confirm it actually bound.** `pkill -f uvicorn` does not work here — it
reports success and kills nothing, so a stale backend keeps port 8000 and the
new process dies with `[Errno 10048]` while your requests silently hit the old
one with none of the config above. Kill by port:

```bash
PID=$(netstat -ano | grep ":8000.*LISTENING" | awk '{print $5}' | head -1)
taskkill //F //PID $PID
```

## 3. Drive real traffic

A cold process exposes **no** `cinespine_*` samples — every metric is labelled,
and a labelled `prometheus_client` metric has no series until its first
`.labels()` call. Only `# HELP` lines are there, so a working scrape and a 404
look identical until something runs.

```bash
curl -s -X POST http://localhost:8000/api/demo/wipe
curl -s http://localhost:8000/api/events/demo
curl -s http://localhost:8000/api/wrap-rescue/demo          # ADK agent + Gemini
curl -s -X POST http://localhost:8000/api/script/parse \
     -H 'Content-Type: application/json' \
     -d '{"script_text":"INT. A - NIGHT\n\nMARA\nHello.\n","title":"Probe","production_id":"DEMO_PRODUCTION"}'
curl -s http://localhost:8000/api/metrics | grep -c '^cinespine_'   # expect ~50, not 0
```

## 4. Query, after waiting for the export

The metric reader exports on a **60s interval**, so wait ~70s before querying or
you will conclude a working exporter is broken.

```bash
curl -s "http://localhost:9090/api/v1/targets" | python -c "
import json,sys
for t in json.load(sys.stdin)['data']['activeTargets']: print(t['scrapeUrl'],'->',t['health'],t.get('lastError',''))"

curl -s "http://localhost:9090/api/v1/label/__name__/values" | python -c "
import json,sys
print([x for x in json.load(sys.stdin)['data'] if x.startswith(('gen_ai','cinespine_'))])"

curl -s --get http://localhost:9090/api/v1/query --data-urlencode 'query=<the panel expr>' | python -c "
import json,sys
d=json.load(sys.stdin)
r=d['data']['result'] if d['status']=='success' else []
print(len(r),'series'); [print(s['metric'],'=',s['value'][1]) for s in r]"
```

**Run each changed panel's exact expression.** Three failure modes that all
render as a blank panel and none of which error:

- **0 series.** A binary op whose sides differ on a label — `rate(x{type="input"})
  + rate(x{type="output"})` matches on `gen_ai_token_type`, finds no partner,
  returns nothing. Aggregate each side first.
- **NaN.** `histogram_quantile` over `rate()` of flat bucket counters. Demo
  traffic is far too sparse to move them; use `sum / count` instead.
- **Empty vector.** Querying `cinespine_*` where only `gen_ai_*` is exported, or
  the reverse.

## 5. Check production with gcx

Local Prometheus proves the query; only Grafana Cloud proves the deployment.

```bash
/e/dev/tools/gcx.exe metrics query 'count by (gen_ai_agent_name) (gen_ai_invoke_agent_duration_seconds_count)' --since 30d
/e/dev/tools/gcx.exe metrics query 'count by (__name__) ({__name__=~"cinespine_.*"})' --since 30d   # expect empty
```

`gcx` is on the Windows user PATH but **not** on Git Bash's; call it by full
path. `--jq '<expr>'` shapes the output without external parsing.

## 6. Tear down

```bash
PID=$(netstat -ano | grep ":8000.*LISTENING" | awk '{print $5}' | head -1); taskkill //F //PID $PID
docker compose --profile observability down
rm -f bv.log
```

The Prometheus service mounts no data volume, so synthetic series pushed during
verification disappear with the container. Check `git status` for scratch files
before finishing.

## Pushing a synthetic metric

To test a query shape without waiting for real traffic, record against the same
instrument the app uses and push to `http://localhost:9090/api/v1/otlp/v1/metrics`.
Record in a **loop with a delay** — a single push makes the first sample
Prometheus sees also the last, and `increase()` over that is 0 however large the
value. Attribute keys must match the instrumentation exactly; for token usage
they are `gen_ai.token.type`, `gen_ai.request.model`, `gen_ai.system`,
`gen_ai.operation.name`.
