"""Telegram message and command handlers."""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path

from aiogram import F, Router, types
from aiogram.filters import Command

from app.db.engine import async_session_factory
from app.db import repository as repo
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

# Injected at startup via set_planner / set_services
_planner = None
_timeline_engine = None
_voice_service = None
_constraint_service = None

# Temporary store for pending voice confirmations {user_id: transcribed_text}
_pending_voice: dict[int, str] = {}


def set_planner(planner) -> None:
    """Inject the core planner instance."""
    global _planner
    _planner = planner


def set_services(timeline=None, voice=None, constraints=None) -> None:
    """Inject additional services."""
    global _timeline_engine, _voice_service, _constraint_service
    if timeline:
        _timeline_engine = timeline
    if voice:
        _voice_service = voice
    if constraints:
        _constraint_service = constraints


# ── Commands ─────────────────────────────────────────────────────────────────


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
        # Create default constraints if none exist
        if _constraint_service:
            await _constraint_service.ensure_defaults(session, message.from_user.id)

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
    await message.answer(text, reply_markup=get_main_keyboard())


@router.message(Command("timeline"))
async def cmd_timeline(message: types.Message) -> None:
    """Show day timeline / schedule."""
    if not message.from_user:
        return

    if not _timeline_engine:
        await message.answer("⚠️ Timeline Engine не инициализирован.")
        return

    async with async_session_factory() as session:
        timeline = await _timeline_engine.build_day(session, message.from_user.id)

    text = format_timeline(timeline)
    await message.answer(text, reply_markup=get_main_keyboard())


@router.message(Command("recurring"))
async def cmd_recurring(message: types.Message) -> None:
    """Show and manage recurring tasks."""
    if not message.from_user:
        return

    async with async_session_factory() as session:
        recurrences = await repo.get_active_recurrences(session, message.from_user.id)

    text = format_recurrence_list(recurrences)
    markup = get_recurrences_keyboard(recurrences)
    await message.answer(text, reply_markup=markup)


@router.message(Command("stats"))
async def cmd_stats(message: types.Message) -> None:
    """Show user statistics."""
    if not message.from_user:
        return

    from app.services.statistics import StatisticsService
    stats_service = StatisticsService()
    
    # We could parse args for period, but default to 'all_time' for now
    args = (message.text or "").split()
    period = "all_time"
    if len(args) > 1 and args[1] in ("today", "week", "month"):
        period = args[1]
        
    async with async_session_factory() as session:
        stats = await stats_service.get_stats(session, message.from_user.id, period)

    text = format_stats(stats)
    await message.answer(text, reply_markup=get_main_keyboard())


# ── Voice Handler ────────────────────────────────────────────────────────────


@router.message(F.voice)
async def handle_voice(message: types.Message) -> None:
    """Handle voice messages — transcribe and pipe through planner."""
    if not message.from_user or not message.voice:
        return

    if not _voice_service:
        await message.answer("⚠️ Голосовой ввод не поддерживается (модель не загружена).")
        return

    # Show typing indicator
    await message.answer("🎤 Распознаю голосовое сообщение...")

    bot = message.bot
    if not bot:
        return

    # Download voice file
    try:
        file = await bot.get_file(message.voice.file_id)
        if not file or not file.file_path:
            await message.answer("❌ Не удалось загрузить голосовое сообщение.")
            return

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            await bot.download_file(file.file_path, destination=tmp)

        # Transcribe
        result = await _voice_service.transcribe(tmp_path)

        # Clean up
        tmp_path.unlink(missing_ok=True)

        if not result.text:
            await message.answer("❌ Не удалось распознать голосовое сообщение. Попробуйте ещё раз.")
            return

        if result.low_confidence:
            # Ask user to confirm
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            builder = InlineKeyboardBuilder()
            builder.button(
                text="✅ Да, верно",
                callback_data=VoiceConfirmCallback(
                    action="confirm", user_id=message.from_user.id
                ).pack(),
            )
            builder.button(
                text="❌ Нет, введу текстом",
                callback_data=VoiceConfirmCallback(
                    action="reject", user_id=message.from_user.id
                ).pack(),
            )
            builder.adjust(2)

            _pending_voice[message.from_user.id] = result.text

            lang_label = {"ru": "🇷🇺", "uk": "🇺🇦", "en": "🇬🇧"}.get(result.language, "🌐")
            await message.answer(
                f"🎤 Распознано {lang_label} (уверенность: {result.confidence:.0%}):\n\n"
                f"<i>{result.text}</i>\n\n"
                f"Это правильно?",
                reply_markup=builder.as_markup(),
            )
            return

        # High confidence — process immediately
        lang_label = {"ru": "🇷🇺", "uk": "🇺🇦", "en": "🇬🇧"}.get(result.language, "🌐")
        await message.answer(
            f"🎤 Распознано {lang_label}:\n<i>{result.text}</i>"
        )

        if _planner:
            async with async_session_factory() as session:
                response = await _planner.process_message(
                    session, message.from_user.id, result.text
                )
            text = format_planner_response(response)
            await message.answer(text, reply_markup=get_main_keyboard())

    except Exception as exc:
        logger.error("Voice processing failed: %s", exc)
        await message.answer("❌ Ошибка обработки голосового сообщения.")


# ── Callback Handlers ────────────────────────────────────────────────────────


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

        # Refresh active tasks for the user
        tasks = await repo.get_active_tasks(session, callback.from_user.id)

    text = format_task_list(tasks)
    markup = get_tasks_keyboard(tasks)

    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        pass  # Message content might be identical


@router.callback_query(ReminderAckCallback.filter())
async def handle_reminder_ack(
    callback: types.CallbackQuery, callback_data: ReminderAckCallback
) -> None:
    """Handle reminder acknowledge button."""
    if not callback.message:
        return

    try:
        reminder_uuid = uuid.UUID(callback_data.reminder_id)
    except ValueError:
        await callback.answer("Ошибка: неверный ID.")
        return

    async with async_session_factory() as session:
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


@router.callback_query(VoiceConfirmCallback.filter())
async def handle_voice_confirm(
    callback: types.CallbackQuery, callback_data: VoiceConfirmCallback
) -> None:
    """Handle voice transcription confirmation."""
    if not callback.message:
        return

    user_id = callback_data.user_id

    if callback_data.action == "reject":
        _pending_voice.pop(user_id, None)
        await callback.answer("Хорошо, введите текст вручную.")
        try:
            await callback.message.edit_text(
                callback.message.text + "\n\n❌ <b>Отклонено</b>",
            )
        except Exception:
            pass
        return

    # Confirm — process the pending text
    text = _pending_voice.pop(user_id, None)
    if not text:
        await callback.answer("Текст не найден, попробуйте ещё раз.")
        return

    await callback.answer("Обрабатываю...")

    if _planner:
        async with async_session_factory() as session:
            response = await _planner.process_message(session, user_id, text)

        reply = format_planner_response(response)
        try:
            await callback.message.edit_text(
                callback.message.text + f"\n\n{reply}",
            )
        except Exception:
            await callback.message.answer(reply, reply_markup=get_main_keyboard())


@router.callback_query(RecurrenceActionCallback.filter())
async def handle_recurrence_action(
    callback: types.CallbackQuery, callback_data: RecurrenceActionCallback
) -> None:
    """Handle inline button clicks for recurrences."""
    if not callback.message:
        return

    try:
        recur_uuid = uuid.UUID(callback_data.recur_id)
    except ValueError:
        await callback.answer("Ошибка: неверный ID.")
        return

    async with async_session_factory() as session:
        if callback_data.action == "cancel":
            success = await repo.cancel_recurrence(session, recur_uuid)
            if success:
                await callback.answer("❌ Регулярная задача отменена.")
            else:
                await callback.answer("Задача не найдена.")

        # Refresh list
        recurrences = await repo.get_active_recurrences(session, callback.from_user.id)

    text = format_recurrence_list(recurrences)
    markup = get_recurrences_keyboard(recurrences)

    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        pass


@router.callback_query(RescheduleActionCallback.filter())
async def handle_reschedule_action(
    callback: types.CallbackQuery, callback_data: RescheduleActionCallback
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
        
    # Accept action
    from datetime import datetime
    try:
        new_time = datetime.fromisoformat(callback_data.new_time)
    except ValueError:
        await callback.answer("Ошибка: неверный формат времени.")
        return
        
    async with async_session_factory() as session:
        # We need rescheduler service here. It's stored in _services if we injected it.
        # But wait, we didn't inject rescheduler into handlers! Let's just instantiate or get it.
        # It's better to just write the logic here or inject it.
        # To avoid importing main here, we can use the ReschedulerService directly if we pass timeline.
        # But timeline is already `_timeline_engine`.
        from app.services.rescheduler import ReschedulerService
        if not _timeline_engine:
            await callback.answer("Ошибка: Timeline не инициализирован.")
            return
            
        rescheduler = ReschedulerService(_timeline_engine)
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
    if text_val == "📅 Расписание":
        await cmd_timeline(message)
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


# ── Helpers ──────────────────────────────────────────────────────────────────


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
