"""Data Cleaner Studio — white-label / brand (v1.4, Group B).

Your name, your colour, your logo — on the app and on the reports.

The brand lives in a local ``brand.json`` file next to the app, the
same pattern as ``settings.json`` in ai_settings.py: nothing is baked
into the code, nothing leaves this computer, and deleting the file
puts the plain "Data Cleaner Studio" brand back.

Stored fields (brand.json):
  name   : the brand name shown in titles ("Data Cleaner Studio")
  accent : the accent colour, a #RRGGBB hex string ("#117f50")
  logo   : "logo.png" once a logo has been saved, else None

Contract:
  - load_brand(base_dir=None) -> dict
  - save_brand(brand, base_dir=None) -> dict (the saved, cleaned brand)
  - save_logo(uploaded_bytes, base_dir=None) -> str (path of logo.png)
  - brand_css(accent) -> str (a <style> block for the app)
  - brand_for_exports(base_dir=None) -> {"name", "accent", "logo"}
  - render_brand_section(st, base_dir=None) -> dict (current brand)

Exports take the brand through ``brand_for_exports()``: pass the dict
as ``brand=...`` to feat_share.html_dashboard_bytes, engine.to_pdf_bytes
and pptx_writer.to_pptx_bytes. With brand=None those functions behave
exactly as they always did.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

BRAND_FILE = "brand.json"
LOGO_FILE = "logo.png"

DEFAULT_NAME = "Data Cleaner Studio"
# Deep Supabase green — the app's one accent (see ui_design.py TOKENS
# for the full palette). Never a bright/neon colour here: the brand
# default must match the app theme.
DEFAULT_ACCENT = "#117f50"
ACCENT_HOVER = "#0e7d4e"

DEFAULT_BRAND = {"name": DEFAULT_NAME, "accent": DEFAULT_ACCENT, "logo": None}

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

__all__ = [
    "DEFAULT_BRAND", "DEFAULT_NAME", "DEFAULT_ACCENT",
    "load_brand", "save_brand", "save_logo",
    "brand_css", "brand_for_exports", "render_brand_section",
]


def _base_dir(base_dir=None) -> Path:
    """App folder (where this file lives), or an explicit override."""
    return Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent


def _brand_file(base_dir=None) -> Path:
    return _base_dir(base_dir) / BRAND_FILE


def _clean_accent(value) -> str:
    """A valid #RRGGBB accent, or the default green when it is not."""
    if isinstance(value, str) and _HEX_RE.match(value.strip()):
        return value.strip()
    return DEFAULT_ACCENT


def _clean_brand(raw) -> dict:
    """A stored / typed brand dict, cleaned: defaults for anything
    missing, blank or invalid. Never raises on bad input."""
    brand = dict(DEFAULT_BRAND)
    if not isinstance(raw, dict):
        return brand
    name = raw.get("name")
    if isinstance(name, str) and name.strip():
        brand["name"] = name.strip()
    brand["accent"] = _clean_accent(raw.get("accent"))
    logo = raw.get("logo")
    if isinstance(logo, str) and logo.strip():
        brand["logo"] = logo.strip()
    elif logo is None:
        brand["logo"] = None
    return brand


def load_brand(base_dir=None) -> dict:
    """Read brand.json (next to the app). Missing or broken file ->
    the defaults, so the app never crashes on a first launch."""
    try:
        stored = json.loads(_brand_file(base_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return dict(DEFAULT_BRAND)
    return _clean_brand(stored)


def save_brand(brand, base_dir=None) -> dict:
    """Write the brand dict to brand.json (next to the app) and
    return the cleaned brand that was saved."""
    cleaned = _clean_brand(brand)
    _brand_file(base_dir).write_text(
        json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
    return cleaned


def save_logo(uploaded_bytes, base_dir=None) -> str:
    """Save a logo as logo.png next to the app and record "logo.png"
    in brand.json. Accepts raw bytes, or an object with .getvalue()
    (a Streamlit file upload). Returns the logo path as a string.
    Raises ValueError for empty input."""
    if hasattr(uploaded_bytes, "getvalue"):
        data = uploaded_bytes.getvalue()
    elif hasattr(uploaded_bytes, "read"):
        data = uploaded_bytes.read()
    else:
        data = uploaded_bytes
    if not isinstance(data, (bytes, bytearray)) or len(data) == 0:
        raise ValueError("The logo file is empty — pick a PNG or JPG image.")
    base = _base_dir(base_dir)
    path = base / LOGO_FILE
    path.write_bytes(bytes(data))
    brand = load_brand(base_dir)
    brand["logo"] = LOGO_FILE
    save_brand(brand, base_dir)
    return str(path)


def brand_css(accent) -> str:
    """A <style> block that recolours the app's primary buttons,
    links and headers to the accent colour. Safe to inject with
    st.markdown(..., unsafe_allow_html=True).

    Primary buttons get white text: the default accent is a deep
    green, and dark text on it would be unreadable. Headings are NOT
    recoloured here — the palette keeps them deep charcoal ink, and
    the theme stylesheet owns them. Links and download-button borders
    take the accent. Inject this AFTER the theme stylesheet so a
    user-picked accent wins the tie on buttons and links; with the
    default accent the result is identical to the theme."""
    accent = _clean_accent(accent)
    hover = ACCENT_HOVER if accent == DEFAULT_ACCENT else accent
    return f"""<style>
.stButton > button[kind="primary"], .stButton > button[data-testid="stBaseButton-primary"] {{
    background-color: {accent} !important;
    border-color: {accent} !important;
    color: #FFFFFF !important;
}}
.stButton > button[kind="primary"]:hover, .stButton > button[data-testid="stBaseButton-primary"]:hover {{
    background-color: {hover} !important;
    border-color: {hover} !important;
    color: #FFFFFF !important;
}}
.stApp a {{ color: {accent} !important; }}
.stDownloadButton > button {{
    border-color: {accent} !important;
}}
</style>"""


def brand_for_exports(base_dir=None) -> dict:
    """{"name", "accent", "logo"} for the export functions.

    "logo" is the absolute path of logo.png when a logo has been saved
    and the file is still there, else None. The other two always have
    values (defaults when nothing was ever saved)."""
    brand = load_brand(base_dir)
    logo = None
    stored = brand.get("logo")
    if isinstance(stored, str) and stored.strip():
        candidate = Path(stored)
        if not candidate.is_absolute():
            candidate = _base_dir(base_dir) / stored
        if candidate.exists():
            logo = str(candidate)
    return {"name": brand["name"], "accent": brand["accent"], "logo": logo}


# --------------------------------------------------------------------------
# render function — thin Streamlit wrapper (st passed in, never imported)
# --------------------------------------------------------------------------

def render_brand_section(st, base_dir=None) -> dict:
    """Brand settings: name, accent colour and logo — as Supabase
    settings rows inside one bordered card. The Settings page's
    "Your brand" section heading + sub-line above this card carry
    the title and description (the way the Profile page's sections
    do), so this function renders the rows only, not its own
    heading.

    All widget keys start with "brand_". Saves to brand.json (and
    logo.png) on this computer only. Returns the current brand dict.
    The coordinator can call brand_css() / brand_for_exports() with the
    result to recolour the app and the exports. Cancel discards what
    was typed: it bumps a generation counter (``brand_gen``) so the
    inputs remount under fresh keys on the next run and render from
    the saved brand. The remount is the only mechanism that actually
    clears a text input's displayed text in a live browser — popping
    the widget keys (inline, via a pending-clear flag, or in an
    on_click callback) clears the backend value but the frontend keeps
    showing the typed text (probe50 + the minimal clear-repro proved
    all four fail in Streamlit 1.66.1; only a key change remounts the
    input).
    """
    current = load_brand(base_dir)
    # Generation counter for the brand inputs (see the docstring):
    # Cancel bumps it; the inputs then remount from the saved brand.
    _brand_gen = st.session_state.get("brand_gen", 0)
    st.markdown(brand_css(current["accent"]), unsafe_allow_html=True)
    with st.container(border=True):
        _nl, _nr = st.columns([1.1, 1])
        with _nl:
            st.markdown('<div class="dcs-settings-title">Brand name</div>',
                        unsafe_allow_html=True)
            st.markdown('<div class="dcs-settings-desc">Shown in report '
                        'and dashboard titles instead of '
                        '\'Data Cleaner Studio\'.</div>',
                        unsafe_allow_html=True)
        with _nr:
            name = st.text_input("Brand name", value=current["name"],
                                 key=f"brand_name_{_brand_gen}",
                                 help="Shown in report and dashboard titles "
                                      "instead of 'Data Cleaner Studio'.")
        _al, _ar = st.columns([1.1, 1])
        with _al:
            st.markdown('<div class="dcs-settings-title">Accent colour'
                        '</div>', unsafe_allow_html=True)
            st.markdown('<div class="dcs-settings-desc">Recolours buttons, '
                        'links and headings. Pick any colour you like.'
                        '</div>', unsafe_allow_html=True)
        with _ar:
            accent = st.color_picker("Accent colour", value=current["accent"],
                                     key=f"brand_accent_{_brand_gen}",
                                     help="Recolours buttons, links and "
                                          "headings. Pick any colour you "
                                          "like.")
        _ll, _lr = st.columns([1.1, 1])
        with _ll:
            st.markdown('<div class="dcs-settings-title">Logo</div>',
                        unsafe_allow_html=True)
            st.markdown('<div class="dcs-settings-desc">PNG or JPG, '
                        'optional. Saved as logo.png next to the app. '
                        'Leave it empty to keep the current logo.</div>',
                        unsafe_allow_html=True)
        with _lr:
            logo_file = st.file_uploader("Logo (PNG or JPG, optional)",
                                         type=["png", "jpg", "jpeg"],
                                         key=f"brand_logo_{_brand_gen}",
                                         help="Saved as logo.png next to the "
                                              "app. Leave it empty to keep "
                                              "the current logo.")
            if current.get("logo"):
                st.write(f"Current logo: {current['logo']}")
        _sp, _cancel_col, _save_col = st.columns([2, 1, 1])
        with _cancel_col:
            if st.button("Cancel", key="brand_cancel", type="secondary",
                         use_container_width=True):
                # Bump the generation so the inputs remount from the
                # saved brand on the next run (see the docstring);
                # drop the old keys.
                for _k in (f"brand_name_{_brand_gen}",
                           f"brand_accent_{_brand_gen}",
                           f"brand_logo_{_brand_gen}"):
                    st.session_state.pop(_k, None)
                st.session_state["brand_gen"] = _brand_gen + 1
                st.rerun()
        with _save_col:
            if st.button("Save brand", key="brand_save", type="primary",
                         use_container_width=True):
                try:
                    brand = {"name": (name or "").strip() or DEFAULT_NAME,
                             "accent": accent,
                             "logo": current.get("logo")}
                    if logo_file is not None:
                        save_logo(logo_file, base_dir)
                        brand["logo"] = LOGO_FILE
                    saved = save_brand(brand, base_dir)
                    st.success(f"Brand saved — reports will now say "
                               f"'{saved['name']}'.")
                    return saved
                except Exception as e:  # noqa: BLE001 - show the error, don't crash
                    st.error(f"Could not save the brand: {e}")
                    return current
    return current
