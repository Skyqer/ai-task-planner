"""CallbackData schemas for inline keyboards."""

from aiogram.filters.callback_data import CallbackData

class TaskActionCallback(CallbackData, prefix="task"):
    action: str  # "done", "cancel", "delete"
    task_id: str
