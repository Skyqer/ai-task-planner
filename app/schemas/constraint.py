"""Pydantic schemas for user constraints."""

from __future__ import annotations

import enum
from typing import Optional

from pydantic import BaseModel, Field


class ConstraintType(str, enum.Enum):
    SLEEP = "sleep"
    SCHOOL = "school"
    UNAVAILABLE = "unavailable"
    FOCUS = "focus"


class UserConstraintSchema(BaseModel):
    """Schema for a single user constraint."""

    constraint_type: ConstraintType
    start_time: str = Field(description="HH:MM format")
    end_time: str = Field(description="HH:MM format")
    days_of_week: Optional[list[int]] = None  # 0=Mon..6=Sun; None=every day
    label: str = ""
    is_active: bool = True


class TimeBlock(BaseModel):
    """A time range within a single day."""

    start: str  # "HH:MM"
    end: str    # "HH:MM"
    label: str = ""
    block_type: str = ""  # "sleep", "school", "task", "free", etc.
    task_id: Optional[str] = None

    @property
    def start_minutes(self) -> int:
        h, m = self.start.split(":")
        return int(h) * 60 + int(m)

    @property
    def end_minutes(self) -> int:
        h, m = self.end.split(":")
        return int(h) * 60 + int(m)

    @property
    def duration_minutes(self) -> int:
        diff = self.end_minutes - self.start_minutes
        return diff if diff > 0 else diff + 24 * 60
