"""Background worker (arq + Redis). Runs as its own process / container:

    uv run arq app.worker.WorkerSettings

The API puts a job id on the Redis queue; this worker picks it up and runs the
pipeline. Retries use arq's built-in Retry with our exponential backoff.
"""

import logging

from arq import Retry
from arq.connections import RedisSettings
from redis.asyncio import Redis

from app.config import settings
from app.db import SessionLocal
from app.digitize.extractors import get_extractor
from app.digitize.pipeline import JobRunner, RetryLater
from app.events import RedisEventBus
from app.storage import get_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def digitize_protocol(ctx: dict, job_id: int) -> str:
    runner: JobRunner = ctx["runner"]
    outcome = await runner.run(job_id, attempt=ctx["job_try"])
    if isinstance(outcome, RetryLater):
        raise Retry(defer=outcome.defer_seconds)
    return "done"


async def startup(ctx: dict) -> None:
    redis = Redis.from_url(settings.redis_url)
    ctx["events_redis"] = redis
    ctx["runner"] = JobRunner(
        SessionLocal,
        get_storage(),
        get_extractor,
        RedisEventBus(redis),
        max_tries=settings.job_max_tries,
        retry_base_seconds=settings.job_retry_base_seconds,
        stage_delay=settings.job_stage_delay_seconds,
    )


async def shutdown(ctx: dict) -> None:
    await ctx["events_redis"].aclose()


class WorkerSettings:
    functions = [digitize_protocol]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_tries = settings.job_max_tries
    job_timeout = 300  # seconds; a stuck LLM call can't hold a worker forever
    allow_abort_jobs = True  # lets the API's cancel interrupt a running job
