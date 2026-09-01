# CineSpine — 3-Minute Demo Video

**Hackathon:** [Agentic Cinema: The Blockbuster Hackathon](https://agentic-cinema.devpost.com/)
**Hard limit:** 3:00. Anything past three minutes is not evaluated.
**Deadline:** 9 September 2026, 2:00 PM Pacific.
**Delivery:** public video on Vimeo or YouTube, link on the Devpost submission form, English (or English subtitles).
**Required content:** footage showing the project actually running.

Every UI label, count and endpoint response below was read off the running app
on 1 September 2026. Where the previous draft of this script named something
that does not exist, the note says so rather than quietly correcting it — the
same mistake is in `DEVPOST_SUBMISSION.md` and has to be fixed there too.

---

## Pre-flight — do all of this before the recorder starts

Four of these are the difference between a demo and an apology.

1. **Image generation needs billing enabled on the Google AI project.**
   Every image model the key can see reports `limit: 0` on the free tier:

   ```
   Quota exceeded for metric: generate_content_free_tier_requests,
   limit: 0, model: gemini-3.1-flash-image
   ```

   Until that is fixed, "Execute & Render AI Concept" serves a bundled JPEG
   from `frontend/public/previz/`. The code now logs that at ERROR and names
   every model it tried, so **check the backend log after one test render**.
   A real render answers with `provider: "Google Gemini image (<model>)"`; a
   placeholder answers `provider: "CineSpine Previz Placeholder"` and lists
   `generator_failures`. Do not narrate live AI generation until you have seen
   the first form. Imagen 3 is gone from the code — it was never reachable on
   a Developer API key.

2. **Clear the duplicated discrepancies.** Day 31 currently shows 12 active,
   but three of them are the same clip three times (`A120_C001` ×3,
   `B039_C001` ×3, and a resolved `C005_C001` ×3), from repeated seeding.
   Confirmed at the API, not just on screen — they carry distinct ids. On
   camera, three identical rows read as a bug in the reconciliation engine.
   Use **Hackathon Demo → Factory Reset**, then **Run Full Demo**, and count
   the rows before recording.

3. **Load the script studio first.** "Screenplay & Previz Studio" opens
   completely empty — "0 Scenes Extracted", "No breakdown yet". Click
   **Load Demo Script** and wait for "3 Scenes Extracted" and "Character
   Visual Consistency: 2 Profiles Active" before you start talking.

4. **The version badge in the header says `v0.2`.** The repo is tagged
   `v0.4.0`. It is on screen for the entire runtime.

Already fixed while preparing this: `aiohttp` was corrupt in `.venv` (missing
`__init__.py`), so character inference failed and the studio showed an amber
"Parsed with warnings — AI character inference was unavailable" banner across
the hero shot. If that banner comes back, that is the cause.

---

## [0:00 – 0:30] The problem

**Visual:** the paperwork itself — daily production report, script supervisor
log, sound report, Silverstack volume manifest. No UI yet.

> Every day on a film set, four departments write down what happened, and they
> write it down separately. The office plans what should happen. The set records
> what it believes happened. The DIT verifies what actually exists on the drives.
> When those three disagree, nothing crashes and no alarm sounds. The
> disagreement is found weeks later in the post-production conform, and by then
> the footage is gone.

---

## [0:30 – 1:20] The 3-axis reconciliation engine

**Click path:** `🎞️ Set & Editorial Spine` → production `Demo Production
(DEMO_PRODUCTION)` → `Day 31` → tab `Active Discrepancies`.

**On screen, with real labels:** the day's tabs read `Composed Master Sheet
(7)`, `Sequences Log Matrix (4)`, `Card & Roll Map`, `Active Discrepancies`,
`Source Documents (18)`, `Requirements & Alerts (0)`.

Each discrepancy card carries its kind (`PAPERWORK_WITHOUT_MEDIA`), the slate
and take (`117A/1 Take 1 (A120_C001)`), a plain sentence — *"Clip A120_C001
logged on set but missing from offload report"* — the witness that said so
(`CAMERA A`, axis `BELIEF`, `Roll: A120`), and two controls: **Resolve /
Assign Card** and **Diagnose**.

**Action:** open one card, press **Resolve / Assign Card**, add the note, show
the row flip to `✓ RESOLVED` with the attribution line
(*"DIT confirmed offload manually" — @lead_editor*).

> CineSpine treats every document as a witness and never resolves a
> disagreement on the witnesses' behalf. Here on day 31, camera logged clip
> A120_C001 on set and the offload report has no such file. Either the clip was
> never offloaded or the log is wrong — the engine will not guess which, so it
> shows both witnesses and lets the assistant editor decide. One click records
> who resolved it, when, and on what grounds.

**Two corrections to the previous draft:** there is no **Consensus Triage**
button — the control is **Resolve / Assign Card**. And the two discrepancies
that draft described (a silent false start on take 3, a missing audio track
from an `A120` / `A_0120` roll collision) are not in the demo data. Do not
describe them.

---

## [1:20 – 2:20] The script and previz studio

**Click path:** `🎬 Screenplay & Previz Studio` → **Load Demo Script** (already
done in pre-flight) → scene `SCENE 27 — INT. GREAT HALL - NAVE - DAY`.

**Action, in order:**
1. Show the three columns: screenplay scenes, `MULTI-CAM SETUPS` (5 setups for
   scene 27), and the camera panel.
2. Switch `Cam A (35mm)` → `Cam B (50mm)` → `Cam C (85mm)`. The optics row
   under the frame moves with it: lens, T-stop, framing (`WS MS MCU CU ECU OTS
   POV`).
3. Click two modifier chips — `+ Volumetric Haze`, `+ Anamorphic Streak Flare`
   — and show them land in the editable prompt box below.
4. Press **Execute & Render Camera A AI Concept**. (The label follows the
   selected camera.)
5. Open **Cast & Character Profiles** and show `LEAD`: the personality polygon
   with `5 of 5 axes scored`, hover an axis for the line it was read from, and
   the lines panel beside it.

> The studio ingests a screenplay and breaks every scene into a three-camera
> rig — a 35mm master, a 50mm over-the-shoulder, an 85mm insert — with a
> cinematographer preset behind it: colour temperature, key-to-fill ratio, film
> stock. The character panel scores the cast on five axes and shows the line of
> dialogue each score was read from, because a reading nobody can check against
> the script is just an assertion with a chart around it. Where the script does
> not support a score, the axis is drawn missing rather than zero.

**Three corrections to the previous draft:** there is **no 3-Camera Multi-View
Grid** — the nearest control is **Batch Render AI Concepts for all 3 Cameras**
on each setup row. There is **no Ctrl+Enter shortcut** anywhere in the
frontend. And the narration must match pre-flight item 1: say "Google Gemini
image models" and only claim a live render if the log shows one.

---

## [2:20 – 2:50] Under the hood

**Visual:** terminal and one API response.

```bash
pytest -q                       # 974 passed, 11 skipped
curl localhost:8000/api/integrations/google-cloud
```

The endpoint answers, verbatim:

```json
{"status":"online","genai_sdk_installed":true,"gcs_sdk_installed":true,
 "gemini_model":"gemini-flash-latest","image_model":"gemini-3.1-flash-image",
 "project_id":"cinespine-agentic-cinema","is_authenticated":true}
```

> Python, FastAPI and the official Google GenAI SDK, with 974 automated tests
> behind it. The spine itself is an append-only log in SQLite — that is the
> source of truth — mirrored into ClickHouse Cloud, which is what the
> analytical questions are asked of. Grafana reads the telemetry.

**Correction to the previous draft:** it said the spine is "an immutable
append-only event spine in ClickHouse". It is not. SQLite is the source of
truth and ClickHouse is a derived mirror that `scripts/rebuild_mirror.py`
rebuilds from it — the repo says so in `backend/app/spine/activity_store.py`.
Claiming otherwise to judges who may read the code is a bad trade.

---

## [2:50 – 3:00] Close

**Visual:** back to the spine board, day 31, discrepancies resolved.

> Four departments, one spine, and every disagreement between them visible on
> the day instead of in the conform. Thank you.

---

## Recording settings

Record at **1920×1080, constant 30 fps**. The UI was checked at that viewport
and the layout holds. Capture system audio off, microphone only, and record
the narration in one pass — the cut points above are all on tab switches,
which are easy to trim.

OBS: base and output resolution both 1920×1080, 30 fps, recording format `mkv`
(remux to mp4 afterwards — a crashed mp4 recording is unrecoverable), encoder
x264, rate control CRF 16, profile `high`.

## Encoding for Vimeo

[Vimeo's compression guidelines](https://help.vimeo.com/hc/en-us/articles/12426043233169-Video-and-audio-compression-guidelines):
H.264 **High Profile**, constant frame rate, variable bitrate, **10–20 Mbps at
1080p**, CRF 18 or below, audio **AAC-LC at 320 kb/s, 48 kHz**. MP4 or MOV.
Files under 200 GB.

```bash
ffmpeg -i recording.mkv -c:v libx264 -profile:v high -preset slow -crf 17 -maxrate 20M -bufsize 40M -pix_fmt yuv420p -r 30 -c:a aac -b:a 320k -ar 48000 -movflags +faststart cinespine-demo.mp4
```

Check it before uploading — anything over 3:00 loses whatever runs past it:

```bash
ffprobe -v error -show_entries format=duration,size -show_entries stream=codec_name,profile,width,height,r_frame_rate,sample_rate -of default=noprint_wrappers=1 cinespine-demo.mp4
```

## Upload checklist

- [ ] Duration is 3:00 or under.
- [ ] Uploaded to Vimeo, privacy set to **public** — a private or
      password-protected link is not evaluated.
- [ ] English narration, or English subtitles attached.
- [ ] Shows the project actually running, not slides.
- [ ] No third-party music, footage, logos or trademarks. The submission rules
      require original work throughout, and a licensed track is still someone
      else's copyright.
- [ ] Link pasted into the Devpost submission form before
      **9 September 2026, 2:00 PM PT**.
