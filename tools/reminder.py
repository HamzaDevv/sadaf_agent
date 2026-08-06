"""
tools/reminder.py — Sadaf Jarvis Reminder Tool

Enhanced date/time parsing:
- Relative: "in 10 minutes", "in 2 hours"
- Day-of-week: "on Monday", "on Friday"
- Day + time: "on Friday at 9pm", "Monday at 9am"
- Tomorrow: "tomorrow", "tomorrow at 3pm"
- Persist reminders across restarts
- Background asyncio task fires TTS when timer triggers
"""
import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from config import REMINDERS_FILE

# Global speak callback — set by main.py on startup
_speak_fn: Optional[Callable] = None

# ── Time Unit Map ─────────────────────────────────────────────────────────────

TIME_UNITS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
}

DAYS_OF_WEEK = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}


# ── Clock-Time Parser ─────────────────────────────────────────────────────────

def _parse_clock_time(text: str) -> Optional[tuple]:
    """
    Extract (hour, minute) from phrases like '9pm', '9:30am', '21:00', '9 pm'.
    Returns None if no clock time found.
    """
    # 12-hour: "9pm", "9:30pm", "9 pm", "9:30 pm"
    m = re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', text.lower())
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = m.group(3)
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        return (hour, minute)

    # 24-hour: "21:00", "09:30"
    m = re.search(r'\b([01]?\d|2[0-3]):([0-5]\d)\b', text)
    if m:
        return (int(m.group(1)), int(m.group(2)))

    return None


# ── Main Delay Parser ─────────────────────────────────────────────────────────

def _parse_delay_seconds(text: str) -> Optional[int]:
    """
    Parse time references from natural language and return seconds from now.

    Supports:
      - "in 5 minutes", "in 2 hours", "in 30 seconds"
      - "tomorrow", "tomorrow at 9am"
      - "on Monday", "on Friday"
      - "on Friday at 9pm", "Monday at 9am"
    """
    text_lower = text.lower()
    now = datetime.now()

    # 1. Relative: "in X minutes/hours/seconds"
    m = re.search(r'\bin\s+(\d+)\s+(\w+)', text_lower)
    if m:
        amount = int(m.group(1))
        unit_str = m.group(2).lower()
        for key, secs in TIME_UNITS.items():
            if unit_str.rstrip("s") == key.rstrip("s"):
                return amount * secs
            if unit_str.startswith(key.rstrip("s")):
                return amount * secs

    # 2. Tomorrow
    if "tomorrow" in text_lower:
        target = now + timedelta(days=1)
        clock = _parse_clock_time(text_lower)
        if clock:
            target = target.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
        else:
            target = target.replace(hour=9, minute=0, second=0, microsecond=0)
        return max(60, int((target - now).total_seconds()))

    # 3. Day of week: "on Monday", "Friday at 9pm", "next Wednesday"
    for day_name, day_num in DAYS_OF_WEEK.items():
        if re.search(r'\b' + day_name + r'\b', text_lower):
            days_ahead = (day_num - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # always next occurrence, not today
            target = now + timedelta(days=days_ahead)
            clock = _parse_clock_time(text_lower)
            if clock:
                target = target.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
            else:
                target = target.replace(hour=9, minute=0, second=0, microsecond=0)
            return max(60, int((target - now).total_seconds()))

    return None


def _delay_to_human(delay_secs: int, fire_at: datetime) -> str:
    """Convert delay to a human-readable string like 'Monday at 9:00 AM'."""
    now = datetime.now()
    days_ahead = (fire_at - now).days

    if delay_secs < 3600:
        mins = delay_secs // 60
        secs = delay_secs % 60
        if mins > 0:
            return f"{mins} minute{'s' if mins != 1 else ''}"
        return f"{secs} second{'s' if secs != 1 else ''}"

    if delay_secs < 86400:
        hrs = delay_secs // 3600
        return f"{hrs} hour{'s' if hrs != 1 else ''}"

    # Day-based: show weekday + time
    weekday = fire_at.strftime("%A")
    time_str = fire_at.strftime("%-I:%M %p").lstrip("0") if fire_at.minute != 0 else fire_at.strftime("%-I %p")
    if days_ahead < 2:
        return f"tomorrow at {time_str}"
    return f"{weekday} at {time_str}"


# ── Message Parser ────────────────────────────────────────────────────────────

def _parse_message(text: str) -> str:
    """Extract the reminder message from natural language."""
    # "remind me ... to <message>"
    m = re.search(r'\bto\s+(.+?)(?:\s+(?:on|at|in)\s+\w|\s*$)', text.lower())
    if m:
        msg = m.group(1).strip()
        if msg:
            return msg
    # Fallback: "remind me ... to <message>" (greedy)
    m = re.search(r'\bto\s+(.+)$', text.lower())
    if m:
        return m.group(1).strip()
    # "remind me about <message>"
    m = re.search(r'\babout\s+(.+?)(?:\s+(?:on|at|in)\s+\w|\s*$)', text.lower())
    if m:
        return m.group(1).strip()
    return "something you wanted to be reminded about"


# ── Persistence ───────────────────────────────────────────────────────────────

def _load_reminders() -> list:
    path = Path(REMINDERS_FILE)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def _save_reminders(reminders: list):
    path = Path(REMINDERS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reminders, indent=2))


def _add_reminder(fire_at_iso: str, message: str):
    reminders = _load_reminders()
    reminders.append({"fire_at": fire_at_iso, "message": message, "fired": False})
    _save_reminders(reminders)


def _mark_fired(fire_at_iso: str, message: str):
    reminders = _load_reminders()
    for r in reminders:
        if r["fire_at"] == fire_at_iso and r["message"] == message:
            r["fired"] = True
    _save_reminders(reminders)


# ── Startup: fire missed reminders ───────────────────────────────────────────

async def fire_pending_reminders(speak_fn: Callable):
    global _speak_fn
    _speak_fn = speak_fn

    reminders = _load_reminders()
    now = datetime.now()
    missed = []

    for r in reminders:
        if r.get("fired"):
            continue
        try:
            fire_at = datetime.fromisoformat(r["fire_at"])
            if fire_at <= now:
                missed.append(r["message"])
                r["fired"] = True
        except Exception:
            r["fired"] = True

    _save_reminders(reminders)

    if missed:
        summary = f"Hey, you have {len(missed)} missed reminder{'s' if len(missed) > 1 else ''}. "
        summary += "Here they are: " + ". Also, ".join(missed) + "."
        print(f"Sadaf: {summary}")
        await speak_fn(summary)

    for r in _load_reminders():
        if not r.get("fired"):
            try:
                fire_at = datetime.fromisoformat(r["fire_at"])
                asyncio.create_task(_schedule_reminder(fire_at, r["message"]))
            except Exception:
                pass


async def _schedule_reminder(fire_at: datetime, message: str):
    now = datetime.now()
    delay = (fire_at - now).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)
    if _speak_fn:
        msg = f"Hey, just a reminder — {message}."
        print(f"Sadaf: {msg}")
        await _speak_fn(msg)
    _mark_fired(fire_at.isoformat(), message)


# ── Main Tool Function ────────────────────────────────────────────────────────

async def set_reminder(query: str, speak_fn: Callable = None) -> str:
    """
    Parse user query and schedule a reminder.
    Supports relative ("in 10 minutes"), day-of-week ("on Friday at 9pm"),
    and tomorrow references ("tomorrow at 8am").
    """
    global _speak_fn
    if speak_fn:
        _speak_fn = speak_fn

    delay_secs = _parse_delay_seconds(query)
    message = _parse_message(query)

    if delay_secs is None:
        return (
            "I couldn't figure out when to set the reminder. "
            "You can say things like 'in 10 minutes', 'on Friday at 9pm', or 'tomorrow at 8am'."
        )

    fire_at = datetime.now() + timedelta(seconds=delay_secs)
    _add_reminder(fire_at.isoformat(), message)
    asyncio.create_task(_schedule_reminder(fire_at, message))

    time_str = _delay_to_human(delay_secs, fire_at)
    return f"Got it. I'll remind you to {message} {time_str}."
