"""Data Cleaner Studio — Group 2: combine & compare (v1.2).

Pure-logic functions (no Streamlit calls) plus thin ``render_*`` functions
that take ``st`` as their first argument. The app integrator wires the
render functions into tabs; see the render-call spec at the bottom of
this module and in the handoff report.

Logic functions
---------------
compare_files(old_df, new_df, key=None)
append_files(dfs)
list_excel_sheets(raw_bytes) / load_excel_sheet(raw_bytes, sheet)
load_excel_all(raw_bytes)
pivot_table(df, rows, cols, values, agg)
add_calculated_column(df, new_name, col_a, op, col_b_or_number)
compare_kpis(old_kpis, new_kpis, pct_threshold=20)

Render functions (every widget key starts with ``c_``; data is stored
under separate, non-widget session-state keys — never reuse a widget key
to store data):
render_compare(st), render_append(st), render_pivot(st, df),
render_calculated(st, df), render_anomaly(st, df)

Only stdlib, pandas and numpy are imported here (plus ``engine`` from
this project). Streamlit is never imported: it is passed in as ``st``.
"""

import io
import re

import numpy as np
import pandas as pd

import engine

__all__ = [
    "compare_files",
    "append_files",
    "list_excel_sheets",
    "load_excel_sheet",
    "load_excel_all",
    "pivot_table",
    "add_calculated_column",
    "compare_kpis",
    "render_compare",
    "render_append",
    "render_pivot",
    "render_calculated",
    "render_anomaly",
]

_AGG_FUNCS = {
    "Sum": "sum",
    "Average": "mean",
    "Count": "count",
    "Min": "min",
    "Max": "max",
}

_CALC_OPS = ("+", "-", "*", "/")


# ============================================================== helpers =====
def _same(a, b) -> bool:
    """True when two cell values are equal, counting NaN == NaN."""
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    try:
        return bool(a == b)
    except Exception:  # noqa: BLE001 - e.g. comparing odd objects
        return str(a) == str(b)


def _row_summary(row: pd.Series, max_cols: int = 5) -> str:
    """Short 'col=value, col=value' summary of a row for detail tables."""
    parts = []
    for col, val in row.items():
        if pd.isna(val):
            parts.append(f"{col}=(blank)")
        else:
            parts.append(f"{col}={val}")
        if len(parts) >= max_cols:
            break
    return ", ".join(parts)


def _parse_kpi_value(value):
    """Pull the numeric part out of an engine.auto_kpis value.

    '78,323.0' -> 78323.0, '77' -> 77.0, 'Electronics (33)' -> 33.0,
    '12.5%' -> 12.5. Returns None when there is no usable number
    (e.g. a date range like '2026-01-01 to 2026-08-29').
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        f = float(value)
        return f if np.isfinite(f) else None
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    cleaned = (s.replace(",", "")
                .replace("₹", "").replace("$", "").replace("€", "")
                .replace("£", "").replace("%", "").strip())
    try:
        return float(cleaned)
    except ValueError:
        pass
    # "Top <col>" KPIs carry their count in parentheses: 'Electronics (33)'.
    m = re.search(r"\(([-+]?\d[\d,]*\.?\d*)\)\s*$", s)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


# ======================================================= 1. compare =======
def compare_files(old_df: pd.DataFrame, new_df: pd.DataFrame,
                  key: str | None = None) -> dict:
    """Compare two versions of a file.

    key given: rows are matched on that column. Otherwise rows are
    matched by position (row 0 with row 0, ...).

    Returns {added, removed, changed_rows, changed_cells, detail_df,
    summary}. detail_df has columns [change, key, column, old, new]:
    one row per changed cell, plus one row per added / removed row
    (column '(row)', old/new holding a short summary of the row).
    """
    if key is not None:
        if key not in old_df.columns:
            raise ValueError(f"Key '{key}' not in the first file.")
        if key not in new_df.columns:
            raise ValueError(f"Key '{key}' not in the second file.")

    common = [c for c in old_df.columns if c in new_df.columns]
    old_only = [c for c in old_df.columns if c not in new_df.columns]
    new_only = [c for c in new_df.columns if c not in old_df.columns]

    rows = []  # detail rows: (change, key, column, old, new)
    added = removed = changed_rows = changed_cells = 0

    if key is not None:
        old_map, new_map = {}, {}
        old_dupes = new_dupes = 0
        for idx, k in enumerate(old_df[key]):
            kk = "" if pd.isna(k) else str(k)
            if kk in old_map:
                old_dupes += 1
            else:
                old_map[kk] = idx
        for idx, k in enumerate(new_df[key]):
            kk = "" if pd.isna(k) else str(k)
            if kk in new_map:
                new_dupes += 1
            else:
                new_map[kk] = idx
        old_keys, new_keys = set(old_map), set(new_map)
        for kk in sorted(new_keys - old_keys):
            added += 1
            rows.append(("added", kk, "(row)", "",
                         _row_summary(new_df.iloc[new_map[kk]])))
        for kk in sorted(old_keys - new_keys):
            removed += 1
            rows.append(("removed", kk, "(row)",
                         _row_summary(old_df.iloc[old_map[kk]]), ""))
        for kk in sorted(old_keys & new_keys):
            o_row, n_row = old_df.iloc[old_map[kk]], new_df.iloc[new_map[kk]]
            cell_changes = [(c, o_row[c], n_row[c]) for c in common
                            if not _same(o_row[c], n_row[c])]
            if cell_changes:
                changed_rows += 1
                changed_cells += len(cell_changes)
                for col, old_v, new_v in cell_changes:
                    rows.append(("changed", kk, col, old_v, new_v))
        match_note = f"matched on key '{key}'"
        dupe_note = ""
        if old_dupes or new_dupes:
            dupe_note = (f" (duplicate keys ignored — first row kept: "
                         f"{old_dupes} in old, {new_dupes} in new)")
    else:
        n_old, n_new = len(old_df), len(new_df)
        for pos in range(min(n_old, n_new)):
            o_row, n_row = old_df.iloc[pos], new_df.iloc[pos]
            cell_changes = [(c, o_row[c], n_row[c]) for c in common
                            if not _same(o_row[c], n_row[c])]
            if cell_changes:
                changed_rows += 1
                changed_cells += len(cell_changes)
                for col, old_v, new_v in cell_changes:
                    rows.append(("changed", str(pos), col, old_v, new_v))
        for pos in range(min(n_old, n_new), n_new):
            added += 1
            rows.append(("added", str(pos), "(row)", "",
                         _row_summary(new_df.iloc[pos])))
        for pos in range(min(n_old, n_new), n_old):
            removed += 1
            rows.append(("removed", str(pos), "(row)",
                         _row_summary(old_df.iloc[pos]), ""))
        match_note = "matched by row position"
        dupe_note = ""

    detail_df = pd.DataFrame(
        rows, columns=["change", "key", "column", "old", "new"])
    summary = (f"Compared {len(old_df):,} rows (old) with {len(new_df):,} rows "
               f"(new), {match_note}: {added} added, {removed} removed, "
               f"{changed_rows} row(s) changed ({changed_cells} cell(s)).")
    if old_only:
        summary += f" Columns only in old file: {', '.join(old_only)}."
    if new_only:
        summary += f" Columns only in new file: {', '.join(new_only)}."
    if not common:
        summary += " No columns in common — nothing could be compared cell by cell."
    summary += dupe_note
    return {"added": added, "removed": removed,
            "changed_rows": changed_rows, "changed_cells": changed_cells,
            "detail_df": detail_df, "summary": summary}


# ======================================================== 2. append =======
def append_files(dfs: list) -> tuple:
    """Stack dataframes with (mostly) the same columns.

    Returns (combined_df, report) where report is
    {rows_per_file, total_rows, columns, missing_columns, extra_columns,
    notes}. missing_columns / extra_columns are {file_N: [columns]} for
    files that differ (1-based numbering, file_1 is the reference);
    notes says the same thing in plain words.
    """
    if not dfs:
        return (pd.DataFrame(),
                {"rows_per_file": [], "total_rows": 0, "columns": [],
                 "missing_columns": {}, "extra_columns": {},
                 "notes": ["No files to append."]})
    rows_per_file = [len(d) for d in dfs]
    union_cols = []
    for d in dfs:
        for c in d.columns:
            if c not in union_cols:
                union_cols.append(c)
    ref_cols = list(dfs[0].columns)
    missing, extra, notes = {}, {}, []
    for i, d in enumerate(dfs[1:], start=2):
        miss = [c for c in union_cols if c not in d.columns]
        ext = [c for c in d.columns if c not in ref_cols]
        if miss:
            missing[f"file_{i}"] = miss
            notes.append(f"File {i} is missing column(s): {', '.join(miss)} "
                         f"(those cells will be blank).")
        if ext:
            extra[f"file_{i}"] = ext
            notes.append(f"File {i} has extra column(s): {', '.join(ext)} "
                         f"(kept in the combined file).")
    if not notes:
        notes.append("All files have the same columns — nothing missing, "
                     "nothing extra.")
    combined = pd.concat(dfs, ignore_index=True, sort=False)
    return (combined,
            {"rows_per_file": rows_per_file,
             "total_rows": int(len(combined)),
             "columns": union_cols,
             "missing_columns": missing,
             "extra_columns": extra,
             "notes": notes})


# ============================================== 3. multi-sheet Excel ======
def list_excel_sheets(raw_bytes: bytes) -> list:
    """Sheet names inside an uploaded Excel file."""
    return pd.ExcelFile(io.BytesIO(raw_bytes)).sheet_names


def load_excel_sheet(raw_bytes: bytes, sheet) -> pd.DataFrame:
    """Load one sheet; empty / whitespace-only strings become NaN,
    exactly like engine.load_file."""
    df = pd.read_excel(io.BytesIO(raw_bytes), sheet_name=sheet)
    return df.replace(r"^\s*$", np.nan, regex=True)


def load_excel_all(raw_bytes: bytes) -> tuple:
    """Append every sheet of an Excel file into one dataframe.

    Returns (combined_df, sheet_names). Column mismatches between
    sheets are handled the same way as append_files (union of columns,
    blanks where a sheet lacks a column).
    """
    names = list_excel_sheets(raw_bytes)
    frames = [load_excel_sheet(raw_bytes, s) for s in names]
    combined, _report = append_files(frames)
    return combined, names


# ========================================================= 4. pivot =======
def pivot_table(df: pd.DataFrame, rows, cols, values: str, agg: str) -> pd.DataFrame:
    """Pivot table via pandas pivot_table.

    rows / cols: a column name, a list of column names, or None (cols).
    values: the numeric column to aggregate. agg in
    Sum / Average / Count / Min / Max.
    """
    if agg not in _AGG_FUNCS:
        raise ValueError(f"Unknown aggregation: {agg} "
                         f"(use one of {', '.join(_AGG_FUNCS)})")
    if values not in df.columns:
        raise ValueError(f"Column '{values}' not in the data.")
    index = None if rows is None else ([rows] if isinstance(rows, str) else list(rows))
    columns = None if cols is None else ([cols] if isinstance(cols, str) else list(cols))
    for col in (index or []) + (columns or []):
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not in the data.")
    if not index and not columns:
        raise ValueError("Pick at least a row or a column grouping.")
    result = pd.pivot_table(df, index=index, columns=columns,
                            values=values, aggfunc=_AGG_FUNCS[agg])
    result = result.reset_index()
    if isinstance(result.columns, pd.MultiIndex):
        result.columns = [" | ".join(str(p) for p in tup if str(p) != "")
                          for tup in result.columns]
    return result


# ============================================== 5. calculated column ======
def add_calculated_column(df: pd.DataFrame, new_name: str, col_a: str,
                          op: str, col_b_or_number) -> pd.DataFrame:
    """Add a column computed from another column and a column or a number.

    op in + - * /. col_b_or_number may be another column name or a
    number (int, float, or a numeric string). Division by zero yields
    NaN, never an error and never infinity. The input frame is not
    changed; an existing column with new_name is replaced.
    """
    if not new_name or not str(new_name).strip():
        raise ValueError("Give the new column a name.")
    if col_a not in df.columns:
        raise ValueError(f"Column '{col_a}' not in the data.")
    if op not in _CALC_OPS:
        raise ValueError(f"Unknown operation: {op} (use one of "
                         f"{', '.join(_CALC_OPS)})")
    a = pd.to_numeric(df[col_a], errors="coerce")
    if isinstance(col_b_or_number, str) and col_b_or_number in df.columns:
        b = pd.to_numeric(df[col_b_or_number], errors="coerce")
        b_desc = col_b_or_number
    else:
        try:
            b = float(col_b_or_number)
        except (TypeError, ValueError):
            raise ValueError(
                f"'{col_b_or_number}' is neither a column nor a number.")
        b_desc = str(col_b_or_number)
    with np.errstate(divide="ignore", invalid="ignore"):
        if op == "+":
            result = a + b
        elif op == "-":
            result = a - b
        elif op == "*":
            result = a * b
        else:  # "/"
            result = a / b
    result = pd.to_numeric(result, errors="coerce").replace(
        [np.inf, -np.inf], np.nan)
    out = df.copy()
    out[str(new_name).strip()] = result
    return out


# ============================================== 6. anomaly alerts =========
def compare_kpis(old_kpis: list, new_kpis: list,
                 pct_threshold: float = 20) -> list:
    """Compare two KPI lists (as returned by engine.auto_kpis).

    Returns [{label, old, new, pct_change, flagged}] for every label
    present in both lists whose value has a usable number. Labels
    with no number (e.g. a date range) are skipped. flagged is True
    when abs(pct_change) >= pct_threshold. old == 0 with new != 0
    gives pct_change inf (and flagged True); 0 -> 0 gives 0.0.
    """
    old_map = {k["label"]: _parse_kpi_value(k["value"]) for k in old_kpis}
    new_map = {k["label"]: _parse_kpi_value(k["value"]) for k in new_kpis}
    out = []
    for label, old_v in old_map.items():
        if label not in new_map:
            continue
        new_v = new_map[label]
        if old_v is None or new_v is None:
            continue
        if old_v == 0:
            pct = 0.0 if new_v == 0 else float("inf")
        else:
            pct = round((new_v - old_v) / abs(old_v) * 100, 1)
        out.append({"label": label, "old": old_v, "new": new_v,
                    "pct_change": pct,
                    "flagged": bool(abs(pct) >= pct_threshold)})
    return out


# ====================================================== render helpers =====
def _current_df(st):
    """The file the app is working on: cleaned if available, else raw."""
    clean = st.session_state.get("clean")
    if clean is not None:
        return clean
    return st.session_state.get("raw")


def _load_uploaded(st, uploaded, what: str):
    """Load an uploaded file via the engine; show the error, return None."""
    try:
        return engine.load_file(uploaded.name, uploaded.getvalue())
    except Exception as e:  # noqa: BLE001 - show the error, don't crash
        st.error(f"Could not read {uploaded.name}: {e}")
        return None


# ================================================== render: compare =======
def render_compare(st):
    """Compare the current file against another uploaded file.

    Own uploader (key c_compare_upload). Stores the result dict in
    session state under data key 'compare_result' (not a widget key).
    Safe to run on every rerun.
    """
    st.subheader("Compare two files")
    st.write("See what changed between this file and another version of "
             "it — rows added or removed, and which cells changed.")
    current = _current_df(st)
    if current is None:
        st.info("Load a file first — the comparison needs a file loaded "
                "on this side.")
        return
    uploaded = st.file_uploader(
        "Other file to compare against (CSV, Excel or JSON)",
        type=["csv", "xlsx", "xls", "json"], key="c_compare_upload")
    if uploaded is None:
        st.info("Upload the other file — the comparison needs two files, "
                "and one is loaded.")
        return
    other = _load_uploaded(st, uploaded, "compare")
    if other is None:
        return
    common = [c for c in current.columns if c in other.columns]
    key_options = ["(match by row position)"] + common
    key_choice = st.selectbox("Match rows by", key_options,
                              key="c_compare_key")
    key = None if key_choice.startswith("(match") else key_choice
    if st.button("Compare files", key="c_compare_run"):
        # Uploaded file = old version, current file = new version.
        st.session_state["compare_result"] = compare_files(other, current, key)
    result = st.session_state.get("compare_result")
    if result:
        st.write(result["summary"])
        st.write(f"Added: **{result['added']}**  ·  "
                 f"Removed: **{result['removed']}**  ·  "
                 f"Changed rows: **{result['changed_rows']}**  ·  "
                 f"Changed cells: **{result['changed_cells']}**")
        if len(result["detail_df"]):
            st.dataframe(result["detail_df"], width="stretch")
        else:
            st.success("The two files are identical on every shared "
                       f"column — {result['added']} added, "
                       f"{result['removed']} removed, "
                       f"{result['changed_cells']} changed cells.")


# =================================================== render: append =======
def render_append(st):
    """Append one or more uploaded files onto the current file.

    Own uploader (key c_append_upload, multiple files). Stores
    (combined_df, report) in session state under data key
    'append_result'. 'Use appended data' replaces the current file
    (raw = combined, clean/actions/kpis cleared, like loading anew).
    Safe to run on every rerun.
    """
    st.subheader("Append files")
    st.write("Stack files with the same columns on top of each other — "
             "for example monthly sales files. The current file comes "
             "first, then the uploaded ones.")
    current = _current_df(st)
    if current is None:
        st.info("Load a file first — appending needs a file to append "
                "onto.")
        return
    uploaded = st.file_uploader(
        "Files to append (CSV, Excel or JSON)",
        type=["csv", "xlsx", "xls", "json"], accept_multiple_files=True,
        key="c_append_upload")
    if not uploaded:
        st.info("Upload at least one file to append onto the loaded file.")
        return
    if st.button("Append files", key="c_append_run"):
        frames = [current]
        names = [st.session_state.get("source_name") or "current file"]
        ok = True
        for f in uploaded:
            df = _load_uploaded(st, f, "append")
            if df is None:
                ok = False
                break
            frames.append(df)
            names.append(f.name)
        if ok:
            combined, report = append_files(frames)
            st.session_state["append_result"] = (combined, report, names)
    result = st.session_state.get("append_result")
    if result:
        combined, report, names = result
        for note in report["notes"]:
            st.write(f"- {note}")
        st.write("Rows per file: " +
                 ", ".join(f"{n}: {r:,}" for n, r in
                           zip(names, report["rows_per_file"])) +
                 f"  →  **{report['total_rows']:,} rows** in total.")
        st.dataframe(combined.head(100), width="stretch")
        if st.button("Use appended data", type="primary", key="c_append_use"):
            st.session_state["raw"] = combined
            st.session_state["clean"] = None
            st.session_state["actions"] = None
            st.session_state["kpis"] = None
            st.session_state["source_name"] = " + ".join(names)
            st.session_state["clean_opts"] = None
            st.session_state["fuzzy_groups"] = None
            st.session_state["join_result"] = None
            st.session_state["append_result"] = None
            st.success(f"Appended — {report['total_rows']:,} rows in "
                       "total. Now clean it in the Clean tab.")
            st.rerun()


# ==================================================== render: pivot =======
def render_pivot(st, df):
    """Pivot-table builder for a dataframe (pass the cleaned / filtered df).

    Stores the pivot result in session state under data key
    'pivot_result'. Safe to run on every rerun.
    """
    st.subheader("Pivot table")
    st.write("Summarise the data — for example total sales by region "
             "and category.")
    if df is None or len(df) == 0:
        st.info("Clean the data first — the pivot table is built from the "
                "cleaned file.")
        return
    num_cols = engine.numeric_cols(df)
    if not num_cols:
        st.info("No number column in this file — the pivot needs one to "
                "summarise.")
        return
    c1, c2, c3 = st.columns(3)
    rows = c1.selectbox("Rows (group by)", list(df.columns), key="c_pivot_rows")
    cols_choice = c2.selectbox("Columns (optional)",
                               ["(none)"] + list(df.columns),
                               key="c_pivot_cols")
    values = c3.selectbox("Values (number)", num_cols, key="c_pivot_values")
    agg = st.selectbox("Summarise with",
                       ["Sum", "Average", "Count", "Min", "Max"],
                       key="c_pivot_agg")
    if st.button("Build pivot table", key="c_pivot_run"):
        cols = None if cols_choice == "(none)" else cols_choice
        try:
            st.session_state["pivot_result"] = pivot_table(
                df, rows, cols, values, agg)
        except Exception as e:  # noqa: BLE001 - show the error, don't crash
            st.error(str(e))
    result = st.session_state.get("pivot_result")
    if result is not None:
        st.dataframe(result, width="stretch")
        st.download_button("Download pivot (.csv)",
                           result.to_csv(index=False).encode("utf-8"),
                           file_name="pivot_table.csv", key="c_pivot_download")


# ============================================== render: calculated =========
def render_calculated(st, df):
    """Calculated-column builder for a dataframe (pass the cleaned df).

    Returns (new_df_or_None, new_actions). The integrator applies the
    return on the same run, e.g.:
        new_df, new_actions = feat_combine.render_calculated(st, clean)
        if new_df is not None:
            st.session_state['clean'] = new_df
            st.session_state['actions'] = actions + new_actions
            st.session_state['kpis'] = engine.auto_kpis(new_df)
    Returns (None, []) when the button was not pressed. Safe on rerun.
    """
    st.subheader("Calculated column")
    st.write("Make a new column from a number column — for example "
             "total = quantity × unit price.")
    if df is None or len(df) == 0:
        st.info("Clean the data first — calculated columns are built on "
                "the cleaned file.")
        return None, []
    num_cols = engine.numeric_cols(df)
    if not num_cols:
        st.info("No number columns in this file — a calculated column "
                "needs at least one number to work on.")
        return None, []
    c1, c2, c3 = st.columns(3)
    col_a = c1.selectbox("First column", num_cols, key="c_calc_col_a")
    op = c2.selectbox("Operation", ["+", "-", "*", "/"], key="c_calc_op")
    b_options = num_cols + ["(enter a number)"]
    col_b_choice = c3.selectbox("Second column or number", b_options,
                                key="c_calc_col_b")
    b_number = None
    if col_b_choice == "(enter a number)":
        b_number = st.number_input("Number", value=0.0, key="c_calc_number")
    new_name = st.text_input("Name for the new column",
                             key="c_calc_new_name",
                             placeholder="e.g. total_price")
    if st.button("Add calculated column", type="primary", key="c_calc_add"):
        if not new_name.strip():
            st.error("Name the new column first — e.g. 'total_price' — "
                     "then add it.")
            return None, []
        col_b = b_number if col_b_choice == "(enter a number)" else col_b_choice
        try:
            new_df = add_calculated_column(df, new_name.strip(), col_a, op, col_b)
        except Exception as e:  # noqa: BLE001 - show the error, don't crash
            st.error(str(e))
            return None, []
        action = (f"Calculated column: {new_name.strip()}",
                  f"{col_a} {op} {col_b}")
        st.success(f"Added column '{new_name.strip()}' "
                   f"({col_a} {op} {col_b}) — {len(new_df):,} rows filled.")
        st.dataframe(new_df[[new_name.strip()]].head(20), width="stretch")
        return new_df, [action]
    return None, []


# =============================================== render: anomaly ==========
def render_anomaly(st, df):
    """KPI anomaly alerts: compare a previous file's KPIs with the
    current cleaned file's KPIs and flag big moves.

    Own uploader for the previous file (key c_anomaly_upload). Stores
    the alert list in session state under data key 'anomaly_result'.
    Safe to run on every rerun.
    """
    st.subheader("Anomaly alerts")
    st.write("Upload the previous version of this file. Its KPIs are "
             "compared with the current file's KPIs, and any KPI that "
             "moved by more than the threshold is flagged.")
    if df is None:
        st.info("Clean the data first — anomaly alerts compare the "
                "cleaned file's KPIs with the previous file's.")
        return
    uploaded = st.file_uploader(
        "Previous file (CSV, Excel or JSON)",
        type=["csv", "xlsx", "xls", "json"], key="c_anomaly_upload")
    if uploaded is None:
        st.info("Upload the previous version of this file — the alerts "
                "compare its KPIs with the current file's.")
        return
    threshold = st.slider("Flag moves bigger than (%)", 1, 100, 20, 1,
                          key="c_anomaly_threshold")
    if st.button("Check for anomalies", key="c_anomaly_run"):
        prev_raw = _load_uploaded(st, uploaded, "anomaly")
        if prev_raw is not None:
            try:
                prev_clean, _actions = engine.clean(prev_raw)
                old_kpis = engine.auto_kpis(prev_clean)
            except Exception:  # noqa: BLE001 - fall back to raw KPIs
                old_kpis = engine.auto_kpis(prev_raw)
            new_kpis = engine.auto_kpis(df)
            st.session_state["anomaly_result"] = compare_kpis(
                old_kpis, new_kpis, pct_threshold=threshold)
    result = st.session_state.get("anomaly_result")
    if result is not None:
        flagged = [r for r in result if r["flagged"]]
        if flagged:
            st.warning(f"{len(flagged)} KPI(s) moved by more than "
                       f"{threshold}% — see below.")
        else:
            st.success(f"No KPI moved by more than {threshold}% — the two "
                       "files agree within that band.")
        if result:
            table = pd.DataFrame(result)
            table["pct_change"] = table["pct_change"].apply(
                lambda v: "inf%" if v == float("inf") else f"{v:+.1f}%")
            table["flagged"] = table["flagged"].apply(
                lambda f: "⚠️ FLAGGED" if f else "")
            st.dataframe(table, width="stretch")
        else:
            st.info("No comparable numeric KPIs between the two files — "
                    "they share no number column to compare.")
