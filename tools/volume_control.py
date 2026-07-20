"""
tools/volume_control.py — Sadaf Jarvis Volume Control Tool

Controls macOS system volume using osascript.
Supports: set level, mute, unmute, get current volume.
"""
import asyncio
import subprocess
import re


def _run_applescript(script: str) -> str:
    """Run an AppleScript command and return output."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=4
        )
        return result.stdout.strip()
    except Exception as e:
        return f"error:{e}"


def _get_volume() -> int:
    """Get current system volume (0-100)."""
    out = _run_applescript("output volume of (get volume settings)")
    try:
        return int(out)
    except Exception:
        return -1


def _get_muted() -> bool:
    out = _run_applescript("output muted of (get volume settings)")
    return out.lower() == "true"


def _set_volume(level: int):
    level = max(0, min(100, level))
    _run_applescript(f"set volume output volume {level}")


def _set_muted(muted: bool):
    _run_applescript(f"set volume {'with' if muted else 'without'} output muted")


async def control_volume(query: str) -> str:
    """Parse user query and control macOS volume."""
    query_lower = query.lower()

    # Mute
    if any(w in query_lower for w in ["mute", "silence", "quiet", "shut up"]):
        await asyncio.to_thread(_set_muted, True)
        return "Alright, I've muted the volume."

    # Unmute
    if any(w in query_lower for w in ["unmute", "unsilence", "turn on sound"]):
        await asyncio.to_thread(_set_muted, False)
        return "Sound is back on."

    # Set to specific level
    level_match = re.search(r"(\d{1,3})\s*(?:%|percent)?", query_lower)

    # Relative up/down
    is_up = any(w in query_lower for w in ["up", "louder", "increase", "raise", "higher"])
    is_down = any(w in query_lower for w in ["down", "lower", "decrease", "quieter", "softer"])

    if is_up or is_down:
        current = await asyncio.to_thread(_get_volume)
        if current < 0:
            return "I couldn't read the current volume level."
        delta = 20
        # Use specific number if mentioned (e.g. "turn up by 10")
        if level_match:
            delta = int(level_match.group(1))
        new_level = current + delta if is_up else current - delta
        new_level = max(0, min(100, new_level))
        await asyncio.to_thread(_set_volume, new_level)
        direction = "up" if is_up else "down"
        return f"Volume turned {direction} to {new_level}%."

    if level_match:
        target = int(level_match.group(1))
        if 0 <= target <= 100:
            await asyncio.to_thread(_set_volume, target)
            return f"Volume set to {target}%."

    # Get current volume
    if any(w in query_lower for w in ["what", "current", "how loud", "check"]):
        current = await asyncio.to_thread(_get_volume)
        muted = await asyncio.to_thread(_get_muted)
        if muted:
            return "Volume is currently muted."
        return f"Volume is at {current}%."

    return "I'm not sure what you want me to do with the volume. Try 'mute', 'volume up', or 'set volume to 50'."
