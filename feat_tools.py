"""Tools tab as Supabase's Integrations page, mapped to this app's own
tools (the mapping the clone spec confirms: Tools -> Integrations —
search + filter dropdowns + 3-col card grid with badges).

Supabase's Integrations page, from the audit (spec Pass B2): a left
sub-nav (INSTALLED list + RESOURCES links), a search box, Category /
Type / Source dropdowns, a grid/list view toggle, a Featured row of
three wide cards, and a 3-column grid of cards (logo, name, one-line
description, badges; the whole card is a link; hover darkens the
border). A card opens a detail page: breadcrumb "Integrations >
<Name>", badges, a primary CTA, and a right rail with TYPE / BUILT BY
/ STATUS / LINKS.

The mapping onto this app's REAL tools, honestly:

* Watch folder — the script that cleans files dropped in a folder.
* Morning auto-clean — the Windows scheduled task (feat_schedule).
* Keyboard shortcuts — the two browser shortcuts (feat_analyse).
* Backups — raw-data safety copies (feat_share).
* Live databases — MySQL / PostgreSQL / SQL Server (feat_export +
  feat_db). The drivers are NOT installed in the cloud build, and
  the card says so plainly — no connection is faked. The form still
  takes the details, and Test connection reports the missing driver
  instead of pretending.
* Google Sheets — writing back to a Sheet needs the user's Google
  credentials and the Sheets API client, neither of which is
  connected in this build (feat_export says so); the card is marked
  NEEDS SETUP and the detail keeps the credential check.
* Scheduled email report — the SMTP daily report (feat_export).
* Supabase (cloud backend) — the app's own accounts / storage /
  backups backend, Cloud or Local (auth).

What is NOT built, and why (stated plainly, not faked):

* A whole card as one link: stock Streamlit cannot make a bordered
  container clickable — the honest equivalent is the Open button on
  each card, the same state-button idiom the Settings sub-nav uses.
* Hover darkening the card border: Streamlit renders the card; there
  is no per-card hover hook in stock Streamlit.
* Detail-page tabs (Overview / Settings / Docs): each tool has exactly
  one real view — its existing section — so a tab bar would be
  decoration with nothing behind it. The detail shows the breadcrumb,
  badges, the section itself, and the TYPE / BUILT BY / STATUS rail.
* Live database connections in the cloud build: the drivers ship as
  wheels in the portable .exe build only. The card status counts the
  drivers that actually import in THIS Python.

Contract:
  - TOOLS: the catalog — one dict per tool (key, name, desc,
    category, type, source, icon, svg, featured, built_by).
  - filter_tools(tools, query, category, type_, source) -> [tool]
    — pure: substring match on name + description (case-insensitive)
    plus the three dropdown filters; "All" passes everything.
  - tool_status(tool, session_state=None, base_dir=None,
    storage_key=None) -> {"installed": bool, "badge": (text, kind),
    "status": str} — live status, no side effects.
  - render_tools_page(st, base_dir=None, storage_key=None,
    app_dir=None, raw=None, clean=None, kpis=None, actions=None)
    -> (df, name, kind) when a backup restore or a database load
    hands the app a frame, else (None, None, None).

Widget keys all start with "tools_"; detail state lives in
session_state["tools_detail"] (a tool key, or None) and the view in
the "tools_view" selectbox ("Grid" / "List").
"""

from __future__ import annotations

from pathlib import Path

import auth
import feat_analyse
import feat_db
import feat_export
import feat_schedule
import feat_share
import ui_design

# --------------------------------------------------------------------------
# Catalog
# --------------------------------------------------------------------------

TOOLS = [
    {
        "key": "watch-folder",
        "name": "Watch folder",
        "desc": ("Drop a messy file into a folder and the cleaned "
                 "version appears in the output folder by itself."),
        "category": "Automation",
        "type": "Automation",
        "source": "Built-in",
        "icon": "folder",
        "svg": "file",
        "featured": True,
        "built_by": "Built-in",
    },
    {
        "key": "morning-clean",
        "name": "Morning auto-clean",
        "desc": ("The cleaning done before you sit down — a daily run "
                 "on your Windows PC, even when the app is closed."),
        "category": "Automation",
        "type": "Automation",
        "source": "Windows",
        "icon": "clock",
        "svg": "clock",
        "featured": True,
        "built_by": "Windows Task Scheduler",
    },
    {
        "key": "shortcuts",
        "name": "Keyboard shortcuts",
        "desc": ("Two browser shortcuts that work while the app is "
                 "open in your browser tab."),
        "category": "Productivity",
        "type": "Utility",
        "source": "Browser",
        "icon": "bolt",
        "svg": "grid",
        "featured": False,
        "built_by": "Built-in",
    },
    {
        "key": "backups",
        "name": "Backups",
        "desc": ("A safety copy of your raw data, saved before "
                 "cleaning — restore it any time from the list."),
        "category": "Storage",
        "type": "Utility",
        "source": "Built-in",
        "icon": "history",
        "svg": "database",
        "featured": False,
        "built_by": "Built-in",
    },
    {
        "key": "live-db",
        "name": "Live databases",
        "desc": ("Pull data straight from MySQL, PostgreSQL, or "
                 "SQL Server."),
        "category": "Data sources",
        "type": "Connection",
        "source": "Database",
        "icon": "database",
        "svg": "database",
        "featured": True,
        "built_by": "MySQL / PostgreSQL / SQL Server",
    },
    {
        "key": "sheets",
        "name": "Google Sheets",
        "desc": ("Write the cleaned data back to a Google Sheet."),
        "category": "Data sources",
        "type": "Connection",
        "source": "Google",
        "icon": "table",
        "svg": "table",
        "featured": False,
        "built_by": "Google",
    },
    {
        "key": "email-report",
        "name": "Scheduled email report",
        "desc": ("Email the PDF report to yourself every day, from "
                 "your own email account (SMTP)."),
        "category": "Exports",
        "type": "Automation",
        "source": "SMTP",
        "icon": "doc",
        "svg": "file",
        "featured": False,
        "built_by": "Built-in",
    },
    {
        "key": "supabase",
        "name": "Supabase (cloud backend)",
        "desc": ("Accounts, file storage, and backups live in your "
                 "Supabase project — or in local files in local mode."),
        "category": "Storage",
        "type": "Connection",
        "source": "Supabase",
        "icon": "storage",
        "svg": "database",
        "featured": False,
        "built_by": "Supabase",
    },
]

_TOOL_BY_KEY = {t["key"]: t for t in TOOLS}


def categories() -> list:
    """Category dropdown options: "All" first, then the catalog's."""
    seen = []
    for tool in TOOLS:
        if tool["category"] not in seen:
            seen.append(tool["category"])
    return ["All"] + seen


def types() -> list:
    """Type dropdown options: "All" first, then the catalog's."""
    seen = []
    for tool in TOOLS:
        if tool["type"] not in seen:
            seen.append(tool["type"])
    return ["All"] + seen


def sources() -> list:
    """Source dropdown options: "All" first, then the catalog's."""
    seen = []
    for tool in TOOLS:
        if tool["source"] not in seen:
            seen.append(tool["source"])
    return ["All"] + seen


# --------------------------------------------------------------------------
# Filtering (pure — no Streamlit)
# --------------------------------------------------------------------------

def filter_tools(tools, query="", category="All", type_="All",
                 source="All") -> list:
    """The tools matching every filter, in catalog order.

    The query is a case-insensitive substring match on name +
    description; an empty query matches everything. "All" passes
    its dropdown. Unknown dropdown values match nothing (a stale
    saved value cannot silently show the whole grid).
    """
    query = (query or "").strip().lower()
    out = []
    for tool in tools:
        if query and query not in (
                tool["name"] + " " + tool["desc"]).lower():
            continue
        if category != "All" and tool["category"] != category:
            continue
        if type_ != "All" and tool["type"] != type_:
            continue
        if source != "All" and tool["source"] != source:
            continue
        out.append(tool)
    return out


# --------------------------------------------------------------------------
# Live status (no side effects — reads only)
# --------------------------------------------------------------------------

def tool_status(tool, session_state=None, base_dir=None,
                storage_key=None) -> dict:
    """{"installed": bool, "badge": (text, kind), "status": str}.

    "installed" means the tool is ready to use right now, in THIS
    build, on THIS computer. The badge is the Supabase-style chip
    the card shows; the status line is the plain sentence under it.
    """
    key = tool["key"]
    if key == "watch-folder":
        return {"installed": True, "badge": ("BUILT-IN", "mint"),
                "status": "Available — the script ships with the app."}
    if key == "morning-clean":
        exists, _detail = feat_schedule.task_status()
        if exists:
            return {"installed": True, "badge": ("INSTALLED", "green"),
                    "status": "Set up — runs every morning on your "
                            "Windows PC."}
        return {"installed": False, "badge": ("NOT INSTALLED", "grey"),
                "status": "Not set up — needs your Windows PC."}
    if key == "shortcuts":
        return {"installed": True, "badge": ("BUILT-IN", "mint"),
                "status": "Available — two browser shortcuts, while "
                        "the app is open."}
    if key == "backups":
        count = len(feat_share.list_backups(base_dir, storage_key))
        return {"installed": True, "badge": ("BUILT-IN", "mint"),
                "status": (f"{count} backup(s) saved." if count else
                           "No backups yet — back up before cleaning.")}
    if key == "live-db":
        drivers = feat_db.db_driver_status()
        have = sum(1 for v in drivers.values() if v)
        if have == 3:
            return {"installed": True, "badge": ("INSTALLED", "green"),
                    "status": "3 of 3 drivers installed in this build."}
        if have:
            return {"installed": True, "badge": ("PARTIAL", "amber"),
                    "status": (f"{have} of 3 drivers installed in this "
                               "build — the others report as missing "
                               "below.")}
        return {"installed": False, "badge": ("NOT INSTALLED", "grey"),
                "status": ("No drivers installed in this build — the "
                           "form still takes your details, but Test "
                           "connection will say so.")}
    if key == "sheets":
        return {"installed": False, "badge": ("NEEDS SETUP", "amber"),
                "status": ("Needs your Google credentials and the "
                           "Sheets API client — neither is connected.")}
    if key == "email-report":
        sched = (session_state or {}).get(feat_export.EMAIL_SCHED_KEY)
        if sched and sched.get("enabled"):
            return {"installed": True, "badge": ("INSTALLED", "green"),
                    "status": (f"Scheduled — daily at {sched.get('time')} "
                               f"to {sched.get('recipient')}")}
        return {"installed": False, "badge": ("NEEDS SETUP", "amber"),
                "status": "Not scheduled — fill in your SMTP details."}
    if key == "supabase":
        backend = auth.get_auth_backend()
        if backend == "local":
            return {"installed": False, "badge": ("LOCAL", "grey"),
                    "status": "Local (this server) — no cloud project "
                            "connected."}
        return {"installed": True, "badge": ("INSTALLED", "green"),
                "status": "Cloud (Supabase) — accounts and files live "
                        "in your project."}
    return {"installed": False, "badge": ("UNKNOWN", "grey"),
            "status": "Unknown tool."}


# --------------------------------------------------------------------------
# Detail sections (the existing real sections, unchanged)
# --------------------------------------------------------------------------

def _render_watch_folder(st, app_dir) -> None:
    """The watch-folder block, as it stood on the Tools tab: the
    download, the command, and the plain note about the recipe."""
    ui_design.section_heading(
        "Watch folder (automatic cleaning)",
        sub="The app cleans files while it is open. For hands-free "
            "cleaning, run this small script: drop a messy file into a "
            "folder and the cleaned version appears in the output folder "
            "by itself.")
    watch_path = Path(app_dir) / "watch_folder.py"
    if watch_path.exists():
        st.download_button("Download watch_folder.py",
                           watch_path.read_bytes(),
                           file_name="watch_folder.py",
                           key="tools_watch_dl")
    st.code("python watch_folder.py --watch incoming --out cleaned "
            "--recipe my_recipe.json", language="bash")
    st.write("Save a recipe from the Clean tab first, then point the "
             "script at it. It also works with `--once` to clean the files "
             "already waiting in the folder and stop.")


def _render_supabase_detail(st) -> None:
    """The cloud-backend detail: the backend label, the verbatim
    warning when there is one, and the way to the full Status tab.
    The Status tab holds the full picture; this is the summary."""
    backend = auth.get_auth_backend()
    label = ("Local (this server)" if backend == "local"
             else "Cloud (Supabase)")
    st.write(f"Account backend: **{label}**.")
    warn = auth.get_backend_warning()
    if warn:
        st.warning(warn)
    if backend == "local":
        st.info("Local mode — accounts live in a file on this server, "
                "and your files live in your folder on this server. "
                "Cloud accounts (including Google sign-in) need a "
                "Supabase project: create the free project, add its URL "
                "and anon key to the app's secrets, and run the setup "
                "SQL in the Supabase SQL editor.")
    else:
        st.success("Cloud accounts are active (Supabase). Sign in with "
                   "your email and password, or with Google if it is "
                   "enabled in the Supabase dashboard.")
    if ui_design.icon_button("Open Status", "status",
                             key="tools_open_status",
                             help="Open the Status tab."):
        st.session_state["pending_tab"] = "status"
        st.rerun()


def _render_detail_body(st, tool, ctx):
    """The tool's own section, in the detail's main column. Returns
    (df, name, kind) when a backup restore or a database load hands
    the app a frame, else (None, None, None) — the caller (app.py)
    loads it with _set_raw exactly as the old Tools tab did."""
    key = tool["key"]
    if key == "watch-folder":
        _render_watch_folder(st, ctx["app_dir"])
    elif key == "morning-clean":
        feat_schedule.render_schedule_section(st)
        feat_analyse.render_morning_run(st)
    elif key == "shortcuts":
        feat_analyse.render_shortcuts_panel(st)
    elif key == "backups":
        restored = feat_share.render_backups(
            st, base_dir=ctx["base_dir"], storage_key=ctx["storage_key"],
            key_prefix="s_backup_tools")
        if restored is not None:
            return (restored,
                    (st.session_state.get("source_name") or "data")
                    + " (restored from backup)", "upload")
    elif key == "live-db":
        ui_design.section_heading("Live database connections")
        df, name = feat_export.render_db_connect(st)
        if df is not None:
            return df, name, "database"
    elif key == "sheets":
        feat_export.render_sheets_export(st, ctx["clean"])
    elif key == "email-report":
        feat_export.render_email_schedule(
            st, ctx["kpis"], ctx["actions"], ctx["raw"], ctx["clean"])
    elif key == "supabase":
        _render_supabase_detail(st)
    return None, None, None


def _render_rail(st, tool, status) -> None:
    """The detail's right rail: TYPE / BUILT BY / STATUS, and LINKS
    only where a real link exists (Google Sheets: the Cloud console
    page the credential help already names)."""
    st.markdown('<div class="dcs-micro-label">Type</div>',
                unsafe_allow_html=True)
    st.write(tool["type"])
    st.markdown('<div class="dcs-micro-label">Built by</div>',
                unsafe_allow_html=True)
    st.write(tool["built_by"])
    st.markdown('<div class="dcs-micro-label">Status</div>',
                unsafe_allow_html=True)
    st.write(status["status"])
    if tool["key"] == "sheets":
        st.markdown('<div class="dcs-micro-label">Links</div>',
                    unsafe_allow_html=True)
        st.markdown("[Google Cloud console — service-account keys]"
                    "(https://console.cloud.google.com/apis/credentials)",
                    unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Cards
# --------------------------------------------------------------------------

def _badges_html(tool, status) -> str:
    """The card's badge row: the live status badge, plus a BUILT-IN
    chip for built-ins — but never the same chip twice. A built-in
    tool's status badge already reads BUILT-IN, so adding the source
    chip too rendered "BUILT-IN BUILT-IN" (live-check find)."""
    text, kind = status["badge"]
    parts = []
    if tool["source"] == "Built-in" and text != "BUILT-IN":
        parts.append(ui_design.pill("BUILT-IN", "mint"))
    parts.append(ui_design.pill(text, kind))
    return " ".join(parts)


def _render_card(st, tool, status, key_suffix="") -> None:
    """One grid card: 34px icon (Supabase's logo slot), name +
    badges, one-line description, live status line, Open button.
    The whole card cannot be one link in stock Streamlit — the Open
    button is the honest equivalent. ``key_suffix`` keeps the
    Featured row's copies from colliding with the grid's keys."""
    with st.container(border=True):
        st.markdown(
            f'{ui_design.svg_icon(tool["svg"], size=34)} '
            f'**{tool["name"]}**  {_badges_html(tool, status)}',
            unsafe_allow_html=True)
        st.write(tool["desc"])
        st.caption(status["status"])
        if ui_design.icon_button("Open", tool["icon"],
                                 key=f"tools_open_{tool['key']}{key_suffix}",
                                 help=f"Open {tool['name']}.",
                                 use_container_width=True):
            st.session_state["tools_detail"] = tool["key"]
            st.rerun()


def _index_of(value, options) -> int:
    """The selectbox index for a saved filter value: its position in
    the options, or 0 ("All" / "Grid") when the value is missing or
    stale. The caller passes this as index= so the dropdown's
    displayed value always follows the saved filter."""
    return options.index(value) if value in options else 0


def _render_featured(st, tools, statuses) -> None:
    """The Featured row: the three featured tools as wide cards, the
    same tools the grid below lists (Supabase does the same). The
    "Featured" label is the row's heading — without it the row reads
    as three unexplained cards (live-check find)."""
    featured = [t for t in tools if t["featured"]]
    if not featured:
        return
    st.markdown('<div class="dcs-micro-label">Featured</div>',
                unsafe_allow_html=True)
    cols = st.columns(len(featured))
    for col, tool in zip(cols, featured):
        with col:
            _render_card(st, tool, statuses[tool["key"]],
                         key_suffix="_featured")


def _render_list_row(st, tool, status) -> None:
    """One list-view row: name + description + badges left, status
    and Open right."""
    with st.container(border=True):
        _left, _right = st.columns([3, 1])
        with _left:
            st.markdown(
                f'**{tool["name"]}**  {_badges_html(tool, status)}',
                unsafe_allow_html=True)
            st.write(tool["desc"])
            st.caption(status["status"])
        with _right:
            if ui_design.icon_button("Open", tool["icon"],
                                     key=f"tools_open_{tool['key']}",
                                     help=f"Open {tool['name']}.",
                                     use_container_width=True):
                st.session_state["tools_detail"] = tool["key"]
                st.rerun()


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------

def render_tools_page(st, base_dir=None, storage_key=None, app_dir=None,
                      raw=None, clean=None, kpis=None, actions=None):
    """The Tools tab as Supabase's Integrations page.

    Left sub-nav (Back to dashboard / Installed / Browse-by-category)
    + main column: H1 + search + Category/Type/Source dropdowns +
    grid/list toggle + Featured row + 3-col card grid (or list view).
    A card's Open button (or an Installed sub-nav row) opens the
    detail: breadcrumb, badges, the tool's own section, and the
    TYPE / BUILT BY / STATUS rail. Returns (df, name, kind) when a
    backup restore or a database load hands the app a frame, else
    (None, None, None). Renders with no data loaded — the Tools tab
    needs no file, same as Settings and KPIs.
    """
    if app_dir is None:
        app_dir = Path(__file__).resolve().parent
    ctx = {"base_dir": base_dir, "storage_key": storage_key,
           "app_dir": app_dir, "raw": raw, "clean": clean,
           "kpis": kpis, "actions": actions}
    session = st.session_state
    detail_key = session.get("tools_detail")
    detail = _TOOL_BY_KEY.get(detail_key) if detail_key else None
    statuses = {t["key"]: tool_status(
        t, session_state=session, base_dir=base_dir,
        storage_key=storage_key) for t in TOOLS}

    _set_nav, _set_main = st.columns([1, 4])
    with _set_nav:
        if st.button("← Back to dashboard",
                     key="tools_back_dashboard",
                     use_container_width=True):
            session["pending_tab"] = "dashboard"
            st.rerun()
        st.markdown('<div class="dcs-micro-label">Tools</div>',
                    unsafe_allow_html=True)
        if st.button("All tools", key="tools_nav_all",
                     disabled=(detail is None
                               and session.get("tools_cat", "All") == "All"
                               and session.get("tools_type", "All") == "All"
                               and session.get("tools_source",
                                               "All") == "All"
                               and not (session.get("tools_q") or "")),
                     use_container_width=True):
            session["tools_detail"] = None
            session["tools_q"] = ""
            session["tools_cat"] = "All"
            session["tools_type"] = "All"
            session["tools_source"] = "All"
            st.rerun()
        st.markdown('<div class="dcs-micro-label">Installed</div>',
                    unsafe_allow_html=True)
        for tool in TOOLS:
            if not statuses[tool["key"]]["installed"]:
                continue
            if st.button(tool["name"],
                         key=f"tools_nav_installed_{tool['key']}",
                         disabled=(detail is not None
                                   and detail["key"] == tool["key"]),
                         use_container_width=True):
                session["tools_detail"] = tool["key"]
                st.rerun()
        st.markdown('<div class="dcs-micro-label">Browse</div>',
                    unsafe_allow_html=True)
        for cat in categories()[1:]:
            if st.button(cat, key=f"tools_nav_cat_{cat}",
                         disabled=(detail is None
                                   and session.get("tools_cat",
                                                   "All") == cat),
                         use_container_width=True):
                session["tools_detail"] = None
                session["tools_cat"] = cat
                st.rerun()

    with _set_main:
        if detail is not None:
            status = statuses[detail["key"]]
            if st.button("← All tools", key="tools_back_all"):
                session["tools_detail"] = None
                st.rerun()
            st.markdown(
                f'<div class="dcs-micro-label">Tools &gt; '
                f'{detail["name"]}</div>',
                unsafe_allow_html=True)
            ui_design.section_heading(
                detail["name"],
                sub=detail["desc"])
            st.markdown(_badges_html(detail, status),
                        unsafe_allow_html=True)
            _main, _rail = st.columns([3, 1])
            with _main:
                _result = _render_detail_body(st, detail, ctx)
            with _rail:
                _render_rail(st, detail, status)
            return _result

        ui_design.section_heading(
            "Tools",
            sub="Automations, connections, and exports — everything "
                "the app plugs into.")
        _q = st.text_input("Search tools", key="tools_q",
                           placeholder="Search tools")
        _fc, _ft, _fs, _fv = st.columns([2, 2, 2, 1])
        with _fc:
            # index= is the single source of truth for the dropdown's
            # DISPLAYED value: a selectbox that was absent for a run
            # (the detail page renders no filters) remounts from its
            # proto default, so the index must be derived from the
            # saved filter every render — otherwise the dropdown shows
            # "All" while the grid still filters by the saved value
            # (live-check find). Same for Type, Source, View.
            _cat_opts = categories()
            _cat = st.selectbox(
                "Category", _cat_opts, key="tools_cat",
                index=_index_of(session.get("tools_cat"), _cat_opts))
        with _ft:
            _typ_opts = types()
            _typ = st.selectbox(
                "Type", _typ_opts, key="tools_type",
                index=_index_of(session.get("tools_type"), _typ_opts))
        with _fs:
            _src_opts = sources()
            _src = st.selectbox(
                "Source", _src_opts, key="tools_source",
                index=_index_of(session.get("tools_source"), _src_opts))
        with _fv:
            # A selectbox, not two small buttons: the 1-wide column
            # would cut a button label off (the old Tools tab had a
            # cut-off label already — see the E2E notes).
            _view_opts = ["Grid", "List"]
            _view = st.selectbox(
                "View", _view_opts, key="tools_view",
                index=_index_of(session.get("tools_view"), _view_opts))
        shown = filter_tools(TOOLS, _q, _cat, _typ, _src)
        st.caption(f"{len(shown)} of {len(TOOLS)} tools")
        _no_filter = (not (_q or "").strip() and _cat == "All"
                      and _typ == "All" and _src == "All")
        if not shown:
            ui_design.empty_state(
                "No tools match",
                "Try a different search, or clear a filter.")
            return None, None, None
        if _no_filter:
            _render_featured(st, TOOLS, statuses)
        if session.get("tools_view", "Grid") == "List":
            for tool in shown:
                _render_list_row(st, tool, statuses[tool["key"]])
        else:
            for _i in range(0, len(shown), 3):
                _cols = st.columns(3)
                for _col, tool in zip(_cols, shown[_i:_i + 3]):
                    with _col:
                        _render_card(st, tool, statuses[tool["key"]])
    return None, None, None
