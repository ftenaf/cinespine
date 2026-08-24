# 🎬 CineSpine

> **The Append-Only Event Spine & 3-Axis Discrepancy Reconciliation Engine for Film & TV Production**

[![CI](https://github.com/ftenaf/cinespine/actions/workflows/ci.yml/badge.svg)](https://github.com/ftenaf/cinespine/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

---

## 📖 The Problem

Film and television productions run on fragmented daily paperwork created by five different departments across set and post-production. Every department keeps its own truth in its own silo:
* **Office:** Call sheets and Daily Production Reports (*parte de producción*) $\rightarrow$ **Intent**
* **Set:** Camera reports (*parte de cámara*), Sound ALE/CSV logs, Script supervisor notes and lined pages $\rightarrow$ **Belief**
* **Post / DIT:** Silverstack volume checksums, offload reports, clip manifests $\rightarrow$ **Existence**

Every handoff loses information, and **witnesses disagree**. An editor looking for take 3 on camera roll `B039` can discover the take was filed as `B39` by an unpadded script export, split into two separate rolls, and marked with a 4-frame timecode drift.

**CineSpine** solves this not by forcing a single fragile view, but by embracing the core truth: **The disagreement is the product.**

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    subgraph INGESTION["1. Asynchronous Ingestion (Confluent Kafka / IBM Track)"]
        A1[Script Supervisor Lined Pages] -->|production.raw.script| K[Confluent Kafka Event Bus]
        A2[Sound ALE / CSV Logs] -->|production.raw.sound| K
        A3[Camera Reports / Manifests] -->|production.raw.camera| K
        A4[Silverstack Offload Manifests] -->|production.raw.dpr| K
    end

    subgraph AGENT_ENGINE["2. Core Agentic Intelligence (Gemini Multimodal ADK)"]
        K --> W[Ingestion & Normalization Worker]
        W --> DET[Deterministic Parsers<br/>Sound / Camera / Silverstack]
        W --> GEM[Gemini Multimodal Vision<br/>Handwritten Script Lining Marks]
        DET --> NORM[Key Folding & Normalizer<br/>Rolls, Takes, Slates, Wild Tracks]
        GEM --> NORM
    end

    subgraph OLAP_SPINE["3. Analytical Event Spine (ClickHouse Cloud Track)"]
        NORM -->|Append-Only| CH[(ClickHouse: production_events)]
        CH --> MV1[Materialized View: takes_meta]
        CH --> MV2[Materialized View: audit_discrepancies]
        MCP[ClickHouse MCP Server] <--> CH
        RECON[Reconciliation Agent] <--> CH
    end

    subgraph OBSERVABILITY["4. Lighthouse Telemetry (Grafana Labs Track)"]
        CH --> GRAF[Grafana Cloud Dashboards]
        GRAF --> G1[Department Sync Lag Matrix]
        GRAF --> G2[Discrepancy Severity Gauge]
        GRAF --> G3[Error Breakdown Heatmap]
    end

    subgraph DASHBOARD["5. Interactive Web Dashboard (Replit Track)"]
        CH --> API[FastAPI REST / WebSocket Gateway]
        API --> UI[React 18 + Vite SPA]
        GRAF -.->|Embedded Panels| UI
        UI --> USER((Production Leads & Editors))
    end
```

---

## ⚙️ Core Invariants & Engineering Principles

1. **The Spine is Append-Only:** Correcting a fact appends a newer event with a later timestamp; never mutate rows in place.
2. **Absence of Report $\neq$ Absence of Material:** A day nobody has offloaded yet must never be rendered as missing footage. Gated on offload coverage.
3. **The Confident Nothing is the Enemy:** Any parser producing zero rows on non-empty input raises an explicit rejection (`PARSER_FAILURE`).
4. **Machine-Generated Data is Never Parsed by LLMs:** Timecodes, checksums, and roll IDs are extracted with strict deterministic validators. Gemini Multimodal is reserved for handwritten script lining and visual assets.

---

## 🚀 Quickstart

### Prerequisites
* Python 3.11+
* Node.js 20+
* Docker & Docker Compose (for local ClickHouse & Kafka)

### 1. Start Local Infrastructure
```bash
docker compose up -d
```

### 2. Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Or .venv\Scripts\Activate on Windows
pip install -r requirements.txt
pytest -v  # Run test suite
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 🧪 Vertical Slices & TDD Roadmap

* **Slice 1: Identity Normalization & Deterministic Parsers (TDD)**
* **Slice 2: Confluent Kafka Event Bus & Ingestion Stream**
* **Slice 3: ClickHouse Append-Only Spine & 3-Axis Reconciliation Engine**
* **Slice 4: Gemini Multimodal Script Extractor & MCP Tools**
* **Slice 5: Grafana Lighthouse Telemetry**
* **Slice 6: Full-Stack React Diff Surface & Replit Deployment**
