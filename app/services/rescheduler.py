"""Smart Rescheduler Service.

Finds overdue tasks and suggests new time slots based on the user's constraints
and existing schedule.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository as repo
from app.models.task import TaskORM, TaskStatus
from app.schemas.rescheduler import RescheduleSuggestion
from app.services.timeline import TimelineEngine

logger = logging.getLogger(__name__)


class ReschedulerService:
    def __init__(
        self, timeline_engine: TimelineEngine, timezone_name: str = "Europe/Kyiv"
    ) -> None:
        self._timeline = timeline_engine
        try:
            from zoneinfo import ZoneInfo

            self._tz = ZoneInfo(timezone_name)
        except ImportError:
            from datetime import timezone

            self._tz = timezone(timedelta(hours=2))

    async def check_and_suggest(
        self, session: AsyncSession, user_id: int
    ) -> list[RescheduleSuggestion]:
        """Find overdue tasks and suggest rescheduling them."""
        now = datetime.now(self._tz)
        today = now.date()

        tasks = await repo.get_active_tasks(session, user_id)
        overdue_tasks = []

        for t in tasks:
            if t.deadline_date and t.deadline_date < today:
                overdue_tasks.append(t)
            elif (
                t.deadline_date == today
                and t.deadline_time
            ):
                dt = datetime.combine(today, t.deadline_time, tzinfo=self._tz)
                if dt < now:
                    overdue_tasks.append(t)
            elif (
                t.fixed_time_date == today
                and t.fixed_time_time
            ):
                dt = datetime.combine(today, t.fixed_time_time, tzinfo=self._tz)
                if dt < now:
                    overdue_tasks.append(t)
            elif t.fixed_time_date and t.fixed_time_date < today:
                overdue_tasks.append(t)

        if not overdue_tasks:
            return []

        # Get today's and tomorrow's timeline to find free windows
        timeline_today = await self._timeline.build_day(session, user_id, today)
        tomorrow = today + timedelta(days=1)
        timeline_tomorrow = await self._timeline.build_day(session, user_id, tomorrow)

        suggestions = []

        # For simplicity, we just look for free windows starting from 'now'
        # in today's timeline, or tomorrow's timeline
        free_windows = []
        for w in timeline_today.free_windows:
            start_dt = datetime.combine(
                today, datetime.strptime(w.start, "%H:%M").time(), tzinfo=self._tz
            )
            if start_dt >= now:
                free_windows.append({"date": today, "window": w})
                
        for w in timeline_tomorrow.free_windows:
            free_windows.append({"date": tomorrow, "window": w})

        # We map overdue tasks to free windows greedily
        window_idx = 0
        for task in overdue_tasks:
            if window_idx >= len(free_windows):
                break
                
            fw = free_windows[window_idx]
            est = task.estimated_minutes or 30
            
            # Simple check if window is large enough
            if fw["window"].duration_minutes >= est:
                suggested_time = datetime.combine(
                    fw["date"], 
                    datetime.strptime(fw["window"].start, "%H:%M").time(), 
                    tzinfo=self._tz
                )
                
                orig_dt = None
                if task.deadline_date and task.deadline_time:
                    orig_dt = datetime.combine(task.deadline_date, task.deadline_time, tzinfo=self._tz)
                
                suggestions.append(
                    RescheduleSuggestion(
                        task_id=task.id,
                        task_title=task.title,
                        original_deadline=orig_dt,
                        suggested_time=suggested_time,
                        reason=f"Free window {fw['window'].start}-{fw['window'].end}",
                    )
                )
                window_idx += 1

        return suggestions

    async def apply_suggestion(
        self, session: AsyncSession, task_id: str, new_time: datetime
    ) -> bool:
        """Apply a rescheduled time to a task."""
        import uuid
        try:
            tid = uuid.UUID(task_id)
        except ValueError:
            return False
            
        task = await session.get(TaskORM, tid)
        if not task or task.is_deleted or task.status != TaskStatus.CREATED:
            return False

        # Determine whether it was a fixed time or deadline
        # If both, update both. If none, set deadline.
        if new_time.tzinfo is None:
            new_time = new_time.replace(tzinfo=self._tz)
            
        time_with_tz = self._to_fixed_offset_time(new_time)

        updated = False
        if task.fixed_time_date:
            task.fixed_time_date = new_time.date()
            task.fixed_time_time = time_with_tz
            updated = True
        
        if task.deadline_date or not updated:
            task.deadline_date = new_time.date()
            task.deadline_time = time_with_tz
            
        await session.commit()
        return True

    @staticmethod
    def _to_fixed_offset_time(dt: datetime):
        """Extract time with a fixed UTC offset from an aware datetime.

        PostgreSQL TIME WITH TIME ZONE only accepts fixed offsets,
        not named timezones like zoneinfo.ZoneInfo.
        """
        utc_offset = dt.utcoffset()
        if utc_offset is None:
            return dt.time()
        fixed_tz = timezone(utc_offset)
        return dt.timetz().replace(tzinfo=fixed_tz)
