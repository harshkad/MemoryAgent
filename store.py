"""
STEP 2+3 of saving memories: take what the extractor proposed, ask the
reconciler what to do with each fact, and apply it to the database.

save_extraction() is the entry point. It:
  1. sends every fact to the profile it is ABOUT
       - about the speaker  -> the speaker's profile
       - about a known person -> THAT person's profile, tagged "told by <speaker>"
  2. records relationships in both directions ("Aman is Rahul's friend" and
     "Rahul is Aman's friend")
  3. for each profile: drops exact repeats, shows the reconciler a shortlist of
     that profile's memories, and applies ADD / UPDATE / NOOP / DELETE.

Rules that protect people's data:
  - Updates keep the old version (status 'superseded'); DELETE only marks 'retracted'.
  - When someone ELSE is telling us about a person, they can only ADD. They can
    never change or delete what the person said about themselves.
"""
import re

from embeddings import embed, embed_one, cosine_similarity, vec_to_bytes, bytes_to_vec
from db import (
    get_all_memories, add_memory, replace_memory, retire_memory,
    set_embedding, update_memory, add_relationship,
)
from reconciler import reconcile
from people import relation_pair
from config import RECONCILE_ALL_THRESHOLD, SHORTLIST_K


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())


def ensure_embeddings(memories: list[dict]) -> list:
    """
    One vector per memory (same order). Vectors are stored in the DB so they are
    computed once; any memory without one gets it here.
    """
    vectors = [None] * len(memories)
    missing = []
    for i, m in enumerate(memories):
        if m.get("embedding"):
            vectors[i] = bytes_to_vec(m["embedding"])
        else:
            missing.append(i)
    if missing:
        for i, vec in zip(missing, embed([memories[i]["fact"] for i in missing])):
            vectors[i] = vec
            try:
                set_embedding(memories[i]["id"], vec_to_bytes(vec))
            except Exception:
                pass  # not fatal: it will just be computed again next time
    return vectors


def edit_memory(memory_id: int, new_text: str):
    """Used by the Memories page when you edit a memory by hand."""
    update_memory(memory_id, new_text, vec_to_bytes(embed_one(new_text)))


def _empty_result() -> dict:
    return {"added": 0, "updated": 0, "deleted": 0, "unchanged": 0, "skipped": 0, "linked": 0, "log": []}


def save_facts(
    user_id: str,
    profile_id: int,
    candidates: list[dict],
    source_text: str = "",
    told_by: dict | None = None,
) -> dict:
    """
    Saves facts into ONE profile. `told_by` = {"id", "name"} when someone else
    said them. candidates: [{"fact", "category"}, ...]
    """
    result = _empty_result()
    if not candidates:
        return result
    told_id = told_by["id"] if told_by else None
    told_name = told_by["name"] if told_by else None

    existing = get_all_memories(user_id, profile_id)

    # 1. exact repeats are free to detect
    seen = {_norm(m["fact"]) for m in existing}
    fresh = []
    for c in candidates:
        key = _norm(c["fact"])
        if key in seen:
            result["unchanged"] += 1
            continue
        seen.add(key)
        fresh.append(c)
    if not fresh:
        return result

    candidate_vectors = embed([c["fact"] for c in fresh])

    def _add(c, vec):
        add_memory(user_id, profile_id, c["fact"], c["category"], vec_to_bytes(vec),
                   source_text, told_id, told_name)
        result["added"] += 1
        result["log"].append(f"ADD: {c['fact']}")

    # Nothing saved yet for this person: everything is simply new.
    if not existing:
        for c, vec in zip(fresh, candidate_vectors):
            _add(c, vec)
        return result

    # 2. shortlist: all memories if the person has few, else the closest ones
    existing_vectors = ensure_embeddings(existing)
    if len(existing) <= RECONCILE_ALL_THRESHOLD:
        shortlist = existing
    else:
        picked = set()
        for vec in candidate_vectors:
            scores = [cosine_similarity(vec, ev) for ev in existing_vectors]
            best = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:SHORTLIST_K]
            picked.update(best)
        shortlist = [existing[i] for i in sorted(picked)]

    # Someone else is talking about this person: they may not change what
    # the person (or anyone else) said, only what THEY said before.
    protected = set()
    if told_by:
        protected = {m["id"] for m in existing if m.get("told_by_id") != told_id}

    # 3. decide
    decisions = reconcile(shortlist, fresh, protected)

    # 4. apply
    for c, vec, d in zip(fresh, candidate_vectors, decisions):
        action = d["action"]
        if action == "ADD":
            _add(c, vec)
        elif action == "UPDATE":
            text = d["text"] or c["fact"]
            new_vec = vec if text == c["fact"] else embed_one(text)
            new_id = replace_memory(d["target_id"], text, c["category"], vec_to_bytes(new_vec),
                                    source_text, told_id, told_name)
            if new_id:
                result["updated"] += 1
                result["log"].append(f"UPDATE #{d['target_id']}: {text}")
            else:
                result["skipped"] += 1
        elif action == "DELETE":
            retire_memory(d["target_id"], "retracted")
            result["deleted"] += 1
            result["log"].append(f"DELETE #{d['target_id']}")
        elif action == "NOOP":
            result["unchanged"] += 1
        else:
            result["skipped"] += 1
            result["log"].append(f"SKIP: {c['fact']} ({d.get('reason', '')})")
    return result


def save_extraction(user_id: str, speaker: dict, extraction: dict, profiles: list[dict]) -> dict:
    """
    extraction: output of extractor.extract(). profiles: every profile (to find
    who a fact is about). Returns merged counts (added / updated / deleted /
    unchanged / skipped / linked).
    """
    total = _empty_result()
    by_name = {p["name"].lower(): p for p in profiles}

    # group facts by the profile they belong to
    groups: dict[int, list[dict]] = {}
    for f in extraction.get("facts", []):
        target = speaker
        if f["about"] != "self":
            target = by_name.get(f["about"].lower(), speaker)
        groups.setdefault(target["id"], []).append(f)

    for target_id, facts in groups.items():
        told_by = None if target_id == speaker["id"] else {"id": speaker["id"], "name": speaker["name"]}
        r = save_facts(user_id, target_id, facts, source_text=f"told by {speaker['name']}" if told_by else "",
                       told_by=told_by)
        for key in ("added", "updated", "deleted", "unchanged", "skipped"):
            total[key] += r[key]
        total["log"].extend(r["log"])

    # relationships, both directions
    for rel in extraction.get("relations", []):
        other = by_name.get(rel["person"].lower())
        if not other or other["id"] == speaker["id"]:
            continue
        mine, theirs = relation_pair(rel["relation"])
        if add_relationship(speaker["id"], other["id"], mine):
            total["linked"] += 1
            total["log"].append(f"LINK: {other['name']} is {speaker['name']}'s {mine}")
        if theirs and add_relationship(other["id"], speaker["id"], theirs):
            total["log"].append(f"LINK: {speaker['name']} is {other['name']}'s {theirs}")
    return total
