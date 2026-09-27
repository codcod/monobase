# monolith-base

Shared infrastructure library for codcod Python services: the Repository and
Unit of Work bases (Percival & Gregory, *Architecture Patterns with Python*,
on SQLAlchemy Core), an async engine factory, an Alembic online-migration
runner, and a TOML config reader with logging setup.

Depends on SQLAlchemy, asyncpg and Alembic only. Python 3.13+.

## What's in it

| Module | Contents |
|---|---|
| `monolith_base.repository` | `AbstractRepository[T]` (`add`, `get`) |
| `monolith_base.unit_of_work` | `AbstractUnitOfWork`, `SqlAlchemyUnitOfWork`: leaving `async with uow:` without `commit()` rolls back |
| `monolith_base.db` | `make_engine(dsn) -> AsyncEngine` (`pool_pre_ping=True`) |
| `monolith_base.migrations` | `run_migrations_online(target_metadata, dsn)`: creates the schema if missing and keeps `alembic_version` in it |
| `monolith_base.config` | `read_config(path) -> dict[str, Any]`, `setup_logging(level)` (UTC, `WARNING` fallback) |

## Depending on it

Releases are git tags. Pin a tag's archive URL, which needs no `git` binary
wherever `uv sync` runs (e.g. the `ghcr.io/astral-sh/uv` builder images):

```toml
[project]
dependencies = ["monolith-base"]

[tool.uv.sources]
monolith-base = { url = "https://github.com/codcod/monolith-base/archive/refs/tags/v0.1.0.tar.gz" }
```

To upgrade, change the tag in the URL and run `uv lock`. For an unreleased
change, point the source at a sibling checkout
(`{ path = "../monolith-base", editable = true }`) and don't commit that.

## Usage

```python
import typing as tp
from typing import Self

from monolith_base.unit_of_work import SqlAlchemyUnitOfWork


class OrderUnitOfWork(SqlAlchemyUnitOfWork):
    orders: SqlAlchemyOrderRepository  # your AbstractRepository[Order] subclass

    @tp.override
    async def __aenter__(self) -> Self:
        _ = await super().__aenter__()
        self.orders = SqlAlchemyOrderRepository(self.connection)
        return self
```

In `migrations/env.py`, with `metadata = sa.MetaData(schema="orders")`:

```python
from monolith_base.migrations import run_migrations_online

run_migrations_online(metadata, dsn)
```

## What goes in

Code goes into `monolith-base` when at least two services need it, or it is
already copied between repositories. Code one service needs stays in that
service until a second one appears. Future additions (an aiohttp extra,
outbox, metrics) land behind optional extras.

The design lives in the `monolith-umbrella` workspace, at
`development/monolith-base/design.md`.

See [`PACKAGING.md`](PACKAGING.md), [`RELEASING.md`](RELEASING.md) and
[`CHANGELOG.md`](CHANGELOG.md). MIT licensed.
