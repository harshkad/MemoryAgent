# Changes in this version (v2, compared with v1)

## 1. Online database (db.py)
Memories now live in a Neon (PostgreSQL) database instead of a local SQLite file, so the data isn't tied to one computer. One shared connection pool keeps queries fast, and connections Neon has put to sleep are dropped and replaced automatically. Set `DATABASE_URL` in `.env`; there is deliberately no default, so a missing value stops the app with a clear message instead of using some other database.

## 2. Profiles ("Who's using?" screen)
Each person picks or creates their own profile, like on Netflix. Memories, chats and colours are kept per profile (profile_ops.py, people.py). Names are unique, can be renamed, and deleting a profile also deletes its memories and links. Every chat shows who started it with a coloured pill.

## 3. Better memory saving (extractor.py, reconciler.py, store.py)
Saving is now three steps instead of one:
1. **Extract:** the small model reads the person's own message and proposes facts (max 5). Questions, jokes, hypotheticals and anything only the assistant said are never saved. A grounding check drops facts whose names or numbers were never actually mentioned.
2. **Reconcile:** the stronger model decides ADD / UPDATE / NOOP / DELETE for each fact (e.g. "Likes pizza" + "Likes pasta" are both kept, but "Lives in Delhi" → "Now lives in Mumbai" replaces the old one).
3. **Apply:** the code checks every decision before writing. Unknown targets, duplicates and unusable answers become SKIP, so nothing is saved rather than guessed.

v1 simply overwrote the closest-looking old memory; embeddings are now only used to build a shortlist, not to decide.

## 4. Nothing is lost by accident
An update adds a new row and marks the old one `superseded`; a taken-back fact is marked `retracted`. Old versions can be restored from History in the Memories page. Embeddings are stored in the database, so each memory is embedded only once.

## 5. Friends and "told by" facts
Saying "Aman is my friend" links the two profiles in both directions. What you say about a person who has a profile is saved into *their* profile, tagged "told by <you>". Someone telling us about a person can only add facts; they can never change or delete what that person said about themselves. A linked friend's own facts are shared in a reply only when you mention them by name, they allow sharing, and the fact isn't in the `health` category.

## 6. Memories page (memory_page.py)
See what is saved for each person, edit a memory by hand, delete it (restorable from History) or erase it for good, and switch "Allow friends to see my info" on or off.

## 7. New chat interface (streamlit_app.py, styles.py)
An iOS Messages-style layout with a sidebar of chats, replies that stream in, a typing indicator and automatic chat titles. Saving memories and writing titles run on a background thread (background.py), so the page is free again as soon as the reply finishes. Chats live only in the browser session; memories and profiles stay in the database.

## 8. Smaller changes
- Replies can be up to 1500 tokens (v1 cut them at 300), and are formatted in Markdown when it helps.
- `llm.py` supports JSON mode (with a retry if it is refused), streaming, and tolerant JSON parsing.
- `reset_db.py` wipes everything and restarts IDs from 1 (you must type `RESET`).
- New settings in `config.py`: `RECONCILER_MODEL`, `DB_POOL_MAX`, `RECONCILE_ALL_THRESHOLD`, `SHORTLIST_K`, `MAX_FACTS_PER_MESSAGE`.
- Added a `.gitignore` that keeps `.env` and other secrets out of git.
- Terminal chat (`main.py`) is gone; the app is Streamlit only.

## Upgrading from v1
v1 stored data in SQLite and v2 uses Postgres, so **existing v1 memories are not migrated**; v2 starts with a clean database. Add `DATABASE_URL` to your `.env`, run `pip install -r requirements.txt`, then `streamlit run streamlit_app.py`. If the database still holds data from an older layout, the app stops and asks you to run `python reset_db.py`.
