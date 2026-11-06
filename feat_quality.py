"""Data Cleaner Studio — Group 1: data quality & trust (v1.2).

Pure logic + thin Streamlit render functions. The logic functions never
touch Streamlit, so they are unit-testable on their own; the render
functions take the ``st`` module as their first argument.

Features
--------
1. Quality score       — quality_score(df)
2. Outlier alerts      — find_outliers(df), apply_outliers(df, column, mode)
3. Validation rules    — check_rules(df, rules)
4. Near-duplicate finder — near_duplicates(df, ...), merge_near_duplicates(...)
5. Audit trail         — record_audit(session_state, step, detail), render_audit(st)
6. Data dictionary     — data_dictionary(df)

Integrator spec (see the render functions' docstrings too)
----------------------------------------------------------
Tabs (simple_app.py):
  - Preview tab : render_quality_panel(st, raw) and render_dictionary(st, raw)
  - Clean tab   : render_outliers(st, clean), render_validation(st, clean),
                  render_near_dupes(st, clean) — AFTER the fuzzy-merge block,
                  so they act on the cleaned frame.
  - Report tab  : render_audit(st) — the log of every quality action.

Session-state keys (data — never widget keys):
  - "q_audit"         : list of {"time", "step", "detail"} (created on demand)
  - "q_rules_data"    : list of validation rule dicts {"column","rule","value"}
  - "q_nd_groups_data": near-duplicate groups found by the last Find click
  - "q_nd_col_data"   : text column those groups belong to

Widget keys (all start with "q_", none doubles as a data key):
  q_outlier_col, q_outlier_mode, q_outlier_apply, q_rule_col, q_rule_type,
  q_rule_value, q_rule_add, q_rule_clear, q_nd_col, q_nd_num, q_nd_thr,
  q_nd_keep, q_nd_find, q_nd_merge, q_audit_download, q_dict_download

Consuming render results (Clean tab):
  new_df, new_actions = render_outliers(st, clean)        # or render_near_dupes
  if new_df is not None:
      st.session_state.clean = new_df
      st.session_state.actions = st.session_state.actions + new_actions
      st.session_state.kpis = engine.auto_kpis(new_df)
"""

from __future__ import annotations

import re
from datetime import date, datetime

import numpy as np
import pandas as pd

import engine

# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------

_MONEY_PREFIX = re.compile(r"^(₹|\$|€|£|Rs\.?|INR)\s*", re.IGNORECASE)
_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")


def _py(value):
    """Convert a numpy/pandas scalar to a plain Python value for display."""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, float) and np.isnan(value):
        return None
    if pd.isna(value):
        return None
    return value


def _numeric_like_mask(series: pd.Series) -> pd.Series:
    """Boolean mask: which non-empty values look like numbers, allowing a
    currency prefix, thousands commas and a trailing % (same tolerance as
    engine._looks_numeric)."""
    vals = series.dropna().astype(object).astype(str).str.strip()
    vals = vals[vals != ""]
    if len(vals) == 0:
        return pd.Series(False, index=vals.index)
    v = vals.str.replace(_MONEY_PREFIX, "", regex=True)
    v = v.str.replace(",", "", regex=False).str.replace(r"%$", "", regex=True).str.strip()
    return v.str.match(_NUMERIC_RE)


def _mixed_type_columns(df: pd.DataFrame) -> list:
    """Columns whose values are a real mix of numbers and text — e.g. a
    Quantity column holding 2, 5 and 'N/A'. A column that is all numbers
    (even with ₹ / $ / commas) or all text is NOT mixed. A minority kind
    needs at least 2 values and 5% of the column to count, so one stray
    typo does not condemn the column."""
    mixed = []
    for col in df.columns:
        s = df[col]
        if s.isna().all():
            continue
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            continue
        mask = _numeric_like_mask(s)
        if len(mask) == 0:
            continue
        n_num = int(mask.sum())
        n_txt = int((~mask).sum())
        minority = min(n_num, n_txt)
        if minority >= 2 and minority / len(mask) >= 0.05:
            mixed.append(col)
    return mixed


# --------------------------------------------------------------------------
# 1. Quality score
# --------------------------------------------------------------------------

def quality_score(df: pd.DataFrame) -> tuple:
    """Score the frame 0–100 and say what drags it down, in plain words.

    Points lost (each capped so one problem cannot zero the score):
      - Missing cells : 1 point per 2% of cells empty, max 40. Cells in
        a column that is 100% empty do NOT count here — that column is
        already charged under "Empty columns" below, and an empty
        column is not any one row's fault.
      - Duplicate rows: 1 point per 1% of rows duplicated, max 20.
      - Empty columns : 5 points per column that is 100% empty, max 20.
      - Mixed-type columns: 5 points per column mixing numbers and text,
        max 20.
    Returns (score:int, breakdown:[{label, points_lost, detail}]) — the
    breakdown only lists problems that actually cost points.
    """
    breakdown = []
    total_cells = df.size
    if total_cells == 0 or len(df.columns) == 0:
        return 0, [{"label": "No data",
                    "points_lost": 100,
                    "detail": "The file has no rows or no columns to score."}]

    empty_cols = [c for c in df.columns if df[c].isna().all()]
    # Missing cells are scored only over columns that hold some data:
    # an all-empty column's cells are charged once, under "Empty
    # columns" below — counting them here too would punish the same
    # defect twice.
    scored = df.drop(columns=empty_cols) if empty_cols else df
    scored_cells = scored.size
    if scored_cells:
        missing_pct = 100 * float(scored.isna().mean().mean())
    else:
        missing_pct = 0.0
    if missing_pct > 0:
        lost = min(40, int(round(missing_pct / 2)))
        detail = (f"{int(scored.isna().sum().sum()):,} of "
                  f"{scored_cells:,} cells ({missing_pct:.1f}%) are empty.")
        if empty_cols:
            detail += (" Columns that are completely empty are not "
                       "counted here — they are listed below.")
        breakdown.append({
            "label": "Missing values",
            "points_lost": lost,
            "detail": detail,
        })

    if len(df) > 0:
        dup_pct = 100 * float(df.duplicated().mean())
        if dup_pct > 0:
            lost = min(20, int(round(dup_pct)))
            breakdown.append({
                "label": "Duplicate rows",
                "points_lost": lost,
                "detail": (f"{int(df.duplicated().sum()):,} of {len(df):,} rows "
                           f"({dup_pct:.1f}%) are exact duplicates."),
            })

    if empty_cols:
        lost = min(20, 5 * len(empty_cols))
        breakdown.append({
            "label": "Empty columns",
            "points_lost": lost,
            "detail": (f"{len(empty_cols)} column(s) are completely empty: "
                       f"{', '.join(str(c) for c in empty_cols)}."),
        })

    mixed = _mixed_type_columns(df)
    if mixed:
        lost = min(20, 5 * len(mixed))
        breakdown.append({
            "label": "Mixed-type columns",
            "points_lost": lost,
            "detail": (f"{len(mixed)} column(s) mix numbers and text, so they "
                       f"cannot be used as numbers: "
                       f"{', '.join(str(c) for c in mixed)}."),
        })

    score = max(0, 100 - sum(b["points_lost"] for b in breakdown))
    return int(score), breakdown


# --------------------------------------------------------------------------
# 2. Outlier alerts (IQR rule)
# --------------------------------------------------------------------------

def _iqr_bounds(s: pd.Series):
    """(lower, upper) IQR bounds for a numeric series, or None when the
    column has too little spread to judge (fewer than 4 values, or IQR 0)."""
    vals = pd.to_numeric(s, errors="coerce").dropna()
    if len(vals) < 4:
        return None
    q1, q3 = vals.quantile(0.25), vals.quantile(0.75)
    iqr = q3 - q1
    if not np.isfinite(iqr) or iqr <= 0:
        return None
    return float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)


def find_outliers(df: pd.DataFrame) -> list:
    """Every value outside Q1 - 1.5*IQR / Q3 + 1.5*IQR, per numeric column.
    Returns [{column, row_index, value, lower, upper}] sorted by column
    then row. row_index is the frame's index label (an int for fresh
    loads)."""
    out = []
    for col in engine.numeric_cols(df):
        bounds = _iqr_bounds(df[col])
        if bounds is None:
            continue
        lower, upper = bounds
        s = pd.to_numeric(df[col], errors="coerce")
        mask = (s < lower) | (s > upper)
        for idx in df.index[mask]:
            out.append({
                "column": col,
                "row_index": int(idx),
                "value": float(s.loc[idx]),
                "lower": lower,
                "upper": upper,
            })
    out.sort(key=lambda r: (str(r["column"]), r["row_index"]))
    return out


def apply_outliers(df: pd.DataFrame, column: str, mode: str) -> tuple:
    """Act on the outliers in one numeric column. mode:
      keep — change nothing (0 rows affected);
      drop — remove the outlier rows;
      cap  — winsorize: pull each outlier back to the nearest bound.
    Returns (new_df, count_affected) where count is rows removed (drop)
    or rows changed (cap)."""
    if mode not in ("keep", "drop", "cap"):
        raise ValueError(f"Unknown outlier mode: {mode} (keep / drop / cap)")
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not in the data.")
    bounds = _iqr_bounds(df[column])
    if bounds is None or mode == "keep":
        return df.copy(), 0
    lower, upper = bounds
    s = pd.to_numeric(df[column], errors="coerce")
    mask = (s < lower) | (s > upper)
    if mode == "drop":
        return df.loc[~mask].reset_index(drop=True), int(mask.sum())
    capped = s.clip(lower=lower, upper=upper)
    out = df.copy()
    out[column] = capped
    changed = int((capped != s).sum())
    return out, changed


# --------------------------------------------------------------------------
# 3. Validation rules
# --------------------------------------------------------------------------

_RULES_NEEDING_VALUE = ("greater_than", "less_than", "equals", "contains")
_RULE_TYPES = _RULES_NEEDING_VALUE + ("not_empty", "date_not_future", "date_not_past")


def check_rules(df: pd.DataFrame, rules: list) -> list:
    """Check every rule against every row. A rule is a dict
    {column, rule, value} with rule one of:
      greater_than / less_than — value must be a number (or number-like
        text) above / below the rule value;
      equals    — equal to the rule value (numbers compare as numbers,
        anything else as case-insensitive text);
      not_empty — the cell must not be blank;
      contains  — the cell's text must contain the rule value
        (case-insensitive);
      date_not_future / date_not_past — the cell's date must not be after
        / before today.
    Missing cells are NOT violations for the comparison rules — blankness
    is not_empty's job. A value that cannot be read as a number (or date)
    when the rule needs one IS a violation.
    Returns [{rule_index, column, rule, row_index, value}] — one entry per
    violating row, in rule order then row order."""
    violations = []
    today = date.today()
    for i, rule in enumerate(rules):
        col = rule.get("column")
        rtype = rule.get("rule")
        value = rule.get("value")
        if col not in df.columns:
            raise ValueError(f"Rule {i}: column '{col}' not in the data.")
        if rtype not in _RULE_TYPES:
            raise ValueError(f"Rule {i}: unknown rule '{rtype}'.")
        s = df[col]
        if rtype == "not_empty":
            # astype(str) turns NaN into "nan"; the isna() half already
            # covers those, so blank strings are the only extra catch.
            bad = s.isna() | (
                s.where(s.isna(), s.astype(object).astype(str)).str.strip() == "")
        elif rtype in ("greater_than", "less_than"):
            num = pd.to_numeric(s, errors="coerce")
            unparseable = s.notna() & num.isna()
            if rtype == "greater_than":
                bad = unparseable | (num.notna() & (num <= float(value)))
            else:
                bad = unparseable | (num.notna() & (num >= float(value)))
        elif rtype == "equals":
            if isinstance(value, (int, float, np.integer, np.floating)) \
                    and not isinstance(value, bool):
                num = pd.to_numeric(s, errors="coerce")
                bad = (s.notna() & num.isna()) | (
                    num.notna() & (num != float(value)))
            else:
                want = str(value).strip().lower()
                text = s.where(s.isna(), s.astype(object).astype(str)).str.strip().str.lower()
                bad = s.notna() & (text != want)
        elif rtype == "contains":
            want = str(value).lower()
            text = s.where(s.isna(), s.astype(object).astype(str)).str.lower()
            bad = s.notna() & ~text.str.contains(want, regex=False)
        elif rtype in ("date_not_future", "date_not_past"):
            parsed = pd.to_datetime(s, errors="coerce", format="mixed")
            unparseable = s.notna() & parsed.isna()
            if rtype == "date_not_future":
                bad = unparseable | (parsed.notna()
                                     & (parsed.dt.date > today))
            else:
                bad = unparseable | (parsed.notna()
                                     & (parsed.dt.date < today))
        for idx in df.index[bad]:
            violations.append({
                "rule_index": i,
                "column": col,
                "rule": rtype,
                "row_index": int(idx),
                "value": _py(s.loc[idx]),
            })
    return violations


# --------------------------------------------------------------------------
# 4. Near-duplicate finder
# --------------------------------------------------------------------------

def near_duplicates(df: pd.DataFrame, text_col: str, num_col=None,
                    threshold: float = 0.85) -> list:
    """Rows that look like the same thing spelled differently — e.g.
    'Aarav Sharma' vs 'Arav Sharma'. Spelling variants come from
    engine.fuzzy_groups on the text column; when num_col is given, rows
    only group together when their numbers are within 1% of each other
    (so two different people who happen to share a similar name do not
    merge). Rows with a missing number are left out of the numeric check.
    Returns [{canonical, members:[row indices]}] — canonical is the most
    frequent spelling; only groups with 2+ rows are returned."""
    if text_col not in df.columns:
        raise ValueError(f"Column '{text_col}' not in the data.")
    if num_col is not None and num_col not in df.columns:
        raise ValueError(f"Column '{num_col}' not in the data.")
    groups = engine.fuzzy_groups(df[text_col], threshold)
    text_norm = df[text_col].astype(object).astype(str).str.strip()
    num = None
    if num_col is not None:
        num = pd.to_numeric(df[num_col], errors="coerce")
    found = []
    for g in groups:
        rows = []
        for val, _count in g["members"]:
            rows.extend(df.index[text_norm == val].tolist())
        if num is None:
            members = sorted(int(i) for i in rows)
            if len(members) > 1:
                found.append({"canonical": g["canonical"], "members": members})
            continue
        # numeric gate: cluster rows whose numbers sit within 1% of the
        # cluster's smallest value.
        scored = [(float(num.loc[i]), int(i)) for i in rows
                  if pd.notna(num.loc[i])]
        scored.sort()
        clusters, cur = [], []
        for val, idx in scored:
            if not cur:
                cur = [(val, idx)]
                continue
            ref = cur[0][0]
            tol = 0.01 * abs(ref) if ref != 0 else 0.0
            if abs(val - ref) <= tol:
                cur.append((val, idx))
            else:
                clusters.append(cur)
                cur = [(val, idx)]
        if cur:
            clusters.append(cur)
        for cluster in clusters:
            members = sorted(idx for _v, idx in cluster)
            if len(members) > 1:
                found.append({"canonical": g["canonical"], "members": members})
    found.sort(key=lambda g: g["canonical"])
    return found


def merge_near_duplicates(df: pd.DataFrame, groups: list, keep: str = "first") -> tuple:
    """Drop the extra rows in each near-duplicate group, keeping the first
    (or last) row of the group in file order. Row indices that no longer
    exist in the frame are ignored, so a stale group list cannot crash a
    merge. Returns (new_df, rows_removed)."""
    if keep not in ("first", "last"):
        raise ValueError(f"keep must be 'first' or 'last', got '{keep}'.")
    drop_idx = []
    for g in groups:
        members = [i for i in g.get("members", []) if i in df.index]
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda i: df.index.get_loc(i))
        drop_idx.extend(ordered[1:] if keep == "first" else ordered[:-1])
    if not drop_idx:
        return df.copy(), 0
    out = df.drop(index=drop_idx).reset_index(drop=True)
    return out, len(drop_idx)


# --------------------------------------------------------------------------
# 5. Audit trail
# --------------------------------------------------------------------------

def record_audit(session_state, step: str, detail: str) -> None:
    """Append {"time", "step", "detail"} to session_state["q_audit"],
    creating the list when it is missing. session_state may be a plain
    dict (tests) or Streamlit's session state — both support this."""
    if "q_audit" not in session_state:
        session_state["q_audit"] = []
    session_state["q_audit"].append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "step": str(step),
        "detail": str(detail),
    })


# --------------------------------------------------------------------------
# 6. Data dictionary
# --------------------------------------------------------------------------

def _fmt_num(v) -> str:
    try:
        return f"{float(v):,.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(v)


def _sample_text(s: pd.Series, kind: str) -> str:
    """What to show as 'sample values' for one column: a min–max range for
    numbers, the top values for categories, one example otherwise."""
    non_null = s.dropna()
    if len(non_null) == 0:
        return "—"
    if kind == "number":
        # Numbers stored as text ("$1,499.00") need the same currency /
        # comma / % stripping as the numeric check before they parse.
        cleaned = (s.astype(object).astype(str).str.strip()
                   .str.replace(_MONEY_PREFIX, "", regex=True)
                   .str.replace(",", "", regex=False)
                   .str.replace(r"%$", "", regex=True).str.strip())
        num = pd.to_numeric(cleaned, errors="coerce").dropna()
        if len(num):
            return f"{_fmt_num(num.min())} to {_fmt_num(num.max())}"
    if kind == "category":
        top = non_null.astype(object).astype(str).value_counts().head(3)
        return ", ".join(f"{v} ({int(n)})" for v, n in top.items())
    val = str(non_null.iloc[0])
    return val if len(val) <= 40 else val[:37] + "..."


def data_dictionary(df: pd.DataFrame) -> tuple:
    """One row per column: column, type, missing %, unique count, sample
    values (min–max for numbers, top values for categories). Returns
    (md_text, table_df) — the markdown is ready for the Report tab."""
    rows = []
    for col in df.columns:
        s = df[col]
        kind = "empty" if s.isna().all() else engine.detect_kind(s)
        rows.append({
            "column": str(col),
            "type": kind,
            "missing %": round(100 * float(s.isna().mean()), 1),
            "unique": int(s.nunique(dropna=True)),
            "sample": _sample_text(s, kind),
        })
    table = pd.DataFrame(rows, columns=["column", "type", "missing %",
                                        "unique", "sample"])
    lines = ["# Data dictionary", "",
             f"{len(df):,} rows, {len(df.columns)} columns.", "",
             "| Column | Type | Missing % | Unique | Sample values |",
             "|---|---|---|---|---|"]
    for r in rows:
        safe = str(r["sample"]).replace("|", "/")
        lines.append(f"| {r['column']} | {r['type']} | {r['missing %']} | "
                     f"{r['unique']} | {safe} |")
    return "\n".join(lines), table


# --------------------------------------------------------------------------
# render functions — thin Streamlit wrappers (st passed in, never imported)
# --------------------------------------------------------------------------

def render_quality_panel(st, df: pd.DataFrame) -> None:
    """Preview tab (or Clean tab): the 0–100 score and what drags it down.
    Reads nothing from session state."""
    st.subheader("Data quality score")
    score, breakdown = quality_score(df)
    st.metric("Quality score", f"{score} / 100")
    st.progress(score / 100)
    if score >= 90:
        st.success("Clean data — nothing major is dragging the score down.")
    elif score >= 70:
        st.warning("Usable, but a few things are worth fixing before you "
                   "trust the numbers.")
    else:
        st.error("Rough data — fix the items below before relying on it.")
    if breakdown:
        st.write("What is dragging the score down:")
        st.table(pd.DataFrame(breakdown))
    else:
        st.write("No deductions — no missing cells, duplicates, empty "
                 "columns or mixed-type columns.")


def render_outliers(st, df: pd.DataFrame):
    """Clean tab: pick a number column, see its IQR outliers, and keep,
    drop or cap them. Returns (new_df_or_None, new_actions) — the
    integrator applies the returned frame to st.session_state.clean (see
    module docstring). Safe to run on every rerun: nothing changes until
    the Apply button is pressed."""
    num_cols = engine.numeric_cols(df)
    if not num_cols:
        st.info("No number columns, so there are no outliers to check.")
        return None, []
    st.subheader("Outlier alerts")
    st.write("Values far outside the usual range (below Q1 − 1.5×IQR or "
             "above Q3 + 1.5×IQR). Check them before you drop or cap — a "
             "real big order looks like an outlier too.")
    col = st.selectbox("Number column", num_cols, key="q_outlier_col")
    outs = [o for o in find_outliers(df) if o["column"] == col]
    if not outs:
        st.success(f"No outliers in {engine._pretty(col)}.")
        return None, []
    st.write(f"{len(outs)} outlier(s) in {engine._pretty(col)}:")
    st.dataframe(pd.DataFrame(outs)[["row_index", "value", "lower", "upper"]]
                 .head(100), width="stretch")
    mode_label = st.radio(
        "What to do with them",
        ["Keep them as they are", "Drop the outlier rows",
         "Cap them to the bounds"],
        key="q_outlier_mode")
    mode = {"Keep them as they are": "keep",
            "Drop the outlier rows": "drop",
            "Cap them to the bounds": "cap"}[mode_label]
    if st.button("Apply", key="q_outlier_apply"):
        new_df, affected = apply_outliers(df, col, mode)
        if mode == "keep" or affected == 0:
            st.info("Kept as they are — nothing changed.")
            return None, []
        action = (f"Outliers: {col}",
                  f"{affected} row(s) "
                  f"{'removed' if mode == 'drop' else 'capped to the IQR bounds'}")
        record_audit(st.session_state, action[0], action[1])
        st.success(f"Done — {action[1]}.")
        return new_df, [action]
    return None, []


def render_validation(st, df: pd.DataFrame) -> None:
    """Clean tab: build validation rules and see every row that breaks
    one. Rules live in session state under "q_rules_data" (a data key,
    never a widget key) so they survive reruns."""
    st.subheader("Validation rules")
    st.write("Set rules your data must follow — e.g. Quantity must be "
             "greater than 0, or Order Date must not be in the future — "
             "and see every row that breaks them.")
    if "q_rules_data" not in st.session_state:
        st.session_state["q_rules_data"] = []
    c1, c2 = st.columns(2)
    col = c1.selectbox("Column", list(df.columns), key="q_rule_col")
    rtype = c2.selectbox(
        "Rule",
        ["greater_than", "less_than", "equals", "not_empty", "contains",
         "date_not_future", "date_not_past"],
        key="q_rule_type")
    needs_value = rtype in _RULES_NEEDING_VALUE
    raw_value = ""
    if needs_value:
        raw_value = st.text_input("Value", key="q_rule_value",
                                  help="A number for greater/less than, "
                                       "text for equals / contains.")
    else:
        st.caption("This rule needs no value.")
    if st.button("Add rule", key="q_rule_add"):
        value = None
        ok = True
        if rtype in ("greater_than", "less_than"):
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                st.error("That rule needs a number — e.g. 0 or 100.")
                ok = False
        elif rtype == "equals":
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                value = raw_value
        elif rtype == "contains":
            value = raw_value
        if ok:
            st.session_state["q_rules_data"].append(
                {"column": col, "rule": rtype, "value": value})
    rules = st.session_state["q_rules_data"]
    if rules:
        for i, r in enumerate(rules):
            st.write(f"{i}. **{r['column']}** {r['rule']}"
                     + (f" {r['value']}" if r.get("value") is not None else ""))
        if st.button("Clear all rules", key="q_rule_clear"):
            st.session_state["q_rules_data"] = []
            rules = []
    if not rules:
        st.info("No rules yet — add one above.")
        return
    violations = check_rules(df, rules)
    for i, r in enumerate(rules):
        n = sum(1 for v in violations if v["rule_index"] == i)
        st.write(f"Rule {i} ({r['column']} {r['rule']}): "
                 f"{n} violating row(s).")
    if violations:
        st.dataframe(pd.DataFrame(violations).head(200), width="stretch")
        if len(violations) > 200:
            st.caption(f"Showing 200 of {len(violations)} violating rows.")
    else:
        st.success("All rules pass — no violating rows.")


def render_near_dupes(st, df: pd.DataFrame):
    """Clean tab: find rows that are the same thing spelled differently
    and merge them. Returns (new_df_or_None, new_actions) like
    render_outliers. Groups found by the Find button are kept in
    session state under "q_nd_groups_data" until merged or re-found."""
    text_cols = [c for c in df.columns
                 if str(df[c].dtype) in ("object", "str")
                 and 1 < df[c].nunique() <= 500]
    if not text_cols:
        st.info("No text column to check for near-duplicates.")
        return None, []
    st.subheader("Near-duplicates")
    st.write("Rows that look like the same thing with a different "
             "spelling — Aarav vs Arav. You review the groups first; "
             "nothing merges without your word.")
    c1, c2 = st.columns(2)
    col = c1.selectbox("Text column", text_cols, key="q_nd_col")
    num_opts = ["(none)"] + engine.numeric_cols(df)
    num_pick = c2.selectbox("Also match on number (optional)", num_opts,
                            key="q_nd_num",
                            help="When set, rows only group when their "
                                 "numbers are within 1% of each other.")
    thr = st.slider("How similar must the spelling be? (higher = stricter)",
                    0.70, 0.95, 0.85, 0.01, key="q_nd_thr")
    keep_label = st.selectbox("When merging, keep", ["first", "last"],
                              key="q_nd_keep")
    if st.button("Find near-duplicates", key="q_nd_find"):
        num_col = None if num_pick == "(none)" else num_pick
        st.session_state["q_nd_groups_data"] = near_duplicates(
            df, col, num_col, thr)
        st.session_state["q_nd_col_data"] = col
    groups = _valid_groups(df, st.session_state.get("q_nd_groups_data"))
    if st.session_state.get("q_nd_groups_data") is not None and not groups:
        st.info("No near-duplicates found.")
        return None, []
    if not groups:
        return None, []
    st.write(f"{len(groups)} near-duplicate group(s):")
    for g in groups[:10]:
        st.write(f"→ **{g['canonical']}**: rows {g['members']}")
        st.dataframe(df.loc[g["members"]], width="stretch")
    if len(groups) > 10:
        st.caption(f"Showing 10 of {len(groups)} groups.")
    if st.button("Merge these groups", type="primary", key="q_nd_merge"):
        new_df, removed = merge_near_duplicates(
            df, groups, keep=keep_label)
        action = (f"Near-duplicates: {st.session_state.get('q_nd_col_data', col)}",
                  f"{removed} row(s) merged into their main spelling")
        record_audit(st.session_state, action[0], action[1])
        st.session_state["q_nd_groups_data"] = None
        st.success(f"Merged — {removed} row(s) removed.")
        return new_df, [action]
    return None, []


def _valid_groups(df: pd.DataFrame, groups):
    """Drop group members whose row index no longer exists (stale groups
    after a re-clean) and drop groups left with fewer than 2 rows."""
    if not groups:
        return []
    valid = []
    for g in groups:
        members = sorted(int(i) for i in g.get("members", [])
                         if i in df.index)
        if len(members) > 1:
            valid.append({"canonical": g.get("canonical", ""),
                          "members": members})
    return valid


def render_audit(st) -> None:
    """Report tab: the log of every quality action taken this session,
    as a table with a CSV download."""
    st.subheader("Audit trail")
    audit = (st.session_state["q_audit"]
             if "q_audit" in st.session_state else [])
    if not audit:
        st.info("No actions recorded yet — outlier fixes and merges "
                "will appear here.")
        return
    st.dataframe(pd.DataFrame(audit), width="stretch")
    csv = pd.DataFrame(audit).to_csv(index=False).encode("utf-8")
    st.download_button("Download audit log (CSV)", csv,
                       file_name="audit_log.csv", mime="text/csv",
                       key="q_audit_download")


def render_dictionary(st, df: pd.DataFrame) -> None:
    """Preview tab: one row per column — type, missing %, unique count,
    sample values (min–max for numbers, top values for categories)."""
    st.subheader("Data dictionary")
    md_text, table_df = data_dictionary(df)
    st.markdown(md_text)
    st.dataframe(table_df, width="stretch")
    st.download_button("Download data dictionary (.md)",
                       md_text.encode("utf-8"),
                       file_name="data_dictionary.md",
                       key="q_dict_download")
