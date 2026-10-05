"""
Takes newly extracted facts and decides: save as new, update an
existing memory, or skip because it's a duplicate.

Uses semantic embeddings (not word-matching) to catch paraphrased
duplicates -- e.g. "works at Jindal" and "employed at Jindal" are
recognized as the same fact even though the wording differs.
"""
from embeddings import embed, cosine_similarity
from db import get_all_memories, add_memory, update_memory
from config import DUPLICATE_THRESHOLD


def save_facts(user_id: str, new_facts: list[str]):
    existing = get_all_memories(user_id)

    for fact in new_facts:
        # Re-fetch each time so facts saved earlier in this same batch
        # are also checked against (avoids saving near-duplicates
        # from within a single extraction call).
        existing = get_all_memories(user_id)
        match = _find_similar_memory(fact, existing)
        if match is None:
            add_memory(user_id, fact)
        else:
            # Overwrite the old version -- treats the newest statement as current.
            # (e.g. "eats chicken now" replaces "is vegetarian")
            update_memory(match["id"], fact)


def _find_similar_memory(new_fact: str, existing: list[dict]):
    if not existing:
        return None

    existing_texts = [m["fact"] for m in existing]
    existing_vectors = embed(existing_texts)
    new_vector = embed([new_fact])[0]

    scores = [cosine_similarity(new_vector, v) for v in existing_vectors]
    best_idx = max(range(len(scores)), key=lambda i: scores[i])

    if scores[best_idx] >= DUPLICATE_THRESHOLD:
        return existing[best_idx]
    return None
