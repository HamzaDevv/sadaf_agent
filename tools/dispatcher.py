"""
tools/dispatcher.py — Sadaf Jarvis Tool Dispatcher (Agentic Edition)

Uses an LLM (llama-3.1-8b-instant) to determine which tool to run
based on a description of the tools. No more regex/keyword matching!
"""
import asyncio
import json
from dataclasses import dataclass
from typing import Callable, Optional

from config import PRIVACY_MODE, CHAT_MODEL, PRIORITY_AGENT
from groq_proxy import groq_proxy

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


# ── Tool entry dataclass ──────────────────────────────────────────────────────
@dataclass
class ToolMatch:
    announcement: str
    tool_fn: Callable
    tool_query: str
    is_async: bool = True
    needs_speak_fn: bool = False
    consolidate_memory: bool = True
    needs_synthesis: bool = False

@dataclass
class ToolEntry:
    name: str
    description: str
    tool_fn: Callable
    announcement: str
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


# ── Agentic Dispatcher ────────────────────────────────────────────────────────
class ToolDispatcher:
    """Routes user queries using an LLM to select the best tool."""

    def __init__(self):
        self.tools_map = {t.name: t for t in TOOL_REGISTRY}
        # Build tool description string for prompt
        self.tool_descriptions = "\n".join(
            f'- "{t.name}": {t.description}' for t in TOOL_REGISTRY
        )

    async def synthesize_response(self, user_query: str, tool_result: str) -> str:
        """Subagent behavior: use an LLM to synthesize a natural answer from raw tool output."""
        system_prompt = """You are Sadaf, a conversational AI.
A background tool just gathered some information to answer the user's query.
Based on the tool's output, provide a direct, natural, and concise answer to the user's query.
Do NOT mention that you used a tool. Do NOT describe the entire tool output if it's not relevant. Just answer the query as naturally as possible, acting as a witty, smart best friend."""
        prompt = f"USER QUERY: {user_query}\n\nTOOL OUTPUT:\n{tool_result}"
        try:
            raw = await groq_proxy.call(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                priority=PRIORITY_AGENT,
                temperature=0.3,
                max_tokens=150
            )
            from utils import strip_think_tags
            raw_clean = strip_think_tags(raw) if raw else ""
            return raw_clean.strip() if raw_clean else tool_result
        except Exception:
            return tool_result

    async def route(self, user_text: str) -> Optional[ToolMatch]:
        """
        Agentic routing: Ask LLM which tool to use.
        Returns ToolMatch or None.
        """
        system_prompt = f"""You are a tool orchestration engine.
Based on the user's input, decide if a specific tool should be called.
If a tool is needed, extract the exact query or parameter that the tool needs.
For example, if the user says "search the web for artificial intelligence news", the tool_name is "web_search" and the tool_query is "artificial intelligence news".

Available tools:
{self.tool_descriptions}

Output ONLY valid JSON in this format:
{{"tool_name": "name_of_tool", "tool_query": "extracted_query_string"}}
or if no tool applies:
{{"tool_name": null, "tool_query": null}}
"""
        try:
            raw = await groq_proxy.call(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                priority=PRIORITY_AGENT,
                temperature=0.0,
                max_tokens=80,
                response_format={"type": "json_object"},
            )
            if not raw:
                return None
            
            parsed = json.loads(raw)
            tool_name = parsed.get("tool_name")
            tool_query = parsed.get("tool_query", "")
            
            if not tool_name or tool_name not in self.tools_map:
                return None

            entry = self.tools_map[tool_name]

            announcement = entry.announcement
            # PRIVACY_MODE: camera asks permission instead of announcing
            if entry.tool_fn is _camera_with_privacy and PRIVACY_MODE:
                announcement = "May I use the camera to take a look?"

            return ToolMatch(
                announcement=announcement,
                tool_fn=entry.tool_fn,
                tool_query=tool_query,
                is_async=entry.is_async,
                needs_speak_fn=entry.needs_speak_fn,
                consolidate_memory=entry.consolidate_memory,
            )
        except Exception as e:
            print(f"[Dispatcher] Error: {e}")
            return None


# Singleton
dispatcher = ToolDispatcher()
