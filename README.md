# monobase

Shared infrastructure library featuring the Repository and Unit of Work bases
(Percival & Gregory, *Architecture Patterns with Python*, on SQLAlchemy Core),
an async engine factory, an Alembic online-migration runner, and a TOML config
reader with logging setup.

Depends on SQLAlchemy, asyncpg and Alembic only. Python 3.13+.

## What's in it

| Module | Contents |
|---|---|
| `monobase.repository` | `AbstractRepository[T]` (`add`, `get`) |
| `monobase.uow` | `AbstractUnitOfWork`, `SqlAlchemyUnitOfWork`: leaving `async with uow:` without `commit()` rolls back |
| `monobase.db` | `make_engine(dsn) -> AsyncEngine` (`pool_pre_ping=True`) |
| `monobase.migrations` | `run_migrations_online(target_metadata, dsn)`: creates the schema if missing and keeps `alembic_version` in it |
| `monobase.outbox` | `outbox_table(metadata, schema)`, `OutboxRepository`, `run_relay(engine, table, deliver)`: transactional outbox, at-least-once delivery |
| `monobase.config` | `read_config(path) -> dict[str, Any]`, `setup_logging(level)` (UTC, `WARNING` fallback) |

## Depending on it

Releases are git tags. Pin a tag's archive URL, which needs no `git` binary
wherever `uv sync` runs (e.g. the `ghcr.io/astral-sh/uv` builder images):

```toml
[project]
dependencies = ["monobase"]

[tool.uv.sources]
monobase = { url = "https://github.com/codcod/monobase/archive/refs/tags/v0.1.0.tar.gz" }
```

To upgrade, change the tag in the URL and run `uv lock`. For an unreleased
change, point the source at a sibling checkout
(`{ path = "../monobase", editable = true }`) and don't commit that.

## Usage

```python
import typing as tp

from monobase.uow import SqlAlchemyUnitOfWork


class OrderUnitOfWork(SqlAlchemyUnitOfWork):
    orders: SqlAlchemyOrderRepository  # your AbstractRepository[Order] subclass

    @tp.override
    async def __aenter__(self) -> tp.Self:
        _ = await super().__aenter__()
        self.orders = SqlAlchemyOrderRepository(self.connection)
        return self
```

In `migrations/env.py`, with `metadata = sa.MetaData(schema="orders")`:

```python
from monobase.migrations import run_migrations_online

run_migrations_online(metadata, dsn)
```

## Outbox

Bind an `OutboxRepository` in your unit of work and add rows before
`commit()`, so events commit with the state change:

```python
from monobase.outbox import OutboxRepository, outbox_table, run_relay

outbox = outbox_table(metadata, "orders")


class OrderUnitOfWork(SqlAlchemyUnitOfWork):
    @tp.override
    async def __aenter__(self) -> tp.Self:
        _ = await super().__aenter__()
        self.outbox = OutboxRepository(self.connection, outbox)
        return self

# inside `async with uow:`, before `await uow.commit()`:
await uow.outbox.add([{"event_id": ..., "event_type": "OrderPlaced",
                       "destination": "risk", "payload": json.dumps(...)}])

# at startup, with your own transport:
asyncio.create_task(run_relay(engine, outbox, deliver))
```

`deliver(row)` receives the row as a dict. A row is marked published once
`deliver` returns; raise from `deliver` to leave a row unpublished (e.g. an
unknown destination) and it is retried on the next poll.

See [`PACKAGING.md`](PACKAGING.md), [`RELEASING.md`](RELEASING.md) and
[`CHANGELOG.md`](CHANGELOG.md). MIT licensed.
