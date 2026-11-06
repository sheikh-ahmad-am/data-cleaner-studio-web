"""Group 3 tests — recipes, undo/snapshots, find & replace, templates,
bulk mode, and the watch-folder script.

Run from the project root:
    .test-venv/bin/python tests/test_feat_automate.py
No Streamlit needed (render functions are not exercised here — they are
thin wrappers over the pure functions tested below).
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import engine
import feat_automate as fa

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = (ROOT / "sample_data" / "messy_sales.csv").read_bytes()


def load_sample():
    return engine.load_file("messy_sales.csv", SAMPLE)


# --------------------------------------------------------------- recipes ----
def test_recipe_round_trip():
    opts = dict(fa.DEFAULT_CLEAN_OPTS)
    opts["drop_dupes"] = False
    fuzzy = {"category": {"ELECTRONICS": "Electronics"}}
    recipe = fa.save_recipe(opts, fuzzy, "Monthly sales")
    text = fa.recipe_to_json(recipe)
    back = fa.recipe_from_json(text)
    assert back == recipe, "JSON round-trip must preserve the recipe"
    assert back["name"] == "Monthly sales"
    assert back["clean_opts"]["drop_dupes"] is False
    assert back["fuzzy"] == fuzzy
    print("recipe round-trip OK")


def test_recipe_validation():
    for bad in ('{"name": 1}', '{"clean_opts": {"nope": true}}',
                '{"clean_opts": {"drop_dupes": "yes"}}',
                '{"name": "x", "extra": 1}', 'not json at all', '[1, 2]',
                '{"name": ""}'):
        try:
            fa.recipe_from_json(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"should have raised ValueError: {bad!r}")
    try:
        fa.save_recipe({"drop_dupes": "yes"}, {}, "x")
        raise AssertionError("non-bool option should raise")
    except ValueError:
        pass
    print("recipe validation OK")


def test_apply_recipe_options_actually_work():
    """drop_dupes=False must keep the duplicates — this proves the recipe
    keys are translated to the engine's keys instead of being ignored."""
    df = load_sample()
    assert len(df) == 80
    recipe = fa.save_recipe(dict(fa.DEFAULT_CLEAN_OPTS), {}, "all on")
    cleaned, _ = fa.apply_recipe(df, recipe)
    assert len(cleaned) == 77 and len(cleaned.columns) == 9, len(cleaned)
    # The sample's known totals still hold after a full clean.
    kpis = {k["label"]: k["value"] for k in engine.auto_kpis(cleaned)}
    assert kpis["Revenue (quantity x unit_price)"] == "207,992.00", kpis
    assert kpis["Top category"] == "Electronics (33)", kpis
    opts = dict(fa.DEFAULT_CLEAN_OPTS)
    opts["drop_dupes"] = False
    recipe = fa.save_recipe(opts, {}, "keep dupes")
    cleaned, _ = fa.apply_recipe(df, recipe)
    assert len(cleaned) == 80, "drop_dupes=False must keep all 80 rows"
    print("apply_recipe OK (77 rows cleaned, dupes kept when switched off)")


def test_apply_recipe_fuzzy():
    df = pd.DataFrame({"city": ["Delhi", "Dehli", "Patna", "Dehli"],
                       "sales": [10, 20, 30, 40]})
    recipe = fa.save_recipe(dict(fa.DEFAULT_CLEAN_OPTS),
                            {"city": {"Dehli": "Delhi"}}, "fix cities")
    cleaned, actions = fa.apply_recipe(df, recipe)
    assert sorted(cleaned["city"].unique()) == ["Delhi", "Patna"], \
        cleaned["city"].unique()
    assert any("fuzzy" in step.lower() for step, _ in actions), actions
    print("apply_recipe fuzzy OK")


# ------------------------------------------------------ undo + snapshots ---
def test_snapshot_undo_restores_exact_frame():
    raw = load_sample()
    cleaned, actions = engine.clean(raw)
    expected = cleaned.copy(deep=True)  # pristine reference (state mutates cleaned)
    state = {"raw": raw, "clean": cleaned, "actions": actions,
             "kpis": engine.auto_kpis(cleaned)}
    fa.push_snapshot(state, "before edit")
    # Mutate the live frame in place, the way an edit would.
    state["clean"].loc[0, "unit_price"] = 999999.0
    state["clean"] = state["clean"].drop(columns=["region"])
    state["actions"] = [("edited", "oops")]
    label = fa.undo(state)
    assert label == "before edit", label
    pd.testing.assert_frame_equal(state["clean"], expected)
    assert state["actions"] == actions
    assert state["kpis"] == engine.auto_kpis(expected)
    assert fa.undo(state) is None, "second undo with no snapshots must be None"
    print("snapshot undo OK (exact frame restored)")


def test_snapshot_is_a_copy_not_a_reference():
    raw = load_sample()
    cleaned, _ = engine.clean(raw)
    state = {"raw": raw, "clean": cleaned, "actions": [], "kpis": []}
    fa.push_snapshot(state, "snap")
    state["clean"].loc[0, "unit_price"] = -1.0
    assert fa.list_snapshots(state) == ["snap"]
    fa.undo(state)
    assert state["clean"].loc[0, "unit_price"] != -1.0
    print("snapshot copy OK")


def test_snapshot_cap():
    state = {"raw": None, "clean": None, "actions": [], "kpis": []}
    for i in range(12):
        fa.push_snapshot(state, f"s{i}")
    labels = fa.list_snapshots(state)
    assert len(labels) == 10, labels
    assert labels[0] == "s2" and labels[-1] == "s11", labels
    print("snapshot cap OK (10 kept, oldest dropped)")


# --------------------------------------------------------- find & replace ---
def test_find_replace_counts():
    df = pd.DataFrame({"city": ["Delhi", "Dehli", "Patna", "Dehli", None],
                       "n": [1, 2, 3, 4, 5]})
    out, count = fa.find_replace(df, "city", "Dehli", "Delhi")
    assert count == 2, count
    assert out["city"].tolist()[:4] == ["Delhi", "Delhi", "Patna", "Delhi"]
    assert pd.isna(out["city"].iloc[4]), "blank cell must stay blank"
    assert df["city"].tolist()[1] == "Dehli", "input frame must not change"
    # Case-insensitive: matches 'delhi' and 'DELHI' too.
    out, count = fa.find_replace(df, "city", "delhi", "New Delhi",
                                 match_case=False)
    assert count == 1, count  # only 'Delhi' matches case-insensitively here
    out2, count2 = fa.find_replace(df, "city", "DELHI", "X", match_case=True)
    assert count2 == 0, count2
    # Regex: collapse the two Dehli cells via a pattern.
    out, count = fa.find_replace(df, "city", r"Dehl.", "Delhi", use_regex=True)
    assert count == 2, count
    print("find_replace OK (counts 2 / 1 / 0 / 2)")


def test_find_replace_errors():
    df = pd.DataFrame({"city": ["Delhi"], "n": [1]})
    for kwargs in ({"column": "nope"}, {"find": ""}):
        try:
            fa.find_replace(df, kwargs.get("column", "city"),
                            kwargs.get("find", "x"), "y")
            raise AssertionError(f"should raise for {kwargs}")
        except ValueError:
            pass
    try:
        fa.find_replace(df, "n", "1", "2")
        raise AssertionError("numeric column should raise")
    except ValueError:
        pass
    try:
        fa.find_replace(df, "city", "([", "x", use_regex=True)
        raise AssertionError("bad regex should raise")
    except ValueError:
        pass
    print("find_replace errors OK")


# --------------------------------------------------------------- templates --
def test_templates_exist_and_apply():
    assert set(fa.TEMPLATES) == {"sales", "attendance", "inventory"}
    for name, t in fa.TEMPLATES.items():
        assert t["description"] and set(t["clean_opts"]) == set(fa.CLEAN_OPT_KEYS)
        assert t["suggested_kpis"], f"{name} needs suggested KPIs"
    cleaned, _ = fa.apply_template(load_sample(), "sales")
    assert len(cleaned) == 77, len(cleaned)
    try:
        fa.apply_template(load_sample(), "nope")
        raise AssertionError("unknown template should raise")
    except ValueError:
        pass
    print("templates OK")


def test_template_sample_files():
    for name, fname in fa.TEMPLATE_SAMPLES.items():
        path = ROOT / "sample_data" / fname
        assert path.exists(), f"missing sample file {fname}"
        df = engine.load_file(fname, path.read_bytes())
        if name in ("attendance", "inventory"):
            assert 20 <= len(df) <= 30, f"{fname}: {len(df)} rows"
        assert df.duplicated().sum() >= 1, f"{fname}: expected a duplicate row"
        assert int(df.isna().sum().sum()) >= 1, f"{fname}: expected a blank"
        cleaned, _ = fa.apply_template(df, name)
        assert len(cleaned) < len(df), f"{name}: template should drop rows"
        assert len(cleaned.columns) <= len(df.columns)
    print("template sample files OK (messy, template cleans them)")


# ------------------------------------------------------------------- bulk ---
def test_bulk_handles_bad_file():
    good = ("good.csv", SAMPLE)
    bad = ("broken.xyz", b"this is not a supported file")
    also_good = ("also_good.csv",
                 b"Name,Amount\nAarav,100\nPriya,200\n")
    results = fa.bulk_clean([good, bad, also_good],
                            fa.save_recipe(dict(fa.DEFAULT_CLEAN_OPTS), {}, "d"))
    assert len(results) == 3
    assert results[0]["error"] is None and len(results[0]["cleaned_df"]) == 77
    assert results[1]["cleaned_df"] is None and results[1]["error"]
    assert results[2]["error"] is None and len(results[2]["cleaned_df"]) == 2
    summary = fa.bulk_summary(results)
    assert list(summary.columns) == ["name", "rows_in", "rows_out", "status"]
    assert len(summary) == 3
    assert summary.iloc[0]["status"] == "OK"
    assert summary.iloc[0]["rows_in"] == 80 and summary.iloc[0]["rows_out"] == 77
    assert summary.iloc[1]["status"].startswith("Failed")
    print("bulk OK (bad file isolated, summary rows correct)")


# ------------------------------------------------------------ watch folder --
def test_watch_folder_once():
    with tempfile.TemporaryDirectory() as tmp:
        watch_dir = Path(tmp) / "in"
        out_dir = Path(tmp) / "out"
        watch_dir.mkdir()
        (watch_dir / "messy.csv").write_bytes(SAMPLE)
        (watch_dir / "notes.md").write_text("not a data file\n")
        recipe_path = Path(tmp) / "recipe.json"
        recipe_path.write_text(json.dumps({
            "name": "watch test",
            "clean_opts": dict(fa.DEFAULT_CLEAN_OPTS),
            "fuzzy": {},
        }))
        proc = subprocess.run(
            [sys.executable, str(ROOT / "watch_folder.py"),
             "--watch", str(watch_dir), "--out", str(out_dir),
             "--recipe", str(recipe_path), "--once"],
            capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        cleaned = pd.read_csv(out_dir / "messy_cleaned.csv")
        assert len(cleaned) == 77, len(cleaned)
        assert len(cleaned.columns) == 9
        log_txt = (out_dir / "messy_cleaning_log.txt").read_text()
        assert "77" in log_txt and "Drop duplicate" in log_txt
        watch_log = (out_dir / "watch_log.txt").read_text()
        assert "messy.csv" in watch_log and "CLEANED" in watch_log
        assert not (out_dir / "notes_cleaned.csv").exists(), \
            "non-data files must not be cleaned"
    print("watch_folder --once OK (77-row cleaned CSV + logs)")


if __name__ == "__main__":
    test_recipe_round_trip()
    test_recipe_validation()
    test_apply_recipe_options_actually_work()
    test_apply_recipe_fuzzy()
    test_snapshot_undo_restores_exact_frame()
    test_snapshot_is_a_copy_not_a_reference()
    test_snapshot_cap()
    test_find_replace_counts()
    test_find_replace_errors()
    test_templates_exist_and_apply()
    test_template_sample_files()
    test_bulk_handles_bad_file()
    test_watch_folder_once()
    print("ALL GROUP 3 TESTS PASSED")
