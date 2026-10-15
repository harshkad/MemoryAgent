"""
Loads settings from environment variables (or a .env file).
Nothing here talks to the network — it just centralizes config
so every other file can do `from config import CHAT_MODEL` etc.

Secrets (GROQ_API_KEY, DATABASE_URL) live ONLY in your .env file, never in code.
See .env.example for the list of variables.
"""
import os
from dotenv import load_dotenv

# override=True: values in .env win over any same-named variable already set in
# your system/user environment (a stale GROQ_API_KEY there would otherwise be
# used instead of the one in .env, and Groq would answer 401).
load_dotenv(override=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Pick any current model from https://console.groq.com/docs/models
CHAT_MODEL = os.getenv("CHAT_MODEL", "llama-3.3-70b-versatile")

# Small/fast model: reads each message and proposes facts, detects speaker changes.
EXTRACTOR_MODEL = os.getenv("EXTRACTOR_MODEL", "llama-3.1-8b-instant")

# Decides ADD / UPDATE / NOOP / DELETE for every proposed fact. This is the step
# that protects your data, so it defaults to the stronger chat model.
RECONCILER_MODEL = os.getenv("RECONCILER_MODEL") or CHAT_MODEL

# Neon connection string. Deliberately NO default: if it is missing the app
# stops with a clear message instead of silently using some other database.
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Connections kept open and reused (opening a fresh one per query is slow).
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "4"))

# --- Reading memories back into a reply ---
# How many past memories to pull into context per reply
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))

# Below this similarity score, a memory is considered irrelevant and dropped
RETRIEVAL_MIN_SCORE = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.4"))

# If a person has this many memories or fewer, skip filtering and include all.
ALWAYS_INCLUDE_THRESHOLD = int(os.getenv("ALWAYS_INCLUDE_THRESHOLD", "15"))

# --- Saving memories ---
# If a person has this many active memories or fewer, the reconciler is shown ALL
# of them for every new fact (most accurate). Above it, only the closest
# SHORTLIST_K memories per new fact are shown.
RECONCILE_ALL_THRESHOLD = int(os.getenv("RECONCILE_ALL_THRESHOLD", "25"))
SHORTLIST_K = int(os.getenv("SHORTLIST_K", "8"))

# Safety cap on how many facts one message may produce
MAX_FACTS_PER_MESSAGE = int(os.getenv("MAX_FACTS_PER_MESSAGE", "5"))

if not GROQ_API_KEY:
    print("WARNING: GROQ_API_KEY is not set. Add it to a .env file.")

if not DATABASE_URL:
    print("WARNING: DATABASE_URL is not set. Add your Neon connection string to a .env file.")
