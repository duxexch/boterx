"""
VEX Games Platform — Game Engine v2
محرك الألعاب المحسّن — محفظة موحدة + خوارزمية مضاعفة + مضاعف ديناميكي
Uses SQLite for balance storage (eliminates CSV corruption risk)
"""

import csv
import os
import json
import random
import uuid
import threading
import time
from datetime import datetime, timedelta
from collections import defaultdict

CSV_ENCODING = 'utf-8-sig'
_wallet_lock = threading.RLock()

# ===== SQLite Database (replaces CSV balance cache) =====
try:
    from db_manager import _gdb as _db
    _USE_SQLITE = True
    print("✅ Game Engine: Using SQLite for balance operations")
except ImportError:
    _USE_SQLITE = False
    _db = None
    print("⚠️ Game Engine: SQLite not available, falling back to CSV cache")

# ===== Fallback: In-Memory Balance Cache (only if SQLite unavailable) =====
_balance_cache = {}
_cache_loaded = False
_cache_lock = threading.Lock()

def _load_balance_cache():
    """تحميل كل الأرصدة من users.csv إلى الذاكرة (fallback only)"""
    global _cache_loaded, _balance_cache
    if _USE_SQLITE:
        return
    with _cache_lock:
        if _cache_loaded:
            return
        try:
            with open('users.csv', 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    tid = row.get('telegram_id', '')
                    if tid:
                        _balance_cache[tid] = {
                            'balance': float(row.get('game_balance', 0) or 0),
                            'currency': row.get('currency', 'EGP'),
                            'dirty': False
                        }
            _cache_loaded = True
            print(f"✅ Balance cache loaded: {len(_balance_cache)} users")
        except Exception as e:
            print(f"Balance cache load error: {e}")
            _cache_loaded = True

def _flush_balance_to_csv(user_id):
    """كتابة رصيد مستخدم واحد فقط — fallback only"""
    global _balance_cache
    try:
        rows = []
        fieldnames = None
        with open('users.csv', 'r', encoding=CSV_ENCODING) as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)
        for row in rows:
            if row.get('telegram_id') == str(user_id):
                cached = _balance_cache.get(str(user_id))
                if cached:
                    row['game_balance'] = f"{cached['balance']:.2f}"
                break
        import tempfile
        fd, tmp_path = tempfile.mkstemp(dir='.', suffix='.tmp')
        with os.fdopen(fd, 'w', newline='', encoding=CSV_ENCODING) as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, '') for k in fieldnames})
        os.replace(tmp_path, 'users.csv')
        if str(user_id) in _balance_cache:
            _balance_cache[str(user_id)]['dirty'] = False
    except Exception as e:
        print(f"Flush balance error for {user_id}: {e}")

_flush_stop = False
def _background_flush_loop():
    """يكتب الأرصدة المتغيرة إلى CSV كل 5 ثواني — fallback only"""
    global _balance_cache
    if _USE_SQLITE:
        # SQLite sync: periodically sync balances back to CSV for bot compatibility
        while not _flush_stop:
            time.sleep(30)
            try:
                _db.sync_to_csv()
            except:
                pass
        return
    while not _flush_stop:
        time.sleep(5)
        dirty_uids = []
        with _cache_lock:
            for uid, info in _balance_cache.items():
                if info.get('dirty'):
                    dirty_uids.append(uid)
                    info['dirty'] = False
        if dirty_uids:
            with _wallet_lock:
                for uid in dirty_uids[:50]:
                    try:
                        _flush_balance_to_csv(uid)
                    except:
                        pass

import atexit
atexit.register(lambda: globals().update(_flush_stop=True))

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
        self.sessions_file = 'game_sessions.csv'
        self._ensure_files()
        self.algorithm = HouseAlgorithm() if HouseAlgorithm else None
        # Start background flush thread
        _load_balance_cache()
        t = threading.Thread(target=_background_flush_loop, daemon=True)
        t.start()
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
                    {'id': 'GAME002', 'name': 'النرد القديم', 'icon': '🎲', 'description': 'خمن الرقم واربح 5 أضعاف!', 'category': 'dice',
                     'min_bet': '5', 'max_bet': '1000', 'base_win_chance': '0.40', 'house_edge_pct': '18',
                     'rtp_target': '82', 'volatility': 'high', 'max_payout_per_session': '5000', 'is_active': 'no',
                     'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                    {'id': 'GAME003', 'name': 'سلوتس', 'icon': '🎰', 'description': 'لُف البكرات واربح الجائزة الكبرى!', 'category': 'slots',
                     'min_bet': '20', 'max_bet': '2000', 'base_win_chance': '0.35', 'house_edge_pct': '20',
                     'rtp_target': '80', 'volatility': 'high', 'max_payout_per_session': '10000', 'is_active': 'yes',
                     'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                    {'id': 'GAME004', 'name': 'Aviator', 'icon': '✈️', 'description': 'اسحب قبل ما تطير الطائرة!', 'category': 'crash',
                     'min_bet': '10', 'max_bet': '5000', 'base_win_chance': '0.40', 'house_edge_pct': '18',
                     'rtp_target': '82', 'volatility': 'high', 'max_payout_per_session': '50000', 'is_active': 'yes',
                     'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                    {'id': 'GAME005', 'name': 'Crash', 'icon': '🚀', 'description': 'الصاروخ يرتفع — اسحب قبل الانفجار!', 'category': 'crash',
                     'min_bet': '10', 'max_bet': '5000', 'base_win_chance': '0.42', 'house_edge_pct': '17',
                     'rtp_target': '83', 'volatility': 'high', 'max_payout_per_session': '50000', 'is_active': 'yes',
                     'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                    {'id': 'GAME006', 'name': 'Mines', 'icon': '💣', 'description': 'اكشف المربعات وتجنب الألغام!', 'category': 'arcade',
                     'min_bet': '10', 'max_bet': '2000', 'base_win_chance': '0.45', 'house_edge_pct': '15',
                     'rtp_target': '85', 'volatility': 'medium', 'max_payout_per_session': '10000', 'is_active': 'yes',
                     'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                    {'id': 'GAME007', 'name': 'Plinko', 'icon': '🔮', 'description': 'أفقط الكرة في الفتحة الذهبية!', 'category': 'arcade',
                     'min_bet': '10', 'max_bet': '2000', 'base_win_chance': '0.40', 'house_edge_pct': '16',
                     'rtp_target': '84', 'volatility': 'medium', 'max_payout_per_session': '8000', 'is_active': 'yes',
                     'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                    {'id': 'GAME008', 'name': 'اليانصيب', 'icon': '🎟️', 'description': 'اشترِ تذكرة واربح الجائزة الكبرى!', 'category': 'lottery',
                     'min_bet': '5', 'max_bet': '500', 'base_win_chance': '0.15', 'house_edge_pct': '25',
                     'rtp_target': '75', 'volatility': 'high', 'max_payout_per_session': '50000', 'is_active': 'yes',
                     'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                    {'id': 'GAME009', 'name': 'عجلة الحظ', 'icon': '🎡', 'description': 'أدر العجلة واربح جوائز نقدية!', 'category': 'wheel',
                     'min_bet': '10', 'max_bet': '1000', 'base_win_chance': '0.40', 'house_edge_pct': '15',
                     'rtp_target': '85', 'volatility': 'medium', 'max_payout_per_session': '5000', 'is_active': 'yes',
                     'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')},
                    {'id': 'GAME010', 'name': 'نرد', 'icon': '🎲', 'description': 'اسحب النرد وتوقع الرقم!', 'category': 'dice',
                     'min_bet': '10', 'max_bet': '5000', 'base_win_chance': '0.16', 'house_edge_pct': '15',
                     'rtp_target': '85', 'volatility': 'high', 'max_payout_per_session': '50000', 'is_active': 'yes',
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
        # ترحيل payment_methods.csv لإضافة available_for_games
        self._migrate_payment_methods_for_games()

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

    def _migrate_payment_methods_for_games(self):
        """إضافة عمود available_for_games إلى payment_methods.csv"""
        try:
            with open('payment_methods.csv', 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                if 'available_for_games' in fieldnames:
                    return
                rows = list(reader)
            new_fields = list(fieldnames) + ['available_for_games']
            for row in rows:
                row['available_for_games'] = 'yes'
            with open('payment_methods.csv', 'w', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=new_fields)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in new_fields})
        except Exception as e:
            print(f"Payment methods migration error: {e}")

    def get_games_payment_methods(self, user_currency=None):
        """قراءة وسائل الدفع النشطة والمتاحة للألعاب — مفلترة حسب العملة.
        إذا لم توجد نتائج بعد الفلترة، أرجع كل الوسائل النشطة."""
        methods = []
        all_active = []
        try:
            with open('payment_methods.csv', 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'active':
                        all_active.append(row)
                        avail = row.get('available_for_games', 'yes')
                        if avail != 'yes':
                            continue
                        method_currency = row.get('currency', '').strip()
                        if not method_currency or method_currency == 'كل العملات' or not user_currency:
                            methods.append(row)
                        elif method_currency == user_currency:
                            methods.append(row)
        except:
            pass
        # Fallback: if filtered list is empty, return all active methods
        if not methods and all_active:
            return all_active
        return methods

    def get_user_info(self, user_id):
        """قراءة بيانات المستخدم — SQLite"""
        if _USE_SQLITE:
            return _db.get_user_row(user_id)
        # Fallback: CSV cache
        _load_balance_cache()
        uid = str(user_id)
        with _cache_lock:
            if uid in _balance_cache:
                pass
        try:
            with open('users.csv', 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('telegram_id') == uid:
                        with _cache_lock:
                            if uid in _balance_cache:
                                row['game_balance'] = f"{_balance_cache[uid]['balance']:.2f}"
                                row['currency'] = _balance_cache[uid]['currency']
                            return row
        except:
            pass
        return {}

    def get_balance(self, user_id):
        """قراءة رصيد محفظة الألعاب — SQLite (فوري)"""
        if _USE_SQLITE:
            return _db.get_balance(user_id)
        # Fallback: CSV cache
        _load_balance_cache()
        uid = str(user_id)
        with _cache_lock:
            if uid in _balance_cache:
                return _balance_cache[uid]['balance']
        try:
            with open('users.csv', 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('telegram_id') == uid:
                        bal = float(row.get('game_balance', 0) or 0)
                        cur = row.get('currency', 'EGP')
                        with _cache_lock:
                            _balance_cache[uid] = {'balance': bal, 'currency': cur, 'dirty': False}
                        return bal
        except:
            pass
        return 0.0

    def get_user_currency(self, user_id):
        """قراءة عملة المستخدم"""
        if _USE_SQLITE:
            return _db.get_user_currency(user_id)
        _load_balance_cache()
        uid = str(user_id)
        with _cache_lock:
            if uid in _balance_cache:
                return _balance_cache[uid]['currency']
        try:
            with open('users.csv', 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('telegram_id') == uid:
                        return row.get('currency', 'EGP')
        except:
            pass
        return 'EGP'

    def add_balance(self, user_id, amount, reason='deposit', idempotency_key=None):
        """إضافة رصيد — SQLite (atomic transaction)"""
        if _USE_SQLITE:
            return _db.add_balance(user_id, amount, idempotency_key=idempotency_key)
        # Fallback: CSV cache
        _load_balance_cache()
        uid = str(user_id)
        amt = float(amount)
        with _cache_lock:
            if uid not in _balance_cache:
                _balance_cache[uid] = {'balance': 0.0, 'currency': 'EGP', 'dirty': False}
            _balance_cache[uid]['balance'] += amt
            _balance_cache[uid]['dirty'] = True
            return _balance_cache[uid]['balance']

    def deduct_balance(self, user_id, amount):
        """خصم رصيد — SQLite (atomic transaction)"""
        if _USE_SQLITE:
            return _db.deduct_balance(user_id, amount)
        # Fallback: CSV cache
        _load_balance_cache()
        uid = str(user_id)
        amt = float(amount)
        with _cache_lock:
            if uid not in _balance_cache:
                _balance_cache[uid] = {'balance': 0.0, 'currency': 'EGP', 'dirty': False}
            current = _balance_cache[uid]['balance']
            if current < amt:
                return False, current
            _balance_cache[uid]['balance'] -= amt
            _balance_cache[uid]['dirty'] = True
            return True, _balance_cache[uid]['balance']

    # ===== ACID Round Settlement (Constitution §2.3) =====
    def settle_round(self, user_id, bet_amount, payout):
        """تسوية جولة كاملة في معاملة ACID واحدة.

        يجمع خصم الرهان + صافي النتيجة في تحديث ذری واحد.
        يمنع فقدان المال لو انهار السيرفر بين العمليتين.
        يتبع الدستور: Wallet ACID — لا تحديث متسلسل.

        bet_amount: المبلغ المراهن (مُتحقق منه server-side).
        payout: إجمالي المكسب (0 عند الخسارة).
        net_delta = payout - bet_amount.

        Returns (success, final_balance).
        """
        if _USE_SQLITE:
            return _db.round_settle(user_id, bet_amount, payout)
        # Fallback: CSV cache (best-effort sequential)
        _load_balance_cache()
        uid = str(user_id)
        bet = float(bet_amount)
        win = float(payout)
        net = win - bet
        with _cache_lock:
            if uid not in _balance_cache:
                _balance_cache[uid] = {'balance': 0.0, 'currency': 'EGP', 'dirty': False}
            current = _balance_cache[uid]['balance']
            if net < 0 and current < abs(net):
                return False, current
            _balance_cache[uid]['balance'] += net
            _balance_cache[uid]['dirty'] = True
            return True, _balance_cache[uid]['balance']

    def settle_with_idempotency(self, user_id, bet_amount, payout, request_id, response_template):
        """Atomic: settle + store idempotency record in ONE SQLite transaction.

        response_template: dict of game-specific fields WITHOUT balance_after.
        balance_after is computed inside the transaction and added before storage.

        Returns (success, stored_result_or_None, cached_response_or_None):
          - cached_response not None → idempotent replay, don't re-process
          - stored_result not None  → first call; has balance_after filled in
          - success False           → insufficient funds, no settlement

        Falls back to settle_round when SQLite is unavailable (no idempotency guarantee).
        """
        if _USE_SQLITE:
            return _db.settle_with_idempotency(
                user_id, bet_amount, payout, request_id, response_template)
        # CSV fallback: no durable idempotency; apply settlement best-effort
        ok, new_bal = self.settle_round(user_id, bet_amount, payout)
        if not ok:
            return False, None, None
        result = dict(response_template)
        result['balance_after'] = new_bal
        return True, result, None

    def credit_with_idempotency(self, user_id, amount, request_id, response_template):
        """Credit-only atomic operation with durable idempotency.

        For pre-deducted games (mines cashout, all-safe reveal) where the bet
        was already deducted upfront.

        Returns (success, stored_result_or_None, cached_response_or_None).
        Falls back to add_balance when SQLite is unavailable.
        """
        if _USE_SQLITE:
            return _db.credit_with_idempotency(
                user_id, amount, request_id, response_template)
        new_bal = self.add_balance(user_id, amount)
        result = dict(response_template)
        result['balance_after'] = new_bal
        return True, result, None

    def get_idempotency_record(self, user_id, request_id):
        """Read a stored idempotency result from SQLite (survives restarts).
        Returns dict or None.
        """
        if _USE_SQLITE:
            return _db.get_idempotency_record(user_id, request_id)
        return None

    # ===== الألعاب =====

    def get_games(self, active_only=True):
        games = []
        try:
            with open(self.catalog_file, 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Strip BOM from keys if present
                    clean = {}
                    for k, v in (row or {}).items():
                        ck = k.lstrip('\ufeff').strip() if k else k
                        clean[ck] = v
                    if active_only and clean.get('is_active') != 'yes':
                        continue
                    games.append(clean)
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

    def create_quick_deposit(self, user_id, amount, payment_method_id, account_number,
                             method_name='', method_account_data='', player_wallet='',
                             save_method=False, purpose='', ticket_count=0):
        """إنشاء إيداع سريع — يكتب في quick_deposits.csv + transactions.csv كمعاملة حقيقية"""
        dep_id = f"DEP{str(int(datetime.now().timestamp()))[-8:]}_{random.randint(1000,9999)}"
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 1. كتابة في quick_deposits.csv
        fieldnames = ['id', 'user_id', 'amount', 'payment_method_id',
                      'account_number', 'status', 'approved_by', 'approved_at',
                      'game_session_id', 'created_at', 'purpose', 'ticket_count']
        row = {
            'id': dep_id, 'user_id': str(user_id), 'amount': str(amount),
            'payment_method_id': payment_method_id, 'account_number': account_number,
            'status': 'pending', 'approved_by': '', 'approved_at': '',
            'game_session_id': '', 'created_at': now_str,
            'purpose': purpose, 'ticket_count': str(ticket_count),
        }
        try:
            with open(self.quick_deposits_file, 'a', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writerow(row)
        except:
            pass

        # 2. كتابة معاملة حقيقية في transactions.csv
        user_info = self.get_user_info(user_id)
        trans_id = f"DEP{datetime.now().strftime('%Y%m%d%H%M%S')}"
        currency = user_info.get('currency', 'SAR')
        customer_id = user_info.get('customer_id', '')
        user_name = user_info.get('name', '')
        company_field = f"{method_name}__{method_account_data}" if method_name else payment_method_id

        try:
            txn_fields = ['id', 'customer_id', 'telegram_id', 'name', 'type', 'company',
                          'wallet_number', 'amount', 'exchange_address', 'status',
                          'date', 'admin_note', 'processed_by', 'currency']
            txn_row = {
                'id': trans_id,
                'customer_id': customer_id,
                'telegram_id': str(user_id),
                'name': user_name,
                'type': 'deposit',
                'company': company_field,
                'wallet_number': player_wallet or account_number,
                'amount': str(amount),
                'exchange_address': '',
                'status': 'pending',
                'date': now_str,
                'admin_note': 'إيداع محفظة VEX',
                'processed_by': '',
                'currency': currency,
            }
            txn_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'transactions.csv')
            with open(txn_file, 'a', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=txn_fields)
                writer.writerow(txn_row)
        except Exception as e:
            print(f"Transaction write error: {e}")

        # 3. حفظ محفظة اللاعب لو طلب ذلك
        if save_method and player_wallet:
            self.add_payment_method(
                user_id=user_id,
                method_name=method_name or 'محفظة',
                account_number=player_wallet,
                method_type='game_wallet',
                icon='🎮'
            )

        return dep_id

    def create_withdrawal(self, user_id, amount, payment_method_id, account_number):
        """إنشاء طلب سحب من محفظة الألعاب — يتطلب استيفاء شرط الرهان 101%"""
        # ── Wagering requirement: must wager 101% of total deposited ──
        wager_ok, wager_msg = self._check_wagering_requirement(user_id, amount)
        if not wager_ok:
            return None, wager_msg
        # خصم الرصيد فوراً (يُعاد لو رفض الأدمن)
        success, balance_after = self.deduct_balance(user_id, amount)
        if not success:
            return None, 'رصيد غير كافٍ'
        dep_id = f"WTH{str(int(datetime.now().timestamp()))[-8:]}_{random.randint(1000,9999)}"
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

    def _check_wagering_requirement(self, user_id, withdrawal_amount):
        """شرط الرهان: لازم العميل يلعب بـ 101% من إجمالي الإيداعات قبل السحب."""
        try:
            uid = str(user_id)
            # احسب إجمالي الإيداعات الموافق عليها
            total_deposited = 0.0
            total_wagered = 0.0
            try:
                with open(self.quick_deposits_file, 'r', encoding=CSV_ENCODING) as f:
                    for row in csv.DictReader(f):
                        if row.get('user_id') == uid and row.get('status') == 'approved':
                            try: total_deposited += float(row.get('amount', 0) or 0)
                            except: pass
            except: pass
            # احسب إجمالي الرهانات من game_sessions
            try:
                with open(self.sessions_file, 'r', encoding=CSV_ENCODING) as f:
                    for row in csv.DictReader(f):
                        if row.get('user_id') == uid:
                            try: total_wagered += float(row.get('bet_amount', 0) or 0)
                            except: pass
            except: pass
            # لو مفيش إيداعات → اسمح بالسحب (حساب جديد)
            if total_deposited <= 0:
                return True, ''
            required_wager = total_deposited * 1.01  # 101%
            if total_wagered < required_wager:
                remaining = required_wager - total_wagered
                msg = f'يجب اللعب بـ {remaining:.0f} إضافية قبل السحب (شرط الرهان 101%)'
                return False, msg
            return True, ''
        except Exception as e:
            # في حالة الخطأ، اسمح بالسحب (fail-open)
            return True, ''

    def approve_deposit(self, dep_id, admin_id):
        """موافقة على إيداع — يضيف الرصيد لمحفظة VEX"""
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
        except Exception as e:
            print(f"approve_deposit CSV error: {e}")
        if approved:
            # Only add to wallet if NOT a directed deposit (lottery tickets etc.)
            purpose = approved.get('purpose', '')
            if purpose != 'lottery_tickets':
                try:
                    new_bal = self.add_balance(approved['user_id'], float(approved['amount']))
                    print(f"approve_deposit: added {approved['amount']} to {approved['user_id']}, new balance: {new_bal}")
                except Exception as e:
                    print(f"approve_deposit add_balance error: {e}")
            else:
                print(f"approve_deposit: directed deposit (lottery_tickets) — skipping wallet add, auto-buy will handle")
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
        rejected = None
        try:
            with open(self.quick_deposits_file, 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row.get('id') == dep_id and row.get('status') == 'pending':
                        row['status'] = 'rejected'
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
        return rejected

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
