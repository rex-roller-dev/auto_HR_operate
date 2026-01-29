import requests

import requests
import time

WPS_TOKEN_URL = "https://openapi.wps.cn/oauth2/token"

CLIENT_ID = "AK20260123MIJKGM"
CLIENT_SECRET = "2549734a740f7d74c1644ed5c9cb577c"

def get_access_token():
    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    resp = requests.post(WPS_TOKEN_URL, data=payload, headers=headers, timeout=10)
    resp.raise_for_status()  # HTTP 层错误直接抛异常

    data = resp.json()
    return data

if __name__ == "__main__":
    token_info = get_access_token()
    print("access_token:", token_info["access_token"])
    print("expires_in:", token_info["expires_in"])
    print("token_type:", token_info["token_type"])

