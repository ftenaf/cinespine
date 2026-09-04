"""
Telemetry: the OTel resource and its guard, the business metrics, the
pipeline's spans, structured logs, and the exporter setup.

Evidence:
- references/domain/handoffs.md ('Department sync latency and lost acknowledgements')
"""
import json
import logging
import os
import socket
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional, Tuple
from urllib.parse import urlparse

from opentelemetry import metrics as otel_metrics
from opentelemetry import trace as otel_trace

from backend.app import __version__
from backend.app.reconciliation.models import DiscrepancyType, Severity

# The FastAPI and httpx instrumentations read this before they build their
# metrics. Without it they emit the pre-1.0 HTTP conventions, whose server
# duration histogram carries no http.route -- so RED by endpoint was impossible
# in Grafana however correctly the spans were named. "http" selects the stable
# conventions: http_server_request_duration_seconds with http_route,
# http_request_method and http_response_status_code.
os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "http")

# -----------------------------------------------------------------------------
# Business metrics
# -----------------------------------------------------------------------------
#
# These were prometheus_client objects served at /api/metrics for something to
# scrape. Nothing scrapes a Cloud Run service, so in production they reached
# nothing while the OTel exporter beside them carried gen_ai_* out every 60s --
# two metric systems, one exporter, and every dashboard on the wrong half
# blank. They are OTel instruments now and leave with everything else.
#
# Names keep their Prometheus spelling on arrival: a counter named
# cinespine.ingested_events lands as cinespine_ingested_events_total, a gauge
# with unit "s" gains _seconds, and a unit in braces is an annotation the
# translation drops. The dashboards did not have to change.
#
# Instruments are created against the global meter at import, before
# setup_otlp() installs a provider; the API hands back proxies that bind to
# whichever provider arrives, so import order does not matter.
_meter = otel_metrics.get_meter("cinespine")

INGESTED_EVENTS = _meter.create_counter(
    "cinespine.ingested_events", unit="{event}",
    description="Production events ingested onto the spine, by department and axis",
)

AI_CACHE_HITS = _meter.create_counter(
    "cinespine.ai_cache_hits", unit="{lookup}",
    description="LLM inference cache lookups, by model and hit/miss status",
)

SSE_ACTIVE_CONNECTIONS = _meter.create_up_down_counter(
    "cinespine.sse_active_connections", unit="{connection}",
    description="Server-Sent Event streaming clients currently connected, by user role",
)

PARSER_REJECTIONS = _meter.create_counter(
    "cinespine.parser_rejections", unit="{document}",
    description="Document parsing rejections routed to the DLQ, by document and error type",
)

# Labelled by day as well as by kind. Without production and shoot_day the
# second day observed would overwrite the first, and the board would show
# whichever day somebody happened to open last while looking like a total.
ACTIVE_DISCREPANCIES = _meter.create_gauge(
    "cinespine.active_discrepancies", unit="{discrepancy}",
    description="Unresolved discrepancies on a shoot day, by severity and kind",
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
DEPARTMENT_SYNC_LAG = _meter.create_gauge(
    "cinespine.department_sync_lag", unit="s",
    description="Seconds between wrap and a department's first filing for that shoot day",
)

# Gone: cinespine_llm_tokens_consumed_total and
# cinespine_llm_inference_duration_seconds. Hand-placed at two of eight model
# call sites, counting total tokens only, and read by nothing since the AI
# cost dashboard moved onto gen_ai_client_token_usage, which the google-genai
# instrumentation records for every call and splits into input and output.


class TelemetryExporter:
    @staticmethod
    def record_ingest(department: str, axis: str) -> None:
        INGESTED_EVENTS.add(1, {"department": department, "axis": axis})

    @staticmethod
    def record_rejection(doc_type: str, error_type: str) -> None:
        PARSER_REJECTIONS.add(1, {"doc_type": doc_type, "error_type": error_type})

    @staticmethod
    def record_cache_lookup(model: str, status: str) -> None:
        """One inference cache lookup; status is "hit" or "miss"."""
        AI_CACHE_HITS.add(1, {"model": model, "status": status})

    @staticmethod
    def record_sse_connection(user_role: str, delta: int) -> None:
        """+1 when a stream opens, -1 when it closes."""
        SSE_ACTIVE_CONNECTIONS.add(delta, {"user_role": user_role})

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
            ACTIVE_DISCREPANCIES.set(count, {
                "production_id": production_id, "shoot_day": shoot_day,
                "severity": severity, "discrepancy_type": kind,
            })

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
            DEPARTMENT_SYNC_LAG.set(seconds, {
                "production_id": production_id,
                "shoot_day": str(row.get("shoot_day", "")),
                "department": str(row.get("department", "")),
                "measurement": measurement,
            })


# -----------------------------------------------------------------------------
# Spans for the pipeline
# -----------------------------------------------------------------------------
#
# Until 2026-09-04 every span came from an auto-instrumentor: the HTTP request,
# the outbound httpx call, the Gemini call. Ingest, parsing, reconciliation,
# the ClickHouse mirror and the MCP tool calls -- the product -- were invisible
# between them. These are the seams; each carries the ids a reader would
# otherwise have to dig out of a log line.
_tracer = otel_trace.get_tracer("cinespine")

_ATTRIBUTE_TYPES = (str, bool, int, float)


def _clean(attributes: Mapping[str, Any]) -> Dict[str, Any]:
    """Drops Nones and stringifies anything OTel cannot carry as-is."""
    out: Dict[str, Any] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        out[key] = value if isinstance(value, _ATTRIBUTE_TYPES) else str(value)
    return out


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[otel_trace.Span]:
    """
    One step of the pipeline, as a span under whatever is current.

    Attribute keys are the caller's; the convention is ``cinespine.<thing>``
    so the product's dimensions sort together in Tempo. An exception raised
    inside is recorded on the span, marks it as an error, and propagates.
    With no tracer provider installed this costs a no-op span and nothing
    else.
    """
    with _tracer.start_as_current_span(name, attributes=_clean(attributes)) as current:
        yield current


def set_attributes(current: otel_trace.Span, **attributes: Any) -> None:
    """Attributes known only once the step has run."""
    current.set_attributes(_clean(attributes))


# -----------------------------------------------------------------------------
# Structured logs
# -----------------------------------------------------------------------------
#
# Cloud Run reads stdout. As plain text every line landed at severity DEFAULT
# with the trace id buried mid-string, so Cloud Logging could neither filter
# by level nor link a line to its trace, and Loki's `detected_level` was a
# guess. One JSON object per line fixes both: `severity` is what Cloud Logging
# parses, the `logging.googleapis.com/*` keys are how it links to the trace,
# and the flat `trace_id`/`span_id` are for everyone else.


class JsonLogFormatter(logging.Formatter):
    def __init__(self, project_id: Optional[str] = None):
        super().__init__()
        self.project_id = project_id

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        context = otel_trace.get_current_span().get_span_context()
        if context.is_valid:
            trace_id = format(context.trace_id, "032x")
            span_id = format(context.span_id, "016x")
            payload["trace_id"] = trace_id
            payload["span_id"] = span_id
            payload["logging.googleapis.com/spanId"] = span_id
            payload["logging.googleapis.com/trace_sampled"] = bool(context.trace_flags.sampled)
            if self.project_id:
                payload["logging.googleapis.com/trace"] = f"projects/{self.project_id}/traces/{trace_id}"
        return json.dumps(payload, default=str)


def structured_logging_wanted(environ: Optional[Mapping[str, str]] = None) -> bool:
    """JSON everywhere but a laptop, where a person is reading the terminal."""
    env = os.environ if environ is None else environ
    explicit = (env.get("CINESPINE_LOG_FORMAT") or "").strip().lower()
    if explicit in ("json", "text"):
        return explicit == "json"
    return deployment_environment(env) != "local"


def configure_structured_logging(environ: Optional[Mapping[str, str]] = None) -> bool:
    """
    Puts the JSON formatter on every handler that writes to the console.

    uvicorn installs its handlers before the app is imported, so they are
    already there to be reformatted; the root logger gets a stdout handler if
    nothing gave it one. The OTLP log handler is left alone -- it carries the
    record's fields natively. Returns whether anything changed.
    """
    env = os.environ if environ is None else environ
    if not structured_logging_wanted(env):
        return False
    formatter = JsonLogFormatter(project_id=env.get("GOOGLE_CLOUD_PROJECT"))
    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(logging.StreamHandler())
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(name).handlers:
            if type(handler) is logging.StreamHandler:
                handler.setFormatter(formatter)
    return True


# -----------------------------------------------------------------------------
# Which deployment is this?
# -----------------------------------------------------------------------------
#
# Every exporter below stamps its data with the resource built here. Until
# 2026-09-03 that resource said only "cinespine-backend 0.1.0", and one
# afternoon of a laptop container running with the production .env pushed
# 2,400 error lines about a missing credentials file into Grafana Cloud, where
# nothing could tell them from Cloud Run's. The environment attribute is what
# makes them separable; the guard is what makes the accident impossible.

# Hosts a local process may export to without being asked twice. The compose
# service name is here because a container on the compose network reaches
# Prometheus by it.
_LOCAL_COLLECTOR_HOSTS = frozenset({
    "localhost", "127.0.0.1", "::1", "host.docker.internal", "prometheus",
})


def deployment_environment(environ: Optional[Mapping[str, str]] = None) -> str:
    """Name of the deployment this process belongs to.

    Cloud Run sets ``K_SERVICE`` on every container it runs, so its presence
    is production whatever else the environment says. Anything else is
    ``local`` unless ``CINESPINE_ENV`` names it.
    """
    env = os.environ if environ is None else environ
    if env.get("K_SERVICE"):
        return "cloudrun"
    return (env.get("CINESPINE_ENV") or "local").strip() or "local"


def service_instance_id(
    environ: Optional[Mapping[str, str]] = None, hostname: Optional[str] = None
) -> str:
    """One id per running process: the Cloud Run revision there, the host name here.

    The revision changes on every deploy, so a series break in Grafana lines
    up with a release rather than having to be guessed from timestamps.
    """
    env = os.environ if environ is None else environ
    return env.get("K_REVISION") or env.get("K_SERVICE") or hostname or socket.gethostname()


def resource_attributes(
    app_name: str,
    environ: Optional[Mapping[str, str]] = None,
    hostname: Optional[str] = None,
) -> Dict[str, str]:
    """The OpenTelemetry resource every signal from this process carries."""
    return {
        "service.name": app_name,
        "service.version": __version__,
        "deployment.environment": deployment_environment(environ),
        "service.instance.id": service_instance_id(environ, hostname),
    }


def remote_export_allowed(
    environment: str, endpoint: str, environ: Optional[Mapping[str, str]] = None
) -> bool:
    """Whether this process may push telemetry to ``endpoint``.

    A deployment exports wherever it is pointed. A local process exports only
    to a local collector unless ``CINESPINE_TELEMETRY_REMOTE_OK=1`` says the
    push into a remote stack is deliberate.
    """
    if environment != "local":
        return True
    env = os.environ if environ is None else environ
    if (env.get("CINESPINE_TELEMETRY_REMOTE_OK") or "").strip().lower() in ("1", "true", "yes"):
        return True
    host = (urlparse(endpoint).hostname or "").lower()
    return host in _LOCAL_COLLECTOR_HOSTS


def backport_fastapi_route_details() -> None:
    """Let the FastAPI instrumentation see the routes inside an included router.

    FastAPI 0.137 stopped copying an included router's routes onto the app and
    mounts an ``_IncludedRouter`` wrapper instead, which has no ``path``.
    ``opentelemetry-instrumentation-fastapi`` 0.63b1 walks ``app.routes``
    expecting plain routes: on a full match it tolerates the missing ``path``,
    on a partial match (right path, wrong method) it does not, and the request
    dies with ``AttributeError`` -- a 500 with no span, where a 405 was due.
    That is the one 5xx Cloud Run served in the week to 2026-09-03.

    0.64b0 flattens the wrapper. It cannot be installed: its
    ``semantic-conventions`` pin needs ``opentelemetry-api`` 1.43 and
    ``google-adk`` 2.8 caps the api at 1.42.1, so the resolver trades ADK down
    two major versions to take it. This is 0.64b0's fix applied to 0.63b1. It
    does nothing once the installed instrumentation carries ``_flatten_routes``
    itself, so it retires on the day ADK lets the upgrade through.
    """
    try:
        import opentelemetry.instrumentation.fastapi as otel_fastapi
    except ImportError:
        return
    if hasattr(otel_fastapi, "_flatten_routes"):
        return

    from starlette.routing import Match, Route

    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:  # FastAPI < 0.137.2
        iter_route_contexts = None

    def _flatten_routes(routes):
        if iter_route_contexts is not None:
            yield from iter_route_contexts(routes)
            return
        for starlette_route in routes:
            if hasattr(starlette_route, "effective_route_contexts"):
                yield from starlette_route.effective_route_contexts()
            else:
                yield starlette_route

    def _get_route_details(scope):
        route = None
        for starlette_route in _flatten_routes(scope["app"].routes):
            match, _ = (
                Route.matches(starlette_route, scope)
                if isinstance(starlette_route, Route)
                else starlette_route.matches(scope)
            )
            if match == Match.FULL:
                try:
                    route = starlette_route.path
                except AttributeError:  # host-routed entries carry no path
                    route = scope.get("path")
                break
            if match == Match.PARTIAL:
                route = starlette_route.path
        return route

    otel_fastapi._get_route_details = _get_route_details


def setup_otlp(app_name: str = "cinespine-backend"):
    """
    Initializes OpenTelemetry traces and logs export to OTLP.
    Reads standard OTEL_ environment variables.
    """
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

    attributes = resource_attributes(app_name)
    environment = attributes["deployment.environment"]
    if not remote_export_allowed(environment, endpoint):
        logger.warning(
            "OpenTelemetry export is disabled: this is a %s process and %s is not a "
            "local collector. Set CINESPINE_TELEMETRY_REMOTE_OK=1 to push a local run "
            "into a remote stack on purpose; it will arrive labelled deployment.environment=%s.",
            environment, endpoint, environment,
        )
        return

    logger.info(
        "Initializing OpenTelemetry for %s (%s, %s), exporting to %s",
        app_name, environment, attributes["service.instance.id"], endpoint,
    )

    # Resource.create also merges OTEL_RESOURCE_ATTRIBUTES, so a deployment
    # can add attributes without a code change.
    resource = Resource.create(attributes)

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

    # -----------------------------------------------------
    # Set up OTLP Metric Exporter
    # -----------------------------------------------------
    #
    # Spans and logs had exporters; metrics had none, so nothing this process
    # measured ever reached Grafana. The gap was invisible because the traces
    # arriving made the pipeline look configured -- a Prometheus query for
    # `gen_ai.*` or `cinespine_*` returned an empty vector while Tempo held the
    # matching spans.
    #
    # Push, not scrape. Nothing scrapes a Cloud Run service: it has no stable
    # address to be scraped at, and a scale-to-zero instance is not there to
    # answer. The exporter carries everything out, the business metrics above
    # included since 2026-09-04.
    #
    # This provider is what the GenAI instrumentation records against, so token
    # counts and call durations become queryable as series rather than only as
    # span attributes.
    try:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

        # 60s rather than the 30s default: these are counters and histograms
        # read on dashboards, not alert inputs, and halving the export volume
        # costs nothing at that resolution.
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(), export_interval_millis=60_000,
        )
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))
        logger.info("OTLP metric exporter installed (60s interval).")
    except Exception as e:  # noqa: BLE001 - observability must not break boot
        logger.warning(f"Could not initialize OTLP Metric Exporter: {e}")

    logger.info("OpenTelemetry initialization complete. Traces, Logs and Metrics are now exporting.")

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
