# ☁️ Deploying CineSpine to Cloud Run

One Cloud Run service for the app, built from
[`Dockerfile.cloudrun`](../Dockerfile.cloudrun): FastAPI serves the API under
`/api` and the compiled SPA at everything else, so there is a single origin and
no CORS between the two halves. ClickHouse itself is ClickHouse Cloud; its MCP
server runs as a second, scale-to-zero Cloud Run service (section 5 — the
hosted MCP is OAuth-only and cannot work headlessly).

Deployed and verified end to end at
`https://cinespine-35447568692.europe-west4.run.app`: three Day 31
discrepancies, three ranked blockers, three requirements filed.

Measured on the built image: **cold start to a healthy `/health` is ~2s**, down
from ~30s under `docker-compose`. Most of that came from dropping `uv run` from
the entrypoint and installing without extras; the rest was moving
GenAI instrumentation off the import path (see `backend/app/core/telemetry.py`).

---

## The one constraint that shapes everything

`spine.db` is the source of truth — productions, requirements, crew,
notifications, tags, screenplays. **Eleven modules write to it**, and Cloud Run's
filesystem is ephemeral and per-instance.

So this deployment pins to a single instance:

```
--min-instances=1 --max-instances=1
```

`max=1` keeps two instances from diverging into two databases. `min=1` keeps the
instance warm so no user pays the cold start, and stops a scale-to-zero from
wiping state. **A revision deploy still resets the database** — reseed with
`GET /api/events/demo`, which is idempotent.

ClickHouse is the analytical mirror, not the source: the app degrades to the
in-memory spine when it is unreachable, so a ClickHouse outage costs analytics
and Wrap Rescue, not the app.

Lifting the single-instance limit means moving those eleven stores to Cloud SQL.
That is a project in its own right, not a step in this one.

---

## 1. One-time project setup

> [!IMPORTANT]
> The first two commands enable billable APIs and grant IAM roles. Both are
> yours to approve — read them before running.

```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com --project=cinespine
```

Confirm the region carries Cloud Run once the API is on (this deployment assumes
`europe-west4`, matching `GOOGLE_CLOUD_LOCATION` so Vertex calls stay in-region):

```bash
gcloud run regions list --project=cinespine --filter="name~europe-west" --format="value(name)"
```

### Artifact Registry

```bash
gcloud artifacts repositories create cinespine --repository-format=docker --location=europe-west4 --description="CineSpine container images" --project=cinespine
```

### Runtime service account

Cloud Run should authenticate as a service account with Application Default
Credentials, rather than the `GCP_CREDENTIALS_JSON` key file `start.sh` writes
to disk for Replit. Nothing on disk, one fewer secret.

```bash
gcloud iam service-accounts create cinespine-run --display-name="CineSpine Cloud Run runtime" --project=cinespine
```

Grant it only what the app uses — Vertex, secret reads, and Cloud Logging:

```bash
gcloud projects add-iam-policy-binding cinespine --member="serviceAccount:cinespine-run@cinespine.iam.gserviceaccount.com" --role="roles/aiplatform.user"
```

```bash
gcloud projects add-iam-policy-binding cinespine --member="serviceAccount:cinespine-run@cinespine.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
```

```bash
gcloud projects add-iam-policy-binding cinespine --member="serviceAccount:cinespine-run@cinespine.iam.gserviceaccount.com" --role="roles/logging.logWriter"
```

Add `roles/storage.objectAdmin` only if you keep the GCS document archive on.

### Secrets

Four values should not sit in the service's environment. Create each from a
file or stdin rather than an argument, so they stay out of your shell history:

```bash
printf '%s' "$GEMINI_API_KEY" | gcloud secrets create cinespine-gemini-api-key --data-file=- --project=cinespine
```

Repeat for `cinespine-clickhouse-password`, `cinespine-clickhouse-mcp-token`,
and `cinespine-otel-headers`.

---

## 2. Environment

`OTEL_EXPORTER_OTLP_HEADERS` contains both `=` and `,`, which `--set-env-vars`
cannot express — that one is a secret below. The rest go in a YAML file, which
avoids the delimiter problem entirely.

Create `deploy/cloudrun.env.yaml` (gitignored — it names your ClickHouse host):

```yaml
GOOGLE_GENAI_USE_VERTEXAI: "TRUE"
GOOGLE_CLOUD_PROJECT: "cinespine"
GOOGLE_CLOUD_LOCATION: "europe-west4"
CINESPINE_WRAP_RESCUE_MODEL: "gemini-2.5-flash"

# ClickHouse Cloud. SECURE moves the port to 8443 on its own.
#
# "1" is correct here and wrong on the MCP service, which wants the literal
# "true" -- same variable name, two parsers. Section 5 has the detail; it cost
# a deploy to find.
CLICKHOUSE_HOST: "<your-instance>.europe-west4.gcp.clickhouse.cloud"
CLICKHOUSE_SECURE: "1"
CLICKHOUSE_USERNAME: "default"

# The self-hosted MCP service from section 5, not ClickHouse Cloud's hosted
# endpoint -- see there for why the hosted one cannot work headlessly. Fill in
# the URL Cloud Run returns for cinespine-mcp after deploying it.
CLICKHOUSE_MCP_URL: "https://cinespine-mcp-<hash>-ew.a.run.app/mcp"

# 30 rather than the 10s default. That service scales to zero, and a cold start
# on Cloud Run measured ~21s before it answered -- far longer than the ~4s the
# same image takes locally, because the image is pulled as well as started.
CLICKHOUSE_MCP_TIMEOUT: "30"

OTEL_EXPORTER_OTLP_ENDPOINT: "https://otlp-gateway-prod-eu-west-2.grafana.net/otlp"
OTEL_EXPORTER_OTLP_PROTOCOL: "http/protobuf"

# Explicit rather than relying on the working directory.
CINESPINE_DB_PATH: "/app/spine.db"
```

---

## 3. Build and deploy

`VITE_GRAFANA_FARO_URL` must be a **build** arg. Vite inlines `VITE_*` at build
time, so setting it on the service does nothing — the bundle is already written,
and `main.tsx` silently skips Faro when the URL is absent.

```bash
gcloud builds submit --tag=europe-west4-docker.pkg.dev/cinespine/cinespine/app:v0.7.0 --project=cinespine
```

`gcloud builds submit` does not forward build args, so either build locally and
push:

```bash
docker build -f Dockerfile.cloudrun --build-arg VITE_GRAFANA_FARO_URL="$VITE_GRAFANA_FARO_URL" -t europe-west4-docker.pkg.dev/cinespine/cinespine/app:v0.7.0 .
```

```bash
docker push europe-west4-docker.pkg.dev/cinespine/cinespine/app:v0.7.0
```

…or add a `cloudbuild.yaml` that passes `--build-arg`. Local build is fine while
this is one service and one person deploying.

Then deploy:

```bash
gcloud run deploy cinespine --image=europe-west4-docker.pkg.dev/cinespine/cinespine/app:v0.7.0 --region=europe-west4 --project=cinespine --service-account=cinespine-run@cinespine.iam.gserviceaccount.com --min-instances=1 --max-instances=1 --cpu=2 --memory=2Gi --timeout=3600 --env-vars-file=deploy/cloudrun.env.yaml --set-secrets=GEMINI_API_KEY=cinespine-gemini-api-key:latest,CLICKHOUSE_PASSWORD=cinespine-clickhouse-password:latest,CLICKHOUSE_MCP_AUTH_TOKEN=cinespine-clickhouse-mcp-token:latest,OTEL_EXPORTER_OTLP_HEADERS=cinespine-otel-headers:latest --allow-unauthenticated
```

Notes on the flags that are not obvious:

- **No `--port`.** Cloud Run's default 8080 matches the image's `${PORT:-8080}`.
- **`--timeout=3600`** for the SSE stream at `/api/events/subscribe`. The default
  300s would drop live connections every five minutes.
- **`--memory=2Gi`** because the import pulls the Google Cloud and ADK client
  libraries; 512Mi is not enough.
- **`--allow-unauthenticated`** makes the service public, which a browser SPA
  needs. Drop it and put IAP in front if this should not be.

---

## 4. After the first deploy

**Add the new origin to Faro.** In Grafana Frontend Observability, add the
service URL to allowed origins. Until you do, the browser blocks every beacon
and it looks identical from both ends — the frontend appears not to send and
Grafana appears not to receive. See [CLICKHOUSE_MCP.md](CLICKHOUSE_MCP.md) for
the same class of silent failure on the backend side.

**Seed the demo**, since a fresh revision starts with an empty `spine.db`:

```bash
curl -s "$(gcloud run services describe cinespine --region=europe-west4 --project=cinespine --format='value(status.url)')/api/events/demo"
```

**Verify**, asserting on numbers rather than HTTP 200s — this stack has a habit
of reporting success while doing nothing:

```bash
curl -s "<SERVICE_URL>/api/discrepancies?production_id=DEMO_PRODUCTION&shoot_day=31"
```

Expect **3** discrepancies. Then `GET /api/wrap-rescue/demo` and expect **3**
blockers and **3** requirement actions, with every `run_select_query` in
`tool_calls` showing `rows > 0`. All calls `ok=true` with `rows=0` everywhere is
the signature of a broken MCP transport, not a quiet day.

---

## 5. The MCP server, self-hosted as a second service

`mcp-clickhouse` runs as its own Cloud Run service, built from the same
`backend/Dockerfile` that compose uses locally. That is the settled shape: the
same container in both places, one version to reason about, pinned by `uv.lock`.

### Why not ClickHouse Cloud's hosted MCP

The obvious move is to point `CLICKHOUSE_MCP_URL` at
`https://mcp.clickhouse.cloud/mcp` and run nothing. It does not work here, and
the reason is structural rather than a configuration gap.

**ClickHouse Cloud's remote MCP is OAuth 2.0 only — it does not accept API
keys.** On first connection the client opens a browser for the user to sign in,
and access is then scoped to that human's organisations and services. That is a
deliberate design: permissions are checked per user, so the MCP identity can
only ever act as the person who authorised it.

Two things follow. Wrap Rescue runs headless on Cloud Run with nobody at a
browser, so it cannot complete the flow. And `HTTPClickHouseMCPClient` sends a
static `Authorization: Bearer` and implements no OAuth at all. The mismatch is
not a missing token — it is that the hosted endpoint is built for interactive
clients (Claude Code, Cursor) and this is a server.

The open-source server, by contrast, accepts exactly the static bearer this
client already sends.

### Deploying it

Build from `backend/Dockerfile`, which installs `--all-extras` and so carries
`mcp-clickhouse` from the `hackathon` extra:

```bash
docker build -f backend/Dockerfile -t europe-west4-docker.pkg.dev/cinespine/cinespine/mcp:v0.7.0 .
```

```bash
docker push europe-west4-docker.pkg.dev/cinespine/cinespine/mcp:v0.7.0
```

```bash
gcloud run deploy cinespine-mcp --image=europe-west4-docker.pkg.dev/cinespine/cinespine/mcp:v0.7.0 --region=europe-west4 --project=cinespine --service-account=cinespine-run@cinespine.iam.gserviceaccount.com --ingress=all --min-instances=0 --max-instances=2 --port=4200 --memory=1Gi --command=uv --args=run,mcp-clickhouse --set-secrets=CLICKHOUSE_PASSWORD=cinespine-clickhouse-password:latest,CLICKHOUSE_MCP_AUTH_TOKEN=cinespine-clickhouse-mcp-token:latest --set-env-vars=CLICKHOUSE_HOST=<your-instance>.europe-west4.gcp.clickhouse.cloud,CLICKHOUSE_USER=default,CLICKHOUSE_SECURE=true,CLICKHOUSE_PORT=8443,CLICKHOUSE_MCP_SERVER_TRANSPORT=http,CLICKHOUSE_MCP_BIND_HOST=0.0.0.0,CLICKHOUSE_MCP_BIND_PORT=4200 --allow-unauthenticated
```

Then put the URL it prints into `CLICKHOUSE_MCP_URL` in the app's env file,
with `/mcp` on the end, and redeploy the app service.

Flags that differ from the app service, and why:

- **`--min-instances=0`.** This service holds no state, so unlike the app it can
  scale to zero and cost nothing between Wrap Rescue runs. Cold start on Cloud
  Run measured ~21s, which is why `CLICKHOUSE_MCP_TIMEOUT` is 30 above. The 10s
  default would have failed the first call after every idle period.
- **`--command` / `--args`** override the image's `CMD`, which starts the
  CineSpine API rather than the MCP server. Same image, different entrypoint.
- **`--ingress=all` with `--allow-unauthenticated`**, which is not what it
  looks like. See below — `internal` was tried first and does not work without
  more machinery than it is worth here.
- **`CLICKHOUSE_SECURE=true`, not `1`.** This server compares
  `os.getenv("CLICKHOUSE_SECURE", "true").lower() == "true"`, so `1` reads as
  false and it connects over plain HTTP on 8123 to a cluster that only speaks
  TLS on 8443. The app's own client parses the same variable with a tolerant
  flag helper where `1` is correct, so **the two services need different values
  for the same name**. Omitting it entirely would also have worked; the
  explicit value is what broke it.

### On ingress, and why this one is public

`--ingress=internal` is the obvious choice and was the first attempt. It does
not work between two Cloud Run services on its own: the app's outbound call
leaves over the public internet, so the internal-only service refuses it at the
frontend and returns **404** — not 403, so it reads like a missing route rather
than a policy decision.

Making it work means Direct VPC egress on the *caller* (`--network`,
`--subnet`, `--vpc-egress=all-traffic`), and once all traffic goes through the
VPC you need Cloud NAT so Vertex, ClickHouse Cloud and Grafana stay reachable.
That is the right answer for production and more machinery than a demo needs.

So this deployment runs the MCP service public and leans on the bearer token,
which is real rather than decorative: `CLICKHOUSE_MCP_AUTH_DISABLED` is
deliberately **not** set, the server logs `Authentication enabled for HTTP/SSE
transport` at startup, it answers `401` without the header, and every tool it
exposes is read-only.

It is still an endpoint to your cluster on the public internet behind one
static token. Fine while this is a demo; revisit with VPC egress if it outlives
one.

The app service still needs no MCP package of its own — its client is plain
JSON-RPC over httpx, which is why `Dockerfile.cloudrun` installs no extras.

### Why self-hosting is the better answer anyway

Pinning the version is the real argument, independent of OAuth. A hosted
endpoint can change its tool surface underneath you, and this codebase is a
worked example of how that fails silently: the client asked for `run_query` for
a long time against a server that exports `run_select_query`, every call came
back empty, and the agent reported clean days it had never looked at. With the
image pinned by `uv.lock`, that change arrives when you choose to take it.

### Do not health-check this server

`/health` on this build hangs for sixty seconds and then answers 503, with
ClickHouse awake and reachable — and its handler blocks the event loop while it
does. So probing it does not merely misreport a working server: a request sent
straight afterwards queues behind the wedged loop and times out too. The
service's own logs show a `POST /mcp` taking exactly the caller's timeout beside
a `GET /health` taking 60s, while the same `/mcp` call against an idle server
returns in 6ms.

`HTTPClickHouseMCPClient.status()` therefore sends `initialize` instead, which
is the honest question — whether the client can speak MCP to that URL — and the
path every tool call takes. If you add your own monitoring, point it at `/mcp`,
not `/health`.

The tool name is `run_select_query`, not `run_query`, and a failed call answers
HTTP 200 with `isError`. Both are handled, and both are written down in
[CLICKHOUSE_MCP.md](CLICKHOUSE_MCP.md).

### Using the hosted MCP yourself

The hosted endpoint is genuinely useful for *interactive* work — querying your
cluster from Claude Code while debugging. Enable it per service in the Cloud
console (**Connect → MCP**), add it to your MCP client config, and complete the
OAuth in your browser. The token stays in your client; it never reaches this
repo, the deployed service, or an agent's environment. That is a separate
capability from what the app needs, not a substitute for it.
