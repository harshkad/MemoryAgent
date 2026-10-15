"""
Produces the actual reply the user sees. Combines the conversation history with
what is known about the person chatting (see retriever.build_context), then
calls the LLM.
"""
from llm import call_llm, call_llm_stream
from config import CHAT_MODEL, EXTRACTOR_MODEL

# Replies can include code blocks, so give them more room than the 300-token default.
REPLY_MAX_TOKENS = 1500

BASE_SYSTEM_PROMPT = """You are a helpful, friendly assistant with memory of past conversations.

Keep replies short and direct -- a sentence or two for simple questions, more
only when the user actually needs detail (e.g. asks for an explanation, a list,
or code). Don't pad answers with unnecessary context, caveats, or restating
the question.

Format replies in Markdown when it helps: **bold**, *italics*, bulleted or
numbered lists, and fenced code blocks with a language tag (e.g. ```python).
Plain short answers don't need any formatting.

You are given what is known about the person you are talking with. Use it
naturally and only when relevant -- don't force it into every reply or repeat it
back like a list. If nothing is relevant to the current message, ignore it.
"""


def build_system_prompt(speaker: dict, context: dict | None = None) -> str:
    context = context or {}
    name = speaker["name"]
    prompt = BASE_SYSTEM_PROMPT + f"\nYou are talking with {name}. Address them as {name} only if it feels natural.\n"

    own = context.get("own") or []
    if own:
        lines = [f"- {m['fact']}" + (f" (told by {m['told_by']})" if m.get("told_by") else "") for m in own]
        prompt += (
            f"\nKnown about {name}:\n" + "\n".join(lines) + "\n"
            f"Items marked 'told by' were said by someone else, not by {name}. "
            f"If one conflicts with something {name} said about themselves, trust {name}.\n"
        )

    relationships = context.get("relationships") or []
    if relationships:
        listing = ", ".join(f"{n} ({rel})" for n, rel in relationships)
        prompt += f"\nPeople in {name}'s life who also have a profile here: {listing}.\n"

    for friend in context.get("shared") or []:
        facts = "\n".join(f"- {f}" for f in friend["facts"])
        prompt += (
            f"\n{friend['name']} ({name}'s {friend['relation']}) has shared this about themselves:\n{facts}\n"
            f"Use it only if {name} asks about {friend['name']}, and share nothing beyond it.\n"
        )
    return prompt


def _build_messages(history: list[dict], user_message: str) -> list[dict]:
    # only role + content go to the API (history entries may carry extra keys)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_message})
    return messages


def get_reply(user_message: str, speaker: dict, context: dict, history: list[dict]) -> str:
    return call_llm(
        model=CHAT_MODEL,
        system_prompt=build_system_prompt(speaker, context),
        messages=_build_messages(history, user_message),
        max_tokens=REPLY_MAX_TOKENS,
    )


def get_reply_stream(user_message: str, speaker: dict, context: dict, history: list[dict]):
    """Like get_reply, but yields the reply piece by piece."""
    yield from call_llm_stream(
        model=CHAT_MODEL,
        system_prompt=build_system_prompt(speaker, context),
        messages=_build_messages(history, user_message),
        max_tokens=REPLY_MAX_TOKENS,
    )


TITLE_SYSTEM_PROMPT = """You write short titles for chat sessions.

Given the first exchange of a conversation, reply with ONLY a title for it:
2 to 5 words, naming the topic. No quotes, no trailing punctuation, no markdown.
"""


def fallback_title(user_message: str) -> str:
    """Instant title (start of the first message), shown until the model's title arrives."""
    text = " ".join(user_message.split())
    if not text:
        return "New chat"
    return text if len(text) <= 40 else text[:37].rstrip() + "..."


def generate_title(user_message: str, reply: str) -> str:
    """Short topic title for a chat. Never raises -- falls back to the start of
    the first message if the model call fails."""
    fallback = fallback_title(user_message)
    try:
        raw = call_llm(
            model=EXTRACTOR_MODEL,  # small/fast model, plenty for a title
            system_prompt=TITLE_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"User: {user_message[:500]}\nAssistant: {reply[:500]}",
            }],
            max_tokens=256,  # headroom: reasoning models spend some of this on hidden thinking
        )
    except Exception:
        return fallback

    lines = (raw or "").strip().splitlines()
    title = lines[0].strip().strip("\"'`*#").rstrip(".!?:").strip() if lines else ""
    return title[:50] or fallback
