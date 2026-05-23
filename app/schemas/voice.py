"""Voice transcription result schema."""

from __future__ import annotations

from pydantic import BaseModel


class TranscriptionResult(BaseModel):
    """Result of speech-to-text transcription."""

    text: str
    language: str = "unknown"
    confidence: float = 0.0
    low_confidence: bool = False
