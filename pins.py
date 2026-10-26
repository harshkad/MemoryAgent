"""
Hashing and checking of profile PINs. Pure functions: no database, no Streamlit.

A PIN is exactly four ASCII digits. It is stored as  scrypt$<salt hex>$<hash hex>
(random 16-byte salt per PIN), never in plain text, and compared in constant time.

Honest limits: four digits are only 10,000 possibilities, so anyone who can read the
database can brute-force the hash instantly. The PIN is a lock on the PROFILE inside
the app (the attempt limit that stops guessing lives in db.verify_profile_pin); it
does not encrypt the stored memories.
"""
import hashlib
import hmac
import os
import re

# [0-9] on purpose: "\d" would also accept digits from other scripts.
_FORMAT = re.compile(r"[0-9]{4}")

_N, _R, _P = 2 ** 14, 8, 1  # scrypt cost (about 16 MB of memory, tens of milliseconds)


def valid_pin(pin) -> bool:
    return isinstance(pin, str) and _FORMAT.fullmatch(pin) is not None


def _digest(pin: str, salt: bytes) -> bytes:
    return hashlib.scrypt(pin.encode("ascii"), salt=salt, n=_N, r=_R, p=_P, dklen=32)


def hash_pin(pin: str, salt: bytes | None = None) -> str:
    if not valid_pin(pin):
        raise ValueError("A PIN is exactly 4 digits.")
    salt = salt or os.urandom(16)
    return f"scrypt${salt.hex()}${_digest(pin, salt).hex()}"


def verify_pin(pin, stored) -> bool:
    """True only if `pin` is a well-formed PIN that matches the stored hash."""
    if not valid_pin(pin) or not isinstance(stored, str):
        return False
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        salt, expected = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
    except ValueError:
        return False
    return hmac.compare_digest(_digest(pin, salt), expected)
