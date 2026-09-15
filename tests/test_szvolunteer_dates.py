import os
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from exceptions import FileError, szvHourMismatchError
from get_data_in_szvolunteer_text import parse_szvolunteer
from volunteer_hours_verify import volunteer_hours_verify


START = date(2025, 9, 1)
END = date(2026, 8, 31)
TEXT = "姓名 测试同学\n志愿者号 123456\n服务时长 9999"


def record(begin, finish, hours, kind="服务时长", number="12345678"):
    return [number, "测试活动", begin + "\n" + finish, hours, "证明人", kind]


class ShenzhenDateTests(unittest.TestCase):
    def parse_pages(self, *tables):
        pages = []
        for table in tables:
            page = MagicMock()
            page.filter.return_value = page
            page.extract_tables.return_value = [table] if table else []
            pages.append(page)
        with patch("get_data_in_szvolunteer_text.extract_text", return_value=TEXT), \
             patch("get_data_in_szvolunteer_text.pdfplumber.open") as open_pdf:
            open_pdf.return_value.__enter__.return_value.pages = pages
            return parse_szvolunteer("text.pdf", START, END)

    def test_details_across_pages_replace_header_total(self):
        result = self.parse_pages(
            [record("2025-10-01 10:00", "2025-10-01 14:00", "3.5")],
            [record("2026-02-01 10:00", "2026-02-01 13:00", "2.25")],
        )
        self.assertEqual(result, {"姓名": "测试同学", "义工号": "123456", "服务时长": 5.75})

    def test_outside_records_excluded(self):
        result = self.parse_pages([
            record("2025-08-31 08:00", "2025-08-31 20:00", "12"),
            record("2026-09-01 08:00", "2026-09-01 20:00", "12"),
        ])
        self.assertEqual(result["服务时长"], 0)

    def test_first_and_last_certification_days_included(self):
        result = self.parse_pages([
            record("2025-09-01 00:00", "2025-09-01 01:00", "0.5"),
            record("2026-08-31 22:00", "2026-08-31 23:59", "1.5"),
        ])
        self.assertEqual(result["服务时长"], 2)

    def test_crossing_either_boundary_counts_full_awarded_hours(self):
        for begin, finish in [
            ("2025-08-31 22:00", "2025-09-01 02:00"),
            ("2026-08-31 22:00", "2026-09-01 02:00"),
            ("2025-08-31 22:00", "2026-09-01 02:00"),
        ]:
            with self.subTest(begin=begin, finish=finish):
                result = self.parse_pages([record(begin, finish, "4")])
                self.assertEqual(result["服务时长"], 4)

    def test_training_never_added(self):
        result = self.parse_pages([
            record("2025-10-01 08:00", "2025-10-01 18:00", "10", "培训时长"),
            record("2025-10-02 08:00", "2025-10-02 18:00", "2"),
        ])
        self.assertEqual(result["服务时长"], 2)

    def test_training_only_returns_zero_service_hours(self):
        result = self.parse_pages([
            record("2025-10-01 08:00", "2025-10-01 18:00", "10", "培训时长"),
        ])
        self.assertEqual(result["服务时长"], 0)

    def test_awarded_hours_used_instead_of_clock_duration(self):
        result = self.parse_pages([
            record("2025-10-01 18:30", "2025-10-01 23:00", "2"),
        ])
        self.assertEqual(result["服务时长"], 2)

    def test_unreadable_page_does_not_become_zero_hours(self):
        with self.assertRaises(FileError):
            self.parse_pages([])

    def test_unreadable_later_page_does_not_return_partial_sum(self):
        with self.assertRaises(FileError):
            self.parse_pages(
                [record("2025-10-01 08:00", "2025-10-01 10:00", "2")], []
            )

    def test_invalid_detail_raises_existing_file_error(self):
        for row in [
            record("2025-10-01 08:00", "", "2"),
            record("2025-10-02 08:00", "2025-10-01 10:00", "2"),
            record("2025-02-30 08:00", "2025-03-01 10:00", "2"),
            record("2025-10-01 08:00", "2025-10-01 10:00", "NaN"),
            record("2025-10-01 08:00", "2025-10-01 10:00", "-2"),
            record("2025-10-01 08:00", "2025-10-01 10:00", "2", "未知类型"),
        ]:
            with self.subTest(row=row):
                with self.assertRaises(FileError):
                    self.parse_pages([row])

    def test_incomplete_row_is_not_silently_skipped(self):
        with self.assertRaises(FileError):
            self.parse_pages([
                record("2025-10-01 08:00", "2025-10-01 10:00", "2"),
                ["12345679", "测试活动", "2025-10-02 08:00", "2"],
            ])

    @unittest.skipUnless(os.environ.get("SZ_VOLUNTEER_SAMPLE_PDF"), "可选：提供本地文字版样本")
    def test_real_sample_and_existing_verifier(self):
        # The personal source PDF stays local and is never stored in the repository.
        sample = os.environ["SZ_VOLUNTEER_SAMPLE_PDF"]
        result = parse_szvolunteer(sample, START, END)
        self.assertEqual(result["服务时长"], 780.59)
        full = parse_szvolunteer(sample, date(2024, 9, 1), END)
        self.assertEqual(full["服务时长"], 1226.85)
        previous = parse_szvolunteer(sample, date(2024, 9, 1), date(2025, 8, 31))
        self.assertEqual(previous["服务时长"], 446.26)
        certificate = {
            "name": result["姓名"], "szu_volunteer_hours": 0,
            "i_volunteer_hours": 0, "volunteer_shenzhen_hours": 1226.85,
        }
        with self.assertRaises(szvHourMismatchError):
            volunteer_hours_verify(certificate, result.copy(), 0, 0, False, False, True)
        certificate["volunteer_shenzhen_hours"] = 780.59
        volunteer_hours_verify(certificate, result.copy(), 0, 0, False, False, True)


if __name__ == "__main__":
    unittest.main()
