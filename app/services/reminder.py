"""Service to handle reminder creation logic."""

import logging
from datetime import datetime, timedelta
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from app.db import repository as repo

logger = logging.getLogger(__name__)

class ReminderService:
    """Service to schedule reminders for tasks."""
    
    def __init__(self, default_offset_hours: int = 2):
        self.default_offset = timedelta(hours=default_offset_hours)
        
    async def schedule_for_task(self, session: AsyncSession, user_id: int, task_orm) -> None:
        """Schedule a reminder for a given task if it has a deadline or fixed time."""
        remind_time = None
        
        # Calculate remind time based on fixed time or deadline
        if task_orm.fixed_time_date and task_orm.fixed_time_time:
            dt = datetime.combine(task_orm.fixed_time_date, task_orm.fixed_time_time)
            if hasattr(task_orm.fixed_time_time, 'tzinfo') and task_orm.fixed_time_time.tzinfo:
                dt = dt.replace(tzinfo=task_orm.fixed_time_time.tzinfo)
            remind_time = dt - self.default_offset
        elif task_orm.deadline_date and task_orm.deadline_time:
            dt = datetime.combine(task_orm.deadline_date, task_orm.deadline_time)
            if hasattr(task_orm.deadline_time, 'tzinfo') and task_orm.deadline_time.tzinfo:
                dt = dt.replace(tzinfo=task_orm.deadline_time.tzinfo)
            remind_time = dt - self.default_offset
            
        if remind_time:
            # Only create reminder if it's in the future
            now = datetime.now(remind_time.tzinfo) if remind_time.tzinfo else datetime.now()
            if remind_time > now:
                await repo.create_reminder(
                    session,
                    task_id=task_orm.id,
                    user_id=user_id,
                    remind_at=remind_time,
                    task_title=task_orm.title,
                )
                logger.info("Scheduled reminder for task %s at %s", task_orm.id, remind_time)
