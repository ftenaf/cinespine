"""
Reads the business metrics back in tests.

They are OTel instruments now (see backend/app/core/telemetry.py). This module
installs one in-memory reader for the whole session; the instruments are
proxies that bind to whichever provider arrives, so it does not matter whether
telemetry.py was imported before or after this runs. conftest.py imports it so
the provider exists before any test does.

Two things a reader of these helpers should know:

- A gauge point is handed out **once per collection** and then cleared, so a
  second read in the same test would see nothing. `metric_points` keeps every
  point it has ever seen and returns the latest value per attribute set.
- Import this as `backend.tests.otel_metrics`, never via conftest: pytest
  loads conftest under its own module name, and importing it by path makes a
  second copy with a second, unattached reader.
"""
from typing import Any, Dict, List, Tuple

from opentelemetry import metrics as otel_metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

METRICS_READER = InMemoryMetricReader()
otel_metrics.set_meter_provider(MeterProvider(metric_readers=[METRICS_READER]))

_seen: Dict[str, Dict[Tuple[Tuple[str, Any], ...], Tuple[Dict[str, Any], Any]]] = {}


def metric_points(name: str) -> List[Tuple[Dict[str, Any], Any]]:
    """
    Latest value per attribute set for one instrument, as (attributes, value).

    `name` is the OTel name (cinespine.active_discrepancies), not the
    Prometheus spelling it arrives under.
    """
    data = METRICS_READER.get_metrics_data()
    for rm in (data.resource_metrics if data else []):
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                bucket = _seen.setdefault(m.name, {})
                for point in m.data.data_points:
                    # Histogram points (the HTTP instrumentation) carry no
                    # single value; nothing here reads them.
                    if not hasattr(point, "value"):
                        continue
                    attrs = dict(point.attributes)
                    bucket[tuple(sorted(attrs.items()))] = (attrs, point.value)
    return list(_seen.get(name, {}).values())
