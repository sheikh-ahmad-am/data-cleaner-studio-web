"""Hand-rolled PPTX writer for Data Cleaner Studio — stdlib only.

Builds a real .pptx (a zip of OOXML parts) using only ``zipfile`` and
string building. No python-pptx import: python-pptx is NOT in the embedded
Windows Python that ships in the .exe, so the shipped code must not need it.

Layout:
  slide 1 — title, summary line, KPI bullets, cleaning-log bullets
  slide 2 — only when ``table_df`` is given: a simple table of the first
            ~8 rows (max 6 columns so it fits the slide)

Validation (in the tests, using python-pptx from the TEST venv only):
the bytes must open in python-pptx, have >= 1 slide, and contain the title.
"""

import io
import zipfile
from xml.sax.saxutils import escape as _xml_escape

EMU_PER_INCH = 914400
SLIDE_W = int(13.333 * EMU_PER_INCH)   # 12192000
SLIDE_H = int(7.5 * EMU_PER_INCH)      # 6858000
MARGIN = int(0.5 * EMU_PER_INCH)       # 457200

_NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _esc(text) -> str:
    """XML-escape text and strip control characters PowerPoint rejects."""
    s = str(text)
    s = "".join(ch for ch in s if ch in ("\n", "\t") or ord(ch) >= 32)
    return _xml_escape(s)


def _para(text, size=12, bold=False, color=None, space_before=0):
    """One <a:p> paragraph. Bullets are a literal bullet prefix (robust)."""
    attrs = f' lang="en-GB" sz="{int(size * 100)}"'
    if bold:
        attrs += ' b="1"'
    inner = ""
    if color:
        inner = f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
    inner += '<a:latin typeface="Calibri"/>'
    rpr = f"<a:rPr{attrs}>{inner}</a:rPr>"
    ppr = ""
    if space_before:
        ppr = f'<a:pPr><a:spcBef><a:spcPts val="{space_before}"/></a:spcBef></a:pPr>'
    return (f"<a:p>{ppr}<a:r>{rpr}"
            f"<a:t>{_esc(text)}</a:t></a:r></a:p>")


def _textbox(shape_id, name, x, y, cx, cy, paras):
    """One <p:sp> text box holding the given paragraph XML strings."""
    body = "".join(paras)
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="{_esc(name)}"/>'
        f'<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/>'
        f'<a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        f'<p:txBody><a:bodyPr wrap="square"/><a:lstStyle/>{body}'
        f'</p:txBody></p:sp>'
    )


def _table_cell(text, size=11, bold=False, fill=None, color=None):
    """One <a:tc> table cell."""
    attrs = f' lang="en-GB" sz="{int(size * 100)}"'
    if bold:
        attrs += ' b="1"'
    inner = ""
    if color:
        inner = (f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>')
    inner += '<a:latin typeface="Calibri"/>'
    rpr = f"<a:rPr{attrs}>{inner}</a:rPr>"
    tcpr = ""
    if fill:
        tcpr = (f'<a:tcPr><a:solidFill><a:srgbClr val="{fill}"/>'
                f'</a:solidFill></a:tcPr>')
    return (
        f'<a:tc><a:txBody><a:bodyPr/><a:lstStyle/>'
        f'<a:p><a:r>{rpr}<a:t>{_esc(text)}</a:t></a:r></a:p>'
        f'</a:txBody>{tcpr}</a:tc>'
    )


def _table_frame(shape_id, x, y, cx, columns, rows):
    """A <p:graphicFrame> holding a simple <a:tbl>.

    ``columns``: header labels. ``rows``: list of row value lists.
    """
    ncols = len(columns)
    col_w = cx // max(ncols, 1)
    grid = "".join(f'<a:gridCol w="{col_w}"/>' for _ in range(ncols))
    row_h = 320040  # ~0.35 inch
    header = "".join(
        _table_cell(c, size=11, bold=True, fill="1F3864", color="FFFFFF")
        for c in columns)
    body_rows = []
    for i, row in enumerate(rows):
        fill = "D9E2F3" if i % 2 else "FFFFFF"
        cells = "".join(
            _table_cell(v, size=11, fill=fill) for v in row)
        body_rows.append(f'<a:tr h="{row_h}">{cells}</a:tr>')
    total_h = row_h * (len(rows) + 1)
    return (
        f'<p:graphicFrame><p:nvGraphicFramePr>'
        f'<p:cNvPr id="{shape_id}" name="Table"/>'
        f'<p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>'
        f'<p:xfrm><a:off x="{x}" y="{y}"/>'
        f'<a:ext cx="{cx}" cy="{total_h}"/></p:xfrm>'
        f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/'
        f'drawingml/2006/table">'
        f'<a:tbl><a:tblPr firstRow="1" bandRow="1"/>'
        f'<a:tblGrid>{grid}</a:tblGrid>'
        f'<a:tr h="{row_h}">{header}</a:tr>'
        f'{"".join(body_rows)}</a:tbl>'
        f'</a:graphicData></a:graphic></p:graphicFrame>'
    )


def _slide_xml(shapes_xml):
    return (
        f'<p:sld xmlns:a="{_NS_A}" xmlns:r="{_NS_R}" xmlns:p="{_NS_P}">'
        f'<p:cSld><p:spTree>'
        f'<p:nvGrpSpPr><p:cNvPr id="1" name=""/>'
        f'<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        f'<p:grpSpPr><a:xfrm><a:off x="0" y="0"/>'
        f'<a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/>'
        f'<a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        f'{"".join(shapes_xml)}'
        f'</p:spTree></p:cSld>'
        f'<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'
    )


_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
</Types>"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>"""

_THEME = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="{_NS_A}" name="Office Theme"><a:themeElements>
<a:clrScheme name="Office">
<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>
<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>
<a:dk2><a:srgbClr val="1F497D"/></a:dk2>
<a:lt2><a:srgbClr val="EEECE1"/></a:lt2>
<a:accent1><a:srgbClr val="4F81BD"/></a:accent1>
<a:accent2><a:srgbClr val="C0504D"/></a:accent2>
<a:accent3><a:srgbClr val="9BBB59"/></a:accent3>
<a:accent4><a:srgbClr val="8064A2"/></a:accent4>
<a:accent5><a:srgbClr val="4BACC6"/></a:accent5>
<a:accent6><a:srgbClr val="F79646"/></a:accent6>
<a:hlink><a:srgbClr val="0000FF"/></a:hlink>
<a:folHlink><a:srgbClr val="800080"/></a:folHlink>
</a:clrScheme>
<a:fontScheme name="Office">
<a:majorFont><a:latin typeface="Calibri"/></a:majorFont>
<a:minorFont><a:latin typeface="Calibri"/></a:minorFont>
</a:fontScheme>
<a:fmtScheme name="Office">
<a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
<a:gradFill rotWithShape="1"><a:gsLst><a:gs pos="0"><a:schemeClr val="phClr"><a:tint val="50000"/></a:schemeClr></a:gs><a:gs pos="100000"><a:schemeClr val="phClr"><a:lumMod val="35000"/></a:schemeClr></a:gs></a:gsLst></a:gradFill>
<a:gradFill rotWithShape="1"><a:gsLst><a:gs pos="0"><a:schemeClr val="phClr"><a:tint val="80000"/></a:schemeClr></a:gs><a:gs pos="100000"><a:schemeClr val="phClr"><a:shade val="30000"/></a:schemeClr></a:gs></a:gsLst></a:gradFill></a:fillStyleLst>
<a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"><a:shade val="95000"/></a:schemeClr></a:solidFill></a:ln><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>
<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst><a:outerShdw blurRad="40000" dist="20000" dir="5400000" rotWithShape="0"><a:srgbClr val="000000"><a:alpha val="38000"/></a:srgbClr></a:outerShdw></a:effectLst></a:effectStyle></a:effectStyleLst>
<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
<a:gradFill rotWithShape="1"><a:gsLst><a:gs pos="0"><a:schemeClr val="phClr"><a:tint val="40000"/></a:schemeClr></a:gs><a:gs pos="40000"><a:schemeClr val="phClr"><a:tint val="45000"/></a:schemeClr></a:gs><a:gs pos="100000"><a:schemeClr val="phClr"><a:shade val="20000"/></a:schemeClr></a:gs></a:gsLst><a:lin ang="16200000" scaled="1"/></a:gradFill>
<a:gradFill rotWithShape="1"><a:gsLst><a:gs pos="0"><a:schemeClr val="phClr"><a:tint val="80000"/></a:schemeClr></a:gs><a:gs pos="100000"><a:schemeClr val="phClr"><a:shade val="30000"/></a:schemeClr></a:gs></a:gsLst><a:lin ang="16200000" scaled="1"/></a:gradFill></a:bgFillStyleLst>
</a:fmtScheme></a:themeElements></a:theme>"""

_SLIDE_MASTER = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="{_NS_A}" xmlns:r="{_NS_R}" xmlns:p="{_NS_P}">
<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>
<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
</p:spTree></p:cSld>
<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
<p:txStyles><p:titleStyle><a:lvl1pPr algn="l"><a:defRPr sz="3200"/></a:lvl1pPr></p:titleStyle>
<p:bodyStyle><a:lvl1pPr algn="l"><a:defRPr sz="1800"/></a:lvl1pPr></p:bodyStyle>
<p:otherStyle><a:defPPr><a:defRPr sz="1800"/></a:defPPr><a:lvl1pPr algn="l"><a:defRPr sz="1800"/></a:lvl1pPr></p:otherStyle>
</p:txStyles></p:sldMaster>"""

_SLIDE_LAYOUT = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="{_NS_A}" xmlns:r="{_NS_R}" xmlns:p="{_NS_P}" type="blank">
<p:cSld name="Blank"><p:spTree>
<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
</p:spTree></p:cSld>
<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>"""

_MASTER_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>"""

_LAYOUT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>"""

_SLIDE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>"""


def _presentation_xml(n_slides):
    sld_ids = "".join(
        f'<p:sldId id="{256 + i}" r:id="rId{2 + i}"/>'
        for i in range(n_slides))
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<p:presentation xmlns:a="{_NS_A}" xmlns:r="{_NS_R}" xmlns:p="{_NS_P}">'
        f'<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/>'
        f'</p:sldMasterIdLst>'
        f'<p:sldIdLst>{sld_ids}</p:sldIdLst>'
        f'<p:sldSz cx="{SLIDE_W}" cy="{SLIDE_H}"/>'
        f'<p:notesSz cx="6858000" cy="9144000"/></p:presentation>'
    )


def _presentation_rels(n_slides):
    rels = [
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/slideMaster" '
        'Target="slideMasters/slideMaster1.xml"/>'
    ]
    for i in range(n_slides):
        rels.append(
            f'<Relationship Id="rId{2 + i}" Type="http://schemas.openxmlformats.org/'
            f'officeDocument/2006/relationships/slide" '
            f'Target="slides/slide{i + 1}.xml"/>')
    body = "\n".join(rels)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        f'{body}\n</Relationships>'
    )


def _report_slide(title, kpis, actions, summary, brand=None):
    """Slide 1: title, summary, KPI bullets, cleaning-log bullets.

    ``brand`` is optional: None behaves exactly as before. A brand dict
    {"name", "accent", ...} replaces "Data Cleaner Studio" with the
    brand name in the title and footer, and colours the title with the
    accent colour."""
    brand_name = None
    accent_hex = None
    if isinstance(brand, dict):
        name = brand.get("name")
        if isinstance(name, str) and name.strip():
            brand_name = name.strip()
        accent = brand.get("accent")
        if (isinstance(accent, str) and len(accent.strip()) == 7
                and accent.strip().startswith("#")
                and all(c in "0123456789abcdefABCDEF"
                        for c in accent.strip()[1:])):
            accent_hex = accent.strip()[1:].upper()
    if brand_name:
        title = str(title).replace("Data Cleaner Studio", brand_name)
    title_color = accent_hex or "1F3864"
    paras = [_para(title, size=28, bold=True, color=title_color),
             _para("", size=11),
             _para(summary, size=13),
             _para("", size=11),
             _para("Key numbers", size=16, bold=True, space_before=6)]
    if kpis:
        for k in kpis:
            paras.append(_para(f"\u2022  {k.get('label', '')}: {k.get('value', '')}",
                               size=12))
    else:
        paras.append(_para("No KPIs yet — clean the data first.", size=12))
    paras.append(_para("", size=11))
    paras.append(_para("What was cleaned", size=16, bold=True, space_before=6))
    if actions:
        for step, detail in actions:
            paras.append(_para(f"\u2022  {step}: {detail}", size=12))
    else:
        paras.append(_para("Nothing cleaned yet.", size=12))
    paras.append(_para("", size=11))
    paras.append(_para(f"Generated by {brand_name or 'Data Cleaner Studio'}. "
                       "Data never leaves this computer.", size=10))
    box = _textbox(2, "Report", MARGIN, int(0.3 * EMU_PER_INCH),
                   SLIDE_W - 2 * MARGIN, SLIDE_H - int(0.6 * EMU_PER_INCH),
                   paras)
    return _slide_xml([box])


def _table_slide(table_df):
    """Slide 2: a simple table of the first ~8 rows (max 6 columns)."""
    df = table_df.head(8)
    cols = [str(c) for c in df.columns[:6]]
    rows = [[str(v)[:24] for v in df.iloc[i, :6]] for i in range(len(df))]
    title_box = _textbox(2, "Table title", MARGIN, int(0.3 * EMU_PER_INCH),
                         SLIDE_W - 2 * MARGIN, int(0.7 * EMU_PER_INCH),
                         [_para("Cleaned data — first rows", size=20,
                                bold=True, color="1F3864")])
    note = ""
    if len(df.columns) > 6 or len(table_df) > 8:
        note = (f"Showing {len(df)} of {len(table_df)} rows and "
                f"{len(cols)} of {len(table_df.columns)} columns.")
    shapes = [title_box]
    shapes.append(_table_frame(3, MARGIN, int(1.2 * EMU_PER_INCH),
                               SLIDE_W - 2 * MARGIN, cols, rows))
    if note:
        shapes.append(_textbox(4, "Table note", MARGIN,
                               int(1.2 * EMU_PER_INCH) + 320040 * (len(rows) + 1)
                               + int(0.15 * EMU_PER_INCH),
                               SLIDE_W - 2 * MARGIN, int(0.4 * EMU_PER_INCH),
                               [_para(note, size=10)]))
    return _slide_xml(shapes)


def to_pptx_bytes(title, kpis, actions, summary, table_df=None, brand=None):
    """Build a valid .pptx report and return it as bytes.

    ``kpis``: list of {"label", "value"} dicts (as engine.auto_kpis makes).
    ``actions``: list of (step, detail) pairs (as engine.clean returns).
    ``table_df``: optional DataFrame — first ~8 rows go on slide 2.
    ``brand``: optional brand dict {"name", "accent", ...} (see
    feat_brand.brand_for_exports). None behaves exactly as before;
    a brand replaces "Data Cleaner Studio" with the brand name in the
    title and footer, and colours the title with the accent colour.
    """
    kpis = list(kpis or [])
    actions = list(actions or [])
    slides = [_report_slide(title, kpis, actions, summary or "", brand=brand)]
    if table_df is not None and len(table_df):
        slides.append(_table_slide(table_df))

    n = len(slides)
    content_types = _CONTENT_TYPES
    if n > 1:
        extra = (
            '<Override PartName="/ppt/slides/slide2.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.presentationml.'
            'slide+xml"/>\n</Types>')
        content_types = content_types.replace("</Types>", extra)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", _ROOT_RELS)
        z.writestr("ppt/presentation.xml", _presentation_xml(n))
        z.writestr("ppt/_rels/presentation.xml.rels", _presentation_rels(n))
        z.writestr("ppt/slideMasters/slideMaster1.xml", _SLIDE_MASTER)
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", _MASTER_RELS)
        z.writestr("ppt/slideLayouts/slideLayout1.xml", _SLIDE_LAYOUT)
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", _LAYOUT_RELS)
        z.writestr("ppt/theme/theme1.xml", _THEME)
        for i, slide in enumerate(slides, start=1):
            z.writestr(f"ppt/slides/slide{i}.xml", slide)
            z.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", _SLIDE_RELS)
    return buf.getvalue()
