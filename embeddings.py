"""
Turns text into embeddings (vectors that capture meaning, not just words)
using a small local model -- runs fully on your machine, free, no API call.

Embeddings are used to FIND which saved memories are close to a new fact
(a shortlist). They are NOT used to decide whether to overwrite anything:
two facts that differ by one word ("Lives in Delhi" / "Lives in Mumbai")
look almost identical to an embedding, so that decision is made by the
reconciler instead.

Vectors are saved in the database (as bytes) so they are only computed once
per memory.

First run downloads a small model (~130MB, one-time, needs internet).
Every run after that is instant and fully offline.
"""
import threading

from fastembed import TextEmbedding
import numpy as np

_model = None
_model_lock = threading.Lock()  # the app and its background worker can both ask at once


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _model


def embed(texts: list[str]) -> list[np.ndarray]:
    """Turns a list of strings into a list of embedding vectors."""
    if not texts:
        return []
    return list(_get_model().embed(texts))


def embed_one(text: str) -> np.ndarray:
    return embed([text])[0]


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def vec_to_bytes(vec) -> bytes:
    """For saving a vector in the database."""
    return np.asarray(vec, dtype=np.float32).tobytes()


def bytes_to_vec(data) -> np.ndarray:
    """For loading a saved vector back."""
    return np.frombuffer(bytes(data), dtype=np.float32)
