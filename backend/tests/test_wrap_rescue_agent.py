import asyncio
from datetime import datetime, timedelta, timezone

import httpx
from starlette.testclient import TestClient

from backend.app.agents.wrap_rescue import (
    ClickHouseMCPStatus,
    GeminiEnterpriseStatus,
    ToolCallTrace,
    WrapRescueAgent,
    WrapRescueResult,
    _mcp_response_json,
    _RUN_QUERY_TOOL,
    _unwrap_mcp_result,
    rank_blockers,
)
from backend.app.main import app
from backend.app.reconciliation.engine import ReconciliationEngine
from backend.app.spine.writer import SpineWriter


def _ago(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def test_ranks_critical_and_unacknowledged_blockers_first():
    blockers = rank_blockers(
        discrepancy_rows=[
            {
                "production_id": "PROD",
                "shoot_day": "31",
                "entity_type": "take",
                "entity_id": "27/7 Take 3",
                "discrepancy_type": "CIRCLED_TAKE_MISMATCH",
                "severity": "WARNING",
                "description": "Script and camera disagree.",
                "created_at": _ago(1),
            },
            {
                "production_id": "PROD",
                "shoot_day": "31",
                "entity_type": "take",
                "entity_id": "28/1 Take 1",
                "discrepancy_type": "PAPERWORK_WITHOUT_MEDIA",
                "severity": "CRITICAL",
                "description": "No verified media exists.",
                "created_at": _ago(2),
            },
        ],
        unacknowledged_rows=[
            {
                "production_id": "PROD",
                "shoot_day": "31",
                "requirement_id": "req_blocked",
                "status": "open",
                "priority": "high",
                "assigned_to": "@sound_supervisor",
                "raised_at": _ago(72),
                "views": 0,
                "acknowledgements": 0,
            }
        ],
        production_id="PROD",
        shoot_day="31",
    )

    assert blockers[0].source == "unacknowledged_requirement"
    assert blockers[0].missing_acknowledgement is True
    assert blockers[1].severity == "CRITICAL"
    assert blockers[1].assigned_to == "@dit"
    assert blockers[2].category == "edit"


class FakeClickHouseMCP:
    """
    Stands in for the MCP client, and labels its traces with the tool name the
    real client sends.

    The label used to be spelled out here as `run_query`, which the official
    server has never exported. The real client asked for that name, got
    `Unknown tool` back for every query it ever made, and this suite stayed
    green throughout -- it was asserting against a name only the fake used.
    Taking it from the same constant is what stops the two drifting again.
    """

    def __init__(self):
        self.queries = []

    async def status(self):
        return ClickHouseMCPStatus(
            configured=True,
            available=True,
            server_url="http://mcp.example/mcp",
            health_url="http://mcp.example/health",
        )

    async def list_tables(self, db):
        return (
            {"tables": [{"name": "audit_discrepancies"}]},
            ToolCallTrace(tool="list_tables", arguments={"database": db}, ok=True, rows=1),
        )

    async def run_query(self, query):
        self.queries.append(query)
        if "audit_discrepancies" in query:
            return (
                [{
                    "discrepancy_id": "disc_1",
                    "production_id": "PROD",
                    "shoot_day": "31",
                    "entity_type": "take",
                    "entity_id": "27/7 Take 3",
                    "discrepancy_type": "TIMECODE_DRIFT",
                    "severity": "CRITICAL",
                    "description": "Camera and sound timecode drift by 8 frames.",
                    "witnesses_json": "[]",
                    "is_resolved": 0,
                    "created_at": _ago(4),
                }],
                ToolCallTrace(tool=_RUN_QUERY_TOOL, arguments={"query": query}, ok=True, rows=1),
            )
        return (
            [],
            ToolCallTrace(tool=_RUN_QUERY_TOOL, arguments={"query": query}, ok=True, rows=0),
        )


class FakeLegacyMCP:
    def query_production_discrepancies(self, production_id, shoot_day):
        return []


class UnavailableClickHouseMCP:
    async def status(self):
        return ClickHouseMCPStatus(
            configured=False,
            available=False,
            reason="CLICKHOUSE_MCP_URL is not set.",
        )

    async def list_tables(self, db):
        raise AssertionError("list_tables should not be called when MCP is unavailable")

    async def run_query(self, query):
        raise AssertionError("run_query should not be called when MCP is unavailable")


def test_agent_does_not_mutate_requirements_without_clickhouse_mcp(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)

    spine = SpineWriter()
    before = spine.list_requirements(production_id="PROD")
    agent = WrapRescueAgent(
        spine_writer=spine,
        reconciler=ReconciliationEngine(),
        legacy_mcp_server=FakeLegacyMCP(),
        clickhouse_mcp=UnavailableClickHouseMCP(),
    )

    result = asyncio.run(agent.run("PROD", "31"))

    after = spine.list_requirements(production_id="PROD")
    assert result.mcp_status.available is False
    assert result.tool_calls == []
    assert result.blockers == []
    assert result.requirement_actions == []
    assert before == after
    assert "no blockers were ranked" in result.final_memo


def test_http_mcp_parses_event_stream_response():
    response = httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text='event: message\ndata: {"result": {"content": [{"type": "text", "text": "{\\"rows\\":[{\\"name\\":\\"audit_discrepancies\\"}]}"}]}}\n\n',
    )

    parsed = _mcp_response_json(response)
    unwrapped = _unwrap_mcp_result(parsed)

    assert parsed["result"]["content"][0]["text"].startswith('{"rows"')
    assert unwrapped == {"rows": [{"name": "audit_discrepancies"}]}


def test_agent_uses_clickhouse_mcp_and_creates_requirement(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)

    spine = SpineWriter()
    mcp = FakeClickHouseMCP()
    agent = WrapRescueAgent(
        spine_writer=spine,
        reconciler=ReconciliationEngine(),
        legacy_mcp_server=FakeLegacyMCP(),
        clickhouse_mcp=mcp,
    )

    result = asyncio.run(agent.run("PROD", "31"))

    assert result.mcp_status.available is True
    assert [call.tool for call in result.tool_calls] == [
        "list_tables", *([_RUN_QUERY_TOOL] * 5),
    ]
    assert result.requirement_actions[0].action == "created"
    requirements = spine.list_requirements(production_id="PROD")
    assert len(requirements) == 1
    assert "WrapRescueSource: discrepancy:TIMECODE_DRIFT:27/7 Take 3" in requirements[0]["description"]
    assert requirements[0]["assigned_to"] == "@sound_supervisor"


def test_wrap_rescue_endpoint_returns_trace(monkeypatch):
    async def fake_run(self, production_id, shoot_day, actor="@wrap_rescue_agent", max_blockers=5):
        return WrapRescueResult(
            production_id=production_id,
            shoot_day=shoot_day,
            actor=actor,
            mcp_status=ClickHouseMCPStatus(configured=True, available=True),
            gemini_status=GeminiEnterpriseStatus(
                configured=False,
                genai_available=False,
                adk_available=False,
                model="deterministic fallback",
                provider="Google GenAI SDK",
            ),
            steps=[{"step": "rank_blockers", "status": "ok", "detail": "Ranked 0."}],
            tool_calls=[],
            blockers=[],
            requirement_actions=[],
            final_memo="Wrap Rescue handoff",
            generated_at=_ago(0),
        )

    monkeypatch.setattr("backend.app.api.routes.WrapRescueAgent.run", fake_run)

    client = TestClient(app)
    response = client.post(
        "/api/agents/wrap-rescue/run",
        json={"production_id": "PROD", "shoot_day": "31", "actor": "@editor"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["actor"] == "@editor"
    assert data["mcp_status"]["available"] is True
    assert data["steps"][0]["step"] == "rank_blockers"


def test_the_memo_reaches_the_runner_and_the_producers(monkeypatch):
    """
    The memo used to exist only in the panel of whoever clicked Run. It now
    lands as a notification for that person and for the crew whose role is
    to act on it, so an agent that "reports to the producer" does.
    """
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)

    spine = SpineWriter()
    spine.register_production(production_id="PROD", name="Prod")
    spine.upsert_production_crew_member({"production_id": "PROD", "handle": "@producer_one", "name": "P", "role": "Line Producer", "department": "production"})
    spine.upsert_production_crew_member({"production_id": "PROD", "handle": "@dit", "name": "D", "role": "DIT / Data Manager", "department": "dit"})
    agent = WrapRescueAgent(
        spine_writer=spine,
        reconciler=ReconciliationEngine(),
        legacy_mcp_server=FakeLegacyMCP(),
        clickhouse_mcp=FakeClickHouseMCP(),
    )

    result = asyncio.run(agent.run("PROD", "31", actor="@assistant_editor"))
    assert result.final_memo

    def inbox(handle):
        return [n for n in spine.list_notifications(recipient_handle=handle) if n["notification_type"] == "COMMENT"]

    runner = inbox("@assistant_editor")
    producer = inbox("@producer_one")
    assert len(runner) == 1 and len(producer) == 1
    assert runner[0]["title"].startswith("Wrap Rescue memo, Day 31")
    assert runner[0]["actor_handle"] == "@wrap_rescue_agent"
    assert runner[0]["message"] == result.final_memo.strip()[:900] or runner[0]["message"].endswith("…")
    assert inbox("@dit") == [], "the DIT gets requirements, not the memo"
