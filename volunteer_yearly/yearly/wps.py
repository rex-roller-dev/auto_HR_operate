"""参考原项目v7元信息/下载链路；凭据只发送到对应的可信域名。"""
import os
from pathlib import Path
import time
from urllib.parse import quote, urlsplit

import requests

from .models import ServiceError, UserError


class DownloadProblem(ServiceError):
    def __init__(self, stage, status=0, transient=False):
        self.status, self.transient = status, transient
        super().__init__(f"WPS{stage}失败（HTTP {status or '未知'}），请管理员检查授权及登录会话")


def cookies():
    jar = requests.cookies.RequestsCookieJar()
    for name, env in (("wps_sid", "WPS_SID"), ("kso_sid", "KSO_SID"), ("wpsua", "WPS_UA")):
        value = os.getenv(env, "").strip()
        if not value:
            continue
        if any(ord(c) < 32 or ord(c) > 126 or c == ";" for c in value):
            raise ServiceError(f"{env}格式错误，请只配置Cookie值")
        for domain in (".wps.cn", ".kdocs.cn"):
            jar.set(name, value, domain=domain, path="/", secure=True)
    return jar


class WPSDownloader:
    def __init__(self, token_manager, settings, session=requests):
        self.tokens, self.settings, self.session = token_manager, settings, session

    def check_session(self):
        sid = os.getenv("WPS_SID", "").strip()
        if not sid:
            return  # 是否需要网页登录凭据，由原账号/接口的实际授权决定。
        try:
            response = self.session.get(
                "https://account.wps.cn/api/v3/islogin",
                cookies={"wps_sid": sid}, timeout=(3, 5), allow_redirects=False,
            )
            result = response.json()
        except (requests.RequestException, ValueError):
            return  # 结果不确定时保留原下载链路，不把网络错误等同于会话失效。
        flags = str(result.get("result", "")) + str(result.get("msg", "")) + str(result.get("code", ""))
        if "userNotLogin" in flags or "SessionNotExist" in flags:
            raise ServiceError("WPS登录会话已失效，请管理员重新登录并更新WPS_SID")

    def _api(self, path, params=None):
        stage = "下载地址申请" if path.endswith("/download") else "文件元信息查询"
        try:
            response = self.session.get(
                "https://openapi.wps.cn/v7/" + path,
                headers={"Authorization": f"Bearer {self.tokens.get()}"},
                cookies=cookies(), params=params or {}, timeout=(5, 20), allow_redirects=False,
            )
            if response.status_code != 200:
                raise DownloadProblem(stage, response.status_code, response.status_code in (408, 429, 500, 502, 503, 504))
            result = response.json()
        except (requests.Timeout, requests.ConnectionError):
            raise DownloadProblem(stage, transient=True) from None
        except requests.RequestException:
            raise DownloadProblem(stage) from None
        except ValueError:
            raise DownloadProblem(stage) from None
        if not isinstance(result, dict) or result.get("code") != 0 or not isinstance(result.get("data"), dict):
            raise DownloadProblem(stage)
        return result["data"]

    def download(self, upload, destination):
        file_id = quote(upload.file_id, safe="")
        meta = self._api(f"files/{file_id}/meta", {"with_drive": "true"})
        drive = str(meta.get("drive_id") or "")
        if not drive:
            raise ServiceError("WPS文件元信息缺少drive_id")
        destination = Path(destination)
        partial = destination.with_suffix(".part")
        for attempt in range(3):
            try:
                info = self._api(f"drives/{quote(drive, safe='')}/files/{file_id}/download")
                url = info.get("url")
                parsed = urlsplit(url or "")
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                    raise ServiceError("WPS返回的下载地址格式错误")
                # 不向下载地址转发Bearer Token；CookieJar会根据域名限制Cookie。
                with self.session.get(url, stream=True, cookies=cookies(), timeout=(5, 25)) as response:
                    if response.status_code != 200:
                        raise DownloadProblem("文件内容下载", response.status_code, response.status_code in (401, 403, 408, 429, 500, 502, 503, 504))
                    size = 0
                    with partial.open("wb") as output:
                        for chunk in response.iter_content(65536):
                            if not chunk:
                                continue
                            size += len(chunk)
                            if size > self.settings.max_pdf_bytes:
                                raise UserError("PDF超过允许的文件大小，请减少导出范围或拆分明细")
                            output.write(chunk)
                    if size == 0:
                        raise DownloadProblem("文件内容下载", transient=True)
                    length = response.headers.get("Content-Length")
                    if length and length.isdigit() and not response.headers.get("Content-Encoding") and size != int(length):
                        raise DownloadProblem("文件内容下载", transient=True)
                with partial.open("rb") as check:
                    if not check.read(1024).lstrip().startswith(b"%PDF-"):
                        raise UserError(f"{upload.platform}附件内容不是有效PDF，请重新导出上传")
                partial.replace(destination)
                return destination
            except (requests.Timeout, requests.ConnectionError, requests.exceptions.ChunkedEncodingError):
                error = DownloadProblem("文件内容下载", transient=True)
            except DownloadProblem as exc:
                error = exc
            except requests.RequestException:
                error = DownloadProblem("文件内容下载")
            finally:
                partial.unlink(missing_ok=True)
            if not error.transient or attempt == 2:
                raise error from None
            time.sleep(attempt + 1)
