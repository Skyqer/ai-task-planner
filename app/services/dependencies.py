"""Task Dependency Service.

Handles logic for blocking tasks until their dependencies are met,
and cycle detection.
"""

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dependency import TaskDependencyORM
from app.models.task import TaskORM, TaskStatus


class DependencyService:
    """Manages task dependencies."""

    async def add_dependency(
        self, session: AsyncSession, task_id: uuid.UUID, depends_on_id: uuid.UUID
    ) -> bool:
        """Add a dependency. Returns False if it would create a cycle or if tasks don't exist."""
        if task_id == depends_on_id:
            return False

        # Check if tasks exist
        t1 = await session.get(TaskORM, task_id)
        t2 = await session.get(TaskORM, depends_on_id)
        if not t1 or not t2:
            return False

        # Cycle detection: check if depends_on_id (or its deps) depends on task_id
        if await self._has_path(session, depends_on_id, task_id):
            return False

        # Add dependency
        dep = TaskDependencyORM(task_id=task_id, depends_on_id=depends_on_id)
        session.add(dep)
        await session.commit()
        return True

    async def _has_path(
        self, session: AsyncSession, start_id: uuid.UUID, target_id: uuid.UUID
    ) -> bool:
        """Check if there is a dependency path from start_id to target_id (DFS)."""
        visited = set()
        stack = [start_id]

        while stack:
            curr = stack.pop()
            if curr == target_id:
                return True
            if curr in visited:
                continue
                
            visited.add(curr)
            
            stmt = select(TaskDependencyORM.depends_on_id).where(
                TaskDependencyORM.task_id == curr
            )
            result = await session.execute(stmt)
            deps = result.scalars().all()
            
            stack.extend(deps)

        return False

    async def can_complete(self, session: AsyncSession, task_id: uuid.UUID) -> bool:
        """Check if all dependencies for a task are completed."""
        stmt = select(TaskDependencyORM.depends_on_id).where(
            TaskDependencyORM.task_id == task_id
        )
        result = await session.execute(stmt)
        dep_ids = result.scalars().all()

        if not dep_ids:
            return True

        # Check statuses of dependencies
        stmt_tasks = select(TaskORM.status).where(TaskORM.id.in_(dep_ids))
        res_tasks = await session.execute(stmt_tasks)
        statuses = res_tasks.scalars().all()

        return all(status == TaskStatus.COMPLETED for status in statuses)

    async def get_incomplete_dependencies(
        self, session: AsyncSession, task_id: uuid.UUID
    ) -> Sequence[TaskORM]:
        """Get the list of incomplete dependency tasks."""
        stmt = select(TaskDependencyORM.depends_on_id).where(
            TaskDependencyORM.task_id == task_id
        )
        result = await session.execute(stmt)
        dep_ids = result.scalars().all()

        if not dep_ids:
            return []

        stmt_tasks = select(TaskORM).where(
            TaskORM.id.in_(dep_ids), TaskORM.status != TaskStatus.COMPLETED
        )
        res_tasks = await session.execute(stmt_tasks)
        return res_tasks.scalars().all()
