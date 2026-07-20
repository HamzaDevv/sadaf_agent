"""
config.py — Sadaf V4 Central Configuration

V4 changes:
  - GROQ_API_KEY (single) → GROQ_API_KEYS (multi-key pool, comma-separated)
  - SUMMARY_MODEL downgraded to llama-3.1-8b-instant (saves 70b quota for chat)
  - COMPLEX_QUERY_THRESHOLD: score above this → use 70b for chat
  - SESSION_COMPACT_THRESHOLD: compact sessions.md when entries hit this
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────────────────────────
# Multiple Groq keys from separate orgs: round-robin to multiply quota
_raw_keys = os.getenv("GROQ_API_KEYS", os.getenv("GROQ_API_KEY", ""))
GROQ_API_KEYS: list[str] = [k.strip() for k in _raw_keys.split(",") if k.strip()]

# Legacy single-key fallback (for any module that still imports it directly)
GROQ_API_KEY: str = GROQ_API_KEYS[0] if GROQ_API_KEYS else ""

GOOGLE_API_KEY  = os.getenv("GOOGLE_API_KEY", "")
TAVILY_API_KEY  = os.getenv("TAVILY_API_KEY", "")
GNEWS_API_KEY   = os.getenv("GNEWS_API_KEY", "")

# ── Privacy / Behaviour Flags ─────────────────────────────────────────────────
# When True: camera tool asks "may I use the camera?" before capturing
PRIVACY_MODE: bool = os.getenv("PRIVACY_MODE", "false").lower() == "true"

# Path to persist reminders across sessions
REMINDERS_FILE = os.path.join(os.path.dirname(__file__), "memories", "reminders.json")

AI_NAME = "Sadaf"

# ── Model Selection ───────────────────────────────────────────────────────────
# Fast 8b: fact extraction, memory agent routing, vision compression, STT
CHAT_MODEL   = "llama-3.1-8b-instant"      # Default chat model (simple queries)
COMPLEX_MODEL = "llama-3.3-70b-versatile"  # Complex/emotional queries (uses 70b quota)
SUMMARY_MODEL = "llama-3.1-8b-instant"     # Session compression (downgraded from 70b)
VISION_MODEL  = "qwen/qwen3.6-27b"         # Camera / Vision (multimodal)
STT_MODEL     = "whisper-large-v3-turbo"   # Fast Groq speech-to-text

# ── Model Routing ─────────────────────────────────────────────────────────────
# Query complexity score ≥ this threshold → use COMPLEX_MODEL for chat
COMPLEX_QUERY_THRESHOLD = 0.55

# Question/reasoning words that boost complexity score
COMPLEX_KEYWORDS = [
    "why", "how", "explain", "understand", "think", "feel", "feeling",
    "should", "would", "could", "help me", "advice", "reason",
    "worried", "anxious", "scared", "confused", "frustrated", "depressed",
    "excited", "nervous", "sad", "angry", "stress", "overwhelmed",
    "plan", "decide", "difference", "compare", "analyze",
]

# ── Rate Limits (free tier, per org) ─────────────────────────────────────────
# With 3 separate-org keys: effective TPM = 3× the per-org limit
GROQ_TPM_8B  = 6_000   # llama-3.1-8b-instant: tokens per minute per org
GROQ_TPM_70B = 12_000  # llama-3.3-70b-versatile: tokens per minute per org
GROQ_RPM     = 30      # requests per minute per org (both models)

# Request priority levels (lower = higher priority)
PRIORITY_CHAT       = 1
PRIORITY_EXTRACTION = 2
PRIORITY_AGENT      = 3

# ── Memory (Multi-File System) ────────────────────────────────────────────────
MEMORY_DIR   = "./memories"
DEFAULT_USER_ID = "sadaf_user"
BUFFER_SIZE  = 10    # Recent conversation turns to keep in RAM

# Session compaction: compress oldest entries when sessions.md exceeds this
SESSION_COMPACT_THRESHOLD = 50   # Total entries before compaction
SESSION_COMPACT_KEEP      = 20   # Keep this many recent entries after compaction

# ── TTS / Voice ───────────────────────────────────────────────────────────────
VOICE = "Samantha"          # macOS TTS Voice
MAX_RESPONSE_WORDS = 80     # Safety cap on TTS output

# ── VAD (Voice Activity Detection) ───────────────────────────────────────
VAD_AGGRESSIVENESS        = 3
VAD_SAMPLE_RATE           = 16000
VAD_FRAME_MS              = 30
VAD_SILENCE_DURATION_MS   = 1200
VAD_MIN_SPEECH_MS         = 600
VAD_POST_SPEECH_COOLDOWN_MS = 1500

# ── Audio Recording ───────────────────────────────────────────────────────────
TIMEOUT                  = 3
PHRASE_TIME_LIMIT        = 30
OUTPUT_FILE              = "transcriptions.txt"
RECORDING_TIME_IN_SECONDS = 1800  # 30 min session max

# ── Speech Recognition Tuning ─────────────────────────────────────────────────
PAUSE_THRESHOLD         = 2
ENERGY_THRESHOLD        = 400
DYNAMIC_ENERGY_THRESHOLD = True
