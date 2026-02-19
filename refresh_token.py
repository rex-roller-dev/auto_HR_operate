import json
import time
import requests
from pathlib import Path
from cos_init import cos_init
# ================= 配置 =================
CLIENT_ID = "AK20260123MIJKGM"
CLIENT_SECRET = "2549734a740f7d74c1644ed5c9cb577c"
# 云函数挂载 COS 的本地路径
COS_MOUNT_DIR = Path("/mnt/token")  # 这里是你 COS 挂载的本地目录
TOKEN_FILE = COS_MOUNT_DIR / "token.json"
REFRESH_URL = "https://openapi.wps.cn/oauth2/token"
BUCKET_NAME = "auto-hr-1388169885"
TOKEN_COS_PATH = "token/token.json"
# ========================================
# 确保目录存在
COS_MOUNT_DIR.mkdir(parents=True, exist_ok=True)

def load_token():
    """从 COS 挂载目录读取 token"""
    if not TOKEN_FILE.exists():
        return None
    with TOKEN_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_token(token_data: dict):
    """
    将 token 信息保存到 COS 对象存储中
    """
    
    # JSON 序列化成字符串
    body = json.dumps(token_data, ensure_ascii=False, indent=2)

    client = cos_init()
    # 上传到 COS
    response = client.put_object(
        Bucket=BUCKET_NAME,             # 要写入的桶，例如 "auto-hr-1388169885-xxxxx"
        Key=f"{TOKEN_COS_PATH}",  # 在桶中的对象路径，例如 "token/token.json"
        Body=body.encode("utf-8")       # 内容需转成二进制
    )

    # 返回上传结果
    return response


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
        raise ValueError(f"未找到 token.json，请先通过授权获取 code 并生成 token。路径：{TOKEN_FILE}")
    
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
