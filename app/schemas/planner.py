"""Pydantic schema for the full planner response."""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field

from app.schemas.task import TaskSchema


class PlannerMode(str, enum.Enum):
    TASK_INPUT = "task_input"
    MORNING_BRIEF = "morning_brief"


class PlannerStatus(str, enum.Enum):
    OK = "ok"
    NEEDS_CLARIFICATION = "needs_clarification"


class ScheduleSuggestionSchema(BaseModel):
    """Suggested time slot for a task."""

    start: str | None = None
    end: str | None = None
    task_title: str = ""
    reason: str = ""


class PlannerResponseSchema(BaseModel):
    """Top-level response from the core planner.

    This schema is used both as the API response format
    and as the LLM response_format for structured output.
    """

    mode: PlannerMode = PlannerMode.TASK_INPUT
    status: PlannerStatus = PlannerStatus.OK
    timezone: str = "Europe/Kyiv"
    tasks: list[TaskSchema] = Field(default_factory=list)
    schedule_suggestions: list[ScheduleSuggestionSchema] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    summary: str = ""
