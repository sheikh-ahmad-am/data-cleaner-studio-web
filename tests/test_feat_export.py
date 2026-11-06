"""Group 4 (export & connect) tests.

Run from the project root:  .test-venv/bin/python tests/test_feat_export.py
No Streamlit app needed — render functions run against a FakeSt.
Real behaviour asserted: PPTX opens in python-pptx, email builds with a
PDF attachment, charts build on the sample, Sheets creds validation.
No real email is ever sent and no network call is ever made.
"""

import datetime
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import altair as alt
import pandas as pd

import engine
import feat_export
import pptx_writer


# ------------------------------------------------------------------ helpers
def _sample_clean():
    raw = Path(__file__).resolve().parent.parent / "sample_data" / "messy_sales.csv"
    df = engine.load_file("messy_sales.csv", raw.read_bytes())
    clean, actions = engine.clean(df)
    return df, clean, actions, engine.auto_kpis(clean)


class FakeSt:
    """Minimal stand-in for the Streamlit module for render tests."""

    def __init__(self, values=None, upload=None):
        self.values = values or {}
        self.upload = upload
        self.session_state = {}
        self.calls = []          # (method, *args) for every call
        self.downloads = []      # kwargs of download_button calls
        self.charts = []         # charts passed to altair_chart

    def _rec(self, method, *args):
        self.calls.append((method,) + args)

    def subheader(self, text):
        self._rec("subheader", text)

    def write(self, text):
        self._rec("write", text)

    def info(self, text):
        self._rec("info", text)

    def warning(self, text):
        self._rec("warning", text)

    def caption(self, text):
        self._rec("caption", text)

    def success(self, text):
        self._rec("success", text)

    def error(self, text):
        self._rec("error", text)

    def markdown(self, text):
        self._rec("markdown", text)

    def file_uploader(self, label, type=None, key=None, help=None):
        self._rec("file_uploader", label)
        return self.upload

    def text_input(self, label, key=None, value="", placeholder=None,
                   help=None, type=None):
        self._rec("text_input", label)
        return self.values.get(key, value)

    def text_area(self, label, key=None, value="", placeholder=None, help=None):
        self._rec("text_area", label)
        return self.values.get(key, value)

    def checkbox(self, label, key=None, value=False, help=None):
        self._rec("checkbox", label)
        return self.values.get(key, value)

    def selectbox(self, label, options, key=None, **kw):
        self._rec("selectbox", label)
        return self.values.get(key, options[0])

    def time_input(self, label, key=None, value=None):
        self._rec("time_input", label)
        return self.values.get(key, value)

    def button(self, label, key=None, **kw):
        self._rec("button", label)
        return self.values.get(key, False)

    def download_button(self, label, data, file_name=None, mime=None,
                        key=None, help=None):
        self._rec("download_button", label)
        self.downloads.append({"label": label, "data": data,
                               "file_name": file_name, "mime": mime})
        return False

    def altair_chart(self, chart, width=None):
        self._rec("altair_chart")
        self.charts.append(chart)

    def messages(self, method):
        return [c[1] for c in self.calls if c[0] == method]


class FakeUpload:
    def __init__(self, raw: bytes):
        self._raw = raw

    def getvalue(self):
        return self._raw


# -------------------------------------------------------------------- pptx
def test_pptx_opens():
    df, clean, actions, kpis = _sample_clean()
    assert (len(df), len(clean)) == (80, 77), "sample must clean 80 -> 77"
    data = pptx_writer.to_pptx_bytes(
        "Data Cleaner Studio — Report", kpis, actions,
        f"Rows: {len(df):,} loaded -> {len(clean):,} after cleaning.",
        table_df=clean)
    assert data[:2] == b"PK", "must be a zip (pptx) file"
    parts = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
    for needed in ("[Content_Types].xml", "_rels/.rels",
                   "ppt/presentation.xml", "ppt/slides/slide1.xml",
                   "ppt/slides/slide2.xml",
                   "ppt/slideMasters/slideMaster1.xml",
                   "ppt/slideLayouts/slideLayout1.xml",
                   "ppt/theme/theme1.xml"):
        assert needed in parts, f"missing part {needed}"
    from pptx import Presentation
    prs = Presentation(io.BytesIO(data))
    assert len(prs.slides) >= 1
    assert len(prs.slides) == 2, "table_df must add a second slide"
    texts = [sh.text for s in prs.slides for sh in s.shapes
             if sh.has_text_frame]
    joined = "\n".join(texts)
    assert "Data Cleaner Studio — Report" in joined, "title missing"
    assert "78,323.0" in joined, "Total unit_price KPI missing"
    assert "Electronics (33)" in joined, "Top category KPI missing"
    assert "80 -> 77 rows" in joined, "cleaning log missing"
    table = next(sh.table for s in prs.slides for sh in s.shapes
                 if sh.has_table)
    assert len(table.rows) == 9, "header + 8 data rows"
    assert len(table.columns) == 6, "max 6 columns"
    assert [c.text for c in table.rows[0].cells][:3] == [
        "order_id", "order_date", "customer"]
    print("pptx OK: 2 slides, title + KPIs + log + 9x6 table")


def test_pptx_no_table():
    data = pptx_writer.to_pptx_bytes("T", [], [], "S")
    from pptx import Presentation
    prs = Presentation(io.BytesIO(data))
    assert len(prs.slides) == 1
    texts = [sh.text for sh in prs.slides[0].shapes if sh.has_text_frame]
    assert "T" in "\n".join(texts) and "Nothing cleaned yet." in "\n".join(texts)
    print("pptx no-table OK: 1 slide, empty KPIs/actions handled")


def test_no_forbidden_imports():
    root = Path(__file__).resolve().parent.parent
    for name in ("pptx_writer.py", "feat_export.py"):
        src = (root / name).read_text()
        for bad in ("import pptx", "from pptx import",
                    "import mysql.connector", "import psycopg2",
                    "import sqlalchemy", "import googleapiclient",
                    "from google"):
            assert bad not in src, f"{name} must not contain {bad!r}"
    print("no forbidden imports OK (stdlib/pandas/numpy/streamlit/altair only)")


# ------------------------------------------------------------ sheets creds
def test_sheets_creds():
    good = json.dumps({"client_email": "x@project.iam.gserviceaccount.com",
                       "private_key": "-----BEGIN PRIVATE KEY-----\nabc"}).encode()
    ok, msg = feat_export.validate_sheets_creds(good)
    assert ok and "pending" in msg.lower(), msg
    assert "Sheets API client is not installed" in msg
    ok, msg = feat_export.validate_sheets_creds(
        json.dumps({"client_email": "x@y.z"}).encode())
    assert not ok and "private_key" in msg
    ok, msg = feat_export.validate_sheets_creds(b"not json at all")
    assert not ok and "not valid JSON" in msg
    ok, msg = feat_export.validate_sheets_creds({"private_key": "k"})
    assert not ok and "client_email" in msg
    print("sheets creds OK: valid -> honest pending; bad files rejected")


# ------------------------------------------------------------------- email
def test_email_message():
    pdf = engine.to_pdf_bytes("T", [{"label": "Rows", "value": "77"}],
                              [("Rows", "80 -> 77 rows")], "summary")
    msg = feat_export.build_email_message(
        "sender@example.com", "me@example.com",
        "Data Cleaner Studio — daily report",
        "Your report is attached.\n\nsummary", pdf)
    assert msg["From"] == "sender@example.com"
    assert msg["To"] == "me@example.com"
    assert msg["Subject"] == "Data Cleaner Studio — daily report"
    atts = [p for p in msg.iter_attachments()]
    assert len(atts) == 1, "exactly one attachment"
    att = atts[0]
    assert att.get_content_type() == "application/pdf"
    assert att.get_filename() == "report.pdf"
    assert att.get_payload(decode=True) == pdf, "attached bytes must be the PDF"
    assert "summary" in msg.get_body().get_content()
    print("email message OK: headers + PDF attachment, no sending")


# ---------------------------------------------------------------------- db
def test_db_driver_and_details():
    # v1.4: the check must report HONESTLY — installed where the driver
    # is present (MySQL in this venv, from the bundled wheel), missing
    # where it is not. It must never claim a driver that is absent.
    _key = {"MySQL": "mysql", "PostgreSQL": "postgres",
            "SQL Server": "sqlserver"}
    import feat_db
    for dbt in ("MySQL", "PostgreSQL", "SQL Server"):
        ok, msg = feat_export.check_db_driver(dbt)
        assert ok == feat_db.db_driver_status()[_key[dbt]], \
            f"{dbt} check must match the real import: {msg}"
        if ok:
            assert "is installed" in msg, msg
        else:
            assert "NOT installed" in msg and "portable build" in msg, msg
    d = feat_export.db_connection_details(
        "MySQL", "db.example.com", "3306", "sales", "orders", "")
    assert d == {"type": "MySQL", "host": "db.example.com", "port": "3306",
                 "database": "sales", "table": "orders", "query": ""}
    assert "password" not in json.dumps(d).lower()
    print("db OK: drivers honestly absent; details never carry a password")


# ------------------------------------------------------------------- charts
def test_heatmap_corr():
    _, clean, _, _ = _sample_clean()
    chart = feat_export.heatmap_corr(clean)
    assert isinstance(chart, alt.Chart)
    chart.to_dict()  # must serialise without error
    data = chart.data
    assert len(data) == 4, "2 numeric cols -> 2x2 matrix"
    assert set(data["column1"]) == {"quantity", "unit_price"}
    assert data["corr"].between(-1, 1).all()
    assert abs(data.loc[(data.column1 == "quantity")
                        & (data.column2 == "quantity"), "corr"].iloc[0]
               - 1.0) < 1e-9, "diagonal must be 1"
    print("heatmap OK: 2x2 matrix, diagonal 1")


def test_treemap_chart():
    _, clean, _, _ = _sample_clean()
    chart = feat_export.treemap_chart(clean, "category", "unit_price")
    assert isinstance(chart, alt.Chart)
    chart.to_dict()
    data = chart.data
    assert len(data) == 4, "4 categories"
    areas = (data["x2"] - data["x"]) * (data["y2"] - data["y"])
    assert abs(areas.sum() - 100 * 60) < 1e-6, "rects must fill 100x60"
    assert (data["x2"] > data["x"]).all() and (data["y2"] > data["y"]).all()
    assert data["x"].min() >= 0 and data["x2"].max() <= 100 + 1e-9
    assert data["y"].min() >= 0 and data["y2"].max() <= 60 + 1e-9
    assert data.loc[data["value"].idxmax(), "category"] == "Electronics"
    print("treemap OK: 4 rects fill the frame, biggest = Electronics")


def test_funnel_chart():
    _, clean, _, _ = _sample_clean()
    chart = feat_export.funnel_chart(clean, "category", "unit_price")
    assert isinstance(chart, alt.Chart)
    chart.to_dict()
    data = chart.data
    assert list(data["category"]) == list(
        data.sort_values("value", ascending=False)["category"])
    assert (data["x"] == -data["value"] / 2).all(), "bars must be centred"
    assert (data["x2"] == data["value"] / 2).all()
    assert data.iloc[0]["category"] == "Electronics"
    print("funnel OK: centred bars, descending, Electronics on top")


def test_squarify_layout_pure():
    rects = feat_export._squarify_layout([50, 30, 20], 0, 0, 100, 60)
    assert len(rects) == 3
    total = sum(w * h for _, _, w, h in rects)
    assert abs(total - 6000) < 1e-6
    print("squarify OK: areas preserved")


# ------------------------------------------------------------------ renders
def test_render_column_charts():
    _, clean, _, _ = _sample_clean()
    st = FakeSt()
    feat_export.render_column_charts(st, clean)
    # 2 numeric histograms + 4 category bar charts (cap 4)
    assert len(st.charts) == 6, f"expected 6 charts, got {len(st.charts)}"
    for c in st.charts:
        assert isinstance(c, alt.Chart)
        c.to_dict()
    print("column charts OK: 6 charts rendered via FakeSt")


def test_render_pptx_download():
    _, clean, actions, kpis = _sample_clean()
    st = FakeSt()
    feat_export.render_pptx_download(st, kpis, actions, clean, clean)
    assert len(st.downloads) == 1
    dl = st.downloads[0]
    assert dl["file_name"] == "report.pptx"
    assert dl["data"][:2] == b"PK"
    print("pptx download render OK")


def test_render_sheets_export():
    _, clean, _, _ = _sample_clean()
    good = FakeUpload(json.dumps(
        {"client_email": "x@y.z", "private_key": "k"}).encode())
    st = FakeSt(upload=good)
    feat_export.render_sheets_export(st, clean)
    assert any("pending" in m.lower() for m in st.messages("success")), \
        "valid creds must get the honest pending message, never fake success"
    assert not st.messages("error")
    st2 = FakeSt(upload=FakeUpload(b"nope"))
    feat_export.render_sheets_export(st2, clean)
    assert st2.messages("error"), "invalid JSON must error"
    print("sheets render OK: valid -> pending, invalid -> error")


def test_render_email_schedule_saves_no_password():
    _, clean, actions, kpis = _sample_clean()
    st = FakeSt(values={
        "e_email_server": "smtp.gmail.com", "e_email_port": "587",
        "e_email_user": "a@b.com", "e_email_pass": "s3cret",
        "e_email_recipient": "c@d.com", "e_email_enable": True,
        "e_email_time": datetime.time(9, 0),
    })
    feat_export.render_email_schedule(st, kpis, actions, clean, clean)
    sched = st.session_state.get("e_email_sched")
    assert sched is not None, "schedule must be stored when enabled + filled"
    assert sched["server"] == "smtp.gmail.com" and sched["time"] == "09:00"
    assert "password" not in json.dumps(sched).lower()
    assert "s3cret" not in json.dumps(sched)
    assert any("never stored" in m for m in st.messages("success"))
    print("email schedule OK: stored without password")


def test_render_db_connect():
    st = FakeSt(values={
        "e_db_type": "MySQL", "e_db_host": "db.example.com",
        "e_db_port": "3306", "e_db_user": "root", "e_db_pass": "pw",
        "e_db_name": "sales", "e_db_table": "orders",
    })
    feat_export.render_db_connect(st)
    assert len(st.downloads) == 1, "JSON download offered when host+db filled"
    details = json.loads(st.downloads[0]["data"])
    assert details["host"] == "db.example.com"
    assert "password" not in json.dumps(details).lower()
    assert "pw" not in json.dumps(details)
    # Test-connection button reports honestly, never a fake success.
    st2 = FakeSt(values={"e_db_test": True, "e_db_type": "PostgreSQL"})
    feat_export.render_db_connect(st2)
    assert any("NOT installed" in m for m in st2.messages("error")), \
        st2.calls
    assert not st2.messages("success")
    print("db connect render OK: honest driver message + password-free JSON")


if __name__ == "__main__":
    test_pptx_opens()
    test_pptx_no_table()
    test_no_forbidden_imports()
    test_sheets_creds()
    test_email_message()
    test_db_driver_and_details()
    test_heatmap_corr()
    test_treemap_chart()
    test_funnel_chart()
    test_squarify_layout_pure()
    test_render_column_charts()
    test_render_pptx_download()
    test_render_sheets_export()
    test_render_email_schedule_saves_no_password()
    test_render_db_connect()
    print("ALL GROUP 4 TESTS PASSED")
