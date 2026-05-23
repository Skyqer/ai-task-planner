"""ORM model for tracking task completions for routine learning."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class TaskCompletionLogORM(Base, UUIDMixin):
    """Log of when tasks were completed, used for learning routines."""

    __tablename__ = "task_completion_logs"

    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    task_type: Mapped[str] = mapped_column(String(50))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    time_of_day_minutes: Mapped[int] = mapped_column(
        doc="Minutes since midnight when the task was completed"
    )
