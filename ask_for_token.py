import requests

def ask_for_token() -> dict:
    url = "https://openapi.wps.cn/oauth2/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": "AK20260123MIJKGM",
        "client_secret": "2549734a740f7d74c1644ed5c9cb577c"
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    response = requests.post(url, data=data, headers=headers)
    print(response.json())
    return response.json()
