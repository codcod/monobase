import pytest

from monolith_base.unit_of_work import AbstractUnitOfWork, SqlAlchemyUnitOfWork


class FakeTransaction:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeConnection:
    def __init__(self) -> None:
        self.closed = False
        self.transaction = FakeTransaction()

    async def begin(self) -> FakeTransaction:
        return self.transaction

    async def close(self) -> None:
        self.closed = True


class FakeEngine:
    def __init__(self) -> None:
        self.connection = FakeConnection()

    async def connect(self) -> FakeConnection:
        return self.connection


async def test_commit_marks_transaction_committed_and_closes_connection():
    uow = SqlAlchemyUnitOfWork(FakeEngine())  # type: ignore[arg-type]
    async with uow:
        await uow.commit()

    assert uow.transaction.committed
    assert not uow.transaction.rolled_back
    assert uow.connection.closed


async def test_exiting_without_commit_rolls_back():
    uow = SqlAlchemyUnitOfWork(FakeEngine())  # type: ignore[arg-type]
    async with uow:
        pass

    assert not uow.transaction.committed
    assert uow.transaction.rolled_back
    assert uow.connection.closed


async def test_exception_in_block_rolls_back_and_still_closes():
    uow = SqlAlchemyUnitOfWork(FakeEngine())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        async with uow:
            raise ValueError("boom")

    assert uow.transaction.rolled_back
    assert uow.connection.closed


async def test_rollback_after_commit_is_not_attempted_again():
    # e.g. an unrelated cleanup path calling rollback() defensively
    uow = SqlAlchemyUnitOfWork(FakeEngine())  # type: ignore[arg-type]
    async with uow:
        await uow.commit()
        await uow.rollback()

    assert not uow.transaction.rolled_back


def test_abstract_unit_of_work_cannot_be_instantiated():
    with pytest.raises(TypeError):
        AbstractUnitOfWork()  # type: ignore[abstract]
