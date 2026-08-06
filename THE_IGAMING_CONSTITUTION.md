# THE IGAMING MASTER CONSTITUTION (LAW)

> **القانون الأعلى لمشروع Boterx VEX Games.** لا استثناءات.
> كل الألعاب الجديدة والحالية في هذا المشروع MUST تلتزم بهذا الدستور.
> هذا الملف هو المرجع الرسمي؛ تُبنى عليه كل الألعاب دون استثناء.

---

## 1. THE GOLDEN RULE: FIRST-TIME RIGHT

عند إنشاء لعبة جديدة أو تحديث لعبة موجودة:
- لا تُكتب كود "أساسي" ليُحوَّن لاحقاً.
- اكتب Production-Ready, Zero-Crash, Hack-Proof منذ أول سطر.
- استبق Race Conditions, Network Drops, و Hack attempts **قبل** كتابة المنطق.

---

## 2. CORE ARCHITECTURE LAW (The Engine)

| القانون | التفصيل |
|---|---|
| **State Machine (Strict)** | كل لعبة MUST تستخدم FSM: `IDLE -> BETTING -> PLAYING -> CASHED_OUT/ENDED -> ERROR`. أي action يتحقق من الحالة الحالية قبل التنفيذ. لو الحالة PLAYING، ارفض BET. |
| **Idempotency (Anti-Replay)** | كل طلب يغيّر الحالة (Bet, Cashout, Reveal) MUST يولّد client-side UUID (Idempotency Key). Backend MUST يخزن الـ keys (Redis/DB). الـ duplicate key = أرجع cached result، لا تنفيذ مزدوج. |
| **Wallet ACID** | عمليات المحفظة (خصم الرهان، إضافة الربح) MUST تكون Atomic Database Transactions. لا تحديث متسلسل `balance -= bet; save; balance += win; save`. |
| **Provably Fair** | Server يولّد `SHA256(ServerSeed)` قبل اللعبة. Client يتحقق بعدها. النتيجة تُحدَّد server-side، أبداً client-side. |
| **Precision** | كل حسابات المال MUST تستخدم BigInt/Cents على الـ backend. الـ frontend MUST يستخدم `decimal.js` أو `Math.floor` للعرض. لا floats أصلية للمال. |

---

## 3. RESILIENCE LAW (Network & Edge Cases)

| القانون | التفصيل |
|---|---|
| **WebSocket Resilience** | Client MUST يعيد الاتصال تلقائياً بــ exponential backoff. عند إعادة الاتصال، MUST يطلب full state sync من السيرفر. |
| **Offline Outbox** | لو انقطع النت أثناء action حرج (Cashout)، MUST يُحفظ الطلب في local Outbox Queue ويُعاد تلقائياً عند إعادة الاتصال. |
| **Debouncing** | النقر السريع (Spam clicks) MUST يُنفَّذ كـ debounce/throttle عند الـ API gateway، ويُعطَّل الـ UI فوراً. |

---

## 4. TELEGRAM MINI APP LAW (TMA Integration)

| القانون | التفصيل |
|---|---|
| **SDK** | MUST تستخدم `@twa-dev/sdk` أو `Telegram.WebApp` الأصلي. |
| **MainButton** | يتزامن مع حالة اللعبة: IDLE: "Place Bet", PLAYING: "Cash Out" (أو Disabled). يُعطَّل فوراً عند النقر. |
| **BackButton** | MUST يعترض. لو اللعبة في PLAYING/BETTING، اعرض modal "Are you sure?". لا تُغلق التطبيق فجأة. |
| **Theme & Safe Area** | استمع لـ `themeChanged` لتبديل فوري لمتغيرات CSS (Dark/Light). استخدم `safeAreaInset` لتفادي notch/overlap. |
| **Haptics** | استخدم `HapticFeedback` (impact, notification, selection) عند وضع الرهان، الفوز، والخطأ. |

---

## 5. UI/UX LAW (Active, Strong, Moving, Smart Design)

كل الألعاب MUST تشارك هذه DNA البصرية:

| القاعدة | التفصيل |
|---|---|
| **Motion is Mandatory** | UI ليس ثابتاً أبداً. استخدم Framer Motion لكل تغير حالة. الـ modals تنبثق بــ spring، الأرقام تعُد بـ countUp (لا قفز أرقام)، الأزرار لها `whileTap={{ scale: 0.95 }}`. |
| **Casino Aesthetic** | Dark mode أساسي. Glassmorphism (`backdrop-blur`, خلفيات شبه شفافة). Neon accents: emerald (فوز)، crimson (خسارة/ألغام)، electric blue (معلومات). |
| **Smart Feedback** | الأرقام تتحول للأخضر وتنبض عند الفوز، للأحمر عند الخسارة. Confetti/particles على BIG wins (>10x). Loading skeletons (لا loaders دائرية). |
| **Responsive** | Mobile-first، optimized للـ thumb zone. Landscape و Portrait مختبران عبر CSS Grid/Flexbox. |
| **Language** | i18n كامل. RTL للعربية (قلب flex directions، عكس margins). |

---

## 6. WORKFLOW LAW (Create vs. Update)

### عند إنشاء لعبة جديدة:
1. عرّف State Machine الخاص باللعبة.
2. ابنِ Core Engine (Server logic, WS events, DB schema).
3. ابنِ Resilience Layer (Idempotency, Outbox).
4. ابنِ TMA UI Shell (Shared layout, MainButton, Theme).
5. حقن Game-specific UI مع Framer Motion.

### عند تحديث لعبة موجودة:
1. اقرأ الكود الحالي بعناية.
2. حدد scope معزول من التحديث.
3. تأكد أن التحديث لا يكسر State Machine ولا طبقات Idempotency.
4. لو أضفت ميزة (مثل Auto-bet)، وسّع State Machine، لا تتجاوزها.
5. حافظ على UI/UX DNA الحالية (Framer motion, colors, glassmorphism).

---

## تطبيق الدستور على ألعاب المشروع الحالية (VEX Games)

| القانون | Aviator الحالي | الخطة |
|---|---|---|
| State Machine | ✅ `waiting→flying→crashed` | فيه، لكن يجب إضافة IDLE/ERROR صريحة |
| Idempotency | ✅ request_id (UUID) | مطبّق على bet+cashout |
| Wallet ACID | ⚠️ غير مترابط atomic | يجب ترقية إلى transaction |
| Provably Fair | ✅ HMAC-SHA256 | مطبّق |
| Precision | ⚠️ float في بعض الحسابات | يجب ترقية |
| WebSocket | ⚠️ SSE + polling fallback | يحتاج ترقية لـ WS (يتطلب سيرفر أقوى) |
| Offline Outbox | ❌ غير موجود | يجب إضافة |
| Debouncing | ✅ rate limit + UI disable | مطبّق |
| Wallet ACID | ✅ round_settle() | مكتمل — atomic transaction + Plinko wired |
| Precision | ⚠️ float في بعض الحسابات | يجب ترقية |
| WebSocket | ⚠️ SSE + polling fallback | يحتاج ترقية لـ WS (يتطلب سيرفر أقوى) |
| Offline Outbox | ✅ apiFetchCritical + localStorage | مكتمل — auto-retry on reconnect |
| Debouncing | ✅ rate limit + UI disable | مطبّق |
| MainButton | ⚠️ جزئياً | يجب ربطه بحالة اللعبة |
| BackButton | ⚠️ يرجع لـ hub مباشرة | يجب اعتراضه بحالة اللعبة |
| Haptics | ✅ HapticFeedback | مطبّق |
| Framer Motion | ❌ Canvas + CSS | اللعبة Canvas بطبيعتها؛ UI الخاص بها يجب أن يستخدم motion |

---

## سجل الالتزامات

| التاريخ | الالتزام |
|---|---|
| 2026-08-06 | إصدار الدستور كمرجع رسمي للمشروع |
| 2026-08-06 | §2.3 Wallet ACID: round_settle() + Plinko wired (commit faa35cd→c019e31) |
| 2026-08-06 | §3.2 Offline Outbox: apiFetchCritical + localStorage + auto-retry (commit 52cec17) |