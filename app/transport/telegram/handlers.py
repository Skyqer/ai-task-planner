"""Telegram message and command handlers."""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository as repo
from app.transport.telegram.states import VoiceInputState
from app.transport.telegram.formatter import (
    format_planner_response,
    format_task_list,
    format_timeline,
    format_recurrence_list,
    format_stats,
    get_main_keyboard,
    get_tasks_keyboard,
    get_recurrences_keyboard,
)
from app.transport.telegram.callbacks import (
    TaskActionCallback,
    ReminderAckCallback,
    VoiceConfirmCallback,
    RecurrenceActionCallback,
    RescheduleActionCallback,
)

logger = logging.getLogger(__name__)
router = Router()


# ── Commands ─────────────────────────────────────────────────────────────────


@router.message(Command("start"))
async def cmd_start(message: types.Message, session: AsyncSession, constraint_service=None) -> None:
    """Welcome message + user registration."""
    if not message.from_user:
        return

    await repo.get_or_create_user(
        session,
        user_id=message.from_user.id,
        username=message.from_user.username,
    )
    # Create default constraints if none exist
    if constraint_service:
        await constraint_service.ensure_defaults(session, message.from_user.id)

    await message.answer(
        "👋 Привет! Я — твой AI-планировщик задач.\n\n"
        "Просто напиши или отправь голосовое сообщение о том, что нужно сделать, и я разберу это в задачи.\n\n"
        "Вы можете использовать кнопки внизу или отправлять команды.",
        reply_markup=get_main_keyboard(),
    )


@router.message(Command("tasks"))
async def cmd_tasks(message: types.Message, session: AsyncSession) -> None:
    """List active tasks."""
    if not message.from_user:
        return

    tasks = await repo.get_active_tasks(session, message.from_user.id)

    if not tasks:
        await message.answer("📋 Нет активных задач.")
        return

    text = format_task_list(tasks)
    await message.answer(text, reply_markup=get_tasks_keyboard(tasks))


@router.message(Command("done"))
async def cmd_done(message: types.Message, session: AsyncSession) -> None:
    """Mark a task as completed. Usage: /done <task_number>"""
    if not message.from_user:
        return

    await _change_task_status(message, session, "completed")


@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, session: AsyncSession) -> None:
    """Cancel a task. Usage: /cancel <task_number>"""
    if not message.from_user:
        return

    await _change_task_status(message, session, "cancelled")


@router.message(Command("delete"))
async def cmd_delete(message: types.Message, session: AsyncSession) -> None:
    """Soft-delete a task. Usage: /delete <task_number>"""
    if not message.from_user:
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("Использование: /delete [номер задачи]")
        return

    idx = int(args[1].strip()) - 1
    tasks = await repo.get_active_tasks(session, message.from_user.id)
    if idx < 0 or idx >= len(tasks):
        await message.answer(f"Нет задачи с номером {idx + 1}.")
        return

    task = tasks[idx]
    await repo.soft_delete_task(session, task.id)
    await message.answer(f"🗑 Удалена: {task.title}")


@router.message(Command("morning"))
async def cmd_morning(message: types.Message, session: AsyncSession, planner=None) -> None:
    """Trigger morning briefing manually."""
    if not message.from_user:
        return

    if not planner:
        await message.answer("⚠️ Планировщик не инициализирован.")
        return

    response = await planner.process_message(
        session, message.from_user.id, "проснулся"
    )

    text = format_planner_response(response)
    await message.answer(text, reply_markup=get_main_keyboard())


@router.message(Command("timeline"))
async def cmd_timeline(message: types.Message, session: AsyncSession, timeline=None) -> None:
    """Show day timeline / schedule."""
    if not message.from_user:
        return

    if not timeline:
        await message.answer("⚠️ Timeline Engine не инициализирован.")
        return

    day_timeline = await timeline.build_day(session, message.from_user.id)

    text = format_timeline(day_timeline)
    await message.answer(text, reply_markup=get_main_keyboard())


@router.message(Command("recurring"))
async def cmd_recurring(message: types.Message, session: AsyncSession) -> None:
    """Show and manage recurring tasks."""
    if not message.from_user:
        return

    recurrences = await repo.get_active_recurrences(session, message.from_user.id)

    text = format_recurrence_list(recurrences)
    markup = get_recurrences_keyboard(recurrences)
    await message.answer(text, reply_markup=markup)


@router.message(Command("stats"))
async def cmd_stats(message: types.Message, session: AsyncSession) -> None:
    """Show user statistics."""
    if not message.from_user:
        return

    from app.services.statistics import StatisticsService
    stats_service = StatisticsService()
    
    args = (message.text or "").split()
    period = "all_time"
    if len(args) > 1 and args[1] in ("today", "week", "month"):
        period = args[1]
        
    stats = await stats_service.get_stats(session, message.from_user.id, period)

    text = format_stats(stats)
    await message.answer(text, reply_markup=get_main_keyboard())


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    """Show list of all available commands."""
    help_text = (
        "📖 <b>Доступные команды</b>\n\n"
        "/start — Регистрация + приветствие\n"
        "/tasks — Список активных задач с inline-кнопками\n"
        "/done &lt;номер&gt; — Отметить задачу как выполненную\n"
        "/cancel &lt;номер&gt; — Отменить задачу\n"
        "/delete &lt;номер&gt; — Удалить задачу\n"
        "/morning — Утренняя сводка (погода + план дня)\n"
        "/timeline — Расписание дня (блокировки + свободные окна)\n"
        "/recurring — Управление регулярными задачами\n"
        "/stats — Статистика (today / week / month / all_time)\n"
        "/help — Показать это сообщение\n\n"
        "💡 Также вы можете просто написать текстом или отправить голосовое сообщение о том, что нужно сделать, "
        "и AI-планировщик разберёт это в задачи."
    )
    await message.answer(help_text, reply_markup=get_main_keyboard())


# ── Voice Handler ────────────────────────────────────────────────────────────


@router.message(F.voice)
async def handle_voice(message: types.Message, session: AsyncSession, state: FSMContext, voice=None, planner=None) -> None:
    """Handle voice messages — transcribe and pipe through planner."""
    if not message.from_user or not message.voice:
        return

    if not voice:
        await message.answer("⚠️ Голосовой ввод не поддерживается (модель не загружена).")
        return

    await message.answer("🎤 Распознаю голосовое сообщение...")

    bot = message.bot
    if not bot:
        return

    try:
        file = await bot.get_file(message.voice.file_id)
        if not file or not file.file_path:
            await message.answer("❌ Не удалось загрузить голосовое сообщение.")
            return

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            await bot.download_file(file.file_path, destination=tmp)

        result = await voice.transcribe(tmp_path)
        tmp_path.unlink(missing_ok=True)

        if not result.text:
            await message.answer("❌ Не удалось распознать голосовое сообщение. Попробуйте ещё раз.")
            return

        lang_label = {"ru": "🇷🇺", "uk": "🇺🇦", "en": "🇬🇧"}.get(result.language, "🌐")

        if result.low_confidence:
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            builder = InlineKeyboardBuilder()
            builder.button(
                text="✅ Да, верно",
                callback_data=VoiceConfirmCallback(
                    action="confirm", user_id=message.from_user.id, msg_id=message.message_id
                ).pack(),
            )
            builder.button(
                text="❌ Нет, введу текстом",
                callback_data=VoiceConfirmCallback(
                    action="reject", user_id=message.from_user.id, msg_id=message.message_id
                ).pack(),
            )
            builder.adjust(2)

            # Store the text in FSM state
            await state.set_state(VoiceInputState.waiting_for_confirmation)
            await state.update_data(transcribed_text=result.text)

            await message.answer(
                f"🎤 Распознано {lang_label} (уверенность: {result.confidence:.0%}):\n\n"
                f"<i>{result.text}</i>\n\n"
                f"Это правильно?",
                reply_markup=builder.as_markup(),
            )
            return

        await message.answer(f"🎤 Распознано {lang_label}:\n<i>{result.text}</i>")

        if planner:
            response = await planner.process_message(session, message.from_user.id, result.text)
            text = format_planner_response(response)
            await message.answer(text, reply_markup=get_main_keyboard())

    except Exception as exc:
        logger.error("Voice processing failed: %s", exc)
        await message.answer("❌ Ошибка обработки голосового сообщения.")


@router.callback_query(VoiceConfirmCallback.filter())
async def handle_voice_confirm(
    callback: types.CallbackQuery, 
    callback_data: VoiceConfirmCallback, 
    session: AsyncSession, 
    state: FSMContext, 
    planner=None
) -> None:
    """Handle voice transcription confirmation."""
    if not callback.message:
        return

    if callback_data.action == "reject":
        await state.clear()
        await callback.answer("Хорошо, введите текст вручную.")
        try:
            await callback.message.edit_text(callback.message.text + "\n\n❌ <b>Отклонено</b>")
        except Exception:
            pass
        return

    # User confirmed
    data = await state.get_data()
    text = data.get("transcribed_text")
    await state.clear()

    if not text:
        await callback.answer("Текст не найден, попробуйте отправить заново.", show_alert=True)
        try:
            await callback.message.edit_text(callback.message.text + "\n\n❌ <b>Текст не найден</b>")
        except Exception:
            pass
        return

    await callback.answer()
    try:
        await callback.message.edit_text(callback.message.text + "\n\n⏳ <b>Обрабатываю...</b>")
    except Exception:
        pass

    if planner:
        response = await planner.process_message(session, callback.from_user.id, text)
        reply = format_planner_response(response)
        try:
            new_text = callback.message.text.replace("⏳ Обрабатываю...", reply)
            if new_text == callback.message.text:
                new_text = callback.message.text + f"\n\n{reply}"
            await callback.message.edit_text(new_text)
        except Exception:
            await callback.message.answer(reply, reply_markup=get_main_keyboard())


# ── Callback Handlers ────────────────────────────────────────────────────────


@router.callback_query(TaskActionCallback.filter())
async def handle_task_action(
    callback: types.CallbackQuery, callback_data: TaskActionCallback, session: AsyncSession
) -> None:
    """Handle inline button clicks for tasks."""
    if not callback.message:
        return

    try:
        task_uuid = uuid.UUID(callback_data.task_id)
    except ValueError:
        await callback.answer("Ошибка: неверный ID задачи.")
        return

    if callback_data.action == "done":
        from app.services.dependencies import DependencyService
        dep_service = DependencyService()
        if not await dep_service.can_complete(session, task_uuid):
            await callback.answer("⏳ Сначала завершите предыдущие задачи!", show_alert=True)
            return
            
        from app.models.task import TaskORM
        from datetime import datetime, timezone
        task = await session.get(TaskORM, task_uuid)
        await repo.mark_completed(session, task_uuid)
        if task:
            await repo.log_task_completion(
                session,
                callback.from_user.id,
                task_uuid,
                task.type.value if task.type else "other",
                datetime.now(timezone.utc)
            )
        await callback.answer("✅ Выполнено!")
    elif callback_data.action == "delete":
        await repo.soft_delete_task(session, task_uuid)
        await callback.answer("🗑 Удалено.")

    tasks = await repo.get_active_tasks(session, callback.fromuser_id if hasattr(callback, 'fromuser_id') else callback.from_user.id)
    text = format_task_list(tasks)
    markup = get_tasks_keyboard(tasks)

    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        pass


@router.callback_query(ReminderAckCallback.filter())
async def handle_reminder_ack(
    callback: types.CallbackQuery, callback_data: ReminderAckCallback, session: AsyncSession
) -> None:
    """Handle reminder acknowledge button."""
    if not callback.message:
        return

    try:
        reminder_uuid = uuid.UUID(callback_data.reminder_id)
    except ValueError:
        await callback.answer("Ошибка: неверный ID.")
        return

    reminder = await repo.acknowledge_reminder(session, reminder_uuid)

    if reminder:
        await callback.answer("✅ Подтверждено!")
        try:
            await callback.message.edit_text(
                callback.message.text + "\n\n✅ <b>Подтверждено</b>",
            )
        except Exception:
            pass
    else:
        await callback.answer("Напоминание не найдено.")


@router.callback_query(RecurrenceActionCallback.filter())
async def handle_recurrence_action(
    callback: types.CallbackQuery, callback_data: RecurrenceActionCallback, session: AsyncSession
) -> None:
    """Handle inline button clicks for recurrences."""
    if not callback.message:
        return

    try:
        recur_uuid = uuid.UUID(callback_data.recur_id)
    except ValueError:
        await callback.answer("Ошибка: неверный ID.")
        return

    if callback_data.action == "cancel":
        success = await repo.cancel_recurrence(session, recur_uuid)
        if success:
            await callback.answer("❌ Регулярная задача отменена.")
        else:
            await callback.answer("Задача не найдена.")

    recurrences = await repo.get_active_recurrences(session, callback.from_user.id)
    text = format_recurrence_list(recurrences)
    markup = get_recurrences_keyboard(recurrences)

    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        pass


@router.callback_query(RescheduleActionCallback.filter())
async def handle_reschedule_action(
    callback: types.CallbackQuery, callback_data: RescheduleActionCallback, session: AsyncSession, timeline=None
) -> None:
    """Handle inline button clicks for rescheduling."""
    if not callback.message:
        return
        
    if callback_data.action == "dismiss":
        await callback.answer("Оставил без изменений.")
        try:
            await callback.message.edit_text(callback.message.text + "\n\n❌ <b>Оставлено без изменений</b>")
        except Exception:
            pass
        return
        
    from datetime import datetime
    try:
        new_time = datetime.fromisoformat(callback_data.new_time)
    except ValueError:
        await callback.answer("Ошибка: неверный формат времени.")
        return
        
    from app.services.rescheduler import ReschedulerService
    if not timeline:
        await callback.answer("Ошибка: Timeline не инициализирован.")
        return
        
    rescheduler = ReschedulerService(timeline)
    success = await rescheduler.apply_suggestion(session, callback_data.task_id, new_time)
        
    if success:
        await callback.answer("✅ Задача перенесена!")
        try:
            await callback.message.edit_text(callback.message.text + "\n\n✅ <b>Перенесено</b>")
        except Exception:
            pass
    else:
        await callback.answer("Ошибка: не удалось перенести задачу.")


# ── Text Handler (catch-all, must be last) ───────────────────────────────────


@router.message()
async def handle_text(message: types.Message, session: AsyncSession, planner=None, timeline=None) -> None:
    """Handle any text message — pass to core planner."""
    if not message.from_user or not message.text:
        return

    text_val = message.text.strip()
    # Call appropriate commands instead of redefining logic
    if text_val == "📋 Мои задачи":
        await cmd_tasks(message, session)
        return
    if text_val == "🌅 Мой день":
        await cmd_morning(message, session, planner)
        return
    if text_val == "📅 Расписание":
        await cmd_timeline(message, session, timeline)
        return
    if text_val == "🔄 Регулярные":
        await cmd_recurring(message, session)
        return
    if text_val == "📊 Статистика":
        await cmd_stats(message, session)
        return
    if text_val == "❓ Помощь":
        await cmd_help(message)
        return

    if not planner:
        await message.answer("⚠️ Планировщик не инициализирован.")
        return

    response = await planner.process_message(
        session, message.from_user.id, message.text
    )

    text = format_planner_response(response)
    await message.answer(text, reply_markup=get_main_keyboard())


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _change_task_status(message: types.Message, session: AsyncSession, action: str) -> None:
    """Helper to complete or cancel a task by number."""
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(f"Использование: /{action.split('_')[0]} [номер задачи]")
        return

    idx = int(args[1].strip()) - 1
    tasks = await repo.get_active_tasks(session, message.from_user.id)
    if idx < 0 or idx >= len(tasks):
        await message.answer(f"Нет задачи с номером {idx + 1}.")
        return

    task = tasks[idx]
    if action == "completed":
        from app.services.dependencies import DependencyService
        dep_service = DependencyService()
        if not await dep_service.can_complete(session, task.id):
            await message.answer(f"⏳ Невозможно завершить '{task.title}'. Сначала выполните предыдущие задачи!")
            return
            
        await repo.mark_completed(session, task.id)
        from datetime import datetime, timezone
        await repo.log_task_completion(
            session,
            message.from_user.id,
            task.id,
            task.type.value if task.type else "other",
            datetime.now(timezone.utc)
        )
        await message.answer(f"✅ Завершена: {task.title}")
    else:
        await repo.mark_cancelled(session, task.id)
        await message.answer(f"❌ Отменена: {task.title}")
