# CineSpine — 3-Minute Demo Video (ClickHouse Track)

**Hackathon:** [Agentic Cinema: The Blockbuster Hackathon](https://agentic-cinema.devpost.com/)
**Track:** ClickHouse. One partner track per entry; this is the one.
**Hard limit:** 3:00. Anything past three minutes is not evaluated.
**Deadline:** 9 September 2026, 2:00 PM Pacific.
**Delivery:** public video on Vimeo or YouTube, link on the Devpost submission form, English (or English subtitles).
**Required content:** footage showing the project actually running.

The brief asks for Gemini plus Google Cloud Agent Builder, integrated with one partner's product via API or MCP. The spine of this video is exactly that sentence: a Google ADK agent that reaches **ClickHouse Cloud only through the official `mcp-clickhouse` server**, and a set of screens that read the same ClickHouse mirror. Grafana appears for one shot as proof the agent is traced; it is not a pillar.

---

## Pre-flight — do all of this before the recorder starts

1. **Reset the demo data.** **Hackathon Demo → Factory Reset**, then **Run Full Demo**. Wait for the log to finish, open **Productions**, and confirm DEMO_PRODUCTION shows Day 31 with active discrepancies. Factory Reset empties the whole spine, so do this once, before recording, never during.
2. **Record on the live URL**, `https://cinespine-35447568692.europe-west4.run.app`, not localhost. Confirm `/api/health` shows the version you deployed.
3. **Warm the Wrap Rescue Agent.** Run it once for Day 31 off-camera. The MCP service scales to zero and its cold start is ~20 s; the second run is fast. Confirm the panel shows `mcp_available: true` and a Gemini memo.
4. **Warm the status endpoint.** Open `/api/productions/DEMO_PRODUCTION/status` once; it reconciles every shoot day and the first call is the slow one.
5. **Load the studio.** Open **Screenplay & Previz Studio**, choose **Demo Production** in the dropdown, wait for "6 Scenes Extracted". Pick a scene with a `CUT TO:` transition; that is the path that uses Gemini for the breakdown, and the deterministic path looks the same but is not the story.
6. **Grafana, one tab.** Explore view, a trace of the warm-up Wrap Rescue run expanded so the span tree reads ADK → `mcp-clickhouse` → ClickHouse → Gemini. One screen, ready to switch to.
7. **Image generation needs billing enabled**, or the render falls back to the labelled placeholder. Either is honest; know which one you will get.

---

## [0:00 – 0:20] The problem

**Visual:** The paperwork: camera report, sound report, script supervisor log, Silverstack manifest. Cut to CineSpine, **Set & Editorial Spine**, `Active Discrepancies`.

> On a film set, four departments write down what happened, in four tools that never meet. When they disagree, nobody finds out until the edit, weeks later.
> CineSpine reads the paperwork as it lands, appends every fact to an immutable spine, and mirrors it into ClickHouse Cloud.

---

## [0:20 – 0:50] Reconciliation on the mirror

**Visual:** Click a discrepancy. Show the three witnesses side by side: script says one take, camera another, DIT has the file. Then open **Productions → Analytics**: "What each department has said", "How long until somebody takes it on".

> Three axes: intent, belief, existence. Every take is cross-checked across all three, and every disagreement is a row in ClickHouse.
> These panels are ClickHouse queries: departments by axis, acknowledgement lag by department, requirement ageing. Questions that need a whole production at once, asked of the columnar mirror instead of the row store.

---

## [0:50 – 1:45] Wrap Rescue: an ADK agent with ClickHouse as its memory

**Visual:** Productions → Wrap Rescue panel. Day 31. Click **Run**. Let the tool-call trace scroll: `list_tables`, `run_query` for discrepancies, `run_query` for unacknowledged requirements, throughput, age. Then the ranked blockers and the memo.

> At wrap, the producer needs to know what will stop tomorrow's shoot. We built the Wrap Rescue Agent on Google's Agent Development Kit.
> It never touches the database directly. It talks to the official ClickHouse MCP server, `mcp-clickhouse`, running as its own Cloud Run service: `list_tables`, then SQL, tool call by tool call, all of it on screen.
> Gemini ranks the blockers and drafts the memo. Then the agent acts: it files a requirement for each blocker, assigned to the department that owns it.

**Visual:** Switch to the Requirements board. The new `[Wrap Rescue]` requirements are there, assigned, with the alert badge lit for that handle.

> Those land in the same spine, get mirrored back to ClickHouse, and the people responsible are notified. The loop closes.

---

## [1:45 – 2:20] One question, ranked: where does the production stand

**Visual:** Open `/api/productions/DEMO_PRODUCTION/status` in a tab, or the Activity card on the production dashboard. Point at the `blocking` list, top item, its severity and age.

> Any producer's real question is "how are we doing". One endpoint answers it in five buckets: done, running, blocking, left, missing.
> Every item carries a severity and an age, and the worst, oldest thing is always first. "Missing" is inference, and each item says which rule inferred it.
> The same answer is a WebMCP tool, so an agent driving the browser can ask it instead of scraping the page.

**Visual:** Production dashboard, Crew Workload beside the Activity card.

> Who owns what, next to who did what. The activity ledger is a ClickHouse table every mutation writes to; it counts actions, not effort, and the card says so.

---

## [2:20 – 2:40] It is traced, not a black box

**Visual:** Grafana tab, the expanded trace. Hold five seconds. Back to the app.

> Every Gemini call and every MCP tool call is a span, with token counts, so an agent's run can be audited like any other request.

---

## [2:40 – 3:00] Studio and close

**Visual:** Screenplay & Previz Studio. The scene with the cut. Click **Run AI-Cam Breakdown**, show the three camera setups, click **Execute & Render Camera A AI Concept**.

> The same screenplay feeds the studio: Gemini breaks a scene into synchronized three-camera setups with real optics, and renders the frame.
> Four departments, one spine, one ClickHouse mirror, one agent that reads it and acts. CineSpine. Thank you.

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
- [ ] Devpost form: partner track set to **ClickHouse**, repository public with LICENSE, live URL filled in.
- [ ] Link pasted into the Devpost submission form before **9 September 2026, 2:00 PM PT**.
