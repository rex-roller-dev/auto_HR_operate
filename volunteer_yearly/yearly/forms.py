import base64
from datetime import date
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit

from .models import Submission, Upload, UserError, SZ, IV


def normalized(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value))).casefold()


def unwrap(event):
    for _ in range(5):
        if isinstance(event, str):
            try:
                event = json.loads(event)
            except (ValueError, TypeError):
                raise UserError("请求不是有效的JSON") from None
        if not isinstance(event, dict):
            raise UserError("请求内容应为JSON对象")
        if "answerContents" in event:
            return event
        if "body" in event:
            body = event["body"]
            if event.get("isBase64Encoded"):
                try:
                    body = base64.b64decode(body, validate=True).decode("utf-8")
                except (ValueError, UnicodeError, TypeError):
                    raise UserError("网关请求体编码错误") from None
            event = body
        elif isinstance(event.get("data"), dict):
            event = event["data"]
        else:
            return event  # 表单绑定校验请求
    raise UserError("请求体嵌套过深")


def find_field(answers, configured, aliases=()):
    if configured.startswith("qid:"):
        matches = [a for a in answers if str(a.get("qid")) == configured[4:]]
    else:
        matches = [a for a in answers if normalized(a.get("title", "")) == normalized(configured)]
        if not matches:
            matches = [a for a in answers if normalized(a.get("title", "")) in {normalized(t) for t in aliases}]
    if len(matches) > 1:
        raise UserError(f"表单字段“{configured}”重复，请联系管理员设置题目ID")
    return matches[0] if matches else None


def value_of(item):
    value = item.get("value") if item else ""
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str):
        value = value[0]
    if not isinstance(value, str):
        raise UserError("姓名、学号及邮箱必须为文本字段")
    value = value.strip()
    if any(ord(c) < 32 for c in value):
        raise UserError("姓名、学号或邮箱包含无效控制字符")
    return value


def parse_submission(data, settings, today=None):
    answers = data.get("answerContents")
    if not isinstance(answers, list) or not all(isinstance(a, dict) for a in answers):
        raise UserError("表单题目数据格式错误")
    name = value_of(find_field(answers, settings.name_field, ("请输入姓名",)))
    student = value_of(find_field(answers, settings.student_field, ("请输入学号",)))
    email = value_of(find_field(answers, settings.email_field, ("电子邮箱", "邮箱地址", "请输入邮箱")))
    if not name or len(name) > 80:
        raise UserError("请填写有效的姓名")
    if not re.fullmatch(r"20\d{2}\d{2,16}", student):
        raise UserError("学号应为纯数字，且前四位为入学年份，例如2024")
    enrollment = int(student[:4])
    today = today or date.today()
    if enrollment < 2000 or enrollment > today.year:
        raise UserError("学号前四位不是有效的入学年份")
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_\x60{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", email) or len(email) > 254:
        raise UserError("请填写有效的邮箱地址")
    aid = str(data.get("aid", "")).strip()
    if not aid or len(aid) > 200 or any(ord(c) < 32 for c in aid):
        raise UserError("表单缺少有效的答卷编号aid，无法安全识别重复回调")
    form_id = str(data.get("fid") or data.get("formId") or "")
    event_id = hashlib.sha256(f"{settings.label}|{form_id}|{aid}".encode()).hexdigest()
    uploads = []
    for platform, field_name in ((SZ, settings.shenzhen_field), (IV, settings.ivolunteer_field)):
        item = find_field(answers, field_name)
        values = item.get("value") if item else []
        if not values:
            continue
        if not isinstance(values, list) or any(not isinstance(v, dict) for v in values):
            raise UserError(f"{platform}上传字段格式错误")
        for entry in values:
            filename = str(entry.get("fileName", ""))
            if not filename.lower().endswith(".pdf") or len(filename) > 240:
                raise UserError(f"{platform}只接受PDF文件")
            if any(c in filename for c in "/\\\r\n") or filename.startswith("."):
                raise UserError("附件文件名无效")
            file_id = str(entry.get("fileId") or "").strip()
            if not file_id:
                url = urlsplit(str(entry.get("fileShareLink", "")))
                if url.scheme != "https" or not url.hostname or not (
                    url.hostname == "kdocs.cn" or url.hostname.endswith(".kdocs.cn")
                ):
                    raise UserError("附件缺少有效的WPS文件编号")
                file_id = url.path.rstrip("/").split("/")[-1]
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", file_id):
                raise UserError("WPS附件编号格式错误")
            upload = Upload(platform, filename, file_id)
            if upload not in uploads:
                uploads.append(upload)
    if not uploads:
        raise UserError("请至少上传志愿深圳或i志愿中的一种PDF明细")
    if len(uploads) > settings.max_files:
        raise UserError(f"附件数量不能超过{settings.max_files}份")
    return Submission(event_id, aid, name, student, email, tuple(uploads))
