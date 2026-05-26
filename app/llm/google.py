"""Google AI Studio LLM provider — uses the OpenAI-compatible API."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.config import Settings
from app.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class GoogleProvider(BaseLLMProvider):
    """LLM provider that calls Google AI Studio (OpenAI-compatible)."""

    def __init__(self, settings: Settings) -> None:
        self._model = settings.google_model
        self._timeout = settings.llm_timeout_seconds
        self._max_retries = settings.llm_max_retries
        self._client = AsyncOpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=settings.google_api_key,
            timeout=self._timeout,
            max_retries=self._max_retries,
        )

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: dict | None = None,
    ) -> str:
        """Call Google API with optional structured output schema."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 2500,
        }

        # Structured output via json_object
        if response_schema is not None:
            kwargs["response_format"] = {"type": "json_object"}

        logger.debug("Google request: model=%s", self._model)

        response = await self._client.chat.completions.create(**kwargs)
        
        content = ""
        if response and response.choices and len(response.choices) > 0:
            content = response.choices[0].message.content or ""

        logger.debug("Google response length: %d chars", len(content))
        if not content:
            raise ValueError("Empty or invalid response from Google.")
            
        return content

    async def generate_summary(self, messages_text: str) -> str:
        """Generate a compact summary of conversation history."""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a context compression assistant. "
                        "Read the conversation history and return a brief summary (2-4 sentences) "
                        "with key facts: tasks, preferences, context. "
                        "Write in English. No fluff."
                    ),
                },
                {"role": "user", "content": messages_text},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""
