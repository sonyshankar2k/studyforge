"""How the API hands work to the background worker."""

from typing import Protocol

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from arq.jobs import Job

from app.config import settings


def arq_job_id(job_id: int, run: int) -> str:
    # One id per run: arq refuses duplicate ids, which also stops double-enqueueing.
    return f"digitize:{job_id}:{run}"


class JobQueue(Protocol):
    async def enqueue(self, job_id: int, run: int) -> None: ...
    async def abort(self, job_id: int, run: int) -> None: ...


class ArqQueue:
    def __init__(self) -> None:
        self._pool: ArqRedis | None = None

    async def _get_pool(self) -> ArqRedis:
        if self._pool is None:
            self._pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        return self._pool

    async def enqueue(self, job_id: int, run: int) -> None:
        pool = await self._get_pool()
        await pool.enqueue_job("digitize_protocol", job_id, _job_id=arq_job_id(job_id, run))

    async def abort(self, job_id: int, run: int) -> None:
        pool = await self._get_pool()
        # Interrupts the job if a worker is running it; harmless if it isn't.
        await Job(arq_job_id(job_id, run), pool).abort(timeout=0)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()


_queue = ArqQueue()


def get_queue() -> JobQueue:
    return _queue
