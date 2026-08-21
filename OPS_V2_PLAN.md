# 📐 الخطة الهندسية الكاملة — نظام المطابقة V2 (Ops Engine)
> **الحالة:** مسودة للمراجعة — بانتظار تأكيد المالك قبل التنفيذ
> **النطاق:** إيداع · سحب · شراء/بيع USDT — موحّدة بمحرك واحد عبر البوت + الويب + لوحات الأدمن والوكلاء
> **التاريخ:** 2026-08-21

---

## 1. الرؤية والمبادئ الحاكمة

1. **مصدر حقيقة واحد**: كل حالة عملية تعيش في SQLite (`BEGIN IMMEDIATE`) — البوت والويب مجرد واجهات فوق نفس المحرك.
2. **لا مال يتحرك بلا دليل**: كل خطوة تنفيذية تتطلب دليلاً (مرجع/لقطة/كود) + تأكيد الطرف المقابل.
3. **لا قفل أبدي**: لكل انتظار مهلة وسلّم تصعيد ينتهي عند الأدمن أو الاسترداد التلقائي.
4. **إخفاء الهوية**: المستخدم يرى `عميل-XXXX` فقط — حتى في الشكاوى والإشعارات.
5. **كل فعل له سجل**: `op_audit_log` append-only لا يمكن تعديله أو حذفه (محكوم بـ triggers).
6. **تكافؤ القنوات**: أي فعل ممكن من الويب ممكن من البوت والعكس (مصفوفة §9).
7. **Feature Flag**: `OPS_V2=on/off` — التشغيل الجديد قابل للإطفاء اللحظي دون رجوع كود.

---

## 2. آلة الحالة الكاملة (State Machine)

```
                    ┌────────────────────────────────────────────────┐
                    │                                                │
CREATED ──claim──► CLAIMED ──أول خطوة──► IN_PROGRESS ──كل الخطوات تم──► PRE_COMPLETE ──(نافذة انقضت بلا شكوى)──► COMPLETED
   │                 │                      │                            │                                  │
   │                 │                      │                            ├─(شكوى خلال النافذة)──► DISPUTED  │
   │                 │                      ├──خطوة مرفوضة ×2──► ESCALATED(أدمن)                            │
   │cancel           │takeover/reassign     │                            │                                  ▼
   ▼                 ▼                      ▼                            ▼                            RATED(خلال 24س) → CLOSED
CANCELLED         CLAIMED'(ملكية جديدة)   (تدفق خطوات مستمر)         DISPUTED ──resolve──► RESOLVED_DEP/WIT/CANCEL
                                                                                              └─(اختياري) INSURANCE_PAYOUT
```

### قواعد الانتقالات
| من → إلى | الشروط | المَن | ملاحظات |
|----------|--------|------|---------|
| CREATED → CLAIMED | وكيل متاح (traffic rules §7) أو أدمن يعالج بنفسه | system/admin | قفل حصري ذرّي |
| CLAIMED → IN_PROGRESS | بدء أول خطوة | معالِج | |
| خطوة: pending → action_done | المنفّذ نفّذ + أرفق الدليل الإلزامي | حسب نوع الخطوة | رفض الدليل الشكلي ممنوع من الواجهة |
| action_done → confirmed | الطرف المقابل أكّد | المقابل | زر واحد + بصمة وقت |
| action_done → rejected | المقابل اعترض بسبب إلزامي | المقابل | ≥2 رفض لنفس الخطوة ⇒ ESCALATED |
| أي مهلة فائتة | تذكير (50% من المهلة) ← تصعيد (100%) | scheduler | ذرّي ومتعدد الآمن (multi-runner safe) |
| IN_PROGRESS → PRE_COMPLETE | آخر خطوة confirmed | system | يبدأ عدّاد نافذة الشكوى |
| PRE_COMPLETE → COMPLETED | انقضت النافذة بلا شكوى | scheduler | يفتح نافذة التقييم |
| ≤PRE_COMPLETE → DISPUTED | أي طرف فتح شكوى بسبب+دليل | user/agent | يجمد المال (escrow قائم أصلاً) |
| COMPLETED → (لا شكوى) | بعد الإتمام: مسار `insurance_claims` منفصل | user | لا نقض للإتمام، مراجعة أثرية |
| CLAIMED/IN_PROGRESS → TAKEOVER | أدمن يصادر بسسبب إلزامي | admin | نقل escrow ذري |
| CLAIMED → REASSIGNED | أدمن يعيد التعيين لوكيل آخر | admin | نقل escrow ذري + إشعار الطرفين |

### المؤقتات (system_settings — قابلة للضبط من اللوحتين)
| المفتاح | افتراضي |
|---------|---------|
| `op_step_action_timeout_min` | 10 |
| `op_step_confirm_timeout_min` | 5 |
| `op_precomplete_window_min` | 15 |
| `op_total_timeout_min` | 60 (تجاوزه ⇒ تصعيد نهائي) |
| `usdt_rate_lock_min` | 10 |
| `rating_window_hours` | 24 |

---

## 3. نموذج البيانات (DDL الجديد/المعدَّل)

### جداول جديدة
```sql
-- محرك الخطوات
CREATE TABLE op_steps (
  id TEXT PRIMARY KEY,
  txn_id TEXT NOT NULL,              -- → match_requests.id
  seq INTEGER NOT NULL,
  step_key TEXT NOT NULL,            -- من القالب
  title_key TEXT NOT NULL,           -- مفتاح i18n
  actor_role TEXT NOT NULL,          -- initiator|counterparty|agent|admin|system
  status TEXT NOT NULL DEFAULT 'pending',
      -- pending|action_done|confirmed|rejected|skipped|expired|escalated
  evidence_type TEXT NOT NULL DEFAULT 'none',  -- none|reference|screenshot|code
  evidence_ref TEXT NOT NULL DEFAULT '',
  action_deadline TEXT NOT NULL DEFAULT '',
  confirm_deadline TEXT NOT NULL DEFAULT '',
  acted_at TEXT DEFAULT '', acted_by TEXT DEFAULT '',
  confirmed_at TEXT DEFAULT '', confirmed_by TEXT DEFAULT '',
  reject_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX idx_steps_txn ON op_steps(txn_id, seq);

-- قوالب الخطوات (قابلة للتعديل من لوحة الأدمن — تبني على نظام الخطوات المخصصة الحالي)
CREATE TABLE op_step_templates (
  id TEXT PRIMARY KEY,
  op_type TEXT NOT NULL,      -- deposit|withdraw|buy_usdt|sell_usdt
  source_type TEXT NOT NULL,  -- company|personal_wallet
  steps_json TEXT NOT NULL,   -- [{key,title_key,actor_role,evidence_type},...] بالترتيب
  is_active INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
);

-- تدقيق غير قابل للتعديل
CREATE TABLE op_audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id TEXT NOT NULL, entity_table TEXT NOT NULL,
  actor_type TEXT NOT NULL,   -- user|agent|admin|system
  actor_id TEXT NOT NULL,
  event TEXT NOT NULL,        -- state transition أو حدث
  from_value TEXT DEFAULT '', to_value TEXT DEFAULT '',
  payload_digest TEXT DEFAULT '',   -- SHA256(payload) لإثبات السلامة
  created_at TEXT NOT NULL
);
CREATE TRIGGER op_audit_no_update BEFORE UPDATE ON op_audit_log
BEGIN SELECT RAISE(ABORT,'audit is append-only'); END;
CREATE TRIGGER op_audit_no_delete BEFORE DELETE ON op_audit_log
BEGIN SELECT RAISE(ABORT,'audit is append-only'); END;

-- مطالبات التأمين بعد الإتمام (بديل الشكوى المحظورة)
CREATE TABLE insurance_claims (
  id TEXT PRIMARY KEY, txn_id TEXT NOT NULL, claimant_type TEXT NOT NULL,
  reason TEXT NOT NULL, evidence_file_id TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open',   -- open|approved|rejected
  payout_amount REAL NOT NULL DEFAULT 0,
  decided_by TEXT DEFAULT '', decided_at TEXT DEFAULT '', created_at TEXT NOT NULL
);

-- قواعد توجيه المرور (تحكم أدمن كامل)
CREATE TABLE routing_rules (
  id TEXT PRIMARY KEY, priority INTEGER NOT NULL DEFAULT 100,
  rule_type TEXT NOT NULL,   -- pin_next_to_agent|block_agent|max_amount_per_txn|route_currency|route_company
  params_json TEXT NOT NULL, -- {"agent_id":..,"remaining":3} | {"currency":"EGP","agent_id":..} ...
  is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
```

### أعمدة تُضاف للجداول القائمة (nullable — ترحيل آمن)
```sql
-- match_requests
ALTER TABLE match_requests ADD COLUMN source_type TEXT NOT NULL DEFAULT 'company'; -- company|personal_wallet
ALTER TABLE match_requests ADD COLUMN claimed_by_type TEXT NOT NULL DEFAULT '';    -- agent|admin
ALTER TABLE match_requests ADD COLUMN claimed_by_id  TEXT NOT NULL DEFAULT '';
ALTER TABLE match_requests ADD COLUMN claimed_at     TEXT NOT NULL DEFAULT '';
ALTER TABLE match_requests ADD COLUMN state          TEXT NOT NULL DEFAULT '';     -- آلة الحالة V2 (فارغ=صف قديم legacy)
ALTER TABLE match_requests ADD COLUMN precomplete_until TEXT NOT NULL DEFAULT '';
ALTER TABLE match_requests ADD COLUMN rate REAL NOT NULL DEFAULT 0;                -- USDT سعر مقفل
ALTER TABLE match_requests ADD COLUMN rate_locked_until TEXT NOT NULL DEFAULT '';
ALTER TABLE match_requests ADD COLUMN network TEXT NOT NULL DEFAULT '';            -- TRC20/...

-- agent_bots (تحكم المرور اليدوي)
ALTER TABLE agent_bots ADD COLUMN drain INTEGER NOT NULL DEFAULT 0;      -- يُنهي الحالي ولا يستقبل جديد
ALTER TABLE agent_bots ADD COLUMN pin_remaining INTEGER NOT NULL DEFAULT 0; -- التزم إليه N طلبات قادمة
ALTER TABLE agent_bots ADD COLUMN cap_per_txn REAL NOT NULL DEFAULT 0;   -- 0=بلا حد
```

---

## 4. قوالب الخطوات الافتراضية (لكل نوع×مصدر — الأدمن يعدّلها)

> `I`=طرف منشئ الطلب، `C`=الطرف المقابل (وكيل/مستخدم)، `A`=أدمن

### 4.1 إيداع — مصدر حساب شركة (`deposit/company`)
| # | الخطوة | المنفّذ | الدليل | يؤكد |
|---|--------|--------|--------|------|
| 1 | تحويل المبلغ لحساب الشركة المعروض | I | مرجع التحويل | C |
| 2 | استلام المبلغ في الحساب | C | لقطة كشف | I |
| 3 | إضافة الرصيد للمستخدم (شركة/منصة) | C أو A | مرجع داخلي | I |

### 4.2 إيداع — من محفظة المستخدم (`deposit/personal_wallet`)
| 1 | خصم محفظة المستخدم (ذري فوري على المنصة) | system | tx داخلي تلقائي | I يرى فوراً |
|---|--------|--------|------|
| 2 | إيداع لرقم حساب المستخدم في الشركة | C(A) | مرجع | I |
> هذا المسار **INTERNAL**: بدون وكيل — موافقة أدمن واحدة ثم تنفيذ.

### 4.3 سحب — إلى حساب شركة (`withdraw/company`)
| 1 | خصم من رصيد المستخدم لدى الشركة (بواسطة المستخدم) | I | لقطة | C |
| 2 | تحويل المبلغ لمحفظة المستخدم | C | مرجع تحويل + hash إن USDT | I |

### 4.4 سحب — من المحفظة الخاصة (`withdraw/personal_wallet`)
| 1 | تجميد المبلغ في المحفظة (hold ذري) | system | تلقائي | — |
| 2 | الأدمن/الوكيل يحوّل للمستخدم | C | مرجع | I يؤكد الاستلام |
| 3 | تحرير الحجز نهائياً | system | تلقائي بعد تأكيد I | — |

### 4.5 شراء USDT (`buy_usdt`) — السعر يقفل لحظة الإنشاء
| 1 | المستخدم يحوّل الفيات للحساب المعروض | I | مرجع | C |
| 2 | الوكيل/الأدمن يحوّل USDT على الشبكة المحددة | C | TXID | I |
> بيع USDT = عكس الدورين بنفس القالب. السبريد: `rate = base ± spread%` من الإعدادات.

---

## 5. الملكية والتصعيد (Claim / Takeover / Escalation)

- **Claim ذرّي**: `UPDATE match_requests SET claimed_by_* WHERE id=? AND claimed_by_id='' ` داخل `BEGIN IMMEDIATE` — المستأول الأول يفوز، الآخرون يرون "بمعالجة".
- **Takeover للأدمن**: زر بلوحة الأدمن (ويب+بوت) — سبب إلزامي يسجل في audit؛ الـescrow يبقى مكانه (الوكيل ذاته)، وتُعلَّم معاملته `admin_override`.
- **Reassign**: نقل `agent_transactions.agent_id` + `escrow_balance` بين وكيلين في نفس المعاملة الذرية + إشعار الطرفين (بالأسماء المستعارة).
- **سلّم التصعيد**: تذكير عند 50% من مهلة الخطوة → تصعيد عند 100% (يبانل الأدمن "يحتاج تدخل") → تجاوز `op_total_timeout_min` → خياران أمام الأدمن: إكمال قسري أو استرداد escrow بضغطة.

---

## 6. الشكاوى والتقييم وصندوق التأمين

| المرحلة | الأداة | القاعدة |
|---------|-------|---------|
| قبل الإتمام | `DISPUTED` | سبب + دليل إلزاميان؛ الأدمن يفصل: لصالح I / لصالح C / إلغاء (+ تعويض تأمين اختياري) |
| بعد الإتمام | `insurance_claims` | لا يُنقض الإتمام؛ صرف من `insurance_pool` بعد مراجعة أثرية؛ يغذي **ثقة داخلية مخفية** |
| التقييم | يفتح عند COMPLETED لـ24س | وزنه بحسب شريحة المبلغ؛ **كاشف تواطؤ**: تكرار نفس الزوج أكثر من X/أسبوع ⇒ علم أحمر للأدمن وحظر تقييم مؤقت |

---

## 7. التحكم الكامل بحركة المرور (أولويات التقييم عند الاختيار)

ترتيب `_pick_agent_locked` الجديد:
```
1. routing_rules نشطة (pin_next_to_agent أولاً، route_company/currency، block_agent يستبعد)
2. drain=1 ⇒ مستبعد من الجديد
3. cap_per_txn && amount>cap ⇒ مستبعد
4. القيود القائمة: is_active، traffic_on، daily quota، spendable>deposit، max_concurrent
5. الوزن العادل الحالي: (daily_count/weight)×tier_mult مع عشوائية ±5%
```
لوحة الأدمن لكل وكيل (ويب+بوت): `Pin ×N` · `Drain` · `Pause` · `Cap/txn` · `Weight` · `Tier override`.

---

## 8. مصفوفة الإشعارات (مَن/ماذا/أين)

| الحدث | المستخدم I | المقابل C | الوكيل المعين | الأدمن |
|-------|-----------|-----------|----------------|--------|
| CREATED | تأكيد+رقم | — | 🔔TG(إن مربوط)+لوحة | 📋 TG+لوحة+SSE |
| CLAIMED | "بدأت المعالجة" | — | مهمة جديدة | تحديث حالة |
| خطوة تحتاج تنفيذاً | TG/ويب حسب دوره | نفسه | لوحة | SSE |
| خطوة تحتاج تأكيداً | TG/ويب | نفسه | لوحة | SSE |
| رفض خطوة | الطرفان | الطرفان | لوحة | 🔔 إن تكررت |
| تصعيد ESCALATED | إشعار | إشعار | ⚠️ | 🚨 أولوية |
| PRE_COMPLETE | عداد نافذة الشكوى | نفسه | لوحة | SSE |
| COMPLETED | طلب تقييم | طلب تقييم | إحصاء | سجل |
| DISPUTED/RESOLVED | الطرفان | الطرفان | لوحة | 🚨/سجل |

قاعدة الخصوصية: نص إشعار المستخدم لا يتضمن أي معرّف وكيل حقيقي — دائماً alias.

---

## 9. مصفوفة تكافؤ القنوات (يجب أن تكون 100% عند التسليم)

| القدرة | مستخدم-ويب | مستخدم-بوت | وكيل-ويب | وكيل-بوت* | أدمن-ويب | أدمن-بوت |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|
| إنشاء طلب (4 أنواع×مصدرين) | ✅ | ✅ | — | — | ✅ (نيابة) | ✅ (نيابة) |
| متابعة حالة لحظية | ✅SSE | ✅polling | ✅ | 🔔فقط | ✅SSE | ✅ |
| تنفيذ خطوة + دليل | ✅ | ✅ | ✅ | 🔔فقط | ✅ نيابة | ✅ نيابة |
| تأكيد/رفض خطوة | ✅ | ✅ | ✅ | 🔔فقط | ✅ | ✅ |
| شكوى/مطالبة تأمين | ✅ | ✅ | ✅ | 🔔 | ✅ فصل | ✅ فصل |
| تقييم | ✅ | ✅ | — | — | عرض | عرض |
| Claim/Takeover/Reassign | — | — | ✅ claim | 🔔 | ✅ كامل | ✅ كامل |
| تحكم مرور (Pin/Drain/Cap) | — | — | — | — | ✅ | ✅ |
| قوالب خطوات + مؤقتات | — | — | — | — | ✅ | ✅ |
| تقارير/تصدير | — | — | ✅ شخصية | — | ✅ | ✅ |

\* قرار معماري: **الوكيل يعمل من الويب فقط** + إشعارات TG (استقبال دون أفعال) — يقلل سطح الهجوم ويوحّد المنطق. (إن أردت أفعالاً من TG للوكيل لاحقاً، المحرك يدعم ذلك بإضافة router.)

---

## 10. نموذج التهديدات وضوابطه

| التهديد | الطرف | الضابط |
|---------|-------|--------|
| تأكيد زور بلا تحويل | أي طرف | دليل إلزامي + تأكيد متبادل + escrow + مهلات |
| حبس أموال برفض التأكيد دائماً | المقابل | مهلات + تصعيد + إكمال/استرداد قسري |
| ابتزاز ما بعد الإتمام | أي طرف | الإتمام نهائي؛ مسار تأمين أثري منفصل |
| تنفيذ مزدوج (أدمن+وكيل) | نظام | Claim lock ذري + takeover موثّق |
| سباق إنشاء/إلغاء مع تسوية متزامنة | نظام | كل العمليات المالية داخل `BEGIN IMMEDIATE` + idempotency-key لكل endpoint معالجة |
| تزوير دليل مكرر (نفس المرجع مرتين) | منفّذ | فهرس فريد على `(evidence_type,evidence_ref)` ضمن النافذة الزمنية + كشف التكرار |
| حصر/توجيه غير عادل للمرور | وكيل | القواعد بأيدي الأدمن فقط + audit لكل تغيير قاعدة |
| كشف هوية الوكيل | مستخدم | aliases في كل المخرجات + فلترة إشعارات |
| طوفان طلبات من حساب جديد | مستخدم | Velocity: حد طلبات متزامنة/يومية حسب عمر الحساب وتاريخه |
| انحراف أرصدة/ledger | نظام | Reconciliation cron ليلي + تنبيه فوري لأي فرق ≠ 0 |

---

## 11. خطة التنفيذ — مراحل بملفات محددة

### 🔴 P0 — الأساس الآمن (يُسلّم أولاً ويُختبر بمعزل)
| # | عمل | ملفات | حجم |
|---|-----|-------|-----|
| 1 | ترحيل مخطط (أعمدة+جداول+triggers audit) | `agent_db.py` | M |
| 2 | محرك الخطوات + المؤقتات (multi-runner-safe) | **جديد** `ops_engine.py` | L |
| 3 | Claim/Takeover/Reassign ذريون | `agent_db.py`, `ops_engine.py` | M |
| 4 | APIs الويب: claim, step-action/confirm/reject, dispute, force-complete, cancel-by-rules | `dashboard/app.py` | L |
| 5 | تكافؤ البوت: callbacks + FSM خطوات (رسائل تفاعلية بالأزرار inline) | `comprehensive_bot.py`, `handlers/callback_handler.py`, `handlers/message_dispatcher.py` | L |
| 6 | Scheduler المؤقتات داخل حلقة الصيانة القائمة | `dashboard/app.py`(maintenance) | S |
| 7 | Idempotency middleware للمعالجات المالية | `dashboard/app.py` | S |
| 8 | Untrack `vex_games.db-shm/wal` + `.gitignore` | git | S |
| 9 | اختبارات: آلة الحالة، المؤقتات، السباقات (double-claim/confirm)، التراجعات | **جديد** `tests/test_ops_engine.py` | M |

**DoD لـP0:** جميع اختبارات P0 خضراء محلياً + E2E يدوي (سيناريوهات §13) على بيئة الإنتاج بعلم `OPS_V2` مفعّل للأدمن فقط 24 ساعة.

### 🟠 P1 — التحكم والمرونة
| # | عمل | ملفات | حجم |
|---|-----|-------|-----|
| 10 | routing_rules + دمجها بالاختيار | `agent_db.py`, `ops_engine.py` | M |
| 11 | وحدة تحكم المرور (UI+API) Pin/Drain/Cap/Pause | `dashboard/templates/agents.html`, app.py, بوت | M |
| 12 | طابور أدمن موحّد: مطابقة+تداول بفلترة واحدة | matching.html أو tab جديد | M |
| 13 | لوحة الوكلاء الحية (عبء/SLA/مخالفات) | stats + صفحة جديدة | M |
| 14 | SSE أحداث العملية (بديل polling للمستخدم) | app.py + home.html | M |
| 15 | مفاتيح i18n لكل النصوص الجديدة ×17 لغة | i18n/*.json + المولّد | M |
| 16 | تقييم مرجّح + كاشف تواطؤ | agent_db/ops_engine | S |

### 🟢 P2 — نضج وأتمتة
| # | عمل | حجم |
|---|-----|-----|
| 17 | INTERNAL auto-exec للمحفظة الداخلية (hold/release ذري عبر game_engine idempotent) | M |
| 18 | USDT: قفل سعر+سبريد+شبكة من الإعدادات، تحذير انتهاء السعر | M |
| 19 | Reconciliation cron + تنبيهات انحراف | S |
| 20 | Velocity limits | S |
| 21 | تصدير تقارير Excel لكل وكيل/فترة | S |

---

## 12. الترحيل والتوافق (Zero-Downtime)

1. كل الأعمدة الجديدة nullable/default — لا كسر للصفوف القائمة.
2. صفوف legacy (`state=''`): تُعرض كما هي في الواجهات القديمة؛ عند أول لمسة (أدمن يفتح الطلب) تُرقّى تلقائياً: `waiting→CREATED`، `matched→IN_PROGRESS` بخطوات synthetic مؤشرة confirmed.
3. Flag `OPS_V2`: dispatcher يوجّه للتدفق الجديد فقط حين يكون مفعلاً؛ الإطفاء يعيد المسار القديم فوراً.
4. Backfill script واحد idempotent يُنفّذ مع `migrate.py`.

## 13. خطة الاختبار
- **Unit:** انتقالات آلة الحالة كلها + رفض انتقالات غير شرعية + المؤقتات (حقن زمن).
- **Integration:** سباق claim مزدوج (2 threads)، تأكيد متزامن من الطرفين، إلغاء مقابل تسوية متزامنة (يجب أن يخسر أحدهما بشكل محدد)، takeover أثناء خطوة نشطة.
- **E2E يدوي (سيناريوهات قبول):** 8 سيناريوهات تغطي كل نوع×مصدر + شكوى سارية + شكوى بعد إتمام (تُرفض من الواجهة) + تصعيد مهلتين.
- **Load:** 200 طلب متزامن — لا deadlocks (WAL+IMMEDIATE)، زمن استجابة API < 300ms p95.

## 14. النشر والرجوع
- مرحلي: P0 بعلم للأدمن فقط ← 24س مراقبة (مقاييس: نسبة تصعيد، شكاوى، أخطاء audit) ← توسيع للجميع.
- Rollback: `OPS_V2=off` + استعادة `/root/backups/<stamp>` (نمط قائم).
- Git: فرع `ops-v2` ← PR إلى main ← بعد القبول نشر للسيرفر بنمط النشر المجرب (backup→upload→compile-check→restart→health).

## 15. قرارات مطلوبة من المالك (افتراضيات جاهزة — موافقتك تكفي)
| # | القرار | الافتراض |
|---|--------|----------|
| D1 | نافذة الشكوى قبل الإتمام | 15 دقيقة |
| D2 | مهلة الخطوة/التأكيد | 10/5 دقائق |
| D3 | المحفظة الداخلية بلا وكيل | نعم (INTERNAL آلي) |
| D4 | Takeover للأدمن بلا قيد | نعم مع سبب إلزامي |
| D5 | الوكيل ويب فقط + إشعارات TG | نعم |
| D6 | ما بعد الإتمام = تأمين فقط | نعم |
