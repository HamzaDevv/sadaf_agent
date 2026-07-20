"""
tools/countdown.py — Sadaf Jarvis Countdown Tool

Calculates time remaining until a named event or specific date
by leveraging the LLM's knowledge.
"""
from datetime import datetime
from groq_proxy import groq_proxy
from config import CHAT_MODEL


async def get_countdown(query: str) -> str:
    """Return spoken-English countdown to a date or event using LLM."""
    now = datetime.now()
    current_date = now.strftime("%A, %B %d %Y")
    
    system_prompt = (
        "You are a helpful voice assistant. The user is asking for a countdown "
        "to a specific date or event (e.g., 'how many days until Christmas' or "
        "'countdown to Friday'). Calculate the days remaining from today and answer "
        "in a single, natural spoken-English sentence. Keep it short and conversational. "
        "No markdown or formatting. "
        f"Today's date is: {current_date}."
    )
    
    try:
        result = await groq_proxy.call(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            temperature=0.2,
            max_tokens=80,
        )
        return result or "I couldn't figure out the countdown for that."
    except Exception as e:
        return f"I had trouble calculating the countdown: {e}"
