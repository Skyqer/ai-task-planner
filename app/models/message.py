"""Message and MemorySummary ORM models for the memory layer."""

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


class MessageORM(Base, UUIDMixin):
    """Individual chat message for conversation history."""

    __tablename__ = "messages"

    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role"),
    )
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
    )


class MemorySummaryORM(Base, UUIDMixin):
    """Compressed conversation summary per user."""

    __tablename__ = "memory_summaries"

    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    summary: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
    )
