import urllib.parse

CLIENT_ID = "AK20260123MIJKGM"
REDIRECT_URI = "http://localhost:8000/callback"
SCOPE = "files sheets"

def get_authorize_url():
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "state": "wps_login"
    }
    return "https://openapi.wps.cn/oauth2/authorize?" + urllib.parse.urlencode(params)

if __name__ == "__main__":
    print(get_authorize_url())
