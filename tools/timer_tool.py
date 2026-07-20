"""
tools/timer_tool.py — Sadaf Jarvis Timer Tool

Sets a countdown timer using asyncio.
Speaks an alert when the timer fires.
Multiple timers can run concurrently.
"""
import asyncio
import re
from typing import Callable, Optional


# Global speak callback — set by main.py
_speak_fn: Optional[Callable] = None

# Track active timers for reporting
_active_timers: list[dict] = []


def set_speak_fn(fn: Callable):
    global _speak_fn
    _speak_fn = fn


# ── Time parsing ─────────────────────────────────────────────────────────────

TIME_UNITS_SECS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
}


def _parse_duration(text: str) -> Optional[int]:
    """
    Parse duration from text. Supports multi-unit:
    '5 minutes and 30 seconds' → 330
    '1 hour 20 minutes' → 4800
    """
    text = text.lower()
    total = 0
    found = False

    for unit, secs in TIME_UNITS_SECS.items():
        pattern = rf"(\d+)\s+{unit}"
        match = re.search(pattern, text)
        if match:
            total += int(match.group(1)) * secs
            found = True

    # Also try bare number (e.g. "set a timer for 5" — assume minutes)
    if not found:
        match = re.search(r"for\s+(\d+)$", text.strip())
        if match:
            total = int(match.group(1)) * 60
            found = True

    return total if found else None


def _human_duration(secs: int) -> str:
    """Convert seconds to human-readable string."""
    parts = []
    if secs >= 3600:
        h = secs // 3600
        parts.append(f"{h} hour{'s' if h > 1 else ''}")
        secs %= 3600
    if secs >= 60:
        m = secs // 60
        parts.append(f"{m} minute{'s' if m > 1 else ''}")
        secs %= 60
    if secs > 0:
        parts.append(f"{secs} second{'s' if secs > 1 else ''}")
    return " and ".join(parts) if parts else "0 seconds"


# ── Background timer ──────────────────────────────────────────────────────────

async def _run_timer(duration_secs: int, label: str):
    """Background task: sleep then speak alert."""
    timer_entry = {"duration": duration_secs, "label": label, "done": False}
    _active_timers.append(timer_entry)

    await asyncio.sleep(duration_secs)

    timer_entry["done"] = True
    if _speak_fn:
        msg = f"Time's up! Your {label} timer has finished." if label else "Time's up! Your timer has finished."
        await _speak_fn(msg)


# ── Main tool function ────────────────────────────────────────────────────────

async def set_timer(query: str, speak_fn: Callable = None) -> str:
    """Parse and start a countdown timer."""
    global _speak_fn
    if speak_fn:
        _speak_fn = speak_fn

    duration_secs = _parse_duration(query)

    if duration_secs is None or duration_secs <= 0:
        return "I couldn't figure out the timer duration. Try 'set a timer for 5 minutes'."

    # Extract optional label (e.g. "timer for 5 minutes for the pasta")
    label = ""
    match = re.search(r"for\s+the\s+(.+)$", query.lower())
    if match:
        # Make sure it's not a time unit
        candidate = match.group(1).strip()
        if not any(unit in candidate for unit in TIME_UNITS_SECS):
            label = candidate

    asyncio.create_task(_run_timer(duration_secs, label))

    human = _human_duration(duration_secs)
    if label:
        return f"Timer set for {human} — I'll let you know when the {label} is ready."
    return f"Timer set for {human}. I'll give you a heads up when it's done."
