# Software Requirements Specification (SRS)
## VEX Compensation System — Mobile App
### Version 1.0 | September 2026

---

## 1. Introduction

### 1.1 Purpose
This document specifies the requirements for the VEX Compensation System mobile application. The app allows users to register betting company accounts, request compensation for losses, manage wallets, invite friends via referral links, and transfer balances — all from their phone.

### 1.2 Scope
- User registration & authentication
- Company browsing & account registration
- Compensation request submission
- Wallet management (frozen/available balances)
- Referral system (invite friends)
- Balance transfer with OTP verification
- Admin notifications (Telegram)

### 1.3 Definitions
| Term | Definition |
|------|-----------|
| **Compensation** | Reimbursement for betting losses, approved by admin |
| **Frozen Balance** | Locked balance — unlockable via referrals or transfers |
| **Available Balance** | Unlocked balance — usable for deposits/transfers |
| **Referral Code** | Unique 8-char code linking referrer to referred user |
| **OTP** | One-Time Password (4 digits) for transfer verification |
| **PIN** | 4-digit secret code set once during first registration |

---

## 2. System Architecture

### 2.1 Backend
- **Server:** Python Flask on port 8080
- **Database:** CSV files (compensation_accounts, compensation_wallets, compensation_referrals, compensation_transfers, compensation_otp, compensation_requests, companies)
- **Auth:** Telegram Bot for OTP delivery & notifications
- **Hosting:** VPS at 69.169.108.197

### 2.2 Data Flow
```
Mobile App → HTTPS → Flask API → CSV Storage
                ↓
        Telegram Bot (OTP + Notifications)
                ↓
        Admin Panel (Approve/Reject)
```

---

## 3. User Types

### 3.1 Player (Mobile App User)
- Browses companies
- Registers accounts in companies
- Submits compensation requests
- Manages wallet
- Invites friends via referral links
- Transfers balance to friends

### 3.2 Admin (Web Panel)
- Reviews & approves/rejects compensation requests
- Manages wallets (credit frozen/available balances)
- Views all referrals and transfers
- Receives Telegram notifications for all actions

---

## 4. Functional Requirements

### 4.1 User Identification

**FR-1.1:** Each device gets a unique `user_id` stored in local storage.
- Format: `WC` + timestamp base36 + 6 random chars (e.g., `WCm5x8k2ab3f`)
- Persisted across sessions

**FR-1.2:** First registration sets a 4-digit PIN (SHA-256 hashed server-side).
- PIN is required for all subsequent registrations
- Cannot be changed once set

---

### 4.2 Company Browsing

**FR-2.1:** App fetches active companies from `GET /api/comp/public/companies`.

**FR-2.2:** Each company card displays:
- Company name
- Icon (uploaded by admin, or default emoji)
- Description
- Promo code (with copy button)
- CTA buttons: Register | App Download | Details

**FR-2.3:** Company data includes:
| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Company ID (e.g., `CMP1XB001`) |
| `name` | string | Display name (e.g., `1XBET`) |
| `icon` | string | Icon path (admin-uploaded) |
| `promo_code` | string | Promo code for registration |
| `affiliate_link` | string | Registration URL |
| `app_link` | string | Mobile app download URL |
| `color` | string | Brand color hex |
| `description` | string | Company description |

---

### 4.3 Account Registration

**FR-3.1:** User taps "Register" → opens affiliate link in browser → returns to app.

**FR-3.2:** Modal shows:
- Company icon & name
- Promo code (copyable)
- Download App button
- **Confirm Registration** button (opens affiliate link)
- **Login** button (for existing accounts)
- Close button

**FR-3.3:** Step 2 (after confirming):
- Account Number input (3–64 chars)
- PIN input (4 digits, numeric)
- Submit button
- Back button

**FR-3.4:** API Call: `POST /api/comp/public/register`
```json
{
  "user_id": "WCm5x8k2ab3f",
  "company_id": "CMPMLB002",
  "company_name": "MELBET",
  "account_number": "12345678",
  "pin": "1234"
}
```

**FR-3.5:** Server validates:
- Company is active
- Account number is 3–64 characters
- PIN is exactly 4 digits
- User doesn't already have active/pending account in this company

**FR-3.6:** On success: account created with `status=pending`. Admin approves → `status=active`.

**FR-3.7:** On first registration: PIN is saved (SHA-256 hash). All future registrations require this PIN.

**FR-3.8:** Admin receives Telegram notification for each new registration.

---

### 4.4 Compensation Request

**FR-4.1:** User taps a registered company → enters compensation amount.

**FR-4.2:** API Call: `POST /api/comp/public/request`
```json
{
  "user_id": "WCm5x8k2ab3f",
  "company_id": "CMPMLB002",
  "company_name": "MELBET",
  "amount": 50
}
```

**FR-4.3:** Server validates:
- User has a registered account in this company
- Amount > 0

**FR-4.4:** Request created with `status=pending`. Admin reviews.

**FR-4.5:** Admin approves → enters amount + note → sends Telegram notification to user.

**FR-4.6:** Admin rejects → enters note → sends Telegram notification to user.

---

### 4.5 Wallet System

**FR-5.1:** Each company gets a wallet with two balances:
| Balance | Description | Usage |
|---------|-------------|-------|
| **Frozen** | Locked balance | Unlockable via referrals/transfers |
| **Available** | Unlocked balance | Usable for deposits, transfers |

**FR-5.2:** API Call: `GET /api/comp/public/wallet?user_id=WCm5x8k2ab3f`
```json
{
  "wallets": [
    {
      "user_id": "WCm5x8k2ab3f",
      "company_id": "CMPMLB002",
      "company_name": "MELBET",
      "icon": "/static/uploads/icons/melbet_xxx.png",
      "frozen": "100.00",
      "available": "50.00",
      "created_at": "2026-09-01T12:00:00"
    }
  ]
}
```

**FR-5.3:** Wallet is created when admin credits the user (not auto-created on registration).

**FR-5.4:** Frozen balance unlock mechanisms:
- **Referral:** 10% of frozen unlocks when referred friend registers
- **Transfer:** Frozen decreases when transferring to friend

---

### 4.6 Referral System

**FR-6.1:** User generates a unique referral link per company.

**FR-6.2:** API Call: `GET /api/comp/public/referral/link?user_id=X&company_id=X&company_name=X`
```json
{
  "link": "https://vex.deals/compensation?ref=A1B2C3D4",
  "code": "A1B2C3D4"
}
```

**FR-6.3:** Referral code is deterministic: `MD5(user_id:company_id:vex)[:8].upper()`

**FR-6.4:** Referred user opens link → auto-applies code via `POST /api/comp/public/referral/apply`

**FR-6.5:** API Call: `POST /api/comp/public/referral/apply`
```json
{
  "code": "A1B2C3D4",
  "user_id": "WC_new_user_id"
}
```

**FR-6.6:** Server validates:
- Code exists
- Not self-referral
- Not already referred

**FR-6.7:** On success:
- Referral status → `registered`
- **10% of referrer's frozen balance unlocks:**
  ```
  unlock_amount = min(frozen, frozen × 0.10)
  frozen -= unlock_amount
  available += unlock_amount
  ```

**FR-6.8:** Referral history: `GET /api/comp/public/referrals?user_id=X`

---

### 4.7 Balance Transfer

**FR-7.1:** Transfer allows sending balance to a friend's account in the same company.

**FR-7.2:** Business Rules:
| Rule | Value |
|------|-------|
| Max transfer amount | 10% of frozen balance |
| Frequency | Once per friend per company |
| OTP required | Yes (Telegram) |
| Target must exist | Yes (same company) |

**FR-7.3:** Step 1 — Initiate Transfer:

API Call: `POST /api/comp/public/transfer/init`
```json
{
  "user_id": "WC_sender_id",
  "company_id": "CMPMLB002",
  "company_name": "MELBET",
  "amount": 10,
  "to_account": "87654321"
}
```

**FR-7.4:** Server validates:
- Frozen balance > 0
- Amount ≤ frozen × 0.10
- Target account exists in same company
- Not self-transfer
- No completed transfer to same account in same company

**FR-7.5:** Server generates 4-digit OTP → sends via Telegram bot → creates transfer with `status=otp_pending`.

**FR-7.6:** Step 2 — Verify Transfer:

API Call: `POST /api/comp/public/transfer/verify`
```json
{
  "pending_id": "TF...",
  "otp": "4829",
  "user_id": "WC_sender_id"
}
```

**FR-7.7:** Server validates:
- OTP matches code
- OTP belongs to this user
- OTP not used
- Transfer still `otp_pending`
- Sender still has enough frozen

**FR-7.8:** On success:
```
sender.frozen -= amount
receiver.available += amount
transfer.status = "completed"
otp.used = "1"
```

**FR-7.9:** Admin receives notification for each completed transfer.

---

## 5. API Reference

### 5.1 Public Endpoints (No Auth)

| # | Method | Endpoint | Description |
|---|--------|----------|-------------|
| 1 | GET | `/api/comp/public/companies` | List active companies |
| 2 | GET | `/api/comp/public/my-accounts?user_id=X` | User's registered accounts |
| 3 | POST | `/api/comp/public/register` | Register account in company |
| 4 | POST | `/api/comp/public/request` | Submit compensation request |
| 5 | GET | `/api/comp/public/wallet?user_id=X` | Get wallet balances |
| 6 | GET | `/api/comp/public/referral/link?user_id=X&company_id=X&company_name=X` | Generate referral link |
| 7 | POST | `/api/comp/public/referral/apply` | Apply referral code |
| 8 | GET | `/api/comp/public/referrals?user_id=X` | List referrals |
| 9 | POST | `/api/comp/public/transfer/init` | Initiate transfer |
| 10 | POST | `/api/comp/public/transfer/verify` | Verify transfer with OTP |
| 11 | GET | `/api/comp/public/transfers?user_id=X` | List transfers |

### 5.2 Request/Response Schemas

#### Register Account
```
POST /api/comp/public/register
Request:  { user_id, company_id, company_name, account_number, pin }
Response: { ok: true, id: "CA..." }
Errors:   { error: "Company not active" }
          { error: "Account already registered" }
          { error: "Invalid PIN" }
```

#### Submit Compensation Request
```
POST /api/comp/public/request
Request:  { user_id, company_id, company_name, amount }
Response: { ok: true, id: "CR..." }
Errors:   { error: "Amount must be greater than 0" }
```

#### Get Wallet
```
GET /api/comp/public/wallet?user_id=X
Response: { wallets: [{ user_id, company_id, company_name, icon, frozen, available, created_at }] }
```

#### Generate Referral Link
```
GET /api/comp/public/referral/link?user_id=X&company_id=X&company_name=X
Response: { link: "https://vex.deals/compensation?ref=CODE", code: "CODE" }
```

#### Apply Referral
```
POST /api/comp/public/referral/apply
Request:  { code, user_id }
Response: { ok: true }
Errors:   { error: "Invalid code" }
          { error: "Cannot refer yourself" }
          { error: "Already referred" }
```

#### Initiate Transfer
```
POST /api/comp/public/transfer/init
Request:  { user_id, company_id, company_name, amount, to_account }
Response: { ok: true, pending_id: "TF...", msg: "تم إرسال رمز التحقق" }
Errors:   { error: "Insufficient frozen balance" }
          { error: "Amount exceeds 10% limit" }
          { error: "Account not found" }
          { error: "Already transferred to this account" }
```

#### Verify Transfer
```
POST /api/comp/public/transfer/verify
Request:  { pending_id, otp, user_id }
Response: { ok: true, msg: "تم التحويل بنجاح" }
Errors:   { error: "Invalid OTP" }
          { error: "OTP expired" }
```

---

## 6. Data Models

### 6.1 companies.csv
```csv
id,name,type,details,is_active,icon,address,affiliate_link,app_link,bot_icon,promo_code,show_in_comp
CMP1XB001,1XBET,both,أكبر شركات المراهنة,yes,,Cyprus,https://...,https://...,,vexwallet,yes
```

### 6.2 compensation_accounts.csv
```csv
id,user_id,company_id,company_name,account_number,status,created_at
CA1A2B3C4D5E,WCm5x8k2ab3f,CMPMLB002,MELBET,12345678,pending,2026-09-01T12:00:00
```

### 6.3 compensation_pins.csv
```csv
user_id,pin_hash,created_at
WCm5x8k2ab3f,e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855,2026-09-01T12:00:00
```

### 6.4 compensation_requests.csv
```csv
id,user_id,company_id,company_name,account_number,screenshot,status,amount,note,created_at,reviewed_at,reviewed_by
CR1A2B3C4D5E,WCm5x8k2ab3f,CMPMLB002,MELBET,12345678,,pending,,,2026-09-01T12:00:00,,
```

### 6.5 compensation_wallets.csv
```csv
user_id,company_id,company_name,frozen,available,created_at
WCm5x8k2ab3f,CMPMLB002,MELBET,100.00,50.00,2026-09-01T12:00:00
```

### 6.6 compensation_referrals.csv
```csv
id,referrer_id,referred_id,company_id,company_name,referral_code,referred_account,status,created_at
REF1A2B3C,WCm5x8k2ab3f,WCnewuser,CMPMLB002,MELBET,A1B2C3D4,12345678,registered,2026-09-01T12:00:00
```

### 6.7 compensation_transfers.csv
```csv
id,from_user,to_account,company_id,company_name,amount,status,otp_phone,created_at
TF1A2B3C,WCm5x8k2ab3f,87654321,CMPMLB002,MELBET,10.00,completed,,2026-09-01T12:00:00
```

### 6.8 compensation_otp.csv
```csv
user_id,phone,code,used,created_at
WCm5x8k2ab3f,,4829,1,2026-09-01T12:00:00
```

---

## 7. Non-Functional Requirements

### 7.1 Performance
- API response time: < 500ms (95th percentile)
- Wallet load: < 1 second
- Transfer OTP delivery: < 5 seconds

### 7.2 Security
- PIN stored as SHA-256 hash (never plaintext)
- OTP is single-use, validated server-side
- All API endpoints validate user_id ownership
- Transfer requires OTP verification (Telegram)
- No sensitive data in logs

### 7.3 Concurrency
- Thread locks on CSV writes (prevents race conditions)
- Transfer double-spend prevention (re-validates balance before execute)
- OTP reuse prevention (marks as used atomically)

### 7.4 Availability
- Server uptime: 99%+
- CSV backups on each deploy
- Admin notifications for all critical actions

---

## 8. User Interface Flows

### 8.1 Home Screen
```
┌─────────────────────────────────┐
│  Companies  │  Wallet  │ Refs  │  ← Tabs
├─────────────────────────────────┤
│  [Company Card]                 │
│  ┌──────┬──────┬──────┐        │
│  │ Sajjel│ App  │ Tafseel│      │  ← 3 CTA buttons
│  └──────┴──────┴──────┘        │
├─────────────────────────────────┤
│  [Company Card]                 │
│  ...                            │
└─────────────────────────────────┘
```

### 8.2 Registration Modal
```
┌─────────────────────────────────┐
│       [Company Icon]            │
│       MELBET                    │
│  Register then paste account ID │
├─────────────────────────────────┤
│  Promo Code: ml_3154096  [📋]  │
├─────────────────────────────────┤
│  [Download App]                 │
├──────────┬──────────┬───────────┤
│ Confirm  │  Login   │  Close    │
│ Register │          │           │
└──────────┴──────────┴───────────┘
         ↓ (Step 2)
┌─────────────────────────────────┤
│  Account Number                 │
│  [________________]             │
│  PIN (4 digits)                 │
│  [____]                         │
├──────────┬──────────────────────┤
│  Submit  │  Back                │
└──────────┴──────────────────────┘
```

### 8.3 Wallet Screen
```
┌─────────────────────────────────┐
│  MELBET                         │
│  ┌────────────┬────────────┐    │
│  │ 🔒 Frozen │ 🔓 Available│    │
│  │ 100.00 USD │ 50.00 USD  │    │
│  └────────────┴────────────┘    │
├──────────┬──────────────────────┤
│ Transfer │  Invite Friend       │
└──────────┴──────────────────────┘
```

### 8.4 Transfer Flow
```
Step 1: Enter amount + friend's account
┌─────────────────────────────────┐
│  Friend's Account Number        │
│  [________________]             │
│  Amount (Max: 10.00 USD)       │
│  [________________]             │
├─────────────────────────────────┤
│  [Send Transfer Request]        │
└─────────────────────────────────┘

Step 2: Enter OTP from Telegram
┌─────────────────────────────────┐
│  Enter OTP from Telegram        │
│  [____]                         │
├─────────────────────────────────┤
│  [Confirm Transfer]             │
└─────────────────────────────────┘
```

---

## 9. Error Handling

| Error | HTTP Code | User Message |
|-------|-----------|--------------|
| Company not active | 400 | "الشركة غير نشطة" |
| Account already registered | 400 | "الحساب مسجل مسبقاً" |
| Invalid PIN | 400 | "الرمز السري غير صحيح" |
| Amount ≤ 0 | 400 | "المبلغ يجب أن يكون أكبر من 0" |
| Insufficient frozen | 400 | "الرصيد المجمد غير كافٍ" |
| Transfer limit exceeded | 400 | "المبلغ يتجاوز الحد الأقصى (10%)" |
| Account not found | 400 | "الحساب غير موجود" |
| Self-transfer | 400 | "لا يمكنك التحويل لنفسك" |
| Duplicate transfer | 400 | "تم التحويل لهذا الحساب مسبقاً" |
| Invalid OTP | 400 | "رمز التحقق غير صحيح" |
| Connection error | 500 | "خطأ في الاتصال بالخادم" |

---

## 10. Admin Integration

### 10.1 Telegram Notifications
All user actions trigger admin notifications:
- New account registration → "📱 تسجيل حساب جديد في {company}"
- Compensation request → "💰 طلب تعويض: {amount}$ في {company}"
- Referral apply → "👥 صديق جديد سجل عبر الرابط"
- Transfer completed → "💸 تحويل: {amount}$ من {sender} إلى {receiver}"

### 10.2 Admin Actions
- Approve/reject compensation requests
- Credit wallet balances (frozen/available)
- View all referrals and transfers
- View uploaded screenshots

---

## 11. Appendix

### 11.1 Supported Companies
| ID | Name | Promo Code |
|----|------|-----------|
| CMP1XB001 | 1XBET | vexwallet |
| CMPMLB002 | MELBET | ml_3154096 |
| CMPBJ003 | BETJAM | VEDO2002 |
| CMPMB004 | MOSTBET | vedo2002 |
| CMPXP005 | XPARI | vedo2002 |
| CMPBB006 | BIZBET | bi_9258 |
| CMPLB007 | LINEBET | VEDO2002 |
| CMPGB008 | GOOOBET | Vex |

### 11.2 Base URL
```
Production: https://vex.deals
API Base:   https://vex.deals/api/comp/public/
```

### 11.3 Local Storage Keys
| Key | Value |
|-----|-------|
| `vex_comp_uid` | User's unique ID (e.g., `WCm5x8k2ab3f`) |
| `vex_lang` | Selected language code |
