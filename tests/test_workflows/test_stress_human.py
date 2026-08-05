import asyncio
import time
import os
import datetime
import pytest
from config import BOSS_MODEL, PRIORITY_AGENT
from groq_proxy import groq_proxy
from tests.utils.fixtures import get_isolated_orchestrator, cleanup_isolated_data

STRESS_HUMAN_PERSONA = """
Name: Dr. Elias Vance
Background: A 45-year-old philosopher, technologist, and polymath. Extremely inquisitive, deep thinker, asks profound questions about existence, consciousness, and the future. He is very talkative and articulate.
Current state: Needs to test the boundaries of the AI in a very long conversation. He will talk about complex philosophical ideas, but also frequently ask the AI to perform practical tasks (e.g., checking the news, getting the weather, setting timers, or calculating complex numbers) to see how the AI balances deep conversation with tool usage.
Goal: Keep the conversation going for up to 50 turns, exploring many topics, asking for specific tool usage, and analyzing the AI's responses deeply.
"""

async def generate_stress_human_reply(history: str) -> str:
    prompt = f"""You are playing the role of a human user in a text/voice conversation with an AI named Sadaf.
Your Persona:
{STRESS_HUMAN_PERSONA}

Conversation History (last few turns):
{history}

Reply naturally as Dr. Elias Vance. Keep your replies substantial, deep, and occasionally request practical tasks (like checking news, weather, or math). Speak like a real person but a very intellectual one.
CRITICAL: If Sadaf fails to answer a request, gives a generic apology, or claims she cannot calculate something, acknowledge the failure and MOVE ON to a completely different topic or tool request. Do NOT repeat the same request over and over.
If the conversation reaches a natural end after many turns, reply with "goodbye".
Reply ONLY with the exact text Dr. Vance says, no quotes, no extra formatting.
"""
    try:
        raw = await groq_proxy.call(
            model=BOSS_MODEL,
            messages=[{"role": "user", "content": prompt}],
            priority=PRIORITY_AGENT,
            temperature=0.8,
            max_tokens=250
        )
        return (raw or "hello").strip()
    except Exception as e:
        print(f"Error generating human reply: {e}")
        return "I seem to have lost my train of thought. Can you tell me the latest news instead?"

@pytest.mark.asyncio
async def test_workflow_stress_human():
    run_id = "wf_stress_human"
    
    # Create log file with note to delete after 1 day
    log_dir = os.path.dirname(os.path.abspath(__file__))
    log_file_path = os.path.join(log_dir, f"stress_test_log_delete_after_1_day_{int(time.time())}.txt")
    
    try:
        orch = get_isolated_orchestrator(run_id)
        user_id = "test_elias_vance"
        
        history_list = []
        
        # Start conversation
        human_text = "Greetings, Sadaf. I am Dr. Elias Vance. I hope you are prepared for a long and profound discussion today. I'd like to start by asking you about the nature of consciousness, and perhaps later we can check some news. What are your thoughts on your own existence?"
        
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write(f"--- STRESS TEST LOG ---\n")
            f.write(f"Timestamp: {datetime.datetime.now().isoformat()}\n")
            f.write(f"Note: This log is generated for a 50-turn stress test and should be manually or automatically deleted after 1 day.\n\n")

        print(f"\n[Stress Test] Starting 50-turn stress test. Logs will be saved to: {log_file_path}\n")

        for turn_idx in range(50):
            start_t = time.time()
            
            # Sadaf replies
            sadaf_reply = await orch.process(user_id, human_text)
            latency = int((time.time() - start_t) * 1000)
            
            history_list.append(f"Elias: {human_text}")
            history_list.append(f"Sadaf: {sadaf_reply}")
            
            # Log to file
            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write(f"Turn {turn_idx + 1} | Latency: {latency}ms\n")
                f.write(f"Elias: {human_text}\n")
                f.write(f"Sadaf: {sadaf_reply}\n")
                f.write("-" * 40 + "\n")
                
            print(f"Completed turn {turn_idx + 1}/50...")
            
            if "goodbye" in sadaf_reply.lower() or "goodbye" in human_text.lower():
                with open(log_file_path, "a", encoding="utf-8") as f:
                    f.write("Conversation ended naturally with a goodbye.\n")
                print("Conversation ended with a goodbye.")
                break
            
            # Keep history manageable for the prompt (last 16 messages / 8 turns max to avoid context window explosion)
            recent_history = "\n".join(history_list[-16:])
            
            # Brief pause to avoid rapid rate limits on the Groq proxy
            await asyncio.sleep(3.0)
            
            # Human replies
            human_text = await generate_stress_human_reply(recent_history)
            
        # Give memory consolidator a moment to finish background tasks
        await asyncio.sleep(2.0)
        print(f"[Stress Test] Finished. Please review the log at {log_file_path}")
        
    finally:
        cleanup_isolated_data(run_id)
