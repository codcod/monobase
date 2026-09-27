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

    def select_params(self) -> list[dict]:
        selects = [s for s, _ in self.executed if isinstance(s, Select)]
        return [s.compile().params for s in selects]

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


async def test_fetch_unpublished_limit_and_exclude(table):
    conn = FakeConnection(polls=[[], []])
    repo = OutboxRepository(conn, table)  # type: ignore[arg-type]
    await repo.fetch_unpublished(limit=5, exclude=[2, 3])
    await repo.fetch_unpublished()

    bounded, plain = (str(s.compile()) for s, _ in conn.executed)
    assert "LIMIT" in bounded
    assert "NOT IN" in bounded
    assert conn.select_params()[0] == {"id_1": [2, 3], "param_1": 5}
    assert "LIMIT" not in plain
    assert "NOT IN" not in plain


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


async def test_relay_backs_off_a_failing_row(table, monkeypatch, caplog):
    row = {"id": 2, **ROW}
    conn = FakeConnection(polls=[[row], [], [row]])
    clock = 0.0
    sleeps = 0
    monkeypatch.setattr(outbox, "_now", lambda: clock)

    async def sleep(_: float) -> None:
        nonlocal clock, sleeps
        sleeps += 1
        if sleeps == 2:
            clock = 10.0  # past the first backoff
        if sleeps == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(outbox.asyncio, "sleep", sleep)

    async def deliver(row):
        raise RuntimeError("down")

    with caplog.at_level(logging.WARNING), pytest.raises(asyncio.CancelledError):
        await run_relay(FakeEngine(conn), table, deliver)  # type: ignore[arg-type]

    first, backing_off, retried = conn.select_params()
    assert "id_1" not in first
    assert backing_off["id_1"] == [2]
    assert "id_1" not in retried
    failed = [r for r in caplog.records if "delivery failed for row 2" in r.message]
    assert len(failed) == 2
    assert failed[0].exc_info is not None
    assert failed[1].exc_info is None
    assert "attempt 2" in failed[1].message
    assert conn.updated_ids() == []


async def test_relay_times_out_a_hung_deliver(table, stop_after_polls, caplog):
    conn = FakeConnection(polls=[[{"id": 1, **ROW}]])

    async def deliver(row):
        await asyncio.Event().wait()  # sleep is patched, so hang on an event

    stop_after_polls(1)
    relay = run_relay(FakeEngine(conn), table, deliver, deliver_timeout=0.01)  # type: ignore[arg-type]
    with caplog.at_level(logging.ERROR), pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(relay, 2)

    assert "Outbox delivery failed for row 1" in caplog.text
    assert conn.updated_ids() == []


async def test_relay_logs_a_failed_mark_separately(table, stop_after_polls, caplog):
    class FailingMark(FakeConnection):
        async def execute(self, stmt, *params):
            if isinstance(stmt, Update):
                raise RuntimeError("db down")
            return await super().execute(stmt, *params)

    conn = FailingMark(polls=[[{"id": 1, **ROW}]])

    async def deliver(row):
        pass

    stop_after_polls(1)
    with caplog.at_level(logging.ERROR), pytest.raises(asyncio.CancelledError):
        await run_relay(FakeEngine(conn), table, deliver)  # type: ignore[arg-type]

    assert "Outbox mark_published failed for row 1" in caplog.text
    assert "delivery failed" not in caplog.text


async def test_relay_passes_batch_size_as_limit(table, stop_after_polls):
    conn = FakeConnection(polls=[[]])

    async def deliver(row):
        pass

    stop_after_polls(1)
    with pytest.raises(asyncio.CancelledError):
        await run_relay(FakeEngine(conn), table, deliver, batch_size=10)  # type: ignore[arg-type]

    assert conn.select_params() == [{"param_1": 10}]


async def test_relay_backoff_doubles_and_caps(table, monkeypatch):
    row = {"id": 2, **ROW}
    backoffs = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0]  # poll_interval=0.5
    # each failure is followed by a poll just before its retry-at, then one at it
    conn = FakeConnection(polls=[[row]] + [[], [row]] * len(backoffs))
    ticks, t = [], 0.0
    for backoff in backoffs:
        t += backoff
        ticks += [t - 0.01, t]
    clock = 0.0
    monkeypatch.setattr(outbox, "_now", lambda: clock)

    async def sleep(_: float) -> None:
        nonlocal clock
        if not ticks:
            raise asyncio.CancelledError
        clock = ticks.pop(0)

    monkeypatch.setattr(outbox.asyncio, "sleep", sleep)

    async def deliver(row):
        raise RuntimeError("down")

    with pytest.raises(asyncio.CancelledError):
        await run_relay(FakeEngine(conn), table, deliver)  # type: ignore[arg-type]

    first, *rest = conn.select_params()
    assert "id_1" not in first
    assert [p.get("id_1") for p in rest] == [[2], None] * len(backoffs)


async def test_relay_survives_a_row_that_never_succeeds(table, monkeypatch, caplog):
    polls = 1100  # past attempt 1024, where 2**attempts overflows a float
    conn = FakeConnection(polls=[[{"id": 1, **ROW}, {"id": 2, **ROW}]] * polls)
    clock = 0.0
    sleeps = 0
    monkeypatch.setattr(outbox, "_now", lambda: clock)

    async def sleep(_: float) -> None:
        nonlocal clock, sleeps
        clock += 100.0  # past the capped backoff
        sleeps += 1
        if sleeps == polls:
            raise asyncio.CancelledError

    monkeypatch.setattr(outbox.asyncio, "sleep", sleep)

    async def deliver(row):
        if row["id"] == 1:
            raise RuntimeError("unknown destination")

    with caplog.at_level(logging.ERROR), pytest.raises(asyncio.CancelledError):
        await run_relay(FakeEngine(conn), table, deliver)  # type: ignore[arg-type]

    assert "Outbox relay poll failed" not in caplog.text
    assert conn.updated_ids() == [2] * polls
