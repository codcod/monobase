import pytest

from monolith_base.repository import AbstractRepository


class InMemoryRepository(AbstractRepository[dict]):
    def __init__(self) -> None:
        self._items: dict[str, dict] = {}

    async def add(self, item: dict) -> None:
        self._items[item["id"]] = item

    async def get(self, id: str) -> dict | None:
        return self._items.get(id)


async def test_add_then_get_returns_the_same_item():
    repo = InMemoryRepository()
    await repo.add({"id": "1", "name": "a"})

    assert await repo.get("1") == {"id": "1", "name": "a"}


async def test_get_missing_id_returns_none():
    repo = InMemoryRepository()

    assert await repo.get("missing") is None


def test_abstract_repository_cannot_be_instantiated():
    with pytest.raises(TypeError):
        AbstractRepository()
