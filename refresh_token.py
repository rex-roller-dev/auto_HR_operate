import json
import time
import requests
from pathlib import Path

# ================= 配置 =================
CLIENT_ID = "AK20260123MIJKGM"
CLIENT_SECRET = "2549734a740f7d74c1644ed5c9cb577c"
TOKEN_FILE = Path("token.json")
REFRESH_URL = "https://openapi.wps.cn/oauth2/token"
# ========================================

def load_token():
    """从本地读取 token"""
    if not TOKEN_FILE.exists():
        return None
    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_token(token_data):
    """保存 token 到本地"""
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token_data, f, ensure_ascii=False, indent=2)

def token_expired(token_data):
    """判断 access_token 是否过期"""
    expires_at = token_data.get("expires_at", 0)
    return time.time() >= expires_at

def refresh_token(refresh_token):
    """使用 refresh_token 刷新 access_token"""
    resp = requests.post(
        REFRESH_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token
        }
    )
    resp.raise_for_status()
    data = resp.json()
    
    # 兼容两种返回格式
    if "data" in data:
        data = data["data"]

    # 计算过期时间戳
    expires_at = time.time() + data.get("expires_in", 7200)
    data["expires_at"] = expires_at
    return data

def get_access_token():
    """获取有效的 access_token，如果过期则刷新"""
    token_data = load_token()
    if token_data is None:
        raise ValueError("未找到 token.json，请先通过授权获取 code 并生成 token")
    
    if token_expired(token_data):
        print("🔄 Access token 已过期，正在刷新...")
        token_data = refresh_token(token_data["refresh_token"])
        save_token(token_data)
        print("✅ Token 已刷新")
    else:
        print("✅ Access token 有效")

    return token_data["access_token"], token_data["refresh_token"]

if __name__ == "__main__":
    access_token, refresh_token = get_access_token()
    print("Access Token:", access_token)
    print("Refresh Token:", refresh_token)
