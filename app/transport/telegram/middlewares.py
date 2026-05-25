"""Middlewares for Telegram dispatcher."""

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.db.engine import async_session_factory


class DatabaseMiddleware(BaseMiddleware):
    """Middleware to inject SQLAlchemy async session into handlers."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with async_session_factory() as session:
            data["session"] = session
            try:
                # We can also choose to automatically commit here, or let handlers do it.
                # Since many handlers only read, or explicitly commit, we leave commit to the repo.
                result = await handler(event, data)
                # await session.commit() # Optional: auto-commit
                return result
            except Exception:
                await session.rollback()
                raise


class DependencyMiddleware(BaseMiddleware):
    """Middleware to inject application services into handlers."""

    def __init__(self, services: Dict[str, Any]):
        super().__init__()
        self.services = services

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        data.update(self.services)
        return await handler(event, data)
