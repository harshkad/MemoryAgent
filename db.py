"""
Everything to do with reading/writing the database (Neon / Postgres).

Tables
  profiles       one row per PERSON using the app (name + their pale colour +
                 whether friends may see their info)
  relationships  "Aman is Rahul's friend" -- one row per direction
  memories       one row per remembered fact, belonging to one profile.
                 status = 'active'      the current version (used in replies)
                          'superseded'  an older version, replaced by a newer row
                          'retracted'   the person took it back
                          'deleted'     removed by hand in the Memories page
                 told_by_name is set when SOMEONE ELSE said it ("told by Rahul").
                 Nothing is overwritten automatically: an update adds a new row
                 and marks the old one 'superseded', so it can be restored.
  app_meta       remembers the schema version

Speed: one pool of ready connections is shared by the whole app, so a query does
not pay for a new TLS connection to Neon every time.

Fresh start: init_db() creates version-2 tables. If it finds the OLD layout
and those tables are empty, it recreates them (so IDs start at 1 again). If the
old tables still hold data it stops and asks you to run reset_db.py.
"""
import threading

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from config import DATABASE_URL, DB_POOL_MAX

SCHEMA_VERSION = "2"

_pool = None
_pool_lock = threading.Lock()
_init_lock = threading.Lock()
_initialized = False


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                if not DATABASE_URL:
                    raise RuntimeError(
                        "DATABASE_URL is not set. Add your Neon connection string to a "
                        ".env file (see .env.example)."
                    )
                pool = ConnectionPool(
                    DATABASE_URL,
                    min_size=1,
                    max_size=DB_POOL_MAX,
                    open=False,
                    # prepare_threshold=None: works with Neon's pooled endpoint too
                    kwargs={"row_factory": dict_row, "prepare_threshold": None, "connect_timeout": 15},
                    check=ConnectionPool.check_connection,  # drops connections Neon has put to sleep
                    max_idle=120,
                    max_lifetime=900,
                )
                try:
                    pool.open(wait=True, timeout=25)
                except PoolTimeout:
                    pool.close()
                    raise RuntimeError(
                        "Couldn't reach the database in time. Check DATABASE_URL and your internet connection."
                    ) from None
                _pool = pool
    return _pool


def _conn():
    """`with _conn() as conn:` -> commits on success, rolls back on error, returns it to the pool."""
    return get_pool().connection()


# ------------------------------------------------------------------ setup

OLD_DATA_MESSAGE = (
    "Your database still holds memories from an older version of this app. "
    "To start fresh (IDs from 1), run:  python reset_db.py"
)


def _create_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id            TEXT NOT NULL,
            name               TEXT NOT NULL,
            color              TEXT NOT NULL,
            share_with_friends BOOLEAN NOT NULL DEFAULT TRUE,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_name ON profiles (user_id, lower(name))")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            profile_id       BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            other_profile_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            relation         TEXT NOT NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (profile_id, other_profile_id, relation)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id       TEXT NOT NULL,
            profile_id    BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            fact          TEXT NOT NULL,
            category      TEXT NOT NULL DEFAULT 'other',
            status        TEXT NOT NULL DEFAULT 'active',
            supersedes_id BIGINT,
            embedding     BYTEA,
            source_text   TEXT,
            told_by_id    BIGINT REFERENCES profiles(id) ON DELETE SET NULL,
            told_by_name  TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_profile_status ON memories (profile_id, status)")


def init_db():
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        with _conn() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(727001)")  # two app sessions can't set up at once
            conn.execute("CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            row = conn.execute("SELECT value FROM app_meta WHERE key = 'schema_version'").fetchone()
            if not row or row["value"] != SCHEMA_VERSION:
                has_old = conn.execute("SELECT to_regclass('public.memories') AS t").fetchone()["t"]
                if has_old:
                    n = conn.execute("SELECT count(*) AS n FROM memories").fetchone()["n"]
                    if n:
                        raise RuntimeError(OLD_DATA_MESSAGE)
                # nothing worth keeping: rebuild so IDs start from 1
                conn.execute("DROP TABLE IF EXISTS memories, relationships, profiles CASCADE")
            _create_tables(conn)
            conn.execute(
                "INSERT INTO app_meta (key, value) VALUES ('schema_version', %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                (SCHEMA_VERSION,),
            )
        _initialized = True


# --------------------------------------------------------------- profiles

def list_profiles(user_id: str) -> list[dict]:
    with _conn() as conn:
        return conn.execute("SELECT * FROM profiles WHERE user_id = %s ORDER BY id", (user_id,)).fetchall()


def get_profile(profile_id: int) -> dict | None:
    with _conn() as conn:
        return conn.execute("SELECT * FROM profiles WHERE id = %s", (profile_id,)).fetchone()


def find_profile_by_name(user_id: str, name: str) -> dict | None:
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM profiles WHERE user_id = %s AND lower(name) = lower(%s)", (user_id, name)
        ).fetchone()


def create_profile(user_id: str, name: str, color: str) -> dict | None:
    """Returns the new profile, or None if someone already has that name."""
    with _conn() as conn:
        return conn.execute(
            "INSERT INTO profiles (user_id, name, color) VALUES (%s, %s, %s) "
            "ON CONFLICT DO NOTHING RETURNING *",
            (user_id, name, color),
        ).fetchone()


def rename_profile(profile_id: int, user_id: str, new_name: str) -> bool:
    """False if another person already has that name."""
    with _conn() as conn:
        clash = conn.execute(
            "SELECT 1 FROM profiles WHERE user_id = %s AND lower(name) = lower(%s) AND id <> %s",
            (user_id, new_name, profile_id),
        ).fetchone()
        if clash:
            return False
        conn.execute("UPDATE profiles SET name = %s WHERE id = %s", (new_name, profile_id))
    return True


def set_share(profile_id: int, share: bool):
    with _conn() as conn:
        conn.execute("UPDATE profiles SET share_with_friends = %s WHERE id = %s", (share, profile_id))


def delete_profile(profile_id: int):
    """Also deletes that person's memories and relationships (cascade)."""
    with _conn() as conn:
        conn.execute("DELETE FROM profiles WHERE id = %s", (profile_id,))


# ----------------------------------------------------------- relationships

def add_relationship(profile_id: int, other_id: int, relation: str) -> bool:
    """True if it was new."""
    with _conn() as conn:
        row = conn.execute(
            "INSERT INTO relationships (profile_id, other_profile_id, relation) VALUES (%s, %s, %s) "
            "ON CONFLICT DO NOTHING RETURNING id",
            (profile_id, other_id, relation),
        ).fetchone()
    return row is not None


def list_relationships(profile_id: int) -> list[dict]:
    """People this profile is linked to: relation, other_id, name, color, share_with_friends."""
    with _conn() as conn:
        return conn.execute(
            "SELECT r.relation, p.id AS other_id, p.name, p.color, p.share_with_friends "
            "FROM relationships r JOIN profiles p ON p.id = r.other_profile_id "
            "WHERE r.profile_id = %s ORDER BY r.id",
            (profile_id,),
        ).fetchall()


# ---------------------------------------------------------------- memories

def add_memory(
    user_id: str,
    profile_id: int,
    fact: str,
    category: str = "other",
    embedding: bytes | None = None,
    source_text: str | None = None,
    told_by_id: int | None = None,
    told_by_name: str | None = None,
    supersedes_id: int | None = None,
) -> int:
    with _conn() as conn:
        row = conn.execute(
            "INSERT INTO memories (user_id, profile_id, fact, category, embedding, source_text, "
            "told_by_id, told_by_name, supersedes_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (user_id, profile_id, fact, category, embedding, source_text, told_by_id, told_by_name, supersedes_id),
        ).fetchone()
    return row["id"]


def replace_memory(
    old_id: int,
    new_fact: str,
    category: str | None = None,
    embedding: bytes | None = None,
    source_text: str | None = None,
    told_by_id: int | None = None,
    told_by_name: str | None = None,
) -> int | None:
    """
    Update WITHOUT losing the old version: inserts the new text as a new row and
    marks the old row 'superseded'. Returns the new row's id, or None if the old
    row is gone or no longer active.
    """
    with _conn() as conn:
        old = conn.execute("SELECT * FROM memories WHERE id = %s FOR UPDATE", (old_id,)).fetchone()
        if not old or old["status"] != "active":
            return None
        new = conn.execute(
            "INSERT INTO memories (user_id, profile_id, fact, category, embedding, source_text, "
            "told_by_id, told_by_name, supersedes_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (old["user_id"], old["profile_id"], new_fact, category or old["category"], embedding,
             source_text, told_by_id, told_by_name, old_id),
        ).fetchone()
        conn.execute(
            "UPDATE memories SET status = 'superseded', updated_at = now() WHERE id = %s", (old_id,)
        )
    return new["id"]


def retire_memory(memory_id: int, status: str = "retracted"):
    """Takes a memory out of use but keeps the row (so it can be restored)."""
    with _conn() as conn:
        conn.execute(
            "UPDATE memories SET status = %s, updated_at = now() WHERE id = %s", (status, memory_id)
        )


def restore_memory(memory_id: int):
    """
    Brings an old/removed memory back. Anything that replaced it later (the whole
    chain of newer versions) becomes 'superseded', so only one version is active.
    """
    with _conn() as conn:
        conn.execute(
            """
            WITH RECURSIVE newer AS (
                SELECT id FROM memories WHERE supersedes_id = %s
                UNION
                SELECT m.id FROM memories m JOIN newer n ON m.supersedes_id = n.id
            )
            UPDATE memories SET status = 'superseded', updated_at = now()
            WHERE id IN (SELECT id FROM newer) AND status = 'active'
            """,
            (memory_id,),
        )
        conn.execute(
            "UPDATE memories SET status = 'active', updated_at = now() WHERE id = %s", (memory_id,)
        )


def update_memory(memory_id: int, new_fact: str, embedding: bytes | None = None):
    """In-place edit (used when YOU edit a memory by hand)."""
    with _conn() as conn:
        conn.execute(
            "UPDATE memories SET fact = %s, embedding = %s, updated_at = now() WHERE id = %s",
            (new_fact, embedding, memory_id),
        )


def set_embedding(memory_id: int, embedding: bytes):
    with _conn() as conn:
        conn.execute("UPDATE memories SET embedding = %s WHERE id = %s", (embedding, memory_id))


def get_all_memories(user_id: str, profile_id: int | None = None, status: str | None = "active"):
    """status: "active" (default), "inactive" (old/removed versions), or None (everything)."""
    sql = "SELECT * FROM memories WHERE user_id = %s"
    params: list = [user_id]
    if profile_id is not None:
        sql += " AND profile_id = %s"
        params.append(profile_id)
    if status == "active":
        sql += " AND status = 'active'"
    elif status == "inactive":
        sql += " AND status <> 'active'"
    sql += " ORDER BY updated_at DESC, id DESC"
    with _conn() as conn:
        return conn.execute(sql, params).fetchall()


def get_shareable_memories(profile_id: int) -> list[dict]:
    """
    What a linked friend may be told about this person: only things the person
    said THEMSELVES (never gossip told by others), and never sensitive categories.
    """
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM memories WHERE profile_id = %s AND status = 'active' "
            "AND told_by_name IS NULL AND category <> 'health' ORDER BY updated_at DESC, id DESC",
            (profile_id,),
        ).fetchall()


def delete_memory(memory_id: int):
    """Permanently erases a row (only used from the Memories page)."""
    with _conn() as conn:
        conn.execute("DELETE FROM memories WHERE id = %s", (memory_id,))
