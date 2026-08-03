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
        حساب احتمال الفوز — صياغة مضاعفة (أقوى من الجمع الخطي)
        
        win_chance = base × f_net × f_heat × f_platform × f_comp × f_admin × f_entropy
        """
        base = float(game.get('base_win_chance', 0.45) or 0.45)
        factors = {}
        reasons = []

        # ===== 1. صافي اللاعب =====
        net = float(player.get('net_position', 0) or 0)
        if net > 0:
            f_net = max(0.3, 1 - (net / 5000))
            reasons.append(f'لاعب رابح ({net:.0f}) → ×{f_net:.2f}')
        elif net < -500:
            f_net = min(1.8, 1 + (abs(net) / 2000))
            reasons.append(f'لاعب خاسر ({net:.0f}) → ×{f_net:.2f}')
        else:
            f_net = 1.0
        factors['net_position'] = f_net

        # ===== 2. الحرارة =====
        heat = float(player.get('heat_level', 0) or 0)
        if heat > 7:
            f_heat = 0.5
            reasons.append(f'ساخن جداً ({heat:.0f}) → ×0.5')
        elif heat > 5:
            f_heat = 0.75
        elif heat < 2:
            f_heat = 1.2
            reasons.append(f'بارد ({heat:.0f}) → ×1.2')
        else:
            f_heat = 1.0
        factors['heat_level'] = f_heat

        # ===== 3. حالة المنصة (جديد!) =====
        platform_edge = self.calculate_platform_edge()
        target_edge = self.get_config('platform_target_edge', 0.15)
        if platform_edge < float(target_edge) * 0.5:
            f_platform = 0.6
            reasons.append(f'منصة تخسر ({platform_edge:.1%}) → ×0.6')
        elif platform_edge < float(target_edge):
            f_platform = 0.8
        else:
            f_platform = 1.0
        factors['platform_edge'] = f_platform

        # ===== 4. دورة التعويض =====
        comp_interval = int(self.get_config('compensation_interval', 8))
        total_games = int(player.get('total_games', 0) or 0)
        if total_games > 0 and (total_games + 1) % comp_interval == 0 and net < 0:
            f_comp = 2.5
            reasons.append(f'دورة تعويض (جلسة {total_games+1}) → ×2.5')
        elif total_games > 0 and (total_games + 1) % comp_interval == comp_interval - 1:
            f_comp = 0.4
            reasons.append('قبل التعويض → ×0.4')
        else:
            f_comp = 1.0
        factors['compensation'] = f_comp

        # ===== 5. تحكم الأدمن (جديد!) =====
        admin_override = float(player.get('admin_win_override', 0) or 0)
        if admin_override > 0:
            f_admin = admin_override
            reasons.append(f'تحكم أدمن → ×{f_admin:.2f}')
        elif admin_override < 0:
            f_admin = 0.05
            reasons.append('أدمن أمر بخسارة → ×0.05')
        else:
            f_admin = 1.0
        factors['admin_override'] = f_admin

        # ===== 6. قيمة اللاعب =====
        ltv = float(player.get('lifetime_value', 0) or 0)
        if ltv > 5000:
            f_ltv = 1.15
        elif ltv < 500:
            f_ltv = 0.9
        else:
            f_ltv = 1.0
        factors['ltv'] = f_ltv

        # ===== 7. حجم المراهنة =====
        avg_bet = float(player.get('avg_bet', bet_amount) or bet_amount)
        if avg_bet > 0 and bet_amount > avg_bet * 3:
            f_bet = 0.6
            reasons.append(f'مراهنة كبيرة → ×0.6')
        else:
            f_bet = 1.0
        factors['bet_size'] = f_bet

        # ===== الصياغة المضاعفة =====
        win_chance = base * f_net * f_heat * f_platform * f_comp * f_admin * f_ltv * f_bet

        # ===== حدود الأمان =====
        win_chance = min(0.92, max(0.03, win_chance))

        # ===== حدود يومية =====
        daily_loss = float(player.get('daily_loss', 0) or 0)
        max_daily_loss = self.get_config('max_daily_loss_per_player', 5000)
        if daily_loss > max_daily_loss:
            win_chance = min(0.85, win_chance * 2)

        daily_win = float(player.get('daily_win', 0) or 0)
        max_daily_win = self.get_config('max_daily_win_per_player', 3000)
        if daily_win > max_daily_win:
            win_chance = max(0.03, win_chance * 0.3)

        # ===== القرار =====
        roll = random.random()
        consec_losses = int(player.get('consecutive_losses', 0) or 0)

        # نمط: خسارة مقنّعة كفوز (30% فرصة لو المراهنة > 50)
        if roll >= win_chance and bet_amount > 50 and random.random() < 0.3:
            decision = 'disguised_loss'
            reason = f'خسارة مقنّعة (احتمال={win_chance:.1%})'
        # نمط: near-miss لو خسر مرتين متتاليتين
        elif roll >= win_chance and consec_losses >= 2 and random.random() < 0.4:
            decision = 'near_miss'
            reason = f'خسارة قريبة (near-miss) — احتمال={win_chance:.1%}'
        elif roll < win_chance:
            decision = 'allow_win'
            reason = f'فوز (احتمال={win_chance:.1%})'
        else:
            decision = 'force_lose'
            reason = f'خسارة (احتمال={win_chance:.1%})'

        return {
            'win_chance': win_chance,
            'factors': factors,
            'decision': decision,
            'reason': '; '.join(reasons) if reasons else reason,
            'all_reasons': reasons + [reason],
            'platform_edge': platform_edge,
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
