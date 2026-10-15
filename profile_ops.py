"""
The rules for creating, editing and deleting a profile, as plain functions
(no Streamlit), so the popups stay thin and the rules can be tested directly.
Each returns an error message to show, or None when it worked.
"""
from db import create_profile, rename_profile, set_share, delete_profile

MAX_NAME_LEN = 30


def clean_name(raw: str) -> str:
    """Tidies spaces ("  Mo   Ali " -> "Mo Ali")."""
    return " ".join((raw or "").split())


def add_profile(user_id: str, raw_name: str, color: str) -> str | None:
    name = clean_name(raw_name)
    if not name:
        return "Please enter a name."
    if len(name) > MAX_NAME_LEN:
        return f"That name is too long ({MAX_NAME_LEN} letters at most)."
    if create_profile(user_id, name, color) is None:
        return "Someone already has that name."
    return None


def edit_profile(user_id: str, profile: dict, raw_name: str, share: bool) -> str | None:
    name = clean_name(raw_name)
    if not name:
        return "The name can't be empty."
    if len(name) > MAX_NAME_LEN:
        return f"That name is too long ({MAX_NAME_LEN} letters at most)."
    if name != profile["name"] and not rename_profile(profile["id"], user_id, name):
        return "Someone already has that name."
    if share != bool(profile["share_with_friends"]):
        set_share(profile["id"], share)
    return None


def remove_profile(profile_id: int):
    """Also removes that person's memories and links."""
    delete_profile(profile_id)
