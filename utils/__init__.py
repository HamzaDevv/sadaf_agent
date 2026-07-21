"""Utility text helpers for Sadaf V3."""
import re
import random


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks from LLM output, even if unclosed."""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Also strip if it starts a think block but never closes it
    text = re.sub(r'<think>.*', '', text, flags=re.DOTALL)
    return text.strip()


def strip_markdown(text: str) -> str:
    """Remove markdown formatting that would sound bad in TTS."""
    # Remove bold/italic
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    # Remove headers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove bullet points (keep the text)
    text = re.sub(r'^\s*[-*•]\s+', '', text, flags=re.MULTILINE)
    # Remove numbered lists
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # Remove code blocks
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`(.+?)`', r'\1', text)
    # Remove links
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    # Collapse multiple newlines into spaces
    text = re.sub(r'\n+', ' ', text)
    return text.strip()


def chunk_at_boundaries(text: str) -> list[str]:
    """
    Split text at sentence boundaries (., !, ?) for streaming TTS.
    Returns a list of sentence chunks.
    """
    text = strip_markdown(text)
    # Split at sentence-ending punctuation, keeping the punctuation
    raw = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    for chunk in raw:
        chunk = chunk.strip()
        if not chunk:
            continue
        # If a sentence is very long, split at commas too
        if len(chunk.split()) > 25:
            sub = re.split(r'(?<=[,;])\s+', chunk)
            chunks.extend([s.strip() for s in sub if s.strip()])
        else:
            chunks.append(chunk)
    return [c for c in chunks if c]


def natural_pause_ms() -> float:
    """Return a randomized natural inter-sentence pause in seconds (80–200ms)."""
    return random.uniform(0.08, 0.20)


def natural_speech_rate() -> int:
    """Return a randomized speech rate in words-per-minute (175–200)."""
    return random.randint(175, 200)
