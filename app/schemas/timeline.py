"""Pydantic schemas for the timeline (day schedule)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.constraint import TimeBlock


class DayTimelineSchema(BaseModel):
    """Full day schedule for a user."""

    date: str  # "YYYY-MM-DD"
    blocks: list[TimeBlock] = Field(default_factory=list)
    free_windows: list[TimeBlock] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
