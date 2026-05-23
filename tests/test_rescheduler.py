"""Tests for Smart Rescheduler Service."""

import pytest
import uuid
from datetime import date, datetime, time

from app.models.task import DeadlineKind, TaskORM, TaskStatus
from app.schemas.timeline import DayTimelineSchema
from app.schemas.constraint import TimeBlock
from app.services.rescheduler import RescheduleSuggestion, ReschedulerService


class DummyTimelineEngine:
    async def build_day(self, session, user_id: int, target_date: date) -> DayTimelineSchema:
        # Return a timeline with a free window from 14:00 to 16:00
        return DayTimelineSchema(
            date=target_date.isoformat(),
            blocks=[],
            free_windows=[
                TimeBlock(start="14:00", end="16:00", block_type="free")
            ],
            warnings=[],
            suggestions=[]
        )


class DummyTask:
    def __init__(self, **kwargs):
        self.id = uuid.uuid4()
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.mark.asyncio
async def test_rescheduler_check_and_suggest(monkeypatch):
    timeline = DummyTimelineEngine()
    svc = ReschedulerService(timeline)
    
    # Mock datetime.now() inside the module
    class MockDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 5, 22, 12, 0, tzinfo=tz)
            
    monkeypatch.setattr("app.services.rescheduler.datetime", MockDatetime)
    
    tasks = [
        # Overdue task from yesterday
        DummyTask(
            title="Old task",
            deadline_date=date(2026, 5, 20),
            deadline_time=None,
            fixed_time_date=None,
            fixed_time_time=None,
            estimated_minutes=30
        ),
        # Task for today but time passed (11:00)
        DummyTask(
            title="Missed today",
            deadline_date=date(2026, 5, 22),
            deadline_time=time(11, 0),
            fixed_time_date=None,
            fixed_time_time=None,
            estimated_minutes=45
        ),
        # Future task (15:00 today) -> Not overdue
        DummyTask(
            title="Future task",
            deadline_date=date(2026, 5, 22),
            deadline_time=time(15, 0),
            fixed_time_date=None,
            fixed_time_time=None,
            estimated_minutes=30
        )
    ]
    
    async def mock_get_active(*args, **kwargs):
        return tasks
        
    monkeypatch.setattr("app.services.rescheduler.repo.get_active_tasks", mock_get_active)
    
    # We pass None for session as we mocked the repo call
    suggestions = await svc.check_and_suggest(None, 123)
    
    assert len(suggestions) == 2
    assert suggestions[0].task_title == "Old task"
    assert suggestions[0].suggested_time.date() == date(2026, 5, 22)
    assert suggestions[0].suggested_time.time() == time(14, 0)
    
    # Second task might not get a suggestion if the window was consumed,
    # wait, our greedy loop in rescheduler currently does not 'consume' the window!
    # Ah, it just moves window_idx += 1. So it takes the next window.
    # Since DummyTimelineEngine returns 1 window per day, the second task will get tomorrow's window.
    assert suggestions[1].task_title == "Missed today"
    assert suggestions[1].suggested_time.date() == date(2026, 5, 23)
    assert suggestions[1].suggested_time.time() == time(14, 0)
