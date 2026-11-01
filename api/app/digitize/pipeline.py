"""What the background worker does for one digitization job.

Stages (with the progress the user sees):
     5%  Starting
    25%  Reading the document           (PDF -> text)
    45%  Finding arms and objectives    (Claude or rule-based extractor)
    90%  Checking the results
   100%  Done: "Found 3 arms and 2 objectives"

Design choices worth knowing for interviews:
- Each status update commits in its own short transaction, so the slow LLM call
  never holds a database transaction open.
- Cancellation is cooperative: the API sets `cancel_requested`, and we check it
  between stages. (The worker also gets an asyncio cancel via arq's abort.)
- Failures are classified: transient ones are retried with exponential backoff,
  permanent ones fail at once with a message a person can act on.
- Every state change is published, so every open browser sees live progress.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from opentelemetry import propagate, trace
from opentelemetry.trace import Status, StatusCode
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.digitize.errors import JobCancelled, PermanentJobError, TransientJobError
from app.digitize.extractors import Extractor
from app.digitize.text import extract_text
from app.events import EventBus
from app.models import DigitizationJob, JobStatus
from app.schemas import JobOut
from app.storage import Storage
from app.telemetry import job_duration, jobs_counter, tracer

log = logging.getLogger(__name__)


@dataclass
class RetryLater:
    """Returned when a transient error should be retried after `defer_seconds`."""

    defer_seconds: int


def job_event(job: DigitizationJob) -> dict:
    return {"type": "job", "job": JobOut.model_validate(job).model_dump(mode="json")}


class JobRunner:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: Storage,
        extractor_factory: Callable[[], Extractor],
        bus: EventBus,
        *,
        max_tries: int = 3,
        retry_base_seconds: int = 5,
        stage_delay: float = 0.0,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage
        self.extractor_factory = extractor_factory
        self.bus = bus
        self.max_tries = max_tries
        self.retry_base_seconds = retry_base_seconds
        self.stage_delay = stage_delay
        # Per-job bookkeeping for telemetry (a worker runs several jobs concurrently).
        self._last_status: dict[int, str] = {}
        self._extractor_name: dict[int, str] = {}

    # ------------------------------------------------------------------ helpers
    async def _update(self, job_id: int, **fields) -> DigitizationJob | None:
        if "status" in fields:
            self._last_status[job_id] = str(fields["status"])
        async with self.session_factory() as session:
            job = await session.get(DigitizationJob, job_id)
            if job is None:
                return None
            for key, value in fields.items():
                setattr(job, key, value)
            await session.commit()
            await session.refresh(job)
        await self.bus.publish(job.study_id, job_event(job))
        return job

    async def _stage(self, job_id: int, progress: int, stage: str) -> None:
        """Move to the next stage, unless the user asked to cancel."""
        async with self.session_factory() as session:
            job = await session.get(DigitizationJob, job_id)
            if job is None or job.cancel_requested:
                raise JobCancelled
        await self._update(job_id, progress=progress, stage=stage)
        trace.get_current_span().add_event(stage, {"job.progress": progress})
        if self.stage_delay:
            await asyncio.sleep(self.stage_delay)

    def _backoff(self, attempt: int) -> int:
        return self.retry_base_seconds * 2 ** (attempt - 1)  # 5s, 10s, 20s ...

    # ------------------------------------------------------------------ main entry
    async def run(
        self, job_id: int, attempt: int = 1, trace_context: dict | None = None
    ) -> RetryLater | None:
        """Run one attempt inside a trace span, and record the outcome as a metric.

        `trace_context` carries the uploading request's trace, so this span joins it.
        """
        started = time.perf_counter()
        with tracer.start_as_current_span(
            "digitization.job",
            context=propagate.extract(trace_context or {}),
            kind=trace.SpanKind.CONSUMER,
            attributes={"job.id": job_id, "job.attempt": attempt},
        ) as span:
            outcome = await self._run(job_id, attempt)
            status = "retry_scheduled" if isinstance(outcome, RetryLater) else self._status(job_id)
            span.set_attribute("job.outcome", status)
            if status == JobStatus.FAILED:
                span.set_status(Status(StatusCode.ERROR, "job failed"))
            attrs = {"outcome": status, "extractor": self._extractor_name.pop(job_id, "none")}
            jobs_counter.add(1, attrs)
            job_duration.record(time.perf_counter() - started, attrs)
            log.info("digitization job finished", extra={"job_id": job_id, "outcome": status})
            return outcome

    def _status(self, job_id: int) -> str:
        return self._last_status.pop(job_id, "skipped")

    async def _run(self, job_id: int, attempt: int) -> RetryLater | None:
        async with self.session_factory() as session:
            job = await session.get(DigitizationJob, job_id)
            if job is None:
                log.warning("Job %s no longer exists; skipping", job_id)
                return None
            if job.is_terminal:
                # Cancelled while queued, or a duplicate delivery: nothing to do (idempotent).
                return None
            filename, content_type, key = job.filename, job.content_type, job.storage_key

        try:
            await self._update(
                job_id,
                status=JobStatus.RUNNING,
                attempts=attempt,
                error=None,
                progress=5,
                stage="Starting",
            )

            await self._stage(job_id, 25, "Reading the document")
            with tracer.start_as_current_span("storage.read"):
                data = await self.storage.read(key)
            with tracer.start_as_current_span("document.extract_text") as span:
                text = await asyncio.to_thread(extract_text, data, content_type, filename)
                span.set_attribute("document.chars", len(text))

            extractor = self.extractor_factory()
            self._extractor_name[job_id] = extractor.name
            label = (
                "Asking Claude to find arms and objectives"
                if extractor.name == "claude"
                else "Finding arms and objectives (rule-based parser)"
            )
            await self._stage(job_id, 45, label)
            with tracer.start_as_current_span(
                "extractor.extract", attributes={"extractor": extractor.name}
            ):
                result = await extractor.extract(text)

            await self._stage(job_id, 90, "Checking the results")
            summary = (
                f"Found {_plural(len(result.arms), 'arm')} and "
                f"{_plural(len(result.objectives), 'objective')}"
            )
            await self._update(
                job_id,
                status=JobStatus.SUCCEEDED,
                progress=100,
                stage=summary,
                extractor=extractor.name,
                result=result.model_dump(mode="json"),
                finished_at=datetime.now(UTC),
            )
            return None

        except (JobCancelled, asyncio.CancelledError) as exc:
            await asyncio.shield(self._mark_cancelled(job_id))
            if isinstance(exc, asyncio.CancelledError):
                raise  # let the queue know the task was aborted
            return None

        except TransientJobError as exc:
            if attempt < self.max_tries:
                delay = self._backoff(attempt)
                await self._update(
                    job_id,
                    status=JobStatus.QUEUED,
                    progress=0,
                    stage=f"Temporary problem: {exc}. Retrying in {delay}s "
                    f"(attempt {attempt + 1} of {self.max_tries})",
                )
                return RetryLater(delay)
            await self._fail(job_id, f"{exc}. Gave up after {attempt} attempts.")
            return None

        except PermanentJobError as exc:
            await self._fail(job_id, str(exc))
            return None

        except Exception:
            log.exception("Unexpected error in job %s", job_id)
            await self._fail(job_id, "Unexpected error while processing. Please try again.")
            return None

    async def _mark_cancelled(self, job_id: int) -> None:
        await self._update(
            job_id,
            status=JobStatus.CANCELLED,
            stage="Cancelled",
            finished_at=datetime.now(UTC),
        )

    async def _fail(self, job_id: int, message: str) -> None:
        await self._update(
            job_id,
            status=JobStatus.FAILED,
            stage="Failed",
            error=message,
            finished_at=datetime.now(UTC),
        )


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"
