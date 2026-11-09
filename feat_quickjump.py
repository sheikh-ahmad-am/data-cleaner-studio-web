"""Quick jump — the honest Streamlit version of Supabase Studio's
Cmd+K command menu (research report §9, pattern 4).

What Supabase does: a global Cmd+K palette that searches navigation,
docs and actions in one overlay, with a visible "Search... Ctrl K"
trigger in the top bar.

What this module does — and its honest limit, stated plainly: a true
overlay command palette is NOT feasible in Streamlit. Streamlit
renders server-side and has no global keyboard listener, so Cmd+K /
Ctrl+K cannot be captured reliably (the browser owns that shortcut in
many contexts). Do NOT fake it with a key-capture hack. What IS
possible, and what the top-bar version does, is a real overlay
panel: the search lives inside an ``st.popover`` ("Search…"), so the
results float above the page instead of pushing content, and the
panel closes on outside click / Escape / selection, the way
Streamlit popovers do. The sidebar version stays an in-flow box.
Either way the box filters the app's real sections and key actions
as the user types, and jumps to the selected one through the app's
existing ``pending_tab`` mechanism
(``st.session_state["pending_tab"] = <section key>`` + ``st.rerun()``,
applied by app.py before the top bar renders).

One thing a small same-origin JS bridge CAN do honestly (Round 3c,
``QUICKJUMP_KEYS_BRIDGE_HTML`` — same pattern as the Round 3 OS
bridge): while the search box itself is focused, ArrowDown /
ArrowUp move the highlight and Enter clicks the highlighted
result — a plain first Enter submits and shows the matches, a
second Enter (or ↓ + Enter) jumps. The
bridge only handles keys in that one box — it never listens
globally — and the Enter click goes through the very same result
button the mouse uses, so the jump takes exactly the mouse path.
Cmd+K / Ctrl+K global capture is still NOT feasible.

Every action listed here is real: all eleven sections plus the key
actions (Upload, Load sample, Clean, Export, Ask, Back up, Morning
run, Shortcuts, What's new). A jump only navigates — it never runs a
destructive action and never changes data.

Integration (for the coordinator — app.py change, one call):
  1. At the top of app.py, next to the other feat imports, add::

         import feat_quickjump

  2. In the top bar, pass the search column with ``compact=True``::

         feat_quickjump.render_quick_jump(
             st, container=_top_actions["search_col"], compact=True)

     The box sits in the top bar like the dashboard's Search pill.
     It must be called AFTER the ``pending_tab`` application near
     the top of the main flow (it already is — the top bar renders
     after that point), and it must NOT be called before the login
     view renders.

Public API (presentation + navigation only — no behaviour changes):
  * ``QUICK_ACTIONS`` — the full action list (dicts).
  * ``filter_actions(query, actions=None)`` — pure: the actions whose
    label / hint / keywords match every word of ``query``; an empty
    query returns all actions, in defined order.
  * ``resolve_section(action_key)`` — pure: the section key an action
    jumps to, or None for an unknown key.
  * ``render_quick_jump(st, actions=None, container=None,
    compact=False)`` — draw the palette (popover in compact mode,
    in-flow box otherwise); returns the section key jumped to, or
    None.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# The action list. ``section`` is an app.py section key (see _nav_labels:
# preview, join, clean, kpis, dashboard, compare, report, tools,
# tutorial, settings, profile). ``key`` is unique and stable — it is
# used for the Streamlit widget keys. ``keywords`` are extra search
# words that do not show in the UI.
# ---------------------------------------------------------------------------
QUICK_ACTIONS = [
    # ---- every section, in the order the app lists them ----
    {"key": "preview", "label": "Upload & preview", "section": "preview",
     "hint": "Upload a file and see the first rows",
     "keywords": "upload file preview rows data load"},
    {"key": "clean", "label": "Clean", "section": "clean",
     "hint": "Fix duplicates, blanks and formats",
     "keywords": "clean fix duplicates blanks format dedupe"},
    {"key": "join", "label": "Join files", "section": "join",
     "hint": "Combine two files on a shared column",
     "keywords": "join merge combine append files"},
    {"key": "kpis", "label": "KPIs", "section": "kpis",
     "hint": "Totals, averages and the KPI list",
     "keywords": "kpi metrics totals averages numbers"},
    {"key": "dashboard", "label": "Dashboard", "section": "dashboard",
     "hint": "Charts and what moves together",
     "keywords": "dashboard charts graphs correlations forecast ask"},
    {"key": "compare", "label": "Compare files", "section": "compare",
     "hint": "What changed between two versions",
     "keywords": "compare diff changes versions old new"},
    {"key": "report", "label": "Report & export", "section": "report",
     "hint": "Download the cleaned file and the report",
     "keywords": "report export download csv excel pdf powerpoint"},
    {"key": "tools", "label": "Tools", "section": "tools",
     "hint": "Watch folder, schedule, backups, databases",
     "keywords": "tools watch folder schedule backup database morning"},
    {"key": "tutorial", "label": "How to use", "section": "tutorial",
     "hint": "The seven-step guide",
     "keywords": "tutorial guide help how to learn steps"},
    {"key": "settings", "label": "Settings", "section": "settings",
     "hint": "Account, backend and API keys",
     "keywords": "settings account backend api key groq gemini"},
    {"key": "profile", "label": "Profile", "section": "profile",
     "hint": "Display name, storage and account",
     "keywords": "profile account display name storage delete"},
    # ---- key actions (jump to the section where they live) ----
    {"key": "upload", "label": "Upload a file", "section": "preview",
     "hint": "CSV, Excel, JSON or Parquet, up to 1000 MB",
     "keywords": "upload file csv xlsx json parquet"},
    {"key": "sample", "label": "Load the sample file", "section": "preview",
     "hint": "messy_sales.csv — 80 rows to practise on",
     "keywords": "sample demo example try messy_sales"},
    {"key": "clean-data", "label": "Clean the data", "section": "clean",
     "hint": "Run the fixes on the loaded file",
     "keywords": "clean run fixes apply"},
    {"key": "export", "label": "Download the cleaned file",
     "section": "report",
     "hint": "CSV, Excel or the PDF report",
     "keywords": "download export cleaned csv excel pdf"},
    {"key": "ask", "label": "Ask a question", "section": "dashboard",
     "hint": "Ask the data in plain words",
     "keywords": "ask question query answer"},
    {"key": "backup", "label": "Back up the raw data", "section": "tools",
     "hint": "A safety copy before cleaning",
     "keywords": "backup restore safety copy raw"},
    {"key": "schedule", "label": "Set up the morning run",
     "section": "tools",
     "hint": "Auto-clean every morning on your Windows PC",
     "keywords": "schedule morning run auto daily task"},
    {"key": "shortcuts", "label": "Keyboard shortcuts", "section": "tools",
     "hint": "Ctrl+O, Ctrl+S and the rest",
     "keywords": "shortcuts keyboard keys ctrl"},
    {"key": "whats-new", "label": "What's new", "section": "preview",
     "hint": "The latest changes, at the top of the page",
     "keywords": "whats new changes version changelog update"},
]

# How many matching actions to show as buttons. The rest stay hidden
# behind a "…and N more" line so the sidebar never fills up.
_MAX_SHOWN = 8


def filter_actions(query, actions=None):
    """Return the actions matching ``query``, in defined order.

    Pure function (no Streamlit calls) so it is unit-testable. Every
    word of the query must appear somewhere in the action's label,
    hint or keywords (case-insensitive, substring match). An empty or
    blank query returns ALL actions — the palette's resting state is
    the full list, not an empty one.
    """
    items = list(QUICK_ACTIONS if actions is None else actions)
    words = str(query or "").strip().lower().split()
    if not words:
        return items
    matches = []
    for action in items:
        haystack = " ".join((action.get("label", ""),
                             action.get("hint", ""),
                             action.get("keywords", ""))).lower()
        if all(word in haystack for word in words):
            matches.append(action)
    return matches


def resolve_section(action_key):
    """Return the section key an action jumps to, or None.

    Pure function. ``action_key`` is a ``QUICK_ACTIONS`` ``key`` (e.g.
    ``"export"`` -> ``"report"``); unknown keys return None so the
    caller never sets a bogus ``pending_tab``.
    """
    for action in QUICK_ACTIONS:
        if action.get("key") == action_key:
            return action.get("section")
    return None


#: Plain session key set on a jump so the NEXT render clears the
#: search query before the input mounts. Writing the input's own
#: key after it mounts raises (a widget owns its key); the flag is
#: a plain key, so the write is legal, and the clear happens
#: before the input is created on the next run — the old panel
#: stayed open after a jump because the query survived the rerun
#: and re-rendered the same results (clone-R1 live failure).
_QUICKJUMP_CLEAR_KEY = "quickjump_clear_after_jump"
#: The top-bar palette's popover key. Its element container carries
#: the ``st-key-<key>`` class, so the design system can hide the
#: trigger's expand_more chevron (the Search pill reads clean).
#: The live key is the base plus an epoch suffix (see
#: ``_popover_key``): Streamlit has no API to force-close a
#: popover, and a popover stays open across a rerun — so after a
#: jump the epoch bumps and the next run mounts a FRESH popover
#: widget (closed by default). Without the bump the panel would
#: stay open after a selection showing an empty input; with it,
#: the panel closes on selection exactly as it does on
#: outside-click / Escape.
QUICKJUMP_POPOVER_KEY = "quickjump_popover"


def _popover_key(st):
    """The live popover key: base + the epoch the last jump left
    behind (0 when no jump has happened yet)."""
    return f"{QUICKJUMP_POPOVER_KEY}_{st.session_state.get('quickjump_popover_epoch', 0)}"


def _render_quick_jump_body(st, host, items, compact=False):
    """The palette body: the search input plus one button per
    matching action, shared by the popover (compact) and in-flow
    (sidebar) versions. Widgets render on ``host`` — the popover
    itself in compact mode (called inside the ``with`` block, so
    the module-level calls land inside it), the container
    otherwise. Returns the section key jumped to, or None.
    Clicking a result sets the clear flag + pending_tab and reruns
    — the flag clears the query on the next run, so the panel never
    re-renders stale results after a jump."""
    query = host.text_input(
        "Quick jump ⌘K",
        key="quickjump_query",
        placeholder="Search sections and actions…",
        label_visibility="collapsed" if compact else "visible",
        help=("Type to filter, then Enter to show the matches — Enter "
              "again (or ↓ + Enter) jumps to the highlighted one. "
              "Streamlit cannot capture the Cmd+K / Ctrl+K shortcut "
              "itself, so this search box is the jump."))
    matches = filter_actions(query, items)
    if query and query.strip() and not matches:
        # Supabase empty-state pattern: a dead end always offers the
        # next step — here, the words that do match something.
        host.info("No matching section or action — "
                  "try 'clean', 'export' or 'profile'.")
        return None
    if not query or not str(query).strip():
        host.caption("Type to filter — pick a result to jump there.")
        return None
    for action in matches[:_MAX_SHOWN]:
        label = f"{action['label']} — {action['hint']}"
        if host.button(label, key=f"quickjump_go_{action['key']}"):
            section = resolve_section(action["key"])
            if section is not None:
                st.session_state[_QUICKJUMP_CLEAR_KEY] = True
                # Bump the popover epoch: the next run mounts a
                # fresh popover (closed), so the panel closes on
                # selection instead of lingering open.
                st.session_state["quickjump_popover_epoch"] = \
                    st.session_state.get("quickjump_popover_epoch", 0) + 1
                st.session_state["pending_tab"] = section
                st.rerun()  # real Streamlit reruns here, so the return
                # below only runs for fakes/tests.
                return section
    if len(matches) > _MAX_SHOWN:
        host.caption(
            f"…and {len(matches) - _MAX_SHOWN} more — "
            "narrow the search to see them.")
    return None


#: Keyboard bridge for the top-bar palette (Round 3c): a
#: zero-height script, same pattern as the Round 3 OS bridge
#: (ui_design.OS_DARK_BRIDGE_HTML) — Streamlit has no
#: server-side way to know Enter was pressed in a text input
#: (its on_change also fires on blur, so it cannot tell "pick
#: the result" from "click away to dismiss"). The bridge runs in
#: the page, finds the search box by its aria-label, and — only
#: while that box is focused — lets ArrowDown / ArrowUp move a
#: highlight among the visible result buttons and Enter click the
#: highlighted one. A plain first Enter only submits (no results
#: are rendered yet), so the matches render for the user to see;
#: a second Enter, or ↓ + Enter, jumps. The
#: click goes through the very same button the mouse uses, so
#: the jump, the query clear and the popover close take exactly
#: the mouse path. State lives on the parent document (not in
#: the iframe) so it survives iframe reloads; the install is
#: idempotent, so a rerun that re-runs the script never stacks
#: a second listener. A failure (sandboxed iframe, disabled JS)
#: leaves the palette exactly as it was — mouse, Escape and
#: outside-click still work; keyboard selection just does not
#: happen. Cmd+K / Ctrl+K global capture is still NOT feasible
#: (see the module docstring) — this bridge only handles keys
#: while the search box itself is focused.
#:
#: One Streamlit fact shapes the design, stated plainly: a text
#: input submits its value on Enter (or blur) — never per
#: keystroke — so while the user is still typing there ARE no
#: result buttons yet, and live-per-keystroke list rendering is
#: NOT feasible with stock Streamlit (it would need a custom
#: component, which this app does not use). Enter therefore works
#: in two beats: a plain first Enter lets Streamlit's own submit
#: go through (no preventDefault), and the matches render in the
#: still-open popover for the user to see and pick — a second
#: Enter clicks the highlighted result. The ArrowDown/ArrowUp
#: keys move the highlight; if the user already moved the
#: highlight and then presses Enter, the bridge remembers the
#: pick (``autoPick``) so that when the results render after the
#: submit rerun it clicks that result for them — ArrowDown +
#: Enter still jumps straight to the chosen result in one beat.
#: The mouse path is untouched (a rendered result button still
#: jumps on click, and clicking the popover background blurs the
#: input, which submits the query and renders the results to
#: click). ``resultButtons`` matches ONLY
#: the ``st-key-quickjump_go_`` result buttons — never any other
#: button in the popover body (the text input itself renders a
#: button with empty text, and clicking that on Enter would
#: swallow the submit).
QUICKJUMP_KEYS_BRIDGE_HTML = """<script>(function(){try{
var doc=window.parent.document;
var S=doc.__dcsQuickJumpKeys;
if(!S){S=doc.__dcsQuickJumpKeys={highlight:0,lastQuery:null,installed:false,timer:null,autoPick:false,moved:false};}
function inputEl(){return doc.querySelector('input[aria-label="Quick jump ⌘K"]');}
function resultButtons(){
var input=inputEl();
if(!input){return [];}
var body=input.closest('div[data-testid="stPopoverBody"]');
var root=body||doc;
return Array.prototype.slice.call(root.querySelectorAll('[class*="st-key-quickjump_go_"] button'));}
function paint(){
var input=inputEl();
if(!input){S.lastQuery=null;S.autoPick=false;S.moved=false;return;}
if(input.value!==S.lastQuery){S.lastQuery=input.value;S.highlight=0;S.autoPick=false;S.moved=false;}
var btns=resultButtons();
if(btns.length&&S.highlight>=btns.length){S.highlight=btns.length-1;}
btns.forEach(function(b,i){
b.style.outline=(i===S.highlight&&btns.length)?'2px solid #117f50':'';
b.style.outlineOffset='1px';});
if(S.autoPick&&btns.length){
var target=btns[Math.min(S.highlight,btns.length-1)];
S.autoPick=false;S.highlight=0;S.lastQuery=null;S.moved=false;
target.click();}}
if(!S.installed){S.installed=true;
doc.addEventListener('keydown',function(e){
var input=inputEl();
if(!input||e.target!==input){return;}
if(e.key==='ArrowDown'){
e.preventDefault();
S.highlight=S.highlight+1;
S.moved=true;
paint();}
else if(e.key==='ArrowUp'){
e.preventDefault();
S.highlight=Math.max(S.highlight-1,0);
S.moved=true;
paint();}
else if(e.key==='Enter'){
var btns=resultButtons();
if(btns.length){
e.preventDefault();
e.stopPropagation();
var target=btns[Math.min(S.highlight,btns.length-1)];
S.highlight=0;S.lastQuery=null;S.autoPick=false;S.moved=false;
target.click();}
else if(input.value.trim()!==''){
// No results rendered yet: a plain first Enter only submits,
// so the matches render in the still-open popover for the user
// to see and pick (second Enter, or a click). Auto-pick only
// when the user already moved the highlight (ArrowDown/Up +
// Enter) — that is a choice, so it jumps straight to it.
if(S.moved){S.autoPick=true;}}}
},true);}
if(S.timer){clearInterval(S.timer);}
S.timer=setInterval(paint,200);
paint();
}catch(err){}})();</script>"""


def render_quick_jump(st, actions=None, container=None, compact=False):
    """Draw the Quick jump palette. Returns the section key jumped
    to, or None when the user did not pick anything this run.

    ``compact`` (the top bar) renders the palette inside an
    ``st.popover`` ("Search…"): the results float above the page
    as an overlay — they never push content — and the panel closes
    on outside click / Escape / selection, the way Streamlit
    popovers do. The old in-flow stack stayed open after selection,
    Escape, clear and navigation (clone-R1 live failure): the query
    was never cleared, so every rerun re-rendered the same results.
    Non-compact (the sidebar) keeps the in-flow box.

    A jump clears the query on the NEXT run (the clear flag, read
    before the input mounts) so no stale results survive a jump in
    either version. Clicking a button sets ``pending_tab`` and
    reruns — the same mechanism the sidebar Profile button and
    every "Go to the Clean tab" button already use, so the jump
    lands exactly where the section radio expects it.

    ``container`` is where the palette renders (``st.sidebar`` by
    default). The app passes the top bar's search column, so the
    box sits in the top bar like the dashboard's Search pill;
    ``compact`` then hides the input's label (the placeholder
    already says what it is) so the bar stays one row tall.
    """
    box = container if container is not None else st.sidebar
    items = list(QUICK_ACTIONS if actions is None else actions)
    if st.session_state.pop(_QUICKJUMP_CLEAR_KEY, False):
        # A jump landed on the previous run: clear the query BEFORE
        # the input mounts, so the results do not re-render.
        st.session_state["quickjump_query"] = ""
    if compact:
        with box.popover("Search…", icon=":material/search:",
                         use_container_width=True,
                         key=_popover_key(st)):
            # Inside the with-block the module-level calls land in
            # the popover, so the host here is ``st`` itself.
            return _render_quick_jump_body(st, st, items, compact=True)
    return _render_quick_jump_body(st, box, items, compact=compact)
