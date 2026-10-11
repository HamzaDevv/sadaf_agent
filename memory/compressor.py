"""
memory/compressor.py — Sadaf V7 Context Compressor

Compacts raw memory into a token-efficient format for the AgentCore prompt.
"""

from typing import List

from config import BOSS_MEMORY_MAX_CHARS, BOSS_HISTORY_MAX_TURNS

class ContextCompressor:
    """Compresses memory and conversation history into a structured, token-efficient format."""

    def compress_memory(self, memory_context: str) -> str:
        """
        Trims and formats the raw memory graph output.
        Keeps only the most relevant recent facts up to a token/char budget.
        """
        if not memory_context or memory_context.strip() == "":
            return "(No relevant memory found.)"

        if len(memory_context) > BOSS_MEMORY_MAX_CHARS:
            trimmed = memory_context[-BOSS_MEMORY_MAX_CHARS:]
            # Snap to a newline if possible
            idx = trimmed.find("\n")
            if idx != -1:
                trimmed = "[...older memory omitted...]\n" + trimmed[idx + 1:]
            return trimmed

        return memory_context

    def compress_history(self, buffer: List[str]) -> str:
        """
        Takes the rolling conversation buffer and returns only the last N turns.
        """
        if not buffer:
            return "(No recent conversation)"

        # Keep only the last BOSS_HISTORY_MAX_TURNS lines
        recent = buffer[-BOSS_HISTORY_MAX_TURNS:]
        return "\n".join(recent)

context_compressor = ContextCompressor()
