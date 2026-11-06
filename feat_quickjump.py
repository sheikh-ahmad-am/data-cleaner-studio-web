"""Quick jump — the honest Streamlit version of Supabase Studio's
Cmd+K command menu (research report §9, pattern 4).

What Supabase does: a global Cmd+K palette that searches navigation,
docs and actions in one overlay, with a visible "Search... Ctrl K"
trigger in the top bar.

What this module does — and its honest limit, stated plainly: a true
overlay command palette is NOT feasible in Streamlit. Streamlit
renders server-side and has no global keyboard listener, so Cmd+K /
Ctrl+K cannot be captured reliably (the browser owns that shortcut in
many contexts) and no overlay can float above the app. Do NOT fake it
with a key-capture hack. The closest honest version is this: a sidebar
search box labelled with a ⌘K hint that filters the app's real
sections and key actions as the user types, and jumps to the selected
one through the app's existing ``pending_tab`` mechanism
(``st.session_state["pending_tab"] = <section key>`` + ``st.rerun()``,
applied by app.py before the top bar renders).

Every action listed here is real: all eleven sections plus the key
actions (Upload, Load sample, Clean, Export, Ask, Back up, Morning
run, Shortcuts, What's new). A jump only navigates — it never runs a
destructive action and never changes data.

Integration (for the coordinator — app.py change, one call):
  1. At the top of app.py, next to the other feat imports, add::

         import feat_quickjump

  2. In the sidebar, right after the sidebar nav renders
     (``ui_design.sidebar_nav(_nav_sections, active=_nav_active)``),
     add::

         feat_quickjump.render_quick_jump(st)

     The box lives in the sidebar so it is visible on every screen,
     like Studio's top-bar search. It must be called AFTER the
     ``pending_tab`` application near the top of the main flow (it
     already is — the sidebar renders after that point), and it must
     NOT be called before the login view renders.

Public API (presentation + navigation only — no behaviour changes):
  * ``QUICK_ACTIONS`` — the full action list (dicts).
  * ``filter_actions(query, actions=None)`` — pure: the actions whose
    label / hint / keywords match every word of ``query``; an empty
    query returns all actions, in defined order.
  * ``resolve_section(action_key)`` — pure: the section key an action
    jumps to, or None for an unknown key.
  * ``render_quick_jump(st, actions=None)`` — draw the sidebar box;
    returns the section key jumped to, or None.
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


def render_quick_jump(st, actions=None):
    """Draw the sidebar Quick jump box. Returns the section key jumped
    to, or None when the user did not pick anything this run.

    The box is a text input (labelled with the ⌘K hint) plus one
    button per matching action. Clicking a button sets
    ``pending_tab`` and reruns — the same mechanism the sidebar
    Profile button and every "Go to the Clean tab" button already use,
    so the jump lands exactly where the section radio expects it.
    """
    items = list(QUICK_ACTIONS if actions is None else actions)
    query = st.sidebar.text_input(
        "Quick jump ⌘K",
        key="quickjump_query",
        placeholder="Search sections and actions…",
        help=("Type to filter the sections and actions below, then pick "
              "one to jump there. Streamlit cannot capture the Cmd+K / "
              "Ctrl+K shortcut itself, so this search box is the jump — "
              "there is no hidden keyboard shortcut."))
    matches = filter_actions(query, items)
    if query and query.strip() and not matches:
        # Supabase empty-state pattern: a dead end always offers the
        # next step — here, the words that do match something.
        st.sidebar.info("No matching section or action — "
                        "try 'clean', 'export' or 'profile'.")
        return None
    if not query or not str(query).strip():
        st.sidebar.caption("Type to filter — pick a result to jump there.")
        return None
    for action in matches[:_MAX_SHOWN]:
        label = f"{action['label']} — {action['hint']}"
        if st.sidebar.button(label, key=f"quickjump_go_{action['key']}"):
            section = resolve_section(action["key"])
            if section is not None:
                st.session_state["pending_tab"] = section
                st.rerun()  # real Streamlit reruns here, so the return
                # below only runs for fakes/tests.
                return section
    if len(matches) > _MAX_SHOWN:
        st.sidebar.caption(
            f"…and {len(matches) - _MAX_SHOWN} more — "
            "narrow the search to see them.")
    return None
