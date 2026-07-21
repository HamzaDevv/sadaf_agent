"""
tools/tool_subagent.py — Sadaf Jarvis Tool Subagent
Executes tools chosen by Boss Orchestrator, saves heavy context to clipboard.
"""
import json
import asyncio
import pyperclip
from typing import Dict, Any, Optional

from config import SUBAGENT_MODEL, PRIORITY_AGENT
from groq_proxy import groq_proxy
from tools.registry import TOOL_REGISTRY
from tools.web_search import read_web_link

class ToolSubagent:
    def __init__(self):
        # Build tool descriptions for the Boss agent to know what this subagent can do
        self.tools_map = {t.name: t for t in TOOL_REGISTRY}
        
        # Add read_web_link manually since it's an internal utility for the subagent
        self.tools_map["read_web_link"] = type('Tool', (), {
            'name': 'read_web_link',
            'description': 'Reads the text content of a given URL. Pass the URL as the query.',
            'tool_fn': read_web_link,
            'is_async': True
        })()
        
        self.manifest = "\n".join(
            f'- "{name}": {t.description}' for name, t in self.tools_map.items()
        )

    def get_manifest(self) -> str:
        """Returns the list of tools for the Boss prompt."""
        return self.manifest

    def get_capabilities(self, query: str = "") -> str:
        """Returns a natural language list of capabilities."""
        return "I can: " + ", ".join(name for name in self.tools_map.keys() if name != "read_web_link")

    async def execute(self, task_description: str, user_query: str, context: str = "") -> Dict[str, Any]:
        """
        Executes a tool based on the Boss's task description.
        Returns a structured dictionary with status, result, and raw_data.
        """
        # If the boss asks for capabilities, bypass LLM routing
        if "capability" in task_description.lower() or "capabilities" in task_description.lower():
            return {
                "status": "success",
                "result": self.get_capabilities(),
                "clipboard_updated": False,
                "raw_data": ""
            }

        prompt = f"""You are the Tool Subagent.
Your job is to select the BEST tool to accomplish the assigned task.
AVAILABLE TOOLS:
{self.manifest}

TASK DESCRIPTION FROM BOSS: {task_description}
USER QUERY: {user_query}

Choose ONE tool that best fits the task.
Output ONLY a JSON object with:
- "tool_name": string (must match a tool name exactly)
- "query": string (the argument to pass to the tool, e.g. the search query, app name, or URL)
If no tool fits, output "tool_name": null.
"""
        try:
            raw = await groq_proxy.call(
                model=SUBAGENT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                priority=PRIORITY_AGENT,
                temperature=0.0
            )
            decision = json.loads(raw)
            tool_name = decision.get("tool_name")
            tool_query = decision.get("query", user_query)
            
            if not tool_name or tool_name not in self.tools_map:
                return {
                    "status": "failure",
                    "error": f"Could not find an appropriate tool to handle the task. LLM requested: {tool_name}"
                }
                
            tool_entry = self.tools_map[tool_name]
            
            # Execute the tool
            try:
                if getattr(tool_entry, "is_async", True):
                    result = await tool_entry.tool_fn(tool_query)
                else:
                    result = await asyncio.to_thread(tool_entry.tool_fn, tool_query)
                    
                # Auto-save rich data to clipboard
                clipboard_updated = False
                if tool_name in ["web_search", "get_news", "read_web_link"] and result:
                    pyperclip.copy(str(result))
                    clipboard_updated = True
                    
                return {
                    "status": "success",
                    "result": str(result),
                    "clipboard_updated": clipboard_updated,
                    "raw_data": str(result),
                    "tool_used": tool_name
                }
                
            except Exception as e:
                return {
                    "status": "failure",
                    "error": f"Tool {tool_name} failed: {e}"
                }
                
        except Exception as e:
            return {
                "status": "failure",
                "error": f"Tool Subagent reasoning failed: {e}"
            }
