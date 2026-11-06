#!/usr/bin/env python3
"""Watch folder — Data Cleaner Studio (Group 3, v1.2).

Watches a folder for new CSV / Excel / JSON files, cleans each one with a
saved recipe, and writes a cleaned CSV plus a cleaning-log .txt into the
output folder. Every action is logged to the console and to watch_log.txt
in the output folder.

Usage:
    python watch_folder.py --watch DIR --out DIR --recipe recipe.json [--once]

--once processes the files already in the folder and exits. Without it the
script keeps watching: watchdog if it is installed, otherwise a plain
polling loop every 5 seconds.

Needs only plain python3 + pandas (+ watchdog if present). No Streamlit.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import engine  # noqa: E402

try:
    from feat_automate import recipe_from_json, to_engine_opts
except Exception:  # noqa: BLE001 - standalone fallback if feat_automate is absent
    _KEY_MAP = {
        "tidy_names": "tidy_columns", "strip": "strip_text",
        "drop_empty": "drop_empty", "fix_numbers": "fix_numbers",
        "parse_dates": "fix_dates", "fix_categories": "fix_categories",
        "drop_dupes": "drop_duplicates", "fill_missing": "fill_missing",
    }

    def recipe_from_json(text):
        data = json.loads(text)
        opts = data.get("clean_opts", {})
        unknown = sorted(set(opts) - set(_KEY_MAP))
        if unknown:
            raise ValueError(f"Unknown cleaning option(s): {', '.join(unknown)}")
        return data

    def to_engine_opts(clean_opts):
        return {_KEY_MAP[k]: bool(v) for k, v in clean_opts.items()
                if k in _KEY_MAP}

INPUT_SUFFIXES = {".csv", ".xlsx", ".xls", ".json", ".txt", ".tsv"}


def load_recipe(path):
    """Read and validate a recipe JSON file. Returns (engine_opts, name)."""
    text = Path(path).read_text(encoding="utf-8")
    recipe = recipe_from_json(text)
    return to_engine_opts(recipe.get("clean_opts", {})), recipe.get("name", "recipe")


def _setup_logging(out_dir):
    """Log to the console and to watch_log.txt in the output folder."""
    out_dir.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("watch_folder")
    log.setLevel(logging.INFO)
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    log.addHandler(console)
    file_handler = logging.FileHandler(out_dir / "watch_log.txt",
                                       encoding="utf-8")
    file_handler.setFormatter(fmt)
    log.addHandler(file_handler)
    return log


def process_file(path, out_dir, engine_opts, log):
    """Clean one file and write <stem>_cleaned.csv + <stem>_cleaning_log.txt.
    Returns True on success, False on failure (logged, never raises)."""
    try:
        raw = Path(path).read_bytes()
        df = engine.load_file(path.name, raw)
        rows_before = len(df)
        cleaned, actions = engine.clean(df, engine_opts)
    except Exception as e:  # noqa: BLE001 - a bad file must not kill the watch
        log.error("FAILED %s: %s", path.name, e)
        return False
    stem = Path(path).stem
    csv_out = out_dir / f"{stem}_cleaned.csv"
    log_out = out_dir / f"{stem}_cleaning_log.txt"
    cleaned.to_csv(csv_out, index=False)
    lines = [f"Source: {path.name}",
             f"Rows: {rows_before:,} -> {len(cleaned):,}",
             f"Columns: {len(df.columns)} -> {len(cleaned.columns)}", "",
             "What was cleaned:"]
    lines += [f"- {step}: {detail}" for step, detail in actions]
    log_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("CLEANED %s: %d -> %d rows, %d columns -> %s",
             path.name, rows_before, len(cleaned), len(cleaned.columns),
             csv_out.name)
    for step, detail in actions:
        log.info("    %s: %s", step, detail)
    return True


def _is_input_file(path):
    return (path.is_file() and path.suffix.lower() in INPUT_SUFFIXES
            and not path.name.startswith(".")
            and path.name != "watch_log.txt")


def process_existing(watch_dir, out_dir, engine_opts, log):
    """Clean every input file currently in the watch folder (sorted)."""
    found = sorted(p for p in Path(watch_dir).iterdir() if _is_input_file(p))
    if not found:
        log.info("No files to process in %s", watch_dir)
    for path in found:
        process_file(path, out_dir, engine_opts, log)
    return [p.name for p in found]


def watch_polling(watch_dir, out_dir, engine_opts, log, poll_seconds=5):
    """Fallback watcher: scan the folder every few seconds for new files."""
    seen = {p.name for p in Path(watch_dir).iterdir() if _is_input_file(p)}
    log.info("Watching %s (polling every %ds) — press Ctrl+C to stop.",
             watch_dir, poll_seconds)
    try:
        while True:
            time.sleep(poll_seconds)
            for path in sorted(Path(watch_dir).iterdir()):
                if _is_input_file(path) and path.name not in seen:
                    seen.add(path.name)
                    # Give a half-written upload a moment to finish.
                    time.sleep(1)
                    process_file(path, out_dir, engine_opts, log)
    except KeyboardInterrupt:
        log.info("Stopped watching %s", watch_dir)


def watch_watchdog(watch_dir, out_dir, engine_opts, log):
    """Watchdog-based watcher (used when the watchdog package is present)."""
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    class Handler(FileSystemEventHandler):
        def on_created(self, event):
            if event.is_directory:
                return
            path = Path(event.src_path)
            if not _is_input_file(path):
                return
            time.sleep(1)  # let the writer finish
            process_file(path, out_dir, engine_opts, log)

    observer = Observer()
    observer.schedule(Handler(), str(watch_dir), recursive=False)
    observer.start()
    log.info("Watching %s (watchdog) — press Ctrl+C to stop.", watch_dir)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Stopped watching %s", watch_dir)
    finally:
        observer.stop()
        observer.join()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Watch a folder, clean new files with a recipe.")
    parser.add_argument("--watch", required=True,
                        help="Folder to watch for new files")
    parser.add_argument("--out", required=True,
                        help="Folder for cleaned CSVs, logs and watch_log.txt")
    parser.add_argument("--recipe", required=True,
                        help="Recipe JSON file (clean_opts + fuzzy)")
    parser.add_argument("--once", action="store_true",
                        help="Process the files already in the folder, then exit")
    args = parser.parse_args(argv)

    watch_dir = Path(args.watch)
    out_dir = Path(args.out)
    if not watch_dir.is_dir():
        print(f"Watch folder not found: {watch_dir}", file=sys.stderr)
        return 2
    try:
        engine_opts, recipe_name = load_recipe(args.recipe)
    except (OSError, ValueError) as e:
        print(f"Could not load recipe '{args.recipe}': {e}", file=sys.stderr)
        return 2

    log = _setup_logging(out_dir)
    log.info("Watch folder started: watch=%s out=%s recipe='%s'",
             watch_dir, out_dir, recipe_name)

    if args.once:
        process_existing(watch_dir, out_dir, engine_opts, log)
        log.info("Done (--once).")
        return 0

    # Process anything already waiting, then keep watching.
    process_existing(watch_dir, out_dir, engine_opts, log)
    try:
        from watchdog.observers import Observer  # noqa: F401
        watch_watchdog(watch_dir, out_dir, engine_opts, log)
    except ImportError:
        log.info("watchdog not installed — falling back to polling.")
        watch_polling(watch_dir, out_dir, engine_opts, log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
