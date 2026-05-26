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
        import re

        text = raw.strip()

        # Strip <thought>...</thought> or <think>...</think> blocks
        text = re.sub(r"<(?:thought|think)>.*?</(?:thought|think)>", "", text, flags=re.DOTALL).strip()

        # Strip markdown code fences
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
        text = text.strip()

        # Find the outermost JSON object using balanced braces
        if not text.startswith("{"):
            start_idx = text.find("{")
            if start_idx == -1:
                logger.error("No JSON object found in LLM response.\nRaw: %s", raw[:500])
                return PlannerResponseSchema(
                    status="ok",
                    warnings=["The AI response was incomplete or incorrect."],
                    summary="Failed to recognize the AI response. Please rephrase your query.",
                )
            text = text[start_idx:]

        # Match balanced braces to find the complete JSON object
        depth = 0
        in_string = False
        escape_next = False
        end_pos = -1
        for i, ch in enumerate(text):
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                if in_string:
                    escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end_pos = i
                    break

        if end_pos != -1:
            text = text[: end_pos + 1]

        try:
            data = json.loads(text)
            return PlannerResponseSchema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.error("Failed to parse LLM response: %s\nRaw: %s", exc, raw[:500])
            return PlannerResponseSchema(
                status="ok",
                warnings=["The AI response was incomplete or incorrect."],
                summary="Failed to recognize the AI response. Please rephrase your query.",
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
