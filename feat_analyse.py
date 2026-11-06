"""Data Cleaner Studio — Batch 5: analyse & explain (v1.3).

Pure logic + thin Streamlit render functions. The logic functions never
touch Streamlit, so they are unit-testable on their own; the render
functions take the ``st`` module as their first argument and only use
widget keys starting with ``an_``. Widget keys and data keys are kept
strictly separate — a widget key is never reused to store data.

Features
--------
1.  Correlation finder   — find_correlations(df, min_abs)
2.  Trend forecast       — forecast_next(df, date_col, num_col, periods)
3.  What-if slider       — what_if_total(df, column, pct)
4.  Row trust score      — row_trust_scores(df)
5.  Saved views          — save_view / list_views / load_view (+ views.json)
6.  Client mode          — render_client_mode_toggle / client_summary
7.  Shareable recipes    — export_recipe_bytes / import_recipe_bytes
                           (same JSON shape as feat_automate recipes)
8.  Keyboard shortcuts   — render_shortcuts_panel (help + a small JS
                           snippet; Streamlit has no native shortcuts)
9.  Multi-file KPIs      — multi_file_kpis(frames)
10. Natural-language Q&A — answer_question (rule layer) + AI fallback
                           through ai_settings (Batch 3; never called
                           without a key, never called in tests)
11. Morning auto-run     — morning_run.py + setup_morning_run.bat
                           (Windows Task Scheduler; set up on the user's
                           own PC, never from here)
12. In-app what's-new    — WHATS_NEW / should_show_whats_new /
                           mark_whats_new_seen (+ seen_version.json
                           locally; per-user views/whats_new_seen.json
                           via storage.py when a user key is given)

Integrator spec (simple_app.py)
-------------------------------
  - Sidebar (under Load): render_client_mode_toggle(st) — sets the data
    key "client_mode"; the coordinator hides the advanced tabs when it
    is True and shows client_summary(df, kpis) instead.
  - Top of the app (right after the title): call
    render_whats_new(st, user_key=_skey) — it shows itself only once
    per new version, per user.
  - Preview tab: render_trust(st, clean) — row health, next to the
    quality panel.
  - KPIs tab: render_what_if(st, filtered) — below "Build your own KPI".
  - Dashboard tab: render_saved_views(st, current_view_dict) at the
    top (returns the view to apply, or None); then
    render_correlations(st, filtered), render_forecast(st, filtered)
    and render_ask(st, filtered) below the charts.
  - Clean tab, "Recipes & templates" expander:
    render_share_recipe(st, recipe) where recipe is the saved recipe
    dict (or None when nothing is saved yet).
  - Compare tab: render_multi_kpi(st).
  - Tools tab: render_shortcuts_panel(st), then
    render_morning_run(st) below the watch-folder block.

Session-state keys (data — never widget keys):
  - "client_mode"   : bool, set by render_client_mode_toggle
  - "an_views_data" : {name: view_dict} mirror of views.json

Widget keys (all start with "an_", none doubles as a data key):
  an_corr_min, an_fc_date, an_fc_num, an_fc_run, an_whatif_col,
  an_whatif_pct, an_trust_n, an_view_name, an_view_save, an_view_pick,
  an_view_apply, an_view_delete, an_client_mode_toggle, an_multi_files,
  an_ask_q, an_ask_run, an_recipe_dl, an_recipe_upload,
  an_morning_dl_py, an_morning_dl_bat, an_morning_write,
  an_whats_new_seen

Local files (in the app folder, next to this module):
  - views.json        : saved views {name: {chart_type, group_by,
                        num_col, slicers}}
  - seen_version.json : {"version": "1.3"} — last what's-new seen
                        (local mode, no user key). With a user key the
                        record lives in that user's per-user storage
                        instead (views/whats_new_seen.json via
                        storage.py), so the dismiss holds per user on
                        Streamlit Cloud too.
  - morning_run.py / setup_morning_run.bat : written by
    write_morning_files() and offered as downloads by
    render_morning_run; morning_in/ and morning_out/ folders are
    created by morning_run.py on the user's PC, not here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

import engine
import feat_automate

try:
    import ai_settings
except ImportError:  # Batch 3 module not landed yet — AI layer stays off
    ai_settings = None

APP_DIR = Path(__file__).resolve().parent
VIEWS_FILE = APP_DIR / "views.json"
SEEN_VERSION_FILE = APP_DIR / "seen_version.json"
# Per-user seen record inside the user's storage "views" folder
# (storage.save_json/load_json). Same shape as seen_version.json.
WHATS_NEW_SEEN_FILENAME = "whats_new_seen.json"
CURRENT_VERSION = "1.3"


# --------------------------------------------------------------------------
# 12. In-app what's-new (kept near the top: render_whats_new is called
#     before anything else, so the version constants live up here)
# --------------------------------------------------------------------------

WHATS_NEW = {
    "1.3": [
        "Correlations: see which numbers move together, in plain words.",
        "Trend forecast: a straight-line guess at tomorrow's number — labelled as a guess, not a promise.",
        "What-if slider: change a number by a % and see the new total instantly.",
        "Row trust score: every row gets a health mark out of 100 — the worst rows are listed first.",
        "Saved views: save a chart plus its slicers under a name and jump back to it in one click.",
        "Client mode: a simple view for a non-technical client — big buttons, advanced tabs hidden.",
        "Shareable recipes: send a cleaning recipe as a small file a teammate can drop in.",
        "Keyboard shortcuts: Ctrl+O jumps to the file uploader, Ctrl+S downloads the cleaned CSV.",
        "Multi-file KPIs: load several monthly files and compare their KPIs in one table.",
        "Ask your data: type a question in plain words and get an answer from the data.",
        "Morning auto-run: a setup file that cleans every file in a folder at 8am on your PC.",
        "What's new: this list — it appears once each time the app gets a new version.",
        "Split & merge columns: split a full name into first/last, or merge two columns into one.",
        "Date intelligence: a date column now gives you Year, Month and Weekday columns.",
        "Currency conversion: turn a column mixing ₹, $ and € into one currency (fixed rates you can edit).",
        "AI insights: one plain-English paragraph on what your data says — needs a free Groq API key in Settings.",
        "Paste a table: copy cells from Excel or a web page and paste them straight in.",
        "Filter rows: build 'show only rows where…' rules and download just the matching rows.",
        "Sampling: clean a 1,000-row sample of a huge file first, then apply it to the full file.",
        "Auto-save workspace: close the app and your file and cleaning come back when you reopen it.",
        "Supabase light theme: near-white, ink text, one deep-green accent — the same look on every screen, whatever your browser's own theme is.",
        "Data masking: hide phone numbers and emails before sharing a file.",
        "Versioned exports: every download gets a new version number, so old files are never overwritten.",
        "Language: the main headings and buttons now speak English, हिन्दी or اردو.",
        "Smart suggestions: the app spots fixable problems and offers each fix in one click.",
        "Column type override: force a column to text, number or date when the guess is wrong.",
        "Standardize phone numbers: every number becomes +91 98765 43210.",
        "Strip special characters: remove emojis and symbols from a text column.",
        "Goal tracking: set a target and watch the progress bar fill up.",
        "Search the whole file: one box finds a value in any column.",
        "Sort the preview: pick a column and a direction.",
        "Recent files: your last 5 files, one click to reopen (with your permission to keep a copy).",
        "Backup before cleaning: the original file is saved first, so you can always go back.",
        "One-click full flow: one button does clean + KPIs + report + email.",
        "Standalone HTML dashboard: the whole dashboard as one file anyone can open in a browser.",
        "Publish to portfolio: a case-study ZIP with the data, a write-up and a chart.",
        "Chart as image: download any chart as a PNG picture.",
        "Styled Excel export: missing values and outliers highlighted red, header row green.",
    ],
}


def _read_seen_version(seen_file=None, user_key=None) -> str | None:
    """Last version the user has seen, or None if never recorded.

    With a user key the record lives in that user's per-user storage
    (views/whats_new_seen.json via storage.py), which holds per user
    in both backends — on Streamlit Cloud the local seen_version.json
    file does not survive across instances, so a plain local file
    can never remember a cloud user's dismiss. Without a user key
    the local seen_version.json file is used, exactly as before
    (local mode / old callers). A storage failure reads as "never
    seen" rather than crashing the page."""
    if user_key is not None:
        import storage
        try:
            data = storage.load_json(user_key, "views",
                                     WHATS_NEW_SEEN_FILENAME)
        except Exception:  # noqa: BLE001 - a broken store must not crash the page
            return None
        if isinstance(data, dict):
            version = data.get("version")
            return str(version) if version else None
        return None
    path = Path(seen_file) if seen_file is not None else SEEN_VERSION_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict):
        version = data.get("version")
        return str(version) if version else None
    return None


def should_show_whats_new(seen_file=None, user_key=None) -> bool:
    """True once per new version: the stored seen-version differs from
    the current version (or nothing was ever stored). Pure check — it
    does not mark anything as seen; render_whats_new does that after
    showing the notes. Pass user_key (the app's per-user storage key)
    so the check is per user in cloud mode; without it the local
    file is checked, as before."""
    return _read_seen_version(seen_file, user_key) != CURRENT_VERSION


def mark_whats_new_seen(seen_file=None, user_key=None) -> None:
    """Record the current version as seen, so the notes stop appearing
    until the next version. With a user key the record goes to that
    user's per-user storage (views/whats_new_seen.json); without one
    it goes to the local seen_version.json file, as before."""
    if user_key is not None:
        import storage
        storage.save_json(user_key, "views", WHATS_NEW_SEEN_FILENAME,
                          {"version": CURRENT_VERSION})
        return None
    path = Path(seen_file) if seen_file is not None else SEEN_VERSION_FILE
    path.write_text(json.dumps({"version": CURRENT_VERSION}, indent=2),
                    encoding="utf-8")


def render_whats_new(st, user_key=None) -> None:
    """Top of the app: show the what's-new notes once per version, then
    mark them seen. Shows nothing at all when this version was already
    seen. Pass user_key (the app's per-user storage key, _skey) so the
    dismiss is remembered per user in cloud mode; without it the
    local file is used, as before. A storage failure on dismiss shows
    a warning instead of crashing the page — the box may then show
    again, but the app keeps working. Returns None."""
    if not should_show_whats_new(user_key=user_key):
        return None
    notes = WHATS_NEW.get(CURRENT_VERSION, [])
    st.subheader(f"What's new in v{CURRENT_VERSION}")
    st.write("A quick look at what changed — press the button and this "
             "box will not pop up again until the next version.")
    for note in notes:
        st.write(f"- {note}")
    if st.button("Got it — don't show this again", key="an_whats_new_seen"):
        try:
            mark_whats_new_seen(user_key=user_key)
        except Exception as e:  # noqa: BLE001 - dismiss failure is not fatal
            st.warning(f"Could not remember that ({e}) — this box may "
                       "show again next time.")
    return None


# --------------------------------------------------------------------------
# 1. Correlation finder
# --------------------------------------------------------------------------

def _strength_word(r: float) -> str:
    """Plain-word strength for a correlation coefficient."""
    a = abs(r)
    if a >= 0.7:
        return "strong"
    if a >= 0.5:
        return "clear"
    return "weak"


def find_correlations(df: pd.DataFrame, min_abs: float = 0.3) -> list:
    """Strongest pairs of number columns, strongest first.

    Returns [{col_a, col_b, r, words}] where r is the Pearson
    correlation (-1 to 1) and words says it in plain English, e.g.
    "When quantity goes up, unit_price tends to go down too — strength
    -0.10 (weak)". Only pairs with |r| >= min_abs are returned, and a
    pair is never listed twice (A-B, never B-A). Needs at least two
    number columns; otherwise the list is empty."""
    num_cols = engine.numeric_cols(df)
    if len(num_cols) < 2:
        return []
    corr = df[num_cols].corr(numeric_only=True)
    found = []
    for i, a in enumerate(num_cols):
        for b in num_cols[i + 1:]:
            r = corr.loc[a, b]
            if pd.isna(r) or abs(float(r)) < min_abs:
                continue
            r = float(r)
            direction = "up" if r > 0 else "down"
            found.append({
                "col_a": a,
                "col_b": b,
                "r": r,
                "words": (f"When {engine._pretty(a)} goes {direction}, "
                          f"{engine._pretty(b)} tends to go {direction} "
                          f"too — strength {r:.2f} "
                          f"({_strength_word(r)})."),
            })
    found.sort(key=lambda d: -abs(d["r"]))
    return found


def render_correlations(st, df: pd.DataFrame) -> None:
    """Dashboard tab, below the charts: the strongest number pairs in
    plain words. Reads nothing from session state. Returns None."""
    st.subheader("What moves together?")
    st.write("Pairs of numbers that rise and fall together. A strength "
             "near 1 (or -1) means they move closely together; near 0 "
             "means they do not move together at all. This is a pattern "
             "in your data, not proof that one causes the other.")
    if df is None or len(df) == 0:
        st.info("Load and clean some data first.")
        return None
    min_abs = st.slider("Only show pairs at least this strong",
                        0.0, 1.0, 0.3, 0.05, key="an_corr_min")
    pairs = find_correlations(df, min_abs=min_abs)
    if not pairs:
        st.info("No number pairs move together that strongly in this "
                "data — try lowering the strength slider.")
        return None
    for p in pairs:
        st.write(f"- **{engine._pretty(p['col_a'])} ↔ "
                 f"{engine._pretty(p['col_b'])}:** {p['words']}")
    st.dataframe(pd.DataFrame(
        [{"Column A": p["col_a"], "Column B": p["col_b"],
          "Correlation": round(p["r"], 3)} for p in pairs]),
        width="stretch")
    return None


# --------------------------------------------------------------------------
# 2. Trend forecast (straight line — a guess, not a promise)
# --------------------------------------------------------------------------

# A slope smaller than this (per day) counts as no trend at all: the
# line is flat, so the guess must sit at the last value and the words
# must say so — a flat series guessed from the line's intercept can
# land far from the last value and contradict it (e.g. guess 2.69
# with last value 3.00 and slope +0.00).
FLAT_SLOPE_EPS = 0.005


def forecast_next(df: pd.DataFrame, date_col: str, num_col: str,
                  periods: int = 1) -> dict:
    """Fit a straight line to a number over time and guess the next
    value(s). Returns {last_value, forecast, slope_per_day, words,
    last_date}. periods is how many days ahead to guess (1 = tomorrow).
    The line is numpy polyfit degree 1 on days since the first date.
    When |slope| < FLAT_SLOPE_EPS the series is flat: slope_per_day
    is reported as 0.0, the guess is the last value, and the words
    say there is no trend — the line's intercept is never allowed to
    pull a flat guess away from the last value. Raises ValueError for
    a missing column, too few dated rows, or periods < 1."""
    if date_col not in df.columns:
        raise ValueError(f"Column '{date_col}' not in the data.")
    if num_col not in df.columns:
        raise ValueError(f"Column '{num_col}' not in the data.")
    if not isinstance(periods, int) or periods < 1:
        raise ValueError("periods must be a whole number of 1 or more")
    dates = pd.to_datetime(df[date_col], errors="coerce")
    values = pd.to_numeric(df[num_col], errors="coerce")
    mask = dates.notna() & values.notna()
    if int(mask.sum()) < 2:
        raise ValueError("Need at least 2 rows with both a date and a "
                         "number to draw a trend line.")
    work = pd.DataFrame({"d": dates[mask], "v": values[mask]})
    work = work.sort_values("d")
    if work["d"].nunique() < 2:
        raise ValueError("Need at least 2 different dates to draw a "
                         "trend line.")
    x = (work["d"] - work["d"].min()).dt.days.astype(float).to_numpy()
    y = work["v"].astype(float).to_numpy()
    slope, intercept = np.polyfit(x, y, 1)
    slope = float(slope)
    last_value = float(y[-1])
    last_date = work["d"].iloc[-1]
    if abs(slope) < FLAT_SLOPE_EPS:
        # Flat — no trend. The straight line's intercept can sit well
        # away from the last value, so a line-based guess would
        # contradict the last value and the "flat" wording; a flat
        # series guesses about the last value instead.
        slope = 0.0
        forecast = last_value
        words = (f"{engine._pretty(num_col)} shows no clear trend — "
                 f"it is flat at around {last_value:,.2f}. The "
                 f"straight-line guess for {periods} day(s) after "
                 f"{last_date.date()} is {last_value:,.2f} (last value "
                 f"{last_value:,.2f}) — a straight-line guess, not a "
                 f"promise.")
    else:
        forecast = float(slope * (x.max() + periods) + intercept)
        direction = "rising" if slope > 0 else "falling"
        words = (f"{engine._pretty(num_col)} is {direction} by about "
                 f"{abs(slope):,.2f} per day. The straight-line guess for "
                 f"{periods} day(s) after {last_date.date()} is "
                 f"{forecast:,.2f} (last value {last_value:,.2f}) — a "
                 f"straight-line guess, not a promise.")
    return {"last_value": last_value, "forecast": forecast,
            "slope_per_day": slope, "words": words,
            "last_date": last_date}


def render_forecast(st, df: pd.DataFrame) -> None:
    """Dashboard tab, below the correlations: pick a date column and a
    number column, get a straight-line guess for the next day. The UI
    labels it honestly as a rough guess. Returns None."""
    st.subheader("Trend forecast")
    st.write("A straight-line guess at the next value — useful for a "
             "rough idea of where a number is heading. It is a guess "
             "from past data, not a promise: real life rarely follows a "
             "straight line.")
    if df is None or len(df) == 0:
        st.info("Load and clean some data first.")
        return None
    date_cols = engine.date_cols(df)
    if not date_cols:
        # Dates stored as text still count once parsed.
        text_dates = [c for c in df.columns
                      if engine.detect_kind(df[c]) == "date"]
        date_cols = text_dates
    num_cols = engine.numeric_cols(df)
    if not date_cols or not num_cols:
        st.info("Need a date column and a number column for a forecast.")
        return None
    c1, c2 = st.columns(2)
    date_col = c1.selectbox("Date column", date_cols, key="an_fc_date")
    num_col = c2.selectbox("Number column", num_cols, key="an_fc_num")
    if st.button("Forecast the next day", key="an_fc_run"):
        try:
            result = forecast_next(df, date_col, num_col, periods=1)
        except ValueError as e:
            st.error(str(e))
            return None
        st.metric(f"Guess for the day after {result['last_date'].date()}",
                  f"{result['forecast']:,.2f}")
        st.write(result["words"])
        st.caption("Last value: "
                   f"{result['last_value']:,.2f}  ·  Slope: "
                   f"{result['slope_per_day']:+,.2f} per day")
    return None


# --------------------------------------------------------------------------
# 3. What-if slider
# --------------------------------------------------------------------------

def what_if_total(df: pd.DataFrame, column: str, pct: float) -> tuple:
    """Current total of a number column, the total after changing every
    value by pct percent, and the difference (new - current). Returns
    (current, new, diff) as floats. Raises ValueError for a missing or
    non-number column."""
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not in the data.")
    if not pd.api.types.is_numeric_dtype(df[column]):
        raise ValueError(f"Column '{column}' is not a number column.")
    current = float(pd.to_numeric(df[column], errors="coerce").sum())
    new = current * (1.0 + float(pct) / 100.0)
    return current, new, new - current


def render_what_if(st, df: pd.DataFrame) -> None:
    """KPIs tab, below "Build your own KPI": pick a number column and a
    % change, see the new total instantly. Returns None."""
    st.subheader("What if...?")
    st.write("Try a change before you make it — for example, what if "
             "every price went up 10%? The totals below update as you "
             "move the slider.")
    if df is None or len(df) == 0:
        st.info("Load and clean some data first.")
        return None
    num_cols = engine.numeric_cols(df)
    if not num_cols:
        st.info("No number columns to try a change on.")
        return None
    c1, c2 = st.columns(2)
    column = c1.selectbox("Number column", num_cols, key="an_whatif_col")
    pct = c2.slider("Change by (%)", -50, 100, 10, 1, key="an_whatif_pct")
    current, new, diff = what_if_total(df, column, pct)
    m1, m2, m3 = st.columns(3)
    m1.metric(f"Current total {engine._pretty(column)}", f"{current:,.2f}")
    m2.metric(f"New total ({pct:+d}%)", f"{new:,.2f}")
    m3.metric("Difference", f"{diff:+,.2f}")
    return None


# --------------------------------------------------------------------------
# 4. Row trust score
# --------------------------------------------------------------------------

def _iqr_bounds(s: pd.Series):
    """(lower, upper) IQR bounds for a numeric series, or None when the
    column has too little spread to judge (fewer than 4 values, or
    IQR 0). Same rule as feat_quality."""
    vals = pd.to_numeric(s, errors="coerce").dropna()
    if len(vals) < 4:
        return None
    q1, q3 = vals.quantile(0.25), vals.quantile(0.75)
    iqr = q3 - q1
    if not np.isfinite(iqr) or iqr <= 0:
        return None
    return float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)


def row_trust_scores(df: pd.DataFrame) -> pd.DataFrame:
    """A health mark (0–100) per row, worst rows first.

    Every row starts at 100 and loses points:
      - 10 points per missing cell;
      - 5 points per value outside the IQR bounds of its number column;
      - 20 points if the row is an exact duplicate of an earlier row.
    Scores never go below 0. Returns a copy of the frame with a
    ``trust_score`` column, sorted worst-first (ties keep file order).
    The input frame is never modified."""
    out = df.copy()
    scores = pd.Series(100, index=df.index, dtype=int)
    # All-empty columns are not a row's fault: count missing cells
    # only over columns that have at least one value.
    missing = df.drop(columns=[c for c in df.columns
                               if df[c].isna().all()]).isna().sum(axis=1)
    scores = scores - (missing * 10)
    for col in engine.numeric_cols(df):
        bounds = _iqr_bounds(df[col])
        if bounds is None:
            continue
        lower, upper = bounds
        s = pd.to_numeric(df[col], errors="coerce")
        scores = scores - (((s < lower) | (s > upper)) * 5)
    scores = scores - (df.duplicated(keep="first") * 20)
    out["trust_score"] = scores.clip(lower=0, upper=100).astype(int)
    out = out.sort_values("trust_score", kind="stable").reset_index(drop=True)
    return out


def render_trust(st, df: pd.DataFrame) -> None:
    """Preview tab, next to the quality panel: the least-trusted rows
    first, with what is wrong with each. Returns None."""
    st.subheader("Row trust scores")
    st.write("Every row gets a health mark out of 100. A row loses 10 "
             "points per empty cell, 5 per unusual (outlier) value and "
             "20 if it is an exact copy of an earlier row. The least "
             "trusted rows are listed first — check those before you "
             "trust the numbers.")
    if df is None or len(df) == 0:
        st.info("Load some data first.")
        return None
    scored = row_trust_scores(df)
    worst = scored[scored["trust_score"] < 100]
    st.metric("Rows below a perfect 100", f"{len(worst):,} of {len(df):,}")
    if len(worst) == 0:
        st.success("Every row scores 100 — no empty cells, outliers or "
                   "duplicate rows.")
        return None
    n = st.slider("How many worst rows to show", 5, 50, 10, 5,
                  key="an_trust_n")
    st.dataframe(worst.head(n), width="stretch")
    return None


# --------------------------------------------------------------------------
# 5. Saved views (views.json + session state)
# --------------------------------------------------------------------------

def _read_views_file(views_file=None) -> dict:
    """{name: view_dict} from views.json, or {} when the file is missing
    or unreadable."""
    path = Path(views_file) if views_file is not None else VIEWS_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_views_file(views: dict, views_file=None) -> None:
    path = Path(views_file) if views_file is not None else VIEWS_FILE
    path.write_text(json.dumps(views, indent=2, sort_keys=True),
                    encoding="utf-8")


def save_view(name: str, view_dict: dict, views_file=None) -> dict:
    """Save a named view: {chart_type, group_by, num_col, slicers}.
    Writes views.json so the view survives restarts. Saving under a
    name that already exists replaces it. Returns the stored view dict.
    Raises ValueError for an empty name or a non-dict view."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("A view needs a non-empty name")
    if not isinstance(view_dict, dict):
        raise ValueError("A view must be a dict "
                         "({chart_type, group_by, num_col, slicers})")
    views = _read_views_file(views_file)
    views[name.strip()] = dict(view_dict)
    _write_views_file(views, views_file)
    return dict(view_dict)


def list_views(views_file=None) -> list:
    """Names of the saved views, A–Z. Empty list when none are saved."""
    return sorted(_read_views_file(views_file))


def load_view(name: str, views_file=None) -> dict:
    """The saved view dict for ``name``. Raises KeyError when no view
    with that name exists."""
    views = _read_views_file(views_file)
    if name not in views:
        raise KeyError(f"No saved view named '{name}'")
    return dict(views[name])


def render_saved_views(st, current_view_dict) -> dict | None:
    """Dashboard tab, at the top: save the current chart + slicer
    combination under a name, or jump back to a saved view in one
    click. current_view_dict is {chart_type, group_by, num_col,
    slicers} for the chart on screen right now (or None when no chart
    is set yet). Returns the view to apply, or None. The coordinator
    applies the returned view (chart type, group-by, number column and
    slicer values) and reruns."""
    st.subheader("Saved views")
    st.write("Save this chart and its filters under a name, then jump "
             "back to the exact same view in one click — even after "
             "closing and reopening the app.")
    if "an_views_data" not in st.session_state:
        st.session_state["an_views_data"] = _read_views_file()
    c1, c2 = st.columns([2, 1])
    name = c1.text_input("View name", key="an_view_name",
                         placeholder="e.g. Sales by region")
    if c2.button("Save this view", key="an_view_save"):
        if not name.strip():
            st.warning("Give the view a name first.")
        elif not current_view_dict:
            st.warning("Set up a chart first — there is nothing to save yet.")
        else:
            try:
                save_view(name, current_view_dict)
            except ValueError as e:
                st.error(str(e))
            else:
                st.session_state["an_views_data"] = _read_views_file()
                st.success(f"Saved view '{name.strip()}'.")
    names = list_views()
    if not names:
        st.info("No saved views yet — save one above.")
        return None
    picked = st.selectbox("Saved views", names, key="an_view_pick")
    c1, c2 = st.columns(2)
    if c1.button("Go to this view", type="primary", key="an_view_apply"):
        try:
            return load_view(picked)
        except KeyError as e:
            st.error(str(e))
            return None
    if c2.button("Delete this view", key="an_view_delete"):
        views = _read_views_file()
        views.pop(picked, None)
        _write_views_file(views)
        st.session_state["an_views_data"] = views
        st.success(f"Deleted view '{picked}'.")
    return None


# --------------------------------------------------------------------------
# 6. Client mode
# --------------------------------------------------------------------------

def render_client_mode_toggle(st) -> None:
    """Sidebar, under Load: a checkbox that switches the app into a
    simplified view for a non-technical client. Stores the flag in the
    data key "client_mode" (the widget itself uses the separate key
    "an_client_mode_toggle"). The coordinator hides the advanced tabs
    when client_mode is True and shows client_summary instead. This
    function only owns the toggle. Returns None."""
    st.sidebar.checkbox(
        "Client mode (simple view)", value=False,
        key="an_client_mode_toggle",
        help="A simplified view for a non-technical client: big buttons, "
             "advanced tabs hidden. Turn it off to get the full app back.")
    st.session_state["client_mode"] = bool(
        st.session_state.get("an_client_mode_toggle", False))
    return None


def client_summary(df: pd.DataFrame, kpis: list | None) -> str:
    """One plain-words paragraph for client mode: how many rows, the
    headline totals and the top category. kpis is engine.auto_kpis(df)
    (a list of {label, value}) or None. Never raises on an empty frame
    — it says so plainly instead."""
    if df is None or len(df) == 0:
        return "No data loaded yet."
    lines = [f"This file has {len(df):,} rows and {len(df.columns)} columns."]
    kpis = kpis or []
    by_label = {k.get("label", ""): k.get("value", "") for k in kpis
                if isinstance(k, dict)}
    totals = [f"{label}: {value}" for label, value in by_label.items()
              if label.startswith(("Total ", "Sum of ", "Revenue ("))]
    if totals:
        lines.append("Headline totals — " + "; ".join(totals[:3]) + ".")
    cat_cols = [c for c in df.columns
                if str(df[c].dtype) in ("object", "str")
                and 1 < df[c].nunique(dropna=True) <= 30]
    if cat_cols:
        col = cat_cols[0]
        top = df[col].value_counts(dropna=False)
        lines.append(f"The most common {engine._pretty(col)} is "
                     f"{top.index[0]} ({int(top.iloc[0]):,} rows).")
    lines.append("The data has been cleaned and checked — the numbers "
                 "above are the ones to use.")
    return " ".join(lines)


# --------------------------------------------------------------------------
# 7. Shareable recipes (same JSON shape as feat_automate recipes)
# --------------------------------------------------------------------------

def export_recipe_bytes(recipe: dict) -> bytes:
    """A recipe as bytes for a download / file share. Uses
    feat_automate.recipe_to_json, so the JSON is exactly the shape the
    app's own recipes use: {name, clean_opts, fuzzy}. Raises ValueError
    for an invalid recipe."""
    return feat_automate.recipe_to_json(recipe).encode("utf-8")


def import_recipe_bytes(raw_bytes) -> dict:
    """Parse a recipe from bytes (or str) shared by a teammate. Uses
    feat_automate.recipe_from_json, so a recipe that fails validation
    here fails the same way everywhere else. Returns the recipe dict.
    Raises ValueError on bad JSON or a bad recipe."""
    if isinstance(raw_bytes, (bytes, bytearray)):
        raw_bytes = bytes(raw_bytes).decode("utf-8")
    return feat_automate.recipe_from_json(raw_bytes)


def render_share_recipe(st, recipe) -> dict | None:
    """Clean tab, "Recipes & templates" expander: download the current
    recipe as a small .json file a teammate can drop in, and load a
    recipe file shared by a teammate. recipe is the saved recipe dict
    (or None when nothing is saved yet). Returns the imported recipe
    dict when a file was just loaded, otherwise None. The coordinator
    applies a returned recipe the same way it applies any saved one."""
    st.subheader("Share a recipe")
    st.write("Send your cleaning steps to a teammate as a small file. "
             "They drop it in here and get the exact same cleaning — "
             "same fixes, same spelling merges. A recipe never carries "
             "your data, only the steps.")
    if recipe is not None:
        try:
            data = export_recipe_bytes(recipe)
        except ValueError as e:
            st.error(str(e))
        else:
            st.download_button(
                f"Download recipe '{recipe.get('name', '')}' (.json)",
                data, file_name=f"{str(recipe.get('name', 'recipe')).replace(' ', '_')}_recipe.json",
                mime="application/json", key="an_recipe_dl")
    else:
        st.info("No recipe to share yet — save one above first.")
    uploaded = st.file_uploader("Load a recipe shared by a teammate (.json)",
                                type=["json"], key="an_recipe_upload")
    if uploaded is not None:
        try:
            imported = import_recipe_bytes(uploaded.getvalue())
        except ValueError as e:
            st.error(f"That recipe file is not valid: {e}")
            return None
        st.success(f"Loaded recipe '{imported['name']}' — apply it from "
                   "the saved recipes list above.")
        return imported
    return None


# --------------------------------------------------------------------------
# 8. Keyboard shortcuts (honest version: Streamlit has no native
#    shortcuts, so this is a help panel + a small browser snippet)
# --------------------------------------------------------------------------

SHORTCUTS_JS = """<script>
(function () {
  // Browser shortcuts for Data Cleaner Studio. They only work while
  // this app is open in your browser tab.
  document.addEventListener('keydown', function (e) {
    // Ctrl+O: jump to the file uploader in the sidebar.
    if (e.ctrlKey && !e.shiftKey && (e.key === 'o' || e.key === 'O')) {
      var up = document.querySelector('input[type="file"]');
      if (up) { e.preventDefault(); up.focus(); up.click(); }
    }
    // Ctrl+S: click the "Download cleaned CSV" button.
    if (e.ctrlKey && !e.shiftKey && (e.key === 's' || e.key === 'S')) {
      var btns = Array.prototype.slice.call(
        document.querySelectorAll('button'));
      var dl = btns.find(function (b) {
        return b.innerText.indexOf('Download cleaned CSV') !== -1;
      });
      if (dl) { e.preventDefault(); dl.click(); }
    }
  });
})();
</script>"""

SHORTCUTS = [
    ("Ctrl+O", "Jump to the file uploader (pick a file to load)."),
    ("Ctrl+S", "Download the cleaned CSV (works once the data is cleaned)."),
]


def render_shortcuts_panel(st) -> None:
    """Tools tab: a help section listing the shortcuts, plus the small
    JavaScript snippet that makes them work in the browser. Labelled
    clearly as browser shortcuts that work while the app is open —
    Streamlit itself has no shortcut support, and no shortcut is
    claimed that the snippet cannot do. Returns None."""
    st.subheader("Keyboard shortcuts")
    st.write("These are browser shortcuts — they work while this app is "
             "open in your browser tab. They do not work when the app "
             "is closed, and there are only two of them: Streamlit has "
             "no built-in shortcut support, so this is everything the "
             "app can offer.")
    for keys, what in SHORTCUTS:
        st.write(f"- **{keys}** — {what}")
    st.caption("Tip: Ctrl+O focuses the file uploader in the sidebar; "
               "Ctrl+S clicks the same 'Download cleaned CSV' button "
               "you see on the Report tab.")
    st.markdown(SHORTCUTS_JS, unsafe_allow_html=True)
    return None


# --------------------------------------------------------------------------
# 9. Multi-file KPI screen
# --------------------------------------------------------------------------

def multi_file_kpis(frames: dict) -> pd.DataFrame:
    """One comparison table for several files: one row per file, one
    column per KPI. frames is {file_name: DataFrame}. Every file is
    measured with the same KPIs (engine.auto_kpis), so the columns
    line up; a KPI a file does not have is left blank. Returns a
    DataFrame with "file" first, then the KPI labels in the order they
    first appear. Raises ValueError for an empty dict."""
    if not isinstance(frames, dict) or not frames:
        raise ValueError("Give at least one file ({name: DataFrame})")
    labels = []
    rows = []
    for name, df in frames.items():
        if not isinstance(df, pd.DataFrame):
            raise ValueError(f"File '{name}' is not a table of data")
        kpis = engine.auto_kpis(df)
        row = {"file": str(name)}
        for k in kpis:
            label = k["label"]
            if label not in labels:
                labels.append(label)
            row[label] = k["value"]
        rows.append(row)
    table = pd.DataFrame(rows, columns=["file"] + labels)
    return table.fillna("")


def render_multi_kpi(st) -> None:
    """Compare tab: upload several files (for example one per month),
    clean each one the same way, and compare their KPIs in one table.
    Returns None."""
    st.subheader("Compare KPIs across files")
    st.write("Load several files — one per month, for example — and see "
             "the same KPIs for each, side by side in one table. Each "
             "file is cleaned with the standard all-fixes cleaning "
             "first, so the comparison is fair.")
    files = st.file_uploader(
        "Files to compare", type=["csv", "xlsx", "xls", "json"],
        accept_multiple_files=True, key="an_multi_files")
    if not files:
        st.info("Add at least one file — two or more makes a real "
                "comparison.")
        return None
    frames = {}
    for f in files:
        try:
            raw = engine.load_file(f.name, f.getvalue())
            cleaned, _actions = engine.clean(
                raw, feat_automate.to_engine_opts(
                    dict(feat_automate.DEFAULT_CLEAN_OPTS)))
            frames[f.name] = cleaned
        except Exception as e:  # noqa: BLE001 - one bad file must not stop the rest
            st.error(f"Could not read {f.name}: {e}")
    if not frames:
        return None
    table = multi_file_kpis(frames)
    st.dataframe(table, width="stretch")
    st.download_button("Download KPI comparison (.csv)",
                       table.to_csv(index=False).encode("utf-8"),
                       file_name="kpi_comparison.csv", mime="text/csv",
                       key="an_multi_dl")
    return None


# --------------------------------------------------------------------------
# 10. Natural-language questions (rule layer + AI fallback)
# --------------------------------------------------------------------------

def _find_column(question: str, columns: list) -> str | None:
    """The first column whose name (or pretty name, e.g. 'unit price'
    for unit_price) appears in the question text. None when no column
    is mentioned."""
    q = question.lower()
    for col in columns:
        name = str(col).lower()
        pretty = engine._pretty(col).lower()
        if name in q or pretty in q:
            return col
    return None


def _category_columns(df: pd.DataFrame) -> list:
    return [c for c in df.columns
            if str(df[c].dtype) in ("object", "str")
            and 1 < df[c].nunique(dropna=True) <= 50]


_SALES_QUESTION_RE = re.compile(r"\b(sold|sell|sales|sale)\b")


def _column_name_tokens(col) -> set:
    """Lowercase word tokens of a column name: unit_price -> {unit,
    price}, so "price" matches but "salesperson" does not match
    "sales"."""
    return {t for t in re.split(r"[^a-z0-9]+", str(col).lower()) if t}


def _find_measure_column(df: pd.DataFrame, tokens) -> str | None:
    """First number column whose name contains one of the tokens, or
    None. Only number columns count — a text column called e.g.
    sales_region is not a measure."""
    wanted = set(tokens)
    for col in engine.numeric_cols(df):
        if _column_name_tokens(col) & wanted:
            return col
    return None


def _sales_measure(df: pd.DataFrame):
    """The sales measure for a "sold the most" question: (label,
    per-row values), or None when the data has nothing to measure
    sales with. Preference order:
      1. a revenue/sales column, summed as revenue;
      2. a quantity x price pair, multiplied row by row as revenue;
      3. a quantity column on its own, as total quantity sold;
      4. the single number column, as its total.
    A row count is never a sales measure."""
    revenue_col = _find_measure_column(
        df, ("revenue", "sales", "turnover"))
    if revenue_col is not None:
        return ("revenue",
                pd.to_numeric(df[revenue_col], errors="coerce"))
    qty_col = _find_measure_column(
        df, ("quantity", "qty", "units", "sold"))
    price_col = _find_measure_column(
        df, ("price", "rate", "amount", "cost"))
    if (qty_col is not None and price_col is not None
            and qty_col != price_col):
        return ("revenue",
                pd.to_numeric(df[qty_col], errors="coerce")
                * pd.to_numeric(df[price_col], errors="coerce"))
    if qty_col is not None:
        return ("total quantity sold",
                pd.to_numeric(df[qty_col], errors="coerce"))
    num_cols = engine.numeric_cols(df)
    if len(num_cols) == 1:
        col = num_cols[0]
        return (f"total {engine._pretty(col)}",
                pd.to_numeric(df[col], errors="coerce"))
    return None


def answer_question(df: pd.DataFrame, question: str) -> str:
    """Answer a plain-words question from the data — no API key needed.

    Patterns handled:
      - top value of a category column ("what is the most common
        category?") — the top value by row count, or by the total of
        a named number column;
      - "sold the most" / "most sales" ("which region sold the
        most?") — the top category by a SALES measure (revenue where
        a quantity x price pair is available, else total quantity
        sold), with the measure named in the answer. A row count is
        never presented as sales;
      - sum / average / max / min of a number column ("what is the
        total unit_price?", "what is the average quantity?");
      - count of rows matching a simple condition ("how many orders
        are Delivered?", "how many rows are there?").
    Returns the answer as one plain sentence, or "" when the question
    matches no pattern — the caller then tries the AI layer (when a
    key is set) or explains that a key is needed for free-form
    questions. Never calls any API."""
    if df is None or len(df) == 0:
        return "No data loaded yet — load a file first."
    if not isinstance(question, str) or not question.strip():
        return ""
    q = question.strip().lower()
    num_cols = engine.numeric_cols(df)
    cat_cols = _category_columns(df)

    # --- count of rows matching a simple condition -------------------
    if "how many" in q or "count" in q:
        if "row" in q and not any(
                str(v).lower() in q
                for c in cat_cols
                for v in df[c].dropna().unique()):
            return f"There are {len(df):,} rows in this data."
        for col in cat_cols:
            for value in df[col].dropna().unique():
                text = str(value).strip()
                if text and text.lower() in q:
                    n = int((df[col].astype(object).astype(str)
                             .str.strip().str.lower()
                             == text.lower()).sum())
                    return (f"{n:,} row(s) have "
                            f"{engine._pretty(col)} = {text}.")
        if "row" in q:
            return f"There are {len(df):,} rows in this data."

    # --- top category by the total of a named number column ---------
    # ("which region has the highest total unit_price?") — this must
    # run before the plain total below, or "total" would win first.
    num_col = _find_column(q, num_cols)
    cat_col = _find_column(q, cat_cols)
    if (num_col is not None and cat_col is not None
            and any(w in q for w in ("which", "top", "most", "highest",
                                     "biggest", "largest"))):
        grouped = df.groupby(cat_col, dropna=False)[num_col].sum()
        best = grouped.sort_values(ascending=False)
        return (f"{best.index[0]} has the highest total "
                f"{engine._pretty(num_col)} "
                f"({float(best.iloc[0]):,.2f}).")

    # --- sum / average / max / min of a number column ---------------
    if num_col is not None:
        s = pd.to_numeric(df[num_col], errors="coerce")
        pretty = engine._pretty(num_col)
        if "total" in q or "sum" in q:
            return f"The total {pretty} is {float(s.sum()):,.2f}."
        if "average" in q or "mean" in q:
            return f"The average {pretty} is {float(s.mean()):,.2f}."
        if any(w in q for w in ("highest", "maximum", "max", "largest",
                                "biggest", "most expensive")):
            return (f"The highest {pretty} is {float(s.max()):,.2f}.")
        if any(w in q for w in ("lowest", "minimum", "min", "smallest",
                                "cheapest")):
            return f"The lowest {pretty} is {float(s.min()):,.2f}."

    # --- "sold the most" / "most sales": measure sales, never count --
    # "Which region sold the most?" is a sales question, not a "most
    # rows" question — so aggregate the sales measure and name it in
    # the answer (e.g. "by revenue"). A row count is never presented
    # as sales. Runs before the plain top-value branch below, which
    # would otherwise answer with a row count.
    if (cat_col is not None and _SALES_QUESTION_RE.search(q)
            and any(w in q for w in ("most", "top", "which", "highest",
                                     "biggest", "largest"))):
        measure = _sales_measure(df)
        if measure is None:
            return ("I can't measure sales from this data — there is "
                    "no quantity or price column to add up.")
        label, values = measure
        grouped = values.groupby(df[cat_col], dropna=False).sum()
        best = grouped.sort_values(ascending=False)
        return (f"{best.index[0]} sold the most, by {label} "
                f"({float(best.iloc[0]):,.2f}).")

    # --- top value of a category column ------------------------------
    cat_col = _find_column(q, cat_cols)
    if cat_col is not None and any(
            w in q for w in ("most", "top", "biggest", "common", "which",
                             "largest", "highest")):
        top = df[cat_col].value_counts(dropna=False)
        top_value, top_n = top.index[0], int(top.iloc[0])
        if num_col is not None:
            grouped = df.groupby(cat_col, dropna=False)[num_col].sum()
            best = grouped.sort_values(ascending=False)
            return (f"{best.index[0]} has the highest total "
                    f"{engine._pretty(num_col)} "
                    f"({float(best.iloc[0]):,.2f}).")
        return (f"The most common {engine._pretty(cat_col)} is "
                f"{top_value} ({top_n:,} rows).")
    return ""


def _data_summary_for_ai(df: pd.DataFrame) -> str:
    """A small text summary of the data to send with a free-form
    question — shape, columns, totals and top values only, never the
    full table."""
    lines = [f"Rows: {len(df)}, columns: {', '.join(str(c) for c in df.columns)}."]
    for col in engine.numeric_cols(df):
        s = pd.to_numeric(df[col], errors="coerce")
        lines.append(f"{col}: total {float(s.sum()):,.2f}, "
                     f"average {float(s.mean()):,.2f}, "
                     f"min {float(s.min()):,.2f}, max {float(s.max()):,.2f}.")
    for col in _category_columns(df):
        top = df[col].value_counts(dropna=False).head(3)
        lines.append(f"{col}: top values — " + ", ".join(
            f"{v} ({int(n)})" for v, n in top.items()) + ".")
    return "\n".join(lines)


def render_ask(st, df: pd.DataFrame) -> None:
    """Dashboard tab, below the forecast: type a question in plain
    words and get an answer from the data. Common questions are
    answered straight from the data with no key needed. A question
    that matches no built-in pattern goes to the AI (via ai_settings)
    only when an API key is set; without a key the app says plainly
    that a key is needed for free-form questions. AI answers are
    always labelled as AI-generated. Returns None."""
    st.subheader("Ask your data")
    st.write("Type a question in plain words — for example 'which "
             "region sold the most?', 'what is the total unit_price?' "
             "or 'how many orders are Delivered?'. Common questions "
             "are answered straight from the data, no key needed.")
    if df is None or len(df) == 0:
        st.info("Load and clean some data first.")
        return None
    question = st.text_input("Your question", key="an_ask_q",
                             placeholder="e.g. which region sold the most?")
    if not st.button("Ask", key="an_ask_run"):
        return None
    if not question.strip():
        st.warning("Type a question first.")
        return None
    answer = answer_question(df, question)
    if answer:
        st.success(answer)
        return None
    # No built-in pattern matched — AI layer, only with a key.
    if ai_settings is None:
        st.info("That question needs free-form answering, which needs "
                "an API key — and the AI settings are not set up in "
                "this build yet. The built-in answers cover top values, "
                "totals, averages, highest/lowest and simple counts.")
        return None
    try:
        key = ai_settings.get_api_key()
    except Exception:  # noqa: BLE001 - a broken settings module must not crash the tab
        key = None
    if not key:
        st.info("That question needs free-form answering, which needs "
                "an API key. Add one in Settings and ask again — the "
                "built-in answers above cover top values, totals, "
                "averages, highest/lowest and simple counts.")
        return None
    try:
        prompt = (f"Answer this question about the data below in one "
                  f"short plain sentence, using only the numbers given.\n"
                  f"Question: {question}\n\nData summary:\n"
                  f"{_data_summary_for_ai(df)}")
        ai_answer = ai_settings.ask_ai(
            prompt,
            system="You answer questions about a table of data. "
                   "Use only the numbers in the summary. If the summary "
                   "cannot answer the question, say so plainly.")
    except Exception as e:  # noqa: BLE001 - show the AI error, don't crash
        st.error(f"The AI answer failed: {e}")
        return None
    st.write(f"**AI-generated answer:** {ai_answer}")
    return None


# --------------------------------------------------------------------------
# 11. Morning auto-run (Windows Task Scheduler — user runs the setup)
# --------------------------------------------------------------------------

MORNING_RUN_PY = '''#!/usr/bin/env python3
"""Morning run — Data Cleaner Studio (Batch 5, v1.3).

Cleans every file in a `morning_in/` folder with a saved recipe and
writes the cleaned files to `morning_out/`. Made to be run by Windows
Task Scheduler every morning (see setup_morning_run.bat), but it also
runs by hand:

    python morning_run.py [--in DIR] [--out DIR] [--recipe FILE]

--in defaults to morning_in/ next to this script, --out to
morning_out/ next to it, --recipe to morning_recipe.json next to it.
Without a recipe file it uses the standard all-fixes cleaning.
One bad file is logged and skipped; the rest still get cleaned.
Needs only plain python3 + pandas. No Streamlit, no Task Scheduler.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import engine  # noqa: E402
import feat_automate  # noqa: E402

FILE_TYPES = (".csv", ".xlsx", ".xls", ".json")


def run_morning(in_dir, out_dir, recipe_path=None):
    """Clean every supported file in in_dir with the recipe and write
    cleaned CSVs (+ a cleaning log per file) into out_dir. Returns a
    list of result dicts: {name, rows_in, rows_out, status}. Missing
    folders are created; a missing in_dir means nothing to do."""
    in_dir, out_dir = Path(in_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if recipe_path is not None and Path(recipe_path).exists():
        recipe = feat_automate.recipe_from_json(
            Path(recipe_path).read_text(encoding="utf-8"))
    else:
        recipe = feat_automate.save_recipe(
            dict(feat_automate.DEFAULT_CLEAN_OPTS), {}, "morning-default")
    results = []
    if not in_dir.exists():
        in_dir.mkdir(parents=True, exist_ok=True)
        return results
    for path in sorted(in_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in FILE_TYPES:
            continue
        try:
            raw = engine.load_file(path.name, path.read_bytes())
            rows_in = len(raw)
            cleaned, actions = feat_automate.apply_recipe(raw, recipe)
            stem = path.stem
            cleaned.to_csv(out_dir / f"{stem}_cleaned.csv", index=False)
            log_lines = [f"{step}: {detail}" for step, detail in actions]
            (out_dir / f"{stem}_log.txt").write_text(
                "\\n".join(log_lines), encoding="utf-8")
            results.append({"name": path.name, "rows_in": rows_in,
                            "rows_out": len(cleaned), "status": "OK"})
            print(f"{path.name}: {rows_in} -> {len(cleaned)} rows cleaned.")
        except Exception as e:  # noqa: BLE001 - one bad file must not stop the run
            results.append({"name": path.name, "rows_in": None,
                            "rows_out": None, "status": f"Failed: {e}"})
            print(f"{path.name}: FAILED — {e}")
    (out_dir / "morning_run_summary.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    return results


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="in_dir", default=str(here / "morning_in"),
                        help="Folder with the messy files (default: morning_in/)")
    parser.add_argument("--out", dest="out_dir", default=str(here / "morning_out"),
                        help="Folder for cleaned files (default: morning_out/)")
    parser.add_argument("--recipe", default=str(here / "morning_recipe.json"),
                        help="Recipe .json to clean with (default: morning_recipe.json)")
    args = parser.parse_args()
    results = run_morning(args.in_dir, args.out_dir, args.recipe)
    ok = sum(1 for r in results if r["status"] == "OK")
    print(f"Morning run done: {ok} of {len(results)} file(s) cleaned.")


if __name__ == "__main__":
    main()
'''

MORNING_SETUP_BAT = """@echo off
REM Morning auto-run setup — Data Cleaner Studio (Batch 5, v1.3).
REM Double-click this file on your own PC. It registers a Windows
REM scheduled task that runs morning_run.py every morning at 8:00am.
REM Nothing is scheduled until you run this file yourself, and you can
REM remove the task any time with:
REM   schtasks /delete /tn "Data Cleaner Studio Morning Run" /f
REM This file needs morning_run.py in the same folder.

set "HERE=%~dp0"
set "PY=%HERE%Data-Cleaner-Studio\\python\\python.exe"
if not exist "%PY%" set "PY=python"
schtasks /create /tn "Data Cleaner Studio Morning Run" /tr "\\"%PY%\\" \\"%HERE%morning_run.py\\"" /sc daily /st 08:00 /f
if %ERRORLEVEL%==0 (
  echo Done — the morning run is set for 8:00am every day.
  echo Put messy files in the morning_in folder and find the cleaned
  echo files in morning_out each morning.
) else (
  echo Could not create the scheduled task. Try right-clicking this
  echo file and choosing "Run as administrator".
)
pause
"""


def write_morning_files(directory=None) -> dict:
    """Write morning_run.py and setup_morning_run.bat into directory
    (default: the app folder). Returns {filename: path}. The two files
    are also available as the MORNING_RUN_PY / MORNING_SETUP_BAT
    constants for download buttons."""
    target = Path(directory) if directory is not None else APP_DIR
    target.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, text in (("morning_run.py", MORNING_RUN_PY),
                       ("setup_morning_run.bat", MORNING_SETUP_BAT)):
        path = target / name
        path.write_text(text, encoding="utf-8")
        written[name] = path
    return written


def render_morning_run(st) -> None:
    """Tools tab, below the watch-folder block: download the two
    morning-run files and read plain instructions. This CANNOT be
    activated from here — the scheduled task only exists once the user
    runs setup_morning_run.bat on his own PC, by double-clicking it.
    The UI text says so plainly. Returns None."""
    st.subheader("Morning auto-run (8am)")
    st.write("Want the cleaning done before you sit down? Put messy "
             "files in a `morning_in` folder in the evening and find "
             "the cleaned files in `morning_out` each morning.")
    st.write("This cannot be switched on from inside the app. The "
             "setup file below only works on your own PC: download "
             "both files, keep them in the same folder as the app, "
             "then double-click `setup_morning_run.bat`. That is the "
             "step that creates the 8am schedule in Windows Task "
             "Scheduler — nothing is scheduled until you run it. "
             "To remove it later, run: "
             "`schtasks /delete /tn \"Data Cleaner Studio Morning Run\" /f`.")
    st.write("The run uses the recipe in `morning_recipe.json` next "
             "to the script (save one from the Clean tab and rename "
             "it), or the standard all-fixes cleaning when there is "
             "no recipe file. One bad file is logged and skipped; "
             "the rest still get cleaned.")
    st.download_button("Download morning_run.py",
                       MORNING_RUN_PY.encode("utf-8"),
                       file_name="morning_run.py", key="an_morning_dl_py")
    st.download_button("Download setup_morning_run.bat",
                       MORNING_SETUP_BAT.encode("utf-8"),
                       file_name="setup_morning_run.bat",
                       key="an_morning_dl_bat")
    if st.button("Save both files next to the app",
                 key="an_morning_write"):
        written = write_morning_files()
        st.success("Saved: " + ", ".join(sorted(written)) + ".")
    return None
