"""Group 5 (enrich & share) tests for feat_enrich.py + ai_settings.py.

Run: .test-venv-enrich/bin/python tests/test_feat_enrich.py  (from project root)
Also pytest-collectable (plain asserts, no fixtures). No Streamlit server
needed — the render functions are exercised with a FakeSt stub, and the AI
call is never made for real: ask_ai is tested with a missing key (expecting
the clear error) and with a mocked urlopen.
"""

import io
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import ai_settings
import engine
import feat_enrich as fe


def _sample_raw():
    return engine.load_file("messy_sales.csv",
                            open("sample_data/messy_sales.csv", "rb").read())


def _sample_clean():
    clean, _actions = engine.clean(_sample_raw())
    return clean


# --------------------------------------------------------------------------
# 1. split & merge columns
# --------------------------------------------------------------------------

def test_split_separator():
    df = pd.DataFrame({"place": ["Mumbai, Maharashtra", "Patna, Bihar",
                                 "Delhi", None, "  "]})
    new_df, actions = fe.split_column(df, "place", "separator", ",")
    assert list(new_df["place_part1"].head(3)) == ["Mumbai", "Patna", "Delhi"]
    assert list(new_df["place_part2"].head(2)) == ["Maharashtra", "Bihar"]
    # Blank / missing values stay blank (NaN, the app's missing marker).
    assert new_df["place_part1"].isna().sum() == 2
    assert new_df["place_part2"].isna().sum() == 3
    assert new_df["place"].tolist()[:1] == ["Mumbai, Maharashtra"]  # original kept
    assert actions[0][0] == "Split column: place"
    assert "2 of 5" in actions[0][1]

    named, _ = fe.split_column(df, "place", "separator", ",",
                               ["city", "state"])
    assert "city" in named.columns and "state" in named.columns
    print("split separator OK")


def test_split_first_last_word():
    clean = _sample_clean()
    new_df, actions = fe.split_column(clean, "customer", "first_last_word")
    assert list(new_df["customer_first"].head(3)) == ["Aarav", "Priya", "Aarav"]
    assert list(new_df["customer_last"].head(3)) == ["Sharma", "Patel", "Sharma"]
    # Ananya Rao (the top customer, 13 rows) splits the same way everywhere.
    mask = new_df["customer"] == "Ananya Rao"
    assert set(new_df.loc[mask, "customer_first"]) == {"Ananya"}
    assert set(new_df.loc[mask, "customer_last"]) == {"Rao"}
    assert "13 of 77" not in actions[0][1]  # all 77 rows split, not just 13
    assert "77 of 77" in actions[0][1]
    print("split first/last OK: Ananya Rao -> Ananya / Rao on all 13 rows")


def test_split_errors():
    df = pd.DataFrame({"a": ["x y"]})
    for call in (lambda: fe.split_column(df, "nope"),
                 lambda: fe.split_column(df, "a", "sideways"),
                 lambda: fe.split_column(df, "a", "separator", ""),
                 lambda: fe.split_column(df, "a", "separator", ",",
                                         ["only_one"]),
                 lambda: fe.split_column(df, "a", "separator", ",",
                                         ["one", "two", "three"])):
        try:
            call()
            raise AssertionError("bad split must raise")
        except ValueError:
            pass
    print("split errors OK")


def test_merge_columns():
    clean = _sample_clean()
    # Build the pair first via split, then merge them back.
    split, _ = fe.split_column(clean, "customer", "first_last_word")
    merged, actions = fe.merge_columns(split, "customer_first", "customer_last",
                                       "full_name")
    assert list(merged["full_name"].head(3)) == ["Aarav Sharma", "Priya Patel",
                                                 "Aarav Sharma"]
    assert (merged["full_name"] == merged["customer"]).all()
    assert "77 of 77" in actions[0][1]

    df = pd.DataFrame({"first": ["Ananya", "Rohan", None],
                       "last": ["Rao", None, "Das"]})
    m2, _ = fe.merge_columns(df, "first", "last", "name", separator=" ")
    assert list(m2["name"]) == ["Ananya Rao", "Rohan", "Das"]
    m3, a3 = fe.merge_columns(df, "first", "last", "name",
                              drop_originals=True)
    assert "first" not in m3.columns and "last" not in m3.columns
    assert "originals dropped" in a3[0][1]
    for call in (lambda: fe.merge_columns(df, "first", "nope", "name"),
                 lambda: fe.merge_columns(df, "first", "first", "name"),
                 lambda: fe.merge_columns(df, "first", "last", "  ")):
        try:
            call()
            raise AssertionError("bad merge must raise")
        except ValueError:
            pass
    print("merge OK")


# --------------------------------------------------------------------------
# 2. date intelligence
# --------------------------------------------------------------------------

def test_date_parts_sample():
    clean = _sample_clean()
    new_df, actions = fe.add_date_parts(clean, "order_date")
    assert list(new_df.columns[-3:]) == ["order_date_year", "order_date_month",
                                         "order_date_weekday"]
    row0 = new_df.iloc[0]
    assert int(row0["order_date_year"]) == 2026
    assert row0["order_date_month"] == "June"
    assert row0["order_date_weekday"] == "Saturday"  # 2026-06-13
    months = set(new_df["order_date_month"].dropna().unique())
    all_months = {"January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November",
                  "December"}
    assert months <= all_months and {"January", "June", "August"} <= months
    assert set(new_df["order_date_year"].dropna().unique()) == {2026}
    assert "77 of 77" in actions[0][1]
    print("date parts OK: 2026-06-13 -> 2026 / June / Saturday")


def test_date_parts_errors():
    df = pd.DataFrame({"name": ["Aarav", "Priya"], "n": [1, 2]})
    for call in (lambda: fe.add_date_parts(df, "nope"),
                 lambda: fe.add_date_parts(df, "name")):
        try:
            call()
            raise AssertionError("bad date column must raise")
        except ValueError:
            pass
    print("date parts errors OK")


# --------------------------------------------------------------------------
# 3. currency conversion
# --------------------------------------------------------------------------

def test_parse_money():
    cases = [("₹799", (799.0, "INR")), ("Rs. 799", (799.0, "INR")),
             ("INR 799", (799.0, "INR")), ("$1,499.00", (1499.0, "USD")),
             ("€50", (50.0, "EUR")), ("£20", (20.0, "GBP")),
             ("1199", (1199.0, "INR")), (799, (799.0, "INR")),
             (None, (None, None)), ("", (None, None)),
             ("not money", (None, None))]
    for raw, want in cases:
        assert fe.parse_money(raw) == want, (raw, fe.parse_money(raw))
    print("parse_money OK")


def test_convert_currency_sample():
    raw = _sample_raw()
    new_df, actions = fe.convert_currency(raw, "Unit Price", "INR")
    assert "Unit Price_INR" in new_df.columns
    # Row 0 "$799.00" -> 799 * 83; row 2 bare 1199 -> 1199 (INR);
    # row 5 "Rs. 799" -> 799.
    assert new_df["Unit Price_INR"].iloc[0] == 799 * 83
    assert new_df["Unit Price_INR"].iloc[2] == 1199.0
    assert new_df["Unit Price_INR"].iloc[5] == 799.0
    assert "75 value(s) converted" in actions[0][1]
    assert "5 value(s) could not be read" in actions[0][1]
    assert "fixed estimates" in actions[0][1].lower()
    total_inr = float(new_df["Unit Price_INR"].sum())
    assert total_inr == 886187.0, total_inr
    print(f"convert to INR OK: total {total_inr:,.2f} over 75 values")

    usd_df, _ = fe.convert_currency(raw, "Unit Price", "USD")
    assert usd_df["Unit Price_USD"].iloc[0] == 799.0
    assert usd_df["Unit Price_USD"].iloc[5] == round(799 / 83, 2)
    assert usd_df["Unit Price_USD"].iloc[2] == round(1199 / 83, 2)

    custom = fe.convert_currency(raw, "Unit Price", "INR",
                                 {"INR": 1.0, "USD": 80.0,
                                  "EUR": 90.0, "GBP": 105.0})
    assert custom[0]["Unit Price_INR"].iloc[0] == 799 * 80
    for call in (lambda: fe.convert_currency(raw, "nope", "INR"),
                 lambda: fe.convert_currency(raw, "Unit Price", "JPY")):
        try:
            call()
            raise AssertionError("bad currency must raise")
        except ValueError:
            pass
    assert "not live rates" in fe.FX_RATES_NOTE
    print("convert currency OK")


# --------------------------------------------------------------------------
# 4. AI insights (never calls the real API here)
# --------------------------------------------------------------------------

def test_insight_prompt():
    clean = _sample_clean()
    kpis = engine.auto_kpis(clean)
    prompt = fe.build_insight_prompt(clean, kpis)
    assert "77 rows" in prompt and "9 columns" in prompt
    assert "Revenue (quantity x unit_price): 207,992.00" in prompt
    assert "Top category: Electronics (33)" in prompt
    assert "Top customer: Ananya Rao (13)" in prompt
    assert "most common is Electronics" in prompt
    assert "only the numbers above" in prompt
    print("insight prompt OK")


def test_ask_ai_missing_key():
    with tempfile.TemporaryDirectory() as tmp:
        # Point settings at an empty folder: no key can be found there.
        with mock.patch.object(ai_settings, "SETTINGS_PATH",
                               Path(tmp) / "settings.json"):
            assert ai_settings.get_api_key() is None
            try:
                ai_settings.ask_ai("Hello")
                raise AssertionError("missing key must raise")
            except ValueError as e:
                assert "Groq API key" in str(e)
                assert "Settings" in str(e)
            try:
                fe.ai_insights_text(_sample_clean(), [])
                raise AssertionError("missing key must raise in insights")
            except ValueError as e:
                assert "Groq API key" in str(e)
    print("ask_ai missing-key OK")


def test_ask_ai_mocked_request():
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content":
                                          "Sales are led by Electronics."}}]}
            ).encode("utf-8")

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["auth"] = request.get_header("Authorization")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    with mock.patch.object(ai_settings, "get_api_key",
                           lambda path=None: "gsk_test_key"), \
         mock.patch.object(ai_settings.urllib.request, "urlopen",
                           fake_urlopen):
        reply = ai_settings.ask_ai("What does the data say?",
                                   system="Be brief.")
    assert reply == "Sales are led by Electronics."
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["method"] == "POST"
    assert captured["auth"] == "Bearer gsk_test_key"
    assert captured["body"]["model"] == "llama-3.3-70b-versatile"
    assert captured["body"]["messages"][0] == {"role": "system",
                                               "content": "Be brief."}
    assert captured["body"]["messages"][1]["content"] == "What does the data say?"
    print("ask_ai mocked request OK")


def test_settings_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "settings.json"
        assert ai_settings.load_settings(path)["groq_api_key"] == ""
        assert ai_settings.load_settings(path)["theme"] == "Dark green"
        assert ai_settings.get_api_key(path) is None
        ai_settings.save_settings({"groq_api_key": "gsk_abc",
                                   "theme": "Light"}, path)
        assert ai_settings.load_settings(path)["groq_api_key"] == "gsk_abc"
        assert ai_settings.get_api_key(path) == "gsk_abc"
        # A broken file falls back to defaults, never crashes.
        path.write_text("{not json", encoding="utf-8")
        assert ai_settings.load_settings(path)["theme"] == "Dark green"
    print("settings round-trip OK")


# --------------------------------------------------------------------------
# 5. paste from clipboard
# --------------------------------------------------------------------------

def test_parse_pasted_table():
    tabbed = "name\tage\tcity\nAarav\t25\tPatna\nPriya\t30\tDelhi\n"
    df = fe.parse_pasted_table(tabbed)
    assert list(df.columns) == ["name", "age", "city"]
    assert len(df) == 2 and df["age"].tolist() == [25, 30]

    comma = "name,age\nAarav,25\nPriya,30\n"
    df2 = fe.parse_pasted_table(comma)
    assert list(df2.columns) == ["name", "age"] and len(df2) == 2
    for bad in ("", "   ", None):
        try:
            fe.parse_pasted_table(bad)
            raise AssertionError("empty paste must raise")
        except ValueError:
            pass
    print("paste OK")


# --------------------------------------------------------------------------
# 6. row filter builder
# --------------------------------------------------------------------------

def test_filter_rules_sample():
    clean = _sample_clean()
    by_cat = fe.apply_filter_rules(
        clean, [{"column": "category", "condition": "equals",
                 "value": "Electronics"}])
    assert len(by_cat) == 33

    big_qty = fe.apply_filter_rules(
        clean, [{"column": "quantity", "condition": "greater than",
                 "value": "4"}])
    assert len(big_qty) == 10

    both = fe.apply_filter_rules(clean, [
        {"column": "category", "condition": "equals", "value": "Electronics"},
        {"column": "quantity", "condition": "greater than", "value": "2"}])
    assert len(both) == 22, len(both)

    contains = fe.apply_filter_rules(
        clean, [{"column": "customer", "condition": "contains",
                 "value": "ananya"}])
    assert len(contains) == 13

    empty = fe.apply_filter_rules(
        clean, [{"column": "region", "condition": "is empty", "value": ""}])
    assert len(empty) == 0  # cleaning filled missing regions with Unknown
    not_empty = fe.apply_filter_rules(
        clean, [{"column": "region", "condition": "is not empty", "value": ""}])
    assert len(not_empty) == 77
    assert len(fe.apply_filter_rules(clean, [])) == 77  # no rules = all rows
    print("filter rules OK: Electronics 33, qty>4 10, both 22, Ananya 13")


def test_filter_rules_errors_and_csv():
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    for call in (lambda: fe.apply_filter_rules(
                     df, [{"column": "nope", "condition": "equals",
                           "value": "x"}]),
                 lambda: fe.apply_filter_rules(
                     df, [{"column": "a", "condition": "about",
                           "value": "1"}])):
        try:
            call()
            raise AssertionError("bad rule must raise")
        except ValueError:
            pass
    out = fe.apply_filter_rules(df, [{"column": "a", "condition": "equals",
                                      "value": "2"}])
    raw = fe.filtered_to_csv_bytes(out)
    assert isinstance(raw, bytes)
    assert pd.read_csv(io.BytesIO(raw))["a"].tolist() == [2]
    print("filter errors + CSV bytes OK")


# --------------------------------------------------------------------------
# 7. sampling
# --------------------------------------------------------------------------

def test_sample_frame():
    big = pd.DataFrame({"n": range(5000), "v": ["x"] * 5000})
    first = fe.sample_frame(big, 1000, "first")
    assert len(first) == 1000 and first["n"].tolist() == list(range(1000))
    r1 = fe.sample_frame(big, 1000, "random", seed=7)
    r2 = fe.sample_frame(big, 1000, "random", seed=7)
    assert r1.equals(r2)  # same seed -> same sample
    r3 = fe.sample_frame(big, 1000, "random", seed=8)
    assert not r1.equals(r3)
    assert len(r1) == 1000 and r1["n"].nunique() == 1000
    small = pd.DataFrame({"n": [1, 2, 3]})
    assert len(fe.sample_frame(small, 1000, "first")) == 3
    for call in (lambda: fe.sample_frame(big, 10, "middle"),
                 lambda: fe.sample_frame(big, 0, "first")):
        try:
            call()
            raise AssertionError("bad sample must raise")
        except ValueError:
            pass
    print("sampling OK")


# --------------------------------------------------------------------------
# 8. auto-save workspace
# --------------------------------------------------------------------------

def test_workspace_roundtrip():
    raw, clean = _sample_raw(), _sample_clean()
    kpis = engine.auto_kpis(clean)
    _c, actions = engine.clean(raw)
    with tempfile.TemporaryDirectory() as tmp:
        folder = fe.save_workspace(raw, clean, "messy_sales.csv",
                                   actions, kpis, base_dir=tmp)
        assert (folder / "raw.csv").exists()
        assert (folder / "clean.csv").exists()
        assert (folder / "state.json").exists()
        state = json.loads((folder / "state.json").read_text())
        assert state["source_name"] == "messy_sales.csv"
        assert state["kpis"][0] == {"label": "Rows", "value": "77"}

        restored = fe.load_workspace(base_dir=tmp)
        assert restored is not None
        assert len(restored["raw"]) == 80 and len(restored["clean"]) == 77
        assert restored["source_name"] == "messy_sales.csv"
        assert restored["actions"][0] == ("Rows", "80 -> 77 rows")
        assert restored["kpis"][0] == {"label": "Rows", "value": "77"}

        # Raw-only save (fresh folder, so no stale clean.csv): clean is None.
        raw_only_dir = Path(tmp) / "rawonly"
        fe.save_workspace(raw, None, "raw only", [], [], base_dir=raw_only_dir)
        restored2 = fe.load_workspace(base_dir=raw_only_dir)
        assert restored2["clean"] is None
        assert len(restored2["raw"]) == 80
    with tempfile.TemporaryDirectory() as tmp:
        assert fe.load_workspace(base_dir=tmp) is None  # never saved
    print("workspace OK")


# --------------------------------------------------------------------------
# 9. dark mode + accent
# --------------------------------------------------------------------------

def test_themes():
    assert set(fe.THEMES) == {"Dark green", "Dark blue", "Light"}
    green = fe.theme_css("Dark green")
    assert "#121212" in green and "#2F5D5A" in green
    blue = fe.theme_css("Dark blue")
    assert "#0d1b2a" in blue and "#4da6ff" in blue
    light = fe.theme_css("Light")
    assert "#ffffff" in light and "#1a7f37" in light
    assert fe.theme_css("Nope") == fe.theme_css("Dark green")
    print("themes OK")


# --------------------------------------------------------------------------
# 10. data masking
# --------------------------------------------------------------------------

def test_mask_values():
    assert fe.mask_phone("98765 43210") == "98XXX X3210"
    assert fe.mask_phone("9876543210") == "98XXX X3210"
    assert fe.mask_phone("12345") == "XXXXX"
    assert fe.mask_email("name@x.com") == "n***@x.com"
    assert fe.mask_email("ananya.rao@gmail.com") == "a***@gmail.com"
    assert fe.mask_text("Aarav Sharma") == "A**** S*****"
    assert fe.mask_text("Ananya Rao") == "A***** R**"
    print("mask values OK")


def test_mask_columns():
    df = pd.DataFrame({
        "phone": ["98765 43210", "91234 56780"],
        "email": ["name@x.com", "a@b.co"],
        "customer": ["Aarav Sharma", "Priya Patel"],
        "amount": [100, 200],
    })
    masked, actions = fe.mask_columns(df, ["phone", "email", "customer"])
    assert list(masked["phone"]) == ["98XXX X3210", "91XXX X6780"]
    assert list(masked["email"]) == ["n***@x.com", "a***@b.co"]
    assert list(masked["customer"]) == ["A**** S*****", "P**** P****"]
    assert list(masked["amount"]) == [100, 200]  # untouched
    assert list(df["phone"]) == ["98765 43210", "91234 56780"]  # original kept
    assert "3 column(s)" in actions[0][1]

    explicit, _ = fe.mask_columns(df, ["customer"], {"customer": "text"})
    assert list(explicit["customer"]) == ["A**** S*****", "P**** P****"]
    try:
        fe.mask_columns(df, ["nope"])
        raise AssertionError("bad mask column must raise")
    except ValueError:
        pass
    print("mask columns OK")


def test_masked_bytes():
    df = pd.DataFrame({"phone": ["98765 43210"], "v": [1]})
    masked, _ = fe.mask_columns(df, ["phone"])
    csv = fe.masked_csv_bytes(masked)
    assert b"98XXX X3210" in csv and b"98765" not in csv
    xlsx = fe.masked_excel_bytes(masked)
    assert xlsx[:4] == b"PK\x03\x04"
    back = pd.read_excel(io.BytesIO(xlsx), sheet_name="Cleaned Data")
    assert back["phone"].tolist() == ["98XXX X3210"]
    print("masked bytes OK")


# --------------------------------------------------------------------------
# 11. versioned exports
# --------------------------------------------------------------------------

def test_versioned_names():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "versions.json"
        assert fe.next_versioned_name("cleaned.csv", path) == "cleaned_v1.csv"
        assert fe.next_versioned_name("cleaned.csv", path) == "cleaned_v2.csv"
        assert fe.next_versioned_name("report.xlsx", path) == "report_v1.xlsx"
        assert fe.next_versioned_name("cleaned.csv", path) == "cleaned_v3.csv"
        assert fe.peek_versioned_name("cleaned.csv", path) == "cleaned_v4.csv"
        assert fe.peek_versioned_name("cleaned.csv", path) == "cleaned_v4.csv"
        assert fe.next_versioned_name("cleaned", path) == "cleaned_v4.csv"
        stored = json.loads(path.read_text())
        assert stored == {"cleaned.csv": 4, "report.xlsx": 1}, stored
    try:
        fe.next_versioned_name("   ")
        raise AssertionError("empty base must raise")
    except ValueError:
        pass
    print("versioned names OK")


# --------------------------------------------------------------------------
# 12. Hindi/Urdu labels
# --------------------------------------------------------------------------

def test_lang():
    keys = ["app_title", "load", "preview", "join", "clean", "kpis",
            "dashboard", "compare", "report", "tools", "clean_my_data",
            "download_report", "try_sample", "tutorial"]
    for lang in ("en", "hi", "ur"):
        assert set(fe.LANG[lang]) == set(keys), lang
        for key in keys:
            assert isinstance(fe.LANG[lang][key], str)
            assert fe.LANG[lang][key].strip() != ""
    assert fe.get_text("clean_my_data", "en") == "Clean my data"
    assert fe.get_text("clean_my_data", "hi") == "मेरा डेटा साफ़ करें"
    assert fe.get_text("clean_my_data", "ur") == "میرا ڈیٹا صاف کریں"
    assert fe.get_text("app_title", "hi") == "डेटा क्लीनर स्टूडियो"
    assert fe.get_text("app_title", "ur") == "ڈیٹا کلینر اسٹوڈیو"
    assert fe.get_text("clean", "xx") == "Clean"  # unknown lang -> English
    assert fe.get_text("no_such_key", "hi") == "no_such_key"
    print("language labels OK")


# --------------------------------------------------------------------------
# render functions (FakeSt — no Streamlit server)
# --------------------------------------------------------------------------

class FakeSt:
    """Minimal stand-in for the streamlit module: widgets return preset
    values (or the first option / default), display calls are recorded."""

    def __init__(self, presets=None):
        self.session_state = {}
        self.presets = presets or {}
        self.calls = []

    def _rec(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def __getattr__(self, name):
        def _call(*args, **kwargs):
            self._rec(name, *args, **kwargs)
            return None
        return _call

    def selectbox(self, label, options, key=None, **kwargs):
        self._rec("selectbox", label, options, key)
        return self.presets.get(key, options[kwargs.get("index", 0)])

    def radio(self, label, options, key=None, **kwargs):
        self._rec("radio", label, options, key)
        return self.presets.get(key, options[0])

    def text_input(self, label, key=None, **kwargs):
        self._rec("text_input", label, key)
        return self.presets.get(key, kwargs.get("value", ""))

    def text_area(self, label, key=None, **kwargs):
        self._rec("text_area", label, key)
        return self.presets.get(key, "")

    def number_input(self, label, key=None, **kwargs):
        self._rec("number_input", label, key)
        return self.presets.get(key, kwargs.get("value", 0))

    def checkbox(self, label, key=None, **kwargs):
        self._rec("checkbox", label, key)
        return bool(self.presets.get(key, kwargs.get("value", False)))

    def multiselect(self, label, options, key=None, **kwargs):
        self._rec("multiselect", label, options, key)
        return self.presets.get(key, kwargs.get("default", []))

    def button(self, label, key=None, **kwargs):
        self._rec("button", label, key)
        return bool(self.presets.get(key, False))

    def download_button(self, label, data, key=None, **kwargs):
        self._rec("download_button", label, key)
        return False

    def columns(self, n):
        self._rec("columns", n)
        return [self] * n


def _called(fake, name):
    return [c for c in fake.calls if c[0] == name]


def test_render_split_merge():
    clean = _sample_clean()
    fake = FakeSt(presets={"n_split_mode": "Split one column into two",
                           "n_split_col": "customer",
                           "n_split_method": "First word / rest (names)",
                           "n_split_new1": "first_name",
                           "n_split_new2": "last_name",
                           "n_split_merge_apply": True})
    new_df, actions = fe.render_split_merge(fake, clean)
    assert new_df is not None
    assert list(new_df["first_name"].head(2)) == ["Aarav", "Priya"]
    assert len(actions) == 1 and actions[0][0] == "Split column: customer"

    fake2 = FakeSt(presets={"n_split_mode": "Merge two columns into one",
                            "n_merge_a": "category", "n_merge_b": "region",
                            "n_merge_sep": " - ", "n_merge_name": "cat_region",
                            "n_split_merge_apply": True})
    new_df2, actions2 = fe.render_split_merge(fake2, clean)
    assert new_df2 is not None
    assert new_df2["cat_region"].iloc[0] == "Electronics - Unknown"
    assert len(actions2) == 1

    fake3 = FakeSt()  # nothing pressed
    assert fe.render_split_merge(fake3, clean) == (None, [])
    assert _called(fake3, "radio")
    print("render split/merge OK")


def test_render_date_and_currency():
    clean = _sample_clean()
    fake = FakeSt(presets={"n_date_col": "order_date",
                           "n_date_apply": True})
    new_df, actions = fe.render_date_intelligence(fake, clean)
    assert new_df is not None and "order_date_weekday" in new_df.columns
    assert new_df["order_date_weekday"].iloc[0] == "Saturday"

    fake2 = FakeSt()
    assert fe.render_date_intelligence(fake2, clean) == (None, [])

    raw = _sample_raw()
    fake3 = FakeSt(presets={"n_fx_col": "Unit Price",
                            "n_fx_target": "INR", "n_fx_apply": True})
    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch.object(ai_settings, "SETTINGS_PATH",
                               Path(tmp) / "settings.json"):
            new_df3, actions3 = fe.render_currency(fake3, raw)
    assert new_df3 is not None
    assert new_df3["Unit Price_INR"].iloc[0] == 799 * 83
    assert len(actions3) == 1
    print("render date + currency OK")


def test_render_ai_insights_no_key_then_key():
    clean = _sample_clean()
    fake = FakeSt()
    with mock.patch.object(ai_settings, "get_api_key", lambda path=None: None):
        fe.render_ai_insights(fake, clean, [])
        assert _called(fake, "info")
        assert "Groq API key" in str(_called(fake, "info")[0][1])
        assert "n_ai_insight_data" not in fake.session_state

    fake2 = FakeSt(presets={"n_ai_get": True})
    with mock.patch.object(ai_settings, "get_api_key",
                           lambda path=None: "gsk_x"), \
         mock.patch.object(ai_settings, "ask_ai",
                           lambda prompt, system="": "Electronics leads sales."):
        fe.render_ai_insights(fake2, clean, engine.auto_kpis(clean))
        assert fake2.session_state["n_ai_insight_data"] == \
            "Electronics leads sales."
        assert any("Electronics leads sales." in str(c[1])
                   for c in _called(fake2, "write"))
    print("render AI insights OK")


def test_render_paste_and_filter():
    fake = FakeSt(presets={
        "n_paste_text": "name\tage\nAarav\t25\nPriya\t30\n",
        "n_paste_load": True})
    pasted = fe.render_paste(fake)
    assert pasted is not None and len(pasted) == 2
    assert list(pasted.columns) == ["name", "age"]

    clean = _sample_clean()
    fake2 = FakeSt(presets={"n_filter_col": "category",
                            "n_filter_cond": "equals",
                            "n_filter_value": "Electronics",
                            "n_filter_add": True})
    fe.render_filter_builder(fake2, clean)
    assert fake2.session_state["n_filter_rules_data"] == [
        {"column": "category", "condition": "equals",
         "value": "Electronics"}]
    assert _called(fake2, "download_button")
    assert any("33 of 77" in str(c[1]) for c in _called(fake2, "write"))
    print("render paste + filter OK")


def test_render_sampling():
    clean = _sample_clean()
    fake = FakeSt()
    assert fe.render_sampling(fake, clean) is None  # 77 rows: too small
    assert _called(fake, "info")

    big = pd.DataFrame({"n": range(5000),
                        "v": ["  x  "] * 5000})
    fake2 = FakeSt(presets={"n_sample_method": "First rows",
                            "n_sample_run": True, "n_sample_apply": True})
    result = fe.render_sampling(fake2, big, None)
    assert result is not None
    assert set(result) == {"sample_clean", "sample_actions", "clean_opts",
                           "sample_n", "sample_method"}
    assert len(result["sample_clean"]) == 1000
    assert result["sample_method"] == "first"
    assert result["clean_opts"] is None
    print("render sampling OK")


def test_render_workspace_theme_masking_versioned_language():
    fake = FakeSt(presets={"n_workspace_toggle": True})
    assert fe.render_workspace_toggle(fake) is True
    fake2 = FakeSt()
    assert fe.render_workspace_toggle(fake2) is False

    with tempfile.TemporaryDirectory() as tmp:
        settings_path = Path(tmp) / "settings.json"
        with mock.patch.object(ai_settings, "SETTINGS_PATH", settings_path):
            fake3 = FakeSt(presets={"n_theme_pick": "Dark blue"})
            assert fe.render_theme_picker(fake3) == "Dark blue"
            assert ai_settings.load_settings()["theme"] == "Dark blue"
            assert fake3.session_state["n_theme_data"] == "Dark blue"
            fake4 = FakeSt(presets={"n_lang_pick": "हिन्दी"})
            assert fe.render_language_picker(fake4) == "hi"
            assert ai_settings.load_settings()["language"] == "hi"
            assert fake4.session_state["n_lang_data"] == "hi"

    df = pd.DataFrame({"phone": ["98765 43210"], "email": ["a@b.co"],
                       "v": [1]})
    fake5 = FakeSt(presets={"n_mask_cols": ["phone", "email"]})
    assert fe.render_masking(fake5, df) == (None, [])
    assert len(_called(fake5, "download_button")) == 2

    with tempfile.TemporaryDirectory() as tmp:
        versions_path = Path(tmp) / "versions.json"
        with mock.patch.object(fe, "_versions_file",
                              lambda path=None: versions_path):
            fake6 = FakeSt(presets={"n_version_reserve": True})
            name = fe.render_versioned_download(fake6, df, "cleaned.csv")
            assert name == "cleaned_v1.csv"
            assert fake6.session_state["n_version_name_data"] == "cleaned_v1.csv"
            assert _called(fake6, "download_button")
    print("render workspace/theme/masking/versioned/language OK")


def test_render_settings():
    with tempfile.TemporaryDirectory() as tmp:
        settings_path = Path(tmp) / "settings.json"
        with mock.patch.object(ai_settings, "SETTINGS_PATH", settings_path):
            fake = FakeSt(presets={"ai_key_input": "gsk_saved",
                                   "ai_key_save": True})
            ai_settings.render_settings(fake)
            assert ai_settings.get_api_key() == "gsk_saved"
            assert _called(fake, "text_input")

            fake2 = FakeSt(presets={"ai_key_input": "gsk_saved",
                                    "ai_key_test": True})
            with mock.patch.object(ai_settings, "ask_ai",
                                   lambda prompt, system="": "OK"):
                ai_settings.render_settings(fake2)
            assert _called(fake2, "success")
    print("render settings OK")


if __name__ == "__main__":
    test_split_separator()
    test_split_first_last_word()
    test_split_errors()
    test_merge_columns()
    test_date_parts_sample()
    test_date_parts_errors()
    test_parse_money()
    test_convert_currency_sample()
    test_insight_prompt()
    test_ask_ai_missing_key()
    test_ask_ai_mocked_request()
    test_settings_roundtrip()
    test_parse_pasted_table()
    test_filter_rules_sample()
    test_filter_rules_errors_and_csv()
    test_sample_frame()
    test_workspace_roundtrip()
    test_themes()
    test_mask_values()
    test_mask_columns()
    test_masked_bytes()
    test_versioned_names()
    test_lang()
    test_render_split_merge()
    test_render_date_and_currency()
    test_render_ai_insights_no_key_then_key()
    test_render_paste_and_filter()
    test_render_sampling()
    test_render_workspace_theme_masking_versioned_language()
    test_render_settings()
    print("ALL ENRICH TESTS PASSED")
