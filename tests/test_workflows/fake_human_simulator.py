import asyncio
import time
from config import BOSS_MODEL, PRIORITY_AGENT
from groq_proxy import groq_proxy
from tests.utils.fixtures import get_isolated_orchestrator, cleanup_isolated_data
from tests.utils.ai_judge import score_conversation

FAKE_HUMAN_PERSONA = """
Name: Alex
Background: 25-year-old software engineer, curious about AI, first time talking to Sadaf.
Current state: Needs to introduce himself, ask a general knowledge question about space, and mention his favorite color is emerald green.
"""

async def generate_human_reply(history: str) -> str:
    prompt = f"""You are playing the role of a human user in a voice conversation with an AI named Sadaf.
Your Persona:
{FAKE_HUMAN_PERSONA}

Conversation History:
{history}

Reply naturally as Alex. Keep it to 1-2 sentences. Speak like a real person.
If the AI says goodbye or the conversation reaches a natural end, reply with "goodbye".
Reply ONLY with the exact text Alex says, no quotes, no extra formatting.
"""
    try:
        raw = await groq_proxy.call(
            model=BOSS_MODEL,
            messages=[{"role": "user", "content": prompt}],
            priority=PRIORITY_AGENT,
            temperature=0.7,
            max_tokens=100
        )
        return (raw or "hello").strip()
    except Exception:
        return "hello"

async def run_workflow_fake_human():
    run_id = "wf_fake_human"
    try:
        orch = get_isolated_orchestrator(run_id)
        user_id = "test_alex"
        
        conversation_turns = []
        history = ""
        
        # Start conversation
        human_text = "Hi there, I'm Alex."
        
        for turn_idx in range(4): # 4 turns
            start_t = time.time()
            sadaf_reply = await orch.process(user_id, human_text)
            latency = int((time.time() - start_t) * 1000)
            
            conversation_turns.append({
                "turn": turn_idx + 1,
                "user": human_text,
                "sadaf": sadaf_reply,
                "latency_ms": latency
            })
            
            history += f"Alex: {human_text}\nSadaf: {sadaf_reply}\n"
            
            if "goodbye" in sadaf_reply.lower() or "goodbye" in human_text.lower():
                break
                
            human_text = await generate_human_reply(history)
            
        # Give memory consolidator a moment to finish background tasks
        await asyncio.sleep(2.0)
        
        # Evaluate
        judge_result = await score_conversation(conversation_turns, FAKE_HUMAN_PERSONA)
        overall_score = judge_result.get("overall", 0)
        
        assert overall_score >= 7.0, f"Conversation score too low: {overall_score}. Notes: {judge_result.get('notes')}"
        
        # Attach metrics to test state if we had a global context, but simple assert works for pass/fail.
        # The runner will catch the exception.
    finally:
        cleanup_isolated_data(run_id)
