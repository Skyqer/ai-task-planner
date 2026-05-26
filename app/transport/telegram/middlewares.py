"""Middlewares for Telegram dispatcher."""

import logging
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from app.db.engine import async_session_factory

logger = logging.getLogger("bot")


class LoggingMiddleware(BaseMiddleware):
    """Middleware that logs every incoming update with user info and timing."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        start = time.perf_counter()

        # Extract human-readable info from the event
        if isinstance(event, Message):
            user = event.from_user
            username = f"@{user.username}" if user and user.username else f"id={user.id if user else '?'}"
            if event.text:
                content = repr(event.text[:60]) + ("..." if len(event.text) > 60 else "")
                kind = "msg"
            elif event.voice:
                content = f"<voice {event.voice.duration}s>"
                kind = "voice"
            else:
                content = "<other>"
                kind = "update"
            logger.info("→ [%s] %s: %s", kind, username, content)
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            username = f"@{user.username}" if user and user.username else f"id={user.id if user else '?'}"
            logger.info("→ [btn] %s: %s", username, event.data)
        else:
            user = None
            username = "unknown"

        try:
            result = await handler(event, data)
            elapsed_ms = (time.perf_counter() - start) * 1000
            if isinstance(event, (Message, CallbackQuery)):
                logger.info("← [done] %s  %.0f ms", username, elapsed_ms)
            return result
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.error("← [err]  %s  %.0f ms  %s", username, elapsed_ms, exc)
            raise


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
                result = await handler(event, data)
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
