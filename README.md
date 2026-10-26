# Changes in this version (v3, compared with v2)

## 1. Profile PINs (pins.py, profile_ops.py, db.py)
A profile can have an optional 4-digit PIN, set when the profile is created or later under Manage profiles. Tapping a protected profile (shown with a 🔒) asks for the PIN before its chat opens, and editing or deleting it asks for the PIN again. Every change to a protected profile re-checks the PIN in `profile_ops.py`, against the database, so the rule holds even if a screen forgets to ask.

- The PIN is stored only as a salted scrypt hash (`scrypt$<salt>$<hash>`) and compared in constant time. The hash is never loaded into the cached profile rows; the app only knows whether a profile `has_pin`.
- 5 wrong tries lock the profile for 5 minutes. The counter and lock time live in the database, so refreshing the page doesn't reset them (`PIN_MAX_ATTEMPTS`, `PIN_LOCKOUT_SECONDS`).
- Only the signed-in profile's chats and memories are shown.
- A forgotten PIN is cleared with `python reset_pin.py "Name"`. The profile keeps all its memories.

This is a lock inside the app, not encryption. Four digits are only 10,000 possibilities, so anyone with direct database access can still read the data.

## 2. Gossip stays private (db.py, retriever.py, memory_page.py)
Facts someone else told us ("told by Harsh") are now hidden from the person they are about: in the reply prompt, the Memories page and History. A new column, `visible_to_subject`, controls this and defaults to hidden.

- The teller sees these facts in a new section on the Memories page, **Things you told me about others**. There they can delete a fact, restore it from "Removed", or switch on **Let <name> see this**.
- Restoring a removed "told" fact makes it hidden again.
- The reply prompt gets a private "things you told me about others" list, used only when you bring that person up.
- The saving pipeline still sees hidden facts, so it doesn't store duplicates.

## 3. "Forget that ..." from the chat (forget.py)
You can now ask the chat to forget something. Before the reply is written:
1. A keyword check runs first (forget, delete, erase, remove, stop remembering, don't remember). Almost every message stops here at no extra cost.
2. Only then does one model call match the request to your stored memories, using the last turn so "forget *that*" works.
3. The code validates the answer and deletes. Deletes are soft, so they can be restored from History.

It never deletes facts a friend told about you, never more than 5 at once ("forget everything" points you to the Memories page), and never anything the model invented. If the memory system fails, nothing is deleted and the reply says so. The reply is told what really happened, so it can't claim a deletion that didn't occur. A forget request is not saved as a new memory.

Because a memory from the message just before might still be saving in the background, the app first waits up to 15 seconds for those jobs (`wait_idle` in `background.py`).

## 4. Safer friend-sharing (people.py, retriever.py)
Facts that name another profile are kept out of what is shared with friends. For example, "Is planning a surprise party for Rahul" no longer reaches Rahul just because it sits in Harsh's profile. This matches by name, so it errs on the side of hiding (a profile named "May" also hides facts that merely contain the word "may").

## 5. Memories page shows only you (memory_page.py)
The "Whose memories" picker is gone. The page shows only the signed-in profile, and only what that person may see: what they said about themselves, plus things a friend told us about them if the friend chose to reveal it.

## 6. Smarter, shorter replies (agent.py)
The system prompt was rewritten. Casual messages get a short, natural reply; serious questions get a clear answer with enough detail. It avoids filler, stock offers like "How can I help you?", repeated information and generic comfort lines. Replies can also carry a one-off note (used by forget so the reply matches what was actually deleted).

## 7. Smaller changes
- New settings in `config.py`: `FORGET_MODEL` (defaults to the stronger model, since it deletes data), `MAX_FORGET_PER_MESSAGE`, `FORGET_CANDIDATE_LIMIT`, `PIN_MAX_ATTEMPTS`, `PIN_LOCKOUT_SECONDS`.
- `reset_pin.py` added.
- Unchanged from v2: `extractor.py`, `store.py`, `llm.py`, `embeddings.py`, `styles.py`, `ui_state.py`. `reconciler.py` has the same logic as v2.

## Upgrading from v2
Nothing to do: start the app and the new columns (`pin_hash`, `pin_failed`, `pin_locked_until`, `visible_to_subject`) are added automatically, and existing data is kept. No `reset_db` needed. Existing "told by" memories become hidden from the person they are about after the automatic migration.
