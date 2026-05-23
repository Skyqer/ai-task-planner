"""Pydantic schemas for reminders."""

from __future__ import annotations

import enum
from typing import Optional

from pydantic import BaseModel


class ReminderStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    EXPIRED = "expired"


class ReminderSchema(BaseModel):
    """Schema for a reminder."""

    task_id: str
    user_id: int
    remind_at: str  # ISO datetime
    status: ReminderStatus = ReminderStatus.PENDING
    sent_count: int = 0
    task_title: str = ""
