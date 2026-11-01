"""Observability: job spans + metrics, HTTP spans, and JSON logs that carry the trace id."""

import io
import json
import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.digitize.errors import PermanentJobError
from app.telemetry import JsonFormatter
from tests.test_jobs import FailingExtractor, make_runner, upload

SPANS = InMemorySpanExporter()
METRICS = InMemoryMetricReader()
PROVIDER = TracerProvider()
PROVIDER.add_span_processor(SimpleSpanProcessor(SPANS))
# Global providers can be set once per process; only this module sets them.
trace.set_tracer_provider(PROVIDER)
metrics.set_meter_provider(MeterProvider(metric_readers=[METRICS]))


@pytest.fixture(autouse=True)
def clear_spans():
    SPANS.clear()


def job_counts() -> dict[tuple[str, str], int]:
    counts = {}
    for rm in METRICS.get_metrics_data().resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == "studyforge.digitization.jobs":
                    for point in metric.data.data_points:
                        key = (point.attributes["outcome"], point.attributes["extractor"])
                        counts[key] = point.value
    return counts


async def test_a_job_run_is_one_trace_with_a_span_per_step(client, study, session_factory, storage):
    job = (await upload(client, study["id"])).json()
    await make_runner(session_factory, storage).run(job["id"])

    spans = {s.name: s for s in SPANS.get_finished_spans()}
    root = spans["digitization.job"]
    assert root.attributes["job.id"] == job["id"]
    assert root.attributes["job.outcome"] == "succeeded"
    for child in ("storage.read", "document.extract_text", "extractor.extract"):
        assert spans[child].parent.span_id == root.context.span_id
        assert spans[child].context.trace_id == root.context.trace_id
    assert [e.name for e in root.events] == [
        "Reading the document",
        "Finding arms and objectives (rule-based parser)",
        "Checking the results",
    ]
    assert job_counts()[("succeeded", "rules")] >= 1


async def test_a_failed_job_marks_its_span_as_an_error(client, study, session_factory, storage):
    job = (await upload(client, study["id"])).json()
    runner = make_runner(session_factory, storage, FailingExtractor(PermanentJobError("bad key")))
    await runner.run(job["id"])

    root = next(s for s in SPANS.get_finished_spans() if s.name == "digitization.job")
    assert root.attributes["job.outcome"] == "failed"
    assert root.status.status_code == trace.StatusCode.ERROR
    assert job_counts()[("failed", "fake")] >= 1


async def test_http_requests_are_traced_and_logs_carry_the_trace_id():
    app = FastAPI()
    log = logging.getLogger("test.telemetry")
    out = io.StringIO()
    handler = logging.StreamHandler(out)
    handler.setFormatter(JsonFormatter())
    log.addHandler(handler)
    log.setLevel(logging.INFO)

    @app.get("/api/things/{thing_id}")
    async def get_thing(thing_id: int):
        log.info("loaded thing", extra={"thing_id": thing_id})
        return {"id": thing_id}

    FastAPIInstrumentor.instrument_app(app, tracer_provider=PROVIDER)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/api/things/7")).status_code == 200
    log.removeHandler(handler)

    server = next(s for s in SPANS.get_finished_spans() if s.kind == trace.SpanKind.SERVER)
    assert server.attributes["http.route"] == "/api/things/{thing_id}"
    line = json.loads(out.getvalue().strip())
    assert line["message"] == "loaded thing"
    assert line["thing_id"] == 7
    assert line["trace_id"] == format(server.context.trace_id, "032x")


def test_log_lines_without_a_span_have_no_trace_id():
    record = logging.makeLogRecord(
        {"name": "x", "levelname": "INFO", "msg": "hello %s", "args": ("you",)}
    )
    line = json.loads(JsonFormatter().format(record))
    assert line["message"] == "hello you"
    assert "trace_id" not in line


async def test_sql_queries_get_spans_on_this_sqlalchemy_version(tmp_path):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.telemetry import instrument_engine

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'spans.db'}")
    instrument_engine(engine, tracer_provider=PROVIDER)
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await engine.dispose()

    sql = [s for s in SPANS.get_finished_spans() if s.attributes.get("db.statement")]
    assert sql and sql[0].attributes["db.statement"] == "SELECT 1"


async def test_the_worker_span_joins_the_trace_of_the_request_that_queued_it(
    client, study, session_factory, storage
):
    from opentelemetry import propagate

    job = (await upload(client, study["id"])).json()
    tracer = PROVIDER.get_tracer("test")
    with tracer.start_as_current_span("POST /api/studies/{id}/digitize") as request_span:
        carrier: dict[str, str] = {}
        propagate.inject(carrier)  # what ArqQueue.enqueue sends with the job
    await make_runner(session_factory, storage).run(job["id"], trace_context=carrier)

    root = next(s for s in SPANS.get_finished_spans() if s.name == "digitization.job")
    assert root.context.trace_id == request_span.get_span_context().trace_id
    assert root.parent.span_id == request_span.get_span_context().span_id
