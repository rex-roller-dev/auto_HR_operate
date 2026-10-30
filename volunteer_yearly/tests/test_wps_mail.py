from pathlib import Path
import smtplib
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

import requests

from yearly.config import Settings
from yearly.models import Upload, IV
from yearly.wps import WPSDownloader, DownloadProblem, cookies
from yearly.mailer import Mailer
from tests.test_rules import student


def api_response(data):
    response = Mock(status_code=200)
    response.json.return_value = {"code": 0, "data": data}
    return response


def media_response(status=200, payload=b"%PDF-1.4\nmock"):
    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = status
    response.headers = {"Content-Length": str(len(payload))}
    response.iter_content.return_value = [payload]
    return response


class WPSTests(unittest.TestCase):
    def test_signed_url_403_gets_new_url_and_does_not_forward_bearer(self):
        session, token = Mock(), Mock()
        token.get.return_value = "test-access"
        session.get.side_effect = [
            api_response({"drive_id": "drive"}),
            api_response({"url": "https://storage.example/report.pdf?attempt=1"}),
            media_response(403),
            api_response({"url": "https://storage.example/report.pdf?attempt=2"}),
            media_response(),
        ]
        with tempfile.TemporaryDirectory() as folder, patch("yearly.wps.time.sleep"):
            path = Path(folder) / "a.pdf"
            WPSDownloader(token, Settings(), session).download(Upload(IV, "a.pdf", "123"), path)
            self.assertTrue(path.read_bytes().startswith(b"%PDF-"))
            self.assertFalse(path.with_suffix(".part").exists())
        media_calls = [c for c in session.get.call_args_list if c.args[0].startswith("https://storage.example")]
        self.assertEqual(len(media_calls), 2)
        self.assertNotIn("headers", media_calls[0].kwargs)

    def test_interface_forbidden_is_not_reported_as_empty_pdf(self):
        session, token = Mock(), Mock()
        session.get.return_value = Mock(status_code=403)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(DownloadProblem):
                WPSDownloader(token, Settings(), session).download(Upload(IV, "a.pdf", "123"), Path(folder) / "a.pdf")
        session.get.assert_called_once()

    def test_cookie_domains_prevent_storage_leakage(self):
        with patch.dict("os.environ", {"WPS_SID": "test-cookie"}, clear=True):
            jar = cookies()
        external = requests.Request("GET", "https://storage.example/report.pdf", cookies=jar).prepare()
        internal = requests.Request("GET", "https://openapi.wps.cn/v7/files/1/meta", cookies=jar).prepare()
        self.assertNotIn("Cookie", external.headers)
        self.assertIn("wps_sid=test-cookie", internal.headers["Cookie"])

    def test_explicit_login_failure_stops_download(self):
        session = Mock()
        session.get.return_value.json.return_value = {"result": "userNotLogin"}
        with patch.dict("os.environ", {"WPS_SID": "test-cookie"}):
            with self.assertRaises(RuntimeError):
                WPSDownloader(Mock(), Settings(), session).check_session()


class MailTests(unittest.TestCase):
    def config(self):
        return patch.dict("os.environ", {
            "SMTP_SERVER": "smtp.example.com", "SMTP_PORT": "465", "SMTP_SECURITY": "ssl",
            "SENDER_EMAIL": "primary@example.com", "SENDER_PASSWORD": "test-primary",
            "AUTO_HR_BACKUP_SENDER_EMAIL": "backup@example.com",
            "AUTO_HR_BACKUP_SENDER_PASSWORD": "test-backup",
        }, clear=True)

    def test_xlsx_mime_and_from_match_backup_account(self):
        primary, backup = Mock(), Mock()
        primary.login.side_effect = smtplib.SMTPAuthenticationError(535, b"test")
        backup.send_message.return_value = {}
        with tempfile.TemporaryDirectory() as folder, self.config(), patch("yearly.mailer.smtplib.SMTP_SSL", side_effect=[primary, backup]):
            path = Path(folder) / "report.xlsx"
            path.write_bytes(b"test-workbook")
            Mailer().send(student(), "测试", "正文", "<p>正文</p>", path)
        message = backup.send_message.call_args.args[0]
        self.assertIn("backup@example.com", message["From"])
        self.assertEqual(list(message.iter_attachments())[0].get_content_type(),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def test_quit_failure_after_acceptance_does_not_resend(self):
        server = Mock()
        server.send_message.return_value = {}
        server.quit.side_effect = OSError("closed")
        with self.config(), patch("yearly.mailer.smtplib.SMTP_SSL", return_value=server) as factory:
            Mailer().send(student(), "测试", "正文")
        factory.assert_called_once()
        server.send_message.assert_called_once()
