"""Clean tab as Supabase's SQL Editor, mapped to this app's own cleaning
run (the mapping the clone spec confirms: Clean -> SQL Editor —
sub-sidebar sections + tabbed editor + Run/Save bar + Results/Chart area).

Supabase's SQL Editor, from the audit (spec Pass A section 6): a left
sub-sidebar (Search queries, + create, SHARED / FAVORITES / PRIVATE /
LOGS / REFERENCE sections, Templates + Examples links, "View running
queries" NEW); a tab bar (one tab "New" + Close X + "More actions" menu
+ "+" new-tab); a query bar ("Query source: Database" dropdown, Save
Ctrl S disabled when empty, green Run Ctrl Enter); a Monaco editor
(hint "Hit CTRL+SHIFT+K to generate query or just start typing");
Results / Chart tabs below (Results empty state "Click Run to execute
your query"; Chart empty state "No data to show / Execute a query and
configure the chart options").

The mapping onto this app's REAL cleaning run, honestly:

* The "query" is one cleaning run: the 8 fixes ticked in the editor.
  The editor lists them as numbered lines; the script preview under
  them is the run written out (only the ticked fixes) — Save stores
  exactly that as a recipe.
* Run = the existing "Clean my data" button (same label, same key,
  same icon) in the Run bar; it runs engine.clean on the loaded file,
  exactly as before.
* Save = stores the active tab's fixes as a recipe under the tab's
  name (disabled when nothing is ticked — the empty-query rule).
* Tabs = run tabs: one per cleaning run on the loaded file. "+" adds
  a run; each tab keeps its own fix set; switching tabs restores it.
* Results = the cleaned frame + "What was fixed" log (the existing
  render, moved into the Results tab); Chart = a real Before/After
  bar chart (Rows / Columns / Missing cells) of the run.
* Sub-sidebar: Recipes (saved recipes, click to apply), Templates
  (the three built-in templates, click to apply), Run history (the
  audit trail, newest first), Reference (Cleaning guide + Messy
  sample file). Search filters the three lists; Filter shows/hides
  sections; "+" adds a run tab.
* The rest of the page is unchanged: Undo, Backups, sampling, fuzzy
  matching, More fixes, Recipes & templates, Fix values, Bulk — they
  sit below the Results area, in the same order as before.

What is NOT built, and why (stated plainly, not faked):

* A Monaco editor: stock Streamlit has no code editor with line
  numbers, syntax highlighting or Ctrl+Enter to run. The editor is
  the numbered fix list + the script preview; Run is a button. The
  Ctrl S / Ctrl Enter kbd chips are deliberately NOT shown — the
  shortcuts do not exist in this app (the clone audit notes the app
  has no keyboard shortcuts; Quick Jump is the equivalent).
* "View running queries": cleaning runs synchronously; there is no
  running query to watch.
* A query-source dropdown with several sources: the app cleans the
  one loaded file. The bar shows the source as a caption, plus a
  real Row limit control for the Results grid.

Contract:
  - CLEAN_FIXES: the catalog — one dict per fix (key, label, desc,
    script).
  - script_lines(opts, source_name) -> [str] — pure: the run written
    out (header comment + one line per ticked fix).
  - chart_data(raw, clean, metric) -> {"labels", "values"} — pure:
    Before/After numbers for Rows, Columns or Missing cells.
  - default_tabs(source_name) / add_tab(tabs, n) /
    close_tab(tabs, key) / active_tab(tabs, active_key) — pure
    tab-list ops on plain dicts.
  - render_clean_page(st, ctx) -> (clean, filtered): the whole Clean
    tab. ctx carries raw/clean/source_name/uploaded/base_dir/
    storage_key/app_dir/run_label and the app-owned callbacks
    (apply_new_clean, audit, save_copy, set_raw, spinner, load_sample,
    persist_recipes). Renders with no data loaded (Run/Save disabled,
    Results empty state with a Try-the-sample CTA).
"""

from __future__ import annotations

import pandas as pd

import engine
import feat_analyse
import feat_automate
import feat_combine
import feat_enrich
import feat_quality
import feat_share
import ui_design

# --------------------------------------------------------------------------
# Catalog: the 8 fixes (the "query" this editor writes)
# --------------------------------------------------------------------------
# Labels are exactly the Clean tab's checkbox labels as they stood
# before this round — the tests find them by label.

CLEAN_FIXES = [
    {"key": "tidy_names",
     "label": "Tidy column names",
     "desc": "Rename columns to clean snake_case.",
     "script": "TIDY COLUMN NAMES"},
    {"key": "strip",
     "label": "Strip extra spaces from text",
     "desc": "Collapse extra spaces inside text and trim the edges.",
     "script": "STRIP EXTRA SPACES"},
    {"key": "drop_empty",
     "label": "Drop empty columns and rows",
     "desc": "Remove columns and rows that are entirely empty.",
     "script": "DROP EMPTY COLUMNS AND ROWS"},
    {"key": "fix_numbers",
     "label": "Fix numbers stored as text (₹, $, %, commas)",
     "desc": "Turn text like ₹1,200 and 45% into real numbers.",
     "script": "FIX NUMBERS STORED AS TEXT"},
    {"key": "parse_dates",
     "label": "Parse dates",
     "desc": "Recognise date text and store it as dates.",
     "script": "PARSE DATES"},
    {"key": "fix_categories",
     "label": "Set categories to one case",
     "desc": "One spelling per category value (Delhi, not DELHI).",
     "script": "SET CATEGORIES TO ONE CASE"},
    {"key": "drop_dupes",
     "label": "Drop duplicate rows",
     "desc": "Keep the first copy of each repeated row.",
     "script": "DROP DUPLICATE ROWS"},
    {"key": "fill_missing",
     "label": "Fill missing values",
     "desc": "Fill blanks with a sensible value per column.",
     "script": "FILL MISSING VALUES"},
]

ROW_LIMITS = [50, 100, 200, 500]
CHART_METRICS = ["Rows", "Columns", "Missing cells"]


# --------------------------------------------------------------------------
# Pure helpers (no Streamlit)
# --------------------------------------------------------------------------

def script_lines(opts, source_name):
    """The run written out as a script: a header comment naming the
    source file, then one line per ticked fix. Pure."""
    lines = [f"-- Clean {source_name or 'no file loaded'}"]
    ticked = [f for f in CLEAN_FIXES if opts.get(f["key"])]
    if not ticked:
        lines.append("-- (no fixes ticked — tick at least one fix to run.)")
    else:
        lines.extend(f["script"] for f in ticked)
    return lines


def chart_data(raw, clean, metric):
    """Before/After numbers for the Chart tab. Pure. metric is one of
    "Rows", "Columns", "Missing cells"."""
    if metric == "Columns":
        before, after = len(raw.columns), len(clean.columns)
    elif metric == "Missing cells":
        before = int(raw.isna().sum().sum())
        after = int(clean.isna().sum().sum())
    else:  # Rows
        before, after = len(raw), len(clean)
    return {"labels": ["Before", "After"], "values": [before, after]}


def default_tabs(source_name):
    """The first tab tracks the loaded file by name."""
    return [{"key": "tab-1", "name": source_name or "No file loaded",
             "opts": dict(feat_automate.DEFAULT_CLEAN_OPTS)}]


def add_tab(tabs, n):
    """Append a run tab numbered n ("Run 2", "Run 3", ...) with default
    fixes. Returns (tabs, new_key). Pure — the caller owns the
    counter, so keys stay unique across closes."""
    key = f"tab-{n}"
    tabs = list(tabs) + [{"key": key, "name": f"Run {n}",
                          "opts": dict(feat_automate.DEFAULT_CLEAN_OPTS)}]
    return tabs, key


def close_tab(tabs, key):
    """Remove the tab; the new active key is the first remaining tab's
    key, or None when none remain. Pure."""
    rest = [t for t in tabs if t["key"] != key]
    return rest, (rest[0]["key"] if rest else None)


def active_tab(tabs, active_key):
    """The active tab, falling back to the first tab when the key is
    unknown (a stale saved value cannot strand the page). Pure."""
    for t in tabs:
        if t["key"] == active_key:
            return t
    return tabs[0]


def _current_opts(st):
    """The ticked fixes right now, read from the editor's checkbox
    widget keys (the live values, whatever the tab dict holds)."""
    return {k: bool(st.session_state.get(f"clean_opt_{k}", True))
            for k in feat_automate.CLEAN_OPT_KEYS}


def _recipes(st):
    """The saved recipes in session state (mirrors
    feat_automate._saved_recipes, which is private to that module)."""
    recipes = st.session_state.get("a_recipes")
    if not isinstance(recipes, list):
        recipes = []
        st.session_state["a_recipes"] = recipes
    return recipes


# --------------------------------------------------------------------------
# Run tabs (session-state ops around the pure helpers)
# --------------------------------------------------------------------------

def _add_run_tab(st):
    """Append a run tab and make it active. The counter in session
    state keeps keys unique across closes."""
    session = st.session_state
    n = int(session.get("clean_tab_counter", 1)) + 1
    session["clean_tab_counter"] = n
    tabs, key = add_tab(session.get("clean_tabs") or [], n)
    session["clean_tabs"] = tabs
    session["clean_tab_active"] = key
    st.rerun()


def _duplicate_tab(st, tab):
    """Copy the active tab (same fixes, new key) and make the copy
    active."""
    session = st.session_state
    n = int(session.get("clean_tab_counter", 1)) + 1
    session["clean_tab_counter"] = n
    key = f"tab-{n}"
    session["clean_tabs"] = list(session["clean_tabs"]) + [
        {"key": key, "name": f"{tab['name']} copy",
         "opts": dict(tab["opts"])}]
    session["clean_tab_active"] = key
    st.rerun()


def _reset_tab(st, tab):
    """Reset the active tab's fixes to the defaults and re-sync the
    editor's checkbox keys, so the display follows at once."""
    tab["opts"] = dict(feat_automate.DEFAULT_CLEAN_OPTS)
    session = st.session_state
    for k in feat_automate.CLEAN_OPT_KEYS:
        session[f"clean_opt_{k}"] = True
    session["clean_tab_synced"] = tab["key"]
    st.rerun()


def _close_active_tab(st, tab):
    """Close the active tab; the first remaining tab becomes active."""
    session = st.session_state
    tabs, new_active = close_tab(session["clean_tabs"], tab["key"])
    session["clean_tabs"] = tabs
    session["clean_tab_active"] = new_active
    st.rerun()


def _save_tab_as_recipe(st, ctx, tab):
    """Save the tab's fixes as a recipe under the tab's name (replacing
    a recipe of the same name, like the Recipes section does). Only
    the fixes are saved — fuzzy merges live in the Recipes section.
    Returns the recipe name."""
    recipes = _recipes(st)
    recipe = feat_automate.save_recipe(tab["opts"], {}, tab["name"])
    recipes[:] = [r for r in recipes if r["name"] != recipe["name"]]
    recipes.append(recipe)
    ctx["persist_recipes"]()
    return recipe["name"]


# --------------------------------------------------------------------------
# Sub-sidebar
# --------------------------------------------------------------------------

def _apply_sidebar_recipe(st, ctx, recipe):
    """Apply a saved recipe to the loaded file, through the same
    apply path the Recipes section uses (it replaces the log)."""
    try:
        cleaned, actions = feat_automate.apply_recipe(ctx["raw"], recipe)
    except Exception as e:  # noqa: BLE001 - show, don't crash
        st.error(f"Could not apply recipe '{recipe['name']}': {e}")
        return
    ctx["apply_new_clean"](cleaned, actions, "Recipe applied",
                           replace_actions=True)
    st.session_state["clean_flash"] = (
        f"Applied recipe '{recipe['name']}': "
        f"{len(ctx['raw']):,} -> {len(cleaned):,} rows.")


def _apply_sidebar_template(st, ctx, name):
    """Apply a built-in template to the loaded file, through the same
    apply path the Templates section uses (it replaces the log)."""
    try:
        cleaned, actions = feat_automate.apply_template(ctx["raw"], name)
    except Exception as e:  # noqa: BLE001 - show, don't crash
        st.error(f"Could not apply template '{name}': {e}")
        return
    ctx["apply_new_clean"](cleaned, actions, "Template applied",
                           replace_actions=True)
    st.session_state["clean_flash"] = (
        f"Template '{name}' applied: "
        f"{len(ctx['raw']):,} -> {len(cleaned):,} rows.")


def _slug(name):
    """A widget-key-safe slug (the empty_state idiom)."""
    return "".join(ch if ch.isalnum() else "-"
                   for ch in str(name).lower())[:24] or "item"


def _render_sidebar_recipes(st, ctx, query):
    """Saved recipes, click to apply. The full management UI (save /
    download / load from file) lives in the Recipes & templates
    expander below; this is the quick-apply list."""
    recipes = _recipes(st)
    shown = [r for r in recipes
             if not query or query in r["name"].lower()]
    if not shown:
        if recipes:
            st.write("No recipes match that search.")
        else:
            st.write("No recipes saved yet — save a run as a recipe "
                     "and it will appear here.")
        return
    for recipe in shown:
        _name, _go = st.columns([3, 1])
        with _name:
            st.caption(recipe["name"])
        with _go:
            if ui_design.icon_button(
                    "", "play", key=f"clean_side_recipe_{_slug(recipe['name'])}",
                    help=f"Apply recipe '{recipe['name']}'.",
                    disabled=ctx["raw"] is None):
                _apply_sidebar_recipe(st, ctx, recipe)


def _render_sidebar_templates(st, ctx, query):
    """The three built-in templates, click to apply. Loading a
    template's messy sample stays in the Templates section below —
    the sidebar only applies to the loaded file."""
    for name, template in feat_automate.TEMPLATES.items():
        if query and query not in (
                name + " " + template["description"]).lower():
            continue
        st.caption(f"**{name.title()}** — {template['description']}")
        if ui_design.icon_button(
                "Apply", "play", key=f"clean_side_template_{name}",
                help=f"Apply the {name} template.",
                disabled=ctx["raw"] is None, use_container_width=True):
            _apply_sidebar_template(st, ctx, name)


def _render_sidebar_history(st, ctx, query):
    """Run history: the audit trail, newest first. The full trail
    (with download) also lives on the Report tab."""
    audit = st.session_state.get("q_audit") or []
    shown = [e for e in reversed(audit)
             if not query or query in (
                 str(e.get("step", "")) + " "
                 + str(e.get("detail", ""))).lower()]
    if not shown:
        st.write("No runs yet — your cleaning runs will be listed "
                 "here once you press Run.")
        return
    for entry in shown[:8]:
        st.caption(f"{entry.get('time', '')} — {entry.get('step', '')}: "
                   f"{entry.get('detail', '')}")
    if audit:
        csv = pd.DataFrame(audit).to_csv(index=False).encode("utf-8")
        st.download_button("Download audit log (CSV)", csv,
                           file_name="audit_log.csv", mime="text/csv",
                           key="clean_audit_download")


def _render_subnav(st, ctx):
    """The SQL Editor's sub-sidebar: Back to dashboard, search +
    Filter + "+" (new run tab), then the Recipes / Templates / Run
    history / Reference sections. Expanded states mirror the spec
    (SHARED/FAVORITES collapsed, PRIVATE/REFERENCE expanded)."""
    session = st.session_state
    if st.button("← Back to dashboard", key="clean_back_dashboard",
                 use_container_width=True):
        session["pending_tab"] = "dashboard"
        st.rerun()
    st.markdown('<div class="dcs-micro-label">Clean</div>',
                unsafe_allow_html=True)
    st.text_input("Search", key="clean_q",
                  placeholder="Search recipes, templates, runs...")
    _f, _plus = st.columns([1, 1])
    with _f:
        with st.popover("Filter"):
            st.checkbox("Recipes", value=True,
                        key="clean_show_recipes")
            st.checkbox("Templates", value=True,
                        key="clean_show_templates")
            st.checkbox("Run history", value=True,
                        key="clean_show_history")
    with _plus:
        if ui_design.icon_button("", "add", key="clean_new_tab",
                                 help="New run tab."):
            _add_run_tab(st)
    _q = (session.get("clean_q") or "").strip().lower()
    if session.get("clean_show_recipes", True):
        with st.expander("Recipes", expanded=False):
            _render_sidebar_recipes(st, ctx, _q)
    if session.get("clean_show_templates", True):
        with st.expander("Templates", expanded=False):
            _render_sidebar_templates(st, ctx, _q)
    if session.get("clean_show_history", True):
        with st.expander("Run history", expanded=True):
            _render_sidebar_history(st, ctx, _q)
    with st.expander("Reference", expanded=True):
        if ui_design.icon_button(
                "Cleaning guide", "book", key="clean_ref_guide",
                help="Open the How to use guide.",
                use_container_width=True):
            session["pending_tab"] = "tutorial"
            st.rerun()
        if ui_design.icon_button(
                "Messy sample file", "file", key="clean_ref_sample",
                help="Load the messy sales sample file.",
                use_container_width=True):
            ctx["load_sample"]()


# --------------------------------------------------------------------------
# Tab bar, Run bar, editor, results
# --------------------------------------------------------------------------

def _render_tab_bar(st, ctx):
    """The tab strip: one button per run tab (the active tab renders
    disabled, the Settings sub-nav idiom), "+" adds a run, "⋯" holds
    Duplicate / Reset / Close for the active tab."""
    session = st.session_state
    tabs = session["clean_tabs"]
    active = active_tab(tabs, session.get("clean_tab_active"))
    cols = st.columns([2] * len(tabs) + [0.6, 0.6])
    for col, tab in zip(cols, tabs):
        with col:
            if ui_design.icon_button(
                    tab["name"], "code", key=f"clean_tab_{tab['key']}",
                    disabled=(tab["key"] == active["key"]),
                    help=f"Switch to run '{tab['name']}'.",
                    use_container_width=True):
                session["clean_tab_active"] = tab["key"]
                st.rerun()
    with cols[len(tabs)]:
        if ui_design.icon_button("", "add", key="clean_tab_add",
                                 help="New run tab."):
            _add_run_tab(st)
    with cols[len(tabs) + 1]:
        with st.popover("⋯"):
            if st.button("Duplicate tab", key="clean_more_dupe"):
                _duplicate_tab(st, active)
            if st.button("Reset options", key="clean_more_reset"):
                _reset_tab(st, active)
            if st.button("Close this tab", key="clean_more_close",
                         disabled=len(tabs) <= 1):
                _close_active_tab(st, active)
    return active


def _render_run_bar(st, ctx):
    """The query bar: source caption, Row limit, Save, Run. Returns
    (run_clicked, row_limit). Save stores the active tab's fixes as a
    recipe under the tab's name; Run is the existing "Clean my data"
    button (same label, key and icon as before this round)."""
    session = st.session_state
    raw = ctx["raw"]
    tabs = session["clean_tabs"]
    active = active_tab(tabs, session.get("clean_tab_active"))
    opts = _current_opts(st)
    _src, _lim, _save, _run = st.columns([3, 1.2, 1, 1.4])
    with _src:
        if raw is None:
            st.caption("Source: no file loaded")
        else:
            st.caption(f"Source: {ctx['source_name']} · "
                       f"{len(raw):,} rows")
    with _lim:
        _now = session.get("clean_row_limit", 100)
        if _now not in ROW_LIMITS:
            _now = 100
        # persist_state="session": the selectbox unmounts whenever the
        # user leaves the Clean section, and Streamlit drops a widget's
        # value when it stops rendering (the default) — so without
        # this the limit fell back to 100 on every return (live-check
        # find, 2026-11-11; the Tools filters happen to survive their
        # detail return, this one did not). "session" keeps the value
        # for the whole session, so the limit returns when the user
        # navigates back; index= still derives the displayed value
        # from the saved limit each render.
        st.selectbox("Row limit", ROW_LIMITS, key="clean_row_limit",
                     index=ROW_LIMITS.index(_now),
                     persist_state="session",
                     help="How many rows the Results grid shows.")
    _row_limit = session.get("clean_row_limit", 100)
    with _save:
        _no_fix = not any(opts.values())
        if ui_design.icon_button(
                "Save", "save", key="clean_save",
                disabled=(raw is None or _no_fix),
                help="Save this run as a recipe named after the tab.",
                use_container_width=True):
            _name = _save_tab_as_recipe(st, ctx, active)
            session["clean_flash"] = (
                f"Saved recipe '{_name}' — find it under Recipes.")
            st.rerun()
    with _run:
        _clicked = ui_design.icon_button(
            ctx["run_label"], "clean", kind="primary", key="clean_btn",
            disabled=(raw is None),
            help="Clean the file with the ticked fixes.",
            use_container_width=True)
    return _clicked, _row_limit


def _run_clean(st, ctx):
    """Run the ticked fixes on the loaded file — the Clean button's
    work, exactly as it stood before this round. Returns
    (clean, filtered)."""
    session = st.session_state
    raw = ctx["raw"]
    opts = _current_opts(st)
    feat_automate.push_snapshot(session, "Before cleaning")
    _opts = feat_automate.to_engine_opts(opts)
    with ctx["spinner"]("Cleaning your data…"):
        uploaded = ctx.get("uploaded")
        if (len(raw) > 100_000 and uploaded is not None
                and uploaded.name.lower().endswith(".csv")):
            # Big file: clean in chunks (same result, less memory).
            cleaned, actions = engine.clean_csv_chunked(
                uploaded.getvalue(), _opts)
        else:
            cleaned, actions = engine.clean(raw, _opts)
    session.clean = cleaned
    session.actions = actions
    session.kpis = engine.auto_kpis(cleaned)
    session.clean_opts = opts
    ctx["audit"]("Clean", f"{len(raw):,} -> {len(cleaned):,} rows")
    ctx["save_copy"](cleaned, ctx["source_name"])
    return cleaned, cleaned


def _render_editor(st, ctx, active):
    """The Monaco stand-in: a bordered editor pane with the hint line,
    the 8 fixes as numbered lines, and the script preview — the run
    written out (only the ticked fixes)."""
    session = st.session_state
    with st.container(border=True):
        _hint, _help = st.columns([11, 1])
        with _hint:
            st.caption("Tick the fixes for this run, then press Run — "
                       "the script below is the run written out.")
        with _help:
            if ui_design.icon_button(
                    "", "help", key="clean_editor_help",
                    help="How cleaning works — open the guide."):
                session["pending_tab"] = "tutorial"
                st.rerun()
        for i, fix in enumerate(CLEAN_FIXES, start=1):
            _num, _box = st.columns([0.45, 11.55])
            with _num:
                st.caption(f"{i:02d}")
            with _box:
                st.checkbox(fix["label"],
                            value=active["opts"].get(fix["key"], True),
                            key=f"clean_opt_{fix['key']}",
                            help=fix["desc"])
        # Write the ticked fixes back into the active tab, so a tab
        # switch restores them.
        for fix in CLEAN_FIXES:
            active["opts"][fix["key"]] = bool(
                session.get(f"clean_opt_{fix['key']}", True))
        st.code("\n".join(script_lines(_current_opts(st),
                                        ctx["source_name"])),
                language="sql")


def _render_results(st, ctx, clean, raw, row_limit):
    """Results / Chart tabs under the editor (Supabase's results
    area). Results holds the existing success line, "What was fixed"
    log and grid; Chart holds a real Before/After bar chart."""
    _tab_res, _tab_chart = st.tabs(["Results", "Chart"])
    with _tab_res:
        if raw is None:
            if ui_design.empty_state(
                    "No data loaded yet",
                    "Upload a file from the sidebar, or try the sample — "
                    "then press Run.",
                    cta_label="Try the sample data", cta_icon="play"):
                ctx["load_sample"]()
        elif clean is None:
            ui_design.empty_state(
                "Nothing cleaned yet",
                "Tick the fixes above, then press Clean my data.")
        else:
            st.success(f"Done: {len(raw):,} rows -> {len(clean):,} rows, "
                       f"{len(raw.columns)} -> {len(clean.columns)} columns.")
            ui_design.section_heading("What was fixed")
            for step, detail in st.session_state.actions:
                st.write(f"- **{step}:** {detail}")
            st.dataframe(clean.head(row_limit), width="stretch")
            st.caption(f"Showing first {min(row_limit, len(clean)):,} of "
                       f"{len(clean):,} rows · {len(clean.columns)} columns")
    with _tab_chart:
        if raw is None or clean is None:
            ui_design.empty_state(
                "No data to show",
                "Run a clean and configure the chart options.")
        else:
            _now = st.session_state.get("clean_chart_metric", "Rows")
            if _now not in CHART_METRICS:
                _now = "Rows"
            _metric = st.selectbox(
                "Chart", CHART_METRICS, key="clean_chart_metric",
                index=CHART_METRICS.index(_now),
                help="What the Before/After bars compare.")
            _data = chart_data(raw, clean, _metric)
            st.bar_chart(pd.DataFrame({"Count": _data["values"]},
                                      index=_data["labels"]))
            st.caption(f"{_metric}: {_data['values'][0]:,} → "
                       f"{_data['values'][1]:,} after cleaning.")


# --------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------

def render_clean_page(st, ctx):
    """The whole Clean tab as Supabase's SQL Editor. Returns
    (clean, filtered) for the caller (app.py) to keep its locals in
    step — every section below writes session state first, exactly as
    the old inline Clean block did.

    Renders with no data loaded: the editor lists the fixes, Run/Save
    are disabled, and the Results tab names the next step (with a
    Try-the-sample CTA). The tab-1 name always tracks the loaded
    file; the checkbox widget keys are synced from the active tab
    whenever the tab changes (checkboxes follow session state; the
    Settings key-bump lesson was about text inputs, and the probe
    pins the switch in the real DOM)."""
    session = st.session_state
    raw = ctx["raw"]
    clean = ctx["clean"]
    filtered = clean
    source_name = ctx["source_name"]

    # Tabs live in session state; tab-1 always tracks the loaded file.
    tabs = session.get("clean_tabs")
    if not tabs:
        tabs = default_tabs(source_name)
        session["clean_tabs"] = tabs
        session["clean_tab_counter"] = 1
    if tabs and tabs[0]["key"] == "tab-1":
        tabs[0]["name"] = source_name or "No file loaded"
    active = active_tab(tabs, session.get("clean_tab_active"))
    if session.get("clean_tab_synced") != active["key"]:
        for k in feat_automate.CLEAN_OPT_KEYS:
            session[f"clean_opt_{k}"] = active["opts"].get(k, True)
        session["clean_tab_synced"] = active["key"]

    _nav, _main = st.columns([1, 4])
    with _nav:
        _render_subnav(st, ctx)
    # The subnav may have applied a recipe/template (session state
    # changed under us) — re-read before the main column.
    clean = session.get("clean")
    raw = session.get("raw")
    filtered = clean
    with _main:
        _flash = session.pop("clean_flash", None)
        if _flash:
            st.success(_flash)
        feat_automate.render_undo(st)
        restored = feat_share.render_backups(
            st, df=raw, source_name=source_name,
            base_dir=ctx["base_dir"], storage_key=ctx["storage_key"],
            key_prefix="s_backup_clean")
        if restored is not None:
            ctx["set_raw"](restored,
                           source_name + " (restored from backup)")
            raw = restored
            clean = None
            filtered = None
            source_name = session.get("source_name")
            ctx["raw"] = raw
            ctx["source_name"] = source_name
        ui_design.section_heading(
            "Clean my data",
            sub="Tick what to fix, then press the button. Every fix is listed "
                "in the log below, so you can check the work.")
        _render_tab_bar(st, ctx)
        _run, _row_limit = _render_run_bar(st, ctx)
        if _run:
            clean, filtered = _run_clean(st, ctx)
        _render_editor(st, ctx, active)
        if raw is not None:
            _samp = feat_enrich.render_sampling(
                st, raw,
                clean_opts=feat_automate.to_engine_opts(_current_opts(st)))
            if _samp is not None:
                _full_clean, _full_actions = engine.clean(
                    raw, _samp["clean_opts"])
                feat_automate.push_snapshot(
                    session, "Before sampling apply")
                session.clean = _full_clean
                session.actions = _full_actions
                session.kpis = engine.auto_kpis(_full_clean)
                ctx["audit"]("Sampling applied to full file",
                             f"{len(raw):,} rows")
                ctx["save_copy"](_full_clean, source_name)
                clean = _full_clean
                filtered = _full_clean
        _render_results(st, ctx, clean, raw, _row_limit)
        if clean is not None:
            ui_design.section_heading(
                "Fix similar names (fuzzy matching)",
                sub="Finds misspellings like Aarav / Arav and Delhi / Dehli "
                    "and merges them into one spelling. You review the groups "
                    "first — nothing merges without your word.")
            text_cols = [c for c in clean.columns
                         if str(clean[c].dtype) in ("object", "str")
                         and 1 < clean[c].nunique() <= 500]
            if text_cols:
                fcol = st.selectbox("Column", text_cols, key="fuzzy_col")
                fthr = st.slider("How similar must names be? (higher = stricter)",
                                 0.70, 0.95, 0.85, 0.01, key="fuzzy_thr")
                if st.button("Find similar names", key="fuzzy_find"):
                    session["fuzzy_groups"] = engine.fuzzy_groups(
                        clean[fcol], fthr)
                    session["fuzzy_col_used"] = fcol
                groups = session.get("fuzzy_groups")
                if groups is not None:
                    if len(groups) == 0:
                        st.info("No similar names found in that column.")
                    else:
                        for g in groups:
                            members = ", ".join(f"{v} ({n:,})"
                                                for v, n in g["members"])
                            st.write(f"→ **{g['canonical']}**: {members}")
                        if st.button("Merge these names",
                                     key="fuzzy_apply"):
                            mapping = {}
                            for g in groups:
                                for v, _ in g["members"][1:]:
                                    mapping[v] = g["canonical"]
                            feat_automate.push_snapshot(
                                session, "Before fuzzy merge")
                            new_clean = engine.apply_fuzzy(
                                clean, session["fuzzy_col_used"], mapping)
                            session["clean"] = new_clean
                            session["actions"] = (
                                session["actions"]
                                + [(f"Fuzzy merge: {session['fuzzy_col_used']}",
                                  f"{len(mapping)} spelling(s) merged")])
                            session["kpis"] = engine.auto_kpis(new_clean)
                            session["fuzzy_groups"] = None
                            ctx["audit"]("Fuzzy merge",
                                         f"{len(mapping)} spelling(s) merged")
                            clean = new_clean
                            filtered = new_clean
                            st.success(f"Merged {len(mapping)} spelling(s) into "
                                       "their main form.")
            else:
                st.info("No text column with a manageable number of values "
                        "in this file.")

            with st.expander("More fixes (column type, phones, special characters)"):
                _ov = feat_share.render_type_override(st, clean)
                if _ov is not None:
                    _ov_col = session.get("s_type_col", "?")
                    _ov_kind = session.get("s_type_kind", "?")
                    clean = ctx["apply_new_clean"](
                        _ov, [("Column type override",
                               f"{_ov_col} forced to {_ov_kind}")],
                        "Column type override")
                    filtered = clean
                _nd, _na = feat_share.render_standardize_phones(st, clean)
                if _nd is not None:
                    clean = ctx["apply_new_clean"](
                        _nd, _na, "Standardize phones")
                    filtered = clean
                _nd, _na = feat_share.render_strip_specials(st, clean)
                if _nd is not None:
                    clean = ctx["apply_new_clean"](
                        _nd, _na, "Strip special characters")
                    filtered = clean

            with st.expander("Recipes & templates"):
                new_df, new_actions = feat_automate.render_recipes(st, raw)
                if new_df is not None:
                    clean = ctx["apply_new_clean"](
                        new_df, new_actions, "Recipe applied",
                        replace_actions=True)
                    filtered = clean
                new_df, new_actions = feat_automate.render_templates(st)
                if new_df is not None:
                    clean = ctx["apply_new_clean"](
                        new_df, new_actions, "Template applied",
                        replace_actions=True)
                    filtered = clean
                _recipes = session.get("a_recipes") or []
                _picked_name = session.get("a_recipe_select")
                _recipe = (next((r for r in _recipes
                                 if r["name"] == _picked_name),
                                None) if _picked_name else None)
                _imported = feat_analyse.render_share_recipe(st, _recipe)
                if _imported is not None:
                    _recipes[:] = [r for r in _recipes
                                   if r["name"] != _imported["name"]]
                    _recipes.append(_imported)
                # Persist recipes per user (recipes/recipes.json).
                ctx["persist_recipes"]()

            with st.expander("Fix values"):
                new_df, new_actions = feat_automate.render_find_replace(st, clean)
                if new_df is not None:
                    clean = ctx["apply_new_clean"](
                        new_df, new_actions, "Find and replace")
                    filtered = clean
                new_df, new_actions = feat_combine.render_calculated(st, clean)
                if new_df is not None:
                    clean = ctx["apply_new_clean"](
                        new_df, new_actions, "Calculated column")
                    filtered = clean
                new_df, new_actions = feat_quality.render_outliers(st, clean)
                if new_df is not None:
                    clean = ctx["apply_new_clean"](
                        new_df, new_actions, "Outliers")
                    filtered = clean
                new_df, new_actions = feat_quality.render_near_dupes(st, clean)
                if new_df is not None:
                    clean = ctx["apply_new_clean"](
                        new_df, new_actions, "Near-duplicates merged")
                    filtered = clean
                feat_quality.render_validation(st, clean)
                _nd, _na = feat_enrich.render_split_merge(st, clean)
                if _nd is not None:
                    clean = ctx["apply_new_clean"](
                        _nd, _na, "Split / merge columns")
                    filtered = clean
                _nd, _na = feat_enrich.render_date_intelligence(st, clean)
                if _nd is not None:
                    clean = ctx["apply_new_clean"](
                        _nd, _na, "Date intelligence")
                    filtered = clean
                _nd, _na = feat_enrich.render_currency(st, clean)
                if _nd is not None:
                    clean = ctx["apply_new_clean"](
                        _nd, _na, "Currency conversion")
                    filtered = clean
                feat_enrich.render_masking(st, clean)

            with st.expander("Clean many files at once"):
                feat_automate.render_bulk(st)
    return clean, filtered
