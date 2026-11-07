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
  * ``render_theme_toggle(st=None)`` — the sidebar Light/Dark switch
    (writes ``st.session_state["dcs_theme"]``); ``render_login_theme_toggle``
    is the same switch as a button for the login screen, which has no
    sidebar.
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
    "active_nav": "#2a2d2c",
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
/* ---- inputs: white, 6px radius, hairline border ---- */
.stApp input, .stApp textarea, .stApp select {
  background-color: #ffffff; color: #030303;
  border-color: #e8e8e8; border-radius: 6px; }
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
/* ---- motion, honestly measured: colour-only 0.2s ease-out ---- */
.stApp .stButton > button, .stApp a, .dcs-nav-row,
div[data-testid="stRadio"] div[role="radiogroup"] label,
.stApp input, .stApp textarea, .stApp select {
  transition: background-color 0.2s cubic-bezier(0.22, 1, 0.36, 1),
    border-color 0.2s cubic-bezier(0.22, 1, 0.36, 1),
    color 0.2s cubic-bezier(0.22, 1, 0.36, 1); }
/* ---- focus: one shared ring — 2px gap + 4px translucent green halo ---- */
.stApp .stButton > button:focus-visible,
div[data-testid="stDownloadButton"] > button:focus-visible,
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
   The mark is the user's PNG (three bars + checkmark). It is layered
   four times over ONE base64 data URI, set inline as --dcs-logo on
   the container, so the 571KB file is inlined once, not four times.
   The three bars rise one by one (scaleY from the bottom, staggered),
   then the checkmark draws itself left to right (clip-path wipe),
   then the whole mark breathes gently while the wait continues. A
   thin shimmer bar runs under the status text. All motion uses the
   Supabase 0.2s cubic-bezier(0.22, 1, 0.36, 1) timing; under
   prefers-reduced-motion the mark renders whole and still. */
.dcs-loader { text-align: center; padding: 2.5rem 1rem 2rem; }
.dcs-loader-mark { position: relative; margin: 0 auto 16px;
  animation: dcs-lm-breathe 1.8s ease-in-out 1.15s infinite alternate; }
.dcs-loader--large .dcs-loader-mark { width: 96px; height: 96px; }
.dcs-loader--compact { text-align: left; padding: 0.5rem 0; }
.dcs-loader--compact .dcs-loader-row { display: flex; align-items: center;
  gap: 12px; }
.dcs-loader--compact .dcs-loader-mark { width: 40px; height: 40px;
  margin: 0; flex: none; }
.dcs-loader-mark > div { position: absolute; inset: 0;
  background-image: var(--dcs-logo); background-size: 100% 100%;
  background-repeat: no-repeat; }
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
  .dcs-loader-mark, .dcs-loader-mark > div, .dcs-loader-shimmer i {
    animation: none !important; } }
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
div[data-testid="stExpander"] { background-color: #232625;
  border: 1px solid #2e2e2e; border-radius: 12px; }
/* ---- spacing: consistent gaps between sections ---- */
div[data-testid="stVerticalBlock"] > div { gap: 0.75rem; }
/* ---- buttons: primary deepened green, subtle vertical gradient ---- */
.stApp .stButton > button[kind="primary"],
div[data-testid="stButton"] > button[kind="primary"] {
  background-color: #006338;
  background: linear-gradient(180deg, #007243 0%, #006338 100%);
  color: #ffffff; border: 1px solid #006338; border-radius: 6px;
  font-weight: 500; }
.stApp .stButton > button[kind="primary"]:hover,
div[data-testid="stButton"] > button[kind="primary"]:hover {
  background-color: #007243;
  background: linear-gradient(180deg, #007a4d 0%, #007243 100%);
  border-color: #007243; color: #ffffff; }
/* ---- secondary buttons: dark panel, 1px border, bright text ---- */
.stApp .stButton > button[kind="secondary"],
div[data-testid="stButton"] > button[kind="secondary"] {
  background-color: #232625; color: #edefee; border: 1px solid #363636;
  border-radius: 6px; font-weight: 500; }
.stApp .stButton > button[kind="secondary"]:hover,
div[data-testid="stButton"] > button[kind="secondary"]:hover {
  background-color: #2a2d2c; color: #edefee; border-color: #363636; }
/* Danger buttons (delete / clear / reset / remove) are secondary buttons
   (type="secondary", never primary). See the light stylesheet for why
   the danger colour lives on this .dcs-danger hook. */
.dcs-danger button[kind="secondary"] { color: #ff6369 !important;
  border-color: #ff6369 !important; }
div[data-testid="stDownloadButton"] > button {
  background-color: #232625; color: #edefee; border: 1px solid #363636;
  border-radius: 6px; }
/* ---- inputs: dark panel, 6px radius, hairline border ---- */
.stApp input, .stApp textarea, .stApp select {
  background-color: #232625; color: #edefee;
  border-color: #2e2e2e; border-radius: 6px; }
.stApp label { color: #edefee; }
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
.dcs-kpi .dcs-kpi-label { font-size: 11px; font-weight: 600;
  letter-spacing: 0.08em; text-transform: uppercase; color: #989a99; }
.dcs-kpi .dcs-kpi-value { font-size: 20px; font-weight: 500;
  color: #edefee; font-family: ui-monospace, "SF Mono", Menlo, monospace; }
.dcs-kpi .dcs-kpi-sub { font-size: 13px; color: #989a99; }
/* ---- file-uploader dropzone + uploaded-file chips: bright on dark ---- */
div[data-testid="stFileUploader"], div[data-testid="stFileUploader"] * {
  color: #edefee !important; }
div[data-testid="stFileUploaderDropzone"] {
  background-color: #232625; border-color: #2e2e2e; }
/* ---- info / success / warning / error boxes: dark panel, bright text ---- */
div[data-testid="stAlert"] { background-color: #232625;
  border-color: #2e2e2e; }
div[data-testid="stAlert"], div[data-testid="stAlert"] * {
  color: #edefee !important; }
div[data-testid="stAlert"] a { color: #4acd8b !important; }
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
  background-color: #262928; color: #edefee; font-weight: 600;
  border-bottom: 1px solid #2e2e2e; font-size: 13px; }
div[data-testid="stDataFrame"] td, div[data-testid="stTable"] td {
  background-color: #232625; color: #edefee;
  border-bottom: 1px solid #2e2e2e; font-size: 13px; }
/* ---- motion, honestly measured: colour-only 0.2s ease-out ---- */
.stApp .stButton > button, .stApp a, .dcs-nav-row,
div[data-testid="stRadio"] div[role="radiogroup"] label,
.stApp input, .stApp textarea, .stApp select {
  transition: background-color 0.2s cubic-bezier(0.22, 1, 0.36, 1),
    border-color 0.2s cubic-bezier(0.22, 1, 0.36, 1),
    color 0.2s cubic-bezier(0.22, 1, 0.36, 1); }
/* ---- focus: one shared ring — 2px dark gap + 4px translucent green halo ---- */
.stApp .stButton > button:focus-visible,
div[data-testid="stDownloadButton"] > button:focus-visible,
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
input[maxlength="6"] { font-family: monospace; font-size: 18px;
  letter-spacing: .35em; }
div[data-testid="stButton"] > button[kind="tertiary"] {
  background: transparent; border: none; box-shadow: none;
  color: #4acd8b; font-size: 13px; padding: 0.25rem 0; min-height: 0; }
div[data-testid="stButton"] > button[kind="tertiary"]:hover {
  background: transparent; color: #4acd8b; text-decoration: underline; }
div[data-testid="stHorizontalBlock"] div[data-testid="column"]:last-child
  div[data-testid="stButton"]:has(> button[kind="tertiary"]) {
  display: flex; justify-content: flex-end; }
/* ---- branded loader: dark twin of the light rules above — same
   mark, same keyframes, same timing; only the text/shimmer colours
   change (muted #989a99, name #edefee, track #2e2e2e, shimmer
   gradient brightened to the dark link green #4acd8b). */
.dcs-loader { text-align: center; padding: 2.5rem 1rem 2rem; }
.dcs-loader-mark { position: relative; margin: 0 auto 16px;
  animation: dcs-lm-breathe 1.8s ease-in-out 1.15s infinite alternate; }
.dcs-loader--large .dcs-loader-mark { width: 96px; height: 96px; }
.dcs-loader--compact { text-align: left; padding: 0.5rem 0; }
.dcs-loader--compact .dcs-loader-row { display: flex; align-items: center;
  gap: 12px; }
.dcs-loader--compact .dcs-loader-mark { width: 40px; height: 40px;
  margin: 0; flex: none; }
.dcs-loader-mark > div { position: absolute; inset: 0;
  background-image: var(--dcs-logo); background-size: 100% 100%;
  background-repeat: no-repeat; }
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
  .dcs-loader-mark, .dcs-loader-mark > div, .dcs-loader-shimmer i {
    animation: none !important; } }
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


def render_theme_toggle(st_module=None) -> str:
    """Render the Light/Dark switch in the sidebar and return the
    theme now in effect. The switch is a selectbox whose widget key
    *is* ``st.session_state["dcs_theme"]`` ("light" by default), so
    picking a theme persists for the session and the stylesheet
    injected at the top of the app follows it on the next rerun —
    login screen included. No behaviour change: the toggle only
    swaps the stylesheet."""
    st_mod = st_module or st
    current = normalize_theme(
        st_mod.session_state.get("dcs_theme", THEME_DEFAULT))
    st_mod.sidebar.selectbox(
        "Theme", options=list(THEMES),
        format_func=lambda t: "Dark" if t == "dark" else "Light",
        key="dcs_theme",
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
        st_mod.session_state["dcs_theme"] = (
            "light" if current == "dark" else "dark")
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
    is layered four times over ONE base64 data URI, set inline as the
    ``--dcs-logo`` custom property on the container (see the
    ``.dcs-loader`` rules in the stylesheets), so the 571KB logo file
    is inlined once, not four times. ``size`` is ``"large"`` (96px
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
             '<div class="dcs-lm-bar1"></div>'
             '<div class="dcs-lm-bar2"></div>'
             '<div class="dcs-lm-bar3"></div>'
             '<div class="dcs-lm-check"></div></div>')
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
    return ('<div class="dcs-loader dcs-loader--' + _size +
            '" style="--dcs-logo: url(\'' + _uri + '\')">' +
            _body + "</div>")


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


def avatar_initial(user) -> str:
    """First letter of the display name (or username, or email) for the
    sidebar avatar circle; ``"?"`` when nothing is set. Upper-cased,
    so "md ahmad" and "Md Ahmad" both give ``"M"``."""
    name = ((user or {}).get("display_name")
            or (user or {}).get("username")
            or (user or {}).get("email") or "?")
    return (str(name).strip()[:1].upper() or "?")


def render_sidebar_avatar(st_module=None, user=None):
    """Render the sidebar avatar: a single green circle with the
    user's initial (see ``avatar_initial``), the only profile element
    in the sidebar. Clicking it opens a menu with the email (shown
    here, and only here, in the sidebar), a Profile action, and
    Log out. Returns ``"profile"`` when Profile was clicked,
    ``"logout"`` when Log out was clicked, else ``None`` — the caller
    acts on it (open the Profile tab / log out). The circle itself is
    styled by the design system CSS (``stPopoverButton`` rules); the
    popover is the honest Streamlit menu — no overlay palette exists
    in Streamlit, and the trigger button is the avatar."""
    st_mod = st_module or st
    email = str((user or {}).get("email") or "")
    # Both buttons are always created, every run: returning early on the
    # Profile click would skip the Log out button for that run, leaving
    # the menu half-built. Collect the action, return after the menu.
    action = None
    with st_mod.sidebar.popover(avatar_initial(user), key="avatar_menu"):
        if email:
            st_mod.caption(email)
        if st_mod.button("Profile", key="avatar_profile_btn"):
            action = "profile"
        if st_mod.button("Log out", key="avatar_logout_btn"):
            action = "logout"
    return action


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
