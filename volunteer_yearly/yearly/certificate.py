from html import escape
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path

import pymupdf
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


class SummaryHTML(HTMLParser):
    """读取已缓存邮件的段落和表格，重试时也使用同一份统计结果。"""

    def __init__(self):
        super().__init__()
        self.paragraphs, self.rows = [], []
        self.tag, self.parts = None, []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.rows.append([])
        if tag in ("p", "th", "td"):
            self.tag, self.parts = tag, []
        if tag == "br":
            self.parts.append("\n")

    def handle_data(self, data):
        if self.tag:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == self.tag:
            text = "".join(self.parts)
            if tag == "p":
                self.paragraphs.append(text)
            else:
                self.rows[-1].append(text)
            self.tag, self.parts = None, []


def _render_template(html, issued_on):
    parsed = SummaryHTML()
    parsed.feed(html)
    body = ParagraphStyle("body", fontName="STSong-Light", fontSize=11, leading=18,
                          wordWrap="CJK", spaceAfter=14)
    title = ParagraphStyle("title", parent=body, fontSize=20, leading=28,
                           alignment=TA_CENTER, spaceAfter=24)
    cell = ParagraphStyle("cell", parent=body, alignment=TA_CENTER, spaceAfter=0, leading=16)
    signature = ParagraphStyle("signature", parent=body, alignment=TA_RIGHT, spaceAfter=0)
    story = [Paragraph("志愿时服务认证", title)]
    story.extend(Paragraph(escape(text), body) for text in parsed.paragraphs[:2])
    if parsed.rows:
        rows = [[Paragraph(escape(value), cell) for value in row] for row in parsed.rows]
        table = Table(rows, colWidths=[145, 171, 171], minRowHeights=[28] * len(rows),
                      repeatRows=1, hAlign="CENTER", spaceBefore=8, spaceAfter=18)
        table.setStyle(TableStyle([
            ("SPAN", (2, 1), (2, -1)),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(table)
    story.extend(Paragraph(escape(text), body) for text in parsed.paragraphs[2:])
    story.append(KeepTogether([
        Spacer(1, 18),
        Paragraph("深圳大学志愿者联合会", signature),
        Paragraph(f"{issued_on.year} 年 {issued_on.month} 月 {issued_on.day} 日", signature),
    ]))
    buffer = BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4, leftMargin=54, rightMargin=54,
                      topMargin=54, bottomMargin=54).build(story)
    return buffer.getvalue()


def write_certificate(html, issued_on, destination):
    """按返件模板排版，再将每页转换为图片，最终PDF只保留图片。"""
    with pymupdf.open(stream=_render_template(html, issued_on), filetype="pdf") as source:
        with pymupdf.open() as result:
            for page in source:
                image = page.get_pixmap(dpi=300, colorspace=pymupdf.csGRAY, alpha=False)
                target = result.new_page(width=page.rect.width, height=page.rect.height)
                target.insert_image(target.rect, pixmap=image)
            result.set_metadata({"title": "志愿服务证明"})
            result.save(destination, garbage=4, deflate=True)
    return Path(destination)
