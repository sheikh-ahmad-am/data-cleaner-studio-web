"""Data Cleaner Studio — built-in tutorial (v1.4, Group B).

A short, plain-words guide for a first-time user: load a file, look
at the health check, clean, check the log, look at the KPIs, use the
dashboard slicers, download the report. No jargon, one idea per step.

The "have I seen this?" flag lives in the same local settings.json
as the Groq key (ai_settings.py) under the key "tutorial_seen" — the
app never asks twice once the user presses "Got it".

Contract:
  - TUTORIAL_STEPS : list of {"title", "text"} dicts (7 steps)
  - is_first_run(settings_path=None) -> bool
  - mark_tutorial_seen(settings_path=None) -> True
  - render_tutorial(st) : the numbered steps
  - render_tutorial_page(st, settings_path=None) : the "How to use" tab
  - render_first_run_banner(st, settings_path=None) -> bool (shown?)

Widget keys all start with "tut_".
"""

from __future__ import annotations

import ai_settings

__all__ = [
    "TUTORIAL_STEPS",
    "is_first_run", "mark_tutorial_seen",
    "render_tutorial", "render_tutorial_page", "render_first_run_banner",
]

TUTORIAL_STEPS = [
    {
        "title": "Load a file",
        "text": ("Upload a CSV, Excel or JSON file from the sidebar, or "
                 "press 'Try the messy sample' to practise. Your file "
                 "stays on this computer — nothing is uploaded anywhere."),
    },
    {
        "title": "Look at the health check",
        "text": ("The Preview tab shows what is wrong with your data: "
                 "how many cells are empty, how many rows are copies of "
                 "each other, and what type each column is."),
    },
    {
        "title": "Clean your data",
        "text": ("Go to the Clean tab, tick the fixes you want — tidy "
                 "names, fix numbers, parse dates, drop copies — then "
                 "press 'Clean my data'. Nothing is changed until you "
                 "press that button."),
    },
    {
        "title": "Check the log",
        "text": ("Under the Clean button, 'What was fixed' lists every "
                 "fix in plain words, with the numbers — for example, "
                 "how many rows were dropped. Read it before you trust "
                 "the result."),
    },
    {
        "title": "Look at your KPIs",
        "text": ("The KPIs tab turns your clean data into simple "
                 "numbers: totals, averages, and the top customer, "
                 "product or category. You can also build your own KPI "
                 "from any number column."),
    },
    {
        "title": "Use the dashboard slicers",
        "text": ("The Dashboard tab draws your charts. The slicers on "
                 "the left filter every chart and KPI at once — untick "
                 "a category or narrow the dates and watch the numbers "
                 "move."),
    },
    {
        "title": "Download the report",
        "text": ("The Report tab has everything to take away: the "
                 "cleaned file as CSV or Excel, a PDF report, a "
                 "PowerPoint, and a standalone HTML dashboard that "
                 "opens in any browser."),
    },
]


def is_first_run(settings_path=None) -> bool:
    """True until the user has pressed "Got it" on the tutorial once.

    Reads the "tutorial_seen" flag from settings.json (next to the
    app, the same file as the Groq key). A missing or broken settings
    file counts as a first run, so a new user always sees the guide.
    """
    try:
        settings = ai_settings.load_settings(path=settings_path)
    except Exception:  # noqa: BLE001 - a broken settings file = first run
        return True
    return not bool(settings.get("tutorial_seen"))


def mark_tutorial_seen(settings_path=None) -> bool:
    """Remember that the user has seen the tutorial: set
    "tutorial_seen" in settings.json (keeping every other setting)
    and return True."""
    try:
        settings = ai_settings.load_settings(path=settings_path)
    except Exception:  # noqa: BLE001 - start from the defaults
        settings = dict(ai_settings.DEFAULT_SETTINGS)
    settings["tutorial_seen"] = True
    ai_settings.save_settings(settings, path=settings_path)
    return True


# --------------------------------------------------------------------------
# render functions — thin Streamlit wrappers (st passed in, never imported)
# --------------------------------------------------------------------------

def render_tutorial(st) -> None:
    """The steps as numbered sections — plain titles, one or two plain
    sentences each. No buttons, no state: safe to show anywhere."""
    st.subheader("How to use Data Cleaner Studio")
    st.write("Seven short steps, from a messy file to a finished report. "
             "Each step takes less than a minute to try.")
    for i, step in enumerate(TUTORIAL_STEPS, start=1):
        st.subheader(f"{i}. {step['title']}")
        st.write(step["text"])


def render_tutorial_page(st, settings_path=None) -> None:
    """The "How to use" tab: the numbered steps, plus a "Got it"
    button that hides this guide next time (key "tut_page_seen")."""
    render_tutorial(st)
    if is_first_run(settings_path):
        if st.button("Got it — I know how this works", key="tut_page_seen"):
            mark_tutorial_seen(settings_path)
            st.success("Got it — this guide will not pop up again. "
                       "You can always find it here, in the 'How to use' tab.")


def render_first_run_banner(st, settings_path=None) -> bool:
    """First-run banner: a short info box plus a "Got it" button
    (key "tut_got_it") that marks the tutorial seen.

    Returns True when the banner was shown, False when the user has
    already seen the tutorial (nothing is drawn then)."""
    if not is_first_run(settings_path):
        return False
    st.info("First time here? This app turns a messy file into clean "
            "data, KPIs, charts and a report in seven short steps. "
            "Open the 'How to use' tab for the full guide, or press "
            "'Got it' and start with a file from the sidebar.")
    if st.button("Got it", key="tut_got_it"):
        mark_tutorial_seen(settings_path)
        st.success("Got it — happy cleaning. The guide stays in the "
                   "'How to use' tab whenever you want it.")
    return True
