"""
All the CSS for the app, in one place.

Kept from before: the iOS Messages look (blue/grey bubbles, rounded input, the
springy slide-in for new messages, the soft blur under the text box).
New: compact sidebar, coloured profile pills / chat dots, the "Who's using?"
picker tiles, and compact dropdowns / popups -- all sharing one set of sizes.
"""
from people import safe_color

BASE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

:root {
    --ios-blue: #007AFF;
    --ios-gray: #E9E9EB;
    --ios-ease: cubic-bezier(0.22, 1, 0.36, 1);   /* smooth, slightly springy */
    --radius: 10px;                               /* one corner size for every control */
    --ctl-h: 2rem;                                /* one height for every compact control */
    --ctl-font: 0.84rem;
}

html, body, .stApp, [data-testid="stSidebar"], button, textarea, input {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter",
                 "Segoe UI", Roboto, sans-serif !important;
    -webkit-font-smoothing: antialiased;
}

/* Only the deploy button / menu are hidden. The header and toolbar stay so
   the sidebar open/close arrow is always reachable. */
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"], [data-testid="stStatusWidget"],
#MainMenu, footer {
    display: none !important;
}
header[data-testid="stHeader"] { background: transparent; }

/* Don't dim the page while a reply is being produced (Streamlit's default). */
[data-stale="true"] { opacity: 1 !important; transition: none !important; }

/* Centered reading column on a full-width page */
[data-testid="stMainBlockContainer"] { max-width: 820px; padding: 1.6rem 1.5rem 7rem 1.5rem; }

/* ---------- Messages ---------- */
@keyframes pop-in {
    from { opacity: 0; transform: translateY(14px) scale(0.96); }
    to   { opacity: 1; transform: translateY(0) scale(1); }
}

[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"] { display: none !important; }

[data-testid="stChatMessage"] {
    background: transparent !important;
    padding: 0.25rem 0 !important;
    display: flex;
}
/* The slide-in only plays for the message(s) you just sent / received. Older
   messages are redrawn on every click, and animating them all made the page
   feel slow. (The app puts new messages in a container keyed "fresh".) */
.st-key-fresh [data-testid="stChatMessage"] { animation: pop-in 0.42s var(--ios-ease) both; }

[data-testid="stChatMessageContent"] {
    flex: 0 1 auto !important;       /* size to the text, not the whole row */
    width: auto !important;
    min-width: 0;
    padding: 0.62rem 1rem;
    border-radius: 20px;
    line-height: 1.45;
    font-size: 0.97rem;
}

/* Assistant: grey bubble, left */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
    justify-content: flex-start;
    transform-origin: bottom left;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"])
    [data-testid="stChatMessageContent"] {
    background: var(--ios-gray);
    color: #111;
    border-bottom-left-radius: 6px;
    max-width: 88%;
    margin-left: 0 !important;
    margin-right: auto !important;
}

/* User: blue bubble, right */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    justify-content: flex-end;
    transform-origin: bottom right;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
    [data-testid="stChatMessageContent"] {
    background: var(--ios-blue);
    color: #fff;
    border-bottom-right-radius: 6px;
    max-width: 75%;
    margin-left: auto !important;
    margin-right: 0 !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
    [data-testid="stChatMessageContent"] * { color: #fff; }

/* Typing indicator (three bouncing dots) */
@keyframes dot-bounce {
    0%, 60%, 100% { transform: translateY(0); opacity: 0.35; }
    30%           { transform: translateY(-5px); opacity: 1; }
}
.typing { display: flex; gap: 5px; align-items: center; height: 1.35rem; }
.typing span {
    width: 8px; height: 8px; border-radius: 50%; background: #8E8E93;
    animation: dot-bounce 1.2s infinite ease-in-out;
}
.typing span:nth-child(2) { animation-delay: 0.15s; }
.typing span:nth-child(3) { animation-delay: 0.30s; }

/* ---------- Input pill ---------- */
[data-testid="stBottom"] > div { background: transparent; }

/* Soft blur under the text box: text scrolling underneath is blurred a little,
   strongest right at the bar and fading out upward. One layer (it used to be
   two stacked ones) -- same look, cheaper to draw while scrolling. */
[data-testid="stBottom"]::before {
    content: "";
    position: absolute;
    left: 0; right: 0; bottom: 0;
    height: 150px;
    pointer-events: none;
    -webkit-backdrop-filter: blur(8px);
    backdrop-filter: blur(8px);
    background: linear-gradient(to top, rgba(255,255,255,0.85) 0%, rgba(255,255,255,0.4) 55%, rgba(255,255,255,0) 100%);
    -webkit-mask-image: linear-gradient(to top, #000 0%, rgba(0,0,0,0.7) 50%, transparent 100%);
    mask-image: linear-gradient(to top, #000 0%, rgba(0,0,0,0.7) 50%, transparent 100%);
}
[data-testid="stBottomBlockContainer"] { position: relative; z-index: 1; }
[data-testid="stBottomBlockContainer"] { max-width: 820px; padding-left: 1.5rem; padding-right: 1.5rem; }
[data-testid="stChatInput"] { border: none !important; box-shadow: none !important; background: transparent !important; }
[data-testid="stChatInput"] > div {
    border-radius: 26px;
    border: 1px solid rgba(60, 60, 67, 0.18) !important;
    background: #fff !important;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
    transition: box-shadow 0.25s var(--ios-ease), border-color 0.25s var(--ios-ease);
}
[data-testid="stChatInput"] > div:focus-within {
    border-color: var(--ios-blue) !important;
    box-shadow: 0 4px 24px rgba(0, 122, 255, 0.18);
}
[data-testid="stChatInput"] textarea { background: transparent !important; }
[data-testid="stChatInput"] button {
    background: var(--ios-blue) !important;
    color: #fff !important;
    border-radius: 50%;
    transition: transform 0.15s var(--ios-ease);
}
[data-testid="stChatInput"] button:active { transform: scale(0.9); }

/* ---------- Profile pill (top of every chat, Memories page) ---------- */
.chat-head { display: flex; align-items: center; margin: 0 0 0.35rem 0; }
.who-pill {
    display: inline-flex; align-items: center; gap: 0.4rem;
    padding: 0.16rem 0.7rem 0.16rem 0.2rem;
    border-radius: 999px;
    background: var(--c, #E5E5EA);
    color: #1C1C1E; font-size: 0.8rem; font-weight: 600; line-height: 1.2;
    box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.06);
}
.who-pill .av {
    width: 1.4rem; height: 1.4rem; border-radius: 50%;
    background: rgba(255, 255, 255, 0.7);
    display: inline-grid; place-items: center;
    font-size: 0.74rem; font-weight: 700;
}

/* ---------- Compact controls (sidebar, Memories page, popups) ---------- */
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.2rem; }
[data-testid="stSidebarContent"] { padding-top: 0; }
[data-testid="stSidebarHeader"] { padding: 0.5rem 0.75rem 0.1rem 0.75rem; height: auto; min-height: 0; }
[data-testid="stSidebarUserContent"] { padding: 0.25rem 0.6rem 1rem 0.6rem; }
[data-testid="stSidebar"][aria-expanded="true"] {
    width: 250px !important; min-width: 250px !important; max-width: 250px !important;
}
[data-testid="stSidebar"] {
    background: #F2F2F7;                       /* flat: blurring a flat colour looked the same but cost speed */
    border-right: 1px solid rgba(60, 60, 67, 0.12);
}

[data-testid="stSidebar"] .stButton > button {
    justify-content: flex-start; text-align: left;
    overflow: hidden; white-space: nowrap;
    min-height: var(--ctl-h); padding: 0.15rem 0.6rem;
    border-radius: var(--radius); border: none;
    background: transparent; color: #1c1c1e;
    font-size: var(--ctl-font);
    transition: background 0.2s var(--ios-ease), transform 0.15s var(--ios-ease);
}
[data-testid="stSidebar"] .stButton button > div { justify-content: flex-start; width: 100%; min-width: 0; }
[data-testid="stSidebar"] .stButton button p {
    text-align: left; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    font-size: var(--ctl-font); margin: 0;
}
[data-testid="stSidebar"] .stButton > button:hover { background: rgba(60, 60, 67, 0.08); }
[data-testid="stSidebar"] .stButton > button:active { transform: scale(0.97); }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { margin: 0.3rem 0 0.1rem 0.3rem; font-size: 0.72rem; }

/* the open chat */
[data-testid="stSidebar"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] .stButton > [data-testid="stBaseButton-primary"] {
    background: rgba(0, 122, 255, 0.14); color: var(--ios-blue); font-weight: 600;
}

/* profile chip (tinted with the profile's colour, see dynamic css) */
[data-testid="stSidebar"] .st-key-switch_profile button { font-weight: 600; }
/* New chat = filled blue; Memories / Back = soft grey */
[data-testid="stSidebar"] .st-key-new_chat button,
[data-testid="stSidebar"] .st-key-new_chat [data-testid="stBaseButton-secondary"] {
    background: var(--ios-blue); color: #fff; font-weight: 600; justify-content: center;
}
[data-testid="stSidebar"] .st-key-new_chat button p { color: #fff; }
[data-testid="stSidebar"] .st-key-new_chat button:hover { background: #0A6FE0; }
[data-testid="stSidebar"] .st-key-open_memories button,
[data-testid="stSidebar"] .st-key-back_to_chat button { background: rgba(60, 60, 67, 0.08); justify-content: center; }

/* New chat / Memories / Back are icon-only (name shows on hover): icon dead centre */
[data-testid="stSidebar"] .st-key-new_chat button,
[data-testid="stSidebar"] .st-key-open_memories button,
[data-testid="stSidebar"] .st-key-back_to_chat button { padding: 0.15rem 0; justify-content: center; }
[data-testid="stSidebar"] .st-key-new_chat button > div,
[data-testid="stSidebar"] .st-key-open_memories button > div,
[data-testid="stSidebar"] .st-key-back_to_chat button > div { justify-content: center; }
[data-testid="stSidebar"] .st-key-new_chat [data-testid="stIconMaterial"],
[data-testid="stSidebar"] .st-key-open_memories [data-testid="stIconMaterial"],
[data-testid="stSidebar"] .st-key-back_to_chat [data-testid="stIconMaterial"] { font-size: 1.2rem; margin: 0; }
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] { gap: 0.35rem; }

/* chat rows: a small dot in the owner's colour, then the title (one line) */
[data-testid="stSidebar"] [class*="st-key-chat_"] button { gap: 0.5rem; }
[data-testid="stSidebar"] [class*="st-key-chat_"] button::before {
    content: ""; flex: 0 0 9px; width: 9px; height: 9px; border-radius: 50%;
    background: #D1D1D6; box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.12);
}

/* inputs, dropdowns and their open lists */
[data-testid="stTextInput"] [data-baseweb="input"],
[data-testid="stTextInput"] input { border-radius: var(--radius); }
[data-testid="stTextInput"] input { font-size: var(--ctl-font); }
[data-baseweb="select"] > div {
    min-height: var(--ctl-h); font-size: var(--ctl-font); border-radius: var(--radius);
}
[data-baseweb="popover"] [role="listbox"] { padding: 0.2rem; border-radius: var(--radius); }
[data-baseweb="popover"] [role="option"], [data-baseweb="popover"] li {
    min-height: 0 !important; padding: 0.3rem 0.65rem !important;
    font-size: var(--ctl-font) !important; border-radius: 8px;
}
[data-testid="stMain"] .stButton > button {
    min-height: var(--ctl-h); padding: 0.15rem 0.7rem;
    font-size: var(--ctl-font); border-radius: var(--radius);
}
[data-testid="stExpander"] summary { font-size: var(--ctl-font); padding: 0.4rem 0.7rem; }
[data-testid="stDialog"] [role="dialog"] { border-radius: 22px; }
[data-testid="stDialog"] [data-testid="stVerticalBlock"] { gap: 0.6rem; }
[data-testid="stDialog"] h2 { font-size: 1.15rem; }

/* ---------- Empty state ---------- */
@keyframes fade-up { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
.empty-state { text-align: center; margin-top: 24vh; color: #8E8E93; animation: fade-up 0.6s var(--ios-ease) both; }
.empty-state h2 { font-weight: 600; letter-spacing: -0.02em; }

/* ---------- "Who's using?" picker ---------- */
.picker-title {
    text-align: center; font-size: 1.9rem; font-weight: 600; letter-spacing: -0.02em;
    margin: 8vh 0 0.3rem 0;
}
.picker-sub { text-align: center; color: #8E8E93; margin-bottom: 2rem; font-size: 0.95rem; }
.tile-name { text-align: center; font-weight: 500; font-size: 0.92rem; margin-top: 0.3rem; color: #1C1C1E; }
[class*="st-key-pick_"] [data-testid="stButton"] { display: flex; justify-content: center; }
[class*="st-key-pick_"] button {
    width: 104px; height: 104px; border-radius: 28px; border: none;
    background: #E5E5EA; color: #1C1C1E;
    transition: transform 0.2s var(--ios-ease), box-shadow 0.2s var(--ios-ease);
}
[class*="st-key-pick_"] button p { font-size: 2.3rem; font-weight: 600; line-height: 1; }
[class*="st-key-pick_"] button:hover { transform: scale(1.07); box-shadow: 0 8px 22px rgba(0, 0, 0, 0.12); }
[class*="st-key-pick_"] button:active { transform: scale(0.96); }
.st-key-pick_add button {
    background: transparent; border: 2px dashed rgba(60, 60, 67, 0.3); color: #8E8E93;
}
.st-key-pick_add button p { font-size: 2.6rem; font-weight: 300; }
[class*="st-key-pick_"], .st-key-manage_profiles {
    width: 100% !important; display: flex !important; justify-content: center !important;
}
.st-key-manage_profiles { margin-top: 1.6rem; }
.preview-tile {
    width: 84px; height: 84px; border-radius: 24px; margin: 0.9rem auto 1.1rem auto;
    display: grid; place-items: center; font-size: 2rem; font-weight: 600; color: #1C1C1E;
}
</style>
"""

HIDE_SIDEBAR_CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"], [data-testid="stExpandSidebarButton"] { display: none !important; }
[data-testid="stMainBlockContainer"] { max-width: 760px; }
</style>
"""


def dynamic_css(profiles: list[dict], chats: list[tuple[str, dict]], active_profile: dict | None) -> str:
    """
    Per-profile colours: picker tiles, the sidebar profile chip, and the dot in front
    of every chat. Colours come from the database and are checked to be plain #RRGGBB.
    chats: [(session_id, {"profile_id": ...}), ...]
    """
    color_of = {p["id"]: safe_color(p.get("color")) for p in profiles}
    rules = []
    for p in profiles:
        rules.append(f'.st-key-pick_{p["id"]} button {{ background: {color_of[p["id"]]} !important; }}')
    for sid, chat in chats:
        color = color_of.get(chat["profile_id"], "#D1D1D6")
        rules.append(f'[data-testid="stSidebar"] .st-key-chat_{sid} button::before {{ background: {color} !important; }}')
    if active_profile:
        rules.append(
            f'[data-testid="stSidebar"] .st-key-switch_profile button '
            f'{{ background: {safe_color(active_profile.get("color"))} !important; }}'
        )
    return "<style>" + "\n".join(rules) + "</style>" if rules else ""
