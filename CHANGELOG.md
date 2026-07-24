# Changelog — LangSense / DUX Bot

All notable changes to this project will be documented in this file.

Format: `YYYY-MM-DD - [Type] Description`

Types: `Added`, `Changed`, `Fixed`, `Removed`, `Security`, `Refactor`, `Docs`

---

## 2026-07-23

### Added
- `PROJECT_BRAIN.md` — Full project analysis (6606-line deep dive)
- `ARCHITECTURE.md` — Visual architecture maps, data flows, module dependencies
- `DEV_GUIDE.md` — Coding conventions, patterns, testing checklist
- `CHANGELOG.md` — This file
- `STATE_TRACKER.md` — Current development state and next actions
- `i18n/` directory — 17 translation files (ar, en, fr, es, de, it, pt, ru, zh, tr, ur, hi, fa, id, ja, ko, th)
- `load_i18n_translations()` — File-based i18n system in comprehensive_bot.py
- `get_i18n_text()` — Get translated text from JSON files
- `get_language_names()` — 17 languages with name, native, flag, rtl info
- `get_supported_languages()` — List of supported language codes
- `show_language_selection()` — Multi-language selection UI with all 17 languages
- `sanitize_input()` — Input sanitization to prevent CSV injection
- `check_rate_limit()` — Rate limiting (5 requests/minute per user per action)
- `validate_phone_number()` — Phone number validation
- `validate_amount()` — Amount validation with max limit (1,000,000)
- Project memory entries for Codely CLI
- Skill `langsense-dev` at `~/.codely/Default/.codely-cli/skills/langsense-dev/SKILL.md`

### Fixed
- Removed `print("🔍 DEBUG BOT_TOKEN:...")` — security vulnerability (token leak to console)
- Fixed `handle_language_change()` — was writing users.csv without `currency` column, causing data loss
- Fixed `ban_user_admin()` — same currency column missing issue
- Fixed `unban_user_admin()` — same currency column missing issue
- Removed duplicate `💾 نسخة احتياطية فورية` button from `admin_keyboard()`
- Renamed duplicate `get_all_payment_methods()` (second definition filtered active-only) to `get_active_payment_methods()`
- Removed unreachable duplicate `text == '🔄 تحديث القائمة'` in admin actions router
- Fixed `send_backup_to_admins()` — reference to undefined variable `target_username`
- Fixed all button matching in `process_message()` to work dynamically across all 17 languages instead of hardcoded AR/EN
- Made `main_keyboard()` fully i18n-aware — buttons use translated labels for any language
- Made deposit/withdraw confirmation buttons (`✅ تأكيد الطلب`, `❌ إلغاء`) work across all languages
- Made registration flow buttons (`⏭️ تخطي`, `❌ إلغاء التسجيل`, `✍️ كتابة الرقم`) work across all languages
- Added null check for `validate_amount()` return value in deposit and withdraw flows

### Changed
- `main_keyboard()` now uses `self.tr()` for all button labels instead of hardcoded Arabic/English
- `handle_language_change()` now supports all 17 languages (was AR↔EN only)
- `tr()` method now checks file-based i18n translations first, falls back to inline dict
- Registration welcome text uses `self.tr('welcome_new', ...)` instead of hardcoded string
- Phone prompt uses `self.tr('enter_phone_prompt', ...)` instead of hardcoded string
- Support info text uses `self.tr('support_info', ...)` instead of hardcoded string
- Admin keyboard no longer has duplicate backup button

### Security
- BOT_TOKEN no longer printed to console (was critical vulnerability)
- Input sanitization added for user name and complaint text (prevents CSV injection)
- Amount validation now rejects negative, zero, and values over 1,000,000
- Phone number validation added (digits only, 7-20 characters)

### Changed (Full i18n integration)
- Deposit flow: all messages now use `self.tr()` — company selection, wallet prompt, amount prompt, validation errors, success confirmation, admin notification
- Withdrawal flow: all messages now use `self.tr()` — company selection, wallet prompt, amount prompt, address prompt, code prompt, final confirmation, success/cancel, admin notification
- Payment method selection: uses `self.tr()` for "no methods" error and selection prompt
- Admin panel: welcome message uses `self.tr('admin_panel', 'ar')`
- Transaction approve/reject: customer notifications use `self.tr()` with customer's language
- User profile display: uses i18n and currency from user record
- Error keyboard: all buttons use translated labels
- All 17 i18n files verified: 66 keys each, all JSON valid, all placeholders consistent
- `cancel_withdraw` key added to all 17 i18n files (was only in inline dict)

### UI Redesign (2026-07-23)
- **Main keyboard**: Redesigned with clean 2-column layout — deposit/withdraw on top, settings at bottom, admin button only visible to admins
- **Admin keyboard**: Reorganized into 9 logical groups (transactions, users, companies, stats, comms, support, settings, admin roles, backup)
- **Inline buttons (inside chat)**: Added `send_inline_message()`, `answer_callback()`, `edit_message()`, `make_inline_btn()`, `make_inline_keyboard()` helper methods
- **Callback handler**: `handle_callback_query()` — processes approve/reject/details buttons inside chat, company save/delete confirmations
- **Admin transaction notifications**: Now use inline buttons (✅ approve | ❌ reject | 👁️ details) instead of reply keyboard
- **Company wizard confirmation**: Inline buttons for save/cancel/edit
- **Company deletion**: Inline buttons for confirm/cancel
- **Company selection**: Single column with custom icons, clean 🔙 back button
- **Payment method selection**: Shows method icons in buttons
- **Shorter admin button labels**: "👥 المستخدمين" instead of "👥 إدارة المستخدمين", "🏢 الشركات" instead of "⚙️ إدارة الشركات", etc.
- **Admin button**: Now "🔧 Admin" instead of "/admin" in main keyboard (only visible to admins)
- **Error keyboard**: Cleaner with translated buttons + main menu

---

## Historical (Pre-analysis)

### Known timeline (from code inspection):
- **2025-08-21** — `LangSense_Backup_20250821_232613.zip` created (full backup)
- **2025** — Multiple bot versions created (simple → advanced → comprehensive)
- **2025** — Aiogram v3 skeleton started (main.py, bot.py, handlers/) but not completed
- **2025** — `comprehensive_bot.py` became the production bot (6606 lines)
- **Unknown** — Button label system, admin permissions, currency system, backup scheduler added

### Features added over time (inferred from code):
1. Basic user registration + deposit/withdraw
2. Company management (simple CRUD)
3. Payment methods per company
4. Multi-currency support (18 currencies)
5. Admin panel with 30+ features
6. Button label customization
7. Admin permission system (per-button)
8. Temp admin with expiry
9. Auto backup (6h) + manual backup
10. Excel report generation
11. Complaint system with reply wizard
12. Broadcast messaging
13. Support data editor
14. System settings editor
15. Quick copy commands
16. Super reset / system fix
17. Admin action logging (audit trail)

---

## Template for future entries:

```
## YYYY-MM-DD

### Added
- New feature X

### Changed
- Modified behavior of Y

### Fixed
- Bug Z in file.py

### Removed
- Deprecated feature W

### Security
- Fixed vulnerability V

### Refactor
- Extracted module M from comprehensive_bot.py

### Docs
- Updated DEV_GUIDE.md with pattern P
```
