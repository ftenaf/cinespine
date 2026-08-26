# Google Cloud & Gemini Enterprise Integration Guide

## 1. Overview
CineSpine incorporates native, runtime integration with Google Cloud and the Gemini Enterprise Agent Platform.

```
+-------------------------------------------------------------------------------+
|                             Google Cloud Platform                             |
|                                                                               |
|  +-------------------------+  +----------------------+  +------------------+  |
|  |     Gemini 2.0 Flash    |  |       Imagen 3       |  |  Google Cloud    |  |
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
* **Module:** [`backend/app/integrations/google_cloud.py`](backend/app/integrations/google_cloud.py) and [`backend/app/script/ai_image_service.py`](backend/app/script/ai_image_service.py)
* **Model 1 (`gemini-2.0-flash`):** Screenplay analysis, emotional tension mapping, and DoP camera placement logic.
* **Model 2 (`imagen-3.0-generate-002`):** Direct generation of photorealistic 35mm film stills customized for Camera A, B, and C.

### B. `google-cloud-storage` SDK
* **Module:** [`backend/app/integrations/google_cloud.py`](backend/app/integrations/google_cloud.py)
* **Bucket:** `gs://cinespine-production-media/`
* **Archival Paths:**
  * Screenplay scripts: `gs://cinespine-production-media/screenplays/{filename}`
  * Previz stills: `gs://cinespine-production-media/previz/{shot_id}_{cam_letter}.jpg`

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
