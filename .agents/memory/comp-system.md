---
name: Compensation system flow
description: How the SVRP compensation (تعويض) flow is wired across web, bot, and admin
---
- Player web flow lives in wallet.html (`/api/player/companies`, `register-account`, `compensation-request`) — do NOT build a parallel /api/comp player system; only admin decision endpoints are under `/api/comp/admin/*`.
- Company account registrations are `pending` from BOTH web and bot (svrp.add_user_company_account) until admin approves in the SVRP page "حسابات الشركات" tab; claims require status active/approved.
- Companies promo_code field added to companies.csv + admin form + public list.
- Unlock rules: new referral → unfreeze 10% of referrer frozen (inside svrp.process_referral_code); p2p transfer ≥10% of frozen → sender unlocks 5% extra; receiver gets amount frozen.
- **Why:** money moves must use `transfer_svrp_frozen_p2p` (db_manager, one SAVEPOINT, svrp_p2p_transfer_log PK idempotency, SQLite authoritative) — CSV wallets are display mirrors only; authorizing off CSV caused negative-balance risk.
- Player/admin Telegram notifications via `_comp_tg`/`_comp_alert_admins` in dashboard/app.py (best-effort, BOT_TOKEN sendMessage).
