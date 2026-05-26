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
from app.services.constraints import ConstraintService
from app.services.reminder import ReminderService
from app.utils.time_parser import parse_time_safe
from app.utils.timezone import now_local, get_local_timezone

logger = logging.getLogger(__name__)

_MORNING_KEYWORDS = {
    "woke up", "good morning", "morning",
    "day plan", "plan for the day", "what's today", "brief",
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
        self._reminder_service = ReminderService()

    async def process_message(self, session: AsyncSession,
                               user_id: int, text: str) -> PlannerResponseSchema:
        """Main pipeline to process user input."""
        # 1. Setup user
        await repo.get_or_create_user(session, user_id)
        await self._constraints.ensure_defaults(session, user_id)
        await self._memory.add_message(session, user_id, "user", text)

        # 2. Build Context
        system_prompt, weather_data = await self._build_context(session, user_id, text)

        # 3. Call LLM
        response = await self._call_llm(system_prompt, text)

        # 4. Post-process & Execute Actions
        response = self._priority.process(response, weather=weather_data, original_text=text)
        await self._execute_actions(session, user_id, response)

        # 5. Finalize
        await self._memory.add_message(session, user_id, "assistant", response.summary or "OK")
        return response

    async def _build_context(self, session: AsyncSession, user_id: int, text: str) -> tuple[str, WeatherData | None]:
        context = await self._memory.get_context(session, user_id)
        is_morning = any(kw in text.lower().strip() for kw in _MORNING_KEYWORDS)

        weather_data: WeatherData | None = None
        if is_morning:
            weather_data = await self._weather.get_current_weather()

        now = now_local(self._tz_name)
        weather_text = weather_data.to_context_string() if weather_data else "Weather data unavailable."

        user_constraints = await self._constraints.get_constraints(session, user_id)
        constraints_text = "\n".join(
            f"- {c.label} ({c.start_time}-{c.end_time})" for c in user_constraints
        ) if user_constraints else "No constraints in the schedule."

        system = SYSTEM_PROMPT.format(
            current_datetime=now.strftime("%Y-%m-%d %H:%M:%S"),
            timezone=self._tz_name,
            weather_data=weather_text,
            existing_tasks=context.active_tasks_text,
            existing_constraints=constraints_text,
            conversation_context=context.to_context_string(),
        )
        return system, weather_data

    async def _call_llm(self, system_prompt: str, user_message: str) -> PlannerResponseSchema:
        try:
            return await self._llm.generate_parsed(system_prompt=system_prompt, user_message=user_message)
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            return PlannerResponseSchema(
                summary="A technical error occurred while communicating with the AI. Please try again.",
                warnings=["AI service is temporarily unavailable or returned an empty response."],
            )

    async def _execute_actions(self, session: AsyncSession, user_id: int, response: PlannerResponseSchema) -> None:
        # Process deleted constraints
        for label in response.deleted_constraints:
            try:
                removed = await self._constraints.remove_constraint_by_label(session, user_id, label)
                if not removed:
                    response.warnings.append(f"Failed to find a constraint in the schedule to delete: '{label}'")
            except Exception as exc:
                logger.error("Failed to remove constraint '%s': %s", label, exc)
                await session.rollback()

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
                response.warnings.append(f"Failed to add constraint '{c.label}'")
                await session.rollback()

        # Process tasks
        for task in response.tasks:
            try:
                await self._save_task(session, user_id, task, self._tz_name)
            except Exception as exc:
                logger.error("Failed to save task '%s': %s", task.title, exc)
                response.warnings.append(f"Failed to save: '{task.title}'")
                await session.rollback()

    @staticmethod
    def _to_fixed_offset_time(t: time_type, tz, ref_date: date_type | None = None) -> time_type:
        """Convert a time with a named timezone (e.g. Europe/Kyiv) to a fixed UTC offset.
        
        PostgreSQL TIME WITH TIME ZONE only accepts fixed offsets, not named
        timezones like zoneinfo.ZoneInfo.
        """
        if ref_date is None:
            ref_date = date_type.today()
        # Build a full datetime to resolve the correct UTC offset for this date
        dt = datetime.combine(ref_date, t, tzinfo=tz)
        utc_offset = dt.utcoffset()
        if utc_offset is None:
            return t
        fixed_tz = timezone(utc_offset)
        return t.replace(tzinfo=fixed_tz)

    async def _save_task(self, session: AsyncSession, user_id: int, task, tz_name: str) -> None:
        tz = get_local_timezone(tz_name)

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
            dl_date = date_type.fromisoformat(dl) if isinstance(dl, str) else dl
            kwargs["deadline_date"] = dl_date
            if task.deadline.time:
                parsed_time = parse_time_safe(task.deadline.time)
                if parsed_time:
                    kwargs["deadline_time"] = self._to_fixed_offset_time(parsed_time, tz, dl_date)
            if task.deadline.kind:
                kwargs["deadline_kind"] = DeadlineKind(task.deadline.kind.value)
                
        if task.fixed_time and task.fixed_time.date:
            ft = task.fixed_time.date
            ft_date = date_type.fromisoformat(ft) if isinstance(ft, str) else ft
            kwargs["fixed_time_date"] = ft_date
            if task.fixed_time.time:
                parsed_time = parse_time_safe(task.fixed_time.time)
                if parsed_time:
                    kwargs["fixed_time_time"] = self._to_fixed_offset_time(parsed_time, tz, ft_date)
                    
        task_orm = await repo.create_task(session, user_id, **kwargs)
        await self._reminder_service.schedule_for_task(session, user_id, task_orm)
