# Google Cloud & Gemini Enterprise Integration Guide

## 1. Overview
CineSpine incorporates native, runtime integration with Google Cloud and the Gemini Enterprise Agent Platform.

```
+-------------------------------------------------------------------------------+
|                             Google Cloud Platform                             |
|                                                                               |
|  +-------------------------+  +----------------------+  +------------------+  |
|  |      Gemini Flash       |  |       Imagen 3       |  |  Google Cloud    |  |
|  |  Screenplay Breakdown   |  |   35mm Cinema Stills |  |     Storage      |  |
|  |  & Tension Extraction   |  | (imagen-3.0-generate)|  | (PDFs & Media)   |  |
|  +------------^------------+  +-----------^----------+  +--------^---------+  |
|               |                           |                      |            |
+---------------|---------------------------|----------------------|------------+
                |                           |                      |
                |                           |                      |
+---------------|---------------------------|----------------------|------------+
|        google.genai SDK            google.genai SDK     google.cloud.storage  |
|                                                                               |
|                         CineSpine Backend Gateway                             |
+-------------------------------------------------------------------------------+
```

---

## 2. Implemented SDKs & Modules

### A. `google-genai` SDK
* **Modules:** [`backend/app/integrations/google_cloud.py`](backend/app/integrations/google_cloud.py), [`backend/app/script/ai_image_service.py`](backend/app/script/ai_image_service.py) and [`backend/app/script/character_ai.py`](backend/app/script/character_ai.py)
* **Character inference (model chosen by `llm_router`, flash tier):** Reads each character's dialogue, parentheticals, the action lines naming them and the settings they appear in, and returns their role, physical appearance, costume and facial features. Called once for the whole cast so the ensemble stays visually coherent, with `response_mime_type: application/json` for structured output.
* **Lined page extraction** ([`backend/app/agents/multimodal.py`](backend/app/agents/multimodal.py)):
  Reads a script supervisor's handwritten lined / facing page (PNG, JPEG, WebP, HEIC or
  PDF, sent inline) and returns scene, slates, takes and camera rolls. Take notation is
  transcribed verbatim and normalised afterwards, so `3*`, `2PK`, `FALSE` and `WT 01`
  keep their meaning. Contact details read off the page header are redacted before the
  result is returned. It raises rather than returning an empty page when no model can
  read it: an empty page is a real answer, and returning one on failure would make an
  outage indistinguishable from a blank page.
* **Screenplay analysis:** Scene-level tension mapping and DoP camera placement logic.
  The model is not pinned. [`backend/app/script/llm_router.py`](backend/app/script/llm_router.py)
  returns an ordered candidate list led by the floating `gemini-flash-latest` alias,
  followed by older flash models. A pinned id 404s the day it is retired, and quota
  is metered per model, so falling through is what keeps the feature working.
  Pro routing is opt-in via `CINESPINE_GEMINI_PRO_MODEL`: a free-tier key is quota'd
  at zero on pro models, not merely throttled.
* **Image synthesis (`imagen-3.0-generate-002`):** Photorealistic 35mm stills per camera, with a REST fallback if the SDK path fails.

### B. `google-cloud-storage` SDK
* **Module:** [`backend/app/integrations/google_cloud.py`](backend/app/integrations/google_cloud.py)
* **Bucket:** `gs://cinespine-production-media/`
* **Archival Paths:**
  * Screenplay scripts: `gs://cinespine-production-media/screenplays/{filename}`
  * Previz stills: `gs://cinespine-production-media/previz/{shot_id}_{cam_letter}.jpg`

---

## 2b. Degradation & Cost Behaviour

Every Google Cloud call in CineSpine is optional. The application runs, and its tests pass, with no
credentials at all.

* **No API key** — character inference is skipped, profiles fall back to what the screenplay literally
  states, and the UI says so in a parse warning. Uploads still succeed.
* **No GCS credentials** — archival degrades to returning an auditable `gs://` reference. Constructing a
  storage client without credentials probes the GCE metadata server and blocks for roughly twelve
  seconds, so the unavailable result is **cached for the life of the process**; only the first upload
  pays it. The call also runs off the event loop, so it never stalls other requests.
* **Timeouts** — character inference abandons after `CINESPINE_AI_CHARACTER_TIMEOUT` seconds (default
  `60`). Measured round trips on a five-scene script are 22–27s. A timeout discards the whole inference,
  so the default deliberately leaves headroom.
* **Tests never call the API.** `main.py` loads `.env`, so a developer with a real key would otherwise
  have every upload test making a live, billed request. A fixture disables inference by default.

---

## 3. Endpoints & Telemetry
* `GET /api/integrations/google-cloud`: Returns JSON telemetry detailing active SDK connections, project IDs, bucket status, and model readiness.
* `POST /api/script/upload`: Automatically uploads and archives the ingested screenplay to GCS.
* `POST /api/script/generate-storyboard`: Compiles DoP optics and executes prompt-to-image synthesis using Gemini / Imagen 3.

---

## 4. Verification & Testing
Run the automated test suite to verify Google Cloud SDK runtime imports and API contracts:
```bash
pytest backend/tests/test_google_cloud_integration.py -v
```
Output:
```
backend/tests/test_google_cloud_integration.py::test_google_cloud_runtime_sdks_installed PASSED
backend/tests/test_google_cloud_integration.py::test_google_cloud_status_function PASSED
backend/tests/test_google_cloud_integration.py::test_google_cloud_status_endpoint PASSED
backend/tests/test_google_cloud_integration.py::test_gcs_media_upload_pipeline PASSED
backend/tests/test_google_cloud_integration.py::test_gemini_screenplay_analysis_runtime PASSED
```
