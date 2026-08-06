"""
brain/orchestrator.py — Sadaf Boss Orchestrator (Central Hub + Intent Synthesizer)

Architecture:
- Lean router: decides routing AND synthesizes a clear intent string for tool subagent
- Intent Synthesis: the boss LLM uses conversation buffer to resolve ambiguous/short
  user utterances into a single complete natural-language intent string
  (e.g. "Monday" → "Set a reminder on Monday at 9am to go to office")
- Clarification state: tracks pending tool + context across turns, so the next
  user reply is merged into the full assembled intent rather than treated as a new query
- All results always flow back through orchestrator → speaker
- Buffer size driven by config.BUFFER_SIZE
"""
import asyncio
import json
import re
import pyperclip
from typing import Optional

from config import BOSS_MODEL, PRIORITY_AGENT, AI_NAME, BUFFER_SIZE, BOSS_MEMORY_MAX_CHARS, BOSS_HISTORY_MAX_TURNS
from llm_proxy import llm_proxy

from memory.memory_agent import MemoryAgent
from memory.consolidator import MemoryConsolidator
from tools.tool_subagent import ToolSubagent
from brain.speaker_agent import SpeakerSubagent


# ── Boss Routing + Intent Synthesis Prompt ────────────────────────────────────
# The boss does TWO things at once:
# 1. Decides routing (tool / vision / clarify / speak)
# 2. Synthesizes a COMPLETE intent string from conversation context
#    so the tool subagent always receives a clear, unambiguous query.

BOSS_PROMPT_TEMPLATE = """\
You are {ai_name}, a JARVIS-like AI assistant, speaking DIRECTLY to {user_name}.

ABSOLUTE RULES:
1. Speak in 1st/2nd person ONLY ("I", "you", "your"). NEVER use 3rd person.
2. You have EXACTLY these capabilities — NEVER invent or mention any others:
   {capability_names}
3. Do NOT hallucinate tools. If it is not in the list above, you cannot do it.
4. SPOKEN OUTPUT RULE: Any text in "direct_response" or "clarify_question" must be
   SHORT, NATURAL, CONVERSATIONAL — like a real person talking (1–3 sentences max).
   Never produce bullet lists or lengthy paragraphs in those fields.

ROUTING DECISION — choose ONE:
- "tool"   → user needs an action/capability. ALWAYS synthesize the full intent.
- "vision" → user wants the camera ("what am I holding", "look at this")
- "clarify"→ a tool is clearly needed BUT key information is still missing
- "speak"  → pure conversation, greetings, or anything requiring no tool

{clarification_context}

CONTEXT:
Memory:
{memory_context}

Recent Conversation:
{recent_history}

INTENT SYNTHESIS (required for "tool" and "vision"):
Look at the FULL conversation history and the user's current message.
Combine them into ONE complete, unambiguous natural-language sentence that fully
captures what the user wants.

Examples:
  History: "set a reminder to go to office" → clarified: "Friday" → clarified: "9pm"
  synthesized_intent → "Set a reminder on Friday at 9pm to go to office"

  History: "what can you do?" → current: "only this?"
  synthesized_intent → "List all your capabilities"

Output ONLY a valid JSON object:
{{
  "reasoning": "brief reasoning",
  "delegate_to": "tool" | "vision" | "clarify" | "speak",
  "synthesized_intent": "complete natural-language intent sentence" (required for tool/vision, else null),
  "task_for_subagent": "short task label for tool subagent" (required for tool/vision, else null),
  "direct_response": "your spoken response in 1-3 short natural sentences" (required for speak, else null),
  "clarify_question": "one short spoken question asking for the missing info" (required for clarify, else null)
}}
"""

CLARIFICATION_CONTEXT_TEMPLATE = """\
⚠️  CLARIFICATION IN PROGRESS:
The user is currently answering a clarification question about a previous request.
- Original request context: {original_context}
- Clarification question that was asked: {question_asked}
- User's new reply (clarification answer): {user_text}

Combine the original context with the user's clarification to build the synthesized_intent.
If still missing info, delegate_to "clarify" again.
"""


class BossOrchestrator:
    def __init__(
        self,
        memory_agent: MemoryAgent,
        tool_subagent: ToolSubagent,
        speaker_subagent: SpeakerSubagent,
        consolidator: MemoryConsolidator,
    ):
        self.memory = memory_agent
        self.tool = tool_subagent
        self.speaker = speaker_subagent
        self.consolidator = consolidator

        # Conversation buffer — size controlled by config
        self.conversation_buffer: list = []

        # Clarification state — tracks pending tool request across turns
        # Structure: {"original_context": str, "question_asked": str} | None
        self._pending_clarification: Optional[dict] = None

        # Track the last tool used (set inside _execute_delegation)
        self._last_tool_used: Optional[str] = None

        # Background consolidation tasks — tracked so they can be cancelled on shutdown
        self._background_tasks: list = []

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _spawn_consolidation(self, user_id: str, user_text: str, ai_response: str):
        """Create a background consolidation task and track it for clean shutdown."""
        # Prune completed tasks from the list first
        self._background_tasks = [t for t in self._background_tasks if not t.done()]
        task = asyncio.create_task(
            self.consolidator.consolidate(user_id, user_text, ai_response)
        )
        self._background_tasks.append(task)

    def cancel_background_tasks(self):
        """Cancel all pending background tasks (consolidation, etc.). Call on shutdown."""
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        self._background_tasks.clear()

    def _get_clipboard(self) -> str:
        try:
            return pyperclip.paste()[:2000]
        except Exception:
            return ""

    def _extract_user_name(self, memory_context: str) -> str:
        for line in memory_context.splitlines():
            if "full_name:" in line or "name:" in line:
                val = line.split(":", 1)[-1].strip()
                if val and val.lower() not in ("none", ""):
                    return val.split()[0]
        return "there"

    def _update_buffer(self, user_text: str, ai_response: str):
        self.conversation_buffer.append(f"User: {user_text}")
        self.conversation_buffer.append(f"AI: {ai_response}")
        if len(self.conversation_buffer) > BUFFER_SIZE * 2:
            self.conversation_buffer = self.conversation_buffer[-(BUFFER_SIZE * 2):]

    def _trim_to_budget(self, memory_context: str, recent_history: str) -> tuple[str, str]:
        """
        Hard-caps memory context and recent history to configured limits.
        Trims oldest entries first to preserve most recent context.
        Called before building the boss prompt to prevent token ballooning.
        """
        # Trim memory context: keep last BOSS_MEMORY_MAX_CHARS characters
        if len(memory_context) > BOSS_MEMORY_MAX_CHARS:
            trimmed_mem = memory_context[-BOSS_MEMORY_MAX_CHARS:]
            # Try to start at a clean line boundary
            nl = trimmed_mem.find("\n")
            if nl != -1:
                trimmed_mem = "[...trimmed...]\n" + trimmed_mem[nl + 1:]
            memory_context = trimmed_mem

        # Trim history: keep last BOSS_HISTORY_MAX_TURNS lines
        history_lines = recent_history.splitlines()
        if len(history_lines) > BOSS_HISTORY_MAX_TURNS:
            history_lines = history_lines[-BOSS_HISTORY_MAX_TURNS:]
            recent_history = "\n".join(history_lines)

        return memory_context, recent_history

    # ── Main Processing Loop ──────────────────────────────────────────────────

    async def process(
        self,
        user_id: str,
        user_text: str,
        emotion: str = "neutral",
        intent: str = "converse",
    ) -> str:
        """
        Central hub:
        1. Gather context + clarification state
        2. Boss LLM: route + synthesize intent
        3. Execute tool/vision/clarify/speak
        4. All results return here before speaker
        5. Update buffer + background memory consolidation
        """
        import asyncio

        # 1. Gather Context
        memory_context = await self.memory.retrieve_context(
            user_id, user_text, buffer=self.conversation_buffer
        )
        user_display_name = self._extract_user_name(memory_context)
        recent_history = "\n".join(self.conversation_buffer[-(BUFFER_SIZE):])

        # Apply prompt budget: trim before injecting into boss prompt
        memory_context, recent_history = self._trim_to_budget(memory_context, recent_history)

        # Fast-path: vision_query intent → skip boss LLM routing
        if intent == "vision_query":
            tool_res = await self.tool.execute(
                task_description="Use the camera to answer the user's visual question.",
                synthesized_intent=user_text,
                user_query=user_text,
                context=self._get_clipboard(),
                memory_context=memory_context,
                user_name=user_display_name,
            )
            speaker_content = self._resolve_tool_result(tool_res)
            final_spoken = await self.speaker.speak(
                content=speaker_content,
                user_name=user_display_name,
                emotion=emotion,
            )
            self._update_buffer(user_text, final_spoken)
            self._spawn_consolidation(user_id, user_text, final_spoken)
            return final_spoken

        # 2. Build boss prompt — inject clarification context if pending
        clarification_context = ""
        if self._pending_clarification:
            clarification_context = CLARIFICATION_CONTEXT_TEMPLATE.format(
                original_context=self._pending_clarification["original_context"],
                question_asked=self._pending_clarification["question_asked"],
                user_text=user_text,
            )

        system_prompt = BOSS_PROMPT_TEMPLATE.format(
            ai_name=AI_NAME,
            user_name=user_display_name,
            capability_names=self.tool.get_short_capability_names(),
            memory_context=memory_context,
            recent_history=recent_history or "(none yet)",
            clarification_context=clarification_context,
        )

        # 3. Boss routing + intent synthesis (no 8b fallback for this critical call)
        try:
            raw = await llm_proxy.call(
                model=BOSS_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"USER: {user_text}"},
                ],
                response_format={"type": "json_object"},
                priority=PRIORITY_AGENT,
                temperature=0.2,
                allow_fallback=False,   # ← never downgrade to 8b for routing decisions
            )

            if not raw:
                return await self._speak_fallback(
                    "My cognitive circuits are overloaded — please try again.",
                    user_display_name, emotion,
                )

            if raw.startswith("RATE_LIMIT:"):
                m = re.search(
                    r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)?s?", raw, re.IGNORECASE
                )
                wait = 60
                if m:
                    wait = int(
                        float(m.group(1) or 0) * 3600
                        + float(m.group(2) or 0) * 60
                        + float(m.group(3) or 0)
                    )
                return await self._speak_fallback(
                    f"I'm rate-limited right now. Give me about {wait} seconds.",
                    user_display_name, emotion,
                )

            decision = json.loads(raw)
            delegate_to = decision.get("delegate_to", "speak")

        except Exception as e:
            print(f"[BossOrchestrator] Routing error: {e}")
            return await self._speak_fallback(
                "Sorry, I got tangled up for a moment.", user_display_name, emotion
            )

        # 4. Execute delegation
        self._last_tool_used = None   # reset before each turn
        speaker_content = await self._execute_delegation(
            delegate_to=delegate_to,
            decision=decision,
            user_text=user_text,
            emotion=emotion,
            memory_context=memory_context,
            user_display_name=user_display_name,
        )

        # 5. Speaker formatting — skip if content is already a natural spoken sentence
        # (boss prompt is instructed to output short conversational sentences, so
        # direct_response and clarify_question are already TTS-ready.)
        # Tool results from subagents may still need reformatting UNLESS the tool
        # already produces TTS-ready output (needs_synthesis=False in registry).
        tool_is_tts_ready = False
        if self._last_tool_used:
            entry = self.tool.tools_map.get(self._last_tool_used)
            if entry and not getattr(entry, "needs_synthesis", True):
                tool_is_tts_ready = True

        needs_speaker = delegate_to in ("tool", "vision") and not tool_is_tts_ready
        if needs_speaker:
            final_spoken = await self.speaker.speak(
                content=speaker_content,
                user_name=user_display_name,
                emotion=emotion,
            )
        else:
            # speak / clarify / tts-ready tool — skip speaker LLM
            final_spoken = speaker_content

        # 6. Update buffer + background consolidation
        self._update_buffer(user_text, final_spoken)
        self._spawn_consolidation(user_id, user_text, final_spoken)

        return final_spoken

    # ── Delegation Handlers ───────────────────────────────────────────────────

    async def _execute_delegation(
        self,
        delegate_to: str,
        decision: dict,
        user_text: str,
        emotion: str,
        memory_context: str = "",
        user_display_name: str = "there",
    ) -> str:
        """Handles all delegation paths, returns speaker-ready content."""

        if delegate_to in ("tool", "vision"):
            # Use the synthesized intent (complete, unambiguous) for tool execution
            synthesized_intent = decision.get("synthesized_intent") or user_text
            task_desc = decision.get("task_for_subagent") or user_text

            if delegate_to == "vision":
                synthesized_intent = f"Use the camera to answer: {user_text}"
                task_desc = synthesized_intent

            tool_res = await self.tool.execute(
                task_description=task_desc,
                synthesized_intent=synthesized_intent,   # ← clean resolved query
                user_query=user_text,                    # ← raw original (for reference)
                context=self._get_clipboard(),
                memory_context=memory_context,
                user_name=user_display_name,
            )

            # Track which tool ran (for speaker bypass logic)
            self._last_tool_used = tool_res.get("tool_used")

            result = self._resolve_tool_result(tool_res)

            # Clear clarification state on success or no_tool
            if tool_res.get("status") in ("success", "no_tool"):
                self._pending_clarification = None

            return result

        elif delegate_to == "clarify":
            clarify_q = decision.get("clarify_question") or "Could you give me more detail?"

            # Build context string for clarification state
            if self._pending_clarification:
                # Extend existing context with new info
                self._pending_clarification["original_context"] += f" | user also said: {user_text}"
            else:
                # Start new clarification state from the recent history + current turn
                original_ctx = (
                    "\n".join(self.conversation_buffer[-6:])
                    + f"\nUser: {user_text}"
                ).strip()
                self._pending_clarification = {
                    "original_context": original_ctx,
                    "question_asked": clarify_q,
                }

            return clarify_q

        else:  # "speak"
            # Clear clarification state if user moved on to conversation
            self._pending_clarification = None
            return decision.get("direct_response") or "I'm not sure how to respond to that."

    def _resolve_tool_result(self, tool_res: dict) -> str:
        """Translates tool result into speaker-ready content."""
        status = tool_res.get("status")

        if status == "success":
            return tool_res.get("result", "Done.")

        elif status == "need_clarification":
            # Tool subagent needs more info — update clarification state
            clarify_msg = tool_res.get(
                "clarification_message",
                "Could you give me a bit more detail?",
            )
            # Preserve clarification state for next turn (don't clear it)
            if self._pending_clarification:
                self._pending_clarification["question_asked"] = clarify_msg
            return clarify_msg

        elif status == "no_tool":
            self._pending_clarification = None
            return "I don't have a tool for that, but I'll keep it in mind."

        else:  # failure
            error = tool_res.get("error", "Something went wrong.")
            print(f"[BossOrchestrator] Tool failure: {error}")
            self._pending_clarification = None
            return "I ran into a small issue trying to do that — could you try again?"

    # ── Fallback Speaker ──────────────────────────────────────────────────────

    async def _speak_fallback(self, content: str, user_name: str, emotion: str) -> str:
        return await self.speaker.speak(
            content=content, user_name=user_name, emotion=emotion
        )
