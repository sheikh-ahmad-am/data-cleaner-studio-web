"""KPIs pattern tests (Observability Overview clone round).

The KPIs tab renders Supabase's Observability Overview, mapped to
this app's own data: header (H1 + "Current file" scope + Refresh),
metric cards (one per auto-KPI + saved custom KPI, each with a
distribution sparkline, a before→after sub-line and a "?" tooltip
that names the metric), the Data health strip (six cards scoring
the cleaned file), the Build-your-own-KPI builder (custom KPIs
become cards now, not a text list), and the goal / what-if /
AI-insights sections below. Three empty states: no file loaded,
file loaded but not cleaned, cleaned.

Self-contained: auth.DB_PATH, storage.BASE_DIR and the scheduler
jobs file are pointed at a temp dir, so the real data/ folder is
untouched. Run ONLY this file:  .test-venv-brevo/bin/python -m pytest
tests/test_kpis_overview.py -q   (from project root)
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# NOTE: app.py is NOT imported here — it executes top-level
# Streamlit code at import (set_page_config, session state), so it
# cannot be imported in a plain pytest; the card builders are
# covered through AppTest below, like the Dashboard/Preview rounds.
import auth  # noqa: E402
import engine  # noqa: E402
import scheduler  # noqa: E402
import storage  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(PROJECT_ROOT / "app.py")
SAMPLE = PROJECT_ROOT / "sample_data" / "messy_sales.csv"


@pytest.fixture
def _tmp_env(tmp_path):
    """Point all server-side state at a temp dir (never the real data/).

    Same redirection pattern as test_profile.py / test_supabase_rebuild.py.
    """
    auth.SUPABASE_CONFIG_PATH = tmp_path / "supabase_config.json"
    auth.DB_PATH = tmp_path / "users.db"
    auth._reset_backend_cache()
    storage.BASE_DIR = tmp_path / "users"
    storage._reset_storage_cache()
    scheduler.DEFAULT_JOBS_FILE = tmp_path / "scheduler" / "jobs.json"
    assert auth.get_auth_backend() == "local", "test must run in local mode"
    yield tmp_path


def find_button(at, label, key=None):
    for b in at.button:
        if b.label == label and (key is None or b.key == key):
            return b
    raise AssertionError(f"button {label!r} (key={key!r}) missing")


def find_text_input(at, label):
    for t in at.text_input:
        if t.label == label:
            return t
    raise AssertionError(f"text input {label!r} missing")


def vals(elements):
    """Plain strings from an AppTest ElementList (its items are elements)."""
    return [e.value for e in elements]


def all_text(at):
    """Every visible string on the page (markdown + captions + headers)."""
    out = []
    out.extend(vals(at.markdown))
    out.extend(vals(at.caption))
    out.extend(e.value for e in at.subheader)
    out.extend(e.value for e in at.header)
    return "\n".join(out)


def expand_rail(at):
    """Open the sidebar rail (it starts collapsed — the dashboard's
    own default, icon-only) so the full sidebar is visible."""
    at.session_state["dcs_rail_mode"] = "expanded"
    at.session_state["dcs_rail_collapsed"] = False
    at.run()
    assert not at.exception, f"exception expanding rail: {at.exception}"


def signup(at, username, password="<redacted>"):
    """Sign up (auto-login) and return the new user's id."""
    at.radio[0].set_value("Sign up").run()
    find_text_input(at, "Username").set_value(username).run()
    find_text_input(at, "Password").set_value(password).run()
    find_button(at, "Create account").click().run()
    assert not at.exception, f"exception on signup: {at.exception}"
    expand_rail(at)
    assert any(b.label == "Try the messy sample" for b in at.button), \
        "signup should log the user straight in"
    return at.session_state["current_user"]["id"]


def load_sample(at):
    up = next(f for f in at.file_uploader if f.label == "Upload a file")
    up.set_value([("messy_sales.csv", SAMPLE.read_bytes(), "text/csv")]).run()
    assert not at.exception, f"exception on upload: {at.exception}"
    assert at.session_state["raw"] is not None, "raw data not loaded"
    assert len(at.session_state["raw"]) == 80, "sample should have 80 rows"


def clean_sample(at):
    find_button(at, "Clean my data").click().run()
    assert not at.exception, f"exception on clean: {at.exception}"
    clean = at.session_state["clean"]
    assert clean is not None and len(clean) == 77, \
        "cleaned data should have 77 rows"


def goto_section(at, label):
    radio = next(r for r in at.radio if r.label == "Section")
    radio.set_value(label).run()
    assert not at.exception, f"exception going to {label}: {at.exception}"
    assert radio.value == label, "section switcher did not stick"


def goto_nav(at, label, key):
    """Navigate via a sidebar nav row (the path that works with no data
    loaded, when the Section radio does not exist yet)."""
    expand_rail(at)
    find_button(at, label, key=key).click().run()
    assert not at.exception, f"exception going to {label}: {at.exception}"


# ---------------------------------------------------------------------------
# 1. Top values count whitespace-normalized (engine)
# ---------------------------------------------------------------------------

def test_kpis_top_counts_whitespace_normalized():
    """The Top KPI follows the shared whitespace-normalized counting
    rule: "Aarav Sharma " and "Aarav  Sharma" count as "Aarav
    Sharma", so the Top value, the profile and a search for the
    name all agree (the Preview fix round's rule, now extended to
    the KPIs)."""
    df = pd.DataFrame({"customer": ["Aarav Sharma", "Aarav Sharma ",
                                    "Aarav  Sharma", "Priya", "Priya"]})
    kpis = {k["label"]: k["value"] for k in engine.auto_kpis(df)}
    assert kpis["Top customer"] == "Aarav Sharma (3)", kpis
    print("kpis Top counts OK: Aarav Sharma (3), whitespace-normalized")


# ---------------------------------------------------------------------------
# 2. Empty states: no file / loaded but not cleaned
# ---------------------------------------------------------------------------

def test_kpis_overview_no_data_empty_state(_tmp_env):
    """No file loaded: the KPIs tab says so plainly and its CTA
    opens the Preview tab to load one."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "kpis1")
    goto_nav(at, "KPIs", key="dcs_nav_kpis")
    md = all_text(at)
    assert "No KPIs yet" in md, "no-data empty state missing"
    assert "Load a file first" in md, "no-data copy must say to load a file"
    find_button(at, "Load a file").click().run()
    assert not at.exception, f"exception on Load a file: {at.exception}"
    assert "Nothing loaded yet" in all_text(at), \
        "Load a file should open Preview's empty state"
    print("kpis no-data empty state OK")


def test_kpis_overview_loaded_not_cleaned(_tmp_env):
    """File loaded but not cleaned: the old wrong copy ("Your file
    is loaded" even with NO file) is gone — the state names the
    loaded file and its CTA opens the Clean tab."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "kpis2")
    load_sample(at)
    goto_section(at, "KPIs")
    md = all_text(at)
    assert "No KPIs yet" in md, "loaded-not-cleaned empty state missing"
    assert "Your file is loaded" in md
    find_button(at, "Go to the Clean tab").click().run()
    assert not at.exception, f"exception on Go to Clean: {at.exception}"
    assert "Clean my data" in all_text(at), \
        "Go to the Clean tab should open Clean"
    print("kpis loaded-not-cleaned empty state OK")


# ---------------------------------------------------------------------------
# 3. Loaded state: cards, sparklines, health strip, "?" navigation
# ---------------------------------------------------------------------------

def test_kpis_overview_loaded_cards_and_help(_tmp_env):
    """After a clean: the metric cards render with real values
    (Rows 77, Revenue 207,992.00, Top Customer with the normalized
    count), distribution sparklines, the Data health strip, and the
    "?" tooltip names the metric and opens the Preview tab."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "kpis3")
    load_sample(at)
    goto_section(at, "Clean")
    clean_sample(at)
    goto_section(at, "KPIs")
    md = "\n".join(vals(at.markdown))
    assert "Current file:" in md, "header must name the scope (Current file)"
    assert "Rows" in md and "77" in md, "Rows card missing"
    assert "80 rows in the loaded file" in md, \
        "Rows card must show the before count"
    assert "10 columns in the loaded file" in md, \
        "Columns card must show the before count"
    assert "Revenue (quantity x unit_price)" in md, "Revenue card missing"
    assert "207,992.00" in md, "Revenue value missing"
    assert "was 112,985.00 in the loaded file" in md, \
        "Revenue card must show the before count (raw file's revenue)"
    clean = at.session_state["clean"]
    _vc = engine.normalize_text_values(clean["customer"]).value_counts()
    _top_name, _top_n = _vc.index[0], int(_vc.iloc[0])
    assert f"{_top_name} ({_top_n})" in md, \
        "Top Customer must carry the normalized count"
    assert "dcs-metric-bars" in md, "cards need distribution sparklines"
    assert "Data health" in md, "Data health strip missing"
    assert "Missing cells" in md and "Data quality score" in md
    assert "Build your own KPI" in md, "builder missing"
    # KPI cards hide the WARNINGS/ERRORS dots (the health strip
    # keeps them): exactly six dots spans, one per health card.
    assert md.count('class="dcs-metric-dots"') == 6, \
        "KPI cards must not carry warning/error dots"
    # Every "?" tooltip names its metric — the Revenue card's says
    # what revenue is, never a plain price sum.
    _helps = {b.key: b.help for b in at.button
              if b.key and b.key.startswith("kpis_help_")}
    assert _helps, "no ? tooltips found on the metric cards"
    assert any("Total revenue" in (h or "") for h in _helps.values()), \
        "Revenue card needs a definition tooltip"
    # The "?" tooltip names the metric, and clicking it opens Preview.
    help_btn = find_button(at, "", key="kpis_help_0")
    assert "Rows in the cleaned file" in help_btn.help, help_btn.help
    help_btn.click().run()
    assert not at.exception, f"exception on ? click: {at.exception}"
    assert "Loaded:" in all_text(at), \
        "the ? button should open the Preview tab"
    print(f"kpis loaded cards OK: Rows 77, Revenue 207,992.00, "
          f"Top Customer {_top_name} ({_top_n}), ? opens Preview")


def test_kpis_overview_health_values(_tmp_env):
    """The health strip's values on the cleaned sample: 96.2% of
    rows kept, 90.0% of columns kept, no missing cells."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "kpis4")
    load_sample(at)
    goto_section(at, "Clean")
    clean_sample(at)
    goto_section(at, "KPIs")
    md = "\n".join(vals(at.markdown))
    for label in ("Missing cells", "Duplicate rows", "Empty columns",
                  "Rows kept", "Columns kept", "Data quality score"):
        assert label in md, f"health card {label!r} missing"
    assert "96.2%" in md, "Rows kept must read 96.2%"
    assert "90.0%" in md, "Columns kept must read 90.0%"
    assert "No missing cells" in md
    print("kpis health values OK: 96.2% rows, 90.0% columns kept")


# ---------------------------------------------------------------------------
# 4. Refresh flash + custom KPI becomes a card (and dedupes)
# ---------------------------------------------------------------------------

def test_kpis_overview_refresh_and_custom_kpi(_tmp_env):
    """Refresh confirms with a flash; a custom KPI built in the
    builder renders as a card — not as a text list any more."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "kpis5")
    load_sample(at)
    goto_section(at, "Clean")
    clean_sample(at)
    goto_section(at, "KPIs")
    find_button(at, "Refresh", key="kpis_refresh").click().run()
    assert not at.exception, f"exception on Refresh: {at.exception}"
    assert any("KPIs refreshed" in v for v in vals(at.success)), \
        "Refresh must confirm the recompute"
    col_sel = next(s for s in at.selectbox if s.key == "kpi_col")
    col_sel.set_value("quantity").run()
    fn_sel = next(s for s in at.selectbox if s.key == "kpi_fn")
    fn_sel.set_value("Median").run()
    find_button(at, "Add KPI", key="kpi_add").click().run()
    assert not at.exception, f"exception on Add KPI: {at.exception}"
    md = "\n".join(vals(at.markdown))
    assert "Median of quantity" in md, "custom KPI should render as a card"
    assert "- **Median of quantity:**" not in md, \
        "custom KPIs must not stay a text list"
    print("kpis Refresh + custom KPI OK: Median of quantity is a card")


def test_kpis_overview_custom_kpi_added_twice_renders_once(_tmp_env):
    """Adding the same custom KPI twice renders one card, not two —
    the card builder dedupes by label (auto-KPIs and customs
    alike)."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "kpis6")
    load_sample(at)
    goto_section(at, "Clean")
    clean_sample(at)
    goto_section(at, "KPIs")
    col_sel = next(s for s in at.selectbox if s.key == "kpi_col")
    col_sel.set_value("quantity").run()
    fn_sel = next(s for s in at.selectbox if s.key == "kpi_fn")
    fn_sel.set_value("Median").run()
    find_button(at, "Add KPI", key="kpi_add").click().run()
    assert not at.exception, f"exception on Add KPI: {at.exception}"
    find_button(at, "Add KPI", key="kpi_add").click().run()
    assert not at.exception, f"exception on second Add KPI: {at.exception}"
    md = "\n".join(vals(at.markdown))
    assert md.count("Median of quantity") == 1, \
        "the same custom KPI added twice must render one card"
    print("kpis custom dedupe OK: Median of quantity once")


# ---------------------------------------------------------------------------
# 5. Custom KPI cards format exactly like built-ins (shared rule)
# ---------------------------------------------------------------------------

def test_kpi_value_kind_shared_rule():
    """The one kind rule every KPI value goes through: money for
    price-like columns; counts for Sum/Min/Max of a quantity-like
    column; Average/Median never use "count" (a mean of quantity
    is 2.7, not 3); Count is always a count; total_* columns do
    not count as price/qty-like."""
    assert engine.kpi_value_kind("quantity", "Sum") == "count"
    assert engine.kpi_value_kind("unit_price", "Sum") == "money"
    assert engine.kpi_value_kind("quantity", "Average") == "number"
    assert engine.kpi_value_kind("unit_price", "Average") == "money"
    assert engine.kpi_value_kind("quantity", "Count") == "count"
    assert engine.kpi_value_kind("quantity", "Median") == "number"
    assert engine.kpi_value_kind("unit_price", "Median") == "money"
    assert engine.kpi_value_kind("quantity", "Min") == "count"
    assert engine.kpi_value_kind("quantity", "Max") == "count"
    assert engine.kpi_value_kind("score", "Sum") == "number"
    assert engine.kpi_value_kind("total_amount", "Sum") == "number"
    print("kpi_value_kind OK: shared rule")


def _add_custom_kpi(at, col, fn):
    col_sel = next(s for s in at.selectbox if s.key == "kpi_col")
    col_sel.set_value(col).run()
    fn_sel = next(s for s in at.selectbox if s.key == "kpi_fn")
    fn_sel.set_value(fn).run()
    find_button(at, "Add KPI", key="kpi_add").click().run()
    assert not at.exception, f"exception on Add KPI {fn} of {col}: " \
        f"{at.exception}"


def _card_element(md_elements, label):
    for e in md_elements:
        if label in e:
            return e
    raise AssertionError(f"card {label!r} missing from the page")


def test_kpis_custom_kpi_formats_like_builtin(_tmp_env):
    """Every custom-KPI function formats like its built-in twin:
    sentence-case label (the column name as-is, never Title
    Case), whole numbers for counts, 1 decimal for other numbers,
    money 2 decimals — all through the shared kpi_value_kind
    rule. Median (no auto twin), Count and Average of unit_price
    are checked against values computed from the cleaned frame."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "kpis7")
    load_sample(at)
    goto_section(at, "Clean")
    clean_sample(at)
    goto_section(at, "KPIs")
    clean = at.session_state["clean"]
    md_els = vals(at.markdown)

    _add_custom_kpi(at, "quantity", "Median")
    md_els = vals(at.markdown)
    _med = float(clean["quantity"].median())
    _med_fmt = engine.format_number(
        _med, engine.kpi_value_kind("quantity", "Median"))
    _med_card = _card_element(md_els, "Median of quantity")
    assert "Median of Quantity" not in "\n".join(md_els), \
        "custom labels must not Title-Case the column"
    assert _med_fmt in _med_card, \
        f"Median card should show {_med_fmt}, got: {_med_card[:200]}"
    assert f"{_med:,.2f}" not in _med_card, \
        "custom values must not force 2 decimals"

    _add_custom_kpi(at, "quantity", "Count")
    md_els = vals(at.markdown)
    _cnt_fmt = engine.format_number(
        int(clean["quantity"].count()),
        engine.kpi_value_kind("quantity", "Count"))
    _cnt_card = _card_element(md_els, "Count of quantity")
    assert _cnt_fmt in _cnt_card, \
        f"Count card should show {_cnt_fmt}, got: {_cnt_card[:200]}"
    assert f"{int(clean['quantity'].count()):,.2f}" not in _cnt_card, \
        "a Count card must show a whole number, never x.00"

    _add_custom_kpi(at, "unit_price", "Average")
    md_els = vals(at.markdown)
    _avg = float(clean["unit_price"].mean())
    _avg_fmt = engine.format_number(
        _avg, engine.kpi_value_kind("unit_price", "Average"))
    _avg_card = _card_element(md_els, "Average of unit_price")
    assert _avg_fmt in _avg_card, \
        f"Average of unit_price should show {_avg_fmt}, got: " \
        f"{_avg_card[:200]}"
    # The same number, the same format, as the built-in twin.
    _auto_card = _card_element(md_els, "Average unit_price")
    assert _avg_fmt in _auto_card, \
        "custom Average of unit_price must match the built-in " \
        "Average unit_price value exactly"
    print("kpis custom formatting OK: Median/Count/Average match built-ins")


def test_kpis_custom_sum_dedupes_and_sub_uses_shared_kind(_tmp_env):
    """A custom Sum of quantity is the auto "Sum of quantity"
    card — same sentence-case label, same number — so it dedupes
    to one card instead of rendering a wrongly-formatted twin,
    and the before→after sub-line uses the shared kind ("was 160",
    never "was 160.0")."""
    at = AppTest.from_file(APP)
    at.run()
    signup(at, "kpis8")
    load_sample(at)
    goto_section(at, "Clean")
    clean_sample(at)
    goto_section(at, "KPIs")
    _add_custom_kpi(at, "quantity", "Sum")
    md = "\n".join(vals(at.markdown))
    assert md.count("Sum of quantity") == 1, \
        "custom Sum of quantity must dedupe against the auto card"
    assert "Sum of Quantity" not in md, \
        "no Title-Case twin of the Sum card may survive"
    assert "208.00" not in md, \
        "no 2-decimal form of the Sum value may survive"
    assert "was 160 in the loaded file" in md, \
        "the Sum sub-line must use the shared kind (whole number)"
    assert "was 160.0" not in md, \
        "the Sum sub-line must not show 1 decimal for a count"
    print("kpis custom Sum OK: dedupes, sub-line uses shared kind")
