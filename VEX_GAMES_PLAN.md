# VEX Games Platform — خطة العمل المتقدمة v2

## الفلسفة
نظام ألعاب مؤسسي مستوى 1xBet/Melbet — باك-إند ذكي، واجهة احترافية، خوارزميات ربحية متعلمة، ولوحة تحكم تحليلية شاملة لإدارة المخاطر.

---

## الباب الأول: البنية التحتية المؤسسية

### 1.1 معمارية النظام (3 طبقات)

```
┌─────────────────────────────────────────────────┐
│  الطبقة 1: واجهة اللاعب (Telegram WebApp)       │
│  ├── games_hub.html — شبكة الألعاب               │
│  ├── game_play.html — محرك اللعبة العام          │
│  └── quick_deposit.html — إيداع سريع             │
├─────────────────────────────────────────────────┤
│  الطبقة 2: API + منطق الأعمال (Flask)            │
│  ├── /api/games/* — إدارة الألعاب                │
│  ├── /api/wallet/* — المحفظة والمعاملات           │
│  ├── /api/engine/* — محرك المراهنات              │
│  └── /api/admin/* — لوحة التحكم                  │
├─────────────────────────────────────────────────┤
│  الطبقة 3: محرك الذكاء (Python Backend)           │
│  ├── game_engine.py — إدارة الجلسات              │
│  ├── house_algorithm.py — خوارزمية الأرباح       │
│  ├── risk_manager.py — إدارة المخاطر             │
│  └── player_tracker.py — تتبع وتحليل اللاعبين    │
└─────────────────────────────────────────────────┘
```

### 1.2 ملفات البيانات (CSV موسّعة)

```csv
# كتالوج الألعاب
games_catalog.csv
  id, name, icon, description, category,
  min_bet, max_bet, base_win_chance, house_edge_pct,
  rtp_target (Return To Player %),
  volatility (low/medium/high),
  max_payout_per_session,
  is_active, created_at

# جلسات اللعب (سجل كامل)
game_sessions.csv
  id, session_id, game_id, user_id,
  bet_amount, multiplier, payout,
  result (win/lose/push),
  balance_before, balance_after,
  win_chance_at_play (الاحتمال الفعلي وقت اللعب),
  algorithm_factors (JSON: العوامل المؤثرة),
  timestamp, duration_seconds

# ملف اللاعب الذكي
player_profiles.csv
  user_id, telegram_id, name,
  total_games, total_sessions,
  total_wagered, total_won, total_lost,
  net_position, win_rate,
  avg_bet, max_bet, min_bet,
  favorite_game, favorite_bet_amount,
  risk_score (0-100),
  heat_level (0-10, مدى نشاط اللاعب الحالي),
  is_vex_partner, vex_partner_since,
  last_played, first_play_date,
  session_streak (جلسات متتالية),
  cooldown_until (تاريخ التبريد),
  lifetime_value (LTV — قيمة اللاعب مدى الحياة),
  churn_risk (احتمال المغادرة 0-100),
  created_at, updated_at

# إيداعات سريعة أثناء اللعب
quick_deposits.csv
  id, user_id, amount, payment_method_id,
  account_number, status (pending/approved/rejected),
  approved_by, approved_at, game_session_id,
  created_at

# وسائل دفع اللاعب المحفوظة
player_payment_methods.csv
  id, user_id, method_name, account_number,
  method_type, icon, is_default, created_at

# سجل الخوارزمية (للتدقيق والمراجعة)
algorithm_decisions.csv
  id, session_id, user_id, game_id,
  base_chance, adjusted_chance,
  factors_applied (JSON),
  decision (allow_win/force_lose/near_miss/compensate),
  reason, timestamp

# تنبيهات المخاطر
risk_alerts.csv
  id, alert_type, user_id, severity,
  message, auto_action_taken,
  status (active/resolved), created_at

# إعدادات الخوارزمية (قابلة للتعديل من اللوحة)
algorithm_config.csv
  key, value, description, last_modified_by, modified_at
```

---

## الباب الثاني: خوارزمية ضمان الأرباح (House Algorithm)

### 2.1 الفلسفة (مستوحاة من 1xBet/Melbet)

الخوارزمية لا تتحكم في نتيجة واحدة — بل تدير **دورة حياة اللاعب الكاملة**:

```
اللاعب الجديد → مرحلة الإغراء → مرحلة الإدمان → مرحلة الاستقرار → مرحلة التبريد
    ↓              ↓              ↓              ↓              ↓
 فوز سهل      خسائر تدريجية    فوز متقطع     توازن دقيق     تبريد إجباري
 (hook)       (reel in)        (keep playing) (harvest)      (cooldown)
```

### 2.2 محرك الاحتمالات (Probability Engine)

```python
class HouseAlgorithm:
    """
    محرك الاحتمالات الذكي — يحسب احتمال الفوز لكل جلسة
    
    العوامل المرجّحة (مجموعها = 100%):
    1. صافي اللاعب (net_position)     — 30%
    2. الحرارة (heat_level)           — 20%
    3. دورة التعويض (compensation)    — 15%
    4. قيمة اللاعب (LTV)              — 10%
    5. حجم المراهنة (bet_size)        — 10%
    6. وقت اللعب (time_of_day)        — 5%
    7. عشوائية (entropy)              — 10%
    """
    
    def calculate_win_chance(self, player, game, bet_amount, session_context):
        base = game.base_win_chance  # مثلاً 0.45
        
        # ========== 1. ضبط صافي اللاعب (30%) ==========
        net = player.net_position  # موجب = رابح، سالب = خاسر
        if net > 0:
            # لاعب رابح — قلل احتمالاته
            # كل 1000 ربح → تقليل 5% من الاحتمال
            reduction = min(0.4, (net / 1000) * 0.05)
            factor_1 = 1 - reduction
        elif net < -1000:
            # لاعب خاسر كثير — حفّزه بفوز
            boost = min(1.5, (abs(net) / 1000) * 0.1)
            factor_1 = 1 + boost
        else:
            factor_1 = 1.0
        
        # ========== 2. الحرارة (20%) ==========
        # heat_level: 0-10 بناءً على آخر 30 دقيقة
        heat = player.heat_level
        if heat > 7:
            factor_2 = 0.7  # لاعب ساخن جداً — اخفض الفوز
        elif heat > 5:
            factor_2 = 0.85
        elif heat < 2:
            factor_2 = 1.1  # لاعب بارد — حفّزه
        else:
            factor_2 = 1.0
        
        # ========== 3. دورة التعويض (15%) ==========
        # كل N جلسات، أعطِ فوز شبه مضمون
        compensation_interval = 8  # كل 8 جلسات
        if player.total_games % compensation_interval == 0:
            if player.net_position < 0:
                factor_3 = 2.0  # فوز مضمون للتعويض
            else:
                factor_3 = 1.0
        elif player.total_games % compensation_interval == compensation_interval - 1:
            # الجلسة قبل التعويض — اجعله يخسر بشدة (near-miss)
            factor_3 = 0.5
        else:
            factor_3 = 1.0
        
        # ========== 4. قيمة اللاعب LTV (10%) ==========
        # LTV عالي → حافظ عليه (لا تخسره)
        ltv = player.lifetime_value
        if ltv > 5000:
            factor_4 = 1.15  # لاعب مهم — أعطه فوز أكبر
        elif ltv < 500:
            factor_4 = 0.9   # لاعب جديد — اختبره
        else:
            factor_4 = 1.0
        
        # ========== 5. حجم المراهنة (10%) ==========
        # مراهنة كبيرة → خطر أكبر على الأرباح
        if bet_amount > player.avg_bet * 3:
            # مراهنة غير معتادة كبيرة — خفض الفوز
            factor_5 = 0.6
        elif bet_amount < player.avg_bet * 0.5:
            # مراهنة صغيرة — لا يهم كثيراً
            factor_5 = 1.1
        else:
            factor_5 = 1.0
        
        # ========== 6. وقت اللعب (5%) ==========
        hour = datetime.now().hour
        if hour >= 0 and hour < 6:
            factor_6 = 1.2  # ليل → لاعب متعب → فوز أسهل (يبيتي)
        elif hour >= 22:
            factor_6 = 1.1  # مساء متأخر
        else:
            factor_6 = 1.0
        
        # ========== 7. العشوائية (10%) ==========
        # أضف ضوضاء عشوائية لمنع اكتشاف النمط
        import random
        entropy = random.uniform(0.85, 1.15)
        
        # ========== الحساب النهائي ==========
        weighted = (
            base * factor_1 * 0.30 +
            base * factor_2 * 0.20 +
            base * factor_3 * 0.15 +
            base * factor_4 * 0.10 +
            base * factor_5 * 0.10 +
            base * factor_6 * 0.05 +
            base * entropy * 0.10
        )
        
        # ========== ضمانات الأمان ==========
        # 1. احتمال الفوز لا يتجاوز 90% (مستحيل 100%)
        weighted = min(0.90, weighted)
        # 2. احتمال الفوز لا يقل عن 5% (مستحيل 0%)
        weighted = max(0.05, weighted)
        # 3. التحقق من حد الخسارة اليومي
        if player.daily_loss > self.get_config('max_daily_loss_per_player', 5000):
            # اللاعب خسر كثير اليوم — أعطه فوز للتعويض
            weighted = min(0.85, weighted * 2)
        # 4. التحقق من حد الربح اليومي
        if player.daily_win > self.get_config('max_daily_win_per_player', 3000):
            # اللاعب ربح كثير اليوم — خفض الفوز
            weighted = max(0.05, weighted * 0.3)
        
        return weighted
```

### 2.3 أنماط التلاعب النفسي (Psychological Patterns)

```python
class PsychologicalEngine:
    """محرك التلاعب النفسي — يشبه أنماط 1xBet"""
    
    def apply_pattern(self, player, session_result):
        """
        أنماط تطبق بعد كل نتيجة:
        """
        
        # 1. "Near-Miss" — خسارة قريبة جداً
        # العميل خسر لكن النتيجة كانت قريبة من الفوز
        # مثال: في السلوتس، بكرتين متطابقتين والثالثة مختلفة بقليل
        # الأثر النفسي: "كنت قريباً! أحاول مرة أخرى"
        if session_result == 'lose' and player.session_streak >= 2:
            self.show_near_miss = True  # واجهة تُظهر أنه كان قريباً
        
        # 2. "Win Streak Illusion" — وهم سلسلة انتصارات
        # بعد خسارة طويلة، أعطِ 2-3 انتصارات صغيرة متتالية
        # الأثر: "أنا محظوظ الآن! أراهن أكبر"
        if player.consecutive_losses >= 5:
            self.force_win_streak = 3  # 3 انتصارات صغيرة
        
        # 3. "Big Loss After Small Wins" — خسارة كبيرة بعد مكاسب صغيرة
        # العميل ربح 3 مرات صغيرة → يراهن كبير → يخسر
        # الأثر: العميل يريد تعويض الخسارة الكبيرة → يلعب أكثر
        if player.small_win_streak >= 3:
            self.max_payout_this_session = 0  # لا فوز هذه الجولة
        
        # 4. "Recovery Bait" — طُعم التعافي
        # بعد خسارة كبيرة، أظهر له أنه "كاد يربح"
        # ثم أعطِه فوز صغير ليعتقد أنه يستعيد أمواله
        if player.last_loss_amount > player.avg_bet * 3:
            self.next_session_force_win = True
            self.next_session_max_payout = player.last_loss_amount * 0.3
        
        # 5. "Loss Disguised as Win" — خسارة مقنّعة كفوز
        # العميل راهن 100 → "ربح" 80 → في الحقيقة خسر 20
        # الأثر: يحتفل بـ "الفوز" رغم أنه خسر
        if bet_amount > 50 and random.random() < 0.3:
            payout = bet_amount * random.uniform(0.5, 0.9)
            self.disguised_win = True  # اعرضها كانتصار
```

### 2.4 إدارة المخاطر (Risk Manager)

```python
class RiskManager:
    """
    نظام إدارة المخاطر — يحمي الأرباح على مستوى المنصة
    """
    
    # حدود قابلة للتعديل من لوحة التحكم
    LIMITS = {
        'max_daily_loss_per_player': 5000,      # أقصى خسارة يومية للاعب
        'max_daily_win_per_player': 3000,       # أقصى ربح يومي للاعب
        'max_session_duration_min': 60,         # أقصى مدة جلسة (دقيقة)
        'max_bets_per_hour': 50,                # أقصى عدد مراهنات/ساعة
        'max_total_platform_payout_hourly': 10000,  # أقصى دفع إجمالي/ساعة
        'platform_target_edge': 0.15,           # هدف هامش الربح (15%)
        'alert_threshold_edge': 0.05,           # تنبيه إذا الهامش < 5%
        'auto_cooldown_after_loss': 2000,       # تبريد إجباري بعد خسارة
        'min_balance_to_play': 10,              # أقل رصيد للعب
    }
    
    def check_risk(self, player, bet_amount, game):
        """فحص المخاطر قبل بدء الجولة"""
        alerts = []
        
        # 1. حد الخسارة اليومي
        if player.daily_loss >= self.LIMITS['max_daily_loss_per_player']:
            alerts.append({
                'type': 'daily_loss_exceeded',
                'severity': 'high',
                'action': 'block_play',
                'message': f'اللاعب تجاوز حد الخسارة اليومي ({player.daily_loss})'
            })
        
        # 2. حد الربح اليومي
        if player.daily_win >= self.LIMITS['max_daily_win_per_player']:
            alerts.append({
                'type': 'daily_win_exceeded',
                'severity': 'high',
                'action': 'reduce_win_chance',
                'message': f'اللاعب تجاوز حد الربح اليومي ({player.daily_win})'
            })
        
        # 3. كثرة المراهنات
        if player.bets_last_hour >= self.LIMITS['max_bets_per_hour']:
            alerts.append({
                'type': 'rate_limit',
                'severity': 'medium',
                'action': 'enforce_cooldown',
                'message': f'كثرة مراهنات: {player.bets_last_hour}/ساعة'
            })
        
        # 4. مراهنة كبيرة غير معتادة
        if bet_amount > player.avg_bet * 5:
            alerts.append({
                'type': 'unusual_bet',
                'severity': 'high',
                'action': 'reduce_win_chance',
                'message': f'مراهنة كبيرة: {bet_amount} (avg: {player.avg_bet})'
            })
        
        # 5. الهامش الكلي للمنصة
        platform_edge = self.calculate_platform_edge()
        if platform_edge < self.LIMITS['alert_threshold_edge']:
            alerts.append({
                'type': 'low_platform_edge',
                'severity': 'critical',
                'action': 'global_win_reduction',
                'message': f'هامش المنصة منخفض: {platform_edge:.1%}'
            })
        
        return alerts
    
    def calculate_platform_edge(self):
        """حساب هامش ربح المنصة الفعلي"""
        total_wagered = sum(p.total_wagered for p in all_players)
        total_won = sum(p.total_won for p in all_players)
        if total_wagered == 0:
            return self.LIMITS['platform_target_edge']
        return 1 - (total_won / total_wagered)
    
    def enforce_cooldown(self, player, minutes=15):
        """تبريد إجباري — منع اللاعب من اللعب"""
        player.cooldown_until = datetime.now() + timedelta(minutes=minutes)
```

### 2.5 تتبع اللاعبين (Player Tracker)

```python
class PlayerTracker:
    """
    تتبع وتحليل سلوك اللاعبين — يتعلم ويتكيف
    """
    
    def update_profile(self, user_id, session_data):
        """تحديث ملف اللاعب بعد كل جلسة"""
        profile = self.get_profile(user_id)
        
        # تحديث الإحصائيات الأساسية
        profile.total_games += 1
        profile.total_wagered += session_data.bet_amount
        
        if session_data.result == 'win':
            profile.total_won += session_data.payout
            profile.consecutive_wins += 1
            profile.consecutive_losses = 0
            profile.daily_win += session_data.payout - session_data.bet_amount
        else:
            profile.total_lost += session_data.bet_amount
            profile.consecutive_losses += 1
            profile.consecutive_wins = 0
            profile.daily_loss += session_data.bet_amount
        
        # تحديث الحرارة
        profile.heat_level = self.calculate_heat(user_id)
        
        # تحديث قيمة اللاعب
        profile.lifetime_value = profile.total_wagered * 0.15  # 15% من إجمالي مراهناته
        
        # تحليل نمط المراهنة
        if session_data.bet_amount > profile.avg_bet * 2:
            profile.risk_score = min(100, profile.risk_score + 5)
        
        # تحديث احتمال المغادرة
        profile.churn_risk = self.predict_churn(profile)
        
        self.save_profile(profile)
    
    def calculate_heat(self, user_id):
        """حساب مستوى حرارة اللاعب (0-10)"""
        recent = self.get_recent_sessions(user_id, minutes=30)
        if not recent:
            return 0
        
        # كلما زاد عدد الجلسات في 30 دقيقة، زادت الحرارة
        count = len(recent)
        heat = min(10, count / 3)  # 30 جلسة في 30 دقيقة = حرارة 10
        
        # ضبط حسب حجم المراهنات
        avg_bet = sum(s.bet_amount for s in recent) / count
        if avg_bet > 100:
            heat = min(10, heat * 1.5)
        
        return heat
    
    def predict_churn(self, profile):
        """توقع احتمال مغادرة اللاعب"""
        # عوامل:
        # 1. لم يلعب منذ فترة طويلة
        # 2. خسائر متتالية كثيرة
        # 3. رصيد منخفض
        # 4. صافي سالب كبير
        
        risk = 0
        
        days_since_play = (datetime.now() - profile.last_played).days
        if days_since_play > 7:
            risk += 30
        elif days_since_play > 3:
            risk += 15
        
        if profile.consecutive_losses > 5:
            risk += 25
        
        if profile.balance < 50:
            risk += 20
        
        if profile.net_position < -2000:
            risk += 25
        
        return min(100, risk)
    
    def get_player_segment(self, profile):
        """تصنيف اللاعب إلى شريحة"""
        if profile.total_games < 10:
            return 'new'  # جديد
        elif profile.net_position > 1000:
            return 'winner'  # رابح (خطر)
        elif profile.net_position < -1000:
            return 'loser'  # خاسر (فرصة)
        elif profile.heat_level > 7:
            return 'hot'  # ساخن (نشط جداً)
        elif profile.churn_risk > 60:
            return 'churning'  # على وشك المغادرة
        elif profile.lifetime_value > 5000:
            return 'vip'  # مهم
        else:
            return 'regular'  # عادي
```

---

## الباب الثالث: لوحة التحكم التحليلية

### 3.1 لوحة المعلومات الرئيسية (Dashboard)

```
┌─────────────────────────────────────────────────────────┐
│  VEX Games Dashboard                                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐     │
│  │ إجمالي   │ │ صافي     │ │ هامش     │ │ لاعبون   │     │
│  │ المراهنات│ │ الربح    │ │ المنصة   │ │ نشطون    │     │
│  │ 125,000 │ │ 18,750  │ │ 15.0%   │ │ 342     │     │
│  │ 📈 +12%  │ │ 📈 +8%  │ │ ✅ هدف   │ │ 📈 +5%  │     │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘     │
│                                                         │
│  ┌─────────────────────────┐ ┌─────────────────────┐   │
│  │  الربح عبر الزمن         │ │ توزيع اللاعبين       │   │
│  │  ╱╲    ╱╲    ╱╲        │ │ 🟢 جديد: 45        │   │
│  │ ╱  ╲  ╱  ╲  ╱  ╲      │ │ 🔴 رابح: 12 (خطر)   │   │
│  │╱    ╲╱    ╲╱    ╲     │ │ 🟡 خاسر: 89         │   │
│  │                       │ │ 🔥 ساخن: 23         │   │
│  │  الأرباح تتزايد         │ │ 💎 VIP: 8           │   │
│  └─────────────────────────┘ └─────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  تنبيهات المخاطر (3)                    [عرض الكل]│   │
│  │  🔴 لاعب #8266 تجاوز حد الربح اليومي (3,200)    │   │
│  │  🟡 هامش المنصة منخفض: 4.2% (الحد الأدنى 5%)    │   │
│  │  🟡 5 لاعبين نشطون بكثرة (حرارة > 8)            │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  أفضل 10 لاعبين بالمراهنة                         │   │
│  │  1. أحمد — 12,500 (صافي: -1,200)  [🔥 ساخن]    │   │
│  │  2. عمر  — 8,300  (صافي: +500)   [⚠️ رابح]     │   │
│  │  3. ...                                         │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 3.2 صفحة اللاعب الواحد (Player Detail)

```
┌─────────────────────────────────────────────────────────┐
│  👤 أحمد محمد (ID: 8266)                                │
│  الشريحة: 🔥 ساخن | الحرارة: 8/10 | خطر المغادرة: 15%   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐     │
│  │ إجمالي   │ │ صافي     │ │ نسبة     │ │ متوسط    │     │
│  │ المراهنات│ │ الخسارة  │ │ الفوز    │ │ المراهنة │     │
│  │ 12,500  │ │ -1,200  │ │ 42%     │ │ 85      │     │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘     │
│                                                         │
│  ┌──────────────────┐ ┌──────────────────────┐        │
│  │ نمط المراهنة      │ │ سجل آخر 20 جلسة       │        │
│  │ 📊 يراهن أكبر     │ │ W L L W L W W L L W  │        │
│  │ بعد الفوز (80%)   │ │ L W L W L L L W L L  │        │
│  │ يلعب ليلاً (60%)  │ │ النمط: متقلب          │        │
│  └──────────────────┘ └──────────────────────┘        │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  قرار الخوارزمية الحالي                            │   │
│  │  • احتمال الفوز الأساسي: 45%                     │   │
│  │  • بعد التعديل: 32% (خفض بسبب الحرارة)          │   │
│  │  • الجلسة القادمة: دورة تعويض → فوز مضمون        │   │
│  │  • التوصية: السماح باللعب + مراقبة              │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  [💎 تعويض يدوي]  [❄️ تبريد إجباري]  [🚫 حظر اللعب]  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 3.3 صفحة إدارة المخاطر

```
┌─────────────────────────────────────────────────────────┐
│  ⚠️ إدارة المخاطر                                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  إعدادات الخوارزمية (قابلة للتعديل)              │   │
│  │  هامش الربح المستهدف: [15]%                      │   │
│  │  أقصى خسارة يومية/لاعب: [5000]                    │   │
│  │  أقصى ربح يومي/لاعب: [3000]                      │   │
│  │  أقصى مراهنات/ساعة: [50]                         │   │
│  │  فترة التبريد (دقيقة): [15]                      │   │
│  │  [💾 حفظ الإعدادات]                               │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  التنبيهات النشطة (3)                             │   │
│  │  🔴 هامش المنصة 4.2% < 5% (حرج)     [تخفيض عام] │   │
│  │  🟡 5 لاعبين حرارتهم > 8             [تبريد جماعي]│   │
│  │  🟡 2 لاعب تجاوزوا حد الربح اليومي    [مراقبة]    │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  موافقات الإيداع السريع (5 معلّق)                 │   │
│  │  ✅ أحمد — 500 ريال — فودافون   [موافقة] [رفض]  │   │
│  │  ✅ عمر  — 200 ريال — بنك       [موافقة] [رفض]  │   │
│  │  ...                                             │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 3.4 صفحة إدارة الألعاب

```
┌─────────────────────────────────────────────────────────┐
│  🎮 إدارة الألعاب                                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 🎁 اختطف  ✅ نشط     RTP: 85%   حرارة: متوسطة    │   │
│  │ min: 10  max: 500   [تعديل] [إيقاف]              │   │
│  ├─────────────────────────────────────────────────┤   │
│  │ 🎲 النرد  ✅ نشط     RTP: 88%   حرارة: منخفضة    │   │
│  │ min: 5   max: 1000  [تعديل] [إيقاف]              │   │
│  ├─────────────────────────────────────────────────┤   │
│  │ 🎰 سلوتس ⏸️ متوقف    RTP: 82%   حرارة: عالية     │   │
│  │ min: 20  max: 2000  [تعديل] [تفعيل]              │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  [➕ إضافة لعبة جديدة]                                   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## الباب الرابع: واجهة اللاعب

### 4.1 شبكة الألعاب (games_hub.html)

```
┌─────────────────────────────────┐
│  💰 رصيدك: 1,250    [💎 تعويض]  │  ← شريط علوي ثابت (Sticky)
│  🔥 مستواك: مبتدئ | 📊 فوز: 42% │
├─────────────────────────────────┤
│                                 │
│  ┌────┐ ┌────┐ ┌────┐          │
│  │🎁 │ │🎲 │ │🎰 │            │  ← شبكة ألعاب (تمرير عمودي)
│  │اختطف│ │نرد │ │سلوتس│         │
│  │10-500│ │5-1k│ │20-2k│       │    كل بطاقة =:
│  └────┘ └────┘ └────┘          │    - أيقونة
│  ┌────┐ ┌────┐ ┌────┐          │    - اسم
│  │🃏 │ │⛳ │ │🧩 │            │    - حدود المراهنة
│  │كوتشينة│ │جولف│ │بازل│        │    - RTP (وهمي)
│  └────┘ └────┘ └────┘          │    - شريط "ساخن"
│                                 │
└─────────────────────────────────┘
```

### 4.2 شاشة اللعبة

```
┌─────────────────────────────────┐
│  💰 رصيدك: 1,250    [💎 تعويض]  │  ← شريط علوي (Sticky)
├─────────────────────────────────┤
│                                 │
│  ┌─────────────────────────┐   │
│  │                         │   │
│  │    [منطقة اللعبة]       │   │  ← منطقة اللعب (Canvas/HTML)
│  │                         │   │
│  │    🎁 اختطف!            │   │
│  │    النتيجة: +250        │   │
│  │                         │   │
│  └─────────────────────────┘   │
│                                 │
├─────────────────────────────────┤
│  المبلغ: [___250___] [▶️ العب!] │  ← شريط المراهنة (Sticky)
│  [+10] [+50] [+100] [الكل]     │  ← أزرار سريعة
└─────────────────────────────────┘
```

### 4.3 مودال "استمرار اللعب" (بعد كل جولة)

```
┌─────────────────────────────────┐
│        🎉 ربحت! +250           │  ← نتيجة الجولة
│   💰 رصيدك: 1,500               │
│                                 │
│  ┌─────────────────────────┐   │
│  │ المبلغ: [___250___]      │   │  ← إدخال سريع
│  │ [▶️ العب مرة أخرى]       │   │  ← زر استئناف
│  └─────────────────────────┘   │
│                                 │
│  ─── 🎮 جرّب ألعاب أخرى ───     │
│  [🎁] [🎲] [🎰] [🃏] [⛳] ←→  │  ← تمرير أفقي للألعاب
│                                 │
│  [🏠 القائمة الرئيسية]           │
└─────────────────────────────────┘
```

### 4.4 مودال "إيداع سريع" (عند نفاد الرصيد)

```
┌─────────────────────────────────┐
│    ⚠️ رصيدك غير كافٍ            │
│                                 │
│  💰 رصيدك: 0                    │
│  🔧 المطلوب: 100                │
│                                 │
│  ─── إيداع سريع ───             │
│                                 │
│  اختر وسيلة الدفع:              │
│  [🏦 البنك الأهلي ✅] [📱 فودافون]│  ← وسائل محفوظة
│                                 │
│  رقم الحساب:                    │
│  ┌───────────────────┐         │
│  │ SA1234567890      │ 👈 نسخ  │  ← نسخ بضغطة
│  └───────────────────┘         │
│                                 │
│  المبلغ: [___100___]            │
│  [✅ تأكيد الإيداع]              │
│                                 │
│  [⏳ بانتظار تأكيد الإدارة...]  │  ← حالة الطلب
└─────────────────────────────────┘
```

---

## الباب الخامس: تدفق البيانات الكامل

### 5.1 دورة حياة جلسة اللعب

```
1. اللاعب يفتح شبكة الألعاب
   → WebApp تحمّل الرصيد من API
   → GET /api/wallet/balance?uid=X

2. اللاعب يختار لعبة
   → WebApp تفتح شاشة اللعبة
   → المبلغ الافتراضي = آخر مراهنة

3. اللاعب يحدد المبلغ ويضغط "العب"
   → POST /api/engine/start
   → {user_id, game_id, bet_amount}
   ↓
   a) RiskManager.check_risk() — فحص المخاطر
   b) HouseAlgorithm.calculate_win_chance() — حساب الاحتمال
   c) PlayerTracker.update_profile() — تسجيل
   d) خصم المبلغ من المحفظة فوراً
   ← Response: {session_id, win_chance, balance_after_bet}
   
4. اللعبة تعرض النتيجة (أنيميشن)
   → النتيجة محسومة من الخوارزمية
   → WebApp تعرض الفوز/الخسارة
   → "Near-miss" إذا خسر

5. مودال "استمرار"
   → إذا رصيد = 0 → مودال إيداع سريع
   → إذا رصيد > 0 → مودال استمرار + اقتراح ألعاب

6. الإيداع السريع (إن لزم)
   → POST /api/deposit/quick
   → {user_id, amount, method_id}
   → طلب للأدمن (pending)
   → الأدمن يوافق → POST /api/admin/approve_deposit
   → يُضاف الرصيد → إشعار للّاعب → اللعبة تستأنف
```

### 5.2 تدفق الإيداع السريع

```
اللاعب: رصيد = 0
    ↓
مودال إيداع سريع
    ↓
يختار وسيلة دفع محفوظة
    ↓
يظهر رقم الحساب (نسخ)
    ↓
يكتب المبلغ → يؤكد
    ↓
POST /api/deposit/quick
    ↓
quick_deposits.csv (status=pending)
    ↓
إشعار للأدمن (inline buttons)
    ↓
الأدمن يوافق
    ↓
+ إضافة الرصيد للمحفظة
+ إشعار للّاعب
+ استئناف اللعبة
```

---

## الباب السادس: خطة التنفيذ

| المرحلة | الوصف | الملفات | الأولوية |
|---------|-------|---------|---------|
| 1 | البنية التحتية | game_engine.py, house_algorithm.py, risk_manager.py, player_tracker.py + CSV جديدة | 🔴 حرج |
| 2 | API endpoints | dashboard/app.py — /api/games/*, /api/wallet/*, /api/engine/*, /api/admin/* | 🔴 حرج |
| 3 | شبكة الألعاب | dashboard/templates/games_hub.html | 🔴 حرج |
| 4 | محرك اللعبة العام | dashboard/templates/game_play.html | 🔴 حرج |
| 5 | مودال الاستمرار + الاقتراحات | داخل game_play.html | 🟠 عالي |
| 6 | الإيداع السريع | dashboard/templates/quick_deposit.html + API | 🟠 عالي |
| 7 | وسائل دفع محفوظة | player_payment_methods.csv + API | 🟡 متوسط |
| 8 | زر التعويض | منطق VEX partner | 🟡 متوسط |
| 9 | لوحة تحكم الويب | dashboard/templates/games_admin.html + APIs | 🟠 عالي |
| 10 | ألعاب جديدة | نرد، سلوتس، كوتشينة | 🟢 لاحقاً |
| 11 | تحليلات متقدمة | لوحة تحليلات + رسوم بيانية | 🟢 لاحقاً |

### ترتيب التنفيذ المقترح:
1. **البنية التحتية** — game_engine + house_algorithm + CSV (الأساس)
2. **API** — كل endpoints
3. **games_hub.html** — شبكة الألعاب
4. **game_play.html** — محرك اللعبة + مودال الاستمرار
5. **الإيداع السريع** — مودال + API + موافقة أدمن
6. **لوحة الأدمن** — تحليلات + مخاطر + موافقات
7. **ألعاب جديدة** — نرد + سلوتس

---

## الباب السابع: الأمان والمناعة

### 7.1 حماية الخوارزمية
- كل الحسابات **server-side** فقط
- العميل يرى فقط: "ربحت" أو "خسرت"
- لا يُرسل `win_chance` للعميل أبداً
- كل قرار يُسجّل في `algorithm_decisions.csv` للتدقيق

### 7.2 منع التلاعب
- التحقق من الرصيد **قبل** كل جولة
- التحقق من `session_id` صالح
- منع الجلسات المتزامنة لنفس اللاعب
- Rate limiting: أقصى 1 جلسة/ثانية
- التحقق من timestamp (منع replay attacks)

### 7.3 الشفافية للأدمن
- سجل كامل لكل قرار خوارزمية
- سبب كل تعديل على الاحتمال
- إمكانية تدقيق أي جلسة
- تنبيهات فورية عند انحراف الأرباح
