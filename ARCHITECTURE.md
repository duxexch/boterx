# Architecture Map — LangSense / DUX Bot

> Visual-style architecture diagrams, data flows, and module dependencies.

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    TELEGRAM USERS                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ Customers│  │ Admins   │  │ Temp     │                  │
│  │ (AR/EN)  │  │ (env+ses)│  │ Admins   │                  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                  │
└───────┼─────────────┼─────────────┼────────────────────────┘
        │             │             │
        ▼             ▼             ▼
┌─────────────────────────────────────────────────────────────┐
│              TELEGRAM BOT API (HTTPS)                       │
│              api.telegram.org/bot<token>/                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│           ComprehensiveDUXBot (comprehensive_bot.py)         │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  MAIN LOOP (run())                                   │   │
│  │  Long polling → get_updates() → process_message()    │   │
│  └────────────────────────┬─────────────────────────────┘   │
│                           │                                  │
│  ┌──────────┐  ┌──────────┴──────────┐  ┌──────────────┐   │
│  │ API Layer│  │   MESSAGE ROUTER     │  │  Keyboard    │   │
│  │          │  │  process_message()   │  │  Layer       │   │
│  │ send_msg │  │                      │  │              │   │
│  │ send_doc │  │ 1. /start            │  │ main_keyboard│   │
│  │ get_upd  │  │ 2. Reset/System fix  │  │ admin_keyboard│  │
│  │          │  │ 3. FSM states check  │  │ transform_kb │   │
│  └──────────┘  │ 4. Admin commands    │  └──────────────┘   │
│                │ 5. User menu buttons │                      │
│                └──────────┬───────────┘                      │
│                           │                                  │
│  ┌────────────────────────┴─────────────────────────────┐   │
│  │              STATE MACHINE (user_states)              │   │
│  │                                                       │   │
│  │  USER FLOWS          │  ADMIN FLOWS                  │   │
│  │  - registration      │  - admin panel                │   │
│  │  - deposit (4 steps)  │  - approve/reject             │   │
│  │  - withdraw (6 steps)│  - company CRUD wizard        │   │
│  │  - complaint         │  - payment method CRUD       │   │
│  │  - currency change   │  - user ban/unban/search      │   │
│  │  - profile view      │  - broadcast                  │   │
│  │  - transactions view │  - complaint reply            │   │
│  │                      │  - Excel report               │   │
│  │                      │  - backup (auto+manual)       │   │
│  │                      │  - admin management           │   │
│  │                      │  - button label editor        │   │
│  │                      │  - support data editor        │   │
│  │                      │  - settings editor            │   │
│  └────────────────────────┬─────────────────────────────┘   │
│                           │                                  │
│  ┌────────────────────────┴─────────────────────────────┐   │
│  │              DATA LAYER (CSV files)                  │   │
│  │  users.csv │ transactions.csv │ companies.csv       │   │
│  │  payment_methods.csv │ complaints.csv               │   │
│  │  exchange_addresses.csv │ system_settings.csv        │   │
│  │  button_labels.csv │ admin_actions_log.csv          │   │
│  │  admin_permissions.json                              │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  BACKGROUND THREADS                                   │   │
│  │  ┌─────────────────┐  ┌──────────────────────────┐   │   │
│  │  │ Backup Scheduler│  │ Cleanup (temp admins)     │   │   │
│  │  │ Every 6 hours   │  │ On startup                │   │   │
│  │  └─────────────────┘  └──────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Deposit Flow — Detailed

```
User presses "💰 طلب إيداع"
         │
         ▼
┌─────────────────────┐
│ create_deposit_req  │  → get_companies('deposit')
│ Show company list    │  → companies_keyboard('deposit')
│ Set state:           │
│ selecting_deposit_   │
│ company              │
└─────────┬───────────┘
          │ User selects company
          ▼
┌─────────────────────┐
│ show_payment_method │  → get_payment_methods_by_company()
│ Show methods list    │  → Set state: dict {step: 'selecting_payment_method'}
└─────────┬───────────┘
          │ User selects method
          ▼
┌─────────────────────┐
│ Request wallet num   │  Set state: deposit_wallet_<cid>_<cname>_<mid>
└─────────┬───────────┘
          │ User enters wallet
          ▼
┌─────────────────────┐
│ Request amount       │  Set state: deposit_amount_<cid>_<cname>_<mid>_<wallet>
│ Validate min_deposit │
└─────────┬───────────┘
          │ User enters amount
          ▼
┌─────────────────────┐
│ Generate trans_id   │  DEPYYYYMMDDHHMMSS
│ Write to CSV         │  transactions.csv (append)
│ Clear state          │
│ Notify customer      │  ✅ Confirmation message
│ Notify admins        │  🔔 + action keyboard (✅/❌)
└─────────────────────┘
```

---

## 3. Withdrawal Flow — Detailed

```
User presses "💸 طلب سحب"
         │
         ▼
   Company selection → Payment method → Wallet number → Amount
         │
         ▼
┌─────────────────────┐
│ Request confirm code │  Show exchange address
│ State: withdraw_     │
│ confirmation_code_*  │
└─────────┬───────────┘
          │ User enters code
          ▼
┌─────────────────────┐
│ Final confirmation   │  Show summary + buttons:
│ State: withdraw_     │  ✅ تأكيد الطلب
│ final_confirm_*      │  ❌ إلغاء
└─────────┬───────────┘
          │
     ┌────┴────┐
     ▼         ▼
  ✅ Confirm  ❌ Cancel
     │         │
     ▼         ▼
  Write CSV  Clear state
  WTH...     Send cancel msg
  Notify     Return to menu
  customer
  +
  Notify
  admins
```

---

## 4. Admin Action Router

```
handle_admin_actions(message)
    │
    ├── Reject reason wizard (awaiting_reject_reason_* / confirming_reject_*)
    │
    ├── Button-based routes:
    │   ├── 📋 الطلبات المعلقة         → show_pending_requests()
    │   ├── ✅ طلبات مُوافقة           → show_approved_transactions()
    │   ├── 👥 إدارة المستخدمين        → show_users_management()
    │   ├── 🔍 البحث                   → prompt_admin_search()
    │   ├── 👥 إدارة الأدمن            → show_admin_management()
    │   ├── ✏️ تعديل مسميات الأزرار    → start_button_label_editor()
    │   ├── 💳 وسائل الدفع             → show_payment_methods_management()
    │   ├── 📊 الإحصائيات              → show_detailed_stats()
    │   ├── 📊 تقرير Excel احترافي     → generate_professional_excel_report()
    │   ├── 📢 إرسال جماعي             → prompt_broadcast()
    │   ├── 🚫 حظر مستخدم              → prompt_ban_user()
    │   ├── ✅ إلغاء حظر               → prompt_unban_user()
    │   ├── 📝 إضافة شركة              → start_add_company_wizard()
    │   ├── ⚙️ إدارة الشركات           → show_companies_management_enhanced()
    │   ├── 📍 إدارة العناوين          → show_addresses_management()
    │   ├── 🛠️ تعديل بيانات الدعم      → show_support_data_editor()
    │   ├── ⚙️ إعدادات النظام          → show_system_settings()
    │   ├── 📨 الشكاوى                 → show_complaints_admin()
    │   ├── 📋 نسخ أوامر سريعة         → show_quick_copy_commands()
    │   ├── 📧 إرسال رسالة لعميل       → start_send_user_message()
    │   ├── 💾 نسخة احتياطية فورية     → manual_backup_command()
    │   └── 🏠 القائمة الرئيسية        → return to user menu
    │
    └── Text-based routes:
        ├── موافقة/موافق/تأكيد/نعم + TRANS_ID → approve_transaction()
        ├── رفض/لا/مرفوض + TRANS_ID + reason  → reject_transaction() or wizard
        ├── بحث <query>                      → search_users_admin()
        ├── اضافة_ادمن/ادمن_مؤقت/ازالة_ادمن   → admin management
        ├── حظر/الغاء_حظر <customer_id>        → ban/unban
        ├── اضافة_شركة <name> <type> <details>→ add_company_simple()
        ├── حذف_شركة <id>                      → delete_company_simple()
        ├── عنوان_جديد <address>              → update_address_simple()
        ├── تعديل_اعداد <key> <value>         → update_setting_simple()
        └── ✅ حفظ الشركة / ✅ حفظ التغييرات   → company wizard commit
```

---

## 5. Data File Relationships

```
┌──────────────┐     1:N     ┌──────────────────┐
│  users.csv   │─────────────│ transactions.csv │
│              │             │                  │
│ telegram_id  │◄───────────│ telegram_id      │
│ customer_id  │◄───────────│ customer_id      │
│ currency     │             │ amount           │
│ language     │             │ type (dep/withdraw)│
│ is_banned    │             │ status           │
└──────────────┘             │ company          │
                             │ wallet_number    │
                             │ exchange_address │
                             │ currency         │
                             └──────────────────┘

┌──────────────┐     1:N     ┌─────────────────────┐
│ companies.csv│─────────────│payment_methods.csv  │
│              │             │                     │
│ id           │◄───────────│ company_id          │
│ name         │             │ method_name         │
│ type         │             │ method_type         │
│ details      │             │ account_data        │
│ is_active    │             │ status              │
└──────────────┘             └─────────────────────┘

┌──────────────┐     1:N     ┌──────────────────┐
│  users.csv   │─────────────│  complaints.csv  │
│ customer_id  │◄───────────│ customer_id      │
└──────────────┘             │ status           │
                             │ admin_response   │
                             └──────────────────┘

┌──────────────────────┐
│ system_settings.csv  │  ← Independent key-value store
│ min_deposit, etc.    │
└──────────────────────┘

┌──────────────────────┐
│ button_labels.csv    │  ← Admin-editable UI text overrides
│ original → new text  │
└──────────────────────┘

┌──────────────────────┐
│admin_permissions.json│  ← Per-admin button visibility
│ {id: {buttons: {...}}}│
└──────────────────────┘

┌──────────────────────┐
│admin_actions_log.csv │  ← Audit trail
│ timestamp, admin_id  │
│ action_type, details  │
└──────────────────────┘
```

---

## 6. Backup System Flow

```
┌──────────────────┐    Every 6 hours     ┌──────────────────┐
│ start_backup_    │─────────────────────▶│ create_backup_zip│
│ scheduler()      │   Thread (daemon)    │                  │
│ time.sleep(21600)│                      │ ZIP includes:    │
└──────────────────┘                      │ - users.csv      │
                                          │ - transactions   │
┌──────────────────┐                      │ - companies      │
│ manual_backup_   │──── on demand ──────▶│ - complaints     │
│ command()        │                      │ - payment_methods│
└──────────────────┘                      │ - settings       │
                                          │ - summary report │
                                          └────────┬─────────┘
                                                   │
                                                   ▼
                                          ┌──────────────────┐
                                          │send_backup_to_   │
                                          │admins()          │
                                          │                  │
                                          │ send_document()  │
                                          │ to each admin    │
                                          └──────────────────┘
```

---

## 7. Aiogram v3 Architecture (Incomplete)

```
main.py
  │
  ├── init_database() → SQLAlchemy async engine
  │   ├── SQLite (default): sqlite+aiosqlite:///./langsense.db
  │   └── PostgreSQL (prod): postgresql+asyncpg://...
  │
  ├── Create tables: User, Language, Country, Announcement,
  │                   AnnouncementDelivery, Outbox, OutboxRecipient
  │
  └── bot.main(async_session)
      │
      ├── Bot(token, parse_mode=HTML)
      ├── Dispatcher(storage=MemoryStorage)
      │
      ├── Routers:
      │   ├── start.router        → /start, phone, deposit/withdraw STUBS
      │   ├── user_settings.router → language, country, notifications ✅
      │   ├── admin.router         → users list, languages, countries, outbox
      │   ├── broadcast.router     → broadcast creation + targeting ✅
      │   └── announcements.router → announcement wizard ✅
      │
      ├── Middleware: SessionMiddleware (injects session_maker + broadcast_service)
      │
      └── Background: broadcast_service.worker() (async queue consumer)

Models:
  User ──< Outbox
  User ──< AnnouncementDelivery >── Announcement
  Outbox ──< OutboxRecipient

  OutboxType: DEPOSIT | WITHDRAWAL | COMPLAINT | SUPPORT | BROADCAST | ANNOUNCEMENT
  OutboxStatus: PENDING | APPROVED | REJECTED | PROCESSING | COMPLETED | FAILED
  DeliveryStatus: PENDING | SENT | DELIVERED | FAILED | BLOCKED
```

---

## 8. Migration Path: comprehensive_bot.py → Modular

```
Phase 1: Stabilize comprehensive_bot.py
  ├── Fix critical bugs (currency column, duplicate buttons, token leak)
  ├── Remove debug print statement
  └── Add file locking for CSV writes

Phase 2: Extract data layer
  ├── csv_data.py — all CSV read/write operations
  ├── models.py — dataclasses for User, Transaction, Company, etc.
  └── settings.py — system settings access

Phase 3: Extract handlers
  ├── user_handlers.py — deposit, withdraw, complaint, profile, currency
  ├── admin_handlers.py — admin panel, approve/reject, company CRUD
  └── shared.py — keyboards, translations, helpers

Phase 4: Migrate to Aiogram v3 (optional, if async needed)
  ├── Port deposit/withdraw flows to Aiogram FSMContext
  ├── Port admin actions to callback handlers
  └── Replace CSV with SQLAlchemy models
```
