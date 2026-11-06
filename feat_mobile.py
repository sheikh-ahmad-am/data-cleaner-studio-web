"""Data Cleaner Studio — Group C: mobile-friendly layout (v1.4).

One function, mobile_css(), returning a <style> block the coordinator
injects once near the top of simple_app.py:

    st.markdown(mobile_css(), unsafe_allow_html=True)

Everything lives inside a single @media (max-width: 768px) block, so the
desktop layout is untouched — the rules only apply on screens 768px wide
or narrower (phones in portrait, small tablets). On those screens the
dashboard:

* stacks every multi-column row full-width (Streamlit columns become one
  column, so nothing squeezes side-by-side and nothing overflows),
* makes buttons and download buttons full-width and tall enough to tap,
* shrinks headings and body text so a KPI row fits without sideways
  scrolling,
* tightens the page padding so the content uses the narrow screen,
* keeps the sidebar usable: it stays collapsible, and when open it takes
  at most 85% of the screen width so it never covers the whole page,
* lets wide tables scroll sideways inside their own box instead of
  breaking the page.

The CSS is a plain string — no JavaScript, no external URLs, nothing
fetched — so it is safe to inject with st.markdown(..., unsafe_allow_html=True).
"""

from __future__ import annotations

MOBILE_BREAKPOINT_PX = 768


def mobile_css() -> str:
    """The mobile stylesheet as one <style> string. Inject once, near the
    top of the app (after st.set_page_config), with:

        st.markdown(mobile_css(), unsafe_allow_html=True)

    Desktop screens (> 768px) see none of these rules."""
    return """<style>
/* Data Cleaner Studio — mobile layout (phones, <= 768px wide). */
/* Desktop is untouched: every rule below sits inside the media query. */
@media (max-width: 768px) {
  /* Stack multi-column rows full-width: one column per row. */
  div[data-testid="stHorizontalBlock"] {
    flex-direction: column !important;
  }
  div[data-testid="stHorizontalBlock"] div[data-testid="column"] {
    width: 100% !important;
    min-width: 100% !important;
    flex: 1 1 100% !important;
  }
  /* Full-width, finger-sized buttons. */
  .stButton > button,
  .stDownloadButton > button {
    width: 100% !important;
    min-height: 44px;
  }
  /* Smaller headings so KPI rows fit without sideways scrolling. */
  .stApp h1 { font-size: 1.6rem !important; line-height: 1.25; }
  .stApp h2 { font-size: 1.3rem !important; line-height: 1.3; }
  .stApp h3 { font-size: 1.15rem !important; line-height: 1.35; }
  .stApp { font-size: 0.95rem; }
  /* Tighter padding — use the narrow screen for content, not margins. */
  .block-container {
    padding-top: 1rem !important;
    padding-bottom: 1rem !important;
    padding-left: 0.75rem !important;
    padding-right: 0.75rem !important;
  }
  /* Sidebar stays usable: collapsible as usual, and when open it takes
     at most 85% of the screen so it never covers the whole page. */
  section[data-testid="stSidebar"] {
    min-width: 200px !important;
    max-width: 85vw !important;
  }
  section[data-testid="stSidebar"] .block-container {
    padding-left: 0.75rem !important;
    padding-right: 0.75rem !important;
  }
  /* Wide tables scroll inside their own box instead of breaking the page. */
  .stDataFrame {
    width: 100% !important;
    overflow-x: auto;
  }
  /* Inputs and selects fill the width too. */
  .stTextInput > div > div > input,
  .stSelectbox > div > div,
  .stNumberInput > div > div > input,
  .stTextArea > div > textarea {
    width: 100% !important;
  }
}
</style>"""


def apply_mobile_css(st) -> None:
    """Inject the mobile stylesheet into a running Streamlit app. Call
    once near the top of the app, after st.set_page_config:

        apply_mobile_css(st)

    Equivalent to st.markdown(mobile_css(), unsafe_allow_html=True)."""
    st.markdown(mobile_css(), unsafe_allow_html=True)
