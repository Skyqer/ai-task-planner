"""Core Planner — transport-agnostic orchestrator."""

from __future__ import annotations

import logging
from datetime import datetime, date as date_type, time as time_type, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository as repo
from app.llm.base import BaseLLMProvider
from app.llm.prompts import SYSTEM_PROMPT
from app.models.task import DeadlineKind, TaskStatus, TaskType
from app.schemas.planner import PlannerResponseSchema
from app.schemas.weather import WeatherData
from app.services.memory import MemoryManager
from app.services.priority import PriorityEngine
from app.services.weather import WeatherService

logger = logging.getLogger(__name__)

_MORNING_KEYWORDS = {
    "проснулся", "проснулась", "доброе утро", "утро",
    "план на день", "план дня", "что сегодня", "сводка",
    "morning", "brief",
}


class CorePlanner:
    """Orchestrator. Receives (user_id, text), returns PlannerResponse.
    Transport-agnostic — does NOT know about Telegram.
    """

    def __init__(self, llm: BaseLLMProvider, weather: WeatherService,
                 memory: MemoryManager, priority: PriorityEngine,
                 timezone_name: str = "Europe/Kyiv") -> None:
        self._llm = llm
        self._weather = weather
        self._memory = memory
        self._priority = priority
        self._tz_name = timezone_name

    def _now(self) -> datetime:
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(self._tz_name))
        except Exception:
            return datetime.now(timezone(timedelta(hours=2)))

    async def process_message(self, session: AsyncSession,
                              user_id: int, text: str) -> PlannerResponseSchema:
        await repo.get_or_create_user(session, user_id)
        await self._memory.add_message(session, user_id, "user", text)

        context = await self._memory.get_context(session, user_id)
        is_morning = any(kw in text.lower().strip() for kw in _MORNING_KEYWORDS)

        weather_data: WeatherData | None = None
        if is_morning:
            weather_data = await self._weather.get_current_weather()

        now = self._now()
        weather_text = weather_data.to_context_string() if weather_data else "Данные о погоде недоступны."

        system = SYSTEM_PROMPT.format(
            current_datetime=now.strftime("%Y-%m-%d %H:%M:%S"),
            timezone=self._tz_name,
            weather_data=weather_text,
            existing_tasks=context.active_tasks_text,
            conversation_context=context.to_context_string(),
        )

        try:
            response = await self._llm.generate_parsed(system_prompt=system, user_message=text)
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            response = PlannerResponseSchema(
                summary="Ошибка при обработке. Попробуйте ещё раз.",
                warnings=[f"LLM error: {exc}"],
            )

        response = self._priority.process(response, weather=weather_data, original_text=text)

        for task in response.tasks:
            try:
                await self._save_task(session, user_id, task)
            except Exception as exc:
                logger.error("Failed to save task '%s': %s", task.title, exc)
                response.warnings.append(f"Не удалось сохранить: '{task.title}'")

        await self._memory.add_message(session, user_id, "assistant", response.summary or "OK")
        return response

    @staticmethod
    async def _save_task(session: AsyncSession, user_id: int, task) -> None:
        kwargs: dict = {
            "title": task.title,
            "details": task.details or None,
            "type": TaskType(task.type.value) if task.type else TaskType.OTHER,
            "priority": task.priority,
            "estimated_minutes": task.estimated_minutes,
            "weather_sensitive": task.weather_sensitive,
            "tags": task.tags or None,
            "status": TaskStatus.CREATED,
        }
        if task.deadline and task.deadline.date:
            dl = task.deadline.date
            kwargs["deadline_date"] = date_type.fromisoformat(dl) if isinstance(dl, str) else dl
            if task.deadline.time:
                # Handle potential ranges like "01:00-01:30" by taking the first part
                time_str = task.deadline.time.split("-")[0].strip()
                p = time_str.split(":")
                try:
                    kwargs["deadline_time"] = time_type(int(p[0]), int(p[1]))
                except (ValueError, IndexError):
                    pass
            if task.deadline.kind:
                kwargs["deadline_kind"] = DeadlineKind(task.deadline.kind.value)
        if task.fixed_time and task.fixed_time.date:
            ft = task.fixed_time.date
            kwargs["fixed_time_date"] = date_type.fromisoformat(ft) if isinstance(ft, str) else ft
            if task.fixed_time.time:
                # Handle potential ranges like "01:00-01:30"
                time_str = task.fixed_time.time.split("-")[0].strip()
                p = time_str.split(":")
                try:
                    kwargs["fixed_time_time"] = time_type(int(p[0]), int(p[1]))
                except (ValueError, IndexError):
                    pass
        await repo.create_task(session, user_id, **kwargs)
