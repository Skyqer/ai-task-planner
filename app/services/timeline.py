"""Timeline Engine — deterministic day schedule builder.

Builds a schedule from constraints, fixed events, and deadline tasks.
No LLM involved — pure algorithmic slot-filling.
"""

from __future__ import annotations

import logging
from datetime import date as date_type, datetime, time as time_type, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository as repo
from app.schemas.constraint import TimeBlock
from app.schemas.timeline import DayTimelineSchema
from app.services.constraints import ConstraintService, compute_free_windows, _parse_time, _format_time

logger = logging.getLogger(__name__)


class TimelineEngine:
    """Builds a day timeline respecting constraints, fixed events, and deadlines."""

    def __init__(self, constraint_service: ConstraintService, tz_name: str = "Europe/Kyiv", weather_service = None) -> None:
        self._constraints = constraint_service
        self._tz_name = tz_name
        self._weather_service = weather_service
        from app.services.routine import RoutineLearner
        from app.services.energy import EnergyService
        self._routine_learner = RoutineLearner()
        self._energy_service = EnergyService()

    async def build_day(
        self, session: AsyncSession, user_id: int, target_date: date_type | None = None
    ) -> DayTimelineSchema:
        """Build a complete day timeline for the user."""
        if target_date is None:
            try:
                from zoneinfo import ZoneInfo
                target_date = datetime.now(ZoneInfo(self._tz_name)).date()
            except Exception:
                target_date = datetime.now(timezone(timedelta(hours=2))).date()

        warnings: list[str] = []
        suggestions: list[str] = []

        # 1. Get constraint blocks (sleep, school, etc.)
        constraint_blocks = await self._constraints.get_blocked_windows(
            session, user_id, target_date
        )
        
        energy_profile = await self._energy_service.get_energy_profile(session, user_id)

        # 2. Get tasks for the day
        tasks = await repo.get_active_tasks(session, user_id)

        # 3. Separate fixed-time tasks and flexible tasks
        fixed_blocks: list[TimeBlock] = []
        flexible_tasks: list[tuple] = []  # (task, priority_score)

        for task in tasks:
            if task.fixed_time_date and task.fixed_time_time:
                ft_date = task.fixed_time_date
                if isinstance(ft_date, str):
                    ft_date = date_type.fromisoformat(ft_date)
                if ft_date == target_date:
                    start_str = task.fixed_time_time.strftime("%H:%M")
                    end_minutes = _parse_time(start_str) + (task.estimated_minutes or 30)
                    end_str = _format_time(end_minutes)

                    # Check conflict with constraints
                    is_blocked = any(
                        _parse_time(start_str) < _parse_time(b.end)
                        and _parse_time(end_str) > _parse_time(b.start)
                        for b in constraint_blocks
                    )
                    if is_blocked:
                        warnings.append(
                            f"⚠️ '{task.title}' запланирована на {start_str}, "
                            f"но это время заблокировано."
                        )

                    fixed_blocks.append(TimeBlock(
                        start=start_str,
                        end=end_str,
                        label=task.title,
                        block_type="task",
                        task_id=str(task.id),
                    ))
                    continue

            # Check deadline tasks for today
            if task.deadline_date:
                dl_date = task.deadline_date
                if isinstance(dl_date, str):
                    dl_date = date_type.fromisoformat(dl_date)
                if dl_date == target_date or dl_date <= target_date:
                    score = task.priority * 100 + (100 - (task.estimated_minutes or 30))
                    flexible_tasks.append((task, score))
                    continue

            # Tasks with no date — include if no date constraints
            if not task.fixed_time_date and not task.deadline_date:
                score = task.priority * 50
                flexible_tasks.append((task, score))

        # 4. Sort flexible tasks by priority score (highest first)
        flexible_tasks.sort(key=lambda x: x[1], reverse=True)

        # 5. All blocked = constraints + fixed tasks
        all_blocked = constraint_blocks + fixed_blocks

        # 6. Detect conflicts between fixed tasks
        for i, fb1 in enumerate(fixed_blocks):
            for fb2 in fixed_blocks[i + 1:]:
                s1, e1 = _parse_time(fb1.start), _parse_time(fb1.end)
                s2, e2 = _parse_time(fb2.start), _parse_time(fb2.end)
                if s1 < e2 and s2 < e1:
                    warnings.append(
                        f"⚠️ Конфликт: '{fb1.label}' и '{fb2.label}' "
                        f"пересекаются ({fb1.start}–{fb1.end} vs {fb2.start}–{fb2.end})."
                    )

        # 7. Compute free windows
        free_windows = compute_free_windows(all_blocked)

        # 8. Place flexible tasks into free windows (greedy)
        placed_blocks: list[TimeBlock] = []
        unplaced: list[str] = []

        for task, _ in flexible_tasks:
            duration = task.estimated_minutes or 30
            placed = False

            task_type_str = task.type.value if task.type else "other"
            pref_slot = await self._routine_learner.get_preferred_slot(
                session, user_id, task_type_str
            )

            # Try to place near preferred slot if available
            if pref_slot is not None:
                for fw in free_windows:
                    if fw.duration_minutes >= duration:
                        if fw.start_minutes <= pref_slot <= fw.end_minutes:
                            # Place as close to preferred slot as possible
                            start_m = max(fw.start_minutes, pref_slot - duration // 2)
                            # Ensure it fits
                            if start_m + duration > fw.end_minutes:
                                start_m = fw.end_minutes - duration
                                
                            end_m = start_m + duration
                            placed_blocks.append(TimeBlock(
                                start=_format_time(start_m),
                                end=_format_time(end_m),
                                label=task.title + " (Привычка)",
                                block_type="task",
                                task_id=str(task.id),
                            ))
                            
                            # We'll just split the free window into two (before and after)
                            # For simplicity, we just rebuild free windows next iteration
                            # But since we're iterating over free_windows, we should just update placed_blocks
                            # and recompute free_windows.
                            placed = True
                            break

                if placed:
                    # Recompute free windows
                    all_blocks = constraint_blocks + fixed_blocks + placed_blocks
                    all_blocks.sort(key=lambda b: _parse_time(b.start))
                    free_windows = compute_free_windows(all_blocks)
                    continue

            # Energy fallback
            suggested_hours = self._energy_service.suggest_task_placement(task.priority, energy_profile)
            
            # Find a free window that overlaps with suggested hours, or just take the first one
            best_fw = None
            for fw in free_windows:
                if fw.duration_minutes >= duration:
                    # Check if fw covers any suggested hour
                    start_h = fw.start_minutes // 60
                    end_h = fw.end_minutes // 60
                    if any(h in suggested_hours for h in range(start_h, end_h + 1)):
                        best_fw = fw
                        break
            
            if not best_fw:
                # Just take the first one
                for fw in free_windows:
                    if fw.duration_minutes >= duration:
                        best_fw = fw
                        break
                        
            if best_fw:
                start_m = best_fw.start_minutes
                end_m = start_m + duration

                placed_blocks.append(TimeBlock(
                    start=_format_time(start_m),
                    end=_format_time(end_m),
                    label=task.title,
                    block_type="task",
                    task_id=str(task.id),
                ))

                # Shrink the free window
                best_fw.start = _format_time(end_m)
                placed = True

            if not placed:
                unplaced.append(task.title)

        if unplaced:
            warnings.append(
                f"⚠️ Не хватает времени для: {', '.join(unplaced)}. "
                f"Рассмотрите перенос на другой день."
            )
            for name in unplaced:
                suggestions.append(f"Перенесите '{name}' на завтра или сократите длительность.")
                
        # Weather check
        if self._weather_service:
            # We fetch weather only for today.
            from datetime import timezone
            # target_date is a date object
            weather = await self._weather_service.get_current_weather()
            if weather and weather.is_rainy:
                # find weather sensitive tasks that are placed today
                weather_sensitive = [t for t in tasks if t.weather_sensitive]
                for w_task in weather_sensitive:
                    # check if w_task is in placed_blocks or fixed_blocks
                    if any(b.task_id == str(w_task.id) for b in fixed_blocks + placed_blocks):
                        warnings.append(
                            f"☔ Внимание: ожидается дождь, а задача '{w_task.title}' "
                            f"чувствительна к погоде. Возможно, стоит её перенести."
                        )
                        suggestions.append(f"Перенесите '{w_task.title}' из-за дождя.")

        # 9. Combine all blocks and sort
        all_blocks = constraint_blocks + fixed_blocks + placed_blocks
        all_blocks.sort(key=lambda b: _parse_time(b.start))

        # Recompute final free windows
        final_free = compute_free_windows(all_blocks)

        return DayTimelineSchema(
            date=target_date.isoformat(),
            blocks=all_blocks,
            free_windows=final_free,
            warnings=warnings,
            suggestions=suggestions,
        )
