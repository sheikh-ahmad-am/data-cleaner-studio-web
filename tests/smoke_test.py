"""Headless smoke test for the Streamlit UI (AppTest — no browser needed).

Flow: open app -> no data -> click 'Try the messy sample' -> data loads
-> click 'Clean my data' -> cleaning log appears -> KPI + Dashboard tabs
render without exceptions.
Run:  /path/to/venv/bin/python tests/smoke_test.py   (from the project root)
"""

from pathlib import Path
import os
import shutil

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "simple_app.py")


def find_button(at, label):
    """AppTest label lookup is unreliable here; match by iterating instead."""
    for b in at.button:
        if b.label == label:
            return b
    raise AssertionError(f"button {label!r} missing")


def main():
    # Start from a clean slate: a previous (failed) run may have left
    # settings.json with tutorial_seen=True, which would hide the
    # first-run banner this test checks.
    _root = Path(__file__).resolve().parent.parent
    for name in ("settings.json", "views.json", "recent.json",
                 "versions.json", "seen_version.json", "brand.json"):
        _p = _root / name
        if _p.exists():
            _p.unlink()
    for dname in ("recent", "backups", "workspace"):
        _d = _root / dname
        if _d.is_dir():
            shutil.rmtree(_d)

    # The 100k-row chunked-clean run takes longer than AppTest's 3s
    # default; 30s covers it without changing the app.
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception, f"startup exception: {at.exception}"
    find_button(at, "Try the messy sample")

    find_button(at, "Try the messy sample").click().run()
    assert not at.exception, f"exception after loading sample: {at.exception}"
    assert at.session_state["raw"] is not None, "raw data not loaded"
    assert len(at.session_state["raw"]) == 80, "sample should have 80 rows"
    print("sample loaded: 80 rows")

    find_button(at, "Clean my data").click().run()
    assert not at.exception, f"exception after cleaning: {at.exception}"
    clean = at.session_state["clean"]
    assert clean is not None and len(clean) == 77, "cleaned data should have 77 rows"
    assert "notes" not in clean.columns
    print("cleaned: 77 rows, notes column dropped")

    # Dashboard + KPIs + Report widgets render (every tab executes each run,
    # so the no-exception check after cleaning already covers rendering;
    # the chart itself runs through Altair, which AppTest cannot query).
    assert any("Group by" in s.label for s in at.selectbox), "dashboard X picker missing"
    assert any("Download cleaned Excel" in b.label for b in at.download_button), "excel download missing"
    assert any("Download PDF report" in b.label for b in at.download_button), "PDF download missing"
    assert any("Second file" in f.label for f in at.file_uploader), "join file uploader missing"
    assert any("Find similar names" in b.label for b in at.button), "fuzzy button missing"
    print("dashboard pickers + report downloads + join + fuzzy render")

    # New chart types render without exceptions. Re-fetch the picker each
    # time: switching chart type rebuilds the widget tree (the Bar/Line/
    # Donut pickers disappear), so a stale element reference breaks.
    for kind in ("Histogram", "Scatter", "Box plot", "Heatmap", "Treemap",
                 "Funnel"):
        chart = next(s for s in at.selectbox if s.label == "Chart")
        chart.set_value(kind).run()
        assert not at.exception, f"exception on {kind} chart: {at.exception}"
    print("Histogram / Scatter / Box plot / Heatmap / Treemap / Funnel render")

    # v1.2 sections render (buttons + downloads from all four groups).
    for label in ("Save snapshot", "Undo last snapshot", "Replace",
                  "Build pivot table", "Add calculated column",
                  "Add rule", "Apply",
                  "Send test email now", "Test connection",
                  "Find near-duplicates", "Clean all files"):
        assert any(label == b.label for b in at.button), \
            f"button {label!r} missing"
    for label in ("Download PowerPoint report (.pptx)",
                  "Download audit log (CSV)", "Download data dictionary (.md)"):
        assert any(label in b.label for b in at.download_button), \
            f"download {label!r} missing"
    print("v1.2 buttons + downloads render")

    # Gated features: upload first, then the button appears and runs.
    def _up(label, files):
        up = next(f for f in at.file_uploader if f.label == label)
        up.set_value(files).run()
        assert not at.exception, f"exception uploading to {label!r}: {at.exception}"

    _up("Other file to compare against (CSV, Excel or JSON)",
        [("compare_old.csv", open("test-pack/compare_old.csv", "rb").read(),
          "text/csv")])
    key_sel = next(s for s in at.selectbox if s.label == "Match rows by")
    key_sel.set_value("order_id").run()
    find_button(at, "Compare files").click().run()
    assert not at.exception, f"exception on compare: {at.exception}"
    cmp_res = at.session_state["compare_result"]
    assert cmp_res["added"] == 77 and cmp_res["removed"] == 5, \
        f"unexpected compare result: {cmp_res}"
    print("compare works: added 77, removed 5")

    _up("Files to append (CSV, Excel or JSON)",
        [("append_jan.csv", open("test-pack/append_jan.csv", "rb").read(),
          "text/csv"),
         ("append_feb.csv", open("test-pack/append_feb.csv", "rb").read(),
          "text/csv")])
    find_button(at, "Append files").click().run()
    assert not at.exception, f"exception on append: {at.exception}"
    combined, _rep, _names = at.session_state["append_result"]
    assert len(combined) == 83, f"appended frame should have 83 rows, got {len(combined)}"
    print("append works: 77 + 3 + 3 = 83 rows")

    _up("Previous file (CSV, Excel or JSON)",
        [("compare_old.csv", open("test-pack/compare_old.csv", "rb").read(),
          "text/csv")])
    find_button(at, "Check for anomalies").click().run()
    assert not at.exception, f"exception on anomaly check: {at.exception}"
    anom = at.session_state["anomaly_result"]
    assert anom and any(r["flagged"] for r in anom), \
        f"expected a flagged KPI jump, got {anom}"
    print("anomaly alerts work:", [r["label"] for r in anom if r["flagged"]])

    _up("Files to clean",
        [("messy_sales.csv", open("sample_data/messy_sales.csv", "rb").read(),
          "text/csv"),
         ("fuzzy_names.csv", open("test-pack/fuzzy_names.csv", "rb").read(),
          "text/csv")])
    find_button(at, "Clean all files").click().run()
    assert not at.exception, f"exception on bulk clean: {at.exception}"
    bulk = at.session_state["a_bulk_results"]
    assert len(bulk) == 2 and all(r["error"] is None for r in bulk), \
        f"bulk should clean 2 files, got {bulk}"
    print("bulk clean works: 2 files OK")

    # Near-duplicates: same look-alike frame as the fuzzy test below.
    import pandas as pd
    at.session_state["clean"] = pd.DataFrame(
        {"name": ["Aarav", "Arav", "Priya", "Priyaa", "Delhi", "Dehli"],
         "sales": [10, 20, 30, 40, 50, 60]})
    at.run()
    assert not at.exception, f"exception setting up near-dupe frame: {at.exception}"
    find_button(at, "Find near-duplicates").click().run()
    assert not at.exception, f"exception on near-dupe find: {at.exception}"
    groups = at.session_state.get("q_nd_groups_data")
    assert groups and len(groups) == 3, f"expected 3 near-dupe groups, got {groups}"
    find_button(at, "Merge these groups").click().run()
    assert not at.exception, f"exception on near-dupe merge: {at.exception}"
    assert len(at.session_state["clean"]) == 3, \
        "merging 3 near-dupe groups should leave 3 rows"
    print("near-duplicate find + merge works")

    # Fuzzy matching finds the sample's mixed-case categories are already
    # unified, so test it on a column with real look-alikes instead.
    at.session_state["clean"] = pd.DataFrame(
        {"name": ["Aarav", "Arav", "Priya", "Priyaa", "Delhi", "Dehli"],
         "sales": [10, 20, 30, 40, 50, 60]})
    at.run()
    fcol = next(s for s in at.selectbox
                if s.label == "Column" and "name" in list(s.options))
    fcol.set_value("name").run()
    find_button(at, "Find similar names").click().run()
    assert not at.exception, f"exception on fuzzy find: {at.exception}"
    groups = at.session_state.get("fuzzy_groups")
    assert groups and len(groups) == 3, f"expected 3 fuzzy groups, got {groups}"
    find_button(at, "Merge these names").click().run()
    assert not at.exception, f"exception on fuzzy apply: {at.exception}"
    assert sorted(at.session_state["clean"]["name"].unique()) == [
        "Aarav", "Delhi", "Priya"], "fuzzy merge did not unify names"
    print("fuzzy find + merge works")

    # Join: feed the second file through the uploader and preview.
    join_up = next(f for f in at.file_uploader if "Second file" in f.label)
    join_up.set_value([("cities.csv",
                        b"customer,city\nAnanya Rao,Delhi\nAarav Sharma,Patna\n",
                        "text/csv")]).run()
    assert not at.exception, f"exception on join upload: {at.exception}"
    left_key = next(s for s in at.selectbox if s.label == "Key in this file")
    left_key.set_value("Customer").run()  # raw (pre-clean) column name
    right_key = next(s for s in at.selectbox if s.label == "Key in second file")
    right_key.set_value("customer").run()
    find_button(at, "Preview join").click().run()
    assert not at.exception, f"exception on join preview: {at.exception}"
    joined, info = at.session_state["join_result"]
    assert info["matched_keys"] == 2, f"expected 2 matched keys, got {info}"
    assert "city" in joined.columns, "joined column missing"
    print("join preview works:", info)

    # The v1.1 checkbox bug is fixed: unchecking "Drop duplicate rows"
    # must actually keep the duplicates (80 rows, not 77).
    drop_box = next(c for c in at.checkbox if c.label == "Drop duplicate rows")
    drop_box.uncheck().run()
    find_button(at, "Clean my data").click().run()
    assert not at.exception, f"exception after uncheck-clean: {at.exception}"
    assert len(at.session_state["clean"]) == 80, \
        "unchecked drop_dupes should keep 80 rows"
    drop_box = next(c for c in at.checkbox if c.label == "Drop duplicate rows")
    drop_box.check().run()
    find_button(at, "Clean my data").click().run()
    assert len(at.session_state["clean"]) == 77, \
        "re-checked drop_dupes should give 77 rows"
    print("checkboxes really control cleaning (80 vs 77 rows)")

    # Undo restores the state before the last clean (the 80-row frame).
    find_button(at, "Undo last snapshot").click().run()
    assert not at.exception, f"exception on undo: {at.exception}"
    assert len(at.session_state["clean"]) == 80, \
        "undo should restore the 80-row frame"
    print("undo works")

    # Multi-sheet Excel: upload the workbook, pick the sheet, load it.
    xlsx_up = next(f for f in at.file_uploader if f.label == "Upload a file")
    xlsx_up.set_value([("messy_sales.xlsx",
                        open("test-pack/messy_sales.xlsx", "rb").read(),
                        "application/vnd.openxmlformats-officedocument"
                        ".spreadsheetml.sheet")]).run()
    assert not at.exception, f"exception on xlsx upload: {at.exception}"
    assert any(s.label == "Sheet" for s in at.selectbox), "sheet picker missing"
    find_button(at, "Load sheet").click().run()
    assert not at.exception, f"exception on sheet load: {at.exception}"
    assert len(at.session_state["raw"]) == 80, "xlsx sheet should load 80 rows"
    assert "Sheet1" in at.session_state["source_name"], \
        f"unexpected source: {at.session_state['source_name']}"
    print("multi-sheet Excel load works")

    # ---- v1.3: clean again (the xlsx load reset clean), then check the
    # new sections render and the main flows work.
    find_button(at, "Clean my data").click().run()
    assert not at.exception, f"exception on v1.3 clean: {at.exception}"
    assert len(at.session_state["clean"]) == 77, "v1.3 clean should give 77 rows"

    md = lambda: [m.value for m in at.markdown]  # noqa: E731
    info = lambda: [i.value for i in at.info]  # noqa: E731
    success = lambda: [s.value for s in at.success]  # noqa: E731
    assert any(s.label == "Theme" for s in at.selectbox), "theme picker missing"
    assert any(s.label == "Language" for s in at.selectbox), "language picker missing"
    assert any(c.label == "Auto-save my workspace" for c in at.checkbox), "workspace toggle missing"
    assert any(c.label == "Client mode (simple view)" for c in at.checkbox), "client mode toggle missing"
    assert any("No recent files yet" in v for v in info()), "recent files section missing"
    assert any(t.label and "Paste the copied table" in t.label for t in at.text_area), "paste area missing"
    assert any(t.label == "Search" for t in at.text_input), "search box missing"
    assert any("Pick a column, a condition and a value" in v for v in md()), "filter builder missing"
    assert any("Things we spotted in your data" in v for v in md()), "suggestions missing"
    assert any("Every row gets a health mark" in v for v in md()), "trust scores missing"
    assert any(b.label == "Set goal" for b in at.button), "goal tracking missing"
    assert any("Try a change before you make it" in v for v in md()), "what-if missing"
    assert any("Groq API key" in v for v in info()), "AI insights missing"
    assert any(b.label == "Save this view" for b in at.button), "saved views missing"
    assert any("rise and fall together" in v for v in md()), "correlations missing"
    assert any(b.label == "Forecast the next day" for b in at.button), "forecast missing"
    assert any(t.label == "Your question" for t in at.text_input), "ask missing"
    assert any(b.label == "Run everything" for b in at.button), "one-click missing"
    assert any(b.label == "Reserve this version" for b in at.button), "versioned export missing"
    assert any("Download dashboard (.html)" in b.label for b in at.download_button), "HTML dashboard missing"
    assert any("Download case study (.zip)" in b.label for b in at.download_button), "portfolio missing"
    assert any("Download styled Excel (.xlsx)" in b.label for b in at.download_button), "styled Excel missing"
    assert any("Download morning_run.py" in b.label for b in at.download_button), "morning run missing"
    assert any("These are browser shortcuts" in v for v in md()), "shortcuts missing"
    print("v1.3 sections render")

    # Search: "ananya" finds her 14 rows (raw file — one duplicate row
    # of hers is still in the raw data; the cleaned file has 13).
    search_box = next(t for t in at.text_input if t.label == "Search")
    search_box.set_value("ananya").run()
    assert not at.exception, f"exception on search: {at.exception}"
    assert any("14 of 80 rows match" in v for v in md()), "search should find 14 rows"
    search_box.set_value("").run()
    print("search works: ananya -> 14 rows")

    # Filter builder: category equals Electronics -> 34 of 80 raw rows
    # (33 after cleaning — the raw file still holds the duplicate row).
    fcol = next(s for s in at.selectbox
                if s.label == "Column" and "Category" in list(s.options))
    fcol.set_value("Category").run()
    cond = next(s for s in at.selectbox if s.label == "Condition")
    cond.set_value("equals").run()
    val = next(t for t in at.text_input if t.label == "Value")
    val.set_value("Electronics").run()
    find_button(at, "Add rule").click().run()
    assert not at.exception, f"exception on filter add: {at.exception}"
    assert any("34 of 80 rows match" in v for v in md()), "filter should match 34 rows"
    find_button(at, "Clear all rules").click().run()
    print("filter builder works: Electronics -> 34 rows")

    # Ask: rule layer answers from the data, no key needed.
    ask_box = next(t for t in at.text_input if t.label == "Your question")
    ask_box.set_value("which region sold the most?").run()
    find_button(at, "Ask").click().run()
    assert not at.exception, f"exception on ask: {at.exception}"
    assert any("West (19 rows)" in v for v in success()), "ask should answer West (19 rows)"
    print("ask works: which region sold the most? -> West (19 rows)")

    # Saved views: save the current chart, then jump back to it.
    view_name = next(t for t in at.text_input if t.label == "View name")
    view_name.set_value("Sales by region").run()
    find_button(at, "Save this view").click().run()
    assert not at.exception, f"exception on view save: {at.exception}"
    assert "Sales by region" in at.session_state.get("an_views_data", {}), \
        "view was not saved"
    find_button(at, "Go to this view").click().run()
    assert not at.exception, f"exception on view apply: {at.exception}"
    assert at.session_state.get("an_pending_view") is None, \
        "pending view should have been applied"
    print("saved views work: save + apply")

    # Client mode: only the simple tabs remain.
    client_box = next(c for c in at.checkbox
                      if c.label == "Client mode (simple view)")
    client_box.check().run()
    assert not at.exception, f"exception on client mode: {at.exception}"
    assert [t.label for t in at.tabs] == [
        "Preview", "Clean", "KPIs", "Dashboard", "Report", "How to use"], \
        f"client mode tabs wrong: {[t.label for t in at.tabs]}"
    client_box = next(c for c in at.checkbox
                      if c.label == "Client mode (simple view)")
    client_box.uncheck().run()
    assert len(at.tabs) == 9, "full tabs should return after client mode off"
    print("client mode works: 6 tabs on, 9 tabs off")

    # ---- v1.4: tutorial tab + first-run banner, brand, schedule,
    # live DB (refused = honest error), Parquet, live formulas,
    # live currency button, chunked clean on a big CSV.
    assert "How to use" in [t.label for t in at.tabs], "tutorial tab missing"
    assert any("First time here?" in v for v in info()), "first-run banner missing"
    find_button(at, "Got it").click().run()
    assert not at.exception, f"exception on banner Got it: {at.exception}"
    # AppTest quirk (same as the language switch): the info box drawn in
    # the click's own run is still there — the banner only disappears on
    # the NEXT run, once the saved flag is read.
    at.run()
    assert not any("First time here?" in v for v in info()), \
        "banner should hide after Got it"
    assert any("Upload a CSV, Excel or JSON file" in v for v in md()), \
        "tutorial page steps missing"
    print("tutorial works: banner hides after Got it, steps render")

    assert any(t.label == "Brand name" for t in at.text_input), \
        "brand name input missing"
    assert any(b.label == "Save brand" for b in at.button), \
        "brand save button missing"
    assert any(b.label == "Set up daily auto-clean" for b in at.button), \
        "schedule setup button missing"
    print("brand + schedule sections render")

    find_button(at, "Set up daily auto-clean").click().run()
    assert not at.exception, f"exception on schedule setup: {at.exception}"
    assert any("not Windows" in v for v in info()), \
        "schedule should explain Windows-only"
    print("schedule setup explains Windows-only on Linux")

    _db_pick = next(s for s in at.selectbox if s.label == "Database")
    _db_pick.set_value("PostgreSQL").run()
    find_button(at, "Test connection").click().run()
    assert not at.exception, f"exception on DB test: {at.exception}"
    _err = [e.value for e in at.error]
    assert any("NOT installed" in v for v in _err), \
        f"DB test should report the missing driver, got {_err}"
    print("DB test connection reports the missing driver honestly")

    _up("Upload a file",
        [("messy_sales.parquet",
          open("test-pack/messy_sales.parquet", "rb").read(),
          "application/octet-stream")])
    assert len(at.session_state["raw"]) == 80, "parquet should load 80 rows"
    find_button(at, "Clean my data").click().run()
    assert not at.exception, f"exception on parquet clean: {at.exception}"
    assert len(at.session_state["clean"]) == 77, \
        "parquet clean should give 77 rows"
    assert any(c.label == "Excel KPIs as live formulas" for c in at.checkbox), \
        "formulas toggle missing"
    assert any("Download cleaned Parquet" in b.label
               for b in at.download_button), "parquet download missing"
    assert any(b.label == "Get live rates" for b in at.button), \
        "live rates button missing"
    print("parquet load + clean works: 80 -> 77; formulas toggle, "
          "parquet download, live rates button render")

    # Chunked clean: a 100,001-row CSV (one exact duplicate) must clean
    # through the chunked path to exactly 100,000 rows.
    import csv
    import io
    _buf = io.StringIO()
    _w = csv.writer(_buf)
    _w.writerow(["order_id", "customer", "amount"])
    for i in range(100000):
        _w.writerow([i, f"Customer {i % 50}", 100 + (i % 7)])
    _w.writerow([0, "Customer 0", 100])  # exact duplicate of row 0
    _up("Upload a file",
        [("big_sales.csv", _buf.getvalue().encode("utf-8"), "text/csv")])
    assert len(at.session_state["raw"]) == 100001, \
        "big csv should load 100,001 rows"
    find_button(at, "Clean my data").click().run()
    assert not at.exception, f"exception on big clean: {at.exception}"
    assert len(at.session_state["clean"]) == 100000, \
        "chunked clean should give 100,000 rows"
    print("chunked clean works: 100,001 -> 100,000 rows")

    # Language switch (last — it relabels the buttons): Hindi title.
    # Note: AppTest does not process the st.rerun() that set_language
    # triggers inside the same .run() call, so the title only changes on
    # the NEXT run. A real browser reruns immediately.
    lang_pick = next(s for s in at.selectbox if s.label == "Language")
    lang_pick.set_value("हिन्दी").run()
    at.run()
    assert not at.exception, f"exception on language switch: {at.exception}"
    assert [t.value for t in at.title] == ["डेटा क्लीनर स्टूडियो"], \
        f"Hindi title wrong: {[t.value for t in at.title]}"
    lang_pick = next(s for s in at.selectbox if s.label == "Language")
    lang_pick.set_value("English").run()
    at.run()
    assert [t.value for t in at.title] == ["Data Cleaner Studio"], \
        "title should return to English"
    print("language switch works: English -> हिन्दी -> English")

    # Clean up the local state files this run created (settings, views),
    # so the project folder stays exactly as the user left it.
    import shutil
    for name in ("settings.json", "views.json", "recent.json",
                 "versions.json", "seen_version.json", "brand.json"):
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", name)
        if os.path.exists(p):
            os.remove(p)
    for dname in ("recent", "backups", "workspace"):
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", dname)
        if os.path.isdir(d):
            shutil.rmtree(d)

    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
