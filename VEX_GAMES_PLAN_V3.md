# VEX Games — خطة التطوير المالي المتقدمة v3

## تحليل الوضع الحالي + خطة الإصلاح الشامل

---

## المشاكل الحرجة المكتشفة (6):

| # | المشكلة | الحل |
|---|---------|-----|
| 1 | **محفظتان منفصلتان** — users.csv و player_profiles.csv بدون تزامن | موحّدة: قراءة الرصيد من users.csv مباشرة |
| 2 | **لا يوجد سحب من محفظة الألعاب** | إضافة زر سحب يطلب من الأدمن |
| 3 | **مضاعف الربح ثابت** (1.7x) | مضاعف ديناميكي حسب اللعبة + شريحة اللاعب + حالة المنصة |
| 4 | **لا يوجد تحكم إداري بكل لاعب** | إضافة لوحة تحكم: ربح مخصص/حظر/تبريد |
| 5 | **خوارزمية ضعيفة** — جمع خطّي بدلاً من مضاعف | صياغة مضاعفة: base × ∏(factor^weight) |
| 6 | **لا إشعارات لحظية** | WebSocket/SSE للأدمن + إشعار للعميل |

---

## المرحلة 1: توحيد المحفظة (الأكثر إلحاحاً)

### الحل: قراءة/كتابة الرصيد من users.csv مباشرة

```python
# game_engine.py — تعديل get_balance و add_balance و deduct_balance

def get_balance(self, user_id):
    """قراءة الرصيد من users.csv (المحفظة الموحدة)"""
    try:
        with open('users.csv', 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('telegram_id') == str(user_id):
                    return float(row.get('game_balance', 0) or 0)
    except:
        pass
    return 0.0

def add_balance(self, user_id, amount):
    """إضافة رصيد لـ game_balance في users.csv"""
    # قراءة → تعديل → كتابة (مع file locking)

def deduct_balance(self, user_id, amount):
    """خصم رصيد من game_balance في users.csv"""
```

### ملفات جديدة:
- `users.csv` — إضافة عمود `game_balance` (migration تلقائي)
- `game_transactions.csv` — سجل مالي كامل (إيداع/سحب/رهان/مكسب)

### تدفق الإيداع الموحد:
```
العميل يضغط "💰 إيداع"
  → يختار وسيلة دفع (من payment_methods.csv)
  → يكتب المبلغ
  → طلب pending في game_transactions.csv
  → إشعار لحظي للأدمن (Telegram inline buttons)
  → الأدمن يوافق → game_balance يُضاف فوراً
  → إشعار لحظي للعميل: "✅ تم إضافة {amount} {currency}"
```

### تدفق السحب:
```
العميل يضغط "💸 سحب"
  → يرى رصيده
  → يكتب المبلغ
  → يختار وسيلة استلام
  → طلب pending
  → إشعار للأدمن
  → الأدمن يحوّل → يوافق → game_balance يُخصم
  → إشعار للعميل
```

---

## المرحلة 2: خوارزمية أقوى من 1xBet

### الصياغة المضاعفة (بدلاً من الجمع الخطي):

```python
def calculate_win_chance(self, player, game, bet_amount):
    base = float(game.get('base_win_chance', 0.45))

    # ===== عوامل مضاعفة (كل عامل يضرب/يقسم الاحتمال) =====

    # 1. صافي اللاعب (40%)
    net = float(player.get('net_position', 0))
    if net > 0:
        # لاعب رابح — خفض بشكل أقوى
        f_net = max(0.3, 1 - (net / 5000))  # عند net=5000 → 0.0 (لا يفوز أبداً)
    elif net < -500:
        f_net = min(1.8, 1 + (abs(net) / 2000))  # تحفيز قوي
    else:
        f_net = 1.0

    # 2. الحرارة (25%)
    heat = float(player.get('heat_level', 0))
    if heat > 7:
        f_heat = 0.5  # لاعب ساخن — خفض 50%
    elif heat > 5:
        f_heat = 0.75
    elif heat < 2:
        f_heat = 1.2  # لاعب بارد — حفّز
    else:
        f_heat = 1.0

    # 3. حالة المنصة العامة (20%) — جديد!
    platform_edge = self.calculate_platform_edge()
    target_edge = self.get_config('platform_target_edge', 0.15)
    if platform_edge < target_edge * 0.5:
        f_platform = 0.6  # المنصة تخسر — خفض الفوز عالمياً
    elif platform_edge < target_edge:
        f_platform = 0.8
    else:
        f_platform = 1.0

    # 4. دورة التعويض (10%)
    comp_interval = int(self.get_config('compensation_interval', 8))
    total_games = int(player.get('total_games', 0))
    if total_games > 0 and (total_games + 1) % comp_interval == 0 and net < 0:
        f_comp = 2.5  # فوز شبه مضمون
    elif total_games > 0 and (total_games + 1) % comp_interval == comp_interval - 1:
        f_comp = 0.4  # خسارة مؤكدة قبل التعويض
    else:
        f_comp = 1.0

    # 5. تحكم الأدمن (5%) — جديد!
    admin_override = float(player.get('admin_win_override', 0))
    if admin_override > 0:
        f_admin = admin_override  # الأدمن يحدد احتمال الفوز يدوياً
    elif admin_override < 0:
        f_admin = 0.05  # الأدمن أمر بخسارة
    else:
        f_admin = 1.0

    # ===== الصياغة المضاعفة =====
    win_chance = base * f_net * f_heat * f_platform * f_comp * f_admin

    # ===== حدود الأمان =====
    win_chance = min(0.92, max(0.03, win_chance))

    # ===== حدود يومية =====
    # (نفس النظام الحالي)

    return win_chance
```

### مزايا الصياغة المضاعفة:
- لاعب رابح + ساخن → `base × 0.3 × 0.5 = base × 0.15` (15% من الأساسي)
- لاعب خاسر + بارد → `base × 1.8 × 1.2 = base × 2.16` (216% من الأساسي)
- منصة تخسر → كل الاحتمالات تُضرب × 0.6
- الأدمن يحدد → `base × admin_value`

### مضاعف الربح الديناميكي:

```python
def calculate_payout_multiplier(self, game, player, platform_edge):
    """حساب مضاعف الربح ديناميكياً"""
    base_mult = float(game.get('base_multiplier', 2.0) or 2.0)

    # تعديل حسب شريحة اللاعب
    segment = self.tracker.get_segment(player)
    segment_mult = {
        'new': 1.2,      # لاعب جديد — مكاسب أكبر (إغراء)
        'loser': 1.3,    # خاسر — حفّزه
        'regular': 1.0,  # عادي
        'hot': 0.8,      # ساخن — قلل المكاسب
        'winner': 0.7,   # رابح — قلل جداً
        'vip': 1.1,      # VIP — حافظ عليه
        'churning': 1.4, # قد يغادر — حفّزه بقوة
    }.get(segment, 1.0)

    # تعديل حسب حالة المنصة
    if platform_edge < 0.05:
        edge_mult = 0.5  # خطر — قلل المكاسب
    elif platform_edge < 0.10:
        edge_mult = 0.8
    else:
        edge_mult = 1.0

    # إضافة عشوائية
    import random
    rand_mult = random.uniform(0.9, 1.15)

    multiplier = base_mult * segment_mult * edge_mult * rand_mult
    return max(1.2, min(10.0, multiplier))
```

---

## المرحلة 3: تحكم الأدمن الكامل

### 3.1 تحكم بكل لاعب:

| التحكم | API | الوصف |
|--------|-----|------|
| **ربح مخصص** | `POST /api/admin/player/{uid}/win-override` | يحدد احتمال فوز محدد (0-1) أو -1 لخسارة مضمونة |
| **حظر لعب** | `POST /api/admin/player/{uid}/block` | يمنع اللاعب من اللعب |
| **تبريد** | `POST /api/admin/player/{uid}/cooldown` | تبريد إجباري لمدة N دقيقة |
| **إضافة رصيد** | `POST /api/admin/player/{uid}/balance` | إضافة/خصم رصيد يدوي |
| **شريك VEX** | `POST /api/admin/player/{uid}/vex` | تفعيل/إيقاف زر التعويض |

### 3.2 تحكم بالأرباح العامة:

```
لوحة الأدمن → ⚙️ إعدادات الأرباح
├─ الربح المستهدف للإدارة: [15]%
├─ أقصى ربح يومي/لاعب: [3000]
├─ أقصى خسارة يومية/لاعب: [5000]
├─ عند انخفاض الهامش < 5%: [خفض الفوز × 0.6]
├─ عند انخفاض الهامش < 3%: [حظر اللعب مؤقتاً]
├─ دورة التعويض كل: [8] جولات
├─ التبريد التلقائي بعد خسارة: [2000]
└─ [💾 حفظ]
```

---

## المرحلة 4: نظام الإشعارات اللحظية

### 4.1 للعميل (في تيليجرام):
```
✅ تم إيداع 500 SAR في محفظتك
🎮 رصيدك الآن: 1,500 SAR
```

### 4.2 للأدمن (في تيليجرام):
```
💰 طلب إيداع جديد
👤 أحمد — 500 SAR — فودافون كاش
[✅ موافقة] [❌ رفض]
```

### 4.3 للوحة الويب (WebSocket/SSE):
```
مراقبة لحظية:
├─ إيداع جديد → تنبيه فوري
├─ لاعب ساخن → تنبيه
├─ هامش منخفض → تنبيه أحمر
├─ خسارة كبيرة → تنبيه
└─ سحب جديد → تنبيه
```

---

## المرحلة 5: أنماط نفسية متقدمة

### 5.1 "خسارة مقنّعة كفوز" (Loss Disguised as Win):
```python
if bet_amount > 50 and random.random() < 0.3:
    payout = bet_amount * random.uniform(0.5, 0.9)
    # اعرض كفوز — العميل يحتفل رغم خسارته
```

### 5.2 "خسارة كبيرة بعد مكاسب صغيرة":
```python
if player.small_win_streak >= 3:
    # العميل ربح 3 مرات صغيرة
    # الآن أجبره على خسارة كبيرة لو راهن كبير
    force_lose = True
    # النتيجة: "كنت رابح! لكن خسرت كل شيء!
    #          لازم ألعب أكثر لأسترجع!"
```

### 5.3 "طُعم التعافي":
```python
if player.last_loss_amount > player.avg_bet * 3:
    # بعد خسارة كبيرة → أعطِ فوز صغير
    # العميل يعتقد أنه "يستعيد" → يراهن أكبر
    next_win_guaranteed = True
    next_payout = player.last_loss_amount * 0.3  # 30% فقط من الخسارة
```

---

## ترتيب التنفيذ:

| الأولوية | المهمة | المدة |
|---------|------|------|
| 🔴 1 | توحيد المحفظة + إيداع/سحب | أساسي |
| 🔴 2 | إصلاح الخوارزمية (صياغة مضاعفة) | أساسي |
| 🟠 3 | مضاعف ديناميكي | عالي |
| 🟠 4 | تحكم الأدمن بكل لاعب | عالي |
| 🟠 5 | إشعارات لحظية | عالي |
| 🟡 6 | أنماط نفسية متقدمة | متوسط |
| 🟡 7 | أمان API (auth) | متوسط |
| 🟢 8 | سجل مالي كامل | لاحقاً |
