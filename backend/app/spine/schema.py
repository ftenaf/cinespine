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
    is_starred UInt8,
    is_pickup UInt8,
    is_vfx UInt8,
    last_updated DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(last_updated)
ORDER BY (production_id, shoot_day, slate, take_id, camera_roll);

-- 3. Audit Discrepancies Table
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
