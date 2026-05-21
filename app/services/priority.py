"""Priority engine — post-processes LLM output to enforce hard priority rules."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

from app.schemas.planner import PlannerResponseSchema
from app.schemas.task import TaskSchema
from app.schemas.weather import WeatherData

logger = logging.getLogger(__name__)

# Keywords that boost priority
_URGENCY_KEYWORDS = {"надо", "обязательно", "срочно", "важно", "критично", "asap"}


class PriorityEngine:
    """Validates and adjusts task priorities based on hard rules.

    Runs AFTER the LLM generates its response, enforcing business
    rules that the LLM might miss or underweight.
    """

    def __init__(self, tz_name: str = "Europe/Kyiv") -> None:
        try:
            from zoneinfo import ZoneInfo
            self._tz = ZoneInfo(tz_name)
        except ImportError:
            self._tz = timezone(timedelta(hours=2))  # fallback EET

    def process(
        self,
        response: PlannerResponseSchema,
        weather: WeatherData | None = None,
        original_text: str = "",
    ) -> PlannerResponseSchema:
        """Apply all priority rules and return modified response."""
        now = datetime.now(self._tz)
        today = now.date()

        for task in response.tasks:
            self._apply_fixed_time_rule(task, today)
            self._apply_deadline_rules(task, now, today)
            self._apply_urgency_keywords(task, original_text)
            self._apply_weather_impact(task, weather, response)

        # Detect time conflicts
        conflicts = self._detect_conflicts(response.tasks, today)
        response.warnings.extend(conflicts)

        return response

    def _apply_fixed_time_rule(self, task: TaskSchema, today: date) -> None:
        """Fixed time today → minimum priority 4."""
        if task.fixed_time.date and task.fixed_time.time:
            if task.fixed_time.date == today.isoformat() or task.fixed_time.date == today:
                task.priority = max(task.priority, 4)

    def _apply_deadline_rules(
        self, task: TaskSchema, now: datetime, today: date
    ) -> None:
        """Apply deadline-based priority adjustments and warnings."""
        if not task.deadline.date:
            return

        deadline_date = task.deadline.date
        if isinstance(deadline_date, str):
            try:
                deadline_date = date.fromisoformat(deadline_date)
            except ValueError:
                return

        if deadline_date < today:
            # Overdue
            task.priority = 5
            return

        if deadline_date == today:
            task.priority = max(task.priority, 4)

            # Check time proximity
            if task.deadline.time:
                try:
                    parts = task.deadline.time.split(":")
                    dl_time = time(int(parts[0]), int(parts[1]))
                    deadline_dt = datetime.combine(
                        today, dl_time, tzinfo=self._tz
                    )
                    remaining = deadline_dt - now

                    if remaining <= timedelta(hours=0):
                        task.priority = 5
                    elif remaining <= timedelta(hours=1):
                        task.priority = 5
                    elif remaining <= timedelta(hours=2):
                        task.priority = 5

                    # Check if there's enough time
                    if (
                        remaining.total_seconds() > 0
                        and task.estimated_minutes
                        and remaining.total_seconds() / 60 < task.estimated_minutes
                    ):
                        task.priority = 5
                except (ValueError, IndexError):
                    pass

    def _apply_urgency_keywords(
        self, task: TaskSchema, original_text: str
    ) -> None:
        """Boost priority if the original text contains urgency keywords."""
        text_lower = original_text.lower()
        if any(kw in text_lower for kw in _URGENCY_KEYWORDS):
            task.priority = min(task.priority + 1, 5)

    def _apply_weather_impact(
        self,
        task: TaskSchema,
        weather: WeatherData | None,
        response: PlannerResponseSchema,
    ) -> None:
        """Add weather warnings for weather-sensitive outdoor tasks."""
        if not task.weather_sensitive or not weather:
            return

        if weather.is_rainy:
            warning = (
                f"⚠️ Задача '{task.title}' чувствительна к погоде. "
                f"Ожидается дождь ({weather.rain_probability * 100:.0f}%). "
                "Рекомендуется перенести или подготовиться."
            )
            if warning not in response.warnings:
                response.warnings.append(warning)

    def _detect_conflicts(
        self, tasks: list[TaskSchema], today: date
    ) -> list[str]:
        """Detect overlapping fixed-time tasks."""
        fixed_tasks = []
        for t in tasks:
            if t.fixed_time.time and t.fixed_time.date:
                ft_date = t.fixed_time.date
                if isinstance(ft_date, str):
                    try:
                        ft_date = date.fromisoformat(ft_date)
                    except ValueError:
                        continue
                if ft_date == today:
                    try:
                        parts = t.fixed_time.time.split(":")
                        start_minutes = int(parts[0]) * 60 + int(parts[1])
                        end_minutes = start_minutes + t.estimated_minutes
                        fixed_tasks.append((t.title, start_minutes, end_minutes))
                    except (ValueError, IndexError):
                        continue

        conflicts = []
        for i, (name_a, start_a, end_a) in enumerate(fixed_tasks):
            for name_b, start_b, end_b in fixed_tasks[i + 1:]:
                if start_a < end_b and start_b < end_a:
                    conflicts.append(
                        f"⚠️ Конфликт: '{name_a}' и '{name_b}' пересекаются по времени."
                    )
        return conflicts
