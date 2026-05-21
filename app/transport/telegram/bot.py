"""aiogram 3.x Bot and Dispatcher setup."""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import Settings


def create_bot(settings: Settings) -> Bot:
    """Create an aiogram Bot instance."""
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    """Create an aiogram Dispatcher and register handlers."""
    from app.transport.telegram.handlers import router

    dp = Dispatcher()
    dp.include_router(router)
    return dp
