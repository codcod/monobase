import asyncio
import contextlib
import logging

import pytest
from sqlalchemy import DateTime, Integer, MetaData, String, Text
from sqlalchemy.sql import Insert, Select, Update

from monobase import outbox
from monobase.outbox import OutboxRepository, outbox_table, run_relay

ROW = {
    "event_id": "e1",
    "event_type": "OrderPlaced",
    "destination": "risk",
    "payload": "{}",
}


class FakeResult:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def mappings(self) -> list[dict]:
        return self.rows


class FakeConnection:
    """
    Records every `execute`. Each select pops the next entry of `polls`: a
    list of rows to return, or an exception to raise.
    """

    def __init__(self, polls: list | None = None) -> None:
        self.executed: list[tuple] = []
        self.polls = polls or []

    async def execute(self, stmt, *params):
        self.executed.append((stmt, params))
        if isinstance(stmt, Select):
            polled = self.polls.pop(0)
            if isinstance(polled, Exception):
                raise polled
            return FakeResult(polled)
        return FakeResult([])

    def updated_ids(self) -> list[int]:
        updates = [s for s, _ in self.executed if isinstance(s, Update)]
        return [s.compile().params["id_1"] for s in updates]


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    @contextlib.asynccontextmanager
    async def connect(self):
        yield self.connection

    begin = connect


@pytest.fixture
def table():
    return outbox_table(MetaData(), "orders")


@pytest.fixture
def stop_after_polls(monkeypatch):
    """Patch the relay's sleep to cancel the loop after `n` polls."""

    def patch(n: int) -> None:
        calls = 0

        async def sleep(_: float) -> None:
            nonlocal calls
            calls += 1
            if calls >= n:
                raise asyncio.CancelledError

        monkeypatch.setattr(outbox.asyncio, "sleep", sleep)

    return patch


def test_outbox_table_shape(table):
    expected = {
        "id": (Integer, False),
        "event_id": (String, False),
        "event_type": (String, False),
        "destination": (String, False),
        "payload": (Text, False),
        "created_at": (DateTime, False),
        "published_at": (DateTime, True),
    }
    assert table.name == "outbox"
    assert table.schema == "orders"
    assert list(table.c.keys()) == list(expected)
    for name, (type_, nullable) in expected.items():
        col = table.c[name]
        assert type(col.type) is type_
        assert col.nullable is nullable
    assert table.c.id.primary_key
    assert table.c.created_at.type.timezone
    assert table.c.published_at.type.timezone


async def test_add_empty_executes_nothing(table):
    conn = FakeConnection()
    await OutboxRepository(conn, table).add([])  # type: ignore[arg-type]
    assert conn.executed == []


async def test_add_inserts_rows_with_timestamps(table):
    conn = FakeConnection()
    rows = [ROW, {**ROW, "event_id": "e2"}]
    await OutboxRepository(conn, table).add(rows)  # type: ignore[arg-type]

    [(stmt, (params,))] = conn.executed
    assert isinstance(stmt, Insert)
    for row, p in zip(rows, params, strict=True):
        assert {k: p[k] for k in row} == row
        assert p["created_at"].tzinfo is not None
        assert p["published_at"] is None


async def test_fetch_unpublished_filters_orders_and_returns_dicts(table):
    conn = FakeConnection(polls=[[{"id": 1, **ROW}]])
    rows = await OutboxRepository(conn, table).fetch_unpublished()  # type: ignore[arg-type]

    assert rows == [{"id": 1, **ROW}]
    assert all(type(r) is dict for r in rows)
    sql = str(conn.executed[0][0].compile())
    assert "WHERE orders.outbox.published_at IS NULL" in sql
    assert "ORDER BY orders.outbox.id" in sql


async def test_mark_published_updates_only_that_row(table):
    conn = FakeConnection()
    await OutboxRepository(conn, table).mark_published(7)  # type: ignore[arg-type]

    [(stmt, _)] = conn.executed
    compiled = stmt.compile()
    assert "WHERE orders.outbox.id = :id_1" in str(compiled)
    assert compiled.params["id_1"] == 7
    assert compiled.params["published_at"].tzinfo is not None


async def test_relay_failed_delivery_does_not_block_the_rest(table, stop_after_polls):
    conn = FakeConnection(polls=[[{"id": i, **ROW} for i in (1, 2, 3)]])
    delivered = []

    async def deliver(row):
        delivered.append(row["id"])
        if row["id"] == 2:
            raise RuntimeError("down")

    stop_after_polls(1)
    with pytest.raises(asyncio.CancelledError):
        await run_relay(FakeEngine(conn), table, deliver)  # type: ignore[arg-type]

    assert delivered == [1, 2, 3]
    assert conn.updated_ids() == [1, 3]


async def test_relay_survives_a_failed_poll(table, stop_after_polls, caplog):
    conn = FakeConnection(polls=[RuntimeError("db down"), [{"id": 5, **ROW}]])
    delivered = []

    async def deliver(row):
        delivered.append(row["id"])

    stop_after_polls(2)
    with caplog.at_level(logging.ERROR), pytest.raises(asyncio.CancelledError):
        await run_relay(FakeEngine(conn), table, deliver)  # type: ignore[arg-type]

    assert "Outbox relay poll failed" in caplog.text
    assert delivered == [5]
    assert conn.updated_ids() == [5]
