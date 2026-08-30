# CineSpine Architecture & Agent Context

Welcome to the CineSpine repository! This file provides the core architecture, stack, and domain knowledge you need to instantly understand the project. **Do not waste time exploring to find this information.**

## Project Overview
**CineSpine** is an Autonomous Append-Only Event Spine, 3-Axis Discrepancy Engine, and Multi-Camera AI Previz Studio for Film & TV Production.
It handles real production paperwork, resolves discrepancies across departments, and generates multi-camera photorealistic storyboards.

## Tech Stack & Locations

### 1. Frontend (React 18, Vite, Tailwind CSS)
- **Directory:** `frontend/`
- **Port:** `5173` (`npm run dev`)
- **Key Components:**
  - `src/components/ScriptStudio.tsx`: The main creative cockpit. Handles Screenplay parsing, Cast Profiling, and the AI Previz Studio.
  - `src/components/DopControls.tsx`: Reusable Director of Photography controls (Focal Length, T-Stop, Presets) used globally and for per-camera overrides.
  - `src/optics.ts` / `src/types.ts`: Contains core mathematical models for sensor geometry, Depth of Field (Circle of Confusion), and interface definitions.

### 2. Backend (Python 3.11+, FastAPI)
- **Directory:** `backend/`
- **Port:** `8000` — run from the **repository root**, not from `backend/`:
  `python -m uvicorn backend.app.main:app --reload --port 8000`
  (modules import each other as `backend.app.*`, so `app.main:app` from inside
  `backend/` fails with `ModuleNotFoundError: No module named 'backend'`.)
- **Key Modules:**
  - `app/api/routes.py`: FastAPI endpoints bridging the frontend to the engine.
  - `app/script/parser.py`: Parses multiple screenplay formats (`.fountain`, `.md`, `.txt`, `.pdf`).
  - `app/script/breakdown_engine.py`: Manages the multi-camera coverage logic (Cam A, B, C, D).
  - `app/script/storyboard_generator.py`: Generates the AI multi-camera concepts via Google Imagen 3.
  - `app/script/dop_presets.py`: Master DoP style presets.

### 3. Data & Infrastructure
- **Event Spine:** ClickHouse / SQLite (`spine.db`). Immutable append-only log of documents, take facts, and discrepancies.
- **GCS:** Google Cloud Storage for media archival.

## What has been learned here

`references/` holds what working on this codebase has taught: the decisions whose reasoning would
otherwise be rediscovered, the defects already paid for once, and the questions nobody has answered.
Start at [references/index.md](references/index.md).

Read it **before** changing ingestion, persistence, the analytical mirror, or anything that serves a
source document. Three of those have produced the same mistake more than once.

The requirements this build is measured against live in a separate workspace,
`E:/projects/agentic-cinema-design`. That decides what must be true; `references/` records what is true
here. The current gap between them is [references/findings/spec-drift.md](references/findings/spec-drift.md).

## Domain Model: The 3 Axes
The core of the discrepancy engine relies on checking alignment across three axes:
1. **Intent:** What the Office planned (Screenplay, Prep).
2. **Belief:** What the Set says happened (Script Supervisor Logs, Sound Mixer ALEs).
3. **Existence:** What is physically on the disk (DIT Silverstack offloads, checksums).
Disagreements between these axes are the primary product of the event spine.

## Agent Guidelines & Tools
1. **Graphify:** This project uses a Graphify knowledge graph (`graphify-out/`). When answering architectural questions, use `graphify query` instead of grepping files.
2. **CodeGraph:** `.codegraph/` is enabled. Use the `codegraph_explore` tool for jumping directly to symbol definitions and call paths.
3. **Testing:** The backend uses `pytest` and currently runs 159 tests (7 skipped without local example PDFs), plus 49 frontend tests via `npm test` in `frontend/`. Ensure no regressions occur when modifying backend logic.
4. **State Management:** The frontend heavily utilizes React Hooks and `localStorage` for client-side persistence (e.g., custom DoP presets), reserving the backend API for heavy lifting (AI generation, event sourcing).
