"""
Turns text into embeddings (vectors that capture meaning, not just words)
using a small local model -- runs fully on your machine, free, no API call.

This is what fixes two things TF-IDF couldn't handle:
  - "Where do I work?" now matches "interning at Jindal" even though
    they share no words, because the model understands they're related.
  - Duplicate facts get caught more reliably, since paraphrases like
    "works at X" and "employed at X" land close together in meaning-space.

First run downloads a small model (~130MB, one-time, needs internet).
Every run after that is instant and fully offline.
"""
from fastembed import TextEmbedding
import numpy as np

_model = None


def _get_model():
    global _model
    if _model is None:
        _model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _model


def embed(texts: list[str]) -> list[np.ndarray]:
    """Turns a list of strings into a list of embedding vectors."""
    if not texts:
        return []
    return list(_get_model().embed(texts))


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
