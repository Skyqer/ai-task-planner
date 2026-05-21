"""Database CRUD operations for tasks, messages, and users."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import MemorySummaryORM, MessageORM, MessageRole
from app.models.task import TaskORM, TaskStatus
from app.models.user import UserORM


# ── Task CRUD ────────────────────────────────────────────────────────────────


async def create_task(session: AsyncSession, user_id: int, **kwargs) -> TaskORM:
    """Create and persist a new task."""
    task = TaskORM(user_id=user_id, **kwargs)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def get_tasks_for_today(
    session: AsyncSession,
    user_id: int,
    today: date | None = None,
) -> list[TaskORM]:
    """Get non-deleted tasks for today (by deadline or fixed_time)."""
    today = today or date.today()
    stmt = (
        select(TaskORM)
        .where(
            TaskORM.user_id == user_id,
            TaskORM.is_deleted.is_(False),
            TaskORM.status.notin_([TaskStatus.COMPLETED, TaskStatus.CANCELLED]),
        )
        .where(
            (TaskORM.deadline_date == today)
            | (TaskORM.fixed_time_date == today)
            | (TaskORM.deadline_date.is_(None) & TaskORM.fixed_time_date.is_(None))
        )
        .order_by(TaskORM.priority.desc(), TaskORM.created_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_active_tasks(
    session: AsyncSession,
    user_id: int,
) -> list[TaskORM]:
    """Get all active (non-deleted, non-completed) tasks."""
    stmt = (
        select(TaskORM)
        .where(
            TaskORM.user_id == user_id,
            TaskORM.is_deleted.is_(False),
            TaskORM.status.notin_([TaskStatus.COMPLETED, TaskStatus.CANCELLED]),
        )
        .order_by(TaskORM.priority.desc(), TaskORM.created_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_task(
    session: AsyncSession,
    task_id: uuid.UUID,
    **kwargs,
) -> TaskORM | None:
    """Update task fields. Returns updated task or None."""
    stmt = (
        update(TaskORM)
        .where(TaskORM.id == task_id)
        .values(**kwargs)
        .returning(TaskORM)
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one_or_none()


async def mark_completed(session: AsyncSession, task_id: uuid.UUID) -> TaskORM | None:
    """Mark a task as completed."""
    return await update_task(session, task_id, status=TaskStatus.COMPLETED)


async def mark_cancelled(session: AsyncSession, task_id: uuid.UUID) -> TaskORM | None:
    """Mark a task as cancelled."""
    return await update_task(session, task_id, status=TaskStatus.CANCELLED)


async def soft_delete_task(
    session: AsyncSession, task_id: uuid.UUID
) -> TaskORM | None:
    """Soft-delete a task."""
    return await update_task(
        session,
        task_id,
        is_deleted=True,
        deleted_at=datetime.now(timezone.utc),
    )


async def get_tasks_with_upcoming_deadlines(
    session: AsyncSession,
    before: datetime,
) -> list[TaskORM]:
    """Get tasks with deadlines before the given datetime (for reminders)."""
    stmt = (
        select(TaskORM)
        .where(
            TaskORM.is_deleted.is_(False),
            TaskORM.status.notin_([TaskStatus.COMPLETED, TaskStatus.CANCELLED]),
            TaskORM.deadline_date.isnot(None),
        )
        .order_by(TaskORM.deadline_date, TaskORM.deadline_time)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ── Message CRUD ─────────────────────────────────────────────────────────────


async def add_message(
    session: AsyncSession,
    user_id: int,
    role: MessageRole,
    content: str,
) -> MessageORM:
    """Store a chat message."""
    msg = MessageORM(user_id=user_id, role=role, content=content)
    session.add(msg)
    await session.commit()
    return msg


async def get_recent_messages(
    session: AsyncSession,
    user_id: int,
    limit: int = 20,
) -> list[MessageORM]:
    """Get last N messages for a user, ordered oldest-first."""
    stmt = (
        select(MessageORM)
        .where(MessageORM.user_id == user_id)
        .order_by(MessageORM.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    messages = list(result.scalars().all())
    messages.reverse()  # oldest first
    return messages


async def count_messages(session: AsyncSession, user_id: int) -> int:
    """Count total messages for a user."""
    from sqlalchemy import func

    stmt = select(func.count(MessageORM.id)).where(
        MessageORM.user_id == user_id
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def delete_old_messages(
    session: AsyncSession,
    user_id: int,
    keep_last: int = 20,
) -> int:
    """Delete messages older than the last N. Returns count deleted."""
    from sqlalchemy import delete

    # Get the created_at of the Nth newest message
    subq = (
        select(MessageORM.created_at)
        .where(MessageORM.user_id == user_id)
        .order_by(MessageORM.created_at.desc())
        .offset(keep_last)
        .limit(1)
        .scalar_subquery()
    )
    stmt = (
        delete(MessageORM)
        .where(
            MessageORM.user_id == user_id,
            MessageORM.created_at <= subq,
        )
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount


# ── Memory Summary CRUD ──────────────────────────────────────────────────────


async def get_memory_summary(
    session: AsyncSession, user_id: int
) -> MemorySummaryORM | None:
    """Get the stored summary for a user."""
    stmt = select(MemorySummaryORM).where(
        MemorySummaryORM.user_id == user_id
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_memory_summary(
    session: AsyncSession, user_id: int, summary: str
) -> MemorySummaryORM:
    """Create or update the memory summary for a user."""
    existing = await get_memory_summary(session, user_id)
    if existing:
        existing.summary = summary
        existing.updated_at = datetime.now(timezone.utc)
    else:
        existing = MemorySummaryORM(user_id=user_id, summary=summary)
        session.add(existing)
    await session.commit()
    return existing


# ── User CRUD ────────────────────────────────────────────────────────────────


async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: str | None = None,
) -> UserORM:
    """Get existing user or create with defaults."""
    stmt = select(UserORM).where(UserORM.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        user = UserORM(id=user_id, username=username)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_all_users(session: AsyncSession) -> list[UserORM]:
    """Get all registered users."""
    result = await session.execute(select(UserORM))
    return list(result.scalars().all())
