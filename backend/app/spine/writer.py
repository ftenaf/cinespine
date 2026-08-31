"""
ClickHouse Append-Only Event Writer, Multi-Production & Document Store.
"""
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from backend.app.spine import character_store, activity_store
from backend.app.spine import production_store
from backend.app.spine import crew_store
from backend.app.spine import requirement_store
from backend.app.spine import notification_store
from backend.app.spine import event_store
from backend.app.spine import breakdown_store
from backend.app.spine import tag_store
from backend.app.spine import clickhouse
from backend.app.streaming.models import DEFAULT_TEAM_USERS

logger = logging.getLogger(__name__)


def _db() -> str:
    """
    The database the mirror writes into.

    Resolved per call rather than captured at import, so a test can point the
    suite somewhere else without the module having to be reloaded.
    """
    from backend.app.spine.clickhouse import database
    return database()

# Events are buffered and sent together. Large enough that an ordinary document
# goes in one insert, small enough that a runaway ingestion cannot grow memory
# without bound before a flush.
EVENT_BATCH_SIZE = 500

# How long the mirror stays shut after a failed insert.
#
# A ClickHouse that is absent at startup costs nothing: connect returns None and
# nothing is attempted. One that dies after connecting is the expensive case --
# the driver retries with backoff on every call, so an ingestion went from 0.9s
# to 16.7s and a single tag save from instant to 8.2s, precisely when the
# infrastructure is already having a bad day. Long enough that a sustained
# outage costs one attempt every half minute, short enough that a restart is
# picked up without anybody intervening.
MIRROR_COOLDOWN_SECONDS = 30


def _clickhouse_datetime(iso: Optional[str]) -> datetime:
    """
    Parses an ISO timestamp into an aware UTC datetime for the driver.

    Aware, not naive: a naive datetime is read as local time and converted, so
    on a machine an hour off UTC every mirrored row landed an hour earlier than
    it happened. The order was still right, which is exactly what makes that
    kind of mistake survive a review.

    Falls back to now rather than raising -- a mirrored row with an approximate
    time is worth more than a lost one.
    """
    if iso:
        try:
            parsed = datetime.fromisoformat(iso)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)

# Registered productions registry
DEFAULT_PRODUCTIONS = {
    "DEMO_PRODUCTION": {
        "production_id": "DEMO_PRODUCTION",
        "name": "Demo Production",
        "director": "Director",
        "status": "In Production",
        "description": "Sample feature production used for demos and tests",
    },
    "PROD_02": {
        "production_id": "PROD_02",
        "name": "Demo Production 02",
        "director": "Demo Unit",
        "status": "Principal Photography",
        "description": "Second sample production for multi-production testing",
    },
    "PROD_01": {
        "production_id": "PROD_01",
        "name": "Demo Production 01",
        "director": "Demo Unit",
        "status": "Active",
        "description": "Hackathon sandbox production",
    },
}


class SpineWriter:
    def __init__(self, clickhouse_client=None):
        # Connect when one was not handed in. Absent or unreachable yields None
        # and the in-memory spine serves every read, exactly as before.
        self.client = clickhouse_client if clickhouse_client is not None else clickhouse.connect()
        # A cache over event_store, not the record itself. Every request that
        # builds takes, sequences or discrepancies walks a production's events
        # in full, so those passes stay in memory; the store is what makes them
        # survivable. Loaded in arrival order, because several reads take the
        # last event as the most recent word.
        self._in_memory_spine: List[Dict[str, Any]] = event_store.load_events()
        self._discrepancy_resolutions: Dict[str, Dict[str, Any]] = event_store.load_resolutions()
        # The built-in team, with anyone registered since layered over it.
        self._team_users: Dict[str, Dict[str, Any]] = {k: dict(v) for k, v in DEFAULT_TEAM_USERS.items()}
        self._team_users.update(event_store.load_users())
        # Rows waiting to go to ClickHouse. One insert per event turned a
        # 72-event ingestion from 0.8s into 7.4s and a 1991-event one into
        # minutes: each insert is a round trip and a new part on the server.
        self._pending_rows: List[List[Any]] = []
        # Monotonic deadline before which the mirror is not attempted at all.
        self._mirror_blocked_until: float = 0.0
        # Production ids already known to exist in the registry, per database
        # file. append_event runs once per event -- a single Silverstack volume
        # is ~2000 of them -- so it must not open a SQLite connection each time
        # to ask a question whose answer stops changing after the first event.
        # Keyed by path because the tests point each test at its own database.
        self._ensured_productions: Dict[str, set] = {}

    # ------------------------------------------------------------------ #
    # Screenplay & character profiles
    #
    # Backed by SQLite rather than process memory: these profiles are authored
    # by hand and drive character consistency across generated frames, so they
    # must survive a backend restart. See spine/character_store.py.
    # ------------------------------------------------------------------ #

    def store_screenplay(
        self,
        script_id: str,
        title: str,
        filename: Optional[str],
        profiles: List[Dict[str, Any]],
        author: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return character_store.store_screenplay(
            script_id=script_id,
            title=title,
            filename=filename,
            profiles=profiles,
            author=author,
        )

    def get_screenplay(self, script_id: str) -> Optional[Dict[str, Any]]:
        return character_store.get_screenplay(script_id)

    def get_character_profiles(self, script_id: str) -> List[Dict[str, Any]]:
        return character_store.get_character_profiles(script_id)

    def get_character_profile(self, script_id: str, character_id: str) -> Optional[Dict[str, Any]]:
        return character_store.get_character_profile(script_id, character_id)

    def update_character_profile(
        self,
        script_id: str,
        character_id: str,
        updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return character_store.update_character_profile(script_id, character_id, updates)

    def save_scene_breakdown(
        self, script_id: str, scene_number: str, shots: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        return breakdown_store.save(script_id, scene_number, shots)

    def get_scene_breakdown(self, script_id: str, scene_number: str) -> Optional[Dict[str, Any]]:
        return breakdown_store.get(script_id, scene_number)

    def list_scene_breakdowns(self, script_id: str) -> Dict[str, List[Dict[str, Any]]]:
        return breakdown_store.list_for_script(script_id)

    def delete_scene_breakdown(self, script_id: str, scene_number: str) -> bool:
        return breakdown_store.delete(script_id, scene_number)

    def store_screenplay_scenes(self, script_id: str, scenes: List[Dict[str, Any]]) -> int:
        return character_store.store_screenplay_scenes(script_id, scenes)

    def get_screenplay_scenes(self, script_id: str) -> List[Dict[str, Any]]:
        return character_store.get_screenplay_scenes(script_id)

    def find_screenplay_scenes(self, script_id: str, scene_number: str) -> List[Dict[str, Any]]:
        return character_store.find_screenplay_scenes(script_id, scene_number)

    def link_production_script(self, production_id: str, script_id: str) -> Dict[str, Any]:
        return character_store.link_production_script(production_id, script_id)

    def get_production_script(self, production_id: str) -> Optional[Dict[str, Any]]:
        return character_store.get_production_script(production_id)

    def unlink_production_script(self, production_id: str) -> bool:
        return character_store.unlink_production_script(production_id)

    def find_productions_for_script(self, script_id: str) -> List[str]:
        return character_store.find_productions_for_script(script_id)

    # ------------------------------------------------------------------ #
    # Editorial tags
    #
    # Hand-authored like the character profiles, and kept in SQLite for the same
    # reason: an editor's read on what is finished must survive a restart.
    # See spine/tag_store.py.
    # ------------------------------------------------------------------ #

    def set_editorial_tag(self, **kwargs) -> Dict[str, Any]:
        record = tag_store.set_tag(**kwargs)
        self._mirror_tag_event(record, action="set")
        return record

    def get_editorial_tag(
        self, production_id: str, target_type: str, target_id: str
    ) -> Optional[Dict[str, Any]]:
        return tag_store.get_tag(production_id, target_type, target_id)

    def list_editorial_tags(self, production_id: str, **filters) -> List[Dict[str, Any]]:
        return tag_store.list_tags(production_id, **filters)

    def clear_editorial_tag(
        self, production_id: str, target_type: str, target_id: str,
        cleared_by: Optional[str] = None,
    ) -> bool:
        cleared = tag_store.clear_tag(production_id, target_type, target_id, cleared_by)
        if cleared:
            trail = tag_store.history(production_id, target_type, target_id, limit=1)
            if trail:
                self._mirror_tag_event(trail[0], action="cleared")
        return cleared

    def mirror_available(self) -> bool:
        """
        Whether to attempt the analytical copy at all right now.

        Callers check this before building rows, not only before inserting: the
        take projection walks every event in a production, and doing that work
        to throw it away is most of the cost.
        """
        if not self.client:
            return False
        if self._mirror_blocked_until and time.monotonic() < self._mirror_blocked_until:
            return False
        return True

    def _try_insert(self, table: str, rows: List[List[Any]], column_names: List[str]) -> bool:
        """
        One insert, and the whole of the failure policy.

        A failure shuts the mirror for a cooldown rather than being retried: the
        spine and SQLite already hold everything written here, so the cost of
        skipping is a stale reporting table, while the cost of trying is paid by
        whoever is waiting for their save.
        """
        if not self.mirror_available():
            return False
        try:
            # Native ClickHouse HTTP stream insertion (async_insert)
            self.client.insert(
                table, 
                rows, 
                column_names=column_names,
                settings={"async_insert": 1, "wait_for_async_insert": 0}
            )
            if self._mirror_blocked_until:
                logger.info("ClickHouse is answering again; the mirror is open")
                self._mirror_blocked_until = 0.0
            return True
        except Exception as exc:
            self._mirror_blocked_until = time.monotonic() + MIRROR_COOLDOWN_SECONDS
            logger.error(
                "ClickHouse insert into %s failed (%s); pausing the mirror for %ds",
                table, exc, MIRROR_COOLDOWN_SECONDS,
            )
            return False

    def record_activity(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Appends one activity event and mirrors it.

        SQLite first and always; the mirror is best effort, exactly like the
        tag and requirement trails. Somebody acknowledging a blocker must not
        fail because a reporting database is unreachable.
        """
        event = activity_store.record(**kwargs)
        self._mirror_activity(event)
        return event

    def _mirror_activity(self, event: Dict[str, Any]) -> None:
        if not self.mirror_available():
            return
        self._try_insert(
            f"{_db()}.user_activity",
            [[
                event.get("event_id", ""),
                event.get("production_id", ""),
                event.get("shoot_day", ""),
                event.get("actor", ""),
                event.get("department", ""),
                event.get("action", ""),
                event.get("target_type", ""),
                event.get("target_id", ""),
                event.get("target_label", ""),
                event.get("seconds_since_target_created"),
                event.get("context_json", "{}"),
                # SQLite's own timestamp, so the two copies agree on order.
                _clickhouse_datetime(event.get("created_at")),
            ]],
            column_names=[
                "event_id", "production_id", "shoot_day", "actor", "department",
                "action", "target_type", "target_id", "target_label",
                "seconds_since_target_created", "context_json", "created_at",
            ],
        )

    def activity_for_target(self, production_id: str, target_type: str, target_id: str) -> List[Dict[str, Any]]:
        return activity_store.for_target(production_id, target_type, target_id)

    def acknowledgement_of(self, production_id: str, target_type: str, target_id: str) -> Optional[Dict[str, Any]]:
        return activity_store.acknowledgement(production_id, target_type, target_id)

    def _mirror_tag_event(self, record: Dict[str, Any], action: str) -> None:
        """
        Copies a tag change to the analytical spine when there is one.

        SQLite has already recorded it by this point, so a ClickHouse that is
        down costs the analytics copy and nothing else. Failing the editor's
        save because a reporting database is unreachable would be the wrong
        trade every time.
        """
        if not self.mirror_available():
            return
        self._try_insert(
            f"{_db()}.editorial_tag_events",
            [[
                    record.get("event_id") or f"tev_{uuid.uuid4().hex[:12]}",
                    record.get("production_id", ""),
                    record.get("target_type", ""),
                    record.get("target_id", ""),
                    action,
                    record.get("status") or "",
                    json.dumps(record.get("needs") or []),
                    json.dumps(record.get("descriptors") or []),
                    record.get("note") or "",
                    record.get("actor") or record.get("updated_by") or "",
                    # SQLite's own timestamp, not the server's clock: the two
                    # copies of the trail have to agree on the order.
                    _clickhouse_datetime(record.get("created_at") or record.get("updated_at")),
            ]],
            column_names=[
                "event_id", "production_id", "target_type", "target_id",
                "action", "status", "needs_json", "descriptors_json",
                "note", "actor", "created_at",
            ],
        )

    def summarize_editorial_tags(self, production_id: str) -> Dict[str, Any]:
        return tag_store.summarize(production_id)

    def store_document(
        self,
        production_id: str,
        shoot_day: str,
        filename: str,
        doc_type: str,
        department: str,
        content: str,
        checksum: Optional[str] = None,
        raw_bytes: Optional[bytes] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Stores raw document text/content with metadata, raw binary bytes, and checksum for in-app previewing and duplicate prevention.
        """
        doc_id = str(uuid.uuid4())
        doc_record: Dict[str, Any] = {
            "doc_id": doc_id,
            "production_id": production_id,
            "shoot_day": shoot_day,
            "filename": filename,
            "doc_type": doc_type,
            "department": department,
            "content": content,
            "raw_bytes": raw_bytes,
            "checksum": checksum,
            "size_bytes": len(raw_bytes) if raw_bytes else len(content.encode("utf-8")),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        event_store.store_document(doc_record)
        return doc_id

    def get_document_by_checksum(
        self,
        production_id: str,
        shoot_day: str,
        checksum: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Finds if a document with the exact same content checksum exists for this production and shoot day.
        """
        return event_store.find_document_by_checksum(production_id, shoot_day, checksum)

    def delete_document(self, doc_id: str) -> bool:
        """
        Deletes an uploaded document from the repository and purges its events from the active spine.
        """
        if not event_store.delete_document(doc_id):
            return False

        # Its readings go with it, from the store and from the cache over it.
        event_store.delete_events_for_document(doc_id)
        self._in_memory_spine = [
            e for e in self._in_memory_spine if e.get("metadata", {}).get("doc_id") != doc_id
        ]
        self._purge_mirrored_document(doc_id)
        return True

    def _purge_mirrored_document(self, doc_id: str) -> None:
        """
        Removes a deleted document's events from the analytical mirror too.

        The mirror is append-only and this is the one thing that is allowed to
        delete from it. Leaving it out meant a document removed from the
        operational store lived on in ClickHouse -- and a row that should never
        have been ingested, a mis-parsed line carrying contact details among
        them, could not be got rid of at all.

        A mutation rather than a delete, because that is what ClickHouse
        offers. Never fatal: the document is already gone from the store the
        app reads, so a mirror that is down costs the tidying and nothing else.
        """
        if not self.mirror_available():
            return
        try:
            self.client.command(
                f"ALTER TABLE {_db()}.production_events DELETE "
                "WHERE JSONExtractString(metadata_json, 'doc_id') = %(doc_id)s",
                parameters={"doc_id": doc_id},
            )
        except Exception as e:
            logger.warning("Could not purge document %s from the analytical mirror: %s", doc_id, e)

    def list_documents(self, production_id: Optional[str] = None, shoot_day: Optional[str] = None) -> List[Dict[str, Any]]:
        return event_store.list_documents(production_id=production_id, shoot_day=shoot_day)

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        return event_store.get_document(doc_id)

    def append_event(self, event: Dict[str, Any]) -> None:
        """
        Appends an event to the immutable spine.

        Written to the store before the cache, so a reader that sees it in
        memory can be sure it is on disk. The write is one insert on a held
        connection in WAL: a 2000-event ingestion pays 0.06s for it, which is
        cheap enough not to need a buffer that a crash could empty.
        """
        event_store.append_event(event)
        self._in_memory_spine.append(event)

        prod_id = event.get("production_id")
        if prod_id:
            self._ensure_production(prod_id)

        if self.mirror_available():
            self._pending_rows.append([
                event.get("event_id"),
                event.get("production_id"),
                event.get("shoot_day"),
                event.get("axis"),
                event.get("department"),
                event.get("doc_type"),
                event.get("entity_type"),
                json.dumps(event.get("payload", {})),
                json.dumps(event.get("metadata", {})),
            ])
            if len(self._pending_rows) >= EVENT_BATCH_SIZE:
                self.flush_events()

    def flush_events(self) -> int:
        """
        Sends the buffered rows in one insert and returns how many went.

        Callers flush at the end of an ingestion so a document's events do not
        sit waiting for the next one. The buffer is dropped on failure rather
        than retried: the in-memory spine already has every event, and a
        reporting copy is not worth growing memory without bound to protect.
        """
        if not self.client or not self._pending_rows:
            return 0

        # Taken from the buffer either way. Holding them while the mirror is
        # shut would grow memory across an outage to protect a reporting copy.
        rows, self._pending_rows = self._pending_rows, []
        sent = self._try_insert(
            f"{_db()}.production_events",
            rows,
            column_names=[
                "event_id",
                "production_id",
                "shoot_day",
                "axis",
                "department",
                "doc_type",
                "entity_type",
                "payload_json",
                "metadata_json",
            ],
        )
        return len(rows) if sent else 0

    # ------------------------------------------------------------------ #
    # Analytical projections
    #
    # The spine is the record; these two tables are indexes over it, kept for
    # querying rather than for reading back into the application. Both are
    # ReplacingMergeTree, so writing the current answer again is how they are
    # kept current -- the older row is dropped on merge.
    # ------------------------------------------------------------------ #

    def project_takes(self, production_id: str, shoot_day: Optional[str] = None) -> int:
        """
        Writes one row per take per camera roll, from the spine's take events.

        One row per roll, not per take, because that is what the table's key
        says: a take shot on three cameras is three rows. Reconciling them into
        one take is a question with an opinion in it, and an index should not
        hold opinions.

        shoot_day defaults to every day, and callers should leave it that way.
        A facing page is filed under the day it was handed over but carries
        takes from every day the scene was covered, so projecting only the
        day a document arrived under left sixty takes in the spine and out of
        the index.
        """
        # Checked before walking the events, not only before inserting: the
        # walk is most of the cost, and doing it to throw the result away is
        # exactly what the breaker exists to avoid.
        if not self.mirror_available():
            return 0

        rows: Dict[tuple, List[Any]] = {}
        for event in self.get_events(production_id=production_id, shoot_day=shoot_day):
            if event.get("entity_type") != "take":
                continue
            p = event.get("payload", {})
            slate, take_id = p.get("slate"), p.get("take_id")
            if not slate or not take_id:
                continue
            roll = p.get("camera_roll") or ""
            day = str(event.get("shoot_day") or shoot_day or "")
            # Keyed by the day too: the same slate and roll can be shot on more
            # than one day, and collapsing them would lose one.
            rows[(day, slate, str(take_id), roll)] = [
                production_id, day, str(p.get("scene") or ""), slate, str(take_id),
                roll, p.get("sound_roll") or "",
                float(p.get("fps") or 24.0),
                p.get("timecode_in") or "", p.get("timecode_out") or "",
                # None survives as None: "no claim" is not "not circled".
                None if p.get("is_starred") is None else int(bool(p.get("is_starred"))),
                int(bool(p.get("is_pickup"))), int(bool(p.get("is_vfx"))),
            ]

        if not rows:
            return 0

        sent = self._try_insert(
            f"{_db()}.takes_meta",
            list(rows.values()),
            column_names=[
                "production_id", "shoot_day", "scene_id", "slate", "take_id",
                "camera_roll", "sound_roll", "fps", "timecode_in", "timecode_out",
                "is_starred", "is_pickup", "is_vfx",
            ],
        )
        return len(rows) if sent else 0

    def project_discrepancies(self, discrepancies: List[Dict[str, Any]]) -> int:
        """
        Writes the discrepancies as they currently stand.

        They are computed from the spine on demand rather than stored, so this
        is a snapshot: a discrepancy that a later document settles is written
        again with is_resolved set, and the older row is dropped on merge.
        """
        if not self.mirror_available() or not discrepancies:
            return 0

        rows = []
        for d in discrepancies:
            rows.append([
                d.get("discrepancy_id") or str(uuid.uuid4()),
                d.get("production_id", ""), str(d.get("shoot_day", "")),
                d.get("entity_type", ""), d.get("entity_id", ""),
                d.get("discrepancy_type", ""), d.get("severity", ""),
                d.get("description", ""),
                json.dumps(d.get("witnesses", [])),
                int(bool(d.get("is_resolved"))),
            ])

        sent = self._try_insert(
            f"{_db()}.audit_discrepancies",
            rows,
            column_names=[
                "discrepancy_id", "production_id", "shoot_day", "entity_type",
                "entity_id", "discrepancy_type", "severity", "description",
                "witnesses_json", "is_resolved",
            ],
        )
        return len(rows) if sent else 0

    def get_events(self, production_id: Optional[str] = None, shoot_day: Optional[str] = None) -> List[Dict[str, Any]]:
        events = self._in_memory_spine
        if production_id:
            events = [e for e in events if e.get("production_id") == production_id]
        if shoot_day:
            events = [e for e in events if e.get("shoot_day") == shoot_day]
        return events

    def list_productions(self) -> List[Dict[str, Any]]:
        """
        Summarizes all registered productions with active days, event counts, and take counts.
        """
        results = []
        for info in self._registered_productions():
            prod_id = info["production_id"]
            prod_events = [e for e in self._in_memory_spine if e.get("production_id") == prod_id]
            
            # Find unique shoot days
            days = sorted(
                list({e.get("shoot_day") for e in prod_events if e.get("shoot_day")}),
                key=lambda x: int(x) if x.isdigit() else 999
            )
            
            # Find unique takes
            takes = {
                f"{e.get('payload', {}).get('slate')}_{e.get('payload', {}).get('take_id')}"
                for e in prod_events
                if e.get("entity_type") == "take"
            }

            last_ts = prod_events[-1].get("timestamp") if prod_events else None

            results.append({
                **info,
                "shoot_days": days,
                "total_events": len(prod_events),
                "total_takes": len(takes),
                "last_activity": last_ts,
            })
        return results

    def _ensure_production(self, production_id: str) -> None:
        """
        Makes sure a production named on an event exists in the registry.

        A built-in demo gets its own name and description rather than being
        marked auto: those ids are known, and an ingest naming one is not a
        guess about what the production is. Anything else is a guess read off a
        filename, and is recorded as one.
        """
        try:
            key = production_store.normalize_production_id(production_id)
        except production_store.UnknownProductionField:
            return

        seen = self._ensured_productions.setdefault(production_store.get_db_path(), set())
        if key in seen:
            return

        if not production_store.get(key):
            known = DEFAULT_PRODUCTIONS.get(key)
            if known:
                production_store.upsert(**known)
            else:
                production_store.register_if_absent(key, origin="auto")
        seen.add(key)

    def _registered_productions(self) -> List[Dict[str, Any]]:
        return production_store.list_all()

    def register_production(
        self,
        production_id: str,
        name: str,
        director: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        return production_store.upsert(
            production_id=production_id,
            name=name,
            director=director or "Main Unit",
            description=description,
            status=status,
            origin="registered",
        )

    def get_production(self, production_id: str) -> Optional[Dict[str, Any]]:
        return production_store.get(production_id)

    def update_production(self, production_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return production_store.update(production_id, updates)

    def delete_production(self, production_id: str) -> bool:
        return production_store.delete(production_id)

    def count_production_events(self, production_id: str) -> int:
        return sum(1 for e in self._in_memory_spine if e.get("production_id") == production_id)

    def list_production_crew(
        self,
        production_id: str,
        active_only: bool = False,
    ) -> List[Dict[str, Any]]:
        return crew_store.list_for(production_id, active_only=active_only)

    def upsert_production_crew_member(self, member: Dict[str, Any]) -> Dict[str, Any]:
        record = crew_store.upsert(member)
        self.register_user(
            handle=record["handle"],
            name=record["name"],
            email=record["email"] or f"{record['handle'].lstrip('@')}@production.film",
            role=record["role"],
            avatar_color="#3b82f6" if record["department"] == "editorial" else "#8b5cf6",
        )
        return record

    def update_production_crew_member(
        self,
        production_id: str,
        handle: str,
        updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        record = crew_store.update(production_id, handle, updates)
        if record:
            self.register_user(
                handle=record["handle"],
                name=record["name"],
                email=record["email"] or f"{record['handle'].lstrip('@')}@production.film",
                role=record["role"],
                avatar_color="#3b82f6" if record["department"] == "editorial" else "#8b5cf6",
            )
        return record

    def delete_production_crew_member(self, production_id: str, handle: str) -> bool:
        return crew_store.delete(production_id, handle)

    def store_discrepancy_resolution(
        self,
        production_id: str,
        shoot_day: str,
        discrepancy_id: str,
        entity_id: Optional[str] = None,
        resolved_card: Optional[str] = None,
        resolution_note: Optional[str] = None,
        resolved_by: str = "Assistant Editor",
    ) -> Dict[str, Any]:
        """
        Stores resolution for a discrepancy, specifying target card/roll assignment and notes.
        """
        resolution = {
            "discrepancy_id": discrepancy_id,
            "production_id": production_id,
            "shoot_day": shoot_day,
            "entity_id": entity_id,
            "is_resolved": True,
            "resolved_card": resolved_card,
            "resolution_note": resolution_note,
            "resolved_by": resolved_by,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }
        self._discrepancy_resolutions[discrepancy_id] = resolution
        event_store.save_resolution(discrepancy_id, resolution)
        if entity_id:
            # Also key by entity_id so dynamic re-reconciliation finds the resolution
            entity_key = f"{production_id}_{shoot_day}_{entity_id}"
            self._discrepancy_resolutions[entity_key] = resolution
            event_store.save_resolution(entity_key, resolution)
        return resolution

    def delete_discrepancy_resolution(self, discrepancy_id: str) -> bool:
        """
        Re-opens an active discrepancy by clearing its resolution record.
        """
        if discrepancy_id not in self._discrepancy_resolutions:
            return False

        res = self._discrepancy_resolutions.pop(discrepancy_id)
        keys = [discrepancy_id]
        ent_id = res.get("entity_id")
        if ent_id:
            ent_k = f"{res.get('production_id')}_{res.get('shoot_day')}_{ent_id}"
            self._discrepancy_resolutions.pop(ent_k, None)
            keys.append(ent_k)
        event_store.delete_resolutions(keys)
        return True

    def get_discrepancy_resolutions(self, production_id: str, shoot_day: str) -> Dict[str, Dict[str, Any]]:
        """
        Returns all resolutions for a production and shoot day.
        """
        return {
            k: v for k, v in self._discrepancy_resolutions.items()
            if v.get("production_id") == production_id and v.get("shoot_day") == shoot_day
        }

    # ==========================================
    # Team Users / Passwordless Profiles
    # ==========================================
    def list_users(self) -> List[Dict[str, Any]]:
        """
        Returns all registered production team users.
        """
        return list(self._team_users.values())

    def get_user(self, handle_or_email: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a user profile by @handle or email (case-insensitive).
        """
        cleaned = handle_or_email.strip().lower()
        if not cleaned.startswith("@") and "@" not in cleaned:
            cleaned = f"@{cleaned}"

        # 1. Match handle
        for handle, u in self._team_users.items():
            if handle.lower() == cleaned or handle.lower() == f"@{cleaned.lstrip('@')}":
                return u
            if u.get("email", "").lower() == cleaned:
                return u
        return None

    def register_user(
        self,
        handle: str,
        name: str,
        email: str,
        role: str,
        avatar_color: str = "#8b5cf6",
    ) -> Dict[str, Any]:
        """
        Registers or updates a team user profile.
        """
        norm_handle = handle.strip()
        if not norm_handle.startswith("@"):
            norm_handle = f"@{norm_handle}"

        user = {
            "handle": norm_handle,
            "name": name.strip(),
            "email": email.strip().lower(),
            "role": role.strip(),
            "avatar_color": avatar_color,
        }
        self._team_users[norm_handle] = user
        event_store.save_user(user)
        return user

    # ==========================================
    # Collaborative Requirements System
    # ==========================================
    def create_requirement(self, requirement: Dict[str, Any]) -> Dict[str, Any]:
        """
        Raises a requirement against a scene, shot or take.

        Stored rather than remembered: a requirement outlives the day it was
        raised on -- that is what raising one is for -- and keeping it in
        process memory wiped a production's outstanding work on every restart,
        while the tags and the script link beside it survived.
        """
        record = requirement_store.create(requirement)
        return self._mirror_requirement_event(record)

    def get_requirement(self, requirement_id: str) -> Optional[Dict[str, Any]]:
        return requirement_store.get(requirement_id)

    def list_requirements(
        self,
        production_id: Optional[str] = None,
        shoot_day: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        assigned_to: Optional[str] = None,
        created_by: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return requirement_store.list_requirements(
            production_id=production_id,
            shoot_day=shoot_day,
            target_type=target_type,
            target_id=target_id,
            assigned_to=assigned_to,
            created_by=created_by,
            status=status,
        )

    def update_requirement(
        self,
        requirement_id: str,
        updates: Dict[str, Any],
        actor: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        record = requirement_store.update(requirement_id, updates, actor=actor)
        return self._mirror_requirement_event(record)

    def resolve_requirement(
        self,
        requirement_id: str,
        resolution_note: str,
        resolved_by: str,
    ) -> Optional[Dict[str, Any]]:
        record = requirement_store.resolve(requirement_id, resolution_note, resolved_by)
        return self._mirror_requirement_event(record)

    def delete_requirement(self, requirement_id: str, actor: Optional[str] = None) -> bool:
        record = requirement_store.delete(requirement_id, actor=actor)
        self._mirror_requirement_event(record)
        return record is not None

    def requirement_history(
        self,
        requirement_id: Optional[str] = None,
        production_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        return requirement_store.history(
            requirement_id=requirement_id, production_id=production_id, limit=limit
        )

    def _mirror_requirement_event(
        self, record: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Copies a requirement change to the analytical spine when there is one,
        and hands the record back without the private event field.

        SQLite has already recorded it by this point, so a ClickHouse that is
        down costs the analytics copy and nothing else. An edit that changed
        nothing carries no event and mirrors nothing.
        """
        if record is None:
            return None
        event = record.pop("_event", None)
        if not event or not self.mirror_available():
            return record

        self._try_insert(
            f"{_db()}.requirement_events",
            [[
                event["event_id"],
                event["requirement_id"],
                event["production_id"],
                event["action"],
                event.get("status") or "",
                event.get("priority") or "",
                event.get("assigned_to") or "",
                json.dumps(event.get("changes") or {}),
                event.get("note") or "",
                event.get("actor") or "",
                # SQLite's own timestamp, not the server's clock: the two
                # copies of the trail have to agree on the order.
                _clickhouse_datetime(event.get("created_at")),
            ]],
            column_names=[
                "event_id", "requirement_id", "production_id", "action",
                "status", "priority", "assigned_to", "changes_json",
                "note", "actor", "created_at",
            ],
        )
        return record

    # ==========================================
    # Real-Time Alerts & Notification Center
    # ==========================================
    def create_notification(self, notification: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sends an alert to one person.

        Stored rather than remembered: held in memory this was the one part of
        the exchange that did not survive a restart. The requirement stayed and
        its trail stayed, while the alert telling somebody it was now theirs
        quietly vanished, and an alert nobody can be shown was never sent.
        """
        return notification_store.create(notification)

    def get_notification(self, notification_id: str) -> Optional[Dict[str, Any]]:
        return notification_store.get(notification_id)

    def list_notifications(
        self,
        recipient_handle: str,
        unread_only: bool = False,
    ) -> List[Dict[str, Any]]:
        return notification_store.list_for(recipient_handle, unread_only=unread_only)

    def count_unread_notifications(self, recipient_handle: str) -> int:
        return notification_store.unread_count(recipient_handle)

    def mark_notification_read(self, notification_id: str) -> bool:
        return notification_store.mark_read(notification_id)

    def mark_all_notifications_read(self, recipient_handle: str) -> int:
        return notification_store.mark_all_read(recipient_handle)

    def seed_defaults(self) -> Dict[str, Any]:
        """
        Seeds baseline demo productions, team users, crew roster, and sample screenplay.
        """
        # 1. Seed Default Productions
        for prod_id, info in DEFAULT_PRODUCTIONS.items():
            try:
                production_store.upsert(**info)
            except Exception as e:
                logger.warning(f"Failed to seed production {prod_id}: {e}")

        # 2. Seed Default Team Users
        self._team_users = {k: dict(v) for k, v in DEFAULT_TEAM_USERS.items()}
        for handle, udata in DEFAULT_TEAM_USERS.items():
            try:
                event_store.save_user({
                    "handle": handle,
                    "name": udata.get("name", handle),
                    "email": udata.get("email", ""),
                    "role": udata.get("role", "General"),
                    "avatar_color": udata.get("avatar_color", "#4f46e5"),
                })
            except Exception as e:
                logger.warning(f"Failed to seed user {handle}: {e}")

        # 3. Seed Production Crew for DEMO_PRODUCTION
        dept_map = {
            "@director": "production",
            "@post_supervisor": "production",
            "@lead_editor": "editorial",
            "@assistant_editor": "editorial",
            "@script_supervisor": "editorial",
            "@dit_operator": "dit",
            "@sound_supervisor": "sound",
            "@vfx_supervisor": "vfx",
        }
        for handle, udata in DEFAULT_TEAM_USERS.items():
            try:
                crew_store.upsert({
                    "production_id": "DEMO_PRODUCTION",
                    "handle": handle,
                    "name": udata.get("name", handle),
                    "email": udata.get("email", ""),
                    "role": udata.get("role", "Crew"),
                    "department": dept_map.get(handle, "general"),
                })
            except Exception as e:
                logger.warning(f"Failed to seed crew for {handle}: {e}")

        # 4. Seed Demo Screenplay from data/examples/demo_script.fountain if available
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        demo_fountain_path = os.path.join(root_dir, "data", "examples", "demo_script.fountain")

        if os.path.exists(demo_fountain_path):
            try:
                with open(demo_fountain_path, "r", encoding="utf-8") as f:
                    fountain_text = f.read()
                from backend.app.script.parser import parse_fountain_screenplay
                parsed = parse_fountain_screenplay(fountain_text, title="The Algorithm")
                profiles_dicts = [p.model_dump() for p in parsed.characters]
                character_store.store_screenplay(
                    script_id=parsed.script_id,
                    title=parsed.title or "The Algorithm",
                    filename="demo_script.fountain",
                    profiles=profiles_dicts,
                    author=parsed.author or "CineSpine Demo",
                )
                scenes_dicts = [s.model_dump() for s in parsed.scenes]
                character_store.store_screenplay_scenes(parsed.script_id, scenes_dicts)
                character_store.link_production_script("DEMO_PRODUCTION", parsed.script_id)
            except Exception as e:
                logger.warning(f"Failed to seed demo screenplay: {e}")


        return {
            "productions": list(DEFAULT_PRODUCTIONS.keys()),
            "users": list(DEFAULT_TEAM_USERS.keys()),
            "screenplay": "DEMO_PRODUCTION linked to demo_script.fountain",
        }

    def wipe_all(self, seed: bool = True) -> Dict[str, Any]:
        """
        Factory reset: cleans up all SQLite tables (the primary source of truth)
        and ClickHouse (the analytical mirror), then re-seeds clean baseline defaults.
        """
        # 1. Clear in-memory caches
        self._in_memory_spine = []
        self._discrepancy_resolutions = {}
        self._pending_rows = []
        self._ensured_productions = {}

        # 2. Clear all SQLite tables in spine.db
        import sqlite3
        db_path = event_store.get_db_path()
        sqlite_cleared = []
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path, timeout=10)
            try:
                tables = [
                    "spine_events",
                    "source_documents",
                    "discrepancy_resolutions",
                    "team_users",
                    "productions",
                    "production_crew",
                    "screenplays",
                    "character_profiles",
                    "screenplay_scenes",
                    "production_scripts",
                    "scene_breakdowns",
                    "requirements",
                    "requirement_events",
                    "notifications",
                    "editorial_tags",
                    "editorial_tag_events",
                    "user_activity",
                    "acknowledgements",
                ]
                for tbl in tables:
                    try:
                        conn.execute(f"DELETE FROM {tbl}")
                        sqlite_cleared.append(tbl)
                    except Exception:
                        pass
                conn.commit()
            finally:
                conn.close()

        # 3. Truncate ClickHouse mirror tables if connected
        clickhouse_cleared = []
        if self.client:
            db_name = _db()
            ch_tables = [
                "spine_events",
                "production_events",
                "takes_meta",
                "editorial_tag_events",
                "requirement_events",
                "activity_events",
                "audit_discrepancies",
                "document_metadata",
                "event_DLQ",
            ]
            for tbl in ch_tables:
                try:
                    self.client.command(f"TRUNCATE TABLE IF EXISTS {db_name}.{tbl}")
                    clickhouse_cleared.append(tbl)
                except Exception as e:
                    logger.warning(f"Failed to truncate ClickHouse table {tbl}: {e}")

        # 4. Re-seed baseline defaults
        seeded_info = None
        if seed:
            seeded_info = self.seed_defaults()

        return {
            "status": "success",
            "message": "Factory reset complete: both databases wiped and baseline state re-seeded.",
            "sqlite_tables": sqlite_cleared,
            "clickhouse_tables": clickhouse_cleared,
            "seeded": seeded_info,
        }
