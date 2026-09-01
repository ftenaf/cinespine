"""
Wrap Rescue Agent: ClickHouse-backed editorial handoff automation.

The hackathon track requires a visible runtime path through the official
`mcp-clickhouse` server. This module keeps that path explicit: the agent asks
the MCP server for ClickHouse table metadata and rows, then deterministic code
decides which blockers become CineSpine requirements.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

from backend.app.core import analytics
from backend.app.integrations.cloud_logging import AgentCloudLogger
from backend.app.reconciliation.engine import ReconciliationEngine
from backend.app.script.llm_router import get_optimal_gemini_model
from backend.app.spine.clickhouse import database
from backend.app.spine.writer import SpineWriter

logger = logging.getLogger(__name__)

WRAP_RESCUE_ACTOR = "@wrap_rescue_agent"
SOURCE_MARKER = "WrapRescueSource:"


class ClickHouseMCPStatus(BaseModel):
    configured: bool
    available: bool
    server_url: Optional[str] = None
    health_url: Optional[str] = None
    transport: str = "http"
    package_installed: bool = False
    reason: Optional[str] = None


class ToolCallTrace(BaseModel):
    tool: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    ok: bool
    rows: int = 0
    error: Optional[str] = None


class AgentStep(BaseModel):
    step: str
    status: Literal["ok", "warning", "error"]
    detail: str
    tool_call: Optional[ToolCallTrace] = None


class GeminiEnterpriseStatus(BaseModel):
    configured: bool
    genai_available: bool
    adk_available: bool
    model: str
    provider: str
    reason: Optional[str] = None


class WrapRescueBlocker(BaseModel):
    source: Literal["discrepancy", "unacknowledged_requirement"]
    source_key: str
    production_id: str
    shoot_day: str
    target_type: str
    target_id: str
    target_label: str
    title: str
    description: str
    priority: Literal["low", "medium", "high", "critical"]
    category: Literal["sound", "vfx", "edit", "color", "reshoot", "legal", "general"]
    assigned_to: str
    status: Literal["open", "in_progress", "blocked"]
    severity: str
    score: float
    age_hours: Optional[float] = None
    missing_acknowledgement: bool = False
    evidence: Dict[str, Any] = Field(default_factory=dict)


class RequirementAction(BaseModel):
    action: Literal["created", "updated", "unchanged"]
    requirement_id: str
    blocker_source: str
    target_label: str
    assigned_to: str
    status: str
    priority: str


class WrapRescueResult(BaseModel):
    production_id: str
    shoot_day: str
    actor: str
    mcp_status: ClickHouseMCPStatus
    gemini_status: GeminiEnterpriseStatus
    steps: List[AgentStep]
    tool_calls: List[ToolCallTrace]
    blockers: List[WrapRescueBlocker]
    requirement_actions: List[RequirementAction]
    final_memo: str
    generated_at: str


class ClickHouseMCPClient(Protocol):
    async def status(self) -> ClickHouseMCPStatus:
        """Returns whether the official MCP server can be reached."""

    async def list_tables(self, db: str) -> tuple[Any, ToolCallTrace]:
        """Calls the official list_tables tool."""

    async def run_query(self, query: str) -> tuple[Any, ToolCallTrace]:
        """Calls the official run_query tool."""

    async def get_total_requirements_by_day_and_role(self, production_id: str) -> tuple[Any, ToolCallTrace]:
        """Query showing Total requirements by Day and Role."""

    async def get_unacknowledged_requirements_blocking_wrap(self, production_id: str, shoot_day: str) -> tuple[Any, ToolCallTrace]:
        """Query showing Count of unacknowledged requirements blocking wrap."""


def _mcp_package_installed() -> bool:
    return importlib.util.find_spec("mcp_clickhouse") is not None


def _jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _unwrap_mcp_result(payload: Dict[str, Any]) -> Any:
    if "error" in payload:
        message = payload["error"].get("message") if isinstance(payload["error"], dict) else payload["error"]
        raise RuntimeError(str(message))

    result = payload.get("result", payload)
    if isinstance(result, dict):
        if "structuredContent" in result:
            return _jsonish(result["structuredContent"])
        content = result.get("content")
        if isinstance(content, list) and content:
            parts = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
            if parts:
                return _jsonish("\n".join(parts))
    return _jsonish(result)


def _mcp_response_json(response: httpx.Response) -> Dict[str, Any]:
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" not in content_type:
        parsed = response.json()
        return parsed if isinstance(parsed, dict) else {"result": parsed}

    for line in response.text.splitlines():
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if not data or data == "[DONE]":
            continue
        parsed = json.loads(data)
        return parsed if isinstance(parsed, dict) else {"result": parsed}
    raise RuntimeError("MCP server returned an empty event stream.")


def _coerce_rows(result: Any) -> List[Dict[str, Any]]:
    result = _jsonish(result)
    if isinstance(result, list):
        return [row for row in result if isinstance(row, dict)]
    if isinstance(result, dict):
        for key in ("rows", "data", "result", "results"):
            nested = result.get(key)
            if isinstance(nested, list):
                return [row for row in nested if isinstance(row, dict)]
        if all(isinstance(v, (str, int, float, bool, type(None), list, dict)) for v in result.values()):
            return [result]
    return []


def _literal(value: str) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


class HTTPClickHouseMCPClient:
    """
    Minimal MCP-over-HTTP client for the official ClickHouse MCP server.

    The server itself is the official partner component; this client only
    performs the JSON-RPC calls the app needs for the demo workflow.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.url = (url or os.environ.get("CLICKHOUSE_MCP_URL", "")).strip()
        self.token = token if token is not None else os.environ.get("CLICKHOUSE_MCP_AUTH_TOKEN", "")
        self.timeout = timeout or float(os.environ.get("CLICKHOUSE_MCP_TIMEOUT", "10"))
        self._session_id: Optional[str] = None
        self._initialized = False

    def _health_url(self) -> Optional[str]:
        if not self.url:
            return None
        base = self.url.rstrip("/")
        if base.endswith("/mcp"):
            base = base[:-4]
        return f"{base}/health"

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json, text/event-stream"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    async def status(self) -> ClickHouseMCPStatus:
        health_url = self._health_url()
        if not self.url:
            return ClickHouseMCPStatus(
                configured=False,
                available=False,
                package_installed=_mcp_package_installed(),
                reason="CLICKHOUSE_MCP_URL is not set.",
            )
        if health_url is None:
            return ClickHouseMCPStatus(
                configured=True,
                available=False,
                server_url=self.url,
                package_installed=_mcp_package_installed(),
                reason="Could not derive the MCP health endpoint.",
            )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(health_url, headers=self._headers())
                response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - status must explain every failed transport
            return ClickHouseMCPStatus(
                configured=True,
                available=False,
                server_url=self.url,
                health_url=health_url,
                package_installed=_mcp_package_installed(),
                reason=str(exc),
            )

        return ClickHouseMCPStatus(
            configured=True,
            available=True,
            server_url=self.url,
            health_url=health_url,
            package_installed=_mcp_package_installed(),
        )

    async def _post_rpc(self, method: str, params: Dict[str, Any], expect_response: bool = True) -> Any:
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params}
        if expect_response:
            payload["id"] = f"cinespine-{uuid.uuid4().hex[:12]}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.url, json=payload, headers=self._headers())
            if "mcp-session-id" in response.headers:
                self._session_id = response.headers["mcp-session-id"]
            response.raise_for_status()
            if not expect_response or not response.content:
                return None
            return _unwrap_mcp_result(_mcp_response_json(response))

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        await self._post_rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "cinespine-wrap-rescue", "version": "0.1.0"},
            },
        )
        try:
            await self._post_rpc("notifications/initialized", {}, expect_response=False)
        except Exception as exc:  # noqa: BLE001 - older transports do not require the notification
            logger.debug("ClickHouse MCP initialized notification was not accepted: %s", exc)
        self._initialized = True

    async def _call_tool(self, name: str, arguments: Dict[str, Any]) -> tuple[Any, ToolCallTrace]:
        trace = ToolCallTrace(tool=name, arguments=arguments, ok=False)
        try:
            await self._ensure_initialized()
            result = await self._post_rpc(
                "tools/call",
                {"name": name, "arguments": arguments},
            )
            rows = _coerce_rows(result)
            trace.ok = True
            trace.rows = len(rows)
            return result, trace
        except Exception as exc:  # noqa: BLE001 - the agent degrades and reports the broken tool
            trace.error = str(exc)
            return [], trace

    async def list_tables(self, db: str) -> tuple[Any, ToolCallTrace]:
        return await self._call_tool(
            "list_tables",
            {"database": db, "page_size": 50, "include_detailed_columns": False},
        )

    async def run_query(self, query: str) -> tuple[Any, ToolCallTrace]:
        return await self._call_tool("run_query", {"query": query})

    async def get_total_requirements_by_day_and_role(self, production_id: str) -> tuple[Any, ToolCallTrace]:
        query = f"""
            WITH latest AS (
                SELECT requirement_id,
                       production_id,
                       argMax(assigned_to, created_at) AS assigned_to
                FROM {database()}.requirement_events
                WHERE production_id = {_literal(production_id)}
                GROUP BY requirement_id, production_id
            ),
            created_on_day AS (
                SELECT JSONExtractString(payload_json, 'requirement_id') AS requirement_id,
                       argMax(shoot_day, created_at) AS shoot_day
                FROM {database()}.production_events
                WHERE production_id = {_literal(production_id)}
                  AND doc_type = 'requirement_event'
                  AND entity_type = 'requirement'
                  AND JSONExtractString(metadata_json, 'action') IN ('created', 'created_by_wrap_rescue')
                GROUP BY requirement_id
            )
            SELECT c.shoot_day AS shoot_day,
                   l.assigned_to AS role,
                   COUNT(*) AS total_requirements
            FROM latest AS l
            JOIN created_on_day AS c ON l.requirement_id = c.requirement_id
            GROUP BY shoot_day, role
            ORDER BY shoot_day ASC, role ASC
        """
        return await self._call_tool("run_query", {"query": query})

    async def get_unacknowledged_requirements_blocking_wrap(self, production_id: str, shoot_day: str) -> tuple[Any, ToolCallTrace]:
        # Reuse the existing _unacknowledged_query to count blocked items
        base_query = _unacknowledged_query(production_id, shoot_day)
        query = f"SELECT count(*) as count FROM ({base_query})"
        return await self._call_tool("run_query", {"query": query})


class GeminiEnterpriseMemoRuntime:
    """Gemini memo stage with explicit ADK readiness reporting."""

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.environ.get("CINESPINE_WRAP_RESCUE_MODEL", "").strip()

    def status(self) -> GeminiEnterpriseStatus:
        try:
            from backend.app.integrations import google_cloud
        except Exception as exc:  # noqa: BLE001 - status should survive import trouble
            return GeminiEnterpriseStatus(
                configured=False,
                genai_available=False,
                adk_available=False,
                model=self.model or "no model called",
                provider="Google Cloud Agent Platform unavailable",
                reason=str(exc),
            )

        configured = bool(
            os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").strip().upper() == "TRUE"
        )
        model = self.model or get_optimal_gemini_model("", "simple")
        adk_available = importlib.util.find_spec("google.adk") is not None
        reason = None if configured else "No Gemini or Vertex AI credentials are configured."
        return GeminiEnterpriseStatus(
            configured=configured,
            genai_available=google_cloud.GENAI_AVAILABLE,
            adk_available=adk_available,
            model=model if configured and google_cloud.GENAI_AVAILABLE else "deterministic fallback",
            provider="Gemini Enterprise Agent Platform" if adk_available else "Google GenAI SDK",
            reason=reason,
        )

    async def draft_memo(
        self,
        production_id: str,
        shoot_day: str,
        blockers: List[WrapRescueBlocker],
        actions: List[RequirementAction],
        source_available: bool = True,
    ) -> tuple[str, AgentStep]:
        status = self.status()
        if not source_available:
            return (
                _deterministic_memo(
                    production_id, shoot_day, blockers, actions, source_available=False
                ),
                AgentStep(
                    step="gemini_enterprise_memo",
                    status="warning",
                    detail=(
                        "ClickHouse MCP did not return a complete row set; skipped Gemini "
                        "drafting and produced an unavailable handoff memo."
                    ),
                ),
            )
        if not status.configured or not status.genai_available:
            return (
                _deterministic_memo(production_id, shoot_day, blockers, actions),
                AgentStep(
                    step="gemini_enterprise_memo",
                    status="warning",
                    detail="Gemini was not configured; produced a deterministic handoff memo.",
                ),
            )

        prompt = _memo_prompt(production_id, shoot_day, blockers, actions)

        if status.adk_available:
            try:
                memo = await self._draft_with_adk(status.model, prompt)
            except Exception as exc:  # noqa: BLE001 - the rescue workflow should still finish
                logger.warning("Gemini ADK memo generation failed: %s", exc)
            else:
                if memo:
                    return (
                        memo,
                        AgentStep(
                            step="gemini_enterprise_adk_memo",
                            status="ok",
                            detail=(
                                "Google ADK ran the Gemini Enterprise memo agent from the "
                                f"{len(blockers)} ranked ClickHouse rows."
                            ),
                        ),
                    )

        def call_model() -> str:
            from backend.app.integrations import google_cloud

            if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").strip().upper() == "TRUE":
                client = google_cloud.genai.Client(
                    vertexai=True,
                    project=os.getenv("GOOGLE_CLOUD_PROJECT"),
                    location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
                )
            else:
                client = google_cloud.genai.Client(
                    api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                )
            response = client.models.generate_content(
                model=status.model,
                contents=prompt,
                config={"temperature": 0.0},
            )
            return (response.text or "").strip()

        try:
            memo = await asyncio.to_thread(call_model)
        except Exception as exc:  # noqa: BLE001 - the rescue workflow should still finish
            logger.warning("Gemini memo generation failed: %s", exc)
            return (
                _deterministic_memo(production_id, shoot_day, blockers, actions),
                AgentStep(
                    step="gemini_enterprise_memo",
                    status="warning",
                    detail=f"Gemini failed; deterministic memo used instead: {exc}",
                ),
            )

        if not memo:
            return (
                _deterministic_memo(production_id, shoot_day, blockers, actions),
                AgentStep(
                    step="gemini_enterprise_memo",
                    status="warning",
                    detail="Gemini returned no text; deterministic memo used instead.",
                ),
            )
        return (
            memo,
            AgentStep(
                step="gemini_enterprise_memo",
                status="warning" if not status.adk_available else "ok",
                detail=(
                    f"Gemini drafted the handoff memo from {len(blockers)} ranked rows."
                    if status.adk_available
                    else "google-adk is not installed; memo used the Google GenAI SDK fallback."
                ),
            ),
        )

    async def _draft_with_adk(self, model: str, prompt: str) -> str:
        from google.adk.agents import LlmAgent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types as genai_types

        agent = LlmAgent(
            name="wrap_rescue_handoff_agent",
            model=model,
            instruction=(
                "Draft concise editorial handoff memos only from the JSON the user provides. "
                "Do not invent facts, names, files, slates, or departments."
            ),
        )
        app_name = "cinespine_wrap_rescue"
        user_id = "wrap_rescue"
        session_id = f"session_{uuid.uuid4().hex[:12]}"
        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        runner = Runner(
            agent=agent,
            app_name=app_name,
            session_service=session_service,
        )
        message = genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=prompt)],
        )

        final_text = ""
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=message,
        ):
            if not event.is_final_response() or not event.content:
                continue
            parts = event.content.parts or []
            final_text = "\n".join(
                part.text for part in parts
                if getattr(part, "text", None)
            ).strip()
        return final_text


def _memo_prompt(
    production_id: str,
    shoot_day: str,
    blockers: List[WrapRescueBlocker],
    actions: List[RequirementAction],
) -> str:
    rows = {
        "production_id": production_id,
        "shoot_day": shoot_day,
        "blockers": [b.model_dump() for b in blockers],
        "requirement_actions": [a.model_dump() for a in actions],
    }
    return (
        "You are CineSpine's Wrap Rescue Agent. Draft a concise editorial handoff memo "
        "using only this JSON. Do not invent facts, names, files, slates, or departments. "
        "Group by immediate risk and owner.\n\n"
        f"{json.dumps(rows, ensure_ascii=True)}"
    )


def _deterministic_memo(
    production_id: str,
    shoot_day: str,
    blockers: List[WrapRescueBlocker],
    actions: List[RequirementAction],
    source_available: bool = True,
) -> str:
    lines = [
        f"Wrap Rescue handoff for {production_id} Day {shoot_day}",
        "",
        (
            f"{len(blockers)} blocker candidates were ranked from ClickHouse-backed rows."
            if source_available
            else "ClickHouse MCP did not return a complete row set; no blockers were ranked."
        ),
        f"{len(actions)} requirement actions were recorded.",
    ]
    for blocker in blockers[:5]:
        lines.append(
            f"- {blocker.priority.upper()} {blocker.target_label}: "
            f"{blocker.title} -> {blocker.assigned_to}"
        )
    if not blockers and source_available:
        lines.append("- No active blocker rows were found for this day.")
    elif not blockers:
        lines.append("- ClickHouse MCP was unavailable or incomplete, so the agent stopped before action.")
    return "\n".join(lines)


def _severity(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value or "INFO").upper()


def _priority(severity: str) -> Literal["low", "medium", "high", "critical"]:
    if severity == "CRITICAL":
        return "critical"
    if severity == "WARNING":
        return "high"
    return "medium"


def _category(kind: str) -> Literal["sound", "vfx", "edit", "color", "reshoot", "legal", "general"]:
    upper = kind.upper()
    if "TIMECODE" in upper or "ROLL" in upper:
        return "sound"
    if "MEDIA" in upper or "OFFLOAD" in upper:
        return "edit"
    if "VFX" in upper:
        return "vfx"
    if "CIRCLED" in upper or "SLATE" in upper:
        return "edit"
    if "SCENE" in upper:
        return "reshoot"
    return "general"


def _assignee(kind: str, category: str) -> str:
    upper = kind.upper()
    if "OFFLOAD" in upper or "MEDIA" in upper:
        return "@dit"
    if category == "sound" or "TIMECODE" in upper:
        return "@sound_supervisor"
    if "CIRCLED" in upper or "SLATE" in upper:
        return "@script_supervisor"
    if category == "reshoot":
        return "@assistant_director"
    return "@assistant_editor"


def _target_type(entity_type: Any, kind: str) -> str:
    entity = str(entity_type or "").lower()
    if entity in {"scene", "shot", "take"}:
        return entity
    if "SCENE" in kind.upper():
        return "scene"
    if "SLATE" in kind.upper():
        return "shot"
    return "take"


def _hours_since(value: Any) -> Optional[float]:
    if not value:
        return None
    try:
        text = str(value)
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    seconds = max(0.0, (datetime.now(timezone.utc) - moment).total_seconds())
    return round(seconds / 3600, 1)


def _score(severity: str, age_hours: Optional[float], missing_ack: bool, source: str) -> float:
    base = {"CRITICAL": 90.0, "WARNING": 60.0, "INFO": 25.0}.get(severity, 25.0)
    if missing_ack:
        base += 20.0
    if age_hours is not None:
        base += min(age_hours / 24.0, 14.0)
    if source == "unacknowledged_requirement":
        base += 8.0
    return round(base, 2)


def _parse_witnesses(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = row.get("witnesses_json") or row.get("witnesses") or []
    parsed = _jsonish(raw)
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def blocker_from_discrepancy(row: Dict[str, Any]) -> WrapRescueBlocker:
    kind = _safe_text(row.get("discrepancy_type"), "DISCREPANCY")
    entity_id = _safe_text(row.get("entity_id"), "unknown")
    severity = _severity(row.get("severity"))
    priority = _priority(severity)
    category = _category(kind)
    target_type = _target_type(row.get("entity_type"), kind)
    production_id = _safe_text(row.get("production_id"))
    shoot_day = _safe_text(row.get("shoot_day"))
    source_key = f"discrepancy:{kind}:{entity_id}"
    age = _hours_since(row.get("created_at"))
    witnesses = _parse_witnesses(row)
    title = f"[Wrap Rescue] {kind.replace('_', ' ').title()} on {entity_id}"
    description = (
        f"{SOURCE_MARKER} {source_key}\n"
        f"{_safe_text(row.get('description'), 'ClickHouse flagged this discrepancy.')}\n\n"
        f"Witness rows: {len(witnesses)}. Raised from ClickHouse MCP audit_discrepancies."
    )
    return WrapRescueBlocker(
        source="discrepancy",
        source_key=source_key,
        production_id=production_id,
        shoot_day=shoot_day,
        target_type=target_type,
        target_id=entity_id,
        target_label=f"{target_type.capitalize()} {entity_id}",
        title=title,
        description=description,
        priority=priority,
        category=category,
        assigned_to=_assignee(kind, category),
        status="open",
        severity=severity,
        score=_score(severity, age, False, "discrepancy"),
        age_hours=age,
        evidence={
            "discrepancy_id": str(row.get("discrepancy_id") or ""),
            "discrepancy_type": kind,
            "witness_count": len(witnesses),
        },
    )


def blocker_from_unacknowledged(row: Dict[str, Any]) -> WrapRescueBlocker:
    requirement_id = _safe_text(row.get("requirement_id"))
    priority = str(row.get("priority") or "medium").lower()
    if priority not in {"low", "medium", "high", "critical"}:
        priority = "medium"
    status = str(row.get("status") or "open").lower()
    if status not in {"open", "in_progress", "blocked"}:
        status = "open"
    severity = "CRITICAL" if priority == "critical" else "WARNING"
    age = _hours_since(row.get("raised_at"))
    source_key = f"requirement:{requirement_id}:unacknowledged"
    assigned_to = _safe_text(row.get("assigned_to"), "@assistant_editor")
    if not assigned_to.startswith("@"):
        assigned_to = f"@{assigned_to}"
    production_id = _safe_text(row.get("production_id"))
    shoot_day = _safe_text(row.get("shoot_day"))
    return WrapRescueBlocker(
        source="unacknowledged_requirement",
        source_key=source_key,
        production_id=production_id,
        shoot_day=shoot_day,
        target_type="take",
        target_id=requirement_id,
        target_label=f"Requirement {requirement_id}",
        title=f"[Wrap Rescue] {requirement_id} has not been acknowledged",
        description=(
            f"{SOURCE_MARKER} {source_key}\n"
            "The requirement is outstanding and has no acknowledgement activity in ClickHouse."
        ),
        priority=priority,  # type: ignore[arg-type]
        category="general",
        assigned_to=assigned_to,
        status="blocked" if priority in {"critical", "high"} else status,  # type: ignore[arg-type]
        severity=severity,
        score=_score(severity, age, True, "unacknowledged_requirement"),
        age_hours=age,
        missing_acknowledgement=True,
        evidence={
            "requirement_id": requirement_id,
            "views": int(row.get("views") or 0),
            "acknowledgements": int(row.get("acknowledgements") or 0),
        },
    )


def rank_blockers(
    discrepancy_rows: List[Dict[str, Any]],
    unacknowledged_rows: List[Dict[str, Any]],
    production_id: str,
    shoot_day: str,
) -> List[WrapRescueBlocker]:
    blockers: List[WrapRescueBlocker] = []
    for row in discrepancy_rows:
        if int(row.get("is_resolved") or 0):
            continue
        enriched = {**row, "production_id": row.get("production_id") or production_id}
        enriched["shoot_day"] = str(enriched.get("shoot_day") or shoot_day)
        try:
            blockers.append(blocker_from_discrepancy(enriched))
        except ValidationError as exc:
            logger.warning("Skipping invalid discrepancy blocker row: %s", exc)

    for row in unacknowledged_rows:
        enriched = {**row, "production_id": row.get("production_id") or production_id}
        enriched["shoot_day"] = str(enriched.get("shoot_day") or shoot_day)
        try:
            blockers.append(blocker_from_unacknowledged(enriched))
        except ValidationError as exc:
            logger.warning("Skipping invalid unacknowledged requirement row: %s", exc)

    return sorted(
        blockers,
        key=lambda b: (-b.score, b.priority, b.target_label, b.source_key),
    )


from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from backend.app.agents.adk_helpers import tool

class WrapRescueAgent(LlmAgent):
    model_config = {"extra": "allow", "arbitrary_types_allowed": True}

    def __init__(
        self,
        spine_writer: SpineWriter,
        reconciler: ReconciliationEngine,
        legacy_mcp_server: Any,
        clickhouse_mcp: Optional[ClickHouseMCPClient] = None,
        gemini_runtime: Optional[GeminiEnterpriseMemoRuntime] = None,
    ):
        super().__init__(
            name="wrap_rescue_agent",
            instruction="Orchestrate wrap rescue checks.",
            tools=[
                self._refresh_analytical_spine, 
                self._query_clickhouse_mcp, 
                self._apply_requirement_actions,
                self.get_total_requirements_by_day_and_role,
                self.get_unacknowledged_requirements_blocking_wrap
            ]
        )
        self.spine_writer = spine_writer
        self.reconciler = reconciler
        self.legacy_mcp_server = legacy_mcp_server
        self.clickhouse_mcp = clickhouse_mcp or HTTPClickHouseMCPClient()
        self.gemini_runtime = gemini_runtime or GeminiEnterpriseMemoRuntime()

    async def run(
        self,
        production_id: str,
        shoot_day: str,
        actor: str = WRAP_RESCUE_ACTOR,
        max_blockers: int = 5,
    ) -> WrapRescueResult:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if api_key:
            try:
                session = InMemorySessionService()
                runner = Runner(agent=self, session_service=session, app_name="cinespine")
            except Exception:  # noqa: S110
                pass

        actor = actor if actor.startswith("@") else f"@{actor}"
        steps: List[AgentStep] = []
        tool_calls: List[ToolCallTrace] = []

        projected = self._refresh_analytical_spine(production_id, shoot_day)
        steps.append(AgentStep(
            step="project_clickhouse_indexes",
            status="ok",
            detail=f"Projected {projected} analytical rows before the agent queried ClickHouse.",
        ))

        mcp_status = await self.clickhouse_mcp.status()
        steps.append(AgentStep(
            step="connect_mcp_clickhouse",
            status="ok" if mcp_status.available else "error",
            detail=mcp_status.reason or "Official ClickHouse MCP server answered its health check.",
        ))

        blockers: List[WrapRescueBlocker] = []
        requirement_actions: List[RequirementAction] = []
        clickhouse_source_available = False
        if mcp_status.available:
            rows, calls = await self._query_clickhouse_mcp(production_id, shoot_day)
            discrepancy_rows, unacknowledged_rows = rows
            tool_calls.extend(calls)
            steps.extend(AgentStep(
                step=f"mcp_tool_{call.tool}",
                status="ok" if call.ok else "error",
                detail=f"{call.tool} returned {call.rows} row(s)." if call.ok else call.error or "",
                tool_call=call,
            ) for call in calls)
            if all(call.ok for call in calls):
                clickhouse_source_available = True
                blockers = rank_blockers(
                    discrepancy_rows, unacknowledged_rows, production_id, shoot_day,
                )
                blockers = blockers[:max(1, max_blockers)]
                steps.append(AgentStep(
                    step="rank_blockers",
                    status="ok",
                    detail=(
                        f"Ranked {len(blockers)} blocker candidate(s) by severity, "
                        "age, and acknowledgement."
                    ),
                ))

                requirement_actions = self._apply_requirement_actions(blockers, actor)
                steps.append(AgentStep(
                    step="write_requirements",
                    status="ok",
                    detail=f"Recorded {len(requirement_actions)} requirement action(s).",
                ))
            else:
                steps.append(AgentStep(
                    step="stop_before_mutation",
                    status="error",
                    detail=(
                        "At least one official ClickHouse MCP tool call failed, so the "
                        "agent did not rank or mutate requirements."
                    ),
                ))
        else:
            steps.append(AgentStep(
                step="stop_before_mutation",
                status="error",
                detail=(
                    "Official ClickHouse MCP is unavailable, so the agent did not "
                    "rank or mutate requirements."
                ),
            ))

        memo, memo_step = await self.gemini_runtime.draft_memo(
            production_id,
            shoot_day,
            blockers,
            requirement_actions,
            source_available=clickhouse_source_available,
        )
        steps.append(memo_step)

        result = WrapRescueResult(
            production_id=production_id,
            shoot_day=shoot_day,
            actor=actor,
            mcp_status=mcp_status,
            gemini_status=self.gemini_runtime.status(),
            steps=steps,
            tool_calls=tool_calls,
            blockers=blockers,
            requirement_actions=requirement_actions,
            final_memo=memo,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._record_agent_event(result)
        analytics.capture(actor, "wrap_rescue_agent_run", {
            "production_id": production_id,
            "shoot_day": shoot_day,
            "mcp_available": mcp_status.available,
            "blockers": len(blockers),
            "requirement_actions": len(requirement_actions),
        })
        try:
            cloud_logger = AgentCloudLogger()
            cloud_logger.log_agent_run(
                agent_name="WrapRescueAgent",
                action="agent_run_completed",
                payload=result.model_dump()
            )
        except Exception as e:
            logger.warning("Failed to ship trace to Cloud Logging: %s", e)
        return result

    @tool
    def _refresh_analytical_spine(self, production_id: str, shoot_day: str) -> int:
        self.spine_writer.flush_events()
        rows = self.spine_writer.project_takes(production_id)
        discrepancies = self.legacy_mcp_server.query_production_discrepancies(
            production_id=production_id,
            shoot_day=shoot_day,
        )
        rows += self.spine_writer.project_discrepancies(discrepancies)
        return rows

    @tool
    async def get_total_requirements_by_day_and_role(self, production_id: str) -> tuple[List[Dict[str, Any]], ToolCallTrace]:
        result, call = await self.clickhouse_mcp.get_total_requirements_by_day_and_role(production_id)
        return _coerce_rows(result), call

    @tool
    async def get_unacknowledged_requirements_blocking_wrap(self, production_id: str, shoot_day: str) -> tuple[List[Dict[str, Any]], ToolCallTrace]:
        result, call = await self.clickhouse_mcp.get_unacknowledged_requirements_blocking_wrap(production_id, shoot_day)
        return _coerce_rows(result), call

    @tool
    async def _query_clickhouse_mcp(
        self,
        production_id: str,
        shoot_day: str,
    ) -> tuple[tuple[List[Dict[str, Any]], List[Dict[str, Any]]], List[ToolCallTrace]]:
        calls: List[ToolCallTrace] = []
        _, list_call = await self.clickhouse_mcp.list_tables(database())
        calls.append(list_call)

        discrepancy_result, discrepancy_call = await self.clickhouse_mcp.run_query(
            _discrepancy_query(production_id, shoot_day)
        )
        calls.append(discrepancy_call)

        unack_result, unack_call = await self.clickhouse_mcp.run_query(
            _unacknowledged_query(production_id, shoot_day)
        )
        calls.append(unack_call)

        # Expanded Analytical Queries for ADK demonstration
        _, throughput_call = await self.clickhouse_mcp.run_query(
            _take_throughput_query(production_id, shoot_day)
        )
        calls.append(throughput_call)

        _, age_call = await self.clickhouse_mcp.run_query(
            _discrepancy_age_query(production_id, shoot_day)
        )
        calls.append(age_call)

        _, agreement_call = await self.clickhouse_mcp.run_query(
            _sound_camera_agreement_query(production_id, shoot_day)
        )
        calls.append(agreement_call)

        return (_coerce_rows(discrepancy_result), _coerce_rows(unack_result)), calls

    @tool
    def _apply_requirement_actions(
        self,
        blockers: List[WrapRescueBlocker],
        actor: str,
    ) -> List[RequirementAction]:
        actions: List[RequirementAction] = []
        existing = [
            row for row in self.spine_writer.list_requirements()
            if row.get("status") != "resolved"
        ]

        for blocker in blockers:
            current = self._find_existing_requirement(existing, blocker)
            if blocker.source == "unacknowledged_requirement" and current:
                action = self._block_existing_requirement(current, blocker, actor)
            elif current:
                action = self._sync_requirement(current, blocker, actor)
            else:
                created = self._create_requirement(blocker, actor)
                existing.append(created)
                action = RequirementAction(
                    action="created",
                    requirement_id=created["requirement_id"],
                    blocker_source=blocker.source_key,
                    target_label=created["target_label"],
                    assigned_to=created["assigned_to"],
                    status=created["status"],
                    priority=created["priority"],
                )
            actions.append(action)
        return actions

    def _find_existing_requirement(
        self,
        existing: List[Dict[str, Any]],
        blocker: WrapRescueBlocker,
    ) -> Optional[Dict[str, Any]]:
        if blocker.source == "unacknowledged_requirement":
            return self.spine_writer.get_requirement(blocker.target_id)
        for row in existing:
            if row.get("production_id") != blocker.production_id:
                continue
            if row.get("target_type") != blocker.target_type:
                continue
            if str(row.get("target_id")) != blocker.target_id:
                continue
            if f"{SOURCE_MARKER} {blocker.source_key}" in (row.get("description") or ""):
                return row
        return None

    def _sync_requirement(
        self,
        current: Dict[str, Any],
        blocker: WrapRescueBlocker,
        actor: str,
    ) -> RequirementAction:
        updates = {
            "description": blocker.description,
            "priority": blocker.priority,
            "category": blocker.category,
            "assigned_to": blocker.assigned_to,
            "status": blocker.status,
            "target_label": blocker.target_label,
        }
        updated = self.spine_writer.update_requirement(
            current["requirement_id"], updates, actor=actor
        ) or current
        changed = updated != current
        if changed:
            self._notify_requirement_move(current, updated, actor)
        return RequirementAction(
            action="updated" if changed else "unchanged",
            requirement_id=updated["requirement_id"],
            blocker_source=blocker.source_key,
            target_label=updated["target_label"],
            assigned_to=updated["assigned_to"],
            status=updated["status"],
            priority=updated["priority"],
        )

    def _block_existing_requirement(
        self,
        current: Dict[str, Any],
        blocker: WrapRescueBlocker,
        actor: str,
    ) -> RequirementAction:
        updates: Dict[str, Any] = {}
        if blocker.status == "blocked" and current.get("status") != "blocked":
            updates["status"] = "blocked"
        if blocker.assigned_to and current.get("assigned_to") != blocker.assigned_to:
            updates["assigned_to"] = blocker.assigned_to
        updated = self.spine_writer.update_requirement(
            current["requirement_id"], updates, actor=actor
        ) if updates else current
        if updates:
            self._notify_requirement_move(current, updated, actor)
        return RequirementAction(
            action="updated" if updates else "unchanged",
            requirement_id=updated["requirement_id"],
            blocker_source=blocker.source_key,
            target_label=updated["target_label"],
            assigned_to=updated["assigned_to"],
            status=updated["status"],
            priority=updated["priority"],
        )

    def _notify_requirement_move(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        actor: str,
    ) -> None:
        def notify(recipient: Optional[str], kind: str, message: str) -> None:
            if not recipient or recipient.lower() == actor.lower():
                return
            self.spine_writer.create_notification({
                "production_id": after["production_id"],
                "recipient_handle": recipient,
                "actor_handle": actor,
                "notification_type": kind,
                "requirement_id": after["requirement_id"],
                "title": f"Wrap Rescue: {after['target_label']}",
                "message": message,
                "target_type": after["target_type"],
                "target_id": after["target_id"],
                "target_label": after["target_label"],
            })

        if after.get("assigned_to") and after.get("assigned_to") != before.get("assigned_to"):
            notify(
                after.get("assigned_to"),
                "ASSIGNED",
                f"{actor} handed you this {after['priority']} requirement: {after['title']}",
            )
        if after.get("status") and after.get("status") != before.get("status"):
            notify(
                after.get("created_by"),
                "STATUS_CHANGED",
                f"{actor} moved this from {before.get('status')} to {after['status']}: {after['title']}",
            )

    def _create_requirement(self, blocker: WrapRescueBlocker, actor: str) -> Dict[str, Any]:
        created = self.spine_writer.create_requirement({
            "production_id": blocker.production_id,
            "shoot_day": blocker.shoot_day,
            "target_type": blocker.target_type,
            "target_id": blocker.target_id,
            "target_label": blocker.target_label,
            "title": blocker.title,
            "description": blocker.description,
            "priority": blocker.priority,
            "category": blocker.category,
            "created_by": actor,
            "assigned_to": blocker.assigned_to,
            "status": blocker.status,
        })
        self.spine_writer.append_event({
            "event_id": str(uuid.uuid4()),
            "production_id": created["production_id"],
            "shoot_day": created["shoot_day"],
            "axis": "intent",
            "department": "editorial",
            "doc_type": "requirement_event",
            "entity_type": "requirement",
            "payload": created,
            "metadata": {
                "requirement_id": created["requirement_id"],
                "action": "created_by_wrap_rescue",
                "assigned_to": created["assigned_to"],
                "created_by": created["created_by"],
            },
            "timestamp": created["created_at"],
        })
        if created["assigned_to"]:
            self.spine_writer.create_notification({
                "production_id": created["production_id"],
                "recipient_handle": created["assigned_to"],
                "actor_handle": actor,
                "notification_type": "ASSIGNED",
                "requirement_id": created["requirement_id"],
                "title": f"Wrap Rescue: {created['target_label']}",
                "message": f"{actor} assigned {created['priority']} work from ClickHouse.",
                "target_type": created["target_type"],
                "target_id": created["target_id"],
                "target_label": created["target_label"],
            })
        return created

    def _record_agent_event(self, result: WrapRescueResult) -> None:
        self.spine_writer.append_event({
            "event_id": str(uuid.uuid4()),
            "production_id": result.production_id,
            "shoot_day": result.shoot_day,
            "axis": "intent",
            "department": "editorial",
            "doc_type": "agent_run",
            "entity_type": "wrap_rescue_run",
            "payload": {
                "blockers": [b.model_dump() for b in result.blockers],
                "requirement_actions": [a.model_dump() for a in result.requirement_actions],
                "mcp_available": result.mcp_status.available,
                "gemini_provider": result.gemini_status.provider,
            },
            "metadata": {
                "actor": result.actor,
                "tool_calls": len(result.tool_calls),
                "agent": "wrap_rescue",
            },
            "timestamp": result.generated_at,
        })
        self.spine_writer.flush_events()


def _discrepancy_query(production_id: str, shoot_day: str) -> str:
    return f"""
        SELECT discrepancy_id, production_id, shoot_day, entity_type, entity_id,
               discrepancy_type, severity, description, witnesses_json,
               is_resolved, created_at
        FROM {database()}.audit_discrepancies
        WHERE production_id = {_literal(production_id)}
          AND shoot_day = {_literal(shoot_day)}
          AND is_resolved = 0
        ORDER BY severity ASC, created_at ASC
        LIMIT 50
    """


def _unacknowledged_query(production_id: str, shoot_day: str) -> str:
    return f"""
        WITH created_on_day AS (
            SELECT JSONExtractString(payload_json, 'requirement_id') AS requirement_id,
                   argMax(shoot_day, created_at) AS shoot_day
            FROM {database()}.production_events
            WHERE production_id = {_literal(production_id)}
              AND doc_type = 'requirement_event'
              AND entity_type = 'requirement'
              AND JSONExtractString(metadata_json, 'action') IN ('created', 'created_by_wrap_rescue')
            GROUP BY requirement_id
        ),
        latest AS (
            SELECT requirement_id,
                   production_id,
                   argMax(status, created_at) AS status,
                   argMax(priority, created_at) AS priority,
                   argMax(assigned_to, created_at) AS assigned_to,
                   min(created_at) AS raised_at
            FROM {database()}.requirement_events
            WHERE production_id = {_literal(production_id)}
            GROUP BY requirement_id, production_id
        )
        SELECT l.requirement_id AS requirement_id,
               l.production_id AS production_id,
               c.shoot_day AS shoot_day,
               l.status AS status,
               l.priority AS priority,
               l.assigned_to AS assigned_to,
               l.raised_at AS raised_at,
               uniqExactIf(a.event_id, a.action = 'viewed') AS views,
               uniqExactIf(a.event_id, a.action = 'acknowledged') AS acknowledgements
        FROM latest AS l
        LEFT JOIN {database()}.user_activity AS a
          ON a.production_id = l.production_id
         AND a.target_type = 'requirement'
         AND a.target_id = l.requirement_id
        INNER JOIN created_on_day AS c
          ON c.requirement_id = l.requirement_id
        WHERE l.status IN ('open', 'in_progress', 'blocked')
          AND c.shoot_day = {_literal(shoot_day)}
        GROUP BY l.requirement_id, l.production_id, l.status, l.priority,
                 l.assigned_to, l.raised_at, c.shoot_day
        HAVING acknowledgements = 0
        ORDER BY l.raised_at ASC
        LIMIT 50
    """


def _take_throughput_query(production_id: str, shoot_day: str) -> str:
    return f"""
        SELECT JSONExtractString(metadata_json, 'camera_roll') AS camera_roll,
               count() AS takes,
               min(created_at) AS first_take,
               max(created_at) AS last_take,
               dateDiff('minute', min(created_at), max(created_at)) AS duration_minutes
        FROM {database()}.production_events
        WHERE production_id = {_literal(production_id)}
          AND shoot_day = {_literal(shoot_day)}
          AND doc_type = 'take'
          AND JSONHas(metadata_json, 'camera_roll')
        GROUP BY camera_roll
        ORDER BY camera_roll ASC
    """


def _discrepancy_age_query(production_id: str, shoot_day: str) -> str:
    return f"""
        SELECT discrepancy_type,
               severity,
               count() AS open_discrepancies,
               avg(dateDiff('hour', created_at, now())) AS avg_age_hours,
               max(dateDiff('hour', created_at, now())) AS max_age_hours
        FROM {database()}.audit_discrepancies
        WHERE production_id = {_literal(production_id)}
          AND shoot_day = {_literal(shoot_day)}
          AND is_resolved = 0
        GROUP BY discrepancy_type, severity
        ORDER BY severity ASC, avg_age_hours DESC
    """


def _sound_camera_agreement_query(production_id: str, shoot_day: str) -> str:
    return f"""
        SELECT JSONExtractString(metadata_json, 'sound_roll') AS sound_roll,
               JSONExtractString(metadata_json, 'camera_roll') AS camera_roll,
               count() AS matched_takes
        FROM {database()}.production_events
        WHERE production_id = {_literal(production_id)}
          AND shoot_day = {_literal(shoot_day)}
          AND doc_type = 'take'
          AND JSONHas(metadata_json, 'sound_roll')
          AND JSONHas(metadata_json, 'camera_roll')
        GROUP BY sound_roll, camera_roll
        ORDER BY matched_takes DESC
    """
