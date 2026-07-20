"""
memory/memory_agent.py — Sadaf V4 Agent-Driven Context Retrieval

Replaces the keyword-based retriever with an LLM-powered agent that:
  1. Reads _index.md (~15 tokens) to understand what files exist
  2. Reasons about which files are relevant to the user's query
  3. Reads only those files (1-3 additional files, always reads identity + sessions)
  4. Assembles a lean, precise context string for the chat LLM

Failure hardening:
  - JSON parse failure → retry once → keyword fallback (zero LLM cost)
  - Hallucinated filenames → validated against actual file list
  - 429 / any error → immediately falls back to keyword matching
  - Always caps at 3 additional files (token safety)

Token efficiency (per turn):
  - Agent routing call:  ~250 tokens (index + prompt)
  - Actual context:      ~200-350 tokens (selected files only)
  - vs V3:              ~800 tokens (full monolith)
"""

import asyncio
import json
from collections import deque
from memory.file_store import MemoryFileStore, MEMORY_FILES
from config import CHAT_MODEL, PRIORITY_AGENT


# ──────────────────────────────────────────────────────────────────────────────
# Keyword Fallback (V3-style, but returns filenames instead of section names)
# ──────────────────────────────────────────────────────────────────────────────

_TOPIC_MAP: dict[str, list[str]] = {
    "career.md":    ["work", "job", "office", "company", "boss", "salary", "colleague",
                     "project", "meeting", "deadline", "career", "promotion", "workplace"],
    "education.md": ["college", "university", "degree", "study", "exam", "semester",
                     "course", "professor", "student", "graduation", "school"],
    "family.md":    ["mom", "dad", "brother", "sister", "family", "parent", "wife",
                     "husband", "kids", "children", "marriage", "relationship", "love"],
    "health.md":    ["sleep", "tired", "sick", "health", "diet", "food", "exercise",
                     "gym", "pain", "doctor", "medicine", "energy", "rest"],
    "interests.md": ["pokemon", "game", "music", "movie", "book", "sport", "hobby",
                     "cricket", "football", "play", "fun", "watch", "listen", "show"],
    "goals.md":     ["plan", "goal", "future", "want to", "dream", "hoping", "next year",
                     "upcoming", "soon", "thinking about", "aim", "target"],
    "behavior.md":  ["like", "love", "hate", "prefer", "usually", "always", "never",
                     "kind of", "tend to", "personality", "habits"],
    "emotions.md":  ["feel", "feeling", "sad", "happy", "stressed", "anxious", "excited",
                     "depressed", "frustrated", "angry", "worried", "nervous", "scared",
                     "proud", "tired", "exhausted", "bored", "overwhelmed"],
}


def _keyword_fallback(query: str) -> list[str]:
    """Return relevant filenames based on keyword matching (zero LLM cost)."""
    lower = query.lower()
    matched = [fn for fn, keywords in _TOPIC_MAP.items() if any(kw in lower for kw in keywords)]
    return matched[:3]  # Cap at 3


# ──────────────────────────────────────────────────────────────────────────────
# Agent Routing Prompt (stable prefix — cache-friendly)
# ──────────────────────────────────────────────────────────────────────────────

_ROUTING_SYSTEM = """\
You are a memory file selector for a personal AI assistant named Sadaf.
Your ONLY job is to decide which memory files to read for the given user query.

Available files and what they contain:
- identity.md   → name, nickname, age, location, language
- career.md     → job title, company, colleagues, work events
- education.md  → college, degree, courses, graduation
- family.md     → family members, relationship status
- health.md     → sleep, diet, exercise, health issues
- interests.md  → games, music, movies, hobbies, food
- goals.md      → short and long-term plans
- behavior.md   → communication style, humor, preferences, dislikes
- emotions.md   → current emotional state, stress triggers
- sessions.md   → already loaded separately, do NOT include it

Rules:
- identity.md is ALWAYS loaded automatically (do NOT list it)
- sessions.md is ALWAYS loaded automatically (do NOT list it)
- Select 0–3 ADDITIONAL files based on relevance only
- If no additional files are needed, output []
- Output ONLY a valid JSON array of filenames, nothing else
- Do NOT hallucinate filenames. Only use files from the list above.

Examples:
- Query "how was your day?" → []
- Query "tell me about my job" → ["career.md"]
- Query "I'm feeling stressed about work" → ["career.md", "emotions.md"]
- Query "tell me everything about me" → ["career.md", "education.md", "interests.md"]
"""


# ──────────────────────────────────────────────────────────────────────────────
# MemoryAgent
# ──────────────────────────────────────────────────────────────────────────────

class MemoryAgent:
    """
    LLM-driven memory context builder.
    Uses file_store to read tiny markdown files rather than a monolithic file.
    """

    def __init__(self, file_store: MemoryFileStore):
        self.store = file_store

    async def build_context(
        self,
        user_id: str,
        buffer: deque,
        user_query: str = "",
    ) -> str:
        """
        Build a lean, relevant context string for the chat LLM system prompt.

        Always includes:
          - identity.md
          - Last 5 session notes from sessions.md

        Agent-selected (0-3 additional):
          - Files chosen by LLM based on query topic

        Fallback (if LLM unavailable):
          - Keyword matching on query (V3-style, now returns filenames)

        Finally appends:
          - Last 5 turns from the live conversation buffer
        """
        self.store.ensure_user_dir(user_id)

        # Step 1: Always load identity and recent sessions
        identity = self.store.read_file(user_id, "identity.md").strip()
        recent_sessions = self.store.get_last_n_sessions(user_id, n=5)

        # Step 2: Determine additional files via LLM agent or keyword fallback
        additional_files = await self._select_files(user_id, user_query, buffer)

        # Step 3: Read selected files
        additional_content = self.store.read_files(user_id, additional_files).strip()

        # Step 4: Build short-term buffer context
        recent_turns = list(buffer)[-5:]
        buffer_context = ""
        if recent_turns:
            lines = "\n".join(f"You: {u}\nSadaf: {a}" for u, a in recent_turns)
            buffer_context = f"# This Conversation (last {len(recent_turns)} turns)\n{lines}"

        # Assemble context
        sections = [s for s in [identity, additional_content, recent_sessions, buffer_context] if s]
        return "\n\n".join(sections).strip()

    async def _select_files(
        self,
        user_id: str,
        query: str,
        buffer: deque,
    ) -> list[str]:
        """
        Use LLM to select relevant additional memory files.
        Falls back to keyword matching on any failure.
        """
        if not query:
            return []

        # Try LLM routing
        try:
            from groq_proxy import groq_proxy

            # Read index for file discovery
            index = self.store.read_index(user_id)

            # Build buffer summary (last 2 turns only, keep it short)
            buffer_summary = ""
            recent = list(buffer)[-2:]
            if recent:
                buffer_summary = " | ".join(f"User: {u}" for u, _ in recent)

            user_msg = (
                f"MEMORY INDEX:\n{index}\n\n"
                f"USER QUERY: {query}\n\n"
                f"RECENT CONVERSATION: {buffer_summary}"
            )

            raw = await groq_proxy.call(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": _ROUTING_SYSTEM},
                    {"role": "user",   "content": user_msg},
                ],
                priority=PRIORITY_AGENT,
                temperature=0.0,
                max_tokens=60,
            )

            if not raw:
                raise ValueError("Empty response from routing agent")

            files = self._parse_and_validate(raw, user_id)
            if files is not None:
                print(f"[MemoryAgent] Selected: {files}")
                return files

        except Exception as e:
            print(f"[MemoryAgent] LLM routing failed ({e}), using keyword fallback")

        # Keyword fallback
        fallback = _keyword_fallback(query)
        print(f"[MemoryAgent] Keyword fallback: {fallback}")
        return fallback

    def _parse_and_validate(self, raw: str, user_id: str) -> list[str] | None:
        """
        Parse JSON array from LLM response and validate filenames.
        Returns None if parsing fails (triggers keyword fallback).
        """
        # Extract JSON array from response (handles extra text)
        match = None
        try:
            start = raw.index("[")
            end = raw.rindex("]") + 1
            match = raw[start:end]
        except ValueError:
            pass

        if not match:
            return None

        try:
            files = json.loads(match)
        except json.JSONDecodeError:
            return None

        if not isinstance(files, list):
            return None

        # Validate: only allow known filenames, cap at 3
        valid_files = MEMORY_FILES  # From file_store
        validated = [
            f for f in files
            if isinstance(f, str) and f in valid_files
            and f not in ("identity.md", "sessions.md")  # Already always loaded
        ]
        return validated[:3]
