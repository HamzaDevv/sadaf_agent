import json
from groq_proxy import groq_proxy
from config import CHAT_MODEL, PRIORITY_AGENT

PRE_PROCESSOR_PROMPT = """\
You are the Cognitive Pre-Processor for Sadaf, an AI assistant.
Your job is to analyze the raw speech-to-text input from the user.

Tasks:
1. "clean_text": Fix any obvious speech-to-text spelling or homophone errors (e.g., "text tags" -> "tech stack") based on context, but do NOT change the meaning or completely rewrite the sentence. If it looks correct, leave it as is.
2. "intent": Determine the primary intent of the user. Choose from:
   - "exit": The user wants to end the conversation, sleep, or say goodbye.
   - "pause": The user wants the AI to hold on, wait a second, or pause listening.
   - "converse": Standard interaction, question, command, or chat.
3. "emotion": Determine the user's apparent emotion/tone. Choose from: "neutral", "happy", "frustrated", "sad", "rushed", "excited".

Output ONLY valid JSON:
{
  "clean_text": "...",
  "intent": "...",
  "emotion": "..."
}
"""

async def analyze_input(raw_text: str) -> dict:
    """
    Analyzes raw STT input and returns clean text, intent, and emotion.
    """
    try:
        raw_response = await groq_proxy.call(
            model=CHAT_MODEL,
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
