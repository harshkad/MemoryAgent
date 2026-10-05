"""
Run this file to chat in your terminal with a memory-enabled agent.

    python main.py

Type 'exit' to quit. Type 'memories' to see everything saved about you.
"""
from db import init_db, get_all_memories
from retriever import get_relevant_memories
from extractor import extract_facts
from store import save_facts
from agent import get_reply

USER_ID = "local_user"  # single-user for now; swap for real IDs if you add accounts


def print_memories():
    memories = get_all_memories(USER_ID)
    if not memories:
        print("(no memories saved yet)")
        return
    for m in memories:
        print(f"  - {m['fact']}")


def main():
    init_db()
    history = []  # conversation so far, in this session

    print("Chat started. Type 'exit' to quit, 'memories' to view saved facts.\n")

    while True:
        user_message = input("You: ").strip()
        if not user_message:
            continue
        if user_message.lower() == "exit":
            break
        if user_message.lower() == "memories":
            print_memories()
            continue

        # 1. Retrieve anything relevant to this message
        memories = get_relevant_memories(USER_ID, user_message)

        # 2. Get the actual reply
        reply = get_reply(user_message, memories, history)
        print(f"Assistant: {reply}\n")

        # 3. Update conversation history
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": reply})

        # 4. Extract + save any new facts from this exchange
        #    (runs after replying so it never slows down the response)
        #    Passing known facts stops the model re-extracting the same
        #    thing every time it comes up again in conversation.
        known_facts = [m["fact"] for m in get_all_memories(USER_ID)]
        new_facts = extract_facts(user_message, reply, known_facts)
        if new_facts:
            save_facts(USER_ID, new_facts)


if __name__ == "__main__":
    main()