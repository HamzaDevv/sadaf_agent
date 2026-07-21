"""
tools/registry.py — Sadaf Jarvis Tool Registry

Defines the available tools and their metadata.
"""
from dataclasses import dataclass
from typing import Callable

# ── Tool imports ─────────────────────────────────────────────────────────────
from tools.web_search import web_search
from tools.news_tool import get_news
from tools.weather_tool import get_weather
from tools.datetime_tool import get_datetime
from tools.reminder import set_reminder
from tools.countdown import get_countdown
from tools.system_info import get_system_info
from tools.app_launcher import launch_app
from tools.clipboard_tool import clipboard_action
from tools.screenshot_tool import take_screenshot
from tools.volume_control import control_volume
from tools.calculator import calculate
from tools.timer_tool import set_timer
from tools.pause_tool import pause_listening
from brain.vision import analyze_scene

@dataclass
class ToolEntry:
    name: str
    description: str
    tool_fn: Callable
    announcement: str = ""
    is_async: bool = True
    needs_speak_fn: bool = False
    consolidate_memory: bool = True
    needs_synthesis: bool = False

async def _camera_with_privacy(query: str, speak_fn: Callable = None) -> str:
    return await analyze_scene(query)

# ── TOOL REGISTRY ─────────────────────────────────────────────────────────────
TOOL_REGISTRY: list[ToolEntry] = [
    ToolEntry(
        name="set_reminder",
        description="Schedule a reminder (e.g. 'remind me in 10 minutes to drink water').",
        tool_fn=set_reminder,
        announcement="Sure, let me set that reminder for you.",
        needs_speak_fn=True,
    ),
    ToolEntry(
        name="set_timer",
        description="Set a countdown timer (e.g. 'set a timer for 5 minutes').",
        tool_fn=set_timer,
        announcement="Starting your timer now.",
        needs_speak_fn=True,
    ),
    ToolEntry(
        name="get_datetime",
        description="Get the current time, date, day of week, or year.",
        tool_fn=get_datetime,
        announcement="",
        is_async=False,
        needs_synthesis=True,
    ),
    ToolEntry(
        name="get_countdown",
        description="Calculate days remaining until an event or date (e.g. 'days until Friday', 'countdown to Christmas').",
        tool_fn=get_countdown,
        announcement="Let me check that for you.",
        needs_synthesis=True,
    ),
    ToolEntry(
        name="calculate",
        description="Evaluate a mathematical expression (e.g. 'what is 15 percent of 50', '2 plus 2').",
        tool_fn=calculate,
        announcement="",
        is_async=False,
        needs_synthesis=True,
    ),
    ToolEntry(
        name="get_system_info",
        description="Check battery level, CPU usage, RAM, or disk space.",
        tool_fn=get_system_info,
        announcement="Running a quick system scan.",
        consolidate_memory=False,
        needs_synthesis=True,
    ),
    ToolEntry(
        name="control_volume",
        description="Mute, unmute, or change system volume level.",
        tool_fn=control_volume,
        announcement="",
    ),
    ToolEntry(
        name="launch_app",
        description="Open a macOS application (e.g. 'open Spotify', 'launch Chrome').",
        tool_fn=launch_app,
        announcement="Opening that for you.",
    ),
    ToolEntry(
        name="clipboard_action",
        description="Read what is currently copied on the clipboard, or copy new text to it.",
        tool_fn=clipboard_action,
        announcement="Checking your clipboard.",
        consolidate_memory=False,
    ),
    ToolEntry(
        name="take_screenshot",
        description="Take a screenshot of the computer screen and optionally analyze what is on it.",
        tool_fn=take_screenshot,
        announcement="Taking a screenshot now.",
        consolidate_memory=False,
    ),
    ToolEntry(
        name="camera_tool",
        description="Use the webcam to look at something, see what the user is holding, or identify an object in front of the camera.",
        tool_fn=_camera_with_privacy,
        announcement="Let me take a look at that.",
        consolidate_memory=False,
        needs_synthesis=True,
    ),
    ToolEntry(
        name="get_weather",
        description="Check current weather, temperature, or rain forecast.",
        tool_fn=get_weather,
        announcement="Let me check the weather for you.",
        consolidate_memory=False,
        needs_synthesis=True,
    ),
    ToolEntry(
        name="get_news",
        description="Fetch latest news headlines, optionally by topic.",
        tool_fn=get_news,
        announcement="Pulling up the latest news.",
        consolidate_memory=False,
        needs_synthesis=True,
    ),
    ToolEntry(
        name="web_search",
        description="Search the internet or google something to find facts, information, or answers to questions.",
        tool_fn=web_search,
        announcement="Let me check that online for you.",
        consolidate_memory=False,
        needs_synthesis=True,
    ),
    ToolEntry(
        name="pause_listening",
        description="Pause or hold on. Used when the user says 'wait a second', 'hold on', or wants the AI to stop listening temporarily.",
        tool_fn=pause_listening,
        announcement="Alright, I'll be right here. Just say 'Sadaf' when you're ready.",
        is_async=False,
    ),
]
