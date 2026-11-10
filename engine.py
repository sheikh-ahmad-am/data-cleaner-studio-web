"""Data Cleaner Studio — engine.

Load messy CSV / Excel / JSON / Google Sheets, profile it, clean it,
compute KPIs, and export a cleaned workbook. Pure pandas — no UI code here,
so the same engine runs in the desktop app and in tests.

Cleaning steps (all reported, nothing silent):
  1. Tidy column names (strip, lower-case, spaces -> underscores)
  2. Strip extra spaces inside text cells
  3. Drop exact duplicate rows
  4. Drop columns / rows that are 100% empty
  5. Numbers: strip currency symbols, commas and % signs, then convert
  6. Dates: parse mixed formats (01/02/2024, 2024-02-01, 1 Feb 2024, ...)
  7. Categories: one consistent case (Title Case, acronyms kept: USB stays USB)
  8. Missing values: numbers -> median (rounded to a whole number for
     integer-like columns), text -> "Unknown", dates left blank
  9. Dates: a column with no time component stays date-only (YYYY-MM-DD)
     wherever the engine shows it — no midnight "00:00:00" is added.
"""

import io
import json
import re
import urllib.request

import numpy as np
import pandas as pd

MONEY_CHARS = re.compile(r"[^0-9.\-]")


# ======================================================= display numbers =====
def format_number(value, kind: str = "number") -> str:
    """THE one number-display rule for this engine (KPIs, summaries,
    report text): thousands separators everywhere; money 2 decimals,
    counts / integers 0 decimals, percentages 1 decimal, other numbers
    1 decimal. kind: "money" | "count" | "percent" | "number".
    Non-finite values (NaN / inf) show as an em dash, never "nan"."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if v != v or v in (float("inf"), float("-inf")):
        return "—"
    if kind == "money":
        return f"{v:,.2f}"
    if kind == "count":
        return f"{v:,.0f}"
    if kind == "percent":
        return f"{v:,.1f}%"
    if kind == "number":
        return f"{v:,.1f}"
    raise ValueError(f"Unknown number kind: {kind} "
                     "(money / count / percent / number)")


# ====================================================== case normalising =====
_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


# Small known-acronym set for _smart_title. A token is kept exactly
# as written only when it is all-caps IN THE SOURCE and it is one of
# these (USB, SKU, ID, ...). A bare "any all-caps word of <= 4 letters
# stays" rule would also keep HOME, LOVE or SALE as separate
# categories — the cleaner would stop unifying case (the sample's
# HOME / Home / home would stay split, 5 categories instead of 4).
# So the acronym behaviour is a small list, not a length rule.
_ACRONYMS = frozenset({
    "USB", "SKU", "ID", "TV", "PC", "CPU", "GPU", "RAM", "SSD", "HDD",
    "LED", "LCD", "HDMI", "PDF", "URL", "API", "VAT", "GST", "MRP",
    "SIM", "GPS", "EMI", "UPI", "PO", "DC",
})


def _title_match(m) -> str:
    """One word inside _smart_title: an all-caps acronym from the small
    set above stays exactly as written (USB Hub stays USB Hub); anything
    else title-cases (ELECTRONICS -> Electronics, HOME -> Home, so
    categories still unify). Only the first letter is upper-cased —
    str.title() would turn "don't" into "Don'T", because it treats the
    apostrophe as a word boundary."""
    word = m.group(0)
    if word.isupper() and word in _ACRONYMS:
        return word
    return word[:1].upper() + word[1:].lower()


def _smart_title(value) -> str:
    """Title Case that keeps acronyms: 'USB Hub' stays 'USB Hub'
    (plain .title() would make it 'Usb Hub'), while 'ELECTRONICS'
    still becomes 'Electronics' and 'HOME' becomes 'Home', so
    categories unify. Only acronyms from the small _ACRONYMS set are
    kept — see _title_match for why a bare length rule would break
    unification. Apostrophes are kept inside the word, so "don't" ->
    "Don't", not "Don'T"."""
    return _WORD_RE.sub(_title_match, str(value))


# ===================================================== integer-like fills =====
def _is_integer_like(s: pd.Series) -> bool:
    """True when every non-empty value in a numeric series is a whole
    number (2.0 counts; 2.5 does not). An empty series is not
    integer-like — there is nothing to judge by."""
    vals = pd.to_numeric(s, errors="coerce").dropna()
    if len(vals) == 0:
        return False
    return bool(((vals == np.floor(vals)) & np.isfinite(vals)).all())


def _round_half_away(median: float) -> int:
    """Round a median to the nearest whole number, halves away from
    zero (2.5 -> 3, -2.5 -> -3) — the fill a person expects, not
    banker's rounding (round(2.5) == 2 in Python)."""
    if median >= 0:
        return int(np.floor(median + 0.5))
    return int(np.ceil(median - 0.5))


def _median_fill_value(s: pd.Series):
    """(fill_value, is_integer_like) for a numeric column: the median,
    rounded to a whole number when the column is integer-like, so a
    filled Quantity is 3, never 2.5 — and a column total stays whole."""
    median = float(pd.to_numeric(s, errors="coerce").median())
    if _is_integer_like(s):
        return _round_half_away(median), True
    return median, False


def _fill_numeric_column(s: pd.Series, fill_value, integer_like: bool) -> pd.Series:
    """Fill a numeric column's missing values, then — when the column
    is integer-like and nothing is missing any more — store it as
    int64, so totals and samples read as whole numbers (208, not
    208.0). Never casts when a NaN survives the fill."""
    out = s.fillna(fill_value)
    if integer_like and int(out.isna().sum()) == 0:
        try:
            return out.astype("int64")
        except (ValueError, OverflowError):
            return out
    return out


# ======================================================= revenue finding =====
_QTY_TOKENS = {"quantity", "qty", "units", "count"}
_PRICE_TOKENS = {"price", "cost", "rate", "amount"}


def _name_tokens(col) -> list:
    return str(col).lower().replace("-", "_").split("_")


def _is_qty_like(col) -> bool:
    """A quantity-like column name: quantity / qty / units / count.
    Names that already aggregate (total_quantity) do not count."""
    toks = _name_tokens(col)
    return "total" not in toks and any(t in _QTY_TOKENS for t in toks)


def _is_price_like(col) -> bool:
    """A price-like column name: price / cost / rate / amount
    (unit_price matches on its 'price' token). Names that already
    aggregate (total_amount) do not count."""
    toks = _name_tokens(col)
    return "total" not in toks and any(t in _PRICE_TOKENS for t in toks)


def _find_revenue_pair(df: pd.DataFrame):
    """(quantity_col, price_col) when the frame has exactly ONE
    quantity-like numeric column AND exactly ONE price-like numeric
    column, and they are different columns — the only case where
    sum(quantity x price) is unambiguously revenue. Anything else
    (no pair, two quantity columns, a total_* column) returns
    (None, None) and the KPIs fall back to honest plain sums."""
    num = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    qty = [c for c in num if _is_qty_like(c)]
    price = [c for c in num if _is_price_like(c)]
    if len(qty) == 1 and len(price) == 1 and qty[0] != price[0]:
        return qty[0], price[0]
    return None, None


def _display_sample(value) -> str:
    """A sample value for profile(): a date with no time component
    shows as YYYY-MM-DD, never '2026-06-13 00:00:00'."""
    if isinstance(value, pd.Timestamp):
        if (value.hour, value.minute, value.second,
                value.microsecond) == (0, 0, 0, 0):
            return value.strftime("%Y-%m-%d")
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)


# ============================================================== loading =====
def _read_csv_bytes(raw: bytes) -> pd.DataFrame:
    """CSV with auto delimiter sniffing; falls back to latin-1 if utf-8 fails."""
    for enc in ("utf-8", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(raw), sep=None, engine="python", encoding=enc)
        except Exception:
            continue
    return pd.read_csv(io.BytesIO(raw), encoding="latin-1")


def load_file(name: str, raw: bytes) -> pd.DataFrame:
    """Load a CSV / Excel / JSON file from raw bytes. Returns a DataFrame.
    Empty and whitespace-only strings become missing values, so a JSON file
    (where blanks arrive as "" instead of null) behaves exactly like a CSV."""
    lname = name.lower()
    if lname.endswith((".csv", ".txt", ".tsv")):
        df = _read_csv_bytes(raw)
    elif lname.endswith((".xlsx", ".xls")):
        xls = pd.ExcelFile(io.BytesIO(raw))
        df = pd.read_excel(xls, sheet_name=xls.sheet_names[0])
    elif lname.endswith(".json"):
        try:
            df = pd.read_json(io.BytesIO(raw))
        except ValueError:
            data = json.loads(raw.decode("utf-8", errors="replace"))
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        df = pd.json_normalize(v)
                        break
                else:
                    df = pd.json_normalize(data)
            else:
                df = pd.json_normalize(data)
    else:
        raise ValueError(f"Unsupported file type: {name} (use .csv, .xlsx, .json)")
    return df.replace(r"^\s*$", np.nan, regex=True)


def sheets_url_to_csv(url: str) -> str:
    """Turn a Google Sheets link into its public CSV export link."""
    m = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if not m:
        raise ValueError("That does not look like a Google Sheets link.")
    return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv"


def load_sheets_url(url: str) -> pd.DataFrame:
    """Load a Google Sheet shared as 'Anyone with the link can view'."""
    csv_url = sheets_url_to_csv(url)
    req = urllib.request.Request(csv_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return _read_csv_bytes(r.read())


# ============================================================= profiling =====
def _looks_numeric(s: pd.Series) -> bool:
    """True if 80%+ of the non-empty values are numbers, allowing a currency
    prefix (₹ $ € £ Rs. INR), commas and a % sign. ID columns like ORD-1001
    do NOT count — stripping their letters would fake a number."""
    vals = s.dropna().astype(object).astype(str).str.strip()
    vals = vals[vals != ""]
    if len(vals) == 0:
        return False
    v = vals.str.replace(r"^(₹|\$|€|£|Rs\.?|INR)\s*", "", regex=True, case=False)
    v = v.str.replace(",", "", regex=False).str.replace(r"%$", "", regex=True).str.strip()
    return bool(v.str.match(r"^-?\d+(\.\d+)?$").mean() >= 0.8)


def _looks_date(s: pd.Series) -> bool:
    """True if 80%+ of the non-empty values parse as dates."""
    vals = s.dropna().astype(object).astype(str).str.strip()
    vals = vals[vals != ""]
    if len(vals) == 0:
        return False
    parsed = pd.to_datetime(vals, errors="coerce", format="mixed")
    return parsed.notna().mean() >= 0.8


def detect_kind(s: pd.Series) -> str:
    """number / date / category / text — guessed from the values themselves."""
    if _looks_numeric(s):
        return "number"
    if _looks_date(s):
        return "date"
    nunique = s.nunique(dropna=True)
    if 1 < nunique <= 30:
        return "category"
    return "text"


def normalize_text_values(s: pd.Series) -> pd.Series:
    """Text values with surrounding whitespace stripped and internal
    whitespace runs collapsed to one space — the ONE counting rule
    shared by profile(), profile_csv_chunked(), the data dictionary
    and search: "  Aarav Sharma " counts as "Aarav Sharma", so the
    profile's top values, the unique count and a search for the name
    all agree. Non-text columns pass through unchanged (only their
    missing values are dropped). Case is preserved — this rule is
    about whitespace, not case."""
    if pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s):
        return (s.dropna().astype(object).astype(str)
                .str.strip().str.replace(r"\s+", " ", regex=True))
    return s.dropna()


def profile(df: pd.DataFrame) -> list:
    """One row per column: name, guessed type, missing %, unique count, sample."""
    rows = []
    for col in df.columns:
        s = df[col]
        rows.append({
            "column": col,
            "type": detect_kind(s),
            "missing": int(s.isna().sum()),
            "missing_pct": round(100 * s.isna().mean(), 1),
            "unique": int(normalize_text_values(s).nunique()),
            "sample": _display_sample(s.dropna().iloc[0]) if s.notna().any() else "",
        })
    return rows


# ============================================================== cleaning =====
def clean(df: pd.DataFrame, options: dict | None = None) -> tuple:
    """Clean the data. Returns (cleaned_df, actions) where actions is a list
    of (step, detail) pairs describing everything that changed."""
    opts = {
        "tidy_columns": True, "strip_text": True, "drop_duplicates": True,
        "drop_empty": True, "fix_numbers": True, "fix_dates": True,
        "fix_categories": True, "fill_missing": True,
    }
    if options:
        opts.update(options)
    actions = []
    out = df.copy()
    rows_before = len(out)

    if opts["tidy_columns"]:
        new_cols = [re.sub(r"[^0-9a-z_]+", "_", c.strip().lower().replace(" ", "_")).strip("_")
                    for c in out.columns]
        changed = sum(1 for a, b in zip(out.columns, new_cols) if a != b)
        out.columns = new_cols
        if changed:
            actions.append(("Tidy column names", f"{changed} column(s) renamed"))

    if opts["strip_text"]:
        n = 0
        for col in out.columns:
            if out[col].dtype == object or str(out[col].dtype) == "str":
                before = out[col].astype(object).astype(str)
                after = out[col].astype(object).where(
                    out[col].isna(), out[col].astype(object).astype(str).str.strip())
                n += int((before != after.astype(str)).sum())
                out[col] = after
        if n:
            actions.append(("Strip extra spaces", f"{n} cell(s) trimmed"))

    if opts["drop_empty"]:
        empty_cols = [c for c in out.columns if out[c].isna().all()]
        if empty_cols:
            out = out.drop(columns=empty_cols)
            actions.append(("Drop empty columns", f"{len(empty_cols)}: {', '.join(empty_cols)}"))
        empty_rows = int(out.isna().all(axis=1).sum())
        if empty_rows:
            out = out[out.notna().any(axis=1)]
            actions.append(("Drop empty rows", f"{empty_rows} row(s) removed"))

    kinds = {row["column"]: row["type"] for row in profile(out)}

    if opts["fix_numbers"]:
        for col, kind in kinds.items():
            if kind == "number" and col in out.columns:
                raw = out[col].astype(object).astype(str).str.strip()
                cleaned = raw.str.replace(r"^(₹|\$|€|£|Rs\.?|INR)\s*", "", regex=True, case=False)
                cleaned = cleaned.str.replace(",", "", regex=False).str.replace(r"%$", "", regex=True).str.strip()
                converted = pd.to_numeric(cleaned, errors="coerce")
                n_fixed = int(((raw != cleaned) & converted.notna()).sum())
                out[col] = converted
                if n_fixed:
                    actions.append((f"Fix numbers: {col}", f"{n_fixed} value(s) cleaned (₹ $ , % removed)"))

    if opts["fix_dates"]:
        for col, kind in kinds.items():
            if kind == "date" and col in out.columns:
                parsed = pd.to_datetime(out[col].astype(object).astype(str),
                                        errors="coerce", format="mixed")
                n_fixed = int(parsed.notna().sum())
                out[col] = parsed
                actions.append((f"Parse dates: {col}", f"{n_fixed} value(s) parsed as dates"))

    if opts["fix_categories"]:
        for col, kind in kinds.items():
            if kind == "category" and col in out.columns:
                before = out[col].astype(object).astype(str)
                out[col] = out[col].astype(object).where(
                    out[col].isna(), out[col].astype(object).astype(str).str.strip()
                    .str.replace(_WORD_RE, _title_match, regex=True))
                n_fixed = int((before != out[col].astype(object).astype(str)).sum())
                if n_fixed:
                    actions.append((f"Fix categories: {col}", f"{n_fixed} value(s) set to one case"))

    if opts["drop_duplicates"]:
        dupes = int(out.duplicated().sum())
        if dupes:
            out = out.drop_duplicates().reset_index(drop=True)
            actions.append(("Drop duplicate rows", f"{dupes} row(s) removed"))

    if opts["fill_missing"]:
        for col in out.columns:
            missing = int(out[col].isna().sum())
            if missing == 0:
                continue
            if pd.api.types.is_numeric_dtype(out[col]):
                fill_value, integer_like = _median_fill_value(out[col])
                out[col] = _fill_numeric_column(out[col], fill_value, integer_like)
                actions.append((f"Fill missing: {col}",
                                f"{missing} filled with median"
                                + (" (rounded to a whole number)"
                                   if integer_like else "")))
            elif pd.api.types.is_datetime64_any_dtype(out[col]):
                actions.append((f"Missing left blank: {col}", f"{missing} date(s) left empty"))
            else:
                out[col] = out[col].fillna("Unknown")
                actions.append((f"Fill missing: {col}", f"{missing} filled with 'Unknown'"))

    actions.insert(0, ("Rows", f"{format_number(rows_before, 'count')} -> "
                             f"{format_number(len(out), 'count')} rows"))
    return out.reset_index(drop=True), actions


# ================================================================== KPIs =====
def auto_kpis(df: pd.DataFrame) -> list:
    """KPIs the app can show without asking: rows, totals, averages, top values.

    Revenue rule: when the frame has exactly one quantity-like column
    and exactly one price-like column (see _find_revenue_pair), the
    price column's plain sum is replaced by Revenue = sum(quantity x
    price), labelled with both column names so nobody mistakes a plain
    price sum for revenue. Otherwise a plain sum is labelled honestly
    as "Sum of <column>", never as revenue. All numbers go through
    format_number: money 2 decimals, counts 0, other numbers 1."""
    kpis = [{"label": "Rows", "value": format_number(len(df), "count")},
            {"label": "Columns", "value": format_number(len(df.columns), "count")}]
    qty_col, price_col = _find_revenue_pair(df)
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            if col == price_col:
                revenue = float((df[qty_col] * df[col]).sum())
                kpis.append({"label": f"Revenue ({qty_col} x {col})",
                             "value": format_number(revenue, "money")})
            elif _is_price_like(col):
                kpis.append({"label": f"Sum of {col}",
                             "value": format_number(df[col].sum(), "money")})
            elif _is_qty_like(col):
                kpis.append({"label": f"Sum of {col}",
                             "value": format_number(df[col].sum(), "count")})
            else:
                kpis.append({"label": f"Sum of {col}",
                             "value": format_number(df[col].sum(), "number")})
            avg_kind = "money" if _is_price_like(col) else "number"
            kpis.append({"label": f"Average {col}",
                         "value": format_number(df[col].mean(), avg_kind)})
        elif str(df[col].dtype) in ("object", "str") and 1 < df[col].nunique(dropna=True) <= 30:
            top = df[col].value_counts(dropna=False).index[0]
            top_n = int(df[col].value_counts(dropna=False).iloc[0])
            kpis.append({"label": f"Top {col}",
                         "value": f"{top} ({format_number(top_n, 'count')})"})
    date_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    if date_cols:
        d = df[date_cols[0]].dropna()
        if len(d):
            kpis.append({"label": f"{date_cols[0]} range",
                         "value": f"{d.min().date()} to {d.max().date()}"})
    return kpis


def numeric_cols(df: pd.DataFrame) -> list:
    """Columns that hold numbers."""
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def date_cols(df: pd.DataFrame) -> list:
    """Columns that hold dates."""
    return [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]


def _pretty(col) -> str:
    """order_id -> Order Id, for screen labels."""
    return str(col).replace("_", " ").strip().title()


def custom_kpi(df: pd.DataFrame, column: str, agg: str):
    """One KPI on demand: sum / average / count / min / max / median."""
    s = df[column]
    if agg == "Sum":
        return float(s.sum())
    if agg == "Average":
        return float(s.mean())
    if agg == "Count":
        return int(s.count())
    if agg == "Min":
        return float(s.min())
    if agg == "Max":
        return float(s.max())
    if agg == "Median":
        return float(s.median())
    raise ValueError(f"Unknown aggregation: {agg}")


def build_report(df_raw: pd.DataFrame, df_clean: pd.DataFrame, actions: list, kpis: list) -> str:
    """Plain-English report of what was loaded, cleaned and measured."""
    lines = ["# Data Cleaner Studio — Report", "",
             f"Rows: {format_number(len(df_raw), 'count')} loaded -> "
             f"{format_number(len(df_clean), 'count')} after cleaning.",
             f"Columns: {format_number(len(df_raw.columns), 'count')} -> "
             f"{format_number(len(df_clean.columns), 'count')}.", "",
             "## What was cleaned"]
    for step, detail in actions:
        lines.append(f"- **{step}**: {detail}")
    lines += ["", "## KPIs"]
    for k in kpis:
        lines.append(f"- **{k['label']}**: {k['value']}")
    lines += ["", "_Generated by Data Cleaner Studio. "
              + __import__("privacy").data_location_line() + "_"]
    return "\n".join(lines)


def to_excel_bytes(cleaned: pd.DataFrame, kpis: list, actions: list,
                   formulas: bool = False) -> bytes:
    """Cleaned workbook: data + KPIs + cleaning log, as bytes for download.

    formulas=False (default) keeps the old behaviour exactly: the KPIs
    sheet holds plain values. formulas=True adds a fourth sheet,
    "KPIs (live)", where each numeric column's total and average are
    LIVE Excel formulas (=SUM / =AVERAGE) pointing at the "Cleaned Data"
    sheet, so the numbers update if the reader edits the data. The
    existing KPIs sheet (values) is untouched either way."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        cleaned.to_excel(w, sheet_name="Cleaned Data", index=False)
        _format_excel_dates(w.sheets["Cleaned Data"], cleaned)
        pd.DataFrame(kpis).to_excel(w, sheet_name="KPIs", index=False)
        pd.DataFrame(actions, columns=["Step", "Detail"]).to_excel(
            w, sheet_name="Cleaning Log", index=False)
        if formulas:
            _add_live_kpis_sheet(w, cleaned)
    return buf.getvalue()


def _format_excel_dates(sheet, cleaned: pd.DataFrame) -> None:
    """Date-only columns show as YYYY-MM-DD in Excel — a datetime cell
    with no time component must not display as '2026-06-13 00:00:00'.
    Columns that do carry times keep a date+time format."""
    for idx, col in enumerate(cleaned.columns, start=1):
        if not pd.api.types.is_datetime64_any_dtype(cleaned[col]):
            continue
        vals = cleaned[col].dropna()
        date_only = len(vals) == 0 or bool(
            ((vals.dt.hour == 0) & (vals.dt.minute == 0)
             & (vals.dt.second == 0) & (vals.dt.microsecond == 0)).all())
        fmt = "yyyy-mm-dd" if date_only else "yyyy-mm-dd hh:mm:ss"
        for row in range(2, len(cleaned) + 2):
            sheet.cell(row=row, column=idx).number_format = fmt


def _add_live_kpis_sheet(writer, cleaned: pd.DataFrame) -> None:
    """Add the "KPIs (live)" sheet: one Total / Average formula row per
    numeric column, each referencing the "Cleaned Data" sheet by column
    letter and the actual data rows (row 1 is the header, so data runs
    2 .. len(cleaned)+1). Non-numeric columns get no formula — there is
    nothing sensible to total."""
    from openpyxl.utils import get_column_letter

    book = writer.book
    sheet = book.create_sheet("KPIs (live)")
    sheet["A1"] = "KPI"
    sheet["B1"] = "Value (live formula)"
    sheet["C1"] = "Column"
    row = 2
    n_rows = len(cleaned)
    if n_rows == 0:
        sheet["A2"] = "No data rows — nothing to total"
        return
    for idx, col in enumerate(cleaned.columns):
        if not pd.api.types.is_numeric_dtype(cleaned[col]):
            continue
        letter = get_column_letter(idx + 1)
        rng = f"'Cleaned Data'!{letter}2:{letter}{n_rows + 1}"
        sheet.cell(row=row, column=1, value=f"Total {col}")
        sheet.cell(row=row, column=2, value=f"=SUM({rng})")
        sheet.cell(row=row, column=3, value=str(col))
        row += 1
        sheet.cell(row=row, column=1, value=f"Average {col}")
        sheet.cell(row=row, column=2, value=f"=AVERAGE({rng})")
        sheet.cell(row=row, column=3, value=str(col))
        row += 1
    if row == 2:
        sheet["A2"] = "No numeric columns — nothing to total"
    sheet.column_dimensions["A"].width = 32
    sheet.column_dimensions["B"].width = 22
    sheet.column_dimensions["C"].width = 20


# ================================================================ join =====
def join_frames(left: pd.DataFrame, right: pd.DataFrame,
                left_on: str, right_on: str, how: str = "left") -> tuple:
    """Join two tables on a key column (like VLOOKUP / Power Query merge).
    how: left (keep all rows from the first file), inner (only matches),
    outer (keep everything). Returns (joined_df, info dict with row counts
    and how many keys matched on each side)."""
    if left_on not in left.columns:
        raise ValueError(f"Key '{left_on}' not in the first file.")
    if right_on not in right.columns:
        raise ValueError(f"Key '{right_on}' not in the second file.")
    if how not in ("left", "inner", "outer"):
        raise ValueError(f"Unknown join type: {how}")
    joined = left.merge(right, left_on=left_on, right_on=right_on, how=how,
                        suffixes=("", "_right"))
    left_keys = set(left[left_on].dropna().astype(str))
    right_keys = set(right[right_on].dropna().astype(str))
    info = {"left_rows": len(left), "right_rows": len(right),
            "joined_rows": len(joined),
            "matched_keys": len(left_keys & right_keys),
            "left_only": len(left_keys - right_keys),
            "right_only": len(right_keys - left_keys)}
    return joined, info


# ============================================================== sqlite =====
def _sqlite_temp(raw: bytes) -> str:
    """sqlite3 needs a real file, not bytes — write to a temp file."""
    import os
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        f.write(raw)
        return f.name


def list_sqlite_tables(raw: bytes) -> list:
    """Table names inside an uploaded SQLite (.db) file."""
    import os
    import sqlite3
    path = _sqlite_temp(raw)
    try:
        con = sqlite3.connect(path)
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        con.close()
        return tables
    finally:
        os.unlink(path)


def load_sqlite(raw: bytes, table: str) -> pd.DataFrame:
    """Load one table from an uploaded SQLite (.db) file."""
    import os
    import sqlite3
    path = _sqlite_temp(raw)
    try:
        con = sqlite3.connect(path)
        df = pd.read_sql_query(f'SELECT * FROM "{table}"', con)
        con.close()
        return df.replace(r"^\s*$", np.nan, regex=True)
    finally:
        os.unlink(path)


# ================================================================ fuzzy =====
def _similar(a, b) -> float:
    """0–1 similarity between two values (1 = identical). A single swapped
    pair of letters — the most common typo (Delhi/Dehli) — scores high."""
    from difflib import SequenceMatcher
    a, b = str(a).strip().lower(), str(b).strip().lower()
    r = SequenceMatcher(None, a, b).ratio()
    if len(a) == len(b) and len(a) > 2:
        diffs = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        if (len(diffs) == 2 and diffs[1] == diffs[0] + 1
                and a[diffs[0]] == b[diffs[1]] and a[diffs[1]] == b[diffs[0]]):
            r = max(r, 0.95)
    return r


def fuzzy_groups(series: pd.Series, threshold: float = 0.85) -> list:
    """Find look-alike values in a text column (Aarav vs Arav, Delhi vs
    Dehli). Returns [{canonical, members: [(value, count), ...]}] where the
    canonical spelling is the most frequent one. Nothing is changed here —
    the app shows the groups first and merges only on approval."""
    vals = series.dropna().astype(str).str.strip()
    vals = vals[vals != ""]
    counts = vals.value_counts()
    values = list(counts.index)
    used = set()
    groups = []
    for v in values:
        if v in used:
            continue
        members = [(v, int(counts[v]))]
        used.add(v)
        for w in values:
            if w in used:
                continue
            if _similar(v, w) >= threshold:
                members.append((w, int(counts[w])))
                used.add(w)
        if len(members) > 1:
            members.sort(key=lambda t: -t[1])
            groups.append({"canonical": members[0][0], "members": members})
    return groups


def apply_fuzzy(df: pd.DataFrame, column: str, mapping: dict) -> pd.DataFrame:
    """Merge spellings: mapping is {old_value: canonical_value}."""
    out = df.copy()
    out[column] = out[column].replace(mapping)
    return out


# ================================================================== PDF =====
def _pdf_escape(s: str) -> str:
    return (s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)"))


def _pdf_clean(s) -> str:
    """PDF's built-in Helvetica only knows latin-1 — swap the rest."""
    return (str(s).replace("₹", "Rs. ").replace("—", "-").replace("–", "-")
            .replace("→", "->").replace("·", "-")
            .encode("latin-1", "replace").decode("latin-1"))


def _hex_to_rgb01(hex_color):
    """A #RRGGBB string -> (r, g, b) floats 0-1, or None when invalid."""
    if not isinstance(hex_color, str):
        return None
    import re
    if not re.match(r"^#[0-9a-fA-F]{6}$", hex_color.strip()):
        return None
    h = hex_color.strip()[1:]
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def to_pdf_bytes(title: str, kpis: list, actions: list, summary: str,
                 brand=None) -> bytes:
    """A real PDF report with zero extra installs — written by hand in pure
    Python (Helvetica, A4, one flowing column). Returns the PDF as bytes.

    ``brand`` is optional: None behaves exactly as before. A brand dict
    {"name", "accent", ...} (see feat_brand.brand_for_exports) replaces
    "Data Cleaner Studio" with the brand name in the title and footer,
    and draws the accent colour as a header band at the top of each page.
    """
    import textwrap

    brand_name = None
    accent_rgb = None
    if isinstance(brand, dict):
        name = brand.get("name")
        if isinstance(name, str) and name.strip():
            brand_name = name.strip()
        accent_rgb = _hex_to_rgb01(brand.get("accent"))
    if brand_name:
        title = str(title).replace("Data Cleaner Studio", brand_name)
    footer_name = brand_name or "Data Cleaner Studio"

    items = [(_pdf_clean(title), 18, True), ("", 11, False),
             (_pdf_clean(summary), 11, False), ("", 11, False),
             ("KPIs", 13, True)]
    for k in kpis:
        items.append((f"- {_pdf_clean(k['label'])}: {_pdf_clean(k['value'])}", 11, False))
    items.append(("", 11, False))
    items.append(("What was cleaned", 13, True))
    for step, detail in actions:
        items.append((f"- {_pdf_clean(step)}: {_pdf_clean(detail)}", 11, False))
    items.append(("", 11, False))
    items.append((f"Generated by {footer_name}. "
                  + __import__("privacy").data_location_line(),
                  9, False))

    wrapped = []
    for text, size, bold in items:
        if text == "":
            wrapped.append(("", size, bold))
            continue
        width = 100 if size <= 11 else (52 if size >= 18 else 78)
        for part in textwrap.wrap(text, width=width) or [""]:
            wrapped.append((part, size, bold))

    pages = []
    cur, y = [], 792
    for text, size, bold in wrapped:
        h = size + 5
        if y - h < 50:
            pages.append(cur)
            cur, y = [], 792
        cur.append((text, size, bold, y))
        y -= h
    if cur:
        pages.append(cur)

    def content_stream(lines):
        ops = []
        if accent_rgb is not None:
            r, g, b = accent_rgb
            ops.append(f"{r:.3f} {g:.3f} {b:.3f} rg 0 812 595 30 re f")
        for text, size, bold, yy in lines:
            font = "/F2" if bold else "/F1"
            ops.append(f"BT {font} {size} Tf 50 {yy} Td ({_pdf_escape(text)}) Tj ET")
        return ("\n".join(ops)).encode("latin-1")

    n_pages = len(pages)
    # Objects: 1 catalog, 2 pages, 3 Helvetica, 4 Helvetica-Bold,
    # then per page: page object + content object.
    page_ids = [5 + 2 * i for i in range(n_pages)]
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode("latin-1"),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        4: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    }
    for i, lines in enumerate(pages):
        pid, cid = 5 + 2 * i, 6 + 2 * i
        stream = content_stream(lines)
        objects[pid] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                        f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                        f"/Contents {cid} 0 R >>").encode("latin-1")
        objects[cid] = (f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
                        + stream + b"\nendstream")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for n in sorted(objects):
        offsets[n] = len(pdf)
        pdf += f"{n} 0 obj\n".encode("latin-1") + objects[n] + b"\nendobj\n"
    xref_at = len(pdf)
    total = max(objects) + 1
    pdf += f"xref\n0 {total}\n".encode("latin-1")
    pdf += b"0000000000 65535 f \n"
    for n in range(1, total):
        pdf += f"{offsets[n]:010d} 00000 n \n".encode("latin-1")
    pdf += (f"trailer\n<< /Size {total} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF"
            ).encode("latin-1")
    return bytes(pdf)


# ================================================== chunked CSV + Parquet =====
# v1.4 — bigger files. The chunked path mirrors clean() exactly (same steps,
# same order, same global medians / "Unknown" fills), but streams the file
# in chunks so a 500k-row CSV does not need the whole frame in memory at
# once. Two passes:
#   pass 1 — global stats: column kinds, global medians (numeric fill),
#            category modes, duplicate keys, globally-empty columns.
#   pass 2 — apply the same per-row steps per chunk with the global stats,
#            global dedupe, then fill missing values.
# Known limits (documented, not silent):
#   * Column kinds are guessed from the first 5,000 rows (same 80% rules as
#     detect_kind); a column whose type only shows up later in the file can
#     be mis-typed. Kinds for columns that were empty in that sample are
#     re-derived from values collected during pass 1.
#   * Medians are exact: pass 1 keeps every de-duplicated numeric value in
#     memory, so RAM scales with the numeric data, not the row count alone.
#   * Dedupe uses 64-bit row hashes (pd.util.hash_pandas_object); a hash
#     collision would wrongly drop a row (probability ~2**-64 per pair).
#     Float -0.0 vs 0.0 also hash differently although pandas treats them
#     as equal duplicates. Both are negligible for real sales data.
#   * Encoding is picked up front (utf-8 if the whole file decodes, else
#     latin-1) — same fallback as _read_csv_bytes.

_CHUNK_KIND_SAMPLE_ROWS = 5000


def _csv_encoding(raw: bytes) -> str:
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def _iter_csv_chunks(raw: bytes, chunksize: int):
    """Yield DataFrames of `chunksize` rows, delimiter-sniffed, with empty /
    whitespace-only strings already turned into NaN (as load_file does)."""
    enc = _csv_encoding(raw)
    reader = pd.read_csv(io.BytesIO(raw), sep=None, engine="python",
                         encoding=enc, chunksize=chunksize)
    for chunk in reader:
        yield chunk.replace(r"^\s*$", np.nan, regex=True)


def _tidy_chunk_columns(df: pd.DataFrame) -> tuple:
    """Same rename as clean(): strip, lower-case, spaces -> underscores."""
    new_cols = [re.sub(r"[^0-9a-z_]+", "_", c.strip().lower().replace(" ", "_")).strip("_")
                for c in df.columns]
    changed = sum(1 for a, b in zip(df.columns, new_cols) if a != b)
    df.columns = new_cols
    return df, changed


def _strip_chunk_text(df: pd.DataFrame) -> int:
    """Same trim as clean(); returns the number of cells trimmed."""
    n = 0
    for col in df.columns:
        if df[col].dtype == object or str(df[col].dtype) == "str":
            before = df[col].astype(object).astype(str)
            after = df[col].astype(object).where(
                df[col].isna(), df[col].astype(object).astype(str).str.strip())
            n += int((before != after.astype(str)).sum())
            df[col] = after
    return n


def _fix_chunk_numbers(df: pd.DataFrame, kinds: dict) -> dict:
    """Same currency/comma/% cleanup as clean(); returns {col: n_fixed}."""
    fixed = {}
    for col, kind in kinds.items():
        if kind == "number" and col in df.columns:
            raw = df[col].astype(object).astype(str).str.strip()
            cleaned = raw.str.replace(r"^(₹|\$|€|£|Rs\.?|INR)\s*", "", regex=True, case=False)
            cleaned = cleaned.str.replace(",", "", regex=False).str.replace(r"%$", "", regex=True).str.strip()
            converted = pd.to_numeric(cleaned, errors="coerce")
            fixed[col] = int(((raw != cleaned) & converted.notna()).sum())
            df[col] = converted
    return fixed


def _fix_chunk_dates(df: pd.DataFrame, kinds: dict) -> dict:
    """Same date parsing as clean(); returns {col: n_parsed}."""
    parsed = {}
    for col, kind in kinds.items():
        if kind == "date" and col in df.columns:
            out = pd.to_datetime(df[col].astype(object).astype(str),
                                 errors="coerce", format="mixed")
            parsed[col] = int(out.notna().sum())
            df[col] = out
    return parsed


def _fix_chunk_categories(df: pd.DataFrame, kinds: dict) -> dict:
    """Same Title Case normalisation as clean(); returns {col: n_fixed}."""
    fixed = {}
    for col, kind in kinds.items():
        if kind == "category" and col in df.columns:
            before = df[col].astype(object).astype(str)
            df[col] = df[col].astype(object).where(
                df[col].isna(), df[col].astype(object).astype(str).str.strip()
                .str.replace(_WORD_RE, _title_match, regex=True))
            fixed[col] = int((before != df[col].astype(object).astype(str)).sum())
    return fixed


def _apply_chunk_steps(df: pd.DataFrame, kinds: dict, opts: dict) -> tuple:
    """clean()'s per-row steps (tidy / strip / drop-empty-rows / fix numbers,
    dates, categories) on one chunk. Returns (df, counts dict). Fill-missing
    and dedupe are NOT done here — they need the global pass-1 stats."""
    counts = {"tidy": 0, "trimmed": 0, "empty_rows": 0,
              "fixed_numbers": {}, "parsed_dates": {}, "fixed_categories": {}}
    if opts["tidy_columns"]:
        df, counts["tidy"] = _tidy_chunk_columns(df)
    if opts["strip_text"]:
        counts["trimmed"] = _strip_chunk_text(df)
    if opts["drop_empty"]:
        empty_rows = int(df.isna().all(axis=1).sum())
        if empty_rows:
            df = df[df.notna().any(axis=1)]
            counts["empty_rows"] = empty_rows
    if opts["fix_numbers"]:
        counts["fixed_numbers"] = _fix_chunk_numbers(df, kinds)
    if opts["fix_dates"]:
        counts["parsed_dates"] = _fix_chunk_dates(df, kinds)
    if opts["fix_categories"]:
        counts["fixed_categories"] = _fix_chunk_categories(df, kinds)
    return df, counts


def _row_hashes(df: pd.DataFrame, kinds: dict | None = None):
    """64-bit hash per row, for global dedupe (NaN == NaN, as duplicated()).

    Numeric columns are hashed as float64: a chunk with no missing values
    reads as int64 while the same column reads as float64 in a chunk with
    missing values, and the hash must not depend on that."""
    hdf = df
    if kinds:
        num_cols = [c for c, k in kinds.items()
                    if k == "number" and c in df.columns]
        if num_cols:
            hdf = df.copy()
            for c in num_cols:
                hdf[c] = pd.to_numeric(hdf[c], errors="coerce").astype("float64")
    return pd.util.hash_pandas_object(hdf, index=False).astype("uint64").tolist()


def _kinds_from_sample(raw: bytes, chunksize: int) -> dict:
    """Guess column kinds from the first rows, after the same tidy/strip/
    drop-empty steps clean() runs before profiling."""
    rows = []
    for chunk in _iter_csv_chunks(raw, chunksize):
        rows.append(chunk)
        if sum(len(c) for c in rows) >= _CHUNK_KIND_SAMPLE_ROWS:
            break
    if not rows:
        return {}
    df = pd.concat(rows, ignore_index=True).head(_CHUNK_KIND_SAMPLE_ROWS)
    df, _ = _tidy_chunk_columns(df)
    _strip_chunk_text(df)
    empty_cols = [c for c in df.columns if df[c].isna().all()]
    if empty_cols:
        df = df.drop(columns=empty_cols)
    df = df[df.notna().any(axis=1)]
    if len(df) == 0 or len(df.columns) == 0:
        return {}
    return {row["column"]: row["type"] for row in profile(df)}


def _default_chunk_opts(options: dict | None) -> dict:
    opts = {
        "tidy_columns": True, "strip_text": True, "drop_duplicates": True,
        "drop_empty": True, "fix_numbers": True, "fix_dates": True,
        "fix_categories": True, "fill_missing": True,
    }
    if options:
        opts.update(options)
    return opts


def chunked_global_stats(raw: bytes, chunksize: int = 50000,
                         options: dict | None = None) -> dict:
    """Pass 1 of the chunked clean: global stats for the whole CSV.

    Returns {"kinds", "medians", "modes", "empty_columns", "rows_before",
    "duplicate_rows", "empty_rows"}. Medians are exact (de-duplicated
    numeric values); modes are the most frequent value per category column
    (ties -> first seen). "integer_like" maps each numeric column to
    whether all its values are whole numbers — the chunked fill rounds
    the median to a whole number for those columns, exactly like
    clean(). "had_missing" maps each numeric column to whether any
    missing value survived dedupe: clean() only casts an integer-like
    column to int64 when it actually filled something, so the chunked
    path must cast on the global answer, not on each chunk's own
    missing count (a chunk with no missing values would otherwise
    stay float and pd.concat would upcast the whole column)."""
    from collections import Counter, defaultdict

    opts = _default_chunk_opts(options)
    kinds = _kinds_from_sample(raw, chunksize)
    numeric_vals = defaultdict(list)
    category_counts = defaultdict(Counter)
    had_missing = {}  # numeric col -> any missing value survived dedupe
    samples = defaultdict(list)  # raw post-strip values, for late kind fixes
    non_empty = set()
    seen_hashes = set()
    rows_before = 0
    duplicate_rows = 0
    empty_rows = 0

    all_cols = None
    for chunk in _iter_csv_chunks(raw, chunksize):
        rows_before += len(chunk)
        if all_cols is None:
            all_cols = list(chunk.columns)
        df, counts = _apply_chunk_steps(chunk, kinds, opts)
        empty_rows += counts["empty_rows"]
        for col in df.columns:
            if df[col].notna().any():
                non_empty.add(col)
            if len(samples[col]) < 200:
                vals = df[col].dropna().astype(object).astype(str).head(
                    200 - len(samples[col])).tolist()
                samples[col].extend(vals)
        if opts["drop_duplicates"] and len(df):
            hashes = _row_hashes(df, kinds)
            keep = []
            for h in hashes:
                if h in seen_hashes:
                    keep.append(False)
                else:
                    keep.append(True)
                    seen_hashes.add(h)
            duplicate_rows += int(len(df) - sum(keep))
            df = df[keep]
        for col, kind in kinds.items():
            if col not in df.columns or len(df) == 0:
                continue
            if kind == "number":
                if bool(df[col].isna().any()):
                    had_missing[col] = True
                numeric_vals[col].extend(
                    df[col].dropna().astype(float).tolist())
            elif kind == "category":
                category_counts[col].update(
                    df[col].dropna().astype(object).astype(str).tolist())

    all_cols = all_cols or []
    tidied_all = [re.sub(r"[^0-9a-z_]+", "_", c.strip().lower().replace(" ", "_")).strip("_")
                  for c in all_cols] if opts["tidy_columns"] else list(all_cols)
    empty_columns = [c for c in tidied_all if c not in non_empty]
    # Kinds for columns that were empty in the sample: re-derive from the
    # values pass 1 actually saw.
    for col in tidied_all:
        if col not in kinds and col not in empty_columns and samples.get(col):
            kinds[col] = detect_kind(pd.Series(samples[col]))

    medians = {c: float(np.median(v)) for c, v in numeric_vals.items() if v}
    integer_like = {}
    for c, v in numeric_vals.items():
        if not v:
            continue
        arr = np.asarray(v, dtype=float)
        integer_like[c] = bool(
            np.isfinite(arr).all() and (arr == np.floor(arr)).all())
    modes = {}
    for c, counter in category_counts.items():
        if counter:
            modes[c] = counter.most_common(1)[0][0]
    return {"kinds": kinds, "medians": medians, "modes": modes,
            "empty_columns": empty_columns, "rows_before": rows_before,
            "duplicate_rows": duplicate_rows, "empty_rows": empty_rows,
            "integer_like": integer_like, "had_missing": had_missing}


def profile_csv_chunked(raw: bytes, chunksize: int = 50000) -> list:
    """profile() for a CSV too big to load at once: streams it in chunks
    and returns the same per-column rows (column, type, missing,
    missing_pct, unique, sample). Types are guessed from the first 5,000
    non-empty values per column; unique counts are exact."""
    from collections import defaultdict

    counts = defaultdict(int)
    missing = defaultdict(int)
    uniques = defaultdict(set)
    samples = {}
    kind_vals = defaultdict(list)
    columns = None
    for chunk in _iter_csv_chunks(raw, chunksize):
        if columns is None:
            columns = list(chunk.columns)
        for col in chunk.columns:
            s = chunk[col]
            counts[col] += len(s)
            missing[col] += int(s.isna().sum())
            vals = s.dropna()
            if len(vals):
                if col not in samples:
                    samples[col] = str(vals.iloc[0])
                # A column reads as int64 in a chunk with no missing values
                # but float64 in a chunk with missing values — 2 and 2.0
                # must count as ONE unique value, as profile() counts them
                # in the single full-frame dtype. Object columns count
                # normalized strings, exactly like profile().
                if pd.api.types.is_numeric_dtype(s):
                    uniques[col].update(float(v) for v in vals.tolist())
                else:
                    uniques[col].update(
                        normalize_text_values(vals).tolist())
                if len(kind_vals[col]) < _CHUNK_KIND_SAMPLE_ROWS:
                    kind_vals[col].extend(
                        vals.astype(object).astype(str).head(
                            _CHUNK_KIND_SAMPLE_ROWS - len(kind_vals[col])).tolist())
    rows = []
    for col in (columns or []):
        total = counts[col]
        kind = detect_kind(pd.Series(kind_vals[col])) if kind_vals[col] else "text"
        rows.append({
            "column": col,
            "type": kind,
            "missing": missing[col],
            "missing_pct": float(round(100 * missing[col] / total, 1)) if total else 0.0,
            "unique": len(uniques[col]),
            "sample": samples.get(col, ""),
        })
    return rows


def clean_csv_chunked(raw: bytes, opts: dict | None = None,
                      chunksize: int = 50000) -> tuple:
    """Chunked clean: (cleaned_df, actions) with the same contract as
    clean(). Two passes over the file (see the module note above); the
    result must match clean(load_file(...)) on data that fits in memory."""
    options = _default_chunk_opts(opts)
    stats = chunked_global_stats(raw, chunksize, options)
    kinds, medians = stats["kinds"], stats["medians"]
    integer_like = stats.get("integer_like", {})
    had_missing = stats.get("had_missing", {})
    empty_columns = set(stats["empty_columns"]) if options["drop_empty"] else set()

    out_chunks = []
    seen_hashes = set()
    tidy_changed = 0
    trimmed = 0
    fixed_numbers = {}
    parsed_dates = {}
    fixed_categories = {}
    dupes = 0
    filled = {}  # step -> [count, kind]  kind: "median" | "unknown" | "blank"

    for chunk in _iter_csv_chunks(raw, chunksize):
        df, counts = _apply_chunk_steps(chunk, kinds, options)
        tidy_changed += counts["tidy"]
        trimmed += counts["trimmed"]
        for col, n in counts["fixed_numbers"].items():
            fixed_numbers[col] = fixed_numbers.get(col, 0) + n
        for col, n in counts["parsed_dates"].items():
            parsed_dates[col] = parsed_dates.get(col, 0) + n
        for col, n in counts["fixed_categories"].items():
            fixed_categories[col] = fixed_categories.get(col, 0) + n
        if empty_columns:
            df = df.drop(columns=[c for c in df.columns if c in empty_columns],
                         errors="ignore")
        if options["drop_duplicates"] and len(df):
            hashes = _row_hashes(df, kinds)
            keep = []
            for h in hashes:
                if h in seen_hashes:
                    keep.append(False)
                else:
                    keep.append(True)
                    seen_hashes.add(h)
            dupes += int(len(df) - sum(keep))
            df = df[keep]
        if options["fill_missing"] and len(df):
            for col in df.columns:
                missing = int(df[col].isna().sum())
                # clean() casts an integer-like column to int64 exactly
                # when it filled something in it. The chunked path must
                # decide that on the GLOBAL missing answer: a chunk with
                # no missing values still needs the cast, or pd.concat
                # upcasts the whole column back to float64.
                casts_int = (pd.api.types.is_numeric_dtype(df[col])
                             and bool(integer_like.get(col, False))
                             and bool(had_missing.get(col, False)))
                if missing == 0:
                    if casts_int and str(df[col].dtype) != "int64":
                        try:
                            df[col] = df[col].astype("int64")
                        except (ValueError, OverflowError):
                            pass
                    continue
                step = f"Fill missing: {col}"
                if pd.api.types.is_numeric_dtype(df[col]):
                    is_int = casts_int
                    raw_median = medians.get(col, df[col].median())
                    fill_value = (_round_half_away(float(raw_median))
                                  if is_int and pd.notna(raw_median)
                                  else raw_median)
                    df[col] = _fill_numeric_column(df[col], fill_value, is_int)
                    filled.setdefault(
                        step, [0, "median_int" if is_int else "median"])[0] += missing
                elif pd.api.types.is_datetime64_any_dtype(df[col]):
                    step = f"Missing left blank: {col}"
                    filled.setdefault(step, [0, "blank"])[0] += missing
                else:
                    df[col] = df[col].fillna("Unknown")
                    filled.setdefault(step, [0, "unknown"])[0] += missing
        if len(df):
            out_chunks.append(df)

    out = (pd.concat(out_chunks, ignore_index=True) if out_chunks
           else pd.DataFrame())
    actions = []
    if tidy_changed:
        actions.append(("Tidy column names", f"{tidy_changed} column(s) renamed"))
    if trimmed:
        actions.append(("Strip extra spaces", f"{trimmed} cell(s) trimmed"))
    if empty_columns:
        actions.append(("Drop empty columns",
                        f"{len(empty_columns)}: {', '.join(sorted(empty_columns))}"))
    if stats["empty_rows"]:
        actions.append(("Drop empty rows", f"{stats['empty_rows']} row(s) removed"))
    for col, n in fixed_numbers.items():
        if n:
            actions.append((f"Fix numbers: {col}",
                            f"{n} value(s) cleaned (₹ $ , % removed)"))
    # clean() reports every date column, even one with 0 parsed values.
    for col, kind in kinds.items():
        if kind == "date":
            actions.append((f"Parse dates: {col}",
                            f"{parsed_dates.get(col, 0)} value(s) parsed as dates"))
    for col, n in fixed_categories.items():
        if n:
            actions.append((f"Fix categories: {col}",
                            f"{n} value(s) set to one case"))
    if dupes:
        actions.append(("Drop duplicate rows", f"{dupes} row(s) removed"))
    for step, (n, kind) in filled.items():
        if kind == "median":
            actions.append((step, f"{n} filled with median"))
        elif kind == "median_int":
            actions.append((step,
                            f"{n} filled with median (rounded to a whole number)"))
        elif kind == "blank":
            actions.append((step, f"{n} date(s) left empty"))
        else:
            actions.append((step, f"{n} filled with 'Unknown'"))
    actions.insert(0, ("Rows", f"{format_number(stats['rows_before'], 'count')} -> "
                             f"{format_number(len(out), 'count')} rows"))
    return out.reset_index(drop=True), actions


# ================================================================ Parquet =====
def load_parquet(raw: bytes) -> pd.DataFrame:
    """Load a Parquet file from raw bytes (pyarrow engine). Empty /
    whitespace-only strings become NaN, like load_file."""
    df = pd.read_parquet(io.BytesIO(raw), engine="pyarrow")
    return df.replace(r"^\s*$", np.nan, regex=True)


def to_parquet_bytes(df: pd.DataFrame) -> bytes:
    """DataFrame -> Parquet bytes (pyarrow engine, no index column)."""
    buf = io.BytesIO()
    df.to_parquet(buf, engine="pyarrow", index=False)
    return buf.getvalue()
