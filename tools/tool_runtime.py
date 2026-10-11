"""
tools/tool_runtime.py — Sadaf V7 Deterministic Tool Runtime

Executes tools requested by the AgentCore. Handles schema matching (via kwargs),
synchronous vs asynchronous execution, and captures observations and errors
to return back to the reasoning loop.
"""

import json
import traceback
from typing import Dict, Any, Callable
from tools.registry import TOOL_REGISTRY

class ToolRuntime:
    def __init__(self):
        self.tools = {t.name: t for t in TOOL_REGISTRY}

    async def execute(self,
                      tool_name: str,
                      parameters: Dict[str, Any],
                      speak_fn: Callable = None,
                      user_name: str = "User",
                      memory_context: str = "") -> str:
        """
        Executes the requested tool with the provided parameters.
        Returns a string observation representing the result or an error message.
        """
        if tool_name not in self.tools:
            return f"ERROR: Tool '{tool_name}' not found. Available tools: {', '.join(self.tools.keys())}"

        tool_entry = self.tools[tool_name]

        # Prepare kwargs
        kwargs = dict(parameters)

        # Inject framework dependencies if the tool requires them
        if tool_entry.needs_speak_fn and speak_fn:
            kwargs["speak_fn"] = speak_fn
        if tool_entry.needs_context:
            kwargs["user_name"] = user_name
            kwargs["memory_context"] = memory_context

        print(f"[ToolRuntime] Executing {tool_name} with {kwargs}")

        try:
            if tool_entry.is_async:
                result = await tool_entry.tool_fn(**kwargs)
            else:
                result = tool_entry.tool_fn(**kwargs)

            # Convert result to string observation
            if result is None:
                return "Success (no output returned)."
            if isinstance(result, str):
                return result

            return json.dumps(result)

        except TypeError as e:
            # Usually happens if DeepSeek passes arguments that don't map to the function signature
            err_msg = f"ERROR: Parameter mismatch for '{tool_name}'. Details: {str(e)}"
            print(f"[ToolRuntime] {err_msg}")
            return err_msg

        except Exception as e:
            traceback.print_exc()
            err_msg = f"ERROR: Execution of '{tool_name}' failed. Details: {str(e)}"
            print(f"[ToolRuntime] {err_msg}")
            return err_msg

# Singleton instance
tool_runtime = ToolRuntime()
