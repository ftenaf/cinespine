"""
The questions ClickHouse is here to answer.

Until now the mirror was write-only: five thousand events sat in it and nothing
in the app ever asked it anything. All the cost of writing, none of the use.

What belongs here is what the row store is bad at. SQLite answers "this take,
this day" in a point lookup and is the right shape for it. These are the other
kind: every day of a production at once, grouped, counted, ordered -- questions
whose answer is a scan, and whose cost in the day-scoped in-memory path would
be a full pass per question per request.

# Reading the payload

`payload_json` is read with JSON functions rather than materialized columns.
Materialized columns would be faster and are the right answer at real volume,
but they only populate for rows inserted after the ALTER, so the existing five
thousand would come back empty until a MATERIALIZE mutation had run over them.
A query that is fast and silently wrong about history is the worse trade.

# Never required

Same contract as the writer beside it. No ClickHouse means every function here
returns None, and the caller says so rather than drawing an empty chart -- a
panel that cannot fill looks exactly like a production with nothing in it,
which `failure-modes.md` calls absence rendered as presence.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from backend.app.spine.clickhouse import database


def _rows(client: Any, sql: str, parameters: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """
    Runs one query and returns its rows as dicts, or None when it could not.

    None and [] mean different things and are kept apart: None is "no
    analytical spine", [] is "asked, and the answer is nothing".
    """
    if client is None:
        return None
    try:
        # The database name is substituted here rather than passed as a query
        # parameter. ClickHouse spells parameters `{name:Type}` and a table
        # name cannot be one of those -- and `{db}` left in the SQL would be
        # read as a parameter nobody set. `database()` validates the name.
        result = client.query(sql.replace("{db}", database()), parameters=parameters)
        return [dict(zip(result.column_names, row)) for row in result.result_rows]
    except Exception as e:
        logger.warning("Analytics query failed: %s", e)
        return None


def production_shape(client: Any, production_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    How much each department has said, on which axis.

    The three-axis claim, counted. A production where one axis is empty is a
    production where a whole department's paperwork is not arriving, and that
    is worth seeing at a glance rather than discovering downstream.
    """
    return _rows(client, """
        SELECT axis, department, count() AS events,
               uniqExact(shoot_day) AS days
        FROM {db}.production_events
        WHERE production_id = {production_id:String}
        GROUP BY axis, department
        ORDER BY axis, events DESC
    """, {"production_id": production_id})


def department_arrivals(client: Any, production_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    When each department's paperwork actually arrived, per shoot day.

    REQ-10 asks for this as a sync matrix. Reported as arrival times rather
    than as a lag from wrap: the report states a wrap time of day and this
    records when a file was ingested, and subtracting one from the other would
    invent a number neither of them supports.
    """
    return _rows(client, """
        SELECT shoot_day, department,
               count() AS events,
               min(created_at) AS first_filed,
               max(created_at) AS last_filed
        FROM {db}.production_events
        WHERE production_id = {production_id:String}
        GROUP BY shoot_day, department
        ORDER BY shoot_day, first_filed
    """, {"production_id": production_id})


def roll_disagreements(client: Any, production_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Takes where two departments put the same camera on different rolls.

    Grouped by camera, and that is the whole difficulty. A take shot on three
    cameras carries three rolls and agrees with itself perfectly; a query that
    only asks "more than one roll for this take" reports every multi-camera
    setup on the show as a conflict. The disagreement is two witnesses
    describing *one* camera differently.

    Requires more than one department, because one department listing its own
    three cameras is not a disagreement either.
    """
    return _rows(client, """
        SELECT shoot_day, slate, take_id, camera, rolls, witnesses
        FROM (
            SELECT shoot_day,
                   JSONExtractString(payload_json, 'slate')       AS slate,
                   JSONExtractString(payload_json, 'take_id')     AS take_id,
                   -- The camera letter a roll starts with: A120 is camera A.
                   substring(JSONExtractString(payload_json, 'camera_roll'), 1, 1) AS camera,
                   arraySort(groupUniqArray(JSONExtractString(payload_json, 'camera_roll'))) AS rolls,
                   arraySort(groupUniqArray(department)) AS witnesses
            FROM {db}.production_events
            WHERE production_id = {production_id:String}
              AND entity_type = 'take'
              AND JSONExtractString(payload_json, 'camera_roll') != ''
            GROUP BY shoot_day, slate, take_id, camera
        )
        WHERE length(rolls) > 1 AND length(witnesses) > 1
        ORDER BY shoot_day, slate, take_id, camera
    """, {"production_id": production_id})


def scene_coverage(client: Any, production_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    What each scene cost, across every day it was shot on.

    A scene is rarely finished in one go, so the day-scoped views can only ever
    show part of one. This is the whole scene: how many days, how many slates,
    how many takes, and which departments have filed for it.
    """
    return _rows(client, """
        SELECT scene,
               uniqExact(shoot_day) AS days,
               arraySort(groupUniqArray(shoot_day)) AS shoot_days,
               uniqExact(slate) AS slates,
               count() AS takes,
               arraySort(groupUniqArray(department)) AS departments
        FROM (
            SELECT shoot_day, department,
                   JSONExtractString(payload_json, 'slate') AS slate,
                   -- The scene is the half of the slate before the shot.
                   if(position(slate, '/') > 0, substring(slate, 1, position(slate, '/') - 1), slate) AS scene
            FROM {db}.production_events
            WHERE production_id = {production_id:String}
              AND entity_type = 'take'
              AND JSONExtractString(payload_json, 'slate') != ''
        )
        -- A scene number starts with a digit. The guard is query hygiene and
        -- it is also a containment: a camera CSV row that is not a take at all
        -- can leave a contact line in the slate field, and an analytics result
        -- is the last place that should surface.
        WHERE scene != '' AND match(scene, '^[0-9]')
        GROUP BY scene
        ORDER BY takes DESC, scene
    """, {"production_id": production_id})


def editorial_state(client: Any, production_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Where every scene and shot has got to, derived from the trail alone.

    argMax over an append-only log is the idiom this data model was asking
    for: the current answer is whichever event is latest, and asking that way
    needs no merge to have happened and no FINAL to force one.
    """
    return _rows(client, """
        SELECT status, count() AS targets
        FROM (
            SELECT target_type, target_id,
                   argMax(status, created_at) AS status,
                   argMax(action, created_at) AS action
            FROM {db}.editorial_tag_events
            WHERE production_id = {production_id:String}
            GROUP BY target_type, target_id
        )
        -- A cleared tag is not a state; it is the absence of one.
        WHERE action != 'cleared' AND status != ''
        GROUP BY status
        ORDER BY targets DESC
    """, {"production_id": production_id})


def requirement_ageing(client: Any, production_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    How long work sits before somebody deals with it, by category.

    The question the requirement trail was mirrored here for: which department
    is the bottleneck, and how long does a blocker stay parked. Read from the
    events rather than the current rows, so a requirement that was blocked for
    a week and then resolved still says so.
    """
    return _rows(client, """
        SELECT category,
               count() AS requirements,
               round(avg(hours_open), 1) AS avg_hours_open,
               round(max(hours_open), 1) AS longest_hours_open,
               countIf(ever_blocked) AS ever_blocked
        FROM (
            SELECT requirement_id,
                   argMax(priority, created_at) AS priority,
                   -- The category is not on the event, so it comes from the
                   -- action trail's own grouping key: any row will do.
                   any(action) AS first_action,
                   maxIf(created_at, action IN ('resolved')) AS resolved_at,
                   min(created_at) AS raised_at,
                   maxIf(1, status = 'blocked') > 0 AS ever_blocked,
                   dateDiff('hour', min(created_at),
                            if(maxIf(created_at, action = 'resolved') > toDateTime64(0, 3),
                               maxIf(created_at, action = 'resolved'), now64(3))) AS hours_open,
                   'general' AS category
            FROM {db}.requirement_events
            WHERE production_id = {production_id:String}
            GROUP BY requirement_id
        )
        GROUP BY category
        ORDER BY requirements DESC
    """, {"production_id": production_id})


def time_to_acknowledge(client: Any, production_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    How long a department takes to take something on, once it is raised.

    REQ-10 asks for a department sync matrix. It was a gauge that could never
    fill, because the only baseline available was a wrap time with no date on
    it. This answers the same question from a fact the product now records:
    the gap between a thing existing and somebody saying they have it.

    About the handover, not the person. Grouped by department because that is
    where a handover stalls; the actor is a role token either way.
    """
    return _rows(client, """
        SELECT department,
               target_type,
               count() AS acknowledged,
               round(avg(seconds_since_target_created) / 60, 1) AS avg_minutes,
               round(quantile(0.5)(seconds_since_target_created) / 60, 1) AS median_minutes,
               round(max(seconds_since_target_created) / 60, 1) AS slowest_minutes
        FROM {db}.user_activity
        WHERE production_id = {production_id:String}
          AND action = 'acknowledged'
          AND seconds_since_target_created IS NOT NULL
        GROUP BY department, target_type
        ORDER BY avg_minutes DESC
    """, {"production_id": production_id})


def unacknowledged_requirements(client: Any, production_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Requirements nobody has taken on, and whether anybody has even looked.

    Two different silences, kept apart. Opened and not acknowledged is somebody
    deciding not to; never opened at all is a blocker that has not reached
    anyone, which is the failure handoffs.md is about.
    """
    return _rows(client, """
        SELECT r.requirement_id AS requirement_id,
               argMax(r.status, r.created_at) AS status,
               argMax(r.priority, r.created_at) AS priority,
               argMax(r.assigned_to, r.created_at) AS assigned_to,
               min(r.created_at) AS raised_at,
               countIf(a.action = 'viewed') AS views,
               countIf(a.action = 'acknowledged') AS acknowledgements
        FROM {db}.requirement_events AS r
        LEFT JOIN {db}.user_activity AS a
          ON a.target_id = r.requirement_id
         AND a.target_type = 'requirement'
         AND a.production_id = r.production_id
        WHERE r.production_id = {production_id:String}
        GROUP BY r.requirement_id
        HAVING acknowledgements = 0
        ORDER BY raised_at
    """, {"production_id": production_id})


def unreviewed_days(client: Any, production_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Days with material on the spine that nobody has opened.

    A day nobody has looked at is not a day with nothing wrong -- it is a day
    with no witness, and those must not render the same way. The same
    distinction the offload gate makes, one level up.
    """
    return _rows(client, """
        SELECT e.shoot_day AS shoot_day,
               count(DISTINCT e.event_id) AS spine_events,
               countIf(a.action = 'viewed') AS views,
               countIf(a.action = 'acknowledged') AS acknowledgements,
               groupUniqArray(a.actor) AS seen_by
        FROM {db}.production_events AS e
        LEFT JOIN {db}.user_activity AS a
          ON a.shoot_day = e.shoot_day
         AND a.production_id = e.production_id
        WHERE e.production_id = {production_id:String}
        GROUP BY e.shoot_day
        ORDER BY views ASC, shoot_day
    """, {"production_id": production_id})


def department_attention(client: Any, production_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Which departments are looking, and at what.

    The honest version of "engagement": it counts entities reached, not
    sessions or pageviews, because the question is coverage of the work rather
    than time spent in the app.
    """
    return _rows(client, """
        SELECT department,
               actor,
               countIf(action = 'viewed') AS views,
               countIf(action = 'acknowledged') AS acknowledgements,
               uniqExact(target_id) AS distinct_targets,
               max(created_at) AS last_seen
        FROM {db}.user_activity
        WHERE production_id = {production_id:String}
        GROUP BY department, actor
        ORDER BY acknowledgements DESC, views DESC
    """, {"production_id": production_id})


def table_sizes(client: Any) -> Optional[List[Dict[str, Any]]]:
    """
    How much is in the analytical spine. Shown so the numbers above have a
    scale attached rather than being read as the whole of the production.
    """
    return _rows(client, """
        SELECT table, sum(rows) AS rows
        FROM system.parts
        WHERE database = 'cinespine' AND active
        GROUP BY table
        ORDER BY table
    """, {})
