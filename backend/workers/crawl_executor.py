"""爬虫专用事件循环：与 uvicorn 主循环隔离。

Windows 上 uvicorn --reload 常用 Selector 循环，同步/半同步爬取一旦跑在主循环上，
/health、登录会一起卡死。所有 run_crawl_once / 重爬 / 连续调度等协程应经本模块提交。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

log = logging.getLogger(__name__)
T = TypeVar("T")

_executor: "_CrawlExecutor | None" = None
_executor_lock = threading.Lock()


class _CrawlExecutor:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()
        self._futures: set[concurrent.futures.Future[Any]] = set()
        self._fut_lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._thread_main,
            name="crawl-executor",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=20):
            raise RuntimeError("爬虫事件循环线程启动超时")

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        def _mark_ready() -> None:
            # 必须在 run_forever 已启动后置位：此前 is_running() 仍为 False，
            # 会导致「日志已 ready、立刻 submit 却报未就绪」的竞态（loop/start 500）。
            self._ready.set()
            log.info("crawl executor loop ready (%s)", type(loop).__name__)

        loop.call_soon(_mark_ready)
        try:
            loop.run_forever()
        finally:
            try:
                loop.close()
            except Exception:
                pass

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError("爬虫事件循环未就绪")
        return self._loop

    def submit(self, coro: Coroutine[Any, Any, T]) -> concurrent.futures.Future[T]:
        fut: concurrent.futures.Future[T] = asyncio.run_coroutine_threadsafe(coro, self.loop)
        with self._fut_lock:
            self._futures.add(fut)

        def _done(f: concurrent.futures.Future[Any]) -> None:
            with self._fut_lock:
                self._futures.discard(f)

        fut.add_done_callback(_done)
        return fut

    def cancel_all(self) -> int:
        """取消本执行器上尚未结束的任务（供紧急停止）。"""
        with self._fut_lock:
            pending = [f for f in self._futures if not f.done()]

        def _cancel_tasks() -> None:
            for task in asyncio.all_tasks(self.loop):
                if not task.done():
                    task.cancel()

        try:
            self.loop.call_soon_threadsafe(_cancel_tasks)
        except Exception:
            log.exception("crawl executor cancel_all failed")
        n = 0
        for f in pending:
            if f.cancel():
                n += 1
        return max(n, len(pending))


def get_crawl_executor() -> _CrawlExecutor:
    global _executor
    with _executor_lock:
        if _executor is None or _executor._loop is None or not _executor._loop.is_running():
            _executor = _CrawlExecutor()
        return _executor


def spawn_crawl(
    coro: Coroutine[Any, Any, T],
    *,
    name: str = "crawl",
) -> concurrent.futures.Future[T]:
    """在爬虫线程启动协程（火忘），不阻塞调用方。"""

    async def _wrapped() -> T:
        try:
            return await coro
        except asyncio.CancelledError:
            log.info("crawl cancelled · %s", name)
            raise
        except Exception:
            log.exception("crawl failed · %s", name)
            raise

    return get_crawl_executor().submit(_wrapped())


async def await_crawl(
    coro: Coroutine[Any, Any, T],
    *,
    name: str = "crawl",
) -> T:
    """在爬虫线程跑协程，当前（通常为 uvicorn）循环只等 Future，可继续处理登录/健康检查。"""
    fut = spawn_crawl(coro, name=name)
    return await asyncio.wrap_future(fut)


def cancel_all_crawls() -> int:
    try:
        return get_crawl_executor().cancel_all()
    except Exception:
        log.exception("cancel_all_crawls")
        return 0
