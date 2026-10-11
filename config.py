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

_raw_gemini_keys = os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", ""))
GEMINI_API_KEYS: list[str] = [k.strip() for k in _raw_gemini_keys.split(",") if k.strip()]

# Legacy single-key fallback (for any module that still imports it directly)
GROQ_API_KEY: str = GROQ_API_KEYS[0] if GROQ_API_KEYS else ""

GOOGLE_API_KEY  = os.getenv("GOOGLE_API_KEY", "")
TAVILY_API_KEY  = os.getenv("TAVILY_API_KEY", "")
GNEWS_API_KEY   = os.getenv("GNEWS_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# ── AI Provider Configuration ─────────────────────────────────────────────────
AI_PROVIDER = os.getenv("AI_PROVIDER", "groq").lower()


# ── Privacy / Behaviour Flags ─────────────────────────────────────────────────
# When True: camera tool asks "may I use the camera?" before capturing
PRIVACY_MODE: bool = os.getenv("PRIVACY_MODE", "false").lower() == "true"

# Controls console output for memory/proxy operations (reduce spam)
VERBOSE_LOGS: bool = os.getenv("VERBOSE_LOGS", "false").lower() == "true"

# Path to persist reminders across sessions
REMINDERS_FILE = os.path.join(os.path.dirname(__file__), "memories", "reminders.json")

AI_NAME = "Sadaf"

# ── Model Selection ───────────────────────────────────────────────────────────
if AI_PROVIDER == "gemini":
    BOSS_MODEL     = "gemini-flash-latest"       # Real current-gen flash model
    SUBAGENT_MODEL = "gemini-flash-lite-latest"  # Cheapest/fastest free tier
    CHAT_MODEL     = "gemini-flash-lite-latest"
    VISION_MODEL   = "gemini-flash-latest"
elif AI_PROVIDER == "deepseek":
    BOSS_MODEL     = "deepseek-v4-flash"
    SUBAGENT_MODEL = "llama-3.1-8b-instant"     # Groq free tier for fast background tasks
    CHAT_MODEL     = "llama-3.1-8b-instant"
    VISION_MODEL   = "qwen/qwen3.6-27b"
else:
    BOSS_MODEL     = "llama-3.3-70b-versatile"  # Boss Orchestrator only (routing + synthesis)
    SUBAGENT_MODEL = "llama-3.1-8b-instant"     # All subagents: pre-processor, memory, tool, speaker
    CHAT_MODEL     = "llama-3.1-8b-instant"     # Fallback chat model
    VISION_MODEL   = "qwen/qwen3.6-27b"  # Camera / Vision (multimodal)

STT_MODEL      = "whisper-large-v3-turbo"   # Fast Groq speech-to-text

# ── Why this split? ─────────────────────────────────────────────────────────
# 70b is only used for the boss orchestrator (routing + intent synthesis).
# All other calls (pre-processor, memory, tool selection, speaker) use 8b
# because they receive structured inputs and don't need deep reasoning.
# This reduces 70b usage from ~5-6 calls/turn to 1, giving ~5× more headroom
# on the free tier (6,000 TPM for 70b per org × 3 orgs = 18,000 TPM effective).

# ── Rate Limits ──────────────────────────────────────────────────────────────
# Groq free tier, per org
GROQ_TPM_8B  = 14_400  # llama-3.1-8b-instant: ~14,400 TPM free per org
GROQ_TPM_70B = 6_000   # llama-3.3-70b-versatile: ~6,000 TPM free per org
GROQ_RPM     = 30      # requests per minute per org (both models)

# Gemini free tier, per key (gemini-2.0-flash-lite / gemini-2.0-flash)
GEMINI_TPM_LITE  = 1_000_000   # gemini-2.0-flash-lite: 1M TPM
GEMINI_TPM_FLASH = 250_000     # gemini-2.0-flash: 250K TPM
GEMINI_RPM_LITE  = 30          # gemini-2.0-flash-lite: 30 RPM
GEMINI_RPM_FLASH = 10          # gemini-2.0-flash: 10 RPM
# How long to lock a key after receiving a 429 (one full quota window + buffer)
GEMINI_RETRY_LOCK_S = 62.0

# Request priority levels (lower = higher priority)
PRIORITY_CHAT       = 1
PRIORITY_EXTRACTION = 2
PRIORITY_AGENT      = 3

# ── Boss Prompt Budget & Context Capacity ────────────────────────────────────
if AI_PROVIDER == "deepseek":
    BOSS_MEMORY_MAX_CHARS  = 4_000  # Compact summary, not raw dump
    BOSS_HISTORY_MAX_TURNS = 12     # Capped rolling window
    BUFFER_SIZE            = 10     # Rolling window; older turns get summarized
elif AI_PROVIDER == "gemini":
    BOSS_MEMORY_MAX_CHARS  = 12_000
    BOSS_HISTORY_MAX_TURNS = 30
    BUFFER_SIZE            = 40
else:
    BOSS_MEMORY_MAX_CHARS  = 1_200  # Conservative for 8b/70b Groq token budget limits
    BOSS_HISTORY_MAX_TURNS = 10
    BUFFER_SIZE            = 20

# ── Consolidator Retry (background memory extraction on 429) ──────────────────
CONSOLIDATOR_MAX_RETRIES = 3
CONSOLIDATOR_RETRY_DELAY = 45.0   # seconds; multiplied by attempt index

# ── Pre-Processor Fast-Path ───────────────────────────────────────────────────
# Regex detects intent category first; LLM confirms + cleans text second.
# If the LLM confirmation is skipped (pure fast-path only), set to True.
# Current: two-level — regex then LLM. This flag controls LLM confirmation.
PRE_PROCESSOR_TWO_LEVEL = True

# ── V7 Architecture Feature Flag ─────────────────────────────────────────────
# Set to True to use the new single-context AgentCore and intent_resolver
USE_V7_ORCHESTRATOR = True

# ── Proxy Token Pacing ────────────────────────────────────────────────────────
# Silent wait threshold: if a request must wait longer than this, Sadaf speaks.
PROXY_SILENT_WAIT_THRESHOLD_S = 3.0
# Proactive spread: keep this fraction of TPM in reserve to avoid burst spikes.
# e.g. 0.15 means use at most 85% of the bucket per-call burst.
PROXY_BURST_RESERVE_FRACTION  = 0.15

# ── Memory (Multi-File System) ────────────────────────────────────────────────
MEMORY_DIR   = "./memories"
DEFAULT_USER_ID = "sadaf_user"


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
