"""Pydantic schemas for tasks and related structures."""

from __future__ import annotations

import enum
import datetime
from datetime import time
from typing import Optional

from pydantic import BaseModel, Field


class TaskType(str, enum.Enum):
    STUDY = "study"
    HOME = "home"
    HEALTH = "health"
    ERRAND = "errand"
    SPORT = "sport"
    WORK = "work"
    OTHER = "other"


class DeadlineKind(str, enum.Enum):
    HARD = "hard"
    SOFT = "soft"


class DeadlineSchema(BaseModel):
    """Deadline sub-object."""

    date: Optional[datetime.date] = None
    time: Optional[str] = None
    kind: Optional[DeadlineKind] = None


class FixedTimeSchema(BaseModel):
    """Fixed time sub-object for hard-scheduled events."""

    date: Optional[datetime.date] = None
    time: Optional[str] = None


class TaskSchema(BaseModel):
    """Individual task as returned by the planner."""

    title: str
    details: str = ""
    type: TaskType = TaskType.OTHER
    priority: int = Field(ge=1, le=5, default=2)
    estimated_minutes: int = Field(ge=1, default=30)
    deadline: DeadlineSchema = Field(default_factory=DeadlineSchema)
    fixed_time: FixedTimeSchema = Field(default_factory=FixedTimeSchema)
    weather_sensitive: bool = False
    tags: list[str] = Field(default_factory=list)
