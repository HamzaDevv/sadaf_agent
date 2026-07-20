"""
tools/clipboard_tool.py — Sadaf Jarvis Clipboard Tool

Read and write the system clipboard via pyperclip.
"""
import asyncio
import re
import pyperclip


def _read_clipboard() -> str:
    try:
        content = pyperclip.paste()
        return content.strip() if content else ""
    except Exception as e:
        return f"error:{e}"


def _write_clipboard(text: str) -> bool:
    try:
        pyperclip.copy(text)
        return True
    except Exception:
        return False


async def clipboard_action(query: str) -> str:
    """Read or write clipboard based on user query."""
    query_lower = query.lower()

    # Write mode: "copy X to clipboard" or "put X on clipboard"
    write_match = re.search(
        r"(?:copy|put|save|write)\s+(.+?)\s+(?:to|on|into)\s+(?:the\s+)?clipboard",
        query_lower
    )
    if write_match:
        text_to_copy = write_match.group(1).strip()
        success = await asyncio.to_thread(_write_clipboard, text_to_copy)
        if success:
            return f"Copied '{text_to_copy}' to your clipboard."
        return "I had trouble writing to the clipboard."

    # Read mode: "what's on my clipboard" / "read clipboard"
    if any(w in query_lower for w in ["read", "what", "show", "get", "paste", "clipboard"]):
        content = await asyncio.to_thread(_read_clipboard)
        if content.startswith("error:"):
            return "I couldn't read the clipboard right now."
        if not content:
            return "Your clipboard is empty right now."
        # Truncate long content for voice
        if len(content) > 200:
            preview = content[:200].strip()
            return f"Your clipboard has: {preview}... and more."
        return f"Your clipboard has: {content}"

    return "I'm not sure what you want me to do with the clipboard."
