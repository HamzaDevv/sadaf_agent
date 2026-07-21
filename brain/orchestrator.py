"""
brain/orchestrator.py — Sadaf Boss Orchestrator
The central reasoning engine for the Antigravity 2.0 multi-agent architecture.
Delegates tasks to Tool, Memory, and Speaker subagents.
"""
import json
import pyperclip
from typing import Optional

from config import BOSS_MODEL, PRIORITY_AGENT, AI_NAME
from groq_proxy import groq_proxy

from memory.memory_agent import MemoryAgent
from memory.consolidator import MemoryConsolidator
from tools.tool_subagent import ToolSubagent
from brain.speaker_agent import SpeakerSubagent

class BossOrchestrator:
    def __init__(
        self,
        memory_agent: MemoryAgent,
        tool_subagent: ToolSubagent,
        speaker_subagent: SpeakerSubagent,
        consolidator: MemoryConsolidator
    ):
        self.memory = memory_agent
        self.tool = tool_subagent
        self.speaker = speaker_subagent
        self.consolidator = consolidator
        
        # We keep a small conversation buffer for the Boss
        self.conversation_buffer = []
        
    def _get_clipboard(self) -> str:
        """Safely gets clipboard contents."""
        try:
            return pyperclip.paste()[:2000] # Limit to 2000 chars to save tokens
        except:
            return ""

    def _extract_user_name(self, memory_context: str) -> str:
        """Extracts the real user name from identity context if available."""
        for line in memory_context.splitlines():
            if "full_name:" in line or "name:" in line:
                val = line.split(":", 1)[-1].strip()
                if val and val.lower() != "none":
                    return val.split()[0]
        return "User"

    async def process(self, user_id: str, user_text: str, emotion: str = "neutral", intent: str = "chat") -> str:
        """
        The main Antigravity 2.0 execution loop.
        Returns the final spoken string to be passed to TTS.
        """
        # 1. Gather Context
        memory_context = await self.memory.retrieve_context(user_id, user_text, buffer=self.conversation_buffer)
        clipboard = self._get_clipboard()
        user_display_name = self._extract_user_name(memory_context)
        
        recent_history = "\n".join(self.conversation_buffer[-4:])
        
        system_prompt = f"""You are {AI_NAME}, the Boss Orchestrator of a JARVIS-like multi-agent system.
Your job is to decide how to respond to the user's query.

CRITICAL DIRECT CONVERSATION & IDENTITY RULES:
1. You are speaking DIRECTLY to the user (whose name is {user_display_name}). Always speak in the 1st/2nd person ("I", "you", "your").
2. NEVER speak about the user in the 3rd person (NEVER say "the user", "he", "she", or "{user_display_name} is asking...").
3. When the user asks you to have a conversation, ask questions, or learn about them, respond DIRECTLY to them with engaging questions!

AVAILABLE SUBAGENTS:
{self.tool.get_manifest()}
- "speaker_subagent": Converts your direct responses into spoken output. Use this if no tools are needed.

CONTEXT:
Memory:
{memory_context}

Clipboard:
{clipboard}

Recent Conversation:
{recent_history}

DECISION REQUIRED:
Output ONLY a JSON object with:
{{
  "reasoning": "Explain why you are delegating to this subagent",
  "delegate_to": "tool_subagent" OR "speaker_subagent",
  "task_for_subagent": "Detailed instructions if tool_subagent, else null",
  "direct_response": "Your direct 1st/2nd-person conversational response TO THE USER if speaker_subagent, else null"
}}
"""

        # 2. Boss Reasoning
        try:
            raw = await groq_proxy.call(
                model=BOSS_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"USER: {user_text}"}
                ],
                response_format={"type": "json_object"},
                priority=PRIORITY_AGENT,
                temperature=0.2
            )
            decision = json.loads(raw)
            
            delegate_to = decision.get("delegate_to")
            
            if delegate_to == "tool_subagent":
                # Execute tool
                tool_res = await self.tool.execute(
                    task_description=decision.get("task_for_subagent", user_text),
                    user_query=user_text,
                    context=clipboard
                )
                
                # If tool succeeded, send raw result to Speaker
                if tool_res["status"] == "success":
                    speaker_content = tool_res["result"]
                else:
                    speaker_content = f"Tool execution failed: {tool_res.get('error')}"
            else:
                # Direct response
                speaker_content = decision.get("direct_response", "I'm not sure how to respond to that.")
                
            # 3. Speaker formatting
            final_spoken = await self.speaker.speak(
                content=speaker_content,
                user_name=user_display_name,
                emotion=emotion
            )
            
            # 4. Update Buffers and Memory
            self.conversation_buffer.append(f"User: {user_text}")
            self.conversation_buffer.append(f"AI: {final_spoken}")
            
            # Background consolidation
            import asyncio
            asyncio.create_task(
                self.consolidator.consolidate(user_id, user_text, final_spoken)
            )
            
            return final_spoken

        except Exception as e:
            print(f"[BossOrchestrator] Error: {e}")
            return "Sorry, my systems got a bit tangled up."
