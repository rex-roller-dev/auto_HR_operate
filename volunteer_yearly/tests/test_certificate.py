from dataclasses import replace
from datetime import date
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf
from PIL import Image, ImageChops

from yearly.certificate import SEAL_PATH, _render_template, write_certificate
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
                pixels.extend(page.get_pixmap(dpi=300, colorspace=pymupdf.csRGB).samples for page in document)
                page = document[-1]
                date_rect = page.search_for("2026 年 11 月 8 日")[-1]
                self.assertEqual(len(page.get_images()), 1)
                stamp_rect = page.get_image_rects(page.get_images()[0][0])[0]
                self.assertTrue(stamp_rect.intersects(date_rect))
                self.assertAlmostEqual(stamp_rect.width, 130, places=3)
                self.assertAlmostEqual(stamp_rect.height / stamp_rect.width, 632 / 1528, places=3)
                self.assertTrue(page.rect.contains(stamp_rect))
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
                    self.assertEqual(image.colorspace.n, 3)
                    red, green, _ = Image.frombytes("RGB", (image.width, image.height), image.samples).split()
                    self.assertGreater(ImageChops.subtract(red, green).getextrema()[1], 80)
        drawn = "".join(text)
        compact = "".join(drawn.split())
        for value in (report.submission.name, "志愿时服务认证", "2025-2026", "2016-2017",
                      "2026-08-31", "8.00", "4.00", "缺少完整活动日期",
                      "未计入任何学年", "深圳大学志愿者联合会", "2026年11月8日"):
            self.assertIn(value, compact)
        self.assertNotIn("xx", drawn)
        self.assertNotIn("X 月", drawn)

    def test_stamp_is_the_original_docker_asset(self):
        data = SEAL_PATH.read_bytes()
        git_blob = b"blob " + str(len(data)).encode() + b"\0" + data
        self.assertEqual(hashlib.sha1(git_blob).hexdigest(), "26ee21c7ed3e128095f06251ea7051ad23d808fa")

    def test_long_notices_continue_on_image_pages_without_losing_signature(self):
        notices = "".join(f"<p>材料提示第{i}条：" + "需要核对的材料信息。" * 40 + "</p>" for i in range(20))
        drawn = []
        image_counts = []

        def capture(html, issued_on):
            data = _render_template(html, issued_on)
            with pymupdf.open(stream=data, filetype="pdf") as document:
                drawn.extend(page.get_text() for page in document)
                image_counts.extend(len(page.get_images()) for page in document)
                page = document[-1]
                stamp_rect = page.get_image_rects(page.get_images()[0][0])[0]
                self.assertTrue(stamp_rect.intersects(page.search_for("2027 年 1 月 2 日")[-1]))
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
        self.assertEqual(image_counts, [0] * (len(image_counts) - 1) + [1])
        self.assertIn("深圳大学志愿者联合会", compact)
        self.assertTrue(compact.endswith("2027年1月2日"))
