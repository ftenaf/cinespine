"""
The deep health check: does each thing this service depends on answer?

`/api/health` says the process is up, which is what Cloud Run's startup probe
needs and nothing more. This is the other question -- can it do its job --
and it exists because of an afternoon of "database or disk is full" errors
that the shallow check reported as healthy. Each dependency is probed the way
the app actually uses it, timed, and reported by name, so the answer says
*what* is wrong rather than that something is.

The overall status is decided by what the product cannot work without:

- SQLite is the spine. If it will not take a write the service is **down**,
  and the response is a 503 so a synthetic check trips.
- ClickHouse is the analytical mirror. It is best effort by design (the
  writer shuts it for a cooldown on failure and carries on), so an outage is
  **degraded**, still a 200, still worth seeing.
- The MCP server scales to zero and takes ~20s to wake, so it is probed only
  when asked (`?mcp=1`); a routine check must not spin it up every minute.
"""
import os
import shutil
import time
from typing import Any, Callable, Dict, Optional

from backend.app.core.telemetry import deployment_environment, service_instance_id, span
from backend.app.spine import event_store


def _timed(probe: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        result = {"ok": True, **probe()}
    except Exception as exc:  # noqa: BLE001 - the whole point is to report it
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    result["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return result


def check_sqlite() -> Dict[str, Any]:
    """A real write on the spine's connection, plus how much disk is left beside it."""
    def probe() -> Dict[str, Any]:
        event_store.probe_write()
        path = event_store.get_db_path()
        usage = shutil.disk_usage(os.path.dirname(os.path.abspath(path)) or ".")
        return {"path": path, "free_mb": round(usage.free / 1e6, 1)}
    return _timed(probe)


def check_clickhouse(writer: Any) -> Dict[str, Any]:
    """SELECT 1 on the writer's own client, and whether the mirror is currently shut."""
    client = getattr(writer, "client", None)
    if client is None:
        return {"ok": True, "configured": False, "latency_ms": 0.0}

    def probe() -> Dict[str, Any]:
        client.query("SELECT 1", settings={"max_execution_time": 3})
        blocked_until = getattr(writer, "_mirror_blocked_until", 0.0) or 0.0
        return {"configured": True, "mirror_open": not (blocked_until and time.monotonic() < blocked_until)}
    return _timed(probe)


async def check_mcp(client: Any) -> Dict[str, Any]:
    """The MCP initialize handshake, which is the path every tool call takes."""
    started = time.perf_counter()
    status = await client.status()
    return {
        "ok": bool(status.available),
        "configured": bool(status.configured),
        "reason": status.reason,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def overall(checks: Dict[str, Dict[str, Any]]) -> str:
    if not checks["sqlite"]["ok"]:
        return "down"
    if any(not c.get("ok", True) for name, c in checks.items() if name != "sqlite"):
        return "degraded"
    return "ok"


async def deep_health(writer: Any, mcp_client: Optional[Any] = None, version: str = "") -> Dict[str, Any]:
    with span("cinespine.health") as current:
        checks: Dict[str, Dict[str, Any]] = {
            "sqlite": check_sqlite(),
            "clickhouse": check_clickhouse(writer),
        }
        if mcp_client is not None:
            checks["mcp"] = await check_mcp(mcp_client)
        status = overall(checks)
        current.set_attribute("cinespine.health.status", status)
        return {
            "status": status,
            "service": "cinespine",
            "version": version,
            "environment": deployment_environment(),
            "instance": service_instance_id(),
            "checks": checks,
        }
