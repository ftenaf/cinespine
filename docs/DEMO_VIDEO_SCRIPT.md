# 🎬 CineSpine — 3-Minute Demo Video Walkthrough Script
**Target Duration:** 2:45 – 3:00  
**Format:** Screen Recording with Voiceover Narration  
**Platform:** YouTube / Vimeo (Public Link for Devpost)  

---

## ⏱️ Timeline & Scene Breakdown

### [0:00 – 0:30] Hook & The Core Problem
* **Visual:** Close-up on fragmented production paperwork (Call Sheet PDF, Script Supervisor log with handwritten notes, Sound ALE report, Silverstack volume manifest).
* **Voiceover:**
  > *"Every day on a film set, hundreds of thousands of dollars are spent across camera, sound, script, and editorial departments. But the biggest cost overrun in cinema isn't creative—it's communication. Every department maintains its own version of the truth: the Office plans what SHOULD happen, the Set logs what they BELIEVE happened, and the DIT verifies what EXISTS on disk. When they disagree, no alarm sounds—until weeks later in the post-production conform, resulting in massive reshoots and lost footage."*

---

### [0:30 – 1:15] The 3-Axis Discrepancy Reconciliation Engine
* **Visual:** Switch to CineSpine UI (`http://localhost:5173`) $\rightarrow$ **Production Overview** and **Discrepancy Matrix**.
* **Action:**
  1. Click on **Scene 27 / Day 31 (Demo Production)**.
  2. Point out the 3 active discrepancy cards:
     - *Card 1: Silent False Start on Take 3 (Script supervisor flagged False Start, Sound labeled Good).*
     - *Card 2: Missing Audio Track on Take 5 (Roll A120 vs A_0120 naming collision).*
  3. Click **"Consensus Triage"** and resolve the discrepancy live with one click.
  4. Show the real-time Notification Toast dispatching to `@director` and the Sound Department.
* **Voiceover:**
  > *"Meet CineSpine. Built on an immutable append-only event spine in ClickHouse, CineSpine treats every document as a witness. Our 3-Axis Reconciliation Engine continuously checks Intent against Belief against Existence. Here on Day 31 of 'Demo Production', CineSpine instantly catches a silent false start on Take 3 and an unlinked audio track caused by a roll naming collision. In one click, the assistant editor reaches consensus, immediately notifying the crew via our real-time notification bus."*

---

### [1:15 – 2:15] AI Script & Multi-Camera Previz Studio
* **Visual:** Click on the **Script & Previz Studio** tab.
* **Action:**
  1. Show the 3-column studio layout: Column 1 (Scenes), Column 2 (Multi-Camera Shot List), Column 3 (Previz Canvas & Prompt Console).
  2. Switch between **Camera A (35mm Master Wide)**, **Camera B (50mm Over-The-Shoulder)**, and **Camera C (85mm Macro Keys/Stops)**.
  3. Switch to **3-Camera Multi-View Grid** showing all three synchronized camera angles side-by-side.
  4. In the editable prompt console, type: *"+ Volumetric Haze, + Anamorphic Streak Flare, + Extreme Close-Up Eyes"*.
  5. Press **Ctrl + Enter** or click **"Execute & Render Camera C AI Concept"**.
  6. Watch the live generation spinner resolve to a new photorealistic AI still powered by **Google Imagen 3 / FLUX.1 Diffusion**.
* **Voiceover:**
  > *"Now, let's step onto the director's floor. CineSpine's Script Studio ingests Fountain and PDF screenplays, autonomously breaking down every scene into a synchronized 3-camera rig: Camera A for the master spatial architecture, Camera B for over-the-shoulder character performance, and Camera C for intense tactile inserts. Using our Director of Photography matrix—featuring Roger Deakins, David Fincher, and Greig Fraser presets—CineSpine calculates true optical physics, lighting contrast ratios, and film stock LUTs. You can edit the camera prompt live, tap one-click cinematography chips, and render photorealistic 35mm film stills in real-time powered by Google Cloud Gemini and Imagen 3."*

---

### [2:15 – 2:45] Google Cloud Architecture & Developer Rigor
* **Visual:** Quick switch to terminal/code showing:
  - `pytest -v` running 100/100 tests green.
  - `backend/app/integrations/google_cloud.py` showing `google.genai` and `google.cloud.storage` SDK imports.
  - `GET /api/integrations/google-cloud` returning `{"status": "online", "gemini_model": "gemini-flash-latest"}`.
* **Voiceover:**
  > *"Under the hood, CineSpine runs on Python FastAPI, ClickHouse, and the official Google GenAI and Google Cloud Storage SDKs, backed by a 100% green automated test suite. Screenplays and media are archived directly to Google Cloud Storage, while Gemini Enterprise coordinates multi-agent analysis."*

---

### [2:45 – 3:00] Conclusion & Call to Action
* **Visual:** Return to CineSpine Studio with all 3 camera frames illuminated, displaying the project tagline.
* **Voiceover:**
  > *"CineSpine bridges the gap between creative visual storytelling and flawless production data integrity. Lights. Camera. Code. Thank you."*
