from sqlalchemy.ext.asyncio import AsyncEngine

from monobase.db import make_engine


def test_make_engine_returns_async_engine_without_connecting():
    engine = make_engine("postgresql+asyncpg://app:app@localhost/app")

    assert isinstance(engine, AsyncEngine)
