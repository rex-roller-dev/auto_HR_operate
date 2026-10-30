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
        for index, value in ((0, "bad\n@example.com"), (3, "2300123456")):
            data = form()
            data["answerContents"][index]["value"] = value
            with self.subTest(value=value), self.assertRaises(UserError):
                parse_submission(data, Settings(), date(2026, 10, 30))
        data = form()
        data["answerContents"][1]["value"][0]["fileName"] = "../test.pdf"
        with self.assertRaises(UserError):
            parse_submission(data, Settings())

    def test_no_uploads_fails(self):
        data = form()
        data["answerContents"][1]["value"] = []
        with self.assertRaises(UserError):
            parse_submission(data, Settings())

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
        self.assertEqual(response.get_json()["bind_code"], "binding-test")
        self.processor.run.assert_not_called()

    def test_health_requires_no_credentials(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)

    def test_submission_completes_before_response(self):
        response = self.client.post("/event-invoke", json=form())
        self.assertEqual(response.status_code, 200)
        self.processor.run.assert_called_once()

    def test_secret_and_malformed_body(self):
        app = create_app(replace(Settings(), callback_secret="expected"))
        self.assertEqual(app.test_client().post("/event-invoke", json={}).status_code, 403)
        self.assertEqual(self.client.post("/event-invoke", data="invalid").status_code, 400)
