# LangSense / DUX Telegram Bot — Project Brain 🧠

> **Last updated:** 2026-07-23 · **Analyzed by:** Codely CLI Deep Analysis
> **Project root:** `C:\Users\gnz\Downloads\bot2\bot`

---

## 1. Project Identity

| Field | Value |
|-------|-------|
| **Name** | LangSense / DUX Financial Telegram Bot |
| **Type** | Telegram Bot — Financial Services (deposit/withdraw/complaints) |
| **Language** | Python 3.8+ |
| **Primary UI Language** | Arabic (RTL) + English |
| **Primary entry point** | `comprehensive_bot.py` (6606 lines — the production bot) |
| **Secondary entry point** | `main.py` → `bot.py` (Aiogram v3 — incomplete, partial handlers) |
| **Data storage** | CSV files (primary), SQLite (simple_bot.py only) |
| **Bot API** | Raw HTTP via `urllib.request` (comprehensive_bot.py), Aiogram v3 (main.py) |
| **External dependencies** | `python-dotenv` only (comprehensive_bot.py); Aiogram+SQLAlchemy (main.py) |

---

## 2. File Inventory & Purpose

### 2.1 Production Code (ACTIVE)

| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| `comprehensive_bot.py` | 6606 | **THE BOT** — all features, single-file architecture | ✅ Production |
| `excel_formatter.py` | 347 | Professional Excel/CSV report generator (openpyxl) | ✅ Support |
| `run_windows.bat` | — | Windows launcher (venv + pip + bot selector) | ✅ |
| `run_linux.sh` | — | Linux setup + launcher | ✅ |
| `run_vps.sh.bat` | — | VPS launcher (Windows→Linux bridge) | ✅ |

### 2.2 Legacy / Alternative Versions (INACTIVE)

| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| `advanced_bot.py` | 1701 | Earlier version with CSV, less features | ⚠️ Legacy |
| `simple_bot.py` | ~350 | Minimal SQLite version | ⚠️ Legacy |
| `simple_improved_bot.py` | 884 | Improved CSV version | ⚠️ Legacy |
| `simple_payment_bot.py` | 706 | Payment-method-focused version | ⚠️ Legacy |
| `fixed_bot.py` | 527 | Bugfix attempt | ⚠️ Legacy |
| `excel_bot.py` | 727 | Excel-storage version | ⚠️ Legacy |
| `test_bot.py` | 124 | DB/API test script | 🔧 Test |

### 2.3 Aiogram v3 Modular Architecture (INCOMPLETE)

| File | Purpose | Status |
|------|---------|--------|
| `main.py` | Entry point — DB init + bot start | ⚠️ Partial |
| `bot.py` | Dispatcher setup + router registration | ⚠️ Partial |
| `config.py` | Environment config with validation | ✅ Good |
| `models.py` | SQLAlchemy models (User, Language, Country, Outbox, etc.) | ✅ Good |
| `handlers/start.py` | /start + registration + deposit/withdraw stubs | ⚠️ Stubs only |
| `handlers/admin.py` | Admin panel (users, langs, countries, outbox) | ⚠️ Partial |
| `handlers/broadcast.py` | Mass messaging with targeting | ✅ Good |
| `handlers/user_settings.py` | Language/country/notifications | ✅ Good |
| `handlers/announcements.py` | Announcement creation wizard | ✅ Good |
| `services/i18n.py` | JSON-based translations | ✅ Good |
| `services/customer_id.py` | Unique customer code generation | ✅ Good |
| `services/broadcast_service.py` | Async broadcast queue + rate limiting | ✅ Good |
| `utils/auth.py` | Admin decorator + permission levels | ✅ Good |
| `utils/keyboards.py` | All keyboard layouts | ✅ Good |
| `translations/ar.json` | Arabic strings | ✅ Complete |
| `translations/en.json` | English strings | ✅ Complete |

### 2.4 Data Files (CSV/JSON)

| File | Schema | Purpose |
|------|--------|---------|
| `users.csv` | `telegram_id, name, phone, customer_id, language, date, is_banned, ban_reason, currency` | User registry |
| `transactions.csv` | `id, customer_id, telegram_id, name, type, company, wallet_number, amount, exchange_address, status, date, admin_note, processed_by, currency` | All financial transactions |
| `companies.csv` | `id, name, type, details, is_active` | Registered companies |
| `payment_methods.csv` | `id, company_id, method_name, method_type, account_data, additional_info, status, created_date` | Payment methods per company |
| `complaints.csv` | `id, customer_id, subject, message, status, date, admin_response` | User complaints |
| `exchange_addresses.csv` | `id, address, is_active` | Withdrawal pickup addresses |
| `system_settings.csv` | `setting_key, setting_value, description` | System configuration |
| `button_labels.csv` | `original_text, new_text, is_active` | Admin-customizable button labels |
| `admin_actions_log.csv` | `timestamp, admin_id, action_type, details` | Admin audit trail |
| `admin_permissions.json` | `{telegram_id: {buttons: {label: bool}}}` | Per-admin button permissions |

---

## 3. Architecture — comprehensive_bot.py

### 3.1 Class Structure

```
ComprehensiveDUXBot
├── __init__()              # State + currencies + translations + backup thread
├── API Layer
│   ├── api_call()          # JSON POST to Telegram API
│   ├── send_message()      # Text + keyboard
│   ├── send_document()     # File upload (multipart)
│   ├── get_updates()       # Long polling
│   └── send_message_without_keyboard()
├── Data Layer
│   ├── init_files()        # Create all CSVs with defaults
│   ├── find_user()         # Read user from CSV
│   ├── get_companies()     # Read companies (filter by type/active)
│   ├── get_payment_methods_by_company()
│   ├── get_transaction()   # Read single transaction
│   ├── get_setting()       # Read system_settings.csv
│   └── get_exchange_address()
├── Keyboard Layer
│   ├── main_keyboard()     # User menu (AR/EN)
│   ├── admin_keyboard()    # Admin panel (permission-filtered)
│   ├── companies_keyboard()
│   └── transform_keyboard() # Apply button label overrides
├── User Flows
│   ├── handle_start()      # Registration / welcome back
│   ├── handle_registration() # Name → phone → customer_id
│   ├── create_deposit_request()  # Company → method → wallet → amount
│   ├── process_deposit_flow()    # State machine for deposit
│   ├── create_withdrawal_request() # Company → method → wallet → amount → address → code
│   ├── process_withdrawal_flow()   # State machine for withdrawal
│   ├── handle_complaint_start() → save_complaint()
│   ├── show_currency_selection() → handle_currency_selection()
│   └── show_user_transactions() / show_user_profile()
├── Admin Flows (30+ features)
│   ├── handle_admin_panel() → handle_admin_actions()
│   ├── Pending requests / Approved transactions
│   ├── approve/reject transaction (with reason wizard)
│   ├── Company CRUD wizard (add/edit/delete with confirmation)
│   ├── Payment method CRUD wizard (add/edit/delete/enable/disable)
│   ├── User management (ban/unban/search)
│   ├── Admin management (permanent/temporary/remove)
│   ├── Broadcast messaging
│   ├── Complaint management + reply wizard
│   ├── Support data editor (phone/telegram/email/hours)
│   ├── System settings viewer/editor
│   ├── Excel report generator
│   ├── Quick copy commands
│   ├── Button label editor
│   └── Backup system (auto 6h + manual ZIP)
├── Security
│   ├── is_admin()          # 3 sources: env, session, temp
│   ├── admin_permissions   # Per-admin button visibility JSON
│   └── log_admin_action() # Audit trail CSV
├── Backup System
│   ├── start_backup_scheduler()  # Thread, every 6 hours
│   ├── create_backup_zip()
│   ├── create_summary_report()
│   └── send_backup_to_admins()
└── Main Loop
    └── run()               # Long polling loop
```

### 3.2 State Machine

Uses `self.user_states` dict. Keys = `telegram_id`, values = state strings.

**Deposit:** `selecting_deposit_company` → `deposit_wallet_<cid>_<cname>_<mid>` → `deposit_amount_<cid>_<cname>_<mid>_<wallet>` → COMMIT

**Withdrawal:** `selecting_withdraw_company` → `withdraw_wallet_<...>` → `withdraw_amount_<...>` → `withdraw_confirmation_code_<...>` → `withdraw_final_confirm_<...>` → COMMIT

**Registration:** `registering_name` → `registering_phone_<name>` → SAVE

**Admin states:** `admin_broadcasting`, `adding_company_*`, `editing_company_*`, `confirming_company_delete`, `deleting_company_<id>`, `sending_user_message_*`, `selecting_method_to_*`, `editing_method_*`, `replying_to_complaint_<id>`, `editing_support_*`, `choose_button_to_edit`, `awaiting_reject_reason_*`

### 3.3 Transaction ID Formats

| Type | Prefix | Format | Example |
|------|--------|--------|---------|
| Deposit | `DEP` | `DEPYYYYMMDDHHMMSS` | `DEP20260723143000` |
| Withdrawal | `WTH` | `WTHYYYYMMDDHHMMSS` | `WTH20260723143000` |
| Complaint | `COMP` | `COMPYYYYMMDDHHMMSS` | `COMP20260723143000` |
| Customer ID | `C` | `C<6-digit-timestamp>` | `C824717` |

### 3.4 Currency System

18 currencies: SAR, AED, EGP, KWD, QAR, BHD, OMR, JOD, LBP, IQD, SYP, MAD, TND, DZD, LYD, USD, EUR, TRY. Each has `name` (Arabic), `symbol`, `flag` (emoji).

---

## 4. Two Architectures — Comparison

| Aspect | comprehensive_bot.py | main.py + bot.py |
|--------|---------------------|------------------|
| Bot API | Raw urllib HTTP | Aiogram v3 |
| Storage | CSV files | SQLAlchemy async |
| FSM | dict (string-based) | Aiogram FSMContext |
| Structure | Single 6606-line file | Modular handlers/services/utils |
| Deposit/Withdraw | Full workflow | Stubs only |
| Admin panel | 30+ features | Basic stats + user list |
| Companies/Methods | Full CRUD + wizards | Not implemented |
| Currencies | 18 currencies | Not implemented |
| Backup | Auto 6h + manual | Not implemented |
| Button customization | Admin-editable | Not implemented |
| Admin permissions | Per-button filtering | Not implemented |
| Maturity | Production-ready | Skeleton |

---

## 5. Known Issues

### Critical
1. No file locking on CSV writes — concurrent access risk
2. State strings use `_` separator — breaks on values with underscores
3. `handle_language_change()` writes users.csv missing `currency` column — data loss
4. `ban_user_admin()` / `unban_user_admin()` same issue
5. `BOT_TOKEN` printed to console on startup

### Architecture
6. 7+ duplicate bot implementations — code sprawl
7. Single 6606-line file — no separation of concerns
8. No tests, no CI/CD
9. `pyproject.toml` has empty dependencies
10. Duplicate `💾 نسخة احتياطية فورية` button in admin keyboard
11. `get_all_payment_methods()` defined twice with different logic (lines ~4100 filters active only, line ~5300 returns all)

---

## 6. Team Perspective

### 🏗️ Architect
- comprehensive_bot.py works but won't scale. Aiogram v3 migration is right direction but incomplete.
- CSV → SQLite/PostgreSQL migration needed.
- State machine needs proper FSM (Aiogram's or custom class).

### 🔧 Backend Developer
- Deposit/withdraw flows well-designed, need refactoring into separate handlers.
- `handle_admin_actions()` is 400+ line if/elif chain — needs dispatch table.
- CSV read/write repeated 30+ times — needs data layer.

### 🎨 UX Developer
- Keyboard layouts clean and consistent.
- Button label customization is powerful.
- Error recovery (super_reset) well-thought-out.
- Arabic RTL good but some messages mix AR/EN.

### 🔒 Security Engineer
- Admin from env is good. Temp admin system reasonable.
- No input sanitization (CSV injection risk).
- No rate limiting on user actions.
- Token leaked to console.

### 📊 Data Analyst
- Statistics comprehensive. Excel report well-structured.
- No historical trends — all point-in-time.

### 🧪 QA Engineer
- No automated tests. Manual only.
- Error handling swallows exceptions silently.

---

## 7. Environment Variables

```env
BOT_TOKEN=<telegram_bot_token>
ADMIN_USER_IDS=123456789,987654321
DATABASE_URL=sqlite+aiosqlite:///./langsense.db
BROADCAST_RATE_LIMIT=30
BROADCAST_CHUNK_SIZE=100
DEFAULT_LANGUAGE=ar
DEFAULT_COUNTRY=SA
CUSTOMER_ID_PREFIX=C
CUSTOMER_ID_YEAR_FORMAT=2025
MAX_FILE_SIZE=20
USERS_PER_PAGE=10
LOG_LEVEL=INFO
```

---

## 8. Quick Commands

```bash
# Run production bot
python comprehensive_bot.py

# Run via launcher
run_windows.bat          # Windows
./run_linux.sh           # Linux

# Dependencies (minimal for comprehensive_bot.py)
pip install python-dotenv openpyxl

# Dependencies (Aiogram v3 version)
pip install aiogram sqlalchemy aiosqlite asyncpg python-dotenv aiohttp pillow apscheduler
```
