from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import unittest

from yearly.models import Activity, Submission, SZ, IV, UserError, aggregate, school_year, hours_text
from yearly.parsers import duration_minutes, decimal_minutes


def activity(begin="2025-08-31", end="2025-09-01", hours="4", platform=SZ, source=None, kind="服务时长", rid=""):
    return Activity(platform, "测试活动", datetime.fromisoformat(begin), datetime.fromisoformat(end),
                    Decimal(hours) * 60, source or platform, "test.pdf", 1, rid, kind)


def student(year="2024"):
    return Submission("event", "aid", "测试同学", year + "123456", "test@example.com", ())


class RulesTests(unittest.TestCase):
    def test_graduate_and_undergraduate_share_enrollment_rules(self):
        records = [activity("2022-10-01", "2022-10-02", rid="before"),
                   activity("2023-08-31", "2023-09-01", rid="enrolled")]
        undergraduate = replace(student(), student_id="2023123456")
        graduate = replace(student(), student_id="2300123456")
        undergrad_report = aggregate(undergraduate, records, 2025, date(2026, 10, 31))
        grad_report = aggregate(graduate, records, 2025, date(2026, 10, 31))
        self.assertEqual(graduate.enrollment, 2023)
        self.assertEqual(grad_report.evaluation_cells(), ["0.00", "0.00", "4.00"])
        self.assertEqual(grad_report.evaluation_cells(), undergrad_report.evaluation_cells())
        self.assertEqual(grad_report.details[0].reason, "未入学")
        self.assertTrue(grad_report.details[1].counted)

    def test_september_boundary_uses_end_date_and_counts_once(self):
        report = aggregate(student(), [activity()], 2025, date(2026, 10, 30))
        self.assertEqual(report.totals[2025].total, Decimal(240))
        self.assertEqual(report.totals[2024].total, 0)

    def test_august31_belongs_to_previous_school_year(self):
        self.assertEqual(school_year(date(2025, 8, 31)), 2024)
        self.assertEqual(school_year(date(2025, 9, 1)), 2025)

    def test_evaluation_cutoff_includes_august31_and_excludes_later_end_dates(self):
        records = [activity("2026-08-31T08:00", "2026-08-31T23:59:59", "4", rid="last-day"),
                   activity("2026-08-31T08:00", "2026-09-01T00:00", "9", rid="after-cutoff")]
        report = aggregate(student(), records, 2025, date(2026, 8, 31))
        self.assertEqual(report.evaluation_cells()[0], "4.00")
        self.assertTrue(report.details[0].counted)
        self.assertFalse(report.details[1].counted)
        self.assertIn("统计截止日", report.details[1].reason)
        self.assertNotIn(2026, report.totals)

    def test_ivol_shenzhen_always_excluded_without_shenzhen_upload(self):
        report = aggregate(student(), [activity(platform=IV, source="志愿 深圳")], 2025, date(2026, 10, 30))
        self.assertEqual(report.totals[2025].total, 0)
        self.assertIn("来源为志愿深圳", report.details[0].reason)

    def test_no_enrollment_is_different_from_zero(self):
        report = aggregate(student(), [], 2025, date(2026, 10, 30))
        self.assertEqual(report.evaluation_cells(), ["0.00", "0.00"])
        self.assertEqual(report.year_cells(range(2025, 2021, -1)), ["0.00", "0.00", "未入学", "未入学"])

    def test_enrollment_history_is_not_limited_to_four_years(self):
        report = aggregate(student("2020"), [activity("2020-09-01", "2020-09-02", "2.25")],
                           2025, date(2026, 8, 31))
        self.assertEqual(list(report.enrollment_years), [2025, 2024, 2023, 2022, 2021, 2020])
        self.assertEqual(report.evaluation_cells(), ["0.00"] * 5 + ["2.25"])

    def test_material_total_ignores_enrollment_but_keeps_all_other_exclusions(self):
        before = activity("2020-10-01", "2020-10-02", "1.25", rid="before")
        records = [before, before,
                   activity("2022-11-01", "2022-11-02", "0.5", platform=IV),
                   activity("2024-10-01", "2024-10-02", "2.25", rid="enrolled"),
                   activity("2025-10-01", "2025-10-02", "3.5", platform=IV),
                   activity("2021-10-01", "2021-10-02", "5", kind="培训时长", rid="training"),
                   activity("2025-11-01", "2025-11-02", "100", platform=IV, source="志愿深圳"),
                   activity("2026-08-31", "2026-09-01", "99", rid="late")]
        for student_id in ("2023123456", "2000123456", "2026123456"):
            submission = replace(student(), student_id=student_id)
            with self.subTest(student_id=student_id):
                report = aggregate(submission, records, 2025, date(2026, 8, 31))
                self.assertEqual(report.material_minutes, Decimal(450))
                self.assertEqual(report.material_hours, "7.50")
        report = aggregate(student("2023"), records, 2025, date(2026, 8, 31))
        self.assertEqual(report.evaluation_cells(), ["3.50", "2.25", "0.00"])
        self.assertEqual(report.details[0].reason, "未入学")

    def test_material_minutes_are_summed_before_rounding(self):
        records = [replace(activity(rid=str(i)), minutes=Decimal(1)) for i in range(3)]
        report = aggregate(student(), records, 2025, date(2026, 8, 31))
        self.assertEqual(report.material_hours, "0.05")

    def test_before_enrollment_records_retained_but_excluded(self):
        report = aggregate(student(), [activity("2023-10-01", "2023-10-02")], 2025, date(2026, 10, 30))
        self.assertEqual(report.details[0].reason, "未入学")
        self.assertEqual(sum(y.total for y in report.totals.values()), 0)

    def test_future_records_not_counted(self):
        report = aggregate(student(), [activity("2026-10-30", "2026-10-31")], 2025, date(2026, 10, 30))
        self.assertIn("晚于", report.details[0].reason)

    def test_training_excluded(self):
        report = aggregate(student(), [activity(kind="培训时长")], 2025, date(2026, 10, 30))
        self.assertEqual(report.details[0].reason, "培训时长不计入服务时长")

    def test_awarded_hours_not_elapsed_time(self):
        report = aggregate(student(), [activity("2025-10-01T08:00", "2025-10-01T20:00", "2")], 2025, date(2026, 10, 30))
        self.assertEqual(report.evaluation_cells()[0], "2.00")

    def test_duplicate_record_id_not_counted_twice(self):
        a = activity(rid="123")
        report = aggregate(student(), [a, a], 2025, date(2026, 10, 30))
        self.assertEqual(report.evaluation_cells()[0], "4.00")
        self.assertEqual(report.details[1].reason, "重复记录")

    def test_conflicting_record_id_fails(self):
        with self.assertRaises(UserError):
            aggregate(student(), [activity(rid="123"), activity(hours="5", rid="123")], 2025, date(2026, 10, 30))

    def test_minutes_summed_before_rounding(self):
        self.assertEqual(hours_text(sum([duration_minutes("1分")] * 60, Decimal(0))), "1.00")
        self.assertEqual(decimal_minutes("4.69"), Decimal("281.40"))

    def test_duration_formats(self):
        for value, expected in (("2小时30分钟", 150), ("1时4分", 64), ("48分", 48), ("0小时", 0)):
            with self.subTest(value=value):
                self.assertEqual(duration_minutes(value), expected)
        for bad in ("", "abc", "-1时", "NaN"):
            with self.subTest(value=bad), self.assertRaises(UserError):
                duration_minutes(bad)

    def test_invalid_order_fails(self):
        with self.assertRaises(UserError):
            aggregate(student(), [activity("2025-10-02", "2025-10-01")], 2025, date(2026, 10, 30))
