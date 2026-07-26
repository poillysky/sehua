"""0 元购买帖：点购买链解锁正文后再解析入库。付费购买留给账号爬。"""

from __future__ import annotations

import logging
import re
from typing import Any

from parsers.thread_gates import (
    extract_purchase_buy_url,
    is_free_purchase_post,
    purchase_gate_kind,
)

log = logging.getLogger(__name__)

_LOGIN_HINTS = (
    "请先登录",
    "請先登錄",
    "您需要登录",
    "您需要登入",
    "还没有登录",
    "還沒有登錄",
)


def _looks_like_login_required(html: str) -> bool:
    blob = html or ""
    return any(h in blob for h in _LOGIN_HINTS)


def _has_download_payload(html: str) -> bool:
    """登录后常见：售价文案仍在，但磁力/电驴已露出。"""
    return bool(re.search(r"magnet:|ed2k://|115://", html or "", re.I))


async def unlock_free_purchase_html(
    fetcher: Any,
    html: str,
    thread_url: str,
    *,
    retries: int = 2,
) -> tuple[str, str]:
    """若为 0 元购买门，请求购买链并重拉帖页。

    返回 (html, note)：
    - note 空：未改动或已解锁
    - note 非空：解锁失败原因（调用方可写入 outcome / 日志）
    """
    if not html or not thread_url:
        return html, ""
    # 已露出下载链：先快退，避免合集大页跑购买门扫描（可省 1s+）
    if _has_download_payload(html):
        return html, ""
    if not is_free_purchase_post(html):
        return html, ""
    buy = extract_purchase_buy_url(html, thread_url)
    if not buy:
        return html, "0元购买无购买链"
    try:
        if hasattr(fetcher, "set_referer"):
            fetcher.set_referer(thread_url)
        tip = await fetcher.get_html(buy, mode="http", retries=max(1, retries))
        if _looks_like_login_required(tip):
            log.info("free-purchase unlock needs login: %s", thread_url)
            return html, "0元购买需登录"
        # 部分站购买成功直接回到帖页
        if purchase_gate_kind(tip) == "none" and (
            "magnet:" in (tip or "").lower()
            or "ed2k:" in (tip or "").lower()
            or "read.php" in (tip or "")
            or "viewthread" in (tip or "").lower()
        ):
            # tip 已是帖页
            if not is_free_purchase_post(tip):
                return tip, ""
        new_html = await fetcher.get_thread_html(thread_url, retries=max(1, retries))
        if is_free_purchase_post(new_html) and "magnet:" not in (new_html or "").lower():
            # 仍锁着：浏览器再试一次购买（Cookie/校验码场景）
            try:
                tip2 = await fetcher.get_html(buy, mode="browser", retries=1)
                if _looks_like_login_required(tip2):
                    return html, "0元购买需登录"
                new_html = await fetcher.get_thread_html(thread_url, retries=max(1, retries))
            except Exception as e:
                log.warning("free-purchase browser unlock failed: %s", e)
        if is_free_purchase_post(new_html) and not re.search(
            r"magnet:|ed2k:", new_html or "", re.I
        ):
            return new_html, "0元购买未解锁"
        return new_html, ""
    except Exception as e:
        log.warning("free-purchase unlock error: %s", e)
        return html, f"0元购买失败：{e}"
