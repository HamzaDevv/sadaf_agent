import json
from groq_proxy import groq_proxy
from config import SUBAGENT_MODEL, PRIORITY_AGENT

PRE_PROCESSOR_PROMPT = """\
You are the Cognitive Pre-Processor for Sadaf, an AI assistant.
Analyze raw speech-to-text (STT) input from the user.

Tasks:
1. "clean_text": Fix minor speech-to-text spelling/homophone errors based on context, without altering the user's intent or meaning.
2. "intent": Determine the user's primary intent. Choose strictly from:
   - "exit": The user explicitly wants to end the interaction, sleep, or say goodbye (e.g. "goodbye", "exit", "quit", "bye").
   - "pause": The user EXPLICITLY asks or commands the assistant to hold on, wait, or pause listening (e.g. "wait a second", "hold on", "pause listening", "give me a minute").
     IMPORTANT: Hesitation, filler sounds, speech pauses, or thinking aloud (e.g. "uh", "um", "hmm", "well", "ah", stuttering) are NOT pause requests. Classify these as "converse".
   - "capabilities_query": The user is asking what features, capabilities, or tools the assistant possesses.
   - "converse": Default for all standard statements, questions, commands, thoughts, disfluencies, or general conversation.
3. "emotion": Determine the apparent emotion ("neutral", "happy", "frustrated", "sad", "rushed", "excited").

Output ONLY valid JSON:
{
  "clean_text": "...",
  "intent": "converse",
  "emotion": "neutral"
}
"""

async def analyze_input(raw_text: str) -> dict:
    """
    Analyzes raw STT input and returns clean text, intent, and emotion.
    """
    try:
        raw_response = await groq_proxy.call(
            model=SUBAGENT_MODEL,
            messages=[
                {"role": "system", "content": PRE_PROCESSOR_PROMPT},
                {"role": "user", "content": f"RAW INPUT: {raw_text}"}
            ],
            priority=PRIORITY_AGENT,
            temperature=0.0,
            max_tokens=150,
            response_format={"type": "json_object"}
        )
        
        if not raw_response:
            return {"clean_text": raw_text, "intent": "converse", "emotion": "neutral"}
            
        result = json.loads(raw_response)
        
        clean_text = result.get("clean_text", raw_text)
        intent = result.get("intent", "converse").lower()
        emotion = result.get("emotion", "neutral").lower()
        
        return {"clean_text": clean_text, "intent": intent, "emotion": emotion}
        
    except Exception as e:
        print(f"[PreProcessor] Error: {e}")
        return {"clean_text": raw_text, "intent": "converse", "emotion": "neutral"}
