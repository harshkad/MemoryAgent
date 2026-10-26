"""
STEP 1 of saving memories: read ONE message and propose what to remember.

It only PROPOSES. It never touches the database and never decides whether
something is a duplicate or an update -- that is the reconciler's job.

New: every fact says who it is ABOUT.
  about = "self"      a fact about the person typing
  about = "Aman"      a fact about someone who has their own profile (it will be
                      saved into Aman's profile, tagged "told by <speaker>")
Anyone without a profile is simply named inside a fact about the speaker.
It can also report relationships ("Aman is my friend").

Safety:
  - only the person's own words are used; the assistant's earlier message is context
  - temperature 0 + JSON mode
  - a grounding check drops facts whose names/numbers were never said
  - "about" must be the speaker or a REAL profile name, otherwise it falls back to self
"""
import re

from llm import call_llm, parse_json_object
from config import EXTRACTOR_MODEL, MAX_FACTS_PER_MESSAGE

CATEGORIES = {
    "identity", "location", "education", "work", "skill", "preference",
    "habit", "project", "goal", "relationship", "health", "other",
}

EXTRACTOR_SYSTEM_PROMPT = """You are the memory extractor for a personal AI assistant.
You read ONE message written by a person (the "speaker") and decide what is worth
remembering. Some people also have their own profile ("known people").

SAVE facts such as:
- who someone is: name, age, location, languages, background
- education, work, skills, tools
- stable preferences, likes, dislikes, habits, routines, dietary rules
- ongoing projects, goals, plans, decisions
- people in their life (relationships)
- constraints or circumstances that will matter later

NEVER save:
- questions, requests, commands, greetings, thanks, small talk
- hypotheticals, jokes, role-play, examples, "what if", or text pasted/quoted from somewhere else
- temporary states (hungry, tired, busy today, current mood, what someone is doing this minute)
- anything only the assistant said. The assistant's message is context only; save something from it ONLY if the speaker clearly confirms it
- general facts about the world
- guesses. Only save what was actually stated or clearly confirmed

WHO A FACT IS ABOUT ("about"):
- "self" when it is about the speaker.
- A known person's EXACT name when the speaker states a fact about that known person. Write the fact WITHOUT repeating the name ("Loves cricket").
- For anyone who is NOT in the known people list, use "self" and name that person inside the fact: "Has a cousin named Sam who is moving to Delhi".
- If the speaker says something about both themselves and a known person ("Aman and I study at IIT Delhi"), write two facts.

RELATIONS: if the speaker says a KNOWN person is their friend / brother / sister / cousin / colleague / roommate / wife / husband / partner / father / mother / son / daughter etc., add {"person": "<exact known name>", "relation": "<one or two lowercase words>"}.

HOW TO WRITE EACH FACT:
- One fact per item. Never combine two separate things.
- A short standalone sentence with no subject word: "Lives in Delhi", "Is allergic to peanuts", "Is learning guitar".
- Keep exact names, numbers and wording. Do not add details, interpret or infer.
- If something changed or stopped, write the NEW current state: "Now lives in Mumbai", "No longer eats chicken".
- Avoid relative time words (today, recently, last month); they go stale.
- At most 5 facts.

OUTPUT: JSON only, exactly this shape:
{"facts": [{"fact": "...", "category": "...", "about": "self"}], "relations": [{"person": "...", "relation": "..."}]}
category is one of: identity, location, education, work, skill, preference, habit, project, goal, relationship, health, other.
If there is nothing to save return {"facts": [], "relations": []}.

EXAMPLES
Speaker: Rahul. Known people: Aman, Priya.
Message: "My friend Aman loves cricket and I play chess."
{"facts": [{"fact": "Loves cricket", "category": "preference", "about": "Aman"}, {"fact": "Plays chess", "category": "preference", "about": "self"}], "relations": [{"person": "Aman", "relation": "friend"}]}

Speaker: Rahul. Known people: Aman.
Message: "My cousin Sam is moving to Delhi."
{"facts": [{"fact": "Has a cousin named Sam who is moving to Delhi", "category": "relationship", "about": "self"}], "relations": []}

Speaker: Rahul. Known people: Aman.
Message: "Aman and I both study at IIT Delhi."
{"facts": [{"fact": "Studies at IIT Delhi", "category": "education", "about": "self"}, {"fact": "Studies at IIT Delhi", "category": "education", "about": "Aman"}], "relations": []}

Speaker: Priya. Known people: Rahul.
Message: "Can you write an email to my boss asking for leave tomorrow?"
{"facts": [], "relations": []}

Speaker: Priya. Known people: Rahul.
Message: "Actually I moved to Mumbai last month."
{"facts": [{"fact": "Now lives in Mumbai", "category": "location", "about": "self"}], "relations": []}

Speaker: Priya. Known people: none.
Previous assistant message (context only): "Want me to stick to vegetarian recipes?"
Message: "yes always"
{"facts": [{"fact": "Prefers vegetarian recipes", "category": "preference", "about": "self"}], "relations": []}
"""

# Words that may start with a capital letter without being a name from the message.
_IGNORED_TOKENS = {"user", "speaker", "he", "she", "they", "the"}


def _alnum(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _is_grounded(fact: str, source_text: str, speaker_name: str) -> bool:
    """
    True if every proper name and number in the fact also appears in the source
    text. A fact like "Works at Google" is rejected when nobody mentioned Google.
    """
    source = _alnum(source_text)
    skip = {_alnum(w) for w in speaker_name.split()} | _IGNORED_TOKENS
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9.'’+#-]*", fact)
    for i, word in enumerate(words):
        has_digit = any(ch.isdigit() for ch in word)
        is_name = word[0].isupper() and i > 0
        if not (has_digit or is_name):
            continue
        token = _alnum(word)
        if not token or token in skip:
            continue
        if token not in source:
            return False
    return True


def extract(
    user_message: str,
    speaker_name: str,
    other_names: list[str] | None = None,
    prev_assistant: str = "",
) -> dict:
    """
    Returns {"facts": [{"fact", "category", "about"}], "relations": [{"person", "relation"}]}.
    "about" is "self" or the exact name of one of other_names.
    Raises if the model call itself fails (the caller reports it).
    """
    empty = {"facts": [], "relations": []}
    if len(user_message.strip()) < 4:
        return empty

    others = [n for n in (other_names or []) if n and n.lower() != speaker_name.lower()]
    canonical = {n.lower(): n for n in others}

    content = f"Speaker: {speaker_name}. Known people: {', '.join(others) if others else 'none'}.\n\n"
    if prev_assistant:
        content += (
            "Previous assistant message (context only, do not extract from it):\n"
            f"{prev_assistant[:500]}\n\n"
        )
    content += f"Message:\n{user_message[:3000]}"

    raw = call_llm(
        model=EXTRACTOR_MODEL,
        system_prompt=EXTRACTOR_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
        max_tokens=800,
        temperature=0,
        json_mode=True,
    )
    data = parse_json_object(raw)
    if not isinstance(data, dict):
        return empty

    grounding_source = f"{user_message}\n{prev_assistant}"
    message_alnum = _alnum(user_message)

    facts, seen = [], set()
    items = data.get("facts") if isinstance(data.get("facts"), list) else []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("fact"), str):
            continue
        fact = " ".join(item["fact"].split()).rstrip(".")
        if not (3 <= len(fact) <= 250):
            continue

        about = item.get("about")
        about = canonical.get(str(about).strip().lower()) if isinstance(about, str) else None
        # about is None -> "self" (also the safe fallback for any name we don't know)
        if about is not None and _alnum(about) not in message_alnum:
            continue  # claims it is about someone the message never named

        key = (about or "self", fact.lower())
        if key in seen:
            continue
        if not _is_grounded(fact, grounding_source, speaker_name):
            continue
        category = item.get("category")
        if not isinstance(category, str) or category.lower() not in CATEGORIES:
            category = "other"
        seen.add(key)
        facts.append({"fact": fact, "category": category.lower(), "about": about or "self"})
        if len(facts) >= MAX_FACTS_PER_MESSAGE:
            break

    relations, seen_rel = [], set()
    items = data.get("relations") if isinstance(data.get("relations"), list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        person = canonical.get(str(item.get("person", "")).strip().lower())
        relation = item.get("relation")
        if not person or not isinstance(relation, str):
            continue
        relation = " ".join(relation.lower().split())
        if not (2 <= len(relation) <= 30) or not re.fullmatch(r"[a-zé' -]+", relation):
            continue
        if _alnum(person) not in message_alnum:
            continue
        if (person, relation) in seen_rel:
            continue
        seen_rel.add((person, relation))
        relations.append({"person": person, "relation": relation})

    return {"facts": facts, "relations": relations}
