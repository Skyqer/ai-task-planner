"""FSM states for Telegram bot."""

from aiogram.fsm.state import State, StatesGroup

class VoiceInputState(StatesGroup):
    """State for voice message processing."""
    waiting_for_confirmation = State()
