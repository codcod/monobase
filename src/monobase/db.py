from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def make_engine(dsn: str) -> AsyncEngine:
    """
    Build an async SQLAlchemy core engine for a service's database.

    Services may share one physical database; each keeps its own schema and
    defines its own `sqlalchemy.Table` objects (with `schema=<name>`)
    against this engine.
    """
    return create_async_engine(dsn, pool_pre_ping=True)
