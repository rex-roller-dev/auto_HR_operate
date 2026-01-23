import requests

url = "https://openapi.wps.cn/oauth2/token"
data = {
    "grant_type": "client_credentials",
    "client_id": "AK20251124JTQCUM",
    "client_secret": "2acda93b48c66a26b7d96b5b20df1b61"
}

headers = {
    "Content-Type": "application/x-www-form-urlencoded"
}

response = requests.post(url, data=data, headers=headers)
print(response.json())
