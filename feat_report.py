"""Report tab as Supabase's Observability custom reports + Reports section,
mapped to this app's own reports (the mapping the clone spec confirms:
Report -> Observability custom reports + Reports section).

Supabase's Observability page, from the audit (spec Pass B2 section 1
and Pass A): a 175px fly-out sub-nav (GENERAL Overview / Query
Performance / API Gateway / Database Connections; PRODUCT Database /
Data API / Auth / Edge Functions / Storage / Realtime; CUSTOM REPORTS
empty state "No custom reports — Build a custom report to track the
metrics..." + outlined "New custom report" button, which opens the
report builder). The Overview header carries H1 + BETA badge, Docs,
Refresh report, and a "Last 24 hours" dropdown (Last 7 days greyed /
plan-gated). The Reports section itself (Pass A): heading + "Add
block" dropdown button, empty-state card "Build a custom report /
Keep track of your most important metrics" + "Add your first block".

The mapping onto this app's REAL reports, honestly:

* The one-page report the app already builds (``engine.build_report``
  over the loaded file, the cleaned file, the fix list and the KPIs,
  with its .md / CSV / Excel / PDF / Parquet downloads) moves
  verbatim under "One-page report" in the sub-nav. Nothing about
  what it contains changes.
* "Reports" is the saved-reports list: custom reports the user
  builds and saves. A saved report is a snapshot — its blocks keep
  the values as of save time, so opening one later shows the numbers
  it was saved with, not today's. Saved reports persist per user
  (reports/reports.json, the same storage mechanism as Clean's
  recipes); a storage failure never stops the tab.
* "Custom report" is the builder: a name, a time range, and an
  "Add block" picker. Every block shows a real value from this
  session's data — Rows before/after, Columns before/after, Rows
  removed, Fixes applied (the fix list), one of the current KPIs,
  or a comparison of two real Clean runs from the audit trail.
  The time range filters which runs the Run blocks can pick (the
  same ranges and the same filter as Compare's Logs view).
* The tab opens with no data loaded: the sub-nav renders and the
  main column shows the "No data loaded yet" empty state with its
  "Try the sample data" CTA — except the Reports view, which still
  lists saved reports when any exist (the Compare precedent: Logs
  renders when entries exist without a file). The builder and the
  one-page report stay behind the empty state until data exists;
  the builder additionally needs a clean before any block has data.

What is NOT built, and why (stated plainly, not faked):

* Scheduled report delivery / email reports: the app has no
  scheduler for reports, so there is no "send this report weekly"
  switch. (The SMTP note in Settings describes the same gap.)
* A "Last 7 days" plan gate: Supabase greys it out as plan-gated.
  Here the audit trail is session-only, so the range list is the
  ranges that filter real session entries (All time / Last 60
  minutes / Last 24 hours / Last 7 days) with a caption saying
  reports cover this session's activity — no fake gating, no
  fake "Upgrade to Pro" prompt.
* Live / auto-refreshing report widgets: stock Streamlit cannot
  push new values into a rendered report as they happen. The
  Refresh report button re-reads the audit trail; that is the
  honest equivalent.
* PDF rendering fidelity: the one-page PDF download is the app's
  existing ``engine.to_pdf_bytes`` output, moved verbatim — this
  round does not redesign it.
* Clickable metric cards that drill into a detail report:
  Supabase's Overview cards are links to detail reports. Stock
  Streamlit cannot make a card body a link; the blocks render
  their values in place instead, and the Runs block's table is
  the comparison itself.

Contract:
  - compute_block(kind, state, kpi_label=None, run_a=None,
    run_b=None) -> dict | None — pure: the block with its data
    computed from the given state, or None when the data it needs
    does not exist yet. ``state`` is a plain dict with raw, clean,
    actions, kpis, audit.
  - report_markdown(name, created, blocks) -> str — pure: the
    saved report as Markdown, from stored block data.
  - render_report_tab(st, ctx) — the tab. ctx keys: raw, clean,
    load_sample, persist_reports, t, base_dir, storage_key,
    audit, save_copy. The last five are only needed by the
    one-page view; the no-data dispatch passes the first four.
"""

import html
from datetime import datetime

import pandas as pd
import streamlit as st

import engine
import feat_automate
import feat_brand
import feat_compare
import feat_enrich
import feat_export
import feat_quality
import feat_share
import ui_design
import ui_loading

VIEW_REPORTS = "reports"
VIEW_BUILDER = "builder"
VIEW_ONEPAGE = "onepage"
_VIEWS = [(VIEW_REPORTS, "Reports"),
          (VIEW_BUILDER, "Custom report"),
          (VIEW_ONEPAGE, "One-page report")]

BLOCK_KINDS = (("rows", "Rows"),
               ("columns", "Columns"),
               ("removed", "Rows removed"),
               ("fixes", "Fixes applied"),
               ("kpi", "A KPI"),
               ("runs", "Compare two runs"))

_TIME_RANGES = feat_compare._TIME_RANGES


# --------------------------------------------------------------------------
# Pure model
# --------------------------------------------------------------------------

def _fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def compute_block(kind, state, kpi_label=None, run_a=None, run_b=None):
    """The block for ``kind`` with its data computed from ``state``
    (a plain dict: raw, clean, actions, kpis, audit), or None when
    the data it needs does not exist yet. The returned dict is
    JSON-able, so a saved report can store it as a snapshot.
    """
    raw = state.get("raw")
    clean = state.get("clean")
    actions = state.get("actions") or []
    kpis = state.get("kpis") or []
    audit = state.get("audit") or []
    if kind == "rows":
        if raw is None or clean is None:
            return None
        before, after = len(raw), len(clean)
        return {"kind": kind, "label": "Rows",
                "data": {"before": before, "after": after,
                         "removed": before - after}}
    if kind == "columns":
        if raw is None or clean is None:
            return None
        return {"kind": kind, "label": "Columns",
                "data": {"before": len(raw.columns),
                         "after": len(clean.columns)}}
    if kind == "removed":
        if raw is None or clean is None:
            return None
        return {"kind": kind, "label": "Rows removed",
                "data": {"removed": len(raw) - len(clean)}}
    if kind == "fixes":
        if not actions:
            return None
        return {"kind": kind, "label": "Fixes applied",
                "data": {"count": len(actions),
                         "steps": [str(s) for s, _d in actions]}}
    if kind == "kpi":
        if not kpis:
            return None
        found = next((k for k in kpis
                      if str(k.get("label", "")) == str(kpi_label)), None)
        if found is None:
            return None
        return {"kind": kind, "label": f"KPI — {found['label']}",
                "data": {"label": str(found["label"]),
                         "value": str(found["value"])}}
    if kind == "runs":
        runs = feat_compare.clean_runs(audit)
        if len(runs) < 2:
            return None
        try:
            a, b = runs[int(run_a)], runs[int(run_b)]
        except (TypeError, ValueError, IndexError):
            return None
        if a is b or run_a == run_b:
            return None
        return {"kind": kind, "label": "Compare two runs",
                "data": {"table": feat_compare.compare_runs_table(a, b),
                         "a_label": f"{a['time']} — {_fmt(a['before'])} → "
                                    f"{_fmt(a['after'])} rows",
                         "b_label": f"{b['time']} — {_fmt(b['before'])} → "
                                    f"{_fmt(b['after'])} rows"}}
    return None


def report_markdown(name, created, blocks) -> str:
    """A saved report as Markdown, rendered from its stored block
    data — the values as of save time, never recomputed."""
    lines = [f"# {name}", "", f"Saved {created} · Data Cleaner Studio",
             ""]
    for block in blocks or []:
        data = block.get("data") or {}
        lines.append(f"## {block.get('label', block.get('kind', ''))}")
        if block.get("kind") == "rows":
            lines.append(f"Rows: {_fmt(data.get('before'))} → "
                         f"{_fmt(data.get('after'))} "
                         f"({_fmt(data.get('removed'))} removed).")
        elif block.get("kind") == "columns":
            lines.append(f"Columns: {_fmt(data.get('before'))} → "
                         f"{_fmt(data.get('after'))}.")
        elif block.get("kind") == "removed":
            lines.append(f"Rows removed: {_fmt(data.get('removed'))}.")
        elif block.get("kind") == "fixes":
            lines.append(f"Fixes applied: {_fmt(data.get('count'))}.")
            for step in data.get("steps") or []:
                lines.append(f"- {step}")
        elif block.get("kind") == "kpi":
            lines.append(f"{data.get('label')}: {data.get('value')}.")
        elif block.get("kind") == "runs":
            lines.append(f"Run A: {data.get('a_label')}.")
            lines.append(f"Run B: {data.get('b_label')}.")
            for row in data.get("table") or []:
                lines.append(f"- {row.get('Metric')}: Run A "
                             f"{row.get('Run A')}, Run B {row.get('Run B')}, "
                             f"Difference {row.get('Difference')}.")
        lines.append("")
    lines.append("_Generated by Data Cleaner Studio._")
    return "\n".join(lines)


def _slug(name: str) -> str:
    out = "".join(c if c.isalnum() else "_" for c in (name or "").lower())
    return out.strip("_") or "custom-report"


# --------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------

def _index_of(value, options) -> int:
    try:
        return list(options).index(value)
    except ValueError:
        return 0


def _render_empty(st, load_sample) -> None:
    """The no-data empty state: the guided card with the one-click
    sample loader (the Tools/Clean/Join/Compare reachability fix —
    the tab opens, the views stay behind the empty state until data
    exists)."""
    if ui_design.empty_state(
            "No data loaded yet",
            "Upload a file from the sidebar on the left, or skip the "
            "setup and explore with the sample file: it loads the "
            "messy sales data (80 rows) so you can see the reports "
            "right away.",
            cta_label="Try the sample data"):
        if load_sample is not None:
            load_sample()
        st.rerun()


def _render_block(st, block, data=None) -> None:
    """One block, rendered from ``data`` (a saved snapshot) or from
    the block's live values when data is None. ``block`` carries
    kind/label; live values are computed by the caller and passed
    in as ``data``."""
    if data is None:
        return
    kind = block.get("kind")
    if kind == "rows":
        ui_design.card("Rows",
                       body=f"{_fmt(data.get('before'))} → "
                            f"{_fmt(data.get('after'))}",
                       footer=f"{_fmt(data.get('removed'))} removed")
        st.bar_chart(pd.DataFrame(
            {"Rows": [data.get("before", 0), data.get("after", 0)]},
            index=["Before", "After"]))
    elif kind == "columns":
        ui_design.card("Columns",
                       body=f"{_fmt(data.get('before'))} → "
                            f"{_fmt(data.get('after'))}")
    elif kind == "removed":
        ui_design.card("Rows removed",
                       body=f"{_fmt(data.get('removed'))}")
    elif kind == "fixes":
        ui_design.card("Fixes applied",
                       body=f"{_fmt(data.get('count'))} fixes")
        for step in data.get("steps") or []:
            st.write(f"- {step}")
    elif kind == "kpi":
        ui_design.card(str(data.get("label", "")),
                       body=html.escape(str(data.get("value", ""))))
    elif kind == "runs":
        st.write(f"Run A: {data.get('a_label')}")
        st.write(f"Run B: {data.get('b_label')}")
        st.dataframe(pd.DataFrame(data.get("table") or []),
                     width="stretch", hide_index=True)


def _render_reports(st, ctx) -> None:
    """The Reports view: the saved-reports list, or Supabase's
    empty state when nothing is saved yet."""
    session = st.session_state
    reports = session.get("q_reports") or []
    ui_design.section_heading(
        "Reports",
        sub="Saved custom reports — each keeps the values as of save "
            "time, so opening one later shows the numbers it was "
            "saved with.")
    open_idx = session.get("report_open")
    if (isinstance(open_idx, int) and 0 <= open_idx < len(reports)):
        report = reports[open_idx]
        if st.button("← All reports", key="rep_back_all",
                     use_container_width=False):
            session["report_open"] = None
            st.rerun()
        ui_design.section_heading(report.get("name", "Custom report"),
                                  sub=f"Saved {report.get('created', '')}")
        for block in report.get("blocks") or []:
            _render_block(st, block, data=block.get("data"))
        st.download_button(
            "Download (.md)",
            report_markdown(report.get("name", "Custom report"),
                            report.get("created", ""),
                            report.get("blocks") or []),
            file_name=f"{_slug(report.get('name', ''))}.md",
            key=f"rep_dl_{open_idx}")
        st.caption("Saved reports keep the values as of save time.")
        return
    if not reports:
        ui_design.card("Build a custom report",
                       body="Keep track of your most important metrics.")
        _c1, _c2 = st.columns(2)
        with _c1:
            if ui_design.icon_button(
                    "New custom report", "add", kind="secondary",
                    key="rep_new",
                    help="Open the report builder."):
                session["report_view"] = VIEW_BUILDER
                st.rerun()
        with _c2:
            if ui_design.icon_button(
                    "Add your first block", "add", kind="secondary",
                    key="rep_first_block",
                    help="Open the report builder."):
                session["report_view"] = VIEW_BUILDER
                st.rerun()
        return
    for i, report in enumerate(reports):
        _c1, _c2, _c3 = st.columns([4, 1, 1])
        with _c1:
            st.write(f"**{report.get('name', 'Custom report')}**")
            st.caption(f"Saved {report.get('created', '')} · "
                       f"{len(report.get('blocks') or [])} blocks")
        with _c2:
            if st.button("Open", key=f"rep_open_{i}",
                         use_container_width=True):
                session["report_open"] = i
                st.rerun()
        with _c3:
            if st.button("Delete", key=f"rep_del_{i}",
                         use_container_width=True):
                reports.pop(i)
                session["q_reports"] = reports
                if ctx.get("persist_reports") is not None:
                    ctx["persist_reports"]()
                session["report_open"] = None
                st.rerun()
    st.caption("Saved reports keep the values as of save time.")


def _render_builder(st, ctx) -> None:
    """The Custom report builder: name, time range (sub-nav),
    Add block over the real metrics, a live draft preview, and
    Save. Blocks with no data yet cannot be added — the picker
    says so instead of adding an empty block."""
    session = st.session_state
    raw = ctx.get("raw")
    clean = ctx.get("clean")
    actions = session.get("actions") or []
    kpis = session.get("kpis") or []
    audit = session.get("q_audit") or []
    time_range = session.get("rep_time_range", "all")
    runs = feat_compare.clean_runs(
        feat_compare.filter_logs(audit, time_range=time_range))
    ui_design.section_heading(
        "Custom report",
        sub="Pick the metrics that matter — every block shows a real "
            "value from this session's data. Blocks show the current "
            "file; Run blocks use runs in the chosen time range.")
    _h1, _h2 = st.columns(2)
    with _h1:
        if ui_design.icon_button(
                "Docs", "book", kind="secondary", key="rep_docs",
                help="Open the How to use guide."):
            session["pending_tab"] = "tutorial"
            st.rerun()
    with _h2:
        if ui_design.icon_button(
                "Refresh report", "refresh", kind="secondary",
                key="rep_refresh",
                help="Re-read the activity log."):
            st.rerun()
    name = st.text_input("Report name", value="Custom report",
                         key="rep_report_name")
    _kind_labels = [label for _key, label in BLOCK_KINDS]
    _kind_keys = [key for key, _label in BLOCK_KINDS]
    _picked = st.selectbox(
        "Block", _kind_labels, key="rep_block_kind_sel",
        index=_index_of(session.get("rep_block_kind"),
                        _kind_labels))
    kind = _kind_keys[_kind_labels.index(_picked)]
    session["rep_block_kind"] = _picked
    kpi_label = None
    run_a = run_b = None
    if kind == "kpi":
        if not kpis:
            st.info("No KPIs yet — KPIs appear after the first clean.")
        else:
            kpi_label = st.selectbox(
                "KPI", [str(k.get("label", "")) for k in kpis],
                key="rep_block_kpi_sel")
    if kind == "runs":
        if len(runs) < 2:
            st.info("Run comparison needs two cleaning runs — clean "
                    "again to add a second run to compare.")
        else:
            _labels = [f"{r['time']} — {_fmt(r['before'])} → "
                       f"{_fmt(r['after'])} rows" for r in runs]
            run_a = st.selectbox("Run A", list(range(len(runs))),
                                 format_func=lambda i: _labels[i],
                                 key="rep_run_a")
            # Run B defaults to a DIFFERENT run: both pickers start
            # at index 0, and comparing a run with itself has no
            # data behind it (compute_block returns None), so the
            # first Add click would only warn.
            run_b = st.selectbox("Run B", list(range(len(runs))),
                                 format_func=lambda i: _labels[i],
                                 key="rep_run_b",
                                 index=1 if len(runs) > 1 else 0)
    if ui_design.icon_button(
            "Add block", "add", kind="primary", key="rep_add_block",
            help="Add this block to the draft report."):
        state = {"raw": raw, "clean": clean, "actions": actions,
                 "kpis": kpis, "audit": audit}
        block = compute_block(kind, state, kpi_label=kpi_label,
                              run_a=run_a, run_b=run_b)
        if block is None:
            st.warning("That block has no data yet — clean the file "
                       "first, or pick a block with data behind it.")
        else:
            draft = list(session.get("report_draft_blocks") or [])
            draft.append({"kind": kind,
                          "kpi_label": kpi_label,
                          "run_a": run_a, "run_b": run_b})
            session["report_draft_blocks"] = draft
            st.rerun()
    draft = session.get("report_draft_blocks") or []
    if draft:
        st.markdown('<div class="dcs-micro-label">Draft</div>',
                    unsafe_allow_html=True)
        state = {"raw": raw, "clean": clean, "actions": actions,
                 "kpis": kpis, "audit": audit}
        for i, params in enumerate(draft):
            block = compute_block(
                params.get("kind"), state,
                kpi_label=params.get("kpi_label"),
                run_a=params.get("run_a"), run_b=params.get("run_b"))
            if block is None:
                continue
            _render_block(st, block, data=block.get("data"))
            if st.button("Remove", key=f"rep_rm_{i}"):
                draft.pop(i)
                session["report_draft_blocks"] = draft
                st.rerun()
        if ui_design.icon_button(
                "Save custom report", "save", kind="primary",
                key="rep_save",
                help="Save this report with today's values."):
            saved_blocks = []
            for params in draft:
                block = compute_block(
                    params.get("kind"), state,
                    kpi_label=params.get("kpi_label"),
                    run_a=params.get("run_a"), run_b=params.get("run_b"))
                if block is not None:
                    saved_blocks.append(block)
            if not saved_blocks:
                st.warning("Add at least one block with data first.")
            else:
                reports = list(session.get("q_reports") or [])
                reports.append({
                    "name": (name or "").strip() or "Custom report",
                    "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "blocks": saved_blocks})
                session["q_reports"] = reports
                if ctx.get("persist_reports") is not None:
                    ctx["persist_reports"]()
                session["report_draft_blocks"] = []
                session["report_view"] = VIEW_REPORTS
                session["report_open"] = len(reports) - 1
                st.rerun()
    st.caption("Reports cover this session's activity — saved "
               "reports keep the values as of save time.")


def _render_onepage(st, ctx) -> None:
    """The one-page report, moved verbatim from the old inline
    Report section: the build_report markdown, the downloads, the
    one-click flow and the extra export formats. Nothing about
    what it contains changes in this round."""
    session = st.session_state
    raw = ctx.get("raw")
    clean = ctx.get("clean")
    _t = ctx.get("t") or (lambda key: key)
    ui_loading.section_gap(px=64)
    ui_design.section_heading("Report")
    report = engine.build_report(raw, clean, session.get("actions"),
                                 session.get("kpis"))
    st.markdown(report)
    _formulas = st.checkbox("Excel KPIs as live formulas",
                            value=True, key="rep_formulas",
                            help="The Excel workbook gets a 'KPIs (live)' "
                                 "sheet where totals are real Excel "
                                 "formulas, not just numbers.")
    _brand_x = feat_brand.brand_for_exports(base_dir=ctx.get("base_dir"))
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.download_button(_t("download_report") + " (.md)", report,
                       file_name="report.md", key="dl_report")
    c2.download_button("Download cleaned CSV",
                       clean.to_csv(index=False).encode("utf-8"),
                       file_name="cleaned_data.csv", key="dl_csv")
    c3.download_button("Download cleaned Excel",
                       engine.to_excel_bytes(clean, session.get("kpis"),
                                             session.get("actions"),
                                             formulas=_formulas),
                       file_name="cleaned_data.xlsx", key="dl_xlsx")
    pdf_bytes = engine.to_pdf_bytes(
        "Data Cleaner Studio — Report", session.get("kpis"),
        session.get("actions"),
        f"Rows: {len(raw):,} loaded -> {len(clean):,} after cleaning. "
        f"Columns: {len(raw.columns)} -> {len(clean.columns)}.",
        brand=_brand_x)
    c4.download_button("Download PDF report", pdf_bytes,
                       file_name="report.pdf", mime="application/pdf",
                       key="dl_pdf")
    c5.download_button("Download cleaned Parquet",
                       engine.to_parquet_bytes(clean),
                       file_name="cleaned_data.parquet", key="dl_parquet")
    _oc_opts = (session.get("clean_opts")
                or dict(feat_automate.DEFAULT_CLEAN_OPTS))
    _oc = feat_share.render_one_click(st, raw, _oc_opts,
                                      base_dir=ctx.get("base_dir"),
                                      storage_key=ctx.get("storage_key"))
    _oc_ran = isinstance(_oc, dict) and _oc.get("status") == "done"
    if _oc_ran:
        session["clean"] = _oc["cleaned"]
        session["actions"] = _oc["actions"]
        session["kpis"] = _oc["kpis"]
        session["clean_opts"] = _oc_opts
        if ctx.get("audit") is not None:
            ctx["audit"]("One-click flow",
                         f"{len(raw):,} -> {len(_oc['cleaned']):,} rows")
        if ctx.get("save_copy") is not None:
            ctx["save_copy"](_oc["cleaned"], session.get("source_name"))
        clean = _oc["cleaned"]
        filtered = clean
    feat_enrich.render_versioned_download(st, clean)
    ui_loading.section_gap()
    with st.expander("More export formats & sharing"):
        _num = engine.numeric_cols(clean)
        _cat = [c for c in clean.columns
                if str(clean[c].dtype) in ("object", "str")
                and clean[c].nunique() <= 50]
        if _cat and _num:
            _gx, _gy = _cat[0], _num[0]
            _grouped = clean.groupby(_gx, dropna=False)[_gy].sum().reset_index()
            _grouped = _grouped.sort_values(_gy, ascending=False)
            feat_share.render_html_download(
                st, session.get("kpis"), session.get("actions"),
                _grouped, _gx, _gy, brand=_brand_x)
            feat_share.render_chart_png(
                st, _grouped, _gx, _gy, title=f"{_gx} vs {_gy}",
                key_suffix="_report")
        feat_share.render_portfolio_download(
            st, clean, session.get("kpis"), session.get("actions"))
        feat_share.render_styled_excel_download(
            st, clean, session.get("kpis"), session.get("actions"))
        feat_export.render_pptx_download(
            st, session.get("kpis"), session.get("actions"), raw, clean,
            brand=_brand_x)
        feat_export.render_sheets_export(st, clean)
        if not _oc_ran:
            feat_export.render_email_schedule(
                st, session.get("kpis"), session.get("actions"), raw, clean)
        feat_quality.render_audit(st)


# --------------------------------------------------------------------------
# Tab
# --------------------------------------------------------------------------

def render_report_tab(st, ctx) -> None:
    """The Report tab as Supabase's Observability custom reports +
    Reports section.

    Left sub-nav (Back to dashboard / Reports / Custom report /
    One-page report + the time-range picker in the builder) + main
    column: the saved-reports list, the builder, or the one-page
    report. Renders with no data loaded — the sub-nav and the
    saved-reports list (or the empty state with its "Try the sample
    data" CTA when nothing is saved); the builder and the one-page
    report stay behind the empty state until data exists.
    """
    session = st.session_state
    raw = ctx.get("raw")
    clean = ctx.get("clean")
    view = session.get("report_view", VIEW_REPORTS)
    if view not in (VIEW_REPORTS, VIEW_BUILDER, VIEW_ONEPAGE):
        view = VIEW_REPORTS

    _set_nav, _set_main = st.columns([1, 4])
    with _set_nav:
        if st.button("← Back to dashboard",
                     key="rep_back_dashboard",
                     use_container_width=True):
            session["pending_tab"] = "dashboard"
            st.rerun()
        st.markdown('<div class="dcs-micro-label">Report</div>',
                    unsafe_allow_html=True)
        for _key, _label in _VIEWS:
            if st.button(_label, key=f"rep_nav_{_key}",
                         disabled=(view == _key),
                         use_container_width=True):
                session["report_view"] = _key
                st.rerun()
        if view == VIEW_BUILDER:
            st.markdown('<div class="dcs-micro-label">Time range</div>',
                        unsafe_allow_html=True)
            _time_opts = [label for _key, label in _TIME_RANGES]
            _time_keys = [key for key, _label in _TIME_RANGES]
            _time_idx = _index_of(session.get("rep_time_range", "all"),
                                  _time_keys)
            _picked_range = st.selectbox(
                "Time range", _time_opts, key="rep_time_range_sel",
                index=_time_idx)
            session["rep_time_range"] = _time_keys[
                _time_opts.index(_picked_range)]
            st.caption("Reports cover this session's activity.")

    with _set_main:
        if view == VIEW_REPORTS:
            reports = session.get("q_reports") or []
            if raw is None and not reports:
                _render_empty(st, ctx.get("load_sample"))
                return
            _render_reports(st, ctx)
        elif view == VIEW_BUILDER:
            if raw is None:
                _render_empty(st, ctx.get("load_sample"))
                return
            if clean is None:
                st.info("Clean the file first — report blocks need "
                        "a cleaned result.")
                if ui_design.icon_button(
                        "Go to the Clean tab", "clean", kind="primary",
                        key="rep_go_clean",
                        help="Open Clean and press the clean button."):
                    session["pending_tab"] = "clean"
                    st.rerun()
                return
            _render_builder(st, ctx)
        else:
            if raw is None:
                _render_empty(st, ctx.get("load_sample"))
                return
            if clean is None:
                if ui_design.empty_state(
                        "No report yet",
                        "Your file is loaded — now clean it and the "
                        "report will appear here, with the cleaned "
                        "file to download. Go to the Clean tab, tick "
                        "what to fix, and press the clean button.",
                        cta_label="Go to the Clean tab"):
                    session["pending_tab"] = "clean"
                    st.rerun()
                return
            _render_onepage(st, ctx)
