---
type: log
title: What was learned, and when
description: Chronology of findings about this codebase, newest first
tags: [log]
---

# Log

Newest first. Each entry names what produced it.

## 2026-08-30

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
