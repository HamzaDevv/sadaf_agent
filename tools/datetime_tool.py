"""
tools/datetime_tool.py — Sadaf Jarvis DateTime Tool

Returns current time, date, day, and timezone info.
No external API — pure Python datetime + pytz.
"""
from datetime import datetime
import pytz


def get_datetime(query: str = "") -> str:
    """Return spoken-English current date and time info."""
    query_lower = query.lower()

    try:
        # Use local system time
        now = datetime.now()
        local_tz = datetime.now().astimezone().tzname()

        # Respond based on what they asked
        if any(w in query_lower for w in ["time", "clock", "hour", "minute"]):
            return f"It's {now.strftime('%I:%M %p')} right now — {local_tz}."

        if any(w in query_lower for w in ["date", "today", "day"]):
            return f"Today is {now.strftime('%A, %B %d %Y')}."

        if any(w in query_lower for w in ["year", "month"]):
            return f"It's {now.strftime('%B %Y')}."

        # Default: both time and date
        return (
            f"It's {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d %Y')}."
        )
    except Exception as e:
        return f"I had trouble reading the time: {e}"
