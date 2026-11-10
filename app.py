"""Data Cleaner Studio — web version (Streamlit).

Port of the desktop .exe app (~/workspace/data-cleaner-studio/
simple_app.py, v1.4 feature set): load a messy file -> profile it ->
clean it -> KPIs -> dashboard -> report. Same engine, same cleaning
logic, same results as the .exe.

Web differences (all deliberate):
* PHASE 2 — SUPABASE WIRED IN. The cloud userbase is integrated:
  auth.py picks the Supabase backend whenever supabase_config.json
  (or SUPABASE_URL / SUPABASE_ANON_KEY) is present, and Settings
  shows the connection status. With no config the app still runs in
  LOCAL MODE (SQLite accounts) — local mode is the default, not a
  fallback error. No Supabase project exists yet, so the cloud path
  is structural only until the user creates the free project and
  adds the config (see README.md / DEPLOY.md section 0).
* AUTH GATE FIRST: nobody sees data without a valid session (auth.py —
  backend-agnostic API: create_user / authenticate / create_session /
  validate_session / delete_session). Sessions live in
  st.session_state and are validated with auth.validate_session on
  every run. The token is ALSO kept in a browser cookie (7 days, the
  same as auth.SESSION_TTL) so a page refresh does not log the user
  out — only the random token is stored, never a password. If the
  cookie library is missing, the app falls back to session-state-only
  behaviour. Passwords are never stored or logged. If the auth
  backend reports a problem, auth.get_backend_warning() says so
  plainly and the app shows that message instead of crashing.
* GOOGLE SIGN-IN: wired to auth.get_google_sign_in_url() /
  auth.handle_oauth_code() (Supabase Auth OAuth). In local mode
  those return None / a clean error, so the login screen shows a
  plain "needs Supabase" note instead of a button — never a crash.
  The button is ALSO gated on the GOOGLE_OAUTH_ENABLED flag
  (Streamlit secrets or environment, default OFF — only
  true/True/"true"/"1" switch it on), because the Google provider
  is not enabled in Supabase: with the flag off the button stays
  hidden even when Supabase is up. See _google_oauth_enabled().
  The OAuth callback (?code=...) is exchanged once and the code is
  cleared from the URL immediately (see _consume_oauth_callback).
  Google sign-in also needs Google enabled in the Supabase
  dashboard (Authentication -> Providers -> Google) — see DEPLOY.md.
* PER-USER STORAGE: every file operation goes through storage.py with
  the logged-in user's storage key (uploads/, cleaned/, recipes/,
  views/, workspaces/ under data/users/<key>/). Files persist across
  sessions. No file path is ever built from user input by hand.
* The .exe's app-folder files (settings.json, brand.json, views.json,
  recent.json, backups/, workspace/, versions.json) are repointed
  per user at login (see _apply_user_paths). NOTE: that repointing
  sets module-level paths, so it is per-process, not per-session —
  fine for one user at a time / low concurrency, but two users
  hitting the server in the same instant share those globals. The
  hard isolation (auth sessions, storage folders, share snapshots)
  does not depend on the globals.
* SHARING: a read-only dashboard link (?share=<token>) resolves to a
  stored snapshot only — never to a live file or another user's data.
* SETTINGS tab: backend status, API keys (your own Groq/Gemini keys,
  stored per user), white-label brand, scheduler jobs, share links.
"""

from __future__ import annotations

import contextlib
import hashlib
import html
import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

import ai_settings
import auth
import engine
import feat_analyse
import feat_automate
import feat_brand
import feat_combine
import feat_enrich
import feat_export
import feat_mobile
import feat_profile
import feat_quality
import feat_quickjump
import feat_schedule
import feat_share
import feat_status
import feat_tutorial
import scheduler
import storage
import ui_design
import ui_loading

try:
    from auth import AuthServiceError
except ImportError:  # Cloud rework: fall back to a local stand-in
    class AuthServiceError(Exception):
        """Auth service error (fallback if auth.py does not define it)."""

_APP_DIR = Path(__file__).resolve().parent

# -------------------------------------------- design system (Supabase) --
# The app's consolidated stylesheets, one per theme: light below
# (near-white background, white cards, near-black ink, one deep-green
# accent) and dark in ui_design.DARK_CSS (near-black green-grey
# surfaces, brightened green accents). Injected at the top of the app
# (right after set_page_config, below) so the login / signup screen
# gets them too — the deep-green primary-button rules here are the
# fallback if the [theme] section of .streamlit/config.toml is ever
# missing. The light literal below is ui_design.DESIGN_SYSTEM_CSS
# pasted verbatim: the Supabase tokens measured off the live dashboard
# (see supabase-design-study.md and the authoritative vibe brief in
# supabase-ui-ux-design-analysis.md). There are exactly two stylesheets
# to maintain, both owned by ui_design.py; do not retype or re-derive
# either. Which one is injected is decided just before the inject call
# from st.session_state["dcs_theme"] ("light" by default).
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
section[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"]:hover {
  background-color: #f8f8f8 !important; }
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
/* ---- disabled inputs (Profile's read-only Primary email +
   Username): the light twin of the dark fill pin below.
   Streamlit's native disabled styling renders the text in a
   faint grey on the white panel (live: darkest pixel #A0A0A0,
   2.61:1, while 'Member since' is #030303 at 20.62:1) —
   pre-existing, not a regression. Pin the text dark and the
   panel one step off white, so the field still reads as
   disabled but the value is legible. The ``color`` pin alone
   is NOT enough: Chromium paints disabled input text with
   ``-webkit-text-fill-color``, not ``color`` — the round-7
   probe read computed ``color`` (#030303, correct) and missed
   that the fill sat at rgba(3,3,3,0.4), so the fields stayed
   faint live. The fill pin below is the actual fix (round 10;
   dark got its twin in round 8, verified live 13.67:1). ---- */
.stApp input:disabled, .stApp textarea:disabled, .stApp select:disabled {
  color: #030303 !important; -webkit-text-fill-color: #030303 !important;
  background-color: #f3f3f3 !important;
  border-color: #e0e0e0 !important; opacity: 1 !important; }
div[data-testid="stTextInput"] input:disabled {
  color: #030303 !important; -webkit-text-fill-color: #030303 !important;
  background-color: #f3f3f3 !important; }
/* ---- Profile light disabled fields, per-key pin (round 10):
   belt-and-braces twin of the dark per-key pin — the two
   global rules above already paint dark in the local
   Supabase-mode probe, but the dark fields stayed dim live
   until the per-key rule landed (round 9), so the light
   fields get the same key-scoped rule, sitting later in the
   sheet so it wins over any competing rule. ---- */
.st-key-profile_primary_email input:disabled,
.st-key-profile_username input:disabled {
  color: #030303 !important; -webkit-text-fill-color: #030303 !important;
  background-color: #f3f3f3 !important; opacity: 1 !important; }
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
/* ---- Quick Jump results wrap instead of truncating: the
   "Label — hint" buttons are long and the top-bar search column
   is narrow — the longest label clipped mid-word live
   ("…on your Wi"). Inside the popover the buttons wrap to two
   lines and left-align; the Search pill's expand_more chevron is
   hidden (the pill reads clean, like the dashboard's). Key-scoped
   (st-key-quickjump_popover / st-key-quickjump_go_*), so no other
   popover or button is touched. ---- */
div[data-testid="stLayoutWrapper"][class*="st-key-quickjump_popover"] button[data-testid="stPopoverButton"] > div > div[aria-hidden="true"] {
  display: none !important; }
div[class*="st-key-quickjump_go"] button[data-testid="stBaseButton-secondary"] {
  white-space: normal !important; height: auto !important;
  text-align: left !important; }
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
/* ---- Dashboard Overview: URL row under the H1 + infra diagram
   canvas (Supabase's Project Overview diagram, mapped to this
   app's pipeline: Upload → Clean → KPIs → Export). No diagram/map
   toggle: there is no map counterpart in this app, so the diagram
   is the only view. Dots use the checkbox-border token, never a
   new hex — the token tests pin every hex in both sheets. */
.dcs-overview-url { font-size: 13px; color: #696969;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dcs-infra-canvas { background-color: #ffffff; border: 1px solid #e8e8e8;
  border-radius: 12px; padding: 1rem;
  background-image: radial-gradient(circle, #d0d0d0 1px, transparent 1px);
  background-size: 16px 16px; }
.dcs-infra-row { display: flex; align-items: stretch; gap: 0.5rem; }
.dcs-infra-node { flex: 1; min-width: 0; background-color: #ffffff;
  border: 1px solid #e8e8e8; border-radius: 8px; padding: 0.75rem; }
.dcs-infra-node-title { font-size: 11px; font-weight: 600;
  letter-spacing: 0.08em; text-transform: uppercase; color: #696969; }
.dcs-infra-node-count { font-size: 20px; font-weight: 500; color: #030303;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  margin-top: 0.25rem; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; }
.dcs-infra-node-sub { font-size: 12px; color: #696969; margin-top: 0.25rem;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dcs-infra-arrow { flex: none; display: flex; align-items: center;
  font-size: 18px; color: #696969; }
</style>"""

st.set_page_config(page_title="Data Cleaner Studio", layout="wide",
                   page_icon=str(_APP_DIR / "assets" / "favicon.png"))

# --------------------------------------- persisted preferences (Round 3) --
# The theme preference + rail mode survive a full page reload in
# browser cookies (the login cookie's machinery, reused — see the
# login-cookie section further down). The restore runs HERE, before
# the stylesheet is injected, so the first paint already uses the
# restored theme/rail instead of flashing the defaults. It seeds keys
# that are absent from session state — or that were defaulted because
# no cookie was visible yet and one has since arrived (the cookie
# component's snapshot only exists after it mounts). Once seeded from
# cookies the in-session choice is never overwritten. The OS reading
# is the exception — it is a sensor value, not a choice, so it
# refreshes on every run from the freshest cookie source.
def _request_cookies():
    """Cookies the browser sent with this session's initial request
    (the WebSocket handshake), or {} when unavailable.

    A snapshot from session start: a cookie written during this
    session does NOT appear here until the next page load. Never
    raises."""
    try:
        cookies = st.context.cookies
    except Exception:  # noqa: BLE001 - no request context (AppTest, …)
        return {}
    try:
        return dict(cookies)
    except Exception:  # noqa: BLE001 - not a mapping: treat as empty
        return {}


def _all_browser_cookies():
    """All cookies visible to this run: the request cookies merged
    with the cookie component's snapshot in session state. The
    snapshot wins on conflict — it is the freshest read (it picks
    up cookies written during this session after a refresh), while
    the request cookies are the session-start snapshot. Never
    raises; {} when nothing is visible yet.

    The snapshot's values are NOT always strings: the component
    JSON-parses them, so a numeric-looking cookie ("1") arrives
    as an int (1) — and a cookie is a string, so coerce scalars
    back. Without this the OS reading (``dcs_os_dark`` "0"/"1")
    is dropped by the string-only merge below and System follows
    the stale request cookie instead of the fresh snapshot."""
    merged = {}
    for _k, _v in _request_cookies().items():
        if isinstance(_v, str):
            merged[_k] = _v
    try:
        stored = st.session_state.get("cookies")
    except Exception:  # noqa: BLE001 - no session state yet
        stored = None
    if isinstance(stored, dict):
        for _k, _v in stored.items():
            if isinstance(_v, str):
                merged[_k] = _v
            elif isinstance(_v, bool):
                merged[_k] = "true" if _v else "false"
            elif isinstance(_v, (int, float)):
                merged[_k] = str(_v)
    return merged


def _restore_prefs_from_cookies():
    """Seed the theme preference, rail mode and OS reading from
    the persisted cookies — before first paint (see the block
    comment above). Invalid values are ignored
    (ui_design.restore_pref_values validates); missing cookies
    leave the defaults alone. The OS reading refreshes on every
    run (sensor, not a choice). The preference + mode seed when
    their session keys are absent — OR when they were defaulted
    because no cookie was visible yet (``_prefs_from_cookies``
    unset) and a cookie has since arrived: the cookie component's
    snapshot only exists after it mounts, so on a run where the
    request cookies are unavailable the values land one run late
    instead of never. Once seeded from cookies the flag sticks
    and the in-session choice is never overwritten — a user change
    can only happen after the first run, by which time the
    snapshot exists. Never raises: a broken restore falls back
    to the defaults."""
    try:
        _restored = ui_design.restore_pref_values(_all_browser_cookies())
    except Exception:  # noqa: BLE001 - a broken restore never
        return  # blocks first paint; defaults apply instead.
    _from_cookies = bool(st.session_state.get("_prefs_from_cookies"))
    _seeded_now = False
    if "theme_pref" in _restored:
        if (ui_design.THEME_PREF_KEY not in st.session_state
                or not _from_cookies):
            st.session_state[ui_design.THEME_PREF_KEY] = (
                _restored["theme_pref"])
            _seeded_now = True
    if "rail_mode" in _restored:
        if (ui_design.RAIL_MODE_KEY not in st.session_state
                or not _from_cookies):
            st.session_state[ui_design.RAIL_MODE_KEY] = (
                _restored["rail_mode"])
            _seeded_now = True
    if _seeded_now:
        st.session_state["_prefs_from_cookies"] = True
    if "os_dark" in _restored:
        st.session_state[ui_design.OS_DARK_KEY] = _restored["os_dark"]
    elif ui_design.OS_DARK_KEY not in st.session_state:
        st.session_state[ui_design.OS_DARK_KEY] = None


_restore_prefs_from_cookies()

# Injected before the login view renders (and before the share-link
# handling below), so the auth screen gets the design system too.
# Which stylesheet: st.session_state["dcs_theme"] ("light" by default,
# flipped by the sidebar toggle and the login-screen switch — both in
# ui_design). The theme tests read the light literal above from source,
# so this rebinding keeps the name DESIGN_SYSTEM_CSS on the injected
# value; the .streamlit/config.toml [theme] base="light" stays as the
# first-paint base only, since Streamlit's native theme is static.
st.session_state.setdefault("dcs_theme", "light")
# Sync the theme widgets to the theme in effect BEFORE any theme
# widget is created this run (top-bar avatar radio, sidebar
# selectbox) — see ui_design.sync_theme_widgets: without this, a
# theme flipped from the login link or the avatar menu leaves the
# sidebar dropdown showing the old theme.
ui_design.sync_theme_widgets()
DESIGN_SYSTEM_CSS = ui_design.theme_css(
    st.session_state.get("dcs_theme") or "light")
st.markdown(DESIGN_SYSTEM_CSS, unsafe_allow_html=True)
# Sidebar rail state + stylesheet (ui_design.rail_css): the mode is
# Supabase's 3-way Sidebar behavior (Expanded / Collapsed / Expand
# on hover), default Expand on hover — the collapsed icon rail is
# Supabase's default, so the rail starts collapsed and remembers its
# state across reruns in session state, like dcs_theme. Injected
# right after the design system so its rules win on equal
# specificity.
st.session_state.setdefault("dcs_rail_collapsed", True)
_rail_mode = ui_design.rail_mode()
st.session_state[ui_design.RAIL_MODE_KEY] = _rail_mode
st.session_state["dcs_rail_collapsed"] = _rail_mode != "expanded"
st.markdown(ui_design.rail_css(
    _rail_mode != "expanded",
    st.session_state.get("dcs_theme") or "light",
    hover=(_rail_mode == "hover")),
    unsafe_allow_html=True)
# OS-preference bridge (Round 3): a zero-height script that mirrors
# prefers-color-scheme into the dcs_os_dark cookie, so a "System"
# theme preference follows the OS on the next run / reload. It runs
# on the login screen too (injected here, before the login view),
# takes no space, and never raises — in AppTest it is an inert
# iframe element.
try:
    st.components.v1.html(ui_design.OS_DARK_BRIDGE_HTML, height=0)
except Exception:  # noqa: BLE001 - no OS bridge without components
    pass
# Quick-jump keyboard bridge (Round 3c): a zero-height script
# that lets Enter / ArrowDown / ArrowUp pick a result while the
# top-bar search box is focused (see
# feat_quickjump.QUICKJUMP_KEYS_BRIDGE_HTML). Same pattern as the
# OS bridge above; a failure leaves the palette mouse-only, never
# crashes — in AppTest it is an inert iframe element.
try:
    st.components.v1.html(feat_quickjump.QUICKJUMP_KEYS_BRIDGE_HTML,
                           height=0)
except Exception:  # noqa: BLE001 - no keyboard bridge without components
    pass
# Rhythm (ui_loading): 1280px container cap + section-gap helpers,
# injected once per run right after the design system.
ui_loading.inject_rhythm()
_SHARES_FILENAME = "shares.json"
_STORAGE_KEY_RE = re.compile(r"^[a-zA-Z0-9_]{3,30}$")

# The deployed app's public address, used for the full share link.
# Override it with the APP_PUBLIC_URL (or APP_URL) environment
# variable or Streamlit secret when the app moves to a new address.
# Default: the live Streamlit Community Cloud URL for this app.
_DEFAULT_APP_URL = "https://datacleanerstudio.streamlit.app"

# The public repository, for the Dashboard "Copy" menu (the second
# address in Supabase's Copy menu, beside the project URL).
_REPO_URL = "https://github.com/sheikh-ahmad-am/data-cleaner-studio-web"


def _app_base_url() -> str:
    """This app's public web address, for the full share link.

    APP_PUBLIC_URL / APP_URL (environment, then Streamlit secrets)
    wins when set; otherwise the known deployed URL above. Never a
    "<your-app>" placeholder — the example link must be openable."""
    raw = (os.environ.get("APP_PUBLIC_URL")
           or os.environ.get("APP_URL") or "").strip()
    if not raw:
        try:
            raw = str(st.secrets.get("APP_PUBLIC_URL", "")
                      or st.secrets.get("APP_URL", "") or "").strip()
        except Exception:  # noqa: BLE001 - no secrets file: use the default
            raw = ""
    return (raw or _DEFAULT_APP_URL).rstrip("/")


# ------------------------------------------------------------- sharing ----
def _find_share(token: str):
    """Resolve a share token to its stored snapshot dict, or None.

    Scans data/users/*/views/shares.json (read-only). The token maps
    to a stored snapshot — never to a live path or another user's
    files, so a shared link can only ever show what its owner saved
    into it at share time.
    """
    if not isinstance(token, str) or not token:
        return None
    base = storage.BASE_DIR
    if not base.is_dir():
        return None
    for user_dir in sorted(base.iterdir()):
        if not user_dir.is_dir():
            continue
        shares_file = user_dir / "views" / _SHARES_FILENAME
        if not shares_file.is_file():
            continue
        try:
            registry = json.loads(shares_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if isinstance(registry, dict) and token in registry:
            snap = registry.get(token)
            if isinstance(snap, dict):
                return snap
    return None


def _render_shared_dashboard(snapshot: dict) -> None:
    """Render ONLY a shared dashboard: no login, no sidebar, no data
    beyond the stored snapshot."""
    st.title(snapshot.get("title") or "Shared dashboard")
    st.caption(
        "Shared read-only view from Data Cleaner Studio. "
        f"Shared on {snapshot.get('created_at', 'an unknown date')}. "
        "This link shows a saved snapshot — it cannot open any other data.")
    kpis = snapshot.get("kpis") or []
    if kpis:
        cols = st.columns(3)
        for i, k in enumerate(kpis):
            if isinstance(k, dict):
                cols[i % 3].metric(str(k.get("label", "")),
                                   str(k.get("value", "")))
    rows = snapshot.get("rows") or []
    if rows:
        ui_design.section_heading("The numbers behind the chart")
        try:
            st.dataframe(pd.DataFrame(rows), width="stretch")
        except Exception:  # noqa: BLE001 - a bad snapshot must still render
            st.write(rows)
    else:
        ui_design.info_card(
            "This shared dashboard has no chart data saved in it.")


_share_token = None
try:
    _qp = st.query_params
    _share_token = _qp.get("share")
except Exception:  # noqa: BLE001 - no query params, no share link
    _share_token = None
if _share_token:
    _snap = _find_share(str(_share_token))
    if _snap is None or _snap.get("revoked"):
        st.error("This share link was revoked or does not exist.")
        st.write("Ask the person who shared it for a new link.")
        st.stop()
    _render_shared_dashboard(_snap)
    st.stop()


# ------------------------------------------------------- storage key ------
def _storage_key(user: dict) -> str:
    """The storage folder key for a user.

    Local mode: the username itself (already [a-zA-Z0-9_]{3,30}).
    Cloud mode: username == email, which storage.py rejects as a
    folder name — so use a stable hash-derived key instead
    ("u_" + first 20 hex chars of sha256(email)). Same user, same
    folder, every time; no two emails can collide in practice, and
    the key never contains the email itself.
    """
    name = str(user.get("username") or "")
    if _STORAGE_KEY_RE.match(name):
        return name
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:20]
    return f"u_{digest}"


def _apply_user_paths(user: dict, skey: str) -> dict:
    """Repoint every .exe-style app-folder file to this user's folder.

    Returns {"root", "ws_dir", "settings_path"} for the callers that
    need them. See the module docstring for the per-process caveat.
    """
    root = storage.user_root(skey)
    settings_path = root / "views" / "settings.json"
    ai_settings.SETTINGS_PATH = settings_path
    feat_analyse.VIEWS_FILE = root / "views" / "views.json"
    feat_analyse.SEEN_VERSION_FILE = root / "views" / "seen_version.json"

    def _versions_file(path=None):
        if path is not None:
            return Path(path)
        return root / "views" / "versions.json"

    feat_enrich._versions_file = _versions_file
    ws_dir = root / "workspaces"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return {"root": root, "ws_dir": ws_dir, "settings_path": settings_path}


# ------------------------------------------------------------- auth gate --
for key, default in [
    ("auth_token", None), ("current_user", None), ("storage_key", None),
    ("user_paths", None), ("auth_mode", "Log in"),
    ("pending_code", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ------------------------------------------- login cookie (refresh-proof) --
# The session token ALSO lives in a browser cookie (7 days, the same
# as auth.SESSION_TTL) so refreshing the page does not log the user
# out. Only the random token is stored — never a password. If the
# cookie library is missing at runtime, the app falls back to the
# old session-state-only behaviour without crashing.
#
# Two timing facts shape this code (both verified against the
# library + Streamlit 1.66.1 source, 2026-11-07):
#   * WRITE: a cookie write goes through a component iframe, which
#     writes document.cookie when it mounts. A write issued in a
#     run that ends with an immediate st.rerun() is LOST — the
#     rerun tears the iframe down before it mounts. That is why
#     _remember_session() only MARKS the cookie pending and the
#     write happens in _ensure_login_cookie(), in a run that
#     completes normally (see below).
#   * READ: the component's snapshot is empty on the first run
#     after a refresh (its iframe has not answered yet). The
#     request cookies (st.context.cookies, sent with the session's
#     initial WebSocket handshake) ARE present on that first run,
#     so they are read first.
_AUTH_COOKIE = "dcs_auth_token"
_AUTH_COOKIE_MAX_AGE = 7 * 24 * 3600  # seconds; matches auth.SESSION_TTL
_AUTH_COOKIE_VERIFY_RETRIES = 3  # re-issues of a lost cookie write

try:
    from streamlit_cookies_controller import CookieController
    _cookie_controller = CookieController()
except Exception:  # noqa: BLE001 - no cookie library: session-state only
    _cookie_controller = None


def _controller_cookie_get(name):
    """Cookie value from the controller's snapshot, or None."""
    if _cookie_controller is None:
        return None
    try:
        value = _cookie_controller.get(name)
    except Exception:  # noqa: BLE001 - a cookie read never crashes login
        return None
    return value if isinstance(value, str) and value else None


def _cookie_get(name):
    """Cookie value, or None when cookies are unavailable/empty.

    The request cookies come first: they are present on the very
    first run after a page load/refresh, when the controller's
    snapshot is still empty (its iframe has not answered yet)."""
    request_value = _request_cookies().get(name)
    if isinstance(request_value, str) and request_value:
        return request_value
    return _controller_cookie_get(name)


def _cookie_read_resolved():
    """True when an empty cookie read can be trusted to mean 'no cookie'.

    The request cookies are authoritative from the first run: if
    the browser had the login cookie it would be in them. When
    there is no request context, the read only counts as resolved
    once the cookie component has registered its value (the
    'cookies' key in session state) — before that, an empty read
    means 'not loaded yet', not 'logged out'."""
    if _request_cookies():
        return True
    return "cookies" in st.session_state


def _controller_refresh():
    """Ask the cookie component for a fresh browser read (no-op when
    the cookie library is missing or its controller has no refresh).
    The fresh snapshot arrives on the next run. Never raises."""
    if _cookie_controller is None:
        return
    refresh = getattr(_cookie_controller, "refresh", None)
    if refresh is None:
        return
    try:
        refresh()
    except Exception:  # noqa: BLE001 - a refresh never crashes login
        pass


def _cookie_set(name, value, max_age=None):
    """Store a cookie: 7-day expiry by default (the login cookie),
    Secure, SameSite=Lax. ``max_age`` overrides the expiry —
    preference cookies pass a year, so a choice is not a session."""
    if _cookie_controller is None:
        return
    try:
        _cookie_controller.set(
            name, value,
            max_age=(max_age if max_age is not None
                     else _AUTH_COOKIE_MAX_AGE),
            secure=True, same_site="lax")
    except Exception:  # noqa: BLE001 - a cookie write never crashes login
        pass


def _cookie_clear(name):
    """Remove a cookie (same attributes it was set with)."""
    if _cookie_controller is None:
        return
    try:
        _cookie_controller.remove(name, secure=True, same_site="lax")
    except Exception:  # noqa: BLE001 - a cookie clear never crashes logout
        pass


def _remember_session(token):
    """Persist a login in session state and mark the login cookie
    for writing.

    The cookie itself is NOT written here: this runs in the login
    run, which ends with an immediate st.rerun() — and a cookie
    write issued in that run is lost, because the component iframe
    that performs the write is torn down before it mounts (verified
    2026-11-07, see the module comment above). The write happens
    in _ensure_login_cookie(), on the next run, which completes
    normally — and is verified + retried there."""
    st.session_state["auth_token"] = token
    st.session_state["_auth_cookie_pending"] = token
    st.session_state["_auth_cookie_retries"] = 0
    st.session_state.pop("_auth_cookie_gave_up", None)


def _do_logout():
    """The ONE logout path: invalidate the server session, clear the
    login cookie, null the session keys and rerun to the login screen.
    Used by the sidebar Log out button and the Profile section."""
    try:
        auth.delete_session(st.session_state.get("auth_token"))
    except AuthServiceError:
        pass
    _cookie_clear(_AUTH_COOKIE)
    for _k in ("auth_token", "current_user", "storage_key", "user_paths",
               "raw", "clean", "actions", "kpis", "pending_code"):
        st.session_state[_k] = None
    # The Account radio ("Log in" / "Sign up") sticks on "Sign up"
    # after a sign-up: without this, logging out lands the user on the
    # Create-account form instead of the login screen. The radio is not
    # rendered in a logout run (login screen only), so assigning its key
    # here is safe — unlike active_tab above.
    st.session_state["auth_mode"] = "Log in"
    # "active_tab" is the Section radio's widget key: assigning it after
    # the radio was created in this run (a logout from the Profile
    # section) raises — deleting it is allowed at any point, and the
    # next login then lands on the first section again.
    try:
        del st.session_state["active_tab"]
    except KeyError:
        pass
    st.rerun()


def _log_user_in(user):
    """Start a session for an authenticated user dict and persist it
    (session state + login cookie) — the one path the Log in button
    and the auto-login after sign-up both use. Returns True when the
    session is live, False when no session could be started (the
    caller shows the error)."""
    try:
        token = auth.create_session(user["id"])
    except AuthServiceError as exc:
        st.error(f"Account service error: {exc}")
        return False
    if not token:
        st.error("Could not start a session. Try again.")
        return False
    _remember_session(token)
    st.session_state["current_user"] = user
    st.session_state["storage_key"] = _storage_key(user)
    return True


def _restore_session_from_cookie():
    """On startup, when session state has no token: read the token
    from the login cookie and validate it with auth.validate_session.

    Returns the user dict when the cookie holds a live session (and
    restores session state), else None — and clears a dead/expired
    cookie so a stale token never lingers. Never raises."""
    if st.session_state.get("auth_token"):
        return None
    token = _cookie_get(_AUTH_COOKIE)
    if not token:
        return None
    try:
        user = auth.validate_session(token)
    except AuthServiceError:
        user = None
    except Exception:  # noqa: BLE001 - a broken backend never crashes login
        return None
    if user is None:
        _cookie_clear(_AUTH_COOKIE)
        return None
    st.session_state["auth_token"] = token
    st.session_state["current_user"] = user
    st.session_state["storage_key"] = _storage_key(user)
    return user


def _ensure_login_cookie():
    """Keep the login cookie in the browser while logged in.

    Runs on every logged-in run (after the auth gate). Two jobs:
      * WRITE: after a login the cookie is only marked pending
        (see _remember_session) — issue the write here, in a run
        that completes normally, so the component iframe that
        performs it actually mounts and writes.
      * VERIFY: a write can still be lost (the browser blocks
        cookies, the tab closes too fast). The controller's
        snapshot is optimistically updated by set(), so it cannot
        confirm a write on its own — refresh() re-reads the
        browser and the fresh snapshot arrives on the next run.
        While a write is pending, re-issue it when the fresh read
        still lacks the token, up to _AUTH_COOKIE_VERIFY_RETRIES
        times. A cookie the browser really sent with the page
        request counts as confirmed. After the retries are spent,
        give up quietly for this token (the session-state login
        still works for this session; the next login retries the
        write). Never raises."""
    token = st.session_state.get("auth_token")
    if not token:
        st.session_state.pop("_auth_cookie_pending", None)
        st.session_state.pop("_auth_cookie_retries", None)
        st.session_state.pop("_auth_cookie_gave_up", None)
        return
    if _cookie_controller is None:
        return
    # Confirmed: the browser really sent this token with the page
    # request, so it predates this session — the write stuck.
    if _request_cookies().get(_AUTH_COOKIE) == token:
        st.session_state.pop("_auth_cookie_pending", None)
        st.session_state.pop("_auth_cookie_retries", None)
        st.session_state.pop("_auth_cookie_gave_up", None)
        return
    pending = st.session_state.get("_auth_cookie_pending")
    if pending is None:
        if st.session_state.get("_auth_cookie_gave_up") == token:
            return  # already retried + gave up for this token
        if _controller_cookie_get(_AUTH_COOKIE) == token:
            return  # already in the browser (or just written)
        _cookie_set(_AUTH_COOKIE, token)
        st.session_state["_auth_cookie_pending"] = token
        st.session_state["_auth_cookie_retries"] = 0
        _controller_refresh()
        return
    if pending != token:
        # A different token is pending (re-login in this session):
        # restart the verify cycle for the new token.
        st.session_state["_auth_cookie_pending"] = token
        st.session_state["_auth_cookie_retries"] = 0
        st.session_state.pop("_auth_cookie_gave_up", None)
        _cookie_set(_AUTH_COOKIE, token)
        _controller_refresh()
        return
    # A write is pending: ask the browser for a fresh read and judge
    # by the snapshot it returns on the next run.
    _controller_refresh()
    if _controller_cookie_get(_AUTH_COOKIE) == token:
        st.session_state.pop("_auth_cookie_pending", None)
        st.session_state.pop("_auth_cookie_retries", None)
        st.session_state.pop("_auth_cookie_gave_up", None)
        return
    retries = st.session_state.get("_auth_cookie_retries", 0)
    if retries < _AUTH_COOKIE_VERIFY_RETRIES:
        st.session_state["_auth_cookie_retries"] = retries + 1
        _cookie_set(_AUTH_COOKIE, token)
        _controller_refresh()
    else:
        st.session_state.pop("_auth_cookie_pending", None)
        st.session_state.pop("_auth_cookie_retries", None)
        st.session_state["_auth_cookie_gave_up"] = token


# ---------------------------------------- preference cookies (Round 3) ----
# The theme preference + rail mode are kept in browser cookies
# (``dcs_theme_pref`` / ``dcs_rail_mode``, one year, Secure,
# SameSite=Lax — the same attributes as the login cookie, longer
# lived because a choice is not a session). The write path is
# centralised here on purpose: the six controls that change these
# values (three theme, two rail, one login toggle) all end in
# different places — some in a run that completes normally, some
# in a run aborted by st.rerun() — so no call site writes a
# cookie itself. Instead _ensure_pref_cookies() runs after the
# shell controls have rendered (and before the login screen's
# final stop): it compares the values in effect with the values
# the browser holds and writes only the mismatches, in a run
# that completes normally. A write lost to a later rerun is
# re-issued on the next run, because the desired value is still
# in session state and still mismatched. A default value is
# never written when no cookie exists yet — there is nothing to
# persist, and a fresh install stays cookie-free until the user
# actually changes something.
_PREF_COOKIE_MAX_AGE = 365 * 24 * 3600  # seconds; a choice, not a session
_PREF_COOKIE_VERIFY_RETRIES = 3  # re-issues of a lost cookie write


def _ensure_one_pref_cookie(name, desired, default, state=None,
                            cookie_get=None, cookie_set=None,
                            controller_refresh=None):
    """Keep one preference cookie at ``desired`` (or do nothing).

    ``default`` is the value that needs no cookie: when the
    browser holds no cookie and the desired value IS the default,
    nothing is written. The verify cycle mirrors
    _ensure_login_cookie: a write is pending until the browser
    really holds the value (request cookies, or the controller's
    snapshot after a refresh); a lost write is re-issued up to
    _PREF_COOKIE_VERIFY_RETRIES times, then given up quietly for
    that value — the session-state choice still applies for this
    session, and the next change retries the write. The injectable
    ``cookie_get`` / ``cookie_set`` / ``controller_refresh`` /
    ``state`` exist for tests; the app calls with the defaults.
    Never raises."""
    _state = state if state is not None else st.session_state
    _get = cookie_get if cookie_get is not None else _cookie_get
    _set = cookie_set if cookie_set is not None else _cookie_set
    _refresh = (controller_refresh if controller_refresh is not None
                else _controller_refresh)
    try:
        _desired = str(desired)
    except Exception:  # noqa: BLE001 - no desired value, no write
        return
    if not _desired:
        return
    _pending_key = f"_pref_cookie_pending_{name}"
    _retries_key = f"_pref_cookie_retries_{name}"
    _gave_up_key = f"_pref_cookie_gave_up_{name}"
    try:
        _browser = _get(name)
    except Exception:  # noqa: BLE001 - a broken read never writes
        return
    if _browser == _desired:
        for _k in (_pending_key, _retries_key, _gave_up_key):
            _state.pop(_k, None)
        return
    if _browser is None and _desired == default:
        return  # the default needs no cookie until it changes
    if (_browser is not None and _desired == default
            and not _state.get("_prefs_from_cookies")):
        # No seed from cookies yet: a default in session state is
        # not a choice — the restore has not had its run yet (the
        # cookie layer only answers after it mounts), so the
        # session may still hold the default while the browser
        # holds a real saved value. Never let that default
        # overwrite the saved cookie; the restore seeds the
        # session from it on the next run, and the write then
        # becomes a no-op (browser == desired).
        return
    try:
        _pending = _state.get(_pending_key)
    except Exception:  # noqa: BLE001 - no readable state, no write
        return
    if _pending is None:
        if _state.get(_gave_up_key) == _desired:
            return  # already retried + gave up for this value
        try:
            _set(name, _desired, max_age=_PREF_COOKIE_MAX_AGE)
        except Exception:  # noqa: BLE001 - a failed write retries
            pass
        _state[_pending_key] = _desired
        _state[_retries_key] = 0
        try:
            _refresh()
        except Exception:  # noqa: BLE001 - a refresh never crashes
            pass
        return
    if _pending != _desired:
        _state[_pending_key] = _desired
        _state[_retries_key] = 0
        _state.pop(_gave_up_key, None)
        try:
            _set(name, _desired, max_age=_PREF_COOKIE_MAX_AGE)
        except Exception:  # noqa: BLE001 - a failed write retries
            pass
        try:
            _refresh()
        except Exception:  # noqa: BLE001 - a refresh never crashes
            pass
        return
    try:
        _refresh()
    except Exception:  # noqa: BLE001 - a refresh never crashes
        pass
    try:
        if _get(name) == _desired:
            for _k in (_pending_key, _retries_key, _gave_up_key):
                _state.pop(_k, None)
            return
    except Exception:  # noqa: BLE001 - a broken read retries below
        pass
    try:
        _retries = _state.get(_retries_key, 0)
    except Exception:  # noqa: BLE001 - no readable state, no write
        return
    if _retries < _PREF_COOKIE_VERIFY_RETRIES:
        _state[_retries_key] = _retries + 1
        try:
            _set(name, _desired, max_age=_PREF_COOKIE_MAX_AGE)
        except Exception:  # noqa: BLE001 - a failed write retries
            pass
        try:
            _refresh()
        except Exception:  # noqa: BLE001 - a refresh never crashes
            pass
    else:
        _state.pop(_pending_key, None)
        _state.pop(_retries_key, None)
        _state[_gave_up_key] = _desired


def _ensure_pref_cookies(st_module=None, cookie_get=None, cookie_set=None,
                         controller_refresh=None):
    """Keep the theme-preference + rail-mode cookies at the values
    in effect (see the block comment above). The desired values
    come from session state: the preference as synced at the top
    of the run, the rail mode via ui_design.rail_mode (which falls
    back to the old pinned bool for pre-clone sessions). The
    injectable ``cookie_get`` / ``cookie_set`` /
    ``controller_refresh`` exist for tests; the app calls with the
    defaults. Never raises."""
    _st = st_module or st
    try:
        _state = _st.session_state
        _pref = ui_design.normalize_theme_pref(
            _state.get(ui_design.THEME_PREF_KEY,
                       ui_design.normalize_theme(
                           _state.get("dcs_theme",
                                      ui_design.THEME_DEFAULT))))
        _mode = ui_design.rail_mode(_st)
    except Exception:  # noqa: BLE001 - no readable state, no writes
        return
    _ensure_one_pref_cookie(
        ui_design.THEME_PREF_COOKIE, _pref, "light",
        state=_state, cookie_get=cookie_get, cookie_set=cookie_set,
        controller_refresh=controller_refresh)
    _ensure_one_pref_cookie(
        ui_design.RAIL_MODE_COOKIE, _mode, ui_design.RAIL_MODE_DEFAULT,
        state=_state, cookie_get=cookie_get, cookie_set=cookie_set,
        controller_refresh=controller_refresh)


def _google_oauth_enabled() -> bool:
    """True only when Google OAuth is explicitly switched on.

    Flag: GOOGLE_OAUTH_ENABLED in Streamlit secrets or the
    environment. Only true/True/"true"/"1" count as on; anything
    else — including a missing flag — is OFF. Default OFF, because
    the Google provider is not enabled in the Supabase dashboard:
    with the flag off the "Continue with Google" button stays
    hidden instead of leading to a dead end.
    """
    raw = (os.environ.get("GOOGLE_OAUTH_ENABLED") or "").strip()
    if not raw:
        try:
            raw = str(st.secrets.get("GOOGLE_OAUTH_ENABLED", "") or "").strip()
        except Exception:  # noqa: BLE001 - no secrets file: not configured
            raw = ""
    return raw in ("true", "True", "1")


def _consume_oauth_callback() -> None:
    """Consume an OAuth redirect (?code=...) once, if one ever arrives.

    The auth module exposes handle_oauth_code (via auth.py, backed by
    google_auth.py): exchange the code for a user + session token and
    clear the code from the URL immediately, so it never lingers in
    the address bar, history or logs. In local mode the handler
    returns a clean error ("Google sign-in is not set up (local
    mode)") and no button exists to start the flow, so a stray ?code=
    is answered with a plain note. Never crashes on a bad callback.
    """
    try:
        _params = st.query_params
    except Exception:  # noqa: BLE001
        return
    _oauth_error = None
    try:
        _oauth_error = _params.get("error_description") or _params.get("error")
    except Exception:  # noqa: BLE001
        _oauth_error = None
    if _oauth_error:
        st.session_state["google_error"] = f"Google sign-in failed: {_oauth_error}"
        return
    try:
        code = _params.get("code")
    except Exception:  # noqa: BLE001
        return
    if not code:
        return
    try:
        del st.query_params["code"]
    except Exception:  # noqa: BLE001 - clearing is best-effort
        pass
    handler = (getattr(auth, "handle_oauth_code", None)
               or getattr(auth, "exchange_oauth_code", None)
               or getattr(auth, "handle_google_callback", None))
    if handler is None or not callable(handler):
        st.session_state["google_error"] = (
            "Google sign-in needs Supabase configured — add the "
            "Supabase details to the app's secrets (see README.md) "
            "and enable Google in the Supabase dashboard. "
            "Use email and password for now.")
        return
    try:
        user, session_token, error = handler(str(code))
    except AuthServiceError as exc:
        st.session_state["google_error"] = str(exc)
        return
    except Exception as exc:  # noqa: BLE001 - a bad callback never crashes
        st.session_state["google_error"] = f"Google sign-in failed: {exc}"
        return
    if error:
        st.session_state["google_error"] = error
        return
    if user is not None and session_token:
        _remember_session(session_token)
        st.session_state["current_user"] = user
        st.session_state["storage_key"] = _storage_key(user)


_consume_oauth_callback()

# A refresh wipes session state but not the login cookie: when there
# is no token in state, try to restore the session from the cookie
# before deciding the user is logged out.
_restore_session_from_cookie()

# Round 3: when the theme preference is System, the OS reading
# (dcs_os_dark) is written by the zero-height JS bridge after
# page load, and the cookie component's snapshot is frozen at its
# first mount — so re-read the browser cookies now. The
# component's frontend polls document.cookie every 300ms, so a
# bridge write is already in its cache; invoking the component
# re-renders it, and a changed value is pushed back and reruns
# the app, where the restore (top of the run) re-resolves the
# theme from the fresh OS reading. Without this, System follows
# the OS as of the previous session, not the current one: the
# reload that changes OS theme shows the old theme until the
# next reload. Only System needs it — Dark/Light never read the
# OS value. A re-read whose value is unchanged pushes nothing,
# so this cannot loop.
if st.session_state.get(ui_design.THEME_PREF_KEY) == "system":
    _controller_refresh()

_current_user = None
if st.session_state.get("auth_token"):
    try:
        _current_user = auth.validate_session(st.session_state["auth_token"])
    except AuthServiceError as exc:
        st.error(f"Account service error: {exc}")
        _current_user = None
    if _current_user is None:
        st.session_state["auth_token"] = None
        st.session_state["current_user"] = None
        st.session_state["storage_key"] = None
        st.session_state["user_paths"] = None
    else:
        st.session_state["current_user"] = _current_user
        st.session_state["storage_key"] = _storage_key(_current_user)

# While logged in, keep the login cookie in the browser (write it
# after a login, verify + re-issue a lost write). A no-op when
# logged out or when the cookie library is missing.
if _current_user is not None:
    _ensure_login_cookie()


def _start_code_step(email, user, purpose):
    """Request the 6-digit login code and park the pending login.

    Called after the password passed (log in) or after the account
    was created and signed in (sign up). On success the pending
    login is stored in session state and the run reruns onto the
    code screen — no session exists yet. On failure the error is
    shown and nothing is parked (this function returns False; the
    success path never returns, it reruns).
    """
    try:
        _ok, _status = auth.request_login_code(email)
    except AuthServiceError as exc:
        st.error(f"Account service error: {exc}")
        return False
    if not _ok:
        if _status == "not_configured":
            st.error(auth.BREVO_SETUP_MESSAGE)
        elif _status == "too_soon":
            st.error("A code was just sent — wait a minute before "
                     "requesting a new one.")
        elif _status == "hourly_limit":
            st.error("Too many codes requested — try again in an hour.")
        else:
            st.error("Could not send the login code — try again in a moment.")
        return False
    st.session_state["pending_code"] = {
        "email": email, "user": user, "purpose": purpose,
    }
    st.rerun()


def _code_step_ui(pending):
    """The 6-digit email-code screen (password already passed).

    `pending` is {"email", "user", "purpose"} from _start_code_step.
    A correct code logs the user in through _log_user_in — the same
    session path as a direct login — and reruns; anything else stays
    on this screen with a clear error. No session exists yet at this
    point: the code is the last gate before one is created.
    """
    _email = pending.get("email", "")
    _user = pending.get("user") or {}
    # Console layout (variant C): left-aligned 18px heading + instruction
    # (email in green), same copy as before — presentation only.
    st.markdown('<h2 class="dcs-console-h2">Check your email</h2>',
                unsafe_allow_html=True)
    st.markdown(f"We sent a 6-digit code to "
                f'<span class="dcs-code-email">{html.escape(_email)}</span>. '
                "Enter it below to finish signing in — it expires in "
                "10 minutes.", unsafe_allow_html=True)
    _code = st.text_input("6-digit code", key="email_code_input",
                          max_chars=6,
                          help="The 6 numbers from the email we just sent.")
    if st.button("Verify code", key="email_code_verify_btn", type="primary",
                 use_container_width=True):
        _typed = (_code or "").strip().replace(" ", "")
        if not _typed:
            st.error("Enter the 6-digit code from the email.")
        else:
            try:
                _ok, _status = auth.verify_login_code(_email, _typed)
            except AuthServiceError as exc:
                st.error(f"Account service error: {exc}")
                _ok, _status = False, None
            if _ok:
                if pending.get("purpose") == "signup":
                    st.session_state["just_signed_up"] = True
                st.session_state["pending_code"] = None
                if _log_user_in(_user):
                    st.rerun()
            elif _status == "wrong":
                st.error("Wrong code — try again.")
            elif _status == "expired":
                st.error("That code expired — request a new one below.")
            elif _status == "too_many":
                st.error("Too many wrong tries — that code no longer works. "
                         "Request a new one below.")
            elif _status == "not_found":
                st.error("No active code for this email — request a new "
                         "one below.")
            else:
                st.error("Could not check the code — try again.")
    # Resend + Back side by side (variant C console code screen).
    _rc1, _rc2 = st.columns(2)
    with _rc1:
        if st.button("Resend code", key="email_code_resend_btn",
                     use_container_width=True):
            try:
                _ok, _status = auth.request_login_code(_email)
            except AuthServiceError as exc:
                st.error(f"Account service error: {exc}")
                _ok, _status = False, None
            if _ok:
                st.success(f"A new code is on its way to {_email}.")
            elif _status == "too_soon":
                st.error("A code was just sent — wait a minute before "
                         "requesting a new one.")
            elif _status == "hourly_limit":
                st.error("Too many codes requested — try again in an hour.")
            elif _status == "not_configured":
                st.error(auth.BREVO_SETUP_MESSAGE)
            else:
                st.error("Could not send a new code — try again in a moment.")
    with _rc2:
        if st.button("Back to login", key="email_code_cancel_btn",
                     use_container_width=True):
            st.session_state["pending_code"] = None
            st.rerun()


def _loader_logo_path():
    """The logo file for the branded loader: the 192px loader variants
    (assets/logo-loader-dark.png, #4acd8b, on the dark theme, the
    light one on light) — the same pick as the console header, at the
    size the mark actually displays (40px compact, 96px large). The
    full 1024px files were 571KB/207KB and were inlined into every
    loader render; the 192px files are ~17KB each and identical at
    display size. The top bar reuses this path too (24px display)."""
    return _APP_DIR / "assets" / (
        "logo-loader-dark.png"
        if (st.session_state.get("dcs_theme") or "light") == "dark"
        else "logo-loader.png")


#: Minimum time the branded loader stays visible (seconds). A fast
#: local wait (loading the sample file) finishes in milliseconds, and
#: Streamlit coalesces the placeholder's create + clear within one
#: script run — so the loader never painted and the live check saw no
#: `.dcs-loader` element at any point during the load. Holding the
#: loader for at least this long guarantees the browser paints it.
#: Slow waits (login, sheet loads, cleaning) already exceed it, so
#: they pay nothing extra.
_BRANDED_SPINNER_MIN_SECONDS = 0.7


@contextlib.contextmanager
def branded_spinner(status, min_seconds=_BRANDED_SPINNER_MIN_SECONDS):
    """Branded wait state, replacing bare st.spinner wherever a user
    waits: the logo mark animating (bars rising, checkmark drawing,
    then a gentle pulse) + the status text + a thin shimmer bar.
    A placeholder is cleared on exit, exactly like st.spinner — but
    not before the loader has been visible for at least ``min_seconds``
    (default 0.7s), so a fast wait still shows the mark instead of
    flashing past unseen."""
    _ph = st.empty()
    _ph.markdown(
        ui_design.loader_block_html(_loader_logo_path(), status,
                                    size="compact"),
        unsafe_allow_html=True)
    _started = time.monotonic()
    try:
        yield
    finally:
        _remaining = min_seconds - (time.monotonic() - _started)
        if _remaining > 0:
            time.sleep(_remaining)
        _ph.empty()


if _current_user is None:
    if not _cookie_read_resolved() and not st.session_state.get("_cookie_wait_done"):
        # The cookie read has not resolved yet (no request cookies
        # and the cookie component has not registered a value):
        # do NOT conclude "logged out" — show a brief loading
        # state and let the component's rerun decide. Bounded to
        # one wait per session so a broken component can never
        # wedge the login screen.
        st.session_state["_cookie_wait_done"] = True
        # Branded loader (large): the mark drawing itself while the
        # session restores. Rendered directly, not through
        # branded_spinner — st.stop() below must NOT clear it (the
        # context manager's finally would), or the screen would go
        # blank until the cookie component's rerun.
        st.markdown(
            ui_design.loader_block_html(
                _loader_logo_path(), "Waking up your workspace…",
                size="large"),
            unsafe_allow_html=True)
        st.stop()
    # Console layout (variant C): header row (logo + title left, theme
    # link right) over a narrow left-aligned form column (~360px).
    # No card, no panel, no tagline — the spare Supabase-console feel.
    # (The tagline is intentionally not shown here: the approved
    # variant C preview has no tagline on the login screen.) Every
    # widget key, label and call below is unchanged — presentation only.
    _c1, _console, _c3 = st.columns([1, 2.5, 1])
    with _console:
        _h_l, _h_r = st.columns([4, 1])
        with _h_l:
            # The mark is dark-green line art: on the dark theme it
            # uses the light recolor (assets/logo-dark.png, #4acd8b),
            # on light the original (assets/logo.png).
            _logo_name = ("logo-dark.png"
                          if (st.session_state.get("dcs_theme")
                              or "light") == "dark"
                          else "logo.png")
            st.markdown(
                ui_design.console_head_html(
                    _APP_DIR / "assets" / _logo_name),
                unsafe_allow_html=True)
        with _h_r:
            # Theme switch for the login screen (no sidebar here): flips
            # the same st.session_state["dcs_theme"] the sidebar toggle
            # writes, so the login screen itself restyles on the rerun.
            ui_design.render_login_theme_toggle()
        banner = auth.get_local_mode_banner()
        if banner:
            ui_design.info_card(banner)
        warning = auth.get_backend_warning()
        if warning:
            st.warning(warning)
        backend = auth.get_auth_backend()
        _f_l, _f_r = st.columns([1, 1])
        with _f_l:
            # Email-code step: the password already passed and a code is
            # waiting — show only the code screen, not the login form.
            if st.session_state.get("pending_code") is not None:
                _code_step_ui(st.session_state["pending_code"])
                st.stop()
            if backend == "local":
                st.caption("Local mode — accounts live on this server only. "
                           "Cloud accounts need Supabase configured "
                           "(see Settings).")
            else:
                st.markdown('<div class="dcs-console-status">Cloud accounts '
                            "are active.</div>", unsafe_allow_html=True)
            if st.session_state.get("google_error"):
                st.error(st.session_state.pop("google_error"))
            mode = st.radio("Account", ["Log in", "Sign up"], key="auth_mode",
                            horizontal=True)
            id_label = "Email" if backend != "local" else "Username"
            id_help = ("Your email address." if backend != "local"
                       else "3–30 characters, letters, digits or underscore only.")
            ident = st.text_input(id_label, key="auth_id_input", help=id_help)
            password = st.text_input("Password", type="password",
                                     key="auth_pw_input",
                                     help="At least 8 characters.")
            if mode == "Log in":
                if st.button("Log in", key="auth_login_btn", type="primary",
                             use_container_width=True):
                    if not ident.strip() or not password:
                        st.error("Enter your email/username and password.")
                    else:
                        _unconfirmed = False
                        with branded_spinner("Logging you in…"):
                            try:
                                user = auth.authenticate(ident.strip(), password)
                            except auth.EmailNotConfirmedError:
                                # Registered but the email is not confirmed yet:
                                # neither a wrong password nor a service error.
                                st.error("Check your inbox — click the verification "
                                         "link first, then log in.")
                                user = None
                                _unconfirmed = True
                            except AuthServiceError as exc:
                                st.error(f"Account service error: {exc}")
                                user = None
                        if user is None:
                            if not _unconfirmed:
                                st.error("Wrong email/username or password. Try again.")
                        elif auth.email_code_required():
                            # Cloud accounts: the 6-digit email code is the
                            # last gate — no session exists until it passes.
                            _start_code_step(ident.strip(), user, "login")
                        elif _log_user_in(user):
                            st.rerun()
            else:
                if st.button("Create account", key="auth_signup_btn",
                             type="primary", use_container_width=True):
                    if not ident.strip() or not password:
                        st.error("Enter an email/username and a password "
                                 "(at least 8 characters).")
                    else:
                        with branded_spinner("Creating your account…"):
                            try:
                                ok, error = auth.create_user(ident.strip(), password)
                            except AuthServiceError as exc:
                                st.error(f"Account service error: {exc}")
                                ok, error = False, None
                        if not ok:
                            st.error(error or "Could not create the account.")
                        elif error == auth.SIGNUP_NEEDS_CONFIRMATION:
                            # The account exists but the email is not confirmed
                            # yet ("Confirm email" is on): no auto-login and no
                            # session cookie — the user must click the link in
                            # their inbox first. (The merge gate switches
                            # "Confirm email" off, so this branch should not
                            # fire on the live app.)
                            st.success(f"Account created for {ident} — check "
                                       "your inbox and click the verification "
                                       "link first, then log in here.")
                        else:
                            # Confirmed account (or local mode, which has no
                            # confirmation step): sign in, then the email
                            # code — the code is both the verification and
                            # the login check. If the sign-in fails, fall
                            # back to the old "switch to Log in" message.
                            _unconfirmed = False
                            with branded_spinner("Logging you in…"):
                                try:
                                    user = auth.authenticate(ident.strip(), password)
                                except auth.EmailNotConfirmedError:
                                    user = None
                                    _unconfirmed = True
                                except AuthServiceError:
                                    user = None
                            if user is not None:
                                if auth.email_code_required():
                                    _start_code_step(ident.strip(), user, "signup")
                                elif _log_user_in(user):
                                    st.session_state["just_signed_up"] = True
                                    st.rerun()
                            elif _unconfirmed:
                                st.success(f"Account created for {ident} — check "
                                           "your inbox and click the verification "
                                           "link first, then log in here.")
                            else:
                                st.success(f"Account created — switch to 'Log in' "
                                           f"above and log in as {ident}.")
            google_url = None
            _google_entry = (getattr(auth, "get_google_sign_in_url", None)
                             or getattr(auth, "google_sign_in_url", None))
            if callable(_google_entry):
                try:
                    google_url = _google_entry()
                except Exception:  # noqa: BLE001 - no Google URL, show the note
                    google_url = None
            if google_url and _google_oauth_enabled():
                st.write("— or —")
                st.link_button("Continue with Google", google_url)
            elif not google_url:
                # Local mode: get_google_sign_in_url() returns None, so there
                # is no button — show the plain-words reason instead.
                st.caption("Google sign-in needs Supabase configured first: "
                           "add the Supabase details to the app's secrets "
                           "(see README.md) and enable Google in the Supabase "
                           "dashboard. "
                           "For now, use email and password above.")
            # else: Supabase is up but GOOGLE_OAUTH_ENABLED is off (the
            # default) — the button stays hidden, no dead end, no note.
            # "What's inside" — three plain lines under the form, so a
            # new visitor feels what the app does. Same narrow column,
            # hairline divider, small muted text, green dot markers.
            # (Not the tagline: the approved variant C preview has no
            # tagline on the login screen; these lines carry the same
            # meaning in fresh words.) Shows in both Log in and
            # Sign up modes; the code screen stops before this point.
            st.markdown(
                '<div class="dcs-console-inside">'
                "<div>Messy CSV, Excel or JSON in — a clean file out.</div>"
                "<div>KPIs, charts, and a one-page report with every "
                "clean.</div>"
                "<div>Private to your account. Nothing shared.</div>"
                "</div>",
                unsafe_allow_html=True)
        # Keep the theme-preference + rail-mode cookies at the
        # values in effect (Round 3): the login screen's theme
        # toggle fires before this point, so a flip here is written
        # on the rerun that renders the login screen again.
        _ensure_pref_cookies()
        st.stop()

# ---- logged in from here on. ----
_user = st.session_state["current_user"]
_skey = st.session_state["storage_key"]
_paths = _apply_user_paths(_user, _skey)
st.session_state["user_paths"] = _paths
_user_root = _paths["root"]
_ws_dir = _paths["ws_dir"]
_settings_path = _paths["settings_path"]

# ------------------------------------------------------- brand + mobile ---
# Theme first, brand second: with the default accent both agree, and
# a user-picked accent wins the tie on buttons and links.
try:
    _brand = feat_brand.load_brand(base_dir=_user_root)
except Exception:  # noqa: BLE001 - a broken brand file must not stop the app
    _brand = {"name": "Data Cleaner Studio",
              "accent": feat_brand.DEFAULT_ACCENT, "logo": None}
try:
    # Mobile stylesheet follows the theme toggle too — its base theme
    # applies on every screen, so a light-only mobile_css() would
    # fight the dark theme with !important rules.
    st.markdown(feat_mobile.mobile_css(
        theme=st.session_state.get("dcs_theme") or "light"),
        unsafe_allow_html=True)
except Exception:  # noqa: BLE001 - theme CSS must never stop the app
    pass
try:
    st.markdown(feat_brand.brand_css(
        _brand.get("accent", feat_brand.DEFAULT_ACCENT)),
        unsafe_allow_html=True)
except Exception:  # noqa: BLE001 - brand CSS must never stop the app
    pass

for key, default in [
    ("raw", None), ("clean", None), ("actions", None), ("kpis", None),
    ("source_name", ""), ("source_kind", "upload"), ("source_url", None),
    ("clean_opts", None), ("fuzzy_groups", None), ("fuzzy_col_used", None),
    ("join_result", None), ("auto_refresh", False), ("refresh_seconds", 900),
    ("q_audit", []), ("a_snaps", []), ("a_recipes", []),
    ("a_bulk_results", None), ("pending_excel", None),
    ("client_mode", False), ("an_pending_view", None),
    ("n_ws_fingerprint", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# Recipes persist per user (recipes/); restore them into the session.
# A storage failure here (e.g. Supabase Storage not configured yet)
# must never stop the app: a first-time user has no recipes anyway.
if not st.session_state.get("a_recipes"):
    try:
        _saved_recipes = storage.load_json(_skey, "recipes", "recipes.json")
    except Exception:  # noqa: BLE001 - missing recipes are not fatal
        _saved_recipes = None
    if isinstance(_saved_recipes, list):
        st.session_state["a_recipes"] = _saved_recipes

# ------------------------------------------------------- language + title ---
# The language picker widget (key "n_lang_pick", in the avatar
# menu — ui_design.render_avatar_menu) only runs later in this
# script, after the top bar — but its value is already in session
# state at the top of the run. Read it HERE, before the top bar
# renders: otherwise the top bar (and every label built from _lang)
# shows the previous language for one run after a switch. The
# label->code map below mirrors the picker's options dict — if the
# picker ever changes its labels, this map must change with it.
_LANG_PICK_LABELS = {"English": "en", "हिन्दी": "hi", "اردو": "ur"}
try:
    _lang_pick = st.session_state.get("n_lang_pick")
    if _lang_pick in _LANG_PICK_LABELS:
        _lang = _LANG_PICK_LABELS[_lang_pick]
    else:
        _lang = (st.session_state.get("n_lang_data")
                 or ai_settings.load_settings().get("language", "en"))
except Exception:  # noqa: BLE001 - a broken settings file must not stop the app
    _lang = "en"
if _lang not in ("en", "hi", "ur"):
    _lang = "en"


def _t(key):
    return feat_enrich.get_text(key, _lang)


_title = (_brand.get("name") if _brand.get("name")
          and _brand["name"] != "Data Cleaner Studio" else _t("app_title"))
# Section labels, one mapping shared by the top bar, the sidebar nav
# and the section radio below, so the three stay in agreement.
# (Settings / Profile / Status are plain labels, not translated keys.)
_nav_labels = {"preview": _t("preview"), "join": _t("join"),
               "clean": _t("clean"), "kpis": _t("kpis"),
               "dashboard": _t("dashboard"), "compare": _t("compare"),
               "report": _t("report"), "tools": _t("tools"),
               "tutorial": _t("tutorial"), "settings": "Settings",
               "profile": "Profile", "status": "Status"}
# The sidebar nav is a flat rail (Supabase's icon rail / labelled
# sidebar) — NO section headers, so there are no nav groups. Only
# the tabs the current mode offers are shown — client mode hides the
# advanced ones; the radio below is the authority on that. The flat
# list is built where the nav renders, from _nav_keys below.
# A "Go to the Clean tab" empty-state button (or any other code) asks
# for a section switch by setting pending_tab, then rerunning: apply it
# here, BEFORE the top bar and the sidebar nav render — writing the
# radio's session key after it exists raises
# StreamlitWidgetAlreadyInstantiatedError. The radio below only
# re-checks the value is still a valid option.
_pending_early = st.session_state.pop("pending_tab", None)
if _pending_early in _nav_labels:
    st.session_state["active_tab"] = _nav_labels[_pending_early]
_top_active = st.session_state.get("active_tab")
if _top_active not in _nav_labels.values():
    _top_active = _nav_labels["preview"]
# Top bar (Supabase shell, 48px): breadcrumb-style title of the current
# screen + the file name when one is loaded. The section radio below is
# the selection control; the sidebar nav mirrors it.
# The breadcrumb is the loaded file's name only — the top bar
# already renders the workspace name ("Data Cleaner Studio") + the
# current screen, so repeating the workspace name here duplicated
# it ("Data Cleaner Studio / Data Cleaner Studio / Preview").
_top_crumb = st.session_state.get("source_name") or ""
# Real top bar (Supabase shell): the logo at the far left, the
# workspace + screen, a search column, a green Upload pill, Help,
# and the avatar at the far right. The avatar menu lives here now,
# not in the sidebar (the dashboard puts it in the top bar).
_top_actions = ui_design.topbar(
    _top_active, breadcrumb=_top_crumb, user=_user,
    logo_path=_loader_logo_path())
# Quick jump fills the top bar's search column (the dashboard's
# Search / Cmd+K pill — the box itself, not an overlay, because
# Streamlit has no global key listener).
feat_quickjump.render_quick_jump(
    st, container=_top_actions["search_col"], compact=True)
if _top_actions["upload"]:
    st.session_state["pending_tab"] = "preview"
    # Upload means "I want to upload" — open the rail too, so the
    # file uploader (which lives in the expanded sidebar) is visible
    # instead of landing on Preview with a collapsed rail and no
    # visible way to pick a file.
    ui_design.set_rail_mode(st, "expanded")
    st.rerun()
if _top_actions["help"]:
    st.session_state["pending_tab"] = "tutorial"
    st.rerun()
if _top_actions["avatar"] == "profile":
    st.session_state["pending_tab"] = "profile"
    st.rerun()
elif _top_actions["avatar"] == "status":
    st.session_state["pending_tab"] = "status"
    st.rerun()
elif _top_actions["avatar"] == "previews":
    st.toast("No feature previews running right now.")
elif _top_actions["avatar"] == "logout":
    _do_logout()
# The main flow, at a glance: upload -> clean -> KPIs -> export.
# ONE render site in the shared shell chrome (right under the top
# bar), so the strip shows on EVERY flow page. It used to live
# inside the Preview block below, so on Clean / KPIs / Report it
# was never rendered at all (the Round 3 live failure: "you are
# here" pinned to Upload, strip absent off Preview). The marker
# follows the page you are actually on (Preview is the Upload
# step) — the old line derived it from whether cleaned data
# existed, so it always read "Clean — you are here" on Preview,
# and it ticked Upload before any file was loaded. Ticks follow
# the data instead (see flow_marker). flow_marker returns None
# off the flow, so Dashboard / Join / Compare / Tools / How to
# use / Settings / Profile / Status show no strip. (On Preview
# the strip now sits above the intro caption instead of below
# it — the strip itself is unchanged.)
_active_key = next(
    (k for k, v in _nav_labels.items() if v == _top_active),
    "preview")
_flow_parts = ui_design.flow_marker(
    _active_key, raw_loaded=st.session_state.raw is not None,
    clean_loaded=st.session_state.clean is not None)
if _flow_parts:
    st.caption("Your flow: " + " → ".join(_flow_parts))
if _top_active == _nav_labels["preview"]:
    st.caption("Put in messy data. Get clean data, KPIs, charts and a report.")
    if st.session_state.pop("just_signed_up", False):
        st.success("Account created — you're logged in. Start with a file "
                   "from the sidebar, or try the sample data.")
    feat_tutorial.render_first_run_banner(st, settings_path=_settings_path)
    feat_analyse.render_whats_new(st, user_key=_skey)

# ------------------------------------------- workspace restore (startup) ---
_ws_marker = _ws_dir / "autosave.txt"
if "n_workspace_toggle" not in st.session_state:
    st.session_state["n_workspace_toggle"] = _ws_marker.exists()
if st.session_state.raw is None and _ws_marker.exists():
    try:
        _ws_restored = feat_enrich.load_workspace(base_dir=_ws_dir)
    except Exception:  # noqa: BLE001 - a broken workspace must not stop the app
        _ws_restored = None
    if _ws_restored is not None:
        st.session_state.raw = _ws_restored["raw"]
        st.session_state.clean = _ws_restored["clean"]
        st.session_state.actions = _ws_restored["actions"] or None
        st.session_state.kpis = _ws_restored["kpis"] or None
        st.session_state.source_name = _ws_restored["source_name"]
        st.session_state.source_kind = "workspace"


def _set_raw(df, name, kind="upload", url=None):
    st.session_state.raw = df
    st.session_state.clean = None
    st.session_state.actions = None
    st.session_state.kpis = None
    st.session_state.source_name = name
    st.session_state.source_kind = kind
    st.session_state.source_url = url
    st.session_state.clean_opts = None
    st.session_state.fuzzy_groups = None
    st.session_state.join_result = None
    st.session_state.q_audit = []
    st.session_state.a_snaps = []


def _audit(step, detail):
    feat_quality.record_audit(st.session_state, step, detail)


def _apply_new_clean(new_df, new_actions, audit_step=None, replace_actions=False):
    """Apply a cleaned frame returned by a render function: snapshot the
    old state first (so Undo works), then update clean/actions/KPIs.
    Recipes/templates clean from raw, so they replace the log; the other
    fix-ups build on the current clean data, so they append to it."""
    feat_automate.push_snapshot(st.session_state, audit_step or "Before change")
    st.session_state.clean = new_df
    if replace_actions:
        st.session_state.actions = new_actions
    else:
        st.session_state.actions = st.session_state.actions + new_actions
    st.session_state.kpis = engine.auto_kpis(new_df)
    if audit_step:
        _audit(audit_step, f"{len(new_df):,} rows")
    return new_df


def _apply_pending_view(view):
    """Apply a saved view (from render_saved_views) before its widgets
    are created this run: chart choice, group-by/number columns and
    slicer values. Invalid values are skipped, never forced."""
    if not isinstance(view, dict) or st.session_state.clean is None:
        return
    clean_now = st.session_state.clean
    cols = list(clean_now.columns)
    ct = view.get("chart_type")
    if ct in ("Bar", "Line", "Donut", "Histogram", "Scatter", "Box plot",
              "Heatmap", "Treemap", "Funnel"):
        st.session_state["chart_type"] = ct
    _key_map = {"Bar": ("dash_x", "dash_y"), "Line": ("dash_x", "dash_y"),
                "Donut": ("dash_x", "dash_y"), "Histogram": (None, "hist_col"),
                "Scatter": ("sc_x", "sc_y"), "Box plot": ("box_x", "box_y"),
                "Treemap": ("tm_x", "tm_y"), "Funnel": ("fn_x", "fn_y")}
    if ct in _key_map:
        gx, ny = _key_map[ct]
        gb, nc = view.get("group_by"), view.get("num_col")
        if gx and gb in cols:
            st.session_state[gx] = gb
        if ny and nc in cols:
            st.session_state[ny] = nc
    slicers = view.get("slicers") or {}
    if isinstance(slicers, dict):
        for col, vals in slicers.items():
            if col in cols and isinstance(vals, list):
                allowed = set(clean_now[col].dropna().unique())
                valid = [v for v in vals if v in allowed]
                if valid:
                    st.session_state[f"slice_{col}"] = valid


def _save_cleaned_copy(df, source_name):
    """Best-effort: persist the cleaned frame to cleaned/ so it
    survives the session, plus a small state file (actions, KPIs,
    clean options) so reopening the file restores the cleaned data
    too instead of only the raw file. Never stops the app when it
    fails."""
    try:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(source_name or "data"))
        storage.save_file(_skey, "cleaned", f"cleaned_{safe}.csv",
                          df.to_csv(index=False).encode("utf-8"))
        storage.save_json(_skey, "cleaned", f"cleaned_{safe}.state", {
            "source_name": str(source_name or ""),
            "actions": [[str(a), str(b)] for a, b in
                        (st.session_state.get("actions") or [])],
            "kpis": st.session_state.get("kpis") or [],
            "clean_opts": st.session_state.get("clean_opts"),
        })
    except Exception:  # noqa: BLE001 - saving a copy must never stop the app
        pass


def _restore_cleaned_state(source_name):
    """Best-effort: restore the cleaned frame + KPIs saved by
    _save_cleaned_copy for this source file. Returns True when the
    cleaned state was restored, False otherwise (the caller then
    says plainly that only the raw file came back). Never raises."""
    try:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(source_name or "data"))
        state = storage.load_json(_skey, "cleaned", f"cleaned_{safe}.state")
        if not isinstance(state, dict):
            return False
        raw_bytes = storage.read_file(_skey, "cleaned", f"cleaned_{safe}.csv")
        cleaned = engine.load_file(f"cleaned_{safe}.csv", raw_bytes)
        st.session_state.clean = cleaned
        st.session_state.actions = (
            [(str(a), str(b)) for a, b in (state.get("actions") or [])]
            or None)
        st.session_state.kpis = state.get("kpis") or engine.auto_kpis(cleaned)
        st.session_state.clean_opts = state.get("clean_opts")
        return True
    except Exception:  # noqa: BLE001 - a missing/broken copy is not fatal
        return False


# ------------------------------------------------------------------ load ---
# Sidebar: grouped nav (clickable icon rows — the dashboard's icon +
# label nav) + the quiet status pill below it. The brand logo and the
# avatar menu live in the top bar now (see the topbar() call above),
# not here. The nav rows navigate via pending_tab + rerun; the
# section radio further down is the authority, and pending_tab is
# how every programmatic switch reaches it.
# Rail state for this run (session state, default collapsed — the
# dashboard's own default). The non-nav sidebar widgets do NOT
# render while the rail is collapsed: what is not in the DOM cannot
# render as vertical one-letter text (the 8b4dd04 live failure —
# "Theme", the status pill, "Load your data", the uploader and the
# client-mode checkbox all squeezed into single-letter columns).
# The nav always renders (it IS the collapsed rail). The rail
# toggle renders once, in the main area (round 9) — pinned FIXED
# to the viewport's bottom-left, not part of the sidebar.
# Widget values persist in session state under their keys and are
# picked back up when the rail re-opens; the rail CSS denylist stays
# as a backstop for the widgets that must stay mounted (the Excel
# sheet picker, the "More ways to load" expander). The top-bar
# Upload pill still pin-expands the rail when clicked.
_rail_collapsed = ui_design.rail_collapsed()
# Theme toggle (sidebar): Light/Dark switch writing
# st.session_state["dcs_theme"]; the stylesheet injected at the top of
# this file follows it on the next rerun. In the collapsed rail the
# theme control also lives in the avatar menu (top bar).
if not _rail_collapsed:
    ui_design.render_theme_toggle()
# Sync client_mode from the toggle widget BEFORE the sidebar nav
# renders: the toggle itself (feat_analyse.render_client_mode_toggle)
# only runs later in this script, after the upload block, and it is
# the only place that copies the widget value into the "client_mode"
# data key — so reading client_mode here would lag one run behind
# the flip, and the nav would show the previous mode's tabs until
# the next rerun. The widget value ("an_client_mode_toggle") is
# already in session state at the top of the run, so read it
# directly; the toggle's own copy later in the run then agrees.
if "an_client_mode_toggle" in st.session_state:
    st.session_state["client_mode"] = bool(
        st.session_state["an_client_mode_toggle"])
_nav_client = bool(st.session_state.get("client_mode", False))
_nav_keys = (["preview", "clean", "kpis", "dashboard", "report",
              "tutorial", "profile", "status"] if _nav_client else
             ["preview", "clean", "join", "kpis", "dashboard", "compare",
              "report", "tools", "tutorial", "settings", "profile",
              "status"])
# Flat rail list, same pages in the same order — no section headers
# (Supabase's rail has none).
_nav_items = [(k, _nav_labels[k]) for k in _nav_keys if k in _nav_labels]
_nav_active = next(
    (k for k, v in _nav_labels.items() if v == _top_active), "preview")
with st.sidebar:
    _nav_clicked = ui_design.sidebar_nav(_nav_items, active=_nav_active,
                                         collapsed=_rail_collapsed)
    if _nav_clicked is not None:
        st.session_state["pending_tab"] = _nav_clicked
        st.rerun()
    # The rail toggle is NOT here: it renders once, in the main
    # area (round 9), pinned FIXED to the viewport's bottom-left
    # — it must not be a descendant of the sidebar, or hovering
    # it re-expands the overlay and the collapse never sticks.
    # Quiet status pill (feat_status): the app's own health — the
    # mode in local mode, "All systems operational" only when the
    # cloud health check genuinely passed. Not rendered while the
    # rail is collapsed (it would squeeze into vertical letters).
    if not _rail_collapsed:
        feat_status.render_status_pill(st)
# The file picker renders only when the rail is pinned open (see
# the rail-state comment above). The top-bar Upload pill still
# pin-expands the rail when clicked.
_banner = auth.get_local_mode_banner()
if _banner and not _rail_collapsed:
    ui_design.info_card(_banner, st_module=st.sidebar)

if not _rail_collapsed:
    st.sidebar.markdown(
        f'<div class="dcs-micro-label">{html.escape(_t("load") + " your data")}'
        "</div>",
        unsafe_allow_html=True)

uploaded = None
if not _rail_collapsed:
    uploaded = st.sidebar.file_uploader(
        "Upload a file", type=["csv", "xlsx", "xls", "json", "parquet"],
        help="CSV, Excel, JSON or Parquet. Up to 1000MB.")
if uploaded is not None and st.session_state.get("last_upload") != uploaded.name:
    try:
        storage.save_upload(_skey, uploaded.name, uploaded.getvalue())
    except Exception as e:  # noqa: BLE001 - show the error, don't crash
        st.sidebar.error(f"Could not save that upload ({uploaded.name}): {e}")
    if uploaded.name.lower().endswith((".xlsx", ".xls")):
        # Excel: hold the bytes and let the user pick a sheet below.
        st.session_state["pending_excel"] = (uploaded.name, uploaded.getvalue())
        st.session_state["last_upload"] = uploaded.name
    elif uploaded.name.lower().endswith(".parquet"):
        try:
            _set_raw(engine.load_parquet(uploaded.getvalue()),
                     uploaded.name)
            st.session_state["last_upload"] = uploaded.name
        except Exception as e:  # noqa: BLE001 - show the error, don't crash
            st.sidebar.error(f"Could not read {uploaded.name} as Parquet: {e}")
    else:
        try:
            _set_raw(engine.load_file(uploaded.name, uploaded.getvalue()),
                     uploaded.name)
            st.session_state["last_upload"] = uploaded.name
        except Exception as e:  # noqa: BLE001 - show the error, don't crash
            st.sidebar.error(f"Could not read {uploaded.name}: {e}")

if st.session_state.get("pending_excel") and not _rail_collapsed:
    ex_name, ex_bytes = st.session_state["pending_excel"]
    try:
        ex_sheets = feat_combine.list_excel_sheets(ex_bytes)
    except Exception as e:  # noqa: BLE001
        st.sidebar.error(f"Could not read that workbook ({ex_name}): {e}")
        ex_sheets = []
    if ex_sheets:
        ex_choice = st.sidebar.selectbox(
            "Sheet", ex_sheets + ["All sheets combined"], key="excel_sheet_pick")
        if st.sidebar.button("Load sheet", key="excel_sheet_load"):
            try:
                # Anti-shift skeleton: reserves the preview's space
                # before the blocking load, exactly like st.spinner.
                ui_loading.skeleton_table(rows=5, columns=4)
                with branded_spinner("Loading that sheet…"):
                    if ex_choice == "All sheets combined":
                        ex_df, _ = feat_combine.load_excel_all(ex_bytes)
                        _set_raw(ex_df, f"{ex_name} (all sheets)")
                    else:
                        _set_raw(feat_combine.load_excel_sheet(ex_bytes, ex_choice),
                                 f"{ex_name} : {ex_choice}")
                st.session_state["pending_excel"] = None
            except Exception as e:  # noqa: BLE001
                st.sidebar.error(f"Could not load the '{ex_choice}' sheet "
                                 f"from {ex_name}: {e}")

if (not _rail_collapsed) and st.sidebar.button(
        _t("try_sample"), key="sample_btn"):
    _sample_path = _APP_DIR / "sample_data" / "messy_sales.csv"
    ui_loading.skeleton_table(rows=5, columns=4)
    with branded_spinner("Loading the sample file…"):
        _set_raw(engine.load_file("messy_sales.csv",
                                  _sample_path.read_bytes()),
                 "messy_sales.csv (sample)", kind="sample")
    st.session_state["last_upload"] = None

# Your saved uploads (per-user storage): re-open without uploading again.
try:
    _saved_uploads = storage.list_files(_skey, "uploads")
except Exception:  # noqa: BLE001
    _saved_uploads = []
if _saved_uploads and not _rail_collapsed:
    with st.sidebar.expander("Your saved files"):
        _saved_pick = st.sidebar.selectbox(
            "Open a saved upload", [""] + _saved_uploads,
            key="saved_upload_pick")
        _c1, _c2 = st.sidebar.columns(2)
        if _c1.button("Open", key="saved_upload_open",
                      disabled=not _saved_pick) and _saved_pick:
            try:
                ui_loading.skeleton_table(rows=5, columns=4)
                with branded_spinner("Opening that file…"):
                    _saved_bytes = storage.read_file(_skey, "uploads", _saved_pick)
                    _set_raw(engine.load_file(_saved_pick, _saved_bytes),
                             _saved_pick, kind="upload")
                st.session_state["last_upload"] = None
                _opened_rows = len(st.session_state.raw)
                if _restore_cleaned_state(_saved_pick):
                    st.sidebar.success(
                        f"Opened {_saved_pick} ({_opened_rows:,} rows) — "
                        "cleaned data restored too.")
                else:
                    st.sidebar.success(
                        f"Opened {_saved_pick} ({_opened_rows:,} rows). Clean "
                        "it in the Clean tab to rebuild the KPIs and the "
                        "report.")
            except Exception as e:  # noqa: BLE001
                st.sidebar.error(f"Could not open {_saved_pick}: {e}")
        if _c2.button("Delete", key="saved_upload_delete",
                      type="secondary",
                      disabled=not _saved_pick) and _saved_pick:
            try:
                storage.delete_file(_skey, "uploads", _saved_pick)
                st.sidebar.success(f"Deleted {_saved_pick}.")
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.sidebar.error(f"Could not delete that file: {e}")

# "More ways to load" renders only when the rail is pinned open
# (see the rail-state comment above): its text input, buttons and
# database uploader would otherwise squeeze into vertical letters.
if not _rail_collapsed:
    with st.sidebar.expander("More ways to load"):
        sheet_url = st.text_input(
            "Google Sheets link (public sheet)",
            help="File -> Share -> Anyone with the link. Paste the link here.")
        if st.button("Load sheet", key="sheet_btn"):
            if not sheet_url.strip():
                st.error("Paste a Google Sheets link first — "
                         "File -> Share -> Anyone with the link, then "
                         "paste the link here.")
            else:
                try:
                    ui_loading.skeleton_table(rows=5, columns=4)
                    with branded_spinner("Loading that sheet…"):
                        _set_raw(engine.load_sheets_url(sheet_url.strip()), "Google Sheet",
                                 kind="sheets", url=sheet_url.strip())
                    st.session_state["last_upload"] = None
                except Exception as e:  # noqa: BLE001
                    st.error(f"Could not load that Google Sheet — check the "
                             "link and sharing settings: {e}")

        st.write("... or a database file")
        db_file = st.file_uploader(
            "SQLite database (.db)", type=["db", "sqlite", "sqlite3"],
            help="A SQLite database file — pick one of its tables to load.")
        if db_file is not None:
            try:
                tables = engine.list_sqlite_tables(db_file.getvalue())
            except Exception as e:  # noqa: BLE001
                st.error(f"Could not read that database file ({db_file.name}): {e}")
                tables = []
            if tables:
                table = st.selectbox("Table", tables, key="db_table")
                if st.button("Load table", key="db_load"):
                    try:
                        ui_loading.skeleton_table(rows=5, columns=4)
                        with branded_spinner("Loading that table…"):
                            _set_raw(engine.load_sqlite(db_file.getvalue(), table),
                                     f"{db_file.name} : {table}")
                        st.session_state["last_upload"] = None
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Could not load the '{table}' table from "
                                 f"{db_file.name}: {e}")

_last_raw_bytes = uploaded.getvalue() if uploaded is not None else None
# Recent files belongs to the Preview tab only: it used to render on
# every tab, so the Profile (and Settings, and every other) page
# showed Preview content above its own content. The reopen flow
# below only matters on Preview anyway.
_reopened = None
if _top_active == _nav_labels["preview"]:
    _reopened = feat_share.render_recent(
        st, df=st.session_state.raw,
        source_name=st.session_state.source_name, raw_bytes=_last_raw_bytes,
        base_dir=_user_root, storage_key=_skey)
if _reopened is not None:
    _reopened_name = st.session_state.pop("s_recent_opened", None)
    _set_raw(_reopened, "Recent file (reopened)", kind="recent")
    # The toast goes to the sidebar when the rail is expanded and to
    # the main area when it is collapsed — a sidebar toast in the
    # 60px rail would render as a vertical column of single letters
    # (the collapsed-rail leak), and the rail CSS hides non-nav
    # sidebar content there anyway, so the feedback would vanish.
    _toast = st.sidebar if not _rail_collapsed else st
    if _reopened_name and _restore_cleaned_state(_reopened_name):
        _toast.success(f"Opened {_reopened_name} — cleaned data "
                       "restored too.")
    elif _reopened_name:
        _toast.info(f"Opened {_reopened_name}. Clean it in the Clean "
                    "tab to rebuild the KPIs and the report.")

if not _rail_collapsed:
    feat_analyse.render_client_mode_toggle(st)

# Settings expander renders only when the rail is pinned open.
if not _rail_collapsed:
    with st.sidebar.expander("Settings (API key)"):
        ai_settings.render_settings(st)

# Theme toggle: the sidebar Light/Dark switch
# (ui_design.render_theme_toggle, wired just below the Profile / Log
# out buttons) and the login-screen switch both write
# st.session_state["dcs_theme"] ("light" by default); the stylesheet
# injected at the top of this file follows it, so the whole app —
# login screen included — switches between the light and dark
# Supabase stylesheets. .streamlit/config.toml stays base="light":
# it is only the first-paint base; the runtime CSS overrides do the
# switching, since Streamlit's native theme is static.
# The language picker lives in the avatar menu now (the standalone
# "Language / भाषा / زبان" section on the Preview tab was removed at
# the user's ask — ui_design.render_avatar_menu carries the same
# selectbox, key "n_lang_pick", options and save). The auto-save
# toggle renders in the MAIN area (its docstring says "Sidebar" but
# the code uses plain st.*, not st.sidebar.*) — so it belongs to the
# Preview home, not to every tab: on Profile / Dashboard / any other
# tab it used to sit above that tab's own content. Guarded to
# Preview like the intro above; the setting is still one click away
# on the home tab.
if _top_active == _nav_labels["preview"]:
    _ws_on = feat_enrich.render_workspace_toggle(st)
else:
    # The toggle is not rendered on this tab, so read the mirrored data
    # key (the widget key is dropped by Streamlit when the widget is
    # not rendered) — auto-save stays on across tab switches.
    _ws_on = bool(st.session_state.get(
        "n_workspace_on",
        st.session_state.get("n_workspace_toggle", False)))

# ---------------------------------------------------------- auto-refresh ---
raw = st.session_state.raw
if (raw is not None and st.session_state.source_kind == "sheets"
        and not _rail_collapsed):
    with st.sidebar.expander("Auto-refresh"):
        st.checkbox("Auto-refresh this sheet", value=False,
                    key="auto_refresh",
                    help="While the app is open, it re-checks the sheet "
                         "and updates the data and KPIs by itself.")
        if st.session_state.get("auto_refresh"):
            mins = st.selectbox(
                "Every", [5, 15, 30, 60], index=1, key="refresh_mins",
                format_func=lambda m: f"{m} minutes")
            st.session_state["refresh_seconds"] = mins * 60
        if st.button("Refresh now", key="refresh_now_btn"):
            try:
                opts = st.session_state.get("clean_opts")
                fresh = engine.load_sheets_url(st.session_state["source_url"])
                _set_raw(fresh, st.session_state["source_name"],
                         kind="sheets", url=st.session_state["source_url"])
                if opts:
                    cleaned, actions = engine.clean(
                        fresh, feat_automate.to_engine_opts(opts))
                    st.session_state["clean"] = cleaned
                    st.session_state["actions"] = actions
                    st.session_state["kpis"] = engine.auto_kpis(cleaned)
                    st.session_state["clean_opts"] = opts
                st.success("Refreshed.")
            except Exception as e:  # noqa: BLE001
                st.error(f"Refresh failed: {e}")

# ------------------------------------------------------- dashboard strips ---
# Defined up here (before the `if raw is None:` empty-state block
# below): the Dashboard tab renders its strips even with no data
# loaded, and that branch stops the script before the old definition
# point — so the function has to exist by then.
def _render_dashboard_strips(st, clean, raw, storage_key):
    """The Supabase Project Overview, mapped to this app's own data
    (never Supabase's), in Supabase's order: URL row + Copy menu,
    six info tiles, the infrastructure diagram, the "Get connected"
    action strip, the API metrics strip (big numbers + service
    cards), the Advisor block, and the Reports section. No Free-plan
    usage panel — Supabase's Overview has none, and neither does
    this page. Pure presentation + navigation — every number comes
    from the loaded file, the storage backend, or the app's own
    health check, and every strip action is a pending_tab jump.

    Card mapping (the six tiles): Status = backend health
    (feat_status); Storage = Supabase bucket usage; Rows = cleaned
    rows; Columns = columns in the cleaned file; KPIs = auto-KPI
    count; File = current source file. API metrics: "Rows
    processed" = the loaded file's row count, "Success rate" = the
    share of rows kept after cleaning. The diagram nodes are the
    app's pipeline (Upload → Clean → KPIs → Export) with live
    counts. "Ask Assistant" opens the How to use guide — this app
    has no AI assistant panel, so the guide is the honest
    counterpart.

    Empty state (``clean`` / ``raw`` None): the strips still render.
    Data-dependent tiles show "—" with "No data yet" (no numbers are
    invented), the metric cards show "—" with a "load a file" sub, and
    the Advisor points at loading a file instead of at cleaning.
    """
    # URL row first, under the H1 (Supabase: project URL + Copy
    # menu under the project name).
    ui_design.overview_url_row(_app_base_url(), _REPO_URL)
    _status = feat_status.get_status()
    _state = _status.get("state")
    _status_value = ("Healthy" if _state == "operational" else
                     "Cloud down" if _state == "unavailable" else
                     "Local mode")
    _status_sub = ("Supabase answered just now" if _state == "operational"
                   else "Cloud backend unreachable" if _state == "unavailable"
                   else "Accounts and files on this server")
    try:
        _used_bytes, _ = storage.storage_usage(storage_key)
        _storage_value = f"{_used_bytes / (1024 * 1024):.1f} MB of 1 GB"
    except Exception:  # noqa: BLE001 - storage is best-effort here
        _storage_value = "—"
    _kpis = st.session_state.get("kpis") or []
    if clean is not None:
        _rows_value, _rows_sub = f"{len(clean):,}", "Cleaned rows"
        _cols_value, _cols_sub = f"{len(clean.columns)}", "In this file"
        _kpis_value, _kpis_sub = f"{len(_kpis)}", "Auto KPIs"
        _file_value = str(st.session_state.get("source_name") or "—")[:24]
        _file_sub = str(st.session_state.get("source_kind") or "")
    else:
        _rows_value, _rows_sub = "—", "No data yet"
        _cols_value, _cols_sub = "—", "No data yet"
        _kpis_value, _kpis_sub = "—", "No data yet"
        _file_value, _file_sub = "—", "No data yet"
    _tiles = [
        ("Status", _status_value, _status_sub, "check"),
        ("Storage", _storage_value, "Free-tier bucket", "database"),
        ("Rows", _rows_value, _rows_sub, "table"),
        ("Columns", _cols_value, _cols_sub, "grid"),
        ("KPIs", _kpis_value, _kpis_sub, "chart"),
        ("File", _file_value, _file_sub, "file"),
    ]
    _row_a, _row_b = _tiles[:3], _tiles[3:]
    for _row in (_row_a, _row_b):
        _cols = st.columns(3)
        for _col, (_label, _value, _sub, _icon) in zip(_cols, _row):
            with _col:
                ui_design.kpi_tile(_label, _value, sub=_sub, icon=_icon)
    # Infrastructure diagram (Supabase's dotted canvas + Primary
    # Database node), mapped to this app's pipeline: Upload → Clean
    # → KPIs → Export, each node with its live count. No diagram/map
    # toggle — there is no map counterpart in this app, so the
    # diagram is the only view.
    _actions = st.session_state.get("actions") or []
    _nodes = [
        {"title": "Upload",
         "count": f"{len(raw):,} rows" if raw is not None else "—",
         "sub": (str(st.session_state.get("source_name") or "—")[:24]
                 if raw is not None else "No file yet")},
        {"title": "Clean",
         "count": f"{len(clean):,} rows" if clean is not None else "—",
         "sub": (f"{len(_actions)} cleaning steps" if _actions
                 else "Not cleaned yet" if raw is not None
                 else "No file yet")},
        {"title": "KPIs",
         "count": f"{len(_kpis)}" if _kpis else "—",
         "sub": "Auto KPIs" if _kpis else "No data yet"},
        {"title": "Export",
         "count": "Ready" if clean is not None else "—",
         "sub": "One-page report" if clean is not None
                else "Waiting for data"},
    ]
    ui_design.infra_diagram(_nodes)
    # "Get connected", for this app: the six ways in, as one strip.
    _cell = ui_design.connect_strip([
        {"key": "preview", "icon": "upload", "title": "Upload",
         "subtitle": "Load a file"},
        {"key": "clean", "icon": "clean", "title": "Clean",
         "subtitle": "Fix the messy bits"},
        {"key": "kpis", "icon": "kpis", "title": "KPIs",
         "subtitle": "See the numbers"},
        {"key": "dashboard", "icon": "chart", "title": "Charts",
         "subtitle": "Visualise it"},
        {"key": "report", "icon": "report", "title": "Report",
         "subtitle": "One-page export"},
        {"key": "tools", "icon": "tools", "title": "Tools",
         "subtitle": "Backups and more"},
    ])
    if _cell is not None:
        st.session_state["pending_tab"] = _cell
        st.rerun()
    # API metrics strip (Supabase: big "Total Requests" / "Success
    # Rate" numbers + service cards). Mapped honestly: "Rows
    # processed" is the loaded file's row count, "Success rate" is
    # the share of rows kept after cleaning — both "—" until the
    # state that measures them exists. No "Last 60 minutes"
    # dropdown: the numbers are for the current file, not a time
    # window, so the scope says so instead of faking one.
    _rows_processed = f"{len(raw):,}" if raw is not None else "—"
    if clean is not None and raw is not None and len(raw):
        _kept = f"{len(clean) / len(raw) * 100:.1f}%"
        _kept_sub = "Rows kept after cleaning"
    else:
        _kept, _kept_sub = "—", "Clean a file to measure it"
    _api_1, _api_2 = st.columns(2)
    with _api_1:
        st.markdown(
            '<div class="dcs-strip-label">Rows processed</div>'
            f'<div class="dcs-metric-value">{_rows_processed}</div>'
            '<div class="dcs-section-sub">Current file</div>',
            unsafe_allow_html=True)
    with _api_2:
        st.markdown(
            '<div class="dcs-strip-label">Success rate</div>'
            f'<div class="dcs-metric-value">{_kept}</div>'
            f'<div class="dcs-section-sub">{_kept_sub}</div>',
            unsafe_allow_html=True)
    # Service metric cards: the file's own data quality — or, with no
    # file loaded, the same cards empty (no numbers invented).
    if raw is not None:
        _missing = raw.isna().sum()
        _missing_total = int(_missing.sum())
        _cols_affected = int((_missing > 0).sum())
        _max_missing = int(_missing.max()) if len(_missing) else 0
        _bars = []
        for _c in list(raw.columns)[:24]:
            _n = int(_missing.get(_c, 0))
            _bars.append((_n / _max_missing * 100 if _max_missing else 0,
                          "warn" if _n > 0 else "ok"))
        _dups = int(raw.duplicated().sum())
        _m1, _m2 = st.columns(2)
        with _m1:
            ui_design.metric_card(
                "Missing cells", f"{_missing_total:,}",
                warnings=_cols_affected, errors=0, bars=_bars,
                sub=f"{_cols_affected} of {len(raw.columns)} columns affected")
        with _m2:
            ui_design.metric_card(
                "Duplicate rows", f"{_dups:,}",
                warnings=0, errors=_dups,
                sub="Exact duplicate rows in the file")
        _issues = _missing_total + _dups
    else:
        _m1, _m2 = st.columns(2)
        with _m1:
            ui_design.metric_card(
                "Missing cells", "—",
                warnings=0, errors=0, bars=[],
                sub="Load a file to check data quality")
        with _m2:
            ui_design.metric_card(
                "Duplicate rows", "—",
                warnings=0, errors=0,
                sub="Load a file to check data quality")
        _issues = None
    # Advisor block (Supabase: "Advisor found no issues" + "Ask
    # Assistant"). The heading IS the verdict; the detail line says
    # what was checked. "Ask Assistant" opens the How to use guide
    # — this app has no AI assistant panel, so the guide is the
    # honest counterpart. In the no-issues state Ask Assistant is
    # the only button (the old "How to use" button went to the same
    # place); the other states keep their action button beside it.
    if _issues is None:
        _adv_text = "No data loaded yet"
        _adv_detail = ("Upload a file and the Advisor will check it "
                       "for missing cells and duplicate rows.")
        _adv_go, _adv_label, _adv_icon = "preview", "Load a file", "upload"
        _adv_help = "Load a file."
    elif _issues == 0:
        _adv_text = "Advisor found no issues"
        _adv_detail = "No missing cells, no duplicate rows."
        _adv_go = None
    else:
        _adv_text = (f"Advisor found {_issues:,} issue"
                     f"{'s' if _issues != 1 else ''}")
        _adv_go, _adv_label, _adv_icon = "clean", "Go to Clean", "play"
        _adv_detail = "Missing cells and duplicate rows to fix."
        _adv_help = "Open the Clean tab."
    ui_design.section_heading(_adv_text)
    st.markdown(
        f'<div class="dcs-section-sub">{_adv_detail}</div>',
        unsafe_allow_html=True)
    _spacer, _b = st.columns([3, 1])
    with _b:
        if _adv_go is not None:
            if ui_design.icon_button(
                    _adv_label, _adv_icon, kind="primary",
                    key="dashboard_advisor_go",
                    help=_adv_help):
                st.session_state["pending_tab"] = _adv_go
                st.rerun()
        if ui_design.icon_button(
                "Ask Assistant", "sparkle", kind="secondary",
                key="dashboard_advisor_ask",
                help="Open the How to use guide."):
            st.session_state["pending_tab"] = "tutorial"
            st.rerun()


    # Reports section (Supabase: "Reports" + "Add block" + the
    # empty-state card). This app keeps no saved reports — the
    # Report tab builds the one-page report on the fly — so the
    # section is always the empty state, but its copy and its
    # buttons' destination follow the real state: no data ->
    # Preview, data -> Clean, cleaned -> Report.
    if clean is not None:
        _rep_go = "report"
        _rep_foot = ("Your data is cleaned — your one-page report "
                     "is ready to build.")
    elif raw is not None:
        _rep_go = "clean"
        _rep_foot = "Data loaded — clean it to unlock the report."
    else:
        _rep_go = "preview"
        _rep_foot = "No data loaded yet — load a file to start."
    _rh, _rb = st.columns([4, 1])
    with _rh:
        ui_design.section_heading("Reports")
    with _rb:
        if ui_design.icon_button(
                "Add block", "add", kind="secondary",
                key="dashboard_reports_add",
                help="Open the report builder."):
            st.session_state["pending_tab"] = _rep_go
            st.rerun()
    ui_design.card("Build a custom report",
                   body="Keep track of your most important metrics.",
                   footer=_rep_foot)
    if ui_design.icon_button(
            "Add your first block", "add", kind="secondary",
            key="dashboard_reports_first",
            help="Open the report builder."):
        st.session_state["pending_tab"] = _rep_go
        st.rerun()


# Rail behavior control (clone Round 1 — Supabase's bottom
# control): the 3-way menu (Expanded / Collapsed / Expand on
# hover). ONE render, in the MAIN area (top level), before the
# empty-state branches below — it must exist on every logged-in run,
# empty or data-loaded, and before any st.stop(). It is deliberately
# NOT in the sidebar: the hover-expand trigger is ``section:hover``
# on the sidebar, and the control must not be a descendant of the
# section, or hovering it re-expands the overlay (the round-8 :has()
# gate did not take effect live, so the gate is gone and the control
# moved out instead). The rail CSS pins it FIXED to the viewport's
# bottom-left at the rail's width, so it reads as the rail's foot.
# The old direct toggle is gone: it flipped the pinned bool, so a
# click in the hover flyout — where the rail looks expanded —
# flipped it to pinned-expanded, which the live check read as "the
# collapse doesn't stick" (rounds 8/9/10). The menu's radio
# on_change sets the mode and reruns itself; there is nothing for
# the caller to flip here. The old two sidebar renders (empty state
# + data-loaded) are deleted: a single main-area render covers both
# states.
ui_design.render_rail_behavior_menu()

# Keep the theme-preference + rail-mode cookies at the values in
# effect (Round 3): every shell control has rendered by now, so
# any on_change that fired this run has already updated session
# state — and this point is before the empty-state st.stop()s
# below, so it runs on every logged-in run, empty or data-loaded.
_ensure_pref_cookies()

if raw is None:
    # The Profile view needs no data: when the user asked for it
    # (sidebar Profile button, or already on the Profile tab), render
    # it here instead of stopping at the empty state — otherwise the
    # profile would be unreachable until a file is loaded. The Back
    # button returns to this empty state (the section switcher below
    # then defaults to the first tab on the next data load).
    _heading_to_profile = (
        st.session_state.get("pending_tab") == "profile"
        or st.session_state.get("active_tab") == "Profile")
    if _heading_to_profile:
        _profile_result = feat_profile.render_profile_view(
            st, _user, _skey, on_logout=_do_logout)
        if _profile_result in ("deleted", "logout"):
            _do_logout()
        if _profile_result == "back":
            # The sub-nav's "← Back to dashboard" — back to the
            # empty state (Preview, no data loaded). The old
            # "← Back to data" button below the content is gone:
            # the sub-nav's Back is the one way back now.
            st.session_state["pending_tab"] = "preview"
            st.rerun()
        st.stop()
    # The Status tab needs no data either (it reports the app's own
    # health and history): render it here too, same as Profile above.
    if st.session_state.get("active_tab") == "Status":
        feat_status.render_status_section(st)
        if st.button("← Back to data", key="status_empty_back"):
            st.session_state.pop("pending_tab", None)
            st.session_state.pop("active_tab", None)
            st.rerun()
        st.stop()
    # The Dashboard tab needs no data either: its strips are the
    # app's own health + the ways in, so render them (empty-state
    # values) instead of the generic "Nothing loaded yet" card —
    # otherwise the Dashboard is unreachable until a file is loaded,
    # and its strips never show.
    if _top_active == _nav_labels["dashboard"]:
        ui_design.section_heading(
            "Dashboard", sub="Your data's health, at a glance.")
        _render_dashboard_strips(st, None, None, _skey)
        st.stop()
    # The How to use tab needs no data either (it is the guide):
    # render it here too, same as Dashboard above — otherwise the
    # top-bar Help button and the Dashboard Advisor's "Ask
    # Assistant" button both dead-end on the empty state instead
    # of opening the guide.
    if _top_active == _nav_labels["tutorial"]:
        feat_tutorial.render_tutorial_page(st, settings_path=_settings_path)
        st.stop()
    # Guided empty state: what to do first, plus a one-click way to try
    # the sample — the same loader the sidebar "Try the messy sample"
    # button uses, not a second mechanism.
    if ui_design.empty_state(
            "Nothing loaded yet",
            "Upload a file from the sidebar on the left, load a Google "
            "Sheet, or open a database table — or skip the setup and "
            "explore with the sample file: it loads the messy sales "
            "data (80 rows) so you can see cleaning, KPIs and the report "
            "right away.",
            cta_label="Try the sample data"):
        _sample_path = _APP_DIR / "sample_data" / "messy_sales.csv"
        with branded_spinner("Loading the sample file…"):
            _set_raw(engine.load_file("messy_sales.csv",
                                      _sample_path.read_bytes()),
                     "messy_sales.csv (sample)", kind="sample")
        st.session_state["last_upload"] = None
        st.rerun()
    st.stop()

if (st.session_state.get("auto_refresh")
        and st.session_state.source_kind == "sheets"
        and st.session_state.get("source_url")):
    @st.fragment(run_every=st.session_state.get("refresh_seconds", 900))
    def _auto_refresh():
        changed = False
        try:
            fresh = engine.load_sheets_url(st.session_state["source_url"])
            if not fresh.equals(st.session_state["raw"]):
                opts = st.session_state.get("clean_opts")
                st.session_state["raw"] = fresh
                if opts:
                    cleaned, actions = engine.clean(
                        fresh, feat_automate.to_engine_opts(opts))
                    st.session_state["clean"] = cleaned
                    st.session_state["actions"] = actions
                    st.session_state["kpis"] = engine.auto_kpis(cleaned)
                else:
                    st.session_state["clean"] = None
                    st.session_state["actions"] = None
                    st.session_state["kpis"] = None
                changed = True
        except Exception:  # noqa: BLE001 - a failed refresh just waits
            changed = False
        if changed:
            st.rerun()

    _auto_refresh()

clean = st.session_state.clean

# ---------------------------------------------- workspace auto-save check ---
if _ws_on:
    _fp = (st.session_state.source_name, len(raw),
           len(clean) if clean is not None else None,
           len(st.session_state.actions) if st.session_state.actions else None)
    if st.session_state.get("n_ws_fingerprint") != _fp:
        try:
            _ws_folder = feat_enrich.save_workspace(
                raw, clean, st.session_state.source_name,
                st.session_state.actions, st.session_state.kpis,
                base_dir=_ws_dir)
            (_ws_folder / "autosave.txt").write_text("on", encoding="utf-8")
            st.session_state["n_ws_fingerprint"] = _fp
        except Exception:  # noqa: BLE001 - auto-save must never stop the app
            pass
elif _ws_marker.exists():
    try:
        _ws_marker.unlink()
    except OSError:
        pass

# -------------------------------------------- apply a pending saved view ---
_pending_view = st.session_state.pop("an_pending_view", None)
if _pending_view:
    _apply_pending_view(_pending_view)

# --------------------------------------------------------------- slicers ---
# The slicer widgets render only when the rail is pinned open (see
# the rail-state comment above — "FILTERS (SLICERS)" squeezed into
# vertical letters live). The FILTERING still runs while collapsed,
# but NOT by reading the widget keys: a widget's session-state
# value is cleaned up the moment the widget unmounts, so
# ``st.session_state.get("slice_<col>")`` returns the default the
# run after a collapse and the filter would reset. Instead every
# pick is copied to a plain (non-widget) ``slice_persist_<col>``
# key on every expanded run — plain keys survive unmounting — and
# the collapsed filter reads that key. The widget's default is
# also seeded from the persistent key, so re-opening the rail
# restores the pick instead of resetting to everything. A slicer
# never picked yet defaults to everything.
if not _rail_collapsed:
    st.sidebar.markdown(
        '<div class="dcs-micro-label">Filters (slicers)</div>',
        unsafe_allow_html=True)
filtered = clean
if clean is not None:
    num_cols = engine.numeric_cols(clean)
    cat_cols = [c for c in clean.columns
                if str(clean[c].dtype) in ("object", "str")
                and clean[c].nunique() <= 50]
    date_cols = engine.date_cols(clean)
    for c in cat_cols:
        _all_vals = sorted(clean[c].dropna().unique())
        _persist_key = f"slice_persist_{c}"
        if not _rail_collapsed:
            _persisted = st.session_state.get(_persist_key)
            _default = (_all_vals if _persisted is None else
                        [v for v in _persisted if v in _all_vals])
            picked = st.sidebar.multiselect(
                f"{engine._pretty(c)}", _all_vals,
                default=_default, key=f"slice_{c}")
            st.session_state[_persist_key] = list(picked)
        else:
            picked = st.session_state.get(_persist_key, _all_vals)
        filtered = filtered[filtered[c].isin(picked)]
    if date_cols:
        dcol = date_cols[0]
        dmin, dmax = clean[dcol].min(), clean[dcol].max()
        _dpersist_key = f"slice_persist_{dcol}"
        if not _rail_collapsed:
            start, end = st.sidebar.date_input(
                f"{engine._pretty(dcol)} range",
                value=st.session_state.get(
                    _dpersist_key, (dmin.date(), dmax.date())),
                key=f"slice_{dcol}")
            st.session_state[_dpersist_key] = (start, end)
        else:
            start, end = st.session_state.get(
                _dpersist_key, (dmin.date(), dmax.date()))
        if start and end:
            mask = (clean[dcol] >= pd.Timestamp(start)) & (
                clean[dcol] <= pd.Timestamp(end) + pd.Timedelta(days=1)
                - pd.Timedelta(seconds=1))
            filtered = filtered[mask]
    if not _rail_collapsed:
        st.sidebar.caption(f"Showing {len(filtered):,} of {len(clean):,} rows")

# (The rail toggle renders once, in the main area, before the
# empty-state branches above — round 9 moved it out of the
# sidebar so hovering it can never re-expand the overlay.)

_client = bool(st.session_state.get("client_mode", False))
# Main flow first (upload -> clean -> KPIs -> export), then the
# secondary views. Nothing removed — just ordered by how often it
# is used. Labels come from the shared _nav_labels mapping above.
_tab_keys = ["preview", "clean", "kpis", "dashboard", "report",
             "join", "compare", "tools", "tutorial", "settings", "profile",
             "status"]
if _client:
    _tab_keys = ["preview", "clean", "kpis", "dashboard", "report", "tutorial",
                 "profile", "status"]
_tab_labels = {k: _nav_labels[k] for k in _tab_keys}
# Section switcher: a horizontal radio, NOT st.tabs.
# Streamlit's tab selection is not sticky — it resets to the first
# tab after some actions (downloads, saves), yanking the user away
# from where they were. A radio IS sticky: its value lives in
# session state under "active_tab", survives every rerun, and can
# be set programmatically (e.g. back to the first section on
# logout). The design-system stylesheet at the top of this file styles
# the options as a tab bar; if those selectors ever stop matching
# a new Streamlit version it degrades to a plain option row, still
# fully working. `tab` stays a set of the available keys so the
# `if "join" in tab:` guards below keep working.
_tab_options = [_tab_labels[k] for k in _tab_keys]
# pending_tab was already applied up at the top bar, before the radio
# existed (writing the radio's session key after it exists raises
# StreamlitWidgetAlreadyInstantiatedError). Same idea as an_pending_view.
# Only re-check the value is still a valid option (e.g. the language
# changed since the label was stored).
if st.session_state.get("active_tab") not in _tab_options:
    st.session_state["active_tab"] = _tab_options[0]
_active_label = st.radio("Section", _tab_options, key="active_tab",
                         horizontal=True, label_visibility="collapsed")
_active_tab = next(k for k, v in _tab_labels.items()
                   if v == _active_label)
# Round 3e — the Quick Jump query must clear on a direct radio
# click too. The palette renders before this radio exists on the
# run, so it cannot see the change itself; note it here (flag +
# rerun when a query is typed — see feat_quickjump).
feat_quickjump.note_section_change(st, _active_label)
tab = set(_tab_keys)

# --------------------------------------------------------------- preview ---
if _active_tab == "preview":
    if _client and clean is not None:
        st.info(feat_analyse.client_summary(clean, st.session_state.kpis))
    if st.session_state.source_kind == "workspace":
        st.caption("Restored from your last auto-saved workspace.")
    ui_design.section_heading(
        f"Loaded: {st.session_state.source_name}",
        sub=f"{len(raw):,} rows, {len(raw.columns)} columns")
    # Column types, the way Supabase shows them (name text,
    # price numeric) — the type is part of the table's honesty.
    _col_types = "  ·  ".join(
        ui_design.column_type_label(c, str(raw[c].dtype))
        for c in list(raw.columns)[:12])
    if len(raw.columns) > 12:
        _col_types += f"  ·  +{len(raw.columns) - 12} more"
    st.markdown(_col_types, unsafe_allow_html=True)
    pasted = feat_enrich.render_paste(st)
    if pasted is not None:
        _set_raw(pasted, "Pasted table", kind="paste")
        raw = pasted
        clean = None
        filtered = None
    shown = feat_share.render_sort(st, raw)
    # Supabase-style toolbar above the table: search the preview, a
    # rows-per-page pick, and the green primary action (Clean now).
    # (The sort controls above and the whole-file search below stay —
    # this row is the table's own toolbar, the way the dashboard's
    # Tables list carries search + filter + a green New button.)
    _tb_search, _tb_rows, _tb_go = st.columns([2.2, 0.8, 1.0])
    with _tb_search:
        _preview_q = st.text_input(
            "Search the preview", key="preview_toolbar_search",
            placeholder="Filter these rows…", label_visibility="collapsed")
    with _tb_rows:
        _preview_n = st.selectbox(
            "Rows", [50, 100, 200], index=1, key="preview_toolbar_rows",
            label_visibility="collapsed")
    with _tb_go:
        if ui_design.icon_button(
                "Clean now", "play", kind="primary",
                key="preview_clean_now",
                help="Go to the Clean tab for this file.",
                use_container_width=True):
            st.session_state["pending_tab"] = "clean"
            st.rerun()
    if _preview_q and str(_preview_q).strip():
        shown = feat_share.search_rows(shown, str(_preview_q).strip())
    st.dataframe(shown.head(int(_preview_n)), width="stretch")
    # The "N tables" footer, for our table: how many rows are shown.
    st.caption(f"Showing {min(len(shown), int(_preview_n)):,} of "
               f"{len(shown):,} rows · {len(raw.columns)} columns")
    feat_share.render_search(st, raw)
    with st.expander("Search, filter & suggested fixes"):
        feat_enrich.render_filter_builder(st, raw)
        sugg_df, sugg_actions = feat_share.render_suggestions(st, raw)
        if sugg_df is not None:
            _set_raw(sugg_df, st.session_state.source_name)
            _audit("Suggestion applied",
                   sugg_actions[0][1] if sugg_actions else "Fix applied")
            raw = sugg_df
            clean = None
            filtered = None
    with st.expander("Health check & data dictionary"):
        profile = engine.profile(raw)
        ui_design.section_heading("Health check")
        st.write(f"Missing cells: {int(raw.isna().sum().sum()):,}  |  "
                 f"Duplicate rows: {int(raw.duplicated().sum())}")
        st.table(pd.DataFrame(profile))
        feat_quality.render_quality_panel(st, raw)
        feat_analyse.render_trust(st, raw)
        # One data dictionary, shown once: heading + table + download.
        # (render_dictionary would show the same table twice — once as
        # markdown, once as a dataframe — so the pieces are rendered
        # here directly from data_dictionary().)
        _dict_md, _dict_table = feat_quality.data_dictionary(raw)
        ui_design.section_heading("Data dictionary")
        st.dataframe(_dict_table, width="stretch")
        st.download_button("Download data dictionary (.md)",
                           _dict_md.encode("utf-8"),
                           file_name="data_dictionary.md",
                           key="q_dict_download")
        feat_export.render_column_charts(st, clean)

# ------------------------------------------------------------------ join ---
if "join" in tab:
    if _active_tab == "join":
        ui_design.section_heading(
            "Join two files",
            sub="Combine this file with a second one on a shared column — "
                "like a customer ID or order ID. Nothing changes until you "
                "press 'Use joined data'.")
        joined_file = st.file_uploader(
            "Second file (CSV, Excel or JSON)", type=["csv", "xlsx", "xls", "json"],
            key="join_upload")
        if joined_file is not None:
            try:
                right = engine.load_file(joined_file.name, joined_file.getvalue())
            except Exception as e:  # noqa: BLE001
                st.error(f"Could not read {joined_file.name}: {e}")
                right = None
            if right is not None:
                c1, c2, c3 = st.columns(3)
                left_key = c1.selectbox("Key in this file", list(raw.columns),
                                        key="join_left_key")
                right_key = c2.selectbox("Key in second file", list(right.columns),
                                         key="join_right_key")
                how_label = c3.selectbox(
                    "How to join",
                    ["Left (keep all rows from this file)",
                     "Inner (only matching rows)",
                     "Outer (keep everything)"],
                    key="join_how")
                how = {"Left (keep all rows from this file)": "left",
                       "Inner (only matching rows)": "inner",
                       "Outer (keep everything)": "outer"}[how_label]
                if st.button("Preview join", key="join_preview_btn"):
                    try:
                        st.session_state["join_result"] = engine.join_frames(
                            raw, right, left_key, right_key, how)
                    except Exception as e:  # noqa: BLE001
                        st.error(str(e))
                preview = st.session_state.get("join_result")
                if preview:
                    joined, info = preview
                    st.write(f"Left: {info['left_rows']:,} rows  ·  "
                             f"Right: {info['right_rows']:,} rows  →  "
                             f"Joined: {info['joined_rows']:,} rows")
                    st.write(f"Matched keys: {info['matched_keys']:,}  ·  "
                             f"Only in this file: {info['left_only']:,}  ·  "
                             f"Only in second file: {info['right_only']:,}")
                    st.dataframe(joined.head(100), width="stretch")
                    if st.button("Use joined data", type="primary", key="join_use"):
                        _set_raw(joined,
                                 f"{st.session_state['source_name']} + {joined_file.name}")
                        st.session_state["join_result"] = None
                        _audit("Join", f"{info['joined_rows']:,} rows")
                        st.success("Joined — now clean it in the Clean tab.")

# ----------------------------------------------------------------- clean ---
if _active_tab == "clean":
    # Round 3d: remember whether cleaned data existed when this
    # section started. The strip (top of the run) reads the
    # pre-section state, so a clean that lands DURING this section
    # would otherwise show its tick one render late (the Round 3c
    # live failure: no "Clean ✓" on the Clean page right after
    # the clean, until the next navigation). The rerun at the end
    # of the section (below) fixes it when the tick flips.
    _clean_had = st.session_state.clean is not None
    feat_automate.render_undo(st)
    restored = feat_share.render_backups(
        st, df=raw, source_name=st.session_state.source_name,
        base_dir=_user_root, storage_key=_skey,
        key_prefix="s_backup_clean")
    if restored is not None:
        _set_raw(restored,
                 st.session_state.source_name + " (restored from backup)")
        raw = restored
        clean = None
        filtered = None
    ui_design.section_heading(
        "Clean my data",
        sub="Tick what to fix, then press the button. Every fix is listed "
            "in the log below, so you can check the work.")
    opts = {
        "tidy_names": st.checkbox("Tidy column names", value=True),
        "strip": st.checkbox("Strip extra spaces from text", value=True),
        "drop_empty": st.checkbox("Drop empty columns and rows", value=True),
        "fix_numbers": st.checkbox("Fix numbers stored as text (₹, $, %, commas)",
                                   value=True),
        "parse_dates": st.checkbox("Parse dates", value=True),
        "fix_categories": st.checkbox("Set categories to one case", value=True),
        "drop_dupes": st.checkbox("Drop duplicate rows", value=True),
        "fill_missing": st.checkbox("Fill missing values", value=True),
    }
    if ui_design.icon_button(_t("clean_my_data"), "clean", kind="primary",
                             key="clean_btn"):
        feat_automate.push_snapshot(st.session_state, "Before cleaning")
        _opts = feat_automate.to_engine_opts(opts)
        with branded_spinner("Cleaning your data…"):
            if (len(raw) > 100_000 and uploaded is not None
                    and uploaded.name.lower().endswith(".csv")):
                # Big file: clean in chunks (same result, less memory).
                cleaned, actions = engine.clean_csv_chunked(
                    uploaded.getvalue(), _opts)
            else:
                cleaned, actions = engine.clean(raw, _opts)
        st.session_state.clean = cleaned
        st.session_state.actions = actions
        st.session_state.kpis = engine.auto_kpis(cleaned)
        st.session_state.clean_opts = opts
        _audit("Clean", f"{len(raw):,} -> {len(cleaned):,} rows")
        _save_cleaned_copy(cleaned, st.session_state.source_name)
        clean = cleaned
        filtered = cleaned
    _samp = feat_enrich.render_sampling(
        st, raw,
        clean_opts=feat_automate.to_engine_opts(opts))
    if _samp is not None:
        _full_clean, _full_actions = engine.clean(raw, _samp["clean_opts"])
        feat_automate.push_snapshot(st.session_state, "Before sampling apply")
        st.session_state.clean = _full_clean
        st.session_state.actions = _full_actions
        st.session_state.kpis = engine.auto_kpis(_full_clean)
        _audit("Sampling applied to full file", f"{len(raw):,} rows")
        _save_cleaned_copy(_full_clean, st.session_state.source_name)
        clean = _full_clean
        filtered = _full_clean
    if clean is not None:
        st.success(f"Done: {len(raw):,} rows -> {len(clean):,} rows, "
                   f"{len(raw.columns)} -> {len(clean.columns)} columns.")
        ui_design.section_heading("What was fixed")
        for step, detail in st.session_state.actions:
            st.write(f"- **{step}:** {detail}")
        st.dataframe(clean.head(100), width="stretch")

        ui_design.section_heading(
            "Fix similar names (fuzzy matching)",
            sub="Finds misspellings like Aarav / Arav and Delhi / Dehli "
                "and merges them into one spelling. You review the groups "
                "first — nothing merges without your word.")
        text_cols = [c for c in clean.columns
                     if str(clean[c].dtype) in ("object", "str")
                     and 1 < clean[c].nunique() <= 500]
        if text_cols:
            fcol = st.selectbox("Column", text_cols, key="fuzzy_col")
            fthr = st.slider("How similar must names be? (higher = stricter)",
                             0.70, 0.95, 0.85, 0.01, key="fuzzy_thr")
            if st.button("Find similar names", key="fuzzy_find"):
                st.session_state["fuzzy_groups"] = engine.fuzzy_groups(
                    clean[fcol], fthr)
                st.session_state["fuzzy_col_used"] = fcol
            groups = st.session_state.get("fuzzy_groups")
            if groups is not None:
                if len(groups) == 0:
                    st.info("No similar names found in that column.")
                else:
                    for g in groups:
                        members = ", ".join(f"{v} ({n:,})"
                                            for v, n in g["members"])
                        st.write(f"→ **{g['canonical']}**: {members}")
                    if st.button("Merge these names",
                                 key="fuzzy_apply"):
                        mapping = {}
                        for g in groups:
                            for v, _ in g["members"][1:]:
                                mapping[v] = g["canonical"]
                        feat_automate.push_snapshot(
                            st.session_state, "Before fuzzy merge")
                        new_clean = engine.apply_fuzzy(
                            clean, st.session_state["fuzzy_col_used"], mapping)
                        st.session_state["clean"] = new_clean
                        st.session_state["actions"] = (
                            st.session_state["actions"]
                            + [(f"Fuzzy merge: {st.session_state['fuzzy_col_used']}",
                              f"{len(mapping)} spelling(s) merged")])
                        st.session_state["kpis"] = engine.auto_kpis(new_clean)
                        st.session_state["fuzzy_groups"] = None
                        _audit("Fuzzy merge",
                               f"{len(mapping)} spelling(s) merged")
                        clean = new_clean
                        filtered = new_clean
                        st.success(f"Merged {len(mapping)} spelling(s) into "
                                   "their main form.")
        else:
            st.info("No text column with a manageable number of values "
                    "in this file.")

        with st.expander("More fixes (column type, phones, special characters)"):
            _ov = feat_share.render_type_override(st, clean)
            if _ov is not None:
                _ov_col = st.session_state.get("s_type_col", "?")
                _ov_kind = st.session_state.get("s_type_kind", "?")
                clean = _apply_new_clean(
                    _ov, [("Column type override",
                           f"{_ov_col} forced to {_ov_kind}")],
                    "Column type override")
                filtered = clean
            _nd, _na = feat_share.render_standardize_phones(st, clean)
            if _nd is not None:
                clean = _apply_new_clean(_nd, _na, "Standardize phones")
                filtered = clean
            _nd, _na = feat_share.render_strip_specials(st, clean)
            if _nd is not None:
                clean = _apply_new_clean(_nd, _na, "Strip special characters")
                filtered = clean

        with st.expander("Recipes & templates"):
            new_df, new_actions = feat_automate.render_recipes(st, raw)
            if new_df is not None:
                clean = _apply_new_clean(new_df, new_actions, "Recipe applied",
                                         replace_actions=True)
                filtered = clean
            new_df, new_actions = feat_automate.render_templates(st)
            if new_df is not None:
                clean = _apply_new_clean(new_df, new_actions, "Template applied",
                                         replace_actions=True)
                filtered = clean
            _recipes = st.session_state.get("a_recipes") or []
            _picked_name = st.session_state.get("a_recipe_select")
            _recipe = (next((r for r in _recipes if r["name"] == _picked_name),
                            None) if _picked_name else None)
            _imported = feat_analyse.render_share_recipe(st, _recipe)
            if _imported is not None:
                _recipes[:] = [r for r in _recipes
                               if r["name"] != _imported["name"]]
                _recipes.append(_imported)
            # Persist recipes per user (recipes/recipes.json).
            try:
                storage.save_json(_skey, "recipes", "recipes.json",
                                  list(st.session_state.get("a_recipes") or []))
            except Exception:  # noqa: BLE001 - recipe save must never stop the app
                pass

        with st.expander("Fix values"):
            new_df, new_actions = feat_automate.render_find_replace(st, clean)
            if new_df is not None:
                clean = _apply_new_clean(new_df, new_actions, "Find and replace")
                filtered = clean
            new_df, new_actions = feat_combine.render_calculated(st, clean)
            if new_df is not None:
                clean = _apply_new_clean(new_df, new_actions, "Calculated column")
                filtered = clean
            new_df, new_actions = feat_quality.render_outliers(st, clean)
            if new_df is not None:
                clean = _apply_new_clean(new_df, new_actions, "Outliers")
                filtered = clean
            new_df, new_actions = feat_quality.render_near_dupes(st, clean)
            if new_df is not None:
                clean = _apply_new_clean(new_df, new_actions, "Near-duplicates merged")
                filtered = clean
            feat_quality.render_validation(st, clean)
            _nd, _na = feat_enrich.render_split_merge(st, clean)
            if _nd is not None:
                clean = _apply_new_clean(_nd, _na, "Split / merge columns")
                filtered = clean
            _nd, _na = feat_enrich.render_date_intelligence(st, clean)
            if _nd is not None:
                clean = _apply_new_clean(_nd, _na, "Date intelligence")
                filtered = clean
            _nd, _na = feat_enrich.render_currency(st, clean)
            if _nd is not None:
                clean = _apply_new_clean(_nd, _na, "Currency conversion")
                filtered = clean
            feat_enrich.render_masking(st, clean)

        with st.expander("Clean many files at once"):
            feat_automate.render_bulk(st)
    # Round 3d: if this section flipped the Clean tick (data
    # cleaned for the first time, or a restore/undo cleared it),
    # rerun now so the strip — rendered at the top of the run,
    # before this section — shows the tick in the same view as
    # the "Done" message, not one render later. The "Done" line
    # re-renders from state on the rerun (it reads the local
    # `clean`, set from session state at the top of the run), so
    # nothing is lost; and the rerun fires only on the flip,
    # never on later fix-ups (the tick is already on then) or on
    # a re-clean (nothing flipped), so it cannot loop.
    if (st.session_state.clean is not None) != _clean_had:
        st.rerun()

# ------------------------------------------------------------------ KPIs ---
if _active_tab == "kpis":
    if clean is None:
        if ui_design.empty_state(
                "No KPIs yet",
                "Your file is loaded — now clean it and the KPIs will "
                "appear here. Go to the Clean tab, tick what to fix, and "
                "press the clean button.",
                cta_label="Go to the Clean tab"):
            # Via pending_tab, not a direct active_tab write: the Section
            # radio is already instantiated by the time this button runs.
            st.session_state["pending_tab"] = "clean"
            st.rerun()
    else:
        ui_design.section_heading("KPIs")
        kpis = engine.auto_kpis(filtered)
        cols = st.columns(3)
        for i, k in enumerate(kpis):
            with cols[i % 3]:
                ui_design.kpi_tile(k["label"], str(k["value"]))
        ui_design.section_heading("Build your own KPI")
        num_cols = engine.numeric_cols(clean)
        if num_cols:
            c1, c2, c3 = st.columns(3)
            kcol = c1.selectbox("Column", num_cols, key="kpi_col")
            kfn = c2.selectbox("Function",
                               ["Sum", "Average", "Count", "Min",
                                "Max", "Median"], key="kpi_fn")
            if c3.button("Add KPI", key="kpi_add"):
                value = engine.custom_kpi(filtered, kcol, kfn)
                st.session_state.kpis = st.session_state.kpis + [
                    {"label": f"{kfn} of {engine._pretty(kcol)}",
                     "value": f"{value:,.2f}"}]
            for k in st.session_state.kpis:
                if k["label"].startswith(("Sum of", "Average of", "Count of",
                                          "Min of", "Max of",
                                          "Median of")):
                    st.write(f"- **{k['label']}:** {k['value']}")
        feat_share.render_goal(st, filtered)
        feat_analyse.render_what_if(st, filtered)
        feat_enrich.render_ai_insights(st, filtered, st.session_state.kpis)



if _active_tab == "dashboard":
    # The strips always render — including the empty state, where they
    # show "—" / "No data yet" instead of invented numbers (see
    # _render_dashboard_strips). The old "No charts yet" empty-state
    # card hid the strips entirely, so it is gone; the Advisor line
    # above is the next step now.
    ui_design.section_heading(
        "Dashboard",
        sub=("Your data's health, at a glance."
             if clean is None else
             "The slicers on the left filter every chart and KPI here."))
    _render_dashboard_strips(st, clean, raw, _skey)
    if clean is not None:
        import altair as alt

        df = filtered
        num_cols = engine.numeric_cols(clean)
        cat_cols = [c for c in clean.columns
                    if str(clean[c].dtype) in ("object", "str")
                    and clean[c].nunique() <= 50]
        date_cols = engine.date_cols(clean)
        _ct_now = st.session_state.get("chart_type", "Bar")
        _gb_now = _nc_now = None
        if _ct_now in ("Bar", "Line", "Donut"):
            _gb_now = st.session_state.get("dash_x")
            _nc_now = st.session_state.get("dash_y")
        elif _ct_now == "Histogram":
            _nc_now = st.session_state.get("hist_col")
        elif _ct_now == "Scatter":
            _gb_now = st.session_state.get("sc_x")
            _nc_now = st.session_state.get("sc_y")
        elif _ct_now == "Box plot":
            _gb_now = st.session_state.get("box_x")
            _nc_now = st.session_state.get("box_y")
        elif _ct_now == "Treemap":
            _gb_now = st.session_state.get("tm_x")
            _nc_now = st.session_state.get("tm_y")
        elif _ct_now == "Funnel":
            _gb_now = st.session_state.get("fn_x")
            _nc_now = st.session_state.get("fn_y")
        _slicers_now = {}
        for _c in cat_cols:
            _k = f"slice_{_c}"
            if _k in st.session_state:
                _slicers_now[_c] = list(st.session_state[_k])
        _view_now = (None if (_gb_now is None and _nc_now is None) else
                     {"chart_type": _ct_now, "group_by": _gb_now,
                      "num_col": _nc_now, "slicers": _slicers_now})
        _applied_view = feat_analyse.render_saved_views(st, _view_now)
        if _applied_view is not None:
            st.session_state["an_pending_view"] = _applied_view
            st.rerun()
        chart_type = st.selectbox(
            "Chart", ["Bar", "Line", "Donut", "Histogram", "Scatter",
                      "Box plot", "Heatmap", "Treemap", "Funnel"],
            key="chart_type")
        grouped = None
        gx = gy = None
        if chart_type == "Histogram":
            hcol = st.selectbox("Number column", num_cols, key="hist_col")
            chart = alt.Chart(df).mark_bar().encode(
                x=alt.X(hcol, bin=True), y="count()",
                tooltip=["count()"]).properties(height=380)
            st.altair_chart(chart, width="stretch")
            st.write(df[hcol].describe().to_frame().T)
        elif chart_type == "Scatter":
            c1, c2, c3 = st.columns(3)
            sx = c1.selectbox("X (number)", num_cols, key="sc_x")
            sy = c2.selectbox("Y (number)", num_cols, key="sc_y")
            color = c3.selectbox("Colour by (optional)",
                                 ["(none)"] + cat_cols, key="sc_c")
            enc = {"x": sx, "y": sy, "tooltip": [sx, sy]}
            if color != "(none)":
                enc["color"] = color
            chart = alt.Chart(df).mark_circle(size=60).encode(
                **enc).properties(height=380)
            st.altair_chart(chart, width="stretch")
        elif chart_type == "Box plot":
            c1, c2 = st.columns(2)
            bx = c1.selectbox("Group by", cat_cols, key="box_x")
            by = c2.selectbox("Number", num_cols, key="box_y")
            chart = alt.Chart(df).mark_boxplot().encode(
                x=bx, y=by).properties(height=380)
            st.altair_chart(chart, width="stretch")
        elif chart_type == "Heatmap":
            if len(num_cols) < 2:
                st.info("Need at least two number columns for a heatmap.")
            else:
                st.altair_chart(feat_export.heatmap_corr(df), width="stretch")
        elif chart_type == "Treemap":
            c1, c2 = st.columns(2)
            tx = c1.selectbox("Group by", cat_cols, key="tm_x")
            ty = c2.selectbox("Size by", num_cols, key="tm_y")
            st.altair_chart(feat_export.treemap_chart(df, tx, ty),
                            width="stretch")
        elif chart_type == "Funnel":
            c1, c2 = st.columns(2)
            fx = c1.selectbox("Step", cat_cols, key="fn_x")
            fy = c2.selectbox("Value", num_cols, key="fn_y")
            st.altair_chart(feat_export.funnel_chart(df, fx, fy),
                            width="stretch")
        else:
            c1, c2, c3 = st.columns(3)
            x_col = c1.selectbox(
                "Group by", cat_cols + date_cols, key="dash_x")
            y_col = c2.selectbox("Number", num_cols, key="dash_y")
            grouped = df.groupby(x_col, dropna=False)[y_col].sum().reset_index()
            grouped = grouped.sort_values(y_col, ascending=False)
            gx, gy = x_col, y_col
            if chart_type == "Bar":
                chart = alt.Chart(grouped).mark_bar().encode(
                    x=alt.X(x_col, sort=None),
                    y=y_col, tooltip=[x_col, y_col]).properties(height=380)
            elif chart_type == "Line":
                chart = alt.Chart(grouped).mark_line(point=True).encode(
                    x=x_col, y=y_col,
                    tooltip=[x_col, y_col]).properties(height=380)
            else:
                chart = alt.Chart(grouped).mark_arc().encode(
                    theta=y_col, color=x_col,
                    tooltip=[x_col, y_col]).properties(height=380)
            st.altair_chart(chart, width="stretch")
            ui_design.section_heading("The numbers behind the chart")
            _grouped_display = grouped.copy()
            _grouped_display[y_col] = _grouped_display[y_col].map(
                lambda v: (f"{v:,.2f}" if float(v) % 1 else f"{v:,.0f}")
                if pd.notna(v) else v)
            st.dataframe(_grouped_display, width="stretch")
            feat_share.render_chart_png(
                st, grouped, x_col, y_col, title=f"{x_col} vs {y_col}",
                kind="line" if chart_type == "Line" else "bar",
                key_suffix="_dash")

        # ---- shareable read-only dashboard link (snapshot, not live data) ----
        with st.expander("Share this dashboard"):
            st.write("Creates a read-only link anyone can open without logging "
                     "in. It shows a saved snapshot of the KPIs and the chart "
                     "numbers — not your files, and not live data. You can "
                     "revoke it any time in Settings.")
            if st.button("Share dashboard", key="share_create_btn"):
                try:
                    _snap_grouped = grouped
                    _snap_gx, _snap_gy = gx, gy
                    if _snap_grouped is None and cat_cols and num_cols:
                        _snap_gx = cat_cols[0]
                        _snap_gy = num_cols[0]
                        _snap_grouped = df.groupby(
                            _snap_gx, dropna=False)[_snap_gy].sum().reset_index()
                        _snap_grouped = _snap_grouped.sort_values(
                            _snap_gy, ascending=False)
                    _rows = []
                    if _snap_grouped is not None:
                        _rows = [{str(k): (None if pd.isna(v) else v)
                                  for k, v in row.items()}
                                 for row in
                                 _snap_grouped.head(50).to_dict("records")]
                    _token = secrets.token_urlsafe(24)
                    with branded_spinner("Creating your share link…"):
                        _registry = storage.load_json(_skey, "views", _SHARES_FILENAME)
                        if not isinstance(_registry, dict):
                            _registry = {}
                        _registry[_token] = {
                            "title": f"{_brand.get('name', 'Data Cleaner Studio')} — shared dashboard",
                            "kpis": [{"label": str(k.get("label", "")),
                                      "value": str(k.get("value", ""))}
                                     for k in (st.session_state.kpis or [])],
                            "rows": _rows,
                            "x_col": str(_snap_gx) if _snap_gx else None,
                            "y_col": str(_snap_gy) if _snap_gy else None,
                            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "revoked": False,
                        }
                        storage.save_json(_skey, "views", _SHARES_FILENAME, _registry)
                    st.session_state["last_share_token"] = _token
                    st.success("Share link created — it stays valid until you "
                               "revoke it in Settings.")
                except Exception as e:  # noqa: BLE001 - show the error, don't crash
                    st.error(f"Could not create the share link: {e}")
            _last_token = st.session_state.get("last_share_token")
            if _last_token:
                st.code(f"{_app_base_url()}?share={_last_token}",
                        language="text")
                st.caption("Anyone with this link can open the read-only dashboard — no login needed.")

        # One pivot table only: render_pivot() prints its own heading.
        feat_combine.render_pivot(st, df)
        with st.expander("More analysis"):
            feat_analyse.render_correlations(st, df)
            feat_analyse.render_forecast(st, df)
            feat_analyse.render_ask(st, df)

# --------------------------------------------------------------- compare ---
if "compare" in tab:
    if _active_tab == "compare":
        ui_design.section_heading(
            "Compare & combine",
            sub="See what changed between two files, stack files together, "
                "or check whether this month's numbers jumped.")
        feat_combine.render_compare(st)
        with st.expander("Combine & check (stack files, anomalies, multi-KPI)"):
            feat_combine.render_append(st)
            if clean is not None:
                feat_combine.render_anomaly(st, clean)
            feat_analyse.render_multi_kpi(st)

# ---------------------------------------------------------------- report ---
if _active_tab == "report":
    if clean is None:
        if ui_design.empty_state(
                "No report yet",
                "Your file is loaded — now clean it and the report will "
                "appear here, with the cleaned file to download. Go to "
                "the Clean tab, tick what to fix, and press the clean "
                "button.",
                cta_label="Go to the Clean tab"):
            # Via pending_tab, not a direct active_tab write: the Section
            # radio is already instantiated by the time this button runs.
            st.session_state["pending_tab"] = "clean"
            st.rerun()
    else:
        # Section rhythm: a generous gap before the report, the way
        # the research's 128px marketing rhythm works at dashboard
        # scale.
        ui_loading.section_gap(px=64)
        ui_design.section_heading("Report")
        report = engine.build_report(raw, clean, st.session_state.actions,
                                     st.session_state.kpis)
        st.markdown(report)
        _formulas = st.checkbox("Excel KPIs as live formulas",
                                value=True, key="rep_formulas",
                                help="The Excel workbook gets a 'KPIs (live)' "
                                     "sheet where totals are real Excel "
                                     "formulas, not just numbers.")
        _brand_x = feat_brand.brand_for_exports(base_dir=_user_root)
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.download_button(_t("download_report") + " (.md)", report,
                           file_name="report.md", key="dl_report")
        c2.download_button("Download cleaned CSV",
                           clean.to_csv(index=False).encode("utf-8"),
                           file_name="cleaned_data.csv", key="dl_csv")
        c3.download_button("Download cleaned Excel",
                           engine.to_excel_bytes(clean, st.session_state.kpis,
                                                 st.session_state.actions,
                                                 formulas=_formulas),
                           file_name="cleaned_data.xlsx", key="dl_xlsx")
        pdf_bytes = engine.to_pdf_bytes(
            "Data Cleaner Studio — Report", st.session_state.kpis,
            st.session_state.actions,
            f"Rows: {len(raw):,} loaded -> {len(clean):,} after cleaning. "
            f"Columns: {len(raw.columns)} -> {len(clean.columns)}.",
            brand=_brand_x)
        c4.download_button("Download PDF report", pdf_bytes,
                           file_name="report.pdf", mime="application/pdf",
                           key="dl_pdf")
        c5.download_button("Download cleaned Parquet",
                           engine.to_parquet_bytes(clean),
                           file_name="cleaned_data.parquet",
                           key="dl_parquet")
        _oc_opts = (st.session_state.get("clean_opts")
                    or dict(feat_automate.DEFAULT_CLEAN_OPTS))
        _oc = feat_share.render_one_click(st, raw, _oc_opts,
                                          base_dir=_user_root,
                                          storage_key=_skey)
        _oc_ran = isinstance(_oc, dict) and _oc.get("status") == "done"
        if _oc_ran:
            st.session_state.clean = _oc["cleaned"]
            st.session_state.actions = _oc["actions"]
            st.session_state.kpis = _oc["kpis"]
            st.session_state.clean_opts = _oc_opts
            _audit("One-click flow",
                   f"{len(raw):,} -> {len(_oc['cleaned']):,} rows")
            _save_cleaned_copy(_oc["cleaned"], st.session_state.source_name)
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
                    st, st.session_state.kpis, st.session_state.actions,
                    _grouped, _gx, _gy, brand=_brand_x)
                feat_share.render_chart_png(
                    st, _grouped, _gx, _gy, title=f"{_gx} vs {_gy}",
                    key_suffix="_report")
            feat_share.render_portfolio_download(
                st, clean, st.session_state.kpis, st.session_state.actions)
            feat_share.render_styled_excel_download(
                st, clean, st.session_state.kpis, st.session_state.actions)
            feat_export.render_pptx_download(
                st, st.session_state.kpis, st.session_state.actions, raw, clean,
                brand=_brand_x)
            feat_export.render_sheets_export(st, clean)
            if not _oc_ran:
                feat_export.render_email_schedule(
                    st, st.session_state.kpis, st.session_state.actions, raw, clean)
            feat_quality.render_audit(st)

# ----------------------------------------------------------------- tools ---
if "tools" in tab:
    if _active_tab == "tools":
        ui_design.section_heading(
            "Watch folder (automatic cleaning)",
            sub="The app cleans files while it is open. For hands-free "
                "cleaning, run this small script: drop a messy file into a "
                "folder and the cleaned version appears in the output folder "
                "by itself.")
        watch_path = _APP_DIR / "watch_folder.py"
        if watch_path.exists():
            st.download_button("Download watch_folder.py",
                               watch_path.read_bytes(),
                               file_name="watch_folder.py", key="tools_watch_dl")
        st.code("python watch_folder.py --watch incoming --out cleaned "
                "--recipe my_recipe.json", language="bash")
        st.write("Save a recipe from the Clean tab first, then point the "
                 "script at it. It also works with `--once` to clean the files "
                 "already waiting in the folder and stop.")
        feat_schedule.render_schedule_section(st)
        with st.expander("Shortcuts & morning run"):
            feat_analyse.render_morning_run(st)
            feat_analyse.render_shortcuts_panel(st)
        with st.expander("Backups & live databases"):
            _restored_tools = feat_share.render_backups(
                st, base_dir=_user_root, storage_key=_skey,
                key_prefix="s_backup_tools")
            if _restored_tools is not None:
                _set_raw(_restored_tools,
                         st.session_state.source_name + " (restored from backup)")
            ui_design.section_heading("Live database connections")
            _db_df, _db_name = feat_export.render_db_connect(st)
            if _db_df is not None:
                _set_raw(_db_df, _db_name, kind="database")
                _audit("Database load", f"{len(_db_df):,} rows from {_db_name}")
                st.success(f"Loaded {_db_name} — clean it in the Clean tab.")

# ------------------------------------------------------------- tutorial ---
if "tutorial" in tab:
    if _active_tab == "tutorial":
        feat_tutorial.render_tutorial_page(st, settings_path=_settings_path)

# -------------------------------------------------------------- settings ---
if "settings" in tab:
    if _active_tab == "settings":
        ui_design.section_heading("Settings")

        # Account — one bordered card: label + description left, the
        # account + Open Profile action right, the backend detail
        # underneath inside the same card.
        # Supabase connection status (Phase 2, wired in): backend from
        # auth.get_auth_backend(), problem text from
        # auth.get_backend_warning() — shown verbatim, so a paused
        # free project reads exactly "Project paused — restore it in
        # the Supabase dashboard".
        _backend = auth.get_auth_backend()
        _backend_label = ("Local (this server)" if _backend == "local"
                          else "Cloud (Supabase)")
        _acct_left, _acct_right, _acct_card = ui_design.settings_card(
            "Account",
            "Who is signed in, and which backend holds the account.")
        with _acct_right:
            st.write(f"Signed in as **{_user.get('display_name') or _user.get('username') or _user.get('email') or '?'}** "
                     f"(account backend: **{_backend_label}**).")
            if ui_design.icon_button(
                    "Open Profile", "profile",
                    key="settings_open_profile",
                    help="Open the Profile tab."):
                st.session_state["pending_tab"] = "profile"
                st.rerun()
        with _acct_card:
            _config_exists = auth.SUPABASE_CONFIG_PATH.is_file()
            _env_configured = bool((os.environ.get("SUPABASE_URL") or "").strip()
                                   and (os.environ.get("SUPABASE_ANON_KEY") or "").strip())
            _cloud_ready = _config_exists or _env_configured
            st.write("Cloud setup: "
                     f"{'connected ✓' if _cloud_ready else 'not set up yet'}")
            _warn = auth.get_backend_warning()
            if _warn:
                st.warning(_warn)
            if _backend == "local":
                st.info("Local mode — accounts live in a file on this "
                        "server, and your files live in your folder on this "
                        "server. That means: your data leaves your computer — "
                        "it lives on the server. Cloud accounts (including "
                        "Google sign-in) need a Supabase project: create the "
                        "free project, add its URL and anon key to the app's "
                        "secrets, and run the setup SQL in the Supabase SQL "
                        "editor. Full steps: "
                        "[README.md — Auth: Supabase](README.md) and "
                        "[DEPLOY.md — section 0](DEPLOY.md). "
                        "Local accounts and Supabase accounts are different "
                        "users — switching backends means re-registering.")
            else:
                st.success("Cloud accounts are active (Supabase). Sign in "
                           "with your email and password, or with Google if "
                           "it is enabled in the Supabase dashboard. Your "
                           "local-mode account (if you had one) is a "
                           "different user — it does not carry over.")

        # AI keys — one bordered card: label + description left, the
        # two key inputs right, Save at the card's bottom-right.
        _keys_left, _keys_right, _keys_card = ui_design.settings_card(
            "AI keys",
            "Your own keys, stored per user. AI insights and "
            "natural-language questions use them; they are saved in "
            "your folder only, never baked into the code or the repo. "
            "Leave a field empty to turn that provider off.")
        _cur_settings = ai_settings.load_settings()
        _groq_set = bool((_cur_settings.get("groq_api_key") or "").strip())
        _gemini_saved = ""
        try:
            _stored_settings = storage.load_json(_skey, "views", "settings.json")
            if isinstance(_stored_settings, dict):
                _gemini_saved = str(_stored_settings.get("gemini_api_key") or "")
        except Exception:  # noqa: BLE001
            _stored_settings = None
        with _keys_right:
            st.write(f"Groq key: {'set ✓' if _groq_set else 'not set'}  ·  "
                     f"Gemini key: {'set ✓' if _gemini_saved.strip() else 'not set'}")
            _new_groq = st.text_input("Groq API key", type="password",
                                      key="settings_groq_key",
                                      help="Starts with gsk_ — get one free at console.groq.com. "
                                           "Leave empty to keep the saved key.")
            _new_gemini = st.text_input("Gemini API key", type="password",
                                        key="settings_gemini_key",
                                        help="Google AI Studio key. The app stores it; "
                                             "the Groq endpoint is used first when both are set. "
                                             "Leave empty to keep the saved key.")
        with _keys_card:
            _sp, _save_col = st.columns([3, 1])
            with _save_col:
                if ui_design.icon_button(
                        "Save API keys", "check", kind="primary",
                        key="settings_keys_save", use_container_width=True,
                        help="Save the keys you typed."):
                    _merged = dict(ai_settings.load_settings())
                    if isinstance(_stored_settings, dict):
                        for _k, _v in _stored_settings.items():
                            if _k not in _merged:
                                _merged[_k] = _v
                    if _new_groq.strip():
                        _merged["groq_api_key"] = _new_groq.strip()
                    if _new_gemini.strip():
                        _merged["gemini_api_key"] = _new_gemini.strip()
                    try:
                        storage.save_json(_skey, "views", "settings.json", _merged)
                        st.success("API keys saved in your folder.")
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Could not save the keys: {e}")

        # One "Your brand" heading only: render_brand_section prints its own.
        feat_brand.render_brand_section(st, base_dir=_user_root)

        with st.expander("Scheduled refresh jobs"):
            st.write("Jobs refresh a Google Sheet or a database table into "
                     "your folder on a schedule. The app only manages the "
                     "list below — the refresh itself is done by the separate "
                     "scheduler process (`python scheduler.py --daemon`), "
                     "which is not running inside this app. On Streamlit "
                     "Community Cloud the daemon cannot run at all.")
            st.write("The default interval below is 3 days — a regular job "
                     "keeps your data fresh without refreshing every hour.")
            _jobs_file = scheduler.DEFAULT_JOBS_FILE
            _payload, _jobs_err = scheduler.load_registry(_jobs_file)
            if _jobs_err:
                st.error(f"Could not read the job registry: {_jobs_err}")
                _payload = {"version": 1, "jobs": []}
            _all_jobs = _payload.get("jobs", []) if isinstance(_payload, dict) else []
            _my_idx = [i for i, j in enumerate(_all_jobs)
                       if isinstance(j, dict) and j.get("user") == _skey]
            if not _my_idx:
                st.info("No scheduled jobs yet.")
            for _pos, _ji in enumerate(_my_idx):
                _job = _all_jobs[_ji]
                _c1, _c2, _c3 = st.columns([3, 1, 1])
                _c1.write(f"**{_job.get('source_type', '?')}** — "
                          f"{_job.get('source', '')} → {_job.get('target', '')} "
                          f"· every {_job.get('interval_minutes', 60)} min · "
                          f"{'enabled' if _job.get('enabled', True) else 'disabled'}"
                          f"{' · last: ' + str(_job.get('last_status')) if _job.get('last_status') else ''}"
                          f"{' · ' + str(_job.get('last_error')) if _job.get('last_error') else ''}")
                if _c2.button("Enable" if not _job.get("enabled", True) else "Disable",
                              key=f"sched_toggle_{_pos}"):
                    _all_jobs[_ji]["enabled"] = not _job.get("enabled", True)
                    try:
                        scheduler.save_registry(_jobs_file, _payload)
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Could not save the job list: {e}")
                if _c3.button("Delete", key=f"sched_delete_{_pos}",
                               type="secondary"):
                    del _all_jobs[_ji]
                    try:
                        scheduler.save_registry(_jobs_file, _payload)
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Could not save the job list: {e}")
            st.write("Add a job:")
            _nj_type = st.selectbox("Source type", ["sheets", "db"],
                                    key="sched_new_type",
                                    help="'sheets' = a public Google Sheet link. "
                                         "'db' = a saved connection name (create it "
                                         "in the Tools tab first).")
            _nj_source = st.text_input("Source (sheet link, or saved connection name)",
                                       key="sched_new_source")
            _nj_target = st.text_input("Save refreshed data to (inside your folder)",
                                       value="uploads/refreshed.csv",
                                       key="sched_new_target")
            _nj_interval = st.number_input("Every (minutes)", min_value=5,
                                           max_value=10080, value=4320,
                                           key="sched_new_interval",
                                           help="Defaults to 3 days (4320 minutes). "
                                                "Set it shorter if you want fresher data.")
            if st.button("Add scheduled job", key="sched_new_add"):
                if not _nj_source.strip() or not _nj_target.strip():
                    st.error("Fill in the source and the target file first.")
                else:
                    _all_jobs.append({
                        "user": _skey, "source_type": _nj_type,
                        "source": _nj_source.strip(),
                        "target": _nj_target.strip(),
                        "interval_minutes": int(_nj_interval),
                        "last_run": None, "next_run": None, "enabled": True,
                    })
                    try:
                        scheduler.save_registry(_jobs_file, _payload)
                        st.success("Job added.")
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Could not save the job list: {e}")

        with st.expander("Shared dashboard links"):
            try:
                _shares = storage.load_json(_skey, "views", _SHARES_FILENAME)
            except Exception:  # noqa: BLE001 - no share links without storage
                _shares = None
            if not isinstance(_shares, dict) or not _shares:
                st.info("No share links yet — create one from the Dashboard tab.")
            else:
                for _pos, (_tok, _snap) in enumerate(sorted(_shares.items())):
                    _c1, _c2 = st.columns([3, 1])
                    _c1.write(f"`?share={_tok[:12]}…` — "
                              f"created {_snap.get('created_at', '?')} — "
                              f"{'REVOKED' if _snap.get('revoked') else 'active'}")
                    if not _snap.get("revoked"):
                        if _c2.button("Revoke", key=f"share_revoke_{_pos}",
                                       type="secondary"):
                            _shares[_tok]["revoked"] = True
                            try:
                                storage.save_json(_skey, "views", _SHARES_FILENAME,
                                                  _shares)
                                st.success("Link revoked — it now shows "
                                           "'revoked or does not exist'.")
                                st.rerun()
                            except Exception as e:  # noqa: BLE001
                                st.error(f"Could not revoke the link: {e}")
                    else:
                        _c2.write("—")

        with st.expander("Still needs your details"):
            st.write("- **Email reports (SMTP):** the Report tab asks for your "
                     "SMTP server, port, username, app password and recipient. "
                     "Nothing is sent until you fill those in and press send.")
            st.write("- **Export to Google Sheets:** needs your Google "
                     "credentials and the Sheets API — not connected yet.")
            st.write("- **Live databases:** need your server details and the "
                     "right driver installed on the server (see the Tools tab).")
            st.write("- **Hosting:** "
                     + ("cloud (Streamlit Cloud)" if _backend != "local"
                        else "this computer")
                     + ". The app is deployed and running here — see DEPLOY.md "
                       "for the hosting notes.")

# -------------------------------------------------------------- profile ---
if "profile" in tab:
    if _active_tab == "profile":
        _profile_result = feat_profile.render_profile_view(
            st, _user, _skey, on_logout=_do_logout)
        if _profile_result in ("deleted", "logout"):
            _do_logout()
        if _profile_result == "back":
            # The sub-nav's "← Back to dashboard" — back to Preview.
            st.session_state["pending_tab"] = "preview"
            st.rerun()

# --------------------------------------------------------------- status ---
if "status" in tab:
    if _active_tab == "status":
        feat_status.render_status_section(st)
