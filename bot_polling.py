"""Entry point for standalone Telegram bot polling."""

import asyncio
import logging

from app.config import settings
from app.db.engine import engine
from app.llm.factory import get_llm_provider
from app.models import Base
from app.services.memory import MemoryManager
from app.services.planner import CorePlanner
from app.services.priority import PriorityEngine
from app.services.scheduler import SchedulerService
from app.services.weather import WeatherService
from app.services.constraints import ConstraintService
from app.services.timeline import TimelineEngine
from app.services.voice import VoiceTranscriptionService
from app.services.rescheduler import ReschedulerService

from app.transport.telegram.bot import create_bot, create_dispatcher
from app.transport.telegram.middlewares import DatabaseMiddleware, DependencyMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set. Exiting.")
        return

    # 1. Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified")

    # 2. Initialize LLM provider
    llm = get_llm_provider(settings)

    # 3. Initialize services
    weather = WeatherService(settings)
    priority = PriorityEngine(settings.timezone)
    memory = MemoryManager(settings, llm)
    constraints = ConstraintService()
    planner = CorePlanner(
        llm=llm,
        weather=weather,
        memory=memory,
        priority=priority,
        constraints=constraints,
        timezone_name=settings.timezone,
    )
    timeline = TimelineEngine(constraints, settings.timezone, weather)
    voice = VoiceTranscriptionService(
        model_size=settings.whisper_model_size,
        unload_seconds=settings.whisper_unload_seconds,
    )
    rescheduler = ReschedulerService(timeline)

    # 4. Setup Bot and Dispatcher
    bot = create_bot(settings)
    dp = create_dispatcher()

    dp.update.middleware(DatabaseMiddleware())
    dp.update.middleware(DependencyMiddleware({
        "planner": planner,
        "timeline": timeline,
        "voice": voice,
        "constraint_service": constraints,
    }))

    # 5. Start scheduler (Optional if you run FastAPI concurrently, but needed here if standalone)
    scheduler = SchedulerService(settings)
    
    class TelegramNotifier:
        async def send(self, user_id: int, message: str) -> None:
            try:
                await bot.send_message(user_id, message, parse_mode="HTML")
            except Exception as exc:
                logger.error("Telegram send failed: %s", exc)
                
        async def send_with_keyboard(self, user_id: int, message: str, keyboard) -> None:
            try:
                await bot.send_message(user_id, message, parse_mode="HTML", reply_markup=keyboard)
            except Exception as exc:
                logger.error("Telegram send with keyboard failed: %s", exc)

    scheduler.set_notifier(TelegramNotifier())
    scheduler.set_rescheduler(rescheduler)
    scheduler.start()

    logger.info("Starting Telegram Bot in polling mode...")
    try:
        await dp.start_polling(bot)
    except asyncio.CancelledError:
        pass
    finally:
        scheduler.shutdown()
        await bot.session.close()
        await engine.dispose()
        logger.info("Bot stopped.")

if __name__ == "__main__":
    asyncio.run(main())
