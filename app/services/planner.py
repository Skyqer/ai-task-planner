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
                 constraints: ConstraintService,
                 timezone_name: str = "Europe/Kyiv") -> None:
        self._llm = llm
        self._weather = weather
        self._memory = memory
        self._priority = priority
        self._constraints = constraints
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
        await self._constraints.ensure_defaults(session, user_id)
        
        await self._memory.add_message(session, user_id, "user", text)

        context = await self._memory.get_context(session, user_id)
        is_morning = any(kw in text.lower().strip() for kw in _MORNING_KEYWORDS)

        weather_data: WeatherData | None = None
        if is_morning:
            weather_data = await self._weather.get_current_weather()

        now = self._now()
        weather_text = weather_data.to_context_string() if weather_data else "Данные о погоде недоступны."

        user_constraints = await self._constraints.get_constraints(session, user_id)
        constraints_text = "\n".join(
            f"- {c.label} ({c.start_time}-{c.end_time})" for c in user_constraints
        ) if user_constraints else "Нет блокировок в расписании."

        system = SYSTEM_PROMPT.format(
            current_datetime=now.strftime("%Y-%m-%d %H:%M:%S"),
            timezone=self._tz_name,
            weather_data=weather_text,
            existing_tasks=context.active_tasks_text,
            existing_constraints=constraints_text,
            conversation_context=context.to_context_string(),
        )

        try:
            response = await self._llm.generate_parsed(system_prompt=system, user_message=text)
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            response = PlannerResponseSchema(
                summary="Произошла техническая заминка при обращении к ИИ. Попробуйте ещё раз или переформулируйте запрос.",
                warnings=["Сервис ИИ временно недоступен или вернул пустой ответ."],
            )

        response = self._priority.process(response, weather=weather_data, original_text=text)

        # Process deleted constraints
        for label in response.deleted_constraints:
            try:
                removed = await self._constraints.remove_constraint_by_label(session, user_id, label)
                if not removed:
                    response.warnings.append(f"Не удалось найти правило в расписании для удаления: '{label}'")
            except Exception as exc:
                logger.error("Failed to remove constraint '%s': %s", label, exc)

        # Process added constraints
        for c in response.added_constraints:
            try:
                from app.models.constraint import ConstraintType
                ctype = ConstraintType(c.constraint_type) if c.constraint_type in [t.value for t in ConstraintType] else ConstraintType.UNAVAILABLE
                await self._constraints.add_constraint(
                    session=session,
                    user_id=user_id,
                    constraint_type=ctype,
                    start_time=c.start_time,
                    end_time=c.end_time,
                    label=c.label
                )
            except Exception as exc:
                logger.error("Failed to add constraint '%s': %s", c.label, exc)
                response.warnings.append(f"Не удалось добавить правило '{c.label}'")

        for task in response.tasks:
            try:
                await self._save_task(session, user_id, task, self._tz_name)
            except Exception as exc:
                logger.error("Failed to save task '%s': %s", task.title, exc)
                response.warnings.append(f"Не удалось сохранить: '{task.title}'")

        await self._memory.add_message(session, user_id, "assistant", response.summary or "OK")
        return response

    @staticmethod
    async def _save_task(session: AsyncSession, user_id: int, task, tz_name: str = "Europe/Kyiv") -> None:
        from datetime import datetime, timezone, timedelta
        try:
            from zoneinfo import ZoneInfo
            tz_info = ZoneInfo(tz_name)
            offset = tz_info.utcoffset(datetime.now(tz_info))
            tz = timezone(offset)
        except Exception:
            tz = timezone(timedelta(hours=2))

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
                    kwargs["deadline_time"] = time_type(int(p[0]), int(p[1]), tzinfo=tz)
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
                    kwargs["fixed_time_time"] = time_type(int(p[0]), int(p[1]), tzinfo=tz)
                except (ValueError, IndexError):
                    pass
        task_orm = await repo.create_task(session, user_id, **kwargs)
        
        # Auto-create reminder (2 hours before) if fixed_time or deadline is set
        remind_time = None
        if task_orm.fixed_time_date and task_orm.fixed_time_time:
            dt = datetime.combine(task_orm.fixed_time_date, task_orm.fixed_time_time)
            # Make timezone aware if needed, assuming local timezone for now
            try:
                from zoneinfo import ZoneInfo
                # Use a default or passed timezone, hardcode Kyiv for now as in planner init
                tz = ZoneInfo("Europe/Kyiv")
                dt = dt.replace(tzinfo=tz)
            except Exception:
                pass
            remind_time = dt - timedelta(hours=2)
        elif task_orm.deadline_date and task_orm.deadline_time:
            dt = datetime.combine(task_orm.deadline_date, task_orm.deadline_time)
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo("Europe/Kyiv")
                dt = dt.replace(tzinfo=tz)
            except Exception:
                pass
            remind_time = dt - timedelta(hours=2)
            
        if remind_time:
            # Only create reminder if it's in the future
            now = datetime.now(remind_time.tzinfo)
            if remind_time > now:
                await repo.create_reminder(
                    session,
                    task_id=task_orm.id,
                    user_id=user_id,
                    remind_at=remind_time,
                    task_title=task_orm.title,
                )
