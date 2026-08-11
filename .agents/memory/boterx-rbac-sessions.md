---
name: Boterx RBAC & sessions
description: New DB tables, RBAC functions, and durable game session management
---

# Boterx RBAC & Active Game Sessions

## New tables (db_manager.py _init_db)
- `active_game_sessions (user_id, game, session_data JSON, bet_amount, created_at, expires_at)`
  PRIMARY KEY (user_id, game) — one active session per user per game
- `admin_roles (uid PK, role, permissions JSON, created_at, created_by)`
- `admin_audit_log (id, uid, action, target, details, ip, timestamp)`
- `financial_ledger (id, user_id, amount, direction, reason, reference_id, balance_after, timestamp)`

## RBAC functions (module-level in db_manager.py, NOT in GameDB class)
- `get_admin_role(uid)` → `{'role': str, 'permissions': dict}`
  Falls back to super_admin for UIDs in ADMIN_USER_IDS env var
- `set_admin_role(uid, role, created_by, extra_permissions)` → bool
- `has_permission(uid, permission)` → bool
- `log_admin_action(uid, action, target, details, ip)` → None

## Active session functions (module-level in db_manager.py)
- `get_active_game_session(user_id, game)` → dict | None (respects TTL)
- `set_active_game_session(user_id, game, data, bet_amount, ttl_seconds)` → None
- `delete_active_game_session(user_id, game)` → None
- `cleanup_expired_game_sessions()` → int (count deleted)
- `refund_expired_game_sessions(gdb_instance)` → list — auto-refunds bets on expiry

## GAME_SESSION_TTL defaults
mines=600s, plinko=300s, snatch=120s, wheel=180s, crash=60s, aviator=60s

## Dashboard RBAC decorator (NOT yet added to app.py)
- `has_permission()` imported from db_manager when needed
- `log_admin_action()` can be called from routes for audit trail
- Current dashboard still uses flat ADMIN_IDS check — RBAC DB is ready but decorator not wired

**Why:** Games (especially mines) need durable bet state — if server restarts mid-game the bet was lost. active_game_sessions solves this with TTL + auto-refund. Admin roles enable multi-department access without sharing one password.
