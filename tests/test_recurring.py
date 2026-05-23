"""Tests for Recurring Tasks scheduler logic."""

from datetime import datetime
from app.services.scheduler import SchedulerService


def test_calc_next_run_daily():
    from_dt = datetime(2026, 5, 22, 12, 0)
    next_dt = SchedulerService._calc_next_run("daily", from_dt)
    assert next_dt == datetime(2026, 5, 23, 12, 0)


def test_calc_next_run_workdays():
    # May 22, 2026 is a Friday
    from_dt = datetime(2026, 5, 22, 12, 0)
    assert from_dt.weekday() == 4
    next_dt = SchedulerService._calc_next_run("workdays", from_dt)
    # Next workday should be Monday, May 25, 2026
    assert next_dt == datetime(2026, 5, 25, 12, 0)
    
    # May 25 is Monday, next is Tuesday
    next_dt_2 = SchedulerService._calc_next_run("workdays", next_dt)
    assert next_dt_2 == datetime(2026, 5, 26, 12, 0)


def test_calc_next_run_weekly():
    from_dt = datetime(2026, 5, 22, 12, 0)
    next_dt = SchedulerService._calc_next_run("weekly", from_dt)
    assert next_dt == datetime(2026, 5, 29, 12, 0)


def test_calc_next_run_weekly_custom():
    # May 22, 2026 is Friday
    from_dt = datetime(2026, 5, 22, 12, 0)
    
    # Target: Mon, Wed, Fri
    next_dt = SchedulerService._calc_next_run("weekly:mon,wed,fri", from_dt)
    # Next one after Friday is Monday (May 25)
    assert next_dt == datetime(2026, 5, 25, 12, 0)
    
    # Target: Tue, Sat
    next_dt = SchedulerService._calc_next_run("weekly:tue,sat", from_dt)
    # Next one after Friday is Saturday (May 23)
    assert next_dt == datetime(2026, 5, 23, 12, 0)


def test_calc_next_run_monthly_custom():
    from_dt = datetime(2026, 5, 22, 12, 0)
    # Target: 15th of the month
    next_dt = SchedulerService._calc_next_run("monthly:15", from_dt)
    assert next_dt.day == 15
    assert next_dt.month == 6
