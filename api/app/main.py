"""StudyForge API entry point.

Run locally:   uv run fastapi dev app/main.py
API docs:      http://localhost:8000/docs   (auto-generated from the code)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.realtime import hub
from app.routers import studies
from app.seed import seed_demo_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Starter shortcut: create tables on startup.
    # Week 1 task: switch to Alembic migrations (`alembic init`, autogenerate).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    if settings.seed_demo_data:
        async with SessionLocal() as session:
            await seed_demo_data(session)
    yield
    await engine.dispose()


app = FastAPI(
    title="StudyForge API",
    description="Collaborative clinical study design editor",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(studies.router)


@app.get("/api/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws/studies/{study_id}")
async def study_updates(ws: WebSocket, study_id: int):
    await hub.join(study_id, ws)
    try:
        while True:
            await ws.receive_text()  # client pings keep the connection alive
    except WebSocketDisconnect:
        hub.leave(study_id, ws)
