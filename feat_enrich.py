"""Data Cleaner Studio — Group 5: enrich & share (v1.3, Batch 3).

Pure logic + thin Streamlit render functions. The logic functions never
touch Streamlit, so they are unit-testable on their own; the render
functions take the ``st`` module as their first argument.

Features
--------
1.  Split & merge columns  — split_column(df, ...), merge_columns(df, ...)
2.  Date intelligence      — add_date_parts(df, column)
3.  Currency conversion    — convert_currency(df, column, target, rates)
4.  AI insights            — build_insight_prompt(df, kpis), ai_insights_text(df, kpis)
5.  Paste from clipboard   — parse_pasted_table(text)
6.  Row filter builder     — apply_filter_rules(df, rules), filtered_to_csv_bytes(df)
7.  Sampling for huge files — sample_frame(df, n, method, seed)
8.  Auto-save workspace    — save_workspace(...), load_workspace(...)
9.  Classic light theme  — theme_css(theme), apply_theme(st, theme)
10. Data masking           — mask_columns(df, columns, kinds), masked_csv_bytes(df),
                             masked_excel_bytes(df)
11. Versioned exports      — next_versioned_name(base)
12. Hindi/Urdu labels      — LANG, get_text(key, lang)

Integrator spec (see the render functions' docstrings too)
----------------------------------------------------------
Tabs (simple_app.py) — suggested homes; the coordinator wires these in:
  - Clean tab, "Fix values" expander : render_split_merge(st, clean),
      render_date_intelligence(st, clean), render_currency(st, clean),
      render_masking(st, clean)
  - Preview tab (or its own expander) : render_paste(st) — returns a
      DataFrame the coordinator sets as raw via _set_raw; render_filter_builder(st, clean)
  - Clean tab, "Clean many files" area : render_sampling(st, raw, clean_opts)
  - KPIs tab (under the KPI list)     : render_ai_insights(st, clean, kpis)
  - Report tab (under the downloads)  : render_versioned_download(st, clean, base)
  - Sidebar (under "Load your data")  : render_settings(st) [ai_settings],
      render_language_picker(st), render_workspace_toggle(st)
      (the theme picker is retired — the app has one Classic theme now;
      render_theme_picker() still exists as a no-UI shim that applies
      Classic, for backwards compatibility)

Session-state keys (data — never widget keys):
  - "n_fx_rates_data"    : {"INR": 1.0, "USD": 83.0, ...} edited FX rates
  - "n_filter_rules_data": list of {"column","condition","value"} filter rules
  - "n_ai_insight_data"  : last AI insight paragraph (str)
  - "n_version_name_data": last reserved versioned filename (str)
  - "n_theme_data"       : chosen theme name (str) — always "Classic"
  - "n_lang_data"        : chosen language code "en" | "hi" | "ur"
  - "n_sample_clean_data" / "n_sample_actions_data" / "n_sample_opts_data":
      last sample-clean run (frame / log / engine.clean options)

Widget keys (all start with "n_", none doubles as a data key):
  n_split_mode, n_split_col, n_split_method, n_split_sep, n_split_new1,
  n_split_new2, n_merge_a, n_merge_b, n_merge_sep, n_merge_name,
  n_merge_drop, n_split_merge_apply, n_date_col, n_date_apply, n_fx_col,
  n_fx_target, n_fx_rate_<CUR>, n_fx_apply, n_ai_get, n_paste_text,
  n_paste_load, n_filter_col, n_filter_cond, n_filter_value, n_filter_add,
  n_filter_clear, n_sample_n, n_sample_method, n_sample_seed, n_sample_run,
  n_sample_apply, n_workspace_toggle, n_mask_cols,
  n_mask_apply, n_version_base, n_version_reserve, n_version_download,
  n_lang_pick, n_ai_open_settings
  (ai_settings owns: ai_key_input, ai_key_save, ai_key_test)

Consuming render results (Clean tab):
  new_df, new_actions = render_split_merge(st, clean)  # or
      render_date_intelligence / render_currency — same pattern as
      feat_quality.render_outliers: apply the returned frame to
      st.session_state.clean, append new_actions, recompute KPIs.
  pasted = render_paste(st)  # a DataFrame or None — on a DataFrame,
      call _set_raw(pasted, "Pasted table", kind="paste").
  sample = render_sampling(st, raw, clean_opts)  # a dict or None — on a
      dict, sample["sample_clean"]/["sample_actions"] describe the sample
      run and sample["clean_opts"] are the engine.clean options to re-run
      on the full file.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pandas as pd

import ai_settings
import engine
import feat_currency

# --------------------------------------------------------------------------
# 12. Hindi/Urdu labels (defined first — render_language_picker needs it)
# --------------------------------------------------------------------------

LANG = {
    "en": {
        "app_title": "Data Cleaner Studio",
        "load": "Load",
        "preview": "Preview",
        "join": "Join",
        "clean": "Clean",
        "kpis": "KPIs",
        "dashboard": "Dashboard",
        "compare": "Compare",
        "report": "Report",
        "tools": "Tools",
        "clean_my_data": "Clean my data",
        "download_report": "Download report",
        "try_sample": "Try the messy sample",
        "tutorial": "How to use",
    },
    "hi": {
        "app_title": "डेटा क्लीनर स्टूडियो",
        "load": "लोड करें",
        "preview": "पूर्वावलोकन",
        "join": "जोड़ें",
        "clean": "साफ़ करें",
        "kpis": "मुख्य आँकड़े",
        "dashboard": "डैशबोर्ड",
        "compare": "तुलना करें",
        "report": "रिपोर्ट",
        "tools": "उपकरण",
        "clean_my_data": "मेरा डेटा साफ़ करें",
        "download_report": "रिपोर्ट डाउनलोड करें",
        "try_sample": "गड़बड़ सैंपल आज़माएँ",
        "tutorial": "कैसे उपयोग करें",
    },
    "ur": {
        "app_title": "ڈیٹا کلینر اسٹوڈیو",
        "load": "لوڈ کریں",
        "preview": "پیش نظارہ",
        "join": "جوڑیں",
        "clean": "صاف کریں",
        "kpis": "اہم اعداد",
        "dashboard": "ڈیش بورڈ",
        "compare": "موازنہ کریں",
        "report": "رپورٹ",
        "tools": "ٹولز",
        "clean_my_data": "میرا ڈیٹا صاف کریں",
        "download_report": "رپورٹ ڈاؤن لوڈ کریں",
        "try_sample": "گندا نمونہ آزمائیں",
        "tutorial": "استعمال کا طریقہ",
    },
}


def get_text(key: str, lang: str = "en") -> str:
    """One label in the chosen language. Unknown language or unknown key
    falls back to English; a key missing even there is returned as-is, so
    the screen never shows a blank."""
    table = LANG.get(lang) or LANG["en"]
    if key in table:
        return table[key]
    return LANG["en"].get(key, key)


# --------------------------------------------------------------------------
# 1. Split & merge columns
# --------------------------------------------------------------------------

def split_column(df: pd.DataFrame, column: str, mode: str = "separator",
                 separator: str = ",", new_names: list | None = None) -> tuple:
    """Split one column into two new columns. mode:
      separator     — split on the FIRST occurrence of `separator`
                      ("City, State" -> "City" | "State");
      first_last_word — split on the first space ("Full Name" ->
                      first word | the rest, e.g. first/last name).
    A value with no separator/space keeps its whole text in the first new
    column and leaves the second blank. The original column is kept, so
    nothing is lost. Returns (new_df, actions)."""
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not in the data.")
    if mode not in ("separator", "first_last_word"):
        raise ValueError(f"Unknown split mode: {mode} "
                         "(separator / first_last_word)")
    if mode == "separator" and (separator is None or str(separator) == ""):
        raise ValueError("Splitting by separator needs a separator — "
                         "e.g. a comma.")
    if new_names is None:
        if mode == "separator":
            new_names = [f"{column}_part1", f"{column}_part2"]
        else:
            new_names = [f"{column}_first", f"{column}_last"]
    if len(new_names) != 2:
        raise ValueError("new_names must name exactly two new columns.")
    first_name, second_name = (str(new_names[0]).strip() or f"{column}_part1",
                               str(new_names[1]).strip() or f"{column}_part2")
    sep = str(separator) if mode == "separator" else " "
    out = df.copy()
    firsts, seconds = [], []
    for value in out[column]:
        if pd.isna(value) or str(value).strip() == "":
            firsts.append(None)
            seconds.append(None)
            continue
        text = str(value).strip()
        if sep in text:
            left, right = text.split(sep, 1)
            firsts.append(left.strip() or None)
            seconds.append(right.strip() or None)
        else:
            firsts.append(text)
            seconds.append(None)
    out[first_name] = firsts
    out[second_name] = seconds
    n_split = sum(1 for s in seconds if s is not None)
    actions = [(f"Split column: {column}",
                f"Split into '{first_name}' and '{second_name}' "
                f"({n_split} of {len(out)} row(s) had something to split)")]
    return out, actions


def merge_columns(df: pd.DataFrame, col_a: str, col_b: str, new_name: str,
                  separator: str = " ", drop_originals: bool = False) -> tuple:
    """Merge two columns into one new column, joining their values with
    `separator` (blank parts are skipped, so "Ananya" + blank -> "Ananya",
    not "Ananya "). The originals are kept unless drop_originals is True.
    Returns (new_df, actions)."""
    for col in (col_a, col_b):
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not in the data.")
    if col_a == col_b:
        raise ValueError("Pick two different columns to merge.")
    if not str(new_name).strip():
        raise ValueError("The merged column needs a name.")
    out = df.copy()
    merged = []
    for a, b in zip(out[col_a], out[col_b]):
        parts = []
        for value in (a, b):
            if pd.isna(value):
                continue
            text = str(value).strip()
            if text:
                parts.append(text)
        merged.append(str(separator).join(parts) if parts else None)
    out[str(new_name).strip()] = merged
    if drop_originals:
        out = out.drop(columns=[col_a, col_b])
    n_filled = sum(1 for v in merged if v is not None)
    actions = [(f"Merge columns: {col_a} + {col_b}",
                f"Merged into '{str(new_name).strip()}' "
                f"({n_filled} of {len(out)} row(s) filled)"
                + ("; originals dropped" if drop_originals else ""))]
    return out, actions


# --------------------------------------------------------------------------
# 2. Date intelligence
# --------------------------------------------------------------------------

def add_date_parts(df: pd.DataFrame, column: str) -> tuple:
    """From any date column, add three columns next to it:
    {column}_year (e.g. 2026), {column}_month ("June"), {column}_weekday
    ("Saturday"). Values that do not parse as dates leave all three blank.
    Returns (new_df, actions)."""
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not in the data.")
    parsed = pd.to_datetime(df[column], errors="coerce", format="mixed")
    n_parsed = int(parsed.notna().sum())
    if n_parsed == 0:
        raise ValueError(f"Column '{column}' has no values that look like "
                         "dates — pick a date column.")
    out = df.copy()
    out[f"{column}_year"] = parsed.dt.year
    out[f"{column}_month"] = parsed.dt.strftime("%B")
    out[f"{column}_weekday"] = parsed.dt.strftime("%A")
    actions = [(f"Date intelligence: {column}",
                f"Added '{column}_year', '{column}_month' and "
                f"'{column}_weekday' ({n_parsed} of {len(out)} row(s) "
                "had a date)")]
    return out, actions


# --------------------------------------------------------------------------
# 3. Currency conversion (FIXED rates — never live rates)
# --------------------------------------------------------------------------

#: Fixed estimates, INR per 1 unit of the currency. The user edits these
#: in the UI; they are labelled "fixed estimates" on screen and never
#: presented as live rates.
DEFAULT_FX_RATES = {"INR": 1.0, "USD": 83.0, "EUR": 90.0, "GBP": 105.0}

FX_RATES_NOTE = ("Fixed estimates — not live rates. 1 USD = ₹83, "
                 "1 EUR = ₹90, 1 GBP = ₹105 unless you change them below.")

_MONEY_SYMBOL = re.compile(
    r"^(₹|Rs\.?|INR|\$|€|£)\s*", re.IGNORECASE)
_SYMBOL_TO_CUR = {"₹": "INR", "rs": "INR", "rs.": "INR", "inr": "INR",
                  "$": "USD", "€": "EUR", "£": "GBP"}


def parse_money(value):
    """Split one money cell into (amount, currency code). "₹799" / "Rs.
    799" / "INR 799" -> (799.0, "INR"); "$1,499.00" -> (1499.0, "USD");
    "€50" -> (50.0, "EUR"); "£20" -> (20.0, "GBP"). A bare number with no
    symbol is treated as INR (the app's home currency) — the screen says
    so. Unparseable / blank -> (None, None)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None, None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value), "INR"
    text = str(value).strip()
    if text == "" or text.lower() == "nan":
        return None, None
    match = _MONEY_SYMBOL.match(text)
    currency = "INR"
    if match:
        symbol = match.group(1)
        currency = _SYMBOL_TO_CUR.get(symbol.lower(), "INR")
        text = text[match.end():].strip()
    text = text.replace(",", "").rstrip("%").strip()
    try:
        return float(text), currency
    except ValueError:
        return None, None


def convert_currency(df: pd.DataFrame, column: str, target: str = "INR",
                     rates: dict | None = None,
                     source: str = "estimated") -> tuple:
    """Convert a column mixing ₹ / $ / € values into ONE currency.
    `rates` maps currency -> INR per 1 unit (defaults to
    DEFAULT_FX_RATES); a value converts as amount * rate[source] /
    rate[target]. Adds a column "{column}_{target}" (e.g. unit_price_INR),
    rounded to 2 decimals. Unparseable cells stay blank and are counted in
    the action log. `source` ("live" / "estimated") is written into the
    action log so the numbers are never mislabelled. Returns
    (new_df, actions)."""
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not in the data.")
    target = str(target).upper()
    merged_rates = dict(DEFAULT_FX_RATES)
    if rates:
        merged_rates.update({str(k).upper(): float(v)
                             for k, v in rates.items()})
    if target not in merged_rates:
        raise ValueError(f"Unknown target currency: {target} "
                         f"(use one of {', '.join(merged_rates)})")
    if merged_rates[target] == 0:
        raise ValueError(f"Rate for {target} is 0 — fix it before converting.")
    out = df.copy()
    converted, n_bad = [], 0
    for value in out[column]:
        amount, source = parse_money(value)
        if amount is None:
            converted.append(None)
            n_bad += 1
            continue
        converted.append(round(amount * merged_rates[source]
                               / merged_rates[target], 2))
    new_col = f"{column}_{target}"
    out[new_col] = converted
    n_ok = len(out) - n_bad
    actions = [(f"Currency conversion: {column} -> {target}",
                f"{n_ok} value(s) converted into {target} "
                f"(column '{new_col}')"
                + (f"; {n_bad} value(s) could not be read and were left blank"
                   if n_bad else "")
                + (". Rates are live rates, just fetched." if source == "live"
                   else ". Rates are fixed estimates, not live rates."))]
    return out, actions


def get_fx_rates(session_state) -> dict:
    """The FX rates the UI is currently using: session state's edited copy
    when present, else the saved settings, else the defaults."""
    stored = session_state.get("n_fx_rates_data") if session_state else None
    if isinstance(stored, dict) and stored:
        return {str(k).upper(): float(v) for k, v in stored.items()}
    return ai_settings.load_settings().get("fx_rates", dict(DEFAULT_FX_RATES))


# --------------------------------------------------------------------------
# 4. AI insights
# --------------------------------------------------------------------------

def build_insight_prompt(df: pd.DataFrame, kpis: list | None = None) -> str:
    """Turn the frame + its KPIs into the prompt sent to the AI: row/column
    counts, every KPI line, the top value of each short text column, and
    the total/average of each number column. Only facts from the data go
    in — the AI is told not to invent numbers."""
    lines = [f"The data has {len(df):,} rows and {len(df.columns)} columns "
             f"({', '.join(str(c) for c in df.columns)})."]
    for kpi in (kpis or []):
        lines.append(f"{kpi.get('label')}: {kpi.get('value')}.")
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            lines.append(f"{col}: total {df[col].sum():,.2f}, "
                         f"average {df[col].mean():,.2f}.")
        elif str(df[col].dtype) in ("object", "str") \
                and 1 < df[col].nunique(dropna=True) <= 30:
            top = df[col].value_counts(dropna=False)
            lines.append(f"{col}: most common is {top.index[0]} "
                         f"({int(top.iloc[0])} rows).")
    date_cols = engine.date_cols(df)
    if date_cols:
        d = df[date_cols[0]].dropna()
        if len(d):
            lines.append(f"{date_cols[0]} runs from {d.min().date()} "
                         f"to {d.max().date()}.")
    lines.append("In one short paragraph, in plain English, say what this "
                 "data says — what is biggest, what grew or shrank, and "
                 "what stands out. Use only the numbers above.")
    return "\n".join(lines)


def ai_insights_text(df: pd.DataFrame, kpis: list | None = None) -> str:
    """One plain-English paragraph on what the data says, via ai_settings.
    Raises the same clear ValueError as ai_settings.ask_ai when no API
    key is set — the render function turns that into plain on-screen words."""
    return ai_settings.ask_ai(build_insight_prompt(df, kpis))


# --------------------------------------------------------------------------
# 5. Paste from clipboard
# --------------------------------------------------------------------------

def parse_pasted_table(text: str) -> pd.DataFrame:
    """Turn pasted copied-table text into a DataFrame. Tab-separated wins
    when tabs are present (that is what a copied spreadsheet gives you);
    otherwise commas. The first row is the header. Blank pastes and
    single-column pastes with no header raise ValueError."""
    if text is None or str(text).strip() == "":
        raise ValueError("Nothing pasted yet — copy a table (from Excel or "
                         "a web page) and paste it into the box.")
    cleaned = str(text).strip("\n").strip()
    sep = "\t" if "\t" in cleaned else ","
    try:
        df = pd.read_csv(io.StringIO(cleaned), sep=sep, engine="python")
    except Exception as e:
        raise ValueError(f"Could not read the pasted table: {e}") from e
    df.columns = [str(c).strip() for c in df.columns]
    if len(df.columns) < 1 or len(df) == 0:
        raise ValueError("The pasted text did not look like a table — "
                         "check it has a header row and at least one row "
                         "of values.")
    return df


# --------------------------------------------------------------------------
# 6. Row filter builder
# --------------------------------------------------------------------------

FILTER_CONDITIONS = ("equals", "not equals", "contains", "greater than",
                     "less than", "greater than or equal",
                     "less than or equal", "is empty", "is not empty")
_CONDITIONS_NEEDING_VALUE = FILTER_CONDITIONS[:7]


def apply_filter_rules(df: pd.DataFrame, rules: list) -> pd.DataFrame:
    """Keep only the rows matching EVERY rule (AND). A rule is
    {"column", "condition", "value"} with condition one of
    FILTER_CONDITIONS. Numbers compare as numbers when both sides parse;
    everything else compares as case-insensitive text. Missing cells never
    match a comparison rule — "is empty" is the rule for those. An empty
    rule list returns the frame unchanged."""
    if not rules:
        return df.copy()
    mask = pd.Series(True, index=df.index)
    for i, rule in enumerate(rules):
        col = rule.get("column")
        cond = rule.get("condition")
        value = rule.get("value")
        if col not in df.columns:
            raise ValueError(f"Rule {i}: column '{col}' not in the data.")
        if cond not in FILTER_CONDITIONS:
            raise ValueError(f"Rule {i}: unknown condition '{cond}'.")
        s = df[col]
        if cond == "is empty":
            bad = s.isna() | (s.astype(object).astype(str).str.strip() == "")
            mask &= bad
            continue
        if cond == "is not empty":
            bad = s.notna() & (s.astype(object).astype(str).str.strip() != "")
            mask &= bad
            continue
        if cond == "contains":
            text = s.where(s.isna(), s.astype(object).astype(str)).str.lower()
            mask &= s.notna() & text.str.contains(str(value).lower(),
                                                  regex=False)
            continue
        num_s = pd.to_numeric(s, errors="coerce")
        try:
            num_v = float(value)
            numeric = True
        except (TypeError, ValueError):
            numeric = False
        if numeric and num_s.notna().any():
            comparable = num_s.notna()
            if cond == "equals":
                mask &= comparable & (num_s == num_v)
            elif cond == "not equals":
                mask &= comparable & (num_s != num_v)
            elif cond == "greater than":
                mask &= comparable & (num_s > num_v)
            elif cond == "less than":
                mask &= comparable & (num_s < num_v)
            elif cond == "greater than or equal":
                mask &= comparable & (num_s >= num_v)
            elif cond == "less than or equal":
                mask &= comparable & (num_s <= num_v)
        else:
            text = s.where(s.isna(), s.astype(object).astype(str)).str.strip().str.lower()
            want = str(value).strip().lower()
            if cond == "equals":
                mask &= s.notna() & (text == want)
            elif cond == "not equals":
                mask &= s.notna() & (text != want)
            elif cond == "greater than":
                mask &= s.notna() & (text > want)
            elif cond == "less than":
                mask &= s.notna() & (text < want)
            elif cond == "greater than or equal":
                mask &= s.notna() & (text >= want)
            elif cond == "less than or equal":
                mask &= s.notna() & (text <= want)
    return df.loc[mask].reset_index(drop=True)


def filtered_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """The given (filtered) frame as CSV bytes, for the download button."""
    return df.to_csv(index=False).encode("utf-8")


# --------------------------------------------------------------------------
# 7. Sampling for huge files
# --------------------------------------------------------------------------

def sample_frame(df: pd.DataFrame, n: int = 1000, method: str = "first",
                 seed: int = 42) -> pd.DataFrame:
    """A small slice of a huge file to clean first: "first" takes the first
    N rows; "random" takes N rows at random (seeded, so the same seed gives
    the same sample). A file already smaller than N comes back unchanged."""
    if method not in ("first", "random"):
        raise ValueError(f"Unknown sampling method: {method} "
                         "(first / random)")
    if n is None or int(n) <= 0:
        raise ValueError("Sample size must be at least 1 row.")
    n = int(n)
    if len(df) <= n:
        return df.copy()
    if method == "first":
        return df.head(n).reset_index(drop=True)
    return df.sample(n=n, random_state=int(seed)).reset_index(drop=True)


# --------------------------------------------------------------------------
# 8. Auto-save workspace
# --------------------------------------------------------------------------

def _workspace_dir(base_dir=None) -> Path:
    return Path(base_dir) if base_dir is not None else (
        Path(__file__).resolve().parent / "workspace")


def save_workspace(raw, clean, source_name: str = "", actions=None,
                   kpis=None, base_dir=None) -> Path:
    """Save the current state locally: workspace/raw.csv, workspace/
    clean.csv (when there is cleaned data) and workspace/state.json
    (source name + cleaning log + KPIs). Returns the workspace folder.
    Old files are overwritten — this is a restore point, not a versioned
    export (see next_versioned_name for that)."""
    folder = _workspace_dir(base_dir)
    folder.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        raw.to_csv(folder / "raw.csv", index=False)
    if clean is not None:
        clean.to_csv(folder / "clean.csv", index=False)
    state = {
        "source_name": str(source_name or ""),
        "actions": [[str(a), str(b)] for a, b in (actions or [])],
        "kpis": [{"label": str(k.get("label", "")),
                  "value": str(k.get("value", ""))}
                 for k in (kpis or [])],
    }
    (folder / "state.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return folder


def load_workspace(base_dir=None):
    """Restore a saved workspace: returns {"raw", "clean", "source_name",
    "actions", "kpis"} or None when no workspace was ever saved. clean is
    None when only raw was saved; actions/kpis come back as lists."""
    folder = _workspace_dir(base_dir)
    raw_path = folder / "raw.csv"
    if not raw_path.exists():
        return None
    raw = pd.read_csv(raw_path)
    clean = pd.read_csv(folder / "clean.csv") \
        if (folder / "clean.csv").exists() else None
    state = {"source_name": "", "actions": [], "kpis": []}
    state_path = folder / "state.json"
    if state_path.exists():
        try:
            stored = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                state.update(stored)
        except ValueError:
            pass
    return {
        "raw": raw,
        "clean": clean,
        "source_name": str(state.get("source_name", "")),
        "actions": [(str(a), str(b)) for a, b in state.get("actions", [])],
        "kpis": [{"label": str(k.get("label", "")),
                  "value": str(k.get("value", ""))}
                 for k in state.get("kpis", [])],
    }


# --------------------------------------------------------------------------
# 9. Supabase light theme (the app's ONE theme)
# --------------------------------------------------------------------------

#: The app has a single Supabase theme — near-white background, near-black
#: ink, one deep-green accent — matching .streamlit/config.toml, which
#: themes the app from first paint (login screen included). Streamlit's
#: own theme is static config, so a picker cannot re-theme the app by
#: itself; the old Classic / Dark green / Dark blue / Light picker is
#: retired. theme_css() / apply_theme() keep their signatures: any old
#: theme name (including a stale "theme" value in an existing
#: settings.json) falls back to Supabase.
THEMES = {
    "Supabase": {
        "background": "#fdfdfd", "text": "#030303",
        "accent": "#117f50", "secondary": "#fdfdfd",
        "button_text": "#FFFFFF",
    },
}


def theme_css(theme_name: str) -> str:
    """The live CSS overrides for a theme name. Any name — "Supabase",
    "Classic", "Dark green", "Dark blue", anything unknown — returns the
    identical Supabase CSS: there is only one theme now."""
    theme = THEMES.get(theme_name) or THEMES["Supabase"]
    return f"""<style>
.stApp {{ background-color: {theme["background"]}; color: {theme["text"]}; }}
.stApp h1, .stApp h2, .stApp h3 {{ color: {theme["text"]}; }}
.stApp .stButton > button[kind="primary"] {{
    background-color: {theme["accent"]}; color: {theme["button_text"]};
    border-color: {theme["accent"]}; }}
.stApp a {{ color: {theme["accent"]}; }}
section[data-testid="stSidebar"] {{
    background-color: {theme["secondary"]}; }}
section[data-testid="stSidebar"] * {{ color: {theme["text"]}; }}
</style>"""


def apply_theme(st, theme_name: str) -> str:
    """Inject the theme's live CSS overrides and remember the choice in
    settings.json for next launch. Returns the theme name actually used
    (always "Supabase" — any other name falls back to it)."""
    name = theme_name if theme_name in THEMES else "Supabase"
    st.markdown(theme_css(name), unsafe_allow_html=True)
    settings = ai_settings.load_settings()
    settings["theme"] = name
    ai_settings.save_settings(settings)
    return name


# --------------------------------------------------------------------------
# 10. Data masking
# --------------------------------------------------------------------------

def mask_phone(value) -> str:
    """98765 43210 -> 98XXX X3210: first 2 and last 4 digits stay, the
    middle becomes X. Short numbers (under 6 digits) are fully masked."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    digits = re.sub(r"\D", "", str(value))
    if digits == "":
        return str(value)
    if len(digits) < 6:
        return "X" * len(digits)
    masked = digits[:2] + "X" * (len(digits) - 6) + digits[-4:]
    if len(masked) == 10:
        return masked[:5] + " " + masked[5:]
    return masked


def mask_email(value) -> str:
    """name@x.com -> n***@x.com: first letter of the name stays, the rest
    becomes ***. Anything without an @ is masked as plain text."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if "@" not in text:
        return mask_text(text)
    local, domain = text.split("@", 1)
    if local == "":
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def mask_text(value) -> str:
    """Mask a name or other free text word by word, keeping each word's
    first letter: "Aarav Sharma" -> "A**** S*****"."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    words = str(value).split(" ")
    out = []
    for word in words:
        if word == "":
            out.append("")
        elif len(word) == 1:
            out.append(word)
        else:
            out.append(word[0] + "*" * (len(word) - 1))
    return " ".join(out)


def _detect_mask_kind(column: str, series: pd.Series) -> str:
    """Guess phone / email / text for a column: by name first (phone,
    mobile, email, mail), then by values (an @ in most values -> email,
    mostly digits -> phone)."""
    name = str(column).lower()
    if "email" in name or "mail" in name:
        return "email"
    if "phone" in name or "mobile" in name or "contact" in name:
        return "phone"
    sample = series.dropna().astype(object).astype(str)
    if len(sample) == 0:
        return "text"
    if (sample.str.contains("@", regex=False).mean() or 0) >= 0.5:
        return "email"
    digits = sample.str.replace(r"\D", "", regex=True)
    if (digits.str.len() >= 6).mean() >= 0.5:
        return "phone"
    return "text"


def mask_columns(df: pd.DataFrame, columns, kinds: dict | None = None) -> tuple:
    """Mask the given columns in a COPY (the original frame is untouched).
    kinds maps column -> "phone" | "email" | "text"; a column without an
    entry is auto-detected. Returns (masked_df, actions)."""
    out = df.copy()
    kinds = kinds or {}
    masked = []
    for col in columns:
        if col not in out.columns:
            raise ValueError(f"Column '{col}' not in the data.")
        kind = kinds.get(col) or _detect_mask_kind(col, out[col])
        if kind == "phone":
            out[col] = out[col].map(mask_phone)
        elif kind == "email":
            out[col] = out[col].map(mask_email)
        elif kind == "text":
            out[col] = out[col].map(mask_text)
        else:
            raise ValueError(f"Unknown mask kind for '{col}': {kind} "
                             "(phone / email / text)")
        masked.append(f"{col} ({kind})")
    actions = [("Mask data",
                f"Masked {len(masked)} column(s) before sharing: "
                f"{', '.join(masked)}")] if masked else []
    return out, actions


def masked_csv_bytes(df: pd.DataFrame) -> bytes:
    """A (masked) frame as CSV bytes, for the download button."""
    return df.to_csv(index=False).encode("utf-8")


def masked_excel_bytes(df: pd.DataFrame, kpis=None, actions=None) -> bytes:
    """A (masked) frame as an Excel workbook (data + KPIs + log), via the
    same writer the Report tab uses."""
    return engine.to_excel_bytes(df, kpis or [], actions or [])


# --------------------------------------------------------------------------
# 11. Versioned exports
# --------------------------------------------------------------------------

def _versions_file(path=None) -> Path:
    return Path(path) if path is not None else (
        Path(__file__).resolve().parent / "versions.json")


def _read_versions(path=None) -> dict:
    try:
        stored = json.loads(_versions_file(path).read_text(encoding="utf-8"))
        return dict(stored) if isinstance(stored, dict) else {}
    except (OSError, ValueError):
        return {}


def next_versioned_name(base: str, path=None) -> str:
    """The next versioned filename for a base name — cleaned_v1.csv,
    cleaned_v2.csv, ... — tracked in versions.json (next to the app) so
    an old version is never overwritten. `base` may carry an extension
    ("cleaned.csv") or not ("cleaned" -> "cleaned_v1.csv"). Each call
    reserves the next number and saves it."""
    if not str(base).strip():
        raise ValueError("A base filename is needed — e.g. cleaned.csv.")
    base = str(base).strip()
    stem, dot, ext = base.rpartition(".")
    if not dot or "/" in stem or "\\" in stem:
        stem, ext = base, "csv"
    key = f"{stem}.{ext}"
    versions = _read_versions(path)
    number = int(versions.get(key, 0)) + 1
    versions[key] = number
    _versions_file(path).write_text(
        json.dumps(versions, indent=2), encoding="utf-8")
    return f"{stem}_v{number}.{ext}"


def peek_versioned_name(base: str, path=None) -> str:
    """What the NEXT versioned name would be, without reserving it — for
    showing on screen before the user commits."""
    if not str(base).strip():
        raise ValueError("A base filename is needed — e.g. cleaned.csv.")
    base = str(base).strip()
    stem, dot, ext = base.rpartition(".")
    if not dot or "/" in stem or "\\" in stem:
        stem, ext = base, "csv"
    number = int(_read_versions(path).get(f"{stem}.{ext}", 0)) + 1
    return f"{stem}_v{number}.{ext}"


# --------------------------------------------------------------------------
# render functions — thin Streamlit wrappers (st passed in, never imported)
# --------------------------------------------------------------------------

def render_split_merge(st, df: pd.DataFrame):
    """Clean tab, "Fix values" expander: split one column into two, or
    merge two columns into one. Returns (new_df_or_None, new_actions) —
    the integrator applies the returned frame like feat_quality's
    render_outliers. Nothing changes until Apply is pressed."""
    st.subheader("Split & merge columns")
    st.write("Split one column into two — a full name into first/last, or "
             "\"City, State\" into two columns — or merge two columns into "
             "one. The original columns are kept unless you tick the box "
             "to drop them.")
    mode_label = st.radio("What to do", ["Split one column into two",
                                         "Merge two columns into one"],
                          key="n_split_mode")
    if mode_label == "Split one column into two":
        col = st.selectbox("Column to split", list(df.columns),
                           key="n_split_col")
        method_label = st.selectbox(
            "How to split",
            ["By separator (e.g. a comma)", "First word / rest (names)"],
            key="n_split_method")
        method = ("separator" if method_label.startswith("By separator")
                  else "first_last_word")
        separator = ","
        if method == "separator":
            separator = st.text_input("Separator", value=",",
                                      key="n_split_sep",
                                      help="The character between the two "
                                           "parts — usually a comma.")
        c1, c2 = st.columns(2)
        default_names = ([f"{col}_part1", f"{col}_part2"] if method == "separator"
                         else [f"{col}_first", f"{col}_last"])
        new1 = c1.text_input("First new column", value=default_names[0],
                             key="n_split_new1")
        new2 = c2.text_input("Second new column", value=default_names[1],
                             key="n_split_new2")
        if st.button("Split column", type="primary",
                     key="n_split_merge_apply"):
            try:
                new_df, actions = split_column(
                    df, col, method, separator, [new1, new2])
            except ValueError as e:
                st.error(str(e))
                return None, []
            st.success(f"Split — {actions[0][1]}.")
            return new_df, actions
        return None, []
    c1, c2 = st.columns(2)
    col_a = c1.selectbox("First column", list(df.columns), key="n_merge_a")
    col_b = c2.selectbox("Second column", list(df.columns), key="n_merge_b")
    separator = st.text_input("Join with", value=" ", key="n_merge_sep",
                              help="Put between the two values — a space "
                                   "for names, a comma for addresses.")
    new_name = st.text_input("New column name", value="merged",
                             key="n_merge_name")
    drop = st.checkbox("Drop the two original columns after merging",
                       value=False, key="n_merge_drop")
    if st.button("Merge columns", type="primary", key="n_split_merge_apply"):
        try:
            new_df, actions = merge_columns(df, col_a, col_b, new_name,
                                            separator, drop)
        except ValueError as e:
            st.error(str(e))
            return None, []
        st.success(f"Merged — {actions[0][1]}.")
        return new_df, actions
    return None, []


def render_date_intelligence(st, df: pd.DataFrame):
    """Clean tab, "Fix values" expander: pick a date column and add Year,
    Month and Weekday columns. Returns (new_df_or_None, new_actions)."""
    st.subheader("Date intelligence")
    st.write("Pick a date column and get three new ones for free: the "
             "year, the month name and the weekday — handy for grouping "
             "sales by month or weekday.")
    candidates = engine.date_cols(df) + [
        c for c in df.columns
        if c not in engine.date_cols(df)
        and engine.detect_kind(df[c]) == "date"]
    if not candidates:
        st.info("No date column found — clean the data first so dates "
                "are parsed, then come back here.")
        return None, []
    col = st.selectbox("Date column", candidates, key="n_date_col")
    if st.button("Add Year / Month / Weekday", type="primary",
                 key="n_date_apply"):
        try:
            new_df, actions = add_date_parts(df, col)
        except ValueError as e:
            st.error(str(e))
            return None, []
        st.success(f"Done — {actions[0][1]}.")
        return new_df, actions
    return None, []


def render_currency(st, df: pd.DataFrame):
    """Clean tab, "Fix values" expander: convert a column mixing ₹ / $ / €
    values into one currency. Returns (new_df_or_None, new_actions).
    Rates are FIXED estimates the user can edit — the screen says so in
    plain words, and they are never presented as live rates."""
    st.subheader("Currency conversion")
    st.write("Turn a price column that mixes ₹, $ and € into one currency.")
    if st.button("Get live rates", key="n_fx_live",
                 help="Fetch today's rates from a free rate service. "
                      "If it fails, the fixed estimates below are used."):
        try:
            _live, _src = feat_currency.get_rates()
            st.session_state["n_fx_rates_data"] = _live
            st.session_state["n_fx_source"] = _src
            if _src == "live":
                st.success("Live rates loaded.")
            else:
                st.info("No live rates right now — using the fixed "
                        "estimates below.")
        except Exception as e:  # noqa: BLE001 - a failed fetch just falls back
            st.warning(f"Could not fetch live rates: {e}")
    _src = st.session_state.get("n_fx_source", "estimated")
    if _src == "live":
        st.info("Using live rates, just fetched. They change through "
                "the day.")
    else:
        st.warning(FX_RATES_NOTE)
    rates = get_fx_rates(st.session_state)
    st.write("Rates (₹ per 1 unit — edit them if you know better ones):")
    cols = st.columns(len(rates))
    new_rates = {}
    for (cur, value), col in zip(sorted(rates.items()), cols):
        new_rates[cur] = col.number_input(
            f"1 {cur} = ₹", value=float(value), min_value=0.0,
            key=f"n_fx_rate_{cur}")
    if new_rates != rates:
        st.session_state["n_fx_rates_data"] = new_rates
        # Hand-edited rates are estimates again, even if live ones were
        # fetched a moment ago — the label must stay honest.
        st.session_state["n_fx_source"] = "estimated"
        settings = ai_settings.load_settings()
        settings["fx_rates"] = new_rates
        ai_settings.save_settings(settings)
        rates = new_rates
        _src = "estimated"
    text_cols = [c for c in df.columns
                 if engine.detect_kind(df[c]) in ("number", "text")]
    if not text_cols:
        st.info("No column with money values in this file.")
        return None, []
    col = st.selectbox("Price column", text_cols, key="n_fx_col")
    target = st.selectbox("Convert everything into",
                          sorted(rates), index=sorted(rates).index("INR")
                          if "INR" in rates else 0, key="n_fx_target")
    st.caption("A value with no symbol (e.g. plain 799) is treated as ₹.")
    if st.button("Convert currency", type="primary", key="n_fx_apply"):
        try:
            new_df, actions = convert_currency(df, col, target, rates,
                                               source=_src)
        except ValueError as e:
            st.error(str(e))
            return None, []
        st.success(f"Done — {actions[0][1]}")
        return new_df, actions
    return None, []


def render_ai_insights(st, df: pd.DataFrame, kpis: list | None = None) -> None:
    """KPIs tab (under the KPI list): one plain-English paragraph on what
    the data says. When no API key is set it says so plainly — what is
    needed, where to get it, and that nothing is sent until a key is
    saved. The paragraph is kept in session state ("n_ai_insight_data")
    so it survives reruns."""
    st.subheader("AI insights")
    if ai_settings.get_api_key() is None:
        st.info("AI insights need a Groq API key first — they are free to "
                "set up: get a key at console.groq.com, paste it in "
                "Settings, and press 'Get AI insights' here. Until then, "
                "nothing is sent anywhere and no insight is shown.")
        if st.button("Open Settings", key="n_ai_open_settings"):
            st.write("Settings lives in the sidebar — paste the key there "
                     "and save it.")
        return
    if st.button("Get AI insights", type="primary", key="n_ai_get"):
        try:
            st.session_state["n_ai_insight_data"] = ai_insights_text(df, kpis)
        except Exception as e:  # noqa: BLE001 - show the error, don't crash
            st.error(str(e))
    insight = st.session_state.get("n_ai_insight_data")
    if insight:
        st.write(insight)


def render_paste(st):
    """Preview tab (or sidebar): paste a copied table and load it as data.
    Returns the DataFrame, or None when nothing was loaded — the
    coordinator sets it as raw data with _set_raw(pasted, "Pasted table",
    kind="paste"). Nothing is loaded until the button is pressed."""
    st.subheader("Paste a table")
    st.write("Copied a table from Excel or a web page? Paste it here — "
             "tabs or commas both work — and it loads as data.")
    text = st.text_area("Paste the copied table (first row = headers)",
                        height=150, key="n_paste_text",
                        help="Copy cells in Excel, paste here, press the "
                             "button.")
    if st.button("Load pasted table", type="primary", key="n_paste_load"):
        try:
            pasted = parse_pasted_table(text)
        except ValueError as e:
            st.error(str(e))
            return None
        st.success(f"Loaded {len(pasted):,} rows, {len(pasted.columns)} "
                   "columns from the paste.")
        st.dataframe(pasted.head(100), width="stretch")
        return pasted
    return None


def render_filter_builder(st, df: pd.DataFrame) -> None:
    """Preview tab: build filter rules (column + condition + value,
    combined with AND), see the matching rows, and download just those
    rows as CSV. Rules live in session state under "n_filter_rules_data"
    so they survive reruns."""
    st.subheader("Filter rows")
    st.write("Pick a column, a condition and a value — add as many rules "
             "as you like, they all apply together (AND) — then download "
             "just the matching rows.")
    if "n_filter_rules_data" not in st.session_state:
        st.session_state["n_filter_rules_data"] = []
    c1, c2, c3 = st.columns(3)
    col = c1.selectbox("Column", list(df.columns), key="n_filter_col")
    cond = c2.selectbox("Condition", list(FILTER_CONDITIONS),
                        key="n_filter_cond")
    value = ""
    if cond in _CONDITIONS_NEEDING_VALUE:
        value = c3.text_input("Value", key="n_filter_value")
    else:
        c3.caption("This condition needs no value.")
    if st.button("Add rule", key="n_filter_add"):
        if cond in _CONDITIONS_NEEDING_VALUE and str(value).strip() == "":
            st.error("That condition needs a value.")
        else:
            st.session_state["n_filter_rules_data"].append(
                {"column": col, "condition": cond, "value": value})
    rules = st.session_state["n_filter_rules_data"]
    if rules:
        for i, r in enumerate(rules):
            suffix = f" {r['value']}" if r.get("value") not in (None, "") else ""
            st.write(f"{i}. **{r['column']}** {r['condition']}{suffix}")
        if st.button("Clear all rules", key="n_filter_clear",
                      type="secondary"):
            st.session_state["n_filter_rules_data"] = []
            rules = []
    if not rules:
        st.info("No rules yet — add one above to filter the rows.")
        return
    try:
        filtered = apply_filter_rules(df, rules)
    except ValueError as e:
        st.error(str(e))
        return
    st.write(f"{len(filtered):,} of {len(df):,} rows match.")
    st.dataframe(filtered.head(100), width="stretch")
    st.download_button(
        "Download filtered rows (CSV)", filtered_to_csv_bytes(filtered),
        file_name="filtered_rows.csv", mime="text/csv",
        key="n_filter_download")


def render_sampling(st, df: pd.DataFrame, clean_opts: dict | None = None):
    """Clean tab: for huge files, clean a small sample first and check the
    log, then apply the same cleaning to the full file. `clean_opts` are
    the engine.clean options (the coordinator passes
    feat_automate.to_engine_opts(st.session_state["clean_opts"]));
    None means the defaults. Returns a dict on "apply to full file":
      {"sample_clean", "sample_actions", "clean_opts", "sample_n",
       "sample_method"} — or None. The coordinator re-runs engine.clean
    on the full frame with the returned clean_opts."""
    st.subheader("Try it on a sample first")
    st.write("Big file? Clean a small sample first and check the log — "
             "then press one button to run the same cleaning on the full "
             "file.")
    if len(df) <= 1000:
        st.info(f"This file has {len(df):,} rows — small enough to clean "
                "in full. Sampling is for files over 1,000 rows.")
        return None
    c1, c2, c3 = st.columns(3)
    n = c1.number_input("Sample size (rows)", value=1000, min_value=10,
                        max_value=len(df), step=100, key="n_sample_n")
    method_label = c2.selectbox("Which rows", ["First rows", "Random rows"],
                                key="n_sample_method")
    seed = c3.number_input("Random seed", value=42, min_value=0,
                           key="n_sample_seed",
                           help="Same seed = same random sample, so you "
                                "can repeat the check.")
    method = "first" if method_label == "First rows" else "random"
    sample = sample_frame(df, int(n), method, int(seed))
    if st.button("Clean the sample", key="n_sample_run"):
        cleaned, actions = engine.clean(sample, clean_opts)
        st.session_state["n_sample_clean_data"] = cleaned
        st.session_state["n_sample_actions_data"] = actions
        st.session_state["n_sample_opts_data"] = clean_opts
    cleaned = st.session_state.get("n_sample_clean_data")
    actions = st.session_state.get("n_sample_actions_data")
    if cleaned is not None and actions is not None:
        st.write(f"Sample: {len(sample):,} rows -> {len(cleaned):,} rows "
                 f"after cleaning.")
        for step, detail in actions:
            st.write(f"- **{step}:** {detail}")
        st.dataframe(cleaned.head(100), width="stretch")
        if st.button("Apply the same cleaning to the full file",
                     type="primary", key="n_sample_apply"):
            return {"sample_clean": cleaned,
                    "sample_actions": actions,
                    "clean_opts": st.session_state.get(
                        "n_sample_opts_data", clean_opts),
                    "sample_n": int(n),
                    "sample_method": method}
    return None


def render_workspace_toggle(st) -> bool:
    """Sidebar: the auto-save on/off switch. Returns True when auto-save
    is on. The coordinator wires the calls: after each change, when this
    is on, call save_workspace(raw, clean, source_name, actions, kpis);
    on startup, call load_workspace() to restore. The toggle itself saves
    nothing — it only reports the choice."""
    st.subheader("Auto-save workspace")
    st.write("When on, your loaded file and cleaned data are saved on "
             "this computer (app folder, workspace/) after each change, "
             "so closing the app does not lose your work.")
    on = st.checkbox("Auto-save my workspace", value=False,
                     key="n_workspace_toggle",
                     help="Saves raw.csv, clean.csv and state.json in the "
                          "app's workspace folder.")
    return bool(on)


def render_theme_picker(st) -> str:
    """Retired: the app has one Supabase theme now (see THEMES), set in
    .streamlit/config.toml, so there is no picker UI any more. Kept for
    backwards compatibility — it applies Supabase, records it in
    settings.json and session state, and returns "Supabase". Any old
    stored theme name is migrated to Supabase."""
    name = apply_theme(st, "Supabase")
    st.session_state["n_theme_data"] = name
    return name


def render_masking(st, df: pd.DataFrame):
    """Clean tab, "Fix values" expander: mask phone numbers, emails and
    any column you pick before sharing — e.g. 98765 43210 -> 98XXX X3210,
    name@x.com -> n***@x.com. Export-only: it offers masked CSV/Excel
    downloads and a preview, and never overwrites your cleaned data.
    Returns (None, []) — see the module docstring."""
    st.subheader("Mask data before sharing")
    st.write("Hide phone numbers, emails and names before you share the "
             "file — the masked copy is for downloading only, your cleaned "
             "data stays untouched.")
    text_cols = [c for c in df.columns
                 if str(df[c].dtype) in ("object", "str")]
    if not text_cols:
        st.info("No text columns to mask in this file.")
        return None, []
    suggested = [c for c in text_cols
                 if _detect_mask_kind(c, df[c]) in ("phone", "email")]
    picked = st.multiselect("Columns to mask", text_cols,
                            default=suggested, key="n_mask_cols",
                            help="Phone and email columns are pre-ticked; "
                                 "add any other column you want hidden.")
    if not picked:
        st.info("Tick at least one column to mask.")
        return None, []
    masked_df, actions = mask_columns(df, picked)
    st.write(f"Masked: {actions[0][1]}.")
    st.dataframe(masked_df.head(100), width="stretch")
    c1, c2 = st.columns(2)
    c1.download_button("Download masked CSV",
                       masked_csv_bytes(masked_df),
                       file_name="masked_data.csv", mime="text/csv",
                       key="n_mask_csv")
    c2.download_button("Download masked Excel",
                       masked_excel_bytes(masked_df),
                       file_name="masked_data.xlsx",
                       key="n_mask_xlsx")
    return None, []


def render_versioned_download(st, df: pd.DataFrame, base: str = "cleaned.csv"):
    """Report tab (under the downloads): offer the cleaned file under the
    next versioned name — cleaned_v1.csv, cleaned_v2.csv, ... — so an old
    version is never overwritten. Press "Reserve this version" first
    (that is the step that claims the number in versions.json), then the
    download button appears with that filename. Returns the reserved
    filename, or None."""
    st.subheader("Versioned export")
    st.write("Every download gets a new version number, so you never "
             "overwrite last week's file by accident.")
    base = st.text_input("Base filename", value=base, key="n_version_base",
                         help="e.g. cleaned.csv — versions are added as "
                              "cleaned_v1.csv, cleaned_v2.csv, ...")
    try:
        upcoming = peek_versioned_name(base)
    except ValueError as e:
        st.error(str(e))
        return None
    st.write(f"Next version: **{upcoming}**")
    if st.button("Reserve this version", key="n_version_reserve"):
        name = next_versioned_name(base)
        st.session_state["n_version_name_data"] = name
        st.success(f"Reserved {name} — download it below.")
    reserved = st.session_state.get("n_version_name_data")
    if reserved:
        st.download_button(f"Download {reserved}",
                           filtered_to_csv_bytes(df),
                           file_name=reserved, mime="text/csv",
                           key="n_version_download")
        return reserved
    return None


def render_language_picker(st) -> str:
    """Sidebar: English / हिन्दी / اردو toggle for the main headings and
    button labels. Saved to settings.json and to session state
    ("n_lang_data"); the coordinator reads get_text(key, lang) to relabel
    the screens. Returns the chosen language code."""
    st.subheader("Language / भाषा / زبان")
    options = {"en": "English", "hi": "हिन्दी", "ur": "اردو"}
    current = ai_settings.load_settings().get("language", "en")
    codes = list(options)
    choice_label = st.selectbox(
        "Language", [options[c] for c in codes],
        index=codes.index(current) if current in codes else 0,
        key="n_lang_pick")
    code = codes[[options[c] for c in codes].index(choice_label)]
    if code != current:
        settings = ai_settings.load_settings()
        settings["language"] = code
        ai_settings.save_settings(settings)
        st.session_state["n_lang_data"] = code
    else:
        st.session_state["n_lang_data"] = code
    return code
