# LangSense / DUX Telegram Bot — Project Brain 🧠

> **Last updated:** 2026-07-26 · **Analyzed by:** Codely CLI
> **Project root:** `C:\Users\gnz\Downloads\bot2\bot`
> **Repo:** `github.com/duxexch/boterx`

---

## 1. Project Identity

| Field | Value |
|-------|-------|
| **Name** | LangSense / DUX Financial Telegram Bot ("Boterx") |
| **Type** | Telegram Bot — Financial Services (deposit/withdraw/complaints/P2P matching) |
| **Language** | Python 3.11+ |
| **UI Languages** | 17 languages (ar, en, fr, es, de, it, pt, ru, zh, tr, ur, hi, fa, id, ja, ko, th) |
| **Primary entry point** | `comprehensive_bot.py` (~10,400 lines — single class `ComprehensiveDUXBot`) |
| **Data storage** | CSV files (utf-8-sig encoding, threading.Lock per file) |
| **Bot API** | Raw HTTP via `urllib.request` (long-polling) |
| **Dependencies** | `python-dotenv`, `openpyxl` (Excel reports) |
| **Deploy** | Render.com (health check server on PORT env var) |

---

## 2. File Inventory

### 2.1 Production Code (ACTIVE)

| File | Lines | Purpose |
|------|-------|---------|
| `comprehensive_bot.py` | ~10,400 | **THE BOT** — all features, single-file architecture |
| `svrp.py` | ~970 | 💎 Smart Recovery — SVRPManager (credits, wallets, tasks, promo codes, tiers) |
| `matching.py` | ~600 | 🔄 P2P Matching — MatchManager (requests, matches, chat, ratings, disputes) |
| `theme_config.py` | ~230 | 🎨 Theme system — 3 themes (Gold, Ocean, Purple) with emoji/color config |

### 2.2 i18n System

| File | Keys | Purpose |
|------|------|---------|
| `i18n/ar.json` | 270 | Arabic translations (primary) |
| `i18n/en.json` | 270 | English translations |
| `i18n/{de,es,fa,fr,hi,id,it,ja,ko,pt,ru,th,tr,ur,zh}.json` | 270 each | 15 other languages |

### 2.3 Data Files (CSV)

| File | Purpose |
|------|---------|
| `users.csv` | User accounts (telegram_id, name, phone, customer_id, language, currency, is_banned) |
| `transactions.csv` | All transactions (deposit/withdraw, status, amounts, currency) |
| `companies.csv` | Exchange companies (name, type, icon, address) |
| `payment_methods.csv` | Payment methods per company (method_name, type, icon) |
| `complaints.csv` | Customer complaints |
| `referrals.csv` | Referral links (referrer → referred) |
| `app_links.csv` | App store links (name, icon_url, download_url, description) |
| `svrp_credits.csv` | Recovery credits (keep/shared, pending/active/used/expired) |
| `svrp_wallets.csv` | Recovery wallets (balance, pending, wagering progress) |
| `svrp_tasks.csv` | Daily tasks (deposit_count, deposit_amount, referral_count) |
| `svrp_promo_codes.csv` | Promo codes (RCV prefix, creator, amount, max_uses) |
| `svrp_user_groups.csv` | User tiers (bronze/silver/gold/platinum) |
| `match_requests.csv` | P2P match requests |
| `matches.csv` | Active P2P matches |
| `chat_messages.csv` | P2P chat messages |
| `ratings.csv` | P2P user ratings |
| `disputes.csv` | P2P disputes |
| `system_settings.csv` | System settings (min_deposit, active_theme, etc.) |
| `admin_permissions.json` | Per-admin button visibility |
| `button_labels.csv` | Editable button labels |

### 2.4 Documentation

| File | Purpose |
|------|---------|
| `PROJECT_BRAIN.md` | This file — full project analysis |
| `ARCHITECTURE.md` | Architecture maps, data flows, state machines |
| `DEV_GUIDE.md` | Coding conventions, patterns, testing checklist |
| `RENDER_GUIDE.md` | Deployment instructions for Render.com |
| `MATCHING_GUIDE.md` | Admin guide for P2P matching system |
| `CHANGELOG.md` | Chronological change log |
| `Procfile` | `web: python comprehensive_bot.py` |
| `requirements.txt` | `python-dotenv`, `openpyxl` |

---

## 3. Architecture Overview

### 3.1 Core Class: `ComprehensiveDUXBot`

Single class with ~60+ methods:
- **Init:** loads .env, creates CSV files, loads i18n (17 langs), initializes SVRP/Matching/Theme
- **HTTP layer:** `api_call()`, `send_message()`, `send_inline_message()`, `send_photo()`, `edit_message()`, `answer_callback()`
- **Message routing:** `process_message()` — state machine with early state checks (before rate limiter)
- **Inline callbacks:** `handle_callback_query()` — approve/reject, SVRP admin, apps wizard, theme switching
- **Rate limiter:** 30 messages/min (checks after state handlers)

### 3.2 State Machine (user_states dict)

| State | Flow |
|-------|------|
| `choosing_start_language` | New user language selection |
| `start_phone_input` | New user phone entry → auto-login or register |
| `registering_name` / `registering_name_{lang}_{phone}` | Registration name entry |
| `registering_phone_{name}` | Registration phone entry |
| `selecting_deposit_company` → `deposit_wallet_*` → `deposit_amount_*` | Deposit flow |
| `selecting_withdraw_company` → `withdraw_wallet_*` → `withdraw_amount_*` → `withdraw_address_*` → `withdraw_confirmation_code_*` → `withdraw_final_confirm_*` | Withdrawal flow |
| `selecting_language` / `selecting_language_admin` | Language change (user/admin) |
| `selecting_currency` | Currency change |
| `writing_complaint` | Complaint submission |
| `phone_login_waiting` | Phone-based login |
| `svrp_create_promo_` / `svrp_redeem_promo_` | SVRP promo code creation/redemption |
| `app_wizard_name` → `app_wizard_*` | Admin app addition wizard (4 steps) |
| `chatting` / `rating` | P2P matching chat and rating |
| `match_enter_code` / `match_amount` / `match_company` | P2P matching flow |
| `awaiting_reject_reason_*` / `confirming_reject_*` | Admin rejection flow |
| `writing_custom_reply_*` | Admin complaint reply |
| `admin_broadcasting` | Admin broadcast message |

### 3.3 Rate Limiter
- **30 messages/minute** for non-admin users
- State handlers (registration, language change, SVRP, deposit/withdraw) checked **before** rate limiter
- Admins exempt from rate limiting

---

## 4. Feature Systems

### 4.1 💎 Smart Recovery (SVRP)

**Purpose:** When a withdrawal is rejected, user gets recovery credits as compensation.

**Flow:**
1. Withdrawal rejected → `trigger_recovery()` creates `pending` credits (50% keep + 50% shared)
2. Credits are **FROZEN** 🧊 (shown as frozen in panel) until wagering complete
3. Each approved transaction → `increment_wagering()` +1
4. When `wagering_completed >= 3` → ALL pending credits auto-activate (UNFROZEN) ✅
5. Unfrozen credits show as 🟢 Available
6. User can create promo codes (RCV prefix) or redeem codes from friends
7. Shared credits activate when a referred friend makes a deposit
8. Credits expire after 30 days (auto-cleanup on startup)
9. Monthly cap: 10,000 per user (auto-reset each month)

**Admin Panel:** Stats + wallets + promos + tasks + cleanup + interactive settings (➕/➖ buttons)

**Config:** recovery_multiplier=2.0, max_recovery_cap=5000, credit_expiry_days=30, wagering_requirement=3

### 4.2 🔄 P2P Matching

MatchManager with 5 CSV files. Matches opposite-type requests (deposit↔withdraw) with fake aliases. Admin verifies codes via inline buttons. Dispute resolution with chat history. Mandatory 1-5 star rating.

### 4.3 🎨 Theme System

3 themes stored in `theme_config.py`:
- **Gold** (🥇): `╔══╗` frames, `▰▱` bars, standard emoji
- **Ocean** (🌊): `╭──╯` frames, `▮▯` bars, blue emoji
- **Purple** (👑): `★━━★` frames, `⬛⬜` bars, purple emoji

Each theme controls: decorative frames, progress bars, status emoji, button emoji prefixes, transaction colors (🟢 deposit / 🔴 withdraw), message format (code/bold/plain). Active theme stored in `system_settings.csv`.

### 4.4 📱 Apps Feature

Admin-managed app download links with icons. Step-by-step wizard (name → icon_url → download_url → description). User panel shows formatted list with clickable download links. First app icon sent as photo.

### 4.5 i18n System

- **270 keys per language** × 17 languages = 4,590 translation strings
- `self.tr(key, lang, **kwargs)` with `{placeholder}` syntax
- All user-facing strings translated: main keyboard, admin keyboard, SVRP panels, deposit/withdraw flows, notifications, errors
- Button routing uses dynamic text sets: `{self.tr('key', l) for l in all_langs}`
- Admin panel: 27 admin button keys, fully translated
- Language-first registration: new users select language → phone → auto-login or register

### 4.6 Colored Formatting

HTML formatting with theme-colored emoji:
- `fmt_deposit_amount()`: 🟢 `<b><code>100.00 SAR</code></b>`
- `fmt_withdraw_amount()`: 🔴 `<b><code>100.00 SAR</code></b>`
- `fmt_success()` / `fmt_error()` / `fmt_info()` / `fmt_warning()`

### 4.7 Admin Roles

4 predefined roles: full, transactions, support, companies. Temp admins with auto-expiry. Per-admin button visibility via `admin_permissions.json`. `admin_keyboard(lang)` auto-detects admin's language.

### 4.8 Smart Notifications

`notify_admins()` + `notify_user()` with type tracking. `notifications_log.csv`. Admin panel shows categorized summary. User panel shows personal notifications.

---

## 5. Registration Flow

1. `/start` → Language selection grid (3 columns, 17 languages)
2. User selects language → Phone number request (contact button or manual)
3. If phone exists in `users.csv` → auto-login with old data (link_telegram_to_user)
4. If new → user enters name → account created with detected language/country/currency
5. Admin notified of new registration

---

## 6. Key Technical Details

- **CSV safety:** `safe_csv_write`/`safe_csv_read` with `threading.Lock` per file
- **Auto-expire:** `cleanup_old_transactions()` expires pending after 72h on startup
- **SVRP auto-expire:** `expire_old_credits()` on startup + monthly cap reset
- **Backup:** Auto-backup every 6 hours (`threading.Timer`)
- **Health check:** HTTP server on PORT env var for Render
- **Anti-spam:** Button text rejection as names/phones, regex validation
- **Back-button safety:** Early intercept in deposit/withdraw/phone_login flows

---

## 7. Deployment

| Platform | URL |
|----------|-----|
| GitHub | `github.com/duxexch/boterx` |
| Render | `boterx.onrender.com` (health check) |

**Procfile:** `web: python comprehensive_bot.py`
**Requirements:** `python-dotenv`, `openpyxl`
**Env vars:** `BOT_TOKEN`, `ADMIN_USER_IDS`
**Python:** 3.11.9
