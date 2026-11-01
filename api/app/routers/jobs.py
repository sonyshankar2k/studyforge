"""Protocol digitization endpoints.

POST /api/studies/{id}/digitize   upload a protocol, start a background job (202)
GET  /api/studies/{id}/jobs       recent jobs for a study
GET  /api/jobs/{id}               one job (status, progress, result)
POST /api/jobs/{id}/cancel        stop a queued or running job
POST /api/jobs/{id}/retry         run a failed or cancelled job again
POST /api/jobs/{id}/apply         add the reviewed, selected items to the study
"""

import logging
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.deps import CurrentUserDep, Id, SessionDep, current_user
from app.digitize.pipeline import job_event
from app.editing import notify, record_audit, to_dict
from app.errors import unprocessable
from app.events import get_bus
from app.models import Arm, DigitizationJob, JobStatus, Objective, Study
from app.queue import JobQueue, get_queue
from app.routers.studies import ARM_FIELDS, OBJECTIVE_FIELDS
from app.schemas import ApplyRequest, ApplyResult, ArmCreate, JobOut, ObjectiveCreate
from app.storage import Storage, get_storage

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["digitization"], dependencies=[Depends(current_user)])

QueueDep = Annotated[JobQueue, Depends(get_queue)]
StorageDep = Annotated[Storage, Depends(get_storage)]

ALLOWED_TYPES = {"application/pdf": ".pdf", "text/plain": ".txt"}
PDF_MAGIC = b"%PDF-"


async def _get_job(session, job_id: Id) -> DigitizationJob:
    job = await session.get(DigitizationJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Job {job_id} not found")
    return job


async def _publish(job: DigitizationJob) -> None:
    await get_bus().publish(job.study_id, job_event(job))


def _detect_type(upload: UploadFile, head: bytes) -> str:
    """Trust the file's bytes, not just its name or the browser's claimed type."""
    name = (upload.filename or "").lower()
    if head.startswith(PDF_MAGIC):
        return "application/pdf"
    if name.endswith(".txt") or upload.content_type == "text/plain":
        try:
            head.decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            pass
    raise HTTPException(
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a PDF or a plain-text (.txt) protocol."
    )


@router.post(
    "/studies/{study_id}/digitize",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={200: {"description": "Same Idempotency-Key as an earlier upload: that job"}},
)
async def start_digitization(
    study_id: Id,
    file: Annotated[UploadFile, File(description="Protocol PDF or .txt")],
    idempotency_key: Annotated[str, Header(min_length=8, max_length=100)],
    response: Response,
    session: SessionDep,
    user: CurrentUserDep,
    queue: QueueDep,
    storage: StorageDep,
):
    """Upload a protocol and start an AI extraction job.

    Send a unique `Idempotency-Key` header per upload (the web app uses a UUID).
    If the request is retried with the same key (say, after a network timeout),
    you get the original job back instead of a duplicate job and duplicate cost.
    """
    if await session.get(Study, study_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Study {study_id} not found")

    existing = await _find_by_key(session, user.id, idempotency_key)
    if existing:
        return _replay(existing, study_id, response)

    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"File is larger than {settings.max_upload_mb} MB."
        )
    if not data:
        raise unprocessable("The file is empty.", "file")
    content_type = _detect_type(file, data[:1024])

    key = await storage.save(data, ALLOWED_TYPES[content_type])
    job = DigitizationJob(
        study_id=study_id,
        created_by_id=user.id,
        created_by=user.email,
        idempotency_key=idempotency_key,
        filename=PurePath(file.filename or "protocol").name[:255],
        content_type=content_type,
        size_bytes=len(data),
        storage_key=key,
    )
    session.add(job)
    try:
        await session.commit()
    except IntegrityError:
        # Two identical requests raced each other; the other one won. Return its job.
        await session.rollback()
        await storage.delete(key)
        existing = await _find_by_key(session, user.id, idempotency_key)
        if existing is None:
            raise
        return _replay(existing, study_id, response)

    try:
        await queue.enqueue(job.id, job.runs)
    except Exception:
        log.exception("Could not enqueue job %s", job.id)
        job.status = JobStatus.FAILED
        job.stage = "Failed"
        job.error = "The background worker queue is unavailable. Try again shortly."
        job.finished_at = datetime.now(UTC)
        await session.commit()

    await session.refresh(job)
    await _publish(job)
    return job


async def _find_by_key(session, user_id: int, key: str) -> DigitizationJob | None:
    stmt = select(DigitizationJob).where(
        DigitizationJob.created_by_id == user_id, DigitizationJob.idempotency_key == key
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _replay(job: DigitizationJob, study_id: Id, response: Response) -> DigitizationJob:
    if job.study_id != study_id:
        raise unprocessable("This Idempotency-Key was already used for a different study.")
    response.status_code = status.HTTP_200_OK
    response.headers["Idempotent-Replayed"] = "true"
    return job


@router.get("/studies/{study_id}/jobs", response_model=list[JobOut])
async def list_jobs(study_id: Id, session: SessionDep):
    stmt = (
        select(DigitizationJob)
        .where(DigitizationJob.study_id == study_id)
        .order_by(DigitizationJob.id.desc())
        .limit(20)
    )
    return (await session.execute(stmt)).scalars().all()


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: Id, session: SessionDep):
    return await _get_job(session, job_id)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: Id, session: SessionDep, queue: QueueDep):
    job = await _get_job(session, job_id)
    if job.is_terminal:
        raise HTTPException(status.HTTP_409_CONFLICT, f"The job has already {job.status}.")

    if job.status == JobStatus.QUEUED:
        # Not started yet: cancel right away. If a worker picks it up later it skips it.
        job.status = JobStatus.CANCELLED
        job.stage = "Cancelled"
        job.finished_at = datetime.now(UTC)
    else:
        # Running: ask the worker to stop at the next checkpoint.
        job.cancel_requested = True
        job.stage = "Cancelling…"
    await session.commit()
    await session.refresh(job)

    try:
        await queue.abort(job.id, job.runs)
    except Exception:
        log.warning("Abort signal for job %s failed; the worker will see the flag", job.id)

    await _publish(job)
    return job


@router.post("/jobs/{job_id}/retry", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def retry_job(job_id: Id, session: SessionDep, queue: QueueDep):
    job = await _get_job(session, job_id)
    if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Only failed or cancelled jobs can be retried."
        )

    job.status = JobStatus.QUEUED
    job.progress = 0
    job.stage = "Waiting for a worker"
    job.error = None
    job.result = None
    job.attempts = 0
    job.cancel_requested = False
    job.finished_at = None
    job.runs += 1
    await session.commit()
    await session.refresh(job)

    try:
        await queue.enqueue(job.id, job.runs)
    except Exception:
        log.exception("Could not enqueue retry of job %s", job.id)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "The background worker queue is unavailable."
        ) from None

    await _publish(job)
    return job


@router.post("/jobs/{job_id}/apply", response_model=ApplyResult)
async def apply_job(job_id: Id, body: ApplyRequest, session: SessionDep, user: CurrentUserDep):
    """Add the items a person selected after reviewing the AI's proposal."""
    job = await _get_job(session, job_id)
    if job.status != JobStatus.SUCCEEDED or not job.result:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only finished jobs can be applied.")
    if job.applied_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "These results were already added.")
    if not body.arms and not body.objectives:
        raise unprocessable("Select at least one item.")

    proposed_arms = job.result.get("arms", [])
    proposed_objectives = job.result.get("objectives", [])
    arms: list[ArmCreate] = []
    objectives: list[ObjectiveCreate] = []
    try:
        for i in sorted(set(body.arms)):
            arms.append(ArmCreate.model_validate(_pick(proposed_arms, i, "arm")))
        for i in sorted(set(body.objectives)):
            objectives.append(
                ObjectiveCreate.model_validate(_pick(proposed_objectives, i, "objective"))
            )
    except ValidationError as exc:
        reason = exc.errors()[0]["msg"].removeprefix("Value error, ")
        raise unprocessable(reason) from None

    source = f"AI extraction from {job.filename} (job {job.id})"
    for arm_in in arms:
        arm = Arm(study_id=job.study_id, **arm_in.model_dump())
        session.add(arm)
        await session.flush()
        record_audit(
            session,
            study_id=job.study_id,
            entity_type="arm",
            entity_id=arm.id,
            action="create",
            changes={**to_dict(arm, ARM_FIELDS), "source": source},
            user=user.email,
        )
    for obj_in in objectives:
        obj = Objective(study_id=job.study_id, **obj_in.model_dump())
        session.add(obj)
        await session.flush()
        record_audit(
            session,
            study_id=job.study_id,
            entity_type="objective",
            entity_id=obj.id,
            action="create",
            changes={**to_dict(obj, OBJECTIVE_FIELDS), "source": source},
            user=user.email,
        )

    job.applied_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(job)

    await notify(job.study_id, "study", job.study_id, "update", user.email)
    await _publish(job)
    return ApplyResult(arms_added=len(arms), objectives_added=len(objectives))


def _pick(items: list, index: int, kind: str) -> dict:
    if not 0 <= index < len(items):
        raise unprocessable(f"No extracted {kind} #{index}")
    return items[index]
