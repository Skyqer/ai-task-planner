"""Tests for Statistics Service."""

import pytest
from datetime import date, datetime, timedelta

from app.models.task import TaskORM, TaskStatus, TaskType
from app.schemas.statistics import StatsSchema
from app.services.statistics import StatisticsService


class DummyTask:
    def __init__(self, **kwargs):
        self.type = None
        self.status = TaskStatus.CREATED
        self.estimated_minutes = None
        self.deadline_date = None
        self.deadline_time = None
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        
        for k, v in kwargs.items():
            setattr(self, k, v)


class DummyType:
    def __init__(self, value):
        self.value = value


@pytest.mark.asyncio
async def test_get_stats(monkeypatch):
    svc = StatisticsService()
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    
    tasks = [
        DummyTask(
            status=TaskStatus.COMPLETED,
            type=DummyType("study"),
            estimated_minutes=30,
            updated_at=datetime.now()
        ),
        DummyTask(
            status=TaskStatus.COMPLETED,
            type=DummyType("work"),
            estimated_minutes=60,
            updated_at=datetime.now()
        ),
        DummyTask(
            status=TaskStatus.CANCELLED,
            updated_at=datetime.now()
        ),
        DummyTask(
            status=TaskStatus.CREATED,
            deadline_date=yesterday,  # Overdue
            updated_at=datetime.now()
        ),
    ]
    
    class MockResult:
        def scalars(self):
            class MockScalars:
                def all(self):
                    return tasks
            return MockScalars()
            
    class MockSession:
        async def execute(self, stmt):
            return MockResult()
            
    async def mock_calc_streak(*args, **kwargs):
        return 3
        
    monkeypatch.setattr(svc, "_calculate_streak", mock_calc_streak)
    
    session = MockSession()
    stats = await svc.get_stats(session, 123, "all_time")
    
    assert stats.total_completed == 2
    assert stats.total_cancelled == 1
    assert stats.total_overdue == 1
    assert stats.current_streak_days == 3
    assert stats.by_category["study"] == 1
    assert stats.by_category["work"] == 1
    assert stats.avg_duration_minutes == 45.0  # (30 + 60) / 2
