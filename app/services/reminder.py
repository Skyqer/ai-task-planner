"""Service to handle reminder creation logic."""

import logging
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from app.db import repository as repo

logger = logging.getLogger(__name__)

class ReminderService:
    """Service to schedule reminders for tasks."""
    
    def __init__(self, default_offset_hours: int = 2):
        self.default_offset = timedelta(hours=default_offset_hours)
        
    async def schedule_for_task(self, session: AsyncSession, user_id: int, task_orm) -> None:
        """Schedule a reminder for a given task based on its deadline or fixed time."""
        event_time = None
        
        # Determine the actual event time
        if task_orm.fixed_time_date and task_orm.fixed_time_time:
            dt = datetime.combine(task_orm.fixed_time_date, task_orm.fixed_time_time)
            if hasattr(task_orm.fixed_time_time, 'tzinfo') and task_orm.fixed_time_time.tzinfo:
                dt = dt.replace(tzinfo=task_orm.fixed_time_time.tzinfo)
            event_time = dt
        elif task_orm.deadline_date and task_orm.deadline_time:
            dt = datetime.combine(task_orm.deadline_date, task_orm.deadline_time)
            if hasattr(task_orm.deadline_time, 'tzinfo') and task_orm.deadline_time.tzinfo:
                dt = dt.replace(tzinfo=task_orm.deadline_time.tzinfo)
            event_time = dt
            
        if event_time:
            now = datetime.now(event_time.tzinfo) if event_time.tzinfo else datetime.now()
            time_until_event = event_time - now

            remind_time = None
            if time_until_event > timedelta(hours=2):
                remind_time = event_time - timedelta(hours=2)
            elif time_until_event > timedelta(minutes=15):
                remind_time = event_time - timedelta(minutes=15)
            elif time_until_event > timedelta(minutes=0):
                remind_time = now + timedelta(minutes=1)  # Almost immediate reminder
                
            if remind_time:
                await repo.create_reminder(
                    session,
                    task_id=task_orm.id,
                    user_id=user_id,
                    remind_at=remind_time,
                    task_title=task_orm.title,
                )
                logger.info("Scheduled reminder for task %s at %s", task_orm.id, remind_time)
