"""
test_stress_human.py — Rate-limit-aware stress / workflow test.

Budget math (worst case, single provider):
  - Gemini flash: 10 RPM × 4 keys = 40 RPM effective
  - Each Sadaf turn makes ~3 internal LLM calls (pre-processor, orchestrator, speaker/memory)
  - Safe inter-turn gap = 60s / (40 RPM / 3 calls) = 4.5 s  →  we use 8 s for headroom
  - 10 turns × 3 calls = 30 calls total — well inside a 1-minute window across all keys

  DO NOT raise STRESS_TURNS above 20 or lower INTER_TURN_DELAY_S below 6.0
  without also adding more API keys.
"""
import asyncio
import time
import os
import datetime
import pytest
from config import PRIORITY_AGENT
from llm_proxy import llm_proxy
from tests.utils.fixtures import get_isolated_orchestrator, cleanup_isolated_data
from tools.timer_tool import cancel_all_timers

# ── Safety knobs ──────────────────────────────────────────────────────────────
STRESS_TURNS        = 10    # keep ≤ 20; raise only if you have more keys
INTER_TURN_DELAY_S  = 8.0  # seconds between turns (respects RPM across all calls)
MAX_QUOTA_FRACTION  = 0.70  # abort if estimated RPM > 70% of per-minute limit
# ─────────────────────────────────────────────────────────────────────────────

# Static question bank — no extra LLM call to generate human replies.
# This saves ~half the quota the old LLM-based simulator burned.
_QUESTIONS = [
    "Greetings, Sadaf. What are your thoughts on consciousness and self-awareness in AI systems?",
    "Fascinating. Do you think free will is compatible with determinism?",
    "Let's shift gears. What is the latest thinking on quantum computing's impact on cryptography?",
    "How do you balance storing memories of our conversation with privacy concerns?",
    "Can you tell me the time right now? I like to stay grounded in the present moment.",
    "What do you think is the most underrated philosophical problem of our era?",
    "Set a timer for 1 minute please. I want to time how long your next response takes.",
    "If you could change one thing about how AI systems like yourself are trained, what would it be?",
    "What's your view on the relationship between language and thought?",
    "Thank you for a thought-provoking session, Sadaf. Goodbye.",
]

# Pad or trim to exactly STRESS_TURNS entries
_PADDED_QUESTIONS = (_QUESTIONS * ((STRESS_TURNS // len(_QUESTIONS)) + 1))[:STRESS_TURNS]


def _estimate_calls_per_turn() -> int:
    """Conservative estimate of internal LLM calls Sadaf makes per user turn."""
    return 3  # pre-processor + orchestrator + speaker/memory consolidator


def _quota_ok(turn_idx: int, rpm_limit: int = 40) -> bool:
    """Return False if we are burning quota too fast (safety abort)."""
    if turn_idx == 0:
        return True
    elapsed_minutes = max(0.01, turn_idx * INTER_TURN_DELAY_S / 60.0)
    effective_rpm = (turn_idx * _estimate_calls_per_turn()) / elapsed_minutes
    ok = effective_rpm < rpm_limit * MAX_QUOTA_FRACTION
    if not ok:
        print(
            f"[StressTest] Quota guard triggered: {effective_rpm:.1f} estimated RPM "
            f"(limit {rpm_limit}, threshold {rpm_limit * MAX_QUOTA_FRACTION:.0f}). Stopping early."
        )
    return ok


@pytest.mark.asyncio
async def test_workflow_stress_human():
    run_id = "wf_stress_human"

    log_dir = os.path.dirname(os.path.abspath(__file__))
    log_file_path = os.path.join(
        log_dir, f"stress_test_log_delete_after_1_day_{int(time.time())}.txt"
    )

    print(
        f"\n[StressTest] Starting {STRESS_TURNS}-turn rate-limited stress test "
        f"({INTER_TURN_DELAY_S}s between turns). Log: {log_file_path}\n"
    )

    orch = None
    try:
        orch = get_isolated_orchestrator(run_id)
        user_id = "test_elias_vance"
        history_log = []

        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write("--- STRESS TEST LOG ---\n")
            f.write(f"Timestamp:  {datetime.datetime.now().isoformat()}\n")
            f.write(f"Turns:      {STRESS_TURNS}\n")
            f.write(f"Delay/turn: {INTER_TURN_DELAY_S}s\n")
            f.write("Note: auto-delete after 1 day\n\n")

        for turn_idx, human_text in enumerate(_PADDED_QUESTIONS):

            # ── Quota safety guard ────────────────────────────────────────────
            if not _quota_ok(turn_idx):
                with open(log_file_path, "a", encoding="utf-8") as f:
                    f.write(f"[STOPPED EARLY at turn {turn_idx + 1} by quota guard]\n")
                break

            # ── Sadaf processes the turn ──────────────────────────────────────
            start_t = time.time()
            sadaf_reply = await orch.process(user_id, human_text)
            latency_ms = int((time.time() - start_t) * 1000)

            history_log.append(f"Elias: {human_text}")
            history_log.append(f"Sadaf: {sadaf_reply}")

            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write(f"Turn {turn_idx + 1}/{STRESS_TURNS} | Latency: {latency_ms}ms\n")
                f.write(f"Elias: {human_text}\n")
                f.write(f"Sadaf: {sadaf_reply}\n")
                f.write("-" * 40 + "\n")

            print(f"[StressTest] Turn {turn_idx + 1}/{STRESS_TURNS} done ({latency_ms}ms)")

            if "goodbye" in sadaf_reply.lower() or "goodbye" in human_text.lower():
                with open(log_file_path, "a", encoding="utf-8") as f:
                    f.write("Conversation ended with goodbye.\n")
                print("[StressTest] Goodbye detected — ending early.")
                break

            # ── Respectful inter-turn pause ───────────────────────────────────
            if turn_idx < STRESS_TURNS - 1:
                print(f"[StressTest] Waiting {INTER_TURN_DELAY_S}s before next turn…")
                await asyncio.sleep(INTER_TURN_DELAY_S)

        # Let background memory consolidation finish
        await asyncio.sleep(2.0)
        print(f"[StressTest] Finished. Log: {log_file_path}")

    finally:
        cancel_all_timers()                      # cancel any pending timer tasks
        if orch is not None:
            orch.cancel_background_tasks()       # cancel any pending consolidation tasks
        cleanup_isolated_data(run_id)
