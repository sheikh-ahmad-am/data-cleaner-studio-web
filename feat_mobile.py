"""Data Cleaner Studio — theme + mobile-friendly layout (v1.4).

One function, mobile_css(), returning a single <style> block the app
injects once near the top of app.py:

    st.markdown(mobile_css(), unsafe_allow_html=True)

Two parts, in this order:

1. The mobile rules, inside one @media (max-width: 768px) block, so
   phones stack columns, get full-width finger-sized buttons, smaller
   headings and tighter padding. Desktop screens (> 768px) see none
   of these rules.
2. The base theme, applied on every screen: the classic, premium
   palette — warm off-white page, white cards, deep charcoal ink,
   one muted deep-teal accent. No bright colours, no gradients, no
   external fonts, nothing fetched over the network.

Palette (single source of truth — keep in sync with feat_brand.py):
  page background  #FAF7F2   cards/surfaces  #FFFFFF
  card border      #E5E0D8   ink             #23272E
  secondary text   #6E6A61   accent (teal)   #2F5D5A
  accent hover     #264845   secondary btn   #EFEDE8 bg / #D9D4C9 border
  danger (sparingly) #9A4A38   warning (muted amber) #8A6D3B

Contrast (WCAG, text on background — all pass 4.5:1):
  ink on page 14.03:1 · ink on white 14.99:1
  secondary text on page 5.04:1 · on white 5.39:1
  white on accent 7.41:1 · white on accent hover 10.02:1
  accent on page 6.93:1 · accent on white 7.41:1
  ink on secondary-button bg 12.81:1 · on its hover bg 11.61:1
  danger on page 5.76:1 · warning on page 4.54:1

The CSS is a plain string — no JavaScript, no external URLs, nothing
fetched — so it is safe to inject with st.markdown(..., unsafe_allow_html=True).
"""

from __future__ import annotations

MOBILE_BREAKPOINT_PX = 768

# The palette, as constants, so the theme and the brand default agree.
PAGE_BG = "#FAF7F2"
CARD_BG = "#FFFFFF"
CARD_BORDER = "#E5E0D8"
INK = "#23272E"
SECONDARY_TEXT = "#6E6A61"
ACCENT = "#2F5D5A"
ACCENT_HOVER = "#264845"
SECONDARY_BTN_BG = "#EFEDE8"
SECONDARY_BTN_BG_HOVER = "#E7E2D8"
SECONDARY_BTN_BORDER = "#D9D4C9"
SIDEBAR_BG = "#F3EFE8"
DANGER = "#9A4A38"
WARNING = "#8A6D3B"


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

/* ---- Base theme: classic, premium, muted. Applies on every screen. ---- */
/* Page: warm off-white, deep charcoal ink. */
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
/* Sidebar: warm neutral, clearly separated from the page. */
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
/* Primary action: deep teal, white text. One per view. */
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"] {{
  background-color: {ACCENT} !important;
  border-color: {ACCENT} !important;
  color: #FFFFFF !important;
}}
.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="stBaseButton-primary"]:hover {{
  background-color: {ACCENT_HOVER} !important;
  border-color: {ACCENT_HOVER} !important;
  color: #FFFFFF !important;
}}
/* Secondary actions: warm neutral fill, ink text, soft border — clearly
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
/* Tabs: inactive labels warm grey, active label teal with a teal bar. */
button[data-testid="stTab"] {{
  color: {SECONDARY_TEXT} !important;
}}
button[data-testid="stTab"][aria-selected="true"] {{
  color: {ACCENT} !important;
}}
div[data-testid="stTab"] {{
  color: {SECONDARY_TEXT} !important;
}}
/* Cards: KPI tiles, expanders and tables sit on white with a warm
   neutral border, so the page reads as one calm surface. */
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
/* Alert boxes: muted tints, one per kind — success is teal, never
   green; errors are muted brick; warnings are muted amber. Text
   stays readable ink on the soft tint. */
div[data-testid="stAlertContentSuccess"] {{
  background-color: rgba(47, 93, 90, 0.08) !important;
  border: 1px solid rgba(47, 93, 90, 0.35) !important;
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
  background-color: rgba(138, 109, 59, 0.08) !important;
  border: 1px solid rgba(138, 109, 59, 0.35) !important;
  border-radius: 10px !important;
  color: {INK} !important;
}}
div[data-testid="stAlertContentError"] {{
  background-color: rgba(154, 74, 56, 0.08) !important;
  border: 1px solid rgba(154, 74, 56, 0.35) !important;
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
