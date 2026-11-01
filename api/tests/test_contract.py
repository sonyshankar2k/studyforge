"""API contract tests, generated from the OpenAPI spec by Schemathesis.

For every endpoint in /openapi.json, Schemathesis generates many requests (valid and
tricky ones: empty strings, huge numbers, odd unicode, missing fields...) and checks:
  - no request ever causes a 500 error;
  - every response matches the schema the API documents (so the Angular types,
    and anyone else relying on the spec, can trust it);
  - responses declare the right content type.

This catches "the code and the docs disagree" bugs that hand-written tests miss.
"""

import asyncio
import os
from pathlib import Path

import pytest
import schemathesis
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, settings
from schemathesis.checks import (
    content_type_conformance,
    not_a_server_error,
    response_schema_conformance,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import db as app_db
from app import main as app_main
from app.db import Base, get_session
from app.main import app
from app.queue import get_queue
from app.storage import LocalStorage, get_storage
from tests.conftest import FakeQueue

schema = schemathesis.openapi.from_asgi("/openapi.json", app)

EXAMPLES = int(os.environ.get("CONTRACT_EXAMPLES", "15"))


@pytest.fixture(scope="module")
def auth_headers(tmp_path_factory) -> dict[str, str]:
    """A file-backed database with one user and a small study, shared by all generated cases."""
    tmp = tmp_path_factory.mktemp("contract")
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{Path(tmp) / 'contract.db'}", poolclass=NullPool
    )

    async def create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(create_tables())
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with factory() as session:
            yield session

    queue, storage = FakeQueue(), LocalStorage(Path(tmp) / "uploads")
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_queue] = lambda: queue
    app.dependency_overrides[get_storage] = lambda: storage
    saved = (app_main.SessionLocal, app_db.SessionLocal)
    app_main.SessionLocal = app_db.SessionLocal = factory

    with TestClient(app) as client:
        token = client.post(
            "/api/auth/register",
            json={
                "email": "contract@test.dev",
                "display_name": "Contract",
                "password": "contract-pass",
            },
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        # Give generated requests real ids to hit (id 1 of everything).
        client.post(
            "/api/studies", json={"title": "Contract study", "acronym": "CT-1"}, headers=headers
        )
        client.post(
            "/api/studies/1/arms", json={"name": "Placebo", "arm_type": "placebo"}, headers=headers
        )
        client.post(
            "/api/studies/1/criteria",
            json={"category": "inclusion", "text": "Adults"},
            headers=headers,
        )
        client.post("/api/studies/1/encounters", json={"name": "Day 1", "day": 1}, headers=headers)
        client.post("/api/studies/1/activities", json={"name": "Vitals"}, headers=headers)

    yield headers

    app.dependency_overrides.clear()
    app_main.SessionLocal, app_db.SessionLocal = saved
    asyncio.run(engine.dispose())


@schema.parametrize()
@settings(
    max_examples=EXAMPLES,
    deadline=None,
    suppress_health_check=list(HealthCheck),
    derandomize=True,  # same cases every run: CI failures are reproducible
)
def test_api_matches_its_openapi_contract(case, auth_headers):
    case.call_and_validate(
        headers=auth_headers,
        checks=[not_a_server_error, response_schema_conformance, content_type_conformance],
    )
