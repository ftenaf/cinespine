# 🎞️ Demo Evidence Contract

The files in `data/examples/` are not sample text. They are the input to the
reconciliation engine and the assistant editorial queue, and the demo only
shows anything because of specific relationships between them. Edit one in
isolation and the demo goes quiet without erroring — which has happened twice.

This document records what those relationships are, so the next edit is made
with them in view.

---

## 1. What the fixtures are

| File | Shoot day | Department | Parser reached |
| :--- | :--- | :--- | :--- |
| `demo_script.fountain` | — | office | Fountain screenplay parser |
| `DEMO_TCLog_Synthetic.pdf` | 31 | script | `parse_scripte_tclog_text` |
| `DEMO_Day1_ScriptLog.txt` | 31 | script | `parse_scripte_tclog_text` |
| `DEMO_Day1_SoundLog.txt` | 31 | sound | `parse_sound_ale` |
| `DEMO_Day1_CamReport.txt` | 31 | camera | `parse_camera_csv` |
| `DEMO_Day1_Silverstack_Offload.txt` | 31 | dit | `parse_silverstack_thumbnail_text` |
| `DEMO_Day2_*` | 32 | as above | narrative-format parsers |

The shoot day is decided by filename: `demo_inject_events` assigns day `32` to
anything containing `Day2` and day `31` to everything else.

---

## 2. The four rules

### Rule 1 — Slates must name scenes the screenplay contains

`demo_script.fountain` defines Scenes 1–6. Day 1 covers Scenes 1 and 2, Day 2
covers 3–6. A slate is `scene/shot`, so Day 1's slates are `1/1`, `1/2`, `2/1`.

Nothing enforces this. Evidence filed under a scene the script does not have is
ingested happily, reconciles against nothing, and appears in the UI as a scene
that came from nowhere. Day 1 spent a while on slates `10/1` and `10/2` for
exactly this reason.

> `DEMO_TCLog_Synthetic.pdf` still violates this rule. It files takes under
> slates `117A/1` and `27B/2` on rolls A120/B039/C005, inherited from the real
> ZoeLog fixtures. It is a parser smoke test — `test_demo_pdf_ingestion.py`
> asserts those exact rolls — so fixing it means changing that test's intent.
> Regenerate with `scripts/generate_synthetic_fixtures.py` if you take it on.

### Rule 2 — Clip names must join the camera report to the offload

`reconcile_existence` matches a logged take to a media file on `clip_name`, via
`is_clip_matched`. The camera report is the only document carrying clip names,
which is why Day 1's camera report is CSV with a `CLIP NAME` column rather than
prose. `A001C001_260831` in the report matches `A001C001_260831.MOV` in the
offload; `_clip_stem` strips the extension.

### Rule 3 — The offload must carry Scene / Shot / Take

The assistant editorial queue only proposes a scene when `_clean_reasons`
returns three or more reasons **and** `has_existence` is true. `has_existence`
comes from a `media_file` event, and that event's scene comes from the parsed
clip's own `scene` field.

Silverstack clips that carry no scene land under `UNKNOWN`, so the offload
evidence attaches to a scene that does not exist and no real scene ever
qualifies. The Day 1 offload is therefore written as a **Pomfort Silverstack
Thumbnail Report** — the one layout whose parser reads labelled `Scene`,
`Shot` and `Take` lines:

```
Name A001C001_260831.MOV
Reel/Tape A_0001_1EIC
Scene 1
Shot 1
Take 1
Camera ARRI ALEXA 35
Sensor FPS 24.000
```

`Reel/Tape A_0001_1EIC` is what makes the camera roll resolve to `A001`, and at
least one video parameter (`Camera`, `Sensor FPS`, `EI/ISO`, `T-Stop`, `Codec`)
is what classifies the clip as camera rather than sound.

### Rule 4 — Beware content-based routing

`handle_silverstack_drop` picks its parser by **inspecting the content**, not
the filename or the classifier's `doc_type`:

```python
if fn.endswith(".PDF") or "POMFORT" in content.upper() or "SILVERSTACK" in content.upper() ...:
    records = parse_silverstack_pdf_text(content)
else:
    records = parse_silverstack_xml(content)
```

A Silverstack **XML** file matches on its own `<Silverstack>` root tag, so it is
routed to the *text* parser and `parse_silverstack_xml` is unreachable for it.
The result is `ParserFailureError` → DLQ → zero `media_file` events → the whole
day reads as awaiting offload. The failure is invisible: ingest still reports
success, because `demo_inject_events` publishes and moves on.

To inspect the DLQ:

```sql
SELECT payload FROM spine_events WHERE doc_type = 'dlq';
```

---

## 3. What Day 1 is designed to demonstrate

Seven takes across two scenes, with three planted findings and one clean scene.

| Slate | Take | Clip | In offload? |
| :--- | :--- | :--- | :--- |
| 1/1 | 1, 2, 3⭐ | `A001C001–3` | yes |
| 1/2 | 1, 2⭐ | `A001C004–5` | yes |
| 2/1 | 1⭐ | `A001C006` | **no** |
| 2/1 | 2 | `A001C007` | yes |
| — | — | `A001C099` | yes, logged by nobody |

Which yields, on shoot day 31:

| Severity | Type | Entity |
| :--- | :--- | :--- |
| CRITICAL | `PAPERWORK_WITHOUT_MEDIA` | `2/1 Take 1 (A001C006_260831)` |
| WARNING | `TIMECODE_DRIFT` | `2/1 Take 2` — 12 frames, script vs sound |
| WARNING | `MEDIA_WITHOUT_PAPERWORK` | `A001C099_260831.MOV` |

And therefore:

- **Scene 1 is clean** — all five reasons met, no blockers, so the assistant
  editorial queue proposes it for turnover.
- **Scene 2 is blocked** — the critical finding on its circled take holds it
  back, with a reason a human can read.

Both halves matter. A demo where every scene is clean shows an empty queue and
no discrepancies; a demo where every scene is blocked shows a queue that never
proposes anything.

**On the timecode drift:** `reconcile_take_witnesses` compares the *first two*
witnesses carrying `timecode_in`. Witness order follows the ingest order in
`demo_inject_events` — script, then sound, then camera — so the drift must be
planted between the script log and the sound log to fire. Camera agreeing with
script would not surface it.

**On scene blocking:** `_active_discrepancies_by_scene` derives the scene by
splitting `entity_id` on `/`. So a finding on `2/1 Take 2` blocks Scene 2, and
any finding placed on a Scene 1 slate would silently make Scene 1 ineligible
too — leaving the editorial queue with nothing to propose.

---

## 4. Tracking

`data/examples/` is excluded by `.gitignore` because a developer's copy holds
real, copyrighted production paperwork carrying crew personal data
(`test_privacy_gate.py` documents this: material seeded from that directory is
explicitly *not* treated as synthetic).

The `DEMO_*` fixtures are the exception and are tracked, via negations that sit
last in `.gitignore` so they survive the `*.pdf` rule:

```gitignore
data/examples/*
...
!data/examples/DEMO_*
!data/examples/demo_*
```

The directory contents are excluded rather than the directory itself — git will
not descend into an excluded directory, so an exception underneath one is dead.

This matters because `demo_inject_events` reads the directory **by filename and
skips what is not there**. While the fixtures were untracked, a fresh clone
ingested no offload evidence at all and still reported the demo injected
successfully.

---

## 5. Editing checklist

Because the backend image bakes `data/` in via `COPY`, fixture edits need a
rebuild before they are visible:

```bash
docker compose up -d --build backend
curl -s -X POST http://localhost:8000/api/demo/wipe
curl -s http://localhost:8000/api/events/demo
curl -s "http://localhost:8000/api/discrepancies?production_id=DEMO_PRODUCTION&shoot_day=31"
```

Expect three discrepancies on day 31. No committed test covers this, so the
check is manual — see [Test suite gaps](CLICKHOUSE_MCP.md#test-suite-gaps) for
why a green suite is not evidence here.
