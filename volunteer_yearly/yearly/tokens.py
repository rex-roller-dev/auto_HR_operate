import json
import time
import requests

from .cosio import Busy, CosLease, CosProblem, pause
from .models import ServiceError


class TokenManager:
    def __init__(self, store, settings, session=requests):
        self.store, self.settings, self.session = store, settings, session

    def _current(self):
        data = self.store.json(self.settings.token_key)
        if not isinstance(data, dict):
            raise ServiceError("COS中未找到WPS Token，请按原项目流程先完成授权")
        return data.get("data", data)

    @staticmethod
    def _valid(data):
        try:
            return bool(data.get("access_token")) and float(data.get("expires_at", 0)) > time.time() + 90
        except (ValueError, TypeError):
            return False

    def _save(self, data):
        payload = json.dumps(data, ensure_ascii=False).encode()
        for attempt in range(3):
            try:
                self.store.put(self.settings.token_key, payload, "application/json")
                return
            except CosProblem:
                # 新refresh_token已产生，重试保存同一份，不能再拿旧Token刷新。
                pause(attempt)
        raise ServiceError("Token刷新后未能确认COS保存成功，请管理员检查授权状态")

    def get(self):
        data = self._current()
        if self._valid(data):
            return data["access_token"]
        lease = CosLease(self.store, self.settings.token_lock_key, self.settings.lease_seconds)
        acquired = False
        for attempt in range(12):
            try:
                acquired = lease.acquire()
                break
            except Busy:
                data = self._current()
                if self._valid(data):
                    return data["access_token"]
                pause(attempt)
        if not acquired:
            raise Busy("WPS授权刷新正在处理中，请重试")
        try:
            data = self._current()
            if self._valid(data):
                return data["access_token"]
            if not self.settings.client_id or not self.settings.client_secret or not data.get("refresh_token"):
                raise ServiceError("缺少WPS_CLIENT_ID、WPS_CLIENT_SECRET或refresh_token")
            try:
                response = self.session.post(
                    "https://openapi.wps.cn/oauth2/token",
                    data={"grant_type": "refresh_token", "client_id": self.settings.client_id,
                          "client_secret": self.settings.client_secret, "refresh_token": data["refresh_token"]},
                    timeout=(5, 20),
                )
                response.raise_for_status()
                refreshed = response.json()
                refreshed = refreshed.get("data", refreshed)
                if not refreshed.get("access_token") or not refreshed.get("refresh_token"):
                    raise ValueError
                refreshed["expires_at"] = time.time() + int(refreshed.get("expires_in", 7200))
            except Exception:
                raise ServiceError("WPS授权刷新失败，请管理员检查应用配置或重新授权") from None
            lease.assert_owned()
            self._save(refreshed)
            return refreshed["access_token"]
        finally:
            lease.finish("released")

    def save_authorization(self, data):
        """供原项目授权模块使用；与刷新操作共用跨实例锁。"""
        lease = CosLease(self.store, self.settings.token_lock_key, self.settings.lease_seconds)
        lease.acquire()
        try:
            token = dict(data)
            token.setdefault("expires_at", time.time() + int(token.get("expires_in", 7200)))
            self._save(token)
        finally:
            lease.finish("released")
