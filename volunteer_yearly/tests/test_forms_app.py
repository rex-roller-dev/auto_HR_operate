import base64
from dataclasses import replace
from datetime import date
import json
import unittest
from unittest.mock import Mock

from app import create_app
from yearly.config import Settings
from yearly.forms import unwrap, parse_submission
from yearly.models import UserError


def form(aid="one"):
    return {"aid": aid, "fid": "form", "answerContents": [
        {"qid": "mail", "title": "邮箱", "type": "input", "value": "test@example.com"},
        {"qid": "upload", "title": "i志愿PDF", "type": "file", "value": [
            {"fileName": "志愿明细.pdf", "fileId": "123456"}]},
        {"qid": "name", "title": "姓名", "type": "input", "value": "测试同学"},
        {"qid": "id", "title": "学号", "type": "input", "value": "2024123456"},
        {"qid": "sz", "title": "志愿深圳PDF", "type": "file", "value": []},
    ]}


class FormTests(unittest.TestCase):
    def test_field_order_is_irrelevant(self):
        result = parse_submission(form(), Settings(), date(2026, 10, 30))
        self.assertEqual(result.name, "测试同学")
        self.assertEqual(result.enrollment, 2024)

    def test_different_submission_of_same_student_keeps_new_id(self):
        a = parse_submission(form("one"), Settings())
        b = parse_submission(form("two"), Settings())
        self.assertNotEqual(a.event_id, b.event_id)
        self.assertEqual(a.event_id, parse_submission(form("one"), Settings()).event_id)

    def test_gateway_body_and_base64(self):
        data = form()
        body = json.dumps(data)
        self.assertEqual(unwrap({"body": body}), data)
        self.assertEqual(unwrap({"body": base64.b64encode(body.encode()).decode(), "isBase64Encoded": True}), data)

    def test_qid_mapping(self):
        data = form()
        data["answerContents"][2]["title"] = "新名称"
        result = parse_submission(data, replace(Settings(), name_field="qid:name"))
        self.assertEqual(result.name, "测试同学")

    def test_invalid_student_email_and_file(self):
        for index, value in ((0, "bad\n@example.com"), (3, "2312123456")):
            data = form()
            data["answerContents"][index]["value"] = value
            with self.subTest(value=value), self.assertRaises(UserError):
                parse_submission(data, Settings(), date(2026, 10, 30))
        data = form()
        data["answerContents"][1]["value"][0]["fileName"] = "../test.pdf"
        with self.assertRaises(UserError):
            parse_submission(data, Settings())

    def test_undergraduate_and_graduate_enrollment(self):
        for student_id, year in (("2023123456", 2023), ("2024123456", 2024),
                                 ("2300123456", 2023), ("2400123456", 2024),
                                 ("2000123456", 2020), ("0000123456", 2000),
                                 ("2600123456", 2026)):
            data = form()
            data["answerContents"][3]["value"] = student_id
            with self.subTest(student_id=student_id):
                result = parse_submission(data, Settings(), date(2026, 10, 31))
                self.assertEqual(result.student_id, student_id)
                self.assertEqual(result.enrollment, year)

    def test_invalid_student_formats_and_future_years(self):
        for student_id in ("2300", "23001", "2300" + "1" * 17,
                           "2300abc123", "23 00123456", "2312123456",
                           "2027123456", "2700123456", "9900123456"):
            data = form()
            data["answerContents"][3]["value"] = student_id
            with self.subTest(student_id=student_id), self.assertRaises(UserError):
                parse_submission(data, Settings(), date(2026, 10, 31))

    def test_no_uploads_fails(self):
        data = form()
        data["answerContents"][1]["value"] = []
        with self.assertRaises(UserError):
            parse_submission(data, Settings())

    def test_upload_prefers_share_sid_over_numeric_file_id(self):
        data = form()
        entry = data["answerContents"][1]["value"][0]
        entry.update(fileId="580000000001", fileSid="share-id", fileShareLink="https://www.kdocs.cn/l/share-id")
        result = parse_submission(data, Settings())
        self.assertEqual(result.uploads[0].file_id, "share-id")

    def test_upload_uses_share_link_when_sid_is_missing(self):
        data = form()
        entry = data["answerContents"][1]["value"][0]
        entry.update(fileId="580000000001", fileShareLink="https://www.kdocs.cn/l/share-id?from=form")
        result = parse_submission(data, Settings())
        self.assertEqual(result.uploads[0].file_id, "share-id")

    def test_missing_aid_fails(self):
        data = form()
        data.pop("aid")
        with self.assertRaises(UserError):
            parse_submission(data, Settings())


class AppTests(unittest.TestCase):
    def setUp(self):
        self.processor = Mock()
        self.processor.run.return_value = {"status": "success"}
        self.app = create_app(replace(Settings(), bind_code="binding-test"), lambda headers: self.processor)
        self.client = self.app.test_client()

    def test_binding_does_not_process(self):
        response = self.client.post("/event-invoke", json={})
        self.assertEqual(response.get_json(), {"bind_code": "binding-test"})
        self.processor.run.assert_not_called()

    def test_empty_binding_post_does_not_parse_submission(self):
        for path in ("/", "/event-invoke"):
            for content_type in (None, "application/json", "text/plain"):
                with self.subTest(path=path, content_type=content_type):
                    response = self.client.post(path, content_type=content_type)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.get_json(), {"bind_code": "binding-test"})
        self.processor.run.assert_not_called()

    def test_explicit_bind_event_ignores_answer_fields(self):
        for answers in ([], None, "binding-placeholder", [{"qid": "name", "value": ""}]):
            data = {"event": "bind", "aid": "", "answerContents": answers}
            for body in (data, {"body": json.dumps(data)}):
                with self.subTest(answers=answers, wrapped="body" in body):
                    response = self.client.post("/event-invoke", json=body)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.get_json(), {"bind_code": "binding-test"})
        self.processor.run.assert_not_called()

    def test_empty_binding_post_still_checks_secret_and_configuration(self):
        app = create_app(replace(Settings(), bind_code="binding-test", callback_secret="expected"),
                         lambda headers: self.processor)
        client = app.test_client()
        self.assertEqual(client.post("/event-invoke").status_code, 403)
        response = client.post("/event-invoke?secret=expected")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"bind_code": "binding-test"})
        unconfigured = create_app(Settings(), lambda headers: self.processor)
        self.assertEqual(unconfigured.test_client().post("/event-invoke").status_code, 503)
        self.processor.run.assert_not_called()

    def test_invalid_submission_is_not_acknowledged_as_binding(self):
        data = form()
        data["answerContents"] = []
        self.assertEqual(self.client.post("/event-invoke", json=data).status_code, 400)
        self.processor.run.assert_not_called()

    def test_health_requires_no_credentials(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)

    def test_submission_completes_before_response(self):
        response = self.client.post("/event-invoke", json=form())
        self.assertEqual(response.status_code, 200)
        self.processor.run.assert_called_once()

    def test_graduate_callback_is_accepted_with_correct_enrollment(self):
        data = form()
        data["answerContents"][3]["value"] = "2300123456"
        response = self.client.post("/event-invoke", json=data)
        self.assertEqual(response.status_code, 200)
        self.processor.run.assert_called_once()
        self.assertEqual(self.processor.run.call_args.args[0].enrollment, 2023)

    def test_secret_and_malformed_body(self):
        app = create_app(replace(Settings(), callback_secret="expected"))
        self.assertEqual(app.test_client().post("/event-invoke", json={}).status_code, 403)
        self.assertEqual(self.client.post("/event-invoke", data="invalid").status_code, 400)
