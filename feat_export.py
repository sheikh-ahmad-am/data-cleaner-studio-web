"""Data Cleaner Studio v1.2 — GROUP 4: export & connect.

Pure logic lives in plain functions (no Streamlit calls) so it can be
tested without the app running. The ``render_*`` functions are thin
Streamlit wrappers: they take ``st`` first and use only widget keys
starting with ``e_``. Widget keys are never reused to store data —
``e_email_sched`` / ``e_db_conn`` are data keys, not widget keys.

Honesty rules in this module — nothing is faked:
  * Google Sheets write-back needs the user's Google credentials + the
    Sheets API client, which is NOT installed in this portable build.
  * Live database drivers (v1.4): MySQL (mysql-connector-python) and
    PostgreSQL (psycopg2-binary) ship as wheels in the portable build.
    SQL Server (pymssql) is best-effort — if its driver is missing the
    UI says so plainly. A DuckDB-based path was tested and also needs a
    runtime extension download (mysql_scanner / postgres_scanner from
    extensions.duckdb.org), which is not bundled — so that route stays
    pending.
  * Scheduled email only works while the app is open (or via Windows
    Task Scheduler). No background sending is promised.
"""

import datetime
import importlib.util
import json
import smtplib
from email.message import EmailMessage

import altair as alt
import pandas as pd

import engine
import feat_db
from pptx_writer import to_pptx_bytes

__all__ = [
    "to_pptx_bytes",
    "validate_sheets_creds",
    "build_email_message",
    "check_db_driver",
    "db_connection_details",
    "heatmap_corr",
    "treemap_chart",
    "funnel_chart",
    "render_pptx_download",
    "render_sheets_export",
    "render_email_schedule",
    "render_db_connect",
    "render_column_charts",
]

SHEETS_PENDING_MSG = (
    "Credentials look valid, but the Sheets API client is not installed in "
    "this portable build — this is pending. Writing back to Google Sheets "
    "needs the Google Sheets API, which will come in a later update."
)

DB_DRIVERS = {
    "MySQL": ("mysql.connector", "mysql-connector-python"),
    "PostgreSQL": ("psycopg2", "psycopg2-binary"),
    "SQL Server": ("pymssql", "pymssql"),
}

DB_DEFAULT_PORTS = {"MySQL": "3306", "PostgreSQL": "5432", "SQL Server": "1433"}

EMAIL_SCHED_KEY = "e_email_sched"
DB_CONN_KEY = "e_db_conn"


# =========================================================== pure logic =====
def validate_sheets_creds(raw):
    """Check a Google service-account JSON (bytes or dict).

    Returns (ok, message). A valid-looking file still cannot write to
    Sheets in this build — the message says so plainly.
    """
    try:
        data = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
    except (ValueError, TypeError, UnicodeDecodeError):
        return False, "That file is not valid JSON — pick the service-account JSON file from Google Cloud."
    if not isinstance(data, dict):
        return False, "That JSON is not a service-account file (expected an object with client_email and private_key)."
    missing = [f for f in ("client_email", "private_key")
               if not data.get(f) or not str(data.get(f)).strip()]
    if missing:
        return False, ("This JSON is missing: " + ", ".join(missing) +
                       ". It needs to be a Google service-account key "
                       "(client_email + private_key).")
    return True, SHEETS_PENDING_MSG


def build_email_message(sender, recipient, subject, body_text,
                        pdf_bytes, pdf_filename="report.pdf"):
    """Build the scheduled-report email (MIME, PDF attached). No sending.

    Returns an EmailMessage. Sending happens only in render_email_schedule
    when the user presses 'Send test email now'.
    """
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body_text)
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf",
                       filename=pdf_filename)
    return msg


def check_db_driver(db_type):
    """Is the driver for this database installed? (bool, message).

    v1.4: the drivers ship as wheels in the portable build. When one is
    missing the message says so plainly (same wording as before, so a
    missing driver is never mistaken for a working connection).
    """
    key = feat_db.normalize_engine(db_type)
    _db_label = {"mysql": "MySQL", "postgres": "PostgreSQL",
                 "sqlserver": "SQL Server"}.get(key, db_type)
    module, package = DB_DRIVERS.get(db_type, (None, None))
    if module is None:
        return False, f"Unknown database type: {db_type}"
    if key and feat_db.db_driver_status().get(key):
        return True, f"{_db_label} driver ({package}) is installed."
    return False, (
        f"The {_db_label} driver ({package}) is NOT installed in this "
        f"portable build, so a live connection cannot be tested yet. "
        f"Save the connection details below as JSON and they will be ready "
        f"for the next update, when the driver is bundled."
    )


def db_connection_details(db_type, host, port, database, table, query):
    """Connection details as a plain dict — NEVER includes the password."""
    return {
        "type": db_type,
        "host": (host or "").strip(),
        "port": (port or "").strip() or DB_DEFAULT_PORTS.get(db_type, ""),
        "database": (database or "").strip(),
        "table": (table or "").strip(),
        "query": (query or "").strip(),
    }


def _numeric_corr_frame(df):
    """Melted correlation matrix of the numeric columns (or None)."""
    nums = engine.numeric_cols(df)
    if len(nums) < 2:
        return None, nums
    corr = df[nums].corr(numeric_only=True)
    long = (corr.reset_index().melt(id_vars="index",
                                    var_name="column2", value_name="corr")
            .rename(columns={"index": "column1"}))
    return long, nums


def heatmap_corr(df):
    """Altair chart: correlation heatmap of the numeric columns."""
    long, nums = _numeric_corr_frame(df)
    if long is None:
        return (alt.Chart(pd.DataFrame({"x": []}))
                .mark_rect()
                .properties(title="Correlation heatmap — need at least "
                                  "2 numeric columns",
                            width=320, height=240))
    return (alt.Chart(long)
            .mark_rect()
            .encode(x=alt.X("column1:N", title=""),
                    y=alt.Y("column2:N", title=""),
                    color=alt.Color("corr:Q", title="Correlation",
                                    scale=alt.Scale(scheme="redblue",
                                                    domain=[-1, 1])),
                    tooltip=["column1", "column2",
                             alt.Tooltip("corr:Q", format=".2f")])
            .properties(title="Correlation heatmap", width=320, height=320))


def _squarify_layout(sizes, x, y, width, height):
    """Squarified treemap layout, pure Python.

    ``sizes``: list of positive numbers (largest first is best).
    Returns [(x, y, w, h), ...] in the same order as ``sizes``,
    filling the (x, y, width, height) rectangle. Rows are laid across
    the longer side; a value joins the current row only while the worst
    rectangle aspect ratio in the row does not get worse.
    """
    total = float(sum(sizes))
    if total <= 0 or width <= 0 or height <= 0:
        return [(x, y, 0, 0)] * len(sizes)
    scale = (width * height) / total
    areas = [s * scale for s in sizes]
    order = sorted(range(len(sizes)), key=lambda i: -areas[i])
    rects = [None] * len(sizes)
    queue = [(i, areas[i]) for i in order]
    cx, cy, cw, ch = float(x), float(y), float(width), float(height)

    def _worst(row_areas, side_len):
        row_total = sum(row_areas)
        if row_total <= 0 or side_len <= 0:
            return float("inf")
        thick = row_total / side_len
        worst = 0.0
        for a in row_areas:
            along = a / thick if thick else 0
            worst = max(worst, along / thick if thick else 0,
                        thick / along if along else 0)
        return worst

    while queue:
        horizontal = cw >= ch
        side = cw if horizontal else ch
        row = [queue.pop(0)]
        while queue:
            cand = row + [queue[0]]
            if (_worst([a for _, a in cand], side)
                    <= _worst([a for _, a in row], side)):
                row.append(queue.pop(0))
            else:
                break
        row_total = sum(a for _, a in row)
        if horizontal:
            thick = row_total / cw if cw else 0
            rx = cx
            for idx, a in row:
                rw = a / thick if thick else 0
                rects[idx] = (rx, cy, rw, thick)
                rx += rw
            cy += thick
            ch -= thick
        else:
            thick = row_total / ch if ch else 0
            ry = cy
            for idx, a in row:
                rh = a / thick if thick else 0
                rects[idx] = (cx, ry, thick, rh)
                ry += rh
            cx += thick
            cw -= thick
        if cw <= 0 or ch <= 0:
            for idx, _ in queue:
                rects[idx] = (cx, cy, 0, 0)
            break
    return rects


def _grouped(df, cat_col, num_col, top_n=12):
    """Aggregate ``num_col`` by ``cat_col``, biggest first (top_n rows)."""
    if cat_col not in df.columns or num_col not in df.columns:
        return None
    grouped = (df.groupby(df[cat_col].astype(str), dropna=False)[num_col]
               .sum(min_count=1).reset_index()
               .rename(columns={cat_col: "category", num_col: "value"}))
    grouped = grouped.dropna(subset=["value"])
    grouped = grouped[grouped["value"] > 0]
    grouped = grouped.sort_values("value", ascending=False).head(top_n)
    return grouped.reset_index(drop=True)


def treemap_chart(df, cat_col, num_col):
    """Altair chart: squarified treemap of ``num_col`` summed by ``cat_col``.

    Rectangles are computed in pure Python (_squarify_layout) and drawn
    with mark_rect + x/x2/y/y2.
    """
    grouped = _grouped(df, cat_col, num_col)
    if grouped is None or grouped.empty:
        return (alt.Chart(pd.DataFrame({"x": []}))
                .mark_rect()
                .properties(title="Treemap — pick a category column and "
                                  "a number column with positive values",
                            width=600, height=360))
    rects = _squarify_layout(list(grouped["value"]), 0, 0, 100, 60)
    plot = grouped.copy()
    plot["x"] = [r[0] for r in rects]
    plot["y"] = [r[1] for r in rects]
    plot["x2"] = [r[0] + r[2] for r in rects]
    plot["y2"] = [r[1] + r[3] for r in rects]
    return (alt.Chart(plot)
            .mark_rect()
            .encode(x=alt.X("x:Q", axis=None),
                    x2="x2:Q",
                    y=alt.Y("y:Q", axis=None),
                    y2="y2:Q",
                    color=alt.Color("category:N", legend=None),
                    tooltip=["category",
                             alt.Tooltip("value:Q", format=",.1f")])
            .properties(title=f"Treemap — {engine._pretty(num_col)} by "
                              f"{engine._pretty(cat_col)}",
                        width=600, height=360))


def funnel_chart(df, cat_col, num_col):
    """Altair chart: funnel of ``num_col`` summed by ``cat_col``.

    Centred bars, biggest stage on top, smallest at the bottom.
    """
    grouped = _grouped(df, cat_col, num_col)
    if grouped is None or grouped.empty:
        return (alt.Chart(pd.DataFrame({"x": []}))
                .mark_bar()
                .properties(title="Funnel — pick a category column and "
                                  "a number column with positive values",
                            width=600, height=360))
    plot = grouped.copy()
    plot["x"] = -plot["value"] / 2
    plot["x2"] = plot["value"] / 2
    order = list(plot["category"])
    return (alt.Chart(plot)
            .mark_bar()
            .encode(x=alt.X("x:Q", title=engine._pretty(num_col)),
                    x2="x2:Q",
                    y=alt.Y("category:N", sort=order,
                            title=engine._pretty(cat_col)),
                    color=alt.Color("category:N", legend=None),
                    tooltip=["category",
                             alt.Tooltip("value:Q", format=",.1f")])
            .properties(title=f"Funnel — {engine._pretty(num_col)} by "
                              f"{engine._pretty(cat_col)}",
                        width=600, height=360))


# ===================================================== render (Streamlit) ===
def render_pptx_download(st, kpis, actions, raw, clean, brand=None):
    """Report tab: download the report as a PowerPoint file.

    Reads: raw, clean (passed in). Writes: nothing to session state.
    ``brand`` is optional (see pptx_writer.to_pptx_bytes) — None keeps
    the plain Data Cleaner Studio branding.
    """
    if clean is None:
        st.info("Clean the data first — the PowerPoint report is built "
                "from the cleaned file and its KPIs.")
        return
    summary = (f"Rows: {len(raw):,} loaded -> {len(clean):,} after cleaning. "
               f"Columns: {len(raw.columns)} -> {len(clean.columns)}."
               if raw is not None else
               f"Rows: {len(clean):,} after cleaning.")
    pptx_bytes = to_pptx_bytes("Data Cleaner Studio — Report",
                               kpis or [], actions or [], summary,
                               table_df=clean, brand=brand)
    st.download_button(
        "Download PowerPoint report (.pptx)", pptx_bytes,
        file_name="report.pptx",
        mime="application/vnd.openxmlformats-officedocument.presentationml."
             "presentation",
        key="e_pptx_dl",
        help="Title, KPIs, cleaning log, plus a table of the first 8 rows "
             "on slide 2.")


def render_sheets_export(st, df):
    """Report tab: export the cleaned data back to Google Sheets.

    Honest pending state: writing needs the user's Google credentials
    AND the Sheets API client, which is not installed in this build.
    No network call is ever attempted here.
    """
    st.subheader("Export to Google Sheets")
    st.write("Writing back to Google Sheets needs your Google credentials "
             "(a service-account JSON file) and the Google Sheets API — "
             "neither is connected in this portable build yet, so this "
             "export is pending. Reading a public sheet still works from "
             "the sidebar.")
    if df is not None:
        st.write(f"Ready to export when connected: {len(df):,} rows, "
                 f"{len(df.columns)} columns.")
    uploaded = st.file_uploader(
        "Service-account JSON (to check your credentials)",
        type=["json"], key="e_sheets_creds",
        help="Google Cloud -> Service accounts -> Keys -> Add key -> JSON. "
             "The file is only checked, never sent anywhere.")
    if uploaded is not None:
        ok, msg = validate_sheets_creds(uploaded.getvalue())
        if ok:
            st.success(msg)
        else:
            st.error(msg)


def render_email_schedule(st, kpis, actions, raw, clean):
    """Report tab: scheduled email report (SMTP).

    The password is typed fresh each time and never written to any file
    or to session state under a data key. Only the schedule (server,
    port, user, recipient, time — never the password) is stored, in
    session_state["e_email_sched"]. Unattended sending needs the app
    open (or Windows Task Scheduler) — no background sending is promised.
    """
    st.subheader("Scheduled email report")
    st.write("Email the PDF report to yourself every day. This sends from "
             "your own email account (SMTP). It only works while the app "
             "is open — for truly unattended sending, run the app through "
             "Windows Task Scheduler instead.")
    server = st.text_input("SMTP server", key="e_email_server",
                           placeholder="smtp.gmail.com",
                           help="Gmail: smtp.gmail.com. Outlook: "
                                "smtp.office365.com.")
    port = st.text_input("SMTP port", key="e_email_port", value="587",
                         help="587 is the usual port (STARTTLS). 465 uses SSL.")
    username = st.text_input("Username / your email", key="e_email_user",
                             placeholder="you@example.com")
    password = st.text_input("Password (use an app password, not your "
                             "main password)", type="password",
                             key="e_email_pass")
    recipient = st.text_input("Send the report to", key="e_email_recipient",
                              placeholder="you@example.com")
    sched_time = st.time_input("Send every day at", key="e_email_time",
                               value=datetime.time(9, 0))
    enable = st.checkbox("Enable daily email report", key="e_email_enable",
                         help="While this is on and the app is open, the "
                              "report is sent at the time above.")

    filled = all([server.strip(), port.strip(), username.strip(),
                  password, recipient.strip()])
    if enable and filled:
        st.session_state[EMAIL_SCHED_KEY] = {
            "server": server.strip(), "port": port.strip(),
            "user": username.strip(), "recipient": recipient.strip(),
            "time": sched_time.strftime("%H:%M"), "enabled": True,
        }
        st.success("Schedule saved (server, port, user, recipient and time "
                   "— the password is never stored). It sends while the app "
                   "is open.")
    elif enable:
        st.warning("Fill in every field above (server, port, username, "
                   "password, recipient) before the schedule can start.")

    if st.button("Send test email now", key="e_email_test"):
        if not filled:
            st.error("Fill in the server, port, username, password and "
                     "recipient first.")
        elif clean is None:
            st.error("Clean the data first — the test email sends the "
                     "report as a PDF, and there is no report yet.")
        else:
            try:
                summary = (f"Rows: {len(raw):,} loaded -> "
                           f"{len(clean):,} after cleaning."
                           if raw is not None else "")
                pdf_bytes = engine.to_pdf_bytes(
                    "Data Cleaner Studio — Report", kpis or [],
                    actions or [], summary)
                msg = build_email_message(
                    username.strip(), recipient.strip(),
                    "Data Cleaner Studio — daily report",
                    "Your Data Cleaner Studio report is attached.\n\n"
                    + summary, pdf_bytes)
                port_n = int(port.strip())
                with st.spinner("Sending the test email…"):
                    if port_n == 465:
                        smtp = smtplib.SMTP_SSL(server.strip(), port_n, timeout=30)
                    else:
                        smtp = smtplib.SMTP(server.strip(), port_n, timeout=30)
                        if port_n == 587:
                            smtp.starttls()
                    with smtp:
                        smtp.login(username.strip(), password)
                        smtp.send_message(msg)
                st.success(f"Test email sent to {recipient.strip()} — "
                           "the PDF report is attached; check the inbox "
                           "(and spam).")
            except Exception as e:  # noqa: BLE001 - show the real error
                st.error(f"Could not send the email: {e}")


def render_db_connect(st):
    """Tools tab: live database connection (v1.4 — really connects).

    Drivers ship as wheels in the portable build. Returns (df, name) when
    the user loads a table, else (None, None) — the caller sets the
    loaded table as the data. The password lives only in this session's
    memory (needed to list/load tables); it is never saved to disk and
    never included in the downloadable connection details.
    """
    st.subheader("Live database connection")
    st.write("Pull data straight from MySQL, PostgreSQL or SQL Server. "
             "Your server details are needed — type them below.")
    status = feat_db.db_driver_status()
    _labels = {"mysql": "MySQL", "postgres": "PostgreSQL",
               "sqlserver": "SQL Server"}
    for _key in ("mysql", "postgres", "sqlserver"):
        if status.get(_key):
            st.caption(f"{_labels[_key]} driver: installed.")
        else:
            st.caption(f"{_labels[_key]} driver: not installed in this build.")
    db_type = st.selectbox("Database", ["MySQL", "PostgreSQL", "SQL Server"],
                           key="e_db_type")
    host = st.text_input("Host", key="e_db_host", placeholder="localhost")
    port = st.text_input("Port", key="e_db_port",
                         placeholder=DB_DEFAULT_PORTS[db_type])
    username = st.text_input("Username", key="e_db_user")
    password = st.text_input("Password", type="password", key="e_db_pass")
    database = st.text_input("Database", key="e_db_name")
    params = {"host": host, "port": port, "user": username,
              "password": password, "database": database}
    connected = False
    if st.button("Test connection", key="e_db_test"):
        ok, msg = check_db_driver(db_type)
        if not ok:
            st.error(msg)
        else:
            with st.spinner("Testing the connection…"):
                ok, msg = feat_db.test_connection(db_type, params=params)
            if ok:
                st.success(msg)
                connected = True
                st.session_state[DB_CONN_KEY] = params
            else:
                st.error(msg)
    elif st.session_state.get(DB_CONN_KEY):
        # A successful test earlier this session — offer the tables again.
        connected = True
        params = st.session_state[DB_CONN_KEY]
    if connected:
        try:
            tables = feat_db.list_tables(db_type, params=params)
        except Exception as e:  # noqa: BLE001 - show the error, don't crash
            st.error(f"Could not list the tables in '{database}': {e}")
            tables = []
        if tables:
            table = st.selectbox("Table", tables, key="e_db_table_pick")
            if st.button("Load table", key="e_db_load"):
                try:
                    with st.spinner(f"Loading {table}…"):
                        df = feat_db.load_table(db_type, params=params,
                                                table=table)
                    st.success(f"Loaded {len(df):,} rows from {table}.")
                    return df, f"{db_type} : {table}"
                except Exception as e:  # noqa: BLE001
                    st.error(f"Could not load that table: {e}")
        else:
            st.info(f"Connected to '{database}', but it has no tables to "
                    "load.")

    details = db_connection_details(db_type, host, port, database, "", "")
    if details["host"] and details["database"]:
        st.download_button(
            "Download connection details (.json)",
            json.dumps(details, indent=2).encode("utf-8"),
            file_name="db_connection.json", mime="application/json",
            key="e_db_dl",
            help="Server, port, database — never the password.")
    return None, None


def render_column_charts(st, df):
    """Preview tab: one small chart per column.

    Numeric columns (cap 6): histogram. Small category columns
    (cap 4, <= 10 unique values): bar chart of value counts.
    """
    if df is None or len(df) == 0:
        return
    st.subheader("Column charts")
    num_cols = engine.numeric_cols(df)[:6]
    for col in num_cols:
        st.write(f"**{engine._pretty(col)}** — distribution")
        chart = (alt.Chart(df)
                 .mark_bar(color="#117f50")
                 .encode(x=alt.X(col, bin=True,
                                 title=engine._pretty(col)),
                         y=alt.Y("count()", title="Rows"),
                         tooltip=["count()"])
                 .properties(height=200)
                 .configure_axis(labelColor="#696969", titleColor="#030303")
                 .configure_view(stroke="#e8e8e8"))
        st.altair_chart(chart, width="stretch")
    cat_cols = [c for c in df.columns
                if str(df[c].dtype) in ("object", "str")
                and 1 < df[c].nunique(dropna=True) <= 10][:4]
    for col in cat_cols:
        counts = (df[col].astype(str).value_counts(dropna=False)
                  .reset_index())
        counts.columns = ["value", "count"]
        st.write(f"**{engine._pretty(col)}** — value counts")
        chart = (alt.Chart(counts)
                 .mark_bar(color="#117f50")
                 .encode(x=alt.X("value:N", title=engine._pretty(col),
                                 sort="-y"),
                         y=alt.Y("count:Q", title="Rows"),
                         tooltip=["value", "count"])
                 .properties(height=200)
                 .configure_axis(labelColor="#696969", titleColor="#030303")
                 .configure_view(stroke="#e8e8e8"))
        st.altair_chart(chart, width="stretch")
