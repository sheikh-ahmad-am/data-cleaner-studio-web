"""Data Cleaner Studio — Group 3: repeat & automate (v1.2).

Recipes, undo snapshots, find-and-replace, templates, bulk cleaning, and
the render functions the app wires into its tabs.

Pure logic functions never call Streamlit; the render_* functions are thin
wrappers that take ``st`` first and only use widget keys starting with
``a_``. Widget keys and data keys are kept strictly separate — a widget
key is never reused to store data.

Option-key note: the app's checkboxes (and therefore this module's
recipes) use the keys tidy_names / strip / drop_empty / fix_numbers /
parse_dates / fix_categories / drop_dupes / fill_missing. engine.clean
expects tidy_columns / strip_text / drop_empty / fix_numbers / fix_dates /
fix_categories / drop_duplicates / fill_missing, so every recipe is
translated through OPT_KEY_MAP before it reaches the engine. Passing the
app keys straight to engine.clean would silently run every step.
"""

import copy
import json
import re

import pandas as pd

import engine

# ------------------------------------------------------------ option keys ---
# Canonical recipe keys (the app's checkbox names) -> engine.clean keys.
OPT_KEY_MAP = {
    "tidy_names": "tidy_columns",
    "strip": "strip_text",
    "drop_empty": "drop_empty",
    "fix_numbers": "fix_numbers",
    "parse_dates": "fix_dates",
    "fix_categories": "fix_categories",
    "drop_dupes": "drop_duplicates",
    "fill_missing": "fill_missing",
}
CLEAN_OPT_KEYS = list(OPT_KEY_MAP)
DEFAULT_CLEAN_OPTS = {k: True for k in CLEAN_OPT_KEYS}

MAX_SNAPSHOTS = 10


def validate_clean_opts(clean_opts):
    """Check a clean_opts dict and return a normalised copy (all 8 keys,
    booleans only). Missing keys default to True. Raises ValueError."""
    if not isinstance(clean_opts, dict):
        raise ValueError("clean_opts must be a dict of option name -> bool")
    unknown = sorted(set(clean_opts) - set(CLEAN_OPT_KEYS))
    if unknown:
        raise ValueError(f"Unknown cleaning option(s): {', '.join(unknown)}")
    out = {}
    for key in CLEAN_OPT_KEYS:
        value = clean_opts.get(key, True)
        if not isinstance(value, bool):
            raise ValueError(f"Cleaning option '{key}' must be true/false, "
                             f"got {value!r}")
        out[key] = value
    return out


def to_engine_opts(clean_opts):
    """Translate canonical recipe keys into the keys engine.clean reads."""
    return {OPT_KEY_MAP[k]: v for k, v in validate_clean_opts(clean_opts).items()}


# --------------------------------------------------------------- recipes ----
def save_recipe(clean_opts, fuzzy_maps, name):
    """Build a recipe dict from cleaning options and fuzzy mappings.

    clean_opts: {8 booleans}; fuzzy_maps: {column: {old_value: new_value}};
    name: a short human label. Returns the recipe dict."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Recipe needs a non-empty name")
    if fuzzy_maps is None:
        fuzzy_maps = {}
    if not isinstance(fuzzy_maps, dict):
        raise ValueError("fuzzy_maps must be {column: {old_value: new_value}}")
    clean_fuzzy = {}
    for col, mapping in fuzzy_maps.items():
        if not isinstance(col, str) or not col:
            raise ValueError(f"Fuzzy column name must be a non-empty string, got {col!r}")
        if not isinstance(mapping, dict):
            raise ValueError(f"Fuzzy mapping for column '{col}' must be a dict")
        clean_fuzzy[col] = {str(k): str(v) for k, v in mapping.items()}
    return {
        "name": name.strip(),
        "clean_opts": validate_clean_opts(clean_opts),
        "fuzzy": clean_fuzzy,
    }


def apply_recipe(df, recipe):
    """Run a recipe on a DataFrame: engine.clean with the recipe's options,
    then the recipe's fuzzy mappings. Returns (cleaned_df, actions)."""
    if not isinstance(recipe, dict):
        raise ValueError("Recipe must be a dict")
    clean_opts = validate_clean_opts(recipe.get("clean_opts", {}))
    cleaned, actions = engine.clean(df, to_engine_opts(clean_opts))
    fuzzy = recipe.get("fuzzy") or {}
    if not isinstance(fuzzy, dict):
        raise ValueError("Recipe 'fuzzy' must be {column: {old: new}}")
    for column, mapping in fuzzy.items():
        if column not in cleaned.columns:
            continue
        if not mapping:
            continue
        cleaned = engine.apply_fuzzy(cleaned, column, dict(mapping))
        actions = actions + [(f"Recipe fuzzy fix: {column}",
                              f"{len(mapping)} value(s) standardised")]
    return cleaned, actions


def recipe_to_json(recipe):
    """Serialise a recipe to a JSON string (validated first)."""
    if not isinstance(recipe, dict):
        raise ValueError("Recipe must be a dict")
    save_recipe(recipe.get("clean_opts", {}), recipe.get("fuzzy", {}),
                recipe.get("name", ""))
    return json.dumps(recipe, indent=2, sort_keys=True)


def recipe_from_json(text):
    """Parse a recipe from JSON. Validates keys and types; raises
    ValueError on any bad input."""
    if isinstance(text, (bytes, bytearray)):
        text = text.decode("utf-8")
    if not isinstance(text, str):
        raise ValueError("Recipe JSON must be text")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("Recipe JSON must be an object")
    unknown = sorted(set(data) - {"name", "clean_opts", "fuzzy"})
    if unknown:
        raise ValueError(f"Unknown recipe key(s): {', '.join(unknown)}")
    return save_recipe(data.get("clean_opts", {}), data.get("fuzzy", {}),
                       data.get("name", ""))


# ------------------------------------------------------ undo + snapshots ---
def push_snapshot(session_state, label):
    """Save the current clean/actions/kpis (real dataframe copies) into
    session_state['a_snaps'] with the given label. Keeps at most 10
    snapshots; the oldest is dropped. Returns the label used."""
    snaps = session_state.get("a_snaps") or []
    if not isinstance(snaps, list):
        snaps = []
    label = (label or "").strip() or f"Snapshot {len(snaps) + 1}"
    clean = session_state.get("clean")
    raw = session_state.get("raw")
    snaps.append({
        "label": label,
        "clean": clean.copy(deep=True) if isinstance(clean, pd.DataFrame) else None,
        "actions": copy.deepcopy(session_state.get("actions")),
        "kpis": copy.deepcopy(session_state.get("kpis")),
        "raw_rows": len(raw) if isinstance(raw, pd.DataFrame) else None,
    })
    session_state["a_snaps"] = snaps[-MAX_SNAPSHOTS:]
    return label


def undo(session_state):
    """Restore the most recent snapshot into clean/actions/kpis and remove
    it from the list. Returns the snapshot's label, or None if there is
    nothing to undo."""
    snaps = session_state.get("a_snaps") or []
    if not snaps:
        return None
    snap = snaps.pop()
    session_state["a_snaps"] = snaps
    if snap["clean"] is not None:
        session_state["clean"] = snap["clean"].copy(deep=True)
    else:
        session_state["clean"] = None
    session_state["actions"] = copy.deepcopy(snap["actions"])
    session_state["kpis"] = copy.deepcopy(snap["kpis"])
    return snap["label"]


def list_snapshots(session_state):
    """Labels of the stored snapshots, oldest first."""
    snaps = session_state.get("a_snaps") or []
    return [s["label"] for s in snaps]


# --------------------------------------------------------- find & replace ---
def find_replace(df, column, find, replace, match_case=True, use_regex=False):
    """Replace text in one text column. Returns (new_df, count_replaced)
    where count is the number of cells that actually changed. The input
    frame is never modified."""
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not in the data")
    if not isinstance(find, str) or find == "":
        raise ValueError("Find text must be a non-empty string")
    if not isinstance(replace, str):
        raise ValueError("Replacement text must be a string")
    s = df[column]
    if not (pd.api.types.is_object_dtype(s)
            or pd.api.types.is_string_dtype(s)):
        raise ValueError(f"Column '{column}' is not a text column")
    mask = s.notna()
    vals = s[mask].astype(str)
    if use_regex:
        try:
            re.compile(find)
        except re.error as e:
            raise ValueError(f"Invalid regular expression: {e}") from e
        flags = 0 if match_case else re.IGNORECASE
        new_vals = vals.str.replace(find, replace, regex=True, flags=flags)
    elif match_case:
        new_vals = vals.str.replace(find, replace, regex=False)
    else:
        new_vals = vals.str.replace(re.escape(find), replace, regex=True,
                                    flags=re.IGNORECASE)
    changed = new_vals != vals
    count = int(changed.sum())
    out = df.copy()
    changed_idx = vals.index[changed]
    if len(changed_idx):
        out.loc[changed_idx, column] = new_vals.loc[changed_idx]
    return out, count


# --------------------------------------------------------------- templates --
TEMPLATES = {
    "sales": {
        "description": "Shop / online-store sales: messy dates, currency "
                       "prices, mixed-case categories, duplicate orders.",
        "clean_opts": dict(DEFAULT_CLEAN_OPTS),
        "suggested_kpis": ["unit_price", "quantity"],
    },
    "attendance": {
        "description": "Class / staff attendance: mixed date formats, "
                       "blank statuses, mixed-case names and statuses, "
                       "duplicate rows.",
        "clean_opts": dict(DEFAULT_CLEAN_OPTS),
        "suggested_kpis": ["days_present", "status"],
    },
    "inventory": {
        "description": "Stock list: mixed-case categories and warehouses, "
                       "prices with currency symbols, blank quantities, "
                       "duplicate items.",
        "clean_opts": dict(DEFAULT_CLEAN_OPTS),
        "suggested_kpis": ["quantity", "unit_price"],
    },
}

# Sample files the templates can load (in sample_data/).
TEMPLATE_SAMPLES = {
    "sales": "messy_sales.csv",
    "attendance": "attendance_sample.csv",
    "inventory": "inventory_sample.csv",
}


def apply_template(df, template_name):
    """Clean a frame with one of the built-in templates. Returns
    (cleaned_df, actions). Raises ValueError for an unknown template."""
    if template_name not in TEMPLATES:
        raise ValueError(
            f"Unknown template '{template_name}' "
            f"(choose from: {', '.join(TEMPLATES)})")
    template = TEMPLATES[template_name]
    recipe = save_recipe(template["clean_opts"], {}, template_name)
    return apply_recipe(df, recipe)


# ------------------------------------------------------------------- bulk ---
def bulk_clean(files, recipe):
    """Clean many files with one recipe. files is a list of
    (name, raw_bytes). Returns one result dict per file:
    {name, cleaned_df, actions, error, rows_in, rows_out}. One bad file
    never stops the others."""
    recipe = recipe_from_json(recipe_to_json(recipe))
    results = []
    for name, raw_bytes in files:
        try:
            df = engine.load_file(name, raw_bytes)
            rows_in = len(df)
            cleaned, actions = apply_recipe(df, recipe)
            results.append({"name": name, "cleaned_df": cleaned,
                            "actions": actions, "error": None,
                            "rows_in": rows_in, "rows_out": len(cleaned)})
        except Exception as e:  # noqa: BLE001 - one bad file must not stop the run
            results.append({"name": name, "cleaned_df": None, "actions": [],
                            "error": str(e), "rows_in": None, "rows_out": None})
    return results


def bulk_summary(results):
    """One row per file: name, rows_in, rows_out, status ('OK' or
    'Failed: <error>')."""
    rows = []
    for r in results:
        rows.append({
            "name": r["name"],
            "rows_in": r["rows_in"],
            "rows_out": r["rows_out"],
            "status": "OK" if r["error"] is None else f"Failed: {r['error']}",
        })
    return pd.DataFrame(rows, columns=["name", "rows_in", "rows_out", "status"])


# --------------------------------------------------------- render helpers ---
def _current_fuzzy_maps(st):
    """Fuzzy mappings from the app's current fuzzy state, if any:
    {column: {old_value: canonical}}."""
    groups = st.session_state.get("fuzzy_groups")
    col = st.session_state.get("fuzzy_col_used")
    if not groups or not col:
        return {}
    mapping = {}
    for g in groups:
        for value, _ in g["members"][1:]:
            mapping[value] = g["canonical"]
    return {col: mapping} if mapping else {}


def _saved_recipes(st):
    recipes = st.session_state.get("a_recipes")
    if not isinstance(recipes, list):
        recipes = []
        st.session_state["a_recipes"] = recipes
    return recipes


# ---------------------------------------------------------- render funcs ----
def render_recipes(st, df):
    """Save the current cleaning options (+ any fuzzy merges) as a named
    recipe, or apply a saved recipe to ``df``. Returns
    (new_df_or_None, new_actions) — the caller writes them into session
    state. Reads st.session_state['clean_opts'] and the fuzzy state;
    writes st.session_state['a_recipes']."""
    st.subheader("Cleaning recipes")
    st.write("Save the fixes you use again and again, then replay them on "
             "the next file in one click.")
    opts = st.session_state.get("clean_opts") or dict(DEFAULT_CLEAN_OPTS)
    fuzzy_maps = _current_fuzzy_maps(st)

    c1, c2 = st.columns([2, 1])
    name = c1.text_input("Recipe name", key="a_recipe_name",
                         placeholder="e.g. Monthly sales cleanup")
    if c2.button("Save recipe", key="a_recipe_save"):
        if not name.strip():
            st.warning("Give the recipe a name first.")
        else:
            try:
                recipe = save_recipe(opts, fuzzy_maps, name)
            except ValueError as e:
                st.error(str(e))
            else:
                recipes = _saved_recipes(st)
                recipes[:] = [r for r in recipes if r["name"] != recipe["name"]]
                recipes.append(recipe)
                st.success(f"Saved recipe '{recipe['name']}' "
                           f"({len(fuzzy_maps)} fuzzy column(s) included).")

    recipes = _saved_recipes(st)
    if recipes:
        names = [r["name"] for r in recipes]
        picked = st.selectbox("Saved recipes", names, key="a_recipe_select")
        c1, c2 = st.columns(2)
        if c1.button("Apply recipe", type="primary", key="a_recipe_apply"):
            recipe = next(r for r in recipes if r["name"] == picked)
            try:
                cleaned, actions = apply_recipe(df, recipe)
            except Exception as e:  # noqa: BLE001
                st.error(f"Could not apply recipe: {e}")
                return None, None
            st.success(f"Applied recipe '{picked}': "
                       f"{len(df):,} -> {len(cleaned):,} rows.")
            return cleaned, actions
        recipe = next(r for r in recipes if r["name"] == picked)
        c2.download_button("Download recipe (.json)",
                           recipe_to_json(recipe),
                           file_name=f"{picked.replace(' ', '_')}_recipe.json",
                           mime="application/json", key="a_recipe_dl")
    else:
        st.info("No saved recipes yet — save one above.")

    uploaded = st.file_uploader("Load a recipe (.json)", type=["json"],
                                key="a_recipe_upload")
    if uploaded is not None:
        try:
            recipe = recipe_from_json(uploaded.getvalue().decode("utf-8"))
        except ValueError as e:
            st.error(f"That recipe file is not valid: {e}")
        else:
            recipes = _saved_recipes(st)
            recipes[:] = [r for r in recipes if r["name"] != recipe["name"]]
            recipes.append(recipe)
            st.success(f"Loaded recipe '{recipe['name']}'.")
    return None, None


def render_undo(st):
    """Snapshot / undo controls. Reads and writes session state
    clean/actions/kpis and the snapshot list 'a_snaps'. Returns the label
    that was just undone, or None."""
    st.subheader("Undo")
    st.write("Save a snapshot before a risky step — one click takes you "
             "back to it.")
    label = st.text_input("Snapshot label", key="a_snap_label",
                          placeholder="e.g. Before fuzzy merge")
    if st.button("Save snapshot", key="a_snap_save"):
        used = push_snapshot(st.session_state, label)
        st.success(f"Snapshot saved: '{used}'.")
    labels = list_snapshots(st.session_state)
    if labels:
        st.write("Snapshots (newest last): " + ", ".join(
            f"'{lab}'" for lab in labels))
        if st.button("Undo last snapshot", key="a_snap_undo"):
            undone = undo(st.session_state)
            if undone is not None:
                st.success(f"Undid to snapshot '{undone}'.")
                return undone
    else:
        st.info("No snapshots yet.")
    return None


def render_find_replace(st, df):
    """Find-and-replace on one text column of ``df``. Returns
    (new_df_or_None, new_actions) — the caller writes them into session
    state. Reads nothing else from session state."""
    st.subheader("Find and replace")
    st.write("Fix a spelling or a code across one column — the count tells "
             "you exactly how many cells changed.")
    text_cols = [c for c in df.columns
                 if pd.api.types.is_object_dtype(df[c])
                 or pd.api.types.is_string_dtype(df[c])]
    if not text_cols:
        st.info("No text columns to search in this data.")
        return None, None
    c1, c2 = st.columns(2)
    column = c1.selectbox("Column", text_cols, key="a_fr_col")
    find = c2.text_input("Find", key="a_fr_find", placeholder="e.g. Dehli")
    replace = st.text_input("Replace with", key="a_fr_replace",
                            placeholder="e.g. Delhi")
    c1, c2 = st.columns(2)
    match_case = c1.checkbox("Match case", value=True, key="a_fr_case")
    use_regex = c2.checkbox("Use regular expression", value=False,
                            key="a_fr_regex",
                            help="Treat 'Find' as a pattern, e.g. \\s+ for spaces.")
    if st.button("Replace", type="primary", key="a_fr_apply"):
        if not find:
            st.warning("Type something to find first.")
            return None, None
        try:
            new_df, count = find_replace(df, column, find, replace,
                                         match_case=match_case,
                                         use_regex=use_regex)
        except ValueError as e:
            st.error(str(e))
            return None, None
        actions = [(f"Find and replace: {column}",
                    f"{count} cell(s) changed: '{find}' -> '{replace}'")]
        if count:
            st.success(f"Changed {count} cell(s) in '{column}'.")
        else:
            st.info(f"No cells in '{column}' matched '{find}'.")
        return new_df, actions
    return None, None


def render_templates(st):
    """Template picker. Applies the chosen template to the raw data in
    session state and returns (cleaned_df_or_None, actions). Also offers
    to load the template's messy sample file, which sets session state
    raw/source_name/source_kind and clears clean/actions/kpis."""
    st.subheader("Templates")
    st.write("One-click cleaning for the three file shapes people bring in "
             "most often. Pick one, or load its messy sample to try it.")
    names = list(TEMPLATES)
    picked = st.selectbox("Template", names, key="a_template_select",
                          format_func=lambda n: f"{n.title()} — "
                          f"{TEMPLATES[n]['description']}")
    template = TEMPLATES[picked]
    st.write(f"**Suggested KPIs:** {', '.join(template['suggested_kpis'])}")
    sample_file = TEMPLATE_SAMPLES[picked]
    c1, c2 = st.columns(2)
    if c1.button(f"Load {picked} sample", key="a_template_load"):
        try:
            from pathlib import Path
            path = Path(__file__).resolve().parent / "sample_data" / sample_file
            raw = engine.load_file(sample_file, path.read_bytes())
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not load the sample: {e}")
            return None, None
        st.session_state["raw"] = raw
        st.session_state["clean"] = None
        st.session_state["actions"] = None
        st.session_state["kpis"] = None
        st.session_state["source_name"] = f"{sample_file} (sample)"
        st.session_state["source_kind"] = "sample"
        st.session_state["last_upload"] = None
        st.success(f"Loaded {sample_file} — now apply the template.")
        st.rerun()
    raw = st.session_state.get("raw")
    if raw is None:
        st.info("Load some data first, then apply the template.")
        return None, None
    if c2.button("Apply template", type="primary", key="a_template_apply"):
        cleaned, actions = apply_template(raw, picked)
        st.success(f"Template '{picked}' applied: "
                   f"{len(raw):,} -> {len(cleaned):,} rows.")
        return cleaned, actions
    return None, None


def render_bulk(st):
    """Bulk cleaning: drop in several files, pick a saved recipe (or the
    default all-fixes recipe), clean them all. Results live in
    st.session_state['a_bulk_results']; the summary is shown in the app.
    Returns None."""
    st.subheader("Bulk clean")
    st.write("Clean a whole folder's worth of files at once — one bad file "
             "is reported and skipped, the rest still get cleaned.")
    files = st.file_uploader("Files to clean", type=["csv", "xlsx", "xls", "json"],
                             accept_multiple_files=True, key="a_bulk_files")
    recipes = _saved_recipes(st)
    options = ["Default — all fixes on"] + [r["name"] for r in recipes]
    picked = st.selectbox("Recipe", options, key="a_bulk_recipe")
    if st.button("Clean all files", type="primary", key="a_bulk_run"):
        if not files:
            st.warning("Add at least one file first.")
            return None
        if picked == options[0]:
            recipe = save_recipe(dict(DEFAULT_CLEAN_OPTS), {}, "default")
        else:
            recipe = next(r for r in recipes if r["name"] == picked)
        inputs = [(f.name, f.getvalue()) for f in files]
        results = bulk_clean(inputs, recipe)
        st.session_state["a_bulk_results"] = results
        st.success(f"Cleaned {sum(1 for r in results if r['error'] is None)} "
                   f"of {len(results)} file(s).")
    results = st.session_state.get("a_bulk_results")
    if results:
        st.dataframe(bulk_summary(results), width="stretch")
        for i, r in enumerate(results):
            if r["error"] is None:
                st.download_button(
                    f"Download cleaned {r['name']}",
                    r["cleaned_df"].to_csv(index=False).encode("utf-8"),
                    file_name=f"{r['name'].rsplit('.', 1)[0]}_cleaned.csv",
                    key=f"a_bulk_dl_{i}")
            else:
                st.error(f"{r['name']}: {r['error']}")
    return None
