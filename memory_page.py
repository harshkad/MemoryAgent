"""
The "Memories" screen: see what has been saved for the person who is signed in, fix it
by hand, and undo changes the app made automatically.

It only ever shows the CURRENT profile (the one that was unlocked with its PIN), and
only what that person may see: facts they said about themselves, plus things a friend
told us about them ONLY if the friend chose to reveal them. A second section lists what
THEY told us about other people, where they decide whether that person may see it.

Buttons use callbacks (on_click) so each click costs ONE refresh of the page,
not two.
"""
import streamlit as st

from db import (
    get_all_memories, retire_memory, restore_memory, delete_memory,
    list_relationships, set_share, get_told_about_others, set_memory_visibility,
    retire_told_memory, restore_told_memory,
)
from store import edit_memory
from people import pill_html
from ui_state import invalidate_profiles, STRETCH

STATUS_TEXT = {
    "superseded": "Replaced by a newer version",
    "retracted": "Taken back (no longer true)",
    "deleted": "Deleted by you",
}


def _save_edit(memory_id: int):
    text = st.session_state.get(f"mem_edit_{memory_id}", "").strip()
    if text:
        edit_memory(memory_id, text)


def _delete(memory_id: int):
    retire_memory(memory_id, "deleted")  # kept in History so it can be restored


def _restore(memory_id: int):
    restore_memory(memory_id)


def _erase(memory_id: int):
    delete_memory(memory_id)


def _toggle_share(profile_id: int):
    set_share(profile_id, st.session_state[f"share_{profile_id}"])
    invalidate_profiles()


def _toggle_visible(memory_id: int, teller_id: int):
    set_memory_visibility(memory_id, teller_id, st.session_state[f"vis_{memory_id}"])


def _delete_told(memory_id: int, teller_id: int):
    retire_told_memory(memory_id, teller_id)


def _restore_told(memory_id: int, teller_id: int):
    restore_told_memory(memory_id, teller_id)


def render_memories_page(user_id: str, person: dict):
    pid = person["id"]

    top_left, top_right = st.columns([3, 2])
    with top_left:
        st.markdown(pill_html(person), unsafe_allow_html=True)

    st.toggle(
        "Allow friends to see my info", value=bool(person["share_with_friends"]),
        key=f"share_{pid}", on_change=_toggle_share, args=(pid,),
        help="Linked friends can be told what this person said about themselves (never health details).",
    )

    links = list_relationships(pid)
    if links:
        st.caption("Linked to: " + ", ".join(f"{r['name']} ({r['relation']})" for r in links))

    # ---- current memories (only what this person is allowed to see)
    active = get_all_memories(user_id, pid, subject_view=True)
    if not active:
        st.info("Nothing saved yet for this person.")
    for m in active:
        text_col, save_col, del_col = st.columns([8, 1.4, 1.6])
        edited = text_col.text_input(
            "Memory", value=m["fact"], key=f"mem_edit_{m['id']}", label_visibility="collapsed",
        )
        if m.get("told_by_name"):
            text_col.caption(f"Told by {m['told_by_name']}")
        unchanged = not edited.strip() or edited.strip() == m["fact"]
        save_col.button("Save", key=f"mem_save_{m['id']}", disabled=unchanged,
                        on_click=_save_edit, args=(m["id"],), **STRETCH)
        del_col.button("Delete", key=f"mem_del_{m['id']}",
                       on_click=_delete, args=(m["id"],), **STRETCH)

    # ---- what this person told us about other people
    told = get_told_about_others(user_id, pid)
    removed_told = get_told_about_others(user_id, pid, status="removed")
    if told or removed_told:
        st.markdown("#### Things you told me about others")
        st.caption("Private to you by default. Switch a toggle on to let that person see it too.")
    for m in told:
        text_col, vis_col, del_col = st.columns([6, 3.4, 1.6])
        text_col.text(m["fact"])
        text_col.caption(f"About {m['subject_name']}")
        vis_col.toggle(
            f"Let {m['subject_name']} see this", value=bool(m["visible_to_subject"]),
            key=f"vis_{m['id']}", on_change=_toggle_visible, args=(m["id"], pid),
        )
        del_col.button("Delete", key=f"told_del_{m['id']}",
                       on_click=_delete_told, args=(m["id"], pid), **STRETCH)
    if removed_told:
        with st.expander(f"Removed ({len(removed_told)})"):
            for m in removed_told:
                text_col, restore_col = st.columns([8, 1.6])
                text_col.text(m["fact"])
                text_col.caption(f"About {m['subject_name']}")
                restore_col.button("Restore", key=f"told_restore_{m['id']}",
                                   on_click=_restore_told, args=(m["id"], pid), **STRETCH)

    # ---- older versions / removed memories (again: only what this person may see)
    old = get_all_memories(user_id, pid, status="inactive", subject_view=True)
    with st.expander(f"History ({len(old)})"):
        if not old:
            st.caption("Old versions show up here when a memory is updated or removed.")
        for m in old:
            text_col, restore_col, erase_col = st.columns([8, 1.6, 1.4])
            text_col.text(m["fact"])
            text_col.caption(STATUS_TEXT.get(m["status"], m["status"]))
            restore_col.button("Restore", key=f"mem_restore_{m['id']}",
                               on_click=_restore, args=(m["id"],), **STRETCH)
            erase_col.button("Erase", key=f"mem_erase_{m['id']}",
                             on_click=_erase, args=(m["id"],), **STRETCH)
