"""
ClickHouse Append-Only Event Spine Schema & DDL.
"""

CLICKHOUSE_SCHEMA_DDL = """
CREATE DATABASE IF NOT EXISTS cinespine;

-- 1. Immutable Append-Only Event Spine
CREATE TABLE IF NOT EXISTS cinespine.production_events (
    event_id UUID,
    production_id LowCardinality(String),
    shoot_day LowCardinality(String),
    axis LowCardinality(String),
    department LowCardinality(String),
    doc_type LowCardinality(String),
    entity_type LowCardinality(String),
    payload_json String,
    metadata_json String,
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (production_id, shoot_day, created_at, event_id);

-- 2. Materialized View: Takes Index
CREATE TABLE IF NOT EXISTS cinespine.takes_meta (
    production_id LowCardinality(String),
    shoot_day LowCardinality(String),
    scene_id String,
    slate String,
    take_id String,
    camera_roll LowCardinality(String),
    sound_roll LowCardinality(String),
    fps Float32,
    timecode_in String,
    timecode_out String,
    -- Nullable because a lined page may assert that a take was circled and may
    -- not assert that it was not: the circle is ink on paper and its absence
    -- from the export is silence, not denial. Writing that silence as 0 would
    -- make the analytical copy state something no witness said.
    is_starred Nullable(UInt8),
    is_pickup UInt8,
    is_vfx UInt8,
    last_updated DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(last_updated)
ORDER BY (production_id, shoot_day, slate, take_id, camera_roll);

-- 3. Editorial Tag History
--
-- The current tag lives in SQLite: it is a handful of mutable rows read one at
-- a time, which ClickHouse is the wrong shape for. What is mirrored here is the
-- trail, where the question is analytical -- what moved this week, who is
-- clearing what -- and the table only ever grows.
CREATE TABLE IF NOT EXISTS cinespine.editorial_tag_events (
    event_id String,
    production_id LowCardinality(String),
    target_type LowCardinality(String),
    target_id String,
    action LowCardinality(String),
    status LowCardinality(String),
    needs_json String,
    descriptors_json String,
    note String,
    actor LowCardinality(String),
    -- Millisecond resolution, and written by the caller rather than defaulted.
    -- At second resolution two changes made in the same second came back
    -- unorderable, so the trail's order -- the thing it exists for -- did not
    -- survive the copy.
    created_at DateTime64(3) DEFAULT now64(3)
) ENGINE = MergeTree()
ORDER BY (production_id, target_type, target_id, created_at);

-- 4. Requirement History
--
-- Same split as the tag trail above, for the same reason. What is owed right
-- now lives in SQLite: a handful of mutable rows, read one at a time and as a
-- list per production, which is not a shape this engine is good at. What is
-- mirrored here is the trail, where the questions are analytical -- how long
-- does a blocker sit, which department is the bottleneck, what got re-opened
-- -- and the table only ever grows.
CREATE TABLE IF NOT EXISTS cinespine.requirement_events (
    event_id       String,
    requirement_id String,
    production_id  String,
    action         String,
    status         String,
    priority       String,
    assigned_to    String,
    changes_json   String,
    note           String,
    actor          String,
    -- Millisecond resolution and written by the caller, matching the tag
    -- trail: at second resolution two changes made in the same second come
    -- back unorderable, and the order is the thing a trail exists for.
    created_at     DateTime64(3)
) ENGINE = MergeTree()
ORDER BY (production_id, requirement_id, created_at);

-- 5. Audit Discrepancies Table
CREATE TABLE IF NOT EXISTS cinespine.audit_discrepancies (
    discrepancy_id UUID,
    production_id LowCardinality(String),
    shoot_day LowCardinality(String),
    entity_type LowCardinality(String),
    entity_id String,
    discrepancy_type LowCardinality(String),
    severity LowCardinality(String),
    description String,
    witnesses_json String,
    is_resolved UInt8 DEFAULT 0,
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY (production_id, shoot_day, discrepancy_type, entity_id);
"""
