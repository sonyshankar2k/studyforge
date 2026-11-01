"""Protocol digitization: upload, idempotency, cancel, retry, the worker pipeline, apply."""

from pathlib import Path

import pytest

from app.digitize.errors import PermanentJobError, TransientJobError
from app.digitize.extractors import RulesExtractor
from app.digitize.pipeline import JobRunner, RetryLater
from app.digitize.schema import ExtractedProtocol

SAMPLE_PDF = Path(__file__).resolve().parents[2] / "samples" / "BREATHE-2_protocol_synopsis.pdf"


async def upload(
    client,
    study_id: int,
    key: str = "key-0001",
    data: bytes | None = None,
    name: str = "protocol.pdf",
    content_type: str = "application/pdf",
):
    data = SAMPLE_PDF.read_bytes() if data is None else data
    return await client.post(
        f"/api/studies/{study_id}/digitize",
        files={"file": (name, data, content_type)},
        headers={"Idempotency-Key": key},
    )


class RecordingBus:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def publish(self, study_id: int, event: dict) -> None:
        self.events.append(event)


class FailingExtractor:
    name = "fake"

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def extract(self, text: str) -> ExtractedProtocol:
        raise self.error


def make_runner(session_factory, storage, extractor=None, bus=None) -> JobRunner:
    return JobRunner(
        session_factory,
        storage,
        lambda: extractor or RulesExtractor(),
        bus or RecordingBus(),
        max_tries=3,
        retry_base_seconds=5,
    )


# ------------------------------------------------------------------ upload + idempotency


async def test_upload_starts_a_queued_job(client, study, queue, storage):
    resp = await upload(client, study["id"])
    assert resp.status_code == 202
    job = resp.json()
    assert job["status"] == "queued"
    assert job["filename"] == "protocol.pdf"
    assert job["created_by"] == "alice@test.dev"
    assert queue.enqueued == [(job["id"], 1)]


async def test_same_idempotency_key_returns_the_same_job(client, study, queue):
    first = await upload(client, study["id"], key="retry-me-123")
    second = await upload(client, study["id"], key="retry-me-123")
    assert second.status_code == 200
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.json()["id"] == first.json()["id"]
    assert len(queue.enqueued) == 1  # no duplicate work


async def test_same_key_from_another_user_is_a_new_job(client, study, auth, queue):
    await upload(client, study["id"], key="shared-key-1")
    other = await client.post(
        f"/api/studies/{study['id']}/digitize",
        files={"file": ("p.pdf", SAMPLE_PDF.read_bytes(), "application/pdf")},
        headers={**auth["bob"], "Idempotency-Key": "shared-key-1"},
    )
    assert other.status_code == 202
    assert len(queue.enqueued) == 2


async def test_reusing_a_key_for_another_study_is_rejected(client, study):
    other = (await client.post("/api/studies", json={"title": "Other study"})).json()
    await upload(client, study["id"], key="key-for-one")
    resp = await upload(client, other["id"], key="key-for-one")
    assert resp.status_code == 422


async def test_idempotency_key_is_required(client, study):
    resp = await client.post(
        f"/api/studies/{study['id']}/digitize",
        files={"file": ("p.pdf", SAMPLE_PDF.read_bytes(), "application/pdf")},
    )
    assert resp.status_code == 422


async def test_rejects_files_that_are_not_pdf_or_text(client, study):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
    resp = await upload(client, study["id"], data=png, name="scan.png", content_type="image/png")
    assert resp.status_code == 415


async def test_rejects_a_pdf_name_that_is_not_really_a_pdf(client, study):
    resp = await upload(client, study["id"], data=b"\xff\xfe not a pdf", name="fake.pdf")
    assert resp.status_code == 415


async def test_accepts_plain_text(client, study):
    resp = await upload(
        client, study["id"], data=b"Arm A: Drug 5 mg daily", name="p.txt", content_type="text/plain"
    )
    assert resp.status_code == 202


async def test_rejects_empty_and_oversized_files(client, study, monkeypatch):
    assert (await upload(client, study["id"], key="empty-file", data=b"")).status_code == 422
    monkeypatch.setattr("app.routers.jobs.settings.max_upload_mb", 0)
    assert (await upload(client, study["id"], key="too-big-1")).status_code == 413


async def test_unavailable_queue_marks_the_job_failed(client, study, queue):
    queue.fail = True
    resp = await upload(client, study["id"])
    assert resp.status_code == 202
    assert resp.json()["status"] == "failed"
    assert "unavailable" in resp.json()["error"]


async def test_job_endpoints_require_sign_in(anon_client):
    assert (await anon_client.get("/api/jobs/1")).status_code == 401
    assert (await anon_client.post("/api/jobs/1/cancel")).status_code == 401


# ------------------------------------------------------------------ worker pipeline


async def test_worker_extracts_arms_and_objectives(client, study, session_factory, storage):
    job = (await upload(client, study["id"])).json()
    bus = RecordingBus()

    outcome = await make_runner(session_factory, storage, bus=bus).run(job["id"])

    assert outcome is None
    done = (await client.get(f"/api/jobs/{job['id']}")).json()
    assert done["status"] == "succeeded"
    assert done["progress"] == 100
    assert done["stage"] == "Found 3 arms and 4 objectives"
    assert done["extractor"] == "rules"
    assert [a["arm_type"] for a in done["result"]["arms"]] == [
        "experimental",
        "active_comparator",
        "placebo",
    ]
    # Progress was streamed: running -> stages -> succeeded
    progress = [e["job"]["progress"] for e in bus.events]
    assert progress == sorted(progress) and progress[-1] == 100


async def test_transient_errors_are_retried_with_backoff(client, study, session_factory, storage):
    job = (await upload(client, study["id"])).json()
    runner = make_runner(
        session_factory, storage, FailingExtractor(TransientJobError("rate limited"))
    )

    assert await runner.run(job["id"], attempt=1) == RetryLater(5)
    queued = (await client.get(f"/api/jobs/{job['id']}")).json()
    assert queued["status"] == "queued"
    assert "Retrying in 5s (attempt 2 of 3)" in queued["stage"]

    assert await runner.run(job["id"], attempt=2) == RetryLater(10)

    assert await runner.run(job["id"], attempt=3) is None
    failed = (await client.get(f"/api/jobs/{job['id']}")).json()
    assert failed["status"] == "failed"
    assert "Gave up after 3 attempts" in failed["error"]


async def test_permanent_errors_fail_without_retrying(client, study, session_factory, storage):
    job = (await upload(client, study["id"])).json()
    runner = make_runner(session_factory, storage, FailingExtractor(PermanentJobError("bad key")))
    assert await runner.run(job["id"]) is None
    failed = (await client.get(f"/api/jobs/{job['id']}")).json()
    assert failed["status"] == "failed"
    assert failed["error"] == "bad key"


async def test_unreadable_pdf_fails_with_a_clear_message(client, study, session_factory, storage):
    job = (await upload(client, study["id"], data=b"%PDF-1.4 garbage")).json()
    await make_runner(session_factory, storage).run(job["id"])
    failed = (await client.get(f"/api/jobs/{job['id']}")).json()
    assert failed["status"] == "failed"
    assert "PDF" in failed["error"] or "No text" in failed["error"]


async def test_a_job_cancelled_while_queued_is_skipped(client, study, session_factory, storage):
    job = (await upload(client, study["id"])).json()
    await client.post(f"/api/jobs/{job['id']}/cancel")
    await make_runner(session_factory, storage).run(job["id"])
    assert (await client.get(f"/api/jobs/{job['id']}")).json()["status"] == "cancelled"


async def test_worker_stops_at_the_next_checkpoint_when_cancelled(
    client, study, session_factory, storage
):
    job = (await upload(client, study["id"])).json()

    class CancelDuringExtraction:
        name = "fake"

        async def extract(self, text: str) -> ExtractedProtocol:
            # The user clicks Cancel while the AI call is in flight.
            await client.post(f"/api/jobs/{job['id']}/cancel")
            return ExtractedProtocol()

    await make_runner(session_factory, storage, CancelDuringExtraction()).run(job["id"])
    done = (await client.get(f"/api/jobs/{job['id']}")).json()
    assert done["status"] == "cancelled"
    assert done["result"] is None


# ------------------------------------------------------------------ cancel + retry


async def test_cancel_a_queued_job(client, study, queue):
    job = (await upload(client, study["id"])).json()
    resp = await client.post(f"/api/jobs/{job['id']}/cancel")
    assert resp.json()["status"] == "cancelled"
    assert queue.aborted == [(job["id"], 1)]
    again = await client.post(f"/api/jobs/{job['id']}/cancel")
    assert again.status_code == 409


async def test_retry_a_failed_job(client, study, session_factory, storage, queue):
    job = (await upload(client, study["id"])).json()
    runner = make_runner(session_factory, storage, FailingExtractor(PermanentJobError("nope")))
    await runner.run(job["id"])

    resp = await client.post(f"/api/jobs/{job['id']}/retry")
    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"
    assert resp.json()["error"] is None
    assert queue.enqueued[-1] == (job["id"], 2)  # new run id, so the queue accepts it

    await make_runner(session_factory, storage).run(job["id"])
    assert (await client.get(f"/api/jobs/{job['id']}")).json()["status"] == "succeeded"


async def test_cannot_retry_a_job_that_is_still_queued(client, study):
    job = (await upload(client, study["id"])).json()
    assert (await client.post(f"/api/jobs/{job['id']}/retry")).status_code == 409


# ------------------------------------------------------------------ review + apply


@pytest.fixture
async def finished_job(client, study, session_factory, storage):
    job = (await upload(client, study["id"])).json()
    await make_runner(session_factory, storage).run(job["id"])
    return (await client.get(f"/api/jobs/{job['id']}")).json()


async def test_apply_adds_only_the_selected_items(client, study, finished_job):
    resp = await client.post(
        f"/api/jobs/{finished_job['id']}/apply", json={"arms": [0, 2], "objectives": [0]}
    )
    assert resp.status_code == 200
    assert resp.json() == {"arms_added": 2, "objectives_added": 1}

    detail = (await client.get(f"/api/studies/{study['id']}")).json()
    assert [a["name"] for a in detail["arms"]] == [
        "SF-202 20 mg once daily",
        "Matching placebo once daily",
    ]
    assert detail["objectives"][0]["level"] == "primary"

    audit = (await client.get(f"/api/studies/{study['id']}/audit")).json()
    sources = [e["changes"].get("source", "") for e in audit if e["action"] == "create"]
    assert sum("AI extraction from protocol.pdf" in s for s in sources) == 3


async def test_results_can_only_be_applied_once(client, finished_job):
    url = f"/api/jobs/{finished_job['id']}/apply"
    assert (await client.post(url, json={"arms": [0]})).status_code == 200
    assert (await client.post(url, json={"arms": [1]})).status_code == 409


async def test_apply_rejects_bad_selections(client, finished_job):
    url = f"/api/jobs/{finished_job['id']}/apply"
    assert (await client.post(url, json={})).status_code == 422
    assert (await client.post(url, json={"arms": [99]})).status_code == 422


async def test_unfinished_jobs_cannot_be_applied(client, study):
    job = (await upload(client, study["id"])).json()
    resp = await client.post(f"/api/jobs/{job['id']}/apply", json={"arms": [0]})
    assert resp.status_code == 409


async def test_list_jobs_for_a_study(client, study):
    await upload(client, study["id"], key="list-key-1")
    await upload(client, study["id"], key="list-key-2")
    jobs = (await client.get(f"/api/studies/{study['id']}/jobs")).json()
    assert len(jobs) == 2
    assert jobs[0]["id"] > jobs[1]["id"]  # newest first
