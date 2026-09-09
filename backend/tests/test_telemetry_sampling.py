"""
Cloud Run forwards every request with a traceparent whose sampled flag is
off. A parent-based sampler that honours it drops the whole trace, and does
so silently. These pin the sampler that ignores an unsampled remote parent.
"""

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import Decision
from opentelemetry.trace import SpanContext, TraceFlags

from backend.app.core.telemetry import SampledParentOnlyPropagator, trace_sampler


def _remote_parent(sampled: bool):
    flags = TraceFlags(TraceFlags.SAMPLED if sampled else TraceFlags.DEFAULT)
    ctx = SpanContext(trace_id=0x1234, span_id=0x56, is_remote=True, trace_flags=flags)
    return trace.set_span_in_context(trace.NonRecordingSpan(ctx))


def test_unsampled_remote_parent_is_sampled_anyway():
    result = trace_sampler().should_sample(_remote_parent(False), 0x1234, "GET /api/productions")
    assert result.decision is Decision.RECORD_AND_SAMPLE


def test_sampled_remote_parent_stays_in_its_trace():
    result = trace_sampler().should_sample(_remote_parent(True), 0x1234, "GET /api/productions")
    assert result.decision is Decision.RECORD_AND_SAMPLE


def test_root_span_is_sampled():
    result = trace_sampler().should_sample(None, 0x1234, "cinespine.agent.wrap_rescue")
    assert result.decision is Decision.RECORD_AND_SAMPLE


def test_provider_records_under_an_unsampled_remote_parent():
    provider = TracerProvider(sampler=trace_sampler())
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("child", context=_remote_parent(False)) as span:
        assert span.is_recording()
        assert span.get_span_context().trace_flags.sampled


def _extract(traceparent: str):
    ctx = SampledParentOnlyPropagator().extract({"traceparent": traceparent})
    return trace.get_current_span(ctx).get_span_context()


def test_unsampled_incoming_traceparent_is_ignored():
    # What Cloud Run's front end sends: valid ids, sampled flag off.
    parent = _extract("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00")
    assert not parent.is_valid


def test_sampled_incoming_traceparent_is_kept():
    # What the Faro-instrumented browser sends.
    parent = _extract("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
    assert parent.is_valid
    assert parent.trace_id == 0x4BF92F3577B34DA6A3CE929D0E0E4736
    assert parent.is_remote


def test_inject_still_carries_the_current_trace():
    provider = TracerProvider(sampler=trace_sampler())
    carrier = {}
    with provider.get_tracer("test").start_as_current_span("out"):
        SampledParentOnlyPropagator().inject(carrier)
    flags = int(carrier["traceparent"].rsplit("-", 1)[1], 16)
    assert flags & TraceFlags.SAMPLED
