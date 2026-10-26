"""
Gathers everything the assistant may use for ONE reply, for the person who is
chatting:

  own            their active memories that THEY may see (all of them when they have
                 few; the most relevant ones, by meaning, when they have many).
                 Facts someone else told us about them appear here ONLY if the
                 teller chose to reveal them (visible_to_subject); then they are
                 labelled "told by ...". Hidden ones (a surprise party...) never do.
  told           what THEY told us about other people, so they can recall it.
                 Private to them: it is only ever put in their own prompt.
  relationships  who they are linked to ("Aman (friend)")
  shared         what a LINKED friend has said about THEMSELVES, but only when
                 this message mentions that friend by name, the friend allows
                 sharing, and the fact is not sensitive and does not name another
                 person who has a profile.

Vectors are stored in the database, so only the question itself is embedded.
"""
from embeddings import embed_one, cosine_similarity
from db import (
    get_all_memories, list_relationships, get_shareable_memories, get_told_about_others, list_profiles,
)
from store import ensure_embeddings
from people import name_mentioned, mentions_other_profile
from config import RETRIEVAL_TOP_K, RETRIEVAL_MIN_SCORE, ALWAYS_INCLUDE_THRESHOLD

SHARED_FACTS_PER_FRIEND = 6


def _rank(memories: list[dict], query: str, limit: int, min_score: float | None) -> list[dict]:
    vectors = ensure_embeddings(memories)
    query_vector = embed_one(query)
    scored = sorted(
        ((m, cosine_similarity(query_vector, v)) for m, v in zip(memories, vectors)),
        key=lambda x: x[1], reverse=True,
    )
    if min_score is not None:
        scored = [(m, s) for m, s in scored if s >= min_score]
    return [m for m, _ in scored[:limit]]


def build_context(user_id: str, speaker: dict, message: str) -> dict:
    # subject_view: never show this person what someone else told us about them in confidence
    memories = get_all_memories(user_id, speaker["id"], subject_view=True)
    if len(memories) > ALWAYS_INCLUDE_THRESHOLD:
        memories = _rank(memories, message, RETRIEVAL_TOP_K, RETRIEVAL_MIN_SCORE)
    own = [{"fact": m["fact"], "told_by": m.get("told_by_name")} for m in memories]

    told_rows = get_told_about_others(user_id, speaker["id"])
    if len(told_rows) > ALWAYS_INCLUDE_THRESHOLD:
        told_rows = _rank(told_rows, message, RETRIEVAL_TOP_K, RETRIEVAL_MIN_SCORE)
    told = [{"about": m["subject_name"], "fact": m["fact"]} for m in told_rows]

    links = list_relationships(speaker["id"])
    relationships: dict[str, list[str]] = {}
    for r in links:
        relationships.setdefault(r["name"], []).append(r["relation"])

    shared, done, all_profiles = [], set(), None
    for r in links:
        if r["other_id"] in done or not r["share_with_friends"] or not name_mentioned(message, r["name"]):
            continue
        done.add(r["other_id"])
        facts = get_shareable_memories(r["other_id"])
        if facts:
            if all_profiles is None:
                all_profiles = list_profiles(user_id)
            facts = [f for f in facts if not mentions_other_profile(f["fact"], r["other_id"], all_profiles)]
        if len(facts) > SHARED_FACTS_PER_FRIEND:
            facts = _rank(facts, message, SHARED_FACTS_PER_FRIEND, None)
        if facts:
            shared.append({
                "name": r["name"],
                "relation": ", ".join(relationships[r["name"]]),
                "facts": [m["fact"] for m in facts],
            })

    return {
        "own": own,
        "told": told,
        "relationships": [(name, ", ".join(rels)) for name, rels in relationships.items()],
        "shared": shared,
    }
