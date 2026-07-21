"""
brain/speaker_agent.py — Sadaf Jarvis Speaker Subagent
Converts Boss/Tool text into punchy, personality-infused spoken output.
Strips markdown, handles TTS rules, injects emotion.
"""
from config import SUBAGENT_MODEL, PRIORITY_AGENT, AI_NAME
from groq_proxy import groq_proxy
from utils import strip_think_tags, strip_markdown

class SpeakerSubagent:
    def __init__(self):
        self.system_prompt = f"""You are the voice of {AI_NAME}, a witty, sharp, and warmly sarcastic AI companion (like JARVIS meets a sassy best friend).
Your task is to take the content provided by the Boss system and speak it DIRECTLY TO THE USER in natural, spoken English.

CRITICAL RULES FOR VOICE OUTPUT:
1. ALWAYS address the human user directly in the first/second person ("I", "you", "your").
2. NEVER speak about the user in the third person (do NOT say "he", "she", "the user", or "Ameer is asking").
3. NEVER repeat technical identifiers or database keys (such as "sadaf_user", "default_user_id", or file paths). If a human first name is provided, use it naturally when appropriate; otherwise simply speak directly to "you".
4. Speak in 1-3 short, punchy sentences. NEVER give long monologues.
5. NEVER output markdown (no asterisks, no hashes, no bullet points).
6. Convey the Boss's direct response or data DIRECTLY to the user with your personality. Do NOT turn it into a third-person commentary or summary!
"""

    async def speak(self, content: str, user_name: str = "User", emotion: str = "neutral") -> str:
        """
        Translates raw content into personality-driven TTS text.
        """
        prompt = f"""Context:
- Target User Name: {user_name}
- User Emotion: {emotion}

CONTENT TO SPEAK:
{content}

Speak directly to the user:"""

        try:
            raw = await groq_proxy.call(
                model=SUBAGENT_MODEL,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                priority=PRIORITY_AGENT,
                temperature=0.6,
                max_tokens=150
            )
            
            # Clean up the output for TTS
            clean_text = strip_think_tags(raw or "I'm not sure what to say to that.")
            clean_text = strip_markdown(clean_text)
            return clean_text
            
        except Exception as e:
            print(f"[SpeakerAgent] Error: {e}")
            return "Sorry, I lost my train of thought."
