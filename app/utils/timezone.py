"""Timezone utilities to avoid duplicated zoneinfo logic."""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Cache for the timezone info to avoid repeatedly importing/instantiating
_default_tzinfo = None


def get_local_timezone(tz_name: str = "Europe/Kyiv"):
    """Get the timezone info object."""
    global _default_tzinfo
    if _default_tzinfo is not None:
        return _default_tzinfo

    try:
        from zoneinfo import ZoneInfo
        _default_tzinfo = ZoneInfo(tz_name)
    except Exception as exc:
        logger.warning("Failed to load ZoneInfo for %s, falling back to UTC+2: %s", tz_name, exc)
        _default_tzinfo = timezone(timedelta(hours=2))
        
    return _default_tzinfo


def now_local(tz_name: str = "Europe/Kyiv") -> datetime:
    """Get the current datetime in the local timezone."""
    return datetime.now(get_local_timezone(tz_name))
