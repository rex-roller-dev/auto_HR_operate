from typing import Optional
import requests
import json
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
TOKEN_FILE = BASE_DIR / "token.json"


def load_access_token(token_file: Path) -> str:
    """
    从 token.json 中读取 access_token
    """
    if not token_file.exists():
        raise FileNotFoundError(f"{token_file} 不存在，请先获取 token")

    with token_file.open("r", encoding="utf-8") as f:
        token_data = json.load(f)

    access_token = token_data.get("access_token")
    if not access_token:
        raise ValueError("token.json 中未找到 access_token")

    return access_token

def get_file_meta(file_id: str, access_token: str) -> dict:
    """
    根据 file_id 获取文件元信息（包含 drive_id）
    """
    url = f"https://openapi.wps.cn/v7/files/{file_id}/meta"

    headers = {
        # ⚠️ 注意：这是 KSO-1 签名后的 token
        "Authorization": f"Bearer {access_token}",
    }

    params = {
        "with_drive": "true"
    }

    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()

    data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(f"WPS API error: {data.get('msg')}")

    return data["data"]

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

    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    params = {}
    if with_hash:
        params["with_hash"] = "true"

    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()

    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Get download info failed: {data.get('msg')}")

    return data["data"]


def download_file_stream(
    download_url: str,
    save_path: Path,
    chunk_size: int = 8192
):
    """
    流式下载文件
    """
    save_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(download_url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in r.iter_content(chunk_size):
                if chunk:
                    f.write(chunk)


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
    cookies: dict | None = None,   # 👈 关键
) -> Path:

    info = get_download_info(drive_id, file_id, access_token)
    download_url = info.get("url")
    # print("Download URL:", download_url)
    if not download_url:
        raise RuntimeError("Download url missing")

    save_path = save_dir / filename
    save_path.parent.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
    }

    with requests.get(
        download_url,
        headers=headers,
        cookies=cookies,   # 👈 关键
        stream=True,
        timeout=60,
    ) as r:
        r.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)

    if not save_path.exists() or save_path.stat().st_size == 0:
        raise RuntimeError("Download failed or empty file")

    return save_path

def download_file_from_wps_with_drive(
    file_id: str,
    filename: str
) -> Path :

    ACCESS_TOKEN = load_access_token(TOKEN_FILE)

    drive_id = get_drive_id_by_file_id(file_id, ACCESS_TOKEN)
    # print(f"Drive ID: {drive_id}")
    cookies = {
        "wps_sid": "V02Snq6gU0PmmPjNhEHnYw15Xoxt7mw00a41e763006af59eae",
        "kso_sid": "TKS-Txfe9jsW8I2kV1Z88rIIK-IRTro0KK-AKhXPKOiwApUIggeWcwYQtJeJzQI70ebuYCppbfoyIeopTp-3gq02QE_YERCSQ3b9fXu398eld0IJRf0pNf6uNzYzO7UIKMIpKyIzO3zA8TcdX_44ASKBNkzkSXf5nxDfcVoNtcIVpmDRQNgyV3QJ-KN-K6oTTKS.B55CrQ2a-ixOknVezaqdxfJhiHe4UpVqpWHd8KCwf_kMW_RdWScXAOBUL6MrR7FedNRxdqJWha6Bu8IdSZILsr"
    }
    print(f"drive_id: {drive_id}, file_id: {file_id}, access_token: {ACCESS_TOKEN}", flush=True)
    path = download_wps_file(
        drive_id=drive_id,
        file_id=file_id,
        access_token=ACCESS_TOKEN,
        save_dir=DOWNLOADS_DIR,
        filename=filename,
        cookies=cookies,   # 👈 关  键
    )
    return path
    


if __name__ == "__main__":
    pass
