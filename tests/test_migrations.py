import contextlib

import pytest
import sqlalchemy as sa

from monolith_base import migrations


class FakeConnection:
    def __init__(self, calls: list[object]) -> None:
        self.calls = calls

    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass

    async def execute(self, statement: object) -> None:
        self.calls.append(statement)

    async def commit(self) -> None:
        self.calls.append("commit")

    async def run_sync(self, fn, *args) -> None:
        self.calls.append("run_sync")
        fn(self, *args)


class FakeEngine:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def connect(self) -> FakeConnection:
        return FakeConnection(self.calls)

    async def dispose(self) -> None:
        self.calls.append("dispose")


@pytest.fixture
def engine(monkeypatch):
    engine = FakeEngine()
    monkeypatch.setattr(migrations, "make_engine", lambda dsn: engine)
    monkeypatch.setattr(
        migrations.context,
        "configure",
        lambda **kw: engine.calls.append(("configure", kw)),
        raising=False,
    )
    monkeypatch.setattr(
        migrations.context,
        "begin_transaction",
        contextlib.nullcontext,
        raising=False,
    )
    monkeypatch.setattr(
        migrations.context,
        "run_migrations",
        lambda: engine.calls.append("run_migrations"),
        raising=False,
    )
    return engine


# Plain `def`: run_migrations_online calls asyncio.run itself.
def test_schema_is_created_and_committed_before_alembic_runs(engine):
    migrations.run_migrations_online(sa.MetaData(schema="inbox"), "dsn")

    create, commit, run_sync, configure, run, dispose = engine.calls
    assert isinstance(create, sa.schema.CreateSchema)
    assert create.element == "inbox"
    assert create.if_not_exists
    assert (commit, run_sync, run, dispose) == (
        "commit",
        "run_sync",
        "run_migrations",
        "dispose",
    )
    assert configure[0] == "configure"


def test_version_table_lives_in_the_target_schema(engine):
    migrations.run_migrations_online(sa.MetaData(schema="inbox"), "dsn")

    [kw] = [c[1] for c in engine.calls if isinstance(c, tuple)]
    assert kw["version_table_schema"] == "inbox"


def test_metadata_without_schema_is_rejected(engine):
    with pytest.raises(AssertionError, match="needs a schema"):
        migrations.run_migrations_online(sa.MetaData(), "dsn")
