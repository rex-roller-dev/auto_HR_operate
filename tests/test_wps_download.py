import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

import download_file_with_dive as downloader


def response(status=200, *, data=None, chunks=(b"document",), headers=None):
    result = MagicMock()
    result.__enter__.return_value = result
    result.status_code = status
    result.headers = headers or {}
    result.json.return_value = data
    result.iter_content.return_value = iter(chunks)
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(
            "request failed https://gateway.wps.cn/file?signature=SECRET", response=result,
        )
    return result


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)
        self.sleep = patch.object(downloader.time, "sleep").start()
        self.addCleanup(patch.stopall)

    def download(self):
        return downloader.download_wps_file("drive", "file", "TOKEN-SECRET", self.folder, "附件.docx")

    def info(self, url="https://gateway.wps.cn/file?signature=SECRET"):
        return response(data={"code": 0, "data": {"url": url}})

    def test_download_uses_exact_url_without_browser_cookies_or_oauth_token(self):
        url = "https://gateway.wps.cn/file?sign=a%2Fb&expires=123"
        with patch.object(downloader.requests, "get", side_effect=[self.info(url), response()]) as get:
            path = self.download()
        self.assertEqual(path.read_bytes(), b"document")
        self.assertEqual(get.call_args_list[0].kwargs["headers"]["Authorization"], "Bearer TOKEN-SECRET")
        self.assertEqual(get.call_args_list[1].args, (url,))
        self.assertNotIn("cookies", get.call_args_list[1].kwargs)
        self.assertNotIn("headers", get.call_args_list[1].kwargs)
        self.assertEqual(list(self.folder.glob("*.part")), [])

    def test_storage_403_reacquires_url_and_recovers(self):
        with patch.object(downloader.requests, "get", side_effect=[
            self.info(), response(403), self.info("https://gateway.wps.cn/fresh"), response(),
        ]) as get:
            self.assertEqual(self.download().read_bytes(), b"document")
        self.assertEqual(get.call_count, 4)
        self.assertEqual(get.call_args_list[3].args[0], "https://gateway.wps.cn/fresh")
        self.sleep.assert_called_once_with(1)

    def test_persistent_403_is_bounded_and_redacted(self):
        output = io.StringIO()
        responses = [item for _ in range(3) for item in (self.info(), response(403))]
        with patch.object(downloader.requests, "get", side_effect=responses) as get, redirect_stdout(output):
            with self.assertRaises(downloader.WPSDownloadError) as raised:
                self.download()
        self.assertEqual(get.call_count, 6)
        self.assertEqual(raised.exception.status, 403)
        self.assertEqual(raised.exception.stage, "文件内容下载")
        self.assertNotIn("SECRET", output.getvalue() + str(raised.exception))
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_api_403_is_not_retried_as_a_storage_url_error(self):
        with patch.object(downloader.requests, "get", return_value=response(403)) as get:
            with self.assertRaises(downloader.WPSDownloadError) as raised:
                self.download()
        self.assertEqual(get.call_count, 1)
        self.assertEqual(raised.exception.stage, "下载地址申请")
        self.sleep.assert_not_called()

    def test_api_503_recovers(self):
        with patch.object(downloader.requests, "get", side_effect=[response(503), self.info(), response()]):
            self.assertEqual(self.download().read_bytes(), b"document")

    def test_interrupted_stream_is_removed_and_retry_starts_from_zero(self):
        def chunks():
            yield b"partial"
            raise requests.exceptions.ChunkedEncodingError("interrupted")

        interrupted = response()
        interrupted.iter_content.return_value = chunks()
        with patch.object(downloader.requests, "get", side_effect=[self.info(), interrupted, self.info(), response()]):
            self.assertEqual(self.download().read_bytes(), b"document")
        self.assertEqual([p.name for p in self.folder.iterdir()], ["附件.docx"])

    def test_empty_download_is_retried(self):
        with patch.object(downloader.requests, "get", side_effect=[
            self.info(), response(chunks=()), self.info(), response(),
        ]):
            self.assertEqual(self.download().read_bytes(), b"document")

    def test_short_download_never_replaces_existing_file(self):
        target = self.folder / "附件.docx"
        target.write_bytes(b"existing document")
        responses = [item for _ in range(3) for item in (
            self.info(), response(chunks=(b"short",), headers={"Content-Length": "100"}),
        )]
        with patch.object(downloader.requests, "get", side_effect=responses):
            with self.assertRaises(downloader.WPSDownloadError):
                self.download()
        self.assertEqual(target.read_bytes(), b"existing document")
        self.assertEqual(len(list(self.folder.iterdir())), 1)

    def test_compressed_content_length_is_not_compared_to_decoded_length(self):
        with patch.object(downloader.requests, "get", side_effect=[
            self.info(), response(headers={"Content-Length": "2", "Content-Encoding": "gzip"}),
        ]):
            self.assertEqual(self.download().read_bytes(), b"document")

    def test_storage_404_is_not_retried(self):
        with patch.object(downloader.requests, "get", side_effect=[self.info(), response(404)]) as get:
            with self.assertRaises(downloader.WPSDownloadError):
                self.download()
        self.assertEqual(get.call_count, 2)

    def test_connection_timeout_recovers(self):
        with patch.object(downloader.requests, "get", side_effect=[
            self.info(), requests.Timeout("SECRET"), self.info(), response(),
        ]):
            self.assertEqual(self.download().read_bytes(), b"document")

    def test_missing_url_and_invalid_api_json_do_not_write_files(self):
        malformed = response()
        malformed.json.side_effect = ValueError("bad JSON SECRET")
        for result in (self.info(""), malformed, response(data={"code": 123, "msg": "SECRET"})):
            with self.subTest(result=result), patch.object(downloader.requests, "get", return_value=result):
                with self.assertRaises(downloader.WPSDownloadError) as raised:
                    self.download()
                self.assertNotIn("SECRET", str(raised.exception))
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_metadata_logs_do_not_expose_token(self):
        output = io.StringIO()
        with patch.object(downloader.requests, "get", return_value=response(data={"code": 0, "data": {"drive_id": "drive"}})), redirect_stdout(output):
            self.assertEqual(downloader.get_drive_id_by_file_id("file", "TOKEN-SECRET"), "drive")
        self.assertNotIn("TOKEN-SECRET", output.getvalue())

    def test_unsafe_filename_is_rejected_before_network_access(self):
        for filename in ("../file", "..\\file", "C:secret", "", ".."):
            with self.subTest(filename=filename), patch.object(downloader.requests, "get") as get:
                with self.assertRaises(ValueError):
                    downloader.download_wps_file("drive", "file", "token", self.folder, filename)
                get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
