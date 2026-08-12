#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sliding-window rate limiter — thread-safe, no Redis required.
Provides per-user (bot) and per-IP (dashboard) rate limiting.
"""

import threading
import time
from collections import deque


class SlidingWindowLimiter:
    """Thread-safe sliding-window rate limiter.

    Args:
        max_calls: Maximum allowed calls in the window.
        window_sec: Window duration in seconds.
    """

    def __init__(self, max_calls: int = 10, window_sec: float = 10.0):
        self.max_calls = max_calls
        self.window_sec = window_sec
        self._windows: dict[str, deque] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        """Return True if the key is within the rate limit, False if exceeded."""
        now = time.monotonic()
        cutoff = now - self.window_sec
        with self._lock:
            if key not in self._windows:
                self._windows[key] = deque()
            dq = self._windows[key]
            # Evict expired timestamps
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self.max_calls:
                return False
            dq.append(now)
            return True

    def is_blocked(self, key: str) -> bool:
        """Inverse of is_allowed — True means the key is rate-limited."""
        return not self.is_allowed(key)

    def remaining(self, key: str) -> int:
        """How many more calls are allowed in the current window."""
        now = time.monotonic()
        cutoff = now - self.window_sec
        with self._lock:
            dq = self._windows.get(key, deque())
            used = sum(1 for t in dq if t >= cutoff)
            return max(0, self.max_calls - used)

    def cleanup_stale(self, max_age_sec: float = 300.0):
        """Remove keys that have been idle longer than max_age_sec."""
        now = time.monotonic()
        cutoff = now - max_age_sec
        with self._lock:
            stale = [k for k, dq in self._windows.items()
                     if not dq or dq[-1] < cutoff]
            for k in stale:
                del self._windows[k]


# ── Shared instances — import and use directly ────────────────────────────────

# Bot: max 10 messages per user per 10 s
user_message_limiter = SlidingWindowLimiter(max_calls=10, window_sec=10.0)

# Bot: max 30 callback queries per user per 10 s (buttons can be pressed faster)
user_callback_limiter = SlidingWindowLimiter(max_calls=30, window_sec=10.0)

# Bot: max 5 deposit/withdrawal initiation per user per 60 s
user_financial_limiter = SlidingWindowLimiter(max_calls=5, window_sec=60.0)

# Dashboard: max 5 login attempts per IP per 60 s
ip_login_limiter = SlidingWindowLimiter(max_calls=5, window_sec=60.0)

# Dashboard game API: max 20 requests per user per 10 s
game_api_limiter = SlidingWindowLimiter(max_calls=20, window_sec=10.0)

# Global Telegram send rate: Telegram allows 30 msg/s globally
_telegram_send_limiter = SlidingWindowLimiter(max_calls=25, window_sec=1.0)


def telegram_send_allowed() -> bool:
    """Return True if we are within the global Telegram send rate limit."""
    return _telegram_send_limiter.is_allowed('__global__')


def start_cleanup_thread(interval_sec: float = 60.0):
    """Spawn a daemon thread that periodically removes stale limiter entries."""
    all_limiters = [
        user_message_limiter, user_callback_limiter, user_financial_limiter,
        ip_login_limiter, game_api_limiter, _telegram_send_limiter,
    ]

    def _loop():
        while True:
            time.sleep(interval_sec)
            for lim in all_limiters:
                try:
                    lim.cleanup_stale()
                except Exception:
                    pass

    t = threading.Thread(target=_loop, daemon=True, name='rate_limiter_cleanup')
    t.start()
    return t
