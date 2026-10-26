"""
A browser-based chat interface for the memory agent, styled after iOS Messages.

Run with:
    streamlit run streamlit_app.py

How it works
  * On opening, a "Who's using?" screen (like Netflix) lets each person pick or create
    their own profile. Picking one opens a NEW chat for that person.
  * Every chat belongs to one profile. Its colour shows in a pill at the top of the
    chat and as a dot in the sidebar, so you can see who started which chat.
  * A profile can have a 4-digit PIN: opening or editing it asks for the PIN first, and
    only the unlocked profile's chats and memories are ever shown (see profile_ops.py, db.verify_profile_pin).
  * Memories are saved per profile. What someone says about another profile (e.g. "Aman
    loves cricket") is saved into THAT profile, tagged "told by ...", and the two profiles
    are linked (see extractor.py / store.py).
  * Saving memories runs on a background thread (background.py), so the page is free again
    as soon as the reply has finished. Chats live only in st.session_state: they disappear
    when you close the app; memories and profiles stay in the database.
"""
import html
import time
import uuid

import streamlit as st
from openai import AuthenticationError

from db import init_db
from profile_ops import add_profile, edit_profile, remove_profile, check_pin
from retriever import build_context
from agent import get_reply_stream, fallback_title
from background import submit, warm_up, remember, make_title, wait_idle
from forget import looks_like_forget, process_forget
from memory_page import render_memories_page
from people import next_color, pill_html, preview_html, initial
from styles import BASE_CSS, HIDE_SIDEBAR_CSS, dynamic_css
from ui_state import get_profiles, invalidate_profiles, STRETCH
from config import GROQ_API_KEY

USER_ID = "local_user"
NEW_CHAT_TITLE = "New chat"

st.set_page_config(
    page_title="Memory Agent",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)
try:
    init_db()
except Exception as e:
    st.error(
        "Couldn't start the database. Check that DATABASE_URL is set in your "
        f".env file (see .env.example).\n\n{e}"
    )
    st.stop()
warm_up()  # loads the embedding model in the background so the first message isn't slow

st.markdown(BASE_CSS, unsafe_allow_html=True)

# A <p> (not a <div>) so Streamlit's own paragraph-margin handling keeps the bubble the right height.
TYPING_HTML = '<p class="typing"><span></span><span></span><span></span></p>'

ss = st.session_state
if "sessions" not in ss:
    ss.sessions = {}        # {session_id: {"title": str, "history": [...], "profile_id": int}}
    ss.active_id = None
    ss.profile_id = None    # None -> show the "Who's using?" screen
    ss.view = "chat"        # "chat" | "memories"
    ss.manage = False       # picker: tap a profile to edit it
    ss.pending = []         # [(kind, Future)] background jobs, collected on the next run

profiles = get_profiles(USER_ID)
by_id = {p["id"]: p for p in profiles}
if ss.profile_id not in by_id:
    ss.profile_id = None


# ------------------------------------------------------------ background jobs
def collect_background():
    """Picks up finished background jobs (memory saving, chat titles) -- never waits."""
    still = []
    for kind, fut in ss.pending:
        if not fut.done():
            still.append((kind, fut))
            continue
        try:
            result = fut.result()
        except Exception as e:
            if kind == "memory":
                st.toast(f"Couldn't update memories: {e}")
            continue
        if kind == "title":
            sid, title = result
            if sid in ss.sessions:
                ss.sessions[sid]["title"] = title
        elif kind == "memory":
            if result["added"] or result["updated"] or result["deleted"] or result["linked"]:
                st.toast("🧠 Memory updated")
            elif result["skipped"]:
                st.toast("Couldn't save some memories this time")
    ss.pending = still


collect_background()


# ---------------------------------------------------------------- navigation
def _new_session(profile_id: int) -> str:
    sid = uuid.uuid4().hex
    ss.sessions[sid] = {"title": NEW_CHAT_TITLE, "history": [], "profile_id": profile_id}
    return sid


def select_profile(profile_id: int):
    """Picking a profile opens a new chat for them (re-using their empty one, if any)."""
    empty = next(
        (sid for sid, c in ss.sessions.items() if c["profile_id"] == profile_id and not c["history"]),
        None,
    )
    ss.active_id = empty or _new_session(profile_id)
    ss.profile_id = profile_id
    ss.view = "chat"


def go_picker():
    ss.profile_id = None
    ss.manage = False
    ss.view = "chat"


def start_new_chat():
    ss.view = "chat"
    current = ss.sessions.get(ss.active_id)
    if current and not current["history"]:
        return  # nothing to leave behind
    ss.active_id = _new_session(ss.profile_id)


def open_chat(sid: str):
    chat = ss.sessions.get(sid)
    if chat is None or chat["profile_id"] != ss.profile_id:
        return  # only the signed-in profile's own chats can be opened (never someone else's)
    ss.active_id = sid
    ss.view = "chat"


def show_memories():
    ss.view = "memories"


def show_chat():
    ss.view = "chat"


def toggle_manage():
    ss.manage = not ss.manage


# ------------------------------------------------------------------- dialogs
@st.dialog("Add profile")
def add_profile_dialog():
    color = next_color([p["color"] for p in get_profiles(USER_ID)])
    n = ss.get("np_counter", 0)
    name = st.text_input("Name", key=f"new_profile_name_{n}", placeholder="Who's this?")
    st.markdown(preview_html(name, color), unsafe_allow_html=True)
    pin = st.text_input("PIN (optional)", type="password", max_chars=4, key=f"new_profile_pin_{n}",
                        placeholder="4 digits", help="Locks this profile: its chats and memories need the PIN to open.")
    pin2 = st.text_input("Confirm PIN", type="password", max_chars=4, key=f"new_profile_pin2_{n}",
                         placeholder="Same 4 digits")
    if st.button("Create profile", type="primary", **STRETCH):
        error = add_profile(USER_ID, name, color, pin, pin2)
        if error:
            st.error(error)
            return
        ss.np_counter = ss.get("np_counter", 0) + 1
        invalidate_profiles()
        st.rerun()


@st.dialog("Edit profile")
def edit_profile_dialog(profile_id: int):
    p = by_id.get(profile_id)
    if not p:
        st.rerun()
    pin_key = f"edit_pin_{profile_id}"  # the verified PIN, kept only while this popup is in use

    # A protected profile can't be edited (or deleted) until its PIN has been entered.
    if p["has_pin"] and pin_key not in ss:
        st.caption("This profile is protected. Enter its PIN to continue.")
        with st.form(f"edit_gate_{profile_id}"):
            entered = st.text_input("PIN", type="password", max_chars=4, placeholder="4-digit PIN",
                                    label_visibility="collapsed")
            unlock = st.form_submit_button("Unlock", type="primary", **STRETCH)
        if unlock:
            error = check_pin(profile_id, entered)
            if error:
                st.error(error)
            else:
                ss[pin_key] = entered
        if pin_key not in ss:
            return

    current_pin = ss.get(pin_key, "")
    name = st.text_input("Name", value=p["name"], key=f"edit_name_{profile_id}")
    share = st.toggle("Allow friends to see my info", value=bool(p["share_with_friends"]),
                      key=f"edit_share_{profile_id}")
    st.markdown("**PIN**")
    new_pin = st.text_input("New PIN" if p["has_pin"] else "Set a PIN (optional)", type="password",
                            max_chars=4, key=f"edit_newpin_{profile_id}", placeholder="4 digits")
    confirm_pin = st.text_input("Confirm PIN", type="password", max_chars=4,
                                key=f"edit_newpin2_{profile_id}", placeholder="Same 4 digits")
    remove_pin = False
    if p["has_pin"]:
        st.caption("Leave the PIN boxes empty to keep the current PIN.")
        remove_pin = st.checkbox("Remove the PIN from this profile", key=f"edit_rmpin_{profile_id}")
    if st.button("Save", type="primary", **STRETCH, key=f"edit_save_{profile_id}"):
        error = edit_profile(USER_ID, p, name, share, current_pin, new_pin, confirm_pin, remove_pin)
        if error:
            st.error(error)
            return
        ss.pop(pin_key, None)
        invalidate_profiles()
        st.rerun()
    st.divider()
    sure = st.checkbox(f"Delete {p['name']} and all their memories", key=f"edit_sure_{profile_id}")
    if st.button("Delete profile", disabled=not sure, **STRETCH, key=f"edit_del_{profile_id}"):
        error = remove_profile(p, current_pin)
        if error:
            st.error(error)
            return
        ss.pop(pin_key, None)
        for sid in [sid for sid, c in ss.sessions.items() if c["profile_id"] == profile_id]:
            del ss.sessions[sid]
        if ss.profile_id == profile_id:
            ss.profile_id = None
        invalidate_profiles()
        st.rerun()


@st.dialog("Enter PIN")
def unlock_dialog(profile_id: int):
    """Shown when a PIN-protected profile is tapped. The chat only opens after the right PIN."""
    p = by_id.get(profile_id)
    if not p:
        st.rerun()
    st.markdown(pill_html(p), unsafe_allow_html=True)
    with st.form(f"unlock_{profile_id}"):
        entered = st.text_input("PIN", type="password", max_chars=4, placeholder="4-digit PIN",
                                label_visibility="collapsed")
        go = st.form_submit_button("Unlock", type="primary", **STRETCH)
    if go:
        error = check_pin(profile_id, entered)
        if error:
            st.error(error)
        else:
            select_profile(profile_id)
            st.rerun()


# -------------------------------------------------------------- picker screen
def render_picker():
    st.markdown(HIDE_SIDEBAR_CSS + dynamic_css(profiles, [], None), unsafe_allow_html=True)
    st.markdown("<div class='picker-title'>Who's using?</div>", unsafe_allow_html=True)
    sub = "Tap a profile to edit it" if ss.manage else "Pick your profile to start a chat"
    st.markdown(f"<div class='picker-sub'>{sub}</div>", unsafe_allow_html=True)

    tiles = list(profiles) + ([] if ss.manage else [None])  # None = the "+" tile
    per_row = 5
    to_edit, to_unlock, to_add = None, None, False
    for start in range(0, len(tiles), per_row):
        row = tiles[start:start + per_row]
        pad = (per_row - len(row)) / 2
        weights = ([pad] if pad > 0 else []) + [1] * len(row) + ([pad] if pad > 0 else [])
        cols = st.columns(weights)
        cols = cols[1:-1] if pad > 0 else cols
        for col, p in zip(cols, row):
            with col:
                if p is None:
                    to_add = st.button("+", key="pick_add") or to_add
                    st.markdown("<div class='tile-name'>Add profile</div>", unsafe_allow_html=True)
                    continue
                if ss.manage:
                    if st.button(initial(p["name"]), key=f"pick_{p['id']}"):
                        to_edit = p["id"]
                        ss.pop(f"edit_pin_{p['id']}", None)  # always ask for the PIN again
                elif p["has_pin"]:
                    if st.button(initial(p["name"]), key=f"pick_{p['id']}"):
                        to_unlock = p["id"]
                else:
                    st.button(initial(p["name"]), key=f"pick_{p['id']}",
                              on_click=select_profile, args=(p["id"],))
                label = ("✎ " if ss.manage else "🔒 " if p["has_pin"] else "") + html.escape(p["name"])
                st.markdown(f"<div class='tile-name'>{label}</div>", unsafe_allow_html=True)

    if profiles:
        st.button("Done" if ss.manage else "Manage profiles", key="manage_profiles", on_click=toggle_manage)

    if to_add:
        add_profile_dialog()
    elif to_edit is not None:
        edit_profile_dialog(to_edit)
    elif to_unlock is not None:
        unlock_dialog(to_unlock)
    elif not profiles and not ss.get("auto_dialog"):
        ss.auto_dialog = True  # first ever launch: open the "Add profile" popup straight away
        add_profile_dialog()


# -------------------------------------------------------------------- sidebar
def render_sidebar(profile: dict):
    """Called once per run, after any message is handled, so a new chat and its
    title show up without needing another refresh."""
    with st.sidebar:
        st.button(profile["name"], key="switch_profile", icon=":material/swap_horiz:",
                  on_click=go_picker, **STRETCH, help="Switch profile")
        left, right = st.columns(2)
        left.button("", key="new_chat", icon=":material/add:", help="New chat",
                    on_click=start_new_chat, **STRETCH)
        if ss.view == "memories":
            right.button("", key="back_to_chat", icon=":material/chat_bubble:", help="Back to chat",
                         on_click=show_chat, **STRETCH)
        else:
            right.button("", key="open_memories", icon=":material/psychology:", help="Memories",
                         on_click=show_memories, **STRETCH)

        st.caption("Chats")
        # Newest first; only chats that have messages, and only THIS profile's: other
        # profiles' chats stay hidden until their own PIN opens them.
        chats = [(sid, c) for sid, c in reversed(list(ss.sessions.items()))
                 if c["history"] and c["profile_id"] == profile["id"]]
        for sid, chat in chats:
            st.button(
                chat["title"], key=f"chat_{sid}", on_click=open_chat, args=(sid,),
                **STRETCH,
                type="primary" if sid == ss.active_id else "secondary",
            )
        st.markdown(dynamic_css(profiles, chats, profile), unsafe_allow_html=True)


def friendly_error(e: Exception) -> str:
    if isinstance(e, AuthenticationError):
        tail = GROQ_API_KEY[-4:] if len(GROQ_API_KEY) >= 8 else "?"
        return (
            "Groq rejected the API key (401). The key this app is using ends in "
            f"**…{tail}**. Check that it matches a live key in your Groq console, "
            "and that no old GROQ_API_KEY is set in your system environment."
        )
    return f"Something went wrong getting a reply: {e}"


# ================================================================== the page
if ss.profile_id is None:
    render_picker()
    st.stop()

profile = by_id[ss.profile_id]
session = ss.sessions.get(ss.active_id)
if session is None or session["profile_id"] != profile["id"]:
    select_profile(profile["id"])
    session = ss.sessions[ss.active_id]
history = session["history"]

if ss.view == "memories":
    render_sidebar(profile)
    render_memories_page(USER_ID, profile)
    st.stop()

# --- chat ---
st.markdown(f'<div class="chat-head">{pill_html(profile)}</div>', unsafe_allow_html=True)

# (st.chat_input is pinned to the bottom of the page wherever it is called)
user_message = st.chat_input("Message")

if not history and not user_message:
    st.markdown(
        '<div class="empty-state"><h2>What can I help you with?</h2></div>',
        unsafe_allow_html=True,
    )

# Replay the conversation (st.markdown renders bold, italics, lists, code)
for msg in history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

reply = None
forget = None  # set when this message was a "forget ..." request (see forget.py)
if user_message:
    # "fresh": only these new bubbles play the slide-in animation (see styles.py)
    with st.container(key="fresh"):
        with st.chat_message("user"):
            st.markdown(user_message)
        with st.chat_message("assistant"):
            slot = st.empty()
            slot.markdown(TYPING_HTML, unsafe_allow_html=True)  # shown until the first words arrive
            try:
                if looks_like_forget(user_message):
                    # The previous message's memories may still be saving in the background;
                    # wait for them so "forget that" can find what was just said.
                    wait_idle([f for kind, f in ss.pending if kind == "memory"])
                    forget = process_forget(USER_ID, profile, user_message, history)
                    if forget and forget["forgotten"]:
                        n = len(forget["forgotten"])
                        st.toast(f"🧠 Forgot {n} memor{'y' if n == 1 else 'ies'}")
                notes = [forget["note"]] if forget else None
                # built AFTER forgetting, so a just-forgotten fact can't leak into the reply
                context = build_context(USER_ID, profile, user_message)
                text, last_paint = "", 0.0
                for piece in get_reply_stream(user_message, profile, context, history, notes):
                    text += piece
                    now = time.monotonic()
                    if now - last_paint > 0.04:  # repaint ~25x/sec so the text flows smoothly
                        slot.markdown(text)
                        last_paint = now
                if text.strip():
                    slot.markdown(text)
                    reply = text
                else:
                    slot.markdown("*(The model returned an empty reply — try again.)*")
            except Exception as e:
                slot.empty()
                st.error(friendly_error(e))

if reply is not None:
    prev_assistant = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), "")
    first_exchange = not history
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": reply})

    # Both of these run on a background thread; the results are picked up on your next click.
    if first_exchange:
        session["title"] = fallback_title(user_message)  # instant; the model's nicer title replaces it
        ss.pending.append(("title", submit(make_title, ss.active_id, user_message, reply)))
    if forget is None:  # a forget request is a command, not new information to remember
        ss.pending.append(("memory", submit(remember, USER_ID, dict(profile), user_message, prev_assistant)))

render_sidebar(profile)
