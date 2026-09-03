"""
The FastAPI instrumentation must see through FastAPI's included-router wrapper.

Evidence:
- references/log.md (2026-09-03, 'A wrong method on any API route was a 500')
"""
import opentelemetry.instrumentation.fastapi as otel_fastapi
from starlette.testclient import TestClient

from backend.app.main import app


def _scope(method, path):
    return {
        "type": "http", "method": method, "path": path, "root_path": "",
        "headers": [], "query_string": b"", "app": app,
    }


def test_a_wrong_method_on_an_included_route_is_405_not_500():
    client = TestClient(app, raise_server_exceptions=False)
    assert client.post("/api/health").status_code == 405
    assert client.post("/api/wrap-rescue/demo").status_code == 405


def test_the_route_walker_names_a_partial_match_instead_of_raising():
    # Last partial match wins, as upstream: here that is the SPA catch-all.
    assert otel_fastapi._get_route_details(_scope("POST", "/api/health")) is not None


def test_the_route_walker_still_names_a_full_match():
    assert otel_fastapi._get_route_details(_scope("GET", "/api/health")) == "/api/health"
