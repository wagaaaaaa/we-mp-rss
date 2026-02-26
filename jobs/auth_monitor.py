import time

from core.config import cfg
from core.print import print_info, print_warning
from core.task import TaskScheduler
from driver.token import wx_cfg
from jobs.failauth import send_wx_code


_scheduler = TaskScheduler()
_job_started = False
_last_alert_ts = 0.0
_JOB_ID = "auto-auth-monitor"


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _is_token_expired() -> bool:
    wx_cfg.reload()
    expiry_ts = _safe_float(wx_cfg.get("expiry.expiry_timestamp", 0), 0.0)
    if expiry_ts <= 0:
        return True
    return expiry_ts <= time.time()


def _is_enabled() -> bool:
    return bool(cfg.get("server.auto_auth_monitor", True))


def check_auth_status():
    global _last_alert_ts

    if not cfg.get("server.send_code", False):
        return
    if not _is_enabled():
        return
    if not _is_token_expired():
        return

    cooldown = _safe_int(cfg.get("server.auth_alert_cooldown", 900), 900)
    now = time.time()
    if now - _last_alert_ts < max(cooldown, 60):
        return
    _last_alert_ts = now

    send_wx_code("wechat login expired; qrcode notify triggered automatically")


def start_auth_monitor():
    global _job_started
    if _job_started:
        return

    if not _is_enabled():
        print_warning("auto auth monitor disabled")
        return

    interval = _safe_int(cfg.get("server.auth_check_interval", 5), 5)
    interval = min(max(interval, 1), 59)
    cron_exp = f"*/{interval} * * * *"

    _scheduler.clear_all_jobs()
    _scheduler.add_cron_job(
        check_auth_status,
        cron_expr=cron_exp,
        job_id=_JOB_ID,
        tag="auto-auth-monitor",
    )
    _scheduler.start()
    _job_started = True
    print_info(f"auto auth monitor enabled, interval={interval}min")
