"""
One function that every other file uses to talk to Groq.
Groq speaks the same API shape as OpenAI, so we just point
the official `openai` library at Groq's base URL.
"""
from openai import OpenAI
from config import GROQ_API_KEY, GROQ_BASE_URL

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url=GROQ_BASE_URL,
)


def call_llm(model: str, system_prompt: str, messages: list[dict]) -> str:
    """
    model: e.g. "deepseek/deepseek-chat-v3-0324:free"
    system_prompt: instructions for the model
    messages: list of {"role": "user"/"assistant", "content": "..."}
    Returns the reply text as a plain string.
    """
    full_messages = [{"role": "system", "content": system_prompt}] + messages

    response = client.chat.completions.create(
    model=model,
    messages=full_messages,
    max_tokens=300,
)
    return response.choices[0].message.content
