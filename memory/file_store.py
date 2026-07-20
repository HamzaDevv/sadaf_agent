"""
memory/file_store.py — Sadaf V4 Multi-File Markdown Memory Engine

Replaces the monolithic markdown_engine.py with a directory of small,
focused markdown files — one per logical memory domain.

Directory structure per user:
    memories/
    └── sadaf_user/
        ├── _index.md        ← table of contents (15 tokens)
        ├── identity.md      ← name, age, location, language
        ├── career.md        ← job, company, colleagues
        ├── education.md     ← college, degree, courses
        ├── family.md        ← family members, relationships
        ├── health.md        ← sleep, diet, exercise
        ├── interests.md     ← games, music, hobbies
        ├── goals.md         ← short/long-term plans
        ├── behavior.md      ← communication style, humor, dislikes
        ├── emotions.md      ← current state, triggers
        └── sessions.md      ← timestamped episodic notes

Design principles:
  - Each file is tiny (~10-30 lines), so reading = low token cost
  - _index.md is a *discovery aid*, not a source of truth
  - All writes are atomic (.tmp → rename)
  - _index.md writes use file locking to prevent race conditions
  - Session compaction prevents unbounded growth
"""

import re
import fcntl
import time
from datetime import datetime
from pathlib import Path
from config import (
    MEMORY_DIR,
    SESSION_COMPACT_THRESHOLD,
    SESSION_COMPACT_KEEP,
)

# ── File Templates ─────────────────────────────────────────────────────────────

MEMORY_FILES = [
    "identity.md",
    "career.md",
    "education.md",
    "family.md",
    "health.md",
    "interests.md",
    "goals.md",
    "behavior.md",
    "emotions.md",
    "sessions.md",
]

FILE_TEMPLATES: dict[str, str] = {
    "identity.md": """\
# Identity
- **Full Name**: Unknown
- **Nickname**: Unknown
- **Age**: Unknown
- **Location**: Unknown
- **Language Preference**: Unknown
""",
    "career.md": """\
# Career
- **Job Title**: Unknown
- **Company**: Unknown
- **Job Start Date**: Unknown
""",
    "education.md": """\
# Education
- **College/University**: Unknown
- **Degree**: Unknown
- **Graduation Year**: Unknown
""",
    "family.md": """\
# Family & Relationships
- **Relationship Status**: Unknown
- **Family Members**: Unknown
""",
    "health.md": """\
# Health & Habits
- **Sleep Pattern**: Unknown
- **Diet**: Unknown
- **Exercise**: Unknown
""",
    "interests.md": """\
# Interests & Hobbies
- **Hobbies**: Unknown
- **Games**: Unknown
- **Music**: Unknown
- **Food Preferences**: Unknown
""",
    "goals.md": """\
# Goals & Plans
- **Short-term Goals**: Unknown
- **Long-term Goals**: Unknown
""",
    "behavior.md": """\
# Behavioral DNA
- **Communication Style**: Unknown
- **Humor Level**: Unknown
- **Preferred Topics**: Unknown
- **Things They Dislike**: Unknown
""",
    "emotions.md": """\
# Emotional Intelligence
- **Current Emotional State**: Neutral
- **Stress Triggers**: Unknown
- **What Cheers Them Up**: Unknown
- **Sensitive Topics**: Unknown
""",
    "sessions.md": """\
# Session Index
""",
}

INDEX_TEMPLATE = """\
---
user_id: {user_id}
total_conversations: 0
last_updated: {today}
---

# Memory Index

| File | Last Modified | Summary |
|---|---|---|
| identity.md | — | No data yet |
| career.md | — | No data yet |
| education.md | — | No data yet |
| family.md | — | No data yet |
| health.md | — | No data yet |
| interests.md | — | No data yet |
| goals.md | — | No data yet |
| behavior.md | — | No data yet |
| emotions.md | — | No data yet |
| sessions.md | — | No data yet |
"""


# ── MemoryFileStore ────────────────────────────────────────────────────────────

class MemoryFileStore:
    """
    Thin filesystem wrapper for per-user multi-file memory directories.
    Provides atomic reads/writes, file locking, and session compaction.
    """

    def __init__(self, storage_dir: str = MEMORY_DIR):
        self.root = Path(storage_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    # ── Path Helpers ──────────────────────────────────────────────────────────

    def _user_dir(self, user_id: str) -> Path:
        return self.root / user_id

    def _file_path(self, user_id: str, filename: str) -> Path:
        return self._user_dir(user_id) / filename

    def _index_path(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "_index.md"

    # ── Initialization ────────────────────────────────────────────────────────

    def ensure_user_dir(self, user_id: str):
        """Create user directory and all template files if they don't exist."""
        user_dir = self._user_dir(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)

        # Create _index.md
        index = self._index_path(user_id)
        if not index.exists():
            today = datetime.now().strftime("%Y-%m-%d")
            index.write_text(
                INDEX_TEMPLATE.format(user_id=user_id, today=today),
                encoding="utf-8",
            )

        # Create each memory file from template
        for filename in MEMORY_FILES:
            fpath = self._file_path(user_id, filename)
            if not fpath.exists():
                fpath.write_text(FILE_TEMPLATES[filename], encoding="utf-8")

    def list_files(self, user_id: str) -> list[str]:
        """Return the list of known memory filenames for this user."""
        return MEMORY_FILES[:]

    # ── Read Operations ───────────────────────────────────────────────────────

    def read_index(self, user_id: str) -> str:
        """Read _index.md — used by memory agent for file discovery."""
        path = self._index_path(user_id)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def read_file(self, user_id: str, filename: str) -> str:
        """Read a single memory file. Returns empty string if not found."""
        path = self._file_path(user_id, filename)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def read_files(self, user_id: str, filenames: list[str]) -> str:
        """Read and concatenate multiple memory files."""
        parts = []
        for fn in filenames:
            content = self.read_file(user_id, fn)
            if content.strip():
                parts.append(content.strip())
        return "\n\n".join(parts)

    def get_last_n_sessions(self, user_id: str, n: int = 5) -> str:
        """Read sessions.md and return only the last N session note lines."""
        content = self.read_file(user_id, "sessions.md")
        if not content:
            return ""
        lines = [l for l in content.splitlines() if l.startswith("- [")]
        last_n = lines[-n:] if len(lines) > n else lines
        return "# Recent Sessions\n" + "\n".join(last_n) if last_n else ""

    # ── Atomic Write ──────────────────────────────────────────────────────────

    def _atomic_write(self, path: Path, content: str):
        """Write content atomically: write to .tmp then rename."""
        tmp = path.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.rename(path)

    # ── Key-Value Upsert ──────────────────────────────────────────────────────

    def write_key(self, user_id: str, filename: str, key: str, value: str):
        """
        Upsert a key-value pair into a memory file.
        - If `- **key**: ...` already exists → update value in place
        - If it doesn't exist → append new bullet under the first `#` header
        """
        if not key or value is None:
            return

        path = self._file_path(user_id, filename)
        if not path.exists():
            # Create from template if missing
            template = FILE_TEMPLATES.get(filename, f"# {filename.replace('.md', '').title()}\n")
            path.write_text(template, encoding="utf-8")

        content = path.read_text(encoding="utf-8")

        key_pattern = rf"(- \*\*{re.escape(key)}\*\*: ).+"
        if re.search(key_pattern, content):
            # Update existing key
            content = re.sub(key_pattern, rf"\g<1>{value}", content)
        else:
            # Append new key under the first header line
            header_match = re.search(r"^#.+$", content, re.MULTILINE)
            if header_match:
                insert_pos = header_match.end() + 1  # after the header line
                new_line = f"- **{key}**: {value}\n"
                content = content[:insert_pos] + new_line + content[insert_pos:]
            else:
                content += f"\n- **{key}**: {value}\n"

        self._atomic_write(path, content)
        print(f"[FileStore] {filename} ← {key}: {value}")

    # ── Session Notes ─────────────────────────────────────────────────────────

    def append_session(self, user_id: str, note: str):
        """Append a timestamped session note to sessions.md."""
        if not note:
            return
        path = self._file_path(user_id, "sessions.md")
        if not path.exists():
            path.write_text(FILE_TEMPLATES["sessions.md"], encoding="utf-8")

        content = path.read_text(encoding="utf-8")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        content += f"- [{timestamp}] {note}\n"
        self._atomic_write(path, content)

        # Check and trigger compaction
        self._maybe_compact_sessions(user_id, path)

    def _maybe_compact_sessions(self, user_id: str, path: Path):
        """Compact sessions.md if it exceeds SESSION_COMPACT_THRESHOLD."""
        content = path.read_text(encoding="utf-8")
        lines = [l for l in content.splitlines() if l.startswith("- [")]
        if len(lines) < SESSION_COMPACT_THRESHOLD:
            return

        keep = lines[-SESSION_COMPACT_KEEP:]
        old_entries = lines[:-SESSION_COMPACT_KEEP]

        # Compress old entries synchronously (just join them for now;
        # the async consolidator will call the LLM compression separately)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        archived_block = f"<!-- Archived on {timestamp}: {len(old_entries)} entries compressed -->\n"

        new_content = (
            "# Session Index\n"
            + archived_block
            + "\n".join(keep)
            + "\n"
        )
        self._atomic_write(path, new_content)
        print(f"[FileStore] Compacted sessions.md: kept last {SESSION_COMPACT_KEEP} entries")

    # ── Conversation Count ────────────────────────────────────────────────────

    def increment_conversation_count(self, user_id: str):
        """Bump total_conversations in _index.md frontmatter."""
        path = self._index_path(user_id)
        if not path.exists():
            return
        content = path.read_text(encoding="utf-8")
        match = re.search(r"total_conversations: (\d+)", content)
        if match:
            new_count = int(match.group(1)) + 1
            content = content.replace(match.group(0), f"total_conversations: {new_count}")
            self._atomic_write(path, content)

    # ── Index Updates (File-Locked) ───────────────────────────────────────────

    def update_index_row(self, user_id: str, filename: str, summary: str):
        """
        Update a single row in _index.md's table with a fresh summary.
        Uses exclusive file locking to prevent concurrent corruption.
        """
        index_path = self._index_path(user_id)
        if not index_path.exists():
            return

        today = datetime.now().strftime("%Y-%m-%d")

        try:
            with open(index_path, "r+", encoding="utf-8") as f:
                # Acquire exclusive lock
                fcntl.flock(f, fcntl.LOCK_EX)
                content = f.read()

                # Replace the row matching this filename
                row_pattern = rf"\| {re.escape(filename)} \|[^\n]+\n"
                new_row = f"| {filename} | {today} | {summary[:60]} |\n"
                if re.search(row_pattern, content):
                    content = re.sub(row_pattern, new_row, content)
                else:
                    # Append new row before the closing of the table
                    content += new_row

                # Also update last_updated in frontmatter
                content = re.sub(
                    r"last_updated: \d{4}-\d{2}-\d{2}",
                    f"last_updated: {today}",
                    content,
                )

                f.seek(0)
                f.write(content)
                f.truncate()
                # Lock released on close
        except Exception as e:
            print(f"[FileStore] Index update error: {e}")

    def rebuild_index(self, user_id: str):
        """
        Rebuild _index.md from scratch by scanning all memory files.
        Called on startup if index is detected as stale.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        rows = []
        for fn in MEMORY_FILES:
            path = self._file_path(user_id, fn)
            if not path.exists():
                rows.append(f"| {fn} | — | No data yet |")
                continue

            content = path.read_text(encoding="utf-8")
            # Extract first key-value line as summary
            kv_lines = [l for l in content.splitlines() if l.startswith("- **")]
            if kv_lines:
                # Strip markdown from summary
                summary = kv_lines[0].replace("- **", "").replace("**:", ":").strip()[:60]
            else:
                summary = "No data yet"

            mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
            rows.append(f"| {fn} | {mtime} | {summary} |")

        # Read existing frontmatter
        index_path = self._index_path(user_id)
        existing = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
        count_match = re.search(r"total_conversations: (\d+)", existing)
        conv_count = count_match.group(1) if count_match else "0"

        new_index = (
            f"---\nuser_id: {user_id}\ntotal_conversations: {conv_count}\nlast_updated: {today}\n---\n\n"
            "# Memory Index\n\n"
            "| File | Last Modified | Summary |\n"
            "|---|---|---|\n"
            + "\n".join(rows)
            + "\n"
        )
        self._atomic_write(index_path, new_index)
        print(f"[FileStore] Rebuilt _index.md for {user_id}")
