"""Data Cleaner Studio — Batch 4: share & finish (v1.3).

Pure logic lives in plain functions (no Streamlit calls) so it can be
tested without the app running. The ``render_*`` functions are thin
Streamlit wrappers: they take ``st`` first and only use widget keys
starting with ``s_``. Widget keys are never reused to store data.

Features
--------
1.  Smart suggestions      — suggest_fixes(df), apply_suggestion(df, action)
2.  Column type override   — override_column_type(df, column, kind)
3.  Standardize phones     — standardize_phones(series)
4.  Strip special chars    — strip_specials(series)
5.  Goal tracking          — goal_progress(df, column, agg, target)
6.  Search the whole file  — search_rows(df, query)
7.  Sort the preview       — render_sort(st, df)
8.  Recent files           — add_recent / list_recent / load_recent
9.  Backup before cleaning — backup_raw / list_backups / restore_backup
10. One-click full flow    — render_one_click(st, raw, opts)
11. Standalone HTML dashboard — html_dashboard_bytes(...)
12. Publish to portfolio   — portfolio_zip_bytes(...)
13. Chart as image (PIL)   — chart_png_bytes(...)
14. Conditional colours in exports — to_excel_bytes_styled(...)

Honesty rules in this module — nothing is faked:
  * Recent files: an uploaded file can only be re-opened if the user
    ticked "Keep a copy for quick reopen" — the copy is then saved in
    the app-local ``recent/`` folder. Without that tick there is nothing
    to re-open, and the list says so plainly.
  * The one-click flow NEVER sends an email by itself. It builds the
    report and PDF, then shows the same SMTP form as
    feat_export.render_email_schedule: the email step is labelled
    pending until the SMTP details are filled in, and sending only
    happens if the user presses "Send test email now" there.
  * Charts are drawn with PIL (Pillow), which IS in the embedded
    build. No matplotlib and no vl-convert are used anywhere here.

Integrator spec (simple_app.py)
-------------------------------
  - Preview tab : render_suggestions(st, raw), render_search(st, raw),
                  render_sort(st, raw) — sort returns the sorted frame
                  to display instead of ``raw``.
  - Clean tab   : render_type_override(st, clean),
                  render_standardize_phones(st, clean),
                  render_strip_specials(st, clean) — the last two return
                  (new_df, new_actions) like feat_quality.render_outliers;
                  apply with _apply_new_clean. render_backups(st, raw,
                  source_name) at the top, BEFORE the Clean button, so
                  the backup exists before any cleaning runs.
  - KPIs tab    : render_goal(st, clean).
  - Sidebar     : render_recent(st, df=raw, source_name=...,
                  raw_bytes=<uploaded bytes or None>) under the Load
                  section — the "Keep a copy" tick only appears when
                  raw_bytes are passed in.
  - Report tab  : render_one_click(st, raw, clean_opts),
                  render_html_download(st, kpis, actions, grouped, ...),
                  render_portfolio_download(st, clean, kpis, actions),
                  render_chart_png(st, grouped, x_col, y_col),
                  render_styled_excel_download(st, clean, kpis, actions).

Session-state keys (data — never widget keys):
  - "s_goal_data"    : {"column", "agg", "target"} saved by Set goal
  - "s_recent_saved" : list of source names already saved as a recent
                       copy this session (stops re-saving on rerun)

Widget keys (all start with "s_", none doubles as a data key):
  s_sugg_apply_{i}, s_type_col, s_type_kind, s_type_apply,
  s_phone_col, s_phone_apply, s_strip_col, s_strip_apply,
  s_goal_col, s_goal_agg, s_goal_target, s_goal_set, s_search_q,
  s_sort_col, s_sort_dir, s_recent_keep, s_recent_open_{i},
  <key_prefix>_now, <key_prefix>_restore_{i} (render_backups takes a
  key_prefix so the Clean and Tools tabs can both render the backup
  list in one run without duplicate widget keys), s_oneclick_run,
  s_html_dl, s_portfolio_dl, s_chart_png_dl, s_chart_kind,
  s_styled_xlsx_dl

Local files / folders (all inside the app folder, next to this file):
  - recent.json : JSON list of the last 5 recent files
  - recent/     : local copies of files the user asked to keep
  - backups/    : timestamped CSV copies of the raw frame (local mode).
    In cloud mode backups live in Supabase Storage instead (see
    backup_raw / list_backups / restore_backup) and the UI shows
    only the file name, never a server path.
"""

from __future__ import annotations

import html
import io
import json
import math
import re
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd

import engine
import privacy
import storage

try:
    from ui_design import column_type_label as _column_type_label
    from ui_design import info_card as _info_card
except Exception:  # noqa: BLE001 - ui_design is presentation-only
    def _column_type_label(name, dtype):
        return (f'<span class="dcs-coltype">{html.escape(str(name))} '
                f'<span class="dcs-coltype-kind">'
                f"{html.escape(str(dtype))}</span></span>")

    def _info_card(text, st_module=None):
        _st = st_module or st
        _st.markdown(
            '<div style="background:#ffffff;border:1px solid #e8e8e8;'
            'border-radius:12px;padding:1rem 1.25rem;">'
            f"{html.escape(str(text))}</div>",
            unsafe_allow_html=True)

__all__ = [
    "suggest_fixes", "apply_suggestion",
    "override_column_type",
    "standardize_phones", "strip_specials",
    "goal_progress", "search_rows",
    "add_recent", "list_recent", "load_recent",
    "backup_raw", "list_backups", "restore_backup",
    "html_dashboard_bytes", "portfolio_zip_bytes",
    "chart_png_bytes", "to_excel_bytes_styled", "column_type_labels",
    "render_suggestions", "render_type_override",
    "render_standardize_phones", "render_strip_specials",
    "render_goal", "render_search", "render_sort",
    "render_recent", "render_backups", "render_one_click",
    "render_html_download", "render_portfolio_download",
    "render_chart_png", "render_styled_excel_download",
]

# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------

MAX_RECENT = 5
RECENT_FILE = "recent.json"
RECENT_DIR = "recent"
BACKUP_DIR = "backups"

# App checkbox keys -> engine.clean keys (same map as feat_automate,
# copied here so this module stays standalone).
OPT_KEY_MAP = {
    "tidy_names": "tidy_columns",
    "strip": "strip_text",
    "drop_empty": "drop_empty",
    "fix_numbers": "fix_numbers",
    "parse_dates": "fix_dates",
    "fix_categories": "fix_categories",
    "drop_dupes": "drop_duplicates",
    "fill_missing": "fill_missing",
}
CLEAN_OPT_KEYS = list(OPT_KEY_MAP)
DEFAULT_CLEAN_OPTS = {k: True for k in CLEAN_OPT_KEYS}

_BG = "#ffffff"
_GREEN = "#117f50"
_TEXT = "#030303"
_MUTED = "#696969"
_GRID = "#e8e8e8"


def _to_engine_opts(clean_opts):
    """Translate app checkbox keys into the keys engine.clean reads."""
    opts = dict(DEFAULT_CLEAN_OPTS)
    if clean_opts:
        unknown = sorted(set(clean_opts) - set(CLEAN_OPT_KEYS))
        if unknown:
            raise ValueError(f"Unknown cleaning option(s): {', '.join(unknown)}")
        for k, v in clean_opts.items():
            if not isinstance(v, bool):
                raise ValueError(f"Cleaning option '{k}' must be true/false, got {v!r}")
            opts[k] = v
    return {OPT_KEY_MAP[k]: v for k, v in opts.items()}


def _base_dir(base_dir=None) -> Path:
    """App folder (where this file lives), or an explicit override."""
    return Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent


def _text_values(series: pd.Series) -> pd.Series:
    """Non-empty values of a column as stripped strings."""
    vals = series.dropna().astype(object).astype(str).str.strip()
    return vals[vals != ""]


def _looks_date_text(series: pd.Series, ratio: float = 0.8) -> bool:
    """True if ``ratio``+ of the non-empty values parse as dates."""
    vals = _text_values(series)
    if len(vals) == 0:
        return False
    parsed = pd.to_datetime(vals, errors="coerce", format="mixed")
    return bool(parsed.notna().mean() >= ratio)


def _iqr_bounds(s: pd.Series):
    """(lower, upper) IQR bounds for a numeric series, or None when the
    column has too little spread to judge (fewer than 4 values, or IQR 0)."""
    vals = pd.to_numeric(s, errors="coerce").dropna()
    if len(vals) < 4:
        return None
    q1, q3 = vals.quantile(0.25), vals.quantile(0.75)
    iqr = q3 - q1
    if not pd.notna(iqr) or iqr <= 0:
        return None
    return float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)


def _safe_filename(name: str) -> str:
    """Make a filename safe to store on disk (keeps letters, digits,
    dot, dash and underscore)."""
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", str(name).strip())
    safe = safe.strip("._") or "file"
    return safe[:120]


def _fmt_num(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f == int(f) and abs(f) < 10_000_000:
        return f"{int(f):,}"
    return f"{f:,.1f}"


def _display_dtype(series: pd.Series) -> str:
    """A column's dtype in Supabase words — text / numeric / boolean /
    timestamp — falling back to the raw pandas dtype string."""
    dtype = str(series.dtype)
    if dtype in ("object", "str", "string"):
        return "text"
    if dtype.startswith(("int", "float", "Int", "Float")):
        return "numeric"
    if dtype == "bool":
        return "boolean"
    if "datetime" in dtype:
        return "timestamp"
    return dtype


def column_type_labels(df: pd.DataFrame) -> list:
    """One Supabase-style column header per column — ``name text``,
    ``price numeric``: the name in ink, the type in muted monospace
    (see ui_design.column_type_label). Pure HTML strings, no Streamlit
    calls, so the caller can join them into a caption or a table
    header row. The type is part of the table's honesty."""
    if df is None:
        return []
    return [_column_type_label(c, _display_dtype(df[c])) for c in df.columns]


# --------------------------------------------------------------------------
# 1. Smart suggestions
# --------------------------------------------------------------------------

def _phone_digits(value):
    """Digits of a phone-like value, or None when it is not phone-shaped.

    Accepts a 10-digit Indian mobile (starts 6-9), the same number with
    a +91 prefix (12 digits) or a 0 prefix (11 digits)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (int,)):
        text = str(value)
    elif isinstance(value, float) and value == int(value):
        text = str(int(value))
    else:
        text = str(value).strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) == 10 and digits[0] in "6789":
        return digits
    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        return digits[2:]
    if len(digits) == 11 and digits.startswith("0") and digits[1] in "6789":
        return digits[1:]
    return None


def _is_phone_column(series: pd.Series) -> bool:
    """True if >90% of the non-empty values look like phone numbers."""
    vals = _text_values(series)
    if len(vals) == 0:
        return False
    hits = sum(1 for v in vals if _phone_digits(v) is not None)
    return hits / len(vals) > 0.9


def _mixed_case_columns(df: pd.DataFrame) -> dict:
    """{column: (n, (example_a, example_b))} for category columns where
    the same value appears in more than one case (Electronics /
    ELECTRONICS / electronics). n counts the extra cases; the example
    pair is two real values from the column itself, so a suggestion
    about Status never shows Category's values."""
    found = {}
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            continue
        if not (1 < s.nunique(dropna=True) <= 30):
            continue
        vals = _text_values(s)
        if len(vals) == 0:
            continue
        lowered = vals.str.lower()
        for low, group in vals.groupby(lowered):
            if group.nunique() > 1:
                distinct = list(dict.fromkeys(str(v) for v in group))
                pair = (distinct[0], distinct[1])
                if col in found:
                    n, _pair = found[col]
                    found[col] = (n + int(group.nunique() - 1), _pair)
                else:
                    found[col] = (int(group.nunique() - 1), pair)
    return found


def suggest_fixes(df: pd.DataFrame) -> list:
    """Scan a DataFrame's profile and suggest fixes in plain words.

    Returns a list of dicts {title, detail, action} where action is a
    machine-readable dict {"type": ..., "column": ...} that
    apply_suggestion() can run. A column can earn more than one
    suggestion (e.g. mixed case AND extra spaces). The list is capped
    at 12 suggestions, most useful first.
    """
    suggestions = []

    def _add(title, detail, action):
        if len(suggestions) < 12:
            suggestions.append({"title": title, "detail": detail, "action": action})

    if df is None or len(df.columns) == 0:
        return suggestions

    for col in df.columns:
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            continue
        if str(s.dtype) not in ("object", "str"):
            continue
        # Gate on the stored dtype, NOT on engine.detect_kind: a column
        # of plain 10-digit phone numbers looks "numeric" to the guesser
        # and a date-parseable text column looks like a "date" — both
        # still need the suggestion.
        if _is_phone_column(s):
            vals = _text_values(s)
            hits = sum(1 for v in vals if _phone_digits(v) is not None)
            _add(f"This column looks like phone numbers — format them?",
                 f"{hits} of {len(vals)} values in {engine._pretty(col)} "
                 f"look like phone numbers.",
                 {"type": "standardize_phones", "column": str(col)})
        if not engine._looks_numeric(s) and _looks_date_text(s):
            vals = _text_values(s)
            parsed = pd.to_datetime(vals, errors="coerce", format="mixed")
            _add(f"Parse {engine._pretty(col)} as dates?",
                 f"{int(parsed.notna().sum())} of {len(vals)} values in "
                 f"{engine._pretty(col)} look like dates.",
                 {"type": "parse_dates", "column": str(col)})

    for col, (n, (ex_a, ex_b)) in _mixed_case_columns(df).items():
        _add("Set categories to one case",
             f"{engine._pretty(col)} has the same value written in "
             f"{n + 1} different cases — e.g. {ex_a} and {ex_b}.",
             {"type": "set_case_title", "column": str(col)})

    for col in df.columns:
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            continue
        if str(s.dtype) in ("object", "str") and engine._looks_numeric(s):
            _add(f"Turn {engine._pretty(col)} into real numbers?",
                 f"{engine._pretty(col)} looks like numbers stored as text "
                 f"(₹, $ or commas in the way).",
                 {"type": "fix_numbers", "column": str(col)})

    for col in df.columns:
        s = df[col]
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            continue
        vals = s.dropna().astype(object).astype(str)
        messy = sum(1 for v in vals if v != v.strip() or "  " in v)
        if messy:
            _add(f"Tidy up the spaces in {engine._pretty(col)}?",
                 f"{messy} value(s) in {engine._pretty(col)} have extra "
                 f"spaces at the ends or doubled up inside.",
                 {"type": "strip_spaces", "column": str(col)})

    for col in df.columns:
        s = df[col]
        if engine.detect_kind(s) not in ("category", "text"):
            continue
        vals = _text_values(s)
        bad = sum(1 for v in vals
                  if any(not (c.isalnum() or c in " ., -&" or c.isspace()) for c in v))
        if bad:
            _add(f"Strip odd symbols from {engine._pretty(col)}?",
                 f"{bad} value(s) in {engine._pretty(col)} contain emojis "
                 f"or symbols that do not belong in the data.",
                 {"type": "strip_specials", "column": str(col)})

    for col in df.columns:
        missing = int(df[col].isna().sum())
        if missing:
            _add(f"Fill in the {missing} blank(s) in {engine._pretty(col)}?",
                 f"{engine._pretty(col)} has {missing} empty cell(s) — "
                 f"numbers get the middle value, text gets 'Unknown'.",
                 {"type": "fill_missing", "column": str(col)})

    dupes = int(df.duplicated().sum())
    if dupes:
        _add("Drop the duplicate rows?",
             f"{dupes} row(s) are exact copies of another row.",
             {"type": "drop_duplicates", "column": ""})

    for col in df.columns:
        if df[col].isna().all():
            _add(f"Drop the empty column {engine._pretty(col)}?",
                 f"{engine._pretty(col)} is completely empty.",
                 {"type": "drop_empty_column", "column": str(col)})

    return suggestions


def apply_suggestion(df: pd.DataFrame, action: dict) -> tuple:
    """Run one suggestion's machine-readable action.

    action is {"type": ..., "column": ...} as returned by
    suggest_fixes(). Returns (new_df, (step, detail)) for the log.
    Raises ValueError for an unknown action type or a missing column.
    """
    if not isinstance(action, dict) or "type" not in action:
        raise ValueError("Suggestion action must be a dict with a 'type'.")
    atype = action["type"]
    col = action.get("column", "")
    out = df.copy()
    if atype == "drop_duplicates":
        n = int(out.duplicated().sum())
        out = out.drop_duplicates().reset_index(drop=True)
        return out, ("Drop duplicate rows", f"{n} row(s) removed")
    if col not in out.columns:
        raise ValueError(f"Column '{col}' not in the data.")
    if atype == "standardize_phones":
        new_s, changed, skipped = standardize_phones(out[col])
        out[col] = new_s
        return out, (f"Standardize phones: {col}",
                     f"{changed} formatted, {skipped} left unchanged")
    if atype == "set_case_title":
        before = out[col].astype(object).astype(str)
        out[col] = out[col].astype(object).where(
            out[col].isna(), out[col].astype(object).astype(str).str.strip().str.title())
        n = int((before != out[col].astype(object).astype(str)).sum())
        return out, (f"Fix categories: {col}", f"{n} value(s) set to one case")
    if atype == "parse_dates":
        parsed = pd.to_datetime(out[col].astype(object).astype(str),
                                errors="coerce", format="mixed")
        out[col] = parsed
        return out, (f"Parse dates: {col}", f"{int(parsed.notna().sum())} value(s) parsed as dates")
    if atype == "fix_numbers":
        raw = out[col].astype(object).astype(str).str.strip()
        cleaned = raw.str.replace(r"^(₹|\$|€|£|Rs\.?|INR)\s*", "", regex=True, case=False)
        cleaned = cleaned.str.replace(",", "", regex=False).str.replace(r"%$", "", regex=True).str.strip()
        out[col] = pd.to_numeric(cleaned, errors="coerce")
        n = int(((raw != cleaned) & out[col].notna()).sum())
        return out, (f"Fix numbers: {col}", f"{n} value(s) cleaned (₹ $ , % removed)")
    if atype == "strip_spaces":
        before = out[col].astype(object).astype(str)
        fixed = out[col].astype(object).where(
            out[col].isna(),
            out[col].astype(object).astype(str).str.strip().str.replace(r"\s+", " ", regex=True))
        out[col] = fixed
        n = int((before != out[col].astype(object).astype(str)).sum())
        return out, (f"Strip extra spaces: {col}", f"{n} cell(s) trimmed")
    if atype == "strip_specials":
        out[col] = strip_specials(out[col])
        return out, (f"Strip special characters: {col}", "Symbols and emojis removed")
    if atype == "fill_missing":
        missing = int(out[col].isna().sum())
        if pd.api.types.is_numeric_dtype(out[col]):
            # Same rule as engine.clean (engine._median_fill_value):
            # the median, rounded to a whole number for integer-like
            # columns (halves away from zero); genuinely fractional
            # columns keep the fractional median. A column with no
            # values at all has no median, so it stays empty.
            if pd.notna(out[col].median()):
                fill_value, _integer_like = engine._median_fill_value(out[col])
                out[col] = out[col].fillna(fill_value)
            return out, (f"Fill missing: {col}", f"{missing} filled with median")
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            return out, (f"Missing left blank: {col}", f"{missing} date(s) left empty")
        out[col] = out[col].fillna("Unknown")
        return out, (f"Fill missing: {col}", f"{missing} filled with 'Unknown'")
    if atype == "drop_empty_column":
        out = out.drop(columns=[col])
        return out, ("Drop empty columns", f"1: {col}")
    raise ValueError(f"Unknown suggestion action: {atype!r}")


# --------------------------------------------------------------------------
# 2. Column type override
# --------------------------------------------------------------------------

def override_column_type(df: pd.DataFrame, column: str, kind: str) -> pd.DataFrame:
    """Force a column to text / number / date when the app's guess is wrong.

    kind is "text", "number" or "date". Text keeps empty cells empty;
    number strips ₹ $ € £, commas and % before converting (values that
    still do not parse become empty); date parses mixed formats (values
    that do not parse become empty). Raises ValueError for an unknown
    kind or a missing column.
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not in the data.")
    if kind not in ("text", "number", "date"):
        raise ValueError(f"kind must be 'text', 'number' or 'date', got {kind!r}")
    out = df.copy()
    s = out[column]
    if kind == "text":
        out[column] = s.where(s.isna(), s.astype(object).astype(str))
    elif kind == "number":
        raw = s.astype(object).astype(str).str.strip()
        cleaned = raw.str.replace(r"^(₹|\$|€|£|Rs\.?|INR)\s*", "", regex=True, case=False)
        cleaned = cleaned.str.replace(",", "", regex=False).str.replace(r"%$", "", regex=True).str.strip()
        converted = pd.to_numeric(cleaned, errors="coerce")
        out[column] = converted.where(s.notna(), pd.NA)
        out[column] = pd.to_numeric(out[column], errors="coerce")
    else:
        out[column] = pd.to_datetime(s.astype(object).astype(str),
                                     errors="coerce", format="mixed")
    return out


# --------------------------------------------------------------------------
# 3. Standardize phone numbers
# --------------------------------------------------------------------------

def standardize_phones(series: pd.Series) -> tuple:
    """Convert phone values to "+91 98765 43210" shape.

    Handles 10-digit numbers, +91-prefixed, 0-prefixed, and values with
    spaces or dashes. Values that do not parse are left untouched.
    Returns (new_series, n_changed, n_skipped) where n_skipped counts
    the non-empty values that could not be parsed.
    """
    out = series.copy()
    changed = 0
    skipped = 0
    for idx, value in series.items():
        if pd.isna(value):
            continue
        text = str(value).strip()
        if not text:
            continue
        digits = _phone_digits(value)
        if digits is None:
            skipped += 1
            continue
        formatted = f"+91 {digits[:5]} {digits[5:]}"
        if formatted != text:
            changed += 1
        out.loc[idx] = formatted
    return out, changed, skipped


# --------------------------------------------------------------------------
# 4. Strip special characters
# --------------------------------------------------------------------------

def strip_specials(series: pd.Series) -> pd.Series:
    """Remove emojis and symbols from text, keeping letters, digits,
    spaces and basic punctuation (., - &). Extra spaces are collapsed
    to one and trimmed. Empty cells stay empty; non-text values pass
    through unchanged."""
    def _clean(value):
        if pd.isna(value) or not isinstance(value, str):
            return value
        kept = "".join(c for c in value
                       if c.isalnum() or c in " ., -&" or c.isspace())
        return re.sub(r"\s+", " ", kept).strip()
    return series.map(_clean)


# --------------------------------------------------------------------------
# 5. Goal tracking
# --------------------------------------------------------------------------

def goal_progress(df: pd.DataFrame, column: str, agg: str, target) -> tuple:
    """Progress towards a KPI target.

    agg is "Sum", "Average" or "Count" on a numeric column. Returns
    (value, pct) where pct is value / target * 100 (not capped — going
    over target shows over 100%). Raises ValueError for a missing
    column, an unknown agg, a non-numeric target, or a target of 0.
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not in the data.")
    if agg not in ("Sum", "Average", "Count"):
        raise ValueError(f"agg must be 'Sum', 'Average' or 'Count', got {agg!r}")
    try:
        target_f = float(target)
    except (TypeError, ValueError):
        raise ValueError(f"Target must be a number, got {target!r}")
    if target_f == 0:
        raise ValueError("Target cannot be 0.")
    value = float(engine.custom_kpi(df, column, agg))
    return value, float(value / target_f * 100)


# --------------------------------------------------------------------------
# 6. Search the whole file
# --------------------------------------------------------------------------

def search_rows(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """Rows where ANY column contains the query (case-insensitive).

    A blank query returns every row. Empty cells never match.
    """
    if query is None or not str(query).strip():
        return df.copy()
    q = str(query).strip().lower()
    mask = pd.Series(False, index=df.index)
    for col in df.columns:
        text = df[col].where(df[col].notna(), "").astype(object).astype(str).str.lower()
        mask = mask | text.str.contains(q, regex=False)
    return df.loc[mask].reset_index(drop=True)


# --------------------------------------------------------------------------
# 8. Recent files
# --------------------------------------------------------------------------

def _recent_json_path(base_dir=None) -> Path:
    return _base_dir(base_dir) / RECENT_FILE


def _read_recent(base_dir=None) -> list:
    path = _recent_json_path(base_dir)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError, UnicodeDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict) and e.get("name")]


def _write_recent(entries, base_dir=None):
    _recent_json_path(base_dir).write_text(
        json.dumps(entries, indent=2), encoding="utf-8")


def add_recent(name, df_bytes_or_path, base_dir=None) -> dict:
    """Save a file copy into the app-local ``recent/`` folder and record
    it in recent.json (newest first, last 5 kept).

    df_bytes_or_path is file bytes, a path to an existing file, or a
    DataFrame (saved as CSV). Returns the entry dict
    {name, filename, when, where}. Raises ValueError for an empty name
    and FileNotFoundError for a missing path.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Recent files need a non-empty name.")
    name = name.strip()
    base = _base_dir(base_dir)
    folder = base / RECENT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    if isinstance(df_bytes_or_path, pd.DataFrame):
        data = df_bytes_or_path.to_csv(index=False).encode("utf-8")
        filename = _safe_filename(name)
        if not filename.lower().endswith(".csv"):
            filename += ".csv"
    elif isinstance(df_bytes_or_path, (bytes, bytearray)):
        data = bytes(df_bytes_or_path)
        filename = _safe_filename(name)
    elif isinstance(df_bytes_or_path, (str, Path)):
        src = Path(df_bytes_or_path)
        if not src.exists():
            raise FileNotFoundError(f"No such file: {src}")
        data = src.read_bytes()
        filename = _safe_filename(name)
    else:
        raise ValueError("df_bytes_or_path must be bytes, a file path, or a DataFrame.")
    stem, dot, ext = filename.rpartition(".")
    candidate = filename
    n = 2
    while (folder / candidate).exists():
        candidate = f"{stem}_{n}.{ext}" if dot else f"{filename}_{n}"
        n += 1
    filename = candidate
    (folder / filename).write_bytes(data)
    entry = {"name": name, "filename": filename,
             "when": datetime.now().isoformat(timespec="seconds"),
             "where": f"{RECENT_DIR}/{filename}"}
    entries = [e for e in _read_recent(base_dir) if e.get("name") != name]
    entries.insert(0, entry)
    _write_recent(entries[:MAX_RECENT], base_dir)
    return entry


def list_recent(base_dir=None) -> list:
    """The recent-files list, newest first ([] when there is none)."""
    return _read_recent(base_dir)


def load_recent(name, base_dir=None) -> pd.DataFrame:
    """Re-open a recent file by its name (or stored filename) and
    return it as a DataFrame. Raises ValueError when the name is not
    in the list or its saved copy is gone."""
    entries = _read_recent(base_dir)
    match = next((e for e in entries
                  if e.get("name") == name or e.get("filename") == name), None)
    if match is None:
        raise ValueError(f"'{name}' is not in the recent files list.")
    path = _base_dir(base_dir) / RECENT_DIR / match["filename"]
    if not path.exists():
        raise ValueError(f"The saved copy of '{name}' is gone "
                         f"({match['filename']} no longer exists).")
    return engine.load_file(match["filename"], path.read_bytes())


# --------------------------------------------------------------------------
# 9. Backup before cleaning
# --------------------------------------------------------------------------

def backup_raw(df: pd.DataFrame, source_name, base_dir=None,
               storage_key=None) -> str:
    """Save a copy of the raw frame, named with a timestamp, e.g.
    messy_sales_2026-11-06_0130.csv. Returns the stored path as a
    string: the local file path in local mode, the Supabase Storage
    object path in cloud mode (when ``storage_key`` is given and the
    app runs in Supabase mode — backups then survive a redeploy).
    Callers must NEVER show this return value to the user: the UI
    shows only the file name (see render_backups / render_one_click),
    never a server path."""
    stem = Path(str(source_name or "data")).stem
    slug = _safe_filename(stem) or "data"
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    candidate = f"{slug}_{stamp}.csv"
    n = 2
    if storage_key is not None and storage._is_supabase_mode():
        while candidate in storage.list_files(storage_key, "backups"):
            candidate = f"{slug}_{stamp}_{n}.csv"
            n += 1
        data = df.to_csv(index=False).encode("utf-8")
        return str(storage.save_file(storage_key, "backups", candidate,
                                    data))
    base = _base_dir(base_dir)
    folder = base / BACKUP_DIR
    folder.mkdir(parents=True, exist_ok=True)
    while (folder / candidate).exists():
        candidate = f"{slug}_{stamp}_{n}.csv"
        n += 1
    path = folder / candidate
    df.to_csv(path, index=False)
    return str(path)


def list_backups(base_dir=None, storage_key=None) -> list:
    """Backups, newest first: [{name, path, when, size_bytes}].

    In cloud mode (``storage_key`` given and Supabase mode on) the
    list comes from Supabase Storage; "when" and "size_bytes" are
    not reported by a Storage listing, so they come back as "" /
    None and the UI omits them. In local mode the entries carry the
    local file path, mtime and size as before."""
    if storage_key is not None and storage._is_supabase_mode():
        return [{"name": name, "path": name, "when": "",
                 "size_bytes": None}
                for name in storage.list_files(storage_key, "backups")]
    folder = _base_dir(base_dir) / BACKUP_DIR
    if not folder.exists():
        return []
    out = []
    for path in sorted(folder.glob("*.csv"),
                       key=lambda p: p.stat().st_mtime, reverse=True):
        out.append({"name": path.name, "path": str(path),
                    "when": datetime.fromtimestamp(
                        path.stat().st_mtime).isoformat(timespec="seconds"),
                    "size_bytes": path.stat().st_size})
    return out


def restore_backup(path, base_dir=None, storage_key=None) -> pd.DataFrame:
    """Load a backup CSV back into a DataFrame. Raises
    FileNotFoundError when the file is gone.

    ``path`` is an entry's "path" from list_backups: a local file
    path in local mode, a bare backup name in cloud mode (read back
    from Supabase Storage when ``storage_key`` is given). A bare
    name in local mode is resolved under ``base_dir``/backups/."""
    if storage_key is not None and storage._is_supabase_mode():
        name = Path(str(path)).name
        data = storage.read_file(storage_key, "backups", name)
        return engine.load_file(name, data)
    path = Path(path)
    if not path.exists() and base_dir is not None:
        candidate = _base_dir(base_dir) / BACKUP_DIR / path.name
        if candidate.exists():
            path = candidate
    if not path.exists():
        raise FileNotFoundError(f"No such backup file: {path}")
    return engine.load_file(path.name, path.read_bytes())


# --------------------------------------------------------------------------
# 11. Standalone HTML dashboard
# --------------------------------------------------------------------------

def _svg_bar_chart(grouped_df, x_col, y_col, title, accent="#117f50") -> str:
    """Inline SVG vertical bar chart, hand-drawn (no JS, no libraries).
    White theme, bars in the accent colour (deep green by default)."""
    if grouped_df is None or len(grouped_df) == 0 or x_col not in grouped_df.columns \
            or y_col not in grouped_df.columns:
        return "<p>No chart data yet — clean the data and pick a group and a number first.</p>"
    bar_color = accent if isinstance(accent, str) and accent.startswith("#") \
        and len(accent) == 7 else "#117f50"
    data = grouped_df.head(12).copy()
    labels = [str(v)[:18] for v in data[x_col]]
    values = [float(v) for v in pd.to_numeric(data[y_col], errors="coerce").fillna(0)]
    top = max(values) if values else 0
    if top <= 0:
        return "<p>No chart data yet — the numbers add up to zero.</p>"
    w, h = 960, 420
    left, bottom, top_pad = 70, 60, 30
    plot_w, plot_h = w - left - 20, h - top_pad - bottom
    slot = plot_w / max(len(values), 1)
    bar_w = max(8, slot * 0.6)
    parts = [f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
             f'role="img" aria-label="{html.escape(str(title))}">']
    parts.append(f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>')
    for frac in (0.25, 0.5, 0.75, 1.0):
        y = top_pad + plot_h * (1 - frac)
        parts.append(f'<line x1="{left}" y1="{y:.0f}" x2="{w - 20}" y2="{y:.0f}" '
                     f'stroke="#e8e8e8" stroke-width="1"/>')
        parts.append(f'<text x="{left - 8}" y="{y + 4:.0f}" fill="#696969" '
                     f'font-size="12" text-anchor="end">{_fmt_num(top * frac)}</text>')
    for i, (label, value) in enumerate(zip(labels, values)):
        bh = plot_h * value / top
        x = left + slot * i + (slot - bar_w) / 2
        y = top_pad + plot_h - bh
        parts.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{bar_w:.0f}" '
                     f'height="{bh:.0f}" fill="{bar_color}" rx="3"/>')
        parts.append(f'<text x="{x + bar_w / 2:.0f}" y="{y - 6:.0f}" fill="#030303" '
                     f'font-size="12" text-anchor="middle">{_fmt_num(value)}</text>')
        parts.append(f'<text x="{x + bar_w / 2:.0f}" y="{h - bottom + 20:.0f}" fill="#030303" '
                     f'font-size="12" text-anchor="middle">{html.escape(label)}</text>')
    parts.append(f'<line x1="{left}" y1="{top_pad + plot_h}" x2="{w - 20}" '
                 f'y2="{top_pad + plot_h}" stroke="#696969" stroke-width="1"/>')
    parts.append("</svg>")
    return "\n".join(parts)


def html_dashboard_bytes(kpis, actions, grouped_df, x_col, y_col,
                         title="Data Cleaner Studio — Dashboard",
                         brand=None) -> bytes:
    """One self-contained HTML file: inline CSS only, no external links,
    no JavaScript libraries. Contains the KPI cards, the cleaning
    summary, and the main grouped bar chart as hand-drawn inline SVG.
    Returns the file as UTF-8 bytes.

    ``brand`` is optional: None behaves exactly as before. A brand
    dict {"name", "accent", ...} (see feat_brand.brand_for_exports)
    replaces "Data Cleaner Studio" with the brand name in the title
    and footer, and uses the accent colour for headings and bars."""
    kpis = kpis or []
    actions = actions or []
    brand_name = None
    accent = "#117f50"
    if isinstance(brand, dict):
        name = brand.get("name")
        if isinstance(name, str) and name.strip():
            brand_name = name.strip()
        acc = brand.get("accent")
        if isinstance(acc, str) and acc.startswith("#") and len(acc) == 7:
            accent = acc
    if brand_name:
        title = str(title).replace("Data Cleaner Studio", brand_name)
    footer_name = brand_name or "Data Cleaner Studio"
    cards = "\n".join(
        f'<div class="card"><div class="kpi-label">{html.escape(str(k.get("label", "")))}</div>'
        f'<div class="kpi-value">{html.escape(str(k.get("value", "")))}</div></div>'
        for k in kpis) or "<p>No KPIs yet.</p>"
    log = "\n".join(
        f"<li><strong>{html.escape(str(step))}:</strong> {html.escape(str(detail))}</li>"
        for step, detail in actions) or "<li>Nothing cleaned yet.</li>"
    chart_title = f"{engine._pretty(y_col)} by {engine._pretty(x_col)}" \
        if x_col and y_col else str(title)
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(str(title))}</title>
<style>
body {{ background: #ffffff; color: #030303; font-family: Arial, Helvetica, sans-serif; margin: 0; padding: 24px; }}
h1 {{ color: {accent}; font-size: 28px; margin: 0 0 4px 0; }}
p.sub {{ color: #696969; margin: 0 0 24px 0; }}
h2 {{ color: {accent}; font-size: 20px; margin: 28px 0 12px 0; }}
.cards {{ display: flex; flex-wrap: wrap; gap: 12px; }}
.card {{ background: #ffffff; border: 1px solid #e8e8e8; border-radius: 10px; padding: 16px 20px; min-width: 160px; }}
.kpi-label {{ color: #696969; font-size: 13px; }}
.kpi-value {{ color: #030303; font-size: 22px; font-weight: bold; margin-top: 4px; }}
ul {{ line-height: 1.7; }}
.chart {{ background: #ffffff; border: 1px solid #e8e8e8; border-radius: 10px; padding: 12px; overflow-x: auto; }}
footer {{ color: #696969; font-size: 12px; margin-top: 28px; }}
</style>
</head>
<body>
<h1>{html.escape(str(title))}</h1>
<p class="sub">Standalone dashboard — open this file in any browser, no internet needed.</p>
<h2>KPIs</h2>
<div class="cards">
{cards}
</div>
<h2>What was cleaned</h2>
<ul>
{log}
</ul>
<h2>{html.escape(chart_title)}</h2>
<div class="chart">
{_svg_bar_chart(grouped_df, x_col, y_col, chart_title, accent=accent)}
</div>
<footer>Generated by {html.escape(footer_name)}. {privacy.data_location_line()}</footer>
</body>
</html>
"""
    return page.encode("utf-8")


# --------------------------------------------------------------------------
# 13. Chart as image (PIL)
# --------------------------------------------------------------------------

def _chart_font(size=14, bold=False):
    """Best available font: DejaVu when present, else PIL's default."""
    try:
        from PIL import ImageFont
        for name in ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
                     "arial.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()
    except Exception:
        from PIL import ImageFont
        return ImageFont.load_default()


def _text_w(draw, text, font) -> int:
    try:
        return int(draw.textlength(text, font=font))
    except Exception:
        box = draw.textbbox((0, 0), text, font=font)
        return box[2] - box[0]


def chart_png_bytes(grouped_df, x_col, y_col, title,
                    kind="bar") -> bytes:
    """Draw a clean bar or line chart with PIL and return PNG bytes.

    1200x675, white theme (#ffffff background, deep-green #117f50 bars /
    line), axes, labels and values. No matplotlib, no vl-convert.
    kind is "bar" or "line". Raises ValueError for an unknown kind.
    """
    if kind not in ("bar", "line"):
        raise ValueError(f"kind must be 'bar' or 'line', got {kind!r}")
    from PIL import Image, ImageDraw

    w, h = 1200, 675
    img = Image.new("RGB", (w, h), _BG)
    draw = ImageDraw.Draw(img)
    title_font = _chart_font(30, bold=True)
    label_font = _chart_font(16)
    small_font = _chart_font(14)
    draw.text((40, 24), str(title)[:60], fill=_TEXT, font=title_font)

    left, right, top, bottom = 100, 40, 100, 110
    plot_w, plot_h = w - left - right, h - top - bottom
    draw.rectangle([left, top, left + plot_w, top + plot_h], outline=_GRID)
    if grouped_df is None or len(grouped_df) == 0 \
            or x_col not in grouped_df.columns or y_col not in grouped_df.columns:
        msg = "No data to chart yet."
        draw.text((left + plot_w // 2 - _text_w(draw, msg, label_font) // 2,
                   top + plot_h // 2), msg, fill=_MUTED, font=label_font)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    data = grouped_df.head(12).copy()
    labels = [str(v)[:14] for v in data[x_col]]
    values = [float(v) for v in pd.to_numeric(data[y_col], errors="coerce").fillna(0)]
    top_v = max(values) if values else 0
    if top_v <= 0:
        top_v = 1.0
    # gridlines + y labels
    for frac in (0.25, 0.5, 0.75, 1.0):
        y = top + plot_h * (1 - frac)
        draw.line([(left, y), (left + plot_w, y)], fill=_GRID)
        lab = _fmt_num(top_v * frac)
        draw.text((left - 12 - _text_w(draw, lab, small_font), y - 8),
                  lab, fill=_MUTED, font=small_font)
    draw.text((12, top + plot_h // 2 - 40), str(y_col)[:20], fill=_MUTED,
              font=small_font)
    n = len(values)
    slot = plot_w / max(n, 1)
    points = []
    for i, (label, value) in enumerate(zip(labels, values)):
        cx = left + slot * i + slot / 2
        y_val = top + plot_h * (1 - value / top_v)
        points.append((cx, y_val))
        if kind == "bar":
            bar_w = max(10, slot * 0.6)
            draw.rectangle([cx - bar_w / 2, y_val, cx + bar_w / 2, top + plot_h],
                           fill=_GREEN)
        vlab = _fmt_num(value)
        draw.text((cx - _text_w(draw, vlab, small_font) // 2, y_val - 24),
                  vlab, fill=_TEXT, font=small_font)
        draw.text((cx - _text_w(draw, label, small_font) // 2, top + plot_h + 12),
                  label, fill=_TEXT, font=small_font)
    if kind == "line":
        if len(points) > 1:
            draw.line(points, fill=_GREEN, width=4)
        for cx, cy in points:
            r = 7
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_GREEN)
    draw.line([(left, top + plot_h), (left + plot_w, top + plot_h)], fill=_MUTED)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------
# 12. Publish to portfolio
# --------------------------------------------------------------------------

def _portfolio_chart(cleaned: pd.DataFrame):
    """(png_bytes, filename) for the portfolio ZIP, or (None, None)
    when there is no category + number pair to chart."""
    cat_cols = [c for c in cleaned.columns
                if str(cleaned[c].dtype) in ("object", "str")
                and 1 < cleaned[c].nunique(dropna=True) <= 30]
    num_cols = engine.numeric_cols(cleaned)
    if not cat_cols or not num_cols:
        return None, None
    x_col, y_col = cat_cols[0], num_cols[0]
    grouped = (cleaned.groupby(x_col, dropna=False)[y_col].sum()
               .reset_index().sort_values(y_col, ascending=False))
    png = chart_png_bytes(grouped, x_col, y_col,
                          f"{engine._pretty(y_col)} by {engine._pretty(x_col)}")
    return png, f"chart_{y_col}_by_{x_col}.png"


def portfolio_zip_bytes(cleaned: pd.DataFrame, kpis, actions, title) -> bytes:
    """Package a case study as a ZIP (stdlib zipfile): cleaned_data.csv,
    an auto-written README.md (what the data was, what was cleaned,
    top KPIs, in plain words), and a chart PNG when the data has a
    category + number pair to chart. Returns the ZIP as bytes."""
    kpis = kpis or []
    actions = actions or []
    lines = [f"# {title}", "",
             "A data-cleaning case study made with Data Cleaner Studio.", "",
             "## What the data was",
             f"The file had {len(cleaned):,} rows and {len(cleaned.columns)} columns: "
             + ", ".join(str(c) for c in cleaned.columns) + ".", "",
             "## What was cleaned"]
    if actions:
        for step, detail in actions:
            lines.append(f"- **{step}**: {detail}")
    else:
        lines.append("- Nothing cleaned yet.")
    lines += ["", "## Top KPIs"]
    if kpis:
        for k in kpis:
            lines.append(f"- **{k.get('label', '')}**: {k.get('value', '')}")
    else:
        lines.append("- No KPIs yet.")
    lines += ["", f"_Made with Data Cleaner Studio. {privacy.data_location_line()}_"]
    readme = "\n".join(lines)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("cleaned_data.csv", cleaned.to_csv(index=False))
        z.writestr("README.md", readme)
        png, fname = _portfolio_chart(cleaned)
        if png is not None:
            z.writestr(fname, png)
    return buf.getvalue()


# --------------------------------------------------------------------------
# 14. Conditional colours in exports
# --------------------------------------------------------------------------

def to_excel_bytes_styled(cleaned: pd.DataFrame, kpis, actions) -> bytes:
    """Excel export where bad cells are highlighted and good ones are not.

    Missing values -> light red fill; numeric outliers (IQR rule) ->
    light red fill; everything else plain. The header row gets a light
    green fill (the data rows are never painted green). Sheets: Cleaned
    Data, KPIs, Cleaning Log. Returns the workbook as bytes.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    red_fill = PatternFill("solid", fgColor="FFC7CE")
    red_font = Font(color="9C0006")
    green_fill = PatternFill("solid", fgColor="C6EFCE")
    green_font = Font(color="006100", bold=True)

    bounds = {col: _iqr_bounds(cleaned[col])
              for col in engine.numeric_cols(cleaned)}
    wb = Workbook()
    ws = wb.active
    ws.title = "Cleaned Data"
    ws.append([str(c) for c in cleaned.columns])
    for cell in ws[1]:
        cell.fill = green_fill
        cell.font = green_font
    for _, row in cleaned.iterrows():
        ws.append(list(row))
    ws.freeze_panes = "A2"
    for c_idx, col in enumerate(cleaned.columns, start=1):
        width = max([len(str(col))] + [len(str(v)) for v in cleaned[col].head(50)
                                        if pd.notna(v)] + [8])
        ws.column_dimensions[ws.cell(row=1, column=c_idx).column_letter].width = min(32, width + 2)
    for r_idx in range(2, ws.max_row + 1):
        for c_idx, col in enumerate(cleaned.columns, start=1):
            cell = ws.cell(row=r_idx, column=c_idx)
            val = cell.value
            is_missing = val is None or (isinstance(val, float) and math.isnan(val)) \
                or (isinstance(val, str) and val.strip() == "")
            if is_missing:
                cell.fill = red_fill
                cell.font = red_font
                continue
            b = bounds.get(col)
            if b is not None and isinstance(val, (int, float)) \
                    and not isinstance(val, bool):
                lower, upper = b
                if val < lower or val > upper:
                    cell.fill = red_fill
                    cell.font = red_font
    ws_k = wb.create_sheet("KPIs")
    ws_k.append(["Label", "Value"])
    for cell in ws_k[1]:
        cell.fill = green_fill
        cell.font = green_font
    for k in (kpis or []):
        ws_k.append([k.get("label", ""), k.get("value", "")])
    ws_l = wb.create_sheet("Cleaning Log")
    ws_l.append(["Step", "Detail"])
    for cell in ws_l[1]:
        cell.fill = green_fill
        cell.font = green_font
    for step, detail in (actions or []):
        ws_l.append([step, detail])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------
# render functions — thin Streamlit wrappers (st passed in, never imported)
# --------------------------------------------------------------------------

def render_suggestions(st, df: pd.DataFrame):
    """Preview tab: plain-words fix suggestions, one card each with an
    Apply button where the fix is safe and one-click. Returns
    (new_df, new_actions) when a suggestion is applied, else (None, []).
    The integrator applies the returned frame like any other fix-up."""
    st.subheader("Suggestions")
    st.write("Things we spotted in your data — press Apply on any fix "
             "you want, one at a time.")
    suggestions = suggest_fixes(df)
    if not suggestions:
        st.info("No suggestions — nothing obvious left to fix in this file.")
        return None, []
    for i, sugg in enumerate(suggestions):
        st.write(f"**{sugg['title']}**")
        st.write(sugg["detail"])
        if st.button("Apply this fix", key=f"s_sugg_apply_{i}"):
            new_df, action = apply_suggestion(df, sugg["action"])
            st.success(f"Done — {action[0]}: {action[1]}. The raw file "
                       "is untouched.")
            return new_df, [action]
    return None, []


def render_type_override(st, df: pd.DataFrame):
    """Clean tab: force a column to text / number / date when the app's
    guess is wrong. Returns the overridden frame when Apply is pressed,
    else None."""
    st.subheader("Column type override")
    st.write("If the app guessed a column's type wrong, force it here — "
             "text, number or date.")
    col = st.selectbox("Column", list(df.columns), key="s_type_col")
    # Supabase table honesty: show the column with its current type.
    st.markdown(_column_type_label(col, _display_dtype(df[col])),
                unsafe_allow_html=True)
    kind_label = st.selectbox("Force it to be",
                              ["text", "number", "date"], key="s_type_kind")
    if st.button("Apply type", key="s_type_apply"):
        new_df = override_column_type(df, col, kind_label)
        st.success(f"{engine._pretty(col)} is now {kind_label} "
                   f"({new_df[col].dtype}).")
        return new_df
    return None


def render_standardize_phones(st, df: pd.DataFrame):
    """Clean tab: pick a column and format every phone number in it as
    +91 98765 43210. Values that do not parse are left untouched and
    counted. Returns (new_df, new_actions) on Apply, else (None, [])."""
    text_cols = [c for c in df.columns if str(df[c].dtype) in ("object", "str")]
    if not text_cols:
        st.info("No text column in this file to format phone numbers in.")
        return None, []
    st.subheader("Standardize phone numbers")
    st.write("Formats numbers as +91 98765 43210 — handles 10-digit, "
             "+91 and 0-prefixed numbers, with spaces or dashes. Anything "
             "that does not look like a phone number is left alone.")
    col = st.selectbox("Phone column", text_cols, key="s_phone_col")
    if st.button("Format phone numbers", key="s_phone_apply"):
        new_s, changed, skipped = standardize_phones(df[col])
        new_df = df.copy()
        new_df[col] = new_s
        action = (f"Standardize phones: {col}",
                  f"{changed} formatted, {skipped} left unchanged")
        st.success(f"Done — {changed} number(s) formatted as +91 …, "
                   f"{skipped} left unchanged in '{col}'.")
        return new_df, [action]
    return None, []


def render_strip_specials(st, df: pd.DataFrame):
    """Clean tab: pick a text column and strip emojis and symbols from
    it (keeps letters, digits, spaces and ., - &). Returns
    (new_df, new_actions) on Apply, else (None, [])."""
    text_cols = [c for c in df.columns if str(df[c].dtype) in ("object", "str")]
    if not text_cols:
        st.info("No text column in this file to strip symbols from.")
        return None, []
    st.subheader("Strip special characters")
    st.write("Removes emojis and symbols from a text column. Letters, "
             "digits, spaces and basic punctuation (., - &) are kept.")
    col = st.selectbox("Text column", text_cols, key="s_strip_col")
    if st.button("Strip symbols", key="s_strip_apply"):
        new_df = df.copy()
        new_df[col] = strip_specials(df[col])
        action = (f"Strip special characters: {col}",
                  "Symbols and emojis removed")
        st.success(f"Done — symbols and emojis removed from '{col}'; "
                   "letters, digits, spaces and ., - & are kept.")
        return new_df, [action]
    return None, []


def render_goal(st, df: pd.DataFrame):
    """KPIs tab: pick a KPI (numeric column + Sum / Average / Count)
    and a target value; shows progress as a bar with "X of target (Y%)"
    in plain words. Returns (value, pct), or None when there is no
    numeric column."""
    num_cols = engine.numeric_cols(df)
    if not num_cols:
        st.info("No number columns in this file, so there is no KPI to "
                "track.")
        return None
    st.subheader("Goal tracking")
    st.write("Pick a number to track and a target — the bar shows how "
             "far along you are.")
    saved = st.session_state.get("s_goal_data") or {}
    col = st.selectbox("KPI column", num_cols, key="s_goal_col")
    agg = st.selectbox("Measure", ["Sum", "Average", "Count"], key="s_goal_agg")
    default_target = float(saved.get("target", 100000)) if saved else 100000.0
    target = st.number_input("Target value", key="s_goal_target",
                             value=default_target)
    if st.button("Set goal", key="s_goal_set"):
        st.session_state["s_goal_data"] = {"column": col, "agg": agg,
                                           "target": float(target)}
    value, pct = goal_progress(df, col, agg, target)
    st.write(f"{_fmt_num(value)} of {_fmt_num(target)} ({pct:.1f}%)")
    st.progress(min(max(pct, 0.0), 100.0) / 100.0)
    if pct >= 100:
        st.success(f"Goal reached — {_fmt_num(value)} of "
                   f"{_fmt_num(target)} ({pct:.1f}%).")
    elif pct >= 50:
        st.write("Over halfway there.")
    else:
        st.write("Still a way to go.")
    return value, pct


def render_search(st, df: pd.DataFrame):
    """Preview tab: one search box over the whole file — any column,
    case-insensitive. Returns the matching rows when a query is typed,
    else None."""
    st.subheader("Search the whole file")
    query = st.text_input("Search", key="s_search_q",
                          placeholder="Type anything — a name, a product, a number…")
    if not query or not str(query).strip():
        st.write("Type above to search every column at once.")
        return None
    matches = search_rows(df, query)
    st.write(f"{len(matches):,} of {len(df):,} rows match "
             f"'{str(query).strip()}'.")
    if len(matches) == 0:
        st.info(f"Nothing matches '{str(query).strip()}' in {len(df):,} "
                "rows — try a shorter word.")
    else:
        st.dataframe(matches.head(100), width="stretch")
    return matches


def render_sort(st, df: pd.DataFrame):
    """Preview tab: sort the preview honestly with controls (Streamlit's
    st.dataframe has no clickable headers). Pick a column and a
    direction; returns the sorted frame."""
    st.subheader("Sort the preview")
    st.write("Pick a column and a direction — the table below follows it.")
    col = st.selectbox("Sort by", list(df.columns), key="s_sort_col")
    direction = st.radio("Direction", ["Ascending", "Descending"],
                         key="s_sort_dir")
    try:
        out = df.sort_values(col, ascending=(direction == "Ascending"),
                             kind="stable", na_position="last")
    except Exception as e:  # noqa: BLE001 - mixed types cannot sort
        st.error(f"Could not sort by {engine._pretty(col)}: {e}")
        return df.copy()
    return out.reset_index(drop=True)


def render_recent(st, df=None, source_name="", raw_bytes=None, base_dir=None,
                  storage_key=None):
    """Sidebar (Load section): recent files, newest first.

    Pass df/source_name/raw_bytes for the file just loaded: when the
    user ticks "Keep a copy for quick reopen" (default off) a local
    copy is saved into the app-local ``recent/`` folder and listed.
    Without that tick nothing is saved — an uploaded file cannot be
    re-opened from a browser upload, and the list says so honestly.
    The tick itself is remembered per user (``storage_key`` ->
    views/recent_prefs.json, the same pattern as the What's-new
    dismiss) so it survives logout/login; without a storage key it
    just lasts the session. Returns the stored frame when an Open
    button is pressed, else None — and records the opened file's
    name in session state ("s_recent_opened") so the caller can
    restore matching cleaned state for it.
    """
    st.subheader("Recent files")
    if raw_bytes is not None:
        stored_keep = None
        if storage_key is not None:
            try:
                _prefs = storage.load_json(storage_key, "views",
                                           "recent_prefs.json")
                stored_keep = (bool(_prefs.get("keep_copy", False))
                               if isinstance(_prefs, dict) else False)
            except Exception:  # noqa: BLE001 - a lost pref is not fatal
                stored_keep = False
            if "s_recent_keep" not in st.session_state:
                try:
                    st.session_state["s_recent_keep"] = stored_keep
                except Exception:  # noqa: BLE001 - never crash the sidebar
                    pass
        keep = st.checkbox("Keep a copy for quick reopen",
                           key="s_recent_keep",
                           help="Saves a copy of this file in the app's "
                                "recent folder, so you can re-open it "
                                "later without uploading again. Off by "
                                "default.")
        if (storage_key is not None and stored_keep is not None
                and bool(keep) != stored_keep):
            try:
                storage.save_json(storage_key, "views", "recent_prefs.json",
                                  {"keep_copy": bool(keep)})
            except Exception:  # noqa: BLE001 - a lost pref is not fatal
                pass
        if keep and source_name:
            saved = st.session_state.get("s_recent_saved") or []
            if source_name not in saved:
                add_recent(source_name, raw_bytes, base_dir)
                saved = saved + [source_name]
                st.session_state["s_recent_saved"] = saved
                st.success(f"Saved {source_name} for quick reopen — it "
                           "will appear in Recent files below.")
    entries = list_recent(base_dir)
    if not entries:
        _info_card("No recent files yet. Tick 'Keep a copy for quick "
                   "reopen' when you load a file and it will appear "
                   "here.")
        return None
    for i, entry in enumerate(entries):
        st.write(f"**{entry['name']}** — {entry.get('when', '')} — "
                 f"{entry.get('where', '')}")
        if st.button("Open", key=f"s_recent_open_{i}"):
            try:
                opened = load_recent(entry["name"], base_dir)
            except Exception as e:  # noqa: BLE001 - show, don't crash
                st.error(str(e))
                return None
            try:
                st.session_state["s_recent_opened"] = entry["name"]
            except Exception:  # noqa: BLE001 - never crash the sidebar
                pass
            st.success(f"Opened {entry['name']} ({len(opened):,} rows).")
            return opened
    return None


def render_backups(st, df=None, source_name="", base_dir=None,
                   storage_key=None, key_prefix="s_backup"):
    """Clean tab (top, BEFORE the Clean button) and Tools tab: back up
    the raw data and restore an earlier backup.

    Pass df + source_name to offer "Back up the raw data now". Returns
    the restored frame when a Restore button is pressed, else None.
    Backups are named <name>_YYYY-MM-DD_HHMM.csv. In cloud mode
    (``storage_key`` given and Supabase mode on) they are stored in
    Supabase Storage under backups/ — never on the server's disk —
    and the UI shows only the file name, never a server path. In
    local mode they live in the app-local ``backups/`` folder and
    the UI still shows only the file name.

    ``key_prefix`` namespaces every widget key in this call: the app
    renders the backup list twice per run (Clean tab + Tools tab),
    so each call MUST use its own prefix or Streamlit raises
    StreamlitDuplicateElementKey as soon as any backup exists.
    """
    st.subheader("Backups")
    st.write("A safety copy of your raw data, saved before cleaning — "
             "so you can always go back to the original file.")
    if df is not None:
        if st.button("Back up the raw data now", key=f"{key_prefix}_now"):
            path = backup_raw(df, source_name or "data", base_dir,
                              storage_key=storage_key)
            st.success(f"Backed up {Path(str(path)).name} "
                       f"({len(df):,} rows) — restore it any time from the "
                       "list below.")
    entries = list_backups(base_dir, storage_key=storage_key)
    if not entries:
        st.info("No backups yet — back up the raw data before cleaning.")
        return None
    for i, entry in enumerate(entries):
        _line = f"**{entry['name']}**"
        if entry.get("when"):
            _line += f" — {entry['when']}"
        if entry.get("size_bytes") is not None:
            _line += f" — {entry['size_bytes']:,} bytes"
        st.write(_line)
        if st.button("Restore", key=f"{key_prefix}_restore_{i}"):
            try:
                restored = restore_backup(entry["path"], base_dir=base_dir,
                                          storage_key=storage_key)
            except Exception as e:  # noqa: BLE001 - show, don't crash
                st.error(str(e))
                return None
            st.success(f"Restored {entry['name']} ({len(restored):,} rows).")
            return restored
    return None


def render_one_click(st, raw, opts, base_dir=None, storage_key=None):
    """Report tab: one button that runs clean (with the current ticked
    options) + recomputes KPIs + builds the report + prepares the email
    with the PDF attached.

    The email step reuses feat_export.render_email_schedule (same SMTP
    form as the Report tab). It NEVER sends without the SMTP details:
    when they are missing the email step is labelled pending and
    nothing is sent. Returns a status dict:
    {"status": "waiting" | "not_ready" | "done", "cleaned": df,
     "actions": [...], "kpis": [...], "report": str,
     "pdf_bytes": bytes, "backup_path": str,
     "email": "pending" | "ready",
     "email_details_missing": bool}.
    The integrator applies status["cleaned"] / ["actions"] / ["kpis"]
    to session state (clean / actions / kpis) after a "done" run.
    """
    st.subheader("One-click: clean, KPIs, report and email")
    st.write("One button does the whole flow: backs up the raw data, "
             "cleans it, rebuilds the KPIs and the report, and prepares "
             "the email with the PDF attached.")
    if raw is None:
        st.info("Load and clean data first — the one-click run needs a "
                "file to back up, clean and report on.")
        return {"status": "not_ready", "error": "No data loaded yet."}
    if not st.button("Run everything", type="primary", key="s_oneclick_run"):
        return {"status": "waiting"}
    source_name = ""
    try:
        source_name = st.session_state.get("source_name") or ""
    except Exception:
        source_name = ""
    backup_path = ""
    cleaned = actions = kpis = report = pdf_bytes = None
    summary = ""
    with st.spinner("Running everything — backing up, cleaning, "
                    "rebuilding the KPIs and the report…"):
        backup_path = backup_raw(raw, source_name or "data", base_dir,
                                 storage_key=storage_key)
        cleaned, actions = engine.clean(raw, _to_engine_opts(opts))
        kpis = engine.auto_kpis(cleaned)
        report = engine.build_report(raw, cleaned, actions, kpis)
        summary = (f"Rows: {len(raw):,} loaded -> {len(cleaned):,} after cleaning. "
                   f"Columns: {len(raw.columns)} -> {len(cleaned.columns)}.")
        pdf_bytes = engine.to_pdf_bytes("Data Cleaner Studio — Report",
                                        kpis, actions, summary)
    st.success(f"Done: {len(raw):,} rows -> {len(cleaned):,} rows, "
               f"{len(actions)} fix(es) applied. "
               f"Backup saved as {Path(str(backup_path)).name} — the raw "
               "file is untouched.")
    email_status = "pending"
    try:
        import feat_export
        feat_export.render_email_schedule(st, kpis, actions, raw, cleaned)
        sched = st.session_state.get("e_email_sched") or {}
        if sched.get("enabled"):
            email_status = "ready"
    except Exception as e:  # noqa: BLE001 - email step stays pending
        st.warning("Email step pending: the email form could not be "
                   f"shown ({e}). Nothing was sent.")
    if email_status == "pending":
        st.warning("Email step pending: fill in the SMTP details below "
                   "(server, port, username, password, recipient) — "
                   "nothing has been sent.")
    else:
        st.success("Email scheduled — it sends while the app is open, "
                   "with the PDF report attached.")
    return {"status": "done", "cleaned": cleaned, "actions": actions,
            "kpis": kpis, "report": report, "pdf_bytes": pdf_bytes,
            "backup_path": backup_path, "email": email_status,
            "email_details_missing": email_status == "pending"}


def render_html_download(st, kpis, actions, grouped_df, x_col, y_col,
                         title="Data Cleaner Studio — Dashboard",
                         brand=None):
    """Report tab: download the dashboard as ONE self-contained HTML
    file (inline CSS, no external links) with KPI cards, the cleaning
    summary and the grouped bar chart as inline SVG. ``brand`` is
    optional (see html_dashboard_bytes) — None keeps the plain
    Data Cleaner Studio branding."""
    st.subheader("Standalone HTML dashboard")
    st.write("One file that opens in any browser — no internet needed. "
             "It has the KPI cards, what was cleaned, and the chart.")
    data = html_dashboard_bytes(kpis, actions, grouped_df, x_col, y_col,
                                title, brand=brand)
    st.download_button("Download dashboard (.html)", data,
                       file_name="dashboard.html", mime="text/html",
                       key="s_html_dl")


def render_portfolio_download(st, cleaned, kpis, actions,
                              title="My data case study"):
    """Report tab: download a case-study ZIP (cleaned_data.csv, an
    auto-written README.md, and a chart PNG when the data can be
    charted)."""
    if cleaned is None:
        st.info("Clean the data first — the case study is built from the "
                "cleaned file.")
        return
    st.subheader("Publish to portfolio")
    st.write("A ZIP with the cleaned data, a plain-words write-up of "
             "what was cleaned, and a chart image — ready to attach to "
             "a portfolio or case-study page.")
    data = portfolio_zip_bytes(cleaned, kpis, actions, title)
    st.download_button("Download case study (.zip)", data,
                       file_name="portfolio_case_study.zip",
                       mime="application/zip", key="s_portfolio_dl")


def render_chart_png(st, grouped_df, x_col, y_col,
                     title="Chart", kind="bar", key_suffix=""):
    """Report / Dashboard tab: download the grouped chart as a PNG
    image (drawn with PIL — no matplotlib needed). key_suffix lets the
    coordinator show this section twice in one run (Dashboard + Report)
    without duplicate widget keys."""
    if grouped_df is None or len(grouped_df) == 0:
        st.info("No chart data yet — clean the data and build a chart "
                "first; the portfolio page needs both.")
        return
    st.subheader("Chart as image")
    st.write("Download the chart as a PNG picture — handy for slides, "
             "reports and portfolio posts.")
    kind_pick = st.selectbox("Chart type", ["bar", "line"],
                             key=f"s_chart_kind{key_suffix}",
                             index=0 if kind == "bar" else 1)
    data = chart_png_bytes(grouped_df, x_col, y_col, title, kind=kind_pick)
    st.download_button("Download chart (.png)", data,
                       file_name="chart.png", mime="image/png",
                       key=f"s_chart_png_dl{key_suffix}")


def render_styled_excel_download(st, cleaned, kpis, actions):
    """Report tab: download the cleaned workbook with conditional
    colours — missing values and numeric outliers highlighted light
    red, header row light green, everything else plain."""
    if cleaned is None:
        st.info("Clean the data first — the styled workbook is built from "
                "the cleaned file.")
        return
    st.subheader("Styled Excel export")
    st.write("Missing values and outliers are highlighted light red, so "
             "problem cells jump out. The header row is light green; "
             "every other cell is left plain.")
    data = to_excel_bytes_styled(cleaned, kpis, actions)
    st.download_button("Download styled Excel (.xlsx)", data,
                       file_name="cleaned_data_styled.xlsx",
                       mime="application/vnd.openxmlformats-officedocument."
                            "spreadsheetml.sheet",
                       key="s_styled_xlsx_dl")
