"""Safe parsing for time formats from LLM output."""

import re
from datetime import time

def parse_time_safe(time_str: str) -> time | None:
    """
    Parse a time string safely, ignoring surrounding text or ranges.
    Returns a datetime.time object or None if parsing fails.
    
    Handles:
    - '14:30'
    - '14:30-15:00' (takes the first part)
    - '02:00 PM' (ignores PM/AM if it just parses numbers, or we can handle it if needed.
                  For MVP we just extract first HH:MM).
    """
    if not time_str:
        return None
        
    time_str = str(time_str).strip()
    
    # Simple regex to extract first HH:MM
    match = re.search(r'(\d{1,2}):(\d{2})', time_str)
    if not match:
        return None
        
    hour_str, min_str = match.groups()
    try:
        h, m = int(hour_str), int(min_str)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return time(hour=h, minute=m)
    except ValueError:
        pass
        
    return None
