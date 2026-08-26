"""
ClickHouse Append-Only Event Writer, Multi-Production & Document Store.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from backend.app.spine import character_store
from backend.app.streaming.models import DEFAULT_TEAM_USERS

logger = logging.getLogger(__name__)

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
        self.client = clickhouse_client
        self._in_memory_spine: List[Dict[str, Any]] = []
        self._productions: Dict[str, Dict[str, Any]] = dict(DEFAULT_PRODUCTIONS)
        self._documents: Dict[str, Dict[str, Any]] = {}
        self._discrepancy_resolutions: Dict[str, Dict[str, Any]] = {}
        self._team_users: Dict[str, Dict[str, Any]] = {k: dict(v) for k, v in DEFAULT_TEAM_USERS.items()}
        self._requirements: Dict[str, Dict[str, Any]] = {}
        self._notifications: Dict[str, Dict[str, Any]] = {}

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
        doc_record = {
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
        self._documents[doc_id] = doc_record
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
        for doc in self._documents.values():
            if (
                doc.get("production_id") == production_id
                and doc.get("shoot_day") == shoot_day
                and doc.get("checksum") == checksum
            ):
                return doc
        return None

    def delete_document(self, doc_id: str) -> bool:
        """
        Deletes an uploaded document from the repository and purges its events from the active spine.
        """
        if doc_id not in self._documents:
            return False

        # Remove the document record
        del self._documents[doc_id]

        # Purge associated events from the in-memory spine
        self._in_memory_spine = [
            e for e in self._in_memory_spine if e.get("metadata", {}).get("doc_id") != doc_id
        ]
        return True

    def list_documents(self, production_id: Optional[str] = None, shoot_day: Optional[str] = None) -> List[Dict[str, Any]]:
        docs = list(self._documents.values())
        if production_id:
            docs = [d for d in docs if d.get("production_id") == production_id]
        if shoot_day:
            docs = [d for d in docs if d.get("shoot_day") == shoot_day]
        
        # Return summary without full heavy content
        return [
            {
                "doc_id": d["doc_id"],
                "production_id": d["production_id"],
                "shoot_day": d["shoot_day"],
                "filename": d["filename"],
                "doc_type": d["doc_type"],
                "department": d["department"],
                "checksum": d.get("checksum"),
                "size_bytes": d["size_bytes"],
                "uploaded_at": d["uploaded_at"],
            }
            for d in docs
        ]

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        return self._documents.get(doc_id)

    def append_event(self, event: Dict[str, Any]) -> None:
        """
        Appends an event to the immutable spine.
        """
        self._in_memory_spine.append(event)

        prod_id = event.get("production_id")
        if prod_id and prod_id not in self._productions:
            self._productions[prod_id] = {
                "production_id": prod_id,
                "name": prod_id.replace("_", " ").title(),
                "director": "Unknown",
                "status": "Active",
                "description": "Auto-registered production",
            }

        if self.client:
            try:
                row = [
                    event.get("event_id"),
                    event.get("production_id"),
                    event.get("shoot_day"),
                    event.get("axis"),
                    event.get("department"),
                    event.get("doc_type"),
                    event.get("entity_type"),
                    json.dumps(event.get("payload", {})),
                    json.dumps(event.get("metadata", {})),
                ]
                self.client.insert(
                    "cinespine.production_events",
                    [row],
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
            except Exception as e:
                logger.error(f"Failed to append event to ClickHouse: {e}")

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
        for prod_id, info in self._productions.items():
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

    def register_production(self, production_id: str, name: str, director: Optional[str] = None, description: Optional[str] = None) -> Dict[str, Any]:
        info = {
            "production_id": production_id,
            "name": name,
            "director": director or "Main Unit",
            "status": "Active",
            "description": description or "",
        }
        self._productions[production_id] = info
        return info

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
        if entity_id:
            # Also key by entity_id so dynamic re-reconciliation finds the resolution
            self._discrepancy_resolutions[f"{production_id}_{shoot_day}_{entity_id}"] = resolution
        return resolution

    def delete_discrepancy_resolution(self, discrepancy_id: str) -> bool:
        """
        Re-opens an active discrepancy by clearing its resolution record.
        """
        deleted = False
        if discrepancy_id in self._discrepancy_resolutions:
            res = self._discrepancy_resolutions.pop(discrepancy_id)
            deleted = True
            ent_id = res.get("entity_id")
            if ent_id:
                ent_k = f"{res.get('production_id')}_{res.get('shoot_day')}_{ent_id}"
                self._discrepancy_resolutions.pop(ent_k, None)
        return deleted

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
        return user

    # ==========================================
    # Collaborative Requirements System
    # ==========================================
    def create_requirement(self, requirement: Dict[str, Any]) -> Dict[str, Any]:
        """
        Creates and stores a requirement attached to a Scene, Shot, or Take.
        """
        req_id = requirement.get("requirement_id") or f"req_{uuid.uuid4().hex[:10]}"
        now_ts = datetime.now(timezone.utc).isoformat()
        assigned = requirement.get("assigned_to", "").strip()
        if assigned and not assigned.startswith("@"):
            assigned = f"@{assigned}"
        created_by = requirement.get("created_by", "@user").strip()
        if created_by and not created_by.startswith("@"):
            created_by = f"@{created_by}"

        rec = {
            "requirement_id": req_id,
            "production_id": requirement.get("production_id", "DEMO_PRODUCTION"),
            "shoot_day": str(requirement.get("shoot_day", "1")),
            "target_type": requirement.get("target_type", "take"),
            "target_id": str(requirement.get("target_id", "")),
            "target_label": requirement.get("target_label") or f"{requirement.get('target_type', 'target').capitalize()} {requirement.get('target_id', '')}",
            "title": requirement.get("title", ""),
            "description": requirement.get("description", ""),
            "priority": requirement.get("priority", "medium"),
            "category": requirement.get("category", "general"),
            "created_by": created_by,
            "assigned_to": assigned,
            "status": requirement.get("status", "open"),
            "resolution_note": requirement.get("resolution_note"),
            "resolved_by": requirement.get("resolved_by"),
            "resolved_at": requirement.get("resolved_at"),
            "created_at": requirement.get("created_at") or now_ts,
            "updated_at": now_ts,
        }
        self._requirements[req_id] = rec
        return rec

    def get_requirement(self, requirement_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a single requirement by ID.
        """
        return self._requirements.get(requirement_id)

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
        """
        Lists and filters requirements by production, shoot day, target, assignee, or status.
        """
        reqs = list(self._requirements.values())
        if production_id:
            reqs = [r for r in reqs if r.get("production_id") == production_id]
        if shoot_day:
            reqs = [r for r in reqs if str(r.get("shoot_day")) == str(shoot_day)]
        if target_type:
            reqs = [r for r in reqs if r.get("target_type") == target_type]
        if target_id:
            reqs = [r for r in reqs if str(r.get("target_id")) == str(target_id)]
        if assigned_to:
            norm_a = assigned_to if assigned_to.startswith("@") else f"@{assigned_to}"
            reqs = [r for r in reqs if r.get("assigned_to", "").lower() == norm_a.lower()]
        if created_by:
            norm_c = created_by if created_by.startswith("@") else f"@{created_by}"
            reqs = [r for r in reqs if r.get("created_by", "").lower() == norm_c.lower()]
        if status:
            reqs = [r for r in reqs if r.get("status") == status]

        # Return sorted by created_at descending
        return sorted(reqs, key=lambda x: x.get("created_at", ""), reverse=True)

    def update_requirement(self, requirement_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Updates fields of an existing requirement.
        """
        if requirement_id not in self._requirements:
            return None

        req = self._requirements[requirement_id]
        for k, v in updates.items():
            if k in ["title", "description", "priority", "category", "status", "assigned_to", "target_label"]:
                if k == "assigned_to" and v and not str(v).startswith("@"):
                    v = f"@{v}"
                req[k] = v

        req["updated_at"] = datetime.now(timezone.utc).isoformat()
        return req

    def resolve_requirement(
        self,
        requirement_id: str,
        resolution_note: str,
        resolved_by: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Marks a requirement as resolved, records resolution note and resolver.
        """
        if requirement_id not in self._requirements:
            return None

        norm_r = resolved_by if resolved_by.startswith("@") else f"@{resolved_by}"
        now_ts = datetime.now(timezone.utc).isoformat()
        req = self._requirements[requirement_id]
        req["status"] = "resolved"
        req["resolution_note"] = resolution_note
        req["resolved_by"] = norm_r
        req["resolved_at"] = now_ts
        req["updated_at"] = now_ts
        return req

    def delete_requirement(self, requirement_id: str) -> bool:
        """
        Deletes a requirement record.
        """
        if requirement_id in self._requirements:
            del self._requirements[requirement_id]
            return True
        return False

    # ==========================================
    # Real-Time Alerts & Notification Center
    # ==========================================
    def create_notification(self, notification: Dict[str, Any]) -> Dict[str, Any]:
        """
        Creates and stores an alert notification for a user.
        """
        notif_id = notification.get("notification_id") or f"notif_{uuid.uuid4().hex[:10]}"
        now_ts = datetime.now(timezone.utc).isoformat()
        recipient = notification.get("recipient_handle", "").strip()
        if recipient and not recipient.startswith("@"):
            recipient = f"@{recipient}"
        actor = notification.get("actor_handle", "").strip()
        if actor and not actor.startswith("@"):
            actor = f"@{actor}"

        notif = {
            "notification_id": notif_id,
            "production_id": notification.get("production_id", "DEMO_PRODUCTION"),
            "recipient_handle": recipient,
            "actor_handle": actor,
            "notification_type": notification.get("notification_type", "ASSIGNED"),
            "requirement_id": notification.get("requirement_id", ""),
            "title": notification.get("title", ""),
            "message": notification.get("message", ""),
            "target_type": notification.get("target_type", "take"),
            "target_id": str(notification.get("target_id", "")),
            "target_label": notification.get("target_label", ""),
            "is_read": False,
            "created_at": notification.get("created_at") or now_ts,
        }
        self._notifications[notif_id] = notif
        return notif

    def list_notifications(
        self,
        recipient_handle: str,
        unread_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Lists notifications for a specific user handle, sorted newest first.
        """
        norm_r = recipient_handle.strip().lower()
        if not norm_r.startswith("@"):
            norm_r = f"@{norm_r}"

        notifs = [
            n for n in self._notifications.values()
            if n.get("recipient_handle", "").lower() == norm_r
        ]
        if unread_only:
            notifs = [n for n in notifs if not n.get("is_read")]

        return sorted(notifs, key=lambda x: x.get("created_at", ""), reverse=True)

    def mark_notification_read(self, notification_id: str) -> bool:
        """
        Marks a specific notification as read.
        """
        if notification_id in self._notifications:
            self._notifications[notification_id]["is_read"] = True
            return True
        return False

    def mark_all_notifications_read(self, recipient_handle: str) -> int:
        """
        Marks all unread notifications for a user as read. Returns count of updated alerts.
        """
        norm_r = recipient_handle.strip().lower()
        if not norm_r.startswith("@"):
            norm_r = f"@{norm_r}"

        count = 0
        for n in self._notifications.values():
            if n.get("recipient_handle", "").lower() == norm_r and not n.get("is_read"):
                n["is_read"] = True
                count += 1
        return count


