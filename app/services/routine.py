"""Routine Learning Service.

Analyzes historical task completions to find preferred times of day for 
specific types of tasks (e.g. studying in the morning, workouts in the evening).
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository as repo

logger = logging.getLogger(__name__)


class RoutineLearner:
    """Analyzes task completion logs to suggest optimal times."""
    
    # Minimum number of samples to establish a pattern
    MIN_SAMPLES = 3

    async def get_preferred_slot(
        self, session: AsyncSession, user_id: int, task_type: str
    ) -> Optional[int]:
        """Get the preferred time (minutes since midnight) for a task type.
        
        Returns None if not enough data to establish a routine.
        """
        if not task_type or task_type == "other":
            return None
            
        logs = await repo.get_task_completion_logs(session, user_id, task_type)
        if len(logs) < self.MIN_SAMPLES:
            return None
            
        # Simple clustering/averaging
        # For a robust system we'd use circular statistics or KDE, 
        # but average is a good start for Phase 2.
        
        # Remove outliers? Let's just do a simple average for now
        avg_minutes = sum(logs) / len(logs)
        return int(avg_minutes)
