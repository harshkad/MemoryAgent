"""
Small pure helpers about PEOPLE (profiles): colours, relationship labels,
name matching, and the little coloured "pill" shown next to a chat.
No database and no Streamlit in here, so it is easy to test.
"""
import html
import re

# Pale colours, handed out in order so every profile gets a different one.
PALETTE = [
    "#F8C8DC", "#C8E6C9", "#BBDEFB", "#FFE0B2", "#E1BEE7", "#FFF59D",
    "#B2EBF2", "#D7CCC8", "#DCEDC8", "#FFCCBC", "#C5CAE9", "#F0F4C3",
]

# Facts in these categories are never shown to other people, even friends.
SENSITIVE_CATEGORIES = {"health"}

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def next_color(used: list[str]) -> str:
    """First palette colour nobody uses yet (cycles once all are taken)."""
    for color in PALETTE:
        if color not in used:
            return color
    return PALETTE[len(used) % len(PALETTE)]


def safe_color(color: str | None) -> str:
    """Only ever lets a plain #RRGGBB value into CSS."""
    return color if color and _HEX.match(color) else "#E5E5EA"


def initial(name: str) -> str:
    name = (name or "?").strip()
    return name[:1].upper() if name else "?"


# ---- relationships -------------------------------------------------------
# relation_pair("brother") -> ("brother", "sibling"):
#   "Aman is Rahul's brother"  (label stored for Rahul -> Aman)
#   "Rahul is Aman's sibling"  (label stored for Aman -> Rahul)
_SYNONYMS = {
    "best friend": "friend", "close friend": "friend", "bestie": "friend", "buddy": "friend",
    "coworker": "colleague", "co-worker": "colleague", "flatmate": "roommate",
    "mom": "mother", "mum": "mother", "dad": "father",
}
_SYMMETRIC = {"friend", "colleague", "roommate", "cousin", "classmate", "neighbour",
              "neighbor", "teammate", "partner", "sibling"}
_SIBLING = {"brother", "sister"}
_PARTNER = {"wife", "husband", "girlfriend", "boyfriend", "spouse", "fiance", "fiancee", "fiancé"}
_PARENT = {"father", "mother", "parent"}
_CHILD = {"son", "daughter", "child"}


def relation_pair(label: str) -> tuple[str, str | None]:
    """(label for the speaker's view, label for the other person's view or None)."""
    label = " ".join(label.lower().split())
    label = _SYNONYMS.get(label, label)
    if label in _SYMMETRIC:
        return label, label
    if label in _SIBLING:
        return label, "sibling"
    if label in _PARTNER:
        return label, "partner"
    if label in _PARENT:
        return label, "child"
    if label in _CHILD:
        return label, "parent"
    return label, None


# ---- names ---------------------------------------------------------------
def name_mentioned(message: str, name: str) -> bool:
    """True if `name` appears in `message` as a whole word, any case."""
    return bool(re.search(rf"(?<!\w){re.escape(name)}(?!\w)", message, re.IGNORECASE))


# ---- small HTML bits (all user text is escaped) ---------------------------
def pill_html(profile: dict) -> str:
    return (
        f'<span class="who-pill" style="--c:{safe_color(profile.get("color"))}">'
        f'<span class="av">{html.escape(initial(profile["name"]))}</span>'
        f'{html.escape(profile["name"])}</span>'
    )


def preview_html(name: str, color: str) -> str:
    return (
        f'<div class="preview-tile" style="background:{safe_color(color)}">'
        f'{html.escape(initial(name.strip() or "?"))}</div>'
    )
