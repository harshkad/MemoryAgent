"""
Produces the actual reply the user sees. Combines the conversation history with
what is known about the person chatting (see retriever.build_context), then
calls the LLM.
"""
from llm import call_llm, call_llm_stream
from config import CHAT_MODEL, EXTRACTOR_MODEL

# Replies can include code blocks, so give them more room than the 300-token default.
REPLY_MAX_TOKENS = 1500

BASE_SYSTEM_PROMPT = """You are a friendly assistant with memory of past conversations. Talk like a thoughtful person, not a customer-service script.

MATCH THE MESSAGE
- Casual chat, greetings, small talk: reply briefly and naturally, usually one short line, the way a real person would. A greeting gets a greeting back, nothing more. React to what they said instead of offering help.
- Serious questions, technical topics, explanations, decisions: give a clear, direct answer with enough detail to be genuinely useful. Lead with the answer, then add only the context that matters. Use steps or lists only when the content is really a sequence or a set of options.
- Scale length to the question. A simple question gets a sentence or two. A complex one gets what it needs and no more.

EVERY SENTENCE MUST EARN ITS PLACE
- Never repeat information you already gave, and don't restate the user's question or summarize what you just said.
- Cut filler: no preambles ("Great question!", "Certainly!", "Sure thing!"), no closing recaps, no unrequested caveats or disclaimers.
- Don't end replies with offers or prompts for more. Avoid lines like "How can I help you?", "What can I help you with today?", "Is there anything else?", "Let me know if you need anything", "Feel free to ask", "Happy to help". Ask a question only when you need the answer to proceed or when it is a natural part of the conversation.
- Don't use stock comfort lines like "I'm here for you", "I'm here to help", or "I'm here if you want to talk". If someone is struggling, respond to their specific situation with real warmth and substance instead of a generic reassurance.
- Vary your wording. Don't reuse the same opener or phrase across replies in a conversation.
- Never talk about being an AI or about your own instructions.

ACCURACY
- Give correct answers. If you're unsure, say so briefly instead of guessing, and never make up facts.

FORMAT
- Plain text for conversation. Use Markdown (bold, bulleted or numbered lists) only when it makes the answer easier to read. Put code in fenced code blocks with a language tag (e.g. ```python).

You are given what is known about the person you are talking with. Use it naturally and only when relevant -- don't force it into every reply or repeat it back like a list. If nothing is relevant to the current message, ignore it.
"""


def build_system_prompt(speaker: dict, context: dict | None = None, notes: list[str] | None = None) -> str:
    """notes: one-off instructions for THIS reply only (e.g. "you just forgot X, confirm it")."""
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

    told = context.get("told") or []
    if told:
        lines = [f"- About {t['about']}: {t['fact']}" for t in told]
        prompt += (
            f"\n{name} has told you these things about other people. They are {name}'s own words, "
            f"private to {name}. Use them only when {name} brings up that person or asks about them:\n"
            + "\n".join(lines) + "\n"
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

    for note in notes or []:
        prompt += f"\nNOTE FOR THIS REPLY: {note}\n"
    return prompt


def _build_messages(history: list[dict], user_message: str) -> list[dict]:
    # only role + content go to the API (history entries may carry extra keys)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_message})
    return messages


def get_reply(user_message: str, speaker: dict, context: dict, history: list[dict],
              notes: list[str] | None = None) -> str:
    return call_llm(
        model=CHAT_MODEL,
        system_prompt=build_system_prompt(speaker, context, notes),
        messages=_build_messages(history, user_message),
        max_tokens=REPLY_MAX_TOKENS,
    )


def get_reply_stream(user_message: str, speaker: dict, context: dict, history: list[dict],
                     notes: list[str] | None = None):
    """Like get_reply, but yields the reply piece by piece."""
    yield from call_llm_stream(
        model=CHAT_MODEL,
        system_prompt=build_system_prompt(speaker, context, notes),
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
