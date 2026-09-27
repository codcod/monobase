import asyncio

import sqlalchemy as sa
from alembic import context
from sqlalchemy.ext.asyncio import AsyncEngine

from .db import make_engine


def _do_run_migrations(connection: sa.Connection, target_metadata: sa.MetaData) -> None:
    # Services may share one physical database, so each service's migration
    # history has to live in its own schema's alembic_version table —
    # otherwise every service fights over the same public.alembic_version
    # row and stamps each other's revisions.
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=target_metadata.schema,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations(
    engine: AsyncEngine, target_metadata: sa.MetaData
) -> None:
    assert target_metadata.schema is not None, "target_metadata needs a schema"

    async with engine.connect() as connection:
        # The schema has to exist before alembic can even check its
        # version table inside that schema — the first migration's own
        # CREATE SCHEMA runs too late for that first check.
        _ = await connection.execute(
            sa.schema.CreateSchema(target_metadata.schema, if_not_exists=True)
        )
        await connection.commit()
        await connection.run_sync(_do_run_migrations, target_metadata)
    await engine.dispose()


def run_migrations_online(target_metadata: sa.MetaData, dsn: str) -> None:
    """
    Standard Alembic `env.py` online-mode entry point for an async
    SQLAlchemy engine. Every service's `migrations/env.py` calls this the
    same way, passing its own `target_metadata` (one schema) and its own
    DSN. `context` is alembic's own global, the same singleton every
    `env.py` already imports.
    """
    engine = make_engine(dsn)
    asyncio.run(_run_async_migrations(engine, target_metadata))
