import os

filepath = "/Users/hamza/Sadaf-BOT/Sadaf_2/tools/dispatcher.py"
with open(filepath, "r") as f:
    content = f.read()

# Add synthesize_response to ToolDispatcher
synthesis_method = """    async def synthesize_response(self, user_query: str, tool_result: str) -> str:
        \"\"\"Subagent behavior: use an LLM to synthesize a natural answer from raw tool output.\"\"\"
        system_prompt = \"\"\"You are Sadaf, a conversational AI.
A background tool just gathered some information to answer the user's query.
Based on the tool's output, provide a direct, natural, and concise answer to the user's query.
Do NOT mention that you used a tool. Do NOT describe the entire tool output if it's not relevant. Just answer the query as naturally as possible, acting as a witty, smart best friend.\"\"\"
        prompt = f"USER QUERY: {user_query}\\n\\nTOOL OUTPUT:\\n{tool_result}"
        try:
            raw = await groq_proxy.call(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                priority=PRIORITY_AGENT,
                temperature=0.3,
                max_tokens=150
            )
            return raw.strip() if raw else tool_result
        except Exception:
            return tool_result

"""

if "async def synthesize_response" not in content:
    content = content.replace("async def route(self, user_text: str)", synthesis_method + "    async def route(self, user_text: str)")

# Add needs_synthesis=True to specific tools
tools_to_update = [
    'name="get_datetime",',
    'name="get_countdown",',
    'name="calculate",',
    'name="get_system_info",',
    'name="camera_tool",',
    'name="get_weather",',
    'name="get_news",',
    'name="web_search",',
]

lines = content.split('\n')
new_lines = []
i = 0
while i < len(lines):
    new_lines.append(lines[i])
    for tool_name in tools_to_update:
        if tool_name in lines[i]:
            # scan forward to add needs_synthesis=True before the closing bracket of ToolEntry
            j = i + 1
            while j < len(lines):
                new_lines.append(lines[j])
                if ")," in lines[j] and lines[j].strip() == "),":
                    new_lines.insert(-1, "        needs_synthesis=True,")
                    i = j
                    break
                j += 1
            break
    i += 1

with open(filepath, "w") as f:
    f.write('\n'.join(new_lines))

print("Updated tools/dispatcher.py")
