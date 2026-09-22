"""每个任务检查一次网页登录会话；不保存 Cookie，不推算到期时间。"""
import os

import requests

from download_file_with_dive import _download_cookies


SESSION_URL = "https://account.wps.cn/api/v3/islogin"


class WPSSessionError(RuntimeError):
    pass


def check_wps_session():
    """True 表示在线，False 表示检查不确定；明确未登录时中止任务。

    根据账号方说明，访问账号接口可延长有效会话；响应本身不提供到期时间。
    检查不可用时继续既有下载流程，避免新增接口故障阻断已恢复的服务。
    """
    sid = os.environ.get("WPS_SID", "").strip()
    if not sid:
        raise WPSSessionError("未配置 WPS_SID，请填写有效的网页登录 Cookie")
    # 仅验证 wps_sid，避免另一种会话凭据掩盖它的失效。
    jar = _download_cookies()["cookies"]
    for cookie in list(jar):
        if cookie.name != "wps_sid":
            jar.clear(cookie.domain, cookie.path, cookie.name)
    try:
        with requests.get(
            SESSION_URL, cookies=jar, timeout=(3, 5), allow_redirects=False,
        ) as response:
            if response.status_code not in (200, 401, 403):
                print(f"WPS 会话检查未确认（HTTP {response.status_code}），继续尝试下载", flush=True)
                return False
            data = response.json()
            result = data.get("result") if isinstance(data, dict) else None
            if result in ("userNotLogin", "SessionNotExist"):
                raise WPSSessionError("WPS 登录会话已失效，请重新登录并更新环境变量 WPS_SID")
            if response.status_code != 200 or result != "ok":
                print("WPS 会话检查响应未确认登录状态，继续尝试下载", flush=True)
                return False
            if any(cookie.name == "wps_sid" and cookie.value != sid for cookie in response.cookies):
                print("WPS 账号接口返回了不同的 SID；未自动保存，请核实并更新环境变量，当前继续使用原凭据下载", flush=True)
            print("WPS 会话检查通过，已调用账号接口；接口未返回到期时间", flush=True)
            return True
    except (requests.RequestException, ValueError):
        # 不输出异常原文、响应体或 Cookie，避免凭据进入日志/邮件。
        print("WPS 会话检查连接或响应异常，未确认续期，继续尝试下载", flush=True)
        return False
