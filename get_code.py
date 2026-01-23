import urllib.parse

# ----------- 配置参数 -----------
client_id = "AK20251124JTQCUM"  # 控制台拿到的 AppID
redirect_uri = "https://sharika-pentahydric-salvador.ngrok-free.dev/callback"  # 控制台登记的回调地址
scope_list = [
    "kso.file.readwrite",
    "kso.file.read",
    "kso.appfile.readwrite"
]  # 权限列表，逗号分隔
state = "test"  # 自定义数据，可选

# ----------- URL encode 处理 -----------
encoded_redirect_uri = urllib.parse.quote(redirect_uri, safe='')

# 将 scope 列表拼成字符串
scope_str = ",".join(scope_list)

# ----------- 构造完整授权 URL -----------
base_url = "https://openapi.wps.cn/oauth2/auth"
auth_url = (
    f"{base_url}?response_type=code"
    f"&client_id={client_id}"
    f"&redirect_uri={encoded_redirect_uri}"
    f"&scope={scope_str}"
    f"&state={state}"
)

print("用户点击授权链接如下：\n")
print(auth_url)
