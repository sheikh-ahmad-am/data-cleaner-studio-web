"""Anti-layout-shift skeletons + section rhythm (research report §9,
patterns 7 and 8).

Pattern 7 — skeleton loading with anti-layout-shift padding: Supabase's
``InnerSideMenuItemLoading`` wraps its ``<Skeleton />`` and adds
y-padding "so the items don't layout shift when shifting to loaded
state and to look visually separated in a list". The helpers here do
the same for this app: every skeleton is a fixed-height placeholder
whose outer geometry (padding, border, radius) matches the loaded
content it stands in for, so nothing jumps when the real data
arrives. Heights are fixed in px, never content-driven.

Pattern 8 — 128px section rhythm + 1280px container + 12–16px UI
text: the marketing site spends its whitespace *between* sections
(128px) while controls stay tight. A dashboard cannot afford 128px
between every block, so this module applies the rhythm where it fits
one: a 1280px content cap (``inject_rhythm``) and generous, named
section gaps (48px standard, 64px large) between major sections,
while controls keep the tight spacing from ``ui_design``.

Rules:
  * Self-contained inline styles — nothing here depends on the shared
    stylesheet in ``ui_design.py`` (which this module does not touch).
    Tokens are imported from ``ui_design.TOKENS`` so the hex values
    stay single-sourced; no hex is re-derived here.
  * One green, rationed: skeletons are monochrome grey (grey bars on
    white) — green only ever means "do this" or "this worked", never
    "loading".
  * The pulse is a gentle opacity fade and is switched off under
    ``prefers-reduced-motion``.

Integration (for the coordinator — app.py call sites, no edits made
here; app.py is owned by other workers):
  1. Once, right after ``inject_design_system()``::

         import ui_loading
         ui_loading.inject_rhythm()

     That caps the content at 1280px and registers the
     ``.dcs-section-gap`` spacer classes.
  2. Between major sections (preview / clean / KPIs / report) add::

         ui_loading.section_gap()          # 48px
         ui_loading.section_gap(px=64)     # 64px, before the report

  3. Loading paths where content currently jumps — replace the bare
     ``st.spinner(...)`` with a skeleton shown first, e.g. the
     "Load sheet" path (``with st.spinner("Loading that sheet…")``)
     and the saved-upload open path::

         ui_loading.skeleton_table(rows=5, columns=4)
         with st.spinner("Loading that sheet…"):
             ...

     and for analysis results (feat_analyse render_forecast /
     render_correlations, and the dashboard charts) show the matching
     placeholder while the numbers compute::

         ui_loading.skeleton()              # text / KPI results
         ui_loading.skeleton_chart()        # charts, 320px tall

     The skeleton paints before the blocking call runs (the same way
     ``st.spinner`` does), then the real content replaces it at the
     same height — no jump.

Public API:
  * ``skeleton_html(lines=3, title=True)`` — pure: the placeholder
    HTML string (title bar + lines), fixed heights.
  * ``skeleton_table_html(rows=5, columns=4)`` — pure: a data-view
    placeholder (header + rows), fixed heights.
  * ``skeleton_chart_html(height=320)`` — pure: a chart placeholder.
  * ``rhythm_css()`` — pure: the ``<style>`` block (1280px cap +
    section-gap classes).
  * ``section_gap_html(px=48)`` — pure: one spacer div.
  * ``skeleton(...)`` / ``skeleton_table(...)`` / ``skeleton_chart(...)``
    / ``inject_rhythm(...)`` / ``section_gap(...)`` — render the above
    through Streamlit (``st_module`` param follows the
    ``ui_design.inject_design_system`` convention; defaults to the
    imported ``streamlit`` module).
"""

from __future__ import annotations

import streamlit as st

from ui_design import TOKENS

# ---------------------------------------------------------------------------
# Fixed geometry — these numbers ARE the anti-shift contract. The loaded
# content these stand in for uses the same values: .dcs-card padding
# (1rem 1.25rem), 12px card radius, ~40px table rows (Supabase Table
# Editor rows), 6px control radius. Change a number here only if the
# matching loaded content changes too.
# ---------------------------------------------------------------------------
_CARD_PADDING = "1rem 1.25rem"
_TITLE_BAR_HEIGHT = 20      # px — matches a 17px section heading line
_LINE_HEIGHT = 14           # px — matches a 14px body line
_LINE_GAP = 10              # px — gap between skeleton bars
_TABLE_HEADER_HEIGHT = 36   # px — matches the dataframe header row
_TABLE_ROW_HEIGHT = 40      # px — matches a Supabase grid row
_TABLE_CELL_HEIGHT = 14     # px — the bar inside a table row
_CHART_HEIGHT = 320         # px — default chart placeholder height
_SECTION_GAP = 48           # px — dashboard-scale section rhythm
_SECTION_GAP_LARGE = 64     # px — before the report / big sections
_CONTAINER_MAX_WIDTH = 1280  # px — report §9 pattern 8 container cap

_BAR = TOKENS["active_nav"]       # skeleton bar grey
_PANEL = TOKENS["panel_grey"]     # chart panel grey
_BORDER = TOKENS["border"]        # hairline
_CARD = TOKENS["card"]            # card white
_RADIUS = TOKENS["card_radius"]   # 12px

# Line widths cycle deterministically (no randomness — stable renders,
# stable tests) so the bars read as text lines, not a solid block.
_LINE_WIDTHS = ("92%", "78%", "85%", "64%", "88%")


def _pulse_style() -> str:
    """The one small ``<style>`` block skeletons need: a gentle opacity
    pulse, switched off for reduced-motion users. Kept here (not in
    the shared stylesheet) so skeletons stay self-contained."""
    return (
        "<style>"
        ".dcs-skeleton-bar { animation: dcs-skeleton-pulse 1.4s "
        "ease-in-out infinite; }"
        "@keyframes dcs-skeleton-pulse { 0%, 100% { opacity: 1; } "
        "50% { opacity: 0.55; } }"
        "@media (prefers-reduced-motion: reduce) { "
        ".dcs-skeleton-bar { animation: none; } }"
        "</style>"
    )


def _bar(width: str, height: int) -> str:
    """One grey skeleton bar, fixed height, 6px radius."""
    return (
        f'<div class="dcs-skeleton-bar" style="width: {width}; '
        f"height: {height}px; background-color: {_BAR}; "
        f"border-radius: 6px;\"></div>"
    )


def skeleton_html(lines: int = 3, title: bool = True) -> str:
    """Return a skeleton placeholder as an HTML string: a card-shaped
    block (white, hairline border, 12px radius, the same 1rem 1.25rem
    padding as a loaded ``.dcs-card``) holding a title bar and
    ``lines`` text-line bars — all fixed heights, so the loaded
    content replaces it without moving anything below it.

    ``lines`` is clamped to 1–6; ``title`` adds the 20px title bar.
    """
    n = max(1, min(6, int(lines)))
    parts = [_pulse_style(),
             f'<div class="dcs-skeleton" style="background-color: {_CARD}; '
             f"border: 1px solid {_BORDER}; border-radius: {_RADIUS}; "
             f"padding: {_CARD_PADDING}; margin-bottom: 1rem;\">"]
    if title:
        parts.append(_bar("45%", _TITLE_BAR_HEIGHT))
        parts.append(f'<div style="height: {_LINE_GAP}px;"></div>')
    for i in range(n):
        parts.append(_bar(_LINE_WIDTHS[i % len(_LINE_WIDTHS)], _LINE_HEIGHT))
        if i < n - 1:
            parts.append(f'<div style="height: {_LINE_GAP}px;"></div>')
    parts.append("</div>")
    return "".join(parts)


def skeleton_table_html(rows: int = 5, columns: int = 4) -> str:
    """Return a data-view skeleton as an HTML string: a white,
    hairline-bordered, 12px-radius block (the same outer geometry as
    a loaded ``st.dataframe``) with a 36px header row and ``rows``
    40px rows, each holding one 14px bar per column. No inner
    padding — like the loaded table, the grid fills the frame.

    ``rows`` is clamped to 1–10, ``columns`` to 1–8.
    """
    n_rows = max(1, min(10, int(rows)))
    n_cols = max(1, min(8, int(columns)))
    widths = ("22%", "30%", "18%", "26%", "20%", "28%", "16%", "24%")
    parts = [_pulse_style(),
             f'<div class="dcs-skeleton-table" style="background-color: '
             f"{_CARD}; border: 1px solid {_BORDER}; "
             f"border-radius: {_RADIUS}; overflow: hidden; "
             f"margin-bottom: 1rem;\">"]
    # Header row: one wide bar, header height, hairline below.
    parts.append(
        f'<div style="height: {_TABLE_HEADER_HEIGHT}px; display: flex; '
        f"align-items: center; padding: 0 1rem; "
        f"border-bottom: 1px solid {_BORDER};\">"
        + _bar("30%", _TABLE_CELL_HEIGHT) + "</div>")
    for r in range(n_rows):
        border = (f"border-bottom: 1px solid {_BORDER};"
                  if r < n_rows - 1 else "")
        cells = "".join(
            f'<div style="flex: 1; padding-right: 1rem;">'
            f"{_bar(widths[c % len(widths)], _TABLE_CELL_HEIGHT)}</div>"
            for c in range(n_cols))
        parts.append(
            f'<div style="height: {_TABLE_ROW_HEIGHT}px; display: flex; '
            f"align-items: center; padding: 0 1rem; {border}\">"
            + cells + "</div>")
    parts.append("</div>")
    return "".join(parts)


def skeleton_chart_html(height: int = 320) -> str:
    """Return a chart skeleton as an HTML string: a card-shaped block
    (same padding / border / radius as a loaded chart card) with a
    20px title bar and one large fixed-height panel. ``height`` is
    clamped to 120–600px.
    """
    h = max(120, min(600, int(height)))
    return (
        _pulse_style()
        + f'<div class="dcs-skeleton-chart" style="background-color: {_CARD}; '
        f"border: 1px solid {_BORDER}; border-radius: {_RADIUS}; "
        f"padding: {_CARD_PADDING}; margin-bottom: 1rem;\">"
        + _bar("35%", _TITLE_BAR_HEIGHT)
        + f'<div style="height: {_LINE_GAP}px;"></div>'
        + f'<div class="dcs-skeleton-bar" style="height: {h}px; '
        f"background-color: {_PANEL}; border-radius: 6px;\"></div>"
        + "</div>"
    )


def rhythm_css() -> str:
    """Return the section-rhythm ``<style>`` block: the 1280px content
    cap (report §9 pattern 8) plus the named section-gap spacer
    classes. No other layout rule lives here — controls keep the
    tight spacing from ``ui_design``."""
    return (
        "<style>"
        "/* Data Cleaner Studio — section rhythm (1280px cap, generous "
        "gaps between major sections; controls stay tight) */"
        f".block-container {{ max-width: {_CONTAINER_MAX_WIDTH}px; }}"
        f".dcs-section-gap {{ height: {_SECTION_GAP}px; }}"
        f".dcs-section-gap-lg {{ height: {_SECTION_GAP_LARGE}px; }}"
        "</style>"
    )


def section_gap_html(px: int = 48) -> str:
    """Return one spacer div, ``px`` tall (clamped to 16–128px). Use
    between major sections so the page breathes the way the report's
    128px marketing rhythm does, at a dashboard scale."""
    h = max(16, min(128, int(px)))
    return (f'<div class="dcs-section-gap" aria-hidden="true" '
            f'style="height: {h}px;"></div>')


# ---------------------------------------------------------------------------
# Render wrappers — thin: build the HTML above, inject it through
# Streamlit. ``st_module`` follows the ui_design.inject_design_system
# convention (defaults to the imported streamlit module; pass the
# app's ``st`` when testing with a fake).
# ---------------------------------------------------------------------------

def skeleton(lines: int = 3, title: bool = True, st_module=None) -> None:
    """Render :func:`skeleton_html` — the text/KPI placeholder."""
    (st_module or st).markdown(skeleton_html(lines=lines, title=title),
                               unsafe_allow_html=True)


def skeleton_table(rows: int = 5, columns: int = 4, st_module=None) -> None:
    """Render :func:`skeleton_table_html` — the data-view placeholder."""
    (st_module or st).markdown(
        skeleton_table_html(rows=rows, columns=columns),
        unsafe_allow_html=True)


def skeleton_chart(height: int = 320, st_module=None) -> None:
    """Render :func:`skeleton_chart_html` — the chart placeholder."""
    (st_module or st).markdown(skeleton_chart_html(height=height),
                               unsafe_allow_html=True)


def inject_rhythm(st_module=None) -> None:
    """Inject :func:`rhythm_css` once, right after
    ``inject_design_system``. Call it once per run, before the main
    content renders."""
    (st_module or st).markdown(rhythm_css(), unsafe_allow_html=True)


def section_gap(px: int = 48, st_module=None) -> None:
    """Render :func:`section_gap_html` — the spacer between major
    sections."""
    (st_module or st).markdown(section_gap_html(px=px),
                               unsafe_allow_html=True)
