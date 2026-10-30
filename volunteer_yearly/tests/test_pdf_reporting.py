from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from openpyxl import load_workbook
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors

from yearly.models import SZ, IV, aggregate
from yearly.parsers import parse_pdf
from yearly.reporting import write_xlsx, email_bodies
from tests.test_rules import student, activity

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


def make_pdf(path, platform=SZ, watermark=False, no_grid=False, source="i志愿"):
    width, height = landscape(A4)
    c = canvas.Canvas(str(path), pagesize=(width, height))
    c.setFont("STSong-Light", 11)
    c.drawString(30, height - 30, "姓名 测试同学" if platform == SZ else "志愿者:测试同学")
    if no_grid:
        center = height - 140
        for x, y, text in [
            (40, center, "测试跨学年活动"), (220, center + 17, "2025.08.31"),
            (250, center, "至"), (220, center - 17, "2025.09.01"),
            (665, center, "8时11分"), (750, center, source),
        ]:
            c.drawString(x, y, text)
    else:
        if platform == SZ:
            data = [
                ["考勤编号", "活动名称", "服务时间", "服务时长", "证明人", "时长类型"],
                ["123456", "测试跨学年活动", "2025-08-31 23:00<br/>2025-09-01 01:00", "1.25", "测试", "服务时长"],
                ["123457", "培训活动", "2025-10-01 10:00<br/>2025-10-01 12:00", "2", "测试", "培训时长"],
            ]
            widths = [80, 220, 140, 70, 70, 70]
        else:
            data = [
                ["志愿组织", "活动名称", "活动时间", "志愿团体", "负责人", "联系人", "联系电话", "服务时间", "数据来源"],
                ["", "跨学年测试活动", "2025.08.31<br/>至<br/>2025.09.01", "测试团体", "测试", "测试", "000", "8时11分", "i志愿"],
                ["", "需排除的深圳活动", "2025.09.02<br/>至<br/>2025.09.03", "测试团体", "测试", "测试", "000", "2时30分", "志愿深圳"],
            ]
            widths = [30, 150, 110, 75, 40, 40, 80, 65, 60]
        style = ParagraphStyle("CJK", fontName="STSong-Light", fontSize=10, leading=14)
        data = [[Paragraph(str(cell), style) for cell in row] for row in data]
        table = Table(data, colWidths=widths)
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                                   ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        _, h = table.wrap(780, height)
        table.drawOn(c, 30, height - 70 - h)
    if watermark:
        c.saveState()
        c.translate(260, 100)
        c.rotate(35)
        c.drawString(0, 0, "www.sva.org.cn")
        c.restoreState()
    c.save()


class PDFTests(unittest.TestCase):
    def test_shenzhen_real_pdf_tables_and_watermark(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sz.pdf"
            make_pdf(path, SZ, watermark=True)
            parsed = parse_pdf(path, SZ)
        self.assertEqual(len(parsed.activities), 2)
        self.assertEqual(parsed.names, {"测试同学"})
        self.assertEqual(parsed.activities[0].minutes, Decimal(75))
        self.assertEqual(parsed.activities[1].kind, "培训时长")

    def test_ivolunteer_real_pdf_table_retains_end_dates_and_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "iv.pdf"
            make_pdf(path, IV)
            parsed = parse_pdf(path, IV)
        self.assertEqual(len(parsed.activities), 2)
        self.assertEqual(parsed.activities[0].end.date(), date(2025, 9, 1))
        self.assertEqual(parsed.activities[0].minutes, Decimal(491))
        report = aggregate(student(), parsed.activities, 2025, date(2026, 10, 30))
        self.assertEqual(report.evaluation_cells()[0], "8.18")
        self.assertIn("来源为志愿深圳", report.details[1].reason)

    def test_ivolunteer_without_borders_uses_separate_record_band(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "iv.pdf"
            make_pdf(path, IV, no_grid=True)
            parsed = parse_pdf(path, IV)
        self.assertEqual(len(parsed.activities), 1)
        self.assertEqual(parsed.activities[0].minutes, Decimal(491))
        self.assertEqual(parsed.activities[0].end.date(), date(2025, 9, 1))

    def test_empty_pdf_not_silently_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "blank.pdf"
            c = canvas.Canvas(str(path))
            c.showPage()
            c.save()
            with self.assertRaises(ValueError):
                parse_pdf(path, IV)

    def test_ivolunteer_accepts_guangzhou_volunteer_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "iv.pdf"
            make_pdf(path, IV, no_grid=True, source="广州志愿时")
            parsed = parse_pdf(path, IV)
        self.assertEqual(len(parsed.activities), 1)
        self.assertEqual(parsed.activities[0].source, "广州志愿时")
        self.assertEqual(parsed.activities[0].minutes, Decimal(491))

    def test_email_contains_only_four_evaluation_years(self):
        report = aggregate(student(), [activity()], 2025, date(2026, 10, 30))
        plain, html = email_bodies(report)
        for year in ("2025-2026", "2024-2025", "2023-2024", "2022-2023"):
            self.assertEqual(html.count("<td>" + year + "</td>"), 1)
        self.assertNotIn("2026-2027", html)
        self.assertNotIn("附件包含", plain)
        self.assertNotIn("活动名称", html)

    def test_workbook_contains_summary_details_and_explicit_text(self):
        a = activity()
        from dataclasses import replace
        a = replace(a, title='=HYPERLINK("https://example.com")')
        report = aggregate(student(), [a], 2025, date(2026, 10, 30))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.xlsx"
            write_xlsx(report, path)
            wb = load_workbook(path)
            self.assertEqual(wb.sheetnames, ["学年汇总", "活动明细", "统计说明"])
            self.assertEqual(wb["活动明细"]["D2"].data_type, "s")
            self.assertEqual(wb["活动明细"]["I2"].value, 4)
            self.assertIn("未入学", [c.value for row in wb["学年汇总"] for c in row])
