"""
tools/app_launcher.py — Sadaf Jarvis App Launcher Tool

Opens macOS applications by name using the `open` shell command.
Supports fuzzy matching so "open spotify" finds "Spotify.app".
"""
import asyncio
import subprocess

# Known app aliases → actual macOS app names
APP_ALIASES: dict[str, str] = {
    "spotify": "Spotify",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "safari": "Safari",
    "firefox": "Firefox",
    "vscode": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "code": "Visual Studio Code",
    "terminal": "Terminal",
    "iterm": "iTerm",
    "slack": "Slack",
    "discord": "Discord",
    "whatsapp": "WhatsApp",
    "telegram": "Telegram",
    "zoom": "zoom.us",
    "finder": "Finder",
    "notes": "Notes",
    "calendar": "Calendar",
    "mail": "Mail",
    "messages": "Messages",
    "facetime": "FaceTime",
    "photos": "Photos",
    "vlc": "VLC",
    "word": "Microsoft Word",
    "excel": "Microsoft Excel",
    "powerpoint": "Microsoft PowerPoint",
    "teams": "Microsoft Teams",
    "xcode": "Xcode",
    "pycharm": "PyCharm",
    "cursor": "Cursor",
    "notion": "Notion",
    "figma": "Figma",
    "postman": "Postman",
    "settings": "System Preferences",
    "system preferences": "System Preferences",
    "activity monitor": "Activity Monitor",
    "music": "Music",
    "apple music": "Music",
    "maps": "Maps",
    "books": "Books",
    "numbers": "Numbers",
    "pages": "Pages",
    "preview": "Preview",
}


def _extract_app_name(query: str) -> str | None:
    """Extract app name from query like 'open spotify' or 'launch chrome'."""
    query_lower = query.lower()
    # Remove trigger words
    for trigger in ["open", "launch", "start", "run", "go to"]:
        query_lower = query_lower.replace(trigger, "").strip()
    query_lower = query_lower.strip()

    # Direct alias lookup
    if query_lower in APP_ALIASES:
        return APP_ALIASES[query_lower]

    # Partial match
    for alias, app in APP_ALIASES.items():
        if alias in query_lower:
            return app

    # Return cleaned query as-is (might be a valid app name)
    return query_lower.title() if query_lower else None


def _open_app(app_name: str) -> bool:
    """Launch macOS app using the `open -a` command."""
    try:
        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


async def launch_app(query: str) -> str:
    """Open a macOS app and return spoken confirmation."""
    app_name = _extract_app_name(query)
    if not app_name:
        return "I'm not sure which app you want me to open."

    success = await asyncio.to_thread(_open_app, app_name)

    if success:
        return f"Opening {app_name} for you."
    else:
        return f"I couldn't find {app_name}. Make sure it's installed and spelled correctly."
