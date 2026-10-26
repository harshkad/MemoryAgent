"""
"Forget that I live in Delhi": removing a memory by asking for it in the chat.

Why it needs its own step: the extractor is told never to save commands, so a forget
request produces no facts, and the reconciler can only delete when a NEW fact
contradicts an old one. Nothing connected "forget X" to the memory it means.

How it works (all of it runs BEFORE the reply, so the assistant can say truthfully
what happened):
  1. A cheap keyword check (looks_like_forget). Almost every message stops here and
     costs nothing extra.
  2. If it matches, one model call sees the message, the last turn (for "forget THAT")
     and the person's memories, and answers: is this a forget request, and which
     memory ids does it clearly mean?
  3. The CODE validates the answer, then deletes. Only memories we showed the model
     can be targeted; too many at once, or "forget everything", deletes nothing.
  4. The reply gets a note describing the outcome ("these were deleted" / "I couldn't
     tell which one you mean"), so it can't claim something that didn't happen.

What can be forgotten: what the person said about THEMSELVES, and what THEY told us
about others. Never what a friend said about them (retire_own_memory refuses it).
Deleting only marks a row 'deleted', so it stays restorable in the Memories page.
"""
import re

from config import FORGET_MODEL, MAX_FORGET_PER_MESSAGE, FORGET_CANDIDATE_LIMIT
from db import (
    get_all_memories, get_told_about_others, retire_own_memory, retire_told_memory,
)
from llm import call_llm, parse_json_object

# Step 1. Deliberately small. "forgot" is left out ("I forgot my keys").
_GATE = re.compile(
    r"\b(forget|delete|erase|remove|stop remembering|(?:do not|don['’]?t|no longer) remember)\b",
    re.IGNORECASE,
)


def looks_like_forget(message: str) -> bool:
    return bool(_GATE.search(message or ""))


FORGET_SYSTEM_PROMPT = """You help a memory-enabled assistant handle requests to forget things.

You get the speaker's latest MESSAGE, a little recent conversation (context only, to understand words like "that" or "it"), and the STORED MEMORIES about the speaker, each with an id. Memories marked "(about X)" are things the speaker told the assistant about another person X.

Decide two things:
1. Is the message a request to forget / erase / delete / stop remembering information that is stored about the speaker or about people they told the assistant about?
   NOT a request: deleting files, code, text or emails; removing items from a task; "forget it" or "never mind" meaning drop the subject; asking how memory works; hypotheticals.
2. If it is, which stored memories does it clearly refer to?

OUTPUT: JSON only, exactly this shape:
{"is_request": true, "ids": [12], "broad": false}
- ids: ids of the memories that CLEARLY match what the speaker wants forgotten. Use the recent conversation to resolve "that" / "it". If nothing matches clearly, or several are equally plausible, use [].
- broad: true when the speaker wants EVERYTHING forgotten, a whole category, or everything about a person. Then ids must be [].
- is_request false -> ids [] and broad false.

EXAMPLES
Memories: [3] Lives in Delhi / [4] Likes cricket
Message: "forget that I live in Delhi" -> {"is_request": true, "ids": [3], "broad": false}

Memories: [3] Lives in Delhi / [4] Likes cricket
Message: "please delete everything you know about me" -> {"is_request": true, "ids": [], "broad": true}

Memories: [3] Lives in Delhi / [4] Likes cricket
Message: "forget the cricket thing" -> {"is_request": true, "ids": [4], "broad": false}

Memories: [3] Lives in Delhi
Message: "forget it, I'll just do it myself" -> {"is_request": false, "ids": [], "broad": false}

Memories: [3] Lives in Delhi
Message: "delete the third paragraph of my essay" -> {"is_request": false, "ids": [], "broad": false}

Recent: the assistant just said "Want me to keep suggesting spicy dishes?" / Memories: [8] Likes spicy food
Message: "no, forget that" -> {"is_request": true, "ids": [8], "broad": false}

Memories: [3] Lives in Delhi / [4] Likes cricket
Message: "forget that" (and the recent conversation does not say what "that" is) -> {"is_request": true, "ids": [], "broad": false}
"""

NOTE_NONE = (
    "The person asked you to forget something, but you could not match it to a saved memory, "
    "so NOTHING was deleted. Say that briefly and ask what exactly they want forgotten; you can "
    "also mention they can manage everything on the Memories page."
)
NOTE_BROAD = (
    "The person asked you to forget a lot at once (everything, or a whole category). NOTHING was "
    "deleted. Tell them briefly to name the specific things to forget, or to use the Memories page "
    "to remove many at once."
)
NOTE_ERROR = (
    "The person asked you to forget something, but the memory system failed, so NOTHING was deleted. "
    "Say so briefly and suggest trying again or using the Memories page."
)


def _note_done(items: list[str]) -> str:
    return (
        "The person asked you to forget something and it is DONE: these saved memories were just "
        "deleted: " + "; ".join(items) + ". Confirm in one short, natural sentence what you forgot. "
        "Do not use those facts in this reply."
    )


def _to_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def parse_decision(raw: str, valid_ids: set[int], limit: int = MAX_FORGET_PER_MESSAGE) -> dict:
    """
    Turns the model's answer into {"is_request", "ids", "broad"}, trusting nothing.
    Raises ValueError when the answer isn't usable JSON (the caller reports an error
    rather than guessing). Rules:
      - only ids we actually showed the model survive (no invented targets)
      - more than `limit` ids, or "broad", means nothing is deleted
    """
    data = parse_json_object(raw)
    if not isinstance(data, dict) or not isinstance(data.get("is_request"), bool):
        raise ValueError("unusable answer")
    if not data["is_request"]:
        return {"is_request": False, "ids": [], "broad": False}
    ids: list[int] = []
    for value in data.get("ids") if isinstance(data.get("ids"), list) else []:
        number = _to_int(value)
        if number in valid_ids and number not in ids:
            ids.append(number)
    broad = data.get("broad") is True or len(ids) > limit
    return {"is_request": True, "ids": [] if broad else ids, "broad": broad}


def _candidates(user_id: str, speaker: dict) -> list[dict]:
    """The memories this person is allowed to forget, each tagged with how to delete it."""
    own = [dict(m, _kind="own") for m in get_all_memories(user_id, speaker["id"]) if not m.get("told_by_name")]
    told = [dict(m, _kind="told") for m in get_told_about_others(user_id, speaker["id"])]
    return own + told


def _last(history: list[dict], role: str) -> str:
    return next((m["content"] for m in reversed(history) if m["role"] == role), "")


def _decide(speaker: dict, message: str, history: list[dict], candidates: list[dict]) -> tuple[dict, list[dict]]:
    shown = candidates
    last_user, last_assistant = _last(history, "user"), _last(history, "assistant")
    if len(shown) > FORGET_CANDIDATE_LIMIT:
        from retriever import _rank  # local import: pulls in the embedding model only when needed
        shown = _rank(shown, f"{last_user} {message}", FORGET_CANDIDATE_LIMIT, None)

    def line(m):
        about = f"(about {m['subject_name']}) " if m["_kind"] == "told" else ""
        return f"[{m['id']}] {about}{m['fact']}"

    content = (
        f"Speaker: {speaker['name']}\n\n"
        "Recent conversation (context only):\n"
        f"User: {last_user[:300] or '(none)'}\nAssistant: {last_assistant[:300] or '(none)'}\n\n"
        f"Latest message:\n{message[:1000]}\n\n"
        "Stored memories:\n" + ("\n".join(line(m) for m in shown) or "(none)")
    )
    valid_ids = {m["id"] for m in shown}
    last_error = None
    for _attempt in range(2):
        raw = call_llm(
            model=FORGET_MODEL,
            system_prompt=FORGET_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            max_tokens=200,
            temperature=0,
            json_mode=True,
        )
        try:
            return parse_decision(raw, valid_ids), shown
        except ValueError as e:
            last_error = e
    raise last_error


def process_forget(user_id: str, speaker: dict, message: str, history: list[dict]) -> dict | None:
    """
    Returns None when this is not a forget request (carry on as a normal message), else
    {"forgotten": [texts actually deleted], "note": instruction for the reply}.
    Never raises: a failure becomes a note saying nothing was deleted.
    """
    if not looks_like_forget(message):
        return None
    try:
        decision, shown = _decide(speaker, message, history, _candidates(user_id, speaker))
    except Exception:
        return {"forgotten": [], "note": NOTE_ERROR}
    if not decision["is_request"]:
        return None
    if decision["broad"]:
        return {"forgotten": [], "note": NOTE_BROAD}
    if not decision["ids"]:
        return {"forgotten": [], "note": NOTE_NONE}

    by_id = {m["id"]: m for m in shown}
    forgotten, failed = [], False
    for memory_id in decision["ids"]:
        m = by_id[memory_id]
        try:
            if m["_kind"] == "told":
                done = retire_told_memory(memory_id, speaker["id"], "deleted")
            else:
                done = retire_own_memory(memory_id, speaker["id"], "deleted")
        except Exception:
            done, failed = False, True
        if done:
            forgotten.append(f"About {m['subject_name']}: {m['fact']}" if m["_kind"] == "told" else m["fact"])
    if not forgotten:
        return {"forgotten": [], "note": NOTE_ERROR if failed else NOTE_NONE}
    return {"forgotten": forgotten, "note": _note_done(forgotten)}
