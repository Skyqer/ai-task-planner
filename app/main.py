"""FastAPI application entry point with full lifespan management."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.db.engine import engine
from app.llm.factory import get_llm_provider
from app.models import Base
from app.services.memory import MemoryManager
from app.services.planner import CorePlanner
from app.services.priority import PriorityEngine
from app.services.scheduler import SchedulerService
from app.services.weather import WeatherService
from app.transport.api.routes import api_router, set_planner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup/shutdown of all subsystems."""
    # ── Startup ──────────────────────────────────────────────────────

    # 1. Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")

    # 2. Initialize LLM provider
    llm = get_llm_provider(settings)
    logger.info("LLM provider: %s", settings.llm_provider)

    # 3. Initialize services
    weather = WeatherService(settings)
    priority = PriorityEngine(settings.timezone)
    memory = MemoryManager(settings, llm)
    planner = CorePlanner(
        llm=llm,
        weather=weather,
        memory=memory,
        priority=priority,
        timezone_name=settings.timezone,
    )

    # 4. Set planner for REST API
    set_planner(planner)

    # 5. Start scheduler
    scheduler = SchedulerService(settings)

    # 6. Start Telegram bot (if token configured)
    bot_task = None
    bot = None
    dp = None

    if settings.telegram_bot_token:
        from aiogram.types import Update
        from app.transport.telegram.bot import create_bot, create_dispatcher
        from app.transport.telegram.handlers import router as tg_router, set_planner as set_tg_planner

        bot = create_bot(settings)
        dp = create_dispatcher()

        # Inject planner into the telegram handlers
        set_tg_planner(planner)

        # Set up notification callback for scheduler
        class TelegramNotifier:
            async def send(self, user_id: int, message: str) -> None:
                try:
                    await bot.send_message(user_id, message, parse_mode="HTML")
                except Exception as exc:
                    logger.error("Telegram send failed: %s", exc)

        scheduler.set_notifier(TelegramNotifier())
        scheduler.start()

        if settings.bot_mode == "polling":
            # Start polling in background
            async def _run_polling():
                try:
                    await dp.start_polling(bot)
                except asyncio.CancelledError:
                    pass

            bot_task = asyncio.create_task(_run_polling())
            logger.info("Telegram bot started (polling)")

        elif settings.bot_mode == "webhook":
            webhook_url = settings.webhook_url.rstrip("/") + "/telegram/webhook"
            await bot.set_webhook(
                url=webhook_url,
                secret_token=settings.webhook_secret or None,
            )
            logger.info("Telegram webhook set: %s", webhook_url)

            # Add webhook endpoint
            @app.post("/telegram/webhook")
            async def telegram_webhook(update: dict):
                tg_update = Update(**update)
                await dp.feed_update(bot, tg_update)
                return {"ok": True}

    else:
        scheduler.start()
        logger.warning("TELEGRAM_BOT_TOKEN not set — bot disabled")

    logger.info("Application started")
    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    scheduler.shutdown()

    if bot_task:
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass

    if bot:
        await bot.session.close()

    await engine.dispose()
    logger.info("Application stopped")


app = FastAPI(
    title="Task Planner",
    description="AI-powered personal task planner",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(api_router)
