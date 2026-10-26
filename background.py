"""
Runs the slow work (asking the model what to remember, saving it, writing a chat
title) on a background thread, so the page is free again the moment the reply
has finished streaming instead of waiting several seconds.

ONE worker thread, first come first served: message 2's memory work only starts
after message 1's has finished, so the reconciler always sees up-to-date memories.

The app keeps the returned Future objects and checks them on its next run
(see collect_background in streamlit_app.py). Nothing in here touches Streamlit.
"""
import threading
from concurrent.futures import ThreadPoolExecutor, Future

_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()
_warmed = False


def submit(fn, *args, **kwargs) -> Future:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="memory-worker")
    return _executor.submit(fn, *args, **kwargs)


def warm_up():
    """Loads the embedding model once, in the background, so the first message isn't slow."""
    global _warmed
    with _lock:
        if _warmed:
            return
        _warmed = True

    def _load():
        try:
            from embeddings import embed
            embed(["warm up"])
        except Exception:
            pass  # not fatal: it just loads on first use instead

    submit(_load)


def wait_idle(futures, timeout: float = 15.0):
    """
    Waits (at most `timeout` seconds) for the given jobs to finish. Used before a
    "forget ..." request, so a memory from the message just before it has been saved
    and can actually be found. Never raises; a job's own error is reported by the app.
    """
    from concurrent.futures import wait
    pending = [f for f in futures if not f.done()]
    if pending:
        wait(pending, timeout=timeout)


# ---------------------------------------------------------------- the jobs

def remember(user_id: str, speaker: dict, user_message: str, prev_assistant: str) -> dict:
    """Extract -> reconcile -> save. Returns the counts from store.save_extraction."""
    from db import list_profiles
    from extractor import extract
    from store import save_extraction

    profiles = list_profiles(user_id)
    others = [p["name"] for p in profiles if p["id"] != speaker["id"]]
    extraction = extract(user_message, speaker["name"], others, prev_assistant)
    if not extraction["facts"] and not extraction["relations"]:
        return {"added": 0, "updated": 0, "deleted": 0, "unchanged": 0, "skipped": 0, "linked": 0, "log": []}
    return save_extraction(user_id, speaker, extraction, profiles)


def make_title(session_id: str, user_message: str, reply: str) -> tuple[str, str]:
    from agent import generate_title
    return session_id, generate_title(user_message, reply)
