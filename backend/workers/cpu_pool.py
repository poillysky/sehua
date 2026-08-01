"""CPU 重活进程池：大合集解析不占 GIL，避免拖死 uvicorn /health。

多磁力帖的 judge/parse 是纯 Python CPU，asyncio.to_thread 仍持 GIL，
与爬虫同进程时管理端会假死。重活走 spawn 进程池。

注意：ProcessPoolExecutor 跑中的任务无法真正 cancel；超时后必须
shutdown + 弃用池，否则子进程会一直吃满 CPU，爬虫看起来「不动了」。

进池策略（勿把普通 Discuz 帖页 ~80–120KB 当重活）：
- 附件语料单独很大 → 进池
- 正文+附件合计极大 → 进池
- 正文内嵌大量 magnet/ed2k → 进池
普通帖首判（仅门禁 / need_attachments）走线程池，避免占满唯一 worker。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import multiprocessing as mp
import threading
from collections.abc import Callable
from typing import Any, TypeVar

log = logging.getLogger(__name__)
T = TypeVar("T")

# 附件语料单独超过此值 → 进进程池（大 txt/zip 抽链）
HEAVY_ATTACH_CHARS = 24_000
# 正文+附件合计超过此值 → 进进程池（勿用 80KB：普通帖页也会误进池排队）
HEAVY_TOTAL_CHARS = 220_000
# 正文内嵌链条数达到此值且 HTML 不太小 → 进进程池
HEAVY_INLINE_LINKS = 80
# 单帖解析墙钟：默认 / 大合集加长 / 封顶（防卡死调度）
PARSE_TIMEOUT_SEC = 120.0
PARSE_TIMEOUT_MAX_SEC = 900.0


_pool: concurrent.futures.ProcessPoolExecutor | None = None
_pool_lock = threading.Lock()


def _estimate_link_count(html: str = "", extra_text: str = "") -> int:
    low = f"{html or ''}\n{extra_text or ''}".lower()
    return low.count("ed2k://") + low.count("magnet:?")


def parse_timeout_sec(html: str = "", extra_text: str = "") -> float:
    """按附件语料与链数估算解析墙钟（1000V 合集默认 120s 不够）。

    例：~1000 条 ed2k → 约 370s；超大附件再按体积加长；封顶 900s。
    """
    t = float(PARSE_TIMEOUT_SEC)
    attach = len(extra_text or "")
    total = len(html or "") + attach
    n_links = _estimate_link_count(html, extra_text)
    if attach >= HEAVY_ATTACH_CHARS:
        # ~200KB 附件语料 → +100s
        t = max(t, PARSE_TIMEOUT_SEC + attach / 2000.0)
    if n_links >= HEAVY_INLINE_LINKS:
        # 1000 链 → +250s
        t = max(t, PARSE_TIMEOUT_SEC + n_links * 0.25)
    if total >= HEAVY_TOTAL_CHARS:
        t = max(t, 180.0)
    return float(min(t, PARSE_TIMEOUT_MAX_SEC))


def is_heavy_parse_payload(html: str = "", extra_text: str = "") -> bool:
    """是否走进程池。

    普通色花堂帖页常 ~80–120KB 且首判只需门禁/下附件，应走线程池；
    仅附件大语料、超大 HTML、或正文内嵌海量链时进唯一 worker 的进程池。
    """
    attach = len(extra_text or "")
    if attach >= HEAVY_ATTACH_CHARS:
        return True
    blob = html or ""
    total = len(blob) + attach
    if total >= HEAVY_TOTAL_CHARS:
        return True
    # 粗扫链数（大小写不敏感）；避免小帖误判
    if len(blob) >= 40_000:
        if _estimate_link_count(blob, "") >= HEAVY_INLINE_LINKS:
            return True
    return False


def get_cpu_pool() -> concurrent.futures.ProcessPoolExecutor:
    global _pool
    with _pool_lock:
        if _pool is None:
            ctx = mp.get_context("spawn")
            _pool = concurrent.futures.ProcessPoolExecutor(
                max_workers=1,
                mp_context=ctx,
            )
            log.info("cpu process pool ready (spawn, workers=1)")
        return _pool


def shutdown_cpu_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            try:
                _pool.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                _pool.shutdown(wait=False)
            except Exception:
                log.exception("cpu pool shutdown")
            _pool = None


async def run_in_cpu_pool(
    fn: Callable[..., T],
    *args: Any,
    timeout: float | None = None,
) -> T:
    """在进程池执行可 pickle 的顶层函数（勿传 lambda / 局部函数）。"""
    limit = float(PARSE_TIMEOUT_SEC if timeout is None else timeout)
    if limit < 1.0:
        limit = float(PARSE_TIMEOUT_SEC)
    loop = asyncio.get_running_loop()
    pool = get_cpu_pool()
    fut = loop.run_in_executor(pool, fn, *args)
    try:
        return await asyncio.wait_for(fut, timeout=limit)
    except asyncio.TimeoutError:
        log.error(
            "cpu pool parse timeout after %.0fs · recreate pool (abandon hung worker)",
            limit,
        )
        # 丢弃卡住的池；下次 get_cpu_pool 新建。旧 worker 可能短暂残留，由 OS 回收。
        shutdown_cpu_pool()
        raise TimeoutError(
            f"重解析超时（>{int(limit)}s），已中止本帖解析以免卡死调度"
        ) from None


async def run_parse_job(fn: Callable[..., T], *args: Any, html: str = "", extra: str = "") -> T:
    """重载荷走进程池，轻载荷走线程池（避免小帖 spawn 开销）。"""
    if is_heavy_parse_payload(html, extra):
        timeout = parse_timeout_sec(html, extra)
        log.info(
            "cpu pool · heavy parse html=%s attach=%s links~%s timeout=%.0fs",
            len(html or ""),
            len(extra or ""),
            _estimate_link_count(html, extra),
            timeout,
        )
        return await run_in_cpu_pool(fn, *args, timeout=timeout)
    return await asyncio.to_thread(fn, *args)
