"""Format PlannerResponse into Telegram-friendly text."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.schemas.planner import PlannerResponseSchema
from app.transport.telegram.callbacks import TaskActionCallback

# Priority emoji mapping
_PRIORITY_EMOJI = {
    1: "⚪",
    2: "🟢",
    3: "🟡",
    4: "🟠",
    5: "🔴",
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


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Get the persistent main menu keyboard."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 Мои задачи")
    builder.button(text="🌅 Мой день")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True, persistent=True)


def get_tasks_keyboard(tasks) -> InlineKeyboardMarkup | None:
    """Get an inline keyboard for task actions."""
    if not tasks:
        return None

    builder = InlineKeyboardBuilder()
    for i, task in enumerate(tasks, 1):
        # We use short UUIDs or just the full UUID if it fits (callback data limit is 64 bytes)
        # We will use TaskActionCallback
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
