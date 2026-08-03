"""
VEX Games Platform — Player Tracker
تتبع وتحليل سلوك اللاعبين — يتعلم ويتكيف
"""

import csv
import os
import json
from datetime import datetime, timedelta

CSV_ENCODING = 'utf-8-sig'


class PlayerTracker:
    """تتبع وتحليل سلوك اللاعبين"""

    def __init__(self):
        self.profiles_file = 'player_profiles.csv'
        self.sessions_file = 'game_sessions.csv'
        self._ensure_files()

    def _ensure_files(self):
        """إنشاء ملفات CSV إن لم تكن موجودة"""
        if not os.path.exists(self.profiles_file):
            fieldnames = [
                'user_id', 'telegram_id', 'name',
                'total_games', 'total_sessions',
                'total_wagered', 'total_won', 'total_lost',
                'net_position', 'win_rate',
                'avg_bet', 'max_bet', 'min_bet',
                'favorite_game', 'favorite_bet_amount',
                'risk_score', 'heat_level',
                'is_vex_partner', 'vex_partner_since',
                'last_played', 'first_play_date',
                'session_streak', 'cooldown_until',
                'lifetime_value', 'churn_risk',
                'consecutive_wins', 'consecutive_losses',
                'daily_win', 'daily_loss', 'last_loss_amount',
                'bets_last_hour', 'balance',
                'created_at', 'updated_at'
            ]
            with open(self.profiles_file, 'w', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

        if not os.path.exists(self.sessions_file):
            fieldnames = [
                'id', 'session_id', 'game_id', 'user_id',
                'bet_amount', 'multiplier', 'payout',
                'result', 'balance_before', 'balance_after',
                'win_chance_at_play', 'algorithm_factors',
                'timestamp', 'duration_seconds'
            ]
            with open(self.sessions_file, 'w', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

    def get_profile(self, user_id):
        """قراءة ملف لاعب — ينشئ إن لم يكن موجوداً"""
        tid = str(user_id)
        try:
            with open(self.profiles_file, 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('telegram_id') == tid or row.get('user_id') == tid:
                        return row
        except:
            pass
        # إنشاء ملف جديد
        profile = self._create_profile(tid)
        return profile

    def _create_profile(self, tid):
        """إنشاء ملف لاعب جديد"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        profile = {
            'user_id': tid,
            'telegram_id': tid,
            'name': '',
            'total_games': '0',
            'total_sessions': '0',
            'total_wagered': '0',
            'total_won': '0',
            'total_lost': '0',
            'net_position': '0',
            'win_rate': '0',
            'avg_bet': '0',
            'max_bet': '0',
            'min_bet': '0',
            'favorite_game': '',
            'favorite_bet_amount': '0',
            'risk_score': '0',
            'heat_level': '0',
            'is_vex_partner': 'no',
            'vex_partner_since': '',
            'last_played': now,
            'first_play_date': now,
            'session_streak': '0',
            'cooldown_until': '',
            'lifetime_value': '0',
            'churn_risk': '0',
            'consecutive_wins': '0',
            'consecutive_losses': '0',
            'daily_win': '0',
            'daily_loss': '0',
            'last_loss_amount': '0',
            'bets_last_hour': '0',
            'balance': '0',
            'created_at': now,
            'updated_at': now,
        }
        self._save_profile(profile)
        return profile

    def _save_profile(self, profile):
        """حفظ/تحديث ملف لاعب"""
        tid = profile.get('telegram_id', profile.get('user_id', ''))
        rows = []
        fieldnames = [
            'user_id', 'telegram_id', 'name',
            'total_games', 'total_sessions',
            'total_wagered', 'total_won', 'total_lost',
            'net_position', 'win_rate',
            'avg_bet', 'max_bet', 'min_bet',
            'favorite_game', 'favorite_bet_amount',
            'risk_score', 'heat_level',
            'is_vex_partner', 'vex_partner_since',
            'last_played', 'first_play_date',
            'session_streak', 'cooldown_until',
            'lifetime_value', 'churn_risk',
            'consecutive_wins', 'consecutive_losses',
            'daily_win', 'daily_loss', 'last_loss_amount',
            'bets_last_hour', 'balance',
            'created_at', 'updated_at'
        ]

        try:
            if os.path.exists(self.profiles_file):
                with open(self.profiles_file, 'r', encoding=CSV_ENCODING) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('telegram_id') == tid:
                            rows.append(profile)
                        else:
                            rows.append(row)
            else:
                rows.append(profile)
        except:
            rows.append(profile)

        # إذا اللاعب غير موجود، أضفه
        if not any(r.get('telegram_id') == tid for r in rows):
            rows.append(profile)

        with open(self.profiles_file, 'w', newline='', encoding=CSV_ENCODING) as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, '') for k in fieldnames})

    def update_profile(self, user_id, session_data):
        """تحديث ملف اللاعب بعد كل جلسة"""
        profile = self.get_profile(user_id)

        bet = float(session_data.get('bet_amount', 0) or 0)
        payout = float(session_data.get('payout', 0) or 0)
        result = session_data.get('result', 'lose')
        game_id = session_data.get('game_id', '')
        balance_after = float(session_data.get('balance_after', 0) or 0)
        now = datetime.now()

        # تحديث الإحصائيات
        total_games = int(profile.get('total_games', 0) or 0) + 1
        total_wagered = float(profile.get('total_wagered', 0) or 0) + bet
        total_won = float(profile.get('total_won', 0) or 0) + (payout if result == 'win' else 0)
        total_lost = float(profile.get('total_lost', 0) or 0) + (bet if result == 'lose' else 0)
        net_position = total_won - total_lost
        win_rate = (total_won / total_wagered * 100) if total_wagered > 0 else 0

        # تحديث المراهنات
        avg_bet = total_wagered / total_games if total_games > 0 else bet
        max_bet = max(float(profile.get('max_bet', 0) or 0), bet)
        min_bet = min(float(profile.get('min_bet', 999999) or 999999), bet) if total_games == 1 else float(profile.get('min_bet', bet) or bet)

        # تحديث المتتاليات
        consec_wins = int(profile.get('consecutive_wins', 0) or 0)
        consec_losses = int(profile.get('consecutive_losses', 0) or 0)
        if result == 'win':
            consec_wins += 1
            consec_losses = 0
            daily_win = float(profile.get('daily_win', 0) or 0) + (payout - bet)
            daily_loss = float(profile.get('daily_loss', 0) or 0)
            last_loss = 0
        else:
            consec_losses += 1
            consec_wins = 0
            daily_loss = float(profile.get('daily_loss', 0) or 0) + bet
            daily_win = float(profile.get('daily_win', 0) or 0)
            last_loss = bet

        # الحرارة
        heat = self._calculate_heat(user_id)

        # LTV
        ltv = total_wagered * 0.15

        # خطر المغادرة
        churn = self._predict_churn(profile, now)

        # المباراة المفضلة
        fav_game = profile.get('favorite_game', '')
        if not fav_game:
            fav_game = game_id

        # مستوى الخطر
        risk_score = int(profile.get('risk_score', 0) or 0)
        if bet > avg_bet * 2:
            risk_score = min(100, risk_score + 5)

        # إعادة ضبط يومي
        last_played_str = profile.get('last_played', '')
        if last_played_str:
            try:
                last_played = datetime.strptime(last_played_str[:16], '%Y-%m-%d %H:%M')
                if last_played.date() != now.date():
                    daily_win = 0
                    daily_loss = 0
            except:
                pass

        updated = dict(profile)
        updated.update({
            'total_games': str(total_games),
            'total_wagered': f"{total_wagered:.2f}",
            'total_won': f"{total_won:.2f}",
            'total_lost': f"{total_lost:.2f}",
            'net_position': f"{net_position:.2f}",
            'win_rate': f"{win_rate:.1f}",
            'avg_bet': f"{avg_bet:.2f}",
            'max_bet': f"{max_bet:.2f}",
            'min_bet': f"{min_bet:.2f}",
            'favorite_game': fav_game,
            'risk_score': str(risk_score),
            'heat_level': f"{heat:.1f}",
            'last_played': now.strftime('%Y-%m-%d %H:%M'),
            'session_streak': str(int(profile.get('session_streak', 0) or 0) + 1),
            'lifetime_value': f"{ltv:.2f}",
            'churn_risk': f"{churn}",
            'consecutive_wins': str(consec_wins),
            'consecutive_losses': str(consec_losses),
            'daily_win': f"{daily_win:.2f}",
            'daily_loss': f"{daily_loss:.2f}",
            'last_loss_amount': f"{last_loss:.2f}",
            'bets_last_hour': str(self._count_bets_last_hour(user_id)),
            'balance': f"{balance_after:.2f}",
            'updated_at': now.strftime('%Y-%m-%d %H:%M'),
        })

        self._save_profile(updated)
        return updated

    def _calculate_heat(self, user_id):
        """حساب مستوى حرارة اللاعب (0-10)"""
        recent = self._get_recent_sessions(user_id, minutes=30)
        if not recent:
            return 0
        count = len(recent)
        heat = min(10, count / 3)
        avg_bet = sum(float(s.get('bet_amount', 0) or 0) for s in recent) / count
        if avg_bet > 100:
            heat = min(10, heat * 1.5)
        return heat

    def _count_bets_last_hour(self, user_id):
        """عد المراهنات في آخر ساعة"""
        recent = self._get_recent_sessions(user_id, minutes=60)
        return len(recent)

    def _get_recent_sessions(self, user_id, minutes=30):
        """قراءة آخر جلسات اللاعب"""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        sessions = []
        try:
            if os.path.exists(self.sessions_file):
                with open(self.sessions_file, 'r', encoding=CSV_ENCODING) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('user_id') != str(user_id):
                            continue
                        ts = row.get('timestamp', '')
                        try:
                            session_time = datetime.strptime(ts[:19], '%Y-%m-%d %H:%M:%S')
                            if session_time > cutoff:
                                sessions.append(row)
                        except:
                            pass
        except:
            pass
        return sessions

    def _predict_churn(self, profile, now=None):
        """توقع احتمال مغادرة اللاعب"""
        if now is None:
            now = datetime.now()
        risk = 0

        last_played_str = profile.get('last_played', '')
        if last_played_str:
            try:
                last = datetime.strptime(last_played_str[:16], '%Y-%m-%d %H:%M')
                days = (now - last).days
                if days > 7:
                    risk += 30
                elif days > 3:
                    risk += 15
            except:
                pass

        consec_losses = int(profile.get('consecutive_losses', 0) or 0)
        if consec_losses > 5:
            risk += 25

        balance = float(profile.get('balance', 0) or 0)
        if balance < 50:
            risk += 20

        net = float(profile.get('net_position', 0) or 0)
        if net < -2000:
            risk += 25

        return min(100, risk)

    def get_segment(self, profile):
        """تصنيف اللاعب إلى شريحة"""
        total_games = int(profile.get('total_games', 0) or 0)
        net = float(profile.get('net_position', 0) or 0)
        heat = float(profile.get('heat_level', 0) or 0)
        churn = int(profile.get('churn_risk', 0) or 0)
        ltv = float(profile.get('lifetime_value', 0) or 0)

        if total_games < 10:
            return 'new'
        elif net > 1000:
            return 'winner'
        elif net < -1000:
            return 'loser'
        elif heat > 7:
            return 'hot'
        elif churn > 60:
            return 'churning'
        elif ltv > 5000:
            return 'vip'
        else:
            return 'regular'

    def set_vex_partner(self, user_id, is_partner=True):
        """تعيين لاعب كشريك VEX"""
        profile = self.get_profile(user_id)
        profile['is_vex_partner'] = 'yes' if is_partner else 'no'
        if is_partner:
            profile['vex_partner_since'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        else:
            profile['vex_partner_since'] = ''
        self._save_profile(profile)
        return profile

    def set_cooldown(self, user_id, minutes=15):
        """ضبط تبريد إجباري"""
        profile = self.get_profile(user_id)
        cd = datetime.now() + timedelta(minutes=minutes)
        profile['cooldown_until'] = cd.strftime('%Y-%m-%d %H:%M')
        self._save_profile(profile)

    def log_session(self, session_data):
        """تسجيل جلسة في game_sessions.csv"""
        fieldnames = [
            'id', 'session_id', 'game_id', 'user_id',
            'bet_amount', 'multiplier', 'payout',
            'result', 'balance_before', 'balance_after',
            'win_chance_at_play', 'algorithm_factors',
            'timestamp', 'duration_seconds'
        ]
        session_id = f"SES{str(int(datetime.now().timestamp()))[-8:]}"
        row = {
            'id': f"ROW{str(int(datetime.now().timestamp()))[-6:]}",
            'session_id': session_data.get('session_id', session_id),
            'game_id': session_data.get('game_id', ''),
            'user_id': str(session_data.get('user_id', '')),
            'bet_amount': str(session_data.get('bet_amount', 0)),
            'multiplier': str(session_data.get('multiplier', 0)),
            'payout': str(session_data.get('payout', 0)),
            'result': session_data.get('result', 'lose'),
            'balance_before': str(session_data.get('balance_before', 0)),
            'balance_after': str(session_data.get('balance_after', 0)),
            'win_chance_at_play': str(session_data.get('win_chance', 0)),
            'algorithm_factors': json.dumps(session_data.get('factors', {})),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'duration_seconds': str(session_data.get('duration', 0)),
        }
        try:
            file_exists = os.path.exists(self.sessions_file)
            with open(self.sessions_file, 'a', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row)
        except Exception as e:
            print(f"Error logging session: {e}")

        return session_id

    def get_all_profiles(self):
        """قراءة كل ملفات اللاعبين"""
        profiles = []
        try:
            if os.path.exists(self.profiles_file):
                with open(self.profiles_file, 'r', encoding=CSV_ENCODING) as f:
                    reader = csv.DictReader(f)
                    profiles = list(reader)
        except:
            pass
        return profiles

    def get_top_players(self, limit=10, sort_by='total_wagered'):
        """أعلى اللاعبين حسب المعيار"""
        profiles = self.get_all_profiles()
        try:
            profiles.sort(key=lambda p: float(p.get(sort_by, 0) or 0), reverse=True)
        except:
            pass
        return profiles[:limit]
