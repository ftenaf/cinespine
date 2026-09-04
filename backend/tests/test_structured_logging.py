"""
One JSON object per log line, with the severity and the trace it belongs to.

Evidence:
- references/log.md (2026-09-04, 'Cloud Logging read every line at severity DEFAULT')
"""
import json
import logging

from opentelemetry import trace as otel_trace

from backend.app.core.telemetry import JsonLogFormatter, span, structured_logging_wanted


def a_record(msg="hello", level=logging.WARNING):
    return logging.LogRecord("cinespine.test", level, __file__, 1, msg, None, None)


def test_a_line_is_json_with_the_fields_cloud_logging_parses():
    line = JsonLogFormatter(project_id="cinespine").format(a_record())
    payload = json.loads(line)
    assert payload["severity"] == "WARNING"
    assert payload["message"] == "hello"
    assert payload["logger"] == "cinespine.test"
    assert payload["time"].endswith("+00:00")


def test_a_line_inside_a_span_links_to_its_trace():
    with span("cinespine.test") as current:
        payload = json.loads(JsonLogFormatter(project_id="cinespine").format(a_record()))
    context = current.get_span_context()
    assert payload["trace_id"] == format(context.trace_id, "032x")
    assert payload["span_id"] == format(context.span_id, "016x")
    assert payload["logging.googleapis.com/trace"] == f"projects/cinespine/traces/{payload['trace_id']}"
    assert payload["logging.googleapis.com/spanId"] == payload["span_id"]


def test_a_line_outside_any_span_carries_no_trace_keys():
    assert not otel_trace.get_current_span().get_span_context().is_valid
    payload = json.loads(JsonLogFormatter().format(a_record()))
    assert "trace_id" not in payload and "logging.googleapis.com/trace" not in payload


def test_an_exception_is_carried_on_the_line():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = a_record("failed", logging.ERROR)
        record.exc_info = sys.exc_info()
    payload = json.loads(JsonLogFormatter().format(record))
    assert "ValueError: boom" in payload["exception"]


def test_json_everywhere_but_a_laptop_unless_told_otherwise():
    assert structured_logging_wanted({"K_SERVICE": "cinespine"})
    assert structured_logging_wanted({"CINESPINE_ENV": "staging"})
    assert not structured_logging_wanted({})
    assert structured_logging_wanted({"CINESPINE_LOG_FORMAT": "json"})
    assert not structured_logging_wanted({"K_SERVICE": "cinespine", "CINESPINE_LOG_FORMAT": "text"})
