# CineSpine — Devpost Submission Package
**Hackathon:** [Agentic Cinema: The Blockbuster Hackathon (Google Cloud & Partners)](https://agentic-cinema.devpost.com/)  
**Track:** ClickHouse (one partner track per entry). Gemini and Google Cloud Agent Development Kit throughout; ClickHouse Cloud reached by the agents only through the official `mcp-clickhouse` MCP server.  
**Repository:** [https://github.com/ftenaf/cinespine](https://github.com/ftenaf/cinespine)  
**Live Application:** [https://cinespine-35447568692.europe-west4.run.app](https://cinespine-35447568692.europe-west4.run.app) (Google Cloud Run, europe-west4)  

---

## 🎬 1. Project Title & Elevator Pitch

### **Project Title:**
**CineSpine**

### **Tagline / Short Pitch (under 200 characters):**
*The autonomous append-only event spine and 3-axis discrepancy engine for film production: orchestrating script-to-screen intent, multi-camera AI previz, and real-time department reconciliation.*

---

## 💡 2. Inspiration: The Hidden Crisis of Film Production

On a major motion picture or high-end television series, hundreds of millions of dollars are spent across dozens of specialized departments: **Office, Set, Sound, Camera, DIT, Editorial, VFX, Colour, and Mastering.**

Yet, the greatest threat to a production is almost never the creative performance—it is **the silent breakdown of communication, paperwork, and handoffs between departments.**

Every department maintains its own version of the truth:
- **The Office** documents what *should* happen (Call sheets, one-liners, actor schedules, shot plans).
- **The Set** documents what they *believe* happened (Script supervisor logs, sound rolls, camera logs, false takes).
- **The Lab / DIT** ingests what *physically exists* on the storage drives (Camera raw clips, checksums, BWF audio tracks).

When a script supervisor notes a take as *False Start*, but the sound recordist files it as *Good*, or when a roll spelling typo masks 4 missing audio channels, **no crash or error is thrown.** The system silently accepts the disagreement. Weeks later in the post-production conform, the mistake explodes into catastrophic delays, missing footage panic, and emergency $200,000 reshoots.

We built **CineSpine** around a radical single principle:  
> *"A document is a witness. Witnesses disagree, and **the disagreement is the product**."*

---

## 🚀 3. What It Does

CineSpine is an end-to-end autonomous film production operating system that unites logistical event reconciliation with creative generative cinematography.

### 🏛️ A. The 3-Axis Reconciliation Engine
CineSpine continuously tracks every production fact across **Three Immutable Axes**:
1. **Intent (Office / Script):** Screenplay scenes, scheduled takes, cast requirements, DoP lighting design.
2. **Belief (Set / Crew):** Live reports from script supervisors, sound engineers, and camera assistants.
3. **Existence (DIT / Storage):** Verified media assets, file checksums, frame durations, and track counts.

Whenever a discrepancy emerges (e.g., audio file missing on disk, take labeled circled on set but absent from call sheet, camera roll naming collision), CineSpine’s reconciliation engine surfaces it with sub-millisecond precision and alerts the responsible department heads via an interactive triage dashboard.

---

### 🎥 B. AI Script & Multi-Camera Previz Studio
CineSpine bridges the gap between the writer's words and the Director of Photography's lens:
- **Multi-Format Screenplay Ingestion:** Drag and drop `.fountain`, `.pdf`, `.fdx`, or `.txt` screenplays with automatic scene, character, action, and dialogue parsing.
- **Autonomous 3-Camera Rig Coverage (Cameras A, B, C):** Automatically calculates coverage geometry:
  - **Camera A (Master Wide):** $24\text{mm}–35\text{mm}$, wide spatial architecture, motivated master lighting.
  - **Camera B (Medium / OTS):** $50\text{mm}–75\text{mm}$, character emotional reaction, dialogue depth.
  - **Camera C (Tactile Macro / Dutch Angle):** $85\text{mm}–100\text{mm}$, shallow depth of field, high-tension inserts.
- **Master DoP Cinematography Matrix:** Select legendary cinematographic styles (*Roger Deakins, David Fincher, Greig Fraser, Gordon Willis, Emmanuel Lubezki, Wes Anderson*) with exact Kelvin color temperatures ($3200\text{K}–6500\text{K}$), Key-to-Fill lighting ratios ($1:1$ to $16:1$), and 35mm film stock LUT emulations (*Kodak Vision3 500T 5219, Fujifilm Eterna*).
- **Interactive Prompt Console & Real-Time AI Generation:** Edit camera prompts on the fly, tap one-click modifier chips (`+ Volumetric Haze`, `+ Anamorphic Streak`, `+ Rain Reflections`), and render photorealistic 35mm concept frames in real-time.

---

### 📡 C. Append-Only Event Spine, ClickHouse Mirror & Live Notification Bus
Every take, log modification, checksum verification, and discrepancy status is written to an immutable event spine, then mirrored into ClickHouse Cloud (`production_events`, `takes_meta`, `audit_discrepancies`, `requirement_events`, `editorial_tag_events`, `user_activity`). Crew members subscribe to real-time event streams filtered by department role (`@director`, Sound, Camera, Editorial), preventing silos and ensuring zero information loss. On Cloud Run the spine survives deploys and restarts: Litestream streams the SQLite WAL to Cloud Storage and restores it on boot.

### 🤖 D. The Wrap Rescue Agent: Google ADK with ClickHouse as its memory
At wrap, the producer needs to know what will stop tomorrow's shoot. The Wrap Rescue Agent is built on Google's Agent Development Kit and never touches the database directly: it talks to the official ClickHouse MCP server (`mcp-clickhouse`, running as its own Cloud Run service), `list_tables` first, then five `run_select_query` calls for unresolved discrepancies, unacknowledged requirements, throughput, ageing and roll matching, every tool call shown on screen. Gemini ranks the blockers and drafts the handoff memo, walking the model chain when one model is overloaded. Then the agent acts: it files a requirement for each blocker, assigned to the owning department, and delivers the memo as a notification to whoever ran it and to the production's director, producers and post supervisors. The requirements land in the same spine, mirror back to ClickHouse, and the loop closes. Every run is a single trace in Grafana Cloud: ADK, MCP tool calls, ClickHouse, Gemini, with token counts.

### 🧭 E. "Where do we stand": one ranked answer, for people and for agents
`GET /api/productions/{id}/status` answers the producer's real question in five buckets: done, running, blocking, left, missing. Every item carries a severity and an age and the worst, oldest thing is always first; "missing" is inference and each item names the rule that inferred it. The production dashboard draws it as the "Where do we stand" card, and the same answer is exposed as a WebMCP tool (`summarize_production_status`) so an agent driving the browser can ask instead of scraping. Beside it, the crew workload card reads the `user_activity` ledger in ClickHouse: every mutation any user makes is a row, so who owns what sits next to who did what.

---

## 🛠️ 4. How We Built It: Architecture & Tech Stack

```mermaid
flowchart TB
    subgraph Ingestion["1. Multi-Department Data Ingestion"]
        S1["Screenplay (.pdf / .fountain)"]
        S2["Call Sheets & One-Liners"]
        S3["Set Reports (Script Sup / Sound)"]
        S4["DIT Checksums & Storage Ingest"]
    end

    subgraph CoreEngine["2. CineSpine Backend Gateway"]
        P1["Fountain / PDF Parser"]
        B1["3-Camera Previz Synthesizer"]
        R1["3-Axis Discrepancy Engine"]
        E1["Append-Only Event Spine Engine"]
    end

    subgraph PartnerStack["3. Partner Ecosystem & AI Stack"]
        CH[("ClickHouse Cloud: analytical mirror")]
        MCP["mcp-clickhouse (official MCP server, Cloud Run)"]
        ADK["Wrap Rescue Agent (Google ADK + Gemini)"]
        GEM["Gemini text + image models"]
        GF["Grafana Cloud: traces, metrics, logs"]
    end

    subgraph FrontendStudio["4. React Production Studio"]
        UI1["Production Overview Dashboard"]
        UI2["3-Axis Discrepancy Matrix"]
        UI3["Script & Multi-Cam Previz Studio"]
        UI4["Crew Notification Center"]
    end

    S1 & S2 & S3 & S4 --> CoreEngine
    CoreEngine --> CH & GEM & GF
    GEM --> B1
    E1 --> CH
    ADK --> MCP --> CH
    ADK --> GEM
    ADK --> E1
    CoreEngine --> FrontendStudio
```

### **The Enterprise Technology Stack:**
- **Google Cloud & Gemini Enterprise Agent Platform:**
  - **Google Agent Development Kit (ADK):** the Wrap Rescue Agent and the assistant-editor queue agent; tool calls, memo drafting and requirement writes as one traced run.
  - **Gemini text models (`gemini-2.5-flash`, with `gemini-3.5-flash`, `gemini-3.6-flash` and `gemini-2.5-flash-lite` as the fallback chain):** screenplay decomposition, character inference in concurrent batches, scene breakdown into three synchronized camera setups, blocker ranking and the handoff memo.
  - **Gemini image models (`gemini-3.1-flash-image` → `gemini-3-pro-image` → `gemini-2.5-flash-image`, via `generate_content`):** Photorealistic 35mm cinema concept frame synthesis; a labelled placeholder when none answers.
- **ClickHouse (High-Throughput Event Spine):**
  - High-performance, append-only time-series storage storing millions of immutable events (takes, checksums, logs, reconciliation diffs) with zero data mutation.
- **Backend Architecture (Python 3.14 + FastAPI + Pydantic v2):**
  - High-performance asynchronous API gateway with SSE event broadcasting.
  - Gemini image-model generation service for hackathon-safe concept frames.
  - Strict 3-axis reconciliation algorithms.
- **Frontend Experience (React 18 + Vite + Tailwind CSS + Lucide Icons):**
  - High-contrast, dark-mode cinematic interface engineered for set monitors and DIT carts.
  - 3-Camera switcher, interactive multi-view grid, and full-screen lightbox inspection.
- **ClickHouse Cloud (partner track):** the analytical mirror of the spine: `production_events`, `takes_meta`, `audit_discrepancies`, `requirement_events`, `editorial_tag_events`, `user_activity`. Every analytics panel, the crew workload ledger and the production status endpoint are ClickHouse queries; the Wrap Rescue Agent reads it through `mcp-clickhouse` (`list_tables`, `run_select_query`) and never with a direct connection.
- **Observability (supporting):** OTLP traces, metrics and logs to Grafana Cloud from both halves, browser (Faro) and backend; every Gemini generation and MCP tool call is a span with token counts, and the Wrap Rescue dashboard shows one agent run end to end.
- **Persistence on Cloud Run:** single instance by design, SQLite spine replicated continuously to Cloud Storage with Litestream and restored on boot, so a deploy never loses a production.
- **Development tooling disclosure:** an AI coding assistant (Anthropic's Claude Code) was used during development, as a developer tool. The submitted software calls Google Cloud AI only (Gemini via the GenAI SDK and Vertex AI, Google ADK) plus the official ClickHouse MCP server. No non-Google model, agent framework or AI API is used by or bundled with the project.

---

## 🧗 5. Challenges We Ran Into

1. **The "Confident Nothing" Trap in Document Parsing:**
   Traditional PDF parsers often silently return 0 rows when encountering irregular script supervisor tables, leading downstream systems to believe no work occurred. We engineered strict invariant assertions and multi-strategy layout extractors so that incomplete parses fail visibly rather than creating dangerous silence.
2. **Distinguishing "Absence of a Report" from "Missing Material":**
   A shooting day where the sound team has not yet offloaded their cards is completely different from a day where an audio file was lost. CineSpine treats time-fenced expectation states differently from confirmed file absence.
3. **A trace that was silently not there:**
   Cloud Run's front end forwards every request with a `traceparent` whose sampled flag is off, and the OpenTelemetry default sampler honoured it: every agent run triggered from the API exported no spans at all, with no warning anywhere, while browser-driven traces arrived because Faro's flag is on. The fix is a sampler and propagator that treat an unsampled remote parent as no parent. Found by sending the same request with and without a sampled header.
4. **Multi-Camera Prompt Coherence:**
   Ensuring that Cameras A, B, and C generated coherent perspectives of the exact same fictional space required building an automated **Cinematography Compiler** (`compile_dop_generative_prompt`) that binds focal lengths, lighting ratios, and DoP aesthetic tokens into every prompt.

---

## 🏆 6. Accomplishments That We're Proud Of

- **Green Automated Test Suite:** 1,067 backend tests (unit, integration, API) and 154 frontend tests, all passing.
- **An agent that closes its own loop:** ranked blockers from ClickHouse through the official MCP server, requirements filed and assigned, memo delivered to the people it was written for, the whole run visible as one trace.
- **True Cross-Department Discrepancy Resolution:** Successfully parsed and reconciled complex historical film production data (*e.g., the Day 31 Great Hall shoot*) in sub-millisecond execution times.
- **Seamless Creative & Technical Fusion:** Empowering directors and cinematographers to instantly visualize 3-camera setups with real DoP optical physics and photorealistic AI rendering.

---

## 🧠 7. What We Learned

- **Cinema Production is a Distributed System:** Film sets are chaotic, real-time asynchronous distributed systems where human operators act as nodes. Building tools for this domain requires event-driven architecture, append-only immutability, and fault-tolerant witness reconciliation.
- **Agentic AI Shines as a Multi-Department Orchestrator:** Rather than replacing human artists, agentic systems excel at eliminating the invisible friction, miscommunication, and paperwork silos that drain film budgets.

---

## 🔮 8. What's Next for CineSpine

- **Temporal Motion Previz:** Integrating Google Lumiere and video generation models to generate 4-second synchronized camera motion previews (dolly moves, crane shots, steadicam tracks).
- **Direct Camera & Sound Hardware Integrations:** Streaming metadata directly from ARRI Alexa, RED V-Raptor, and Sound Devices 833/Scorpio recorders via WiFi/IP on set.
- **Dialogue-versus-script audio check:** transcribe the sound department's take audio with Gemini, compare it with the scene's dialogue, and file `DIALOGUE_DRIFT` discrepancies into the same spine so the Wrap Rescue Agent ranks them with everything else.
- **Automated Wrap Reports & Executive Briefs:** One-click generation of studio-compliant Daily Production Reports (DPRs), cost variance projections, and executive daily recaps.

---

## 📦 9. Links & Deliverables

- **GitHub Repository:** [https://github.com/ftenaf/cinespine](https://github.com/ftenaf/cinespine)
- **License:** Open Source MIT License (included in root repository)
- **Video Demo (3-Minute Trailer):** *[YouTube / Vimeo Link]*
- **Documentation & Architecture:** `docs/` and `docs/architecture/` (runtime, events-and-agents, AI-usage diagrams)
- **Grafana Cloud dashboard:** Wrap Rescue Agent, one run end to end (`grafana/dashboards/wrap_rescue_agent.json`)
