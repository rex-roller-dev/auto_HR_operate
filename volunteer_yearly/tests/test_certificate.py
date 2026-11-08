from dataclasses import replace
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

from yearly.certificate import _render_template, write_certificate
from yearly.models import aggregate
from yearly.reporting import email_bodies
from tests.test_rules import student, activity


class CertificateTests(unittest.TestCase):
    def test_filled_certificate_contains_only_page_images(self):
        report = aggregate(student(), [
            activity(rid="dated"),
            replace(activity(rid="undated"), begin=None, end=None),
        ], 2025, date(2026, 8, 31))
        _, html = email_bodies(report)
        text, pixels = [], []
        def capture(html, issued_on):
            data = _render_template(html, issued_on)
            with pymupdf.open(stream=data, filetype="pdf") as document:
                text.extend(page.get_text() for page in document)
                pixels.extend(page.get_pixmap(dpi=300, colorspace=pymupdf.csGRAY).samples for page in document)
            return data

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "certificate.pdf"
            with patch("yearly.certificate._render_template", side_effect=capture):
                self.assertEqual(write_certificate(html, date(2026, 11, 8), path), path)
            with pymupdf.open(path) as result:
                self.assertEqual(len(result), 1)
                self.assertEqual(result.embfile_count(), 0)
                for index, page in enumerate(result):
                    self.assertEqual(page.get_text(), "")
                    self.assertEqual(page.get_fonts(), [])
                    self.assertEqual(len(page.get_images()), 1)
                    self.assertIsNone(page.first_annot)
                    image = pymupdf.Pixmap(result, page.get_images()[0][0])
                    self.assertEqual(image.samples, pixels[index])
        drawn = "".join(text)
        compact = "".join(drawn.split())
        for value in (report.submission.name, "志愿时服务认证", "2025-2026", "2016-2017",
                      "2026-08-31", "8.00", "4.00", "缺少完整活动日期",
                      "未计入任何学年", "深圳大学志愿者联合会", "2026年11月8日"):
            self.assertIn(value, compact)
        self.assertNotIn("xx", drawn)
        self.assertNotIn("X 月", drawn)

    def test_long_notices_continue_on_image_pages_without_losing_signature(self):
        notices = "".join(f"<p>材料提示第{i}条：" + "需要核对的材料信息。" * 40 + "</p>" for i in range(20))
        drawn = []

        def capture(html, issued_on):
            data = _render_template(html, issued_on)
            with pymupdf.open(stream=data, filetype="pdf") as document:
                drawn.extend(page.get_text() for page in document)
            return data

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "certificate.pdf"
            with patch("yearly.certificate._render_template", side_effect=capture):
                write_certificate(notices, date(2027, 1, 2), path)
            with pymupdf.open(path) as result:
                self.assertGreater(len(result), 1)
                self.assertTrue(all(not page.get_text() and len(page.get_images()) == 1 for page in result))
        compact = "".join("".join(drawn).split())
        self.assertIn("材料提示第19条", compact)
        self.assertIn("深圳大学志愿者联合会", compact)
        self.assertTrue(compact.endswith("2027年1月2日"))
