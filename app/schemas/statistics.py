"""Schemas for statistics service."""

from pydantic import BaseModel, Field


class StatsSchema(BaseModel):
    """Aggregated statistics for a user."""
    
    total_completed: int = 0
    total_overdue: int = 0
    total_cancelled: int = 0
    
    # Breakdowns
    by_category: dict[str, int] = Field(default_factory=dict)
    
    # Metrics
    avg_duration_minutes: float = 0.0
    
    # Streaks (completed tasks per day for last N days)
    # Just a simple score for now
    current_streak_days: int = 0
    
    # Time period
    period: str = "all_time"  # e.g., "today", "week", "month", "all_time"
