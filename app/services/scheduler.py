"""Scheduler subsystem — reminders, morning briefs, recurring tasks."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Protocol

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import Settings
from app.db.engine import async_session_factory
from app.db import repository as repo

logger = logging.getLogger(__name__)


class NotificationCallback(Protocol):
    """Interface for sending notifications to users."""

    async def send(self, user_id: int, message: str) -> None: ...

    async def send_with_keyboard(
        self, user_id: int, message: str, keyboard: Any
    ) -> None: ...


class SchedulerService:
    """APScheduler-based scheduler for periodic tasks."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._scheduler = AsyncIOScheduler()
        self._notifier: NotificationCallback | None = None
        self._rescheduler = None
        
    def set_rescheduler(self, rescheduler) -> None:
        """Set the rescheduler service."""
        self._rescheduler = rescheduler

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
            self._check_pending_reminders,
            "interval",
            minutes=1,
            id="check_reminders",
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
        self._scheduler.add_job(
            self._check_rescheduling,
            "interval",
            hours=2,
            id="check_rescheduling",
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

    async def _check_pending_reminders(self) -> None:
        """Find pending/sent reminders that need to be delivered."""
        if not self._notifier:
            return

        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(self._settings.timezone)
        except ImportError:
            from datetime import timezone
            tz = timezone(timedelta(hours=2))

        now = datetime.now(tz)

        async with async_session_factory() as session:
            # We fetch reminders due up to 'now'
            reminders = await repo.get_pending_reminders(session, now)
            
            for reminder in reminders:
                # Calculate if we should send it (initial send or retry every 30 mins)
                if reminder.last_sent_at:
                    if (now - reminder.last_sent_at) < timedelta(minutes=30):
                        continue

                msg = f"🔔 Напоминание:\n<b>{reminder.task_title}</b>"
                
                try:
                    from app.transport.telegram.formatter import get_reminder_keyboard
                    
                    # Hack: directly access bot in notifier if possible, or send without keyboard
                    # But since notifier signature is just string, we might need a richer interface.
                    # Let's adjust Notifier Protocol dynamically if supported.
                    
                    if hasattr(self._notifier, "send_with_keyboard"):
                        await self._notifier.send_with_keyboard(
                            reminder.user_id, 
                            msg, 
                            get_reminder_keyboard(str(reminder.id))
                        )
                    else:
                        await self._notifier.send(reminder.user_id, msg)
                    
                    await repo.update_reminder_sent(session, reminder.id)
                except Exception as exc:
                    logger.error("Failed to send reminder %s: %s", reminder.id, exc)

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
        
        # Helper to get the next specific weekday
        def next_weekday(d: datetime, weekday: int) -> datetime:
            days_ahead = weekday - d.weekday()
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7
            return d + timedelta(days=days_ahead)

        if pattern == "daily":
            return from_dt + timedelta(days=1)
            
        if pattern == "workdays":
            next_d = from_dt + timedelta(days=1)
            while next_d.weekday() >= 5:  # 5=Sat, 6=Sun
                next_d += timedelta(days=1)
            return next_d
            
        if pattern.startswith("weekly:"):
            # e.g., weekly:mon,wed,fri
            parts = pattern.split(":")
            if len(parts) > 1:
                days_str = parts[1].split(",")
                day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
                target_days = [day_map[d.strip()] for d in days_str if d.strip() in day_map]
                if target_days:
                    target_days.sort()
                    current_weekday = from_dt.weekday()
                    
                    # Find the next day in the list that is > current_weekday
                    for td in target_days:
                        if td > current_weekday:
                            return next_weekday(from_dt, td)
                            
                    # If none found in current week, pick the first day of next week
                    return next_weekday(from_dt, target_days[0])

        if pattern.startswith("weekly"):
            return from_dt + timedelta(weeks=1)
            
        if pattern.startswith("monthly"):
            try:
                if ":" in pattern:
                    day_part = int(pattern.split(":")[1])
                    # Create the date for the current month
                    try:
                        target_d = from_dt.replace(day=day_part)
                        if target_d <= from_dt:
                            # Move to next month
                            # A simple way to add a month is to add 32 days to the 1st of the current month
                            next_month_d = (from_dt.replace(day=1) + timedelta(days=32)).replace(day=day_part)
                            return next_month_d
                        return target_d
                    except ValueError:
                        # Day is out of range for the month, simple fallback
                        pass
            except ValueError:
                pass
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

    async def _check_rescheduling(self) -> None:
        """Find overdue tasks and send reschedule suggestions."""
        if not self._notifier or not self._rescheduler:
            return
            
        async with async_session_factory() as session:
            users = await repo.get_all_users(session)
            for user in users:
                suggestions = await self._rescheduler.check_and_suggest(session, user.id)
                for sugg in suggestions:
                    msg = (
                        f"⏳ <b>Просрочено:</b> {sugg.task_title}\n"
                        f"💡 Рекомендую перенести на <b>{sugg.suggested_time.strftime('%H:%M')} "
                        f"({sugg.suggested_time.date()})</b>\n"
                        f"<i>Причина: {sugg.reason}</i>"
                    )
                    
                    try:
                        from app.transport.telegram.formatter import get_reschedule_keyboard
                        if hasattr(self._notifier, "send_with_keyboard"):
                            await self._notifier.send_with_keyboard(
                                user.id, 
                                msg, 
                                get_reschedule_keyboard(str(sugg.task_id), sugg.suggested_time.isoformat())
                            )
                        else:
                            await self._notifier.send(user.id, msg)
                    except Exception as exc:
                        logger.error("Failed to send reschedule suggestion for task %s: %s", sugg.task_id, exc)
