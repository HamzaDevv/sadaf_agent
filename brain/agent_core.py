"""
brain/agent_core.py — Sadaf V7 Agent Core (DeepSeek Context)

Handles complex planning and function calling when the intent requires it.
Uses static prompt prefixing to guarantee 100% cache hits on DeepSeek's API.
Default 2-step loop (call tool -> observation -> generate response), max 3 steps.
"""
import json
import asyncio
from typing import Dict, Any, List

from config import BOSS_MODEL, PRIORITY_AGENT, BUFFER_SIZE, AI_NAME
from llm_proxy import llm_proxy
from tools.registry import TOOL_REGISTRY
from tools.tool_runtime import tool_runtime
from memory.memory_agent import MemoryAgent
from memory.compressor import context_compressor
from memory.consolidator import MemoryConsolidator

SYSTEM_PROMPT_TEMPLATE = """\
You are {ai_name}, a JARVIS-like AI assistant speaking DIRECTLY to {user_name}.

ABSOLUTE RULES:
1. Speak in 1st/2nd person ONLY ("I", "you", "your"). NEVER use 3rd person.
2. SPOKEN OUTPUT: Any text you output directly will be spoken out loud via TTS. Keep it SHORT, NATURAL, and CONVERSATIONAL (1-3 sentences max).
3. If you decide to call a tool, call the tool directly using the provided tool definitions.
4. DO NOT hallucinate tools. If it is not in the list, you cannot do it.
5. Do not use markdown like *asterisks* or # hashes.
6. If a tool returns an error or says it couldn't perform the task, relay that failure to the user. DO NOT guess, make up, or hallucinate the answer.
"""

class AgentCore:
    def __init__(
        self,
        memory_agent: MemoryAgent,
        consolidator: MemoryConsolidator,
        speaker_subagent,  # Passed for compatibility/fallback, bypassed for text
    ):
        self.memory = memory_agent
        self.consolidator = consolidator
        self.speaker = speaker_subagent

        self.conversation_buffer: list = []
        self._background_tasks: list = []

        self.tools_manifest = self._build_tool_manifest()

    def _build_tool_manifest(self) -> List[Dict[str, Any]]:
        manifest = []
        for t in TOOL_REGISTRY:
            if t.name == "list_capabilities":
                continue
            manifest.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters
                }
            })
        return manifest

    def _spawn_consolidation(self, user_id: str, user_text: str, ai_response: str):
        self._background_tasks = [t for t in self._background_tasks if not t.done()]
        task = asyncio.create_task(
            self.consolidator.consolidate(user_id, user_text, ai_response)
        )
        self._background_tasks.append(task)

    def _update_buffer(self, user_text: str, ai_response: str):
        self.conversation_buffer.append(f"User: {user_text}")
        self.conversation_buffer.append(f"AI: {ai_response}")
        if len(self.conversation_buffer) > BUFFER_SIZE * 2:
            self.conversation_buffer = self.conversation_buffer[-(BUFFER_SIZE * 2):]

    def _extract_user_name(self, memory_context: str) -> str:
        for line in memory_context.splitlines():
            if "full_name:" in line or "name:" in line:
                val = line.split(":", 1)[-1].strip()
                if val and val.lower() not in ("none", ""):
                    return val.split()[0]
        return "there"

    async def process(self, user_id: str, user_text: str, emotion: str = "neutral", intent: str = "converse") -> str:
        """
        V7 main execution loop.
        """
        memory_context_raw = await self.memory.retrieve_context(
            user_id, user_text, buffer=self.conversation_buffer
        )
        user_display_name = self._extract_user_name(memory_context_raw)

        memory_context = context_compressor.compress_memory(memory_context_raw)
        recent_history = context_compressor.compress_history(self.conversation_buffer)

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            ai_name=AI_NAME,
            user_name=user_display_name
        )

        context_msg = (
            f"MEMORY CONTEXT:\n{memory_context}\n\n"
            f"RECENT HISTORY:\n{recent_history}"
        )

        # Static prompt prefixing for max DeepSeek cache hits
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": context_msg},
            {"role": "user", "content": user_text}
        ]

        max_steps = 3
        current_step = 0
        final_spoken = ""

        while current_step < max_steps:
            current_step += 1

            response = await llm_proxy.call(
                model=BOSS_MODEL,
                messages=messages,
                priority=PRIORITY_AGENT,
                temperature=0.2,
                tools=self.tools_manifest
            )

            if not response:
                final_spoken = "My cognitive circuits are overloaded. Please try again."
                break

            # Direct text response
            if isinstance(response, str):
                final_spoken = response
                break

            # Tool call response
            if hasattr(response, "tool_calls") and response.tool_calls:
                # Add assistant message with tool calls
                msg_dict = {"role": "assistant", "content": response.content or "", "tool_calls": []}

                for tc in response.tool_calls:
                    tc_dict = {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    msg_dict["tool_calls"].append(tc_dict)
                messages.append(msg_dict)

                # Execute tools and add tool observations
                for tc in response.tool_calls:
                    tool_name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except Exception:
                        args = {}

                    obs = await tool_runtime.execute(
                        tool_name=tool_name,
                        parameters=args,
                        user_name=user_display_name,
                        memory_context=memory_context
                    )

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tool_name,
                        "content": obs
                    })
                continue

            # Fallback for unexpected object response without tool calls
            final_spoken = getattr(response, "content", "I am not sure what to say.") or "I am not sure what to say."
            break

        # Strip markdown for TTS
        final_spoken = final_spoken.replace("*", "").replace("#", "")

        self._update_buffer(user_text, final_spoken)
        self._spawn_consolidation(user_id, user_text, final_spoken)

        return final_spoken
