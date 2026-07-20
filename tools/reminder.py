"""
tools/reminder.py — Sadaf Jarvis Reminder Tool

Features:
- Parse natural language: "remind me in 10 minutes to drink water"
- Persist reminders to a JSON file (survive restarts)
- On startup: fire any past-due reminders immediately as a catch-up summary
- Background asyncio task speaks reminder when timer fires
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

# ── Time parsing helpers ──────────────────────────────────────────────────────

TIME_UNITS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
}


def _parse_delay_seconds(text: str) -> Optional[int]:
    """
    Parse phrases like 'in 5 minutes', 'after 2 hours', 'in 30 seconds'.
    Returns total seconds or None if not found.
    """
    pattern = r"in\s+(\d+)\s+(\w+)"
    match = re.search(pattern, text.lower())
    if match:
        amount = int(match.group(1))
        unit = match.group(2).rstrip("s") + "s"  # normalize to plural
        # Match unit
        for key, secs in TIME_UNITS.items():
            if key.startswith(match.group(2).rstrip("s")):
                return amount * secs
    return None


def _parse_message(text: str) -> str:
    """Extract the reminder message from phrases like 'remind me to ...', 'remind me in 5 min to ...'"""
    # Try: "remind me in X minutes to <message>"
    match = re.search(r"\bto\s+(.+)$", text.lower())
    if match:
        return match.group(1).strip()
    # Try: "remind me about <message>"
    match = re.search(r"\babout\s+(.+)$", text.lower())
    if match:
        return match.group(1).strip()
    return "something you wanted to be reminded about"


# ── Persistence ───────────────────────────────────────────────────────────────

def _load_reminders() -> list[dict]:
    path = Path(REMINDERS_FILE)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def _save_reminders(reminders: list[dict]):
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
    """
    Called on startup. Any reminder whose fire_at time has already passed
    is announced immediately as a catch-up alert.
    """
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
            r["fired"] = True  # corrupt entry — discard

    _save_reminders(reminders)

    if missed:
        summary = f"Hey, you have {len(missed)} missed reminder{'s' if len(missed) > 1 else ''}. "
        summary += "Here they are: " + ". Also, ".join(missed) + "."
        await speak_fn(summary)

    # Schedule any unfired future reminders
    for r in _load_reminders():
        if not r.get("fired"):
            try:
                fire_at = datetime.fromisoformat(r["fire_at"])
                asyncio.create_task(_schedule_reminder(fire_at, r["message"]))
            except Exception:
                pass


async def _schedule_reminder(fire_at: datetime, message: str):
    """Wait until fire_at then speak the reminder."""
    now = datetime.now()
    delay = (fire_at - now).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)
    # Speak
    if _speak_fn:
        await _speak_fn(f"Hey, just a reminder — {message}.")
    _mark_fired(fire_at.isoformat(), message)


# ── Main tool function ────────────────────────────────────────────────────────

async def set_reminder(query: str, speak_fn: Callable = None) -> str:
    """
    Parse user query and schedule a reminder.
    Example: "remind me in 10 minutes to drink water"
    """
    global _speak_fn
    if speak_fn:
        _speak_fn = speak_fn

    delay_secs = _parse_delay_seconds(query)
    message = _parse_message(query)

    if delay_secs is None:
        return "I couldn't figure out when to remind you. Try saying 'remind me in 10 minutes to...'"

    fire_at = datetime.now() + timedelta(seconds=delay_secs)
    _add_reminder(fire_at.isoformat(), message)

    # Schedule background task
    asyncio.create_task(_schedule_reminder(fire_at, message))

    mins = delay_secs // 60
    secs = delay_secs % 60
    if mins > 0:
        time_str = f"{mins} minute{'s' if mins != 1 else ''}"
    else:
        time_str = f"{secs} second{'s' if secs != 1 else ''}"

    return f"Got it. I'll remind you to {message} in {time_str}."
