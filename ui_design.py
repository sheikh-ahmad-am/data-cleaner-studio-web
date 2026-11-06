"""Data Cleaner Studio — Supabase design system (foundation module).

The single source of truth for the app's look, measured off the live
Supabase dashboard and marketing site — see ``supabase-design-study.md``
in the repo root (committed alongside this module as the design
reference) and the research notes' design-language / UX-patterns
sections. The AUTHORITATIVE brief is ``supabase-ui-ux-design-analysis.md``
(also committed with this module): Supabase feels calm, precise, and
quietly confident — a well-lit workbench, nothing shouting. One green
that only ever means "do this" or "this worked". Borders, not shadows.
Motion is functional only (spinner, skeleton fade, subtle hovers, tab
swaps). One primary action per screen. Empty states are explicit with a
next step; errors name the cause and the fix.

Hold every screen built on this module against the brief's test: "A
developer opens it, sees exactly what to do next, and trusts it because
nothing is trying to impress them." If a screen is trying to impress,
it has failed the brief.

Worker B pastes the ``DESIGN_SYSTEM_CSS`` body below verbatim
into app.py's literal ``DESIGN_SYSTEM_CSS = \"\"\"<style>...</style>\"\"\"``
assignment (the theme tests read it from app.py source); Worker C
restyles the feat_* screens with the tokens and helpers here.

Rules the whole module follows:
  * One accent, rationed: deep green is for primary actions, brand and
    success only. Everything else is monochrome (near-black ink, muted
    grey, hairline borders) on near-white.
  * Flat: borders do the work, never shadows. Cards carry no box-shadow.
  * Green is used sparingly; amber pills mark beta / warning states;
    the restrained danger red below is for destructive actions only.

Public API (presentation only — no behaviour changes):
  * ``TOKENS`` — every design token as a dict of hex / size strings.
  * ``DESIGN_SYSTEM_CSS`` — the full ``<style>...</style>`` block.
  * ``inject_design_system(st=None)`` — inject the stylesheet.
  * ``topbar(title, breadcrumb="")`` — 48px top bar with breadcrumb.
  * ``sidebar_nav(sections, active=None)`` — grouped nav rows.
  * ``section_heading(text, sub=None)`` — 16-18px section heading.
  * ``kpi_tile(label, value, sub=None)`` — status tile (icon box +
    uppercase micro-label + value).
  * ``card(title=None, body="", footer=None)`` — white bordered card.
  * ``pill(text, kind="mint")`` — status pill; returns an HTML string.
  * ``empty_state(title, body="", cta_label=None)`` — guided empty
    state; returns True when its CTA button is clicked.
  * ``column_type_label(name, dtype)`` — a table column header the way
    Supabase shows it (``name text``): name in ink, type in muted mono.
  * ``storage_bar(used_pct, label=None)`` — a thin storage-usage
    hairline (Profile screen), green fill, muted label.
"""

from __future__ import annotations

import html

import streamlit as st

# ---------------------------------------------------------------------------
# Tokens — measured off the live Supabase dashboard / marketing site
# (supabase-design-study.md). Hex values are lowercase throughout so the
# stylesheet checks match them exactly.
# ---------------------------------------------------------------------------
TOKENS = {
    # Surfaces
    "bg": "#fdfdfd",            # page / app / top-bar / sidebar background
    "card": "#ffffff",          # card and panel background
    "border": "#e8e8e8",        # hairline: card edges, table gridlines
    "button_border": "#e5e5e5",  # secondary-button hairline border
    "checkbox_border": "#d0d0d0",
    "panel_grey": "#f8f8f8",    # inline-code chips, subtle panels
    # Greens — the one accent, rationed to brand / primary / success
    "primary": "#117f50",       # primary-button background (deep green)
    "gradient_top": "#118050",  # primary-button gradient, top
    "gradient_bottom": "#0e7d4e",  # primary-button gradient, bottom
    "brand_green": "#3ecf8e",   # logo mark green
    "icon_green": "#16b674",    # node / status-icon green
    "mint_pill": "#e9f8f1",     # pale mint pill fill (e.g. NEW banner)
    # Amber — beta / warning pills
    "amber_fill": "#f4ece3",    # pale cream pill fill
    "amber_text": "#e69344",    # amber pill text
    "amber_border": "#f3ba63",  # amber pill border / accent
    # Type
    "ink": "#030303",           # near-black headings and body text
    "body": "#4d4d4d",          # body copy on marketing pages
    "muted": "#696969",         # muted / secondary text, micro-labels
    # Navigation
    "active_nav": "#f3f3f3",    # active nav row / active tab pill
    "hover": "#f8f8f8",         # nav-row hover wash
    # Destructive actions only — a restrained red, never the old dark
    # ink, and never used for ordinary text or accents.
    "danger": "#b91c1c",
    # Type scale
    "h1_size": "28px",
    "section_size": "17px",
    "body_size": "14px",
    "micro_size": "11px",
    # Radii
    "card_radius": "12px",
    "button_radius": "6px",
    "input_radius": "6px",
    "topbar_height": "48px",
}

# ---------------------------------------------------------------------------
# Consolidated stylesheet. Worker B: paste this whole block verbatim into
# app.py as its literal DESIGN_SYSTEM_CSS assignment — do not retype it,
# do not re-derive it. The theme tests read that assignment from source.
# ---------------------------------------------------------------------------
DESIGN_SYSTEM_CSS = """<style>
/* ---- page: near-white everywhere, no separate grey canvas ---- */
.stApp { background-color: #fdfdfd; color: #030303; }
.stApp p, .stApp li, .stApp span { color: #030303; }
.stApp { font-size: 14px; }
/* ---- typography: H1 28px medium, sections 16-18px, body 13-14px ---- */
.stApp h1 { font-size: 28px; font-weight: 500; color: #030303;
  line-height: 1.2; margin-bottom: 0.25rem; }
.stApp h2 { font-size: 18px; font-weight: 500; color: #030303;
  margin-top: 1.25rem; margin-bottom: 0.5rem; }
.stApp h3 { font-size: 16px; font-weight: 600; color: #030303;
  margin-top: 1rem; margin-bottom: 0.4rem; }
.stApp [data-testid="stCaptionContainer"], .stApp small {
  color: #696969; }
/* ---- tiny uppercase section labels: 10-11px, letterspaced, muted ---- */
.dcs-micro-label, .dcs-section-label {
  font-size: 11px; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase; color: #696969; }
/* ---- cards: white, 1px hairline border, 10-12px radius, flat ---- */
.dcs-card { background-color: #ffffff; border: 1px solid #e8e8e8;
  border-radius: 12px; padding: 1rem 1.25rem; margin-bottom: 1rem; }
div[data-testid="stExpander"] { background-color: #ffffff;
  border: 1px solid #e8e8e8; border-radius: 12px; }
/* ---- spacing: consistent gaps between sections ---- */
div[data-testid="stVerticalBlock"] > div { gap: 0.75rem; }
/* ---- buttons: primary deep green, subtle vertical gradient ---- */
.stApp .stButton > button[kind="primary"],
div[data-testid="stButton"] > button[kind="primary"] {
  background-color: #117f50;
  background: linear-gradient(180deg, #118050 0%, #0e7d4e 100%);
  color: #ffffff; border: 1px solid #117f50; border-radius: 6px;
  font-weight: 500; }
.stApp .stButton > button[kind="primary"]:hover,
div[data-testid="stButton"] > button[kind="primary"]:hover {
  background-color: #117f50;
  background: linear-gradient(180deg, #118050 0%, #0e7d4e 100%);
  border-color: #117f50; color: #ffffff; }
/* ---- secondary buttons: white, 1px light border, black text ---- */
.stApp .stButton > button[kind="secondary"],
div[data-testid="stButton"] > button[kind="secondary"] {
  background-color: #ffffff; color: #030303; border: 1px solid #e5e5e5;
  border-radius: 6px; font-weight: 500; }
.stApp .stButton > button[kind="secondary"]:hover,
div[data-testid="stButton"] > button[kind="secondary"]:hover {
  background-color: #f8f8f8; color: #030303; border-color: #e5e5e5; }
/* Danger buttons (delete / clear / reset / remove) are secondary buttons
   (type="secondary", never primary). Streamlit buttons cannot carry a
   custom class, so the danger colour lives on this .dcs-danger hook for
   any future wrapper that can target it — the buttons themselves rely
   on the secondary treatment above. */
.dcs-danger button[kind="secondary"] { color: #b91c1c !important;
  border-color: #b91c1c !important; }
div[data-testid="stDownloadButton"] > button {
  background-color: #ffffff; color: #030303; border: 1px solid #e5e5e5;
  border-radius: 6px; }
/* ---- inputs: white, 6px radius, hairline border ---- */
.stApp input, .stApp textarea, .stApp select {
  background-color: #ffffff; color: #030303;
  border-color: #e8e8e8; border-radius: 6px; }
.stApp label { color: #030303; }
/* ---- sidebar: near-white, hairline edge, nav rows as pills ---- */
section[data-testid="stSidebar"] { background-color: #fdfdfd;
  border-right: 1px solid #e8e8e8; }
section[data-testid="stSidebar"] * { color: #030303; }
section[data-testid="stSidebar"] a { color: #117f50; }
.dcs-nav-row { display: block; padding: 0.35rem 0.75rem;
  border-radius: 6px; font-size: 13px; color: #030303;
  border-left: 2px solid transparent; margin-bottom: 2px; }
.dcs-nav-row:hover { background-color: #f8f8f8; }
.dcs-nav-row.dcs-nav-active { background-color: #f3f3f3;
  font-weight: 600; color: #030303; border-left: 2px solid #030303; }
/* ---- links: deep green, sparingly ---- */
.stApp a { color: #117f50; }
/* ---- top bar: 48px, near-white, hairline bottom border ---- */
.dcs-topbar { height: 48px; display: flex; align-items: center;
  gap: 0.75rem; background-color: #fdfdfd;
  border-bottom: 1px solid #e8e8e8; margin-bottom: 1rem; }
.dcs-topbar .dcs-topbar-title { font-size: 17px; font-weight: 500;
  color: #030303; }
.dcs-topbar .dcs-topbar-crumb { font-size: 13px; color: #696969; }
/* ---- KPI metric values + labels: ink, never faint grey ---- */
div[data-testid="stMetricValue"], div[data-testid="stMetricValue"] * {
  color: #030303 !important; }
div[data-testid="stMetricLabel"], div[data-testid="stMetricLabel"] * {
  color: #696969 !important; }
/* ---- KPI tiles: white icon box + micro-label + value ---- */
.dcs-kpi { background-color: #ffffff; border: 1px solid #e8e8e8;
  border-radius: 12px; padding: 0.9rem 1rem; }
.dcs-kpi .dcs-kpi-label { font-size: 11px; font-weight: 600;
  letter-spacing: 0.08em; text-transform: uppercase; color: #696969; }
.dcs-kpi .dcs-kpi-value { font-size: 20px; font-weight: 500;
  color: #030303; font-family: ui-monospace, "SF Mono", Menlo, monospace; }
.dcs-kpi .dcs-kpi-sub { font-size: 13px; color: #696969; }
/* ---- file-uploader dropzone + uploaded-file chips: ink on white ---- */
div[data-testid="stFileUploader"], div[data-testid="stFileUploader"] * {
  color: #030303 !important; }
/* ---- info / success / warning / error boxes: nested elements ink ---- */
div[data-testid="stAlert"], div[data-testid="stAlert"] * {
  color: #030303 !important; }
div[data-testid="stAlert"] a { color: #117f50 !important; }
/* ---- pills: fully rounded, uppercase ~10px, letterspaced ---- */
.dcs-pill { display: inline-block; font-size: 10px; font-weight: 600;
  letter-spacing: 0.08em; text-transform: uppercase;
  border-radius: 999px; padding: 0.15rem 0.6rem; line-height: 1.6; }
.dcs-pill-mint { background-color: #e9f8f1; color: #117f50; }
.dcs-pill-amber { background-color: #f4ece3; color: #e69344;
  border: 1px solid #f3ba63; }
.dcs-pill-green { background-color: #117f50; color: #ffffff; }
.dcs-pill-grey { background-color: #f3f3f3; color: #696969; }
.dcs-pill-danger { background-color: #ffffff; color: #b91c1c;
  border: 1px solid #b91c1c; }
/* ---- code: white panels with hairline border, never dark blocks ---- */
.stApp code, .stApp pre { background-color: #f8f8f8; color: #030303;
  font-family: ui-monospace, "SF Mono", Menlo, monospace; }
div[data-testid="stCodeBlock"] { background-color: #ffffff;
  border: 1px solid #e8e8e8; border-radius: 12px; }
div[data-testid="stCodeBlock"] pre { background-color: #ffffff; }
/* ---- numbers and code: monospace ---- */
.dcs-mono { font-family: ui-monospace, "SF Mono", Menlo, monospace; }
/* ---- column headers show their type (name text, price numeric) ---- */
.dcs-coltype { font-size: 13px; color: #030303; }
.dcs-coltype .dcs-coltype-kind { font-size: 12px; color: #696969;
  font-family: ui-monospace, "SF Mono", Menlo, monospace; }
/* ---- storage usage: one thin hairline, green fill, muted label ---- */
.dcs-storage { height: 4px; background-color: #e8e8e8;
  border-radius: 999px; overflow: hidden; }
.dcs-storage > div { height: 100%; background-color: #117f50;
  border-radius: 999px; }
/* ---- spinner: green ---- */
div[data-testid="stSpinner"] { color: #117f50; }
div[data-testid="stSpinner"] > div { border-top-color: #117f50 !important; }
/* ---- section switcher (radio styled as a tab bar) ---- */
div[data-testid="stRadio"] div[role="radiogroup"] {
  gap: 0.35rem !important; }
div[data-testid="stRadio"] div[role="radiogroup"] label {
  background-color: #ffffff !important;
  border: 1px solid #e8e8e8 !important;
  border-radius: 6px !important;
  padding: 0.35rem 0.9rem !important;
  color: #030303 !important; }
div[data-testid="stRadio"] div[role="radiogroup"] label:hover {
  background-color: #f8f8f8 !important; }
div[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) {
  background-color: #f3f3f3 !important;
  border-color: #e8e8e8 !important;
  color: #030303 !important; font-weight: 600 !important; }
/* ---- dense spreadsheet-like tables: white, hairline gridlines ---- */
div[data-testid="stDataFrame"], div[data-testid="stTable"] {
  background-color: #ffffff; border: 1px solid #e8e8e8;
  border-radius: 12px; }
div[data-testid="stDataFrame"] table, div[data-testid="stTable"] table {
  background-color: #ffffff; }
div[data-testid="stDataFrame"] th, div[data-testid="stTable"] th {
  background-color: #ffffff; color: #030303; font-weight: 600;
  border-bottom: 1px solid #e8e8e8; font-size: 13px; }
div[data-testid="stDataFrame"] td, div[data-testid="stTable"] td {
  background-color: #ffffff; color: #030303;
  border-bottom: 1px solid #e8e8e8; font-size: 13px; }
/* ---- subtle, instant hovers (no long transitions) ---- */
.stApp .stButton > button, .stApp a, .dcs-nav-row {
  transition: background-color 0.1s ease, color 0.1s ease; }
/* ---- empty state: centred, calm, guided ---- */
.dcs-empty { text-align: center; padding: 2.5rem 1rem;
  background-color: #ffffff; border: 1px solid #e8e8e8;
  border-radius: 12px; }
.dcs-empty h3 { font-size: 17px; font-weight: 500; color: #030303; }
.dcs-empty p { font-size: 14px; color: #696969; }
/* ---- footer ---- */
.dcs-footer { color: #696969; font-size: 0.85rem; text-align: center;
  padding: 1.5rem 0 0.5rem; }
</style>"""


def inject_design_system(st_module=None) -> None:
    """Inject ``DESIGN_SYSTEM_CSS`` into the page. Call once, right after
    ``set_page_config`` (and before the login view renders), so the auth
    screen gets the design system too. ``st_module`` defaults to the
    imported ``streamlit`` module; pass the app's ``st`` when testing
    with a fake."""
    (st_module or st).markdown(DESIGN_SYSTEM_CSS, unsafe_allow_html=True)


def topbar(title: str, breadcrumb: str = "") -> None:
    """Render the 48px top bar: breadcrumb (muted, left) + page title.

    Presentation only — the bar is a visual shell; navigation stays
    with the app's own controls.
    """
    crumb = (f'<span class="dcs-topbar-crumb">{html.escape(breadcrumb)}'
             f"</span><span class=\"dcs-topbar-crumb\"> / </span>"
             if breadcrumb else "")
    st.markdown(
        f'<div class="dcs-topbar">{crumb}'
        f'<span class="dcs-topbar-title">{html.escape(title)}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )


def sidebar_nav(sections, active: str | None = None) -> None:
    """Render grouped sidebar nav rows.

    ``sections`` is a list of ``(label, items)`` where ``label`` is the
    tiny uppercase section heading (e.g. "Manage") and ``items`` is a
    list of ``(key, label)`` pairs — or plain label strings, in which
    case the label itself is the key. The row whose key equals
    ``active`` gets the active pill (``#f3f3f3`` + semibold + dark left
    edge); the rest get the subtle hover wash.

    Display-only: this helper draws the rows, it does not navigate.
    The caller keeps its own selection control (e.g. the tab-bar radio)
    and passes the current key back in as ``active``.
    """
    parts: list[str] = []
    for section_label, items in sections:
        parts.append(
            f'<div class="dcs-section-label">{html.escape(section_label)}'
            f"</div>")
        for item in items:
            key, label = item if isinstance(item, tuple) else (item, item)
            cls = "dcs-nav-row dcs-nav-active" if key == active \
                else "dcs-nav-row"
            parts.append(
                f'<div class="{cls}">{html.escape(str(label))}</div>')
    st.markdown("\n".join(parts), unsafe_allow_html=True)


def section_heading(text: str, sub: str | None = None) -> None:
    """Render a 16-18px section heading with an optional muted sub-line
    underneath (the dashboard's "Get connected" / "Users" pattern)."""
    sub_html = (f'<div style="font-size: 13px; color: #696969;">'
                f"{html.escape(sub)}</div>" if sub else "")
    st.markdown(
        f'<h2 style="font-size: 17px; font-weight: 500; color: #030303;">'
        f"{html.escape(text)}</h2>{sub_html}",
        unsafe_allow_html=True,
    )


def kpi_tile(label: str, value: str, sub: str | None = None) -> None:
    """Render one status tile: uppercase micro-label, large (monospace)
    value, optional muted sub-line — the dashboard home's six-tile
    pattern (STATUS / Healthy, COMPUTE SIZE / NANO, ...)."""
    sub_html = (f'<div class="dcs-kpi-sub">{html.escape(sub)}</div>'
                if sub else "")
    st.markdown(
        f'<div class="dcs-kpi">'
        f'<div class="dcs-kpi-label">{html.escape(label)}</div>'
        f'<div class="dcs-kpi-value">{html.escape(str(value))}</div>'
        f"{sub_html}</div>",
        unsafe_allow_html=True,
    )


def card(title: str | None = None, body: str = "",
         footer: str | None = None) -> None:
    """Render a white card (1px hairline border, 12px radius, flat).

    ``title`` is the card heading (skipped when None), ``body`` is HTML
    already escaped / authored by the caller, ``footer`` an optional
    muted footer line. Keep ``body`` short — cards are for one idea.
    """
    title_html = (f'<div style="font-size: 16px; font-weight: 600; '
                  f'color: #030303; margin-bottom: 0.5rem;">'
                  f"{html.escape(title)}</div>" if title else "")
    footer_html = (f'<div style="font-size: 13px; color: #696969; '
                   f'margin-top: 0.75rem;">{html.escape(footer)}</div>'
                   if footer else "")
    st.markdown(
        f'<div class="dcs-card">{title_html}{body}{footer_html}</div>',
        unsafe_allow_html=True,
    )


def pill(text: str, kind: str = "mint") -> str:
    """Return a status pill as an HTML string (embed it in markdown or
    in a card body). ``kind`` is one of:

    * ``"mint"`` — pale mint fill, green text (success / NEW)
    * ``"amber"`` — pale cream fill, amber text (BETA / warning)
    * ``"green"`` — solid deep-green fill, white text
    * ``"grey"`` — pale grey fill, muted text (neutral / disabled)
    * ``"danger"`` — white fill, restrained red text + border
    """
    kinds = {"mint": "dcs-pill-mint", "amber": "dcs-pill-amber",
             "green": "dcs-pill-green", "grey": "dcs-pill-grey",
             "danger": "dcs-pill-danger"}
    cls = kinds.get(kind, "dcs-pill-mint")
    return (f'<span class="dcs-pill {cls}">{html.escape(str(text))}'
            f"</span>")


def empty_state(title: str, body: str = "",
                cta_label: str | None = None) -> bool:
    """Render a guided empty state: centred title + muted body inside a
    white bordered card, with an optional CTA button underneath.

    Returns True when the CTA button is clicked (False when there is no
    CTA, or it was not clicked), so the caller can act on it.
    """
    st.markdown(
        f'<div class="dcs-empty"><h3>{html.escape(title)}</h3>'
        f"<p>{html.escape(body)}</p></div>" if body else
        f'<div class="dcs-empty"><h3>{html.escape(title)}</h3></div>',
        unsafe_allow_html=True,
    )
    if cta_label:
        slug = "".join(ch if ch.isalnum() else "-"
                       for ch in cta_label.lower())[:24] or "cta"
        return bool(st.button(cta_label, type="primary",
                              key=f"dcs-empty-{slug}"))
    return False


def column_type_label(name: str, dtype: str) -> str:
    """Return a table column header the way Supabase shows it — ``name
    text``, ``price numeric``: the column name in ink, its type in muted
    monospace beside it. The type is part of the table's honesty.
    Returns an HTML string for use in a header row or card body."""
    return (f'<span class="dcs-coltype">{html.escape(str(name))} '
            f'<span class="dcs-coltype-kind">'
            f"{html.escape(str(dtype))}</span></span>")


def storage_bar(used_pct: float, label: str | None = None) -> None:
    """Render storage usage as one thin progress hairline (the Profile
    screen pattern): a 4px track with a green fill, and an optional
    muted label underneath (e.g. "1.2 GB of 5 GB used"). ``used_pct``
    is clamped to 0-100. Quiet by design — no numbers shouting, no
    coloured warnings; the danger zone lives elsewhere."""
    pct = max(0.0, min(100.0, float(used_pct)))
    label_html = (f'<div style="font-size: 13px; color: #696969; '
                  f'margin-top: 0.35rem;">{html.escape(label)}</div>'
                  if label else "")
    st.markdown(
        f'<div class="dcs-storage"><div style="width: {pct:.1f}%;">'
        f"</div></div>{label_html}",
        unsafe_allow_html=True,
    )
