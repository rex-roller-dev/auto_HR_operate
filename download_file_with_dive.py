import requests
import time
import tempfile
from urllib.parse import urlsplit
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
MAX_DOWNLOAD_ATTEMPTS = 3
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class WPSDownloadError(RuntimeError):
    """只保留定位信息，避免把签名 URL、Token 写入表格或邮件。"""

    def __init__(self, stage, *, status=None, retryable=False, detail=""):
        self.stage = stage
        self.status = status
        self.retryable = retryable
        message = f"WPS {stage}失败"
        if status is not None:
            message += f"（HTTP {status}）"
        if detail:
            message += f"：{detail}"
        super().__init__(message)


def _get_api_data(url, access_token, params, stage):
    try:
        with requests.get(
            url, headers={"Authorization": f"Bearer {access_token}"},
            params=params, timeout=(10, 20),
        ) as response:
            response.raise_for_status()
            data = response.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        raise WPSDownloadError(
            stage, status=status, retryable=status in RETRYABLE_STATUS,
        ) from None
    except (requests.Timeout, requests.ConnectionError):
        raise WPSDownloadError(stage, retryable=True, detail="连接中断或超时") from None
    except (requests.RequestException, ValueError):
        raise WPSDownloadError(stage, detail="接口响应异常") from None
    if not isinstance(data, dict) or data.get("code") != 0:
        raise WPSDownloadError(stage, detail="接口未返回成功结果，请检查 WPS 接口日志")
    if not isinstance(data.get("data"), dict):
        raise WPSDownloadError(stage, detail="接口数据缺失")
    return data["data"]


def get_file_meta(file_id: str, access_token: str) -> dict:
    """
    根据 file_id 获取文件元信息（包含 drive_id）
    """
    url = f"https://openapi.wps.cn/v7/files/{file_id}/meta"

    return _get_api_data(url, access_token, {"with_drive": "true"}, "文件元信息查询")

def get_drive_id_by_file_id(file_id: str, access_token: str) -> str:
    meta = get_file_meta(file_id, access_token)

    drive_id = meta.get("drive_id")
    if not drive_id:
        raise ValueError("drive_id not found, check with_drive parameter")

    return drive_id

def get_download_info(
    drive_id: str,
    file_id: str,
    access_token: str,
    with_hash: bool = False
) -> dict:
    """
    获取文件下载信息（真实下载 URL）
    """
    url = f"https://openapi.wps.cn/v7/drives/{drive_id}/files/{file_id}/download"

    params = {"with_hash": "true"} if with_hash else {}
    return _get_api_data(url, access_token, params, "下载地址申请")


def download_file_stream(
    download_url: str,
    save_path: Path,
    chunk_size: int = 8192
):
    """
    流式下载文件
    """
    # 使用申请接口返回的完整 URL，不混入另一个账号的网页登录 Cookie。
    # 不向下载域名转发 OAuth Token；临时 URL 的查询参数保持原样。
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = None
    try:
        with requests.get(download_url, stream=True, timeout=(10, 30)) as response:
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=save_path.parent, prefix=".wps-", suffix=".part", delete=False,
            ) as output:
                partial_path = Path(output.name)
                size = 0
                for chunk in response.iter_content(chunk_size):
                    if chunk:
                        output.write(chunk)
                        size += len(chunk)
            if size == 0:
                raise WPSDownloadError("文件内容下载", retryable=True, detail="返回空文件")
            # requests 会自动解压，此时不能与压缩后的 Content-Length 比较。
            length = response.headers.get("Content-Length")
            if length and length.isdigit() and not response.headers.get("Content-Encoding"):
                if size != int(length):
                    raise WPSDownloadError("文件内容下载", retryable=True, detail="文件传输不完整")
        partial_path.replace(save_path)
    finally:
        if partial_path is not None:
            partial_path.unlink(missing_ok=True)


def is_file_download_success(
    file_path: Path,
    min_size: int = 1
) -> bool:
    """
    判断文件是否下载成功
    """
    if not file_path.exists():
        return False
    if not file_path.is_file():
        return False
    if file_path.stat().st_size < min_size:
        return False
    return True


def download_wps_file(
    drive_id: str,
    file_id: str,
    access_token: str,
    save_dir: Path,
    filename: str,
) -> Path:
    # 文件名来自表单，只允许写入指定下载目录。
    if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename or ":" in filename:
        raise ValueError("附件文件名无效")
    save_path = Path(save_dir) / filename
    for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        try:
            # 每次重试重新申请地址，不能重复使用可能已经失效的签名 URL。
            info = get_download_info(drive_id, file_id, access_token)
            download_url = info.get("url")
            if not isinstance(download_url, str) or not download_url:
                raise WPSDownloadError("下载地址申请", detail="下载地址缺失")
            parsed = urlsplit(download_url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise WPSDownloadError("下载地址申请", detail="下载地址格式无效")
            print(f"WPS 文件内容下载，第 {attempt}/{MAX_DOWNLOAD_ATTEMPTS} 次", flush=True)
            download_file_stream(download_url, save_path)
            return save_path
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            error = WPSDownloadError(
                "文件内容下载", status=status,
                retryable=status in RETRYABLE_STATUS or status in {401, 403},
            )
        except (requests.Timeout, requests.ConnectionError, requests.exceptions.ChunkedEncodingError):
            error = WPSDownloadError("文件内容下载", retryable=True, detail="连接中断或超时")
        except requests.RequestException:
            error = WPSDownloadError("文件内容下载", detail="请求异常")
        except WPSDownloadError as exc:
            error = exc
        if not error.retryable or attempt == MAX_DOWNLOAD_ATTEMPTS:
            raise error from None
        print(f"{error}；重新申请下载地址后重试", flush=True)
        time.sleep(attempt)


def download_file_from_wps_with_drive(
    file_id: str,
    filename: str,
    access_token: str,
) -> Path:
    drive_id = get_drive_id_by_file_id(file_id, access_token)
    return download_wps_file(
        drive_id=drive_id,
        file_id=file_id,
        access_token=access_token,
        save_dir=DOWNLOADS_DIR,
        filename=filename,
    )
