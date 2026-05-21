"""Telegram message and command handlers."""

from __future__ import annotations

import logging
import uuid

from aiogram import Router, types
from aiogram.filters import Command

from app.db.engine import async_session_factory
from app.db import repository as repo
from app.transport.telegram.formatter import (
    format_planner_response,
    format_task_list,
    get_main_keyboard,
    get_tasks_keyboard,
)
from app.transport.telegram.callbacks import TaskActionCallback

logger = logging.getLogger(__name__)
router = Router()

# Core planner is injected at startup via set_planner
_planner = None


def set_planner(planner) -> None:
    """Inject the core planner instance."""
    global _planner
    _planner = planner


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    """Welcome message + user registration."""
    if not message.from_user:
        return

    async with async_session_factory() as session:
        await repo.get_or_create_user(
            session,
            user_id=message.from_user.id,
            username=message.from_user.username,
        )

    await message.answer(
        "👋 Привет! Я — твой AI-планировщик задач.\n\n"
        "Просто напиши, что нужно сделать, и я разберу это в задачи.\n\n"
        "Вы можете использовать кнопки внизу или отправлять команды.",
        reply_markup=get_main_keyboard(),
    )


@router.message(Command("tasks"))
async def cmd_tasks(message: types.Message) -> None:
    """List active tasks."""
    if not message.from_user:
        return

    async with async_session_factory() as session:
        tasks = await repo.get_active_tasks(session, message.from_user.id)

    if not tasks:
        await message.answer("📋 Нет активных задач.")
        return

    text = format_task_list(tasks)
    await message.answer(text, reply_markup=get_tasks_keyboard(tasks))


@router.message(Command("done"))
async def cmd_done(message: types.Message) -> None:
    """Mark a task as completed. Usage: /done <task_number>"""
    if not message.from_user:
        return

    await _change_task_status(message, "completed")


@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message) -> None:
    """Cancel a task. Usage: /cancel <task_number>"""
    if not message.from_user:
        return

    await _change_task_status(message, "cancelled")


@router.message(Command("delete"))
async def cmd_delete(message: types.Message) -> None:
    """Soft-delete a task. Usage: /delete <task_number>"""
    if not message.from_user:
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("Использование: /delete [номер задачи]")
        return

    idx = int(args[1].strip()) - 1
    async with async_session_factory() as session:
        tasks = await repo.get_active_tasks(session, message.from_user.id)
        if idx < 0 or idx >= len(tasks):
            await message.answer(f"Нет задачи с номером {idx + 1}.")
            return

        task = tasks[idx]
        await repo.soft_delete_task(session, task.id)
        await message.answer(f"🗑 Удалена: {task.title}")


@router.message(Command("morning"))
async def cmd_morning(message: types.Message) -> None:
    """Trigger morning briefing manually."""
    if not message.from_user:
        return

    if not _planner:
        await message.answer("⚠️ Планировщик не инициализирован.")
        return

    async with async_session_factory() as session:
        response = await _planner.process_message(
            session, message.from_user.id, "проснулся"
        )

    text = format_planner_response(response)
    await message.answer(text)


@router.message()
async def handle_text(message: types.Message) -> None:
    """Handle any text message — pass to core planner."""
    if not message.from_user or not message.text:
        return

    text_val = message.text.strip()
    if text_val == "📋 Мои задачи":
        await cmd_tasks(message)
        return
    if text_val == "🌅 Мой день":
        await cmd_morning(message)
        return

    if not _planner:
        await message.answer("⚠️ Планировщик не инициализирован.")
        return

    async with async_session_factory() as session:
        response = await _planner.process_message(
            session, message.from_user.id, message.text
        )

    text = format_planner_response(response)
    await message.answer(text, reply_markup=get_main_keyboard())


@router.callback_query(TaskActionCallback.filter())
async def handle_task_action(
    callback: types.CallbackQuery, callback_data: TaskActionCallback
) -> None:
    """Handle inline button clicks for tasks."""
    if not callback.message:
        return

    try:
        task_uuid = uuid.UUID(callback_data.task_id)
    except ValueError:
        await callback.answer("Ошибка: неверный ID задачи.")
        return

    async with async_session_factory() as session:
        if callback_data.action == "done":
            await repo.mark_completed(session, task_uuid)
            await callback.answer("✅ Выполнено!")
        elif callback_data.action == "delete":
            await repo.soft_delete_task(session, task_uuid)
            await callback.answer("🗑 Удалено.")

        # Refresh active tasks for the user
        tasks = await repo.get_active_tasks(session, callback.from_user.id)

    text = format_task_list(tasks)
    markup = get_tasks_keyboard(tasks)

    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        pass  # Message content might be identical


async def _change_task_status(message: types.Message, action: str) -> None:
    """Helper to complete or cancel a task by number."""
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(f"Использование: /{action.split('_')[0]} [номер задачи]")
        return

    idx = int(args[1].strip()) - 1
    async with async_session_factory() as session:
        tasks = await repo.get_active_tasks(session, message.from_user.id)
        if idx < 0 or idx >= len(tasks):
            await message.answer(f"Нет задачи с номером {idx + 1}.")
            return

        task = tasks[idx]
        if action == "completed":
            await repo.mark_completed(session, task.id)
            await message.answer(f"✅ Завершена: {task.title}")
        else:
            await repo.mark_cancelled(session, task.id)
            await message.answer(f"❌ Отменена: {task.title}")
