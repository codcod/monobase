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
| `monobase.unit_of_work` | `AbstractUnitOfWork`, `SqlAlchemyUnitOfWork`: leaving `async with uow:` without `commit()` rolls back |
| `monobase.db` | `make_engine(dsn) -> AsyncEngine` (`pool_pre_ping=True`) |
| `monobase.migrations` | `run_migrations_online(target_metadata, dsn)`: creates the schema if missing and keeps `alembic_version` in it |
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

from monobase.unit_of_work import SqlAlchemyUnitOfWork


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

See [`PACKAGING.md`](PACKAGING.md), [`RELEASING.md`](RELEASING.md) and
[`CHANGELOG.md`](CHANGELOG.md). MIT licensed.
