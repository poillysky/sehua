"""Windows + uvicorn --reload 下，主循环是 Selector，无法 create_subprocess。

Playwright 必须在独立的 Proactor 事件循环线程里启动与操作。
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

log = logging.getLogger(__name__)
T = TypeVar("T")


class _PlaywrightRuntime:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._thread_main,
            name="pw-proactor",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=20):
            raise RuntimeError("浏览器事件循环线程启动超时")

    def _thread_main(self) -> None:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        log.info("Playwright Proactor loop ready (%s)", type(loop).__name__)
        try:
            loop.run_forever()
        finally:
            try:
                loop.close()
            except Exception:
                pass

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            raise RuntimeError("浏览器事件循环未就绪")
        return self._loop


_runtime: _PlaywrightRuntime | None = None
_runtime_lock = threading.Lock()


def get_pw_runtime() -> _PlaywrightRuntime:
    global _runtime
    with _runtime_lock:
        if _runtime is None or _runtime._loop is None or not _runtime._loop.is_running():
            _runtime = _PlaywrightRuntime()
        return _runtime


async def run_on_pw_loop(coro: Coroutine[Any, Any, T]) -> T:
    """在 Playwright 专用 Proactor 循环上执行协程。"""
    runtime = get_pw_runtime()
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is runtime.loop:
        return await coro
    fut = asyncio.run_coroutine_threadsafe(coro, runtime.loop)
    return await asyncio.wrap_future(fut)
