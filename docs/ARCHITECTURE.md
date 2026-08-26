# 🏛️ CineSpine — C4 Architecture Documentation

> Comprehensive structural, container, component, and runtime sequence architecture documentation for **CineSpine** following the **C4 Model**.

---

## 🎬 Animated System Architecture & User Event Flows (SMIL SVG)

### 1. Multi-Persona User Event Flows & Append-Only Event Spine
![CineSpine Multi-Persona User Event Flows](architecture/cinespine-user-event-flows-animated.svg)

### 2. End-to-End System Architecture (Production to Cloud)
![CineSpine Animated Architecture Diagram](architecture/cinespine-architecture-animated.svg)

### 3. Event System & Real-Time SSE Broker
![CineSpine Event System Animated](architecture/cinespine-event-system-animated.svg)

---

## 1. Level 1: System Context Diagram
The System Context diagram illustrates CineSpine within the operational environment of a film & television production unit, showing external practitioners and external cloud ecosystems.

```mermaid
C4Context
  title System Context Diagram - CineSpine Production Intelligence

  Person(script_sup, "Script Supervisor", "Logs takes, slates, lined pages, and circled takes on set")
  Person(sound_mixer, "Sound Mixer", "Records multi-track poly-WAVs and exports Sound ALE / CSV logs")
  Person(camera_crew, "Camera Department", "Generates ZoeLog CSV reports and camera card manifests")
  Person(dit_crew, "DIT / Data Manager", "Offloads cards, computes checksums, and produces Silverstack reports")
  Person(editorial, "Editorial Team", "Assistant & Lead Editors cutting dailies and resolving discrepancies")
  Person(director, "Director / DoP", "Decomposes screenplay, defines optics, reviews 3-camera AI previz")

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

  Rel(sound_dev, sound_mixer, "Exports sound files & reports")
  Rel(silverstack, dit_crew, "Exports offload reports & checksums")

  Rel(cinespine, gemini_api, "Executes semantic breakdown & Imagen 3 synthesis", "google.genai SDK")
  Rel(cinespine, gcs_bucket, "Archives source scripts & media bytes", "google.cloud.storage SDK")
  Rel(cinespine, clickhouse_cloud, "Appends immutable production events", "Native / HTTPS")
  Rel(cinespine, grafana_cloud, "Pushes operational telemetry & lag metrics", "Prometheus / OTLP")
```

---

## 2. Level 2: Container Diagram
Zooms into the technical boundaries of the CineSpine platform.

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
    Container(previz_engine, "AI Multi-Camera Previz Synthesizer", "google.genai SDK, DoP Matrix", "Compiles 3-camera setups (Cam A/B/C) and renders photorealistic stills")
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

## 3. Level 3: Component Diagram (Backend Core)
Details the internal components of the CineSpine Python FastAPI service.

```mermaid
C4Component
  title Component Diagram - CineSpine Core Backend Subsystems

  Container_Boundary(backend_core, "CineSpine FastAPI Service") {
    Component(routes, "API Route Handlers", "backend.app.api.routes", "REST endpoints for /api/script/*, /api/takes, /api/discrepancies")
    Component(script_parser, "Screenplay Ingestion Engine", "backend.app.script.parser", "Parses Fountain, PDF, and FDX formats into structured scenes and dialogue")
    Component(breakdown, "Multi-Camera Previz Engine", "backend.app.script.breakdown_engine", "Calculates synchronized 3-camera rigs (Cam A, B, C) per setup")
    Component(dop_matrix, "DoP Optical Matrix", "backend.app.script.dop_matrix", "Calculates focal lengths, T-stops, Kelvin, and lighting contrast ratios")
    Component(ai_service, "AI Generative Service", "backend.app.script.ai_image_service", "Calls Google GenAI (Imagen 3 & Gemini 2.0) with DoP prompt compilation")
    Component(gcp_client, "Google Cloud Integration Client", "backend.app.integrations.google_cloud", "Wraps google.genai and google.cloud.storage clients")
    Component(recon, "3-Axis Reconciliation Engine", "backend.app.engine.reconciliation", "Executes multi-witness diffing algorithms")
    Component(spine, "Append-Only Event Spine", "backend.app.core.event_spine", "ClickHouse / SQLite append-only storage and replay engine")
  }

  Rel(routes, script_parser, "Parses uploaded script bytes")
  Rel(routes, breakdown, "Generates multi-camera coverage")
  Rel(breakdown, dop_matrix, "Applies DoP optical physics")
  Rel(routes, ai_service, "Executes prompt-to-image synthesis")
  Rel(ai_service, gcp_client, "Calls Google GenAI & Imagen 3")
  Rel(routes, gcp_client, "Archives PDF scripts to GCS")
  Rel(routes, recon, "Runs discrepancy reconciliation")
  Rel(recon, spine, "Appends discrepancy events")
  Rel(routes, spine, "Appends consensus resolutions")
```

---

## 4. Level 4: Dynamic Runtime Sequence Diagram
Shows the step-by-step lifecycle when a user edits a camera prompt and renders a photorealistic 35mm concept frame.

```mermaid
sequenceDiagram
    autonumber
    actor User as Director / DoP
    participant UI as React Script Studio
    participant API as FastAPI Gateway
    participant DoP as DoP Compiler
    participant GCP as Google GenAI SDK (Imagen 3)
    participant GCS as Google Cloud Storage
    participant Spine as ClickHouse Event Spine

    User->>UI: Selects Camera C & edits prompt (+ Volumetric Haze, + Anamorphic Streak)
    User->>UI: Presses Ctrl + Enter ("Execute & Render Camera C")
    UI->>API: POST /api/script/generate-storyboard (prompt, Cam C, 85mm T1.4, Deakins 5600K, 4:1)
    API->>DoP: compile_dop_generative_prompt()
    DoP-->>API: 35mm Motion Picture Cinema Still, 85mm Macro T1.4, 5600K, Kodak 500T...
    API->>GCP: client.models.generate_images(model="imagen-3.0-generate-002", prompt=...)
    GCP-->>API: Returns 8K Generated Image Bytes
    API->>GCS: upload_media_to_google_cloud_storage(image_bytes, "previz/shot_27_cam_c.jpg")
    API->>Spine: append_event("PREVIZ_FRAME_GENERATED", {shot_id, cam_letter: "C", uri})
    API-->>UI: 200 OK (image_url, compiled_prompt, provider: "Google Imagen 3")
    UI-->>User: Displays new photorealistic 35mm film still with "Live AI Diffusion" badge
```

---

## ⚡ 5. Append-Only Event Spine & Live SSE Fan-Out Architecture

### Animated Event System Diagram (SMIL SVG)

![CineSpine Event System Animated](architecture/cinespine-event-system-animated.svg)

### Event Sourcing & State Projection Model

```mermaid
flowchart LR
    subgraph Producers["1. Event Producers"]
        P1["Document Parser"]
        P2["3-Axis Reconciliation"]
        P3["Consensus Hub"]
        P4["Previz Studio"]
    end

    subgraph EventSpine["2. ClickHouse Event Spine (Immutable)"]
        direction TB
        E1["#8492 [TAKE_EXTRACTED]<br/>Slate 27/3 • Take 3"]
        E2["#8493 [DISCREPANCY_FLAGGED]<br/>False Start vs Good"]
        E3["#8494 [PREVIZ_GENERATED]<br/>Cam C 85mm T1.4"]
        E4["#8495 [DISCREPANCY_RESOLVED]<br/>Consensus Recorded"]
        E1 --> E2 --> E3 --> E4
    end

    subgraph Broker["3. LiveEventBroker (SSE)"]
        B1["/api/events/subscribe"]
        B2["Role Filter: SOUND / CAMERA / EDITORIAL"]
        B3["User Dispatch: @director"]
    end

    subgraph Consumers["4. Reactive Client State"]
        C1["Discrepancy Matrix (Auto-Updates)"]
        C2["Previz Canvas (Real-Time Render)"]
        C3["Toast Notifications (@director)"]
        C4["Grafana Telemetry & Sync Lag"]
    end

    Producers -->|"append_event"| EventSpine
    EventSpine -->|"broadcast"| Broker
    Broker -->|"Server-Sent Events"| Consumers
```

### Event System Guarantees:
1. **Zero Mutation Invariant:** Events are append-only. Takes and slates are never updated in place; state is computed as a fold over historical events.
2. **Auditability & Traceability:** Every discrepancy resolution, consensus vote, and prompt modification records the originating practitioner handle (`@assistant_editor`, `@director`) and UTC timestamp.
3. **Non-Blocking Real-Time Fan-Out:** The FastAPI `LiveEventBroker` utilizes asynchronous Server-Sent Events (SSE) scoped by `production_id`, `shoot_day`, and user handle to push live updates with sub-millisecond latency and zero browser polling.

