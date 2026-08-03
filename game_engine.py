"""
VEX Games Platform — Game Engine
محرك الألعاب — يدير الجلسات والمحفظة والخوارزمية
"""

import csv
import os
import json
import random
import uuid
from datetime import datetime, timedelta
from collections import defaultdict

CSV_ENCODING = 'utf-8-sig'

# استيراد الوحدات
try:
    from house_algorithm import HouseAlgorithm
    from risk_manager import RiskManager
    from player_tracker import PlayerTracker
except ImportError:
    HouseAlgorithm = None
    RiskManager = None
    PlayerTracker = None


class GameManager:
    """محرك الألعاب — النقطة المركزية لإدارة كل الألعاب"""

    def __init__(self):
        self.catalog_file = 'games_catalog.csv'
        self.quick_deposits_file = 'quick_deposits.csv'
        self.player_payment_methods_file = 'player_payment_methods.csv'
        self._ensure_files()

        # تهيئة الوحدات
        self.algorithm = HouseAlgorithm() if HouseAlgorithm else None
        self.risk = RiskManager() if RiskManager else None
        self.tracker = PlayerTracker() if PlayerTracker else None

    def _ensure_files(self):
        """إنشاء ملفات CSV"""
        if not os.path.exists(self.catalog_file):
            fieldnames = ['id', 'name', 'icon', 'description', 'category',
                          'min_bet', 'max_bet', 'base_win_chance', 'house_edge_pct',
                          'rtp_target', 'volatility', 'max_payout_per_session',
                          'is_active', 'created_at']
            with open(self.catalog_file, 'w', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                # ألعاب افتراضية
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

    # ─── إدارة الألعاب ───

    def get_games(self, active_only=True):
        """قراءة قائمة الألعاب"""
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
        """قراءة لعبة واحدة"""
        for g in self.get_games(active_only=False):
            if g.get('id') == game_id:
                return g
        return None

    def add_game(self, name, icon, description, category, min_bet, max_bet,
                 base_win_chance, house_edge_pct, rtp_target=85, volatility='medium'):
        """إضافة لعبة جديدة"""
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

    # ─── إدارة الجلسات ───

    def start_session(self, user_id, game_id, bet_amount):
        """
        بدء جلسة لعب — النقطة المركزية
        
        Returns:
            dict: {
                'success': bool,
                'session_id': str,
                'balance_before': float,
                'balance_after': float,
                'win_chance': float,
                'decision': str (allow_win/force_lose/near_miss),
                'factors': dict,
                'psychological_hints': dict,
                'alerts': list,
                'error': str (إن فشل)
            }
        """
        # 1. قراءة ملف اللاعب
        player = self.tracker.get_profile(user_id)

        # 2. قراءة اللعبة
        game = self.get_game(game_id)
        if not game:
            return {'success': False, 'error': 'اللعبة غير موجودة'}

        # 3. التحقق من الحدود
        min_bet = float(game.get('min_bet', 10) or 10)
        max_bet = float(game.get('max_bet', 1000) or 1000)
        if bet_amount < min_bet:
            return {'success': False, 'error': f'الحد الأدنى للمراهنة: {min_bet}'}
        if bet_amount > max_bet:
            return {'success': False, 'error': f'الحد الأقصى للمراهنة: {max_bet}'}

        # 4. فحص المخاطر
        risk_check = self.risk.check_risk(player, bet_amount, game)
        if not risk_check['allowed']:
            return {
                'success': False,
                'error': 'محظور مؤقتاً',
                'alerts': risk_check['alerts'],
                'risk_actions': risk_check['actions']
            }

        # 5. التحقق من الرصيد
        balance = float(player.get('balance', 0) or 0)
        if balance < bet_amount:
            return {
                'success': False,
                'error': 'رصيد غير كافٍ',
                'need_deposit': True,
                'balance': balance,
                'required': bet_amount
            }

        # 6. حساب الاحتمال
        algo_result = self.algorithm.calculate_win_chance(player, game, bet_amount)

        # 7. خصم الرصيد فوراً
        balance_before = balance
        balance_after = balance - bet_amount

        # 8. تحديث رصيد اللاعب
        player['balance'] = f"{balance_after:.2f}"
        self.tracker._save_profile(player)

        # 9. تسجيل القرار
        session_id = f"SES{str(int(datetime.now().timestamp()))[-8:]}"
        self.algorithm.log_decision(
            session_id=session_id,
            user_id=user_id,
            game_id=game_id,
            base_chance=float(game.get('base_win_chance', 0.45)),
            adjusted_chance=algo_result['win_chance'],
            factors=algo_result['factors'],
            decision=algo_result['decision'],
            reason=algo_result['reason']
        )

        # 10. الأنماط النفسية
        psych_hints = self.algorithm.apply_psychological_pattern(
            player, algo_result['decision'], game
        )

        # 11. تسجيل التنبيهات إن وجدت
        for alert in risk_check['alerts']:
            if alert['severity'] in ('high', 'critical'):
                self.risk.create_alert(
                    alert_type=alert['type'],
                    user_id=user_id,
                    severity=alert['severity'],
                    message=alert['message'],
                    auto_action=','.join(risk_check['actions'])
                )

        return {
            'success': True,
            'session_id': session_id,
            'balance_before': balance_before,
            'balance_after': balance_after,
            'win_chance': algo_result['win_chance'],
            'decision': algo_result['decision'],
            'factors': algo_result['factors'],
            'psychological_hints': psych_hints,
            'alerts': risk_check['alerts'],
        }

    def end_session(self, session_id, user_id, game_id, bet_amount, result, payout=0):
        """إنهاء جلسة وتسجيل النتائج"""
        # قراءة الرصيد الحالي
        player = self.tracker.get_profile(user_id)
        balance_before = float(player.get('balance', 0) or 0)

        # إضافة المكسب للرصيد
        if result == 'win' and payout > 0:
            balance_after = balance_before + payout
        else:
            balance_after = balance_before  # الخصم تم في start_session

        # تسجيل الجلسة
        session_data = {
            'session_id': session_id,
            'game_id': game_id,
            'user_id': user_id,
            'bet_amount': bet_amount,
            'payout': payout,
            'result': result,
            'balance_before': balance_before,
            'balance_after': balance_after,
            'multiplier': (payout / bet_amount) if bet_amount > 0 and payout > 0 else 0,
        }
        self.tracker.log_session(session_data)

        # تحديث رصيد اللاعب
        player['balance'] = f"{balance_after:.2f}"
        self.tracker._save_profile(player)

        # تحديث ملف اللاعب
        self.tracker.update_profile(user_id, {
            **session_data,
            'balance_after': balance_after,
        })

        return {
            'success': True,
            'balance_before': balance_before,
            'balance_after': balance_after,
            'result': result,
            'payout': payout,
        }

    # ─── المحفظة ───

    def get_balance(self, user_id):
        """قراءة رصيد اللاعب"""
        player = self.tracker.get_profile(user_id)
        return float(player.get('balance', 0) or 0)

    def add_balance(self, user_id, amount, reason='deposit'):
        """إضافة رصيد للمحفظة"""
        player = self.tracker.get_profile(user_id)
        current = float(player.get('balance', 0) or 0)
        new_balance = current + float(amount)
        player['balance'] = f"{new_balance:.2f}"
        self.tracker._save_profile(player)
        return new_balance

    def deduct_balance(self, user_id, amount):
        """خصم رصيد من المحفظة"""
        player = self.tracker.get_profile(user_id)
        current = float(player.get('balance', 0) or 0)
        if current < float(amount):
            return False, current
        new_balance = current - float(amount)
        player['balance'] = f"{new_balance:.2f}"
        self.tracker._save_profile(player)
        return True, new_balance

    # ─── الإيداع السريع ───

    def create_quick_deposit(self, user_id, amount, payment_method_id, account_number):
        """إنشاء طلب إيداع سريع"""
        dep_id = f"DEP{str(int(datetime.now().timestamp()))[-8:]}"
        fieldnames = ['id', 'user_id', 'amount', 'payment_method_id',
                      'account_number', 'status', 'approved_by', 'approved_at',
                      'game_session_id', 'created_at']
        row = {
            'id': dep_id,
            'user_id': str(user_id),
            'amount': str(amount),
            'payment_method_id': payment_method_id,
            'account_number': account_number,
            'status': 'pending',
            'approved_by': '',
            'approved_at': '',
            'game_session_id': '',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        try:
            with open(self.quick_deposits_file, 'a', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writerow(row)
        except:
            pass
        return dep_id

    def approve_deposit(self, dep_id, admin_id):
        """موافقة على إيداع سريع"""
        rows = []
        approved_deposit = None
        try:
            with open(self.quick_deposits_file, 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row.get('id') == dep_id and row.get('status') == 'pending':
                        row['status'] = 'approved'
                        row['approved_by'] = str(admin_id)
                        row['approved_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        approved_deposit = row
                    rows.append(row)
            with open(self.quick_deposits_file, 'w', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        except:
            pass

        if approved_deposit:
            self.add_balance(approved_deposit['user_id'], float(approved_deposit['amount']))

        return approved_deposit

    def reject_deposit(self, dep_id, admin_id):
        """رفض إيداع سريع"""
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
        """قراءة طلبات الإيداع المعلقة"""
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

    # ─── وسائل دفع اللاعب ───

    def add_payment_method(self, user_id, method_name, account_number, method_type, icon='💳'):
        """إضافة وسيلة دفع للاعب"""
        method_id = f"PM{str(int(datetime.now().timestamp()))[-6:]}"
        fieldnames = ['id', 'user_id', 'method_name', 'account_number',
                      'method_type', 'icon', 'is_default', 'created_at']
        row = {
            'id': method_id,
            'user_id': str(user_id),
            'method_name': method_name,
            'account_number': account_number,
            'method_type': method_type,
            'icon': icon,
            'is_default': 'no',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }
        try:
            with open(self.player_payment_methods_file, 'a', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writerow(row)
        except:
            pass
        return method_id

    def get_payment_methods(self, user_id):
        """قراءة وسائل دفع اللاعب"""
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

    # ─── إحصائيات ───

    def get_platform_stats(self):
        """إحصائيات المنصة"""
        profiles = self.tracker.get_all_profiles()
        total_wagered = sum(float(p.get('total_wagered', 0) or 0) for p in profiles)
        total_won = sum(float(p.get('total_won', 0) or 0) for p in profiles)
        total_lost = sum(float(p.get('total_lost', 0) or 0) for p in profiles)
        active_players = len([p for p in profiles if int(p.get('total_games', 0) or 0) > 0])
        edge = self.risk.calculate_platform_edge()

        segments = defaultdict(int)
        for p in profiles:
            seg = self.tracker.get_segment(p)
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
            'active_alerts': len(self.risk.get_active_alerts()),
        }
