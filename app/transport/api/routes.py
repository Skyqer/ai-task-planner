"""REST API transport — endpoints for future web/mobile clients."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.db import repository as repo
from app.schemas.planner import PlannerResponseSchema

api_router = APIRouter(prefix="/api/v1", tags=["api"])

# Planner instance is set at startup
_planner = None


def set_planner(planner) -> None:
    """Inject the core planner instance."""
    global _planner
    _planner = planner


class MessageRequest(BaseModel):
    user_id: int
    text: str


class TaskUpdateRequest(BaseModel):
    title: str | None = None
    priority: int | None = None
    status: str | None = None


@api_router.get("/health")
async def health_check():
    return {"status": "ok"}


@api_router.post("/message", response_model=PlannerResponseSchema)
async def process_message(
    body: MessageRequest,
    session: AsyncSession = Depends(get_session),
):
    """Send a text message to the planner and get structured response."""
    if not _planner:
        return PlannerResponseSchema(
            summary="Планировщик не инициализирован.",
            warnings=["Service not ready"],
        )
    return await _planner.process_message(session, body.user_id, body.text)


@api_router.get("/tasks/{user_id}")
async def get_tasks(
    user_id: int,
    session: AsyncSession = Depends(get_session),
):
    """List active tasks for a user."""
    tasks = await repo.get_active_tasks(session, user_id)
    return [
        {
            "id": str(t.id),
            "title": t.title,
            "type": t.type.value,
            "priority": t.priority,
            "status": t.status.value,
            "estimated_minutes": t.estimated_minutes,
            "deadline_date": str(t.deadline_date) if t.deadline_date else None,
            "deadline_time": t.deadline_time.strftime("%H:%M") if t.deadline_time else None,
            "fixed_time_date": str(t.fixed_time_date) if t.fixed_time_date else None,
            "fixed_time_time": t.fixed_time_time.strftime("%H:%M") if t.fixed_time_time else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tasks
    ]


@api_router.patch("/tasks/{task_id}")
async def update_task(
    task_id: str,
    body: TaskUpdateRequest,
    session: AsyncSession = Depends(get_session),
):
    """Update a task."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"error": "No fields to update"}

    task = await repo.update_task(session, uuid.UUID(task_id), **updates)
    if not task:
        return {"error": "Task not found"}
    return {"status": "updated", "task_id": task_id}


@api_router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Soft-delete a task."""
    task = await repo.soft_delete_task(session, uuid.UUID(task_id))
    if not task:
        return {"error": "Task not found"}
    return {"status": "deleted", "task_id": task_id}
