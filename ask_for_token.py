# 使用下面的链接获取code
# https://openapi.wps.cn/oauth2/auth?client_id=AK20260123MIJKGM&response_type=code&scope=kso.sheets.readwrite,kso.sheets.read,kso.file.readwrite,kso.file.read&state=123341111cc&redirect_uri=https://www.baidu.com

import requests
import json
from pathlib import Path
from typing import Dict

def get_access_token(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str
) -> dict:
    """
    使用 authorization_code 换取 access_token
    """
    url = "https://openapi.wps.cn/oauth2/token"

    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    resp = requests.post(url, data=data, headers=headers, timeout=10)
    resp.raise_for_status()

    token_data = resp.json()

    if "access_token" not in token_data:
        raise RuntimeError(f"Get token failed: {token_data}")

    return token_data

def save_token(token_data: Dict, file_path: str = "token.json"):
    """
    将 access_token 信息保存到 token.json
    """
    path = Path(file_path)

    with path.open("w", encoding="utf-8") as f:
        json.dump(token_data, f, ensure_ascii=False, indent=2)

def ask_for_token(code: str):
    """
    引导用户获取 authorization_code 并换取 access_token
    """
    token_info = get_access_token(
        client_id="AK20260123MIJKGM",
        client_secret="2549734a740f7d74c1644ed5c9cb577c",
        code = code,
        redirect_uri="https://www.baidu.com"
    )

    save_token(token_info)

if __name__ == "__main__":
    # 示例：请将下面的 YOUR_AUTHORIZATION_CODE 替换为实际的 code
    code   = "kso_ac_X6WNUhLmA75UEj6MhIsCi6VnaNVsWldqVbWRcH7Uw3w.EYDpz_uqo0QaQyc7c5NZsRNuo3TA536FhqSx5jD2DOo"
    ask_for_token(code)
    print("✅ Token 已保存到 token.json")
