import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import requests

import wps_session


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.dict(wps_session.os.environ, {
            "WPS_SID": "SID-SECRET", "KSO_SID": "KSO-SECRET", "WPS_UA": "",
        }).start()
        self.get = patch.object(wps_session.requests, "get").start()
        self.response = MagicMock()
        self.get.return_value.__enter__.return_value = self.response
        self.response.status_code = 200
        self.response.json.return_value = {"result": "ok", "userid": 123}
        self.response.cookies = requests.cookies.RequestsCookieJar()
        self.output = io.StringIO()

    def check(self):
        with redirect_stdout(self.output):
            return wps_session.check_wps_session()

    def test_online_uses_sid_once_without_oauth_or_other_identity(self):
        self.assertTrue(self.check())
        self.get.assert_called_once()
        call = self.get.call_args
        self.assertEqual(call.args, (wps_session.SESSION_URL,))
        self.assertFalse(call.kwargs["allow_redirects"])
        self.assertEqual(call.kwargs["timeout"], (3, 5))
        self.assertNotIn("headers", call.kwargs)
        prepared = requests.Request("GET", call.args[0], cookies=call.kwargs["cookies"]).prepare()
        self.assertEqual(prepared.headers["Cookie"], "wps_sid=SID-SECRET")
        self.assertNotIn("SECRET", self.output.getvalue())

    def test_explicit_invalid_session_stops_task(self):
        for result in ("userNotLogin", "SessionNotExist"):
            for status in (200, 401, 403):
                with self.subTest(result=result, status=status):
                    self.response.status_code = status
                    self.response.json.return_value = {"result": result, "msg": "SID-SECRET"}
                    with self.assertRaises(wps_session.WPSSessionError) as error:
                        self.check()
                    self.assertIn("更新环境变量 WPS_SID", str(error.exception))
                    self.assertNotIn("SECRET", str(error.exception))

    def test_unknown_status_or_result_does_not_claim_expiration(self):
        for status, data in ((403, {"result": "ok"}), (200, {"result": "unknown"}),
                             (200, []), (503, {}), (302, {})):
            with self.subTest(status=status, data=data):
                self.response.status_code = status
                self.response.json.return_value = data
                self.assertFalse(self.check())

    def test_transport_error_allows_download_and_redacts(self):
        for error in (requests.Timeout("SID-SECRET"), requests.ConnectionError("SID-SECRET")):
            self.get.side_effect = error
            self.assertFalse(self.check())
        self.assertNotIn("SECRET", self.output.getvalue())

    def test_non_json_response_allows_download(self):
        self.response.json.side_effect = ValueError("SID-SECRET")
        self.assertFalse(self.check())
        self.assertNotIn("SECRET", self.output.getvalue())

    def test_missing_sid_fails_before_network(self):
        with patch.dict(wps_session.os.environ, {"WPS_SID": ""}):
            with self.assertRaises(wps_session.WPSSessionError):
                self.check()
        self.get.assert_not_called()

    def test_changed_sid_warns_without_persisting_or_logging_value(self):
        self.response.cookies.set("wps_sid", "NEW-SECRET", domain=".wps.cn")
        self.assertTrue(self.check())
        self.assertIn("不同的 SID", self.output.getvalue())
        self.assertNotIn("SECRET", self.output.getvalue())
        self.assertEqual(wps_session.os.environ["WPS_SID"], "SID-SECRET")

    def test_same_sid_does_not_warn_about_rotation(self):
        self.response.cookies.set("wps_sid", "SID-SECRET", domain=".wps.cn")
        self.assertTrue(self.check())
        self.assertNotIn("不同的 SID", self.output.getvalue())


if __name__ == "__main__":
    unittest.main()
