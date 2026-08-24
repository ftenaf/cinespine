"""
Ingestion Dispatcher Worker.

Consumes raw document events from Kafka, runs parsers, and emits verified events onto the spine topic.
"""
from typing import Dict, Any
from backend.app.streaming.models import EventEnvelope, DocumentType
from backend.app.streaming.bus import EventBus
from backend.app.parsers.sound_ale import parse_sound_ale
from backend.app.parsers.camera_csv import parse_camera_csv
from backend.app.parsers.silverstack_xml import parse_silverstack_xml
from backend.app.parsers.base import ParserFailureError


class IngestionDispatcher:
    def __init__(self, bus: EventBus):
        self.bus = bus
        self._wire_subscribers()

    def _wire_subscribers(self) -> None:
        self.bus.subscribe("production.raw.sound", self.handle_sound_drop)
        self.bus.subscribe("production.raw.camera", self.handle_camera_drop)
        self.bus.subscribe("production.raw.dit", self.handle_silverstack_drop)
        self.bus.subscribe("production.raw.silverstack", self.handle_silverstack_drop)

    def handle_sound_drop(self, envelope: EventEnvelope) -> None:
        try:
            records = parse_sound_ale(envelope.raw_content)
            for rec in records:
                spine_event: Dict[str, Any] = {
                    "event_id": envelope.event_id,
                    "production_id": envelope.production_id,
                    "shoot_day": envelope.shoot_day,
                    "axis": envelope.axis.value,
                    "department": envelope.department.value,
                    "doc_type": envelope.doc_type.value,
                    "entity_type": "take",
                    "payload": {
                        "scene": rec.scene,
                        "slate": rec.slate,
                        "take_id": rec.take_id,
                        "sound_roll": rec.sound_roll,
                        "timecode_in": rec.timecode_in,
                        "timecode_out": rec.timecode_out,
                        "tracks": rec.tracks,
                        "is_starred": rec.is_starred,
                        "is_pickup": rec.is_pickup,
                        "is_false_start": rec.is_false_start,
                        "is_wild_track": rec.is_wild_track,
                        "note": rec.note,
                    },
                    "timestamp": envelope.timestamp,
                }
                self.bus.publish("production.events.spine", spine_event)
        except ParserFailureError as e:
            self._emit_dlq(envelope, "PARSER_FAILURE", str(e))
        except Exception as e:
            self._emit_dlq(envelope, "SYSTEM_ERROR", str(e))

    def handle_camera_drop(self, envelope: EventEnvelope) -> None:
        try:
            records = parse_camera_csv(envelope.raw_content)
            for rec in records:
                spine_event: Dict[str, Any] = {
                    "event_id": envelope.event_id,
                    "production_id": envelope.production_id,
                    "shoot_day": envelope.shoot_day,
                    "axis": envelope.axis.value,
                    "department": envelope.department.value,
                    "doc_type": envelope.doc_type.value,
                    "entity_type": "take",
                    "payload": {
                        "slate": rec.slate,
                        "take_id": rec.take_id,
                        "camera_roll": rec.camera_roll,
                        "clip_name": rec.clip_name,
                        "timecode_in": rec.timecode_in,
                        "timecode_out": rec.timecode_out,
                        "fps": rec.fps,
                        "lens": rec.lens,
                        "iso": rec.iso,
                        "is_starred": rec.is_starred,
                        "is_pickup": rec.is_pickup,
                        "is_vfx": rec.is_vfx,
                        "note": rec.note,
                    },
                    "timestamp": envelope.timestamp,
                }
                self.bus.publish("production.events.spine", spine_event)
        except ParserFailureError as e:
            self._emit_dlq(envelope, "PARSER_FAILURE", str(e))
        except Exception as e:
            self._emit_dlq(envelope, "SYSTEM_ERROR", str(e))

    def handle_silverstack_drop(self, envelope: EventEnvelope) -> None:
        try:
            records = parse_silverstack_xml(envelope.raw_content)
            for clip in records:
                spine_event: Dict[str, Any] = {
                    "event_id": envelope.event_id,
                    "production_id": envelope.production_id,
                    "shoot_day": envelope.shoot_day,
                    "axis": envelope.axis.value,
                    "department": envelope.department.value,
                    "doc_type": envelope.doc_type.value,
                    "entity_type": "media_file",
                    "payload": {
                        "file_name": clip.file_name,
                        "camera_roll": clip.camera_roll,
                        "file_size_bytes": clip.file_size_bytes,
                        "checksum": clip.checksum,
                        "checksum_type": clip.checksum_type,
                        "volume_name": clip.volume_name,
                        "duration_frames": clip.duration_frames,
                    },
                    "timestamp": envelope.timestamp,
                }
                self.bus.publish("production.events.spine", spine_event)
        except ParserFailureError as e:
            self._emit_dlq(envelope, "PARSER_FAILURE", str(e))
        except Exception as e:
            self._emit_dlq(envelope, "SYSTEM_ERROR", str(e))

    def _emit_dlq(self, envelope: EventEnvelope, error_type: str, reason: str) -> None:
        dlq_event: Dict[str, Any] = {
            "error_type": error_type,
            "reason": reason,
            "production_id": envelope.production_id,
            "shoot_day": envelope.shoot_day,
            "doc_type": envelope.doc_type.value,
            "original_event_id": envelope.event_id,
            "timestamp": envelope.timestamp,
        }
        self.bus.publish("production.events.dlq", dlq_event)
