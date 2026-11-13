"""How to use tab as Supabase's Migrations empty state + Help panel,
mapped to this app's own help (the mapping the clone spec confirms:
How to use -> Migrations empty state + Help panel).

Supabase's Migrations page, from the audit (spec): the Database
sub-nav's Migrations entry shows an empty state plus a CLI
instruction card — "no migrations yet" with the commands that
create and push one, each with a copy button. Supabase's Help
panel (the "?" icon in the top bar) opens a right-side panel with
Assistant, Docs, Troubleshooting, Status, Contact support, Discord.

The mapping onto this app's REAL help, honestly:

* "Guide" is the app's own guide — the seven steps from
  ``feat_tutorial.TUTORIAL_STEPS``, rendered verbatim (including
  the privacy sentence, which the tutorial swaps for the
  mode-correct wording), plus the same "Got it" button. The guide
  needs no data, so it renders with no file loaded; when nothing
  is loaded yet the "No data loaded yet" empty state with its
  "Try the sample data" CTA sits above it (the Tools/Clean/Join/
  Compare/Report reachability fix).
* "Migrations" is Supabase's empty state + instruction cards.
  This app has no schema migrations and no CLI, so the empty
  state says so plainly — "No migrations yet: cleaning happens
  in place on your file, so there is nothing to migrate" — and
  the instruction cards show the real data journey (load, clean,
  take it away) as copyable text in ``st.code`` blocks, which
  carry Streamlit's own copy button. No fake CLI commands.
  A second card points at where changes actually live: every
  cleaning run is recorded in the audit trail, with buttons to
  Compare's Logs and Clean's run history (real navigation).
* "Help" is the Help panel's sections that have a real
  counterpart here: Assistant (the app's "Ask your data", which
  lives on the Preview tab under More analysis), Docs (a button
  per guide step, opening the Guide view), and Status (the app's
  own Status tab). Troubleshooting, Contact support and Discord
  have no counterpart in this app, so they are not rendered —
  not faked.

What is NOT built, and why (stated plainly, not faked):

* A guided tour / interactive walkthrough: stock Streamlit
  cannot highlight elements or step through the UI. The numbered
  guide, with buttons that navigate to the tab each step is
  about, is the honest equivalent.
* Hash-anchor scrolling to one guide step: not achievable in
  stock Streamlit (the Settings round proved it). A Docs button
  opens the Guide view, where all seven steps are visible — it
  does not scroll to one step.
* A CLI: the instruction cards copy the real workflow text;
  there is no ``dcs`` command to run.

Contract:
  - VIEW_GUIDE / VIEW_MIGRATIONS / VIEW_HELP : sub-nav view keys.
  - MIGRATION_STEPS : list of {"title", "text"} dicts (3 steps).
  - render_howtouse_tab(st, ctx) — the tab. ctx keys: raw,
    load_sample, settings_path. ``raw`` is only needed for the
    Guide view's no-data empty state; the tab renders with no
    data loaded.
"""

import feat_tutorial
import ui_design

VIEW_GUIDE = "guide"
VIEW_MIGRATIONS = "migrations"
VIEW_HELP = "help"
_VIEWS = [(VIEW_GUIDE, "Guide"),
          (VIEW_MIGRATIONS, "Migrations"),
          (VIEW_HELP, "Help")]

MIGRATION_STEPS = [
    {"title": "Load a file",
     "text": ("Upload a CSV, Excel or JSON file from the sidebar, "
              "or press \"Try the messy sample\".")},
    {"title": "Clean it",
     "text": ("Tick the fixes on the Clean tab, then press "
              "\"Clean my data\".")},
    {"title": "Take it away",
     "text": ("Download the cleaned file and the report from the "
              "Report tab.")},
]


# --------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------

def _render_empty(st, load_sample) -> None:
    """The no-data empty state: the guided card with the one-click
    sample loader (the Tools/Clean/Join/Compare/Report
    reachability fix — the tab opens, the guide stays visible
    below, and the CTA loads the sample so the reader can follow
    along)."""
    if ui_design.empty_state(
            "No data loaded yet",
            "Upload a file from the sidebar on the left, or skip the "
            "setup and explore with the sample file: it loads the "
            "messy sales data (80 rows) so you can follow the guide "
            "with real data.",
            cta_label="Try the sample data"):
        if load_sample is not None:
            load_sample()
        st.rerun()


def _render_guide(st, ctx) -> None:
    """The Guide view: the seven steps, verbatim from
    feat_tutorial (same wording, same privacy-sentence swap,
    same "Got it" button), with the no-data empty state above
    them when nothing is loaded yet."""
    if ctx.get("raw") is None:
        _render_empty(st, ctx.get("load_sample"))
    feat_tutorial.render_tutorial_page(
        st, settings_path=ctx.get("settings_path"))


def _render_migrations(st, ctx) -> None:
    """The Migrations view: Supabase's empty state + instruction
    cards. The empty state is real — this app keeps no schema
    migrations — and the cards show the real data journey as
    copyable text (st.code carries Streamlit's own copy button).
    A second card points at where changes actually live: the
    audit trail."""
    ui_design.section_heading(
        "Migrations",
        sub="Schema migrations, Supabase-style — this app keeps none.")
    ui_design.card(
        "No migrations yet",
        body="This app has no database migrations. Cleaning happens "
             "in place on your file, so there is nothing to migrate "
             "— and nothing waiting for you here.")
    st.markdown('<div class="dcs-micro-label">Get started</div>',
                unsafe_allow_html=True)
    st.write("The data journey, in three steps — each one copies "
             "with the button on its right.")
    for step in MIGRATION_STEPS:
        st.markdown(
            f'<div class="dcs-micro-label">{step["title"]}</div>',
            unsafe_allow_html=True)
        st.code(step["text"])
    ui_design.card(
        "Where your changes live",
        body="Cleaning runs are the migration history of this file — "
             "every run is recorded in the audit trail, newest first.")
    _c1, _c2 = st.columns(2)
    with _c1:
        if ui_design.icon_button(
                "Open Compare → Logs", "book", kind="secondary",
                key="htu_mig_compare",
                help="Open the activity log."):
            st.session_state["pending_tab"] = "compare"
            st.rerun()
    with _c2:
        if ui_design.icon_button(
                "Open Clean → Run history", "book", kind="secondary",
                key="htu_mig_clean",
                help="Open the Clean tab's run history."):
            st.session_state["pending_tab"] = "clean"
            st.rerun()


def _render_help(st, ctx) -> None:
    """The Help view: the Help panel's sections that have a real
    counterpart here — Assistant, Docs, Status. Troubleshooting,
    Contact support and Discord have none, so they are not
    rendered."""
    ui_design.section_heading(
        "Help",
        sub="Assistant, docs and status — the app's own help, in "
            "Supabase's Help panel shape.")
    ui_design.card(
        "Assistant",
        body="Ask your data answers questions about your file in "
             "plain words. It lives on the Preview tab, under "
             "More analysis.")
    if ui_design.icon_button(
            "Open Preview", "book", kind="secondary",
            key="htu_help_preview",
            help="Open Preview — Ask your data is under More analysis."):
        st.session_state["pending_tab"] = "preview"
        st.rerun()
    ui_design.card(
        "Docs",
        body="The guide: seven short steps, from a messy file to a "
             "finished report. Pick a step to open the guide.")
    for i, step in enumerate(feat_tutorial.TUTORIAL_STEPS):
        if st.button(f"{i + 1}. {step['title']}",
                     key=f"htu_doc_{i}", use_container_width=False):
            st.session_state["howtouse_view"] = VIEW_GUIDE
            st.rerun()
    ui_design.card(
        "Status",
        body="Is the app healthy? The Status tab shows the app's "
             "own health.")
    if ui_design.icon_button(
            "Open Status", "book", kind="secondary",
            key="htu_help_status",
            help="Open the Status tab."):
        st.session_state["pending_tab"] = "status"
        st.rerun()


# --------------------------------------------------------------------------
# Tab
# --------------------------------------------------------------------------

def render_howtouse_tab(st, ctx) -> None:
    """The How to use tab as Supabase's Migrations empty state +
    Help panel.

    Left sub-nav (Back to dashboard / Guide / Migrations / Help)
    + main column: the guide, the migrations empty state with its
    instruction cards, or the help panel. Renders with no data
    loaded — the sub-nav and the guide stay visible, and the
    "Try the sample data" CTA sits above the steps until a file
    is loaded.
    """
    session = st.session_state
    view = session.get("howtouse_view", VIEW_GUIDE)
    if view not in (VIEW_GUIDE, VIEW_MIGRATIONS, VIEW_HELP):
        view = VIEW_GUIDE

    _set_nav, _set_main = st.columns([1, 4])
    with _set_nav:
        if st.button("← Back to dashboard",
                     key="htu_back_dashboard",
                     use_container_width=True):
            session["pending_tab"] = "dashboard"
            st.rerun()
        st.markdown('<div class="dcs-micro-label">How to use</div>',
                    unsafe_allow_html=True)
        for _key, _label in _VIEWS:
            if st.button(_label, key=f"htu_nav_{_key}",
                         disabled=(view == _key),
                         use_container_width=True):
                session["howtouse_view"] = _key
                st.rerun()

    with _set_main:
        if view == VIEW_GUIDE:
            _render_guide(st, ctx)
        elif view == VIEW_MIGRATIONS:
            _render_migrations(st, ctx)
        else:
            _render_help(st, ctx)
