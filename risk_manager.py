"""
VEX Games Platform — Risk Manager
نظام إدارة المخاطر — يحمي الأرباح على مستوى المنصة
"""

import csv
import os
import json
from datetime import datetime, timedelta

CSV_ENCODING = 'utf-8-sig'


class RiskManager:
    """نظام إدارة المخاطر — حدود + تنبيهات + إجراءات تلقائية"""

    DEFAULT_LIMITS = {
        'max_daily_loss_per_player': 5000,
        'max_daily_win_per_player': 3000,
        'max_session_duration_min': 60,
        'max_bets_per_hour': 50,
        'max_total_platform_payout_hourly': 10000,
        'platform_target_edge': 0.15,
        'alert_threshold_edge': 0.05,
        'auto_cooldown_after_loss': 2000,
        'min_balance_to_play': 10,
    }

    def __init__(self, config_file='algorithm_config.csv'):
        self.config_file = config_file
        self.limits = self._load_limits()

    def _load_limits(self):
        """تحميل الحدود من ملف الإعدادات"""
        limits = dict(self.DEFAULT_LIMITS)
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding=CSV_ENCODING) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        key = row.get('key', '')
                        val = row.get('value', '')
                        if key in limits:
                            try:
                                limits[key] = float(val)
                            except:
                                pass
            except:
                pass
        return limits

    def get_limit(self, key):
        """قراءة حد"""
        return self.limits.get(key, self.DEFAULT_LIMITS.get(key))

    def check_risk(self, player, bet_amount, game):
        """
        فحص المخاطر قبل بدء الجولة
        
        Returns:
            dict: {
                'allowed': bool — هل يُسمح باللعب؟
                'alerts': list — قائمة التنبيهات
                'actions': list — الإجراءات المطلوبة
            }
        """
        alerts = []
        actions = []
        allowed = True

        # 1. التحقق من التبريد
        cooldown = player.get('cooldown_until', '')
        if cooldown:
            try:
                cd_time = datetime.strptime(cooldown, '%Y-%m-%d %H:%M')
                if cd_time > datetime.now():
                    remaining = (cd_time - datetime.now()).seconds // 60
                    alerts.append({
                        'type': 'cooldown_active',
                        'severity': 'high',
                        'message': f'تبريد إجباري — متبقي {remaining} دقيقة'
                    })
                    actions.append('block_play')
                    allowed = False
            except:
                pass

        # 2. حد الخسارة اليومي
        daily_loss = float(player.get('daily_loss', 0) or 0)
        max_loss = self.get_limit('max_daily_loss_per_player')
        if daily_loss >= max_loss:
            alerts.append({
                'type': 'daily_loss_exceeded',
                'severity': 'high',
                'message': f'تجاوز حد الخسارة اليومي ({daily_loss:.0f}/{max_loss:.0f})'
            })
            actions.append('block_play')
            allowed = False

        # 3. حد الربح اليومي
        daily_win = float(player.get('daily_win', 0) or 0)
        max_win = self.get_limit('max_daily_win_per_player')
        if daily_win >= max_win:
            alerts.append({
                'type': 'daily_win_exceeded',
                'severity': 'high',
                'message': f'تجاوز حد الربح اليومي ({daily_win:.0f}/{max_win:.0f})'
            })
            actions.append('reduce_win_chance')

        # 4. كثرة المراهنات
        bets_hour = int(player.get('bets_last_hour', 0) or 0)
        max_bets = self.get_limit('max_bets_per_hour')
        if bets_hour >= max_bets:
            alerts.append({
                'type': 'rate_limit',
                'severity': 'medium',
                'message': f'كثرة مراهنات: {bets_hour}/{max_bets:.0f} في الساعة'
            })
            actions.append('enforce_cooldown')

        # 5. مراهنة كبيرة غير معتادة
        avg_bet = float(player.get('avg_bet', bet_amount) or bet_amount)
        if avg_bet > 0 and bet_amount > avg_bet * 5:
            alerts.append({
                'type': 'unusual_bet',
                'severity': 'high',
                'message': f'مراهنة كبيرة: {bet_amount} (avg: {avg_bet:.0f})'
            })
            actions.append('reduce_win_chance')

        # 6. رصيد منخفض
        balance = float(player.get('balance', 0) or 0)
        min_balance = self.get_limit('min_balance_to_play')
        if balance < bet_amount:
            alerts.append({
                'type': 'insufficient_balance',
                'severity': 'high',
                'message': f'رصيد غير كافٍ: {balance:.0f} < {bet_amount}'
            })
            actions.append('block_play')
            allowed = False

        # 7. خسارة كبيرة — تبريد تلقائي
        last_loss = float(player.get('last_loss_amount', 0) or 0)
        auto_cooldown = self.get_limit('auto_cooldown_after_loss')
        if last_loss >= auto_cooldown:
            alerts.append({
                'type': 'large_loss_cooldown',
                'severity': 'medium',
                'message': f'خسارة كبيرة ({last_loss:.0f}) → تبريد تلقائي'
            })
            actions.append('enforce_cooldown')

        return {
            'allowed': allowed,
            'alerts': alerts,
            'actions': actions,
        }

    def create_alert(self, alert_type, user_id, severity, message, auto_action=''):
        """إنشاء تنبيه مخاطر"""
        fieldnames = ['id', 'alert_type', 'user_id', 'severity',
                      'message', 'auto_action_taken', 'status', 'created_at']
        alert_id = f"ALT{str(int(datetime.now().timestamp()))[-8:]}"
        row = {
            'id': alert_id,
            'alert_type': alert_type,
            'user_id': str(user_id),
            'severity': severity,
            'message': message[:300],
            'auto_action_taken': auto_action,
            'status': 'active',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        try:
            file_exists = os.path.exists('risk_alerts.csv')
            with open('risk_alerts.csv', 'a', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row)
        except:
            pass
        return alert_id

    def get_active_alerts(self):
        """قراءة التنبيهات النشطة"""
        alerts = []
        try:
            if os.path.exists('risk_alerts.csv'):
                with open('risk_alerts.csv', 'r', encoding=CSV_ENCODING) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('status') == 'active':
                            alerts.append(row)
        except:
            pass
        return alerts

    def resolve_alert(self, alert_id):
        """حل تنبيه"""
        try:
            rows = []
            with open('risk_alerts.csv', 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row.get('id') == alert_id:
                        row['status'] = 'resolved'
                    rows.append(row)
            with open('risk_alerts.csv', 'w', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        except:
            pass

    def calculate_platform_edge(self, sessions_file='game_sessions.csv'):
        """حساب هامش ربح المنصة"""
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
            return self.get_limit('platform_target_edge')
        return 1 - (total_won / total_wagered)

    def check_platform_health(self):
        """فحص صحة المنصة العامة"""
        edge = self.calculate_platform_edge()
        target = self.get_limit('platform_target_edge')
        threshold = self.get_limit('alert_threshold_edge')

        health = {
            'edge': edge,
            'target': target,
            'status': 'healthy',
            'alerts': [],
        }

        if edge < threshold:
            health['status'] = 'critical'
            health['alerts'].append({
                'type': 'low_platform_edge',
                'severity': 'critical',
                'message': f'هامش المنصة منخفض: {edge:.1%} < {threshold:.1%}'
            })
        elif edge < target * 0.7:
            health['status'] = 'warning'
            health['alerts'].append({
                'type': 'edge_below_target',
                'severity': 'medium',
                'message': f'هامش المنصة تحت المستهدف: {edge:.1%} < {target:.1%}'
            })

        return health
