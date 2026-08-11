#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NotificationHub — priority-queue notification dispatcher for the bot.

Replaces ad-hoc send_message() call sites with a central service that:
  • Enforces Telegram's 30 msg/s global rate limit (uses 25 to stay safe)
  • Enforces 1 msg/s per-user to avoid flooding individual chats
  • Queues messages by priority (CRITICAL > HIGH > NORMAL > LOW)
  • Never blocks the caller — put() is non-blocking
  • Runs a single background sender thread (safe on 1-CPU servers)

Usage:
    from bot_utils.notification_hub import hub

    hub.send(chat_id, text, priority=hub.HIGH)
    hub.send_admin(text, admin_ids, priority=hub.CRITICAL)
    hub.broadcast(text, user_ids, priority=hub.LOW)
"""

import threading
import time
import logging
import queue
from dataclasses import dataclass, field
from typing import Optional, List

logger = logging.getLogger('boterx.notifications')

# Priority constants (lower number = higher priority)
CRITICAL = 0   # Lockdown alerts, security events
HIGH     = 1   # Transaction results, admin actions
NORMAL   = 2   # Game results, routine notifications
LOW      = 3   # Broadcasts, promotional


@dataclass(order=True)
class _NotifItem:
    priority: int
    seq: int = field(compare=True)          # tiebreak by insertion order
    chat_id: str = field(compare=False)
    text: str = field(compare=False)
    parse_mode: str = field(compare=False, default='HTML')
    keyboard: Optional[dict] = field(compare=False, default=None)
    retry_count: int = field(compare=False, default=0)


class NotificationHub:
    """Central notification dispatcher.

    Args:
        send_fn: Callable(method, data) → Telegram API response dict or None.
                 Should be bot.api_call — injected after init to avoid
                 circular imports.
    """

    CRITICAL = CRITICAL
    HIGH     = HIGH
    NORMAL   = NORMAL
    LOW      = LOW

    # Per-user minimum interval between messages (seconds)
    _USER_INTERVAL = 1.0
    # Global minimum interval between any two sends (seconds, ≈ 25 msg/s)
    _GLOBAL_INTERVAL = 1.0 / 25.0
    # Max retries for failed sends
    _MAX_RETRY = 2

    def __init__(self):
        self._q: queue.PriorityQueue = queue.PriorityQueue()
        self._seq = 0
        self._seq_lock = threading.Lock()
        self._send_fn = None          # injected via .init(send_fn)
        self._last_user_send: dict[str, float] = {}
        self._last_global_send: float = 0.0
        self._state_lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def init(self, send_fn):
        """Inject the Telegram send callable and start the worker thread."""
        self._send_fn = send_fn
        if not self._running:
            self._running = True
            self._thread = threading.Thread(
                target=self._worker, daemon=True, name='notif_hub'
            )
            self._thread.start()
            logger.info("NotificationHub started.")
        return self

    def send(self, chat_id, text: str, priority: int = NORMAL,
             parse_mode: str = 'HTML', keyboard=None):
        """Queue a single message. Non-blocking."""
        self._enqueue(str(chat_id), text, priority, parse_mode, keyboard)

    def send_admin(self, text: str, admin_ids: list, priority: int = HIGH,
                   parse_mode: str = 'HTML'):
        """Queue the same message to every admin ID."""
        for aid in admin_ids:
            self._enqueue(str(aid), text, priority, parse_mode)

    def broadcast(self, text: str, user_ids: list, priority: int = LOW,
                  parse_mode: str = 'HTML'):
        """Queue one message per user. Use LOW priority for mass broadcasts."""
        for uid in user_ids:
            self._enqueue(str(uid), text, priority, parse_mode)

    def qsize(self) -> int:
        return self._q.qsize()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _next_seq(self) -> int:
        with self._seq_lock:
            self._seq += 1
            return self._seq

    def _enqueue(self, chat_id: str, text: str, priority: int,
                 parse_mode: str = 'HTML', keyboard=None):
        item = _NotifItem(
            priority=priority,
            seq=self._next_seq(),
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            keyboard=keyboard,
        )
        try:
            self._q.put_nowait(item)
        except queue.Full:
            logger.warning("NotificationHub queue full — dropping LOW priority item.")

    def _worker(self):
        """Background sender thread: rate-limits and dispatches messages."""
        while self._running:
            try:
                item = self._q.get(timeout=2)
            except queue.Empty:
                continue

            if not self._send_fn:
                self._q.put(item)   # re-queue until init() is called
                time.sleep(0.5)
                continue

            # ── Per-user rate limit ────────────────────────────────────────
            now = time.time()
            with self._state_lock:
                last = self._last_user_send.get(item.chat_id, 0.0)
                wait_user = self._USER_INTERVAL - (now - last)
                if wait_user > 0:
                    # Re-queue with same priority; will be picked up soon
                    self._q.put(item)
                    time.sleep(min(wait_user, 0.1))
                    continue

                # ── Global rate limit ──────────────────────────────────────
                wait_global = self._GLOBAL_INTERVAL - (now - self._last_global_send)
                if wait_global > 0:
                    time.sleep(wait_global)

                self._last_user_send[item.chat_id] = time.time()
                self._last_global_send = time.time()

            # ── Send ──────────────────────────────────────────────────────
            try:
                data = {
                    'chat_id': item.chat_id,
                    'text': item.text,
                    'parse_mode': item.parse_mode,
                }
                if item.keyboard:
                    import json
                    data['reply_markup'] = json.dumps(item.keyboard) \
                        if not isinstance(item.keyboard, str) else item.keyboard
                result = self._send_fn('sendMessage', data)
                if result and result.get('ok'):
                    logger.debug("Sent to %s (priority=%d)", item.chat_id, item.priority)
                else:
                    desc = (result or {}).get('description', 'unknown')
                    if 'blocked' in desc or 'chat not found' in desc:
                        pass  # user blocked bot — don't retry
                    elif item.retry_count < self._MAX_RETRY:
                        item.retry_count += 1
                        self._q.put(item)
                        logger.warning("Retrying send to %s (%s)", item.chat_id, desc)
            except Exception as exc:
                logger.error("NotificationHub send error: %s", exc)
                if item.retry_count < self._MAX_RETRY:
                    item.retry_count += 1
                    self._q.put(item)


# Singleton — import this in comprehensive_bot.py and inject send_fn
hub = NotificationHub()
