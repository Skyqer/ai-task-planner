"""Application configuration via pydantic-settings."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All application settings, read from .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Database ──────────────────────────────────────────────────────
    database_url: str = (
        ""
    )

    # ── LLM Provider ─────────────────────────────────────────────────
    llm_provider: Literal["openrouter", "ollama", "google"] = "openrouter"

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_model: str = "deepseek/deepseek-r1:free"

    # Ollama (used when LLM_PROVIDER=ollama)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # Google
    google_api_key: str = ""
    google_model: str = "gemini-3.1-flash-lite-preview"

    # ── Telegram ─────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    bot_mode: Literal["polling", "webhook"] = "polling"
    webhook_url: str = ""
    webhook_secret: str = ""

    # ── Weather ──────────────────────────────────────────────────────
    openweather_api_key: str = ""
    weather_city: str = ""
    weather_country: str = ""

    # ── General ──────────────────────────────────────────────────────
    timezone: str = "Europe/Kyiv"

    # ── Memory ───────────────────────────────────────────────────────
    memory_max_messages: int = 20
    memory_summary_threshold: int = 15

    # ── LLM Timeouts ─────────────────────────────────────────────────
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 3

    # ── Voice ────────────────────────────────────────────────────────
    whisper_model_size: str = "base"
    whisper_unload_seconds: int = 120  # 0 = keep model in memory forever


settings = Settings()
