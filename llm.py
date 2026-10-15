"""
One function that every other file uses to talk to Groq.
Groq speaks the same API shape as OpenAI, so we just point
the official `openai` library at Groq's base URL.
"""
import json
import re

from openai import OpenAI, BadRequestError
from config import GROQ_API_KEY, GROQ_BASE_URL

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url=GROQ_BASE_URL,
)


def call_llm(
    model: str,
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 300,
    temperature: float | None = None,
    json_mode: bool = False,
) -> str:
    """
    model: a Groq model id, e.g. "llama-3.3-70b-versatile"
    system_prompt: instructions for the model
    messages: list of {"role": "user"/"assistant", "content": "..."}
    max_tokens: cap on the length of the reply (default 300).
    temperature: 0 = same answer every time (use for extraction/decisions).
    json_mode: ask the API to return one valid JSON object. If the model or
               API rejects that option, we retry once without it.
    Returns the reply text as a plain string.
    """
    full_messages = [{"role": "system", "content": system_prompt}] + messages

    kwargs = dict(model=model, messages=full_messages, max_tokens=max_tokens)
    if temperature is not None:
        kwargs["temperature"] = temperature
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(**kwargs)
    except BadRequestError:
        if not json_mode:
            raise
        # JSON mode refused (unsupported, or the model's JSON failed validation).
        kwargs.pop("response_format")
        response = client.chat.completions.create(**kwargs)

    return response.choices[0].message.content or ""


def call_llm_stream(model: str, system_prompt: str, messages: list[dict], max_tokens: int = 300):
    """
    Same as call_llm, but yields the reply in small text pieces as the model
    produces them, so the UI can show it flowing in instead of waiting for
    the whole answer.
    """
    full_messages = [{"role": "system", "content": system_prompt}] + messages

    stream = client.chat.completions.create(
        model=model,
        messages=full_messages,
        max_tokens=max_tokens,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        piece = chunk.choices[0].delta.content
        if piece:
            yield piece


def parse_json_object(text: str):
    """
    Turns a model reply into a Python object, or returns None if it can't.
    Tolerates ```json fences and chatter before/after the JSON.
    """
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None
