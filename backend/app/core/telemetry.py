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

# Back, and computable now. It was removed on 2026-08-30 because wrap is stated
# as a time of day with no date beside it, so there was no moment to subtract
# from -- and a gauge that can never fill renders as a flat zero, which reads
# as "no lag" rather than "not known". The date is on the spine since the same
# afternoon, so the subtraction is real.
#
# `measurement` is the label that keeps it honest. Paperwork loaded months
# after the shoot has a correct lag that says nothing about the night it was
# filed, and 780 hours in a matrix a reader expects to be hours would tell them
# something false in a form that looks true. A dashboard can show handovers and
# backfills; it must not show them as one number.
DEPARTMENT_SYNC_LAG = Gauge(
    "cinespine_department_sync_lag_seconds",
    "Seconds between wrap and a department's first filing for that shoot day",
    ["production_id", "shoot_day", "department", "measurement"],
)


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
    def record_sync_lag(production_id: str, rows: Iterable[Dict[str, Any]]) -> None:
        """
        Publishes the department sync matrix.

        Only rows that could be measured. A day whose paperwork states no wrap
        or no date has no baseline, and writing zero for it would claim the
        department filed at the moment of a wrap nobody recorded.
        """
        for row in rows or []:
            seconds = row.get("lag_seconds")
            measurement = row.get("measurement")
            if seconds is None or not measurement:
                continue
            DEPARTMENT_SYNC_LAG.labels(
                production_id=production_id,
                shoot_day=str(row.get("shoot_day", "")),
                department=str(row.get("department", "")),
                measurement=measurement,
            ).set(seconds)

    @staticmethod
    def get_metrics_payload() -> bytes:
        return generate_latest()

    @staticmethod
    def get_content_type() -> str:
        return CONTENT_TYPE_LATEST

def setup_otlp(app_name: str = "cinespine-backend"):
    """
    Initializes OpenTelemetry traces and logs export to OTLP.
    Reads standard OTEL_ environment variables.
    """
    import os
    import logging
    import time
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    logger = logging.getLogger(__name__)
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    
    if not endpoint:
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set. OpenTelemetry export is disabled.")
        return

    logger.info(f"Initializing OpenTelemetry for {app_name}, exporting to {endpoint}")

    resource = Resource.create({
        "service.name": app_name,
        "service.version": "0.1.0"
    })

    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)
    
    otlp_exporter = OTLPSpanExporter()
    span_processor = BatchSpanProcessor(otlp_exporter)
    tracer_provider.add_span_processor(span_processor)

    # Instrument python logging to inject trace_id and span_id
    LoggingInstrumentor().instrument(set_logging_format=True)
    
    # -----------------------------------------------------
    # Set up OTLP Log Exporter
    # -----------------------------------------------------
    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

        logger_provider = LoggerProvider(resource=resource)
        set_logger_provider(logger_provider)
        
        otlp_log_exporter = OTLPLogExporter()
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(otlp_log_exporter))
        
        # Attach OTel handler to the root logger so all logs are exported
        otel_log_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
        logging.getLogger().addHandler(otel_log_handler)
    except ImportError as e:
        logger.warning(f"Could not initialize OTLP Log Exporter (requires newer opentelemetry packages): {e}")

    logger.info("OpenTelemetry initialization complete. Traces and Logs are now exporting.")

    # -----------------------------------------------------
    # GenAI / Agent Observability
    # -----------------------------------------------------
    #
    # Instruments the google-genai SDK, which is the layer this app actually
    # calls: `client.models.generate_content` in character inference, the
    # camera-report vision reader, the multimodal extractor and the Wrap Rescue
    # memo. Spans cover generate_content and execute_tool, so an agent run is a
    # tree rather than one opaque HTTP span.
    #
    # This replaced openlit, which patched the client library of every provider
    # it supports and hard-depended on anthropic, openai and boto3 to do it --
    # three vendor SDKs nothing here calls. That cost ~34 seconds at init, so it
    # had to run on a background thread to keep the app's import off the
    # critical path; a platform that gave up waiting for the port reported it as
    # though the process had crashed.
    #
    # This one instruments only what is used, so it runs inline: no thread, no
    # window where model calls go unrecorded, no vendor SDKs in the image.
    #
    # Message content is not captured by default, which is the right default
    # here -- prompts carry unreleased screenplay text. Set
    # OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT deliberately if that is
    # ever wanted.
    if os.environ.get("CINESPINE_DISABLE_GENAI_TELEMETRY", "").strip() not in ("", "0", "false", "False"):
        logger.info("GenAI instrumentation is disabled by CINESPINE_DISABLE_GENAI_TELEMETRY.")
        return

    try:
        from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor

        started = time.perf_counter()
        GoogleGenAiSdkInstrumentor().instrument()
        logger.info(
            "google-genai instrumentation attached in %.2fs.",
            time.perf_counter() - started,
        )
    except Exception as e:  # noqa: BLE001 - observability must not break boot
        logger.warning(f"Could not instrument google-genai: {e}")
