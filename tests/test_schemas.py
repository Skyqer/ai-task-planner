"""Tests for Pydantic schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.planner import PlannerResponseSchema
from app.schemas.task import DeadlineSchema, FixedTimeSchema, TaskSchema


def test_task_schema_defaults():
    """TaskSchema should have sensible defaults."""
    task = TaskSchema(title="Test")
    assert task.priority == 2
    assert task.estimated_minutes == 30
    assert task.weather_sensitive is False
    assert task.tags == []
    assert task.type.value == "other"


def test_task_schema_with_deadline():
    """TaskSchema should accept deadline fields."""
    task = TaskSchema(
        title="Math homework",
        type="study",
        priority=4,
        estimated_minutes=45,
        deadline=DeadlineSchema(
            date="2026-05-22",
            time="16:00",
            kind="hard",
        ),
    )
    assert task.deadline.kind.value == "hard"
    assert task.deadline.time == "16:00"


def test_task_schema_invalid_priority():
    """Priority outside 1-5 should fail validation."""
    with pytest.raises(ValidationError):
        TaskSchema(title="Test", priority=0)

    with pytest.raises(ValidationError):
        TaskSchema(title="Test", priority=6)


def test_task_schema_invalid_time_format():
    """Invalid time format should fail validation."""
    with pytest.raises(ValidationError):
        TaskSchema(
            title="Test",
            deadline=DeadlineSchema(time="25:99"),
        )


def test_planner_response_empty():
    """Empty PlannerResponse should be valid."""
    resp = PlannerResponseSchema()
    assert resp.mode.value == "task_input"
    assert resp.status.value == "ok"
    assert resp.tasks == []
    assert resp.warnings == []


def test_planner_response_full():
    """Full PlannerResponse should validate."""
    resp = PlannerResponseSchema(
        mode="morning_brief",
        status="ok",
        timezone="Europe/Kyiv",
        tasks=[TaskSchema(title="Test task", priority=3)],
        warnings=["Weather warning"],
        summary="1 задача",
    )
    assert resp.mode.value == "morning_brief"
    assert len(resp.tasks) == 1


def test_planner_response_needs_clarification():
    """Status needs_clarification with questions."""
    resp = PlannerResponseSchema(
        status="needs_clarification",
        clarification_questions=["Когда дедлайн?"],
    )
    assert resp.status.value == "needs_clarification"
    assert len(resp.clarification_questions) == 1
