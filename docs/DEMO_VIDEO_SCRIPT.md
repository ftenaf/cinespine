# CineSpine — 3-Minute Demo Video (ClickHouse & Grafana Track)

**Hackathon:** [Agentic Cinema: The Blockbuster Hackathon](https://agentic-cinema.devpost.com/)
**Hard limit:** 3:00. Anything past three minutes is not evaluated.
**Deadline:** 9 September 2026, 2:00 PM Pacific.
**Delivery:** public video on Vimeo or YouTube, link on the Devpost submission form, English (or English subtitles).
**Required content:** footage showing the project actually running.

This script is specifically tuned to maximize the **ClickHouse** and **Grafana Labs** partner tracks, dedicating ~60% of the runtime to these features.

---

## Pre-flight — do all of this before the recorder starts

1. **Clear the duplicated discrepancies.** Day 31 currently shows 12 active, but three of them are the same clip three times. Use **Hackathon Demo → Factory Reset**, then **Run Full Demo**, and count the rows before recording.
2. **Verify Production Services.** Since the app is deployed to production, just ensure your live production URL is loaded and the Wrap Rescue Agent is successfully talking to the production ClickHouse MCP server.
3. **Open Grafana Cloud.** Have your Grafana Cloud dashboard open in another tab, logged in. Navigate to the **Alerting -> Alert Rules** page, and have a trace containing `GoogleGenAiSdkInstrumentor` ready to show in the **Explore** view.
4. **Load the script studio first.** "Screenplay & Previz Studio" opens completely empty. Click **Load Demo Script** and wait for "3 Scenes Extracted" before you start talking.
5. **Image generation needs billing enabled.** Ensure your Google AI project has billing enabled or the Gemini image render falls back to the labelled placeholder.

---

## [0:00 – 0:25] The Problem & The Event Spine

**Visual:** The paperwork itself — daily production report, script supervisor log, sound report, Silverstack volume manifest. Then, transition to the CineSpine UI (`Active Discrepancies` tab).

> Every day on a film set, multiple departments log what happens in their own siloed tools. When they disagree, mistakes are found weeks later in the edit.
> CineSpine fixes this. Every action on set appends to an immutable SQLite spine, mirrored into **ClickHouse** for high-performance queries.

---

## [0:25 – 1:15] ClickHouse Track: Assistant Editor Queue & Workload Analytics

**Visual:** Click on the `Crew Workload` or `Assistant Editorial` dashboard. Show the activity ledger and completion charts.

> Because our event projections live in ClickHouse, we can run complex queries without hammering our operational database. 
> This Assistant Editor Queue balances tasks across the crew, instantly calculating blockers, completion counts, and median response times—giving producers a real-time pulse of post-production.

---

## [1:15 – 2:05] ClickHouse Track: Wrap Rescue Agent (Google ADK)

**Visual:** Show the UI trace of the Wrap Rescue Agent executing its thought process in the production environment. Show the final Gemini-authored memo output.

> At wrap, producers need a summary of what went wrong. We built this Wrap Rescue Agent on Google ADK. 
> It connects to the `mcp-clickhouse` server and uses ClickHouse as its memory. It runs SQL queries to rank blockers by severity, drafting a data-backed memo to prioritize tomorrow's fires.

---

## [2:05 – 2:40] Grafana Track: Agent Observability & Telemetry

**Visual:** Switch to the Grafana Cloud tab. 
1. Show **Alerting -> Alert Rules** (expand "CineSpine Discrepancies").
2. Show the **Explore** tab with a GenAI trace expanded.

> We push OTLP traces and metrics to Grafana Cloud, with native ClickHouse alerts for critical discrepancies. 
> More importantly, using the `GoogleGenAiSdkInstrumentor`, every Gemini generation and ClickHouse MCP tool call is traced as a semantic span—making the agent's decisions completely legible.

---

## [2:40 – 3:00] Previz Studio & Close

**Visual:** Switch to the `🎬 Screenplay & Previz Studio` tab. Briefly show the 3-camera setups and click **Execute & Render Camera A AI Concept**.

> Finally, our Previz Studio parses screenplays to generate 3-camera cinematic concepts using Gemini image models, simulating real optical physics. 
> Four departments, one spine, total clarity. Thank you.

---

## Recording settings

Record at **1920×1080, constant 30 fps**. The UI was checked at that viewport and the layout holds. Capture system audio off, microphone only, and record the narration in one pass.

OBS: base and output resolution both 1920×1080, 30 fps, recording format `mkv` (remux to mp4 afterwards), encoder x264, rate control CRF 16, profile `high`.

## Encoding for Vimeo

[Vimeo's compression guidelines](https://help.vimeo.com/hc/en-us/articles/12426043233169-Video-and-audio-compression-guidelines):
H.264 **High Profile**, constant frame rate, variable bitrate, **10–20 Mbps at 1080p**, CRF 18 or below, audio **AAC-LC at 320 kb/s, 48 kHz**. MP4 or MOV. Files under 200 GB.

```bash
ffmpeg -i recording.mkv -c:v libx264 -profile:v high -preset slow -crf 17 -maxrate 20M -bufsize 40M -pix_fmt yuv420p -r 30 -c:a aac -b:a 320k -ar 48000 -movflags +faststart cinespine-demo.mp4
```

Check it before uploading — anything over 3:00 loses whatever runs past it:

```bash
ffprobe -v error -show_entries format=duration,size -show_entries stream=codec_name,profile,width,height,r_frame_rate,sample_rate -of default=noprint_wrappers=1 cinespine-demo.mp4
```

## Upload checklist

- [ ] Duration is 3:00 or under.
- [ ] Uploaded to Vimeo, privacy set to **public** — a private or password-protected link is not evaluated.
- [ ] English narration, or English subtitles attached.
- [ ] Shows the project actually running, not slides.
- [ ] No third-party music, footage, logos or trademarks. The submission rules require original work throughout, and a licensed track is still someone else's copyright.
- [ ] Link pasted into the Devpost submission form before **9 September 2026, 2:00 PM PT**.
