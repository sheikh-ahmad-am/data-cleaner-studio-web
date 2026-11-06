#!/usr/bin/env python3
"""Morning run — Data Cleaner Studio (Batch 5, v1.3).

Cleans every file in a `morning_in/` folder with a saved recipe and
writes the cleaned files to `morning_out/`. Made to be run by Windows
Task Scheduler every morning (see setup_morning_run.bat), but it also
runs by hand:

    python morning_run.py [--in DIR] [--out DIR] [--recipe FILE]

--in defaults to morning_in/ next to this script, --out to
morning_out/ next to it, --recipe to morning_recipe.json next to it.
Without a recipe file it uses the standard all-fixes cleaning.
One bad file is logged and skipped; the rest still get cleaned.
Needs only plain python3 + pandas. No Streamlit, no Task Scheduler.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import engine  # noqa: E402
import feat_automate  # noqa: E402

FILE_TYPES = (".csv", ".xlsx", ".xls", ".json")


def run_morning(in_dir, out_dir, recipe_path=None):
    """Clean every supported file in in_dir with the recipe and write
    cleaned CSVs (+ a cleaning log per file) into out_dir. Returns a
    list of result dicts: {name, rows_in, rows_out, status}. Missing
    folders are created; a missing in_dir means nothing to do."""
    in_dir, out_dir = Path(in_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if recipe_path is not None and Path(recipe_path).exists():
        recipe = feat_automate.recipe_from_json(
            Path(recipe_path).read_text(encoding="utf-8"))
    else:
        recipe = feat_automate.save_recipe(
            dict(feat_automate.DEFAULT_CLEAN_OPTS), {}, "morning-default")
    results = []
    if not in_dir.exists():
        in_dir.mkdir(parents=True, exist_ok=True)
        return results
    for path in sorted(in_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in FILE_TYPES:
            continue
        try:
            raw = engine.load_file(path.name, path.read_bytes())
            rows_in = len(raw)
            cleaned, actions = feat_automate.apply_recipe(raw, recipe)
            stem = path.stem
            cleaned.to_csv(out_dir / f"{stem}_cleaned.csv", index=False)
            log_lines = [f"{step}: {detail}" for step, detail in actions]
            (out_dir / f"{stem}_log.txt").write_text(
                "\n".join(log_lines), encoding="utf-8")
            results.append({"name": path.name, "rows_in": rows_in,
                            "rows_out": len(cleaned), "status": "OK"})
            print(f"{path.name}: {rows_in} -> {len(cleaned)} rows cleaned.")
        except Exception as e:  # noqa: BLE001 - one bad file must not stop the run
            results.append({"name": path.name, "rows_in": None,
                            "rows_out": None, "status": f"Failed: {e}"})
            print(f"{path.name}: FAILED — {e}")
    (out_dir / "morning_run_summary.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    return results


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="in_dir", default=str(here / "morning_in"),
                        help="Folder with the messy files (default: morning_in/)")
    parser.add_argument("--out", dest="out_dir", default=str(here / "morning_out"),
                        help="Folder for cleaned files (default: morning_out/)")
    parser.add_argument("--recipe", default=str(here / "morning_recipe.json"),
                        help="Recipe .json to clean with (default: morning_recipe.json)")
    args = parser.parse_args()
    results = run_morning(args.in_dir, args.out_dir, args.recipe)
    ok = sum(1 for r in results if r["status"] == "OK")
    print(f"Morning run done: {ok} of {len(results)} file(s) cleaned.")


if __name__ == "__main__":
    main()
