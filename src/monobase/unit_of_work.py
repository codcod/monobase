import abc
import typing as tp
from typing import Self

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncTransaction


class AbstractUnitOfWork(abc.ABC):
    """
    One business transaction: `async with uow: ...; await uow.commit()`.
    Exiting the block without calling `commit()` — whether the body raised
    or just forgot — rolls back, same as the book's UoW: correctness doesn't
    depend on every caller remembering to handle the failure path.
    """

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.rollback()

    @abc.abstractmethod
    async def commit(self) -> None: ...

    @abc.abstractmethod
    async def rollback(self) -> None: ...


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    """
    Owns one `AsyncConnection` + transaction for the lifetime of the `async
    with` block. Service-specific subclasses override `__aenter__` to also
    construct their repositories bound to `self.connection`, then call
    `super().__aenter__()` — mirrors the book's per-context
    `SqlAlchemyUnitOfWork.__enter__` attaching `self.batches = ...`.
    """

    engine: AsyncEngine
    connection: AsyncConnection
    transaction: AsyncTransaction
    _committed: bool

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    @tp.override
    async def __aenter__(self) -> Self:
        self.connection = await self.engine.connect()
        self.transaction = await self.connection.begin()
        self._committed = False
        return await super().__aenter__()

    @tp.override
    async def __aexit__(self, *exc: object) -> None:
        await super().__aexit__(*exc)
        await self.connection.close()

    @tp.override
    async def commit(self) -> None:
        await self.transaction.commit()
        self._committed = True

    @tp.override
    async def rollback(self) -> None:
        # A transaction already committed can't be rolled back too — only
        # roll back if `commit()` was never reached (exception or a caller
        # that just forgot).
        if not self._committed:
            await self.transaction.rollback()
