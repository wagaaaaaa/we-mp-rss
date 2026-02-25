import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

CONTAINER_NAME = os.environ.get("WEMPRSS_CONTAINER", "we-mp-rss")
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
POLL_RETRY = int(os.environ.get("QRCODE_RETRY", "20"))
POLL_INTERVAL = float(os.environ.get("QRCODE_RETRY_INTERVAL", "1.5"))
COOLDOWN_SECONDS = int(os.environ.get("ALERT_COOLDOWN", "120"))
WEMPRSS_BASE_URL = os.environ.get("WEMPRSS_BASE_URL", "http://127.0.0.1:8001")
WEMPRSS_ADMIN_USER = os.environ.get("WEMPRSS_ADMIN_USER", "admin")
WEMPRSS_ADMIN_PASS = os.environ.get("WEMPRSS_ADMIN_PASS", "admin@123")
LOG_FILE = os.environ.get(
    "MONITOR_LOG_FILE",
    r"F:\coding\we-mp-rss\data\monitor_feishu_qrcode.log",
)


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str):
    text = f"[{now_str()}] {msg}"
    print(text, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass


def post_json(url: str, data: dict, headers: dict | None = None) -> dict:
    body = json.dumps(data).encode("utf-8")
    req_headers = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    return json.loads(text)


def post_form(url: str, data: dict, headers: dict | None = None) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    return json.loads(text)


def get_tenant_access_token() -> str:
    resp = post_json(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
    )
    if resp.get("code") != 0:
        raise RuntimeError(f"tenant_access_token failed: {resp}")
    return resp["tenant_access_token"]


def upload_image(image_path: str, token: str) -> str:
    boundary = "----CodexBoundary" + str(int(time.time() * 1000))
    with open(image_path, "rb") as f:
        image_data = f.read()

    parts = []
    parts.append((
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"image_type\"\r\n\r\n"
        f"message\r\n"
    ).encode("utf-8"))
    parts.append((
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"image\"; filename=\"wx_qrcode.png\"\r\n"
        f"Content-Type: image/png\r\n\r\n"
    ).encode("utf-8"))
    parts.append(image_data)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)

    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/im/v1/images",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))

    if payload.get("code") != 0:
        raise RuntimeError(f"image upload failed: {payload}")
    return payload["data"]["image_key"]


def send_webhook_text(text: str):
    post_json(
        FEISHU_WEBHOOK,
        {"msg_type": "text", "content": {"text": text}},
    )


def send_webhook_image(image_key: str):
    post_json(
        FEISHU_WEBHOOK,
        {"msg_type": "image", "content": {"image_key": image_key}},
    )


def send_login_success_notice() -> bool:
    if not FEISHU_WEBHOOK:
        return False
    send_webhook_text("授权成功")
    return True


def get_wemprss_access_token() -> str:
    url = f"{WEMPRSS_BASE_URL}/api/v1/wx/auth/login"
    resp = post_form(url, {"username": WEMPRSS_ADMIN_USER, "password": WEMPRSS_ADMIN_PASS})
    if resp.get("code") != 0:
        raise RuntimeError(f"we-mp-rss login failed: {resp}")
    return resp["data"]["access_token"]


def create_qrcode_via_api() -> dict:
    token = get_wemprss_access_token()
    url = f"{WEMPRSS_BASE_URL}/api/v1/wx/auth/qr/code"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    if payload.get("code") != 0:
        raise RuntimeError(f"create qrcode failed: {payload}")
    return payload


def copy_qrcode_from_container(tmp_path: str) -> bool:
    cmd = ["docker", "cp", f"{CONTAINER_NAME}:/app/static/wx_qrcode.png", tmp_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0


def notify_qrcode(reason: str):
    if not FEISHU_WEBHOOK:
        log("FEISHU_WEBHOOK missing, skip notify")
        return

    with tempfile.TemporaryDirectory() as td:
        qr_path = os.path.join(td, "wx_qrcode.png")
        ok = False
        for _ in range(POLL_RETRY):
            if copy_qrcode_from_container(qr_path):
                ok = True
                break
            time.sleep(POLL_INTERVAL)

        if not ok:
            send_webhook_text(f"we-mp-rss 触发重新登录（{reason}），但暂未取到二维码文件。")
            log("qr not found, text sent")
            return

        if FEISHU_APP_ID and FEISHU_APP_SECRET:
            try:
                token = get_tenant_access_token()
                image_key = upload_image(qr_path, token)
                send_webhook_text(f"we-mp-rss 触发重新登录（{reason}），请在二维码有效期内扫码。")
                send_webhook_image(image_key)
                log("qrcode image sent to feishu")
                return
            except Exception as e:
                log(f"send image failed: {e}")

        send_webhook_text(f"we-mp-rss 触发重新登录（{reason}），已检测到二维码但图片发送失败。")


def is_sys_info_401(line: str) -> bool:
    l = line.lower()
    return "401 unauthorized" in l and "/api/v1/wx/sys/info" in l


def is_pull_auth_failure(line: str) -> bool:
    return "请先扫码登录公众号平台" in line


def is_login_success(line: str) -> bool:
    keywords = (
        "登录成功，正在获取cookie和token",
        "登录成功！",
        "Token登录成功",
        "verified login:",
    )
    return any(k in line for k in keywords)


def run_monitor():
    if not FEISHU_WEBHOOK:
        log("FEISHU_WEBHOOK is empty, exiting")
        return

    since = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    cmd = ["docker", "logs", "-f", "--timestamps", "--since", since, CONTAINER_NAME]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    log(f"monitor started for container={CONTAINER_NAME}, since={since}")

    last_alert_at = 0.0
    last_success_notify_at = 0.0
    awaiting_login_success_notice = False
    try:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.strip()

            if is_login_success(line):
                log("login success detected")
                now = time.time()
                if (
                    awaiting_login_success_notice
                    and now - last_success_notify_at >= COOLDOWN_SECONDS
                ):
                    try:
                        if send_login_success_notice():
                            last_success_notify_at = now
                            log("login success notice sent")
                    except Exception as e:
                        log(f"send login success notice failed: {e}")
                awaiting_login_success_notice = False
                continue

            reason = ""
            if is_sys_info_401(line):
                reason = "sys_info_401"
            elif is_pull_auth_failure(line):
                reason = "pull_auth_failure"
            else:
                continue

            now = time.time()
            if now - last_alert_at < COOLDOWN_SECONDS:
                log(f"unauthorized detected but in cooldown, skip sending ({reason})")
                continue
            last_alert_at = now

            log(f"triggered by: {reason}")
            try:
                payload = create_qrcode_via_api()
                log(f"qrcode generated via api: {payload.get('data', {})}")
            except Exception as e:
                log(f"create qrcode via api failed: {e}")
                try:
                    send_webhook_text(f"we-mp-rss 检测到掉线（{reason}），自动生成二维码失败：{e}")
                except Exception:
                    pass
                continue

            notify_qrcode(f"{reason}_auto_qrcode")
            awaiting_login_success_notice = True
    finally:
        if proc.poll() is None:
            proc.terminate()


if __name__ == "__main__":
    run_monitor()
