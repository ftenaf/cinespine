---
name: verify-observability
description: Verify a CineSpine metrics, dashboard or telemetry change against a running stack rather than against configuration. Use when editing grafana/dashboards/*, grafana/prometheus.yml, backend/app/core/telemetry.py or any business metric in it, OTel exporter settings, or when asked whether a metric "actually reaches Grafana", or to push a dashboard to Grafana Cloud. Covers the local OTLP loop, querying production with gcx, and pushing grafana/dashboards/*.json to Grafana Cloud with gcx.
---

# Verifying observability changes

Every defect found in this area was a configuration that read correctly. A
scrape target can be `up` and 404 every request; a panel can return an empty
vector that renders identically to a healthy, quiet system. **Do not report an
observability change as working on the strength of the diff.**

Read `docs/OBSERVABILITY.md` first. Every metric family is OTel and pushed
since 2026-09-04; §4 there records the scrape-versus-push split that used to
exist, which is where every defect in this area came from.

## 1. Bring up the stack

The backend pushes to Prometheus's OTLP receiver on `localhost:9090`, so the
**backend runs on the host**, not in compose. Only the dependencies go in
Docker.

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
       CLICKHOUSE_USER=default CLICKHOUSE_PASSWORD=password CLICKHOUSE_SECURE=false
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

A cold process exports **no** `cinespine_*` series — an instrument with no
recordings has no data points to send — so a working pipeline and a broken one
look identical until something runs.

```bash
curl -s -X POST http://localhost:8000/api/demo/wipe
curl -s http://localhost:8000/api/events/demo
curl -s http://localhost:8000/api/wrap-rescue/demo          # ADK agent + Gemini
curl -s -X POST http://localhost:8000/api/script/parse \
     -H 'Content-Type: application/json' \
     -d '{"script_text":"INT. A - NIGHT\n\nMARA\nHello.\n","title":"Probe","production_id":"DEMO_PRODUCTION"}'
```

## 4. Query, after waiting for the export

The metric reader exports on a **60s interval**, so wait ~70s before querying or
you will conclude a working exporter is broken.

```bash
curl -s "http://localhost:9090/api/v1/label/__name__/values" | python -c "
import json,sys
print([x for x in json.load(sys.stdin)['data'] if x.startswith(('gen_ai','cinespine_','http_server'))])"

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
- **Empty vector.** Querying a name nothing emits. The old scrape-only
  `cinespine_*` and the deleted `cinespine_llm_*` pair are the historical
  examples; check the name against the label-values query above.

## 5. Check production with gcx

Local Prometheus proves the query; only Grafana Cloud proves the deployment.

```bash
/e/dev/tools/gcx.exe metrics query 'count by (gen_ai_agent_name) (gen_ai_invoke_agent_duration_seconds_count)' --since 30d
/e/dev/tools/gcx.exe metrics query 'count by (__name__) ({__name__=~"cinespine_.*"})' --since 30d   # expect empty
```

`gcx` is on the Windows user PATH but **not** on Git Bash's; call it by full
path. `--jq '<expr>'` shapes the output without external parsing.

## 6. Push the dashboard to Grafana Cloud

`grafana/dashboards/*.json` is provisioned into the **local** Grafana only.
Nothing carries it to Grafana Cloud, so a panel fix that is verified locally and
committed is still the old panel in production until it is pushed. The
`ai_cost_observability` dashboard sat one commit stale in Cloud for exactly this
reason. The repo file is the source of truth; a push overwrites edits made in
the Cloud UI.

The file is the classic dashboard model, which the API calls `v1`. The server
prefers `v2`, so pass `--api-version dashboard.grafana.app/v1` on **both** the
`get` and the `update`, or the update fails with `400 ... does not match the
expected API version`. The update also needs the `metadata.resourceVersion`
from a fresh `get`; that is the optimistic-concurrency token.

```bash
G=/e/dev/tools/gcx.exe
DASH=ai_cost_observability                      # the "uid" field in the JSON
M="$LOCALAPPDATA/Temp/cinespine-dash-manifest.json"

$G dashboards get $DASH --api-version dashboard.grafana.app/v1 -o json \
  | grep -v '^{"class":"hint"' | python -c "
import json,sys
m=json.load(sys.stdin); spec=json.load(open('grafana/dashboards/$DASH.json'))
spec['uid']=m['metadata']['name']
if 'schemaVersion' in m['spec']: spec['schemaVersion']=m['spec']['schemaVersion']
meta={k:m['metadata'][k] for k in ('name','namespace','resourceVersion')}
json.dump({'apiVersion':m['apiVersion'],'kind':'Dashboard','metadata':meta,'spec':spec},open(sys.argv[1],'w'))" "$M"

$G dashboards update $DASH --api-version dashboard.grafana.app/v1 -f "$M"
rm -f "$M"
```

If the `get` returns not-found the dashboard has never been pushed: drop
`resourceVersion` from `metadata` and use `dashboards create -f` instead.

**Verify the stored copy, then look at it.** `updated` in the mutation output
only proves the request was accepted.

```bash
$G dashboards get $DASH --api-version dashboard.grafana.app/v1 -o json \
  | grep -v '^{"class":"hint"' | python -c "
import json,sys
c=json.load(sys.stdin)['spec']; l=json.load(open('grafana/dashboards/$DASH.json'))
same=len(c['panels'])==len(l['panels']) and all(
  a['title']==b['title'] and a['targets'][0]['expr']==b['targets'][0]['expr']
  for a,b in zip(c['panels'],l['panels']))
print('MATCHES LOCAL:',same); print([p['title'] for p in c['panels']])"

$G dashboards snapshot $DASH --since 24h --width 1400 --height 900 --output-dir "$LOCALAPPDATA/Temp"
```

Open the PNG. Against production expect every `gen_ai_*` panel to carry data
after any Wrap Rescue or parse traffic in the range, and the **AI Cache Hit
Ratio panel to read "No data"**: it queries `cinespine_*`, which nothing on
Cloud Run scrapes. That blank is the deployment, not the push.

The panels name no datasource, so they resolve to the stack's default. Today
that is `grafanacloud-prom`; check with `gcx datasources list` if a pushed
dashboard renders empty everywhere.

## 7. Tear down

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
