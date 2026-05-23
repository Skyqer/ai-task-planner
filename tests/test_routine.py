"""Tests for Routine Learning Service."""

import pytest
import uuid
from datetime import datetime

from app.services.routine import RoutineLearner


@pytest.mark.asyncio
async def test_routine_learner_not_enough_data(monkeypatch):
    learner = RoutineLearner()
    
    async def mock_get_logs(*args, **kwargs):
        return [600, 610]  # Only 2 logs, MIN_SAMPLES is 3
        
    monkeypatch.setattr("app.services.routine.repo.get_task_completion_logs", mock_get_logs)
    
    # Needs at least 3
    pref = await learner.get_preferred_slot(None, 123, "study")
    assert pref is None


@pytest.mark.asyncio
async def test_routine_learner_with_data(monkeypatch):
    learner = RoutineLearner()
    
    async def mock_get_logs(*args, **kwargs):
        # 10:00 (600), 10:10 (610), 09:50 (590) -> avg 600
        return [600, 610, 590]
        
    monkeypatch.setattr("app.services.routine.repo.get_task_completion_logs", mock_get_logs)
    
    pref = await learner.get_preferred_slot(None, 123, "study")
    assert pref == 600
