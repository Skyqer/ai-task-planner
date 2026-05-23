"""CallbackData schemas for inline keyboards."""

from aiogram.filters.callback_data import CallbackData


class TaskActionCallback(CallbackData, prefix="task"):
    action: str  # "done", "cancel", "delete"
    task_id: str


class ReminderAckCallback(CallbackData, prefix="remind"):
    reminder_id: str


class VoiceConfirmCallback(CallbackData, prefix="voice"):
    action: str  # "confirm", "reject"
    user_id: int


class RecurrenceActionCallback(CallbackData, prefix="recur"):
    action: str  # "cancel"
    recur_id: str


class RescheduleActionCallback(CallbackData, prefix="resched"):
    action: str  # "accept", "dismiss"
    task_id: str
    new_time: str = ""
