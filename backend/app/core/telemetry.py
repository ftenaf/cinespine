"""
Lighthouse Telemetry and Prometheus Metrics Exporter.

Evidence:
- references/domain/handoffs.md ('Department sync latency and lost acknowledgements')
"""
from typing import Any, Dict, Iterable, Tuple

from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

from backend.app.reconciliation.models import DiscrepancyType, Severity

# Metrics
INGESTED_EVENTS = Counter(
    "cinespine_ingested_events_total",
    "Total production events ingested onto the spine",
    ["department", "axis"],
)

LLM_TOKENS_CONSUMED = Counter(
    "cinespine_llm_tokens_consumed_total",
    "Total tokens consumed by generative tasks",
    ["model", "task_complexity"]
)

AI_CACHE_HITS = Counter(
    "cinespine_ai_cache_hits_total",
    "Cache hit ratio for LLM inference",
    ["model", "status"]
)

LLM_LATENCY = Histogram(
    "cinespine_llm_inference_duration_seconds",
    "Time spent waiting for Gemini/Imagen API responses",
    ["model"]
)

SSE_ACTIVE_CONNECTIONS = Gauge(
    "cinespine_sse_active_connections",
    "Number of active Server-Sent Event streaming clients",
    ["user_role"]
)

PARSER_REJECTIONS = Counter(
    "cinespine_parser_rejections_total",
    "Total document parsing rejections routed to DLQ",
    ["doc_type", "error_type"],
)

# Labelled by day as well as by kind. Without production and shoot_day the
# second day observed would overwrite the first, and the board would show
# whichever day somebody happened to open last while looking like a total.
ACTIVE_DISCREPANCIES = Gauge(
    "cinespine_active_discrepancies",
    "Unresolved discrepancies on a shoot day, by severity and kind",
    ["production_id", "shoot_day", "severity", "discrepancy_type"],
)

# cinespine_department_sync_lag_seconds was declared here and never set, and it
# has been removed rather than wired up. The lag is measured from wrap, and a
# daily production report states wrap as a time of day -- "18:55" -- with no
# date on it. What the spine has to subtract from is the moment the document
# was uploaded to this system, which for day 31 is months after the day was
# shot. The subtraction would invent a number neither witness supports.
#
# A gauge that can never fill is worse than no gauge: it renders as a flat zero
# on a dashboard, which reads as "no lag" rather than "not known" -- absence
# rendered as presence. Recorded in references/open-questions.md, where it now
# names what is missing: the report's own date.


class TelemetryExporter:
    @staticmethod
    def record_ingest(department: str, axis: str) -> None:
        INGESTED_EVENTS.labels(department=department, axis=axis).inc()

    @staticmethod
    def record_rejection(doc_type: str, error_type: str) -> None:
        PARSER_REJECTIONS.labels(doc_type=doc_type, error_type=error_type).inc()

    @staticmethod
    def record_discrepancies(
        production_id: str, shoot_day: str, discrepancies: Iterable[Dict[str, Any]]
    ) -> None:
        """
        Publishes the unresolved count for one day, one series per kind.

        Every combination is written, zeros included, rather than only the ones
        that occurred. A gauge keeps its last value forever, so setting only
        what is present would leave a discrepancy that has since been resolved
        showing its old count -- the board would say a problem is still open
        after somebody fixed it.

        Explicit zeros also say something true that silence does not: "no
        critical missing media on day 31" is a fact, and it is different from
        never having looked, which stays absent from the metric entirely.
        """
        counts: Dict[Tuple[str, str], int] = {
            (severity.value, kind.value): 0
            for severity in Severity for kind in DiscrepancyType
        }
        for d in discrepancies:
            if d.get("is_resolved"):
                continue
            key = (str(d.get("severity", "")), str(d.get("discrepancy_type", "")))
            if key in counts:
                counts[key] += 1

        for (severity, kind), count in counts.items():
            ACTIVE_DISCREPANCIES.labels(
                production_id=production_id, shoot_day=shoot_day,
                severity=severity, discrepancy_type=kind,
            ).set(count)

    @staticmethod
    def get_metrics_payload() -> bytes:
        return generate_latest()

    @staticmethod
    def get_content_type() -> str:
        return CONTENT_TYPE_LATEST
