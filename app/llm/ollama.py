"""Ollama LLM provider — local models via the ollama Python client."""

from __future__ import annotations

import logging

from ollama import AsyncClient

from app.config import Settings
from app.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """LLM provider for local models running on Ollama."""

    def __init__(self, settings: Settings) -> None:
        self._model = settings.ollama_model
        self._client = AsyncClient(host=settings.ollama_base_url)

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: dict | None = None,
    ) -> str:
        """Call Ollama with optional structured output via format parameter."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "options": {"temperature": 0},
        }

        # Structured output: pass JSON schema to the format parameter
        if response_schema is not None:
            kwargs["format"] = response_schema

        logger.debug("Ollama request: model=%s", self._model)

        response = await self._client.chat(**kwargs)
        content = response.message.content or ""

        logger.debug("Ollama response length: %d chars", len(content))
        return content

    async def generate_summary(self, messages_text: str) -> str:
        """Generate a compact summary of conversation history."""
        response = await self._client.chat(
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
            options={"temperature": 0.2},
        )
        return response.message.content or ""
