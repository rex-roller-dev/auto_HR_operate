from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock

from yearly.config import Settings
from yearly.cosio import CosStore, SummaryCSV
from yearly.forms import parse_submission
from yearly.service import Processor
from yearly.tokens import TokenManager
from yearly.models import IV
from tests.fakes import FakeCos
from tests.test_forms_app import form
from tests.test_pdf_reporting import make_pdf


class TokenTests(unittest.TestCase):
    def test_concurrent_refresh_happens_once_and_rotated_token_saved(self):
        client = FakeCos()
        store = CosStore(client, "bucket")
        cfg = replace(Settings(), client_id="test-client", client_secret="test-secret")
        store.put(cfg.token_key, json.dumps({"access_token": "old", "refresh_token": "r0", "expires_at": 0}).encode(), "application/json")
        session = Mock()
        response = Mock()
        response.json.return_value = {"access_token": "new", "refresh_token": "r1", "expires_in": 7200}
        session.post.return_value = response
        def get_one(_):
            return TokenManager(store, cfg, session).get()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(get_one, range(8)))
        self.assertEqual(results, ["new"] * 8)
        session.post.assert_called_once()
        self.assertEqual(store.json(cfg.token_key)["refresh_token"], "r1")

    def test_valid_access_token_is_reused(self):
        store = CosStore(FakeCos(), "bucket")
        cfg = Settings()
        store.put(cfg.token_key, json.dumps({"access_token": "valid", "refresh_token": "r", "expires_at": time.time()+7200}).encode(), "application/json")
        session = Mock()
        self.assertEqual(TokenManager(store, cfg, session).get(), "valid")
        session.post.assert_not_called()


class FakeDownloader:
    def __init__(self):
        self.calls = 0

    def check_session(self):
        pass

    def download(self, upload, destination):
        self.calls += 1
        make_pdf(destination, IV)
        return destination


class PipelineTests(unittest.TestCase):
    def test_full_processing_cos_upload_summary_mail_and_tmp_cleanup(self):
        store = CosStore(FakeCos(), "bucket")
        downloader, mailer = FakeDownloader(), Mock()
        with tempfile.TemporaryDirectory() as folder:
            cfg = replace(Settings(), cos_bucket="bucket", temp_root=folder)
            now = lambda: datetime(2026, 10, 30, tzinfo=timezone(timedelta(hours=8)))
            processor = Processor(cfg, store, downloader=downloader, mailer=mailer, clock=now)
            submission = parse_submission(form(), cfg)
            def verify_attachment(*args):
                self.assertTrue(Path(args[-1]).exists())
            mailer.send.side_effect = verify_attachment
            self.assertEqual(processor.run(submission)["status"], "success")
            self.assertEqual(processor.run(submission)["status"], "duplicate")
            self.assertEqual(list(Path(folder).iterdir()), [])
        self.assertEqual(downloader.calls, 1)
        mailer.send.assert_called_once()
        content = store.read(cfg.summary_key).decode("utf-8-sig")
        self.assertIn("8.18", content)
        self.assertIn("未入学", content)

    def test_retry_after_smtp_failure_reuses_prepared_report_without_extra_row(self):
        store = CosStore(FakeCos(), "bucket")
        downloader, mailer = FakeDownloader(), Mock()
        mailer.send.side_effect = [RuntimeError("simulated"), None]
        with tempfile.TemporaryDirectory() as folder:
            cfg = replace(Settings(), cos_bucket="bucket", temp_root=folder)
            processor = Processor(cfg, store, downloader=downloader, mailer=mailer)
            submission = parse_submission(form(), cfg)
            with self.assertRaises(RuntimeError):
                processor.run(submission)
            self.assertEqual(processor.run(submission)["status"], "success")
            self.assertEqual(downloader.calls, 1)
            _, rows = SummaryCSV(store, cfg.summary_key, 2025)._read()
            self.assertEqual(len(rows), 2)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_new_submission_by_same_student_adds_another_row(self):
        store = CosStore(FakeCos(), "bucket")
        with tempfile.TemporaryDirectory() as folder:
            cfg = replace(Settings(), cos_bucket="bucket", temp_root=folder)
            processor = Processor(cfg, store, downloader=FakeDownloader(), mailer=Mock())
            for aid in ("one", "two"):
                processor.run(parse_submission(form(aid), cfg))
            _, rows = SummaryCSV(store, cfg.summary_key, 2025)._read()
        self.assertEqual(len(rows), 3)
