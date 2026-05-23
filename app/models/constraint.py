"""User constraint ORM models (sleep, school, unavailable blocks)."""

import enum
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Enum,
    ForeignKey,
    SmallInteger,
    String,
    Time,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ConstraintType(str, enum.Enum):
    SLEEP = "sleep"
    SCHOOL = "school"
    UNAVAILABLE = "unavailable"
    FOCUS = "focus"


class UserConstraintORM(Base, UUIDMixin, TimestampMixin):
    """A time-block constraint for a user (e.g. sleep 23:00-07:00)."""

    __tablename__ = "user_constraints"

    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    constraint_type: Mapped[ConstraintType] = mapped_column(
        Enum(ConstraintType, name="constraint_type"),
    )
    start_time: Mapped[str] = mapped_column(String(5))  # "HH:MM"
    end_time: Mapped[str] = mapped_column(String(5))    # "HH:MM"
    days_of_week: Mapped[list[int] | None] = mapped_column(
        ARRAY(SmallInteger), nullable=True,
    )  # 0=Mon..6=Sun; None means every day
    label: Mapped[str] = mapped_column(String(200), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
