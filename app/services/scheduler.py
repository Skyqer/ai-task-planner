"""Scheduler subsystem — reminders, morning briefs, recurring tasks."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Protocol

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import Settings
from app.db.engine import async_session_factory
from app.db import repository as repo

logger = logging.getLogger(__name__)


class NotificationCallback(Protocol):
    """Interface for sending notifications to users."""

    async def send(self, user_id: int, message: str) -> None: ...


class SchedulerService:
    """APScheduler-based scheduler for periodic tasks."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._scheduler = AsyncIOScheduler()
        self._notifier: NotificationCallback | None = None

    def set_notifier(self, notifier: NotificationCallback) -> None:
        """Set the notification callback (e.g., Telegram sender)."""
        self._notifier = notifier

    def start(self) -> None:
        """Register all jobs and start the scheduler."""
        self._scheduler.add_job(
            self._check_upcoming_deadlines,
            "interval",
            minutes=15,
            id="check_deadlines",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._create_recurring_tasks,
            "interval",
            hours=1,
            id="recurring_tasks",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._cleanup_old_messages,
            "cron",
            hour=3,
            minute=0,
            id="cleanup_messages",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info("Scheduler started with %d jobs", len(self._scheduler.get_jobs()))

    def shutdown(self) -> None:
        """Gracefully shut down the scheduler."""
        self._scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    async def _check_upcoming_deadlines(self) -> None:
        """Find tasks with deadlines within 1 hour and send reminders."""
        if not self._notifier:
            return

        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(self._settings.timezone)
        except ImportError:
            from datetime import timezone
            tz = timezone(timedelta(hours=2))

        now = datetime.now(tz)
        threshold = now + timedelta(hours=1)

        async with async_session_factory() as session:
            tasks = await repo.get_tasks_with_upcoming_deadlines(session, threshold)
            for task in tasks:
                if not task.deadline_date or not task.deadline_time:
                    continue

                deadline_dt = datetime.combine(
                    task.deadline_date, task.deadline_time, tzinfo=tz
                )
                remaining = deadline_dt - now

                if timedelta(0) < remaining <= timedelta(hours=1):
                    mins = int(remaining.total_seconds() / 60)
                    msg = (
                        f"⏰ Напоминание: '{task.title}' — "
                        f"дедлайн через {mins} мин "
                        f"({task.deadline_time.strftime('%H:%M')})"
                    )
                    try:
                        await self._notifier.send(task.user_id, msg)
                    except Exception as exc:
                        logger.error("Failed to send reminder: %s", exc)

    async def _create_recurring_tasks(self) -> None:
        """Check RecurrenceORM and create new task instances."""
        from app.models.task import RecurrenceORM, TaskORM, TaskStatus

        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(self._settings.timezone)
        except ImportError:
            from datetime import timezone
            tz = timezone(timedelta(hours=2))

        now = datetime.now(tz)

        async with async_session_factory() as session:
            from sqlalchemy import select
            stmt = select(RecurrenceORM).where(
                RecurrenceORM.is_active.is_(True),
                RecurrenceORM.next_run <= now,
            )
            result = await session.execute(stmt)
            recurrences = result.scalars().all()

            for rec in recurrences:
                # Load the template task
                template = await session.get(TaskORM, rec.task_id)
                if not template:
                    rec.is_active = False
                    continue

                # Create a new task instance
                await repo.create_task(
                    session,
                    user_id=template.user_id,
                    title=template.title,
                    details=template.details,
                    type=template.type,
                    priority=template.priority,
                    estimated_minutes=template.estimated_minutes,
                    weather_sensitive=template.weather_sensitive,
                    tags=template.tags,
                    status=TaskStatus.CREATED,
                )

                # Advance next_run
                rec.next_run = self._calc_next_run(rec.pattern, now)
                await session.commit()

                logger.info("Created recurring task: %s", template.title)

    @staticmethod
    def _calc_next_run(pattern: str, from_dt: datetime) -> datetime:
        """Calculate next run from a pattern string."""
        pattern = pattern.lower().strip()
        if pattern == "daily":
            return from_dt + timedelta(days=1)
        if pattern.startswith("weekly"):
            return from_dt + timedelta(weeks=1)
        if pattern.startswith("monthly"):
            return from_dt + timedelta(days=30)
        # Default: daily
        return from_dt + timedelta(days=1)

    async def _cleanup_old_messages(self) -> None:
        """Prune message history beyond retention limit."""
        async with async_session_factory() as session:
            users = await repo.get_all_users(session)
            for user in users:
                deleted = await repo.delete_old_messages(
                    session,
                    user.id,
                    keep_last=self._settings.memory_max_messages,
                )
                if deleted:
                    logger.info("Cleaned %d old messages for user %d", deleted, user.id)
