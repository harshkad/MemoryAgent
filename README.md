# Changes in this version

## 1. "Forget that ..." works from the chat (forget.py)
A keyword check runs first (forget / delete / erase / remove / stop remembering / don't remember).
Only then does one model call match the request to the person's stored memories. The code validates
the answer, deletes (soft: restorable from History) and tells the reply what really happened.
Never deletes: facts a friend told about you, more than 5 at once ("forget everything" -> points to the
Memories page), or anything the model invents. A forget request is not saved as a new memory.

## 2. Gossip stays private
Facts someone else told us ("told by Harsh") are hidden from the person they are about: in the reply
prompt, the Memories page and History. The teller sees them under "Things you told me about others"
(can delete, restore, or switch on "Let <name> see this"). Facts that name another profile are also
kept out of friend-sharing. Existing "told by" memories become hidden after the automatic migration.

## 3. Profile PINs
Optional 4-digit PIN when creating a profile, or later under Manage profiles. Opening, editing or
deleting a protected profile needs it. Stored as a salted scrypt hash; 5 wrong tries lock the profile
for 5 minutes (counter lives in the database, so refreshing doesn't reset it). Only the signed-in
profile's chats and memories are shown. A forgotten PIN is cleared with:  python reset_pin.py "Name"
This is a lock inside the app, not encryption: someone with database access can still read the data.
