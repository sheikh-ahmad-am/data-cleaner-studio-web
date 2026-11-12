"""Join tab as Supabase's Database page: Tables + Schema Visualizer,
mapped to this app's own data (the mapping the clone spec confirms:
Join -> Database Tables + Schema Visualizer).

Supabase's Database page, from the audit (spec Pass B1): a left
sub-nav (Tables list + Schema Visualizer link), a Tables list (table
name, row count, columns, size), a table detail (columns with types
+ row preview), and a Schema Visualizer — a dotted canvas with one
card per table (columns listed inside) and lines between related
tables. A "Copy as SQL" action renders the table as a CREATE TABLE
statement.

The mapping onto this app's REAL tables, honestly:

* The loaded file is one table, named after the file (the sample
  loads as "messy_sales.csv (sample)"). There is no separate
  "sample" table: the sample IS the loaded file's table when it is
  loaded, and no table is invented for it when another file is.
* The cleaned table exists only after a clean: same name + "
  (cleaned)", derived from the raw table. Until then the Tables
  list has one row and the visualizer has one card.
* The relationship is lineage, not a foreign key: the cleaned
  table is derived from the raw table. The canvas says so in the
  cleaned card's sub-line ("Derived from <raw name>") — no fake
  FK arrows, no invented keys.
* "Copy as SQL" is real: a CREATE TABLE statement generated from
  the table's actual columns and guessed types, with a Download
  .sql button.
* The old Join-two-files form (join another file on a key) lives
  under "Join files" in the sub-nav, moved verbatim — same labels,
  same keys, same ``engine.join_frames`` call, same preview lines,
  same "Use joined data" behaviour. Nothing about the join itself
  changed.

What is NOT built, and why (stated plainly, not faked):

* Clickable diagram nodes: stock Streamlit cannot make a node in
  an HTML canvas clickable — the Dashboard round proved this.
  The visualizer is a static diagram (the canvas + cards render
  honestly) and each table has a real Open button under the canvas
  and in the sub-nav Tables list. The canvas says so.
* Zoom / fit / auto-layout controls: with one or two tables there
  is nothing to lay out or zoom into, so the canvas is fixed.
* Export PNG: Streamlit cannot screenshot its own canvas.
* A whole table row as one link: stock Streamlit cannot make a
  dataframe row clickable — the sub-nav table buttons and the
  visualizer's Open buttons are the honest equivalent, the same
  state-button idiom the Tools sub-nav uses.
* Realtime / RLS columns: this app has no realtime subscriptions
  and no row-level security on its tables, so the list shows
  Table / Rows / Columns / Size only — the Supabase columns that
  have a real value here.

Contract:
  - list_tables(raw, clean, source_name) -> [table] — pure:
    one descriptor per real table (key, name, kind, rows, columns,
    size, size_bytes). No table is invented.
  - table_size(df) -> str — pure: human-readable bytes.
  - filter_tables(tables, query) -> [table] — pure: case-insensitive
    substring match on the table name.
  - sql_type(kind) -> str — pure: engine kind -> SQL type.
  - create_table_sql(name, df) -> str — pure: a CREATE TABLE
    statement for the table's actual columns.
  - column_lines(df, limit=8) -> [str] — pure: "name — type" lines
    for a visualizer card, capped with an "… and N more" line.
  - render_join_page(st, raw=None, clean=None, source_name=None,
    load_sample=None, set_raw=None, audit=None) -> None — the page.
    Renders with no data loaded: the sub-nav and an empty state
    with a "Try the sample data" CTA (load_sample is called when
    the CTA is clicked); the tables, the visualizer and the join
    form all need a loaded file, so they stay behind the empty
    state until one exists.

Widget keys all start with "join_"; the view lives in
session_state["join_view"] ("tables" / "visualizer" /
"join-files") and the open table in session_state["join_detail"]
(a table key, or None).
"""

from __future__ import annotations

import html

import pandas as pd

import engine
import ui_design

VIEW_TABLES = "tables"
VIEW_VISUALIZER = "visualizer"
VIEW_JOIN_FILES = "join-files"

_VIEWS = [(VIEW_TABLES, "Tables"),
          (VIEW_VISUALIZER, "Schema Visualizer"),
          (VIEW_JOIN_FILES, "Join files")]

_SQL_TYPES = {"number": "numeric", "date": "timestamp",
              "category": "text", "text": "text"}


# --------------------------------------------------------------------------
# Pure model
# --------------------------------------------------------------------------

def table_size(df) -> str:
    """Human-readable size of a frame (memory usage, deep)."""
    nbytes = int(df.memory_usage(deep=True).sum())
    if nbytes < 1024:
        return f"{nbytes} B"
    if nbytes < 1024 ** 2:
        return f"{nbytes / 1024:.1f} KB"
    return f"{nbytes / 1024 ** 2:.1f} MB"


def list_tables(raw, clean, source_name=None) -> list:
    """One descriptor per REAL table: the loaded file, and the
    cleaned copy once it exists. No table is invented — the sample
    is a table only when it is the loaded file, and the cleaned
    table only after a clean."""
    tables = []
    name = str(source_name or "data")
    if raw is not None:
        tables.append({"key": "raw", "name": name, "kind": "raw",
                       "rows": int(len(raw)),
                       "columns": int(len(raw.columns)),
                       "size": table_size(raw),
                       "size_bytes": int(
                           raw.memory_usage(deep=True).sum())})
    if clean is not None:
        tables.append({"key": "cleaned",
                       "name": name + " (cleaned)", "kind": "cleaned",
                       "rows": int(len(clean)),
                       "columns": int(len(clean.columns)),
                       "size": table_size(clean),
                       "size_bytes": int(
                           clean.memory_usage(deep=True).sum())})
    return tables


def filter_tables(tables, query="") -> list:
    """The tables whose name contains the query (case-insensitive
    substring); an empty query matches everything."""
    query = (query or "").strip().lower()
    if not query:
        return list(tables)
    return [t for t in tables if query in t["name"].lower()]


def sql_type(kind) -> str:
    """The engine's guessed kind as a SQL column type."""
    return _SQL_TYPES.get(str(kind), "text")


def _sql_ident(name) -> str:
    """A quoted SQL identifier (double quotes, embedded quotes
    doubled)."""
    return '"' + str(name).replace('"', '""') + '"'


def create_table_sql(name, df) -> str:
    """A CREATE TABLE statement for the table's actual columns and
    guessed types — what Supabase's "Copy as SQL" renders."""
    lines = [f"CREATE TABLE {_sql_ident(name)} ("]
    cols = list(df.columns)
    for _i, col in enumerate(cols):
        _comma = "," if _i < len(cols) - 1 else ""
        lines.append(f"  {_sql_ident(col)} "
                     f"{sql_type(engine.detect_kind(df[col]))}{_comma}")
    lines.append(");")
    return "\n".join(lines)


def column_lines(df, limit=8) -> list:
    """\"name — type\" lines for a visualizer card, capped at
    ``limit`` columns with an \"… and N more columns\" line."""
    lines = [f"{col} — {engine.detect_kind(df[col])}"
             for col in list(df.columns)[:limit]]
    if len(df.columns) > limit:
        lines.append(f"… and {len(df.columns) - limit} more columns")
    return lines


# --------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------

def _render_empty(st, load_sample) -> None:
    """The no-data empty state: the guided card with the one-click
    sample loader (the Tools/Clean reachability fix — the tab
    opens, the actions stay behind the empty state until data
    exists)."""
    if ui_design.empty_state(
            "No data loaded yet",
            "Upload a file from the sidebar on the left, or skip the "
            "setup and explore with the sample file: it loads the "
            "messy sales data (80 rows) so you can see the tables, "
            "the schema, and the join right away.",
            cta_label="Try the sample data"):
        if load_sample is not None:
            load_sample()
        st.rerun()


def _render_tables_view(st, tables) -> None:
    """The Tables list: search + Table / Rows / Columns / Size,
    with Supabase's \"Total: N tables\" footer."""
    ui_design.section_heading(
        "Tables",
        sub="Every table in this workspace — the file you loaded, "
            "and the cleaned copy once it exists.")
    _q = st.text_input("Search tables", key="join_q",
                       placeholder="Search tables")
    shown = filter_tables(tables, _q)
    st.caption(f"{len(shown)} of {len(tables)} tables")
    if not shown:
        ui_design.empty_state(
            "No tables match",
            "Try a different search.")
        return
    _frame = pd.DataFrame([{"Table": t["name"], "Rows": t["rows"],
                            "Columns": t["columns"], "Size": t["size"]}
                           for t in shown])
    st.dataframe(_frame, width="stretch", hide_index=True)
    st.caption(f"Total: {len(tables)} table"
               f"{'s' if len(tables) != 1 else ''}")


def _render_detail(st, table, df) -> None:
    """One table's detail: breadcrumb, columns with types (the
    Preview definition view), and a row preview."""
    if st.button("← All tables", key="join_back_all"):
        st.session_state["join_detail"] = None
        st.rerun()
    st.markdown(
        f'<div class="dcs-micro-label">Join &gt; '
        f'{html.escape(table["name"])}</div>',
        unsafe_allow_html=True)
    ui_design.section_heading(
        table["name"],
        sub=(f"{table['rows']:,} rows · {table['columns']} columns · "
             f"{table['size']}"))
    st.markdown('<div class="dcs-micro-label">Columns</div>',
                unsafe_allow_html=True)
    st.table(pd.DataFrame(engine.profile(df)))
    st.markdown('<div class="dcs-micro-label">Data preview</div>',
                unsafe_allow_html=True)
    st.dataframe(df.head(100), width="stretch")
    if len(df) > 100:
        st.caption(f"Showing first 100 of {len(df):,} rows · "
                   f"{len(df.columns)} columns")
    else:
        st.caption(f"Showing all {len(df):,} rows · "
                   f"{len(df.columns)} columns")


def _schema_canvas_html(tables, df_by_key) -> str:
    """The visualizer canvas: the Dashboard's dotted-canvas classes
    (.dcs-infra-canvas / .dcs-infra-row / .dcs-infra-node /
    .dcs-infra-arrow) with one node per table, the columns listed
    inside, and an arrow between the raw table and the cleaned
    table it derives from. Static HTML — the nodes are not
    clickable in stock Streamlit (the Dashboard round proved it),
    so the canvas carries no buttons; the Open buttons below it
    are the navigation."""
    _parts = ['<div class="dcs-infra-canvas">'
              '<div class="dcs-infra-row">']
    for _i, table in enumerate(tables):
        if _i:
            _parts.append('<div class="dcs-infra-arrow">→</div>')
        _df = df_by_key[table["key"]]
        _sub = (f"{table['columns']} columns"
                if table["kind"] == "raw"
                else f"Derived from {html.escape(tables[0]['name'])}")
        _lines = "".join(
            '<div class="dcs-infra-node-sub">'
            f"{html.escape(line)}</div>"
            for line in column_lines(_df))
        _parts.append(
            '<div class="dcs-infra-node">'
            '<div class="dcs-infra-node-title">'
            f"{html.escape(table['name'])}</div>"
            '<div class="dcs-infra-node-count">'
            f"{table['rows']:,} rows</div>"
            '<div class="dcs-infra-node-sub">'
            f"{_sub}</div>{_lines}</div>")
    _parts.append("</div></div>")
    return "".join(_parts)


def _index_of(value, options) -> int:
    """The selectbox index for a saved value: its position in the
    options, or 0 when the value is missing or stale (the Tools
    filter idiom — the displayed value always follows the saved
    one)."""
    return options.index(value) if value in options else 0


def _render_visualizer(st, tables, df_by_key) -> None:
    """The Schema Visualizer: the static dotted canvas, the Open
    buttons under it, and Copy as SQL."""
    ui_design.section_heading(
        "Schema Visualizer",
        sub="The raw table and the cleaned table, and how the second "
            "is derived from the first.")
    st.markdown(_schema_canvas_html(tables, df_by_key),
                unsafe_allow_html=True)
    st.caption("Static diagram — the nodes are not clickable in this "
               "build; open a table with the buttons below.")
    _cols = st.columns(len(tables))
    for _col, table in zip(_cols, tables):
        with _col:
            if ui_design.icon_button(
                    f"Open {table['name']}", "table",
                    key=f"join_open_{table['key']}",
                    help=f"Open {table['name']}.",
                    use_container_width=True):
                st.session_state["join_detail"] = table["key"]
                st.session_state["join_view"] = VIEW_TABLES
                st.rerun()
    st.markdown('<div class="dcs-micro-label">Copy as SQL</div>',
                unsafe_allow_html=True)
    _names = [t["name"] for t in tables]
    _picked = st.selectbox(
        "Table", _names, key="join_sql_table",
        index=_index_of(st.session_state.get("join_sql_table"), _names))
    _table = next(t for t in tables if t["name"] == _picked)
    _sql = create_table_sql(_table["name"], df_by_key[_table["key"]])
    st.code(_sql, language="sql")
    _slug = "".join(ch if ch.isalnum() else "-"
                    for ch in _table["name"].lower())[:24] or "table"
    st.download_button("Download .sql", _sql,
                       file_name=f"{_slug}.sql", key="join_sql_dl")


def _render_join_files(st, raw, set_raw, audit) -> None:
    """The join-two-files form, moved verbatim from the old inline
    Join section — same labels, same widget keys, same
    ``engine.join_frames`` call, same preview lines, same "Use
    joined data" behaviour. The only change is the plumbing:
    ``_set_raw`` / ``_audit`` arrive as arguments instead of
    closing over app.py's locals."""
    ui_design.section_heading(
        "Join files",
        sub="Combine this file with a second one on a shared column — "
            "like a customer ID or order ID. Nothing changes until you "
            "press 'Use joined data'.")
    joined_file = st.file_uploader(
        "Second file (CSV, Excel or JSON)",
        type=["csv", "xlsx", "xls", "json"], key="join_upload")
    if joined_file is not None:
        try:
            right = engine.load_file(joined_file.name,
                                     joined_file.getvalue())
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not read {joined_file.name}: {e}")
            right = None
        if right is not None:
            c1, c2, c3 = st.columns(3)
            left_key = c1.selectbox("Key in this file",
                                    list(raw.columns),
                                    key="join_left_key")
            right_key = c2.selectbox("Key in second file",
                                     list(right.columns),
                                     key="join_right_key")
            how_label = c3.selectbox(
                "How to join",
                ["Left (keep all rows from this file)",
                 "Inner (only matching rows)",
                 "Outer (keep everything)"],
                key="join_how")
            how = {"Left (keep all rows from this file)": "left",
                   "Inner (only matching rows)": "inner",
                   "Outer (keep everything)": "outer"}[how_label]
            if st.button("Preview join", key="join_preview_btn"):
                try:
                    st.session_state["join_result"] = engine.join_frames(
                        raw, right, left_key, right_key, how)
                except Exception as e:  # noqa: BLE001
                    st.error(str(e))
            preview = st.session_state.get("join_result")
            if preview:
                joined, info = preview
                st.write(f"Left: {info['left_rows']:,} rows  ·  "
                         f"Right: {info['right_rows']:,} rows  →  "
                         f"Joined: {info['joined_rows']:,} rows")
                st.write(f"Matched keys: {info['matched_keys']:,}  ·  "
                         f"Only in this file: {info['left_only']:,}  ·  "
                         f"Only in second file: {info['right_only']:,}")
                st.dataframe(joined.head(100), width="stretch")
                if st.button("Use joined data", type="primary",
                             key="join_use"):
                    set_raw(joined,
                            f"{st.session_state['source_name']} + "
                            f"{joined_file.name}")
                    st.session_state["join_result"] = None
                    audit("Join", f"{info['joined_rows']:,} rows")
                    st.success("Joined — now clean it in the Clean tab.")


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------

def render_join_page(st, raw=None, clean=None, source_name=None,
                     load_sample=None, set_raw=None, audit=None):
    """The Join tab as Supabase's Database page.

    Left sub-nav (Back to dashboard / Tables / Schema Visualizer /
    Join files + the tables list) + main column: the Tables list,
    a table detail, the Schema Visualizer, or the join-files form.
    Renders with no data loaded — the sub-nav and the empty state
    with its "Try the sample data" CTA; the tables, the visualizer
    and the join form all need a loaded file, so they stay behind
    the empty state until one exists.
    """
    session = st.session_state
    tables = list_tables(raw, clean, source_name)
    df_by_key = {"raw": raw, "cleaned": clean}
    detail_key = session.get("join_detail")
    detail = next((t for t in tables if t["key"] == detail_key),
                  None) if detail_key else None
    view = session.get("join_view", VIEW_TABLES)
    if view not in (VIEW_TABLES, VIEW_VISUALIZER, VIEW_JOIN_FILES):
        view = VIEW_TABLES

    _set_nav, _set_main = st.columns([1, 4])
    with _set_nav:
        if st.button("← Back to dashboard",
                     key="join_back_dashboard",
                     use_container_width=True):
            session["pending_tab"] = "dashboard"
            st.rerun()
        st.markdown('<div class="dcs-micro-label">Join</div>',
                    unsafe_allow_html=True)
        for _key, _label in _VIEWS:
            if st.button(_label, key=f"join_nav_{_key}",
                         disabled=(view == _key and detail is None),
                         use_container_width=True):
                session["join_view"] = _key
                session["join_detail"] = None
                st.rerun()
        if tables:
            st.markdown('<div class="dcs-micro-label">Tables</div>',
                        unsafe_allow_html=True)
            for table in tables:
                if st.button(table["name"],
                             key=f"join_nav_table_{table['key']}",
                             disabled=(detail is not None
                                       and detail["key"] == table["key"]),
                             use_container_width=True):
                    session["join_detail"] = table["key"]
                    session["join_view"] = VIEW_TABLES
                    st.rerun()

    with _set_main:
        if detail is not None:
            _render_detail(st, detail, df_by_key[detail["key"]])
            return
        if raw is None:
            _render_empty(st, load_sample)
            return
        if view == VIEW_VISUALIZER:
            _render_visualizer(st, tables, df_by_key)
        elif view == VIEW_JOIN_FILES:
            _render_join_files(st, raw, set_raw, audit)
        else:
            _render_tables_view(st, tables)
