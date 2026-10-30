"""Migration tests: the migrations build the same schema as the models, and roll back cleanly.

If someone changes a model but forgets `alembic revision --autogenerate`,
test_models_and_migrations_match fails in CI and tells them what's missing.
"""

import asyncio
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import Base

API_DIR = Path(__file__).resolve().parents[1]


def _config(url: str) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


async def _inspect(url: str, fn):
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        result = await conn.run_sync(fn)
    await engine.dispose()
    return result


def _diff(sync_conn):
    ctx = MigrationContext.configure(sync_conn, opts={"compare_type": True})
    return compare_metadata(ctx, Base.metadata)


def _tables(sync_conn):
    return set(inspect(sync_conn).get_table_names())


def test_models_and_migrations_match(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'mig.db'}"
    command.upgrade(_config(url), "head")
    diff = asyncio.run(_inspect(url, _diff))
    assert diff == [], f"Models changed without a migration: {diff}"


def test_downgrade_removes_everything(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'mig.db'}"
    cfg = _config(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    assert asyncio.run(_inspect(url, _tables)) <= {"alembic_version"}
