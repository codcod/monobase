import abc


class AbstractRepository[T](abc.ABC):
    """
    A collection-like façade over one aggregate's storage. Concrete
    repositories live in each service's own code (there's no shared
    table/row shape to build a generic SQLAlchemy implementation against
    here — each bounded context owns its own domain type and table).
    """

    @abc.abstractmethod
    async def add(self, item: T) -> None: ...

    @abc.abstractmethod
    async def get(self, id: str) -> T | None: ...
