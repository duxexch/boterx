"""
VEX Games Platform — House Algorithm
خوارزمية ضمان الأرباح — مستوحاة من 1xBet/Melbet

7 عوامل مرجّحة تحسب احتمال الفوز لكل جلسة + 5 أنماط تلاعب نفسي.
"""

import csv
import os
import json
import random
import math
from datetime import datetime, timedelta
from collections import defaultdict

CSV_ENCODING = 'utf-8-sig'

# ─── أوزان العوامل (المجموع = 1.0) ───
FACTOR_WEIGHTS = {
    'net_position': 0.30,    # صافي اللاعب
    'heat_level': 0.20,      # الحرارة
    'compensation': 0.15,    # دورة التعويض
    'ltv': 0.10,             # قيمة اللاعب
    'bet_size': 0.10,        # حجم المراهنة
    'time_of_day': 0.05,     # وقت اللعب
    'entropy': 0.10,          # عشوائية
}

# ─── حدود الأمان ───
MAX_WIN_CHANCE = 0.90   # أقصى احتمال فوز 90%
MIN_WIN_CHANCE = 0.05   # أقل احتمال فوز 5%


class HouseAlgorithm:
    """محرك الاحتمالات الذكي — يحسب احتمال الفوز لكل جلسة"""

    def __init__(self, config_file='algorithm_config.csv'):
        self.config_file = config_file
        self.config = self._load_config()

    # ─── الإعدادات ───

    def _load_config(self):
        """تحميل إعدادات الخوارزمية من CSV"""
        defaults = {
            'target_house_edge': '0.15',
            'max_daily_loss_per_player': '5000',
            'max_daily_win_per_player': '3000',
            'max_bets_per_hour': '50',
            'compensation_interval': '8',
            'max_session_duration_min': '60',
            'auto_cooldown_after_loss': '2000',
            'min_balance_to_play': '10',
            'platform_target_edge': '0.15',
            'alert_threshold_edge': '0.05',
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding=CSV_ENCODING) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        defaults[row.get('key', '')] = row.get('value', '')
            except:
                pass
        return defaults

    def get_config(self, key, default=None):
        """قراءة إعداد"""
        val = self.config.get(key, '')
        if not val:
            return default
        try:
            return float(val)
        except:
            return val

    def update_config(self, key, value, modified_by='admin'):
        """تحديث إعداد"""
        self.config[key] = str(value)
        rows = []
        fieldnames = ['key', 'value', 'description', 'last_modified_by', 'modified_at']
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding=CSV_ENCODING) as f:
                    reader = csv.DictReader(f)
                    existing = {r.get('key', ''): r for r in reader}
            except:
                existing = {}
        else:
            existing = {}

        if key in existing:
            row = existing[key]
            row['value'] = str(value)
            row['last_modified_by'] = modified_by
            row['modified_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            rows = list(existing.values())
        else:
            existing[key] = {
                'key': key, 'value': str(value),
                'description': '', 'last_modified_by': modified_by,
                'modified_at': datetime.now().strftime('%Y-%m-%d %H:%M')
            }
            rows = list(existing.values())

        with open(self.config_file, 'w', newline='', encoding=CSV_ENCODING) as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, '') for k in fieldnames})

    # ─── الحساب الرئيسي ───

    def calculate_win_chance(self, player, game, bet_amount):
        """
        حساب احتمال الفوز لجلسة واحدة
        
        Args:
            player: dict — ملف اللاعب (من player_profiles.csv)
            game: dict — معلومات اللعبة (من games_catalog.csv)
            bet_amount: float — مبلغ المراهنة
        
        Returns:
            dict: {
                'win_chance': float (0.05 - 0.90),
                'factors': dict — تفاصيل كل عامل,
                'decision': str — القرار النهائي,
                'reason': str — سبب القرار
            }
        """
        base = float(game.get('base_win_chance', 0.45) or 0.45)
        factors = {}
        reasons = []

        # ===== 1. صافي اللاعب (30%) =====
        net = float(player.get('net_position', 0) or 0)
        if net > 0:
            reduction = min(0.4, (net / 1000) * 0.05)
            factor_1 = 1 - reduction
            reasons.append(f'لاعب رابح ({net:.0f}) → خفض {reduction:.0%}')
        elif net < -1000:
            boost = min(1.5, (abs(net) / 1000) * 0.1)
            factor_1 = 1 + boost
            reasons.append(f'لاعب خاسر ({net:.0f}) → تحفيز +{boost:.0%}')
        else:
            factor_1 = 1.0
        factors['net_position'] = factor_1

        # ===== 2. الحرارة (20%) =====
        heat = float(player.get('heat_level', 0) or 0)
        if heat > 7:
            factor_2 = 0.7
            reasons.append(f'لاعب ساخن جداً ({heat:.0f}/10) → خفض 30%')
        elif heat > 5:
            factor_2 = 0.85
            reasons.append(f'لاعب ساخن ({heat:.0f}/10) → خفض 15%')
        elif heat < 2:
            factor_2 = 1.1
            reasons.append(f'لاعب بارد ({heat:.0f}/10) → تحفيز 10%')
        else:
            factor_2 = 1.0
        factors['heat_level'] = factor_2

        # ===== 3. دورة التعويض (15%) =====
        comp_interval = int(self.get_config('compensation_interval', 8))
        total_games = int(player.get('total_games', 0) or 0)
        if total_games > 0 and total_games % comp_interval == 0 and net < 0:
            factor_3 = 2.0
            reasons.append(f'دورة تعويض (جلسة {total_games}) → فوز مضمون')
        elif total_games > 0 and total_games % comp_interval == comp_interval - 1:
            factor_3 = 0.5
            reasons.append(f'قبل دورة التعويض → خفض للموضة (near-miss)')
        else:
            factor_3 = 1.0
        factors['compensation'] = factor_3

        # ===== 4. قيمة اللاعب LTV (10%) =====
        ltv = float(player.get('lifetime_value', 0) or 0)
        if ltv > 5000:
            factor_4 = 1.15
            reasons.append(f'لاعب VIP (LTV={ltv:.0f}) → حافظ عليه +15%')
        elif ltv < 500:
            factor_4 = 0.9
            reasons.append(f'لاعب جديد (LTV={ltv:.0f}) → اختبره -10%')
        else:
            factor_4 = 1.0
        factors['ltv'] = factor_4

        # ===== 5. حجم المراهنة (10%) =====
        avg_bet = float(player.get('avg_bet', bet_amount) or bet_amount)
        if avg_bet > 0 and bet_amount > avg_bet * 3:
            factor_5 = 0.6
            reasons.append(f'مراهنة كبيرة ({bet_amount} > {avg_bet:.0f}×3) → خفض 40%')
        elif avg_bet > 0 and bet_amount < avg_bet * 0.5:
            factor_5 = 1.1
            reasons.append(f'مراهنة صغيرة → لا يهم +10%')
        else:
            factor_5 = 1.0
        factors['bet_size'] = factor_5

        # ===== 6. وقت اللعب (5%) =====
        hour = datetime.now().hour
        if 0 <= hour < 6:
            factor_6 = 1.2
            reasons.append('ليل متأخر → فوز أسهل +20%')
        elif hour >= 22:
            factor_6 = 1.1
        else:
            factor_6 = 1.0
        factors['time_of_day'] = factor_6

        # ===== 7. العشوائية (10%) =====
        entropy = random.uniform(0.85, 1.15)
        factors['entropy'] = entropy

        # ===== الحساب المرجّح =====
        weighted = base * (
            factor_1 * FACTOR_WEIGHTS['net_position'] +
            factor_2 * FACTOR_WEIGHTS['heat_level'] +
            factor_3 * FACTOR_WEIGHTS['compensation'] +
            factor_4 * FACTOR_WEIGHTS['ltv'] +
            factor_5 * FACTOR_WEIGHTS['bet_size'] +
            factor_6 * FACTOR_WEIGHTS['time_of_day'] +
            entropy * FACTOR_WEIGHTS['entropy']
        )

        # ===== ضمانات الأمان =====
        # حدود الاحتمال
        weighted = min(MAX_WIN_CHANCE, weighted)
        weighted = max(MIN_WIN_CHANCE, weighted)

        # حد الخسارة اليومي
        daily_loss = float(player.get('daily_loss', 0) or 0)
        max_daily_loss = self.get_config('max_daily_loss_per_player', 5000)
        if daily_loss > max_daily_loss:
            weighted = min(0.85, weighted * 2)
            reasons.append(f'تجاوز حد الخسارة اليومي ({daily_loss:.0f}) → تعويض')

        # حد الربح اليومي
        daily_win = float(player.get('daily_win', 0) or 0)
        max_daily_win = self.get_config('max_daily_win_per_player', 3000)
        if daily_win > max_daily_win:
            weighted = max(MIN_WIN_CHANCE, weighted * 0.3)
            reasons.append(f'تجاوز حد الربح اليومي ({daily_win:.0f}) → خفض شديد')

        # ===== القرار النهائي =====
        roll = random.random()
        if roll < weighted:
            decision = 'allow_win'
            reason = f'فوز (احتمال={weighted:.1%}, roll={roll:.2f})'
        else:
            # تحديد نوع الخسارة
            consec_losses = int(player.get('consecutive_losses', 0) or 0)
            if consec_losses >= 2 and random.random() < 0.4:
                decision = 'near_miss'
                reason = f'خسارة قريبة (near-miss) — احتمال={weighted:.1%}'
            else:
                decision = 'force_lose'
                reason = f'خسارة (احتمال={weighted:.1%}, roll={roll:.2f})'

        return {
            'win_chance': weighted,
            'factors': factors,
            'decision': decision,
            'reason': '; '.join(reasons) if reasons else reason,
            'all_reasons': reasons + [reason],
        }

    # ─── تسجيل القرار ───

    def log_decision(self, session_id, user_id, game_id, base_chance, adjusted_chance,
                     factors, decision, reason, log_file='algorithm_decisions.csv'):
        """تسجيل قرار الخوارزمية للتدقيق"""
        fieldnames = ['id', 'session_id', 'user_id', 'game_id',
                      'base_chance', 'adjusted_chance', 'factors_applied',
                      'decision', 'reason', 'timestamp']
        row = {
            'id': f"DEC{str(int(datetime.now().timestamp()))[-8:]}",
            'session_id': session_id,
            'user_id': str(user_id),
            'game_id': game_id,
            'base_chance': f"{base_chance:.4f}",
            'adjusted_chance': f"{adjusted_chance:.4f}",
            'factors_applied': json.dumps(factors),
            'decision': decision,
            'reason': reason[:200],
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        try:
            file_exists = os.path.exists(log_file)
            with open(log_file, 'a', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row)
        except Exception as e:
            print(f"Error logging decision: {e}")

    # ─── حساب هامش المنصة ───

    def calculate_platform_edge(self, sessions_file='game_sessions.csv'):
        """حساب هامش ربح المنصة الفعلي"""
        total_wagered = 0
        total_won = 0
        try:
            if os.path.exists(sessions_file):
                with open(sessions_file, 'r', encoding=CSV_ENCODING) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        total_wagered += float(row.get('bet_amount', 0) or 0)
                        total_won += float(row.get('payout', 0) or 0)
        except:
            pass
        if total_wagered == 0:
            return float(self.get_config('platform_target_edge', 0.15))
        return 1 - (total_won / total_wagered)

    # ─── الأنماط النفسية ───

    def apply_psychological_pattern(self, player, decision, game_data=None):
        """
        تطبيق نمط نفسي على نتيجة الجلسة
        Returns: dict with display hints for the WebApp
        """
        hints = {
            'show_near_miss': False,
            'celebration_level': 'normal',
            'motivational_text': '',
            'suggested_bet': None,
        }

        consec_losses = int(player.get('consecutive_losses', 0) or 0)
        consec_wins = int(player.get('consecutive_wins', 0) or 0)
        net = float(player.get('net_position', 0) or 0)

        if decision == 'near_miss':
            hints['show_near_miss'] = True
            hints['motivational_text'] = '🔥 كادت أن تصطادها! حاول مرة أخرى!'
            hints['celebration_level'] = 'tease'

        elif decision == 'allow_win':
            if consec_losses >= 5:
                hints['motivational_text'] = '🎉 أخيراً! الحظ يعود لك!'
                hints['celebration_level'] = 'big'
            elif consec_wins >= 2:
                hints['motivational_text'] = '⚡ أنت على موجة! استمر!'
                hints['celebration_level'] = 'excited'

        elif decision == 'force_lose':
            if consec_losses >= 3:
                hints['motivational_text'] = '💪 الحظ قريب! جرب مبلغ مختلف'
                hints['suggested_bet'] = 'smaller'
            else:
                hints['motivational_text'] = '🎯 حظ أوفر في المرة القادمة!'

        return hints
