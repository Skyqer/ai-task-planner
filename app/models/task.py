"""Task and Recurrence ORM models."""

import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class TaskType(str, enum.Enum):
    STUDY = "study"
    HOME = "home"
    HEALTH = "health"
    ERRAND = "errand"
    SPORT = "sport"
    WORK = "work"
    OTHER = "other"


class TaskStatus(str, enum.Enum):
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DeadlineKind(str, enum.Enum):
    HARD = "hard"
    SOFT = "soft"


class TaskORM(Base, UUIDMixin, TimestampMixin):
    """Main task model with full lifecycle support."""

    __tablename__ = "tasks"

    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    title: Mapped[str] = mapped_column(String(500))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    type: Mapped[TaskType] = mapped_column(
        Enum(TaskType, name="task_type"),
        default=TaskType.OTHER,
    )
    priority: Mapped[int] = mapped_column(SmallInteger, default=2)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=30)

    # Deadline
    deadline_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline_time: Mapped[time | None] = mapped_column(
        Time(timezone=True), nullable=True
    )
    deadline_kind: Mapped[DeadlineKind | None] = mapped_column(
        Enum(DeadlineKind, name="deadline_kind"), nullable=True
    )

    # Fixed time (hard-scheduled events)
    fixed_time_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fixed_time_time: Mapped[time | None] = mapped_column(
        Time(timezone=True), nullable=True
    )

    weather_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )

    # Lifecycle
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"),
        default=TaskStatus.CREATED,
    )

    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    recurrence: Mapped["RecurrenceORM | None"] = relationship(
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan",
    )


class RecurrenceORM(Base, UUIDMixin):
    """Recurring task pattern."""

    __tablename__ = "recurrences"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
    )
    # Pattern examples: "daily", "weekly:mon,wed,fri", "monthly:15"
    pattern: Mapped[str] = mapped_column(String(100))
    next_run: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    task: Mapped[TaskORM] = relationship(back_populates="recurrence")
