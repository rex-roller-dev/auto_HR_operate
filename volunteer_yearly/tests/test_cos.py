import csv
import io
import json
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import multiprocessing
import unittest
from unittest.mock import patch

from yearly.cosio import CosStore, CosLease, SummaryCSV, Busy, CosProblem, client_from_env
from tests.fakes import FakeCos


def row_for(journal, event):
    years = [str(2026 - year) if year >= 2024 else "未入学" for year in journal.years]
    return ["测试", "2024123456", *years, "3.00",
            event, "2026-10-30T12:00:00+08:00"]


def process_append(data, lock, index):
    journal = SummaryCSV(CosStore(FakeCos(data, lock), "bucket"), "summary.csv", 2025)
    event = f"event-{index % 12}"
    return journal.append_once(row_for(journal, event), event)


class CosTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeCos()
        self.store = CosStore(self.client, "bucket")
        self.journal = SummaryCSV(self.store, "summary.csv", 2025)

    def test_real_sdk_client_can_initialize_without_network(self):
        client = client_from_env("ap-guangzhou", {"X-Scf-Secret-Id": "test-id", "X-Scf-Secret-Key": "test-key", "X-Scf-Session-Token": "test-session"})
        self.assertTrue(callable(client.append_object))

    def rows(self):
        return list(csv.reader(io.StringIO(self.store.read("summary.csv").decode("utf-8-sig"))))

    def test_schema_covers_every_supported_enrollment_year_and_material_total(self):
        self.assertEqual(list(self.journal.years), list(range(2025, 1999, -1)))
        self.assertIn("2000-2001学年义工时（小时）", self.journal.headers)
        self.assertEqual(self.journal.headers[-3], "材料总时长（小时）")
        self.journal.append_once(row_for(self.journal, "one"), "one")
        self.assertEqual(self.rows()[1][-3], "3.00")
        self.assertEqual(len(self.rows()[1]), len(self.journal.headers))

    def test_append_is_idempotent_and_new_submissions_retained(self):
        for event in ("one", "one", "two"):
            self.journal.append_once(row_for(self.journal, event), event)
        self.assertEqual(len(self.rows()), 3)

    def test_network_response_lost_after_commit_does_not_duplicate(self):
        self.client.ambiguous_once = True
        with patch("yearly.cosio.pause"):
            self.journal.append_once(row_for(self.journal, "one"), "one")
        self.assertEqual(len(self.rows()), 2)

    def test_header_once_in_thread_race(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda i: self.journal.append_once(row_for(self.journal, str(i)), str(i)), range(24)))
        self.assertEqual(len(self.rows()), 25)

    def test_multiple_processes_no_lost_rows_or_duplicate_events(self):
        with multiprocessing.Manager() as manager:
            data, lock = manager.dict(), manager.RLock()
            with ProcessPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(process_append, [data] * 48, [lock] * 48, range(48)))
            result = CosStore(FakeCos(data, lock), "bucket").read("summary.csv").decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(result)))
        self.assertEqual(len(rows), 13)
        self.assertEqual({r[-2] for r in rows[1:]}, {f"event-{i}" for i in range(12)})
        self.assertEqual(sum(results), 12)

    def test_nonappendable_file_is_not_overwritten(self):
        self.client.reject_append = True
        with self.assertRaises(CosProblem) as caught:
            self.journal.append_once(row_for(self.journal, "one"), "one")
        self.assertEqual(caught.exception.code, "ObjectNotAppendable")
        self.assertIsNone(self.store.read("summary.csv"))

    def test_invalid_existing_schema_fails_without_overwrite(self):
        self.store.put("summary.csv", b"bad,header\r\n", "text/csv")
        with self.assertRaises(Exception):
            self.journal.append_once(row_for(self.journal, "one"), "one")
        self.assertEqual(self.store.read("summary.csv"), b"bad,header\r\n")

    def test_lease_acquisition_done_and_stale_owner(self):
        now = [1000]
        first = CosLease(self.store, "lease.jsonl", seconds=1200, now=lambda: now[0])
        second = CosLease(self.store, "lease.jsonl", seconds=1200, now=lambda: now[0])
        self.assertTrue(first.acquire())
        with self.assertRaises(Busy):
            second.acquire()
        now[0] += 1201
        self.assertTrue(second.acquire())
        with self.assertRaises(Busy):
            first.finish()
        second.finish()
        self.assertFalse(CosLease(self.store, "lease.jsonl").acquire())

    def test_lease_ambiguous_claim_recognizes_owner(self):
        self.client.ambiguous_once = True
        with patch("yearly.cosio.pause"):
            self.assertTrue(CosLease(self.store, "lease").acquire())
