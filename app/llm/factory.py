"""Factory function to instantiate the configured LLM provider."""

from __future__ import annotations

from app.config import Settings
from app.llm.base import BaseLLMProvider


def get_llm_provider(settings: Settings) -> BaseLLMProvider:
    """Return the correct LLM provider based on config.

    Raises:
        ValueError: If the configured provider is unknown.
    """
    if settings.llm_provider == "openrouter":
        from app.llm.openrouter import OpenRouterProvider

        return OpenRouterProvider(settings)

    if settings.llm_provider == "ollama":
        from app.llm.ollama import OllamaProvider

        return OllamaProvider(settings)

    if settings.llm_provider == "google":
        from app.llm.google import GoogleProvider

        return GoogleProvider(settings)

    raise ValueError(
        f"Unknown LLM provider: {settings.llm_provider!r}. "
        "Supported: 'openrouter', 'ollama'."
    )
