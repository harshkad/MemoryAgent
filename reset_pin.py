"""
Removes the PIN from one profile (for when somebody forgets it). It needs direct
access to the database, so only the person who runs the app can do it.

    python reset_pin.py "Harsh"

The profile keeps all its memories; it just has no PIN until its owner sets a new one
(Manage profiles -> tap the profile -> set a PIN).
"""
import sys

import psycopg

from config import DATABASE_URL


def main():
    if not DATABASE_URL:
        sys.exit("DATABASE_URL is not set. Add it to your .env file first.")
    if len(sys.argv) != 2:
        sys.exit('Usage: python reset_pin.py "Profile name"')
    name = sys.argv[1].strip()
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "UPDATE profiles SET pin_hash = NULL, pin_failed = 0, pin_locked_until = NULL "
            "WHERE lower(name) = lower(%s) RETURNING name",
            (name,),
        ).fetchall()
    if not rows:
        sys.exit(f"No profile named {name!r}. Nothing was changed.")
    print(f"Done. {rows[0][0]} no longer has a PIN.")


if __name__ == "__main__":
    main()
