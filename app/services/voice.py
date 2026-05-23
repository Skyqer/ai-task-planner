"""Voice transcription service using faster-whisper."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from app.schemas.voice import TranscriptionResult

logger = logging.getLogger(__name__)

_CONFIDENCE_THRESHOLD = 0.6


class VoiceTranscriptionService:
    """Speech-to-text using SYSTRAN/faster-whisper.

    Lazy-loads the model on first transcription call.
    Supports ru, uk, en with auto-detection.
    """

    def __init__(self, model_size: str = "base") -> None:
        self._model_size = model_size
        self._model = None

    def _load_model(self) -> None:
        """Lazy-load the whisper model."""
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self._model_size,
                device="cpu",
                compute_type="int8",
            )
            logger.info("Whisper model '%s' loaded", self._model_size)
        except Exception as exc:
            logger.error("Failed to load Whisper model: %s", exc)
            raise

    async def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Transcribe an audio file to text.

        Args:
            audio_path: Path to an audio file (WAV or OGG).

        Returns:
            TranscriptionResult with text, language, and confidence.
        """
        # Convert to WAV if needed (Telegram sends OGG/OGA)
        wav_path = await self._ensure_wav(audio_path)

        try:
            self._load_model()
        except Exception:
            return TranscriptionResult(
                text="",
                language="unknown",
                confidence=0.0,
                low_confidence=True,
            )

        try:
            segments, info = self._model.transcribe(
                str(wav_path),
                beam_size=5,
                language=None,  # auto-detect
                vad_filter=True,
            )

            # Collect segments
            texts: list[str] = []
            confidences: list[float] = []
            for segment in segments:
                texts.append(segment.text.strip())
                confidences.append(segment.avg_logprob)

            full_text = " ".join(texts).strip()
            avg_confidence = (
                sum(confidences) / len(confidences) if confidences else 0.0
            )
            # Convert log-prob to a 0-1 scale (rough heuristic)
            # avg_logprob is typically -0.1 (good) to -1.0 (bad)
            normalized_confidence = max(0.0, min(1.0, 1.0 + avg_confidence))

            detected_lang = info.language if info else "unknown"

            return TranscriptionResult(
                text=full_text,
                language=detected_lang,
                confidence=normalized_confidence,
                low_confidence=normalized_confidence < _CONFIDENCE_THRESHOLD,
            )

        except Exception as exc:
            logger.error("Transcription failed: %s", exc)
            return TranscriptionResult(
                text="",
                language="unknown",
                confidence=0.0,
                low_confidence=True,
            )
        finally:
            # Clean up temporary WAV if we created one
            if wav_path != audio_path and wav_path.exists():
                wav_path.unlink(missing_ok=True)

    @staticmethod
    async def _ensure_wav(audio_path: Path) -> Path:
        """Convert audio to WAV format if it isn't already."""
        if audio_path.suffix.lower() == ".wav":
            return audio_path

        wav_path = audio_path.with_suffix(".wav")
        try:
            proc = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(audio_path),
                    "-ar", "16000", "-ac", "1", "-f", "wav",
                    str(wav_path),
                ],
                capture_output=True,
                timeout=30,
            )
            if proc.returncode != 0:
                logger.error("ffmpeg conversion failed: %s", proc.stderr.decode())
                return audio_path  # Try with original file
            return wav_path
        except FileNotFoundError:
            logger.error("ffmpeg not found — install it for voice support")
            return audio_path
        except subprocess.TimeoutExpired:
            logger.error("ffmpeg conversion timed out")
            return audio_path
