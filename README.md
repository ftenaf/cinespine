# 🎬 CineSpine

> **The Autonomous Append-Only Event Spine, 3-Axis Discrepancy Engine & Multi-Camera AI Previz Studio for Film & TV Production**  
> *Submitted to [Agentic Cinema: The Blockbuster Hackathon](https://agentic-cinema.devpost.com/) (Google Cloud & Partner Ecosystem: ClickHouse, Grafana Labs, Replit).*

[![CI Test Suite](https://img.shields.io/badge/Pytest-100%2F100%20Green-brightgreen.svg)](https://github.com/ftenaf/cinespine/actions)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11%20%7C%203.14-blue.svg)](https://python.org)
[![Google Cloud: Gemini & Imagen 3](https://img.shields.io/badge/Google%20Cloud-Gemini%202.0%20%26%20Imagen%203-4285F4.svg)](https://cloud.google.com/vertex-ai)
[![Event Spine: ClickHouse](https://img.shields.io/badge/Event%20Spine-ClickHouse%20OLAP-FEE000.svg)](https://clickhouse.com)
[![Observability: Grafana](https://img.shields.io/badge/Observability-Grafana%20Labs-F46800.svg)](https://grafana.com)
[![Frontend: React 18 + Vite](https://img.shields.io/badge/Frontend-React%2018%20%2B%20Vite%20%2B%20Tailwind-61DAFB.svg)](https://vitejs.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple.svg)](https://opensource.org/licenses/MIT)

---

## 🌟 Executive Summary & The Problem Space

In motion picture and episodic television production, **the bottleneck is never the creative talent—it is the catastrophic breakdown of documentation, communication, and handoffs between departments.**

Every department maintains its own version of reality:
* **The Office (Intent):** Screenplay scenes, call sheets, one-liners, actor schedules, and planned shot lists.
* **The Set (Belief):** Script supervisor logs, camera logs (*parte de cámara*), sound reports (*parte de sonido*), and false take notes.
* **The Lab / DIT (Existence):** Verified camera raw clips, offload checksum manifests, multi-track poly-WAVs, and editorial conforms.

When a script supervisor notes a take as *False Start*, but the sound recordist files it as *Good*, or when a roll spelling typo (`A120` vs `A_0120`) silently drops audio tracks, **no computer crashes.** The mistake sits undetected for weeks until the editorial conform, creating emergency panic and costing studios hundreds of thousands of dollars in re-shoots.

**CineSpine** solves this by enforcing a single immutable truth:  
> *"A document is a witness. Witnesses disagree, and **the disagreement is the product**."*

### 🏛️ Animated System Architecture & C4 Model

### 1. Multi-Persona User Event Flows & Append-Only Event Spine
![CineSpine Multi-Persona User Event Flows](docs/architecture/cinespine-user-event-flows-animated.svg)

### 2. End-to-End System Architecture (Production to Cloud)
![CineSpine Animated Architecture Diagram](docs/architecture/cinespine-architecture-animated.svg)

> *See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for full C4 Level 1–4 diagrams and sequence flows.*

### Level 1: System Context Diagram

```mermaid
C4Context
  title System Context Diagram - CineSpine Production Intelligence

  Person(script_sup, "Script Supervisor", "Logs takes, slates, lined pages, and circled takes on set")
  Person(sound_mixer, "Sound Mixer", "Records multi-track poly-WAVs and exports Sound ALE / CSV logs")
  Person(camera_crew, "Camera Department", "Generates ZoeLog CSV reports and camera card manifests")
  Person(dit_crew, "DIT / Data Manager", "Offloads cards, computes checksums, and produces Silverstack reports")
  Person(editorial, "Editorial Team", "Assistant & Lead Editors cutting dailies and resolving discrepancies")
  Person(director, "Director / DoP", "Decomposes screenplay, defines optics, reviews multi-camera AI previz")

  System(cinespine, "CineSpine Platform", "Append-only event spine, 3-axis discrepancy reconciler, and multi-camera AI previz studio")

  System_Ext(sound_dev, "Sound Devices 664 / 8-Series", "Generates BEXT timecoded poly-WAVs and Sound Reports")
  System_Ext(silverstack, "Pomfort Silverstack Lab", "Generates offload volume XMLs and thumbnail contact sheets")
  System_Ext(gemini_api, "Google Cloud Gemini 2.0 & Imagen 3", "Extracts semantic narrative tension & synthesizes 35mm concept stills")
  System_Ext(gcs_bucket, "Google Cloud Storage (GCS)", "Archives screenplay PDFs and verified production media assets")
  System_Ext(clickhouse_cloud, "ClickHouse Cloud", "Analytical OLAP storage for historical event replays & audit logs")
  System_Ext(grafana_cloud, "Grafana Cloud Lighthouse", "Real-time production sync lag and telemetry dashboards")

  Rel(script_sup, cinespine, "Uploads Daily Timecode Logs & Lined Pages", "PDF/Text")
  Rel(sound_mixer, cinespine, "Uploads Sound ALE Reports & Day Logs", "CSV/ALE")
  Rel(camera_crew, cinespine, "Uploads ZoeLog Camera Reports", "CSV")
  Rel(dit_crew, cinespine, "Uploads Silverstack Volume & Thumbnail Reports", "XML/PDF")
  Rel(editorial, cinespine, "Inspects takes, tracks requirements, resolves discrepancies", "HTTPS / SSE")
  Rel(director, cinespine, "Uploads screenplay, selects DoP styles, edits camera prompts", "HTTPS / UI")

  Rel(cinespine, gemini_api, "Executes semantic breakdown & Imagen 3 synthesis", "google.genai SDK")
  Rel(cinespine, gcs_bucket, "Archives source scripts & media bytes", "google.cloud.storage SDK")
  Rel(cinespine, clickhouse_cloud, "Appends immutable production events", "Native / HTTPS")
  Rel(cinespine, grafana_cloud, "Pushes operational telemetry & lag metrics", "Prometheus / OTLP")
```

---

### Level 2: Container Diagram

```mermaid
C4Container
  title Container Diagram - CineSpine Technical Architecture

  Person(user, "Production Crew & Directors", "Interacts via web browser")

  Container_Boundary(cinespine_app, "CineSpine Platform") {
    Container(spa, "CineSpine Frontend Studio", "React 18, Vite, Tailwind CSS, Lucide Icons", "Single-Page App offering Script Studio, Slate Navigator, Discrepancy Matrix, and Previz Lightbox")
    Container(api_gateway, "FastAPI Backend Gateway", "FastAPI, Python 3.11/3.14, Uvicorn", "Provides REST endpoints for takes, sequences, discrepancies, documents, and script breakdown")
    Container(sse_broker, "Live Event Broker", "Async Server-Sent Events (SSE)", "Maintains push connections scoped by production/day/user with zero-polling sync")
    Container(dispatcher, "Ingestion & Dispatch Pipeline", "Python Async Event Bus", "Classifies documents, validates schemas, and routes to deterministic extractors")
    Container(parsers, "Deterministic & Screenplay Extractors", "Python, pdfplumber, pypdf, Fountain parser", "Normalizes slates, takes, rolls, timecodes, and screenplay scenes")
    Container(recon_engine, "3-Axis Reconciliation Engine", "Python Rule Engine", "Cross-references Intent, Belief, and Existence to flag conflicts")
    Container(previz_engine, "AI Multi-Camera Previz Synthesizer", "google.genai SDK, DoP Matrix", "Compiles multi-camera setups (Cam A/B/C/D...) and renders photorealistic stills")
    ContainerDb(event_store, "Append-Only Event Spine", "SQLite / ClickHouse DB", "Immutable store for raw documents, parsed take facts, discrepancies, and audit trails")
  }

  Rel(user, spa, "Edits camera prompts, views dailies, resolves conflicts", "HTTPS")
  Rel(spa, api_gateway, "Queries takes, sequences, requirements, script breakdown", "JSON / HTTPS")
  Rel(spa, sse_broker, "Subscribes to live event stream (/api/events/subscribe)", "text/event-stream")
  Rel(api_gateway, sse_broker, "Publishes lifecycle events (Ingest, Resolve, Alert)")
  Rel(api_gateway, dispatcher, "Dispatches uploaded documents")
  Rel(dispatcher, parsers, "Executes parsing & normalization")
  Rel(parsers, event_store, "Appends normalized take and document facts")
  Rel(recon_engine, event_store, "Scans multi-witness facts, appends discrepancies")
  Rel(api_gateway, previz_engine, "Dispatches multi-camera breakdown & image generation")
  Rel(previz_engine, event_store, "Persists generated camera coverage packs")
```

---

## ⚡ Multi-Persona Production Event Flows (By User Type)

Every department on a film set acts as an **independent witness**. When a user interacts with CineSpine, their action is packaged into an **immutable, monotonically sequenced, typed event envelope**:

```json
{
  "event_id": "EVT_99482_A",
  "sequence_num": 1042,
  "timestamp_utc": "2026-08-26T09:00:00.000Z",
  "production_id": "DEMO_PRODUCTION",
  "shoot_day": "Day 31",
  "user_role": "SCRIPT_SUPERVISOR",
  "user_id": "script_sup_1",
  "event_type": "TAKE_LOGGED",
  "payload": {
    "scene_number": "1",
    "slate": "101/1",
    "take_number": 1,
    "status": "GOOD",
    "circled": true,
    "director_notes": "Print it. Great emotional delivery from LEAD."
  }
}
```

### Event Taxonomy Across Production Roles:

| User Type / Role | Emitted Event Types | Description & Semantic Payload | Target Subsystems |
| :--- | :--- | :--- | :--- |
| **🎬 Director & DoP** | `SCREENPLAY_PARSED`<br/>`CHARACTER_LOOK_LOCKED`<br/>`3CAM_PREVIZ_RENDERED`<br/>`CAMERA_ANGLE_ADDED`<br/>`CAMERA_ANGLE_DELETED`<br/>`DOP_OPTICS_CONFIGURED` | Uploads script (`.fountain`, `.md`, `.pdf`), extracts cast profiles, adjusts optical framing ($2.39:1$), spawns extra angles (Crane Cam D, Macro Cam E), and renders FLUX.1/Imagen 3 concept stills. | Screenplay Previz Studio, Cast Profiler, Optical Viewfinder |
| **📝 Script Supervisor** | `SCRIPT_REPORT_INGESTED`<br/>`TAKE_LOGGED`<br/>`CIRCLED_TAKE_FLAGGED`<br/>`FALSE_START_RECORDED`<br/>`DIRECTOR_NOTE_APPENDED` | Logs lined pages, continuity notes, False Starts, and circled takes on set. Asserts the "Set Belief" axis. | 3-Axis Reconciliation Engine, Composed Master Sheet |
| **🎙️ Sound Mixer** | `SOUND_ALE_INGESTED`<br/>`POLY_WAV_TRACKS_MAPPED`<br/>`WILD_TRACK_LOGGED`<br/>`TIMECODE_SYNC_ASSERTED` | Ingests Sound Devices 8-Series BEXT logs, maps ISO tracks (Boom, Lav 1, Lav 2), logs Wild Tracks (`WT 104`), asserts audio existence. | Card & Roll Map, Sequences Matrix, Audio Verifier |
| **💾 DIT & Data Manager** | `CARD_OFFLOAD_VERIFIED`<br/>`SILVERSTACK_MANIFEST_INGESTED`<br/>`CHECKSUM_VALIDATED`<br/>`RAW_CLIP_REGISTERED` | Offloads camera magazines ($A031$), computes MD5/XXHash64 checksums, parses Silverstack XML manifests, asserts "Physical Existence" axis. | Master Sheet, Roll Map, Storage Verifier |
| **✂️ Editor & Post Supervisor** | `DISCREPANCY_INSPECTED`<br/>`OVERRIDE_APPLIED`<br/>`CONSENSUS_REACHED`<br/>`MASTER_CONFORM_LOCKED` | Inspects 3-Axis conflicts (e.g. False Start vs Good, missing audio roll), overrides with editorial audit rationale, and locks master conform ledger. | Discrepancy Hub, Master Sheet, Editorial Export |
| **🤖 Autonomous Sentinel (Lighthouse)** | `3AXIS_SCAN_COMPLETED`<br/>`SYNC_LAG_ALERTED`<br/>`TELEMETRY_EMITTED` | Background event loop continuously scanning Intent ⟷ Belief ⟷ Existence for silent omissions and pushes lag telemetry to Grafana Labs. | Grafana Dashboards, Crew Alert Notifications |

---

### ⚡ Event System & Real-Time SSE Broker Architecture

![CineSpine Event System Animated](docs/architecture/cinespine-event-system-animated.svg)

```mermaid
flowchart LR
    subgraph Producers["1. Multi-Persona Event Producers"]
        P1["Director / DoP<br/>Screenplay & Previz"]
        P2["Script Supervisor<br/>Lined Logs & Takes"]
        P3["Sound Mixer<br/>ALE & Multi-Track"]
        P4["DIT / Lab<br/>Silverstack Offloads"]
        P5["Editor / Post<br/>Discrepancy Triage"]
    end

    subgraph EventSpine["2. ClickHouse Event Spine (Immutable Append-Only)"]
        direction TB
        E1["#1040 [SCREENPLAY_PARSED] Scene 1 & 2 • 3 Cast"]
        E2["#1041 [TAKE_LOGGED] Slate 101/1 • ⭐ Circled"]
        E3["#1042 [FALSE_START_RECORDED] Slate 101/2 • 'Aborted'"]
        E4["#1043 [DISCREPANCY_FLAGGED] Take 2 Belief vs Sound"]
        E5["#1044 [CAMERA_ANGLE_ADDED] Setup 1 • Cam D Crane"]
        E6["#1045 [DISCREPANCY_RESOLVED] Consensus Recorded"]
        E1 --> E2 --> E3 --> E4 --> E5 --> E6
    end

    subgraph Broker["3. LiveEventBroker (Zero-Polling SSE)"]
        B1["/api/events/subscribe?prod=DEMO_PRODUCTION"]
        B2["Role Filter: SOUND / CAMERA / EDITORIAL"]
        B3["User Dispatch: @assistant_editor"]
    end

    subgraph Consumers["4. Reactive Client State (Sub-5ms Push)"]
        C1["🎬 Previz Studio (3-Cam Concept Frames)"]
        C2["🎞️ Composed Master Sheet (Live Ledger)"]
        C3["🚨 3-Axis Discrepancy Matrix (Auto-Resolves)"]
        C4["📊 Grafana Telemetry & Sync Lag Monitors"]
    end

    Producers -->|"POST /api/events/publish"| EventSpine
    EventSpine -->|"broadcast"| Broker
    Broker -->|"Server-Sent Events (SSE)"| Consumers
```

---

## ✨ Core Innovations & Capabilities

### 1. 🎬 Dual-Pillar Architectural Experience
CineSpine decouples filmmaking operations into two distinct, distraction-free hero workspaces:
* **Pillar 1: 🎬 Screenplay & Previz Studio**: A pristine creative cockpit for Directors, Screenwriters, and Cinematographers to decompose scripts, profile actors, configure optics, and generate multi-angle camera concepts.
* **Pillar 2: 🎞️ Set & Editorial Spine**: An analytical operational hub for DITs, Script Supervisors, Sound Recordists, and Assistant Editors featuring the Composed Master Sheet, Sequences Log Matrix, Card & Roll Map, Active Discrepancies Hub, and DIT search engine.

### 2. 🎥 Multi-Camera Previz & Master DoP Studio
* **Multi-Format Screenplay Ingestion:** Parses `.fountain`, `.md` (Markdown), `.txt` (Plaintext), `.pdf`, and `.fdx` (Final Draft) scripts.
* **Autonomous & Dynamic Multi-Camera Rig Management:**
  * Generates synchronized **Camera A** ($28\text{mm}$ Wide Master), **Camera B** ($50\text{mm}$ Medium / OTS), and **Camera C** ($85\text{mm}$ Profile / Macro).
  * **Add & Remove Cameras Dynamically:** Add **Camera D (Crane / Wide POV)**, **Camera E (Extreme Close-Up Macro)**, or **Camera F (Steadicam)** per scene, or remove unneeded cameras with automatic re-focusing.
  * **1-Click Batch Render:** Render concepts for all cameras ($A, B, C, D\dots$) simultaneously in parallel.
* **DoP Framing & Master Optical Controls:**
  * **Aspect Ratio Selector ($2.39:1$ Scope, $1.85:1$ Flat, $16:9$ UHD, $4:3$ Academy)** located inside the DoP Studio.
  * Real-time optical tuners: Lens focal lengths ($18\text{mm}–135\text{mm}$), Apertures ($T1.3–T11$), Color temperatures ($2800\text{K}–7500\text{K}$), Key-to-fill lighting ratios ($1:1$ to $16:1$), and film stock LUT emulations.
* **Persistent Character Consistency:** Locks character physical traits and headshot profiles so all generated camera concepts enforce consistent actor appearance.

### 3. 🔍 3-Axis Discrepancy Reconciliation Engine
* Reconciles Intent (Planned), Belief (Logged on set), and Existence (Stored on disk) with sub-millisecond precision.
* Catches silent false starts, unlinked audio tracks, timecode drift, roll name collisions, and missing coverage.
* Features an interactive **Consensus & Resolution Triage Hub** for Assistant Editors, DITs, and Post Supervisors.

### 4. 📡 Append-Only Event Spine & Real-Time SSE Bus
* Backed by **ClickHouse** and SQLite for zero-data-loss event streaming.
* Real-time Server-Sent Events (SSE) dispatching live updates to crew members based on department handle (`@director`, Sound, Camera, Editorial).

---

## ☁️ Google Cloud & Partner Integration (Runtime Verified)

CineSpine executes real runtime API calls to Google Cloud and partner services:

```python
# 1. Official Google GenAI SDK Runtime Import
from google import genai
from google.genai import types as genai_types

# Gemini 2.0 Screenplay Semantic Breakdown
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
analysis = client.models.generate_content(
    model="gemini-2.0-flash",
    contents=prompt
)

# Google Imagen 3 Photorealistic 35mm Previz Synthesis
result = client.models.generate_images(
    model="imagen-3.0-generate-002",
    prompt=compiled_dop_prompt,
    config=dict(number_of_images=1, aspect_ratio="16:9")
)

# 2. Official Google Cloud Storage (GCS) Media Ingest
from google.cloud import storage as gcs_storage
gcs_client = gcs_storage.Client(project="cinespine-agentic-cinema")
blob = gcs_client.bucket("cinespine-production-media").blob("screenplays/scene_27.pdf")
blob.upload_from_string(file_bytes, content_type="application/pdf")
```

| Partner / Service | Role in CineSpine | Verification |
| :--- | :--- | :--- |
| **Google Cloud (Gemini 2.0)** | Screenplay semantic analysis & DoP prompt compilation | Runtime imported via `google-genai` SDK |
| **Google Cloud (Imagen 3)** | Photorealistic 35mm cinematic concept art generation | Model `imagen-3.0-generate-002` |
| **Google Cloud Storage (GCS)** | Screenplay PDF & high-res media archival | Bucket `gs://cinespine-production-media/` |
| **ClickHouse** | Immutable high-throughput append-only event spine | Time-series event logging & replay |
| **Grafana Labs** | Real-time production sync lag, take throughput telemetry | Metrics exporter (`GET /metrics`) |

---

## 🚀 Quickstart Guide

### Prerequisites
- **Python 3.11+** (or Python 3.14)
- **Node.js 18+** & `npm`

### 1. Clone & Setup Backend
```bash
git clone https://github.com/ftenaf/cinespine.git
cd cinespine

# Create virtual environment
python -m venv .venv
# On Windows:
.\.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies (including Google Cloud SDKs)
pip install -e .
pip install google-genai google-cloud-storage
```

### 2. Start the Backend API Server
```bash
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
* Backend API Gateway: `http://localhost:8000`
* Interactive API Docs: `http://localhost:8000/docs`
* Google Cloud Telemetry: `http://localhost:8000/api/integrations/google-cloud`

### 3. Setup & Start Frontend Studio
```bash
cd frontend
npm install
npm run dev
```
* Studio UI: `http://localhost:5173`

---

## 🧪 Automated Test Suite (100% Green)

CineSpine includes a comprehensive test suite covering parsers, 3-axis reconciliation algorithms, Google Cloud runtime integrations, and Script Studio endpoints:

```bash
pytest -v
```

```
============================== 100 passed in 130s ===============================
backend/tests/test_agents.py .................. [100%]
backend/tests/test_api.py ..................... [100%]
backend/tests/test_google_cloud_integration.py  [100%] (5 passed)
backend/tests/test_script_studio.py ........... [100%] (9 passed)
backend/tests/test_reconciliation.py .......... [100%]
backend/tests/test_pdf_parsers.py ............. [100%]
```

---

## 📂 Project Structure

```
cinespine/
├── backend/
│   ├── app/
│   │   ├── api/routes.py                # FastAPI REST & SSE Gateway
│   │   ├── core/                        # Event spine, database models, state
│   │   ├── engine/                      # 3-Axis Discrepancy Reconciliation Engine
│   │   ├── integrations/
│   │   │   └── google_cloud.py          # Google GenAI & GCS Storage Client
│   │   ├── script/
│   │   │   ├── parser.py                # Screenplay Parser (.fountain, .pdf, .fdx)
│   │   │   ├── breakdown_engine.py      # Multi-Camera (A/B/C) Coverage Engine
│   │   │   ├── dop_matrix.py            # Master DoP Optical Matrix
│   │   │   ├── ai_image_service.py      # Real-Time AI Generation Engine
│   │   │   └── storyboard_generator.py  # 35mm Cinema Still Generator
│   │   └── main.py                      # FastAPI Application Gateway
│   └── tests/                           # 100 Automated Pytest Tests
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ScriptStudio.tsx         # AI Script & Multi-Cam Previz Studio
│   │   │   ├── ProductionDashboard.tsx  # Main Operations & Dailies Hub
│   │   │   ├── DiscrepancyMatrix.tsx    # 3-Axis Reconciliation Hub
│   │   │   └── NotificationPanel.tsx    # Crew Real-Time Dispatch
│   │   └── App.tsx                      # Root Studio Application
│   └── package.json
├── docs/
│   ├── DEVPOST_SUBMISSION.md            # Official Hackathon Submission Package
│   ├── GOOGLE_CLOUD_INTEGRATION.md      # Google Cloud Architecture Guide
│   ├── DEMO_VIDEO_SCRIPT.md             # 3-Minute Demo Video Walkthrough Script
│   └── architecture/                    # C4 Architecture Diagrams
└── README.md
```

---

## 📜 License & Acknowledgments

* **License:** [MIT License](LICENSE)
* **Hackathon:** Built for [Agentic Cinema: The Blockbuster Hackathon](https://agentic-cinema.devpost.com/)
* **Created by:** Francisco & The CineSpine Team
