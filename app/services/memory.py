"""Memory layer — manages conversation context for LLM calls."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import repository as repo
from app.llm.base import BaseLLMProvider
from app.models.message import MessageRole

logger = logging.getLogger(__name__)


class ConversationContext:
    """Container for the assembled LLM context."""

    def __init__(
        self,
        summary: str = "",
        recent_messages: list[dict[str, str]] | None = None,
        active_tasks_text: str = "",
    ) -> None:
        self.summary = summary
        self.recent_messages = recent_messages or []
        self.active_tasks_text = active_tasks_text

    def to_context_string(self) -> str:
        """Format the full context for injection into the system prompt."""
        parts: list[str] = []

        if self.summary:
            parts.append(f"Brief summary: {self.summary}")

        if self.recent_messages:
            msgs = []
            for msg in self.recent_messages[-5:]:  # last 5 for prompt
                role = "User" if msg["role"] == "user" else "Assistant"
                msgs.append(f"{role}: {msg['content'][:200]}")
            parts.append("Recent messages:\n" + "\n".join(msgs))

        return "\n\n".join(parts) if parts else "No previous context."


class MemoryManager:
    """Three-tier context management:
    1. Recent messages (last N)
    2. Summarized context (compressed by LLM)
    3. Task context (active tasks)
    """

    def __init__(
        self,
        settings: Settings,
        llm_provider: BaseLLMProvider,
    ) -> None:
        self._max_messages = settings.memory_max_messages
        self._summary_threshold = settings.memory_summary_threshold
        self._llm = llm_provider

    async def add_message(
        self,
        session: AsyncSession,
        user_id: int,
        role: str,
        content: str,
    ) -> None:
        """Store a message and trigger summarization if threshold reached."""
        msg_role = MessageRole.USER if role == "user" else MessageRole.ASSISTANT
        await repo.add_message(session, user_id, msg_role, content)
        await self._summarize_if_needed(session, user_id)

    async def get_context(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> ConversationContext:
        """Build the full conversation context for LLM prompt."""
        # 1. Get stored summary
        summary_record = await repo.get_memory_summary(session, user_id)
        summary_text = summary_record.summary if summary_record else ""

        # 2. Get recent messages
        recent = await repo.get_recent_messages(
            session, user_id, limit=self._max_messages
        )
        recent_dicts = [
            {"role": msg.role.value, "content": msg.content}
            for msg in recent
        ]

        # 3. Get active tasks
        tasks = await repo.get_active_tasks(session, user_id)
        if tasks:
            task_lines = []
            for t in tasks:
                line = f"- [{t.priority}] {t.title}"
                if t.deadline_date:
                    line += f" (deadline: {t.deadline_date}"
                    if t.deadline_time:
                        line += f" {t.deadline_time}"
                    line += ")"
                if t.fixed_time_date:
                    line += f" [fixed: {t.fixed_time_date}"
                    if t.fixed_time_time:
                        line += f" {t.fixed_time_time}"
                    line += "]"
                task_lines.append(line)
            tasks_text = "\n".join(task_lines)
        else:
            tasks_text = "No active tasks."

        return ConversationContext(
            summary=summary_text,
            recent_messages=recent_dicts,
            active_tasks_text=tasks_text,
        )

    async def _summarize_if_needed(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> None:
        """If message count exceeds threshold, summarize old messages."""
        count = await repo.count_messages(session, user_id)
        if count <= self._summary_threshold:
            return

        logger.info(
            "User %d has %d messages, summarizing (threshold=%d)",
            user_id, count, self._summary_threshold,
        )

        # Get all recent messages for summarization
        messages = await repo.get_recent_messages(session, user_id, limit=count)

        # Combine old messages (beyond the last 5) into text
        old_messages = messages[:-5] if len(messages) > 5 else messages
        text = "\n".join(
            f"{m.role.value}: {m.content}" for m in old_messages
        )

        # Get existing summary for context
        existing = await repo.get_memory_summary(session, user_id)
        if existing:
            text = f"Предыдущая сводка: {existing.summary}\n\nНовые сообщения:\n{text}"

        try:
            new_summary = await self._llm.generate_summary(text)
            await repo.upsert_memory_summary(session, user_id, new_summary)
            # Delete old messages, keep last N
            await repo.delete_old_messages(
                session, user_id, keep_last=self._max_messages
            )
            logger.info("Summarized context for user %d", user_id)
        except Exception as exc:
            logger.error("Summarization failed for user %d: %s", user_id, exc)
