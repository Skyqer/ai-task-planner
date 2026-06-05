"""Voice transcription service using faster-whisper."""

from __future__ import annotations

import gc
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import psutil

from app.schemas.voice import TranscriptionResult

logger = logging.getLogger(__name__)

_CONFIDENCE_THRESHOLD = 0.6

# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------

_process = psutil.Process()


def _mem_mb() -> float:
    """Return current RSS of this process in MB."""
    return _process.memory_info().rss / (1024 * 1024)


class _PeakMemoryTracker:
    """Background thread that polls RSS and records the peak value."""

    def __init__(self, interval: float = 0.05) -> None:
        self._interval = interval
        self._peak: float = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._peak = _mem_mb()
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self) -> None:
        while not self._stop.is_set():
            current = _mem_mb()
            if current > self._peak:
                self._peak = current
            self._stop.wait(self._interval)

    def stop(self) -> float:
        """Stop tracking and return the peak RSS in MB."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        # one final sample after stop
        final = _mem_mb()
        if final > self._peak:
            self._peak = final
        return self._peak


class VoiceTranscriptionService:
    """Speech-to-text using SYSTRAN/faster-whisper.

    Lazy-loads the model on first transcription call.
    Automatically unloads after *unload_seconds* of inactivity to free RAM.
    Supports ru, uk, en with auto-detection.
    """

    def __init__(
        self,
        model_size: str = "base",
        unload_seconds: int = 120,
    ) -> None:
        self._model_size = model_size
        self._unload_seconds = unload_seconds
        self._model = None
        self._lock = threading.Lock()
        self._unload_timer: threading.Timer | None = None

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """Lazy-load the whisper model (thread-safe)."""
        if self._model is not None:
            return
        with self._lock:
            # Double-check after acquiring lock
            if self._model is not None:
                return
            try:
                mem_before = _mem_mb()
                logger.info("[MEMORY] before whisper load: %.1f MB", mem_before)

                from faster_whisper import WhisperModel
                from faster_whisper.utils import download_model

                # Resolve the actual model path to log the real HF model name
                import os

                if os.path.isdir(self._model_size):
                    model_path = self._model_size
                else:
                    model_path = download_model(
                        self._model_size, local_files_only=False
                    )

                self._model = WhisperModel(
                    self._model_size,
                    device="cpu",
                    compute_type="int8",
                )

                # --- Log real model info ---
                # Extract HF repo name from cache path
                # e.g. .../models--Systran--faster-whisper-base/...
                hf_model_name = self._model_size
                for part in Path(model_path).parts:
                    if part.startswith("models--"):
                        hf_model_name = (
                            part.replace("models--", "").replace("--", "/")
                        )
                        break

                # Model file size on disk
                model_bin = Path(model_path) / "model.bin"
                model_file_size = (
                    model_bin.stat().st_size / (1024 * 1024)
                    if model_bin.exists()
                    else 0.0
                )

                real_compute = self._model.model.compute_type

                mem_after = _mem_mb()
                logger.info("[MEMORY] after whisper load: %.1f MB", mem_after)
                logger.info(
                    "[WHISPER] model: %s | compute_type: %s | "
                    "file size: %.1f MB | path: %s",
                    hf_model_name,
                    real_compute,
                    model_file_size,
                    model_path,
                )
                logger.info(
                    "[MEMORY] whisper model loaded — used: %.1f MB",
                    mem_after - mem_before,
                )
            except Exception as exc:
                logger.error("Failed to load Whisper model: %s", exc)
                raise

    def _unload_model(self) -> None:
        """Evict the model from RAM to free memory."""
        with self._lock:
            if self._model is None:
                return
            mem_before = _mem_mb()
            self._model = None
            gc.collect()
            mem_after = _mem_mb()
            logger.info(
                "[MEMORY] whisper model unloaded — freed: %.1f MB "
                "(%.1f → %.1f MB)",
                mem_before - mem_after,
                mem_before,
                mem_after,
            )

    def _schedule_unload(self) -> None:
        """Reset the auto-unload timer after each transcription."""
        # Cancel any existing timer
        if self._unload_timer is not None:
            self._unload_timer.cancel()

        if self._unload_seconds <= 0:
            return  # 0 means keep model forever

        self._unload_timer = threading.Timer(
            self._unload_seconds, self._unload_model
        )
        self._unload_timer.daemon = True
        self._unload_timer.start()
        logger.info(
            "[WHISPER] model will be unloaded in %d s if idle",
            self._unload_seconds,
        )

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    async def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Transcribe an audio file to text.

        Args:
            audio_path: Path to an audio file (WAV or OGG).

        Returns:
            TranscriptionResult with text, language, and confidence.
        """
        try:
            self._load_model()
        except Exception:
            return TranscriptionResult(
                text="",
                language="unknown",
                confidence=0.0,
                low_confidence=True,
            )

        tracker = _PeakMemoryTracker(interval=0.05)

        try:
            mem_before = _mem_mb()
            logger.info("[MEMORY] before transcription: %.1f MB", mem_before)

            tracker.start()
            t_start = time.monotonic()

            segments, info = self._model.transcribe(
                str(audio_path),
                beam_size=1,
                language=None,  # auto-detect
                vad_filter=True,
            )

            # Collect segments
            texts: list[str] = []
            confidences: list[float] = []
            for segment in segments:
                texts.append(segment.text.strip())
                confidences.append(segment.avg_logprob)

            elapsed = time.monotonic() - t_start
            peak_mem = tracker.stop()
            mem_after = _mem_mb()

            logger.info("[MEMORY] after transcription: %.1f MB", mem_after)
            logger.info(
                "[MEMORY] transcription stats — "
                "used: %.1f MB | peak: %.1f MB | duration: %.2f s",
                mem_after - mem_before,
                peak_mem,
                elapsed,
            )

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
            tracker.stop()
            logger.error("Transcription failed: %s", exc)
            return TranscriptionResult(
                text="",
                language="unknown",
                confidence=0.0,
                low_confidence=True,
            )
        finally:
            # Schedule auto-unload timer
            self._schedule_unload()


