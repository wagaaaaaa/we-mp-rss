import threading
from typing import Tuple

import requests

from .token import set_token
from core.print import print_warning, print_success


WX_LOGIN_ED = True
WX_LOGIN_INFO = None
login_lock = threading.Lock()


def setStatus(status: bool):
    global WX_LOGIN_ED
    with login_lock:
        WX_LOGIN_ED = status


def getStatus():
    global WX_LOGIN_ED
    with login_lock:
        return WX_LOGIN_ED


def getLoginInfo():
    global WX_LOGIN_INFO
    with login_lock:
        return WX_LOGIN_INFO


def setLoginInfo(info):
    global WX_LOGIN_INFO
    with login_lock:
        WX_LOGIN_INFO = info


def _cookie_header_from_data(data: dict) -> str:
    cookie_str = str(data.get("cookies_str", "") or "").strip()
    if cookie_str:
        return cookie_str
    cookies = data.get("cookies", {})
    if isinstance(cookies, dict):
        return "; ".join([f"{k}={v}" for k, v in cookies.items()])
    return ""


def _verify_login_session(token: str, cookie_header: str) -> Tuple[bool, str]:
    if not token:
        return False, "missing token"
    if not cookie_header:
        return False, "missing cookie"

    url = "https://mp.weixin.qq.com/cgi-bin/searchbiz"
    params = {
        "action": "search_biz",
        "begin": 0,
        "count": 1,
        "query": "腾讯",
        "token": token,
        "lang": "zh_CN",
        "f": "json",
        "ajax": "1",
    }
    headers = {
        "Cookie": cookie_header,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token={token}",
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        if resp.status_code != 200:
            return False, f"http={resp.status_code}"
        payload = resp.json()
        base_resp = payload.get("base_resp", {})
        ret = base_resp.get("ret")
        # 200013 means frequency control but session is usually valid.
        if ret in (0, 200013):
            return True, "ok"
        err_msg = str(base_resp.get("err_msg", ""))
        return False, f"ret={ret}, err={err_msg}"
    except Exception as e:
        return False, f"verify_exception={e}"


def _notify_auth_success():
    from core.config import cfg
    from core.notice import notice

    text = "授权成功"
    notice_cfg = cfg.get("notice", {}) or {}
    for channel in ("dingding", "feishu", "wechat", "custom"):
        webhook = str(notice_cfg.get(channel, "") or "").strip()
        if webhook:
            notice(webhook, "", text)


def Success(data: dict, ext_data: dict = {}):
    if data is None:
        print_warning("login callback returned empty data")
        setStatus(False)
        return

    setLoginInfo(data)
    expiry = data.get("expiry")
    if expiry is None:
        print_warning("login callback has no expiry")
        setStatus(False)
        return

    token = str(data.get("token", "") or "")
    cookie_header = _cookie_header_from_data(data)
    verify_ok, verify_detail = _verify_login_session(token, cookie_header)

    if verify_ok:
        print_success(
            f"verified login: expiry={expiry.get('expiry_time')} "
            f"remaining={expiry.get('remaining_seconds')} token={token}"
        )
        set_token(data, ext_data or {})
        setStatus(True)
        _notify_auth_success()
    else:
        print_warning(f"login verify failed: {verify_detail}")
        setStatus(False)
