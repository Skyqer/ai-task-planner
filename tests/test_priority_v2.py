"""Tests for Priority Engine v2 (Phase 2 enhancements)."""

from datetime import date, datetime, time, timedelta

from app.models.task import DeadlineKind, TaskType
from app.schemas.planner import PlannerResponseSchema
from app.schemas.task import DeadlineSchema, TaskSchema
from app.services.priority import PriorityEngine


def test_overdue_detection():
    engine = PriorityEngine()
    today = date(2026, 5, 22)
    now = datetime(2026, 5, 22, 12, 0, tzinfo=engine._tz)
    
    task = TaskSchema(
        title="Old task",
        deadline=DeadlineSchema(
            date="2026-05-20",
            kind=DeadlineKind.HARD,
        ),
        priority=2,
    )
    resp = PlannerResponseSchema(tasks=[task])
    
    engine._apply_deadline_rules(task, now, today, resp)
    
    assert task.priority == 5
    assert any("просрочена" in w for w in resp.warnings)


def test_type_boost():
    engine = PriorityEngine()
    
    task_study = TaskSchema(title="Study math", type=TaskType.STUDY, priority=2)
    engine._apply_type_rules(task_study)
    assert task_study.priority == 3
    
    task_work = TaskSchema(title="Work project", type=TaskType.WORK, priority=3)
    engine._apply_type_rules(task_work)
    assert task_work.priority == 4
    
    task_home = TaskSchema(title="Clean room", type=TaskType.HOME, priority=2)
    engine._apply_type_rules(task_home)
    assert task_home.priority == 2


def test_not_enough_time_warning():
    engine = PriorityEngine()
    today = date(2026, 5, 22)
    now = datetime(2026, 5, 22, 12, 0, tzinfo=engine._tz)
    
    # 2 hours left, but task takes 3 hours (180 mins)
    task = TaskSchema(
        title="Big task",
        deadline=DeadlineSchema(
            date="2026-05-22",
            time="14:00",
            kind=DeadlineKind.HARD,
        ),
        estimated_minutes=180,
        priority=2,
    )
    resp = PlannerResponseSchema(tasks=[task])
    
    engine._apply_deadline_rules(task, now, today, resp)
    
    assert task.priority == 5
    assert any("может не хватить времени" in w for w in resp.warnings)
