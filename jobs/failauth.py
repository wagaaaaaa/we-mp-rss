import os
import time

import requests

from core.config import cfg
from core.print import print_warning
from driver.base import WX_API
from driver.success import Success
from jobs.notice import sys_notice


def _get_feishu_webhook() -> str:
    try:
        return str(cfg.get("notice")["feishu"] or "").strip()
    except Exception:
        return ""


def _is_feishu_webhook(url: str) -> bool:
    return "open.feishu." in url


def _get_tenant_access_token(app_id: str, app_secret: str) -> str:
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=20,
    )
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"get tenant token failed: {payload}")
    return payload["tenant_access_token"]


def _upload_qrcode_to_feishu(image_path: str, tenant_token: str) -> str:
    with open(image_path, "rb") as f:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/images",
            headers={"Authorization": f"Bearer {tenant_token}"},
            data={"image_type": "message"},
            files={"image": ("wx_qrcode.png", f, "image/png")},
            timeout=30,
        )
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"upload qrcode failed: {payload}")
    return payload["data"]["image_key"]


def _send_feishu_text(webhook: str, text: str):
    payload = {"msg_type": "text", "content": {"text": text}}
    resp = requests.post(webhook, json=payload, timeout=20)
    try:
        print(resp.text)
    except Exception:
        pass


def _send_feishu_qrcode_card(webhook: str, image_key: str):
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "template": "red",
                "title": {"tag": "plain_text", "content": "WeRSS授权失效"},
            },
            "elements": [
                {
                    "tag": "img",
                    "img_key": image_key,
                    "alt": {"tag": "plain_text", "content": "二维码"},
                },
            ],
        },
    }
    resp = requests.post(webhook, json=payload, timeout=20)
    try:
        print(resp.text)
    except Exception:
        pass


def _send_feishu_qrcode_notice() -> bool:
    webhook = _get_feishu_webhook()
    if not webhook or (not _is_feishu_webhook(webhook)):
        return False

    app_id = str(os.environ.get("FEISHU_APP_ID", "")).strip()
    app_secret = str(os.environ.get("FEISHU_APP_SECRET", "")).strip()
    image_path = os.path.abspath("./static/wx_qrcode.png")

    if not app_id or not app_secret or (not os.path.exists(image_path)):
        _send_feishu_text(webhook, "二维码发送失败，请稍后重试")
        return True

    try:
        tenant_token = _get_tenant_access_token(app_id, app_secret)
        image_key = _upload_qrcode_to_feishu(image_path, tenant_token)
        _send_feishu_qrcode_card(webhook, image_key)
        return True
    except Exception as e:
        print_warning(f"send feishu qrcode card failed: {e}")
        _send_feishu_text(webhook, "二维码发送失败，请稍后重试")
        return True


def send_wx_code(title: str = "", url: str = ""):
    if not cfg.get("server.send_code", False):
        return
    if WX_API.GetHasCode():
        CallBackNotice()
        return
    WX_API.GetCode(Notice=CallBackNotice, CallBack=Success)


def CallBackNotice(data=None, ext_data=None):
    if data is not None:
        print_warning(data)
        return

    text = "登录失效，请扫描下方二维码重新授权"
    title = str(cfg.get("server.code_title", "微信登录提醒"))
    has_qrcode = WX_API.GetHasCode()

    if has_qrcode:
        # Send non-Feishu channels only to keep Feishu as single notification.
        sys_notice(text, title, skip_feishu=True)
        if not _send_feishu_qrcode_notice():
            # No Feishu webhook configured: keep one fallback message.
            sys_notice(text, title)
        return

    sys_notice(text, title)
