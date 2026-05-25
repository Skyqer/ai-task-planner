"""Constraint service — manages user time-block constraints."""

from __future__ import annotations

import logging
from datetime import date, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.constraint import ConstraintType, UserConstraintORM
from app.schemas.constraint import TimeBlock, UserConstraintSchema

logger = logging.getLogger(__name__)

# Defaults applied on first user registration
_DEFAULT_CONSTRAINTS = [
    {
        "constraint_type": ConstraintType.SLEEP,
        "start_time": "23:00",
        "end_time": "07:00",
        "label": "Sleep",
    },
    {
        "constraint_type": ConstraintType.SCHOOL,
        "start_time": "08:00",
        "end_time": "14:00",
        "label": "School",
        "days_of_week": [0, 1, 2, 3, 4],  # Mon-Fri
    },
]


def _parse_time(t: str) -> int:
    """Convert 'HH:MM' to minutes since midnight."""
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _format_time(minutes: int) -> str:
    """Convert minutes since midnight to 'HH:MM'."""
    minutes = minutes % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class ConstraintService:
    """Manages user constraints and computes blocked/free time windows."""

    async def ensure_defaults(
        self, session: AsyncSession, user_id: int
    ) -> None:
        """Create default constraints if user has none."""
        stmt = select(UserConstraintORM).where(
            UserConstraintORM.user_id == user_id
        )
        result = await session.execute(stmt)
        if result.scalars().first() is not None:
            return  # Already has constraints

        for defaults in _DEFAULT_CONSTRAINTS:
            constraint = UserConstraintORM(
                user_id=user_id, **defaults
            )
            session.add(constraint)
        await session.commit()
        logger.info("Created default constraints for user %d", user_id)

    async def get_constraints(
        self, session: AsyncSession, user_id: int
    ) -> list[UserConstraintSchema]:
        """Get all active constraints for a user."""
        stmt = (
            select(UserConstraintORM)
            .where(
                UserConstraintORM.user_id == user_id,
                UserConstraintORM.is_active.is_(True),
            )
            .order_by(UserConstraintORM.start_time)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [
            UserConstraintSchema(
                constraint_type=r.constraint_type,
                start_time=r.start_time,
                end_time=r.end_time,
                days_of_week=r.days_of_week,
                label=r.label,
                is_active=r.is_active,
            )
            for r in rows
        ]

    async def get_blocked_windows(
        self, session: AsyncSession, user_id: int, target_date: date
    ) -> list[TimeBlock]:
        """Get all blocked time windows for a specific date."""
        constraints = await self.get_constraints(session, user_id)
        day_of_week = target_date.weekday()  # 0=Mon

        blocks: list[TimeBlock] = []
        for c in constraints:
            # Check if this constraint applies to the target day
            if c.days_of_week is not None and day_of_week not in c.days_of_week:
                continue

            start_m = _parse_time(c.start_time)
            end_m = _parse_time(c.end_time)

            if start_m < end_m:
                # Normal range (e.g. 08:00–14:00)
                blocks.append(TimeBlock(
                    start=c.start_time,
                    end=c.end_time,
                    label=c.label or c.constraint_type.value,
                    block_type=c.constraint_type.value,
                ))
            else:
                # Overnight range (e.g. 23:00–07:00)
                # Split into two blocks for the target day
                blocks.append(TimeBlock(
                    start="00:00",
                    end=c.end_time,
                    label=c.label or c.constraint_type.value,
                    block_type=c.constraint_type.value,
                ))
                blocks.append(TimeBlock(
                    start=c.start_time,
                    end="23:59",
                    label=c.label or c.constraint_type.value,
                    block_type=c.constraint_type.value,
                ))

        # Sort by start time
        blocks.sort(key=lambda b: _parse_time(b.start))
        return blocks

    async def get_free_windows(
        self, session: AsyncSession, user_id: int, target_date: date
    ) -> list[TimeBlock]:
        """Get available (free) time windows for a specific date."""
        blocked = await self.get_blocked_windows(session, user_id, target_date)
        return compute_free_windows(blocked)

    async def is_time_blocked(
        self,
        session: AsyncSession,
        user_id: int,
        target_date: date,
        start: str,
        end: str,
    ) -> bool:
        """Check if a given time range overlaps with any constraint."""
        blocked = await self.get_blocked_windows(session, user_id, target_date)
        start_m = _parse_time(start)
        end_m = _parse_time(end)

        for b in blocked:
            b_start = _parse_time(b.start)
            b_end = _parse_time(b.end)
            if start_m < b_end and end_m > b_start:
                return True
        return False

    async def add_constraint(
        self,
        session: AsyncSession,
        user_id: int,
        constraint_type: ConstraintType,
        start_time: str,
        end_time: str,
        label: str = "",
        days_of_week: list[int] | None = None,
    ) -> UserConstraintORM:
        """Add a new constraint."""
        c = UserConstraintORM(
            user_id=user_id,
            constraint_type=constraint_type,
            start_time=start_time,
            end_time=end_time,
            label=label,
            days_of_week=days_of_week,
        )
        session.add(c)
        await session.commit()
        await session.refresh(c)
        return c

    async def remove_constraint(
        self, session: AsyncSession, constraint_id: str
    ) -> bool:
        """Soft-deactivate a constraint."""
        import uuid
        stmt = select(UserConstraintORM).where(
            UserConstraintORM.id == uuid.UUID(constraint_id)
        )
        result = await session.execute(stmt)
        constraint = result.scalar_one_or_none()
        if not constraint:
            return False
        constraint.is_active = False
        await session.commit()
        return True

    async def remove_constraint_by_label(
        self, session: AsyncSession, user_id: int, label: str
    ) -> bool:
        """Soft-deactivate a constraint by its label (case-insensitive)."""
        stmt = select(UserConstraintORM).where(
            UserConstraintORM.user_id == user_id,
            UserConstraintORM.label.ilike(label.strip()),
            UserConstraintORM.is_active.is_(True)
        )
        result = await session.execute(stmt)
        constraints = result.scalars().all()
        if not constraints:
            return False
        
        for c in constraints:
            c.is_active = False
        await session.commit()
        return True


def compute_free_windows(
    blocked: list[TimeBlock],
    day_start: str = "00:00",
    day_end: str = "23:59",
) -> list[TimeBlock]:
    """Compute free windows from a list of blocked windows.

    Pure function — no DB access. Used by both ConstraintService and TimelineEngine.
    """
    if not blocked:
        return [TimeBlock(start=day_start, end=day_end, block_type="free")]

    # Merge overlapping blocks
    merged: list[tuple[int, int]] = []
    for b in sorted(blocked, key=lambda x: _parse_time(x.start)):
        s = _parse_time(b.start)
        e = _parse_time(b.end)
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    # Find gaps
    free: list[TimeBlock] = []
    ds = _parse_time(day_start)
    de = _parse_time(day_end)

    cursor = ds
    for s, e in merged:
        if cursor < s:
            free.append(TimeBlock(
                start=_format_time(cursor),
                end=_format_time(s),
                block_type="free",
            ))
        cursor = max(cursor, e)

    if cursor < de:
        free.append(TimeBlock(
            start=_format_time(cursor),
            end=_format_time(de),
            block_type="free",
        ))

    return free
