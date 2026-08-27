"""
Lighthouse Telemetry and Prometheus Metrics Exporter.

Evidence:
- references/domain/handoffs.md ('Department sync latency and lost acknowledgements')
"""
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

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

ACTIVE_DISCREPANCIES = Gauge(
    "cinespine_active_discrepancies",
    "Count of active discrepancies",
    ["severity", "discrepancy_type"],
)

DEPARTMENT_SYNC_LAG = Gauge(
    "cinespine_department_sync_lag_seconds",
    "Elapsed time since call sheet wrap until department upload",
    ["department", "shoot_day"],
)


class TelemetryExporter:
    @staticmethod
    def record_ingest(department: str, axis: str) -> None:
        INGESTED_EVENTS.labels(department=department, axis=axis).inc()

    @staticmethod
    def record_rejection(doc_type: str, error_type: str) -> None:
        PARSER_REJECTIONS.labels(doc_type=doc_type, error_type=error_type).inc()

    @staticmethod
    def set_discrepancies_count(severity: str, discrepancy_type: str, count: int) -> None:
        ACTIVE_DISCREPANCIES.labels(severity=severity, discrepancy_type=discrepancy_type).set(count)

    @staticmethod
    def set_sync_lag(department: str, shoot_day: str, lag_seconds: float) -> None:
        DEPARTMENT_SYNC_LAG.labels(department=department, shoot_day=shoot_day).set(lag_seconds)

    @staticmethod
    def get_metrics_payload() -> bytes:
        return generate_latest()

    @staticmethod
    def get_content_type() -> str:
        return CONTENT_TYPE_LATEST
