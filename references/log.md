---
type: log
title: What was learned, and when
description: Chronology of findings about this codebase, newest first
tags: [log]
---

# Log

Newest first. Each entry names what produced it.

## 2026-09-03

**A wrong method on any API route was a 500, and the instrumentation was the
cause.** The only 5xx Cloud Run served in a week was a POST to a GET-only
route: `opentelemetry-instrumentation-fastapi` 0.63b1 walks `app.routes`
expecting plain routes, FastAPI 0.137+ mounts an `_IncludedRouter` wrapper
with no `path`, and on the partial match (right path, wrong method) the walker
raises before any span exists. Reproduced locally: POST `/api/health` -> 500,
no span. 0.64b0 fixes it and cannot be installed -- its semantic-conventions
pin needs `opentelemetry-api` 1.43 and `google-adk` 2.8 caps the api at 1.42.1,
so `uv lock` trades ADK down from 2.8 to 1.14 to take it. The fix is
backported in `telemetry.py` and retires itself once the installed
instrumentation has `_flatten_routes`.

**A laptop container pushed into the production stack, and nothing could tell.**
Seven days of Grafana Cloud logs held 2,400 error lines about
`/app/gcp-credentials.json` and 800 about a full disk. That path is the compose
bind-mount, which Cloud Run never sets, and Cloud Logging had neither string
from the service -- so a local container running with the production `.env`
had exported straight into Grafana Cloud. The resource said only
`cinespine-backend 0.1.0`; there was no attribute to filter on. Every signal
now carries `deployment.environment` (`cloudrun` wherever `K_SERVICE` is set,
otherwise `local`) and `service.instance.id` (the revision name), and a local
process refuses to export anywhere but a local collector unless
`CINESPINE_TELEMETRY_REMOTE_OK=1` says the push is deliberate. The Cloud alert
rules select `deployment_environment!="local"`.

**Nothing in Grafana Cloud notified anyone.** The root notification policy
routed to a receiver named `empty`, and the only contact point was the Asserts
webhook. The four CineSpine rules in `grafana/provisioning/alerting/rules.yml`
exist only locally, against a ClickHouse datasource Cloud does not have. Four
rules now live in the Cloud folder `CineSpine`, on data that exists: backend
telemetry silent, error-log burst, 5xx responses, GenAI call failures.

**Four dashboard panels queried metrics that never arrive, and an empty panel
looks like a quiet system.** The AI cost dashboard read `cinespine_*`, which
`prometheus_client` serves and the OTel exporter does not carry. Rewritten onto
the GenAI conventions. Two things the rewrite turned up:

The hand-placed token counter cannot price anything. It sits at two call sites
of eight, and records `total_token_count` only -- while output is billed far
above input. A dollar figure from it is wrong by a factor that moves with the
mix: precise-looking and unfalsifiable. `gen_ai_client_token_usage` covers every
`google-genai` call and splits the two.

Summing the two token types the obvious way returns **nothing**.
`rate(...{type="input"}) + rate(...{type="output"})` matches on every label
including `gen_ai_token_type`, finds no partner, and yields an empty vector --
the same silent failure the panels were being rescued from. Confirmed: the naive
form returns 0 series against live data.

**The local stack had never scraped anything.** `prometheus.yml` carried no
`metrics_path`, so it asked for `/metrics` while the app serves `/api/metrics`.
The target reported healthy and 404'd every scrape, so no `cinespine_*` series
had ever existed locally -- every local dashboard was empty, not just the AI one.
`gen_ai_*` is pushed and never scraped, so it needs `--web.enable-otlp-receiver`
on top; without it a dashboard can work in Cloud and be dead on a developer's
machine.

**p95 was the right question and the wrong query.** A demo makes a handful of
model calls and one agent run, so the bucket counters are flat across any
sensible rate window; `rate()` is 0 for every bucket and `histogram_quantile` of
all-zero buckets is `NaN`. Measured on a real Wrap Rescue run: the p95 form
returned `NaN` where `sum / count` returned 1.20s. The panels are means until
traffic is continuous enough to move the buckets.

**Two of the three agents never run as agents.** See
[findings/agent-telemetry-coverage.md](findings/agent-telemetry-coverage.md).

## 2026-08-30

**The department sync matrix is built, and it says which kind of measurement each row is.** REQ-10's
original ask, computable at last because the shoot day now carries a calendar date: wrap on 2026-07-28 at
18:55, minus when each department first filed.

The concern that kept it unbuilt was not that the number is wrong -- it is exactly right -- but that it
would be read wrong. On this paperwork every department filed 780-odd hours after wrap because the
documents were imported a month later, and 780 hours in a matrix a reader expects to be hours tells them
something false in a form that looks true. So every row carries `measurement`: `handover` or `backfill`.
Nothing decides a backfill is uninteresting, only that it is not the same measurement, and the gauge
carries the same label so a dashboard cannot add the two together.

`CINESPINE_HANDOVER_WINDOW_HOURS` decides where one becomes the other, defaulting to 48. Written down as
a judgement rather than a domain fact: a day's paperwork is expected before the next shooting day and a
weekend can sit in between, and a production that works differently should not inherit this one's habits.

`cinespine_department_sync_lag_seconds` is back, ten hours after being removed. The removal was right
while it stood -- there was no date to subtract from, and a gauge that can never fill reads as "no lag"
rather than "not known". Its test was rewritten rather than deleted, because the reason it went is worth
as much as the reason it returned. What survives from that decision is that nothing unmeasurable is
published: a day with no wrap or no date gets no series, because a zero would claim the department filed
at the moment of a wrap nobody recorded.

**Two backfills of history came with it.** The `shoot_date` claims only existed for documents ingested
after the subscriber was added, so `scripts/backfill_shoot_dates.py` appends the claim each stored
document was always making -- it alters nothing, and skips documents that state no date. Nine of eleven
had one.

**The shoot day is bound to a calendar date, and the last open question is closed.** Francisco named
where the date is written and which source to trust: the Thumbnail Report's volume stamp, `260728_SD31`,
because it is the only place the date and the shoot day appear together and so cannot be paired wrongly.
Four sources are read in his order and the answer carries which document said it.

Every document emits its own date claim, from a subscriber on every raw topic rather than from inside the
parsers -- every department states the date, and a document whose parser refuses it has still said what
day it covers. `SHOOT_DATE_DISAGREEMENT` reports when two disagree and deliberately does not resolve it:
the most reliable source is still not the answer, and which document is wrong belongs to the people who
wrote them. Against the real data all eight day-31 documents agree on 2026-07-28 and the check is silent.

**The thumbnail parser's skip list named this exact document.** `"and 28 July"`, `"260728_SD31"` and
`"DEMO PRODUCTION"` were matched as literal strings, so another production's report would have carried
those lines into its clips -- and the list was discarding the volume stamp that answers the question.
Matched on shape now.

**The sync lag is computable and still not built.** The date was the missing input. On historical
paperwork the only other timestamp is the ingest, months later, so the number would be correct and mean
nothing; what REQ-10 asks for is answered by the acknowledgement axis instead.

**Four parsers had the contact-details defect, not one.** `camera_csv` was fixed in the morning,
`sound_ale` in the afternoon, and a sweep found two more: `silverstack_thumbnail`, where the address
landed in `file_name` and no slate-shaped guard would have caught it, and `scripte_tclog`, where every
unrecognised line is appended to the previous take's note. All eight parsers are clean now, and all 11
real documents still parse to the same 40 events and the same five slates.

The `scripte_tclog` case needed a different answer from the others. A note is free text and legitimately
carries names -- rewriting it would be the helpful correction, a witness statement quietly altered. So the
line is refused rather than redacted: declining to attribute something plainly not about this take leaves
the note as what somebody actually wrote. `privacy.is_contact_information` shares its patterns with
`redact`, so there is one definition of contact information in the codebase.

Recorded in [findings/defects-found.md](findings/defects-found.md), and the lesson is the count rather
than any one instance: three fixes were applied believing each was the last.

**Three stale entries corrected in [findings/spec-drift.md](findings/spec-drift.md).** REQ-10 still said
both gauges had no callers -- one fills now and the other was removed with reasons, and what the
requirement actually asks for is answered by the acknowledgement axis. REQ-13 was listed as a gap when the
behaviour it is for works: notifications ride the requirement events and the SSE handler refreshes on any
of them, so emitting `NOTIFICATION_ADDED` would fire twice for one fact. REQ-09's naming is wrong and
staying wrong, which is a decision and now reads as one. All three moved to deliberate divergences.

**The mirror is live on ClickHouse Cloud, and rebuilding it found three things.** 42 spine events, 45 tag
events, 13 requirement events and the activity trail now sit in the hosted instance, and all ten
analytics queries answer from it.

The rebuild script did not load `.env`, though its own docstring said it read the environment "the same
as the app" -- the app loads it in `main.py` and the script imports the spine directly, so a fully
configured machine got "No ClickHouse connection" while the app beside it was connected.

It also still split the DDL on `;`. `connect()` was fixed for the comment-semicolon bug and the script
was not, so it failed on the schema loop -- before the truncate, which is the only reason nothing was
lost. And `user_activity` was not among its sources, so a rebuild would have left the acknowledgement
axis inconsistent with the spine it claims to rebuild from.

**A join reported 78 views of a day two people had opened.** `unreviewed_days` and
`unacknowledged_requirements` both join activity against a trail with many rows per key, and `countIf`
multiplies every activity row by the number of trail rows beside it. `uniqExactIf` over the activity id
counts what happened. The number was plausible, which is what made it dangerous: an obviously broken
figure gets investigated, and 78 would have been read off a dashboard as engagement. Guarded on the SQL
rather than on data, because the shape of the join is the defect and a data test only fails once there is
enough of it.

**Acknowledgement is an axis on the spine now, not a metric bought from someone else.** `handoffs.md`
names the gap: "No acknowledgement is recorded anywhere." A blocker is raised, a notification goes out,
and nothing in the production can answer whether the person it was for ever saw it. `user_activity` is
that answer -- appended in SQLite, mirrored to ClickHouse, queried by the app's own analytics surface.

`viewed` and `acknowledged` are kept apart and always must be. A view is weak evidence about attention;
an acknowledgement is a claim somebody made, and only the second can carry an obligation. Conflating them
would turn "three people had this on screen" into "three people took this on". The view is recorded when
a requirement is expanded rather than when it renders, for the same reason: a row scrolling past in a
list is not somebody looking at it.

Four queries came with it, and they are the department sync matrix REQ-10 asked for -- from a fact the
product records rather than a wrap time with no date on it: time to acknowledge by department, raised and
nobody has taken it on, days nobody has looked at, and which departments are looking at what. The middle
two separate two silences that an empty list conflates: opened and not acknowledged is somebody deciding
not to; never opened at all is a blocker that has not reached anyone.

How long the target had existed is measured server-side, never sent by the client. A browser clock is not
a witness, and time-to-acknowledge is the whole point of the record. Where a target has no creation time
-- a scene, a shoot day -- the age is null rather than zero: zero would say it was acknowledged instantly
and drag every average towards a number nobody measured.

Verified end to end against ClickHouse Cloud: a requirement raised, viewed, acknowledged six seconds
later, and the panel reading `sound · requirement — median 0.1m`.

**`sound_ale` had the PII hole that `camera_csv` had.** Found by probing the other parsers rather than
assuming the one fix was enough: a contact line with an email and a phone number became a slate, exactly
as it did in the camera parser, and it now leaves the machine because the mirror is hosted. Guarded with
the same shape test. Fixing it exposed a second defect underneath -- `normalize_slate` keeps the `.WAV`
on a filename, so a row whose slate comes from the NAME column became the slate `49WTT01.WAV`, truthy
enough that the filename fallback below it never ran. Stripping the extension first resolves it properly
to `49/WT`.

**A semicolon in a comment deleted a table.** The DDL was split on `;`, so an ordinary sentence in a new
comment -- "a view is weak evidence about attention; an acknowledgement is a claim" -- cut a CREATE TABLE
in half and `user_activity` silently never got created. Comments are now stripped before the split. Worth
recording because the failure was a syntax error a long way from the prose that caused it.

**And one I introduced and caught.** The new panel said "Everything raised has been acknowledged" while
three unacknowledged requirements sat on the board above it -- because the Cloud mirror holds no
requirement rows to join against. A query returning nothing is not a fact about the production. The empty
states now say what was found and name the rebuild script.

**The cast detail is one component again, and every screenplay type has one home.** 314 lines of markup
were duplicated between `ScriptStudio.tsx`, which is what actually rendered, and
`CharacterProfileCard.tsx`, which rendered in the popup. Diffed before collapsing rather than assumed
equal: they differed in 21 lines, all cosmetic or a callback the card already takes as a prop. The inline
copy is now a `<CharacterProfileCard>`, and ScriptStudio is 2703 lines rather than ~3050.

**Five types were declared twice, and two of them disagreed.** `CharacterProfile`,
`CharacterRelationship` and `DialogueLine` were identical. `ScreenplayScene` and `ShotProposal` were not:
one file said `dialogues`, the other `dialogue?`, and they disagreed about what a camera is. Two types
with one name and different shapes is worse than a duplicate -- the compiler is content either way and
the mismatch only shows at runtime. The copies in `types.ts` turned out to be dead, imported by nothing
in the file or out of it, so the live versions moved in and the dead ones went, taking `CameraSetup` with
them, which existed only to serve the dead `ShotProposal`.

**`--reload` wedges this backend, and the fix is a flag.** Recommended this morning without noticing:
the app holds a Server-Sent Events stream open, uvicorn's graceful shutdown waits for connections to
close, and the SSE connection never does. Every code change left the server stuck on "Waiting for
connections to close" until the browser tab was shut. `.claude/launch.json` now passes
`--timeout-graceful-shutdown 1`. The symptom looked like a frontend fault -- 500s in the console -- which
is why it took a while to see.

**A character's personality, scored from the script, with the lines it was read from beside it.** Five
axes drawn as a polygon, and every line that character speaks, navigable in script order. The two are
deliberately side by side: the polygon is a reading and the lines are its evidence, and a reading nobody
can check against the script is an assertion with a chart around it.

The axes are the Big Five, named rather than invented. Five dimensions made up for this app would be
pseudo-psychology with a chart around it and nobody could say what a score meant. They score the
*character* as written, never an actor.

**The interesting part is the gap.** Rule 2 of the character prompt says never say a detail is unknown --
right for costume, because a wardrobe has to be built and "unknown" cannot be photographed. It is wrong
for personality: a character with four lines does not contain five readings. So the axes are an explicit
exception in the prompt, a score may come back null, and null survives all the way to the chart. It is
drawn as a missing vertex and a dashed spoke, never as a zero, because zero puts a point at the centre
and reads as "none of this trait" -- absence rendered as presence. A score outside 0-100 is dropped
rather than clamped: a model returning 140 has not understood the scale, and clamping would turn a broken
answer into a confident one.

**Two facts that looked identical and no longer do.** Character profiles are built from dialogue cues, so
a character who never speaks has no profile -- which made "appears and never speaks" indistinguishable
from "not in this script". The lines endpoint now checks the scene text for a whole-word uppercase
mention, which is the screenplay convention for naming someone in action, and reports the two separately.
Case-sensitive on purpose: a lowercase "lead" in prose is the English word.

**Found while building it: the cast detail is duplicated.** The same markup exists in
`CharacterProfileCard.tsx` (which renders in the popup) and inline in `ScriptStudio.tsx` (which is what
actually renders), and `CharacterProfile` is declared twice -- in `types.ts` and again in
`ScriptStudio.tsx`. Adding a field to one and not the other type-errors in exactly one place and is easy
to miss. Both were updated and both carry a note; collapsing them is worth doing on its own rather than
inside a feature.

Verified in the browser against the real demo script, whose LEAD already carried genuine inference:
openness 85 "dedicates himself entirely to complex musical counterpoint", extraversion 15 "whispers to
himself and walks out without answering", volatility 90. The first draft clipped its own axis labels to
"Conscie" and "vol... 90", which named nothing -- short forms and a wider viewBox since.

**The test suite was writing into the mirror a demo reads from, and now is not.** With CLICKHOUSE_HOST
set, a suite run put fixtures -- CHTEST, HEAVY, BATCH1, INTENT_DISAGREE -- into the same tables as the
production's rows: 5355 of 5830 were test data, so the analytics panel was 92% fixtures and nothing about
it looked wrong, because the rows have the same shape as real ones. The same failure as the compose files
sharing a project name, one layer down: two things that should have been separate were separated only by
nobody having run them together.

`CLICKHOUSE_DATABASE` now selects the database, defaulting to `cinespine`, and the tests use
`cinespine_test`. It is set at conftest *import* rather than in a fixture, because `backend.app.main`
builds its writer at import time and that is when the schema is created -- a fixture runs later, so the
app would have made its tables in one database while writes resolved to another and every insert failed
into a database with no tables. That is exactly what happened on the first attempt.

Falsified by running the whole suite twice against a live ClickHouse: `cinespine` stayed at 5830 rows
throughout, and 325 rows landed in `cinespine_test`. Before the change that run would have added to the
production database.

**The mirror was wiped and rebuilt from the spine**, by `scripts/rebuild_mirror.py`, which exists rather
than being a one-off because the mirror had drifted twice in a day: test residue, and 84 rows under a
slate no department ever wrote from the Silverstack defect. It went from 5830 rows to 41 -- the true
contents of the dev spine -- and the analytics queries now return two scenes with four and three
departments, no test productions, and no disagreements. The script refuses to run when
CLICKHOUSE_DATABASE is anything but the default, since rebuilding the test database from the real spine
would be the mistake in the other direction.

The rebuild reuses the app's own `_clickhouse_datetime` rather than converting timestamps a second way,
so rebuilt rows carry the times the live path would have written -- including the fix for naive datetimes
landing an hour early.

**The slate ranges are a completeness check now, and the first thing they caught was ours.** Office states
`Slates: 27/7 - 8, 49/1 - 9, 117/1 - 5` and nothing read it, though it is the only expected extent the day
carries -- so nothing could notice a slate that should not exist. Run against the real day the new check
produced exactly one finding, `27/27`, a slate no department ever wrote: all three Silverstack parsers
were building `scene + "/" + shot` when Silverstack's `Shot` field is already the whole slate. DIT had
been disagreeing with camera about every take of the day while the board showed nothing, because the two
never met on a common key. With the parsers fixed the check is silent on that day.

The check stays quiet in three cases where the page is silent rather than denying: a scene with no stated
range, a slate whose shot half is not a number, and a report where no ranges parsed at all. Turning any of
those into a finding would be absence rendered as presence.

**The two dead gauges are closed: one filled, one removed.** `cinespine_active_discrepancies` was declared
and never set, so it could only ever render as a flat zero -- absence rendered as presence, on a board
whose whole job is to say whether a day is clean. It is now written wherever discrepancies are computed,
and gained `production_id` and `shoot_day` labels: without them the second day somebody opened would
overwrite the first while still looking like a total. Every severity and kind is written on each
observation, zeros included, because a gauge keeps its last value and setting only what occurred would
leave a resolved discrepancy showing its old count. A day nobody has opened stays absent rather than zero,
which are different facts.

Observed where the discrepancies are computed rather than at scrape time. Reconciling every day of a shoot
on every Prometheus scrape would cost far more than the number is worth, so the gauge covers the days
somebody has looked at.

`cinespine_department_sync_lag_seconds` went the other way. It cannot be computed: wrap is stated as a
time of day with no date, and the only other timestamp is when the document reached this system. It is now
an open question that names the missing input -- the report's own date -- rather than a gauge that can
never fill. Both Grafana dashboards pointed at it, so both panels were repointed: one to paperwork filed
per department, which is the half of a sync matrix that is actually known, and one to discrepancies broken
down by kind, which the new labels made possible.

**The editorial vocabulary now runs to the end of the chain**, and adding it migrated nothing. See the
entry in [findings/spec-drift.md](findings/spec-drift.md) and
[domain/completion.md](domain/completion.md), which had recorded the change as needing a migration and was
wrong about that: the defect was in `finished`'s label and description, which are vocabulary metadata and
are never stored on a tag. A rename would have needed one -- and would have meant rewriting an append-only
trail, falsifying what people recorded at the time.

**The analytical mirror can now live somewhere other than this machine.** The connector hardcoded plain
HTTP on 8123, so a hosted ClickHouse was unreachable by construction. `CLICKHOUSE_SECURE` now selects
TLS and the default port follows it to 8443, because the two are not independent: a managed instance
answers only on the TLS port, and a secure connection aimed at 8123 does not fail with "wrong protocol"
-- it fails as unreachable, which reads like the server being down and sends people to the wrong end.
The failure message now names the protocol and port it tried, for the same reason. `CLICKHOUSE_VERIFY`
exists for a self-hosted instance with a private certificate authority, and defaults to checking.

TLS is stated, never inferred from the hostname. Inferring means keeping a list of what hosted endpoints
look like, and that list is wrong the day a provider adds a domain.

Verified against a real TLS server rather than by asserting the flag was passed: a ClickHouse with a
self-signed certificate on 18443 accepted the connection and all five tables were created over it. Both
negatives were checked too -- certificate verification on refuses a self-signed cert, and plain HTTP
aimed at the TLS port fails with a message naming plain HTTP. The handshake test stays in the suite,
skipped unless `CINESPINE_TLS_CLICKHOUSE` is set.

**Whether PostHog and CineSpine could share one ClickHouse: tested, and the answer is no.** The schema
applies to PostHog's ClickHouse 22.8 and all six analytics queries return the same shapes there as on
24.3, so it would work. It should still not be done. PostHog 1.43 refuses ClickHouse >=22.9, so sharing
pins the mirror at a version a third party controls; the mirror would live inside a stack that is
optional and may not exist at all if PostHog's cloud is used; a `down -v` on that file would delete it,
which is the coupling the compose projects were just separated to prevent; and PostHog owns that
server's cluster, keeper and migrations. In the cloud it is not possible at all -- PostHog's SaaS runs
its own ClickHouse with no way to point it elsewhere, and self-hosted PostHog needs `remote_servers` and
`macros` that ClickHouse Cloud does not let anyone define.

**The self-hosted-only check was removed, and the payload is now the whole defence.** Both clients used
to refuse a host on `posthog.com`. The deployment may use PostHog's cloud, so the check is gone --
`is_configured` is now just "a key and a host", with the host still required rather than defaulted
because where telemetry goes should be written down rather than inherited. The argument for the original
constraint was not wrong; what changed is the judgement that the disclosure is acceptable, and that rests
entirely on the payload being bounded. So the bound is now stated exactly in
[constraints/privacy.md](constraints/privacy.md) rather than implied: which production, which day, which
department, which surface, and a role token for who. Twelve tests went and three replaced them; every
filter test stayed, and carries more weight than it did.

`advanced_disable_decide: true` matters more after this change, not less. `/decide` is how PostHog can
switch capture on from the server, and with a third-party destination that is the difference between
settings that are ours and settings that can be changed remotely.

**A self-hosted PostHog stack exists as an opt-in file**, `docker-compose.posthog.yml`, on port 8010 --
PostHog's default is 8000, which is this app's backend, and `.env.example` had been documenting that
collision as if it were a working value. Seven containers, including PostHog's own ClickHouse and Kafka:
its internal architecture, not this project's, and the reason it is opt-in rather than in the default up.

Brought up and verified rather than written and asserted. Four things were wrong on the first attempt:
the MinIO healthcheck used `curl`, which that image does not contain; `mc ready local` assumes port 9000
while the container serves 19000, so the check never passed and the web service waited forever on a
dependency that was actually healthy; the web command `/compose/start` is mounted from PostHog's own repo
and does not exist in the image, whose entrypoint already runs migrate, worker and server; and Postgres
was pinned to 16, which this PostHog release refuses outright.

**A `--remove-orphans` took down the base stack, and all three compose files are now separate projects.**
Every file defaulted to the project name `cinespine`, so tearing down one reached the containers of
another -- ClickHouse, Grafana and Prometheus, up 21 hours, all removed. The named volumes meant no data
was lost (5914 events still in the mirror). Now: `cinespine`, `cinespine-observability`,
`cinespine-posthog`.

The base file keeps the name it had, deliberately. A project name is part of a volume's name, so
renaming it would orphan `cinespine_clickhouse_data` and the mirror would come back empty -- which looks
exactly like a mirror that was never written to. The observability file was safe to rename because
everything in it is a bind mount.

**Separate projects turned up a second bug that had to be fixed first.** Grafana was defined in *two*
files, same container name, same port. While they shared a project name Compose treated the two as one
service and the last `up` won, so nothing ever complained; split into separate projects they collided
outright and neither would start. The definition in `docker-compose.yml` was the stub -- no provisioning,
no dashboards, and its `grafana_data` volume had never been written to -- so it went, and Grafana is now
defined only in the observability file. Migrating the running containers needed them removed once, since
they still carried the old project label.

Falsified with the command that caused the incident: `docker compose -f docker-compose.observability.yml
down --remove-orphans` now removes its own two containers and leaves ClickHouse and all seven PostHog
containers running.

**Acknowledging after the write.** The hole found while removing Kafka is closed: `EventBus.publish`
now runs every handler and then raises `EventHandlerError` carrying all the failures, so handlers stay
isolated from each other while a failure becomes impossible to absorb. `/api/upload` and
`/api/upload/file` answer 500 and name the doc_id; `/api/seed` counts failures separately from skips,
because in bulk the old behaviour reported every file as ingested while each produced nothing. A failed
spine write is deliberately *not* a DLQ entry: the DLQ means the paperwork was refused, which sends
someone to check a report that was fine.

Falsified rather than assumed -- with the swallowing put back, 10 of the 13 new tests fail, and the
three that pass are the negative controls (a healthy upload, a legitimately rejected document, a publish
where nothing fails).

**Two things this turned up.** `/api/upload/file`'s failure branch named a variable not in its scope, so
it would have raised NameError instead of the error it was reporting -- untested, which is why it was
wrong. And `monkeypatch.undo()` is unsafe in this suite: the autouse fixtures in `backend/tests/conftest.py`
take the same function-scoped monkeypatch, so undoing a patch also reverts `CINESPINE_DB_PATH` and the
test then reads a different database than the one it wrote to.

**Kafka was never running, and has been removed rather than wired.** `EventBus` carried a Confluent
producer that could not execute -- the only construction passed `in_memory=True`, which short-circuits
the branch that builds it -- and `docker-compose.yml` started a Redpanda container that this app never
connected to. Tracing the ingest path settled it: upload, parse, spine write and mirror are one
synchronous call stack in one process, so the broker would have sat between two functions. The spine is
already an append-only log in SQLite that the mirror rebuilds from, so the durability argument runs the
other way. Container, `confluent-kafka` wheel and dead branch all gone; the bus stayed, because
ingestion and DLQ telemetry both run through it. The REQ-01 gap is now recorded as a decision in
[findings/spec-drift.md](findings/spec-drift.md).

**Publishing to a topic nobody listens on is silent, and the ingest path swallows handler failures.**
Two related holes found while removing the broker. The first already caused a bug once -- office
documents were classified, published to `production.raw.office`, and produced nothing while the upload
reported INGESTED -- and `EventBus.topics()` now makes the wiring inspectable. The second is open: a
handler that raises is logged and swallowed, so a spine write that fails still returns 200. The fix is
to acknowledge after the write, not to put a queue in front of it.

**Six questions answered by the domain source.** `pt` means part; "complete" is a chain of seven stages
rather than a state; reject rows that do not look like takes; delete from the mirror too; requirements
need a production level; the demo should run on anonymised real paperwork. The first two are now domain
documents, three are implemented, and the last is a piece of work nobody has started. See
[open-questions.md](open-questions.md).

**A camera CSV footer could become a scene.** normalize_slate canonicalises whatever it is given, so a
contact line became a slate and reached the spine, the mirror and an analytics result. The parser now
tests the shape of a slate before accepting a row.

**A day nobody had offloaded rendered as a clean day.** The gate had the negative -- never report missing
media without a report -- and then said nothing, which is the same mistake pointing the other way. Fixing
it surfaced two larger defects sharing the block: the existence findings were computed into a local and
dropped, and the clip matcher failed on a file extension.

**Clearing the search box was hiding a wrong-array bug.** Deep-linking emptied the reader's query, which
the requirement forbids -- and the emptying was load-bearing: the jump computed an index into `takes` and
the navigator reads `filteredTakes`, so it only ever landed correctly because the filters had just been
cleared. Fixed by pinning the target by identity.

**The analytical mirror was write-only.** Every `SELECT` in the codebase went to SQLite while 5,090 events
sat in ClickHouse unread. The cost of writing was paid and none of the use taken. Fixed by
[the read path](architecture/analytical-mirror.md).

**A multi-camera take is not a disagreement.** The obvious disagreement query -- more than one roll for
this take -- returned rows immediately, and every one was a take shot on three cameras agreeing with
itself perfectly. Grouping by camera returns nothing on the demo day, which is the honest answer.

**A parsed fact can carry contact details.** A camera CSV row that was not a take at all left a contact
line in the `slate` field, reached the mirror, and surfaced in a scene grouping. See
[open questions](open-questions.md).

**Office documents reached no handler.** `production.raw.office` had no subscriber. A daily production
report ingested to zero events, zero takes and no dead-letter entry, while the upload answered
`INGESTED`. See [findings/defects-found.md](findings/defects-found.md).

**Source documents were served ungated.** Both document endpoints returned the original paperwork,
including a script supervisor's phone number and email. See [constraints/privacy.md](constraints/privacy.md).

**The shipped PII scrubber destroyed production data.** `A120 280726` came back as `A[REDACTED_PHONE]`:
a camera card and its shoot date read as a phone number.

**An audit against the design workspace found six gaps.** See [findings/spec-drift.md](findings/spec-drift.md).

## 2026-08-29

**A sequence shot over several days claimed to belong to one.** Scene 119 covered on day 11 and finished
on day 31 came back as two unrelated rows. Third instance of the same mistake; see
[domain/shoot-days.md](domain/shoot-days.md).

**Per-event durability was affordable.** Measured before choosing: 2,000 events cost 9.4s with a
connection per event and 0.06s on a held connection in WAL. See
[architecture/persistence.md](architecture/persistence.md).

**Requirements lost their history.** Creating and resolving reached the spine; every handover and block in
between was an in-place overwrite.

## 2026-08-28 and earlier

**Ingestion slowed 9x when every event was inserted to ClickHouse separately.** A 72-event document went
from 0.8s to 7.4s and a 1,991-event volume to over two minutes. Fixed by batching.

**A facing page carries takes from across the schedule.** It is filed on the day it is handed over, not
the day its takes were shot. First instance of the shoot-day mistake.

**Silence is not denial.** A lined page that does not mark a take as circled has not said it was
uncircled. Recorded as `None` rather than `false`.
