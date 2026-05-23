"""OpenRouter LLM provider — uses the OpenAI-compatible API."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.config import Settings
from app.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class OpenRouterProvider(BaseLLMProvider):
    """LLM provider that calls OpenRouter API (OpenAI-compatible)."""

    def __init__(self, settings: Settings) -> None:
        self._model = settings.openrouter_model
        self._timeout = settings.llm_timeout_seconds
        self._max_retries = settings.llm_max_retries
        self._client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key,
            timeout=self._timeout,
            max_retries=self._max_retries,
        )

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: dict | None = None,
    ) -> str:
        """Call OpenRouter with optional structured output schema."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 1500,
        }

        # Structured output via json_object
        if response_schema is not None:
            kwargs["response_format"] = {"type": "json_object"}
            # Enable response healing plugin for robustness
            kwargs["extra_headers"] = {
                "X-Title": "TaskPlanner",
            }

        logger.debug("OpenRouter request: model=%s", self._model)

        response = await self._client.chat.completions.create(**kwargs)
        
        content = ""
        if response and response.choices and len(response.choices) > 0:
            content = response.choices[0].message.content or ""

        logger.debug("OpenRouter response length: %d chars", len(content))
        if not content:
            raise ValueError("Empty or invalid response from OpenRouter.")
            
        return content

    async def generate_summary(self, messages_text: str) -> str:
        """Generate a compact summary of conversation history."""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты — помощник для сжатия контекста. "
                        "Прочитай историю переписки и верни краткую сводку (2-4 предложения) "
                        "с ключевыми фактами: задачи, предпочтения, контекст. "
                        "Пиши на русском. Без воды."
                    ),
                },
                {"role": "user", "content": messages_text},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""
