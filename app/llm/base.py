"""Abstract base class for LLM providers."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

from pydantic import ValidationError

from app.schemas.planner import PlannerResponseSchema

logger = logging.getLogger(__name__)


class BaseLLMProvider(ABC):
    """Interface that all LLM providers must implement.

    Core planner and services depend ONLY on this interface,
    never on a concrete provider.
    """

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: dict | None = None,
    ) -> str:
        """Send a prompt to the LLM and return raw text/JSON response.

        Args:
            system_prompt: Full system instructions.
            user_message: The user's input with injected context.
            response_schema: JSON schema dict for structured output (if supported).

        Returns:
            Raw string response from the LLM.
        """
        ...

    async def generate_parsed(
        self,
        system_prompt: str,
        user_message: str,
    ) -> PlannerResponseSchema:
        """Generate and parse into PlannerResponseSchema.

        Falls back to a minimal error response on parse failure.
        """
        schema = PlannerResponseSchema.model_json_schema()
        raw = await self.generate(
            system_prompt=system_prompt,
            user_message=user_message,
            response_schema=schema,
        )
        return self._parse_response(raw)

    @staticmethod
    def _parse_response(raw: str) -> PlannerResponseSchema:
        """Parse raw LLM output into PlannerResponseSchema."""
        # Strip markdown code fences or conversational filler
        text = raw.strip()
        if not text.startswith("{"):
            start_idx = text.find("{")
            end_idx = text.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                text = text[start_idx : end_idx + 1]

        try:
            data = json.loads(text)
            return PlannerResponseSchema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.error("Failed to parse LLM response: %s\nRaw: %s", exc, raw[:500])
            return PlannerResponseSchema(
                status="ok",
                warnings=[f"Ошибка разбора ответа LLM: {exc}"],
                summary="Не удалось обработать ответ. Попробуйте переформулировать.",
            )

    @abstractmethod
    async def generate_summary(self, messages_text: str) -> str:
        """Generate a short summary of conversation history.

        Used by the memory layer to compress old messages.

        Args:
            messages_text: Formatted conversation history.

        Returns:
            Compact summary string.
        """
        ...
