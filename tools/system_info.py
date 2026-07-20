"""
tools/system_info.py — Sadaf Jarvis System Diagnostics Tool

Uses psutil to report CPU, RAM, battery, and disk usage.
Returns a natural spoken-English summary.
"""
import asyncio
import psutil


def _get_system_stats() -> dict:
    """Gather system stats synchronously (runs in thread)."""
    stats = {}

    # CPU
    stats["cpu"] = psutil.cpu_percent(interval=0.5)

    # RAM
    mem = psutil.virtual_memory()
    stats["ram_used_gb"] = round(mem.used / (1024 ** 3), 1)
    stats["ram_total_gb"] = round(mem.total / (1024 ** 3), 1)
    stats["ram_pct"] = mem.percent

    # Disk (root partition)
    try:
        disk = psutil.disk_usage("/")
        stats["disk_used_gb"] = round(disk.used / (1024 ** 3), 1)
        stats["disk_total_gb"] = round(disk.total / (1024 ** 3), 1)
        stats["disk_pct"] = disk.percent
    except Exception:
        stats["disk_pct"] = None

    # Battery
    try:
        battery = psutil.sensors_battery()
        if battery:
            stats["battery_pct"] = round(battery.percent)
            stats["plugged_in"] = battery.power_plugged
        else:
            stats["battery_pct"] = None
    except Exception:
        stats["battery_pct"] = None

    return stats


async def get_system_info(query: str = "") -> str:
    """Return a spoken-English system status summary."""
    query_lower = query.lower()
    stats = await asyncio.to_thread(_get_system_stats)

    parts = []

    # Selective reporting based on what was asked
    if any(w in query_lower for w in ["battery", "charge", "power", "plugged"]):
        bat = stats.get("battery_pct")
        if bat is not None:
            plug = "plugged in" if stats.get("plugged_in") else "on battery"
            parts.append(f"Battery is at {bat}%, {plug}.")
        else:
            parts.append("I couldn't read battery info — you might be on a desktop.")
        return " ".join(parts)

    if any(w in query_lower for w in ["cpu", "processor", "load"]):
        parts.append(f"CPU is at {stats['cpu']}% usage.")
        return " ".join(parts)

    if any(w in query_lower for w in ["ram", "memory"]):
        parts.append(f"RAM usage is {stats['ram_pct']}% — {stats['ram_used_gb']} GB used of {stats['ram_total_gb']} GB.")
        return " ".join(parts)

    if any(w in query_lower for w in ["disk", "storage", "space"]):
        if stats.get("disk_pct") is not None:
            parts.append(f"Disk is {stats['disk_pct']}% full — {stats['disk_used_gb']} GB of {stats['disk_total_gb']} GB used.")
        return " ".join(parts)

    # Full report
    parts.append(f"CPU is at {stats['cpu']}%.")
    parts.append(f"RAM is at {stats['ram_pct']}% — {stats['ram_used_gb']} of {stats['ram_total_gb']} GB used.")
    if stats.get("disk_pct") is not None:
        parts.append(f"Disk is {stats['disk_pct']}% full.")
    if stats.get("battery_pct") is not None:
        plug = "plugged in" if stats.get("plugged_in") else "on battery"
        parts.append(f"Battery at {stats['battery_pct']}%, {plug}.")

    return " ".join(parts)
