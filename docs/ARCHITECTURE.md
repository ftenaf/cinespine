# 🏛️ CineSpine — C4 Architecture Documentation

> Comprehensive structural, container, component, and runtime sequence architecture documentation for **CineSpine** following the **C4 Model**.

**Companion documents:**

- [CLICKHOUSE_MCP.md](CLICKHOUSE_MCP.md) — the contract between the Wrap Rescue
  Agent and the official `mcp-clickhouse` server: tool names, result shapes,
  and why a failed call there can look like a successful one.
- [DEMO_DATA.md](DEMO_DATA.md) — the relationships the demo fixtures in
  `data/examples/` must satisfy for reconciliation and the editorial queue to
  show anything.
- [CLOUD_RUN_DEPLOY.md](CLOUD_RUN_DEPLOY.md) — deploying as a single Cloud Run
  service, and the SQLite constraint that decides its instance count.
- [OBSERVABILITY.md](OBSERVABILITY.md) — what reaches Grafana Cloud, how the
  agents' model calls are traced for Agent Observability, and the CORS failure
  that looks identical from both ends.

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
  System_Ext(gemini_api, "Google Cloud Gemini & Imagen 3", "Extracts semantic narrative tension & synthesizes 35mm concept stills")
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
    Container(wrap_agent, "Wrap Rescue Agent", "Google ADK, backend.app.agents.wrap_rescue", "Ranks end-of-day blockers from the analytical mirror and files them as requirements")
    Container(queue_agent, "Assistant Editor Queue Agent", "Google ADK, backend.app.agents.editorial_queue", "Proposes discrepancy-free scenes for assistant editorial turnover")
    ContainerDb(event_store, "Append-Only Event Spine", "SQLite / ClickHouse DB", "Immutable store for raw documents, parsed take facts, discrepancies, and audit trails")
  }

  System_Ext(mcp_clickhouse, "mcp-clickhouse", "Official ClickHouse MCP server (FastMCP streamable HTTP). The agent's only route to the analytical mirror")

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
  Rel(api_gateway, wrap_agent, "Runs end-of-day rescue for a production/day")
  Rel(wrap_agent, mcp_clickhouse, "list_tables, run_select_query", "JSON-RPC / HTTP")
  Rel(mcp_clickhouse, event_store, "SELECT against the analytical mirror")
  Rel(wrap_agent, event_store, "Appends ranked blockers as requirements")
  Rel(api_gateway, queue_agent, "Plans assistant editorial batches")
  Rel(queue_agent, event_store, "Reads scene evidence, appends turnover requirements")
```

> The Wrap Rescue Agent reaches ClickHouse **only** through `mcp-clickhouse`;
> there is no direct driver on that path. That indirection is deliberate — the
> partner component has to be on the runtime path, not beside it — but it means
> a broken tool call is the difference between "the day is clear" and "nothing
> was read". [CLICKHOUSE_MCP.md](CLICKHOUSE_MCP.md) records the contract and the
> guarantees that keep those two apart.

---

## 3. Level 3: Component Diagram (Backend Core)
Details the internal components of the CineSpine Python FastAPI service.

```mermaid
C4Component
  title Component Diagram - CineSpine Core Backend Subsystems

  Container_Boundary(backend_core, "CineSpine FastAPI Service") {
    Component(routes, "API Route Handlers", "backend.app.api.routes", "REST and SSE endpoints for /api/script/*, /api/takes, /api/discrepancies")
    Component(script_parser, "Screenplay Ingestion Engine", "backend.app.script.parser", "Parses Fountain, Markdown, plaintext, PDF and FDX into scenes, cast and relationships")
    Component(char_ai, "Character Inference", "backend.app.script.character_ai", "Sends per-character script evidence to Gemini, then validates the answer for specificity")
    Component(char_store, "Character Profile Store", "backend.app.spine.character_store", "SQLite persistence of screenplays and hand-edited character profiles")
    Component(breakdown, "Multi-Camera Previz Engine", "backend.app.script.breakdown_engine", "Calculates synchronized camera rigs per setup")
    Component(dop_presets, "DoP Style Presets", "backend.app.script.dop_presets", "Master cinematographer style profiles and override resolution")
    Component(ai_service, "AI Generative Service", "backend.app.script.ai_image_service", "Calls Google Imagen with the compiled DoP prompt")
    Component(gcp_client, "Google Cloud Integration Client", "backend.app.integrations.google_cloud", "Wraps google.genai and google.cloud.storage clients")
    Component(recon, "3-Axis Reconciliation Engine", "backend.app.reconciliation.engine", "Executes multi-witness diffing algorithms")
    Component(spine, "Append-Only Event Spine", "backend.app.spine.writer", "ClickHouse / in-memory append-only event and document store")
  }

  Rel(routes, script_parser, "Parses uploaded script bytes")
  Rel(routes, char_ai, "Infers cast appearance, wardrobe and facial detail")
  Rel(char_ai, gcp_client, "Calls Gemini for grounded character profiles")
  Rel(routes, char_store, "Stores and reads character profiles")
  Rel(char_store, spine, "Reached through the spine writer facade")
  Rel(routes, breakdown, "Generates multi-camera coverage")
  Rel(breakdown, dop_presets, "Applies master DoP style")
  Rel(routes, ai_service, "Executes prompt-to-image synthesis")
  Rel(ai_service, gcp_client, "Calls Google GenAI & Imagen 3")
  Rel(routes, gcp_client, "Archives uploaded scripts to GCS")
  Rel(routes, recon, "Runs discrepancy reconciliation")
  Rel(recon, spine, "Appends discrepancy events")
  Rel(routes, spine, "Appends consensus resolutions")
```

### Note on optical computation

There is deliberately **no backend DoP optics component**. Sensor geometry, angle of view, depth of field
and delivery resolution are computed in the browser (`frontend/src/optics.ts`) because they must respond
to a slider without a round trip. The backend holds *style* (`dop_presets.py`), not *physics*. The two
meet only in the compiled image prompt.

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

## 5. Character Profile Lifecycle

A character profile is the one artefact in the Script Studio a human authors by hand, and it drives every
generated frame that character appears in. Four properties follow from that, and the design exists to
guarantee them.

```mermaid
flowchart TD
  U["Screenplay uploaded"] --> P["Parse<br/>scenes, cast, relationships"]
  P --> ID["script_id = hash(script text)"]
  P --> SEED["Seed profiles from the script itself<br/>action-line appositives, dialogue"]
  SEED --> AI{"Inference<br/>available?"}
  AI -- no --> WARN["Keep script-derived profile<br/>+ parse warning"]
  AI -- yes --> GEM["Gemini: grounded per-character evidence"]
  GEM --> VAL{"Specific<br/>enough?"}
  VAL -- no --> RETRY["One targeted retry<br/>naming the weak fields"]
  RETRY --> VAL2{"Better?"}
  VAL2 -- no --> WARN2["Report which characters stayed generic"]
  VAL2 -- yes --> MERGE
  VAL -- yes --> MERGE["Merge into stored profiles"]
  WARN --> MERGE
  WARN2 --> MERGE
  MERGE --> STORE[("SQLite<br/>character_profiles")]
  STORE --> UI["Cast profiler (editable)"]
  UI -- "user edits" --> STORE
  STORE --> PROMPT["Scene image prompt<br/>only characters present in that scene"]
```

**1. Identity is content-derived.** `script_id` is a hash of the normalised screenplay text, so
re-uploading the same script resolves to the same profiles instead of regenerating them.

**2. The merge is asymmetric, on purpose.** Structural fields (dialogue counts, scene presence,
relationships) always come from the fresh parse. Fields a human has edited always win. An edited
character who disappears from a later draft is retained and flagged, not deleted.

**3. Inference can never fail an upload.** Missing key, error, timeout, unparseable output and partial
coverage each leave the script-derived profile in place and add a parse warning. The user is told what
happened rather than shown a silent downgrade.

**4. Specificity is measured, not requested.** A prompt cannot guarantee that "a striking screen presence"
does not come back. Each free-text field is checked for filler words, placeholder phrasing, minimum length
and at least one concrete noun. Only demonstrably better text replaces a weak field.

---

## ⚡ 6. Append-Only Event Spine & Live SSE Fan-Out Architecture

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

### The activity ledger (`user_activity`)

Beside the event spine, which records what a production did, `user_activity`
records what people did to the tool. SQLite is the source of truth and
ClickHouse holds the mirror, like every other store.

Two kinds of row, kept apart in every query and never summed:

- **Views** (`viewed`, `acknowledged`): what a person tells us about their
  attention. Written by the Requirements board through `POST /api/activity`.
- **Mutations** (`created`, `updated`, `resolved`, `reopened`, `deleted`,
  `tagged`, `uploaded`, `linked`, `unlinked`, `ran_agent`): what the API saw
  them change. Written server-side by `_record()` in `backend/app/api/routes.py`
  after every mutation route's write succeeds, so no surface can forget to.
  Never raises: the write it describes has already happened.

Target types: `requirement`, `discrepancy`, `notification`, `shoot_day`,
`scene`, `shot`, `take`, `document`, `production`, `crew`, `script`,
`breakdown`, `tag`, `agent`. The vocabulary is closed; an unknown verb or
target is refused, not stored (`backend/app/spine/activity_store.py`).

Two rules that keep the numbers honest:

- **`actor_source=default`.** A route whose body names nobody (productions,
  crew, script links, breakdowns, bare uploads) records the change under
  `@director` and tags the row's `context_json` with `actor_source: default`.
  Per-person queries exclude those rows; per-department queries keep them.
  The change happened; crediting the director with it would be a fiction.
- **No free text.** `context_json` passes through `analytics.safe_properties`,
  the same blocklist product analytics applies, so a title, note or filename
  cannot reach the ledger by way of a new call site.

What reads it: `GET /api/analytics` carries `actions_by_actor_and_day`,
`actions_by_department_and_hour` and `first_touch_lag`
(`backend/app/spine/analytics.py`), and the production dashboard's Activity
card draws them beside Crew workload. The card says the one thing the
numbers cannot: a count of actions is activity, not effort. Identity is the
self-declared `@handle` from the passwordless login, so per-person figures
are honor-system until there is auth.
