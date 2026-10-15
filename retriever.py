"""
Gathers everything the assistant may use for ONE reply, for the person who is
chatting:

  own            their active memories (all of them when they have few; the most
                 relevant ones, by meaning, when they have many). Facts that
                 someone else told us are labelled "told by ...".
  relationships  who they are linked to ("Aman (friend)")
  shared         what a LINKED friend has said about THEMSELVES, but only when
                 this message mentions that friend by name, the friend allows
                 sharing, and the fact is not sensitive.

Vectors are stored in the database, so only the question itself is embedded.
"""
from embeddings import embed_one, cosine_similarity
from db import get_all_memories, list_relationships, get_shareable_memories
from store import ensure_embeddings
from people import name_mentioned
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
    memories = get_all_memories(user_id, speaker["id"])
    if len(memories) > ALWAYS_INCLUDE_THRESHOLD:
        memories = _rank(memories, message, RETRIEVAL_TOP_K, RETRIEVAL_MIN_SCORE)
    own = [{"fact": m["fact"], "told_by": m.get("told_by_name")} for m in memories]

    links = list_relationships(speaker["id"])
    relationships: dict[str, list[str]] = {}
    for r in links:
        relationships.setdefault(r["name"], []).append(r["relation"])

    shared, done = [], set()
    for r in links:
        if r["other_id"] in done or not r["share_with_friends"] or not name_mentioned(message, r["name"]):
            continue
        done.add(r["other_id"])
        facts = get_shareable_memories(r["other_id"])
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
        "relationships": [(name, ", ".join(rels)) for name, rels in relationships.items()],
        "shared": shared,
    }
