"""执行实际回调函数；隔离模块顶层的云服务初始化及 stdout 重绑定。"""
import ast
import io
import os
import re
import tempfile
import time
import types
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from queue import Queue
from unittest.mock import MagicMock, patch

from flask import Flask, jsonify, request

from download_file_with_dive import WPSDownloadError


class CallbackFailureTests(unittest.TestCase):
    def run_callback(self, *, token_error=False, second_file=False, success=False, session_error=False):
        source = Path(__file__).resolve().parents[1] / "main.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        callback = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "wps_callback")
        callback.decorator_list = []
        code = compile(ast.Module(body=[callback], type_ignores=[]), str(source), "exec")
        answers = [{"value": "test", "type": "input"} for _ in range(14)]
        answers.append({"type": "file", "title": "认证表", "value": [
            {"fileName": "form.docx", "fileShareLink": "https://www.kdocs.cn/l/file"},
        ]})
        if second_file:
            answers[-1]["value"].append({"fileName": "proof.pdf", "fileShareLink": "https://www.kdocs.cn/l/proof"})
        data = {"aid": "test-only", "answerContents": answers}
        original_error = RuntimeError("token unavailable") if token_error else WPSDownloadError("文件内容下载", status=403)
        queue = Queue()
        environment = {
            "request": request, "jsonify": jsonify, "task_queue": queue,
            "time": time, "os": os, "Path": Path, "re": re, "datetime": datetime,
            "extract_body": lambda value: value,
        }
        for name in ("get_access_token", "download_file_from_wps_with_drive", "make_back_info",
                     "write_verify_result", "send_failure_email", "send_success_email", "shutil",
                     "parse_volunteer", "volunteer_hours_verify", "check_wps_session"):
            environment[name] = MagicMock()
        environment["get_access_token"].return_value = ("token", "refresh")
        if session_error:
            from wps_session import WPSSessionError
            original_error = WPSSessionError("WPS 登录会话已失效")
            environment["check_wps_session"].side_effect = original_error
        if success:
            environment["download_file_from_wps_with_drive"].return_value = Path("form.docx")
            environment["parse_volunteer"].return_value = {
                "start_date": "2025-09-01", "end_date": "2026-08-31",
            }
        elif token_error:
            environment["get_access_token"].side_effect = original_error
        else:
            environment["download_file_from_wps_with_drive"].side_effect = (
                [Path("form.docx"), original_error] if second_file else original_error
            )
        filtering = types.ModuleType("Duplicate_data_filtering")
        filtering.check_and_mark_aid = MagicMock(return_value=False)
        output = io.StringIO()
        app = Flask(__name__)
        with tempfile.TemporaryDirectory() as folder:
            environment["downloads_dir"] = Path(folder) / "downloads"
            exec(code, environment)
            with patch.dict("sys.modules", {"Duplicate_data_filtering": filtering}), \
                 patch.dict(os.environ, {"CODE": ""}), redirect_stdout(output), \
                 app.test_request_context("/event-invoke", method="POST", json=data):
                _, status = environment["wps_callback"]()
        self.assertEqual(status, 200)
        self.assertEqual(queue.unfinished_tasks, 0)
        if token_error:
            environment["check_wps_session"].assert_not_called()
        else:
            environment["check_wps_session"].assert_called_once_with()
        if session_error:
            environment["download_file_from_wps_with_drive"].assert_not_called()
        if success:
            environment["make_back_info"].assert_called_once()
            self.assertEqual(environment["make_back_info"].call_args.kwargs["src_docx"], Path("form.docx"))
            environment["send_success_email"].assert_called_once()
            environment["send_failure_email"].assert_not_called()
            self.assertIsNone(environment["write_verify_result"].call_args.kwargs["exception"])
        else:
            environment["make_back_info"].assert_not_called()
            environment["send_success_email"].assert_not_called()
            self.assertIs(environment["send_failure_email"].call_args.kwargs["exception"], original_error)
        if token_error:
            environment["write_verify_result"].assert_not_called()
        elif not success:
            self.assertIs(environment["write_verify_result"].call_args.kwargs["exception"], original_error)
        self.assertNotIn("回写内容准备失败", output.getvalue())
        self.assertNotIn("local_path", output.getvalue())
        self.assertNotIn("Worker 发生异常", output.getvalue())

    def test_first_attachment_failure_preserves_original_error(self):
        self.run_callback()

    def test_session_failure_preserves_writeback_and_notification(self):
        self.run_callback(session_error=True)

    def test_second_attachment_failure_does_not_stamp_incomplete_application(self):
        self.run_callback(second_file=True)

    def test_token_failure_has_no_uninitialized_local_errors(self):
        self.run_callback(token_error=True)

    def test_success_still_generates_receipt_and_writes_success(self):
        self.run_callback(success=True)


if __name__ == "__main__":
    unittest.main()
