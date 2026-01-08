import time
from collections import deque

class CancelBackoff:
    """
    对外只有一个方法：next_sleep()
    每调用一次，表示发生了一次 cancel，并返回本次应 sleep 的秒数。

    规则：
    - 基准 sleep = base_seconds（默认 1s）
    - 在 window_seconds（默认 30s）内，每多一次 cancel，额外 + step_seconds（默认 3s）
    - 超出窗口的 cancel 自动失效
    """
    def __init__(self, base_seconds=1, step_seconds=3, window_seconds=30, max_seconds=None):
        self.base = float(base_seconds)
        self.step = float(step_seconds)
        self.window = float(window_seconds)
        self.max_seconds = None if max_seconds is None else float(max_seconds)
        self._events = deque()

    def next_sleep(self):
        now = time.monotonic()

        # 清理窗口外事件
        cutoff = now - self.window
        while self._events and self._events[0] <= cutoff:
            self._events.popleft()

        # 记录本次 cancel
        self._events.append(now)

        # 计算退避时间
        sec = self.base + self.step * (len(self._events) - 1)
        if self.max_seconds is not None:
            sec = min(sec, self.max_seconds)

        return sec
