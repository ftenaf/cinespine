# CineSpine Infrastructure & Alerting Walkthrough

We have successfully finished implementing all outstanding integration features from the plan to complete the Hackathon "Wow" factor.

## 1. Test Suite Restoration (ClickHouse Streaming)

The introduction of native ClickHouse Event Streams via `async_insert=1` broke test mocks because `FakeClickHouse` wasn't absorbing the strict `**kwargs` from `client.insert()`.

- **Mock Signature Fix:** Updated the `insert` signature across the entire test suite (`FakeClickHouse` implementations in multiple test files).
- **Agent Analytical Tool Mocks:** The `WrapRescueAgent` fallback execution loop naturally triggered the new `get_total_requirements_by_day_and_role` and `get_unacknowledged_requirements_blocking_wrap` tools we added. The `test_wrap_rescue_agent.py` test suite assertions were appropriately expanded to reflect the `6` tool executions.
- **Status:** The `backend/tests` suite is perfectly green again with **971 passing tests**!

## 2. ClickHouse RBAC & 2FA Configuration

ClickHouse's Open Source SQL-driven access controls do not natively support TOTP, but the XML-based Configuration natively supports it. We chose the optimal path to build real Enterprise Security:

- **Security Profile (`security.xml`):** Created a ClickHouse configuration mapping that uses `access_management=1` on the `default` user for administration.
- **Role-Based Access Control:** Added an `admin_role` (`ALL ON *.*`) and a `read_only_role` (`SELECT ON cinespine.*`).
- **Time-Based One-Time Passwords (2FA):** Configured a `dit_user` with a standard `password_sha256_hex` hash and a `time_based_one_time_password` (TOTP base32 secret). The user is securely sandboxed to the `read_only_role`.
- **Infrastructure Bind:** Mounted the `clickhouse/users.d` directory to the `cinespine-clickhouse` container via `docker-compose.yml`.

## 3. Operational Intelligence: ClickHouse Alerting

To address the "Wire discrepancy detection to ClickHouse alert rules" request, we leaned on Grafana's industry-standard Alerting Engine powered directly by ClickHouse analytics.

- **Datasource Provisioning:** Configured Grafana to install the `grafana-clickhouse-datasource` plugin automatically on startup via `docker-compose.observability.yml` and explicitly provisioned the ClickHouse datasource.
- **Alert Rules:** Provisioned a native Grafana Alerting Rule that continually polls the `audit_discrepancies` table to detect any unacknowledged or unresolved `CRITICAL` discrepancies.
- **Judges Impact:** Evaluators and Judges will immediately see a functioning Grafana dashboard setup paired with proactive alerting on ClickHouse discrepancies, providing tangible Operational Intelligence.

---

> [!TIP]
> The next time you bring up the stack with `docker compose up -d` and `docker compose -f docker-compose.observability.yml up -d`, the new alerts and ClickHouse users will be automatically seeded!


# End-to-End Demo Walkthrough

We have fully implemented the end-to-end demo and partner integration showcase, focusing on **Google Cloud AI + ClickHouse + Grafana** working together in harmony.

## 1. Demo Data Fixtures & Scripts

- [NEW] [generate_synthetic_fixtures.py](file:///e:/projects/cinespine/scripts/generate_synthetic_fixtures.py): A script that generates `DEMO_TCLog_Synthetic.pdf`. This script uses the `fpdf` library to create a synthetic Timecode Log with correctly formatted slates, satisfying the strict event parsers.
- [NEW] [test_demo_pdf_ingestion.py](file:///e:/projects/cinespine/backend/tests/test_demo_pdf_ingestion.py): A test to ensure our synthetic PDF successfully survives the `pdf_parsers.py` checks and yields correctly structured records.
- [NEW] [demo_partner_integrations.py](file:///e:/projects/cinespine/scripts/demo_partner_integrations.py): A standalone CLI script that orchestrates the demo endpoints (Wipe, Ingest, Wrap Rescue Agent) and displays colorful rich-text CLI output, proving the end-to-end integration works independently of the frontend.

## 2. API Endpoints

In [routes.py](file:///e:/projects/cinespine/backend/app/api/routes.py), we've added the following dedicated endpoints:
1. `GET /api/events/demo`: Reads the synthetic `demo_script.fountain` and `DEMO_TCLog_Synthetic.pdf` files from disk, classifies them, and injects `EventEnvelope` messages directly into the internal EventBus exactly as `POST /upload/file` would.
2. `POST /api/demo/wipe`: Resets the database state by truncating the `spine_events`, `event_DLQ`, and `document_metadata` tables. 
3. `GET /api/wrap-rescue/demo`: Invokes the `GeminiDiscrepancyAssistant` (the newly refactored ADK agent) to answer a specific discrepancy query about the demo production using the ClickHouse MCP server.

## 3. Frontend Integration

- [NEW] [HackathonDemo.tsx](file:///e:/projects/cinespine/frontend/src/components/HackathonDemo.tsx): A dedicated React component showcasing the pipeline. It features a "Run Full Demo" button and a "Factory Reset" button, backed by an inline terminal log panel that displays the real-time status of the backend orchestrations and the final response of the Wrap Rescue Agent.
- [MODIFIED] [App.tsx](file:///e:/projects/cinespine/frontend/src/App.tsx): Registered a new "Hackathon Demo" top-level pillar. The view switcher now allows judges and evaluators to easily jump to the Demo Page in one click.

## How to Test

1. Generate the fixtures: `uv run scripts/generate_synthetic_fixtures.py`
2. Open the UI, click on the **Hackathon Demo** button (red/orange gradient) in the top nav.
3. Hit **Run Full Demo** and watch the logs track the ingestion, settlement, and Wrap Rescue AI analysis!



# Application Dockerization & Compose Unification

I have completed the dockerization of the CineSpine application and the unification of the Docker Compose files. Here is a summary of the changes:

## 1. Dockerized the Application
- **Backend**: Created [`backend/Dockerfile`](file:///e:/projects/cinespine/backend/Dockerfile) which uses `python:3.11-slim` and `uv` to install dependencies and run the FastAPI app on port 8000.
- **Frontend**: Created [`frontend/Dockerfile`](file:///e:/projects/cinespine/frontend/Dockerfile) which uses a multi-stage build. It first compiles the React/Vite app using Node.js, and then serves the static assets using a lightweight Nginx container on port 80.
- **Context Handling**: Added a `.dockerignore` file at the root to ensure things like `node_modules`, `.venv`, and `spine.db` aren't sent to the Docker daemon, improving build performance.

## 2. Unified Docker Compose
- Created a single, unified [`docker-compose.yml`](file:///e:/projects/cinespine/docker-compose.yml).
- **Core Services**: Included the new `frontend` and `backend` services alongside the existing `clickhouse` service. These start by default when running `docker compose up -d`.
- **Profiles for Optional Stacks**:
  - Migrated the observability stack (Prometheus & Grafana) into the main compose file, but placed them under `profiles: ["observability"]`.
  - Migrated the PostHog stack (Postgres, Redis, ClickHouse, Kafka, MinIO, Web, Plugins) into the main compose file, but placed them under `profiles: ["posthog"]`.
- Safely deleted the now-redundant `docker-compose.observability.yml` and `docker-compose.posthog.yml`.

## How to run the application

**Run the Core App (Frontend, Backend, Spine Database)**
```bash
docker compose up -d
```

**Run with Observability Metrics**
```bash
docker compose --profile observability up -d
```

**Run with PostHog Telemetry**
```bash
docker compose --profile posthog up -d
```

**Run Everything Together**
```bash
docker compose --profile observability --profile posthog up -d
```

The frontend will be accessible at `http://localhost:5173`, the backend at `http://localhost:8000`, Grafana at `http://localhost:3000`, and PostHog at `http://localhost:8010`.

---

## 4. Database Backup, Restore & Factory Reset

### Backup & Restore (SQLite + ClickHouse)
```bash
# 1. Take a safe timestamped online backup (spine.db + ai_cache.db)
python scripts/backup_databases.py

# 2. List available backups
python scripts/backup_databases.py --list

# 3. Restore a backup (restores SQLite and automatically rebuilds ClickHouse mirror)
python scripts/backup_databases.py --restore backups/backup_YYYYMMDD_HHMMSS
```

### Factory Reset & Baseline Seeding

# 1. Take a safe online backup (safe with active WAL mode)
python scripts/backup_databases.py

# 2. List available backups
python scripts/backup_databases.py --list

# 3. Restore a backup (restores SQLite and automatically rebuilds ClickHouse analytical mirror)
python scripts/backup_databases.py --restore backups/backup_20260831_221302



### Docker Volume Snapshot
```bash
# Backup ClickHouse container volume
docker run --rm -v cinespine_clickhouse_data:/data -v ${PWD}/backups:/backup alpine tar -czf /backup/clickhouse_data_backup.tar.gz -C /data .

# Restore ClickHouse container volume
docker run --rm -v cinespine_clickhouse_data:/data -v ${PWD}/backups:/backup alpine tar -xzf /backup/clickhouse_data_backup.tar.gz -C /data
```


# Wipe everything and re-seed baseline defaults
python scripts/wipe_and_seed.py

# Wipe everything without re-seeding (completely empty state)
python scripts/wipe_and_seed.py --no-seed




gcx synthetic-monitoring checks update cinespine-deep-health-88757 -f grafana/synthetic/deep-health.yaml