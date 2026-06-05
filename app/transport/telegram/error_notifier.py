"""Telegram logging handler for ERROR / CRITICAL notifications.

Sends formatted error reports to a Telegram admin chat with:
- Deduplication: same error at most once per DEDUP_WINDOW seconds
- Global rate-limit: at most MAX_PER_MINUTE messages per minute
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
from collections import deque
from typing import Optional

from aiogram import Bot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_DEDUP_WINDOW = 300        # 5 minutes — same error suppressed within this window
_MAX_PER_MINUTE = 10       # hard cap on messages per minute
_MAX_MESSAGE_LEN = 4000    # Telegram message limit (safe margin from 4096)


def _format_error_message(record: logging.LogRecord) -> str:
    """Build a human-readable Telegram message from a log record."""
    # Extract function / module info
    func = record.funcName or "—"
    module = record.module or record.name

    # Format the timestamp
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))

    # Build error details
    error_text = record.getMessage()

    # Include traceback if present
    tb = ""
    if record.exc_info and record.exc_info[1]:
        tb_lines = traceback.format_exception(*record.exc_info)
        tb = "\n".join(tb_lines)

    level_emoji = "🔴" if record.levelno >= logging.CRITICAL else "❌"

    parts = [
        f"{level_emoji} <b>{record.levelname}</b>",
        "",
        f"<b>Module:</b>  <code>{module}</code>",
        f"<b>Function:</b>  <code>{func}</code>",
        "",
        f"<b>Error:</b>",
        f"<code>{_escape_html(error_text)}</code>",
    ]

    if tb:
        # Trim traceback if too long
        if len(tb) > 1500:
            tb = tb[:750] + "\n... (trimmed) ...\n" + tb[-750:]
        parts.append("")
        parts.append(f"<b>Traceback:</b>")
        parts.append(f"<pre>{_escape_html(tb)}</pre>")

    parts.append("")
    parts.append(f"🕐 {ts}")

    text = "\n".join(parts)

    # Final safety trim
    if len(text) > _MAX_MESSAGE_LEN:
        text = text[:_MAX_MESSAGE_LEN - 20] + "\n... (trimmed)"

    return text


def _escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _dedup_key(record: logging.LogRecord) -> str:
    """Create a key for deduplication: module + function + first line of message."""
    msg_first_line = record.getMessage().split("\n")[0][:200]
    exc_type = ""
    if record.exc_info and record.exc_info[0]:
        exc_type = record.exc_info[0].__name__
    return f"{record.name}:{record.funcName}:{exc_type}:{msg_first_line}"


class TelegramErrorHandler(logging.Handler):
    """Logging handler that sends ERROR+ messages to Telegram.

    Thread-safe. Uses fire-and-forget async sends via the running event loop.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int | str,
        dedup_window: int = _DEDUP_WINDOW,
        max_per_minute: int = _MAX_PER_MINUTE,
    ) -> None:
        super().__init__(level=logging.ERROR)
        self._bot = bot
        self._chat_id = chat_id
        self._dedup_window = dedup_window
        self._max_per_minute = max_per_minute

        # dedup: key -> last_sent_timestamp
        self._seen: dict[str, float] = {}
        # global rate-limit: timestamps of recent sends
        self._send_times: deque[float] = deque()

    # ------------------------------------------------------------------
    # Rate-limiting helpers
    # ------------------------------------------------------------------

    def _is_duplicate(self, key: str) -> bool:
        """Return True if this error was sent recently."""
        now = time.monotonic()
        last = self._seen.get(key)
        if last is not None and (now - last) < self._dedup_window:
            return True
        self._seen[key] = now
        # Cleanup old entries periodically
        if len(self._seen) > 500:
            cutoff = now - self._dedup_window
            self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
        return False

    def _is_rate_limited(self) -> bool:
        """Return True if we've hit the per-minute cap."""
        now = time.monotonic()
        # Purge entries older than 60s
        while self._send_times and (now - self._send_times[0]) > 60:
            self._send_times.popleft()
        if len(self._send_times) >= self._max_per_minute:
            return True
        self._send_times.append(now)
        return False

    # ------------------------------------------------------------------
    # logging.Handler interface
    # ------------------------------------------------------------------

    def emit(self, record: logging.LogRecord) -> None:
        """Process a log record — send to Telegram if passes filters."""
        # Skip our own logger to avoid recursion
        if record.name.startswith("aiogram") or record.name == __name__:
            return

        key = _dedup_key(record)

        if self._is_duplicate(key):
            return
        if self._is_rate_limited():
            return

        text = _format_error_message(record)

        # Fire-and-forget: schedule in the running event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._send(text))
        except RuntimeError:
            # No running event loop — skip silently
            pass

    async def _send(self, text: str) -> None:
        """Actually send the message to Telegram."""
        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                parse_mode="HTML",
            )
        except Exception:
            # Never raise from the error handler itself
            pass


def setup_error_notifier(bot: Bot, chat_id: int | str) -> Optional[TelegramErrorHandler]:
    """Attach TelegramErrorHandler to the root logger.

    Returns the handler instance (for potential removal later), or None
    if chat_id is empty/falsy.
    """
    if not chat_id:
        logger.info("TELEGRAM_ADMIN_CHAT_ID not set — error notifications disabled")
        return None

    handler = TelegramErrorHandler(bot=bot, chat_id=chat_id)
    logging.getLogger().addHandler(handler)
    logger.info(
        "Telegram error notifications enabled → chat_id=%s "
        "(dedup=%ds, max=%d/min)",
        chat_id,
        handler._dedup_window,
        handler._max_per_minute,
    )
    return handler
