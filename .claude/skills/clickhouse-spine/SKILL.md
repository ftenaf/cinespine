---
name: clickhouse-spine
description: Query, read or extend the CineSpine ClickHouse analytical spine correctly. Use when writing SQL against the cinespine or cinespine_test databases, adding a query to backend/app/spine/analytics.py, adding a Grafana panel that reads ClickHouse, answering "what is in ClickHouse", or interpreting a count from any of its six tables. Covers the grain and engine of each table, the two read rules (FINAL on the snapshot, argMax on the trails) that every naive GROUP BY gets wrong, which columns are not populated, and how to reach the database as admin, as read-only, and through Grafana.
---

# The ClickHouse spine

Six tables in database `cinespine` (prod) and `cinespine_test` (pytest, same
host, much larger, synthetic). DDL is `backend/app/spine/schema.py`, applied
with `IF NOT EXISTS` on every app connect; the writer is
`backend/app/spine/writer.py`; every query the app asks is
`backend/app/spine/analytics.py`, served as one JSON by `GET /api/analytics`.
Read those before adding a query -- the question is probably already asked.

ClickHouse is a **mirror**, never the source. SQLite (`spine.db`) holds the
current rows; ClickHouse holds the history and answers the scan-shaped
questions. Nothing in the app reads a current fact from ClickHouse.

## The tables

| Table | Engine | Grain | What it is |
| :--- | :--- | :--- | :--- |
| `production_events` | MergeTree | one row per parsed fact from a departmental document | the raw ingestion trail: `axis` (existence / belief / intent), `department`, `doc_type`, `entity_type`, `payload_json` |
| `takes_meta` | ReplacingMergeTree(`last_updated`) | one row per (production, shoot_day, slate, take_id, **camera_roll**) | reconciled takes with starred / pickup / vfx flags and timecodes |
| `audit_discrepancies` | ReplacingMergeTree(`created_at`) | one row per (production, shoot_day, discrepancy_type, entity_id) | the audit's findings as they currently stand, `is_resolved` 0/1 |
| `requirement_events` | MergeTree | one row per state change of a requirement | append-only trail: `action`, `status`, `priority`, `assigned_to` |
| `editorial_tag_events` | MergeTree | one row per tag set or cleared on a scene or shot | append-only trail of post stages |
| `user_activity` | MergeTree | one row per user action | ledger every mutation route writes via `_record()` in routes.py: `action`, `target_type`, `actor`, `seconds_since_target_created` |

A "requirement" is a cross-department ask on the Requirements board, not a
deliverable. `production_events.payload_json` is read with JSON functions,
not materialized columns, on purpose (see the analytics.py docstring).

## The two read rules

Both were found by getting them wrong on the demo data, which is small
enough that the error is visible. At real volume it would not be.

**1. Snapshots are read `FINAL`.** `audit_discrepancies` is re-emitted every
time the audit recomputes, with `is_resolved` updated, and the older version
stays until a background merge. Until then a settled finding is present
twice. On 2026-09-04 prod had 6 rows for 3 findings; a plain `countIf(is_resolved = 0)`
said 3 open when all 3 were resolved.

```sql
SELECT discrepancy_type, severity,
       countIf(is_resolved = 0) AS open, countIf(is_resolved = 1) AS resolved
FROM cinespine.audit_discrepancies FINAL
WHERE production_id = 'DEMO_PRODUCTION'
GROUP BY discrepancy_type, severity
```

`takes_meta` is the same engine and gets the same `FINAL`.

**2. Trails are resolved with `argMax`.** `requirement_events`,
`editorial_tag_events` and `user_activity` are append-only. `GROUP BY status`
counts every transition ever made, not the state now. The current state is
the latest event per entity, and a `deleted` or `cleared` last action means
there is no state.

```sql
SELECT status, priority, count() AS requirements
FROM (
    SELECT requirement_id,
           argMax(status,   created_at) AS status,
           argMax(priority, created_at) AS priority,
           argMax(action,   created_at) AS last_action
    FROM cinespine.requirement_events
    WHERE production_id = 'DEMO_PRODUCTION'
    GROUP BY requirement_id
)
WHERE last_action != 'deleted'
GROUP BY status, priority
```

Prefer `argMax` over `FINAL` where the table allows it: it needs no merge and
no forced one.

## What a number does and does not mean

- `takes_meta` is one row **per camera roll**, so "takes" is
  `uniqExact(slate, take_id)`, never `count()`. A three-camera setup is three rows.
- `takes_meta.sound_roll` is empty on every prod row; sound is not reconciled
  into rolls yet. A "missing sound roll" panel reads 100% and means nothing.
- `takes_meta.is_starred` is Nullable: NULL is "the paperwork did not say",
  0 is "the paperwork said not starred". Do not coalesce them.
- `user_activity.seconds_since_target_created` is NULL where the target was
  never created at a moment (a scene, a shoot day). Exclude, never treat as 0.
- `user_activity` rows whose actor is a server-side fallback carry
  `actor_source=default` in `context_json`; per-actor queries exclude them.
- Views and mutations in `user_activity` are separate facts. Never sum them.
- ClickHouse keeps rows that pre-Litestream deploys erased from SQLite, so
  a ClickHouse count above the SQLite count for anything before 2026-09-04 is
  history, not a broken mirror.
- Post stages seen in prod: ready_to_edit, mounted, picture_lock, conformed,
  colour_sound_vfx, dcp, finished. Do not hardcode a shorter list.
- `production_events` also carries synthetic doc types from automation
  (`agent_run`, `discrepancy_resolution`) under editorial / office.

## Reaching it

Three identities, in order of preference for the job:

| Job | How |
| :--- | :--- |
| ad-hoc read, prove a number | `clickhouse_connect` from `.venv` as `default`, creds from `.env` (`CLICKHOUSE_HOST`, `CLICKHOUSE_PASSWORD`, port 8443, `secure=True`). Write the script to a file, run `.venv/Scripts/python <file>`. |
| Grafana panels | user `grafana_ro`: SELECT on `cinespine.*` and four `system` tables, `readonly = 2`. Password only in `.env` as `CLICKHOUSE_GRAFANA_PASSWORD`; never print it. `readonly = 1` breaks the plugin (it sets `max_execution_time` per query). |
| through the Cloud datasource | `/e/dev/tools/gcx.exe datasources clickhouse query -d clickhouse_ds "<sql>"` (positional SQL, no `-q`) |
| as the user's console identity | `clickhousectl` in WSL, read-only; see the memory `cinespine-clickhousectl` |

Writes as `default` are real: lightweight `DELETE FROM cinespine.t WHERE ...`
works on SharedMergeTree. A local dev server mirrors into the **prod**
`cinespine` database (`CLICKHOUSE_DATABASE` unset); only pytest is isolated.

`table_sizes()` in analytics.py hardcodes `database = 'cinespine'` and is
wrong under `cinespine_test`. Known, not fixed.

## Adding a query

1. Write it in `analytics.py` through `_rows()`, with `{db}` for the database
   and `{production_id:String}` as the parameter. Say in the docstring which
   read rule applies and why.
2. Add the key to the `/api/analytics` dict in `backend/app/api/routes.py`,
   the type in `frontend/src/types.ts`, a card in
   `frontend/src/components/AnalyticsPanel.tsx`.
3. Tests in `backend/tests/test_analytics_queries.py`: one `None`-client
   assertion, one live assertion that proves the rule (e.g. open + resolved
   equals the number of distinct keys). Live tests run against `cinespine_test`.
4. If it belongs on a dashboard, add the panel in
   `grafana/dashboards/build_clickhouse_production_health.py`, regenerate,
   and push per the `verify-observability` skill. Judge it on the snapshot.
