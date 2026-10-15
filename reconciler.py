"""
STEP 2 of saving memories: for every proposed fact, decide what to do with it.

    ADD     new information, or related to an existing memory but a separate
            fact that can be true at the same time ("likes pizza" + "likes pasta")
    UPDATE  replaces/refines ONE existing memory about the same attribute
            ("Lives in Delhi" -> "Now lives in Mumbai")
    NOOP    an existing memory already says it
    DELETE  the person takes an existing memory back, with no replacement

The model makes the judgement (it understands meaning, which embeddings do
not), but the CODE checks everything it says before anything is written:
  - the target id must be one we actually showed it
  - an existing memory can be targeted only once per batch
  - bad / missing answers become SKIP (nothing is saved) instead of a guess
"""
from llm import call_llm, parse_json_object
from config import RECONCILER_MODEL

RECONCILER_SYSTEM_PROMPT = """You keep one person's long-term memory list accurate and free of duplicates.

You get EXISTING memories (each with an id) and NEW candidate facts (numbered),
all about the same person. For each candidate choose exactly one action:

ADD    - the candidate is new, OR it is related to an existing memory but is a separate fact that can be true at the same time.
UPDATE - the candidate replaces or refines ONE existing memory about the same attribute of the same person, so the old memory is now wrong or less complete.
NOOP   - an existing memory already says the same thing (same meaning, equal or more detail).
DELETE - the person takes back or denies an existing memory and gives no replacement.

HOW TO DECIDE
1. Related is NOT the same. Two memories on the same topic usually both stay.
   "Likes pizza" + "Likes pasta" -> ADD.  "Has a dog named Bruno" + "Has a cat" -> ADD.  "Studies at X" + "Plays cricket" -> ADD.
2. Some attributes hold only ONE value at a time: current city, employer, job title, age, name, relationship status, current course or year. A new value for one of these -> UPDATE the old memory.
   Existing "Lives in Delhi", candidate "Now lives in Mumbai" -> UPDATE.
3. Many-valued things pile up: hobbies, foods, languages, skills, friends, pets, projects, goals. A new one -> ADD, never UPDATE.
4. Refinement: extra detail about the very same fact -> UPDATE, and "text" must keep every detail of the old memory that is still true.
   Existing "Studies computer science", candidate "Studies computer science at IIT Delhi" -> UPDATE with text "Studies computer science at IIT Delhi".
5. Never merge two different facts into one memory. Never UPDATE a memory only because it is on a similar topic.
6. If unsure between ADD and UPDATE, choose ADD. Choose NOOP only when an existing memory clearly already contains the fact.
7. Each existing id may be targeted by at most one candidate.

OUTPUT: JSON only, exactly this shape, one decision per candidate in order:
{"decisions": [{"candidate": 1, "reason": "max 12 words", "action": "ADD", "target_id": null, "text": null}]}
- target_id: required for UPDATE and DELETE (an id from the EXISTING list), otherwise null
- text: required for UPDATE (the full final memory, one short sentence), otherwise null
"""


def _to_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _same_text(a: str, b: str) -> bool:
    return " ".join(a.lower().split()).rstrip(".") == " ".join(b.lower().split()).rstrip(".")


def _skip(reason: str = "") -> dict:
    return {"action": "SKIP", "target_id": None, "text": None, "reason": reason}


def reconcile(existing: list[dict], candidates: list[dict], protected_ids: set | None = None) -> list[dict]:
    """
    existing:      memories the model may see, each with "id" and "fact"
    candidates:    [{"fact": ..., "category": ...}, ...]
    protected_ids: ids that must NOT be changed or deleted (used when someone ELSE
                   is telling us about a person: they may add, never overwrite).
    Returns one decision per candidate (same order):
        {"action": "ADD"|"UPDATE"|"NOOP"|"DELETE"|"SKIP", "target_id", "text", "reason"}
    """
    decisions = [_skip("no decision") for _ in candidates]
    if not candidates:
        return decisions
    protected_ids = protected_ids or set()

    existing_by_id = {m["id"]: m["fact"] for m in existing}

    existing_block = "\n".join(f"[{m['id']}] {m['fact']}" for m in existing) or "(none)"
    candidate_block = "\n".join(f"{i}. {c['fact']}" for i, c in enumerate(candidates, 1))
    content = f"EXISTING memories:\n{existing_block}\n\nNEW candidates:\n{candidate_block}"

    data = None
    for _attempt in range(2):
        raw = call_llm(
            model=RECONCILER_MODEL,
            system_prompt=RECONCILER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            max_tokens=900,
            temperature=0,
            json_mode=True,
        )
        parsed = parse_json_object(raw)
        if isinstance(parsed, dict) and isinstance(parsed.get("decisions"), list):
            data = parsed
            break
    if data is None:
        return decisions  # everything stays SKIP: save nothing rather than guess

    used_targets: set[int] = set()
    seen_candidates: set[int] = set()

    for item in data["decisions"]:
        if not isinstance(item, dict):
            continue
        number = _to_int(item.get("candidate"))
        if number is None or not (1 <= number <= len(candidates)):
            continue
        i = number - 1
        if i in seen_candidates:
            continue
        seen_candidates.add(i)

        action = str(item.get("action", "")).strip().upper()
        reason = item.get("reason") if isinstance(item.get("reason"), str) else ""
        target = _to_int(item.get("target_id"))
        text = item.get("text") if isinstance(item.get("text"), str) else ""
        text = " ".join(text.split())
        candidate_text = candidates[i]["fact"]

        if action == "ADD":
            decisions[i] = {"action": "ADD", "target_id": None, "text": None, "reason": reason}

        elif action == "NOOP":
            decisions[i] = {"action": "NOOP", "target_id": None, "text": None, "reason": reason}

        elif action in ("UPDATE", "DELETE"):
            if target not in existing_by_id:
                decisions[i] = _skip("target id was not one of the existing memories")
            elif target in protected_ids:
                # Not allowed to change this memory. An UPDATE is kept safely as a
                # separate new memory (it will show as "told by ..."); a DELETE is ignored.
                if action == "UPDATE":
                    decisions[i] = {"action": "ADD", "target_id": None, "text": None,
                                    "reason": "target is protected"}
                else:
                    decisions[i] = _skip("target is protected")
            elif target in used_targets:
                # Two new facts want the same old memory. The first one wins;
                # a second UPDATE is kept safely as its own new memory.
                if action == "UPDATE":
                    decisions[i] = {"action": "ADD", "target_id": None, "text": None,
                                    "reason": "target already used"}
                else:
                    decisions[i] = _skip("target already used")
            elif action == "DELETE":
                used_targets.add(target)
                decisions[i] = {"action": "DELETE", "target_id": target, "text": None, "reason": reason}
            else:
                new_text = text or candidate_text
                if len(new_text) > 300:
                    decisions[i] = _skip("update text too long")
                elif _same_text(new_text, existing_by_id[target]):
                    decisions[i] = {"action": "NOOP", "target_id": None, "text": None,
                                    "reason": "update would change nothing"}
                else:
                    used_targets.add(target)
                    decisions[i] = {"action": "UPDATE", "target_id": target,
                                    "text": new_text.rstrip("."), "reason": reason}

    return decisions
