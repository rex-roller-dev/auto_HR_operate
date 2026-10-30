import io
import threading
import time


class FakeCosError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code

    def get_status_code(self):
        return self.status

    def get_error_code(self):
        return self.code


class Body:
    def __init__(self, content):
        self.content = content

    def get_raw_stream(self):
        return io.BytesIO(self.content)


class FakeCos:
    """按服务端原子position检查建模，可使用multiprocessing.Manager代理。"""
    def __init__(self, data=None, lock=None):
        self.data = data if data is not None else {}
        self.lock = lock if lock is not None else threading.RLock()
        self.ambiguous_once = False
        self.reject_append = False

    def get_object(self, Bucket, Key):
        with self.lock:
            if (Bucket, Key) not in self.data:
                raise FakeCosError(404, "NoSuchKey")
            content = self.data[(Bucket, Key)]
        time.sleep(0.001)
        return {"Body": Body(content)}

    def put_object(self, Bucket, Key, Body, **kwargs):
        with self.lock:
            self.data[(Bucket, Key)] = Body if isinstance(Body, bytes) else Body.read()
        return {"ETag": "fake"}

    def append_object(self, Bucket, Key, Position, Data, **kwargs):
        if self.reject_append:
            raise FakeCosError(409, "ObjectNotAppendable")
        with self.lock:
            content = self.data.get((Bucket, Key), b"")
            if len(content) != Position:
                raise FakeCosError(409, "PositionNotEqualToLength")
            self.data[(Bucket, Key)] = content + Data
            if self.ambiguous_once:
                self.ambiguous_once = False
                raise FakeCosError(0, "TransportError")
        return {"x-cos-next-append-position": str(len(content) + len(Data))}
