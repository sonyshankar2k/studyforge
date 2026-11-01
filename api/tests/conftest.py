"""Test setup: each test gets a fresh in-memory SQLite database.

Fixtures:
  anon_client  - HTTP client with no credentials (for testing 401s)
  client       - HTTP client signed in as alice@test.dev
  auth         - {"alice": headers, "bob": headers, "carol": headers} to act as other users
"""

import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"  # nothing listens here: in-process events
os.environ["EXTRACTOR"] = "rules"
os.environ["JOB_STAGE_DELAY_SECONDS"] = "0"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import db as app_db  # noqa: E402
from app import main as app_main  # noqa: E402
from app.db import Base, get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.queue import get_queue  # noqa: E402
from app.storage import LocalStorage, get_storage  # noqa: E402

TEST_PASSWORD = "correct-horse-battery"


class FakeQueue:
    """Records what the API asked the worker to do, instead of using Redis."""

    def __init__(self) -> None:
        self.enqueued: list[tuple[int, int]] = []
        self.aborted: list[tuple[int, int]] = []
        self.fail = False

    async def enqueue(self, job_id: int, run: int) -> None:
        if self.fail:
            raise ConnectionError("redis down")
        self.enqueued.append((job_id, run))

    async def abort(self, job_id: int, run: int) -> None:
        self.aborted.append((job_id, run))


@pytest.fixture
def queue() -> FakeQueue:
    q = FakeQueue()
    app.dependency_overrides[get_queue] = lambda: q
    return q


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    s = LocalStorage(tmp_path / "uploads")
    app.dependency_overrides[get_storage] = lambda: s
    return s


@pytest.fixture
async def session_factory(monkeypatch, queue, storage):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    # The WebSocket endpoint opens its own session; point it at the test DB too.
    monkeypatch.setattr(app_main, "SessionLocal", factory)
    monkeypatch.setattr(app_db, "SessionLocal", factory)
    yield factory
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def anon_client(session_factory):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def auth(anon_client) -> dict[str, dict[str, str]]:
    headers = {}
    for name in ("alice", "bob", "carol"):
        resp = await anon_client.post(
            "/api/auth/register",
            json={
                "email": f"{name}@test.dev",
                "display_name": name.title(),
                "password": TEST_PASSWORD,
            },
        )
        assert resp.status_code == 201, resp.text
        headers[name] = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    return headers


@pytest.fixture
async def client(session_factory, auth):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=auth["alice"]
    ) as c:
        yield c


@pytest.fixture
async def study(client):
    resp = await client.post("/api/studies", json={"title": "Test Study", "phase": "Phase 2"})
    assert resp.status_code == 201
    return resp.json()
