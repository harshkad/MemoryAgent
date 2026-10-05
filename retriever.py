"""
Finds which saved memories are relevant to the current message.

Uses real semantic embeddings (via embeddings.py) so it can match on
meaning, not just shared words -- "where do I work" now correctly
matches a saved memory like "interning at Jindal".

If you only have a handful of memories saved, there's no point being
clever about filtering -- we just include all of them. Filtering only
kicks in once the list gets long enough that dumping everything would
bloat the prompt.
"""
from embeddings import embed, cosine_similarity
from db import get_all_memories
from config import RETRIEVAL_TOP_K, RETRIEVAL_MIN_SCORE, ALWAYS_INCLUDE_THRESHOLD


def get_relevant_memories(user_id: str, query: str) -> list[str]:
    memories = get_all_memories(user_id)
    if not memories:
        return []

    facts = [m["fact"] for m in memories]

    # Small memory list -- just include everything, no filtering needed.
    if len(facts) <= ALWAYS_INCLUDE_THRESHOLD:
        return facts

    # Larger list -- rank by semantic similarity to the current message.
    fact_vectors = embed(facts)
    query_vector = embed([query])[0]

    scored = [
        (fact, cosine_similarity(query_vector, vec))
        for fact, vec in zip(facts, fact_vectors)
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    relevant = [fact for fact, score in scored if score >= RETRIEVAL_MIN_SCORE]
    return relevant[:RETRIEVAL_TOP_K]
