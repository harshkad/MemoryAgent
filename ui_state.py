"""
Keeps the list of profiles in the Streamlit session, so ordinary clicks never
need to ask the database for it. Call invalidate_profiles() after changing
any profile (create / rename / delete / sharing switch).
"""
import inspect

import streamlit as st

from db import list_profiles


def get_profiles(user_id: str) -> list[dict]:
    if "profiles_cache" not in st.session_state:
        st.session_state.profiles_cache = list_profiles(user_id)
    return st.session_state.profiles_cache


def invalidate_profiles():
    st.session_state.pop("profiles_cache", None)


# "make this button fill its row": newer Streamlit uses width="stretch" (use_container_width
# is deprecated there), older versions only know use_container_width.
STRETCH = {"width": "stretch"} if "width" in inspect.signature(st.button).parameters else {"use_container_width": True}
