"""请求节奏：基准延迟 + AutoThrottle（按近窗失败率抬升延迟）。"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AutoThrottle:
    base_delay: float = 2.0
    current_delay: float = 2.0
    max_delay: float = 60.0
    window: int = 20
    failure_threshold: int = 5
    consecutive_failures: int = 0
    _outcomes: deque[bool] = field(default_factory=deque)
    _stop: bool = False

    def configure(
        self,
        *,
        base_delay: float,
        max_delay: float = 60.0,
        window: int = 20,
        failure_threshold: int = 5,
    ) -> None:
        self.base_delay = max(0.5, float(base_delay or 2.0))
        self.max_delay = max(5.0, float(max_delay or 60.0))
        self.window = max(5, int(window or 20))
        self.failure_threshold = max(2, min(20, int(failure_threshold or 5)))
        self.current_delay = self.base_delay
        self._outcomes = deque(maxlen=self.window)
        self.consecutive_failures = 0
        # 不在此清除 _stop：避免配置刷新冲掉正在进行的手动停止

    def request_stop(self) -> None:
        self._stop = True

    def clear_stop(self) -> None:
        self._stop = False

    def should_stop(self) -> bool:
        return self._stop

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self._outcomes.append(True)
        self._adjust()

    def record_failure(self) -> int:
        self.consecutive_failures += 1
        self._outcomes.append(False)
        self._adjust()
        return self.consecutive_failures

    def _adjust(self) -> None:
        if not self._outcomes:
            return
        failures = sum(1 for ok in self._outcomes if not ok)
        rate = failures / len(self._outcomes)
        if rate <= 0:
            self.current_delay = max(self.base_delay, self.current_delay * 0.85)
            return
        factor = 1.0 + rate * 6.0
        self.current_delay = min(
            self.max_delay,
            max(self.base_delay, self.base_delay * factor),
        )

    async def sleep_for(self, seconds: float) -> None:
        """可中断睡眠：stop 后最多约 0.5s 内醒来，避免冷却卡住退出。"""
        end = time.monotonic() + max(0.0, float(seconds or 0))
        while True:
            if self._stop:
                return
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            await asyncio.sleep(min(0.5, remaining))

    async def sleep(self) -> None:
        await self.sleep_for(float(self.current_delay or 0))

    def status(self) -> dict[str, Any]:
        total = len(self._outcomes)
        failures = sum(1 for ok in self._outcomes if not ok)
        return {
            "fetch_delay_base": round(self.base_delay, 2),
            "fetch_delay_current": round(self.current_delay, 2),
            "fetch_delay_max": round(self.max_delay, 2),
            "fetch_sample_window": self.window,
            "fetch_success_rate": round((total - failures) / total, 3) if total else None,
            "fetch_sample_size": total,
            "fetch_failure_threshold": self.failure_threshold,
            "consecutive_failures": self.consecutive_failures,
        }


# 进程内单例（调度器共用）
THROTTLE = AutoThrottle()
