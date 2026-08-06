"""
tools/tool_subagent.py — Sadaf Tool Subagent (Autonomous)

Autonomous executor with:
- Full tool manifest (lives here, not in orchestrator)
- Parameter validation before execution
- Returns need_clarification back to orchestrator if params are missing
- speak_fn wiring for tools like reminder/timer
- Always passes full original user_query to tools (never paraphrased)
"""
import json
import asyncio
import pyperclip
from typing import Dict, Any, Optional, Callable

from config import SUBAGENT_MODEL, PRIORITY_AGENT
from llm_proxy import llm_proxy
from tools.registry import TOOL_REGISTRY
from tools.web_search import read_web_link


TOOL_SELECTION_PROMPT = """\
You are the Tool Subagent. Select the BEST tool for the fully resolved user intent.

AVAILABLE TOOLS:
{manifest}

FULLY RESOLVED USER INTENT (use this — the orchestrator already resolved all context):
{synthesized_intent}

ORIGINAL RAW USER QUERY (for reference only):
{user_query}

RULES:
1. Use ONLY tools from the list above. NEVER invent tools.
2. If no tool fits, set tool_name to null and status to "no_tool".
3. The RESOLVED INTENT is your primary input — it is a complete, unambiguous instruction.
4. Validate that the resolved intent has enough info to run the selected tool:
   - For "set_reminder": must include WHEN (time, day, or relative duration). If missing → need_clarification.
   - For "set_timer": must include a duration. If missing → need_clarification.
   - For "control_volume": must include direction/level. If missing → need_clarification.
   - For "launch_app": must include an app name. If missing → need_clarification.
   - All other tools: ambiguity is fine — proceed.
5. For the "query" field, pass the FULLY RESOLVED USER INTENT verbatim.

Output ONLY a valid JSON object:
{{
  "tool_name": "tool_name_here" | null,
  "query": "the fully resolved intent string",
  "status": "ready" | "need_clarification" | "no_tool",
  "clarification_message": "What specific info is still missing? (only for need_clarification)"
}}
"""


class ToolSubagent:
    def __init__(self, speak_fn: Optional[Callable] = None):
        self._speak_fn = speak_fn

        # Build tool map and manifest from registry
        self.tools_map = {t.name: t for t in TOOL_REGISTRY}

        # Add read_web_link as an internal utility
        self.tools_map["read_web_link"] = type("Tool", (), {
            "name": "read_web_link",
            "description": "Reads the text content of a given URL. Pass the URL as the query.",
            "tool_fn": read_web_link,
            "is_async": True,
            "needs_speak_fn": False,
        })()

        # Build manifest for the prompt (only user-facing tools, not read_web_link)
        self.manifest = "\n".join(
            f'- "{name}": {t.description}'
            for name, t in self.tools_map.items()
            if name != "read_web_link"
        )

    def set_speak_fn(self, speak_fn: Callable):
        """Allow main.py to wire the TTS callback after init."""
        self._speak_fn = speak_fn

    def get_short_capability_names(self) -> str:
        """Returns a short comma-separated list of tool names for the orchestrator's lean prompt."""
        names = [
            name for name in self.tools_map
            if name not in ("read_web_link", "pause_listening")
        ]
        return ", ".join(names)

    async def execute(
        self,
        task_description: str,
        synthesized_intent: str,
        user_query: str,
        context: str = "",
        memory_context: str = "",
        user_name: str = "there",
    ) -> Dict[str, Any]:
        """
        Autonomously selects and executes a tool.

        synthesized_intent: complete, unambiguous intent built by the orchestrator
                            from conversation context (e.g. "Set a reminder on Friday
                            at 9pm to go to office").
        user_query:         the raw user utterance (for fallback / reference only).
        memory_context:     the user's full memory context (used by news/search tools
                            for personalization).
        user_name:          the user's first name (for personalized tool output).

        Returns one of:
          {"status": "success",           "result": "...", ...}
          {"status": "need_clarification","clarification_message": "..."}
          {"status": "failure",           "error": "..."}
          {"status": "no_tool",           "error": "No suitable tool found."}
        """
        task_description   = str(task_description)   if task_description   is not None else ""
        synthesized_intent = str(synthesized_intent) if synthesized_intent is not None else ""
        user_query         = str(user_query)         if user_query         is not None else ""

        # The synthesized intent is the primary input for tool selection
        effective_query = synthesized_intent or user_query

        prompt = TOOL_SELECTION_PROMPT.format(
            manifest=self.manifest,
            synthesized_intent=effective_query,
            user_query=user_query,
        )

        try:
            raw = await llm_proxy.call(
                model=SUBAGENT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                priority=PRIORITY_AGENT,
                temperature=0.0,
            )
            decision = json.loads(raw)
        except Exception as e:
            return {"status": "failure", "error": f"Tool selection reasoning failed: {e}"}

        tool_name = decision.get("tool_name")
        tool_query = decision.get("query", user_query)  # fallback to original
        status = decision.get("status", "ready")
        clarification_message = decision.get("clarification_message", "")

        # — Clarification needed — return back to orchestrator
        if status == "need_clarification":
            return {
                "status": "need_clarification",
                "clarification_message": clarification_message or "Could you give me a bit more detail?",
            }

        # — No suitable tool —
        if status == "no_tool" or not tool_name:
            return {
                "status": "no_tool",
                "error": "I don't have a tool that can handle this request.",
            }

        # — Unknown tool name (safety check) —
        if tool_name not in self.tools_map:
            return {
                "status": "failure",
                "error": f"Unknown tool requested: {tool_name}",
            }

        tool_entry = self.tools_map[tool_name]

        # ─ Announce action (speak while the tool runs, no extra latency) ─────────
        announcement = getattr(tool_entry, "announcement", "")
        if announcement and self._speak_fn:
            # Fire-and-don't-await: the announcement TTS runs while the
            # underlying API call (news/weather/search) is in-flight.
            asyncio.create_task(self._speak_fn(announcement))

        # ─ Execute ──────────────────────────────────────────────────────────────────
        # Determine if this tool accepts context extras (e.g. memory, user_name)
        needs_context = getattr(tool_entry, "needs_context", False)
        try:
            # Wire speak_fn if the tool needs TTS callbacks (reminder, timer)
            needs_speak = getattr(tool_entry, "needs_speak_fn", False)
            if needs_speak and self._speak_fn:
                if getattr(tool_entry, "is_async", True):
                    result = await tool_entry.tool_fn(tool_query, speak_fn=self._speak_fn)
                else:
                    result = await asyncio.to_thread(
                        tool_entry.tool_fn, tool_query, self._speak_fn
                    )
            elif needs_context:
                # Tools that opt-in to memory context (e.g. get_news)
                if getattr(tool_entry, "is_async", True):
                    result = await tool_entry.tool_fn(
                        tool_query,
                        memory_context=memory_context,
                        user_name=user_name,
                    )
                else:
                    result = await asyncio.to_thread(
                        tool_entry.tool_fn, tool_query,
                        memory_context=memory_context,
                        user_name=user_name,
                    )
            elif getattr(tool_entry, "is_async", True):
                result = await tool_entry.tool_fn(tool_query)
            else:
                result = await asyncio.to_thread(tool_entry.tool_fn, tool_query)

            # Auto-save rich results to clipboard
            clipboard_updated = False
            if tool_name in ("web_search", "get_news", "read_web_link") and result:
                pyperclip.copy(str(result))
                clipboard_updated = True

            return {
                "status": "success",
                "result": str(result),
                "clipboard_updated": clipboard_updated,
                "tool_used": tool_name,
            }

        except Exception as e:
            return {
                "status": "failure",
                "error": f"Tool '{tool_name}' encountered an error: {e}",
            }
