"""Tests for Dependency Service."""

import pytest
import uuid
from unittest.mock import AsyncMock, patch

from app.models.task import TaskORM, TaskStatus
from app.services.dependencies import DependencyService


@pytest.mark.asyncio
async def test_dependency_cycle_detection():
    svc = DependencyService()
    
    t1_id = uuid.uuid4()
    t2_id = uuid.uuid4()
    t3_id = uuid.uuid4()
    
    # Let's patch _has_path to simulate a cycle
    async def mock_has_path(session, start_id, target_id):
        # We want to add t3 -> t1
        # It checks if t1 has a path to t3
        if start_id == t1_id and target_id == t3_id:
            return True
        return False
        
    svc._has_path = mock_has_path
    
    session = AsyncMock()
    session.get.side_effect = lambda model, pk: TaskORM(id=pk)
    
    # Adding t3 -> t1 should fail because t1 has path to t3 (cycle)
    success = await svc.add_dependency(session, t3_id, t1_id)
    assert success is False
    
    # Adding t3 -> t2 should succeed (assuming no path from t2 to t3)
    success = await svc.add_dependency(session, t3_id, t2_id)
    assert success is True


@pytest.mark.asyncio
async def test_can_complete():
    svc = DependencyService()
    
    t1_id = uuid.uuid4()
    t2_id = uuid.uuid4()
    
    session = AsyncMock()
    
    # Mocking execute for can_complete
    # First execute gets dep_ids
    # Second execute gets task statuses
    
    class MockResult:
        def __init__(self, items):
            self.items = items
        def scalars(self):
            class MockScalars:
                def __init__(self, items):
                    self.items = items
                def all(self):
                    return self.items
            return MockScalars(self.items)
            
    async def mock_execute(stmt):
        stmt_str = str(stmt).lower()
        if "task_dependencies.depends_on_id" in stmt_str:
            return MockResult([t2_id])
        if "tasks.status" in stmt_str:
            return MockResult([TaskStatus.CREATED])
        return MockResult([])
        
    session.execute = mock_execute
    
    assert await svc.can_complete(session, t1_id) is False
    
    # Now mock statuses as completed
    async def mock_execute_completed(stmt):
        stmt_str = str(stmt).lower()
        if "task_dependencies.depends_on_id" in stmt_str:
            return MockResult([t2_id])
        if "tasks.status" in stmt_str:
            return MockResult([TaskStatus.COMPLETED])
        return MockResult([])
        
    session.execute = mock_execute_completed
    assert await svc.can_complete(session, t1_id) is True
