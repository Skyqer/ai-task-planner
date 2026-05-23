"""Schemas for the smart rescheduler."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class RescheduleSuggestion(BaseModel):
    """A suggestion to reschedule an overdue or blocked task."""
    
    task_id: uuid.UUID
    task_title: str
    original_deadline: datetime | None = None
    suggested_time: datetime
    reason: str = Field(description="Why this time is suggested (e.g., found free window)")
