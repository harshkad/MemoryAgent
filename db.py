"""
Everything to do with actually reading/writing the memories table.
Uses plain SQLite -- no server to install, just a local .db file.
"""
import sqlite3
from datetime import datetime, timezone
from config import DB_PATH


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            fact TEXT NOT NULL,
            category TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def add_memory(user_id: str, fact: str, category: str = "general"):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute(
        "INSERT INTO memories (user_id, fact, category, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, fact, category, now, now),
    )
    conn.commit()
    conn.close()


def update_memory(memory_id: int, new_fact: str):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute(
        "UPDATE memories SET fact = ?, updated_at = ? WHERE id = ?",
        (new_fact, now, memory_id),
    )
    conn.commit()
    conn.close()


def get_all_memories(user_id: str):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM memories WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_memory(memory_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    conn.commit()
    conn.close()
