# Workload tracking: measure what people do, not just what they own

Status: done, 2026-09-04. Steps 1-4 landed (554c851, 1d97033, 1c350e7 and
the docs commit). Kept as the record of why. Open follow-up: thread
`currentUser.handle` into the production, crew, script-link and breakdown
bodies so those rows stop being `actor_source=default`.

## Why

`crew_workload` (backend/app/spine/workload.py) answers "who owns how many
open requirements". That is assignment, not activity. `user_activity` was built
to hold activity but has one writer: the Requirements board records `viewed`
and `acknowledged`. The other 36 mutation routes record nothing, so the table
cannot answer "who did what today".

## What the number means, said up front

Counted actions are activity, not effort. A tag set in two seconds and a
discrepancy resolved after an hour's search are one row each. The dashboard
card says so in its subtitle, or the number gets read as a score. Identity is
the self-declared `@handle` from `/auth/login` (auto-creates any handle, no
password). Fine for a crew that trusts each other; wrong for anything else.
Auth is out of scope here.

## Step 1: capture every mutation, server-side

`backend/app/spine/activity_store.py`
- Widen `ACTIONS` from `("viewed", "acknowledged")` to add
  `created`, `updated`, `resolved`, `reopened`, `deleted`, `tagged`,
  `uploaded`, `linked`, `unlinked`, `ran_agent`.
- Widen `TARGET_TYPES` to add `crew`, `script`, `breakdown`, `tag`, `agent`.
- No schema change: `action` and `target_type` are TEXT. ClickHouse table
  is `LowCardinality(String)`-free plain String (schema.py:110), also fine.

`backend/app/api/routes.py`
- One helper near `record_activity`:
  `_record(actor, action, target_type, target_id, production_id, shoot_day="", department="", target_label="", context=None)`.
  Wraps `spine_writer.record_activity`, swallows `UnknownActivityValue` with a
  `logger.warning`, never raises. Context goes through
  `analytics.safe_properties` so free text cannot leak into `context_json`.
- Call it from these routes, actor from the field each body already has:

| route | action | target_type | actor field |
|---|---|---|---|
| POST /productions | created | production | body has none: use `@director` default, flag in doc |
| PATCH /productions/{id} | updated | production | same |
| DELETE /productions/{id} | deleted | production | same |
| POST /productions/{id}/crew | created | crew | `handle` is the subject, actor unknown: `@director` |
| PATCH /productions/{id}/crew/{handle} | updated | crew | same |
| DELETE /productions/{id}/crew/{handle} | deleted | crew | same |
| POST /upload, /upload/file | uploaded | document | `@upload` (matches PostHog call at 837) |
| DELETE /documents/{doc_id} | deleted | document | `@director` |
| POST /discrepancies/{id}/resolve | resolved | discrepancy | `resolved_by` |
| POST /discrepancies/{id}/unresolve | reopened | discrepancy | body: add `reopened_by` optional |
| POST /requirements | created | requirement | `created_by` |
| PATCH /requirements/{id} | updated | requirement | `updated_by` |
| POST /requirements/{id}/resolve | resolved | requirement | `resolved_by` |
| DELETE /requirements/{id} | deleted | requirement | query param `by`, default `@director` |
| PUT /tags | tagged | tag | `updated_by` |
| DELETE /tags | deleted | tag | `updated_by` |
| POST /notifications/{id}/read | acknowledged | notification | `recipient_handle` (already PostHog'd at 2495) |
| POST /agents/wrap-rescue/run | ran_agent | agent | `actor` |
| POST /agents/assistant-editor-queue/run | ran_agent | agent | `actor` |
| POST /script/parse, /script/upload | uploaded | script | `@director` |
| POST /script/link, DELETE /script/link | linked / unlinked | script | `@director` |
| PUT/DELETE /script/{id}/breakdowns/{scene} | updated / deleted | breakdown | `@director` |

Not recorded: `/seed`, `/demo/wipe`, `/auth/*`, `/assistant/explain`,
`/script/characters/*`, `/script/presets/suggest`, `/script/generate-storyboard`,
`/activity` itself. Reads never.

Rows where the actor is a default rather than a field are honest about it:
`context_json` carries `{"actor_source": "default"}` so a query can exclude
them. Follow-up, not this step: thread `currentUser.handle` from
`frontend/src/App.tsx:80` into those bodies.

Tests: `backend/tests/test_activity_capture.py`. One test per route family:
call the route, read `GET /activity?production_id&target_type&target_id`,
assert one row with the expected action and actor. One test that an unknown
action is refused by the store. One that the mirror receives the row
(`test_acknowledgement.py::test_an_activity_event_is_mirrored` is the model).

## Step 2: queries

`backend/app/spine/analytics.py`, ClickHouse only, same `_rows` contract
(None when unreachable):
- `actions_by_actor_and_day(client, production_id)`: actor, shoot_day,
  mutations, views. Views and mutations as separate columns; never summed.
- `actions_by_department_and_hour(client, production_id)`: for the
  "when does sound do its paperwork" question.
- `first_touch_lag(client, production_id)`: per requirement, seconds from
  `requirement_events.created` to the assignee's first `user_activity` row
  on it. Median and p90 per actor.

Exclude `context_json LIKE '%"actor_source": "default"%'` from per-actor
groupings.

`GET /api/analytics` (routes.py:2560 area) gains the three keys.

Tests: `backend/tests/test_analytics_queries.py` already gates on
`HAS_CLICKHOUSE`; add three cases using `isolated_clickhouse_database`.

## Step 3: surfaces

`frontend/src/components/ProductionDashboard.tsx`: `ActivityCard` next to
`CrewWorkloadCard` (line 151 pattern). Table: actor, today's mutations,
today's views, 7-day sparkline of mutations. Subtitle: "Counts actions, not
effort." Types in `frontend/src/types.ts` beside `CrewWorkload` (656).
`frontend/src/api.ts`: read from `fetchProductionAnalytics`, no new call.

Grafana: Grafana Cloud has no ClickHouse datasource (checked 2026-09-04,
`gcx api /api/datasources`). Options: install the ClickHouse plugin on the
stack and add `t3wb3t0af4.europe-west4.gcp.clickhouse.cloud:8443` as a
datasource with a read-only ClickHouse user (create one: the console
identity is OAuth, `default` is admin); or skip Grafana and keep this
in-app. Recommend skip for now; the dashboard card answers the question.

## Step 4: docs

- `docs/ARCHITECTURE.md`: `user_activity` is the activity ledger; list the
  vocabulary and the actor_source rule.
- `README.md` env table: nothing new.
- Memory `cinespine-clickhousectl`: update "only written by the Requirements
  board" once step 1 lands.

## Order and size

1. Step 1, routes + store + tests: ~half day. Only risky step; 22 call sites.
2. Step 2, queries + tests: ~2h. Needs ClickHouse in the test env.
3. Step 3, card: ~2h.
4. Step 4: ~30min.

Deploy after step 1 alone is worth it: rows start accumulating before the
card exists.
