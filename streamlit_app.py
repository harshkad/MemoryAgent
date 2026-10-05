"""
A browser-based chat interface for the memory agent.

Run with:
    streamlit run streamlit_app.py

Reuses every existing module (agent, retriever, extractor, store, db)
untouched -- this file is purely the interface layer on top.
"""
import streamlit as st
from db import init_db, get_all_memories
from retriever import get_relevant_memories
from extractor import extract_facts
from store import save_facts
from agent import get_reply

USER_ID = "local_user"

st.set_page_config(page_title="Memory Agent", page_icon="💬", layout="centered")
init_db()

# --- ChatGPT/iMessage-style bubble layout: user on the right, assistant on the left ---
st.markdown("""
<style>
.chat-row { display: flex; margin: 8px 0; }
.chat-row.user { justify-content: flex-end; }
.chat-row.assistant { justify-content: flex-start; }
.bubble {
    max-width: 70%;
    padding: 10px 14px;
    border-radius: 16px;
    line-height: 1.4;
    font-size: 0.95rem;
    white-space: pre-wrap;
}
.bubble.user { background-color: #2563eb; color: white; border-bottom-right-radius: 4px; }
.bubble.assistant { background-color: #f0f0f0; color: #111; border-bottom-left-radius: 4px; }
</style>
""", unsafe_allow_html=True)


def render_bubble(role: str, content: str):
    st.markdown(
        f'<div class="chat-row {role}"><div class="bubble {role}">{content}</div></div>',
        unsafe_allow_html=True,
    )


# --- Session state setup (survives across reruns in the same browser tab) ---
if "history" not in st.session_state:
    st.session_state.history = []  # list of {"role": ..., "content": ...}

st.title("💬 Memory Agent")

# Replay existing conversation as bubbles
for msg in st.session_state.history:
    render_bubble(msg["role"], msg["content"])

# New message input (pinned to bottom by Streamlit automatically)
user_message = st.chat_input("Type a message...")

if user_message:
    render_bubble("user", user_message)

    with st.spinner("Thinking..."):
        memories_for_prompt = get_relevant_memories(USER_ID, user_message)
        reply = get_reply(user_message, memories_for_prompt, st.session_state.history)

    render_bubble("assistant", reply)

    st.session_state.history.append({"role": "user", "content": user_message})
    st.session_state.history.append({"role": "assistant", "content": reply})

    # Extract + save new facts -- known facts are passed in so the model
    # doesn't keep re-saving the same thing every time it comes up again.
    known_facts = [m["fact"] for m in get_all_memories(USER_ID)]
    new_facts = extract_facts(user_message, reply, known_facts)
    if new_facts:
        save_facts(USER_ID, new_facts)