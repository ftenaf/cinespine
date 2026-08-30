"""
Ingestion Dispatcher Worker.

Subscribes to the raw document topics on the in-process event bus, runs
auto-classification and the deterministic parsers, and emits verified events
onto the spine topic.
"""
import logging
from typing import Dict, Any
from backend.app.streaming.models import EventEnvelope, DocumentType
from backend.app.streaming.bus import EventBus, EventHandlerError
from backend.app.parsers.sound_ale import parse_sound_ale
from backend.app.parsers.camera_csv import parse_camera_csv
from backend.app.parsers.silverstack_xml import parse_silverstack_xml
from backend.app.parsers.pdf_parsers import (
    extract_text_from_pdf,
    parse_zoelog_camera_text,
    parse_scripte_tclog_text,
    parse_scripte_detailed_editor_log_text,
    parse_silverstack_volume_text,
    parse_silverstack_pdf_text,
)
from backend.app.parsers.dpr import parse_daily_production_report
from backend.app.parsers.base import ParsedCameraRecord, ParserFailureError
from backend.app.normalizers.slates import normalize_slate
from backend.app.normalizers.takes import normalize_take

logger = logging.getLogger(__name__)


def _looks_like_pdf(text: str) -> bool:
    """
    Whether this arrived as PDF bytes decoded into a string.

    The JSON upload route carries raw_content as text, so a DPR posted that
    way needs its text layer extracting before any field is readable.
    """
    return bool(text) and text.lstrip().startswith("%PDF")


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
        # Office had no subscriber at all. Its documents were classified,
        # published to a topic nobody listened on, and produced nothing --
        # while the upload reported INGESTED. The confident nothing, on the
        # axis the whole architecture is named for.
        self.bus.subscribe("production.raw.office", self.handle_office_drop)

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
        except EventHandlerError:
            # The spine write failed, not the document. A DLQ entry would say
            # this paperwork was rejected, which is a different thing entirely
            # and would send someone to check a report that was fine. Let it
            # reach the caller, which has to answer for the ingest.
            raise
        except Exception as e:
            self._emit_dlq(envelope, "SYSTEM_ERROR", str(e))

    def handle_camera_drop(self, envelope: EventEnvelope) -> None:
        try:
            fn = (envelope.filename or "").upper()
            content = envelope.raw_content

            # A handwritten report has already been read, as a picture, during
            # upload: its rows are ink and no text parser can see them. Where
            # those rows exist they are the document, so parsing the text layer
            # would add nothing and find nothing.
            handwritten = envelope.metadata.get("handwritten_rows") or []
            if handwritten:
                records = [ParsedCameraRecord(**row) for row in handwritten]
            elif fn.endswith(".PDF") or "ZOELOG" in content.upper():
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
                        "raw_payload": rec.raw_payload,
                    },
                    "metadata": envelope.metadata,
                    "timestamp": envelope.timestamp,
                }
                self.bus.publish("production.events.spine", spine_event)
        except ParserFailureError as e:
            self._emit_dlq(envelope, "PARSER_FAILURE", str(e))
        except EventHandlerError:
            # The spine write failed, not the document. A DLQ entry would say
            # this paperwork was rejected, which is a different thing entirely
            # and would send someone to check a report that was fine. Let it
            # reach the caller, which has to answer for the ingest.
            raise
        except Exception as e:
            self._emit_dlq(envelope, "SYSTEM_ERROR", str(e))

    def handle_script_drop(self, envelope: EventEnvelope) -> None:
        try:
            fn = (envelope.filename or "").upper()
            content = envelope.raw_content

            # A timecode log is laid out around its timecode columns. Every
            # other script report -- the editor's log, the detailed editor's
            # log, the facing pages -- is read by the same state machine, which
            # handles both the flat one-row-per-line layout and the multi-line
            # one the PDF text layer actually produces.
            if "TCLOG" in fn or "TIMECODE LOG" in content.upper():
                records = parse_scripte_tclog_text(content)
            else:
                records = parse_scripte_detailed_editor_log_text(content)

            # A lined page's circles are ink drawn on the printed script. The
            # asterisk in its text layer is the export's typed marker, and the
            # absence of one is not evidence that nobody drew a circle -- the
            # drawing simply does not reach us. So this document may report that
            # a take was circled and may not report that it was not: None means
            # "no claim", which the reconciliation engine already skips.
            # Reading silence as a denial produced conflicts against the
            # timecode log on every take the export did not mark.
            can_deny_circle = envelope.doc_type != DocumentType.SCRIPT_LINED

            # A facing page files a shot under every scene it plays in, so one
            # page carries takes from several shoot days. Filing them all under
            # the day the page was uploaded puts a Day 11 take among Day 31
            # witnesses, where it can only ever disagree with them.
            elsewhere = [r for r in records if r.shoot_day and r.shoot_day != envelope.shoot_day]
            if elsewhere:
                logger.info(
                    "%s: %d of %d rows belong to shoot day(s) %s, not %s",
                    envelope.filename, len(elsewhere), len(records),
                    ", ".join(sorted({r.shoot_day for r in elsewhere})), envelope.shoot_day,
                )

            for rec in records:
                spine_event: Dict[str, Any] = {
                    "event_id": envelope.event_id,
                    "production_id": envelope.production_id,
                    "shoot_day": rec.shoot_day or envelope.shoot_day,
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
                        "is_starred": True if rec.is_starred else (False if can_deny_circle else None),
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
        except EventHandlerError:
            # The spine write failed, not the document. A DLQ entry would say
            # this paperwork was rejected, which is a different thing entirely
            # and would send someone to check a report that was fine. Let it
            # reach the caller, which has to answer for the ingest.
            raise
        except Exception as e:
            self._emit_dlq(envelope, "SYSTEM_ERROR", str(e))

    def handle_office_drop(self, envelope: EventEnvelope) -> None:
        """
        Reads Office's daily production report onto the intent axis.

        Two axes come off one page, and keeping them apart is the point.
        `Scenes Scheduled` is intent: what Office planned. Everything else the
        report says about the day -- complete, part complete, not shot, shot
        without being scheduled -- is Office's *belief* about what happened,
        and Office does not observe what happened. Writing those as existence
        would make the plan authoritative for reality, which is exactly the
        boundary dept-office.md calls load-bearing.

        Both negatives are stated on the page and have always died there.
        Emitting them is what lets anything downstream ask.
        """
        try:
            text = envelope.raw_content
            if envelope.doc_type == DocumentType.DPR and _looks_like_pdf(text):
                text = extract_text_from_pdf(text.encode("latin-1", errors="ignore"))

            report = parse_daily_production_report(text)

            def emit(payload: Dict[str, Any], axis: str, entity_type: str) -> None:
                self.bus.publish("production.events.spine", {
                    "event_id": envelope.event_id,
                    "production_id": envelope.production_id,
                    "shoot_day": envelope.shoot_day,
                    "axis": axis,
                    "department": envelope.department.value,
                    "doc_type": envelope.doc_type.value,
                    "entity_type": entity_type,
                    "payload": payload,
                    "metadata": envelope.metadata,
                    "timestamp": envelope.timestamp,
                })

            # 1. Intent. What Office planned for the day.
            for ref in report.scenes_scheduled:
                emit({"scene": ref.scene, "raw": ref.raw, "state": "scheduled"},
                     "intent", "scene")

            # 2. Office's belief about the same day. A separate axis from the
            #    plan, and separate from what Set and the disk say.
            office_states = (
                ("complete", report.scenes_complete),
                ("part_complete", report.scenes_part_complete),
                ("scheduled_not_shot", report.scenes_scheduled_not_shot),
                ("shot_not_scheduled", report.scenes_shot_not_scheduled),
            )
            for state, refs in office_states:
                for ref in refs:
                    emit({"scene": ref.scene, "raw": ref.raw, "office_state": state},
                         "belief", "scene")

            # 3. The day itself: wrap and call times, set-ups, pages, and the
            #    card and slate ranges. The wrap time is the baseline a
            #    department's handover lag is measured from, and a slate
            #    outside every range was never scheduled.
            emit(report.as_payload(), "intent", "shoot_day")

        except ParserFailureError as e:
            self._emit_dlq(envelope, "PARSER_FAILURE", str(e))
        except EventHandlerError:
            # The spine write failed, not the document. A DLQ entry would say
            # this paperwork was rejected, which is a different thing entirely
            # and would send someone to check a report that was fine. Let it
            # reach the caller, which has to answer for the ingest.
            raise
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
        except EventHandlerError:
            # The spine write failed, not the document. A DLQ entry would say
            # this paperwork was rejected, which is a different thing entirely
            # and would send someone to check a report that was fine. Let it
            # reach the caller, which has to answer for the ingest.
            raise
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
