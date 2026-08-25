# CineSpine - C4 Architecture Documentation

> Comprehensive C4 Model Diagrams (System Context, Containers, Components, and Dynamic Workflows) for the CineSpine Event-Sourced Film & TV Production Reconciliation Platform.

---

## 1. Level 1: System Context Diagram

The System Context diagram illustrates CineSpine within the film and television production environment, showing external stakeholders, departmental hardware, and external cloud services.

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

## 2. Level 2: Container Diagram

The Container diagram zooms into CineSpine to show the high-level technical building blocks: the frontend single-page application, FastAPI application, real-time SSE broker, ingestion pipeline, and data storage.

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

## 3. Level 3: Component Diagram (FastAPI Backend)

The Component diagram shows the modular structure of the backend application in `backend/app/`.

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

## 4. Level 4: Dynamic Diagram (Collaborative Ingestion & Resolution Flow)

This Dynamic diagram tracks the end-to-end event sequence when a new document is dropped, a discrepancy is flagged, and an editor resolves it.

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
