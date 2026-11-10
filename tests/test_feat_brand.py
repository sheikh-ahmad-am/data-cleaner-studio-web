"""Group B (v1.4) — white-label brand tests + branded exports.

Run from the project root:  .test-venv-brand/bin/python tests/test_feat_brand.py
No Streamlit app needed — render functions run against a FakeSt.
Brand files live in a temp folder (base_dir), never the real app folder.
No network call is ever made.
"""

import datetime
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import engine
import feat_brand
import feat_share
import pptx_writer

BRAND = {"name": "Acmecorp Analytics", "accent": "#ff8800", "logo": None}
PNG_BYTES = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)


def _sample_clean():
    raw = Path(__file__).resolve().parent.parent / "sample_data" / "messy_sales.csv"
    raw_df = engine.load_file("messy_sales.csv", raw.read_bytes())
    clean, actions = engine.clean(raw_df)
    return raw_df, clean, actions, engine.auto_kpis(clean)


def _grouped(clean):
    return (clean.groupby("category", dropna=False)["unit_price"].sum()
            .reset_index().sort_values("unit_price", ascending=False))


class FakeSt:
    """Minimal stand-in for the Streamlit module for render tests."""

    def __init__(self, values=None):
        self.values = values or {}
        self.session_state = {}
        self.calls = []
        self.downloads = []

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

    def success(self, text):
        self._rec("success", text)

    def error(self, text):
        self._rec("error", text)

    def markdown(self, text, unsafe_allow_html=None):
        self._rec("markdown", text)

    def text_input(self, label, key=None, value="", placeholder=None,
                   help=None, type=None):
        self._rec("text_input", label, key)
        return self.values.get(key, value)

    def color_picker(self, label, key=None, value="#6fff54", help=None):
        self._rec("color_picker", label, key)
        return self.values.get(key, value)

    def file_uploader(self, label, key=None, type=None, help=None):
        self._rec("file_uploader", label, key)
        return self.values.get(key)

    def button(self, label, key=None, **kw):
        self._rec("button", label, key)
        return self.values.get(key, False)

    def rerun(self):
        self._rec("rerun")

    def container(self, border=None):
        self._rec("container")

        class _Ctx:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _Ctx()

    def columns(self, spec):
        self._rec("columns")

        class _Ctx:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return [_Ctx() for _ in spec]

    def download_button(self, label, data, file_name=None, mime=None,
                        key=None, help=None):
        self._rec("download_button", label)
        self.downloads.append({"label": label, "data": data,
                               "file_name": file_name, "mime": mime})
        return False

    def messages(self, method):
        return [c[1] for c in self.calls if c[0] == method]

    def keys_used(self):
        """Every widget key the render code asked for."""
        return [c[2] for c in self.calls
                if len(c) > 2 and isinstance(c[2], str) and c[2].startswith("brand_")]


class FakeUpload:
    def __init__(self, raw: bytes):
        self._raw = raw

    def getvalue(self):
        return self._raw


# ------------------------------------------------------------------ brand
def test_brand_defaults_and_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        # Nothing saved yet: the plain defaults.
        brand = feat_brand.load_brand(tmp)
        assert brand == {"name": "Data Cleaner Studio",
                         "accent": "#117f50", "logo": None}, brand
        assert (Path(tmp) / "brand.json").exists() is False, \
            "loading must not create the file"
        # Save + load round-trip.
        saved = feat_brand.save_brand(BRAND, tmp)
        assert saved == BRAND, saved
        assert json.loads((Path(tmp) / "brand.json").read_text()) == BRAND
        assert feat_brand.load_brand(tmp) == BRAND
        # A name with only spaces and a bad accent fall back to defaults.
        saved = feat_brand.save_brand(
            {"name": "   ", "accent": "not-a-colour", "logo": None}, tmp)
        assert saved["name"] == "Data Cleaner Studio"
        assert saved["accent"] == "#117f50"
        # A broken brand.json also falls back to the defaults.
        (Path(tmp) / "brand.json").write_text("{not json", encoding="utf-8")
        assert feat_brand.load_brand(tmp)["name"] == "Data Cleaner Studio"
        # Unknown extra keys are dropped, not carried along.
        (Path(tmp) / "brand.json").write_text(
            json.dumps({"name": "X", "accent": "#123456", "logo": None,
                        "surprise": 1}), encoding="utf-8")
        assert feat_brand.load_brand(tmp) == {"name": "X", "accent": "#123456",
                                              "logo": None}
    print("brand defaults + round-trip OK: save/load identical, bad file -> defaults")


def test_logo_save_and_exports_dict():
    with tempfile.TemporaryDirectory() as tmp:
        feat_brand.save_brand(BRAND, tmp)
        # Raw bytes.
        path = feat_brand.save_logo(PNG_BYTES, tmp)
        assert Path(path).name == "logo.png" and Path(path).exists()
        assert Path(path).read_bytes() == PNG_BYTES
        assert feat_brand.load_brand(tmp)["logo"] == "logo.png"
        # A Streamlit-style upload (has .getvalue()).
        feat_brand.save_logo(FakeUpload(PNG_BYTES + b"more"), tmp)
        assert Path(tmp, "logo.png").read_bytes() == PNG_BYTES + b"more"
        # brand_for_exports resolves the logo to a real path.
        out = feat_brand.brand_for_exports(tmp)
        assert out == {"name": "Acmecorp Analytics", "accent": "#ff8800",
                       "logo": str(Path(tmp) / "logo.png")}, out
        assert Path(out["logo"]).exists()
        # No logo saved: logo is None, name/accent still have values.
        with tempfile.TemporaryDirectory() as tmp2:
            out = feat_brand.brand_for_exports(tmp2)
            assert out == {"name": "Data Cleaner Studio", "accent": "#117f50",
                           "logo": None}, out
        # A logo recorded in brand.json but deleted from disk -> None.
        (Path(tmp) / "logo.png").unlink()
        assert feat_brand.brand_for_exports(tmp)["logo"] is None
        # Empty logo bytes are rejected, not saved as a 0-byte file.
        try:
            feat_brand.save_logo(b"", tmp)
        except ValueError as e:
            assert "empty" in str(e).lower()
        else:
            raise AssertionError("empty logo bytes must raise ValueError")
    print("logo OK: bytes + upload object saved as logo.png, exports dict "
          "resolves the path, missing logo -> None")


def test_brand_css():
    css = feat_brand.brand_css("#ff8800")
    assert css.startswith("<style>") and "</style>" in css
    assert "#ff8800" in css, "CSS must contain the accent"
    assert "button" in css.lower()
    # Default accent, and an invalid accent falls back to the default.
    assert "#6fff54" in feat_brand.brand_css("#6fff54")
    assert "#117f50" in feat_brand.brand_css("banana")
    assert "banana" not in feat_brand.brand_css("banana")
    print("brand CSS OK: custom accent in <style>, invalid accent -> #117f50")


def test_render_brand_section():
    with tempfile.TemporaryDirectory() as tmp:
        # Nothing pressed: shows the section, returns the current brand.
        st = FakeSt()
        out = feat_brand.render_brand_section(st, tmp)
        assert out == {"name": "Data Cleaner Studio", "accent": "#117f50",
                       "logo": None}, out
        # The section title is a settings row now (the Settings page's
        # section heading above the card carries "Your brand"); the
        # rows are "Brand name" / "Accent colour" / "Logo".
        assert any("Brand name" in m for m in st.messages("markdown")), \
            "brand name row missing"
        assert all(k.startswith("brand_") for k in st.keys_used()), st.calls
        assert "brand_name_0" in st.keys_used() and "brand_accent_0" in st.keys_used()
        assert "brand_logo_0" in st.keys_used() and "brand_save" in st.keys_used()
        assert "brand_cancel" in st.keys_used(), "Cancel button missing"
        assert any("#117f50" in m for m in st.messages("markdown")), \
            "current brand CSS must be injected"
        # Save pressed with a new name, colour and logo upload.
        st = FakeSt(values={"brand_name_0": "Acmecorp Analytics",
                            "brand_accent_0": "#ff8800",
                            "brand_logo_0": FakeUpload(PNG_BYTES),
                            "brand_save": True})
        out = feat_brand.render_brand_section(st, tmp)
        assert out["name"] == "Acmecorp Analytics"
        assert out["accent"] == "#ff8800" and out["logo"] == "logo.png"
        assert feat_brand.load_brand(tmp) == out
        assert (Path(tmp) / "logo.png").exists()
        assert any("Acmecorp" in m for m in st.messages("success"))
        # Cancel pressed with changed inputs: nothing is saved; the
        # press bumps the generation counter and reruns, and the NEXT
        # render remounts the inputs under fresh keys, so they come
        # back from the saved brand. Two renders, the way Streamlit
        # runs it: a plain pop of the widget keys does not clear a
        # text input's displayed text in a live browser (probe50 +
        # the minimal clear-repro proved it); only a key change
        # remounts the input.
        feat_brand.save_brand(BRAND, tmp)
        st = FakeSt(values={"brand_name_0": "Changed Name",
                            "brand_accent_0": "#000000",
                            "brand_cancel": True})
        st.session_state.update({"brand_name_0": "Changed Name",
                                 "brand_accent_0": "#000000"})
        out = feat_brand.render_brand_section(st, tmp)
        assert out == BRAND, out
        assert feat_brand.load_brand(tmp) == BRAND, \
            "Cancel must not write brand.json"
        assert st.session_state.get("brand_gen") == 1, \
            "Cancel must bump the generation counter"
        assert any(c[0] == "rerun" for c in st.calls), \
            "Cancel must rerun so the inputs come back from the saved brand"
        # The rerun: inputs remount under fresh keys and render from
        # the saved brand; the old keys are dropped.
        st2 = FakeSt(values={})
        st2.session_state.update(st.session_state)
        out2 = feat_brand.render_brand_section(st2, tmp)
        assert out2 == BRAND, out2
        assert "brand_name_0" not in st2.session_state, \
            "the rerun must drop the old input keys"
        assert "brand_accent_0" not in st2.session_state
        assert "brand_name_1" in st2.keys_used(), \
            "the rerun must mount the inputs under the new generation"
    print("render brand OK: brand_* keys only, save writes brand.json + logo.png, cancel discards")


# ------------------------------------------------------- branded exports
def test_html_dashboard_brand():
    _, clean, actions, kpis = _sample_clean()
    grouped = _grouped(clean)
    # brand=None: exactly as before.
    plain = feat_share.html_dashboard_bytes(
        kpis, actions, grouped, "category", "unit_price").decode("utf-8")
    assert "Data Cleaner Studio — Dashboard" in plain
    assert "Generated by Data Cleaner Studio." in plain
    assert "#117f50" in plain
    # brand given: name replaces the title + footer, accent recolours.
    branded = feat_share.html_dashboard_bytes(
        kpis, actions, grouped, "category", "unit_price",
        brand=BRAND).decode("utf-8")
    assert "Acmecorp Analytics — Dashboard" in branded
    assert "Data Cleaner Studio" not in branded, \
        "no trace of the old name may survive in a branded export"
    assert "Generated by Acmecorp Analytics." in branded
    assert "#ff8800" in branded and 'fill="#ff8800"' in branded, \
        "accent must recolour the headings and the SVG bars"
    assert "207,992.00" in branded, "KPIs must survive branding"
    # An explicit custom title is branded too.
    custom = feat_share.html_dashboard_bytes(
        kpis, actions, grouped, "category", "unit_price",
        title="Data Cleaner Studio — Weekly", brand=BRAND).decode("utf-8")
    assert "Acmecorp Analytics — Weekly" in custom
    # render pass-through keeps brand=None working.
    st = FakeSt()
    feat_share.render_html_download(st, kpis, actions, grouped,
                                    "category", "unit_price")
    assert st.downloads[0]["file_name"] == "dashboard.html"
    assert b"Data Cleaner Studio" in st.downloads[0]["data"]
    print("HTML dashboard brand OK: None unchanged, brand swaps title/footer/accent")


def test_pdf_brand():
    kpis = [{"label": "Rows", "value": "77"},
            {"label": "Total unit_price", "value": "207,992.00"}]
    actions = [("Rows", "80 -> 77 rows"),
               ("Drop duplicate rows", "3 row(s) removed")]
    summary = "Rows: 80 loaded -> 77 after cleaning."
    # brand=None: exactly as before.
    plain = engine.to_pdf_bytes("Data Cleaner Studio — Report", kpis,
                                actions, summary)
    assert plain[:5] == b"%PDF-"
    # brand given: name replaces the title; the PDF stays valid.
    branded = engine.to_pdf_bytes("Data Cleaner Studio — Report", kpis,
                                  actions, summary, brand=BRAND)
    assert branded[:5] == b"%PDF-" and len(branded) > 500
    from pypdf import PdfReader
    plain_text = "\n".join((p.extract_text() or "")
                           for p in PdfReader(io.BytesIO(plain)).pages)
    branded_text = "\n".join((p.extract_text() or "")
                             for p in PdfReader(io.BytesIO(branded)).pages)
    assert "Data Cleaner Studio" in plain_text
    assert "Acmecorp Analytics" in branded_text, branded_text
    assert "Report" in branded_text
    assert "Data Cleaner Studio" not in branded_text
    assert "Generated by Acmecorp Analytics." in branded_text
    assert "207,992.00" in branded_text, "KPIs must survive branding"
    # The branded PDF carries the accent as a header band (a fill rect
    # in the page content stream), the plain one carries no such band.
    assert b"1.000 0.533 0.000 rg" in branded, \
        "accent #ff8800 must appear as an RGB fill in the branded PDF"
    assert b"1.000 0.533 0.000 rg" not in plain
    print("PDF brand OK: None unchanged, brand swaps title/footer + accent band")


def test_pptx_brand():
    _, clean, actions, kpis = _sample_clean()
    summary = "Rows: 80 loaded -> 77 after cleaning."
    # brand=None: exactly as before.
    plain = pptx_writer.to_pptx_bytes("Data Cleaner Studio — Report",
                                      kpis, actions, summary, table_df=clean)
    assert plain[:2] == b"PK"
    # brand given: name replaces the title on slide 1, file stays valid.
    branded = pptx_writer.to_pptx_bytes("Data Cleaner Studio — Report",
                                        kpis, actions, summary,
                                        table_df=clean, brand=BRAND)
    assert branded[:2] == b"PK"
    from pptx import Presentation
    for data, want_name, want_slides in (
            (plain, "Data Cleaner Studio — Report", 2),
            (branded, "Acmecorp Analytics — Report", 2)):
        prs = Presentation(io.BytesIO(data))
        assert len(prs.slides) == want_slides
        joined = "\n".join(sh.text for s in prs.slides for sh in s.shapes
                           if sh.has_text_frame)
        assert want_name in joined, joined
        assert "207,992.00" in joined
    plain_joined = "\n".join(
        sh.text for s in Presentation(io.BytesIO(plain)).slides
        for sh in s.shapes if sh.has_text_frame)
    branded_joined = "\n".join(
        sh.text for s in Presentation(io.BytesIO(branded)).slides
        for sh in s.shapes if sh.has_text_frame)
    assert "Data Cleaner Studio" not in branded_joined
    assert "Generated by Acmecorp Analytics." in branded_joined
    # The accent colour lands in the slide XML as the title colour.
    slide_xml = zipfile.ZipFile(io.BytesIO(branded)).read(
        "ppt/slides/slide1.xml").decode("utf-8")
    assert "FF8800" in slide_xml, "accent must colour the PPTX title"
    assert "FF8800" not in zipfile.ZipFile(io.BytesIO(plain)).read(
        "ppt/slides/slide1.xml").decode("utf-8")
    print("PPTX brand OK: None unchanged, brand swaps title/footer + accent")


if __name__ == "__main__":
    test_brand_defaults_and_roundtrip()
    test_logo_save_and_exports_dict()
    test_brand_css()
    test_render_brand_section()
    test_html_dashboard_brand()
    test_pdf_brand()
    test_pptx_brand()
    print("ALL BRAND TESTS PASSED")
