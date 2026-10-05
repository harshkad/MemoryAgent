"""
Produces the actual reply the user sees. Combines the conversation
history with relevant memories, then calls the LLM.
"""
from llm import call_llm
from config import CHAT_MODEL

BASE_SYSTEM_PROMPT = """You are a helpful, friendly assistant with memory of past conversations.

Keep replies short and direct -- a sentence or two for simple questions, more
only when the user actually needs detail (e.g. asks for an explanation, a list,
or code). Don't pad answers with unnecessary context, caveats, or restating
the question.

You may be given a list of known facts about the user below. Use them naturally
and only when relevant -- don't force them into every reply or repeat them back
like a list. If nothing is relevant to the current message, just ignore them.
"""


def build_system_prompt(memories: list[str]) -> str:
    if not memories:
        return BASE_SYSTEM_PROMPT

    memory_block = "\n".join(f"- {m}" for m in memories)
    return f"{BASE_SYSTEM_PROMPT}\nKnown about this user:\n{memory_block}"


def get_reply(user_message: str, memories: list[str], history: list[dict]) -> str:
    system_prompt = build_system_prompt(memories)
    messages = history + [{"role": "user", "content": user_message}]
    return call_llm(model=CHAT_MODEL, system_prompt=system_prompt, messages=messages)
