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
                details.append(f"~{task.estimated_minutes} мин")
            if task.deadline and task.deadline.time:
                kind = "⏰" if task.deadline.kind and task.deadline.kind.value == "hard" else "🕐"
                details.append(f"{kind} до {task.deadline.time}")
            if task.deadline and task.deadline.date:
                details.append(f"📅 {task.deadline.date}")
            if task.fixed_time and task.fixed_time.time:
                details.append(f"📌 в {task.fixed_time.time}")
            if task.type:
                details.append(f"[{task.type.value}]")

            if details:
                line += f"\n   └ <i>{' · '.join(details)}</i>"
            task_lines.append(line)

        parts.append("\n".join(task_lines))

    # Schedule suggestions
    if response.schedule_suggestions:
        sug_lines = ["📋 <b>Рекомендации:</b>"]
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
        q_lines = ["❓ <b>Уточни:</b>"]
        for i, q in enumerate(response.clarification_questions, 1):
            q_lines.append(f"  {i}. {q}")
        parts.append("\n".join(q_lines))

    text = "\n\n".join(parts) if parts else "✅ Обработано."

    # Truncate if exceeds Telegram limit
    if len(text) > _TELEGRAM_MAX_LENGTH:
        text = text[: _TELEGRAM_MAX_LENGTH - 20] + "\n\n... (обрезано)"

    return text


def format_task_list(tasks) -> str:
    """Format a list of TaskORM objects for the /tasks command."""
    if not tasks:
        return "📋 Нет активных задач."

    lines = ["✨ <b>Ваши активные задачи</b>\n"]
    for i, task in enumerate(tasks, 1):
        emoji = _PRIORITY_EMOJI.get(task.priority, "⚪")
        line = f"{emoji} <b>{i}. {task.title}</b>"

        details = []
        if task.estimated_minutes:
            details.append(f"~{task.estimated_minutes} мин")
        if task.deadline_date:
            details.append(f"📅 {task.deadline_date}")
        if task.deadline_time:
            details.append(f"⏰ {task.deadline_time.strftime('%H:%M')}")
        if task.fixed_time_time:
            details.append(f"📌 {task.fixed_time_time.strftime('%H:%M')}")
        if task.status:
            details.append(f"[{task.status.value}]")

        if details:
            line += f"\n   └ <i>{' · '.join(details)}</i>\n"
        lines.append(line)

    return "\n".join(lines)


def format_timeline(timeline: DayTimelineSchema) -> str:
    """Format a day timeline for Telegram."""
    parts: list[str] = [f"📅 <b>Расписание на {timeline.date}</b>\n"]

    if timeline.blocks:
        for block in timeline.blocks:
            emoji = _BLOCK_TYPE_EMOJI.get(block.block_type, "📦")
            parts.append(f"  {emoji} {block.start} – {block.end}  <b>{block.label}</b>")
    else:
        parts.append("  Нет запланированных блоков.")

    if timeline.free_windows:
        parts.append("\n✨ <b>Свободные окна:</b>")
        for fw in timeline.free_windows:
            duration = fw.duration_minutes
            parts.append(f"  🟢 {fw.start} – {fw.end} ({duration} мин)")

    if timeline.warnings:
        parts.append("")
        for w in timeline.warnings:
            parts.append(w)

    if timeline.suggestions:
        parts.append("\n💡 <b>Рекомендации:</b>")
        for s in timeline.suggestions:
            parts.append(f"  • {s}")

    text = "\n".join(parts)
    if len(text) > _TELEGRAM_MAX_LENGTH:
        text = text[: _TELEGRAM_MAX_LENGTH - 20] + "\n\n... (обрезано)"
    return text


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Get the persistent main menu keyboard."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 Мои задачи")
    builder.button(text="🌅 Мой день")
    builder.button(text="📅 Расписание")
    builder.button(text="🔄 Регулярные")
    builder.button(text="📊 Статистика")
    builder.button(text="❓ Помощь")
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
        text="✅ Понял",
        callback_data=ReminderAckCallback(reminder_id=reminder_id).pack(),
    )
    return builder.as_markup()


def format_recurrence_list(recurrences) -> str:
    """Format a list of RecurrenceORM objects for the /recurring command."""
    if not recurrences:
        return "🔄 Нет активных повторяющихся задач."

    lines = ["🔄 <b>Ваши регулярные задачи</b>\n"]
    for i, rec in enumerate(recurrences, 1):
        task = rec.task
        emoji = _PRIORITY_EMOJI.get(task.priority, "⚪")
        line = f"{emoji} <b>{i}. {task.title}</b>"

        details = []
        details.append(f"повтор: {rec.pattern}")
        if rec.next_run:
            details.append(f"следующий запуск: {rec.next_run.strftime('%Y-%m-%d %H:%M')}")
        
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
            text=f"❌ Отменить {i}",
            callback_data=RecurrenceActionCallback(action="cancel", recur_id=str(rec.id)).pack(),
        )

    builder.adjust(2)
    return builder.as_markup()


def get_reschedule_keyboard(task_id: str, new_time_iso: str) -> InlineKeyboardMarkup:
    """Get an inline keyboard for rescheduling suggestions."""
    from app.transport.telegram.callbacks import RescheduleActionCallback
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Согласен",
        callback_data=RescheduleActionCallback(
            action="accept", 
            task_id=task_id, 
            new_time=new_time_iso[:20]  # truncate if needed to fit callback size limits
        ).pack(),
    )
    builder.button(
        text="❌ Оставить как есть",
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
        "today": "Сегодня",
        "week": "Неделя",
        "month": "Месяц",
        "all_time": "За всё время",
    }
    period_name = period_names.get(stats.period, stats.period)

    lines = [
        f"📊 <b>Ваша статистика ({period_name})</b>",
        "",
        f"✅ <b>Выполнено:</b> {stats.total_completed}",
        f"❌ <b>Отменено:</b> {stats.total_cancelled}",
        f"⏳ <b>Просрочено:</b> {stats.total_overdue}",
        f"🔥 <b>Серия (дней):</b> {stats.current_streak_days}",
    ]
    
    if stats.total_completed > 0:
        lines.append(f"⏱ <b>Среднее время на задачу:</b> {stats.avg_duration_minutes} мин")
        
        if stats.by_category:
            lines.append("")
            lines.append("🗂 <b>По категориям:</b>")
            for cat, count in sorted(stats.by_category.items(), key=lambda x: x[1], reverse=True):
                # map internal category names to human readable if needed
                from app.transport.telegram.formatter import _PRIORITY_EMOJI # reuse if needed, or just map
                cat_emoji = {"work": "💼", "study": "📚", "home": "🏠", "health": "💊", "sport": "🏋️", "errand": "🛒"}.get(cat, "📌")
                lines.append(f"  {cat_emoji} {cat.capitalize()}: {count}")

    return "\n".join(lines)
