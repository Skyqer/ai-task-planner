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
        "👋 Hello! I am your AI task planner.\n\n"
        "Just write or send a voice message about what needs to be done, and I will break it down into tasks.\n\n"
        "You can use the buttons below or send commands.",
        reply_markup=get_main_keyboard(),
    )


@router.message(Command("tasks"))
async def cmd_tasks(message: types.Message, session: AsyncSession) -> None:
    """List active tasks."""
    if not message.from_user:
        return

    tasks = await repo.get_active_tasks(session, message.from_user.id)

    if not tasks:
        await message.answer("📋 No active tasks.")
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
        await message.answer("Usage: /delete [task number]")
        return

    idx = int(args[1].strip()) - 1
    tasks = await repo.get_active_tasks(session, message.from_user.id)
    if idx < 0 or idx >= len(tasks):
        await message.answer(f"No task with number {idx + 1}.")
        return

    task = tasks[idx]
    await repo.soft_delete_task(session, task.id)
    await message.answer(f"🗑 Deleted: {task.title}")


@router.message(Command("morning"))
async def cmd_morning(message: types.Message, session: AsyncSession, planner=None) -> None:
    """Trigger morning briefing manually."""
    if not message.from_user:
        return

    if not planner:
        await message.answer("⚠️ Planner is not initialized.")
        return

    response = await planner.process_message(
        session, message.from_user.id, "woke up"
    )

    text = format_planner_response(response)
    await message.answer(text, reply_markup=get_main_keyboard())


@router.message(Command("timeline"))
async def cmd_timeline(message: types.Message, session: AsyncSession, timeline=None) -> None:
    """Show day timeline / schedule."""
    if not message.from_user:
        return

    if not timeline:
        await message.answer("⚠️ Timeline Engine is not initialized.")
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
        "📖 <b>Available commands</b>\n\n"
        "/start — Registration + welcome\n"
        "/tasks — Active tasks list with inline buttons\n"
        "/done &lt;номер&gt; — Mark task as completed\n"
        "/cancel &lt;номер&gt; — Cancel task\n"
        "/delete &lt;номер&gt; — Delete task\n"
        "/morning — Morning brief (weather + day plan)\n"
        "/timeline — Day schedule (constraints + free windows)\n"
        "/recurring — Manage recurring tasks\n"
        "/stats — Statistics (today / week / month / all_time)\n"
        "/help — Show this message\n\n"
        "💡 You can also just write text or send a voice message about what needs to be done, "
        "and the AI planner will break it down into tasks."
    )
    await message.answer(help_text, reply_markup=get_main_keyboard())


# ── Voice Handler ────────────────────────────────────────────────────────────


@router.message(F.voice)
async def handle_voice(message: types.Message, session: AsyncSession, state: FSMContext, voice=None, planner=None) -> None:
    """Handle voice messages — transcribe and pipe through planner."""
    if not message.from_user or not message.voice:
        return

    if not voice:
        await message.answer("⚠️ Voice input is not supported (model not loaded).")
        return

    await message.answer("🎤 Recognizing voice message...")

    bot = message.bot
    if not bot:
        return

    try:
        file = await bot.get_file(message.voice.file_id)
        if not file or not file.file_path:
            await message.answer("❌ Failed to download voice message.")
            return

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            await bot.download_file(file.file_path, destination=tmp)

        result = await voice.transcribe(tmp_path)
        tmp_path.unlink(missing_ok=True)

        if not result.text:
            await message.answer("❌ Failed to recognize voice message. Please try again.")
            return

        lang_label = {"ru": "🇷🇺", "uk": "🇺🇦", "en": "🇬🇧"}.get(result.language, "🌐")

        if result.low_confidence:
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            builder = InlineKeyboardBuilder()
            builder.button(
                text="✅ Yes, correct",
                callback_data=VoiceConfirmCallback(
                    action="confirm", user_id=message.from_user.id, msg_id=message.message_id
                ).pack(),
            )
            builder.button(
                text="❌ No, I will type",
                callback_data=VoiceConfirmCallback(
                    action="reject", user_id=message.from_user.id, msg_id=message.message_id
                ).pack(),
            )
            builder.adjust(2)

            # Store the text in FSM state
            await state.set_state(VoiceInputState.waiting_for_confirmation)
            await state.update_data(transcribed_text=result.text)

            await message.answer(
                f"🎤 Recognized {lang_label} (confidence: {result.confidence:.0%}):\n\n"
                f"<i>{result.text}</i>\n\n"
                f"Is this correct?",
                reply_markup=builder.as_markup(),
            )
            return

        await message.answer(f"🎤 Recognized {lang_label}:\n<i>{result.text}</i>")

        if planner:
            response = await planner.process_message(session, message.from_user.id, result.text)
            text = format_planner_response(response)
            await message.answer(text, reply_markup=get_main_keyboard())

    except Exception as exc:
        logger.error("Voice processing failed: %s", exc)
        await message.answer("❌ Voice processing error.")


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
        await callback.answer("Okay, type the text manually.")
        try:
            await callback.message.edit_text(callback.message.text + "\n\n❌ <b>Rejected</b>")
        except Exception:
            pass
        return

    # User confirmed
    data = await state.get_data()
    text = data.get("transcribed_text")
    await state.clear()

    if not text:
        await callback.answer("Text not found, try sending again.", show_alert=True)
        try:
            await callback.message.edit_text(callback.message.text + "\n\n❌ <b>Text not found</b>")
        except Exception:
            pass
        return

    await callback.answer()
    try:
        await callback.message.edit_text(callback.message.text + "\n\n⏳ <b>Processing...</b>")
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
        await callback.answer("Error: invalid task ID.")
        return

    if callback_data.action == "done":
        from app.services.dependencies import DependencyService
        dep_service = DependencyService()
        if not await dep_service.can_complete(session, task_uuid):
            await callback.answer("⏳ First complete previous tasks!", show_alert=True)
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
        await callback.answer("✅ Completed!")
    elif callback_data.action == "delete":
        await repo.soft_delete_task(session, task_uuid)
        await callback.answer("🗑 Deleted.")

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
        await callback.answer("Error: invalid ID.")
        return

    reminder = await repo.acknowledge_reminder(session, reminder_uuid)

    if reminder:
        await callback.answer("✅ Confirmed!")
        try:
            await callback.message.edit_text(
                callback.message.text + "\n\n✅ <b>Confirmed</b>",
            )
        except Exception:
            pass
    else:
        await callback.answer("Reminder not found.")


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
        await callback.answer("Error: invalid ID.")
        return

    if callback_data.action == "cancel":
        success = await repo.cancel_recurrence(session, recur_uuid)
        if success:
            await callback.answer("❌ Recurring task cancelled.")
        else:
            await callback.answer("Task not found.")

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
        await callback.answer("Left unchanged.")
        try:
            await callback.message.edit_text(callback.message.text + "\n\n❌ <b>Left unchanged</b>")
        except Exception:
            pass
        return
        
    from datetime import datetime
    try:
        new_time = datetime.fromisoformat(callback_data.new_time)
    except ValueError:
        await callback.answer("Error: invalid time format.")
        return
        
    from app.services.rescheduler import ReschedulerService
    if not timeline:
        await callback.answer("Error: Timeline is not initialized.")
        return
        
    rescheduler = ReschedulerService(timeline)
    success = await rescheduler.apply_suggestion(session, callback_data.task_id, new_time)
        
    if success:
        await callback.answer("✅ Task rescheduled!")
        try:
            await callback.message.edit_text(callback.message.text + "\n\n✅ <b>Rescheduled</b>")
        except Exception:
            pass
    else:
        await callback.answer("Error: failed to reschedule task.")


# ── Text Handler (catch-all, must be last) ───────────────────────────────────


@router.message()
async def handle_text(message: types.Message, session: AsyncSession, planner=None, timeline=None) -> None:
    """Handle any text message — pass to core planner."""
    if not message.from_user or not message.text:
        return

    text_val = message.text.strip()
    # Call appropriate commands instead of redefining logic
    if text_val == "📋 My tasks":
        await cmd_tasks(message, session)
        return
    if text_val == "🌅 My day":
        await cmd_morning(message, session, planner)
        return
    if text_val == "📅 Schedule":
        await cmd_timeline(message, session, timeline)
        return
    if text_val == "🔄 Recurring":
        await cmd_recurring(message, session)
        return
    if text_val == "📊 Statistics":
        await cmd_stats(message, session)
        return
    if text_val == "❓ Help":
        await cmd_help(message)
        return

    if not planner:
        await message.answer("⚠️ Planner is not initialized.")
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
        await message.answer(f"Usage: /{action.split('_')[0]} [номер задачи]")
        return

    idx = int(args[1].strip()) - 1
    tasks = await repo.get_active_tasks(session, message.from_user.id)
    if idx < 0 or idx >= len(tasks):
        await message.answer(f"No task with number {idx + 1}.")
        return

    task = tasks[idx]
    if action == "completed":
        from app.services.dependencies import DependencyService
        dep_service = DependencyService()
        if not await dep_service.can_complete(session, task.id):
            await message.answer(f"⏳ Cannot complete '{task.title}'. First complete previous tasks!")
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
        await message.answer(f"✅ Completed: {task.title}")
    else:
        await repo.mark_cancelled(session, task.id)
        await message.answer(f"❌ Cancelled: {task.title}")
