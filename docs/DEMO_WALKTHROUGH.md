# CineSpine Hackathon Demo Walkthrough

Welcome to the **CineSpine** demo! This guide will walk you through the end-to-end "Wow" factors of our production operating system.

## 🏁 1. The Quick Start (Hackathon Mode)
If you want to see the entire pipeline instantly without uploading files manually:
1. Navigate to **[http://localhost:5173/hackathon](http://localhost:5173/hackathon)**.
2. Click **"Run Demo"**.
3. Watch as the system auto-ingests a synthetic screenplay, generates the 3-Camera Breakdown, and visualizes the generative DoP parameters.

## 📊 2. Partner Integration Showcase (CLI)
We have a dedicated script that demonstrates the real-time event pipeline (Events → Pub/Sub → SSE → ClickHouse).
1. Open a new terminal in the `cinespine` repository.
2. Run `uv run scripts/demo_partner_integrations.py`.
3. You will see synthetic events published to the broker, picked up by the SSE listener, and persisted immediately into ClickHouse streams.

## 🚨 3. ClickHouse Operational Intelligence (Grafana)
We have wired ClickHouse directly into Grafana to monitor the `audit_discrepancies` table for critical issues.
1. Open Grafana at **[http://localhost:3000](http://localhost:3000)** (admin/admin).
2. Navigate to **Alerting -> Alert Rules**.
3. Expand **CineSpine Discrepancies** to see the native ClickHouse alerting rule that fires whenever a `CRITICAL` discrepancy goes unresolved.

## 🤖 4. Wrap Rescue Agent API (Google ADK)
You can directly interact with the Wrap Rescue Agent (built on Google ADK) without using the UI.
1. Run `curl -X GET http://localhost:8000/api/wrap-rescue/demo`.
2. The agent will analyze the event spine, identify critical blockers, and generate a structured Gemini-authored memo for the producers.

The agent reads ClickHouse through the official `mcp-clickhouse` server, which
runs as its own compose service — `docker compose up -d` starts it alongside
the backend. Against the seeded demo it should report **3 blockers and 3
requirement actions** on shoot day 31.

If it reports a clean day, check `tool_calls` in the response before believing
it: every call showing `ok=true` with `rows=0` means the query path is broken,
not that the day is clear. See [CLICKHOUSE_MCP.md](CLICKHOUSE_MCP.md) for why
those two states look identical from the outside.

## 🧹 5. Factory Reset
To wipe the slate clean and drop all ClickHouse discrepancy events and SQLite state:
- Click the red **"Factory Reset"** button on the `/hackathon` route, OR
- Run `curl -X POST http://localhost:8000/api/demo/wipe`.

Enjoy evaluating CineSpine!
