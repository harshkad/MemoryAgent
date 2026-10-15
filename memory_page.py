"""
The "Memories" screen: see what has been saved for each person, fix it by hand,
and undo changes the app made automatically.

Buttons use callbacks (on_click) so each click costs ONE refresh of the page,
not two.
"""
import streamlit as st

from db import (
    get_all_memories, retire_memory, restore_memory, delete_memory,
    list_relationships, set_share,
)
from store import edit_memory
from people import pill_html
from ui_state import get_profiles, invalidate_profiles, STRETCH

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


def render_memories_page(user_id: str, active_profile: dict):
    profiles = get_profiles(user_id)
    ids = [p["id"] for p in profiles]
    by_id = {p["id"]: p for p in profiles}
    default_index = ids.index(active_profile["id"]) if active_profile["id"] in ids else 0

    top_left, top_right = st.columns([3, 2])
    with top_left:
        pid = st.selectbox(
            "Whose memories", ids, index=default_index,
            format_func=lambda i: by_id[i]["name"], key="mem_profile",
            label_visibility="collapsed",
        )
    person = by_id[pid]
    with top_right:
        st.markdown(pill_html(person), unsafe_allow_html=True)

    st.toggle(
        "Allow friends to see my info", value=bool(person["share_with_friends"]),
        key=f"share_{pid}", on_change=_toggle_share, args=(pid,),
        help="Linked friends can be told what this person said about themselves (never health details).",
    )

    links = list_relationships(pid)
    if links:
        st.caption("Linked to: " + ", ".join(f"{r['name']} ({r['relation']})" for r in links))

    # ---- current memories
    active = get_all_memories(user_id, pid)
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

    # ---- older versions / removed memories
    old = get_all_memories(user_id, pid, status="inactive")
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
