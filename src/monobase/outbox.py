import asyncio
import logging
import typing as tp
from collections.abc import Awaitable, Callable, Collection, Sequence
from datetime import UTC, datetime

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    insert,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

logger = logging.getLogger(__name__)


def outbox_table(metadata: MetaData, schema: str) -> Table:
    """
    The `outbox` table in `schema`, column-for-column the shape
    stock-exchange's services already migrated, so switching a consumer
    over needs no Alembic revision.
    """
    return Table(
        "outbox",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("event_id", String, nullable=False),
        Column("event_type", String, nullable=False),
        Column("destination", String, nullable=False),
        Column("payload", Text, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("published_at", DateTime(timezone=True), nullable=True),
        schema=schema,
    )


class OutboxRow(tp.TypedDict):
    """One event to enqueue; `payload` is already serialized by the consumer."""

    event_id: str
    event_type: str
    destination: str
    payload: str


class OutboxRepository:
    """
    Outbox storage bound to one connection. A service's UoW subclass binds
    it to `self.connection` in `__aenter__` (`self.outbox =
    OutboxRepository(self.connection, table)`), so `add` lands in the same
    transaction as the state change it describes.
    """

    def __init__(self, connection: AsyncConnection, table: Table) -> None:
        self.connection = connection
        self.table = table

    async def add(self, rows: Sequence[OutboxRow]) -> None:
        if not rows:
            return
        now = datetime.now(UTC)
        await self.connection.execute(
            insert(self.table),
            [{**row, "created_at": now, "published_at": None} for row in rows],
        )

    async def fetch_unpublished(
        self, limit: int | None = None, exclude: Collection[int] = ()
    ) -> list[dict[str, tp.Any]]:
        stmt = (
            select(self.table)
            .where(self.table.c.published_at.is_(None))
            .order_by(self.table.c.id)
            .limit(limit)
        )
        if exclude:
            stmt = stmt.where(self.table.c.id.not_in(exclude))
        result = await self.connection.execute(stmt)
        return [dict(r) for r in result.mappings()]

    async def mark_published(self, row_id: int) -> None:
        await self.connection.execute(
            update(self.table)
            .where(self.table.c.id == row_id)
            .values(published_at=datetime.now(UTC))
        )


type Deliver = Callable[[dict[str, tp.Any]], Awaitable[None]]

_MAX_BACKOFF = 60.0


def _now() -> float:
    return asyncio.get_running_loop().time()


async def run_relay(  # noqa: PLR0913
    engine: AsyncEngine,
    table: Table,
    deliver: Deliver,
    poll_interval: float = 0.5,
    *,
    batch_size: int = 100,
    deliver_timeout: float = 30.0,
) -> None:
    """
    Poll `table` forever, handing up to `batch_size` unpublished rows per
    poll (oldest first) to `deliver` and marking each published once
    `deliver` returns: delivery is at-least-once. A row whose `deliver`
    raises or outlasts `deliver_timeout` is logged and retried with backoff
    (capped at 60 s) without blocking the rest, so raise from `deliver` to
    leave a row unpublished (e.g. an unknown destination). Run one relay per
    outbox table: a second relay on the same table delivers every row twice.
    Cancel the task to stop.
    """
    # ponytail: in memory, so it resets on restart, grows by one entry per row
    # that never succeeds or is published elsewhere, and a fast-failing outage
    # can put ~batch_size * 60 s / poll ids in the NOT IN list (asyncpg caps
    # binds at 32767); a persistent attempts column needs a migration.
    failures: dict[int, tuple[int, float]] = {}
    while True:
        try:
            now = _now()
            backing_off = [i for i, (_, at) in failures.items() if at > now]
            async with engine.connect() as conn:
                rows = await OutboxRepository(conn, table).fetch_unpublished(
                    limit=batch_size, exclude=backing_off
                )
            for row in rows:
                row_id = row["id"]
                try:
                    async with asyncio.timeout(deliver_timeout):
                        await deliver(row)
                except Exception as exc:
                    attempts = failures.get(row_id, (0, 0.0))[0] + 1
                    # clamp the exponent: 2**1024 overflows a float
                    exp = min(attempts, 64)
                    backoff = min(poll_interval * 2**exp, _MAX_BACKOFF)
                    failures[row_id] = (attempts, _now() + backoff)
                    if attempts == 1:
                        logger.exception("Outbox delivery failed for row %s", row_id)
                    else:
                        logger.warning(
                            "Outbox delivery failed for row %s (attempt %d): %r",
                            row_id,
                            attempts,
                            exc,
                        )
                    continue
                failures.pop(row_id, None)
                try:
                    async with engine.begin() as conn:
                        await OutboxRepository(conn, table).mark_published(row_id)
                except Exception:
                    logger.exception(
                        "Outbox mark_published failed for row %s; "
                        "it will be redelivered",
                        row_id,
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Outbox relay poll failed")
        await asyncio.sleep(poll_interval)
