"""Observability: structured logs, traces and metrics (OpenTelemetry).

- Logs are JSON lines (one object per line) carrying `trace_id` / `span_id`, so a log
  line can be matched to the request or job that wrote it in Grafana / Datadog / CloudWatch.
- Traces cover HTTP requests (FastAPI), SQL queries (SQLAlchemy), Redis calls, and each
  background digitization job (a span per job with a child span per stage).
- Metrics: request metrics from the FastAPI instrumentation, plus our own
  `studyforge.digitization.jobs` counter and `studyforge.digitization.duration` histogram.

Export is OFF unless OTEL_EXPORTER_OTLP_ENDPOINT is set (e.g. http://jaeger:4318), so local
dev and tests pay nothing. Any OTLP backend works: Jaeger, Grafana Tempo, Honeycomb, Datadog.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

from app.config import settings

tracer = trace.get_tracer("studyforge")
meter = metrics.get_meter("studyforge")

jobs_counter = meter.create_counter(
    "studyforge.digitization.jobs", description="Digitization job runs, by outcome"
)
job_duration = meter.create_histogram(
    "studyforge.digitization.duration", unit="s", description="Time to run one digitization job"
)

# Standard LogRecord attributes (and uvicorn's ANSI "color_message") are not "extra" fields.
_RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "color_message"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the active trace id when there is one."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": settings.service_name,
        }
        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:
            entry["trace_id"] = format(ctx.trace_id, "032x")
            entry["span_id"] = format(ctx.span_id, "016x")
        # Anything passed with `log.info("...", extra={"job_id": 7})` is kept.
        entry.update({k: v for k, v in vars(record).items() if k not in _RESERVED})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())
    # uvicorn and arq install their own text handlers: route them through ours instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "arq"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True


def build_tracer_provider(exporter: SpanExporter | None = None) -> TracerProvider:
    provider = TracerProvider(resource=Resource.create({"service.name": settings.service_name}))
    if exporter is None and settings.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces")
    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def _setup_metrics() -> None:
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/metrics")
    )
    metrics.set_meter_provider(
        MeterProvider(
            resource=Resource.create({"service.name": settings.service_name}),
            metric_readers=[reader],
        )
    )


def instrument_engine(engine: Any, tracer_provider: Any = None) -> None:
    """A span per SQL query. The instrumentation's declared range stops before
    SQLAlchemy 2.1, but the engine event hooks it uses are unchanged, so skip that
    check (tests/test_telemetry.py proves the spans are produced)."""
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument(
        engine=engine.sync_engine, tracer_provider=tracer_provider, skip_dep_check=True
    )


def setup_telemetry(app: Any = None, engine: Any = None) -> bool:
    """Configure logs always; traces and metrics only when an OTLP endpoint is set.

    Returns True when export is on.
    """
    configure_logging()
    if not settings.otel_exporter_otlp_endpoint:
        return False

    from opentelemetry.instrumentation.redis import RedisInstrumentor

    trace.set_tracer_provider(build_tracer_provider())
    _setup_metrics()
    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, excluded_urls="api/health")
    if engine is not None:
        instrument_engine(engine)
    RedisInstrumentor().instrument()
    logging.getLogger(__name__).info(
        "telemetry export on", extra={"otlp_endpoint": settings.otel_exporter_otlp_endpoint}
    )
    return True
