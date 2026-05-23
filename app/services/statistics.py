"""Statistics Service.

Calculates user task completion stats and metrics.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import TaskORM, TaskStatus
from app.models.routine import TaskCompletionLogORM
from app.schemas.statistics import StatsSchema

logger = logging.getLogger(__name__)


class StatisticsService:
    """Calculates statistics for a user's task history."""

    def __init__(self, tz_name: str = "Europe/Kyiv") -> None:
        try:
            from zoneinfo import ZoneInfo
            self._tz = ZoneInfo(tz_name)
        except ImportError:
            self._tz = timezone(timedelta(hours=2))

    async def get_stats(
        self, session: AsyncSession, user_id: int, period: str = "all_time"
    ) -> StatsSchema:
        """Calculate statistics for a given period (today, week, month, all_time)."""
        now = datetime.now(self._tz)
        today = now.date()

        start_date = None
        if period == "today":
            start_date = today
        elif period == "week":
            start_date = today - timedelta(days=7)
        elif period == "month":
            start_date = today - timedelta(days=30)

        # Base query for tasks
        stmt = select(TaskORM).where(TaskORM.user_id == user_id)
        
        # NOTE: For deleted tasks, we might still want to count them as cancelled or completed?
        # Let's include soft-deleted if we want total history, but typically we just look at statuses.
        
        result = await session.execute(stmt)
        tasks = result.scalars().all()

        stats = StatsSchema(period=period)

        # Let's filter by updated_at or created_at for the period
        filtered_tasks = []
        for t in tasks:
            # Approximate: if start_date is set, we only count tasks created or updated after start_date
            # Realistically, we should use task completion logs for more accurate time-bounded stats.
            if start_date:
                # If we have updated_at, use it, else created_at
                dt = t.updated_at or t.created_at
                # Convert to local date
                if dt:
                    if dt.tzinfo:
                        dt = dt.astimezone(self._tz)
                    if dt.date() < start_date:
                        continue
            filtered_tasks.append(t)

        for t in filtered_tasks:
            if t.status == TaskStatus.COMPLETED:
                stats.total_completed += 1
                cat = t.type.value if t.type else "other"
                stats.by_category[cat] = stats.by_category.get(cat, 0) + 1
                if t.estimated_minutes:
                    # Rolling sum, we'll average later
                    stats.avg_duration_minutes += t.estimated_minutes
                    
            elif t.status == TaskStatus.CANCELLED:
                stats.total_cancelled += 1
            elif t.status == TaskStatus.CREATED:
                # Check if overdue
                if t.deadline_date and t.deadline_date < today:
                    stats.total_overdue += 1
                elif t.deadline_date == today and t.deadline_time:
                    dt_deadline = datetime.combine(today, t.deadline_time, tzinfo=self._tz)
                    if dt_deadline < now:
                        stats.total_overdue += 1

        if stats.total_completed > 0:
            stats.avg_duration_minutes = round(stats.avg_duration_minutes / stats.total_completed, 1)

        # Calculate streak (consecutive days with at least 1 completed task)
        stats.current_streak_days = await self._calculate_streak(session, user_id, today)

        return stats

    async def _calculate_streak(self, session: AsyncSession, user_id: int, today) -> int:
        """Calculate current streak of days with completed tasks."""
        # Query distinct days from TaskCompletionLogORM
        stmt = (
            select(func.date(TaskCompletionLogORM.completed_at).label("day"))
            .where(TaskCompletionLogORM.user_id == user_id)
            .group_by(func.date(TaskCompletionLogORM.completed_at))
            .order_by(func.date(TaskCompletionLogORM.completed_at).desc())
        )
        result = await session.execute(stmt)
        days = [row.day for row in result.all()]
        
        streak = 0
        current = today
        for d in days:
            if d == current:
                streak += 1
                current -= timedelta(days=1)
            elif d == current - timedelta(days=1):
                # Maybe they didn't complete anything today yet, but did yesterday
                if streak == 0:
                    streak += 1
                    current = d - timedelta(days=1)
                else:
                    break
            else:
                break
                
        return streak
