---
name: Boterx maintenance daemons
description: Session cleanup, FSM state cleanup, and replay-protection nonce store added to bot + dashboard
---

## Unified session-maintenance daemon (dashboard/app.py)

Replaced the old `_mines_cleanup_daemon` (10-min, mines-only) with `_session_maintenance_daemon` (5-min interval):
1. Calls `refund_expired_game_sessions()` for ALL games — bet refunded via idempotent credit
2. For refunded mines sessions, immediately evicts the matching `mines_user_sessions.json` entry (prevents play-after-refund)
3. Prunes both mines JSON files
4. Calls `cleanup_expired_nonces()` to keep auth_nonces table bounded

**Why:** startup-only refund left bets locked if server ran continuously; mines JSON prune silently deleted bet info without refunding.

## FSM stale-state cleanup (comprehensive_bot.py)

`_fsm_cleanup_worker` thread in `run()` — runs every 15 minutes.
Queries `user_states WHERE updated_at < NOW()-45min`, clears deposit_*/withdraw_*/selecting_deposit/selecting_withdraw states.

**Why:** users who walk away mid deposit/withdraw flow are permanently stuck until they press Cancel.

## Replay-protection nonce store (db_manager.py + dashboard/app.py)

`auth_nonces` table in `vex_games.db`:
- `check_and_mark_nonce(token_hash, user_id, ttl=3720)` — INSERT OR IGNORE, returns False on replay
- `cleanup_expired_nonces()` — deletes expired rows
- Wired into `webapp_auth()` after HMAC+freshness check: SHA-256 hash of initData → 403 REPLAY_INIT_DATA on reuse
- Fail-open: if nonce DB write fails, request is allowed through (logged)

**Why:** same initData could be replayed from another device/IP within the 1-hour auth_date window; table survives restarts so replay protection is durable.
