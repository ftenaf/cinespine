"""
The product's own steps are spans, not just the HTTP request around them.

Evidence:
- references/log.md (2026-09-04, 'The pipeline was invisible between an HTTP span and a SQLite read')
"""
import asyncio

from fastapi.testclient import TestClient

from backend.app.agents.wrap_rescue import HTTPClickHouseMCPClient
from backend.app.main import app
from backend.tests.otel_metrics import SPAN_EXPORTER, finished_spans

client = TestClient(app)

A_TIMECODE_LOG = "27/7 1 09:26:12:04 09:28:58:12\nA120 280726 2:46\n"


def test_an_upload_is_an_ingest_span_with_the_ids_a_reader_needs():
    SPAN_EXPORTER.clear()
    client.post("/api/upload", json={
        "raw_content": A_TIMECODE_LOG, "filename": "SPAN_TCLog_D031.txt",
        "production_id": "SPAN_PROD", "shoot_day": "31",
    })
    ingest = finished_spans("cinespine.ingest")
    assert ingest, "the upload produced no ingest span"
    attrs = ingest[-1].attributes
    assert attrs["cinespine.production_id"] == "SPAN_PROD"
    assert attrs["cinespine.shoot_day"] == "31"
    assert attrs["cinespine.department"] and attrs["cinespine.doc_type"]
    assert "cinespine.mirrored_rows" in attrs


def test_each_parser_that_ran_is_a_parse_span_under_the_ingest():
    SPAN_EXPORTER.clear()
    client.post("/api/upload", json={
        "raw_content": A_TIMECODE_LOG, "filename": "SPAN2_TCLog_D031.txt",
        "production_id": "SPAN_PROD", "shoot_day": "31",
    })
    ingest = finished_spans("cinespine.ingest")[-1]
    parses = [s for s in finished_spans("cinespine.parse")
              if s.parent is not None and s.parent.span_id == ingest.context.span_id]
    assert parses, "no parse span hung under the ingest"
    assert {s.attributes["cinespine.handler"] for s in parses} >= {"handle_shoot_date"}


def test_asking_for_a_day_is_a_reconcile_span_that_counts_what_it_found():
    SPAN_EXPORTER.clear()
    client.post("/api/upload", json={
        "raw_content": A_TIMECODE_LOG, "filename": "SPAN3_TCLog_D031.txt",
        "production_id": "SPAN_RECON", "shoot_day": "31",
    })
    client.get("/api/discrepancies", params={"production_id": "SPAN_RECON", "shoot_day": "31"})
    recon = finished_spans("cinespine.reconcile")
    assert recon, "asking for a day produced no reconcile span"
    attrs = recon[-1].attributes
    assert attrs["cinespine.production_id"] == "SPAN_RECON"
    assert attrs["cinespine.events"] >= 1
    assert "cinespine.discrepancies" in attrs and "cinespine.unresolved" in attrs
    if attrs["cinespine.unresolved"]:
        assert any(e.name == "cinespine.discrepancy" for e in recon[-1].events)


def test_a_failed_mcp_tool_call_is_a_span_that_says_so():
    SPAN_EXPORTER.clear()
    mcp = HTTPClickHouseMCPClient(url="http://127.0.0.1:9/mcp", timeout=0.2)
    result, trace = asyncio.run(mcp.run_query("SELECT 1"))
    assert trace.ok is False
    tool_spans = finished_spans("cinespine.mcp.tool")
    assert tool_spans, "the tool call produced no span"
    attrs = tool_spans[-1].attributes
    assert attrs["cinespine.tool"] == trace.tool
    assert attrs["cinespine.ok"] is False
    assert attrs["cinespine.error"]
