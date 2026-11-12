"""Compare tab as Supabase's Logs page, mapped to this app's own
activity (the mapping the clone spec confirms: Compare -> Logs).

Supabase's Logs page, from the audit (spec Pass B2 section 2): an H1
with BETA + NEW badges and a dismissible banner; a left filter panel
(Time Range, Log Type checkboxes, Level checkboxes, collapsed
groups, "Capture your logs" + Go to Log Drains); a top bar
(free-text filter, Refresh, rows-per-page, Download logs, green
Live toggle); a timeline histogram; a table DATE / source / status /
METHOD / PATHNAME / EVENT MESSAGE (green 200 / amber 400 chips);
row click -> a bottom detail drawer (tabs Overview / Raw JSON /
Timeline / User, copy/AI/close, collapsible Log fields).

The mapping onto this app's REAL log, honestly:

* The log IS the app's own audit trail (``q_audit`` — the list of
  {"time", "step", "detail"} the app already records). An entry
  exists only because the app recorded it: a clean, a join, a file
  or sample load, a database load, a quality action. Nothing is
  invented, and no log row is fabricated to fill the table.
* Log Type is the subsystem the step belongs to: Clean (clean runs
  and clean operations), Quality (outlier / near-duplicate /
  fuzzy-merge actions), Database (database loads), File (sample
  and file loads, failed loads), Join (joins). Steps the app does
  not know yet land in "Other" rather than being forced into a
  bucket.
* Level is Success for every completed action and Error for a
  failed load or a failed join preview. The app records no
  warning-grade events, so the Warning filter honestly shows (0)
  instead of pretending otherwise.
* Time Range, the free-text filter, rows-per-page, Download logs
  (CSV of the filtered entries) and Refresh are all real: they
  filter / export / re-read the same audit trail.
* The timeline histogram is a real count of entries per hour (per
  day when the entries span more than a day), not a Supabase
  traffic chart.
* Row click opens the detail the way stock Streamlit allows: a
  selectbox picks the entry and the detail renders below the table
  with Overview / Raw JSON tabs — the same drawer contents
  (fields, raw JSON), without the bottom-drawer chrome Streamlit
  cannot build.
* The log covers this session only: ``q_audit`` resets when a new
  file is loaded (``_set_raw`` clears it), so loading a file
  starts a fresh log whose first entry is the load itself.

Compare semantics: the tab is named Compare, so beside the Logs
view there is a "Compare runs" view — the Clean entries in the
audit trail are real runs (each "80 -> 77 rows" with a timestamp),
and picking two runs shows each run's before/after and the delta
between them. Snapshots (``a_snaps``) hold the KPIs of earlier
states, so when two KPI-bearing snapshots exist the same view
compares their KPIs with ``feat_combine.compare_kpis``. The old
file-comparison feature (``feat_combine.render_compare`` plus the
Combine & check expander) lives under "Compare files" in the
sub-nav, moved verbatim — nothing about it changed.

What is NOT built, and why (stated plainly, not faked):

* Live tail / the green Live toggle: stock Streamlit cannot push
  log lines to the browser as they happen — there is no streaming.
  The Refresh button is the honest equivalent: it re-reads the
  audit trail. The toggle is omitted, not drawn disabled.
* A log query language (Supabase's "Filter by Time range, Log
  Type, Level..." structured syntax): the free-text filter is a
  plain substring match on step + detail. No fake query parser.
* Log Drains / "Capture your logs": this app has no log drains,
  so there is nowhere to route logs to. Omitted, not gated.
* Timeline / User tabs in the detail drawer: a log entry has no
  per-entry timeline and no user attached to it, so the drawer
  has Overview and Raw JSON only.
* "Explain with AI": the app has no log-explanation feature, so
  the drawer offers the raw JSON (copyable) and nothing else.
* Clickable log-graph elements / a whole table row as one link:
  stock Streamlit cannot make a dataframe row clickable — the
  "Open log entry" selectbox is the honest equivalent.

Contract:
  - classify_log(entry) -> dict — pure: the entry plus "type"
    and "level" (defaults for missing keys).
  - filter_logs(entries, time_range="all", types=None,
    levels=None, query="") -> [classified] — pure, chronological
    order preserved; each classified entry also carries "_idx",
    its position in the input list (the detail picker uses it).
  - histogram_counts(entries) -> [(label, count)] — pure:
    per-hour buckets, per-day when the entries span > 1 day.
  - parse_clean_detail(detail) -> (before, after) | None — pure.
  - clean_runs(audit) -> [run] — pure: one {time, before, after,
    removed} per "Clean" audit entry, chronological.
  - snapshot_options(snaps, current_kpis) -> [(key, label, kpis)]
    — pure: snapshots that carry KPIs, plus "Current" when the
    current KPIs exist.
  - compare_runs_table(run_a, run_b) -> [row] — pure: Rows
    before / Rows after / Rows removed for each run + difference.
  - render_compare_tab(st, raw=None, clean=None,
    load_sample=None) -> None — the page. Renders with no data
    loaded: the sub-nav and an empty state with a "Try the sample
    data" CTA; the views need a loaded file (or, for Logs, at
    least one recorded entry — e.g. a failed load with no file).
    NOTE for the integrator: app.py must dispatch this page in
    BOTH places — the no-data early block (beside Join, before
    the generic "Nothing loaded yet" empty state, with
    st.stop()) AND the main tab dispatch — or the tab is
    unreachable until a file is loaded (the Join round fixed
    the same reachability gap for Join; this round found
    Compare missing from the no-data block).

Widget keys all start with "cmp_"; the view lives in
session_state["compare_view"] ("logs" / "runs" / "files").
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta

import pandas as pd

import feat_analyse
import feat_combine
import ui_design

__all__ = [
    "classify_log",
    "filter_logs",
    "histogram_counts",
    "parse_clean_detail",
    "clean_runs",
    "snapshot_options",
    "compare_runs_table",
    "render_compare_tab",
]

VIEW_LOGS = "logs"
VIEW_RUNS = "runs"
VIEW_FILES = "files"
_VIEWS = ((VIEW_LOGS, "Logs"),
          (VIEW_RUNS, "Compare runs"),
          (VIEW_FILES, "Compare files"))

LOG_TYPES = ("Clean", "Quality", "Database", "File", "Join")
LOG_LEVELS = ("success", "warning", "error")
_LEVEL_LABELS = {"success": "Success", "warning": "Warning",
                 "error": "Error"}

_CLEAN_STEPS = {"Clean", "Suggestion applied", "One-click flow",
                "Sampling applied to full file"}
_QUALITY_STEPS = {"Fuzzy merge"}
_QUALITY_PREFIXES = ("Outliers:", "Near-duplicates:")
_DATABASE_STEPS = {"Database load"}
_FILE_STEPS = {"Sample loaded", "File loaded", "File load failed"}
_JOIN_STEPS = {"Join", "Join preview failed"}
_ERROR_STEPS = {"File load failed", "Join preview failed"}

_TIME_RANGES = (("all", "All time"),
                ("60m", "Last 60 minutes"),
                ("24h", "Last 24 hours"),
                ("7d", "Last 7 days"))
_TIME_DELTAS = {"60m": timedelta(minutes=60),
                "24h": timedelta(hours=24),
                "7d": timedelta(days=7)}

_CLEAN_RE = re.compile(r"([\d,]+)\s*->\s*([\d,]+)\s*rows")


# --------------------------------------------------------------------------
# Pure model
# --------------------------------------------------------------------------

def _type_for_step(step: str) -> str:
    """Which subsystem a recorded step belongs to."""
    if step in _CLEAN_STEPS:
        return "Clean"
    if step in _QUALITY_STEPS or step.startswith(_QUALITY_PREFIXES):
        return "Quality"
    if step in _DATABASE_STEPS:
        return "Database"
    if step in _FILE_STEPS:
        return "File"
    if step in _JOIN_STEPS:
        return "Join"
    return "Other"


def _level_for_step(step: str) -> str:
    """Success for every completed action, error for a failed load
    or a failed join preview. The app records no warning-grade
    events, so "warning" never comes out of this function."""
    return "error" if step in _ERROR_STEPS else "success"


def classify_log(entry: dict) -> dict:
    """The entry plus its derived "type" and "level". Missing keys
    default to "" / "success" — entries recorded before a level
    existed still classify."""
    step = str(entry.get("step", ""))
    level = entry.get("level") or _level_for_step(step)
    return {"time": str(entry.get("time", "")),
            "step": step,
            "detail": str(entry.get("detail", "")),
            "type": _type_for_step(step),
            "level": level}


def _parse_time(value: str):
    """The audit trail's "%Y-%m-%d %H:%M:%S" timestamps, or None
    when the value does not parse (such entries only ever match
    the "All time" range)."""
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def filter_logs(entries, time_range: str = "all", types=None,
                levels=None, query: str = "") -> list:
    """The classified entries that match every active filter, in
    chronological order (the render reverses them, newest first).
    types / levels are sets of the values to keep (None = all)."""
    now = datetime.now()
    delta = _TIME_DELTAS.get(time_range)
    q = (query or "").strip().lower()
    out = []
    for i, entry in enumerate(entries):
        c = classify_log(entry)
        c["_idx"] = i
        if delta is not None:
            t = _parse_time(c["time"])
            if t is None or now - t > delta:
                continue
        if types is not None and c["type"] not in types:
            continue
        if levels is not None and c["level"] not in levels:
            continue
        if q and q not in (c["step"] + " " + c["detail"]).lower():
            continue
        out.append(c)
    return out


def histogram_counts(entries) -> list:
    """(label, count) buckets for the timeline chart: per hour
    when the entries span a day or less, per day when they span
    more. Entries with no parseable time are skipped — the chart
    counts real timestamps only."""
    times = [t for t in (_parse_time(str(e.get("time", "")))
                         for e in entries) if t is not None]
    if not times:
        return []
    by_day = (max(times) - min(times)) > timedelta(days=1)
    buckets: dict = {}
    for t in times:
        label = t.strftime("%Y-%m-%d") if by_day else \
            t.strftime("%Y-%m-%d %H:00")
        buckets[label] = buckets.get(label, 0) + 1
    return sorted(buckets.items())


def parse_clean_detail(detail: str):
    """("80 -> 77 rows") -> (80, 77); anything else -> None."""
    m = _CLEAN_RE.search(detail or "")
    if not m:
        return None
    return (int(m.group(1).replace(",", "")),
            int(m.group(2).replace(",", "")))


def clean_runs(audit) -> list:
    """One run per "Clean" audit entry, chronological: the run's
    time and its before/after row counts."""
    runs = []
    for entry in audit or []:
        if str(entry.get("step", "")) != "Clean":
            continue
        parsed = parse_clean_detail(str(entry.get("detail", "")))
        if parsed is None:
            continue
        before, after = parsed
        runs.append({"time": str(entry.get("time", "")),
                     "before": before, "after": after,
                     "removed": before - after})
    return runs


def snapshot_options(snaps, current_kpis) -> list:
    """[(key, label, kpis)] for every snapshot that carries KPIs,
    plus the current KPIs as "Current". Snapshots store KPIs only
    from the second clean on (the first snapshot is taken before
    the first clean, when there are no KPIs yet)."""
    options = []
    for i, snap in enumerate(snaps or []):
        kpis = (snap or {}).get("kpis")
        if kpis:
            options.append((f"snap:{i}",
                            f"{(snap or {}).get('label') or 'Snapshot'} "
                            f"(snapshot)", kpis))
    if current_kpis:
        options.append(("current", "Current (cleaned now)", current_kpis))
    return options


def compare_runs_table(run_a: dict, run_b: dict) -> list:
    """Rows before / Rows after / Rows removed for each of two
    runs, plus the difference (B − A) between them."""
    return [
        {"Metric": "Rows before",
         "Run A": run_a["before"], "Run B": run_b["before"],
         "Difference": run_b["before"] - run_a["before"]},
        {"Metric": "Rows after",
         "Run A": run_a["after"], "Run B": run_b["after"],
         "Difference": run_b["after"] - run_a["after"]},
        {"Metric": "Rows removed",
         "Run A": run_a["removed"], "Run B": run_b["removed"],
         "Difference": run_b["removed"] - run_a["removed"]},
    ]


# --------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------

def _index_of(value, options) -> int:
    """The selectbox index for a saved value: its position in the
    options, or 0 when the value is missing or stale (the Tools
    filter idiom — the displayed value always follows the saved
    one)."""
    return options.index(value) if value in options else 0


def _render_empty(st, load_sample) -> None:
    """The no-data empty state: the guided card with the one-click
    sample loader (the Tools/Clean/Join reachability fix — the tab
    opens, the views stay behind the empty state until data
    exists)."""
    if ui_design.empty_state(
            "No data loaded yet",
            "Upload a file from the sidebar on the left, or skip the "
            "setup and explore with the sample file: it loads the "
            "messy sales data (80 rows) so you can see the activity "
            "log right away.",
            cta_label="Try the sample data"):
        if load_sample is not None:
            load_sample()
        st.rerun()


def _render_logs(st, audit) -> None:
    """The Logs view: filter panel values (read from session state
    — the widgets live in the left column), top bar, timeline
    histogram, table, and the entry detail."""
    ui_design.section_heading(
        "Logs",
        sub="Beta — the app's own activity log: every clean, join, "
            "load and quality action, this session only. An entry "
            "exists only because the app recorded it.")
    session = st.session_state

    time_key = session.get("cmp_time_range", "all")
    picked_types = {t for t in LOG_TYPES
                    if session.get(f"cmp_type_{t.lower()}", True)}
    if session.get("cmp_type_other", True):
        picked_types.add("Other")
    picked_levels = {lv for lv in LOG_LEVELS
                     if session.get(f"cmp_level_{lv}", True)}
    query = session.get("cmp_q", "")
    shown = list(reversed(filter_logs(
        audit, time_range=time_key, types=picked_types,
        levels=picked_levels, query=query)))

    # Top bar: free-text filter is the left column's "Filter logs"
    # input; here Refresh, rows-per-page and Download logs.
    _c1, _c2, _c3 = st.columns(3)
    with _c1:
        if st.button("Refresh logs", key="cmp_refresh"):
            st.rerun()
    with _c2:
        rows_opts = ["25", "50", "100"]
        per_page = int(st.selectbox(
            "Rows per page", rows_opts, key="cmp_rows",
            index=_index_of(str(session.get("cmp_rows", "50")),
                            rows_opts)))
    with _c3:
        if shown:
            csv = pd.DataFrame(shown).to_csv(index=False).encode("utf-8")
            st.download_button("Download logs", csv,
                               file_name="logs.csv", mime="text/csv",
                               key="cmp_download")
    st.caption(f"{len(shown)} of {len(audit)} logs")

    if not shown:
        ui_design.empty_state(
            "No logs match these filters",
            "Loosen a filter — or clear the search — to see the "
            "entries again.")
        return

    counts = histogram_counts(audit)
    if counts:
        _chart = pd.DataFrame(counts, columns=["time", "logs"])
        _chart = _chart.set_index("time")
        st.bar_chart(_chart)
        _span_days = len({label[:10] for label, _ in counts}) > 1
        st.caption("Logs per day" if _span_days else "Logs per hour")

    page = shown[:per_page]
    _frame = pd.DataFrame([{
        "Time": e["time"],
        "Type": e["type"],
        "Level": _LEVEL_LABELS.get(e["level"], e["level"]),
        "Step": e["step"],
        "Detail": e["detail"]} for e in page])
    st.dataframe(_frame, width="stretch", hide_index=True)
    st.caption(f"Showing first {len(page)} of {len(shown)} logs")
    if len(shown) == len(page):
        st.caption(f"No more data to load ({len(shown)} of "
                   f"{len(shown)} logs)")

    # Detail: pick an entry — the honest equivalent of Supabase's
    # row-click drawer (stock Streamlit cannot make a dataframe
    # row clickable). The value is the entry's position in the
    # full audit list, so it stays put when the filters change.
    _shown_full = [e["_idx"] for e in page]
    _picked = st.selectbox(
        "Open log entry", [None] + _shown_full,
        format_func=lambda i: ("—" if i is None else
                               f"{audit[i].get('time', '')} · "
                               f"{audit[i].get('step', '')}"),
        key="cmp_open",
        index=_index_of(session.get("cmp_open"), [None] + _shown_full))
    if _picked is not None:
        _entry = classify_log(audit[_picked])
        _tab_over, _tab_json = st.tabs(["Overview", "Raw JSON"])
        with _tab_over:
            st.table(pd.DataFrame([
                {"Field": "Time", "Value": _entry["time"]},
                {"Field": "Type", "Value": _entry["type"]},
                {"Field": "Level",
                 "Value": _LEVEL_LABELS.get(_entry["level"],
                                            _entry["level"])},
                {"Field": "Step", "Value": _entry["step"]},
                {"Field": "Detail", "Value": _entry["detail"]},
            ]))
        with _tab_json:
            st.json(_entry)
            st.code(json.dumps(_entry, indent=2), language="json")


def _render_runs(st, audit) -> None:
    """The Compare runs view: the Clean entries in the audit trail
    are real runs; pick two and see each run's before/after plus
    the delta between them. Snapshots that carry KPIs can be
    compared the same way."""
    ui_design.section_heading(
        "Compare runs",
        sub="Every clean is a run in the log — pick two runs and "
            "see how their results differ, or compare the KPIs of "
            "two saved snapshots.")
    session = st.session_state
    runs = clean_runs(audit)
    if not runs:
        st.info("No cleaning runs yet — press Clean my data in the "
                "Clean tab, then come back here to compare runs.")
        return
    _frame = pd.DataFrame([{
        "Time": r["time"], "Rows before": r["before"],
        "Rows after": r["after"], "Rows removed": r["removed"]}
        for r in reversed(runs)])
    st.dataframe(_frame, width="stretch", hide_index=True)
    if len(runs) < 2:
        _only = runs[0]
        st.write(f"The one run so far: {_only['before']:,} → "
                 f"{_only['after']:,} rows "
                 f"({_only['removed']:,} removed). Clean again — "
                 "change a fix first, or just press Run again — to "
                 "add a second run to compare.")
    else:
        _labels = [f"{r['time']} — {r['before']:,} → {r['after']:,} rows"
                   for r in runs]
        _a = st.selectbox("Run A", list(range(len(runs))),
                          format_func=lambda i: _labels[i],
                          key="cmp_run_a",
                          index=_index_of(session.get("cmp_run_a"), list(range(len(runs)))))
        _b = st.selectbox("Run B", list(range(len(runs))),
                          format_func=lambda i: _labels[i],
                          key="cmp_run_b",
                          index=_index_of(session.get("cmp_run_b"), list(range(len(runs)))))
        if _a == _b:
            st.info("Pick two different runs to see the difference "
                    "between them.")
        else:
            st.dataframe(pd.DataFrame(
                compare_runs_table(runs[_a], runs[_b])),
                width="stretch", hide_index=True)
    st.markdown('<div class="dcs-micro-label">Compare KPIs</div>',
                unsafe_allow_html=True)
    _options = snapshot_options(session.get("a_snaps") or [],
                                session.get("kpis"))
    if len(_options) < 2:
        st.info("KPI comparison needs two snapshots with KPIs — "
                "snapshots store KPIs after the first clean, so clean "
                "again (or apply a change) to add one.")
        return
    _labels = [label for _key, label, _k in _options]
    _keys = [key for key, _label, _k in _options]
    _a = st.selectbox("Snapshot A", _keys,
                      format_func=lambda k: _labels[_keys.index(k)],
                      key="cmp_snap_a",
                      index=_index_of(session.get("cmp_snap_a"), _keys))
    _b = st.selectbox("Snapshot B", _keys,
                      format_func=lambda k: _labels[_keys.index(k)],
                      key="cmp_snap_b",
                      index=_index_of(session.get("cmp_snap_b"), _keys))
    if _a == _b:
        st.info("Pick two different snapshots to compare their KPIs.")
        return
    _by_key = {key: kpis for key, _label, kpis in _options}
    _kpis_a = _by_key[_a]
    _kpis_b = _by_key[_b]
    _compared = feat_combine.compare_kpis(_kpis_a, _kpis_b)
    if not _compared:
        st.info("No comparable numeric KPIs between the two "
                "snapshots — they share no number column to compare.")
        return
    _table = pd.DataFrame(_compared)
    _table["pct_change"] = _table["pct_change"].apply(
        lambda v: "inf%" if v == float("inf") else f"{v:+.1f}%")
    _table["flagged"] = _table["flagged"].apply(
        lambda f: "⚠️ FLAGGED" if f else "")
    st.dataframe(_table, width="stretch")


def _render_files(st, clean) -> None:
    """The old file-comparison feature, moved verbatim from the
    Compare tab — same render calls, same expander, same keys.
    Nothing about it changed."""
    feat_combine.render_compare(st)
    with st.expander("Combine & check (stack files, anomalies, "
                     "multi-KPI)"):
        feat_combine.render_append(st)
        if clean is not None:
            feat_combine.render_anomaly(st, clean)
        feat_analyse.render_multi_kpi(st)


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------

def render_compare_tab(st, raw=None, clean=None, load_sample=None):
    """The Compare tab as Supabase's Logs page.

    Left sub-nav (Back to dashboard / Logs / Compare runs /
    Compare files + the Logs filter panel) + main column: the Logs
    view, the Compare runs view, or the old Compare files view.
    Renders with no data loaded — the sub-nav and the empty state
    with its "Try the sample data" CTA; the views need a loaded
    file, except Logs, which also renders when entries exist
    without a file (a failed load, for example).
    """
    session = st.session_state
    audit = session.get("q_audit") or []
    view = session.get("compare_view", VIEW_LOGS)
    if view not in (VIEW_LOGS, VIEW_RUNS, VIEW_FILES):
        view = VIEW_LOGS

    _set_nav, _set_main = st.columns([1, 4])
    with _set_nav:
        if st.button("← Back to dashboard",
                     key="cmp_back_dashboard",
                     use_container_width=True):
            session["pending_tab"] = "dashboard"
            st.rerun()
        st.markdown('<div class="dcs-micro-label">Compare</div>',
                    unsafe_allow_html=True)
        for _key, _label in _VIEWS:
            if st.button(_label, key=f"cmp_nav_{_key}",
                         disabled=(view == _key),
                         use_container_width=True):
                session["compare_view"] = _key
                st.rerun()
        if view == VIEW_LOGS:
            st.markdown('<div class="dcs-micro-label">Filters</div>',
                        unsafe_allow_html=True)
            _time_opts = [label for _key, label in _TIME_RANGES]
            _time_keys = [key for key, _label in _TIME_RANGES]
            _time_idx = _index_of(
                session.get("cmp_time_range", "all"), _time_keys)
            _picked_range = st.selectbox(
                "Time range", _time_opts, key="cmp_time_range_sel",
                index=_time_idx)
            session["cmp_time_range"] = _time_keys[
                _time_opts.index(_picked_range)]
            _counts = {}
            for _c in filter_logs(audit, time_range="all"):
                _counts[_c["type"]] = _counts.get(_c["type"], 0) + 1
                _counts["level:" + _c["level"]] = \
                    _counts.get("level:" + _c["level"], 0) + 1
            st.markdown('<div class="dcs-micro-label">Log type</div>',
                        unsafe_allow_html=True)
            for _t in LOG_TYPES:
                st.checkbox(f"{_t} ({_counts.get(_t, 0)})",
                            value=True, key=f"cmp_type_{_t.lower()}")
            if _counts.get("Other", 0):
                st.checkbox(f"Other ({_counts.get('Other', 0)})",
                            value=True, key="cmp_type_other")
            st.markdown('<div class="dcs-micro-label">Level</div>',
                        unsafe_allow_html=True)
            for _lv in LOG_LEVELS:
                st.checkbox(
                    f"{_LEVEL_LABELS[_lv]} ({_counts.get('level:' + _lv, 0)})",
                    value=True, key=f"cmp_level_{_lv}")
            st.caption("No warning-grade events — the app records "
                       "successes and failures only.")
            st.caption("Logs cover this session only — the trail "
                       "resets when a new file is loaded.")
            st.text_input("Filter logs", key="cmp_q",
                          placeholder="Filter by step or detail")

    with _set_main:
        if raw is None and not audit:
            _render_empty(st, load_sample)
            return
        if view == VIEW_RUNS:
            _render_runs(st, audit)
        elif view == VIEW_FILES:
            _render_files(st, clean)
        else:
            _render_logs(st, audit)
