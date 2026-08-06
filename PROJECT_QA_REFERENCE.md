# Boterx VEX Games — Master Reference & QA Knowledge Base

> **هذا الملف هو المرجع الرسمي للمشروع.** أي تعديل، لعبة جديدة، أو تحديث يجب أن يُبنى على هذا المرجع.
> A: خريطة الألعاب | B: منهجية QA | C: بنية النظام | D: القواعد الثابتة (SRS) | E: سجل التغييرات
> F: عملية إضافة لعبة جديدة
>
> **⚠️ القانون الأعلى:** راجع `THE_IGAMING_CONSTITUTION.md` قبل كتابة أي كود لعبة.
> هذا الدستور (Constitution) يحكم كل الألعاب — لا استثناءات.

---

## A. خريطة الألعاب (Games Catalog)

| اللعبة | ID | الحالة | نمط اللعبة | نظام الرهان | Notes |
|---|---|---|---|---|---|
| Aviator | GAME004 | ✅ Live | Real-time multiplier (crash) | صداع SSE global round | الأكثر تعقيداً — Provably Fair مربوط |
| Crash | GAME005 | ✅ Live | Crash graph | SSE global round | نسخة مبسطة من Aviator |
| Mines | GAME006 | ✅ Live | Grid reveal (mines) | Per-player session | Provably Fair جاهز للربط |
| Plinko | GAME007 | ✅ Live | Ball physics | Per-drop | Rows 8/12/16, Risk Low/Med/High |
| Lucky Wheel | GAME009 | ✅ Live | Spinning wheel | Per-spin | 8 segments |
| Lottery | GAME008 | ✅ Live | Ticket draw | Per-ticket | Provably Fair مع seed |
| Snatch (Gift) | GAME001 | ✅ Live | Catch-the-gift | Per-spin | WebApp |

**لعبة تريد إضافتها؟** اتبع قسم D (قواعد الثابتة) + B (منهجية QA) وسيُطبّق كل شيء تلقائياً.

---

## B. منهجية QA — Matrix Approach (مستوى AAA/iGaming)

**المبدأ:** اكتب 40-50 **Core Functional Case** لكل لعبة، ثم اضربها في **Environmental Matrices** (Network + Telegram + Security + UI + Performance + Edge + Race). الناتج: 300-500 حالة فريدة **بدون تكرار** بتكلفة كتابة منخفضة.

### أعمدة ملف Excel (ثابتة لكل لعبة):
```
Test ID | Module | Feature | Test Title | Preconditions | Test Steps | Expected Result
| Priority (Critical/High/Medium/Low) | Severity | Test Type | Status | Notes
```

### صيغة Test ID (قواعد ثابتة):
```
{GAME3}-{CATEGORY}-{SEQ:03d}
GAME3 = أول 3 حروف من اللعبة (AVI, MIN, CRS, PLK, WHE, LOT, SNC)
CATEGORY = FUNC / EDGE / RACE / NET / SEC / UI / TG / PERF / ERR
```

### الفئات (Test Types) المطلوبة لكل لعبة:
| الفئة | تغطي |
|---|---|
| **Functional** | كل الوظائف الطبيعية (رهان، سحب، لعب) |
| **Edge Case** | القيم القصوى، القيود، الحالات النادرة |
| **Race Conditions** | الضغط المتزامن، double-click، سباق التوقيت |
| **Network** | Offline, Slow 3G, Packet Loss, Timeout, Reconnect |
| **Security** | Replay, Duplicate, Invalid Payload, Session Expired, Unauthorized, Rate Limit |
| **UI** | Responsive (Portrait/Landscape), Dark Mode, RTL (Arabic), Low-end device |
| **Telegram Mini App** | Open/Close, Resume, Background, Theme Change, Safe Area, MainButton, BackButton |
| **Performance** | Low Memory, Low FPS, CPU, Battery |
| **Error Handling** | كل أخطاء الخادم والعميل |

### مصفوفات التوليد (تُضرب في Core cases):
```python
network_states = [Offline, Slow3G, PacketLoss, Reconnect, Timeout]
telegram_states = [MainButton, BackButton, ThemeChange, SafeArea, Resume]
security_states = [ReplayAttack, InvalidJWT, SessionExpired, RateLimit, DuplicatePayload]
ui_states = [Landscape, DarkMode, RTL, LowEndDevice]
perf_states = [LowMemory, LowFPS]
```

### مثال (Aviator) — Core → Matrix:
- 45 Core Functional
- × 5 Network = 225
- × 5 Telegram = 225
- × 5 Security = 225
- + ~50 Edge/Race/Error خاص
- **الإجمالي ≈ 420 حالة فريدة**

---

## C. بنية النظام (Technical Architecture)

```
vex.deals (VPS 69.169.108.197, 1core/2GB)
├── nginx → 443/80 → gunicorn:8080
│
├── comprehensive_bot.py      # Telegram bot — 11,818 سطر (split 45.6%)
│   ├── bot_utils/            # استخرج: constants, validation, telegram_helpers, csv_helpers
│   └── handlers/             # استخرج: deposit_withdraw, message_dispatcher, callback_handler, admin_actions
│
├── dashboard/app.py          # Flask — Aviator engine + SSE + games + chat
├── game_engine.py            # GameManager — wallet SQLite
├── house_algorithm.py        # HouseAlgorithm — win chance
├── risk_manager.py           # RiskManager
├── player_tracker.py         # PlayerTracker
├── db_manager.py             # SQLite — users, game_sessions, aviator_rounds
├── provably_fair.py          # HMAC-SHA256 — مربوط بـ Aviator
└── i18n/ (17 لغة)
```

### قيود السيرفر الحالية (مهمة لـ Performance tests):
- **1 core / 2GB RAM** → يدعم ~60 اتصال SSE متزامن كحد أقصى
- gunicorn: `--workers 1 --threads 100 --timeout 0 --backlog 2048`
- LimitNOFILE=65535
- **لا WebSocket بعد** — SSE فقط + polling fallback
- لـ 3000 لاعب: يحتاج ترقية سيرفر (multi-core) + WebSocket + فصل game loop

---

## D. قواعد الثابتة (SRS / Constraint Rules) — تُطبق على كل لعبة

### أ. البنية الفنية (كل الألعاب):
1. **Server-Authoritative** — المضاعف/النتيجة يتولد على السيرفر، العميل يعرض فقط
2. **Provably Fair** — seed_hash قبل الجولة، server_seed بعدها (SHA256 commitment)
3. **SSE global round** — كل اللاعبين يرون نفس الرقم في نفس اللحظة (مصدر واحد)
4. **Auto-Reconnect** — fallback polling إذا لم تصل رسالة SSE خلال timeout
5. **Canvas 0x0 bug ممنوع** — show #app أولاً ثم resizeCanvas في requestAnimationFrame
6. **Cross-browser** — `var` بدل const/let، لا `?.`، try/catch حول APIs خارجية
7. **Responsive mobile-first** — vw/vh/clamp

### ب. الأمان (كل الألعاب):
1. **لا تثق بأي بيانات من العميل** بخصوص المنطق الحرج
2. **تحقق الرهان/السحب على السيرفر** — توقيت server_ts
3. **Replay protection** — request_id فريد لكل رهان/سحب
4. **Rate limit** — 10 req/5s لكل مستخدم
5. **Authoritative cashout** — يرفض لو mult ≥ crash_point

### ج. عمر اللعبة (دورة حياتية):
```
WAITING_BETS (6s countdown) → LOCKED → TAXI (2s slow) → CLIMBING (multiplier)
→ CRASHED → RESULTS (5s) → WAITING_BETS...
```

### د. الرهان (مثل 1xBet):
- أثناء العد: زر "رهان" → بعد الرهان يظهر "إلغاء"
- بعد الإقلاع: الزر يتحول للمبلغ المراهن به ويزداد مع المضاعف
- لا يمكن المراهنة أثناء الطيران — رسالة "انتظر الجولة القادمة"

### هـ. الواجهة (كل الألعاب):
- شريط علوي: رصيد + عملة + مؤشر اتصال (🟡/🟢/🔴) + صوت
- شريط تاريخ الجولات
- لوحة رهان: ½, 2×, Min, Max + Auto cashout
- مظلة/باراشوت بالاسم + المبلغ (تختفي بعد 3s)
- إجمالي الأرباح الموزعة بعد الانفجار

---

## E. سجل التغييرات (Changelog)

| التاريخ | التغيير |
|---|---|
| 2026-08-05 | Aviator: global round + provably fair + security hardening + load test |
| 2026-08-06 | code split -45.6% (bot_utils + 4 handlers mixins) |
| 2026-09-01 | **(هنا يُضاف أي تعديل قادم)** |

---

## F. عملية إضافة لعبة جديدة (Standard Onboarding)

عند طلب إضافة لعبة جديدة، اتبع هذا التسلسل **بترتيب صارم**:

1. **سجّل اللعبة هنا** في قسم A (خريطة الألعاب) بتعريف سطر.
2. **حدد نمط اللعبة** (crash / grid / physics / wheel / lottery / catch).
3. **اربط بالـ Backend**:
   - أضف GAME10x في `games_catalog.csv`
   - أضف endpoints في `dashboard/app.py` (server-authoritative)
   - اربط Provably Fair إن أمكن
   - سجّل الجولات في `db_manager.py`
4. **ابنِ الـ UI** حسب قسم D-هـ (الواجهة القياسية).
5. **طبّق الأمان** من D-ب (server validation, replay, rate limit).
6. **اربط Transport**: SSE global round (أو per-player حسب اللعبة).
7. **توليد QA Excel** عبر سكربت `qa_matrix_generator.py` بنفس منهجية B.
8. **اختبار حمل** عبر `load_test_aviator.py` المعدل للعبة.

> عند اكتمال أي خطوة، حدّث هذا الملف في سجل E.