"""StudyForge API entry point.

Run locally:   uv run alembic upgrade head      (create/upgrade the database schema)
               uv run fastapi dev app/main.py
API docs:      http://localhost:8000/docs        (auto-generated from the code)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import SessionLocal, engine
from app.models import User
from app.realtime import hub
from app.routers import auth, studies
from app.security import decode_access_token
from app.seed import seed_demo_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The schema is managed by Alembic migrations (see api/migrations), not created here.
    if settings.seed_demo_data:
        async with SessionLocal() as session:
            await seed_demo_data(session)
    yield
    await engine.dispose()


app = FastAPI(
    title="StudyForge API",
    description="Collaborative clinical study design editor",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(studies.router)


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
