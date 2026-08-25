# 🎬 CineSpine

> **The Append-Only Event Spine, Real-Time Collaboration Hub & 3-Axis Discrepancy Reconciliation Engine for Film & TV Production**

[![CI](https://github.com/ftenaf/cinespine/actions/workflows/ci.yml/badge.svg)](https://github.com/ftenaf/cinespine/actions)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![Node: 20+](https://img.shields.io/badge/Node-20+-green.svg)](https://nodejs.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple.svg)](https://opensource.org/licenses/MIT)

---

## 📖 The Problem

Film and television productions run on fragmented daily paperwork created by five different departments across set and post-production. Every department keeps its own truth in its own silo:

* **Office:** Call sheets and Daily Production Reports (*parte de producción*) $\rightarrow$ **Intent**
* **Set:** Camera reports (*parte de cámara*), Sound ALE/CSV logs, Script supervisor notes and lined pages $\rightarrow$ **Belief**
* **Post / DIT:** Silverstack volume checksums, offload reports, clip manifests $\rightarrow$ **Existence**

Every handoff loses information, and **witnesses disagree**. An editor looking for Take 1 on camera roll `A120` can discover the take was filed under `A_0120` by a script export, split into two separate rolls, and marked with a 4-frame timecode drift against the Sound ALE recorder.

**CineSpine** solves this not by forcing a single fragile view, but by embracing the core truth: **The disagreement is the product.**

---

## 🏛️ C4 Architecture Documentation

### Level 1: System Context Diagram
The System Context diagram illustrates CineSpine within the operational environment of a film & television production unit, showing external practitioners and external cloud ecosystems.

```mermaid
C4Context
  title System Context Diagram - CineSpine Production Intelligence

  Person(script_sup, "Script Supervisor", "Logs takes, slates, lined pages, and circled takes on set")
  Person(sound_mixer, "Sound Mixer", "Records multi-track poly-WAVs and exports Sound ALE / CSV logs")
  Person(camera_crew, "Camera Department", "Generates ZoeLog CSV reports and camera card manifests")
  Person(dit_crew, "DIT / Data Manager", "Offloads cards, computes checksums, and produces Silverstack reports")
  Person(editorial, "Editorial Team", "Assistant & Lead Editors cutting dailies and resolving discrepancies")

  System(cinespine, "CineSpine Platform", "Append-only event spine, 3-axis discrepancy reconciler, and real-time collaboration hub")

  System_Ext(sound_dev, "Sound Devices 664 / 8-Series", "Generates BEXT timecoded poly-WAVs and Sound Reports")
  System_Ext(silverstack, "Pomfort Silverstack Lab", "Generates offload volume XMLs and thumbnail contact sheets")
  System_Ext(gemini_api, "Google Gemini Multimodal API", "Analyzes handwritten script lining marks and visual assets")
  System_Ext(clickhouse_cloud, "ClickHouse Cloud", "Analytical OLAP storage for historical event replays")
  System_Ext(grafana_cloud, "Grafana Cloud Lighthouse", "Real-time production sync lag and telemetry dashboards")

  Rel(script_sup, cinespine, "Uploads Daily Timecode Logs & Lined Pages", "PDF/Text")
  Rel(sound_mixer, cinespine, "Uploads Sound ALE Reports & Day Logs", "CSV/ALE")
  Rel(camera_crew, cinespine, "Uploads ZoeLog Camera Reports", "CSV")
  Rel(dit_crew, cinespine, "Uploads Silverstack Volume & Thumbnail Reports", "XML/PDF")
  Rel(editorial, cinespine, "Inspects takes, tracks requirements, resolves discrepancies", "HTTPS / SSE")

  Rel(sound_dev, sound_mixer, "Exports sound files & reports")
  Rel(silverstack, dit_crew, "Exports offload reports & checksums")

  Rel(cinespine, gemini_api, "Extracts handwritten notes & visual context", "HTTPS / JSON")
  Rel(cinespine, clickhouse_cloud, "Appends immutable production events", "Native / HTTPS")
  Rel(cinespine, grafana_cloud, "Pushes operational telemetry & lag metrics", "Prometheus / OTLP")
```

---

### Level 2: Container Diagram
Zooms into the technical boundaries of the CineSpine platform.

```mermaid
C4Container
  title Container Diagram - CineSpine Technical Architecture

  Person(user, "Production Crew & Editors", "Interacts via web browser")

  Container_Boundary(cinespine_app, "CineSpine Platform") {
    Container(spa, "CineSpine Frontend SPA", "React 18, Vite, Tailwind CSS, Lucide Icons", "Single-Page App offering Slate Navigator, Requirements Hub, Discrepancy Matrix, and PDF Viewer")
    Container(api_gateway, "FastAPI Backend Gateway", "FastAPI, Python 3.11/3.14, Uvicorn", "Provides REST endpoints for takes, sequences, discrepancies, documents, and requirements")
    Container(sse_broker, "Live Event Broker", "Async Server-Sent Events (SSE)", "Maintains push connections scoped by production/day/user with zero-polling sync")
    Container(dispatcher, "Ingestion & Dispatch Pipeline", "Python Async Event Bus", "Classifies documents, validates schemas, and routes to deterministic extractors")
    Container(parsers, "Deterministic & Multimodal Extractors", "Python, pdfplumber, PyPDF2, Gemini SDK", "Normalizes slates, takes, camera rolls, sound rolls, and timecodes")
    Container(recon_engine, "3-Axis Reconciliation Engine", "Python Rule Engine", "Cross-references Intent, Belief, and Existence to flag conflicts")
    ContainerDb(event_store, "Append-Only Event Spine", "SQLite / ClickHouse DB", "Immutable store for raw documents, parsed take facts, discrepancies, and audit trails")
  }

  Rel(user, spa, "Views dailies, manages action items, resolves conflicts", "HTTPS")
  Rel(spa, api_gateway, "Queries takes, sequences, requirements, document bytes", "JSON / HTTPS")
  Rel(spa, sse_broker, "Subscribes to live event stream (/api/events/subscribe)", "text/event-stream")
  Rel(api_gateway, sse_broker, "Publishes lifecycle events (Ingest, Resolve, Alert)")
  Rel(api_gateway, dispatcher, "Dispatches uploaded documents")
  Rel(dispatcher, parsers, "Executes parsing & normalization")
  Rel(parsers, event_store, "Appends normalized take and document facts")
  Rel(recon_engine, event_store, "Scans multi-witness facts, appends discrepancies")
  Rel(api_gateway, event_store, "Reads aggregated takes, sequences, and requirements")
  Rel(api_gateway, recon_engine, "Appends consensus resolution events")
```

---

### Level 3: Component Diagram (FastAPI Backend)
Illustrates the internal Python modules under `backend/app/`.

```mermaid
C4Component
  title Component Diagram - CineSpine Backend Architecture

  Container(spa, "React SPA", "TypeScript", "Frontend Client")

  Container_Boundary(backend, "FastAPI Application") {
    Component(routes, "API Routes & Endpoints", "backend.app.api.routes", "REST endpoints for /api/takes, /api/sequences, /api/requirements, /api/seed")
    Component(live_broker, "LiveEventBroker", "backend.app.streaming.broker", "Manages active SSE subscriber queues and synchronous event broadcast")
    Component(dispatcher, "IngestionDispatcher", "backend.app.streaming.dispatcher", "Routes files to departmental parsers and publishes raw events")
    Component(event_bus, "SpineEventBus", "backend.app.streaming.bus", "Pub/sub event bus segregating topics (production.raw.*)")
    Component(classifier, "DocumentClassifier", "backend.app.classifier.classifier", "Detects document type and department via header signatures")
    Component(camera_parser, "CameraParser", "backend.app.parsers.camera_csv", "Parses ZoeLog CSV reports with roll & clip extraction")
    Component(sound_parser, "SoundParser", "backend.app.parsers.sound_ale", "Parses Sound ALE/CSV reports with BEXT timecodes")
    Component(script_parser, "ScriptParser", "backend.app.parsers.pdf_parsers", "Parses daily TCLogs and detailed editor logs")
    Component(silverstack_parser, "SilverstackParser", "backend.app.parsers.parsers", "Parses Silverstack volume XMLs and thumbnail sheets")
    Component(normalizers, "Normalizers", "backend.app.normalizers", "Folds slates (27/7), takes (3*), and camera rolls (A120)")
    Component(recon, "ReconciliationEngine", "backend.app.reconciliation.engine", "Evaluates circle take conflicts, TC drift, and missing media")
    Component(spine_writer, "SpineStore & Writer", "backend.app.api.routes", "Stores raw documents, events, discrepancies, and requirements in SQLite/ClickHouse")
    Component(agents, "Discrepancy Agent", "backend.app.agents.discrepancy_agent", "Generates natural language conflict explanations")
  }

  Rel(spa, routes, "HTTP REST Queries & Mutations")
  Rel(spa, live_broker, "SSE Stream Subscription (/api/events/subscribe)")

  Rel(routes, spine_writer, "Queries & Mutates State")
  Rel(routes, live_broker, "Pushes Live Events")
  Rel(routes, dispatcher, "Submits Ingestion Payloads")

  Rel(dispatcher, classifier, "Classifies Document")
  Rel(dispatcher, event_bus, "Publishes Raw Upload Events")
  Rel(dispatcher, camera_parser, "Delegates Camera Reports")
  Rel(dispatcher, sound_parser, "Delegates Sound Reports")
  Rel(dispatcher, script_parser, "Delegates Script Logs")
  Rel(dispatcher, silverstack_parser, "Delegates Offload Manifests")

  Rel(camera_parser, normalizers, "Normalizes Roll & Slate")
  Rel(sound_parser, normalizers, "Normalizes Take & Timecode")
  Rel(script_parser, normalizers, "Normalizes Action Notes")

  Rel(dispatcher, recon, "Triggers 3-Axis Audit")
  Rel(recon, spine_writer, "Persists Discrepancies")
  Rel(recon, agents, "Explains Conflicts")
```

---

### Level 4: Dynamic Diagram (Collaborative Ingestion & Resolution Flow)
Tracks the end-to-end event sequence when a new document is dropped, a discrepancy is flagged, and an editor resolves it.

```mermaid
C4Dynamic
  title Dynamic Diagram - Multi-User Ingestion & Real-Time Resolution Flow

  Person(dit, "DIT Lead", "Uploads Silverstack offload report")
  Person(editor, "Assistant Editor", "Resolves discrepancy on UI")
  Container(spa_editor, "Editor Session", "React SPA", "Connected as @assistant_editor")
  Container(spa_team, "Team Session", "React SPA", "Connected as @lead_editor")
  Container(api, "FastAPI Gateway", "Python", "REST API")
  Container(dispatcher, "Dispatcher & Parsers", "Python", "Ingestion Pipeline")
  Container(recon, "Reconciliation Engine", "Python", "3-Axis Conflict Audit")
  Container(broker, "LiveEventBroker", "SSE Broker", "Broadcast Hub")
  ContainerDb(db, "Event Spine", "SQLite / ClickHouse", "Append-Only Store")

  Rel(dit, api, "1. POST /api/upload (Silverstack Report)", "HTTPS")
  Rel(api, dispatcher, "2. Route to parser", "Raw bytes")
  Rel(dispatcher, db, "3. Append normalized take media facts", "SQL Append")
  Rel(dispatcher, recon, "4. Trigger discrepancy reconciliation", "Take facts")
  Rel(recon, db, "5. Flag 'Roll Mismatch (A120 vs A121)'", "Insert Discrepancy")
  Rel(api, broker, "6. Broadcast 'DOCUMENT_INGESTED'", "Internal Event")
  Rel(broker, spa_editor, "7. Push SSE update (Refresh UI)", "text/event-stream")
  Rel(broker, spa_team, "8. Push SSE update (Refresh UI)", "text/event-stream")

  Rel(editor, spa_editor, "9. Click 'Resolve as Card A120' with note", "User Click")
  Rel(spa_editor, api, "10. POST /api/discrepancies/resolve", "JSON")
  Rel(api, db, "11. Append 'DISCREPANCY_RESOLVED' event", "SQL Append")
  Rel(api, broker, "12. Broadcast 'DISCREPANCY_RESOLVED'", "Internal Event")
  Rel(broker, spa_editor, "13. Push SSE: Update badge to Resolved", "text/event-stream")
  Rel(broker, spa_team, "14. Push SSE: Notification & resolved state", "text/event-stream")
```

---

## ✨ Key Features

### 1. Multi-Camera & Audio Take Aggregation
* **Synchronized Take Cards:** Groups multi-camera angles (A, B, C) with proxy thumbnails, codec info, lens/ISO metadata, and Sound Devices WAV audio clips on a unified timeline.
* **Intelligent Media Matching:** Reconciles ZoeLog clip names (`A120_C001`), Silverstack volumes (`A_0120C001_...`), and Sound ALE files (`27-7T01.WAV`).
* **Sequence Action Summaries:** Combines dramatic action descriptions (`"LEAD plays -> He sees SUPPORT"`) and camera setup notes into human-readable sequence summaries.

### 2. Real-Time Push Subscriptions (Server-Sent Events)
* **Zero-Polling Sync:** Persistent SSE stream at `/api/events/subscribe` pushes instantaneous event notifications (`DOCUMENT_INGESTED`, `REQUIREMENT_RESOLVED`, `DISCREPANCY_RESOLVED`, `NOTIFICATION_ADDED`).
* **Decoupled Lifecycle:** Synchronous subscriber registration compatible with Python 3.11 (CI) and modern Python 3.14 event loops.

### 3. Collaborative Requirements & Alerts Hub
* **Multi-User Crew Identity:** Passwordless team member profiles (`@director`, `@sound_supervisor`, `@assistant_editor`, `@lead_editor`, `@dit_lead`, `@vfx_supervisor`).
* **4-Grain Target Binding:** Bind action items directly to `production`, `scene`, `shot`, or `take` grains.
* **Resolution Workflow & Auditing:** Captures resolver handle, timestamp, and explanation notes, triggering bi-directional notifications to assignees and creators.
* **Direct Deep-Link Navigation:** Clicking target badges (e.g. `Take 27/7 T1`) navigates straight to the Slate Navigator without polluting or altering search filter queries.

### 4. 3-Axis Discrepancy Matrix
* **Side-by-Side Witness Diffs:** Inspects conflicting evidence across **Intent** (DPR/Call sheet), **Belief** (Script, Camera, Sound reports), and **Existence** (Silverstack offload checksums).
* **1-Click Consensus Resolution:** Resolve discrepancies with clear audit trails without mutating historical events.

### 5. Interactive Document Explorer & Visual PDF Preview
* In-browser visual PDF previewer with pagination and pan/zoom controls.
* Extracted JSON metadata streaming for technical verification.

---

## ⚙️ Core Invariants & Engineering Principles

1. **The Spine is Append-Only:** Correcting a fact appends a newer event with a later timestamp; historical records are never mutated or deleted.
2. **Absence of Report $\neq$ Absence of Material:** A day without offload records is never rendered as "missing footage". Gated on offload coverage.
3. **The Confident Nothing is the Enemy:** Any parser producing zero rows on non-empty input raises an explicit rejection (`PARSER_FAILURE`).
4. **Machine-Generated Data is Never Parsed by LLMs:** Timecodes, checksums, and roll IDs are extracted with strict deterministic validators. Gemini Multimodal is reserved for handwritten script lining and visual assets.
5. **Deterministic Fallback Seed Dataset:** Includes self-contained fallback paperwork data for zero-dependency CI runs and containerized demos.

---

## 🚀 Quickstart

### Prerequisites
* Python 3.11+
* Node.js 20+

### 1. Clone & Setup Backend
```bash
git clone https://github.com/ftenaf/cinespine.git
cd cinespine

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate

# Install dependencies in editable mode
pip install -r backend/requirements.txt
pip install -e .

# Run 86-test verification suite
pytest -v

# Start FastAPI backend server
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Setup Frontend
```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 📡 REST & SSE API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/seed` | `POST` | Seeds production documents from local files or embedded fallback demo dataset. |
| `/api/takes` | `GET` | Returns aggregated takes with multi-camera angles, audio clips, and requirements. |
| `/api/sequences` | `GET` | Returns script sequences with aggregated action descriptions and active camera/sound cards. |
| `/api/discrepancies` | `GET` | Returns active cross-department witness discrepancies. |
| `/api/discrepancies/resolve` | `POST` | Resolves a discrepancy and appends a consensus event to the spine. |
| `/api/documents` | `GET` | Lists ingested paperwork documents with metadata and checksums. |
| `/api/documents/{doc_id}/preview` | `GET` | Streams binary document bytes for visual PDF previewing. |
| `/api/events/subscribe` | `GET` | Server-Sent Events (SSE) push stream scoped by `production_id`, `shoot_day`, and `user_handle`. |
| `/api/requirements` | `GET`, `POST` | Fetches and creates collaborative action items across 4 entity target grains. |
| `/api/requirements/{id}/resolve` | `POST` | Resolves an action item with resolver metadata and explanation note. |
| `/api/notifications` | `GET` | Returns user-specific alert notifications. |
| `/api/users` | `GET` | Lists production team members and roles. |

---

## 🧪 Test Suite & CI Automation

The codebase is covered by **86 automated pytest test cases** and automated GitHub Actions CI:

```bash
pytest -v
```

* `test_agents.py`: AI Discrepancy & Chat Agents.
* `test_api.py`: REST Endpoints, Multi-Camera Grouping & Fallback Seeding.
* `test_classifier.py`: Deterministic Document Routing.
* `test_document_preview.py`: Visual PDF Streaming & Thumbnails.
* `test_events_subscription.py`: SSE Real-Time Broker & Multi-Subscriber Push.
* `test_normalizers.py`: Slate, Take, and Roll Normalization.
* `test_parsers.py`: Sound ALE, ZoeLog Camera CSV, and Silverstack XML.
* `test_pdf_parsers.py`: Binary PDF Extraction.
* `test_production_inference.py`: DPR vs. Set Cross-Inference.
* `test_real_pdf_examples.py`: Real-World Production Paperwork Fixtures.
* `test_reconciliation.py`: 3-Axis Discrepancy Detection & Resolution.
* `test_requirements.py`: Collaborative Action Items & Notifications.
* `test_scripte_parsers.py`: Scripte TCLog & Editor Logs.
* `test_streaming.py`: Event Dispatcher & Message Bus.

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
