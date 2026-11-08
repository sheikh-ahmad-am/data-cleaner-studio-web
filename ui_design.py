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
  * ``TOKENS`` — every light-theme design token as a dict of hex /
    size strings.
  * ``DARK_TOKENS`` — the dark-theme tokens, same keys as ``TOKENS``
    plus ``primary_hover``, ``link`` and ``focus_gap``. Dark hexes
    are secondary-sourced candidates from the research report
    (§1.2) — surface ``#1b1d1c``, text ``#edefee`` — picked so every
    text/background pair passes WCAG AA (see the contrast test in
    tests/test_supabase_theme.py).
  * ``DESIGN_SYSTEM_CSS`` — the full light ``<style>...</style>`` block.
  * ``DARK_CSS`` — the full dark ``<style>...</style>`` block, same
    structure and class names as the light one, dark tokens only.
  * ``theme_css(theme)`` — the stylesheet for ``"light"`` or
    ``"dark"`` (anything else falls back to light); ``normalize_theme``
    does the same name check without returning CSS.
  * ``inject_design_system(st=None, theme="light")`` — inject the
    stylesheet for the given theme.
  * ``MATERIAL_ICONS`` / ``icon_for(name)`` — the Material shortcode
    for a semantic icon name; ``icon_button(label, icon, kind, ...)``
    is a Supabase-style icon button (16px line icon left of the
    label, tooltip via ``help``); ``svg_icon(name, size)`` is the
    inline-SVG twin for HTML the widgets cannot reach.
  * ``THEME_SELECT_KEY`` / ``THEME_RADIO_KEY`` — the theme controls'
    widget keys (never ``"dcs_theme"`` itself, which is the plain
    session key the stylesheet follows); ``sync_theme_widgets`` syncs
    them to the theme in effect before any theme widget is created,
    so the sidebar dropdown can never show "Light" while the page is
    dark.
  * ``render_theme_toggle(st=None)`` — the sidebar Light/Dark switch
    (writes ``st.session_state["dcs_theme"]`` via ``on_change``);
    ``render_login_theme_toggle`` is the same switch as a button for
    the login screen, which has no sidebar.
  * ``topbar(title, breadcrumb="", user=None, logo_path=None)`` — the
    real top bar: logo + workspace + screen, search column, green
    ``Upload`` pill, Help icon button, avatar; returns the actions
    (``avatar`` / ``upload`` / ``help`` / ``search_col``).
  * ``sidebar_nav(sections, active=None)`` — grouped nav rows as
    clickable icon buttons (the active row is a disabled button
    styled as the active pill); returns the clicked key or None.
  * ``render_avatar_menu(st=None, user=None, container=None)`` — the
    avatar + Supabase-style account menu (email bold, Account,
    Feature previews, Changelog, Theme Dark/Light radio, Timezone,
    Sign out; no Upgrade — no paid tier); ``render_sidebar_avatar``
    is the sidebar-placement wrapper kept for old call sites.
  * ``section_heading(text, sub=None)`` — 16-18px section heading
    (colours in the stylesheet, never inline hex).
  * ``kpi_tile(label, value, sub=None, icon=None)`` — status tile
    (icon box + uppercase micro-label + value).
  * ``card(title=None, body="", footer=None)`` — white bordered card.
  * ``settings_card(title, desc=None)`` — one Supabase-style settings
    card (label + description left, controls right; returns
    ``(left, right, card)`` so the caller can add a Save row at the
    card's bottom-right).
  * ``metric_card(label, value, warnings=0, errors=0, bars=None)`` —
    a service metric card (label + warning/error dots, large count,
    bar sparkline).
  * ``connect_strip(cells)`` — the "Get connected" six-cell strip,
    mapped to the app's own actions; returns the clicked cell key.
  * ``pill(text, kind="mint")`` — status pill; returns an HTML string.
  * ``empty_state(title, body="", cta_label=None)`` — guided empty
    state; returns True when its CTA button is clicked.
  * ``column_type_label(name, dtype)`` — a table column header the way
    Supabase shows it (``name text``): name in ink, type in muted mono.
  * ``storage_bar(used_pct, label=None)`` — a thin storage-usage
    hairline (Profile screen), green fill, muted label.
"""

from __future__ import annotations

import base64
import html
from pathlib import Path

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
# Dark tokens — same keys as TOKENS, plus the extras the dark theme
# needs (primary hover, brightened link green, focus-ring gap colour).
# Provenance: the research report's dark candidates (§1.2), all
# secondary-sourced (measured by forcing the dark colour scheme, not
# official tokens) — surface #1b1d1c, text #edefee, secondary #bcbdbc /
# #989a99, primary fills deepened to #006338, brand links brightened to
# #4acd8b. Every value below was picked against WCAG AA: ink-on-surface
# 14.67:1, secondary-on-surface 8.99:1, muted-on-surface 5.99:1,
# link-on-surface 8.39:1, white-on-primary-fill 7.39:1, mint-text on
# mint-fill 6.65:1, amber-text on amber-fill 9.04:1, danger-on-surface
# 5.84:1 (all >= 4.5:1; see test_dark_theme_contrast_aa). The brand
# mint #3ecf8e stays logo-only, never text on a light surface — on dark
# it is only ever a hover/link-adjacent green, never body text.
# ---------------------------------------------------------------------------
DARK_TOKENS = {
    # Surfaces — near-black green-grey, card one step lighter
    "bg": "#1b1d1c",
    "card": "#232625",
    "border": "#2e2e2e",
    "button_border": "#363636",
    "checkbox_border": "#4a4d4c",
    "panel_grey": "#262928",
    # Greens — primary fill deepened so it does not read lime on dark;
    # links/icons brightened so they still read as green on dark.
    "primary": "#006338",
    "gradient_top": "#007243",
    "gradient_bottom": "#006338",
    "brand_green": "#3ecf8e",
    "icon_green": "#4acd8b",
    "mint_pill": "#123527",
    # Amber — beta / warning pills (dark fill, brightened text)
    "amber_fill": "#2a2118",
    "amber_text": "#f3ba63",
    "amber_border": "#8a6a2f",
    # Type
    "ink": "#edefee",
    "body": "#bcbdbc",
    "muted": "#989a99",
    # Navigation
    # active_nav is a clear step lighter than the card (#232625) and
    # the hover wash (#262928): the old #2a2d2c was too close to
    # both to read as a highlight live, so the active icon looked
    # unmarked. #343837 is visibly lighter but still a quiet grey.
    "active_nav": "#343837",
    "hover": "#262928",
    # Destructive actions only — brightened red, readable on dark
    "danger": "#ff6369",
    # Type scale / radii — identical to the light theme
    "h1_size": "28px",
    "section_size": "17px",
    "body_size": "14px",
    "micro_size": "11px",
    "card_radius": "12px",
    "button_radius": "6px",
    "input_radius": "6px",
    "topbar_height": "48px",
    # Dark-only extras
    "primary_hover": "#007243",
    "link": "#4acd8b",
    "focus_gap": "#1b1d1c",
    "focus_halo": "#30ba798c",
}

#: The two themes the app ships. Default is "light" (the first-paint
#: base in .streamlit/config.toml is light too).
THEME_DEFAULT = "light"
THEMES = ("light", "dark")


def normalize_theme(value) -> str:
    """Return ``"light"`` or ``"dark"`` for any stored theme value;
    anything unknown (including None and legacy names) falls back to
    the light default, so a stale value can never strand the app."""
    return value if value in THEMES else THEME_DEFAULT


# ---------------------------------------------------------------------------
# Icons — the "button logo" (page-by-page study §10).
#
# Supabase's dashboard puts a small 16px line icon immediately left of
# every action button's label (plus on New, play on Run, plug on
# Connect, book on Docs, sparkle on Ask Assistant, copy on Copy) and
# on every nav row. Our 93 buttons were all text-only because
# ``st.button`` has no icon slot — but Streamlit 1.32+ accepts an
# ``icon=`` shortcode (``:material/<name>:``), which renders a real
# outline glyph left of the label. That is what this module uses:
# one semantic name per action, mapped to a Material Symbols name.
# Every name here was verified to render (AppTest: no exception, icon
# set on the button) against streamlit 1.66.1 — an invalid name raises
# StreamlitAPIException at render time, so a bad name can never ship
# silently; the rebuild tests pin the whole map. ``power_plug`` is
# NOT a valid Material name — Connect uses ``link`` (Supabase's
# Connect icon reads as a plug/link either way).
# ---------------------------------------------------------------------------
MATERIAL_ICONS = {
    # Actions
    "add": ":material/add:",
    "play": ":material/play_arrow:",
    "upload": ":material/upload:",
    "download": ":material/download:",
    "search": ":material/search:",
    "connect": ":material/link:",
    "book": ":material/menu_book:",
    "sparkle": ":material/auto_awesome:",
    "copy": ":material/content_copy:",
    "save": ":material/save:",
    "refresh": ":material/refresh:",
    "filter": ":material/filter_alt:",
    "sort": ":material/sort:",
    "edit": ":material/edit:",
    "delete": ":material/delete:",
    "check": ":material/check:",
    "close": ":material/close:",
    "help": ":material/help:",
    "info": ":material/info:",
    "warning": ":material/warning:",
    "more": ":material/more_vert:",
    "chevron_right": ":material/chevron_right:",
    "chevron_left": ":material/chevron_left:",
    "open": ":material/open_in_new:",
    "undo": ":material/undo:",
    "bolt": ":material/electric_bolt:",
    "fix": ":material/auto_fix_high:",
    # Nav / sections
    "preview": ":material/preview:",
    "clean": ":material/cleaning_services:",
    "join": ":material/join_inner:",
    "kpis": ":material/analytics:",
    "dashboard": ":material/dashboard:",
    "compare": ":material/compare_arrows:",
    "report": ":material/assessment:",
    "tools": ":material/build:",
    "tutorial": ":material/school:",
    "settings": ":material/settings:",
    "profile": ":material/person:",
    "status": ":material/monitor_heart:",
    # Objects
    "home": ":material/home:",
    "table": ":material/table_chart:",
    "database": ":material/database:",
    "lock": ":material/lock:",
    "folder": ":material/folder:",
    "code": ":material/code:",
    "chart": ":material/bar_chart:",
    "doc": ":material/description:",
    "account": ":material/person:",
    "flask": ":material/science:",
    "changelog": ":material/list_alt:",
    "logout": ":material/logout:",
    "grid": ":material/grid_view:",
    "storage": ":material/storage:",
    "functions": ":material/functions:",
    "terminal": ":material/terminal:",
    "history": ":material/history:",
    "lightbulb": ":material/lightbulb:",
    "image": ":material/image:",
    "diamond": ":material/diamond:",
    "clock": ":material/schedule:",
}

#: Nav key -> icon name, so the sidebar rows and the top bar share one
#: mapping (a nav item never has two different icons).
NAV_ICONS = {
    "preview": "preview", "clean": "clean", "join": "join",
    "kpis": "kpis", "dashboard": "dashboard", "compare": "compare",
    "report": "report", "tools": "tools", "tutorial": "tutorial",
    "settings": "settings", "profile": "profile", "status": "status",
}


def icon_for(name: str) -> str:
    """The Material shortcode for a semantic icon name (``":material/…"``).

    Unknown names fall back to ``"diamond"`` — a visible glyph, never
    a crash and never a silent missing icon."""
    return MATERIAL_ICONS.get(str(name), MATERIAL_ICONS["diamond"])


def icon_button(label: str, icon: str, kind: str = "secondary",
                key=None, help: str | None = None,
                disabled: bool = False, use_container_width: bool = False,
                st_module=None) -> bool:
    """A Supabase-style icon button: a small line icon immediately left
    of the label (the "button logo" the dashboard has and we lacked).

    ``kind`` is ``"primary"`` (green pill — New / Connect / Run /
    the one primary action), ``"secondary"`` (white, hairline border)
    or ``"danger"`` (secondary + the red danger treatment: a
    ``dcs-danger-zone`` marker is emitted just before the button and
    the stylesheet colours every secondary button after that marker
    red — the marker only ever appears in a danger zone, whose
    buttons are all destructive, so nothing else turns red).
    ``help`` is the hover tooltip — every icon-only or icon button
    carries one, the way the dashboard's tooltips name each control.
    Returns True when clicked. ``st_module`` defaults to the imported
    ``streamlit``; pass the app's ``st`` when testing with a fake."""
    st_mod = st_module or st
    if kind == "danger":
        st_mod.markdown('<div class="dcs-danger-zone"></div>',
                        unsafe_allow_html=True)
    return bool(st_mod.button(
        label, icon=icon_for(icon),
        type="primary" if kind == "primary" else "secondary",
        key=key, help=help, disabled=disabled,
        use_container_width=use_container_width))


# ---------------------------------------------------------------------------
# Inline SVG line icons — for HTML the widgets cannot reach (KPI icon
# boxes, the "Get connected" strip, the active nav pill). Same 24x24
# Lucide-style language as the Material glyphs above (1px-ish stroke,
# round caps): a tiny hand-checked set, one path per icon, so a wrong
# path is obvious on sight. ``size`` is the rendered pixel size.
# ---------------------------------------------------------------------------
_SVG_PATHS = {
    # 3x3 grid of dots (the dashboard's STATUS tile icon).
    "dots": ('<circle cx="5" cy="5" r="1.6"/><circle cx="12" cy="5" r="1.6"/>'
             '<circle cx="19" cy="5" r="1.6"/><circle cx="5" cy="12" r="1.6"/>'
             '<circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>'
             '<circle cx="5" cy="19" r="1.6"/><circle cx="12" cy="19" r="1.6"/>'
             '<circle cx="19" cy="19" r="1.6"/>'),
    "database": ('<ellipse cx="12" cy="5" rx="9" ry="3"/>'
                 '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>'
                 '<path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3"/>'),
    "file": ('<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 '
             '0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>'),
    "clock": ('<circle cx="12" cy="12" r="10"/>'
              '<path d="M12 6v6l4 2"/>'),
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "alert": ('<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 '
              '21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4M12 17h.01"/>'),
    "chart": ('<path d="M3 3v18h18"/><path d="M18 17V9M13 17V5M8 17v-3"/>'),
    "upload": ('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
               '<path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>'),
    "link": ('<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07'
             'l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 '
             '0 0 0 7.07 7.07l1.71-1.71"/>'),
    "table": ('<rect x="3" y="3" width="18" height="18" rx="2"/>'
              '<path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>'),
    "eye": ('<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>'
            '<circle cx="12" cy="12" r="3"/>'),
    "grid": ('<rect x="3" y="3" width="7" height="7" rx="1"/>'
             '<rect x="14" y="3" width="7" height="7" rx="1"/>'
             '<rect x="3" y="14" width="7" height="7" rx="1"/>'
             '<rect x="14" y="14" width="7" height="7" rx="1"/>'),
}


def svg_icon(name: str, size: int = 16) -> str:
    """An inline SVG line icon (``name`` from ``_SVG_PATHS``) as an
    HTML string, ``size`` px square, stroke ``currentColor`` so it
    follows the surrounding text colour. Unknown names render the
    dots grid — a visible glyph, never an empty box."""
    paths = _SVG_PATHS.get(str(name), _SVG_PATHS["dots"])
    return (f'<svg width="{int(size)}" height="{int(size)}" '
            f'viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{paths}</svg>')

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
/* Cards and expanders answer the hover: the hairline deepens one
   step (to the checkbox-border token #d0d0d0) — no shadow, no lift,
   no colour change, just the border, Supabase-quiet. */
.dcs-card:hover { border-color: #d0d0d0; }
div[data-testid="stExpander"] { background-color: #ffffff;
  border: 1px solid #e8e8e8; border-radius: 12px; }
div[data-testid="stExpander"]:hover { border-color: #d0d0d0; }
/* ---- spacing: consistent gaps between sections ---- */
div[data-testid="stVerticalBlock"] > div { gap: 0.75rem; }
/* Settings cards (Profile/Settings) sit closer together — the
   dashboard's settings pages are dense, one card after another, not
   separated by wide blank gaps. This is the space BETWEEN the cards
   (the rule above is the space INSIDE each block); scoped to the main
   area so the sidebar's own rhythm is untouched. */
section[data-testid="stMain"] div[data-testid="stVerticalBlock"] {
  gap: 0.75rem; }
/* ---- buttons: primary deep green, subtle vertical gradient ---- */
.stApp .stButton > button[kind="primary"],
div[data-testid="stButton"] > button[kind="primary"] {
  background-color: #117f50;
  background: linear-gradient(180deg, #118050 0%, #0e7d4e 100%);
  color: #ffffff; border: 1px solid #117f50; border-radius: 999px;
  font-weight: 500; }
.stApp .stButton > button[kind="primary"]:hover,
div[data-testid="stButton"] > button[kind="primary"]:hover {
  background-color: #007243;
  background: linear-gradient(180deg, #0e7d4e 0%, #007243 100%);
  border-color: #007243; color: #ffffff; }
/* ---- secondary buttons: white, 1px light border, black text ---- */
.stApp .stButton > button[kind="secondary"],
div[data-testid="stButton"] > button[kind="secondary"] {
  background-color: #ffffff; color: #030303; border: 1px solid #e5e5e5;
  border-radius: 6px; font-weight: 500; }
.stApp .stButton > button[kind="secondary"]:hover,
div[data-testid="stButton"] > button[kind="secondary"]:hover {
  background-color: #03030307; color: #030303; border-color: #e5e5e5; }
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
div[data-testid="stDownloadButton"] > button:hover {
  background-color: #f8f8f8; color: #030303; border-color: #e5e5e5; }
/* ---- button colours, testid-anchored (fix-up 2026-11-07) ----
   Streamlit 1.66 does not put a `kind` attribute on the rendered
   <button> (emotion filters the prop), so the [kind="secondary"] /
   [kind="primary"] rules above never match in the browser — every
   button fell back to Streamlit's native light-theme white, which is
   why dark mode showed white pills with pale-grey text. These rules
   anchor on the testids Streamlit DOES put in the DOM
   (div[data-testid="stButton"] on the wrapper,
   button[data-testid="stBaseButton-secondary|primary"] on the button
   itself), carry !important, and out-specify the mobile stylesheet's
   blanket `.stButton > button` rule, so they win even when that sheet
   is a theme behind. The `*` rules pin the label + icon colour too —
   a pale icon on a white pill reads as "no icon". The selectors are
   DESCENDANT (no `>`): a button with an icon or a help tooltip has
   an intermediate plain div between the wrapper and the <button>
   (the $u help wrapper renders a div only when help is set —
   verified in the 1.66.1 frontend bundle), so `>` never matches
   those buttons and the rules would be dead — exactly the live
   failure round 6 fixed (compact pills, no active highlight). */
div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"],
div[data-testid="stDownloadButton"] > button {
  background-color: #ffffff !important; color: #030303 !important;
  border: 1px solid #e5e5e5 !important; border-radius: 6px;
  font-weight: 500; }
div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"] *,
div[data-testid="stDownloadButton"] > button * {
  color: #030303 !important; }
div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"]:hover,
div[data-testid="stDownloadButton"] > button:hover {
  background-color: #f3f3f3 !important; color: #030303 !important;
  border-color: #d4d4d4 !important; }
div[data-testid="stButton"] button[data-testid="stBaseButton-primary"] {
  background-color: #117f50 !important;
  background: linear-gradient(180deg, #118050 0%, #0e7d4e 100%) !important;
  color: #ffffff !important; border: 1px solid #117f50 !important;
  border-radius: 999px; font-weight: 500; }
div[data-testid="stButton"] button[data-testid="stBaseButton-primary"] * {
  color: #ffffff !important; }
/* Sidebar nav rows + the active (disabled) pill, same anchoring.
   Full-width rows (gap 3): the old `button[kind="secondary"]`
   selector was dead — Streamlit 1.66.1 renders no `kind` attribute
   on the <button> (the kind lives in
   `data-testid="stBaseButton-secondary"`), so the expanded nav rows
   rendered as compact pills hugging their labels. The wrapper div
   is forced full-width too (see below). The selectors are
   DESCENDANT (no `>`): the nav buttons carry icon= + help=, so the
   $u help wrapper nests an intermediate plain div between the
   wrapper and the <button> — `>` never matched, which is why the
   testid-anchored fix in 5028aa3 still rendered as compact pills
   live. The collapsed rail's own rule (rail_css, later in the page,
   more specific) still centres the icon-only buttons. */
section[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"] {
  background-color: #ffffff !important; color: #030303 !important;
  border: 1px solid #e5e5e5 !important;
  width: 100% !important; justify-content: flex-start !important; }
section[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"] * {
  color: #030303 !important; }
section[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"]:disabled {
  background-color: #f3f3f3 !important; color: #030303 !important;
  border: 1px solid #e5e5e5 !important; opacity: 1 !important;
  border-left: 2px solid #030303 !important; font-weight: 600 !important; }
section[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"]:disabled * {
  color: #030303 !important; }
/* Danger-zone buttons (the .dcs-danger-zone marker icon_button emits
   before a destructive button): red text + border on the secondary
   panel, testid-anchored the same way. The tail is descendant (the
   intermediate help-wrapper div); the `:has()` head is kept — the
   marker div IS a direct child of the vertical block, and there is
   no other CSS way to select "a block after the marker". */
div[data-testid="stVerticalBlock"] > div:has(.dcs-danger-zone) ~ div div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"] {
  color: #b91c1c !important; border-color: #b91c1c !important; }
div[data-testid="stVerticalBlock"] > div:has(.dcs-danger-zone) ~ div div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"] * {
  color: #b91c1c !important; }
/* ---- inputs: white, 6px radius, hairline border ---- */
.stApp input, .stApp textarea, .stApp select {
  background-color: #ffffff; color: #030303;
  border-color: #e8e8e8; border-radius: 6px; }
.stApp input:hover, .stApp textarea:hover, .stApp select:hover {
  border-color: #d0d0d0; }
.stApp label { color: #030303; }
/* ---- checkboxes: hairline box border, green check ---- */
.stApp input[type="checkbox"] { accent-color: #117f50; }
div[data-testid="stCheckbox"] div[data-baseweb="checkbox"] span {
  border-color: #d0d0d0; }
/* ---- sidebar: near-white, hairline edge, nav rows as pills ---- */
section[data-testid="stSidebar"] { background-color: #fdfdfd;
  border-right: 1px solid #e8e8e8; }
section[data-testid="stSidebar"] * { color: #030303; }
section[data-testid="stSidebar"] a { color: #117f50; }
.dcs-nav-row { display: block; padding: 0.35rem 0.75rem;
  border-radius: 6px; font-size: 13px; color: #030303;
  border-left: 2px solid transparent; margin-bottom: 2px; }
.dcs-nav-row:hover { background-color: #f8f8f8; color: #0e7e4e; }
.dcs-nav-row.dcs-nav-active { background-color: #f3f3f3;
  font-weight: 600; color: #030303; border-left: 2px solid #030303; }
/* ---- expanded nav rows are full-width (gap 3): the wrapper div
   is forced full-width here; the button itself gets its width from
   the merged sidebar rule above. The old `button[kind="secondary"]`
   selector was dead — Streamlit 1.66.1 renders no `kind` attribute
   on the <button> (the kind lives in
   `data-testid="stBaseButton-secondary"`), so the rows rendered as
   compact pills hugging their labels. The avatar trigger is a
   stPopoverButton, not an stButton, so it is untouched by this
   rule. The collapsed rail's own rule (rail_css, later in the
   page, more specific) still centres the icon-only buttons. ---- */
section[data-testid="stSidebar"] div[data-testid="stButton"] {
  width: 100% !important; }
/* ---- uploader format line wraps instead of truncating: the
   instructions element ("1GB per file • CSV, XLSX, XLS, JSON,
   PARQUET") is one long line in the 260px sidebar, so it was cut
   off at the right edge ("…JS…"). ---- */
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"],
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] * {
  white-space: normal !important; overflow: visible !important;
  text-overflow: clip !important; }
/* ---- tooltips: Supabase's dark rounded pill, white text, in both
   themes — Streamlit's native tooltip is a light box by default.
   The content lives in a floating portal, so the rule is
   document-wide (no sidebar scoping). The pill is dark in both
   themes by design, but each theme uses its OWN near-black so no
   dark token leaks into the light sheet (light ink here,
   the dark surface in the dark sheet). No shortcut chips: the
   app has no G-then-X navigation shortcuts, so none are shown. ---- */
div[data-testid="stTooltipContent"] {
  background-color: #030303 !important; color: #ffffff !important;
  border-radius: 8px !important; padding: 6px 10px !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25) !important; }
div[data-testid="stTooltipContent"] * { color: #ffffff !important; }
/* ---- sidebar collapse control: the chevron that hides / shows the
   sidebar. Streamlit renders it as collapsedControl when the bar is
   hidden and as a header button inside the bar when it is shown
   (the testid varies by version, so all three are styled) — muted
   by default, quiet wash on hover, same 6px radius as everything. */
div[data-testid="collapsedControl"],
section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"],
section[data-testid="stSidebar"] button[kind="header"] {
  color: #696969; border-radius: 6px; }
div[data-testid="collapsedControl"]:hover,
section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"]:hover,
section[data-testid="stSidebar"] button[kind="header"]:hover {
  background-color: #f8f8f8; color: #030303; }
/* ---- sidebar avatar: green circle, initial only ---- */
div[data-testid="stPopover"] { margin-bottom: 0.75rem; }
div[data-testid="stPopover"] button[data-testid="stPopoverButton"] {
  width: 44px !important; height: 44px !important;
  min-width: 44px !important; max-width: 44px !important;
  border-radius: 50% !important;
  background-color: #117f50 !important; background: #117f50 !important;
  color: #ffffff !important; border: 1px solid #117f50 !important;
  font-size: 18px !important; font-weight: 600 !important;
  padding: 0 !important; justify-content: center !important;
  align-items: center !important; }
div[data-testid="stPopover"] button[data-testid="stPopoverButton"]:hover {
  background-color: #0e7d4e !important; background: #0e7d4e !important; }
div[data-testid="stPopover"] button[data-testid="stPopoverButton"] svg {
  display: none !important; }
/* ---- avatar menu (popover body): white card, hairline border ---- */
div[data-testid="stPopoverBody"] { background-color: #ffffff;
  border: 1px solid #e8e8e8; border-radius: 12px; }
/* Avatar menu rows: the Profile / theme / Log out buttons inside the
   popover are menu rows, not pills — full-width, left-aligned, no
   border, quiet wash on hover. The popover is used only by the
   avatar, so scoping to stPopoverBody is safe. */
div[data-testid="stPopoverBody"] .stButton > button[kind="secondary"] {
  width: 100% !important; justify-content: flex-start !important;
  background: transparent !important; background-color: transparent !important;
  border: none !important; box-shadow: none !important;
  border-radius: 6px !important; padding: 0.35rem 0.75rem !important;
  font-weight: 400 !important; color: #030303 !important; }
div[data-testid="stPopoverBody"] .stButton > button[kind="secondary"]:hover {
  background-color: #f8f8f8 !important; color: #030303 !important; }
/* Menu divider: one hairline between the email, the actions and Log out. */
.dcs-menu-divider { border-top: 1px solid #e8e8e8; margin: 0.35rem 0; }
/* ---- links: deep green, sparingly ---- */
.stApp a { color: #117f50; }
.stApp a:hover { color: #0e7e4e; }
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
.dcs-kpi:hover { border-color: #d0d0d0; }
.dcs-kpi .dcs-kpi-label { font-size: 11px; font-weight: 600;
  letter-spacing: 0.08em; text-transform: uppercase; color: #696969; }
.dcs-kpi .dcs-kpi-value { font-size: 20px; font-weight: 500;
  color: #030303; font-family: ui-monospace, "SF Mono", Menlo, monospace; }
.dcs-kpi .dcs-kpi-sub { font-size: 13px; color: #696969; }
/* Strip label: the same 11px uppercase micro-label as the KPI tiles,
   for the Dashboard "Get connected" strip heading (it was missing —
   the strip rendered its six cells with no visible label). */
.dcs-strip-label { font-size: 11px; font-weight: 600;
  letter-spacing: 0.08em; text-transform: uppercase; color: #696969;
  margin-bottom: 0.5rem; }
/* ---- file-uploader dropzone + uploaded-file chips: ink on white ----
   The dropzone is a <section>, not a <div> (see the dark twin) —
   the selector below carries no element qualifier. The background
   is pinned white explicitly so the light dropzone can never
   inherit a dark fill. */
div[data-testid="stFileUploader"], div[data-testid="stFileUploader"] * {
  color: #030303 !important; }
[data-testid="stFileUploaderDropzone"] {
  background-color: #ffffff !important; border-color: #e8e8e8 !important; }
[data-testid="stFileUploaderDropzone"]:hover { border-color: #d0d0d0 !important; }
/* ---- native dropdown menus (baseweb portal): white menu, quiet hover ---- */
div[data-baseweb="popover"] { background-color: #ffffff; }
div[data-baseweb="menu"] li[role="option"] { color: #030303; }
div[data-baseweb="menu"] li[role="option"]:hover {
  background-color: #f8f8f8; }
/* ---- info / success / warning / error boxes: nested elements ink ---- */
div[data-testid="stAlert"], div[data-testid="stAlert"] * {
  color: #030303 !important; }
div[data-testid="stAlert"] a { color: #117f50 !important; }
/* ---- info boxes ONLY: no sky-blue ---- */
div[data-testid="stAlert"]:has(div[data-testid="stAlertContentInfo"]) div[data-testid="stAlertContainer"] {
  background-color: #ffffff !important; border: 1px solid #e8e8e8 !important;
  border-radius: 12px !important; }
div[data-testid="stAlert"]:has(div[data-testid="stAlertContentInfo"]) div[data-testid="stAlertContentInfo"] {
  border: none !important; background-color: transparent !important; }
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
  background-color: #ffffff; color: #696969; font-weight: 600;
  border-bottom: 1px solid #e8e8e8; font-size: 11px;
  text-transform: uppercase; letter-spacing: 0.08em; }
div[data-testid="stDataFrame"] td, div[data-testid="stTable"] td {
  background-color: #ffffff; color: #030303;
  border-bottom: 1px solid #e8e8e8; font-size: 13px; }
/* ---- motion, honestly measured: colour-only 0.2s ease-out ----
   Every hover above is a colour/border change only (no scale, no
   shadow, no movement) and every one of those elements carries this
   transition, so the hover never snaps. */
.stApp .stButton > button, .stApp a, .dcs-nav-row,
div[data-testid="stRadio"] div[role="radiogroup"] label,
.stApp input, .stApp textarea, .stApp select,
.dcs-card, .dcs-kpi, .dcs-console-inside div,
div[data-testid="stDownloadButton"] > button,
div[data-testid="stExpander"],
[data-testid="stFileUploaderDropzone"],
div[data-testid="stPopoverBody"] .stButton > button,
div[data-testid="stPopover"] button[data-testid="stPopoverButton"],
div[data-testid="collapsedControl"],
section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"],
section[data-testid="stSidebar"] button[kind="header"],
div[data-baseweb="menu"] li[role="option"] {
  transition: background-color 0.2s cubic-bezier(0.22, 1, 0.36, 1),
    border-color 0.2s cubic-bezier(0.22, 1, 0.36, 1),
    color 0.2s cubic-bezier(0.22, 1, 0.36, 1); }
/* ---- focus: one shared ring — 2px gap + 4px translucent green halo ---- */
.stApp .stButton > button:focus-visible,
div[data-testid="stDownloadButton"] > button:focus-visible,
div[data-testid="stPopover"] button[data-testid="stPopoverButton"]:focus-visible,
div[data-testid="collapsedControl"] button:focus-visible,
section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"]:focus-visible,
.stApp a:focus-visible,
div[data-testid="stRadio"] div[role="radiogroup"] label:focus-within {
  outline: none;
  box-shadow: 0 0 0 2px #fdfdfd, 0 0 0 6px #30ba798c; }
.stApp input:focus, .stApp textarea:focus, .stApp select:focus {
  outline: none;
  box-shadow: 0 0 0 2px #fdfdfd, 0 0 0 6px #30ba798c; }
/* ---- empty state: centred, calm, guided ---- */
.dcs-empty { text-align: center; padding: 2.5rem 1rem;
  background-color: #ffffff; border: 1px solid #e8e8e8;
  border-radius: 12px; }
.dcs-empty h3 { font-size: 17px; font-weight: 500; color: #030303; }
.dcs-empty p { font-size: 14px; color: #696969; }
/* ---- footer ---- */
.dcs-footer { color: #696969; font-size: 0.85rem; text-align: center;
  padding: 1.5rem 0 0.5rem; }
/* ---- login console layout (variant C): no card, top-left logo + title,
   narrow left-aligned form column, theme switch as a text link ---- */
.dcs-console-head { display: flex; align-items: center; gap: 12px; }
.dcs-console-head img { width: 40px; height: 40px; }
.dcs-console-head h1 { font-size: 22px; font-weight: 500; margin: 0; }
.dcs-console-h2 { font-size: 18px; font-weight: 500; margin: 0 0 16px; }
.dcs-code-email { color: #117f50; font-weight: 600; }
.dcs-console-status { font-size: 13px; color: #696969; display: flex;
  align-items: center; gap: 6px; margin-top: 0.75rem; }
.dcs-console-status::before { content: ""; width: 8px; height: 8px;
  border-radius: 50%; background: #117f50; display: inline-block;
  flex: none; }
/* "What's inside" — three plain lines under the login form (variant C):
   hairline divider, small muted text, green dot markers. */
.dcs-console-inside { border-top: 1px solid #e8e8e8; margin-top: 1.5rem;
  padding-top: 1rem; font-size: 13px; color: #696969; }
.dcs-console-inside div { display: flex; align-items: flex-start; gap: 8px;
  margin: 0 0 6px; }
.dcs-console-inside div::before { content: ""; width: 6px; height: 6px;
  border-radius: 50%; background: #117f50; display: inline-block;
  flex: none; margin-top: 6px; }
/* The "What's inside" rows answer a hover too: the line deepens
   from muted to ink (the dot stays green) — the same quiet
   treatment as the nav rows. */
.dcs-console-inside div:hover { color: #030303; }
/* ---- status dot: the 8px green dot from the login status line,
   reusable anywhere a state is shown (sidebar status pill). ---- */
.dcs-dot { display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; background: #117f50; flex: none; }
.dcs-dot--warn { background: #e69344; }
.dcs-dot--muted { background: #696969; }
input[maxlength="6"] { font-family: monospace; font-size: 18px;
  letter-spacing: .35em; }
/* tertiary buttons render as plain text links — used only by the login
   theme switch (console header). */
div[data-testid="stButton"] > button[kind="tertiary"] {
  background: transparent; border: none; box-shadow: none;
  color: #117f50; font-size: 13px; padding: 0.25rem 0; min-height: 0; }
div[data-testid="stButton"] > button[kind="tertiary"]:hover {
  background: transparent; color: #117f50; text-decoration: underline; }
/* right-align the theme link inside the console header row */
div[data-testid="stHorizontalBlock"] div[data-testid="column"]:last-child
  div[data-testid="stButton"]:has(> button[kind="tertiary"]) {
  display: flex; justify-content: flex-end; }
/* ---- branded loader: the logo mark animating, Supabase-style ----
   The mark is the user's PNG (three bars + checkmark), layered as
   four <img> slices over ONE small base64 data URI (the 192px
   loader file, ~17KB) — an <img> per slice, because the earlier
   background-image carried on an inline custom property never
   painted live: two live checks saw the status text but never the
   mark, while <img> data URIs already paint everywhere else in
   this app (top bar, console header). The three bars rise one by
   one (scaleY from the bottom, staggered),
   then the checkmark draws itself left to right (clip-path wipe),
   then the whole mark breathes gently while the wait continues. A
   thin shimmer bar runs under the status text. All motion uses the
   Supabase 0.2s cubic-bezier(0.22, 1, 0.36, 1) timing; under
   prefers-reduced-motion the mark renders whole and still. */
.dcs-loader { text-align: center; padding: 2.5rem 1rem 2rem; }
.dcs-loader-mark { position: relative; margin: 0 auto 16px;
  animation: dcs-lm-breathe 1.8s ease-in-out 1.15s infinite alternate; }
.dcs-loader--large .dcs-loader-mark { width: 96px; height: 96px; }
.dcs-loader--compact { text-align: left; padding: 0.75rem 1rem;
  position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
  z-index: 1000001; pointer-events: none; max-width: 90vw;
  background: #ffffff; border: 1px solid #e8e8e8; border-radius: 12px;
  box-shadow: 0 8px 24px rgba(3, 3, 3, 0.16); }
.dcs-loader--compact .dcs-loader-row { display: flex; align-items: center;
  gap: 12px; }
.dcs-loader--compact .dcs-loader-mark { width: 40px; height: 40px;
  margin: 0; flex: none; }
.dcs-loader-mark > img { position: absolute; inset: 0; width: 100%;
  height: 100%; object-fit: fill; }
.dcs-lm-bar1 { clip-path: inset(0 63% 0 18%); transform-origin: 50% 100%;
  animation: dcs-lm-rise .45s cubic-bezier(.22,1,.36,1) 0s both; }
.dcs-lm-bar2 { clip-path: inset(0 44% 0 37%); transform-origin: 50% 100%;
  animation: dcs-lm-rise .45s cubic-bezier(.22,1,.36,1) .13s both; }
.dcs-lm-bar3 { clip-path: inset(0 23% 0 57%); transform-origin: 50% 100%;
  animation: dcs-lm-rise .45s cubic-bezier(.22,1,.36,1) .26s both; }
.dcs-lm-check { clip-path: inset(0 9% 0 54%);
  animation: dcs-lm-drawcheck .6s cubic-bezier(.22,1,.36,1) .45s both; }
@keyframes dcs-lm-rise { from { transform: scaleY(0); } to { transform: scaleY(1); } }
@keyframes dcs-lm-drawcheck { from { clip-path: inset(0 100% 0 54%); } to { clip-path: inset(0 9% 0 54%); } }
@keyframes dcs-lm-breathe { from { transform: scale(1); } to { transform: scale(1.035); } }
.dcs-loader-name { font-size: 17px; font-weight: 600; color: #030303; }
.dcs-loader-status { color: #696969; font-size: 13px; margin-top: 6px; }
.dcs-loader--compact .dcs-loader-status { margin-top: 0; }
.dcs-loader-shimmer { width: 200px; height: 3px; margin: 20px auto 0;
  background: #e8e8e8; border-radius: 2px; overflow: hidden; }
.dcs-loader--compact .dcs-loader-shimmer { width: 160px; margin: 12px 0 0; }
.dcs-loader-shimmer i { display: block; height: 100%; width: 40%;
  border-radius: 2px; background: linear-gradient(90deg, #118050, #117f50);
  animation: dcs-lm-slide 1.4s cubic-bezier(.22,1,.36,1) infinite; }
@keyframes dcs-lm-slide { 0% { transform: translateX(-110%); } 100% { transform: translateX(520%); } }
@media (prefers-reduced-motion: reduce) {
  .dcs-loader-mark, .dcs-loader-mark > img, .dcs-loader-shimmer i {
    animation: none !important; } }
/* ---- Supabase faithful rebuild (2026-11-07, page-by-page study) ----
   Primary buttons are pills (New / Connect / Run are fully rounded in
   the dashboard; secondary stays 6px). Dataframe headers are the
   dashboard's uppercase micro-labels (see the th rule above). The
   rules below are the rebuild's own pieces: the top bar row, the
   avatar menu rows, the nav active pill, the danger marker, the
   settings cards, the KPI icon box and the metric cards. */
.dcs-topbar-left { display: flex; align-items: center; gap: 8px;
  min-width: 0; flex-wrap: nowrap; }
.dcs-topbar-logo { width: 24px; height: 24px; flex: none; }
.dcs-topbar-brand { font-size: 17px; font-weight: 500; color: #030303;
  white-space: nowrap; flex: none; }
/* ---- top-bar breadcrumb never overlaps the search column: the
   spans are flex items with no min-width, so a long breadcrumb
   overflowed its column and sat on top of the search hint. They
   shrink and ellipsize instead; the brand never shrinks. ---- */
.dcs-topbar-left > span { min-width: 0; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.dcs-topbar-rule { border-top: 1px solid #e8e8e8; margin: 0.25rem 0 1rem; }
/* ---- Profile (Preferences) page: Supabase's two-column account
   page — a narrow sub-nav at the left (Back link, section rows)
   and bordered cards at the right. The sub-nav column carries a
   hairline right edge; the marker div is the page's own element,
   so the rule only fires on the Profile page. The sub-nav rows are
   anchor links to the section headings (the page is one stacked
   page, not separate pages — the links scroll to the card). The
   .stApp prefix out-specifies the sheet's own h3 / a rules. ---- */
div:has(> .dcs-profile-page) ~ div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child {
  border-right: 1px solid #e8e8e8; padding-right: 1rem; }
.stApp .dcs-profile-section { font-size: 15px; font-weight: 600;
  color: #030303; margin: 1.25rem 0 0.25rem; }
.stApp .dcs-profile-section-sub { font-size: 13px; color: #696969;
  margin-bottom: 0.5rem; }
.stApp .dcs-profile-subnav-link { display: block; padding: 0.35rem 0.75rem;
  border-radius: 6px; font-size: 13px; color: #030303; }
.stApp a.dcs-profile-subnav-link { text-decoration: none; }
.stApp a.dcs-profile-subnav-link:hover { background-color: #f8f8f8;
  color: #0e7e4e; text-decoration: none; }
.dcs-profile-subnav-link.dcs-profile-subnav-active {
  background-color: #f3f3f3; font-weight: 600; }
/* ---- avatar menu rows: bold email, micro section label, timezone row ---- */
.dcs-menu-email { font-size: 14px; font-weight: 700; color: #030303;
  padding: 0.35rem 0.75rem; overflow-wrap: anywhere; }
.dcs-menu-label { font-size: 11px; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase; color: #696969;
  padding: 0.35rem 0.75rem 0.1rem; }
.dcs-menu-row { display: flex; align-items: center;
  justify-content: space-between; gap: 0.75rem; font-size: 13px;
  color: #030303; padding: 0.35rem 0.75rem; }
.dcs-menu-value { color: #696969; font-size: 13px; }
/* ---- avatar menu theme radio: plain rows, not the tab-bar pills ----
   (the global radio rules style options as pills; inside the menu
   the theme rows are plain, with the native radio dot marking the
   selected one — the dashboard's System / Dark / Light rows). */
div[data-testid="stPopoverBody"] div[data-testid="stRadio"] div[role="radiogroup"] {
  gap: 0 !important; }
div[data-testid="stPopoverBody"] div[data-testid="stRadio"] div[role="radiogroup"] label {
  background-color: transparent !important; border: none !important;
  border-radius: 6px !important; padding: 0.35rem 0.75rem !important;
  color: #030303 !important; font-weight: 400 !important; }
div[data-testid="stPopoverBody"] div[data-testid="stRadio"] div[role="radiogroup"] label:hover {
  background-color: #f8f8f8 !important; }
div[data-testid="stPopoverBody"] div[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) {
  background-color: #f3f3f3 !important; font-weight: 600 !important; }
/* ---- sidebar nav: the active row is a DISABLED secondary button
   (you are already there) — it renders as the active pill: pale
   fill, semibold ink, dark left edge, full opacity. No other
   disabled sidebar button exists, so this rule only ever hits nav.
   Descendant selector + testid (no `>` and no `kind=` — Streamlit
   1.66.1 renders no `kind` attribute and nests the intermediate
   help-wrapper div, so both the old forms were dead). */
section[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"]:disabled {
  background-color: #f3f3f3; color: #030303; font-weight: 600;
  border-left: 2px solid #030303; opacity: 1; }
/* ---- danger zone: a .dcs-danger-zone marker colours every secondary
   button after it red (the Delete buttons). The marker only ever
   appears inside a danger zone, whose buttons are all destructive. */
div[data-testid="stVerticalBlock"] > div:has(.dcs-danger-zone) ~ div div[data-testid="stButton"] > button[kind="secondary"] {
  color: #b91c1c !important; border-color: #b91c1c !important; }
/* ---- headings / cards: colours in the stylesheet, never inline hex,
   so they read in both themes (the old inline #030303 / #696969
   rendered near-black on dark). */
.dcs-section-heading { font-size: 17px; font-weight: 500; color: #030303; }
.dcs-section-sub { font-size: 13px; color: #696969; }
.dcs-card-title { font-size: 16px; font-weight: 600; color: #030303;
  margin-bottom: 0.5rem; }
.dcs-card-footer { font-size: 13px; color: #696969; margin-top: 0.75rem; }
.dcs-settings-title { font-size: 16px; font-weight: 600; color: #030303; }
.dcs-settings-desc { font-size: 13px; color: #696969; margin-top: 0.25rem; }
/* ---- KPI icon box: the dashboard's 48px icon box at the tile's left ---- */
.dcs-kpi { display: flex; gap: 0.75rem; align-items: flex-start; }
.dcs-kpi-icon { width: 48px; height: 48px; flex: none; display: flex;
  align-items: center; justify-content: center; border: 1px solid #e8e8e8;
  border-radius: 8px; background-color: #ffffff; color: #117f50; }
.dcs-kpi-text { flex: 1; min-width: 0; }
.dcs-dot--danger { background: #b91c1c; }
/* ---- metric cards: label + warning/error dots, large count, bars ---- */
.dcs-metric-card { background-color: #ffffff; border: 1px solid #e8e8e8;
  border-radius: 12px; padding: 0.9rem 1rem; margin-bottom: 1rem; }
.dcs-metric-card:hover { border-color: #d0d0d0; }
.dcs-metric-head { display: flex; align-items: center;
  justify-content: space-between; gap: 0.75rem; }
.dcs-metric-dots { display: flex; gap: 0.75rem; align-items: center; }
.dcs-metric-count { font-size: 11px; font-weight: 600;
  letter-spacing: 0.06em; color: #696969; display: inline-flex;
  align-items: center; gap: 4px; }
.dcs-metric-value { font-size: 28px; font-weight: 500; color: #030303;
  font-family: ui-monospace, "SF Mono", Menlo, monospace; margin-top: 0.25rem; }
.dcs-metric-bars { display: flex; align-items: flex-end; gap: 2px;
  height: 40px; margin-top: 0.75rem; }
.dcs-metric-bars i { flex: 1; border-radius: 1px; min-height: 2px;
  display: block; }
.dcs-bar-ok { background: #117f50; }
.dcs-bar-warn { background: #e69344; }
.dcs-bar-error { background: #b91c1c; }
</style>"""


# ---------------------------------------------------------------------------
# Dark stylesheet. Same structure, selectors and class names as the light
# one above, with DARK_TOKENS substituted — every rule below is the dark
# twin of a light rule, so switching themes never moves layout, only
# colour. Notes on the substitutions:
#   * primary fill deepens to #006338 (rest) and lightens toward #007243
#     on hover — the reverse direction of light, where the fill darkens
#     toward #007243 — because a dark fill cannot darken further and
#     stay readable; white on #006338 is 7.39:1.
#   * links / icons brighten to #4acd8b (8.39:1 on the surface).
#   * the focus-ring gap is the dark surface #1b1d1c, not #fdfdfd, so
#     the 2px gap still reads; the halo stays #30ba798c in both themes.
#   * code blocks stay panel-dark (#232625 / #262928), never pure black.
#   * Streamlit's native dropdown menus render in a baseweb portal, so
#     the dark menu rules at the end are best-effort — the native theme
#     in .streamlit/config.toml stays light (first-paint base only).
# ---------------------------------------------------------------------------
DARK_CSS = """<style>
/* ---- page: near-black green-grey everywhere ---- */
.stApp { background-color: #1b1d1c; color: #edefee; }
.stApp p, .stApp li, .stApp span { color: #edefee; }
.stApp { font-size: 14px; }
header[data-testid="stHeader"] { background-color: #1b1d1c; }
/* ---- typography: H1 28px medium, sections 16-18px, body 13-14px ---- */
.stApp h1 { font-size: 28px; font-weight: 500; color: #edefee;
  line-height: 1.2; margin-bottom: 0.25rem; }
.stApp h2 { font-size: 18px; font-weight: 500; color: #edefee;
  margin-top: 1.25rem; margin-bottom: 0.5rem; }
.stApp h3 { font-size: 16px; font-weight: 600; color: #edefee;
  margin-top: 1rem; margin-bottom: 0.4rem; }
.stApp [data-testid="stCaptionContainer"], .stApp small {
  color: #989a99; }
/* ---- tiny uppercase section labels: 10-11px, letterspaced, muted ---- */
.dcs-micro-label, .dcs-section-label {
  font-size: 11px; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase; color: #989a99; }
/* ---- cards: dark panel, 1px hairline border, 10-12px radius, flat ---- */
.dcs-card { background-color: #232625; border: 1px solid #2e2e2e;
  border-radius: 12px; padding: 1rem 1.25rem; margin-bottom: 1rem; }
/* Cards and expanders answer the hover: the hairline lightens one
   step (to the dark checkbox-border token #4a4d4c) — no shadow, no
   lift, no colour change, just the border, Supabase-quiet. */
.dcs-card:hover { border-color: #4a4d4c; }
div[data-testid="stExpander"] { background-color: #232625;
  border: 1px solid #2e2e2e; border-radius: 12px; }
div[data-testid="stExpander"]:hover { border-color: #4a4d4c; }
/* ---- spacing: consistent gaps between sections ---- */
div[data-testid="stVerticalBlock"] > div { gap: 0.75rem; }
/* Settings cards sit closer together in dark mode too (same rule as
   the light stylesheet — the gap is not a colour). */
section[data-testid="stMain"] div[data-testid="stVerticalBlock"] {
  gap: 0.75rem; }
/* ---- buttons: dark panel, bright text (round 2, 2026-11-07) ----
   The [kind="…"] rules that were here are gone: Streamlit 1.66 puts
   no `kind` attribute on the rendered <button> (emotion filters the
   prop), so they never matched — dead rules that only looked like a
   fix. The live rules are the descendant selectors below. */
/* ---- button colours, descendant selectors (round 2, 2026-11-07) ----
   The first fix-up anchored on
   `div[data-testid="stButton"] > button[data-testid="stBaseButton-…"]`
   and "proved" it with a cascade simulation — but it matched NOTHING
   live. The shipped Streamlit 1.66.1 frontend nests an intermediate
   element between the stButton wrapper div and the <button> (the
   Button component renders Tooltip → intermediate node → BaseButton),
   so the `>` child combinator never matches; the download-button
   component nests differently, which is why its `>` rule was the only
   one that worked — and why the one plain st.button without icon/help
   ("Clean my data") rendered the dark gradient while every icon/help
   button stayed a white pill. These rules use DESCENDANT selectors
   and never depend on the button's own testid, so they match whatever
   the nesting is. Specificity (0,1,2)+ beats mobile_css's blanket
   `.stButton > button` (0,1,1), which is injected after this sheet —
   including when that sheet is a theme behind. */
div[data-testid="stButton"] button,
div[data-testid="stDownloadButton"] button,
div[data-testid="stFormSubmitButton"] button,
div[data-testid="stFileUploader"] button {
  background-color: #232625 !important; color: #edefee !important;
  border: 1px solid #363636 !important; border-radius: 6px;
  font-weight: 500; }
div[data-testid="stButton"] button *,
div[data-testid="stDownloadButton"] button *,
div[data-testid="stFormSubmitButton"] button *,
div[data-testid="stFileUploader"] button * {
  color: #edefee !important; }
div[data-testid="stButton"] button:hover,
div[data-testid="stDownloadButton"] button:hover,
div[data-testid="stFormSubmitButton"] button:hover,
div[data-testid="stFileUploader"] button:hover {
  background-color: #2a2d2c !important; color: #edefee !important;
  border-color: #363636 !important; }
/* Primary buttons: the green pill, white text — more specific than the
   blanket above, so it wins for primary buttons. */
div[data-testid="stButton"] button[data-testid="stBaseButton-primary"] {
  background-color: #006338 !important;
  background: linear-gradient(180deg, #007243 0%, #006338 100%) !important;
  color: #ffffff !important; border: 1px solid #006338 !important;
  border-radius: 999px; font-weight: 500; }
div[data-testid="stButton"] button[data-testid="stBaseButton-primary"] * {
  color: #ffffff !important; }
/* Sidebar nav rows + the active (disabled) pill, same anchoring.
   Full-width left-aligned rows (Load sheet, Try the messy sample,
   Quick jump picks) — Supabase's sidebar actions are rows, not
   centred pills. The avatar trigger is a stPopoverButton, not an
   stButton, so it is untouched by this rule. */
section[data-testid="stSidebar"] div[data-testid="stButton"] button {
  width: 100%; justify-content: flex-start;
  background-color: #232625 !important; color: #edefee !important;
  border: 1px solid #363636 !important; }
section[data-testid="stSidebar"] div[data-testid="stButton"] button * {
  color: #edefee !important; }
section[data-testid="stSidebar"] div[data-testid="stButton"] button:disabled {
  background-color: #343837 !important; color: #edefee !important;
  border: 1px solid #363636 !important; opacity: 1 !important;
  border-left: 2px solid #edefee !important; font-weight: 600 !important; }
section[data-testid="stSidebar"] div[data-testid="stButton"] button:disabled * {
  color: #edefee !important; }
/* Danger-zone buttons: red text + border on the dark secondary panel.
   The `> div:has(.dcs-danger-zone) ~ div` head is kept: the marker div
   IS a direct child of the vertical block, so that part is true —
   only the tail was broken (it used the `>` + testid chain). */
div[data-testid="stVerticalBlock"] > div:has(.dcs-danger-zone) ~ div div[data-testid="stButton"] button {
  color: #ff6369 !important; border-color: #ff6369 !important; }
div[data-testid="stVerticalBlock"] > div:has(.dcs-danger-zone) ~ div div[data-testid="stButton"] button * {
  color: #ff6369 !important; }
/* ---- inputs: dark panel, 6px radius, hairline border ---- */
.stApp input, .stApp textarea, .stApp select {
  background-color: #232625; color: #edefee;
  border-color: #2e2e2e; border-radius: 6px; }
.stApp input:hover, .stApp textarea:hover, .stApp select:hover {
  border-color: #4a4d4c; }
.stApp label { color: #edefee; }
/* ---- disabled inputs (Profile's read-only Primary email +
   Username): Streamlit's native disabled styling renders the text
   in a very dark grey on the dark panel, near-unreadable live.
   Pin the text bright and the panel one step lighter than the
   card, so the field still reads as disabled but the value is
   legible. Dark theme only — the light Profile passes and is
   untouched. ---- */
.stApp input:disabled, .stApp textarea:disabled, .stApp select:disabled {
  color: #edefee !important; background-color: #2a2d2c !important;
  border-color: #363636 !important; opacity: 1 !important; }
div[data-testid="stTextInput"] input:disabled {
  color: #edefee !important; background-color: #2a2d2c !important; }
/* ---- checkboxes: hairline box border, bright green check ---- */
.stApp input[type="checkbox"] { accent-color: #4acd8b; }
div[data-testid="stCheckbox"] div[data-baseweb="checkbox"] span {
  border-color: #4a4d4c; }
/* ---- sidebar: near-black, hairline edge, nav rows as pills ---- */
section[data-testid="stSidebar"] { background-color: #1b1d1c;
  border-right: 1px solid #2e2e2e; }
section[data-testid="stSidebar"] * { color: #edefee; }
section[data-testid="stSidebar"] a { color: #4acd8b; }
.dcs-nav-row { display: block; padding: 0.35rem 0.75rem;
  border-radius: 6px; font-size: 13px; color: #edefee;
  border-left: 2px solid transparent; margin-bottom: 2px; }
.dcs-nav-row:hover { background-color: #262928; color: #4acd8b; }
.dcs-nav-row.dcs-nav-active { background-color: #2a2d2c;
  font-weight: 600; color: #edefee; border-left: 2px solid #edefee; }
/* ---- sidebar collapse control: the chevron that hides / shows the
   sidebar — muted by default, quiet wash on hover, same 6px radius
   as everything (see the light stylesheet for the selector note). */
div[data-testid="collapsedControl"],
section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"],
section[data-testid="stSidebar"] button[kind="header"] {
  color: #989a99; border-radius: 6px; }
div[data-testid="collapsedControl"]:hover,
section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"]:hover,
section[data-testid="stSidebar"] button[kind="header"]:hover {
  background-color: #262928; color: #edefee; }
/* ---- sidebar avatar: same green circle in dark mode ---- */
div[data-testid="stPopover"] { margin-bottom: 0.75rem; }
div[data-testid="stPopover"] button[data-testid="stPopoverButton"] {
  width: 44px !important; height: 44px !important;
  min-width: 44px !important; max-width: 44px !important;
  border-radius: 50% !important;
  background-color: #117f50 !important; background: #117f50 !important;
  color: #ffffff !important; border: 1px solid #117f50 !important;
  font-size: 18px !important; font-weight: 600 !important;
  padding: 0 !important; justify-content: center !important;
  align-items: center !important; }
div[data-testid="stPopover"] button[data-testid="stPopoverButton"]:hover {
  background-color: #0e7d4e !important; background: #0e7d4e !important; }
div[data-testid="stPopover"] button[data-testid="stPopoverButton"] svg {
  display: none !important; }
/* ---- avatar menu (popover body): dark card, hairline border ---- */
div[data-testid="stPopoverBody"] { background-color: #232625;
  border: 1px solid #2e2e2e; border-radius: 12px; }
/* Avatar menu rows: the Profile / theme / Log out buttons inside the
   popover are menu rows, not pills — full-width, left-aligned, no
   border, quiet wash on hover (see the light stylesheet). */
div[data-testid="stPopoverBody"] div[data-testid="stButton"] button {
  width: 100% !important; justify-content: flex-start !important;
  background: transparent !important; background-color: transparent !important;
  border: none !important; box-shadow: none !important;
  border-radius: 6px !important; padding: 0.35rem 0.75rem !important;
  font-weight: 400 !important; color: #edefee !important; }
div[data-testid="stPopoverBody"] div[data-testid="stButton"] button:hover {
  background-color: #262928 !important; color: #edefee !important; }
/* Menu divider: one hairline between the email, the actions and Log out. */
.dcs-menu-divider { border-top: 1px solid #2e2e2e; margin: 0.35rem 0; }
/* The email caption inside the menu is secondary body text: the
   #bcbdbc body token (not the fainter #989a99 micro-label grey), so
   the address stays readable on the dark card. */
div[data-testid="stPopoverBody"] [data-testid="stCaptionContainer"] {
  color: #bcbdbc; }
/* ---- links: brightened green, sparingly ---- */
.stApp a { color: #4acd8b; }
.stApp a:hover { color: #3ecf8e; }
/* ---- top bar: 48px, near-black, hairline bottom border ---- */
.dcs-topbar { height: 48px; display: flex; align-items: center;
  gap: 0.75rem; background-color: #1b1d1c;
  border-bottom: 1px solid #2e2e2e; margin-bottom: 1rem; }
.dcs-topbar .dcs-topbar-title { font-size: 17px; font-weight: 500;
  color: #edefee; }
.dcs-topbar .dcs-topbar-crumb { font-size: 13px; color: #989a99; }
/* ---- KPI metric values + labels: bright text, never faint grey ---- */
div[data-testid="stMetricValue"], div[data-testid="stMetricValue"] * {
  color: #edefee !important; }
div[data-testid="stMetricLabel"], div[data-testid="stMetricLabel"] * {
  color: #989a99 !important; }
/* ---- KPI tiles: dark panel icon box + micro-label + value ---- */
.dcs-kpi { background-color: #232625; border: 1px solid #2e2e2e;
  border-radius: 12px; padding: 0.9rem 1rem; }
.dcs-kpi:hover { border-color: #4a4d4c; }
.dcs-kpi .dcs-kpi-label { font-size: 11px; font-weight: 600;
  letter-spacing: 0.08em; text-transform: uppercase; color: #989a99; }
.dcs-kpi .dcs-kpi-value { font-size: 20px; font-weight: 500;
  color: #edefee; font-family: ui-monospace, "SF Mono", Menlo, monospace; }
.dcs-kpi .dcs-kpi-sub { font-size: 13px; color: #989a99; }
/* Strip label: dark twin of the light rule above. */
.dcs-strip-label { font-size: 11px; font-weight: 600;
  letter-spacing: 0.08em; text-transform: uppercase; color: #989a99;
  margin-bottom: 0.5rem; }
/* ---- file-uploader dropzone + uploaded-file chips: bright on dark ----
   The dropzone element is a <section>, NOT a <div> (Streamlit 1.66.1
   renders it as R = a styled `section` with data-testid
   "stFileUploaderDropzone" — verified in the FileUploader chunk),
   so a `div[...]` selector never matched and the dark background
   rule was dead: the box stayed Streamlit's light secondaryBg
   (white) with near-white text on it. The selector below carries
   no element qualifier, and !important beats the emotion
   backgroundColor. */
div[data-testid="stFileUploader"], div[data-testid="stFileUploader"] * {
  color: #edefee !important; }
[data-testid="stFileUploaderDropzone"] {
  background-color: #232625 !important; border-color: #2e2e2e !important; }
[data-testid="stFileUploaderDropzone"]:hover { border-color: #4a4d4c !important; }
/* ---- uploader format line wraps instead of truncating: the
   instructions element ("1GB per file • CSV, XLSX, XLS, JSON,
   PARQUET") is one long line in the 260px sidebar, so it was cut
   off at the right edge ("…JS…"). ---- */
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"],
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] * {
  white-space: normal !important; overflow: visible !important;
  text-overflow: clip !important; }
/* ---- tooltips: Supabase's dark rounded pill, white text, in both
   themes — Streamlit's native tooltip is a light box by default.
   The content lives in a floating portal, so the rule is
   document-wide (no sidebar scoping). The pill is dark in both
   themes by design, but each theme uses its OWN near-black so no
   dark token leaks into the light sheet (light ink in the
   light sheet, the dark surface here). No shortcut chips: the
   app has no G-then-X navigation shortcuts, so none are shown. ---- */
div[data-testid="stTooltipContent"] {
  background-color: #1b1d1c !important; color: #ffffff !important;
  border-radius: 8px !important; padding: 6px 10px !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25) !important; }
div[data-testid="stTooltipContent"] * { color: #ffffff !important; }
/* ---- info / success / warning / error boxes: dark panel, bright text ---- */
div[data-testid="stAlert"] { background-color: #232625;
  border-color: #2e2e2e; }
div[data-testid="stAlert"], div[data-testid="stAlert"] * {
  color: #edefee !important; }
div[data-testid="stAlert"] a { color: #4acd8b !important; }
/* ---- info boxes ONLY: no sky-blue ---- */
div[data-testid="stAlert"]:has(div[data-testid="stAlertContentInfo"]) div[data-testid="stAlertContainer"] {
  background-color: #232625 !important; border: 1px solid #2e2e2e !important;
  border-radius: 12px !important; }
div[data-testid="stAlert"]:has(div[data-testid="stAlertContentInfo"]) div[data-testid="stAlertContentInfo"] {
  border: none !important; background-color: transparent !important; }
/* ---- pills: fully rounded, uppercase ~10px, letterspaced ---- */
.dcs-pill { display: inline-block; font-size: 10px; font-weight: 600;
  letter-spacing: 0.08em; text-transform: uppercase;
  border-radius: 999px; padding: 0.15rem 0.6rem; line-height: 1.6; }
.dcs-pill-mint { background-color: #123527; color: #4acd8b; }
.dcs-pill-amber { background-color: #2a2118; color: #f3ba63;
  border: 1px solid #8a6a2f; }
.dcs-pill-green { background-color: #006338; color: #ffffff; }
.dcs-pill-grey { background-color: #2a2d2c; color: #989a99; }
.dcs-pill-danger { background-color: #2b1e1e; color: #ff6369;
  border: 1px solid #ff6369; }
/* ---- code: dark panels with hairline border, never pure black ---- */
.stApp code, .stApp pre { background-color: #262928; color: #edefee;
  font-family: ui-monospace, "SF Mono", Menlo, monospace; }
div[data-testid="stCodeBlock"] { background-color: #232625;
  border: 1px solid #2e2e2e; border-radius: 12px; }
div[data-testid="stCodeBlock"] pre { background-color: #232625; }
/* ---- numbers and code: monospace ---- */
.dcs-mono { font-family: ui-monospace, "SF Mono", Menlo, monospace; }
/* ---- column headers show their type (name text, price numeric) ---- */
.dcs-coltype { font-size: 13px; color: #edefee; }
.dcs-coltype .dcs-coltype-kind { font-size: 12px; color: #989a99;
  font-family: ui-monospace, "SF Mono", Menlo, monospace; }
/* ---- storage usage: one thin hairline, bright green fill, muted label ---- */
.dcs-storage { height: 4px; background-color: #2e2e2e;
  border-radius: 999px; overflow: hidden; }
.dcs-storage > div { height: 100%; background-color: #4acd8b;
  border-radius: 999px; }
/* ---- spinner: bright green ---- */
div[data-testid="stSpinner"] { color: #4acd8b; }
div[data-testid="stSpinner"] > div { border-top-color: #4acd8b !important; }
/* ---- section switcher (radio styled as a tab bar) ---- */
div[data-testid="stRadio"] div[role="radiogroup"] {
  gap: 0.35rem !important; }
div[data-testid="stRadio"] div[role="radiogroup"] label {
  background-color: #232625 !important;
  border: 1px solid #2e2e2e !important;
  border-radius: 6px !important;
  padding: 0.35rem 0.9rem !important;
  color: #edefee !important; }
div[data-testid="stRadio"] div[role="radiogroup"] label:hover {
  background-color: #262928 !important; }
div[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) {
  background-color: #2a2d2c !important;
  border-color: #2e2e2e !important;
  color: #edefee !important; font-weight: 600 !important; }
/* ---- dense spreadsheet-like tables: dark panel, hairline gridlines ---- */
div[data-testid="stDataFrame"], div[data-testid="stTable"] {
  background-color: #232625; border: 1px solid #2e2e2e;
  border-radius: 12px; }
div[data-testid="stDataFrame"] table, div[data-testid="stTable"] table {
  background-color: #232625; }
div[data-testid="stDataFrame"] th, div[data-testid="stTable"] th {
  background-color: #262928; color: #989a99; font-weight: 600;
  border-bottom: 1px solid #2e2e2e; font-size: 11px;
  text-transform: uppercase; letter-spacing: 0.08em; }
div[data-testid="stDataFrame"] td, div[data-testid="stTable"] td {
  background-color: #232625; color: #edefee;
  border-bottom: 1px solid #2e2e2e; font-size: 13px; }
/* ---- motion, honestly measured: colour-only 0.2s ease-out ----
   Every hover above is a colour/border change only (no scale, no
   shadow, no movement) and every one of those elements carries this
   transition, so the hover never snaps. */
.stApp .stButton button, .stApp a, .dcs-nav-row,
div[data-testid="stRadio"] div[role="radiogroup"] label,
.stApp input, .stApp textarea, .stApp select,
.dcs-card, .dcs-kpi, .dcs-console-inside div,
div[data-testid="stDownloadButton"] button,
div[data-testid="stExpander"],
[data-testid="stFileUploaderDropzone"],
div[data-testid="stPopoverBody"] div[data-testid="stButton"] button,
div[data-testid="stPopover"] button[data-testid="stPopoverButton"],
div[data-testid="collapsedControl"],
section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"],
section[data-testid="stSidebar"] button[kind="header"],
div[data-baseweb="menu"] li[role="option"] {
  transition: background-color 0.2s cubic-bezier(0.22, 1, 0.36, 1),
    border-color 0.2s cubic-bezier(0.22, 1, 0.36, 1),
    color 0.2s cubic-bezier(0.22, 1, 0.36, 1); }
/* ---- focus: one shared ring — 2px dark gap + 4px translucent green halo ---- */
.stApp .stButton button:focus-visible,
div[data-testid="stDownloadButton"] button:focus-visible,
div[data-testid="stPopover"] button[data-testid="stPopoverButton"]:focus-visible,
div[data-testid="collapsedControl"] button:focus-visible,
section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"]:focus-visible,
.stApp a:focus-visible,
div[data-testid="stRadio"] div[role="radiogroup"] label:focus-within {
  outline: none;
  box-shadow: 0 0 0 2px #1b1d1c, 0 0 0 6px #30ba798c; }
.stApp input:focus, .stApp textarea:focus, .stApp select:focus {
  outline: none;
  box-shadow: 0 0 0 2px #1b1d1c, 0 0 0 6px #30ba798c; }
/* ---- native dropdown menus (baseweb portal): best-effort dark ---- */
div[data-baseweb="popover"] { background-color: #232625; }
div[data-baseweb="menu"] li[role="option"] { color: #edefee; }
div[data-baseweb="menu"] li[role="option"]:hover {
  background-color: #2a2d2c; }
/* ---- empty state: centred, calm, guided ---- */
.dcs-empty { text-align: center; padding: 2.5rem 1rem;
  background-color: #232625; border: 1px solid #2e2e2e;
  border-radius: 12px; }
.dcs-empty h3 { font-size: 17px; font-weight: 500; color: #edefee; }
.dcs-empty p { font-size: 14px; color: #989a99; }
/* ---- footer ---- */
.dcs-footer { color: #989a99; font-size: 0.85rem; text-align: center;
  padding: 1.5rem 0 0.5rem; }
/* ---- login console layout (variant C): dark twin of the light rules
   above — same layout, dark tokens only. ---- */
.dcs-console-head { display: flex; align-items: center; gap: 12px; }
.dcs-console-head img { width: 40px; height: 40px; }
.dcs-console-head h1 { font-size: 22px; font-weight: 500; margin: 0; }
.dcs-console-h2 { font-size: 18px; font-weight: 500; margin: 0 0 16px; }
.dcs-code-email { color: #4acd8b; font-weight: 600; }
.dcs-console-status { font-size: 13px; color: #989a99; display: flex;
  align-items: center; gap: 6px; margin-top: 0.75rem; }
.dcs-console-status::before { content: ""; width: 8px; height: 8px;
  border-radius: 50%; background: #4acd8b; display: inline-block;
  flex: none; }
/* "What's inside" — dark twin of the light rules above: same layout,
   dark tokens only (hairline #2e2e2e, muted #989a99, dot #4acd8b). */
.dcs-console-inside { border-top: 1px solid #2e2e2e; margin-top: 1.5rem;
  padding-top: 1rem; font-size: 13px; color: #989a99; }
.dcs-console-inside div { display: flex; align-items: flex-start; gap: 8px;
  margin: 0 0 6px; }
.dcs-console-inside div::before { content: ""; width: 6px; height: 6px;
  border-radius: 50%; background: #4acd8b; display: inline-block;
  flex: none; margin-top: 6px; }
/* The "What's inside" rows answer a hover too: the line deepens
   from muted to ink (the dot stays green) — the same quiet
   treatment as the nav rows. */
.dcs-console-inside div:hover { color: #edefee; }
/* ---- status dot: the 8px green dot from the login status line,
   reusable anywhere a state is shown (sidebar status pill). ---- */
.dcs-dot { display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; background: #4acd8b; flex: none; }
.dcs-dot--warn { background: #f3ba63; }
.dcs-dot--muted { background: #989a99; }
input[maxlength="6"] { font-family: monospace; font-size: 18px;
  letter-spacing: .35em; }
div[data-testid="stButton"] button[data-testid="stBaseButton-tertiary"] {
  background: transparent !important; border: none !important;
  box-shadow: none !important;
  color: #4acd8b !important; font-size: 13px; padding: 0.25rem 0;
  min-height: 0; }
div[data-testid="stButton"] button[data-testid="stBaseButton-tertiary"]:hover {
  background: transparent !important; color: #4acd8b !important;
  text-decoration: underline; }
div[data-testid="stHorizontalBlock"] div[data-testid="column"]:last-child
  div[data-testid="stButton"]:has(button[data-testid="stBaseButton-tertiary"]) {
  display: flex; justify-content: flex-end; }
/* ---- branded loader: dark twin of the light rules above — same
   mark, same keyframes, same timing; only the text/shimmer colours
   change (muted #989a99, name #edefee, track #2e2e2e, shimmer
   gradient brightened to the dark link green #4acd8b). */
.dcs-loader { text-align: center; padding: 2.5rem 1rem 2rem; }
.dcs-loader-mark { position: relative; margin: 0 auto 16px;
  animation: dcs-lm-breathe 1.8s ease-in-out 1.15s infinite alternate; }
.dcs-loader--large .dcs-loader-mark { width: 96px; height: 96px; }
.dcs-loader--compact { text-align: left; padding: 0.75rem 1rem;
  position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
  z-index: 1000001; pointer-events: none; max-width: 90vw;
  background: #232625; border: 1px solid #363636; border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45); }
.dcs-loader--compact .dcs-loader-row { display: flex; align-items: center;
  gap: 12px; }
.dcs-loader--compact .dcs-loader-mark { width: 40px; height: 40px;
  margin: 0; flex: none; }
.dcs-loader-mark > img { position: absolute; inset: 0; width: 100%;
  height: 100%; object-fit: fill; }
.dcs-lm-bar1 { clip-path: inset(0 63% 0 18%); transform-origin: 50% 100%;
  animation: dcs-lm-rise .45s cubic-bezier(.22,1,.36,1) 0s both; }
.dcs-lm-bar2 { clip-path: inset(0 44% 0 37%); transform-origin: 50% 100%;
  animation: dcs-lm-rise .45s cubic-bezier(.22,1,.36,1) .13s both; }
.dcs-lm-bar3 { clip-path: inset(0 23% 0 57%); transform-origin: 50% 100%;
  animation: dcs-lm-rise .45s cubic-bezier(.22,1,.36,1) .26s both; }
.dcs-lm-check { clip-path: inset(0 9% 0 54%);
  animation: dcs-lm-drawcheck .6s cubic-bezier(.22,1,.36,1) .45s both; }
@keyframes dcs-lm-rise { from { transform: scaleY(0); } to { transform: scaleY(1); } }
@keyframes dcs-lm-drawcheck { from { clip-path: inset(0 100% 0 54%); } to { clip-path: inset(0 9% 0 54%); } }
@keyframes dcs-lm-breathe { from { transform: scale(1); } to { transform: scale(1.035); } }
.dcs-loader-name { font-size: 17px; font-weight: 600; color: #edefee; }
.dcs-loader-status { color: #989a99; font-size: 13px; margin-top: 6px; }
.dcs-loader--compact .dcs-loader-status { margin-top: 0; }
.dcs-loader-shimmer { width: 200px; height: 3px; margin: 20px auto 0;
  background: #2e2e2e; border-radius: 2px; overflow: hidden; }
.dcs-loader--compact .dcs-loader-shimmer { width: 160px; margin: 12px 0 0; }
.dcs-loader-shimmer i { display: block; height: 100%; width: 40%;
  border-radius: 2px; background: linear-gradient(90deg, #3ecf8e, #4acd8b);
  animation: dcs-lm-slide 1.4s cubic-bezier(.22,1,.36,1) infinite; }
@keyframes dcs-lm-slide { 0% { transform: translateX(-110%); } 100% { transform: translateX(520%); } }
@media (prefers-reduced-motion: reduce) {
  .dcs-loader-mark, .dcs-loader-mark > img, .dcs-loader-shimmer i {
    animation: none !important; } }
/* ---- Supabase faithful rebuild (2026-11-07, page-by-page study) ----
   Dark twin of the light rebuild block above: same structure, dark
   tokens only. Primary buttons are pills; dataframe headers are the
   dashboard's uppercase micro-labels; the top bar, avatar menu rows,
   nav active pill, danger marker, settings cards, KPI icon box and
   metric cards follow the dark tokens. */
.dcs-topbar-left { display: flex; align-items: center; gap: 8px;
  min-width: 0; flex-wrap: nowrap; }
.dcs-topbar-logo { width: 24px; height: 24px; flex: none; }
.dcs-topbar-brand { font-size: 17px; font-weight: 500; color: #edefee;
  white-space: nowrap; flex: none; }
/* ---- top-bar breadcrumb never overlaps the search column: the
   spans are flex items with no min-width, so a long breadcrumb
   overflowed its column and sat on top of the search hint. They
   shrink and ellipsize instead; the brand never shrinks. ---- */
.dcs-topbar-left > span { min-width: 0; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.dcs-topbar-rule { border-top: 1px solid #2e2e2e; margin: 0.25rem 0 1rem; }
/* ---- Profile (Preferences) page: Supabase's two-column account
   page — a narrow sub-nav at the left (Back link, section rows)
   and bordered cards at the right. The sub-nav column carries a
   hairline right edge; the marker div is the page's own element,
   so the rule only fires on the Profile page. The sub-nav rows are
   anchor links to the section headings (the page is one stacked
   page, not separate pages — the links scroll to the card). The
   .stApp prefix out-specifies the sheet's own h3 / a rules. ---- */
div:has(> .dcs-profile-page) ~ div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child {
  border-right: 1px solid #2e2e2e; padding-right: 1rem; }
.stApp .dcs-profile-section { font-size: 15px; font-weight: 600;
  color: #edefee; margin: 1.25rem 0 0.25rem; }
.stApp .dcs-profile-section-sub { font-size: 13px; color: #989a99;
  margin-bottom: 0.5rem; }
.stApp .dcs-profile-subnav-link { display: block; padding: 0.35rem 0.75rem;
  border-radius: 6px; font-size: 13px; color: #edefee; }
.stApp a.dcs-profile-subnav-link { text-decoration: none; }
.stApp a.dcs-profile-subnav-link:hover { background-color: #2a2d2c;
  color: #4acd8b; text-decoration: none; }
.dcs-profile-subnav-link.dcs-profile-subnav-active {
  background-color: #2a2d2c; font-weight: 600; }
/* ---- avatar menu rows: bold email, micro section label, timezone row ---- */
.dcs-menu-email { font-size: 14px; font-weight: 700; color: #edefee;
  padding: 0.35rem 0.75rem; overflow-wrap: anywhere; }
.dcs-menu-label { font-size: 11px; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase; color: #989a99;
  padding: 0.35rem 0.75rem 0.1rem; }
.dcs-menu-row { display: flex; align-items: center;
  justify-content: space-between; gap: 0.75rem; font-size: 13px;
  color: #edefee; padding: 0.35rem 0.75rem; }
.dcs-menu-value { color: #989a99; font-size: 13px; }
/* ---- avatar menu theme radio: plain rows, not the tab-bar pills ---- */
div[data-testid="stPopoverBody"] div[data-testid="stRadio"] div[role="radiogroup"] {
  gap: 0 !important; }
div[data-testid="stPopoverBody"] div[data-testid="stRadio"] div[role="radiogroup"] label {
  background-color: transparent !important; border: none !important;
  border-radius: 6px !important; padding: 0.35rem 0.75rem !important;
  color: #edefee !important; font-weight: 400 !important; }
div[data-testid="stPopoverBody"] div[data-testid="stRadio"] div[role="radiogroup"] label:hover {
  background-color: #262928 !important; }
div[data-testid="stPopoverBody"] div[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) {
  background-color: #2a2d2c !important; font-weight: 600 !important; }
/* ---- headings / cards: colours in the stylesheet, never inline hex ---- */
.dcs-section-heading { font-size: 17px; font-weight: 500; color: #edefee; }
.dcs-section-sub { font-size: 13px; color: #989a99; }
.dcs-card-title { font-size: 16px; font-weight: 600; color: #edefee;
  margin-bottom: 0.5rem; }
.dcs-card-footer { font-size: 13px; color: #989a99; margin-top: 0.75rem; }
.dcs-settings-title { font-size: 16px; font-weight: 600; color: #edefee; }
.dcs-settings-desc { font-size: 13px; color: #989a99; margin-top: 0.25rem; }
/* ---- KPI icon box: the dashboard's 48px icon box at the tile's left ---- */
.dcs-kpi { display: flex; gap: 0.75rem; align-items: flex-start; }
.dcs-kpi-icon { width: 48px; height: 48px; flex: none; display: flex;
  align-items: center; justify-content: center; border: 1px solid #2e2e2e;
  border-radius: 8px; background-color: #232625; color: #4acd8b; }
.dcs-kpi-text { flex: 1; min-width: 0; }
.dcs-dot--danger { background: #ff6369; }
/* ---- metric cards: label + warning/error dots, large count, bars ---- */
.dcs-metric-card { background-color: #232625; border: 1px solid #2e2e2e;
  border-radius: 12px; padding: 0.9rem 1rem; margin-bottom: 1rem; }
.dcs-metric-card:hover { border-color: #4a4d4c; }
.dcs-metric-head { display: flex; align-items: center;
  justify-content: space-between; gap: 0.75rem; }
.dcs-metric-dots { display: flex; gap: 0.75rem; align-items: center; }
.dcs-metric-count { font-size: 11px; font-weight: 600;
  letter-spacing: 0.06em; color: #989a99; display: inline-flex;
  align-items: center; gap: 4px; }
.dcs-metric-value { font-size: 28px; font-weight: 500; color: #edefee;
  font-family: ui-monospace, "SF Mono", Menlo, monospace; margin-top: 0.25rem; }
.dcs-metric-bars { display: flex; align-items: flex-end; gap: 2px;
  height: 40px; margin-top: 0.75rem; }
.dcs-metric-bars i { flex: 1; border-radius: 1px; min-height: 2px;
  display: block; }
.dcs-bar-ok { background: #4acd8b; }
.dcs-bar-warn { background: #f3ba63; }
.dcs-bar-error { background: #ff6369; }
</style>"""


def theme_css(theme) -> str:
    """Return the full stylesheet for ``theme`` (``"light"`` or
    ``"dark"``). Anything else — None, a legacy name, a typo — falls
    back to the light stylesheet, so a bad stored value can never
    strand the app without styling. The light return is exactly
    ``DESIGN_SYSTEM_CSS`` (pixel-identical tokens, spacing and radii);
    the dark return is exactly ``DARK_CSS``."""
    return DARK_CSS if normalize_theme(theme) == "dark" else DESIGN_SYSTEM_CSS


def inject_design_system(st_module=None, theme: str = "light") -> None:
    """Inject the stylesheet for ``theme`` into the page. Call once,
    right after ``set_page_config`` (and before the login view renders),
    so the auth screen gets the design system too. ``st_module``
    defaults to the imported ``streamlit`` module; pass the app's
    ``st`` when testing with a fake."""
    (st_module or st).markdown(theme_css(theme), unsafe_allow_html=True)


#: Widget keys for the two theme controls. They are deliberately NOT
#: ``"dcs_theme"``: ``dcs_theme`` is the plain session key the
#: stylesheet follows, and every control writes it — while a widget
#: that OWNS the ``dcs_theme`` key keeps its own stored value and
#: ignores a direct write to it. That is exactly the live bug the
#: user saw: flip the theme from the login link (or the avatar menu)
#: and the sidebar selectbox still showed "Light" while the page
#: went dark, because the selectbox owned the key. The controls
#: below own their own keys (``dcs_theme_select``,
#: ``avatar_theme_radio``) and sync both ways through
#: ``sync_theme_widgets`` + ``on_change`` callbacks.
THEME_SELECT_KEY = "dcs_theme_select"
THEME_RADIO_KEY = "avatar_theme_radio"
PROFILE_THEME_RADIO_KEY = "profile_theme_radio"


def sync_theme_widgets(st_module=None) -> None:
    """Sync the theme widgets to the theme in effect — call once per
    run, BEFORE any theme widget is created (the app calls it right
    after the ``dcs_theme`` setdefault, before the top bar).

    Writing a widget's session key is only allowed before that widget
    is instantiated in the run, which is exactly where this runs — so
    a theme flipped from anywhere (login link, avatar menu, sidebar
    selectbox, Profile Appearance card) is reflected in every control
    on the next run, and the sidebar dropdown can never again show
    "Light" while the page is dark. The widgets' ``on_change``
    callbacks write back the other way (widget -> ``dcs_theme``), so
    the two directions agree."""
    st_mod = st_module or st
    current = normalize_theme(
        st_mod.session_state.get("dcs_theme", THEME_DEFAULT))
    st_mod.session_state[THEME_SELECT_KEY] = current
    st_mod.session_state[THEME_RADIO_KEY] = current
    st_mod.session_state[PROFILE_THEME_RADIO_KEY] = current


def render_theme_toggle(st_module=None) -> str:
    """Render the Light/Dark switch in the sidebar and return the
    theme now in effect. The switch is a selectbox whose widget key
    is ``dcs_theme_select`` (NOT ``dcs_theme`` — see the note above
    ``THEME_SELECT_KEY``): its ``on_change`` writes the shared
    ``dcs_theme`` key, and ``sync_theme_widgets`` (called at the top
    of the app, before this widget exists in the run) keeps the
    selectbox showing the theme in effect even when it was flipped
    from the login link or the avatar menu. No behaviour change: the
    toggle only swaps the stylesheet."""
    st_mod = st_module or st
    current = normalize_theme(
        st_mod.session_state.get("dcs_theme", THEME_DEFAULT))

    def _on_change():
        st_mod.session_state["dcs_theme"] = normalize_theme(
            st_mod.session_state.get(THEME_SELECT_KEY, current))
        # The avatar menu's radio is created earlier in the run (top
        # bar), so its key cannot be written here — it is re-synced
        # by sync_theme_widgets at the top of the next run, and by
        # the re-sync inside render_avatar_menu before the radio is
        # created. The selectbox key below is re-synced the same way.

    # Re-sync immediately before creating the selectbox: the theme
    # may have flipped earlier in this run (avatar-menu radio), and
    # the top-of-run sync predates that flip — without this, the
    # dropdown can show the old theme while the page is already the
    # new one (the 2026-11-07 screenshot: dark page, "Light"
    # dropdown). Writing the key before creation is the legal
    # moment; after creation it would raise.
    st_mod.session_state[THEME_SELECT_KEY] = current
    st_mod.sidebar.selectbox(
        "Theme", options=list(THEMES),
        format_func=lambda t: "Dark" if t == "dark" else "Light",
        key=THEME_SELECT_KEY,
        on_change=_on_change,
        help="Switch the whole app between the light and dark "
             "Supabase look.")
    return normalize_theme(
        st_mod.session_state.get("dcs_theme", current))


def render_login_theme_toggle(st_module=None) -> None:
    """Render the theme switch as a text link for the login screen, which
    has no sidebar. A tertiary button (borderless, link-green — see the
    ``button[kind="tertiary"]`` rules in both stylesheets), so it reads
    as the small "Switch to dark theme" link at the top-right of the
    variant C console header. Flips ``st.session_state["dcs_theme"]``
    between light and dark and reruns, so the login screen itself
    restyles. The sidebar selectbox is not rendered on this screen, so
    writing the shared key here never collides with the widget."""
    st_mod = st_module or st
    current = normalize_theme(
        st_mod.session_state.get("dcs_theme", THEME_DEFAULT))
    label = ("Switch to light theme" if current == "dark"
             else "Switch to dark theme")
    if st_mod.button(label, key="dcs_theme_login_toggle", type="tertiary"):
        _new = "light" if current == "dark" else "dark"
        st_mod.session_state["dcs_theme"] = _new
        # Both theme widgets are re-synced from dcs_theme by
        # sync_theme_widgets at the top of the next run; write them
        # here too so no run can ever show a stale control (neither
        # widget exists on the login screen, so writing their keys
        # here is safe).
        st_mod.session_state[THEME_SELECT_KEY] = _new
        st_mod.session_state[THEME_RADIO_KEY] = _new
        st_mod.rerun()


def _logo_data_uri(logo_path):
    """The logo file as a ``data:`` URI (``None`` when the file is
    missing or unreadable). Shared by the console header and the
    branded loader — the PNG is inlined as base64 because Streamlit
    cannot put an ``st.image`` inside a flex row, and the loader
    layers need the same URI."""
    try:
        _p = Path(logo_path)
        if _p.is_file():
            _mime = ("image/svg+xml" if _p.suffix == ".svg"
                     else "image/png")
            return ("data:" + _mime + ";base64," +
                    base64.b64encode(_p.read_bytes()).decode("ascii"))
    except OSError:
        pass
    return None


def console_head_html(logo_path) -> str:
    """Header row for the variant C console login: 40px logo + 22px
    title, left-aligned (``.dcs-console-head``). ``logo_path`` is the
    ``assets/logo.png`` path (``assets/logo-dark.png`` when the theme
    is dark — the mark is dark-green line art, so the dark variant is
    the same mark recolored to the dark link green ``#4acd8b``). When
    the file is missing only the title renders, same as the old
    ``st.image`` guard. The PNG is inlined as base64 because
    Streamlit cannot put an ``st.image`` inside a flex row."""
    _uri = _logo_data_uri(logo_path)
    _logo = ('<img src="' + _uri + '" alt="Data Cleaner Studio logo">'
             if _uri else "")
    return ('<div class="dcs-console-head">' + _logo +
            "<h1>Data Cleaner Studio</h1></div>")


def loader_block_html(logo_path, status, size="large") -> str:
    """The branded loader: the logo mark animating Supabase-style —
    the three bars rising one by one (staggered), the checkmark
    drawing itself left to right, then a gentle pulse while the wait
    continues — plus the status line and a thin shimmer bar. The mark
    is layered as four <img> slices over ONE small base64 data URI
    (the 192px loader file, ~17KB — the same data URI in all four
    slices, so the file is inlined once per slice, not once per
    layer of a bigger file). An <img> per slice, not a background
    image on a custom property: the earlier mechanism never painted
    live (two live checks saw the status text but never the mark),
    while <img> data URIs already paint everywhere else in this app.
    ``size`` is ``"large"`` (96px
    mark, centred, app name + status — the login screen while the
    session restores) or ``"compact"`` (40px mark in a row with the
    status — a file-processing wait). A missing logo file renders the
    status line alone, so a wait never breaks. The status text is
    escaped; the logo path is never echoed."""
    _size = "compact" if size == "compact" else "large"
    _status = html.escape(str(status))
    _uri = _logo_data_uri(logo_path)
    if _uri is None:
        return ('<div class="dcs-loader dcs-loader--' + _size + '">'
                '<div class="dcs-loader-status">' + _status +
                "</div></div>")
    _mark = ('<div class="dcs-loader-mark">'
             '<img src="' + _uri + '" alt="" class="dcs-lm-bar1">'
             '<img src="' + _uri + '" alt="" class="dcs-lm-bar2">'
             '<img src="' + _uri + '" alt="" class="dcs-lm-bar3">'
             '<img src="' + _uri + '" alt="" class="dcs-lm-check"></div>')
    if _size == "compact":
        _body = ('<div class="dcs-loader-row">' + _mark +
                 '<div class="dcs-loader-status">' + _status +
                 "</div></div>"
                 '<div class="dcs-loader-shimmer"><i></i></div>')
    else:
        _body = (_mark +
                 '<div class="dcs-loader-name">Data Cleaner Studio</div>'
                 '<div class="dcs-loader-status">' + _status + "</div>"
                 '<div class="dcs-loader-shimmer"><i></i></div>')
    return ('<div class="dcs-loader dcs-loader--' + _size + '">' +
            _body + "</div>")


def topbar(title: str, breadcrumb: str = "", user=None,
           logo_path=None, st_module=None) -> dict:
    """Render the real top bar (Supabase shell, ~48px): the app logo
    at the far left (the user's bars-and-checkmark mark — the Supabase
    bolt's placement, his logo, never the Supabase mark) + the
    workspace name + the current screen, then a search column, a green
    ``Upload`` pill (the Connect-style primary action), a Help
    icon-only button, and the avatar at the far right.

    The search column is returned empty for the caller to fill with
    the Quick jump box (the honest Streamlit version of Supabase's
    Search / Cmd+K pill) — the caller keeps owning the search, this
    bar only owns its place. Returns a dict: ``"avatar"`` is the
    avatar-menu action (``"profile"`` / ``"logout"`` / ``"status"`` /
    ``"previews"`` / None), ``"upload"`` / ``"help"`` are True when
    those buttons were clicked, and ``"search_col"`` is the column
    to render the Quick jump input in. Presentation + navigation
    only — the caller acts on the returned actions (pending_tab +
    rerun, the same mechanism the sidebar Profile button uses).
    """
    st_mod = st_module or st
    _uri = _logo_data_uri(logo_path) if logo_path else None
    _logo = (f'<img src="{_uri}" alt="" class="dcs-topbar-logo">'
             if _uri else "")
    # The breadcrumb is the file name only when a file is loaded,
    # and the page name only when none is loaded — never both. The
    # brand already says the workspace name, so rendering the title
    # AND the crumb produced three segments ("Data Cleaner Studio /
    # Preview / messy_sales.csv (sample)") with the page name and
    # the file name both truncated. The title span renders only
    # when there is no breadcrumb; the crumb span only when there
    # is one. The ellipsis/nowrap guards on the spans stay, so
    # nothing overlaps the search box.
    _crumb = (f'<span class="dcs-topbar-crumb"> / '
              f"{html.escape(breadcrumb)}</span>" if breadcrumb else "")
    _title = (f'<span class="dcs-topbar-title"> / '
              f"{html.escape(title)}</span>" if not breadcrumb else "")
    _brand = ('<span class="dcs-topbar-brand">Data Cleaner Studio</span>')
    _left = (f'<div class="dcs-topbar-left">{_logo}{_brand}{_title}'
             f"{_crumb}</div>")
    cols = st_mod.columns([2.3, 1.9, 1.1, 0.35, 0.45], gap="small",
                          vertical_alignment="center")
    with cols[0]:
        st_mod.markdown(_left, unsafe_allow_html=True)
    with cols[2]:
        _upload = icon_button(
            "Upload", "upload", kind="primary", key="topbar_upload",
            help="Go to Preview to upload a file.", st_module=st_mod)
    with cols[3]:
        _help = bool(st_mod.button(
            "", icon=icon_for("help"), key="topbar_help",
            help="How to use — open the guide."))
    with cols[4]:
        _avatar_action = render_avatar_menu(st_module=st_mod, user=user,
                                            container=cols[4])
    st_mod.markdown('<div class="dcs-topbar-rule"></div>',
                    unsafe_allow_html=True)
    return {"avatar": _avatar_action, "upload": bool(_upload),
            "help": bool(_help), "search_col": cols[1]}


# ---------------------------------------------------------------------------
# The sidebar rail — Supabase's real nav (page-by-page study §0/§9, live
# walk appendix). The dashboard's first nav layer is a narrow icon-only
# rail (~60px); hovering it expands it AUTOMATICALLY as an overlay
# (~260px, labels + controls appear, ~0.2s ease) floating above the
# page, and moving the mouse away shrinks it back — no toggle click,
# no server rerun (the user's video shows the rail alternating
# expanded/collapsed as the mouse moves, the expanding sidebar
# overlapping the page title). The bottom toggle is the PINNED state:
# click it and the sidebar STAYS expanded; click again and it stays
# collapsed (hover then works as the temporary expand). Our old
# sidebar was icon + label rows under DATA / ANALYSE / OUTPUT /
# WORKSPACE headers — that is not Supabase's sidebar, and a restyle of
# Streamlit's hide/unhide chevron did not satisfy the user, so the rail
# is rebuilt here as a real two-state nav:
#
#   * collapsed (default — Supabase's own default): the sidebar is
#     forced to 60px and holds ONLY icon buttons (nav + the collapse
#     toggle) while not hovered. The labels ARE in the DOM (the nav
#     buttons always render their label — the rail CSS hides the
#     label span when collapsed and not hovered) and every
#     expanded-sidebar control (theme selectbox, status pill, file
#     uploader, sample button, expanders, checkbox, slicers) is
#     rendered too, CSS-hidden until hover — that is what makes the
#     hover expand able to reveal them with no rerun. Each nav icon
#     carries its plain label as its ``help`` tooltip, and hovering
#     a row still shows the dark "Go to <Page>" tooltip.
#   * expanded (pinned): the sidebar is forced to 260px and holds
#     the full sidebar (theme selectbox, icon + label nav rows,
#     toggle, status pill, uploader) — the same content as before,
#     minus the section headers, which Supabase's rail does not have.
#     Hover changes nothing in this state.
#
# The width is forced with author !important rules: Streamlit 1.66.1
# sets the sidebar width as an inline style (resizable wrapper, width
# also kept in localStorage) with min/max-width from the emotion
# class, and author !important beats both. The layout is flex row
# with the main area flex:1 (verified in the 1.66.1 frontend bundle),
# so the main area grows into the freed space on its own. The content
# padding (~24px each side) is overridden to 6px in the collapsed
# state or it would eat the whole 60px rail. The state lives in
# session state (``dcs_rail_collapsed``, default True) and is
# remembered across reruns the way dcs_theme is.
# ---------------------------------------------------------------------------
RAIL_COLLAPSED_KEY = "dcs_rail_collapsed"
RAIL_WIDTH_COLLAPSED = "60px"
RAIL_WIDTH_EXPANDED = "260px"


def rail_collapsed(st_module=None) -> bool:
    """True when the sidebar rail is in its collapsed (icon-only)
    state. Defaults to True — Supabase's own default, and the state
    the user asked for. Anything stored that is not a bool reads as
    collapsed when truthy, expanded when falsy."""
    st_mod = st_module or st
    return bool(st_mod.session_state.get(RAIL_COLLAPSED_KEY, True))


def rail_css(collapsed: bool, theme) -> str:
    """The rail stylesheet for one state + theme, as a ``<style>``
    block. Injected per run (after the design system) so the width
    follows the session-state rail state — the base stylesheets never
    change, and the app.py literal stays the verbatim light paste.

    Supabase's real sidebar (the user's video): the default is an
    icon-only rail (~60px); hovering the rail expands it
    AUTOMATICALLY as an overlay (~260px, labels + controls appear,
    ~0.2s ease) floating above the page content — no toggle click,
    no server rerun — and moving the mouse away shrinks it back.
    The bottom toggle is the PINNED state: click it and the sidebar
    STAYS expanded; click again and it stays collapsed (hover then
    works as the temporary expand). When pinned-expanded, hover
    changes nothing.

    The hover expand is pure client-side CSS — ``:hover`` on the
    section with a width transition on the sidebar content — so the
    0.2s glide is genuinely achievable here, unlike the click-toggle
    glide (the toggle drives a full server rerun and the sidebar
    remounts at the new width, so a CSS width transition cannot
    interpolate across it; the transition list still carries
    flex-basis + width for the toggle, but the live check is the
    only proof of whether it glides). The overlay does not push the
    page: the section stays a 60px flex item (the main area never
    moves) and only its content (``stSidebarContent``) becomes an
    absolutely-positioned 260px panel above the content.

    For the hover to reveal the labels, the nav labels are always
    rendered (sidebar_nav) — the hover overlay shows them. The
    non-nav controls are NOT in the DOM while collapsed: app.py
    guards them on the rail state (they render only when pinned
    open), because what is not in the DOM cannot render as vertical
    one-letter text — the 8b4dd04 live failure, where the theme
    selectbox, status pill, uploader and checkbox all squeezed into
    single-letter columns despite a CSS denylist. The denylist
    stays as a backstop for the two widgets that must stay mounted
    (the Excel sheet picker, the "More ways to load" expander):
    an explicit testid denylist of DESCENDANT selectors (no ``>``,
    no ``:has()`` — the 8b4dd04 denylist used ``>`` and matched
    zero elements live: an intermediate plain div sits between the
    user content and the vertical block, and every widget root is
    a grandchild of the block, never a direct child), the no-help
    buttons (sample, load sheet — their <button> is a DIRECT child
    of the wrapper, unlike nav/toggle buttons, which have the
    help-wrapper div in between), and the nav label spans. The
    widgets that stay mounted keep their values; the guarded ones
    persist theirs in session state and pick them back up on
    re-open. Hovering a collapsed rail therefore shows the nav
    labels + the toggle; the uploader, theme, status and slicers
    appear when the rail is pinned open.

    Both states: the sidebar is a flex column
    (``stSidebarContent`` > header + ``stSidebarUserContent`` >
    vertical block). The toggle — the vertical block's LAST child,
    rendered after the slicers — is pinned FIXED to the viewport's
    bottom-left at the rail's width in every state, so it never
    sits below the fold however tall the content is (absolute
    scrolled away with the content live; sticky stopped 56px
    short; fixed held at the viewport bottom at every scroll
    offset in the real-DOM probe). The vertical block carries
    bottom padding so the last content row scrolls above it.
    Streamlit's native top "«" collapse control is hidden: the
    rail collapses to the 60px icon rail, never to 0px.

    Collapsed: 60px sidebar, 6px content padding, 4px gaps, rail
    buttons as 36px borderless squares with a centred icon (12
    icons + toggle fit a 573px viewport: 13 x 36 + 12 x 4 + padding
    = 528px, so the scroll offset clamps to ~0 when collapsing),
    a subtle wash on hover and the active (disabled) icon in a
    rounded-square highlight. The button rules repeat the base
    sheet's five selectors (button, button *, :hover, :disabled,
    :disabled *) with the rail values, so they win on equal
    specificity by coming later in the page — and they are
    DESCENDANT selectors (no ``>``): the nav buttons carry icon=
    + help=, so the $u help wrapper nests an intermediate plain
    div between the wrapper and the <button>, and ``>`` never
    matched (the 5028aa3 live failure).
    Expanded: 260px sidebar; the nav rows keep the base sheet's
    icon + label row styling."""
    _tokens = (DARK_TOKENS if normalize_theme(theme) == "dark"
               else TOKENS)
    _width = (RAIL_WIDTH_COLLAPSED if collapsed
              else RAIL_WIDTH_EXPANDED)
    _ink = _tokens["ink"]
    _hover = _tokens["hover"]
    _active = _tokens["active_nav"]
    _bg = _tokens["bg"]
    _shadow = ("0 0 24px rgba(0, 0, 0, 0.45)"
               if normalize_theme(theme) == "dark"
               else "0 0 24px rgba(3, 3, 3, 0.18)")
    _ease = "200ms cubic-bezier(0.22,1,0.36,1)"
    # The hover glide's own ease: 250ms, the value the real-DOM
    # probe measured as visibly gradual (60 -> 213 -> 252 -> 259
    # -> 260px across 40ms samples). The 200ms ease read as a snap
    # live (the check saw no glide, snap or <=150ms).
    _glide = "250ms cubic-bezier(0.4,0,0.2,1)"
    # The toggle's FIXED pin (all states): the wrapper is removed
    # from flow and pinned to the viewport's bottom-left, so it
    # never sits below the fold however tall the sidebar content
    # is. The vertical block's bottom padding (same states) lets
    # the last content row scroll above it. FIXED, not absolute:
    # absolute scrolls away with the content (the 5028aa3 live
    # failure — the toggle sat at content-bottom, 1409px down a
    # 998px viewport), and sticky stopped 56px short. Fixed held
    # at the viewport bottom (998px) at every scroll offset in the
    # real-DOM probe. The selector targets the toggle's element
    # container ONLY, by its Streamlit key class
    # (``st-key-dcs_rail_toggle`` — the class Streamlit puts on
    # the element container of a widget with that key). A plain
    # ``div:last-child`` descendant selector is WRONG here: it
    # matches every div that is a last child of its parent
    # anywhere in the vertical block, so it fixed EVERY sidebar
    # widget to the viewport bottom and the whole sidebar
    # collapsed into one overlapping stack (caught by the
    # round-7 real-DOM probe — the expanded sidebar rendered
    # empty except for the toggle).
    def _toggle_pin_rules(width, hover=False):
        _sel = (
            'section[data-testid="stSidebar"]:hover '
            'div[data-testid="stElementContainer"].st-key-dcs_rail_toggle {'
            if hover else
            'section[data-testid="stSidebar"] '
            'div[data-testid="stElementContainer"].st-key-dcs_rail_toggle {')
        return [
            _sel,
            "  margin-top: 0 !important; position: fixed !important;",
            "  bottom: 0 !important; left: 0 !important;",
            f"  width: {width} !important;",
            "  z-index: 2 !important;",
            f"  background: {_bg} !important; padding: 4px 12px 8px !important; }}",
        ]
    _css = [
        "<style>",
        "/* ---- sidebar rail: Supabase icon rail / labelled sidebar ---- */",
        'section[data-testid="stSidebar"] {',
        f"  width: {_width} !important; min-width: {_width} !important;",
        f"  max-width: {_width} !important; flex: 0 0 {_width} !important;",
        f"  transition: transform {_ease},",
        f"    min-width {_ease},",
        f"    max-width {_ease},",
        f"    width {_ease},",
        # The rendered width is the flex-basis (the section is a
        # flex item in the app's flex-row container), so the
        # transition must cover flex-basis or a width change never
        # animates. (The click-toggle glide still cannot be proven
        # from CSS alone — the toggle remounts the sidebar — but
        # the hover glide below is pure client-side and real.)
        f"    flex-basis {_ease} !important; }}",
        # The scroll container becomes a flex column, the user
        # content + vertical block fill the height. Its width
        # transition is the hover glide (collapsed): the content
        # goes 60px -> 260px as an overlay and back, with no rerun.
        # The base width is EXPLICIT (60px, set in the collapsed
        # branch): a transition from ``auto`` never interpolates,
        # which is why the 8b4dd04 glide snapped — the content's
        # width was auto (59px) and jumped straight to 260px.
        'section[data-testid="stSidebar"] div[data-testid="stSidebarContent"] {',
        "  display: flex !important; flex-direction: column !important;",
        f"  transition: width {_glide} !important; }}",
        # Streamlit's native collapse control (the top "«" that
        # hides the sidebar entirely to 0px, "»" to restore) is
        # suppressed: the rail collapses to the 60px icon rail,
        # never to 0px, and only the bottom toggle + hover govern
        # it. Without this the two collapse controls fight — the
        # native one hides the whole sidebar while the bottom one
        # still says "Collapse sidebar".
        'div[data-testid="stSidebarCollapseButton"] {',
        "  display: none !important; }",
        'section[data-testid="stSidebar"] div[data-testid="stSidebarHeader"] {',
        "  flex: none !important; }",
        'section[data-testid="stSidebar"] div[data-testid="stSidebarUserContent"] {',
        "  flex: 1 1 auto !important; min-height: 0 !important;",
        "  display: flex !important; flex-direction: column !important; }",
        'section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {',
        "  flex: 1 1 auto !important; min-height: 0 !important;",
        "  display: flex !important; flex-direction: column !important; }",
        # Pin the toggle to the bottom of the rail (collapsed, not
        # hovered): FIXED to the viewport's bottom-left at the
        # rail's width, so it holds however tall the sidebar
        # content is. (The 8b4dd04 sticky rule never matched live
        # — its ``stSidebarUserContent > stVerticalBlock`` chain
        # is broken by the intermediate plain div — and the
        # collapsed pin only "passed" because the content happened
        # to fit. Fixed is the uniform mechanism, proven in the
        # real-DOM probe at every scroll offset.) The pin width is
        # the CURRENT state's width (``_width``): a collapsed-width
        # pin left in the expanded stylesheet would put a 60px
        # rule in the expanded CSS even though the later 260px
        # rule wins the cascade.
    ] + _toggle_pin_rules(_width)
    if collapsed:
        _deny = [
            # DESCENDANT selectors throughout: the 8b4dd04 denylist
            # used ``stSidebarUserContent > stVerticalBlock >
            # div[data-testid=...]`` and matched ZERO elements live
            # — an intermediate plain div sits between the user
            # content and the vertical block, and every widget root
            # is a GRANDCHILD of the block (inside its element
            # container), never a direct child. The descendant
            # form hid every non-nav widget in the real-DOM probe
            # (selectbox, markdowns, uploader, checkbox, alert all
            # display:none, nav button still visible).
            'section[data-testid="stSidebar"]:not(:hover) div[data-testid="stVerticalBlock"] div[data-testid="stCheckbox"],',
            'section[data-testid="stSidebar"]:not(:hover) div[data-testid="stVerticalBlock"] div[data-testid="stMarkdown"],',
            'section[data-testid="stSidebar"]:not(:hover) div[data-testid="stVerticalBlock"] div[data-testid="stMultiSelect"],',
            'section[data-testid="stSidebar"]:not(:hover) div[data-testid="stVerticalBlock"] div[data-testid="stDateInput"],',
            'section[data-testid="stSidebar"]:not(:hover) div[data-testid="stVerticalBlock"] div[data-testid="stCaption"],',
            'section[data-testid="stSidebar"]:not(:hover) div[data-testid="stVerticalBlock"] div[data-testid="stExpander"],',
            'section[data-testid="stSidebar"]:not(:hover) div[data-testid="stVerticalBlock"] div[data-testid="stFileUploader"],',
            'section[data-testid="stSidebar"]:not(:hover) div[data-testid="stVerticalBlock"] div[data-testid="stSelectbox"],',
            'section[data-testid="stSidebar"]:not(:hover) div[data-testid="stVerticalBlock"] div[data-testid="stAlert"],',
            'section[data-testid="stSidebar"]:not(:hover) div[data-testid="stVerticalBlock"] div[data-testid="stTextInput"],',
            'section[data-testid="stSidebar"]:not(:hover) div[data-testid="stVerticalBlock"] div[data-testid="stRadio"],',
            'section[data-testid="stSidebar"]:not(:hover) div[data-testid="stVerticalBlock"] div[data-testid="stNumberInput"] {',
            "  display: none !important; }",
        ]
        _css += [
            # The collapsed content's width is EXPLICIT (60px):
            # a transition from ``auto`` never interpolates, so
            # the hover glide snapped live. With a definite 60px
            # base and a 260px hover width, the 250ms transition
            # has two lengths to interpolate between (real-DOM
            # probe: 60 -> 213 -> 252 -> 259 -> 260px).
            'section[data-testid="stSidebar"] div[data-testid="stSidebarContent"] {',
            "  padding-left: 6px !important; padding-right: 6px !important;",
            f"  width: {RAIL_WIDTH_COLLAPSED} !important; }}",
            'section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {',
            "  gap: 4px !important; padding-bottom: 56px !important; }",
            # Hover expand (pinned-collapsed only): the section
            # stays a 60px flex item — the main area never moves —
            # and only its content becomes a 260px overlay floating
            # above the page. No rerun, no remount: the width
            # transition on the content is the real 0.2s glide.
            # The section's z-index lifts the overlay above the
            # main area; the shadow is the overlay's depth.
            'section[data-testid="stSidebar"]:hover {',
            "  z-index: 1000000 !important; }",
            'section[data-testid="stSidebar"]:hover div[data-testid="stSidebarContent"] {',
            "  position: absolute !important; left: 0 !important;",
            "  top: 0 !important; bottom: 0 !important;",
            "  width: 260px !important; max-width: 260px !important;",
            f"  box-shadow: {_shadow} !important;",
            f"  transition: width {_glide} !important; }}",
            # Hover-expanded: the element containers go full-width
            # (the expanded-pill fix — the nav buttons' width:100%
            # resolves against the 260px overlay, not a
            # content-sized ~100px box), and the toggle pins FIXED
            # at the overlay's 260px width. The vertical block
            # carries bottom padding so the last content row can
            # scroll above the fixed toggle.
            'section[data-testid="stSidebar"]:hover div[data-testid="stVerticalBlock"] {',
            "  padding-bottom: 56px !important; }",
            'section[data-testid="stSidebar"]:hover div[data-testid="stVerticalBlock"] div[data-testid="stElementContainer"],',
            'section[data-testid="stSidebar"]:hover div[data-testid="stVerticalBlock"] div[data-testid="stLayoutWrapper"] {',
            "  width: 100% !important; align-self: stretch !important; }",
            # Hover-expanded rows read left-aligned like the
            # pinned-expanded ones: the collapsed branch's button
            # rule centres them (icon-only rail), and it would win
            # over the base sheet's flex-start here.
            'section[data-testid="stSidebar"]:hover div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"] {',
            "  justify-content: flex-start !important; }",
        ] + _toggle_pin_rules(RAIL_WIDTH_EXPANDED, hover=True) + [
            # Hiding, collapsed and NOT hovered (the denylist): every
            # non-nav child of the vertical block is hidden — the
            # client-mode checkbox, the slicers, the uploader, the
            # expanders, the theme selectbox, the status pill and
            # any sidebar alert. The widgets stay mounted (their
            # values survive); only the nav rows + toggle stay
            # visible. Explicit testids, NO :has(): the 5028aa3
            # safety net used :has() and never took effect live —
            # and, per the bundle, it would have hidden the nav
            # buttons too (their direct child is the intermediate
            # help-wrapper div, not another stButton div).
        ] + _deny + [
            # Non-nav sidebar buttons (sample, load sheet): they
            # carry no help=, so Streamlit renders their <button>
            # as a DIRECT child of the wrapper — unlike nav/toggle
            # buttons, which have the help-wrapper div in between.
            # Hide the direct-child button when collapsed and not
            # hovered; the nav + toggle keep showing.
            'section[data-testid="stSidebar"]:not(:hover) div[data-testid="stVerticalBlock"] div[data-testid="stButton"] > button {',
            "  display: none !important; }",
            # Nav labels, collapsed and not hovered: the label text
            # lives in a <span style="display: contents"> inside
            # the button (the only span Streamlit renders with that
            # inline style), so hiding it leaves the icon alone in
            # the 36px square. On hover (or pinned-expanded) the
            # label shows. Both serialisations of the inline style
            # are covered (React may or may not put a space after
            # the colon).
            'section[data-testid="stSidebar"]:not(:hover) div[data-testid="stButton"] button span[style*="display: contents"],',
            'section[data-testid="stSidebar"]:not(:hover) div[data-testid="stButton"] button span[style*="display:contents"] {',
            "  display: none !important; }",
            'section[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"] {',
            "  width: 100% !important; height: 36px !important;",
            "  min-height: 36px !important; padding: 0 !important;",
            "  border: none !important; border-radius: 8px !important;",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  justify-content: center !important; }",
            'section[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"] * {',
            f"  color: {_ink} !important; }}",
            'section[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"]:hover {',
            f"  background-color: {_hover} !important;",
            "  border: none !important; }",
            'section[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"]:disabled {',
            f"  background-color: {_active} !important;",
            "  border: none !important; opacity: 1 !important; }",
            'section[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"]:disabled * {',
            f"  color: {_ink} !important; }}",
        ]
    else:
        _css += [
            # Expanded: the content scrolls, so the toggle pins
            # FIXED to the viewport bottom (absolute scrolled away
            # with the content live; fixed held at 998px at every
            # scroll offset in the real-DOM probe), and the
            # vertical block carries bottom padding so the last
            # content row can scroll above it. The element
            # containers go full-width (the expanded-pill fix).
            'section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {',
            "  padding-bottom: 56px !important; }",
            'section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] div[data-testid="stElementContainer"],',
            'section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] div[data-testid="stLayoutWrapper"] {',
            "  width: 100% !important; align-self: stretch !important; }",
        ]
        # (The toggle pin is already emitted above at the state's
        # width — 260px here — so no second pin is needed.)
    _css.append("</style>")
    return "\n".join(_css)


def sidebar_nav(items, active: str | None = None, collapsed: bool = False,
                st_module=None):
    """Render the sidebar nav as Supabase's rail rows.

    ``items`` is a flat list of ``(key, label)`` pairs — or plain
    label strings, in which case the label itself is the key. Grouped
    ``(section, items)`` input is still accepted and flattened (the
    old call shape), but NO section headers are rendered: Supabase's
    rail has none, and the DATA / ANALYSE / OUTPUT / WORKSPACE
    headers are gone. Every row carries its line icon left of its
    label (the dashboard's icon + label rows) and a ``help`` tooltip
    reading "Go to <label>" — the tooltip is the only place the label
    appears in the collapsed state, and it carries no shortcut chips:
    the app has no G-then-X navigation shortcuts, so none are shown.
    The row for ``active`` is a DISABLED button — you are already
    there, so it cannot be clicked — and the stylesheet renders a
    disabled sidebar button as the
    active pill (light) / rounded-square highlight (collapsed).
    Clicking any other row returns its key; the caller sets
    ``pending_tab`` and reruns (the radio below is the authority,
    and pending_tab is how every programmatic switch reaches it).
    Returns the clicked key, or None when nothing was clicked. Call
    inside ``with st.sidebar:`` — the buttons render wherever the
    caller puts them.

    The label is ALWAYS rendered, in both states: the hover rail
    (Supabase's real behaviour — hover the icon rail and it expands
    as an overlay showing the labels) needs the label text in the
    DOM while collapsed, so the rail CSS can reveal it on hover.
    When collapsed and not hovered, the rail stylesheet hides the
    label span (``span[style*="display: contents"]`` — the only span
    Streamlit renders with that inline style) and the button reads
    as an icon-only square; on hover (or pinned-expanded) the label
    shows. ``collapsed`` therefore only changes the CSS state the
    caller is in, not the label — the widget keys and tooltips are
    identical in both states, so tests and navigation do not depend
    on which state the rail is in."""
    st_mod = st_module or st
    clicked = None
    _flat = []
    for _item in items:
        if (isinstance(_item, tuple) and len(_item) == 2
                and isinstance(_item[1], (list, tuple))):
            _flat.extend(_item[1])
        else:
            _flat.append(_item)
    for _item in _flat:
        key, label = (_item if isinstance(_item, tuple)
                      else (_item, _item))
        if st_mod.button(
                str(label),
                icon=icon_for(NAV_ICONS.get(key, "diamond")),
                key=f"dcs_nav_{key}", help=f"Go to {label}",
                type="secondary", disabled=(key == active)):
            clicked = key
    return clicked


def render_rail_toggle(st_module=None) -> bool:
    """Render the rail's collapse / expand toggle as an icon button
    and return True when it was clicked (the caller flips
    ``dcs_rail_collapsed`` and reruns). Collapsed: a right chevron,
    icon-only, "Expand sidebar". Expanded: a left chevron with the
    label "Collapse sidebar". Call inside ``with st.sidebar:``,
    LAST in the sidebar content (after the slicers) — the rail CSS
    pins the vertical block's last child to the bottom, so the
    toggle is the collapse control at the rail's foot, not a nav
    row. Streamlit's own sidebar collapse chevron (top of the bar)
    is untouched and keeps working alongside this one."""
    st_mod = st_module or st
    if rail_collapsed(st_mod):
        return bool(st_mod.button(
            "", icon=icon_for("chevron_right"), key="dcs_rail_toggle",
            help="Expand sidebar", type="secondary"))
    return bool(st_mod.button(
        "Collapse sidebar", icon=icon_for("chevron_left"),
        key="dcs_rail_toggle", help="Collapse sidebar",
        type="secondary"))


def avatar_initial(user) -> str:
    """First letter of the display name (or username, or email) for the
    sidebar avatar circle; ``"?"`` when nothing is set. Upper-cased,
    so "md ahmad" and "Md Ahmad" both give ``"M"``."""
    name = ((user or {}).get("display_name")
            or (user or {}).get("username")
            or (user or {}).get("email") or "?")
    return (str(name).strip()[:1].upper() or "?")


def _render_language_menu_selectbox(st_module=None) -> str:
    """The language picker as a small row in the avatar menu (the
    standalone "Language / भाषा / زبان" section on the Preview tab
    is gone — the user asked for it to live here instead). Same
    options (English / हिन्दी / اردو), same widget key
    ("n_lang_pick") and same save (settings.json + the
    "n_lang_data" session key), so switching works exactly as
    before — the coordinator reads the key at the top of the run.
    Returns the chosen language code."""
    st_mod = st_module or st
    import ai_settings  # local import: ui_design must not import it
    # at the top level (ai_settings is a plain settings store).
    _options = {"en": "English", "hi": "हिन्दी", "ur": "اردو"}
    try:
        _current = ai_settings.load_settings().get("language", "en")
    except Exception:  # noqa: BLE001 - a broken settings file
        _current = "en"  # must not stop the menu rendering.
    _codes = list(_options)
    _choice = st_mod.selectbox(
        "Language", [_options[c] for c in _codes],
        index=_codes.index(_current) if _current in _codes else 0,
        key="n_lang_pick", label_visibility="collapsed")
    _code = _codes[[_options[c] for c in _codes].index(_choice)]
    try:
        if _code != _current:
            _settings = ai_settings.load_settings()
            _settings["language"] = _code
            ai_settings.save_settings(_settings)
        st_mod.session_state["n_lang_data"] = _code
    except Exception:  # noqa: BLE001 - the session key is the
        st_mod.session_state["n_lang_data"] = _code  # fallback.
    return _code


def render_avatar_menu(st_module=None, user=None, container=None):
    """Render the avatar (a single green circle with the user's
    initial) and the Supabase-style account menu that opens from it.

    The menu is the dashboard's real one, page-by-page study §8 and
    the live-walk appendix: the email in bold at the top (plain text,
    never a link), then icon rows — Account, Feature previews,
    Changelog — a hairline, a "Theme" section with a Dark/Light radio
    (the selected row carries the filled dot, the way Supabase's
    System/Dark/Light rows do), a hairline, a Timezone row
    ("Auto (Asia/Calcutta)" — display-only; the app runs on IST),
    a hairline, a small "Language" row (English / हिन्दी / اردو —
    the standalone Language section on the Preview tab was removed
    at the user's ask, and the picker moved here), a hairline, then
    Sign out. No "Upgrade to Pro", no paid-tier anything: the app
    has no paid tier and none is invented.

    ``container`` is where the avatar lives — a top-bar column (the
    dashboard puts the avatar at the top bar's far right) or
    ``st.sidebar``; None means the sidebar. Returns ``"profile"``
    when Account was clicked (the caller opens the Profile tab),
    ``"status"`` for Changelog (the caller opens the Status tab,
    which holds the "What's new" changelog), ``"previews"`` for
    Feature previews (the caller says plainly there are none running),
    ``"logout"`` for Sign out, else None. The theme radio writes the
    shared ``dcs_theme`` key itself (via ``on_change``) and
    ``sync_theme_widgets`` keeps it showing the theme in effect.

    Why a radio, not the old theme button: the old "Switch to dark
    theme" button existed in code but did not render on screen in the
    live check — and a radio is what Supabase actually shows (one
    widget, one selected row, no stack of buttons to lose).
    The circle itself is styled by the design system CSS
    (``stPopoverButton`` rules); the popover is the honest Streamlit
    menu — no overlay palette exists in Streamlit, and the trigger
    button is the avatar."""
    st_mod = st_module or st
    email = str((user or {}).get("email") or "")
    current = normalize_theme(
        st_mod.session_state.get("dcs_theme", THEME_DEFAULT))
    # All buttons are always created, every run: returning early on
    # the Account click would skip the Sign out button for that run,
    # leaving the menu half-built. Collect the action, return after
    # the menu.
    action = None
    _host = container if container is not None else st_mod.sidebar
    with _host.popover(avatar_initial(user), key="avatar_menu"):
        if email:
            st_mod.markdown(
                f'<div class="dcs-menu-email">{html.escape(email)}</div>',
                unsafe_allow_html=True)
        st_mod.markdown('<div class="dcs-menu-divider"></div>',
                        unsafe_allow_html=True)
        if icon_button("Account", "account", key="avatar_account_btn",
                       help="Open your Profile.", st_module=st_mod):
            action = "profile"
        if icon_button("Feature previews", "flask",
                       key="avatar_previews_btn",
                       help="See what is being tried out.",
                       st_module=st_mod):
            action = "previews"
        if icon_button("Changelog", "changelog",
                       key="avatar_changelog_btn",
                       help="What changed, newest first.",
                       st_module=st_mod):
            action = "status"
        st_mod.markdown('<div class="dcs-menu-divider"></div>',
                        unsafe_allow_html=True)
        st_mod.markdown('<div class="dcs-menu-label">Theme</div>',
                        unsafe_allow_html=True)

        def _on_theme():
            _new = normalize_theme(
                st_mod.session_state.get(THEME_RADIO_KEY, current))
            st_mod.session_state["dcs_theme"] = _new
            # The sidebar selectbox is created later in the run (it
            # lives below the top bar), so its key can be written
            # here — it then shows the new theme on this very run
            # instead of one run behind (the 2026-11-07 screenshot:
            # dark page, "Light" dropdown). Writing it after the
            # selectbox exists would raise, which is why this lives
            # in the radio's callback and not the selectbox's.

        # Re-sync immediately before creating the radio, for the
        # same reason as the selectbox re-sync in
        # render_theme_toggle: the theme may have flipped earlier in
        # this run, and the top-of-run sync predates that flip.
        st_mod.session_state[THEME_RADIO_KEY] = current
        st_mod.radio(
            "Theme", options=list(THEMES),
            format_func=lambda t: "Dark" if t == "dark" else "Light",
            key=THEME_RADIO_KEY, on_change=_on_theme,
            label_visibility="collapsed")
        st_mod.markdown('<div class="dcs-menu-divider"></div>',
                        unsafe_allow_html=True)
        st_mod.markdown(
            '<div class="dcs-menu-row"><span>Timezone</span>'
            '<span class="dcs-menu-value">Auto (Asia/Calcutta)</span>'
            "</div>",
            unsafe_allow_html=True)
        st_mod.markdown('<div class="dcs-menu-divider"></div>',
                        unsafe_allow_html=True)
        st_mod.markdown('<div class="dcs-menu-label">Language</div>',
                        unsafe_allow_html=True)
        _render_language_menu_selectbox(st_mod)
        st_mod.markdown('<div class="dcs-menu-divider"></div>',
                        unsafe_allow_html=True)
        if icon_button("Sign out", "logout", key="avatar_logout_btn",
                       help="Log out of this account.",
                       st_module=st_mod):
            action = "logout"
    return action


def render_sidebar_avatar(st_module=None, user=None):
    """Backwards-compatible name for ``render_avatar_menu`` (sidebar
    placement): the sidebar avatar + account menu. New code calls
    ``render_avatar_menu`` directly (the avatar lives in the top bar
    now); this wrapper keeps the old call sites and tests working."""
    return render_avatar_menu(st_module=st_module, user=user,
                              container=None)


def section_heading(text: str, sub: str | None = None) -> None:
    """Render a 16-18px section heading with an optional muted sub-line
    underneath (the dashboard's "Get connected" / "Users" pattern).
    The colours live in the stylesheet (``.dcs-section-heading`` /
    ``.dcs-section-sub``) — never inline hex — so the heading reads
    in both themes (the old inline ``#030303`` / ``#696969`` rendered
    near-black on dark)."""
    sub_html = (f'<div class="dcs-section-sub">'
                f"{html.escape(sub)}</div>" if sub else "")
    st.markdown(
        f'<h2 class="dcs-section-heading">{html.escape(text)}</h2>'
        f"{sub_html}",
        unsafe_allow_html=True,
    )


def kpi_tile(label: str, value: str, sub: str | None = None,
             icon: str | None = None) -> None:
    """Render one status tile: uppercase micro-label, large (monospace)
    value, optional muted sub-line — the dashboard home's six-tile
    pattern (STATUS / Healthy, COMPUTE SIZE / NANO, ...). With
    ``icon`` (an ``svg_icon`` name) the tile gains the dashboard's
    48px icon box at the left, icon + label + value in a row; without
    it the tile is the old label + value stack."""
    sub_html = (f'<div class="dcs-kpi-sub">{html.escape(sub)}</div>'
                if sub else "")
    icon_html = (f'<div class="dcs-kpi-icon">{svg_icon(icon, 22)}</div>'
                 if icon else "")
    st.markdown(
        f'<div class="dcs-kpi">{icon_html}'
        f'<div class="dcs-kpi-text">'
        f'<div class="dcs-kpi-label">{html.escape(label)}</div>'
        f'<div class="dcs-kpi-value">{html.escape(str(value))}</div>'
        f"{sub_html}</div></div>",
        unsafe_allow_html=True,
    )


def card(title: str | None = None, body: str = "",
         footer: str | None = None) -> None:
    """Render a white card (1px hairline border, 12px radius, flat).

    ``title`` is the card heading (skipped when None), ``body`` is HTML
    already escaped / authored by the caller, ``footer`` an optional
    muted footer line. Keep ``body`` short — cards are for one idea.
    The title/footer colours live in the stylesheet
    (``.dcs-card-title`` / ``.dcs-card-footer``), never inline hex,
    so the card reads in both themes.
    """
    title_html = (f'<div class="dcs-card-title">'
                  f"{html.escape(title)}</div>" if title else "")
    footer_html = (f'<div class="dcs-card-footer">'
                   f"{html.escape(footer)}</div>" if footer else "")
    st.markdown(
        f'<div class="dcs-card">{title_html}{body}{footer_html}</div>',
        unsafe_allow_html=True,
    )


def settings_card(title: str, desc: str | None = None):
    """Open a Supabase-style settings card and return
    ``(left, right, card)``: a bordered card whose first row is
    [label + description | controls]. ``left`` is already filled with
    the bold title + muted description; ``right`` is the empty
    controls column for the caller to fill; ``card`` is the bordered
    container itself, so the caller can append a Save row at the
    card's bottom-right (``with card:`` again, then columns [3, 1]
    with the Save button in the right one). The dashboard's settings
    pages put label + description left and input (+ Copy) right, one
    bordered card per section, Save at the bottom-right — this is
    that shape, for Profile and Settings."""
    _card = st.container(border=True)
    with _card:
        _left, _right = st.columns([1.1, 1])
        with _left:
            st.markdown(
                f'<div class="dcs-settings-title">'
                f"{html.escape(title)}</div>",
                unsafe_allow_html=True)
            if desc:
                st.markdown(
                    f'<div class="dcs-settings-desc">'
                    f"{html.escape(desc)}</div>",
                    unsafe_allow_html=True)
    return _left, _right, _card


def metric_card(label: str, value, warnings: int = 0, errors: int = 0,
                bars=None, sub: str | None = None) -> None:
    """A Supabase service metric card: uppercase label at left with
    WARNINGS / ERRORS dot counts at right, a large count below, and a
    bar sparkline along the bottom. ``bars`` is a list of per-bucket
    heights — each item is a number (0-100, green) or a
    ``(height, kind)`` pair where kind is ``"ok"`` (green),
    ``"warn"`` (amber) or ``"error"`` (red). A card with no bars
    renders the count and dots only. The dots and counts are the
    app's own data (missing cells, duplicates) — never Supabase's."""
    _warn = (f'<span class="dcs-metric-count">'
             f'<span class="dcs-dot dcs-dot--warn"></span>'
             f"WARNINGS {int(warnings)}</span>")
    _err = (f'<span class="dcs-metric-count">'
            f'<span class="dcs-dot dcs-dot--danger"></span>'
             f"ERRORS {int(errors)}</span>")
    _bars_html = ""
    if bars:
        _items = []
        for _b in list(bars)[:24]:
            if isinstance(_b, (tuple, list)):
                _h, _k = float(_b[0]), str(_b[1])
            else:
                _h, _k = float(_b), "ok"
            _h = max(2.0, min(100.0, _h))
            # Bar colours live in the stylesheet (.dcs-bar-ok / -warn /
            # -error) so they follow the theme — never inline hex.
            _cls = {"warn": "dcs-bar-warn", "error": "dcs-bar-error"}.get(
                _k, "dcs-bar-ok")
            _items.append(
                f'<i class="{_cls}" style="height: {_h:.0f}%;"></i>')
        _bars_html = ('<div class="dcs-metric-bars">' + "".join(_items) +
                      "</div>")
    sub_html = (f'<div class="dcs-kpi-sub">{html.escape(sub)}</div>'
                if sub else "")
    st.markdown(
        f'<div class="dcs-metric-card">'
        f'<div class="dcs-metric-head">'
        f'<span class="dcs-kpi-label">{html.escape(label)}</span>'
        f'<span class="dcs-metric-dots">{_warn} {_err}</span></div>'
        f'<div class="dcs-metric-value">{html.escape(str(value))}</div>'
        f"{sub_html}{_bars_html}</div>",
        unsafe_allow_html=True,
    )


def connect_strip(cells) -> str | None:
    """The dashboard's "Get connected" strip, mapped to the app: six
    equal cells in one bordered strip, each an icon button (title) +
    a muted subtitle. ``cells`` is a list of dicts with ``key``,
    ``icon`` (an ``icon_button`` name), ``title`` and ``subtitle``.
    Clicking a cell returns its key — the caller navigates
    (pending_tab + rerun). Returns None when nothing was clicked.
    The strip carries its visible "Get connected" label above the
    cells (the label was missing — the strip rendered with no heading).
    """
    st.markdown('<div class="dcs-strip-label">Get connected</div>',
                unsafe_allow_html=True)
    clicked = None
    with st.container(border=True):
        _cols = st.columns(len(cells)) if cells else []
        for _col, _cell in zip(_cols, cells):
            with _col:
                if icon_button(
                        _cell["title"], _cell["icon"], kind="secondary",
                        key=f"dcs_connect_{_cell['key']}",
                        help=_cell.get("subtitle") or _cell["title"],
                        use_container_width=True):
                    clicked = _cell["key"]
                if _cell.get("subtitle"):
                    st.caption(_cell["subtitle"])
    return clicked


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


def info_card(text: str, st_module=None) -> None:
    """Render a plain Supabase-style card for an informational note
    — the replacement for ``st.info``, whose pale sky-blue halo
    (``rgba(28,131,255,0.1)`` on the alert container, around a
    white inner box) the user asked to remove. Uses the ``.dcs-card``
    class, so it follows the theme (white / #e8e8e8 hairline in
    light, #232625 / #2e2e2e in dark) and carries no blue, no icon
    and no colour at all. The text is escaped. A CSS backstop in
    both stylesheets neutralises any ``st.info`` that still renders
    (see the ``stAlertContentInfo`` rules), so no blue box survives
    anywhere — but call sites should use this card directly."""
    st_mod = st_module or st
    st_mod.markdown(
        f'<div class="dcs-card">{html.escape(str(text))}</div>',
        unsafe_allow_html=True)


def empty_state(title: str, body: str = "",
                cta_label: str | None = None,
                cta_icon: str = "play") -> bool:
    """Render a guided empty state: centred title + muted body inside a
    white bordered card, with an optional CTA button underneath.

    The CTA is an icon button (``cta_icon``, default "play" — every
    empty-state CTA is a "go / start" action), so it carries the small
    line icon left of its label like every other action button.
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
        return bool(icon_button(
            cta_label, cta_icon, kind="primary",
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
