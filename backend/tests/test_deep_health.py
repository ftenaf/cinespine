"""
/api/health/deep answers "can it do its job", not "is the process up".

Evidence:
- references/log.md (2026-09-04, 'A full disk reported healthy')
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.core import health
from backend.app.main import app
from backend.app.spine import event_store

client = TestClient(app)


def test_the_shallow_check_still_answers_and_checks_nothing():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_sqlite_is_proved_by_a_write(isolated_character_db):
    result = health.check_sqlite()
    assert result["ok"] is True
    assert result["free_mb"] > 0
    assert "latency_ms" in result


def test_a_spine_that_cannot_take_a_write_is_down(monkeypatch):
    def full(): raise OSError("database or disk is full")
    monkeypatch.setattr(event_store, "probe_write", full)
    result = health.check_sqlite()
    assert result["ok"] is False
    assert "disk is full" in result["error"]
    assert health.overall({"sqlite": result, "clickhouse": {"ok": True}}) == "down"


def test_no_mirror_configured_is_not_a_failure():
    result = health.check_clickhouse(SimpleNamespace(client=None))
    assert result == {"ok": True, "configured": False, "latency_ms": 0.0}


def test_a_mirror_that_answers_is_ok_and_says_whether_it_is_open():
    writer = SimpleNamespace(client=SimpleNamespace(query=lambda *a, **k: None), _mirror_blocked_until=0.0)
    result = health.check_clickhouse(writer)
    assert result["ok"] is True and result["mirror_open"] is True


def test_a_mirror_that_does_not_answer_degrades_rather_than_downs():
    def boom(*a, **k): raise ConnectionError("refused")
    writer = SimpleNamespace(client=SimpleNamespace(query=boom), _mirror_blocked_until=0.0)
    result = health.check_clickhouse(writer)
    assert result["ok"] is False and "refused" in result["error"]
    assert health.overall({"sqlite": {"ok": True}, "clickhouse": result}) == "degraded"


def test_the_mcp_server_is_probed_only_when_asked():
    class Never:
        async def status(self):
            raise AssertionError("must not be called")
    report = asyncio.run(health.deep_health(SimpleNamespace(client=None), mcp_client=None))
    assert "mcp" not in report["checks"]

    class Cold:
        async def status(self):
            return SimpleNamespace(available=False, configured=True, reason="timed out")
    report = asyncio.run(health.deep_health(SimpleNamespace(client=None), mcp_client=Cold()))
    assert report["checks"]["mcp"]["ok"] is False
    assert report["status"] == "degraded"


def test_the_endpoint_names_the_deployment_and_is_503_only_when_down(monkeypatch, isolated_character_db):
    r = client.get("/api/health/deep")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert body["environment"] == "local"
    assert body["instance"]
    assert body["checks"]["sqlite"]["ok"] is True
    assert "mcp" not in body["checks"]

    def full(): raise OSError("database or disk is full")
    monkeypatch.setattr(event_store, "probe_write", full)
    r = client.get("/api/health/deep")
    assert r.status_code == 503
    assert r.json()["status"] == "down"
