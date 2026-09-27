import asyncio
import logging
import typing as tp
from collections.abc import Awaitable, Callable, Sequence
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

    async def fetch_unpublished(self) -> list[dict[str, tp.Any]]:
        result = await self.connection.execute(
            select(self.table)
            .where(self.table.c.published_at.is_(None))
            .order_by(self.table.c.id)
        )
        return [dict(r) for r in result.mappings()]

    async def mark_published(self, row_id: int) -> None:
        await self.connection.execute(
            update(self.table)
            .where(self.table.c.id == row_id)
            .values(published_at=datetime.now(UTC))
        )


type Deliver = Callable[[dict[str, tp.Any]], Awaitable[None]]


async def run_relay(
    engine: AsyncEngine,
    table: Table,
    deliver: Deliver,
    poll_interval: float = 0.5,
) -> None:
    """
    Poll `table` forever, handing each unpublished row (oldest first) to
    `deliver` and marking it published once `deliver` returns: delivery is
    at-least-once. A row whose `deliver` raises is logged and left for the
    next poll without blocking the rest, so raise from `deliver` to leave a
    row unpublished (e.g. an unknown destination). Cancel the task to stop.
    """
    while True:
        try:
            async with engine.connect() as conn:
                rows = await OutboxRepository(conn, table).fetch_unpublished()
            for row in rows:
                try:
                    await deliver(row)
                    async with engine.begin() as conn:
                        await OutboxRepository(conn, table).mark_published(row["id"])
                except Exception:
                    logger.exception("Outbox delivery failed for row %s", row["id"])
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Outbox relay poll failed")
        await asyncio.sleep(poll_interval)
