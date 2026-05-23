"""Tests for Constraint Service."""

import pytest
from datetime import date

from app.schemas.constraint import TimeBlock
from app.services.constraints import ConstraintService, compute_free_windows


def test_compute_free_windows_empty():
    blocked = []
    free = compute_free_windows(blocked)
    assert len(free) == 1
    assert free[0].start == "00:00"
    assert free[0].end == "23:59"


def test_compute_free_windows_single():
    blocked = [TimeBlock(start="10:00", end="12:00", block_type="task")]
    free = compute_free_windows(blocked)
    assert len(free) == 2
    assert free[0].start == "00:00"
    assert free[0].end == "10:00"
    assert free[1].start == "12:00"
    assert free[1].end == "23:59"


def test_compute_free_windows_overlap():
    blocked = [
        TimeBlock(start="10:00", end="12:00", block_type="task"),
        TimeBlock(start="11:30", end="13:00", block_type="task"),
    ]
    free = compute_free_windows(blocked)
    assert len(free) == 2
    assert free[0].start == "00:00"
    assert free[0].end == "10:00"
    assert free[1].start == "13:00"
    assert free[1].end == "23:59"
