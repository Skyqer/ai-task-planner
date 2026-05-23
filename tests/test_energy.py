"""Tests for Energy Service."""

import pytest

from app.services.energy import EnergyService


@pytest.mark.asyncio
async def test_energy_service():
    svc = EnergyService()
    
    class MockUser:
        def __init__(self, energy_profile):
            self.energy_profile = energy_profile
            
    class MockSession:
        async def get(self, *args, **kwargs):
            return MockUser({"9": 5, "14": 1})
            
    session = MockSession()
    profile = await svc.get_energy_profile(session, 123)
    
    assert profile["9"] == 5
    assert profile["14"] == 1
    # Fallback to default
    assert profile["10"] == 5
    assert profile["0"] == 1

    high_priority_hours = svc.suggest_task_placement(5, profile)
    assert 9 in high_priority_hours
    assert 10 in high_priority_hours
    assert 14 not in high_priority_hours
    
    low_priority_hours = svc.suggest_task_placement(1, profile)
    # low priority should suggest moderate hours (2, 3), 14 is 1, so it won't be there, 
    # but e.g. 7 (energy 3) should be there
    assert 7 in low_priority_hours
    assert 9 not in low_priority_hours
