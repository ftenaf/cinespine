"""
Generates clickhouse_production_health.json beside this file.

The dashboard is JSON because Grafana provisions JSON; it is generated
because fourteen panels of hand-edited SQL inside JSON strings is where
quoting mistakes go to hide. Edit here, run this, commit both.

    python grafana/dashboards/build_clickhouse_production_health.py

Every panel reads the same tables the app's /api/analytics reads, with the
same two rules: audit_discrepancies is read FINAL (a re-emitted snapshot on a
ReplacingMergeTree, so an unmerged older version counts a settled finding as
still open) and the three event trails are resolved to current state with
argMax (a raw GROUP BY status counts every transition ever made).
"""
import json
import os

DS = {"type": "grafana-clickhouse-datasource", "uid": "clickhouse_ds"}
P = "'${production_id}'"

FINAL_NOTE = (
    "audit_discrepancies is a re-emitted snapshot on a ReplacingMergeTree. Until a merge runs "
    "a settled finding is present twice, so every query here reads FINAL; without it a resolved "
    "finding counts as still open."
)
ARGMAX_NOTE = (
    "Append-only trail. Current state is the latest event per entity (argMax), "
    "never a raw GROUP BY status."
)

_next_id = 1


def _id():
    global _next_id
    _next_id += 1
    return _next_id - 1


def target(sql, fmt=1):
    return {
        "datasource": DS, "editorType": "sql", "queryType": "sql",
        "format": fmt, "rawSql": sql.strip(), "refId": "A",
    }


def panel(ptype, title, sql, x, y, w, h, fmt=1, desc="", **extra):
    p = {
        "id": _id(), "type": ptype, "title": title, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": [target(sql, fmt)],
    }
    if desc:
        p["description"] = desc
    p.update(extra)
    return p


def row(title, y):
    return {
        "id": _id(), "type": "row", "title": title, "collapsed": False,
        "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": [],
    }


def stat_threshold(color):
    return {
        "fieldConfig": {"defaults": {
            "color": {"mode": "thresholds"},
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "green", "value": None}, {"color": color, "value": 1},
            ]},
        }, "overrides": []},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "colorMode": "background", "graphMode": "none",
        },
    }


STACKED_BARS = {"fieldConfig": {"defaults": {"custom": {
    "drawStyle": "bars", "fillOpacity": 60, "stacking": {"mode": "normal"},
}}, "overrides": []}}

panels = [
    row("Continuity: what the audit found", 0),
    panel("stat", "Open CRITICAL",
          f"SELECT countIf(is_resolved = 0) AS open_critical FROM cinespine.audit_discrepancies FINAL "
          f"WHERE production_id = {P} AND severity = 'CRITICAL'",
          0, 1, 4, 4, desc=FINAL_NOTE, **stat_threshold("red")),
    panel("stat", "Open WARNING",
          f"SELECT countIf(is_resolved = 0) AS open_warning FROM cinespine.audit_discrepancies FINAL "
          f"WHERE production_id = {P} AND severity = 'WARNING'",
          4, 1, 4, 4, desc=FINAL_NOTE, **stat_threshold("orange")),
    panel("stat", "Resolved",
          f"SELECT countIf(is_resolved = 1) AS resolved FROM cinespine.audit_discrepancies FINAL "
          f"WHERE production_id = {P}",
          8, 1, 4, 4, desc=FINAL_NOTE,
          fieldConfig={"defaults": {"color": {"mode": "fixed", "fixedColor": "blue"}}, "overrides": []},
          options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                   "colorMode": "value", "graphMode": "none"}),
    panel("table", "Findings by type", f"""
SELECT discrepancy_type, severity,
       countIf(is_resolved = 0) AS open,
       countIf(is_resolved = 1) AS resolved,
       arraySort(groupUniqArrayIf(shoot_day, is_resolved = 0)) AS open_days
FROM cinespine.audit_discrepancies FINAL
WHERE production_id = {P}
GROUP BY discrepancy_type, severity
ORDER BY open DESC, multiIf(severity = 'CRITICAL', 0, severity = 'WARNING', 1, 2), discrepancy_type
""", 12, 1, 12, 8, desc=FINAL_NOTE),
    panel("table", "Open findings", f"""
SELECT severity, shoot_day, discrepancy_type, entity_type, entity_id, description
FROM cinespine.audit_discrepancies FINAL
WHERE production_id = {P} AND is_resolved = 0
ORDER BY multiIf(severity = 'CRITICAL', 0, severity = 'WARNING', 1, 2), shoot_day, discrepancy_type
""", 0, 5, 12, 8, desc="Everything still unsettled, most severe first. Empty is the answer worth wanting."),

    row("Ingestion: who has filed", 13),
    panel("timeseries", "Documents ingested per department", f"""
SELECT $__timeInterval(created_at) AS time, department, count() AS events
FROM cinespine.production_events
WHERE production_id = {P} AND $__timeFilter(created_at)
GROUP BY time, department
ORDER BY time
""", 0, 14, 14, 8, fmt=0,
          desc="One row per parsed fact from a departmental document. A department going flat while others file is the signal.",
          **STACKED_BARS),
    panel("table", "Last filing per department", f"""
SELECT department, max(created_at) AS last_filed,
       dateDiff('minute', max(created_at), now()) AS minutes_ago,
       count() AS events, uniqExact(shoot_day) AS days
FROM cinespine.production_events
WHERE production_id = {P}
GROUP BY department
ORDER BY last_filed DESC
""", 14, 14, 10, 8, desc="Freshness board. A department not on this list has never filed for this production."),

    row("Takes: what was shot", 22),
    panel("table", "Takes per shoot day", f"""
SELECT shoot_day,
       uniqExact(slate, take_id) AS takes, uniqExact(slate) AS slates,
       countIf(is_starred) AS starred, countIf(is_pickup) AS pickups, countIf(is_vfx) AS vfx,
       countIf(camera_roll = '') AS rows_without_camera_roll
FROM cinespine.takes_meta FINAL
WHERE production_id = {P}
GROUP BY shoot_day
ORDER BY shoot_day
""", 0, 23, 12, 7,
          desc="Grain is one row per take per camera roll, so takes is uniqExact(slate, take_id), not count(). "
               "sound_roll is not reconciled yet and is left off on purpose."),
    panel("barchart", "Post-production stage per scene and shot", f"""
SELECT status, count() AS targets
FROM (
    SELECT target_type, target_id,
           argMax(status, created_at) AS status,
           argMax(action, created_at) AS action
    FROM cinespine.editorial_tag_events
    WHERE production_id = {P}
    GROUP BY target_type, target_id
)
WHERE action != 'cleared' AND status != ''
GROUP BY status
ORDER BY targets DESC
""", 12, 23, 12, 7, desc=ARGMAX_NOTE + " A cleared tag is the absence of a state, not one.",
          options={"orientation": "horizontal", "showValue": "always", "legend": {"showLegend": False}}),

    row("Requirements: what is being asked", 30),
    panel("table", "Current state by status and priority", f"""
SELECT status, priority, count() AS requirements
FROM (
    SELECT requirement_id,
           argMax(status, created_at) AS status,
           argMax(priority, created_at) AS priority,
           argMax(action, created_at) AS last_action
    FROM cinespine.requirement_events
    WHERE production_id = {P}
    GROUP BY requirement_id
)
WHERE last_action != 'deleted'
GROUP BY status, priority
ORDER BY multiIf(status = 'blocked', 0, status = 'open', 1, status = 'in_progress', 2, 3),
         multiIf(priority = 'critical', 0, priority = 'high', 1, 2)
""", 0, 31, 12, 8, desc=ARGMAX_NOTE + " Deleted requirements are excluded."),
    panel("table", "Blocked and open, oldest first", f"""
SELECT requirement_id, status, priority, assigned_to,
       round(dateDiff('hour', raised_at, now()), 1) AS hours_open
FROM (
    SELECT requirement_id,
           argMax(status, created_at) AS status,
           argMax(priority, created_at) AS priority,
           argMax(assigned_to, created_at) AS assigned_to,
           argMax(action, created_at) AS last_action,
           min(created_at) AS raised_at
    FROM cinespine.requirement_events
    WHERE production_id = {P}
    GROUP BY requirement_id
)
WHERE last_action != 'deleted' AND status IN ('blocked', 'open')
ORDER BY hours_open DESC
LIMIT 50
""", 12, 31, 12, 8, desc="Ageing of everything nobody has finished. Hours since first raised."),

    row("Engagement: who is looking", 39),
    panel("timeseries", "Actions per hour by kind", f"""
SELECT $__timeInterval(created_at) AS time, action, count() AS actions
FROM cinespine.user_activity
WHERE production_id = {P} AND $__timeFilter(created_at)
GROUP BY time, action
ORDER BY time
""", 0, 40, 14, 8, fmt=0,
          desc="Views and mutations are separate series on purpose; do not sum them. "
               "A count of actions is activity, not effort.",
          **STACKED_BARS),
    panel("table", "Time to acknowledge, by actor", f"""
SELECT actor, count() AS acknowledgements,
       round(quantile(0.5)(seconds_since_target_created) / 60, 1) AS median_minutes,
       round(max(seconds_since_target_created) / 60, 1) AS slowest_minutes
FROM cinespine.user_activity
WHERE production_id = {P} AND action = 'acknowledged' AND seconds_since_target_created > 0
GROUP BY actor
ORDER BY median_minutes DESC
""", 14, 40, 10, 8,
          desc="How long a requirement had existed when its assignee acknowledged it. "
               "Rows with no creation time are excluded rather than counted as instant."),
]

PRODUCTIONS = "SELECT DISTINCT production_id FROM cinespine.production_events ORDER BY production_id"

dashboard = {
    "uid": "clickhouse_production_health",
    "title": "Production Health from ClickHouse (CineSpine)",
    "description": (
        "The analytical spine read directly. Same questions as /api/analytics, "
        "asked of the cinespine database with a production_id filter."
    ),
    "tags": ["cinespine", "clickhouse"],
    "editable": True, "graphTooltip": 1, "schemaVersion": 39, "version": 1, "refresh": "1m",
    "time": {"from": "now-7d", "to": "now"},
    "timezone": "utc",
    "templating": {"list": [{
        "name": "production_id", "label": "Production", "type": "query", "datasource": DS,
        "query": {"rawSql": PRODUCTIONS, "queryType": "sql", "editorType": "sql", "format": 1},
        "definition": PRODUCTIONS,
        "refresh": 1, "sort": 1, "includeAll": False, "multi": False,
        "current": {"text": "DEMO_PRODUCTION", "value": "DEMO_PRODUCTION"},
    }]},
    "annotations": {"list": []},
    "panels": panels,
}

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "clickhouse_production_health.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, indent=2)
        f.write("\n")
    print(f"{out}: {len(panels)} panels")
