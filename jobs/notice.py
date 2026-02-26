from core.config import cfg


def sys_notice(
    text: str = "",
    title: str = "",
    tag: str = "绯荤粺閫氱煡",
    type: str = "",
    skip_feishu: bool = False,
):
    from core.notice import notice

    markdown_text = f"### {title} {type} {tag}\n{text}"
    notice_cfg = cfg.get("notice", {}) or {}

    dingding_webhook = str(notice_cfg.get("dingding", "") or "")
    if dingding_webhook:
        notice(dingding_webhook, title, markdown_text)

    feishu_webhook = str(notice_cfg.get("feishu", "") or "")
    if feishu_webhook and (not skip_feishu):
        notice(feishu_webhook, title, markdown_text)

    wechat_webhook = str(notice_cfg.get("wechat", "") or "")
    if wechat_webhook:
        notice(wechat_webhook, title, markdown_text)

    custom_webhook = str(notice_cfg.get("custom", "") or "")
    if custom_webhook:
        notice(custom_webhook, title, markdown_text)
