"""User ORM model for per-user settings."""

from datetime import datetime, time

from sqlalchemy import BigInteger, DateTime, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserORM(Base):
    """User preferences and settings."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Kyiv")
    weather_city: Mapped[str] = mapped_column(String(100), default="Uzhhorod")
    morning_brief_time: Mapped[time] = mapped_column(
        Time, default=time(8, 0)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
    )
