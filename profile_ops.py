"""
The rules for creating, editing and deleting a profile, as plain functions
(no Streamlit), so the popups stay thin and the rules can be tested directly.
Each returns an error message to show, or None when it worked.

PINs: a profile may have a 4-digit PIN. EVERY change to a PIN-protected profile
(rename, sharing switch, new/removed PIN, delete) re-checks the PIN here, against the
database, so the rule holds even if a screen forgets to ask. check_pin() is also what
the "Who's using?" screen calls before opening a protected profile.
"""
from db import (
    create_profile, rename_profile, set_share, delete_profile, set_pin, verify_profile_pin,
)
from pins import hash_pin, valid_pin

MAX_NAME_LEN = 30
PIN_HINT = "A PIN is exactly 4 digits."


def clean_name(raw: str) -> str:
    """Tidies spaces ("  Mo   Ali " -> "Mo Ali")."""
    return " ".join((raw or "").split())


def _wait_text(seconds: int) -> str:
    minutes, secs = divmod(max(int(seconds), 1), 60)
    return f"{minutes} min {secs} s" if minutes else f"{secs} s"


def check_pin(profile_id: int, pin: str) -> str | None:
    """None if the PIN is right (or the profile has none); otherwise a message to show."""
    result = verify_profile_pin(profile_id, pin or "")
    status = result["status"]
    if status == "ok":
        return None
    if status == "locked":
        return f"Too many wrong PINs. Try again in {_wait_text(result['wait'])}."
    if status == "wrong":
        left = result["left"]
        return f"Wrong PIN. {left} attempt{'s' if left != 1 else ''} left."
    if status == "invalid":
        return "Enter the 4-digit PIN."
    return "That profile no longer exists."


def _check_new_pin(pin: str, confirm: str) -> str | None:
    """Validates a PIN being SET (both fields must be filled and match)."""
    if not valid_pin(pin):
        return PIN_HINT
    if pin != confirm:
        return "The two PINs don't match."
    return None


def add_profile(user_id: str, raw_name: str, color: str, pin: str = "", pin_confirm: str = "") -> str | None:
    """A PIN is optional here: leave both PIN fields empty for an unprotected profile."""
    name = clean_name(raw_name)
    if not name:
        return "Please enter a name."
    if len(name) > MAX_NAME_LEN:
        return f"That name is too long ({MAX_NAME_LEN} letters at most)."
    pin_hash = None
    if pin or pin_confirm:
        error = _check_new_pin(pin, pin_confirm)
        if error:
            return error
        pin_hash = hash_pin(pin)
    if create_profile(user_id, name, color, pin_hash) is None:
        return "Someone already has that name."
    return None


def edit_profile(
    user_id: str,
    profile: dict,
    raw_name: str,
    share: bool,
    current_pin: str = "",
    new_pin: str = "",
    confirm_pin: str = "",
    remove_pin: bool = False,
) -> str | None:
    """
    current_pin: the profile's present PIN (ignored when it has none).
    new_pin + confirm_pin: set or change the PIN. remove_pin: take the PIN away.
    Everything is validated first; the PIN check comes before anything is written.
    """
    name = clean_name(raw_name)
    if not name:
        return "The name can't be empty."
    if len(name) > MAX_NAME_LEN:
        return f"That name is too long ({MAX_NAME_LEN} letters at most)."
    if remove_pin and (new_pin or confirm_pin):
        return "Either set a new PIN or remove it, not both."
    new_hash = None
    if new_pin or confirm_pin:
        error = _check_new_pin(new_pin, confirm_pin)
        if error:
            return error
        new_hash = hash_pin(new_pin)

    error = check_pin(profile["id"], current_pin)
    if error:
        return error

    if name != profile["name"] and not rename_profile(profile["id"], user_id, name):
        return "Someone already has that name."
    if share != bool(profile["share_with_friends"]):
        set_share(profile["id"], share)
    if remove_pin:
        set_pin(profile["id"], None)
    elif new_hash:
        set_pin(profile["id"], new_hash)
    return None


def remove_profile(profile: dict, pin: str = "") -> str | None:
    """Also removes that person's memories and links. Needs the PIN if there is one."""
    error = check_pin(profile["id"], pin)
    if error:
        return error
    delete_profile(profile["id"])
    return None
