"""COS是共享状态的唯一依据；不使用本机文件锁协调云函数实例。"""
import csv
import io
import json
import os
import random
import time
import uuid

from .models import ServiceError, year_label


class CosProblem(ServiceError):
    def __init__(self, status, code):
        self.status = status
        self.code = code
        super().__init__(f"COS操作失败（HTTP {status}，{code}）")


class Busy(ServiceError):
    pass


def client_from_env(region, headers=None):
    from qcloud_cos import CosConfig, CosS3Client
    headers = headers or {}
    sid = headers.get("X-Scf-Secret-Id") or os.getenv("TENCENTCLOUD_SECRETID") or os.getenv("COS_SECRET_ID")
    key = headers.get("X-Scf-Secret-Key") or os.getenv("TENCENTCLOUD_SECRETKEY") or os.getenv("COS_SECRET_KEY")
    token = headers.get("X-Scf-Session-Token") or os.getenv("TENCENTCLOUD_SESSIONTOKEN") or os.getenv("COS_SESSION_TOKEN")
    if not sid or not key:
        raise ServiceError("未配置COS访问凭据或云函数执行角色")
    return CosS3Client(CosConfig(Region=region, SecretId=sid, SecretKey=key, Token=token, Scheme="https", Timeout=20), retry=0)


class CosStore:
    def __init__(self, client, bucket):
        if not bucket:
            raise ServiceError("未配置COS_BUCKET")
        self.client = client
        self.bucket = bucket

    def _call(self, method, **kwargs):
        try:
            return getattr(self.client, method)(Bucket=self.bucket, **kwargs)
        except Exception as exc:
            status = getattr(exc, "get_status_code", lambda: 0)()
            code = getattr(exc, "get_error_code", lambda: "TransportError")()
            # 错误消息不包含SDK的完整请求、签名、临时凭据或对象内容。
            raise CosProblem(int(status or 0), str(code)) from None

    def read(self, key, limit=32 * 1024 * 1024):
        try:
            result = self._call("get_object", Key=key)
        except CosProblem as exc:
            if exc.status == 404 and exc.code in ("NoSuchKey", "NoSuchObject", "NotFound"):
                return None
            raise
        body = result["Body"].get_raw_stream()
        try:
            content = body.read(limit + 1)
        finally:
            body.close()
        if len(content) > limit:
            raise ServiceError("COS文件超过当前处理大小限制，请按评选学年分表")
        return content

    def put(self, key, content, content_type):
        return self._call("put_object", Key=key, Body=content, ContentType=content_type, EnableMD5=True)

    def append(self, key, position, content, content_type="application/x-ndjson"):
        return self._call("append_object", Key=key, Position=position, Data=content, ContentType=content_type)

    def json(self, key, limit=1024 * 1024):
        content = self.read(key, limit)
        if content is None:
            return None
        try:
            return json.loads(content)
        except (ValueError, UnicodeError):
            raise ServiceError("COS状态文件格式错误，请联系管理员") from None


def pause(attempt):
    time.sleep(min(0.04 * 2 ** attempt, 0.8) + random.uniform(0, 0.04))


def retryable(exc):
    return isinstance(exc, CosProblem) and (
        exc.status in (0, 408, 409, 429, 500, 502, 503, 504)
        and exc.code not in ("ObjectNotAppendable", "InvalidObjectState", "AccessDenied")
    )


class CosLease:
    """使用append的字节位置校验抢占租约；租期大于SCF最长900秒执行期。

    超时/失联时先重新读日志核对owner，避免服务端已成功但客户端重试产生错误状态。
    旧进程不能释放新owner的租约。此约束适用于执行超时<=900秒的SCF。
    """
    def __init__(self, store, key, seconds=1200, now=time.time):
        self.store, self.key, self.seconds, self.now = store, key, seconds, now
        self.owner = uuid.uuid4().hex

    def _read(self):
        content = self.store.read(self.key, 1024 * 1024) or b""
        try:
            last = json.loads(content.splitlines()[-1]) if content else {}
        except (ValueError, IndexError):
            raise ServiceError("COS租约日志损坏，请联系管理员") from None
        return content, last

    def acquire(self):
        for attempt in range(15):
            content, last = self._read()
            if last.get("owner") == self.owner and last.get("state") == "running" and last.get("until", 0) > self.now():
                return True
            if last.get("state") == "done":
                return False
            if last.get("state") == "running" and last.get("until", 0) > self.now():
                raise Busy("同一任务或共享资源正在处理中，请稍后重试")
            event = {"owner": self.owner, "state": "running", "until": self.now() + self.seconds}
            try:
                self.store.append(self.key, len(content), (json.dumps(event) + "\n").encode())
                return True
            except CosProblem as exc:
                if not retryable(exc):
                    raise
                pause(attempt)
        raise Busy("COS租约竞争暂未完成，请重试")

    def assert_owned(self):
        _, last = self._read()
        if last.get("owner") != self.owner or last.get("state") != "running" or last.get("until", 0) <= self.now():
            raise Busy("任务租约已失效，停止当前实例写入")

    def finish(self, state="done", result="success"):
        for attempt in range(15):
            content, last = self._read()
            if last.get("owner") == self.owner and last.get("state") == state:
                return
            if last.get("owner") != self.owner or last.get("state") != "running" or last.get("until", 0) <= self.now():
                raise Busy("任务租约已失效，未修改其他实例状态")
            event = {"owner": self.owner, "state": state, "until": 0, "result": result}
            try:
                self.store.append(self.key, len(content), (json.dumps(event) + "\n").encode())
                return
            except CosProblem as exc:
                if not retryable(exc):
                    raise
                pause(attempt)
        raise Busy("未能确认任务状态，请重试")


def csv_safe(value):
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


class SummaryCSV:
    def __init__(self, store, key, year, limit=32 * 1024 * 1024):
        self.store, self.key, self.year, self.limit = store, key, year, limit

    @property
    def headers(self):
        return ["姓名", "学号"] + [
            f"{year_label(y)}学年义工时（小时）" for y in range(self.year, self.year - 4, -1)
        ] + ["评选学年", "明细COS对象键", "提交编号", "处理时间（北京时间）"]

    def _read(self):
        content = self.store.read(self.key, self.limit) or b""
        try:
            rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig")))) if content else []
        except (UnicodeError, csv.Error):
            raise ServiceError("汇总CSV格式无效，未执行覆盖写入") from None
        if rows and (rows[0] != self.headers or any(len(row) != len(self.headers) for row in rows[1:])):
            raise ServiceError("汇总CSV列与配置不一致或内容不完整，请使用新的对象键")
        return content, rows

    def append_once(self, row, event_id):
        if len(row) != len(self.headers) or str(row[-2]) != event_id:
            raise ValueError("汇总行与提交编号不一致")
        for attempt in range(25):
            content, rows = self._read()
            if any(r[-2] == event_id for r in rows[1:]):
                return False
            out = io.StringIO(newline="")
            writer = csv.writer(out, lineterminator="\r\n")
            if not content:
                writer.writerow(self.headers)
            writer.writerow([csv_safe(c) for c in row])
            payload = (b"\xef\xbb\xbf" if not content else b"") + out.getvalue().encode("utf-8")
            if len(content) + len(payload) > self.limit:
                raise ServiceError("汇总表大小超过限制，请联系管理员分表")
            try:
                self.store.append(self.key, len(content), payload, "text/csv; charset=utf-8")
                return True
            except CosProblem as exc:
                if not retryable(exc):
                    raise
                # 409位置竞争、或响应丢失时均重新读取：检查提交编号后再追加。
                pause(attempt)
        # 最后一笔请求也可能已经落盘，但响应丢失。
        _, rows = self._read()
        if any(r[-2] == event_id for r in rows[1:]):
            return False
        raise Busy("汇总表并发追加暂未完成，请重试；个人明细已保留")
