"""
After a chat exchange, ask the LLM: "was there anything worth
remembering here?" and get back a clean list of short facts.

Known facts are included in the prompt so the model doesn't keep
re-extracting the same thing every time it comes up in conversation --
it only reports something if it's new or updates an existing fact.
"""
import json
from llm import call_llm
from config import EXTRACTOR_MODEL

EXTRACTOR_SYSTEM_PROMPT = """You extract durable facts about the user from a conversation.

Only extract things worth remembering long-term: preferences, personal details,
ongoing projects, opinions, decisions. Ignore small talk, greetings, and anything
temporary or already obvious from context.

You will be given a list of facts already known about the user. Do NOT
re-extract anything already covered by that list. Only report a fact if it is
genuinely new, or if it updates/contradicts something already known (in which
case, report the new, corrected version).

Respond with ONLY a JSON array of short, plain-English facts, each written as a
standalone sentence about the user. No other text, no markdown formatting.

Example response:
["Prefers vegetarian food", "Is building a fitness tracking app"]

If there is nothing new worth remembering, respond with exactly: []
"""


def extract_facts(user_message: str, assistant_reply: str, known_facts: list[str] = None) -> list[str]:
    known_facts = known_facts or []
    known_block = "\n".join(f"- {f}" for f in known_facts) if known_facts else "(none yet)"

    conversation_text = (
        f"Already known about the user:\n{known_block}\n\n"
        f"New exchange:\nUser: {user_message}\nAssistant: {assistant_reply}"
    )

    raw_output = call_llm(
        model=EXTRACTOR_MODEL,
        system_prompt=EXTRACTOR_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": conversation_text}],
    )

    try:
        facts = json.loads(raw_output.strip())
        if isinstance(facts, list):
            return [f for f in facts if isinstance(f, str) and f.strip()]
    except (json.JSONDecodeError, AttributeError):
        pass

    return []