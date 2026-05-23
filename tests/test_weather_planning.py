"""Tests for Weather-aware Planning."""

import pytest
import uuid
from datetime import date, time

from app.schemas.timeline import DayTimelineSchema
from app.schemas.weather import WeatherData
from app.services.timeline import TimelineEngine
from app.models.task import TaskORM


class MockWeatherService:
    def __init__(self, is_rainy=True):
        self.is_rainy = is_rainy
        
    async def get_current_weather(self, city=None):
        return WeatherData(
            temperature=15.0,
            feels_like=14.0,
            description="дождь" if self.is_rainy else "ясно",
            rain_probability=0.8 if self.is_rainy else 0.0,
            wind_speed=5.0,
            humidity=80,
            is_rainy=self.is_rainy
        )


class MockConstraintService:
    async def get_blocked_windows(self, session, user_id, target_date):
        return []


class MockEnergyService:
    async def get_energy_profile(self, session, user_id):
        return {}
    def suggest_task_placement(self, priority, profile):
        return []


class MockSession:
    pass


@pytest.mark.asyncio
async def test_weather_aware_timeline(monkeypatch):
    weather = MockWeatherService(is_rainy=True)
    constraints = MockConstraintService()
    timeline = TimelineEngine(constraints, "Europe/Kyiv", weather)
    timeline._energy_service = MockEnergyService()
    
    t1 = TaskORM(
        id=uuid.uuid4(),
        title="Walk the dog",
        weather_sensitive=True,
        estimated_minutes=30,
        priority=3
    )
    t2 = TaskORM(
        id=uuid.uuid4(),
        title="Read a book",
        weather_sensitive=False,
        estimated_minutes=60,
        priority=3
    )
    
    async def mock_get_active_tasks(*args, **kwargs):
        return [t1, t2]
        
    monkeypatch.setattr("app.services.timeline.repo.get_active_tasks", mock_get_active_tasks)
    
    # Needs a mock for routine learner as well
    class MockRoutineLearner:
        async def get_preferred_slot(self, session, user_id, task_type):
            return None
            
    timeline._routine_learner = MockRoutineLearner()
    
    day = await timeline.build_day(MockSession(), 123, target_date=date(2026, 5, 22))
    
    # We should have a warning about rain for t1
    assert any("дождь" in w for w in day.warnings)
    assert any("Walk the dog" in w for w in day.warnings)
    
    # Suggestion
    assert any("из-за дождя" in s for s in day.suggestions)
