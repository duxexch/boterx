---
name: Boterx concurrent bot
description: Architecture of the rewritten run() loop with ThreadPoolExecutor and rate limiting
---

# Boterx Concurrent Bot Architecture

## run() method — comprehensive_bot.py
- Uses `ThreadPoolExecutor(max_workers=20)` — each update dispatched to pool
- Per-user `threading.Semaphore(MAX_CONCURRENT_PER_USER=2)` — prevents same user flooding
- Broadcast moved to daemon thread `_broadcast_worker` (every 30s) — main loop never blocked
- Processed-update dedup ring (set, max 3000 entries, then clear)

## Rate limiting — bot_utils/rate_limiter.py
- `SlidingWindowLimiter` class: thread-safe deque per key, cleanup daemon
- Shared instances: `user_message_limiter` (10/10s), `user_callback_limiter` (30/10s),
  `financial_limiter` (5/60s), `ip_login_limiter` (5/60s), `game_api_limiter` (20/10s)
- Import: `from bot_utils.rate_limiter import user_message_limiter, user_callback_limiter, start_cleanup_thread`

## Notification hub — bot_utils/notification_hub.py
- `NotificationHub`: priority queue (CRITICAL/HIGH/NORMAL/LOW)
- Rate limits: 1 msg/s per user, 25 msg/s global
- Background sender thread with retry logic (3 attempts, exponential backoff)
- Init: `hub.init(api_call_fn)` — call after bot construction
- Singleton: `from bot_utils.notification_hub import hub`
- Confirmed working: logs show "NotificationHub started." on boot

## Imports added to comprehensive_bot.py
```python
from bot_utils.rate_limiter import user_message_limiter, user_callback_limiter, start_cleanup_thread as _start_rl_cleanup
from bot_utils.notification_hub import hub as _notif_hub
from concurrent.futures import ThreadPoolExecutor
```

## __init__ additions
```python
_notif_hub.init(self.api_call)
self.notif = _notif_hub
_start_rl_cleanup(interval_sec=60.0)
```

**Why:** Original run() was a single-threaded sequential loop — one slow handler blocked all 5000 users. ThreadPoolExecutor with semaphore gives parallelism without unbounded concurrency per user.
