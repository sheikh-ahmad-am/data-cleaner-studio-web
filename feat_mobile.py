"""Data Cleaner Studio — theme + mobile-friendly layout (v1.4).

One function, mobile_css(), returning a single <style> block the app
injects once near the top of app.py:

    st.markdown(mobile_css(), unsafe_allow_html=True)

Two parts, in this order:

1. The mobile rules, inside one @media (max-width: 768px) block, so
   phones stack columns, get full-width finger-sized buttons, smaller
   headings and tighter padding. Desktop screens (> 768px) see none
   of these rules.
2. The base theme, applied on every screen: the Supabase palette —
   near-white page, white cards, near-black ink, one deep-green
   accent. No bright colours, no gradients except the subtle primary
   -button gradient, no external fonts, nothing fetched over the
   network.

Palette (single source of truth — keep in sync with ui_design.py
TOKENS and feat_brand.py):
  page background  #FDFDFD   cards/surfaces  #FFFFFF
  card border      #E8E8E8   ink             #030303
  secondary text   #696969   accent (green)  #117F50
  accent hover     #0E7D4E   secondary btn   #FFFFFF bg / #E5E5E5 border
  danger (sparingly) #B91C1C   warning (muted amber) #E69344

Contrast (WCAG, text on background — all pass 4.5:1):
  ink on page 20.28:1 · ink on white 20.62:1
  secondary text on page 5.40:1 · on white 5.49:1
  white on accent 5.03:1 · white on accent hover 5.17:1
  accent on page 4.94:1 · accent on white 5.03:1
  ink on secondary-button bg 20.62:1
  danger on page 6.36:1 · amber is pill-only (large/bold labels),
  never body text.

The CSS is a plain string — no JavaScript, no external URLs, nothing
fetched — so it is safe to inject with st.markdown(..., unsafe_allow_html=True).
"""

from __future__ import annotations

MOBILE_BREAKPOINT_PX = 768

# The palette, as constants, so the theme and the brand default agree.
# Supabase tokens — keep in sync with ui_design.py TOKENS.
PAGE_BG = "#FDFDFD"
CARD_BG = "#FFFFFF"
CARD_BORDER = "#E8E8E8"
INK = "#030303"
SECONDARY_TEXT = "#696969"
ACCENT = "#117F50"
ACCENT_HOVER = "#0E7D4E"
GRADIENT_TOP = "#118050"  # primary-button gradient top (TOKENS gradient_top)
SECONDARY_BTN_BG = "#FFFFFF"
SECONDARY_BTN_BG_HOVER = "#F8F8F8"
SECONDARY_BTN_BORDER = "#E5E5E5"
SIDEBAR_BG = "#FDFDFD"
DANGER = "#B91C1C"
WARNING = "#E69344"


def mobile_css() -> str:
    """The theme + mobile stylesheet as one <style> string. Inject once,
    near the top of the app (after st.set_page_config), with:

        st.markdown(mobile_css(), unsafe_allow_html=True)

    The mobile rules sit in the @media block first; the base theme
    follows and applies on every screen."""
    return f"""<style>
/* Data Cleaner Studio — mobile layout (phones, <= 768px wide). */
/* Desktop is untouched: every rule below sits inside the media query. */
@media (max-width: 768px) {{
  /* Stack multi-column rows full-width: one column per row. */
  div[data-testid="stHorizontalBlock"] {{
    flex-direction: column !important;
  }}
  div[data-testid="stHorizontalBlock"] div[data-testid="column"] {{
    width: 100% !important;
    min-width: 100% !important;
    flex: 1 1 100% !important;
  }}
  /* Full-width, finger-sized buttons. */
  .stButton > button,
  .stDownloadButton > button {{
    width: 100% !important;
    min-height: 44px;
  }}
  /* Smaller headings so KPI rows fit without sideways scrolling. */
  .stApp h1 {{ font-size: 1.6rem !important; line-height: 1.25; }}
  .stApp h2 {{ font-size: 1.3rem !important; line-height: 1.3; }}
  .stApp h3 {{ font-size: 1.15rem !important; line-height: 1.35; }}
  .stApp {{ font-size: 0.95rem; }}
  /* Tighter padding — use the narrow screen for content, not margins. */
  .block-container {{
    padding-top: 1rem !important;
    padding-bottom: 1rem !important;
    padding-left: 0.75rem !important;
    padding-right: 0.75rem !important;
  }}
  /* Sidebar stays usable: collapsible as usual, and when open it takes
     at most 85% of the screen so it never covers the whole page. */
  section[data-testid="stSidebar"] {{
    min-width: 200px !important;
    max-width: 85vw !important;
  }}
  section[data-testid="stSidebar"] .block-container {{
    padding-left: 0.75rem !important;
    padding-right: 0.75rem !important;
  }}
  /* Wide tables scroll inside their own box instead of breaking the page. */
  .stDataFrame {{
    width: 100% !important;
    overflow-x: auto;
  }}
  /* Inputs and selects fill the width too. */
  .stTextInput > div > div > input,
  .stSelectbox > div > div,
  .stNumberInput > div > div > input,
  .stTextArea > div > textarea {{
    width: 100% !important;
  }}
}}

/* ---- Base theme: Supabase — near-white, hairlines, one green. ---- */
/* Page: near-white, near-black ink. */
.stApp {{
  background-color: {PAGE_BG} !important;
  color: {INK} !important;
}}
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {{
  color: {INK} !important;
}}
.stApp p, .stApp li, .stApp label {{
  color: {INK} !important;
}}
div[data-testid="stCaptionContainer"] {{
  color: {SECONDARY_TEXT} !important;
}}
.stApp a {{
  color: {ACCENT} !important;
}}
/* Comfortable, consistent page spacing; headings get breathing room. */
.block-container {{
  padding-top: 2rem !important;
  padding-bottom: 2rem !important;
}}
.stApp h2 {{
  margin-top: 1.25rem !important;
}}
/* Sidebar: near-white, clearly separated from the page. */
section[data-testid="stSidebar"] {{
  background-color: {SIDEBAR_BG} !important;
  border-right: 1px solid {CARD_BORDER} !important;
}}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2 {{
  color: {INK} !important;
}}
/* Primary action: deep green, white text, subtle vertical gradient.
   One per view. */
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"] {{
  background-color: {ACCENT} !important;
  background: linear-gradient(180deg, {GRADIENT_TOP} 0%, {ACCENT_HOVER} 100%) !important;
  border-color: {ACCENT} !important;
  color: #FFFFFF !important;
}}
.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="stBaseButton-primary"]:hover {{
  background-color: {ACCENT_HOVER} !important;
  background: linear-gradient(180deg, {GRADIENT_TOP} 0%, {ACCENT_HOVER} 100%) !important;
  border-color: {ACCENT_HOVER} !important;
  color: #FFFFFF !important;
}}
/* Secondary actions: white fill, ink text, hairline border — clearly
   readable, and clearly not the primary button. */
.stButton > button,
.stDownloadButton > button,
.stLinkButton > a {{
  background-color: {SECONDARY_BTN_BG} !important;
  color: {INK} !important;
  border: 1px solid {SECONDARY_BTN_BORDER} !important;
}}
.stButton > button:hover,
.stDownloadButton > button:hover,
.stLinkButton > a:hover {{
  background-color: {SECONDARY_BTN_BG_HOVER} !important;
  color: {INK} !important;
  border-color: {SECONDARY_BTN_BORDER} !important;
}}
/* Button labels wrap instead of truncating with an ellipsis. */
.stButton > button,
.stDownloadButton > button,
.stLinkButton > a {{
  white-space: normal !important;
  height: auto !important;
  min-height: 44px;
  line-height: 1.35 !important;
}}
/* Tabs: inactive labels muted grey, active label green. */
button[data-testid="stTab"] {{
  color: {SECONDARY_TEXT} !important;
}}
button[data-testid="stTab"][aria-selected="true"] {{
  color: {ACCENT} !important;
}}
div[data-testid="stTab"] {{
  color: {SECONDARY_TEXT} !important;
}}
/* Cards: KPI tiles, expanders and tables sit on white with a hairline
   border, so the page reads as one calm surface. */
div[data-testid="stMetric"] {{
  background-color: {CARD_BG} !important;
  border: 1px solid {CARD_BORDER} !important;
  border-radius: 10px !important;
  padding: 0.75rem 1rem !important;
}}
div[data-testid="stMetricLabel"] {{
  color: {SECONDARY_TEXT} !important;
}}
div[data-testid="stMetricValue"] {{
  color: {INK} !important;
}}
details[data-testid="stExpander"] {{
  background-color: {CARD_BG} !important;
  border: 1px solid {CARD_BORDER} !important;
  border-radius: 10px !important;
}}
div[data-testid="stDataFrame"],
div[data-testid="stTable"] {{
  border: 1px solid {CARD_BORDER} !important;
  border-radius: 10px !important;
}}
/* Inputs: white fields, ink text, soft border. */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stTextArea > div > textarea,
.stSelectbox > div > div,
.stDateInput > div > div > input,
.stTimeInput > div > div > input {{
  background-color: {CARD_BG} !important;
  color: {INK} !important;
  border-color: {SECONDARY_BTN_BORDER} !important;
}}
.stFileUploader > div {{
  background-color: {CARD_BG} !important;
  border: 1px dashed {SECONDARY_BTN_BORDER} !important;
  border-radius: 10px !important;
}}
/* Checkboxes, radios and sliders take the accent, not a bright colour. */
input[type="checkbox"], input[type="radio"] {{
  accent-color: {ACCENT} !important;
}}
div[data-testid="stProgress"] > div > div {{
  background-color: {ACCENT} !important;
}}
/* Alert boxes: muted tints, one per kind — success is green;
   errors are restrained red; warnings are amber. Text
   stays readable ink on the soft tint. */
div[data-testid="stAlertContentSuccess"] {{
  background-color: rgba(17, 127, 80, 0.08) !important;
  border: 1px solid rgba(17, 127, 80, 0.35) !important;
  border-radius: 10px !important;
  color: {INK} !important;
}}
div[data-testid="stAlertContentInfo"] {{
  background-color: {CARD_BG} !important;
  border: 1px solid {CARD_BORDER} !important;
  border-radius: 10px !important;
  color: {INK} !important;
}}
div[data-testid="stAlertContentWarning"] {{
  background-color: rgba(230, 147, 68, 0.08) !important;
  border: 1px solid rgba(230, 147, 68, 0.35) !important;
  border-radius: 10px !important;
  color: {INK} !important;
}}
div[data-testid="stAlertContentError"] {{
  background-color: rgba(185, 28, 28, 0.08) !important;
  border: 1px solid rgba(185, 28, 28, 0.35) !important;
  border-radius: 10px !important;
  color: {INK} !important;
}}
/* Danger and warning accents, used by the alert tints above. */
.stApp {{
  --dcs-danger: {DANGER};
  --dcs-warning: {WARNING};
}}
</style>"""


def apply_mobile_css(st) -> None:
    """Inject the theme + mobile stylesheet into a running Streamlit app.
    Call once near the top of the app, after st.set_page_config:

        apply_mobile_css(st)

    Equivalent to st.markdown(mobile_css(), unsafe_allow_html=True)."""
    st.markdown(mobile_css(), unsafe_allow_html=True)
