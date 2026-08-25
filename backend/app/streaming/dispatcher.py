"""
Ingestion Dispatcher Worker.

Consumes raw document events from Kafka, runs auto-classification, parsers, and emits verified events onto the spine topic.
"""
from typing import Dict, Any
from backend.app.streaming.models import EventEnvelope, DocumentType
from backend.app.streaming.bus import EventBus
from backend.app.parsers.sound_ale import parse_sound_ale
from backend.app.parsers.camera_csv import parse_camera_csv
from backend.app.parsers.silverstack_xml import parse_silverstack_xml
from backend.app.parsers.pdf_parsers import (
    extract_text_from_pdf,
    parse_zoelog_camera_text,
    parse_editors_log_text,
    parse_scripte_tclog_text,
    parse_scripte_detailed_editor_log_text,
    parse_silverstack_volume_text,
    parse_silverstack_pdf_text,
)
from backend.app.parsers.base import ParserFailureError
from backend.app.normalizers.slates import normalize_slate
from backend.app.normalizers.takes import normalize_take


class IngestionDispatcher:
    def __init__(self, bus: EventBus):
        self.bus = bus
        self._wire_subscribers()

    def _wire_subscribers(self) -> None:
        self.bus.subscribe("production.raw.sound", self.handle_sound_drop)
        self.bus.subscribe("production.raw.camera", self.handle_camera_drop)
        self.bus.subscribe("production.raw.dit", self.handle_silverstack_drop)
        self.bus.subscribe("production.raw.silverstack", self.handle_silverstack_drop)
        self.bus.subscribe("production.raw.script", self.handle_script_drop)

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
                        "camera_roll": rec.camera_roll,
                        "timecode_in": rec.timecode_in,
                        "timecode_out": rec.timecode_out,
                        "file_name": rec.file_name,
                        "duration": rec.duration,
                        "sample_rate": rec.sample_rate,
                        "bit_depth": rec.bit_depth,
                        "tracks": rec.tracks,
                        "is_starred": rec.is_starred,
                        "is_pickup": rec.is_pickup,
                        "is_false_start": rec.is_false_start,
                        "is_wild_track": rec.is_wild_track,
                        "is_vfx": rec.is_vfx,
                        "note": rec.note,
                        "raw_payload": rec.raw_payload,
                    },
                    "metadata": envelope.metadata,
                    "timestamp": envelope.timestamp,
                }
                self.bus.publish("production.events.spine", spine_event)
        except ParserFailureError as e:
            self._emit_dlq(envelope, "PARSER_FAILURE", str(e))
        except Exception as e:
            self._emit_dlq(envelope, "SYSTEM_ERROR", str(e))

    def handle_camera_drop(self, envelope: EventEnvelope) -> None:
        try:
            fn = (envelope.filename or "").upper()
            content = envelope.raw_content

            # Check if PDF format
            if fn.endswith(".PDF") or "ZOELOG" in content.upper():
                records = parse_zoelog_camera_text(content)
            else:
                records = parse_camera_csv(content)

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
                    "metadata": envelope.metadata,
                    "timestamp": envelope.timestamp,
                }
                self.bus.publish("production.events.spine", spine_event)
        except ParserFailureError as e:
            self._emit_dlq(envelope, "PARSER_FAILURE", str(e))
        except Exception as e:
            self._emit_dlq(envelope, "SYSTEM_ERROR", str(e))

    def handle_script_drop(self, envelope: EventEnvelope) -> None:
        try:
            fn = (envelope.filename or "").upper()
            content = envelope.raw_content

            # Route to Scripte TCLog vs Detailed Editor Log vs standard Editor Log
            if "TCLOG" in fn or "TIMECODE LOG" in content.upper():
                records = parse_scripte_tclog_text(content)
            elif "DETAILED" in fn or "DETAILED EDITOR'S LOG" in content.upper() or "EDITOR" in fn or "EDITOR'S LOG" in content.upper() or "DAILY EDITOR'S LOG" in content.upper():
                try:
                    records = parse_scripte_detailed_editor_log_text(content)
                except Exception:
                    records = parse_editors_log_text(content)
            else:
                try:
                    records = parse_scripte_detailed_editor_log_text(content)
                except Exception:
                    records = parse_editors_log_text(content)

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
                        "camera_roll": rec.camera_roll,
                        "recording_date": rec.recording_date,
                        "timecode_in": rec.timecode_in,
                        "timecode_out": rec.timecode_out,
                        "is_starred": rec.is_starred,
                        "is_pickup": rec.is_pickup,
                        "is_wild_track": rec.is_wild_track,
                        "is_vfx": rec.is_vfx,
                        "is_mos": rec.is_mos,
                        "note": rec.note,
                    },
                    "metadata": envelope.metadata,
                    "timestamp": envelope.timestamp,
                }
                self.bus.publish("production.events.spine", spine_event)
        except ParserFailureError as e:
            self._emit_dlq(envelope, "PARSER_FAILURE", str(e))
        except Exception as e:
            self._emit_dlq(envelope, "SYSTEM_ERROR", str(e))

    def handle_silverstack_drop(self, envelope: EventEnvelope) -> None:
        try:
            fn = (envelope.filename or "").upper()
            content = envelope.raw_content

            thumbnails_map = envelope.metadata.get("thumbnails")

            if fn.endswith(".PDF") or "POMFORT" in content.upper() or "SILVERSTACK" in content.upper() or "VOLUME REPORT" in content.upper() or "SHOOTING DAY" in content.upper():
                records = parse_silverstack_pdf_text(content, thumbnails_map=thumbnails_map)
            else:
                records = parse_silverstack_xml(content)

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
                        "reel_tape": clip.reel_tape,
                        "scene": clip.scene,
                        "shot": clip.shot,
                        "take_id": clip.take_id,
                        "codec": clip.codec,
                        "recording_date": clip.recording_date,
                        "camera": clip.camera,
                        "fps": clip.fps,
                        "iso": clip.iso,
                        "tstop": clip.tstop,
                        "is_vfx": clip.is_vfx,
                        "card_type": clip.card_type,
                        "thumbnail_b64": clip.thumbnail_b64,
                    },
                    "metadata": envelope.metadata,
                    "timestamp": envelope.timestamp,
                }
                self.bus.publish("production.events.spine", spine_event)

                # If the Silverstack report contains Scene/Take (e.g. Thumbnail or Volume report), emit take existence record
                if clip.scene and clip.take_id:
                    raw_slate = f"{clip.scene}/{clip.shot}" if clip.shot else clip.scene
                    norm_slate = normalize_slate(raw_slate) or raw_slate
                    scene_val = norm_slate.split("/")[0] if "/" in norm_slate else clip.scene
                    take_event: Dict[str, Any] = {
                        "event_id": envelope.event_id,
                        "production_id": envelope.production_id,
                        "shoot_day": envelope.shoot_day,
                        "axis": envelope.axis.value,
                        "department": envelope.department.value,
                        "doc_type": envelope.doc_type.value,
                        "entity_type": "take",
                        "payload": {
                            "scene": scene_val,
                            "slate": norm_slate,
                            "take_id": clip.take_id,
                            "camera_roll": clip.camera_roll,
                            "sound_roll": clip.reel_tape if clip.card_type == "sound" else None,
                            "clip_name": clip.file_name,
                            "codec": clip.codec,
                            "recording_date": clip.recording_date,
                            "reel_tape": clip.reel_tape,
                            "camera": clip.camera,
                            "fps": clip.fps,
                            "iso": clip.iso,
                            "tstop": clip.tstop,
                            "is_vfx": clip.is_vfx,
                            "is_pickup": clip.is_pickup,
                            "is_wild_track": clip.is_wild_track,
                            "card_type": clip.card_type,
                            "thumbnail_b64": clip.thumbnail_b64,
                        },
                        "metadata": envelope.metadata,
                        "timestamp": envelope.timestamp,
                    }
                    self.bus.publish("production.events.spine", take_event)
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
