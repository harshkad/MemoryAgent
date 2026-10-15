"""
Wipes EVERYTHING (profiles, relationships, memories) so you can start fresh.
Because the tables are dropped and recreated, new IDs start from 1 again.

    python reset_db.py

You must type RESET to confirm. This cannot be undone.
"""
import sys

import psycopg

from config import DATABASE_URL


def main():
    if not DATABASE_URL:
        sys.exit("DATABASE_URL is not set. Add it to your .env file first.")
    if "--yes" not in sys.argv:
        answer = input("This permanently deletes ALL profiles and memories. Type RESET to continue: ")
        if answer.strip() != "RESET":
            sys.exit("Cancelled. Nothing was changed.")
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("DROP TABLE IF EXISTS memories, relationships, profiles, app_meta CASCADE")
    print("Done. Start the app and it will create fresh tables (IDs from 1).")


if __name__ == "__main__":
    main()
