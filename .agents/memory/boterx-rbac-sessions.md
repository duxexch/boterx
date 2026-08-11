---
name: Boterx RBAC & sessions
description: Admin roles, permissions, DB tables, and deploy/test notes for the RBAC system
---

# Boterx RBAC & Sessions

## DB tables (in vex_games.db)
- `admin_roles` — uid, role, permissions (JSON), created_at, created_by
- `admin_audit_log` — audit trail for admin actions
- `active_game_sessions` — in-progress game state
- `financial_ledger` — double-entry ledger rows

## RBAC functions (db_manager.py, module scope — NOT in GameDB class)
- `has_permission(uid, perm)` — checks admin_roles table, falls back to ADMIN_USER_IDS env for super_admin
- `get_admin_role(uid)` — returns {role, permissions} dict
- `set_admin_role(uid, role, created_by, extra_permissions)` — inserts/replaces row; returns False if role not in ROLE_PERMISSIONS
- `log_admin_action()` — appends to admin_audit_log

## ROLE_PERMISSIONS (current, db_manager.py module scope)
```
super_admin:     ALL 14 permissions (True)
finance_admin:   approve_deposits, reject_deposits, approve_withdrawals, reject_withdrawals, view_financial, view_statistics
support_admin:   view_financial=True, ban_users=False, send_broadcast=False
game_admin:      manage_games, view_statistics
broadcast_admin: send_broadcast
```
Missing (proposed #43): company_admin (manage_companies + manage_settings + view_statistics),
                         bot_admin (manage_bots + send_broadcast + view_statistics)

## All 14 permissions (super_admin set)
approve_deposits, reject_deposits, approve_withdrawals, reject_withdrawals,
ban_users, unban_users, manage_admins, manage_bots, send_broadcast,
view_financial, manage_games, view_statistics, manage_companies, manage_settings

## Dashboard decorators (dashboard/app.py)
- `@permission_required(perm)` — API routes → 401 if no session, 403 if wrong perm
- `@page_permission_required(perm)` — page routes → 403 HTML page
- `@app.context_processor _inject_admin_context` — injects admin_role + admin_perms dict into every template

## Frontend button hiding
- `base.html` injects `_RBAC` JS object + `rbac(perm)` helper before {% block scripts %}
- Templates use `x-show="rbac('perm')"` / `x-if="condition && rbac('perm')"` / `{% if not admin_perms or admin_perms.get('perm') %}`
- Empty admin_perms dict = super_admin = show everything (no True defaults needed)

## Test suite
- `dashboard/tests/test_rbac.py` — run against localhost:8080
  - Login via POST /vex/admin/admin with {admin_id, password} fields
  - 70/70 has_permission() unit tests pass against live ROLE_PERMISSIONS
  - Verified: no-session → 401 on all sensitive API endpoints
- Proposed follow-up #42: HTTP-level per-role 403 tests still missing

## Deploy note
- git push to GitHub fails (no token) — use: tar czf - <files> | sshpass -p PASS ssh root@IP "cd /opt/bot && tar xzf -"
- Then: systemctl restart boterx boterx-dashboard && python3 migrate.py
- migrate.py is now safe to run: database.py filters None/empty column names from CSV headers

**Why:** RBAC enforcement is double-gated (session + permission). super_admin = env ADMIN_USER_IDS (no DB row needed).
