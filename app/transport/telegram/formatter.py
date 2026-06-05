"""Format PlannerResponse into Telegram-friendly text."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.schemas.planner import PlannerResponseSchema
from app.schemas.timeline import DayTimelineSchema
from app.transport.telegram.callbacks import TaskActionCallback, ReminderAckCallback

# Priority emoji mapping
_PRIORITY_EMOJI = {
    1: "⚪",
    2: "🟢",
    3: "🟡",
    4: "🟠",
    5: "🔴",
}

_BLOCK_TYPE_EMOJI = {
    "sleep": "🌙",
    "school": "🏫",
    "unavailable": "🚫",
    "focus": "🎯",
    "task": "📌",
    "free": "✨",
}

_TELEGRAM_MAX_LENGTH = 4096


def format_planner_response(response: PlannerResponseSchema) -> str:
    """Convert PlannerResponse into a formatted Telegram message."""
    parts: list[str] = []

    # Summary
    if response.summary:
        parts.append(response.summary)

    # Tasks
    if response.tasks:
        task_lines = []
        for i, task in enumerate(response.tasks, 1):
            emoji = _PRIORITY_EMOJI.get(task.priority, "⚪")
            line = f"{emoji} <b>{i}. {task.title}</b>"

            details = []
            if task.estimated_minutes:
                details.append(f"~{task.estimated_minutes} min")
            if task.deadline and task.deadline.time:
                kind = "⏰" if task.deadline.kind and task.deadline.kind.value == "hard" else "🕐"
                details.append(f"{kind} until {task.deadline.time}")
            if task.deadline and task.deadline.date:
                details.append(f"📅 {task.deadline.date}")
            if task.fixed_time and task.fixed_time.time:
                details.append(f"📌 at {task.fixed_time.time}")
            if task.type:
                details.append(f"[{task.type.value}]")

            if details:
                line += f"\n   └ <i>{' · '.join(details)}</i>"
            task_lines.append(line)

        parts.append("\n".join(task_lines))

    # Schedule suggestions
    if response.schedule_suggestions:
        sug_lines = ["📋 <b>Recommendations:</b>"]
        for s in response.schedule_suggestions:
            time_range = ""
            if s.start and s.end:
                time_range = f"{s.start} – {s.end}: "
            sug_lines.append(f"  • {time_range}{s.task_title} — {s.reason}")
        parts.append("\n".join(sug_lines))

    # Warnings
    if response.warnings:
        warn_lines = [f"⚠️ {w}" for w in response.warnings]
        parts.append("\n".join(warn_lines))

    # Clarification questions
    if response.clarification_questions:
        q_lines = ["❓ <b>Clarify:</b>"]
        for i, q in enumerate(response.clarification_questions, 1):
            q_lines.append(f"  {i}. {q}")
        parts.append("\n".join(q_lines))

    text = "\n\n".join(parts) if parts else "✅ Processed."

    # Truncate if exceeds Telegram limit
    if len(text) > _TELEGRAM_MAX_LENGTH:
        text = text[: _TELEGRAM_MAX_LENGTH - 20] + "\n\n... (truncated)"

    return text


def format_task_list(tasks) -> str:
    """Format a list of TaskORM objects for the /tasks command."""
    if not tasks:
        return "📋 No active tasks."

    lines = ["✨ <b>Your active tasks</b>\n"]
    for i, task in enumerate(tasks, 1):
        emoji = _PRIORITY_EMOJI.get(task.priority, "⚪")
        line = f"{emoji} <b>{i}. {task.title}</b>"

        details = []
        if task.estimated_minutes:
            details.append(f"~{task.estimated_minutes} min")
        if task.deadline_date:
            details.append(f"📅 {task.deadline_date}")
        if task.deadline_time:
            details.append(f"⏰ {task.deadline_time.strftime('%H:%M')}")
        if task.fixed_time_time:
            details.append(f"📌 {task.fixed_time_time.strftime('%H:%M')}")
        if task.status:
            details.append(f"[{task.status.value}]")

        if details:
            line += f"\n   └ <i>{' · '.join(details)}</i>"
        if task.details:
            line += f"\n   📝 <i>{task.details}</i>"
        line += "\n"
        lines.append(line)

    return "\n".join(lines)


def format_timeline(timeline: DayTimelineSchema) -> str:
    """Format a day timeline for Telegram."""
    parts: list[str] = [f"📅 <b>Schedule for {timeline.date}</b>\n"]

    if timeline.blocks:
        for block in timeline.blocks:
            emoji = _BLOCK_TYPE_EMOJI.get(block.block_type, "📦")
            parts.append(f"  {emoji} {block.start} – {block.end}  <b>{block.label}</b>")
    else:
        parts.append("  No scheduled blocks.")

    if timeline.free_windows:
        parts.append("\n✨ <b>Free windows:</b>")
        for fw in timeline.free_windows:
            duration = fw.duration_minutes
            parts.append(f"  🟢 {fw.start} – {fw.end} ({duration} min)")

    if timeline.warnings:
        parts.append("")
        for w in timeline.warnings:
            parts.append(w)

    if timeline.suggestions:
        parts.append("\n💡 <b>Recommendations:</b>")
        for s in timeline.suggestions:
            parts.append(f"  • {s}")

    text = "\n".join(parts)
    if len(text) > _TELEGRAM_MAX_LENGTH:
        text = text[: _TELEGRAM_MAX_LENGTH - 20] + "\n\n... (truncated)"
    return text


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Get the persistent main menu keyboard."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 My tasks")
    builder.button(text="🌅 My day")
    builder.button(text="📅 Schedule")
    builder.button(text="🔄 Recurring")
    builder.button(text="📊 Statistics")
    builder.button(text="❓ Help")
    builder.adjust(3, 3)
    return builder.as_markup(resize_keyboard=True, persistent=True)


def get_tasks_keyboard(tasks) -> InlineKeyboardMarkup | None:
    """Get an inline keyboard for task actions."""
    if not tasks:
        return None

    builder = InlineKeyboardBuilder()
    for i, task in enumerate(tasks, 1):
        builder.button(
            text=f"✅ {i}",
            callback_data=TaskActionCallback(action="done", task_id=str(task.id)).pack(),
        )
        builder.button(
            text=f"🗑 {i}",
            callback_data=TaskActionCallback(action="delete", task_id=str(task.id)).pack(),
        )

    # Adjust to 2 buttons per row (✅ and 🗑 for each task)
    builder.adjust(2)
    return builder.as_markup()


def get_reminder_keyboard(reminder_id: str) -> InlineKeyboardMarkup:
    """Get an inline keyboard for a reminder acknowledgement."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Got it",
        callback_data=ReminderAckCallback(reminder_id=reminder_id).pack(),
    )
    return builder.as_markup()


def format_recurrence_list(recurrences) -> str:
    """Format a list of RecurrenceORM objects for the /recurring command."""
    if not recurrences:
        return "🔄 No active recurring tasks."

    lines = ["🔄 <b>Your recurring tasks</b>\n"]
    for i, rec in enumerate(recurrences, 1):
        task = rec.task
        emoji = _PRIORITY_EMOJI.get(task.priority, "⚪")
        line = f"{emoji} <b>{i}. {task.title}</b>"

        details = []
        details.append(f"repeats: {rec.pattern}")
        if rec.next_run:
            details.append(f"next run: {rec.next_run.strftime('%Y-%m-%d %H:%M')}")
        
        if details:
            line += f"\n   └ <i>{' · '.join(details)}</i>\n"
        lines.append(line)

    return "\n".join(lines)


def get_recurrences_keyboard(recurrences) -> InlineKeyboardMarkup | None:
    """Get an inline keyboard to manage recurrences."""
    if not recurrences:
        return None

    from app.transport.telegram.callbacks import RecurrenceActionCallback
    builder = InlineKeyboardBuilder()
    for i, rec in enumerate(recurrences, 1):
        builder.button(
            text=f"❌ Cancel {i}",
            callback_data=RecurrenceActionCallback(action="cancel", recur_id=str(rec.id)).pack(),
        )

    builder.adjust(2)
    return builder.as_markup()


def get_reschedule_keyboard(task_id: str, new_time_iso: str) -> InlineKeyboardMarkup:
    """Get an inline keyboard for rescheduling suggestions."""
    from app.transport.telegram.callbacks import RescheduleActionCallback
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Agree",
        callback_data=RescheduleActionCallback(
            action="accept", 
            task_id=task_id, 
            new_time=new_time_iso[:20]  # truncate if needed to fit callback size limits
        ).pack(),
    )
    builder.button(
        text="❌ Leave as is",
        callback_data=RescheduleActionCallback(
            action="dismiss", 
            task_id=task_id, 
            new_time=""
        ).pack(),
    )
    return builder.as_markup()


def format_stats(stats) -> str:
    """Format user statistics for Telegram."""
    period_names = {
        "today": "Today",
        "week": "Week",
        "month": "Month",
        "all_time": "All time",
    }
    period_name = period_names.get(stats.period, stats.period)

    lines = [
        f"📊 <b>Your statistics ({period_name})</b>",
        "",
        f"✅ <b>Completed:</b> {stats.total_completed}",
        f"❌ <b>Cancelled:</b> {stats.total_cancelled}",
        f"⏳ <b>Overdue:</b> {stats.total_overdue}",
        f"🔥 <b>Day streak:</b> {stats.current_streak_days}",
    ]
    
    if stats.total_completed > 0:
        lines.append(f"⏱ <b>Average time per task:</b> {stats.avg_duration_minutes} min")
        
        if stats.by_category:
            lines.append("")
            lines.append("🗂 <b>By categories:</b>")
            for cat, count in sorted(stats.by_category.items(), key=lambda x: x[1], reverse=True):
                # map internal category names to human readable if needed
                cat_emoji = {"work": "💼", "study": "📚", "home": "🏠", "health": "💊", "sport": "🏋️", "errand": "🛒"}.get(cat, "📌")
                lines.append(f"  {cat_emoji} {cat.capitalize()}: {count}")

    return "\n".join(lines)


def format_sys_stats(uptime_str: str, ram_mb: float, users: int, tasks: int, whisper_enabled: bool) -> str:
    """Format system statistics for Telegram."""
    lines = [
        "🖥 <b>System Statistics</b>\n",
        f"⏱ <b>Uptime:</b> {uptime_str}",
        f"💾 <b>RAM:</b> {ram_mb:.0f} MB",
        f"👥 <b>Users:</b> {users}",
        f"📋 <b>Tasks:</b> {tasks}",
        f"🎙 <b>Whisper:</b> {'enabled' if whisper_enabled else 'disabled'}",
    ]
    return "\n".join(lines)
