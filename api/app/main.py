"""StudyForge API entry point.

Run locally:   uv run alembic upgrade head      (create/upgrade the database schema)
               uv run fastapi dev app/main.py
               uv run python -m app.worker          (background worker, needs Redis)
API docs:      http://localhost:8000/docs        (auto-generated from the code)
"""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.config import settings
from app.db import SessionLocal, engine
from app.events import RedisEventBus, forward_redis_events, set_bus
from app.models import User
from app.queue import _queue
from app.realtime import hub
from app.routers import auth, design, jobs, studies
from app.security import decode_access_token
from app.seed import seed_demo_data
from app.telemetry import setup_telemetry

log = logging.getLogger(__name__)


async def _connect_event_bus() -> tuple[Redis | None, asyncio.Task | None]:
    """Use Redis for live events when it's reachable; otherwise stay single-process."""
    redis = Redis.from_url(settings.redis_url)
    try:
        await asyncio.wait_for(redis.ping(), timeout=2)
    except Exception:
        log.warning("Redis not reachable at %s: live events stay in-process", settings.redis_url)
        await redis.aclose()
        return None, None
    set_bus(RedisEventBus(redis))
    return redis, asyncio.create_task(forward_redis_events(redis))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The schema is managed by Alembic migrations (see api/migrations), not created here.
    if settings.seed_demo_data:
        async with SessionLocal() as session:
            await seed_demo_data(session)
    redis, forwarder = await _connect_event_bus()
    yield
    if forwarder:
        forwarder.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await forwarder
    if redis:
        await redis.aclose()
    await _queue.close()
    await engine.dispose()


app = FastAPI(
    title="StudyForge API",
    description="Collaborative clinical study design editor",
    version="0.5.0",
    lifespan=lifespan,
)
setup_telemetry(app=app, engine=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(studies.router)
app.include_router(design.router)
app.include_router(jobs.router)


@app.get("/api/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws/studies/{study_id}")
async def study_updates(ws: WebSocket, study_id: int, token: str = ""):
    # Browsers can't set an Authorization header on WebSockets, so the token
    # comes as a query parameter. Reject the connection if it's not valid.
    user_id = decode_access_token(token)
    async with SessionLocal() as session:
        user = await session.get(User, user_id) if user_id is not None else None
    if user is None:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await hub.join(study_id, ws)
    try:
        while True:
            await ws.receive_text()  # client pings keep the connection alive
    except WebSocketDisconnect:
        hub.leave(study_id, ws)
