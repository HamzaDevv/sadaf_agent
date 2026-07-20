"""
memory/consolidator.py — Sadaf V4 2-Stage Memory Consolidation Pipeline

V4 changes:
  - Uses MemoryFileStore instead of MarkdownMemoryEngine
  - Uses groq_proxy for session compression (8b instead of 70b)
  - Writes facts via file_store.write_key() (per-file, per-key)
  - Updates _index.md row after each file write
  - Session compaction handled inside file_store.append_session()

Stage 1 (Async, ~50ms): Extract structured facts via llama-3.1-8b-instant
Stage 2 (Immediate): Patch memory files surgically via MemoryFileStore
Background: LLM-powered session compression if sessions.md gets long
"""
import asyncio
from memory.file_store import MemoryFileStore
from memory.extractor import extract_facts
from config import SUMMARY_MODEL, PRIORITY_EXTRACTION


class MemoryConsolidator:
    def __init__(self, file_store: MemoryFileStore):
        self.store = file_store

    async def consolidate(self, user_id: str, user_input: str, ai_response: str):
        """
        2-stage consolidation pipeline:
          1. Extract facts (fast LLM call → JSON)
          2. Write to correct memory files
          3. Update _index.md per-file summaries
          4. Append session note
        """
        try:
            # Stage 1: Extract facts
            patch = await extract_facts(user_input, ai_response)

            facts          = patch.get("facts", [])
            emotional_state = patch.get("emotional_state")
            session_note   = patch.get("session_note")

            # Stage 2: Write facts to their respective files
            updated_files = set()
            for fact in facts:
                filename = fact.get("file", "")
                key      = fact.get("key", "")
                value    = fact.get("value", "")
                if filename and key and value:
                    await asyncio.to_thread(
                        self.store.write_key, user_id, filename, key, value
                    )
                    updated_files.add(filename)

            # Emotional state → emotions.md
            if emotional_state:
                await asyncio.to_thread(
                    self.store.write_key,
                    user_id, "emotions.md",
                    "Current Emotional State", emotional_state.capitalize()
                )
                updated_files.add("emotions.md")

            # Update _index.md rows for each modified file
            for filename in updated_files:
                asyncio.create_task(
                    self._refresh_index_row(user_id, filename)
                )

            # Append session note
            if session_note:
                await asyncio.to_thread(
                    self.store.append_session, user_id, session_note
                )

        except Exception as e:
            print(f"[Consolidator] Error: {e}")

    async def _refresh_index_row(self, user_id: str, filename: str):
        """Update the _index.md summary row for a file after a write."""
        try:
            content = await asyncio.to_thread(self.store.read_file, user_id, filename)
            # Extract first key-value pair as summary
            kv_lines = [l for l in content.splitlines() if l.startswith("- **")]
            summary = (
                kv_lines[0].replace("- **", "").replace("**:", ":").strip()[:60]
                if kv_lines else "Updated"
            )
            await asyncio.to_thread(
                self.store.update_index_row, user_id, filename, summary
            )
        except Exception as e:
            print(f"[Consolidator] Index refresh error for {filename}: {e}")

    async def compress_sessions_with_llm(self, user_id: str):
        """
        Background task: use llama-3.1-8b-instant to condense old session notes
        into a short paragraph before compaction.
        Called externally if deep compression is needed (e.g., after 100+ sessions).
        """
        from groq_proxy import groq_proxy

        try:
            content = await asyncio.to_thread(self.store.read_file, user_id, "sessions.md")
            if not content:
                return

            response = await groq_proxy.call(
                model=SUMMARY_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a memory summarizer. Condense the following session log "
                            "entries into 2-3 short sentences capturing the most important "
                            "facts and patterns about this user. Output only the summary sentences, "
                            "no markdown, no bullet points."
                        ),
                    },
                    {"role": "user", "content": content},
                ],
                priority=PRIORITY_EXTRACTION,
                temperature=0.1,
                max_tokens=150,
            )

            if not response:
                return

            # Find last N entries to keep
            import re
            entries = re.findall(r"^- \[.+?$", content, re.MULTILINE)
            from config import SESSION_COMPACT_KEEP
            keep = entries[-SESSION_COMPACT_KEEP:]

            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            new_content = (
                f"# Session Index\n"
                f"<!-- Compressed on {timestamp} -->\n"
                f"<!-- Summary: {response} -->\n"
                + "\n".join(keep) + "\n"
            )

            await asyncio.to_thread(
                self.store._atomic_write,
                self.store._file_path(user_id, "sessions.md"),
                new_content,
            )
            print(f"[Consolidator] LLM-compressed sessions for {user_id}")

        except Exception as e:
            print(f"[Consolidator] Compression error: {e}")
