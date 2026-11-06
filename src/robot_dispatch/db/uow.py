from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from robot_dispatch.repositories.sql import (
    SqlEventRepository,
    SqlOutboxRepository,
    SqlRobotRepository,
    SqlTaskRepository,
)


class SqlUnitOfWork:
    """One database transaction per unit of work.

    The session is created on enter and closed on exit. `commit()` is explicit:
    leaving the block without a commit rolls the transaction back, exactly like a
    session that gets closed by the garbage collector in SQLAlchemy.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self.tasks: SqlTaskRepository
        self.robots: SqlRobotRepository
        self.events: SqlEventRepository
        self.outbox: SqlOutboxRepository
        self._committed = False

    async def __aenter__(self) -> SqlUnitOfWork:
        self.session = self._session_factory()
        self.tasks = SqlTaskRepository(self.session)
        self.robots = SqlRobotRepository(self.session)
        self.events = SqlEventRepository(self.session)
        self.outbox = SqlOutboxRepository(self.session)
        self._committed = False
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.session is None:
            return
        try:
            if exc_type is not None or not self._committed:
                await self.session.rollback()
        finally:
            await self.session.close()
            self.session = None

    async def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("unit of work is not started")
        await self.session.commit()
        self._committed = True

    async def rollback(self) -> None:
        if self.session is None:
            return
        await self.session.rollback()
        self._committed = False

    async def flush(self) -> None:
        if self.session is not None:
            await self.session.flush()


def make_sql_uow_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[], SqlUnitOfWork]:
    def factory() -> SqlUnitOfWork:
        return SqlUnitOfWork(session_factory)

    return factory
