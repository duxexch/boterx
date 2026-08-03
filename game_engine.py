"""
VEX Games Platform — Game Engine v2
محرك الألعاب المحسّن — محفظة موحدة + خوارزمية مضاعفة + مضاعف ديناميكي
"""

import csv
import os
import json
import random
import uuid
import threading
from datetime import datetime, timedelta
from collections import defaultdict

CSV_ENCODING = 'utf-8-sig'
_wallet_lock = threading.Lock()

try:
    from house_algorithm import HouseAlgorithm
    from risk_manager import RiskManager
    from player_tracker import PlayerTracker
except ImportError:
    HouseAlgorithm = None
    RiskManager = None
    PlayerTracker = None


class GameManager:
    """محرك الألعاب v2 — محفظة موحدة من users.csv"""

    def __init__(self):
        self.catalog_file = 'games_catalog.csv'
        self.quick_deposits_file = 'quick_deposits.csv'
        self.player_payment_methods_file = 'player_payment_methods.csv'
        self._ensure_files()
        self.algorithm = HouseAlgorithm() if HouseAlgorithm else None
        self.risk = RiskManager() if RiskManager else None
        self.tracker = PlayerTracker() if PlayerTracker else None

    def _ensure_files(self):
        if not os.path.exists(self.catalog_file):
            fieldnames = ['id', 'name', 'icon', 'description', 'category',
                          'min_bet', 'max_bet', 'base_win_chance', 'house_edge_pct',
                          'rtp_target', 'volatility', 'max_payout_per_session',
                          'is_active', 'created_at']
            with open(self.catalog_file, 'w', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                games = [
                    {'id': 'GAME001', 'name': 'اختطف', 'icon': '🎁', 'description': 'اخطف الهدية قبل ما تختفي!', 'category': 'arcade',
                     'min_bet': '10', 'max_bet': '500', 'base_win_chance': '0.45', 'house_edge_pct': '15',
                     'rtp_target': '85', 'volatility': 'medium', 'max_payout_per_session': '2000', 'is_active': 'yes',
                     'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                    {'id': 'GAME002', 'name': 'النرد', 'icon': '🎲', 'description': 'خمن الرقم واربح 5 أضعاف!', 'category': 'dice',
                     'min_bet': '5', 'max_bet': '1000', 'base_win_chance': '0.40', 'house_edge_pct': '18',
                     'rtp_target': '82', 'volatility': 'high', 'max_payout_per_session': '5000', 'is_active': 'yes',
                     'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                    {'id': 'GAME003', 'name': 'سلوتس', 'icon': '🎰', 'description': 'لُف البكرات واربح الجائزة الكبرى!', 'category': 'slots',
                     'min_bet': '20', 'max_bet': '2000', 'base_win_chance': '0.35', 'house_edge_pct': '20',
                     'rtp_target': '80', 'volatility': 'high', 'max_payout_per_session': '10000', 'is_active': 'yes',
                     'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                    {'id': 'GAME004', 'name': 'Aviator', 'icon': '✈️', 'description': 'اسحب قبل ما تطير الطائرة!', 'category': 'crash',
                     'min_bet': '10', 'max_bet': '5000', 'base_win_chance': '0.40', 'house_edge_pct': '18',
                     'rtp_target': '82', 'volatility': 'high', 'max_payout_per_session': '50000', 'is_active': 'yes',
                     'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                ]
                for g in games:
                    writer.writerow({k: g.get(k, '') for k in fieldnames})

        if not os.path.exists(self.quick_deposits_file):
            fieldnames = ['id', 'user_id', 'amount', 'payment_method_id',
                          'account_number', 'status', 'approved_by', 'approved_at',
                          'game_session_id', 'created_at']
            with open(self.quick_deposits_file, 'w', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

        if not os.path.exists(self.player_payment_methods_file):
            fieldnames = ['id', 'user_id', 'method_name', 'account_number',
                          'method_type', 'icon', 'is_default', 'created_at']
            with open(self.player_payment_methods_file, 'w', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

        # ترحيل users.csv لإضافة game_balance
        self._migrate_users_csv()

    def _migrate_users_csv(self):
        """إضافة عمود game_balance إلى users.csv"""
        try:
            with open('users.csv', 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                if 'game_balance' in fieldnames:
                    return
                rows = list(reader)
            new_fields = list(fieldnames) + ['game_balance']
            for row in rows:
                if 'game_balance' not in row or not row.get('game_balance'):
                    row['game_balance'] = '0'
            with open('users.csv', 'w', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=new_fields)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in new_fields})
        except Exception as e:
            print(f"Migration error: {e}")

    # ===== المحفظة الموحدة (users.csv) =====

    def get_balance(self, user_id):
        """قراءة رصيد محفظة الألعاب من users.csv"""
        with _wallet_lock:
            try:
                with open('users.csv', 'r', encoding=CSV_ENCODING) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('telegram_id') == str(user_id):
                            return float(row.get('game_balance', 0) or 0)
            except:
                pass
            return 0.0

    def get_user_currency(self, user_id):
        """قراءة عملة المستخدم"""
        try:
            with open('users.csv', 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('telegram_id') == str(user_id):
                        return row.get('currency', 'SAR')
        except:
            pass
        return 'SAR'

    def add_balance(self, user_id, amount, reason='deposit'):
        """إضافة رصيد لـ game_balance في users.csv"""
        with _wallet_lock:
            try:
                with open('users.csv', 'r', encoding=CSV_ENCODING) as f:
                    reader = csv.DictReader(f)
                    fieldnames = reader.fieldnames
                    rows = list(reader)
                for row in rows:
                    if row.get('telegram_id') == str(user_id):
                        current = float(row.get('game_balance', 0) or 0)
                        row['game_balance'] = f"{current + float(amount):.2f}"
                        break
                with open('users.csv', 'w', newline='', encoding=CSV_ENCODING) as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in rows:
                        writer.writerow({k: row.get(k, '') for k in fieldnames})
                return self.get_balance(user_id)
            except Exception as e:
                print(f"add_balance error: {e}")
                return 0.0

    def deduct_balance(self, user_id, amount):
        """خصم رصيد من game_balance في users.csv"""
        with _wallet_lock:
            try:
                with open('users.csv', 'r', encoding=CSV_ENCODING) as f:
                    reader = csv.DictReader(f)
                    fieldnames = reader.fieldnames
                    rows = list(reader)
                for row in rows:
                    if row.get('telegram_id') == str(user_id):
                        current = float(row.get('game_balance', 0) or 0)
                        if current < float(amount):
                            return False, current
                        row['game_balance'] = f"{current - float(amount):.2f}"
                        break
                with open('users.csv', 'w', newline='', encoding=CSV_ENCODING) as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in rows:
                        writer.writerow({k: row.get(k, '') for k in fieldnames})
                return True, self.get_balance(user_id)
            except Exception as e:
                print(f"deduct_balance error: {e}")
                return False, 0.0

    # ===== الألعاب =====

    def get_games(self, active_only=True):
        games = []
        try:
            with open(self.catalog_file, 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if active_only and row.get('is_active') != 'yes':
                        continue
                    games.append(row)
        except:
            pass
        return games

    def get_game(self, game_id):
        for g in self.get_games(active_only=False):
            if g.get('id') == game_id:
                return g
        return None

    def add_game(self, name, icon, description, category, min_bet, max_bet,
                 base_win_chance, house_edge_pct, rtp_target=85, volatility='medium'):
        game_id = f"GAME{str(int(datetime.now().timestamp()))[-6:]}"
        fieldnames = ['id', 'name', 'icon', 'description', 'category',
                      'min_bet', 'max_bet', 'base_win_chance', 'house_edge_pct',
                      'rtp_target', 'volatility', 'max_payout_per_session',
                      'is_active', 'created_at']
        row = {
            'id': game_id, 'name': name, 'icon': icon, 'description': description,
            'category': category, 'min_bet': str(min_bet), 'max_bet': str(max_bet),
            'base_win_chance': str(base_win_chance), 'house_edge_pct': str(house_edge_pct),
            'rtp_target': str(rtp_target), 'volatility': volatility,
            'max_payout_per_session': str(float(max_bet) * 5),
            'is_active': 'yes', 'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }
        try:
            with open(self.catalog_file, 'a', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writerow(row)
        except:
            pass
        return game_id

    # ===== الجلسات =====

    def start_session(self, user_id, game_id, bet_amount):
        """بدء جلسة لعب — خصم + حساب الاحتمال"""
        player = self.tracker.get_profile(user_id)
        game = self.get_game(game_id)
        if not game:
            return {'success': False, 'error': 'اللعبة غير موجودة'}

        min_bet = float(game.get('min_bet', 10) or 10)
        max_bet = float(game.get('max_bet', 1000) or 1000)
        if bet_amount < min_bet:
            return {'success': False, 'error': f'الحد الأدنى للمراهنة: {min_bet}'}
        if bet_amount > max_bet:
            return {'success': False, 'error': f'الحد الأقصى للمراهنة: {max_bet}'}

        risk_check = self.risk.check_risk(player, bet_amount, game)
        if not risk_check['allowed']:
            risk_types = [a.get('type', '') for a in risk_check['alerts']]
            if 'insufficient_balance' in risk_types and 'cooldown_active' not in risk_types and 'daily_loss_exceeded' not in risk_types:
                balance = self.get_balance(user_id)
                return {'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance, 'required': bet_amount}
            alert_msg = risk_check['alerts'][0]['message'] if risk_check['alerts'] else 'محظور مؤقتاً'
            return {'success': False, 'error': alert_msg, 'alerts': risk_check['alerts']}

        balance = self.get_balance(user_id)
        if balance < bet_amount:
            return {'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance, 'required': bet_amount}

        algo_result = self.algorithm.calculate_win_chance(player, game, bet_amount)

        # خصم الرصيد من users.csv
        success, balance_after = self.deduct_balance(user_id, bet_amount)
        if not success:
            return {'success': False, 'error': 'فشل خصم الرصيد', 'need_deposit': True}

        session_id = f"SES{str(int(datetime.now().timestamp()))[-8:]}"
        self.algorithm.log_decision(
            session_id=session_id, user_id=user_id, game_id=game_id,
            base_chance=float(game.get('base_win_chance', 0.45)),
            adjusted_chance=algo_result['win_chance'],
            factors=algo_result['factors'],
            decision=algo_result['decision'],
            reason=algo_result['reason']
        )

        psych_hints = self.algorithm.apply_psychological_pattern(player, algo_result['decision'], game)

        for alert in risk_check['alerts']:
            if alert['severity'] in ('high', 'critical'):
                self.risk.create_alert(
                    alert_type=alert['type'], user_id=user_id,
                    severity=alert['severity'], message=alert['message'],
                    auto_action=','.join(risk_check['actions'])
                )

        return {
            'success': True,
            'session_id': session_id,
            'balance_before': balance,
            'balance_after': balance_after,
            'win_chance': algo_result['win_chance'],
            'decision': algo_result['decision'],
            'factors': algo_result['factors'],
            'psychological_hints': psych_hints,
            'alerts': risk_check['alerts'],
        }

    def end_session(self, session_id, user_id, game_id, bet_amount, result, payout=0):
        """إنهاء جلسة — إضافة المكسب للرصيد"""
        balance_before = self.get_balance(user_id)
        if result == 'win' and payout > 0:
            balance_after = self.add_balance(user_id, payout)
        else:
            balance_after = balance_before

        session_data = {
            'session_id': session_id, 'game_id': game_id, 'user_id': user_id,
            'bet_amount': bet_amount, 'payout': payout, 'result': result,
            'balance_before': balance_before, 'balance_after': balance_after,
            'multiplier': (payout / bet_amount) if bet_amount > 0 and payout > 0 else 0,
        }
        self.tracker.log_session(session_data)
        self.tracker.update_profile(user_id, {**session_data, 'balance_after': balance_after})

        return {
            'success': True, 'balance_before': balance_before,
            'balance_after': balance_after, 'result': result, 'payout': payout,
        }

    # ===== المضاعف الديناميكي =====

    def calculate_payout_multiplier(self, game, player):
        """حساب مضاعف الربح ديناميكياً — حسب اللعبة + شريحة اللاعب + حالة المنصة"""
        base_mult = 2.0
        try:
            base_mult = max(1.5, float(game.get('rtp_target', 85)) / 50)
        except:
            pass

        segment = self.tracker.get_segment(player) if self.tracker else 'regular'
        segment_mult = {
            'new': 1.2, 'loser': 1.3, 'regular': 1.0,
            'hot': 0.8, 'winner': 0.7, 'vip': 1.1, 'churning': 1.4,
        }.get(segment, 1.0)

        platform_edge = self.risk.calculate_platform_edge() if self.risk else 0.15
        if platform_edge < 0.05:
            edge_mult = 0.5
        elif platform_edge < 0.10:
            edge_mult = 0.8
        else:
            edge_mult = 1.0

        rand_mult = random.uniform(0.9, 1.15)
        multiplier = base_mult * segment_mult * edge_mult * rand_mult
        return max(1.2, min(10.0, multiplier))

    # ===== الإيداع السريع =====

    def create_quick_deposit(self, user_id, amount, payment_method_id, account_number):
        dep_id = f"DEP{str(int(datetime.now().timestamp()))[-8:]}"
        fieldnames = ['id', 'user_id', 'amount', 'payment_method_id',
                      'account_number', 'status', 'approved_by', 'approved_at',
                      'game_session_id', 'created_at']
        row = {
            'id': dep_id, 'user_id': str(user_id), 'amount': str(amount),
            'payment_method_id': payment_method_id, 'account_number': account_number,
            'status': 'pending', 'approved_by': '', 'approved_at': '',
            'game_session_id': '', 'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        try:
            with open(self.quick_deposits_file, 'a', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writerow(row)
        except:
            pass
        return dep_id

    def create_withdrawal(self, user_id, amount, payment_method_id, account_number):
        """إنشاء طلب سحب من محفظة الألعاب"""
        # خصم الرصيد فوراً (يُعاد لو رفض الأدمن)
        success, balance_after = self.deduct_balance(user_id, amount)
        if not success:
            return None, 'رصيد غير كافٍ'
        dep_id = f"WTH{str(int(datetime.now().timestamp()))[-8:]}"
        fieldnames = ['id', 'user_id', 'amount', 'payment_method_id',
                      'account_number', 'status', 'approved_by', 'approved_at',
                      'game_session_id', 'created_at']
        row = {
            'id': dep_id, 'user_id': str(user_id), 'amount': str(amount),
            'payment_method_id': payment_method_id, 'account_number': account_number,
            'status': 'pending_withdrawal', 'approved_by': '', 'approved_at': '',
            'game_session_id': '', 'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        try:
            with open(self.quick_deposits_file, 'a', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writerow(row)
        except:
            pass
        return dep_id, None

    def approve_deposit(self, dep_id, admin_id):
        rows = []
        approved = None
        try:
            with open(self.quick_deposits_file, 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row.get('id') == dep_id and row.get('status') == 'pending':
                        row['status'] = 'approved'
                        row['approved_by'] = str(admin_id)
                        row['approved_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        approved = row
                    rows.append(row)
            with open(self.quick_deposits_file, 'w', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        except:
            pass
        if approved:
            self.add_balance(approved['user_id'], float(approved['amount']))
        return approved

    def approve_withdrawal(self, dep_id, admin_id):
        """موافقة على سحب — الرصيد مخصوم بالفعل"""
        rows = []
        approved = None
        try:
            with open(self.quick_deposits_file, 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row.get('id') == dep_id and row.get('status') == 'pending_withdrawal':
                        row['status'] = 'withdrawal_approved'
                        row['approved_by'] = str(admin_id)
                        row['approved_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        approved = row
                    rows.append(row)
            with open(self.quick_deposits_file, 'w', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        except:
            pass
        return approved

    def reject_withdrawal(self, dep_id, admin_id):
        """رفض سحب — إعادة الرصيد"""
        rows = []
        rejected = None
        try:
            with open(self.quick_deposits_file, 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row.get('id') == dep_id and row.get('status') == 'pending_withdrawal':
                        row['status'] = 'withdrawal_rejected'
                        row['approved_by'] = str(admin_id)
                        row['approved_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        rejected = row
                    rows.append(row)
            with open(self.quick_deposits_file, 'w', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        except:
            pass
        if rejected:
            self.add_balance(rejected['user_id'], float(rejected['amount']))
        return rejected

    def reject_deposit(self, dep_id, admin_id):
        rows = []
        try:
            with open(self.quick_deposits_file, 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row.get('id') == dep_id and row.get('status') == 'pending':
                        row['status'] = 'rejected'
                        row['approved_by'] = str(admin_id)
                        row['approved_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    rows.append(row)
            with open(self.quick_deposits_file, 'w', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        except:
            pass

    def get_pending_deposits(self):
        deposits = []
        try:
            with open(self.quick_deposits_file, 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'pending':
                        deposits.append(row)
        except:
            pass
        return deposits

    def get_pending_withdrawals(self):
        """قراءة طلبات السحب المعلقة"""
        withdrawals = []
        try:
            with open(self.quick_deposits_file, 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'pending_withdrawal':
                        withdrawals.append(row)
        except:
            pass
        return withdrawals

    # ===== وسائل الدفع =====

    def add_payment_method(self, user_id, method_name, account_number, method_type, icon='💳'):
        method_id = f"PM{str(int(datetime.now().timestamp()))[-6:]}"
        fieldnames = ['id', 'user_id', 'method_name', 'account_number',
                      'method_type', 'icon', 'is_default', 'created_at']
        row = {
            'id': method_id, 'user_id': str(user_id), 'method_name': method_name,
            'account_number': account_number, 'method_type': method_type,
            'icon': icon, 'is_default': 'no', 'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }
        try:
            with open(self.player_payment_methods_file, 'a', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writerow(row)
        except:
            pass
        return method_id

    def get_payment_methods(self, user_id):
        methods = []
        try:
            with open(self.player_payment_methods_file, 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('user_id') == str(user_id):
                        methods.append(row)
        except:
            pass
        return methods

    # ===== إحصائيات =====

    def get_platform_stats(self):
        profiles = self.tracker.get_all_profiles() if self.tracker else []
        total_wagered = sum(float(p.get('total_wagered', 0) or 0) for p in profiles)
        total_won = sum(float(p.get('total_won', 0) or 0) for p in profiles)
        total_lost = sum(float(p.get('total_lost', 0) or 0) for p in profiles)
        active_players = len([p for p in profiles if int(p.get('total_games', 0) or 0) > 0])
        edge = self.risk.calculate_platform_edge() if self.risk else 0.15

        segments = defaultdict(int)
        for p in profiles:
            seg = self.tracker.get_segment(p) if self.tracker else 'regular'
            segments[seg] += 1

        return {
            'total_wagered': total_wagered,
            'total_won': total_won,
            'total_lost': total_lost,
            'net_profit': total_lost - total_won,
            'platform_edge': edge,
            'active_players': active_players,
            'segments': dict(segments),
            'pending_deposits': len(self.get_pending_deposits()),
            'pending_withdrawals': len(self.get_pending_withdrawals()),
            'active_alerts': len(self.risk.get_active_alerts()) if self.risk else 0,
        }
