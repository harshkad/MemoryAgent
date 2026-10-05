"""
Loads settings from environment variables (or a .env file).
Nothing here talks to the network — it just centralizes config
so every other file can do `from config import CHAT_MODEL` etc.
"""
import os
from dotenv import load_dotenv

load_dotenv()  # reads a local .env file if present

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Pick any current model from https://console.groq.com/docs/models
# (Groq's free tier applies per-account rate limits, not a ":free" suffix
# on the model name like OpenRouter -- just use the plain model id.)
CHAT_MODEL = os.getenv("CHAT_MODEL", "llama-3.3-70b-versatile")
EXTRACTOR_MODEL = os.getenv("EXTRACTOR_MODEL", "llama-3.1-8b-instant")

DB_PATH = os.getenv("DB_PATH", "memory.db")

# How many past memories to pull into context per reply
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))

# Below this similarity score, a memory is considered irrelevant and dropped
# (embeddings similarity scores run higher than TF-IDF ones did, hence 0.4 not 0.08)
RETRIEVAL_MIN_SCORE = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.4"))

# If you have this many memories or fewer, skip filtering and include all of
# them -- not worth being clever about relevance until the list gets long.
ALWAYS_INCLUDE_THRESHOLD = int(os.getenv("ALWAYS_INCLUDE_THRESHOLD", "15"))

# How similar two facts must be (0-1) to be treated as duplicates/updates
DUPLICATE_THRESHOLD = float(os.getenv("DUPLICATE_THRESHOLD", "0.75"))

if not GROQ_API_KEY:
    print("WARNING: GROQ_API_KEY is not set. Add it to a .env file.")