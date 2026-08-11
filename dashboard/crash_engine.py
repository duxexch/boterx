"""
crash_engine.py — Crash v2: Dual-Side Betting (💥 انفجار vs 🚀 صعود)

ARCHITECTURE (same pattern as aviator_engine.py):
  - State machine: WAITING(6s) → FLIGHT(dynamic) → CRASHED(4s) → WAITING ...
  - Game loop runs FOREVER — always cycling, even with 0 players.
  - Crash point is SECRET until crash — never sent to client during flight.
  - Server is the SOLE authority for payouts.
  - Client computes visible multiplier locally: e^(0.07 * elapsed).
  - Polling-based (1s) — SSE disabled (gunicorn gthread incompatible).

DUAL-SIDE BETTING:
  Side A "💥 انفجار" (Crash): bet it crashes at/below target X
    - crash ≤ X → WIN: payout = bet × X
    - mult > X → drain starts, can EXIT with remaining
    - drain ≥ 100% → lose all

  Side B "🚀 صعود" (Rise): bet it survives to target X
    - crash < X → LOSE all
    - mult ≥ X → survived, drain starts, CANNOT exit
    - drain ≥ 100% → lose all

7-STRATEGY SMART ALGORITHM:
  Strategies randomly selected per round. Considers player counts,
  bet pools, 10-round house profit history. Occasionally triggers
  "Moon Shot" big-win rounds to impress players.
"""

import math
import time
import json
import random
import secrets
import threading
from datetime import datetime

# ── Config ──────────────────────────────────────────────
WAITING_DURATION = 6      # seconds — betting window
CRASHED_DURATION = 4      # seconds — crash display then loop
TICK_RATE = 0.05          # 50ms internal tick
HOUSE_EDGE = 0.03         # 3% base edge
GROWTH_RATE = 0.07        # mult = e^(0.07 * t_seconds)
DRAIN_RATE = 0.5           # 50% drain per full X growth past target
MAX_MULTIPLIER = 100.0     # HARD CAP — force crash at 100x, never millions
WATCHDOG_TIMEOUT = 120     # seconds — if game loop stuck, force restart
EMERGENCY_THRESHOLD = 50.0 # if multiplier reaches 50x, evaluate emergency crash

# ── 7 Strategies ─────────────────────────────────────────
# Each strategy: (min_x, max_x, weight, description)
STRATEGIES = [
    {'name': 'early_crash',  'min': 1.00, 'max': 1.30,  'weight': 30},  # Rise loses all
    {'name': 'normal_low',   'min': 1.30, 'max': 2.00,  'weight': 20},  # Mixed
    {'name': 'medium',       'min': 2.00, 'max': 4.00,  'weight': 15},  # Crash drained, Rise partial
    {'name': 'high_fly',     'min': 4.00, 'max': 10.00, 'weight': 10},  # Rise wins big but drains
    {'name': 'moon_shot',    'min': 10.0, 'max': 50.0,  'weight': 5},   # WOW round
    {'name': 'house_protect', 'min': 1.00, 'max': 1.10, 'weight': 10},  # Near-instant crash
    {'name': 'balanced',     'min': 1.50, 'max': 2.50,  'weight': 10},  # Fair middle
]

# ── Runtime deps (injected by init_crash_engine) ────────
_gm = None
_pf = None
_is_pf = lambda: False
_is_vex = lambda: False

# ── Game state ──────────────────────────────────────────
_state = {
    'phase': 'waiting',
    'multiplier': 1.0,
    'crash_point': 2.0,        # SECRET
    'round_id': 0,
    'flight_start': 0.0,
    'crash_bets': {},           # uid -> {amount, target_x, exited: False, remaining, payout}
    'rise_bets': {},            # uid -> {amount, target_x, remaining, payout}
    'history': [],              # last 50 crash points
    'house_profits': [],        # last 10 rounds: (total_in - total_out)
    'strategy_used': '',        # for debug/log
    'seed_hash': '', 'client_seed': '', 'server_seed': '',
    'server_ts': 0.0,
    'request_ids': {},
    'total_bets_in': 0,         # total bet amount this round
    'total_payout': 0,          # total paid out this round
    'last_heartbeat': time.time(),  # watchdog: last game loop heartbeat
}
_lock = threading.Lock()
_rate = {}

# ── Rate limiter ────────────────────────────────────────
def _rate_ok(uid, limit=10, window=5.0):
    now = time.time()
    hits = [h for h in _rate.get(uid, []) if now - h < window]
    if len(hits) >= limit:
        _rate[uid] = hits
        return False
    hits.append(now)
    _rate[uid] = hits
    return True

# ── Provably fair ───────────────────────────────────────
def _seed_ready():
    return bool(_state.get('seed_hash')) and bool(_state.get('client_seed'))

def _pick_strategy():
    """Smart strategy selection based on pools + 10-round profit history."""
    with _lock:
        crash_pool = sum(b['amount'] for b in _state['crash_bets'].values())
        rise_pool = sum(b['amount'] for b in _state['rise_bets'].values())
        profits = list(_state['house_profits'])
        round_id = _state['round_id']

    # Calculate house profit over last 10 rounds
    recent_profit = sum(profits[-10:]) if profits else 0
    total_recent = sum(abs(p) for p in profits[-10:]) if profits else 0

    # Strategy 6 (House Protect): if house lost too much recently
    if recent_profit < -total_recent * 0.3 and total_recent > 0:
        return STRATEGIES[5]  # house_protect

    # Strategy 5 (Moon Shot): if house is very profitable, trigger big win
    # Every ~10 rounds, if profit is good, 85% chance to moon shot (15% skip for unpredictability)
    if round_id > 0 and round_id % 10 == 0 and recent_profit > 0:
        if random.random() < 0.85:
            return STRATEGIES[4]  # moon_shot

    # If rise pool >> crash pool (most bet on survival) → early crash to profit house
    if rise_pool > crash_pool * 1.5 and rise_pool > 0:
        # 60% chance early crash, 40% normal
        if random.random() < 0.60:
            return STRATEGIES[0]  # early_crash
        return STRATEGIES[1]  # normal_low

    # If crash pool >> rise pool (most bet on crash) → fly higher to drain crash bettors
    if crash_pool > rise_pool * 1.5 and crash_pool > 0:
        if random.random() < 0.50:
            return STRATEGIES[2]  # medium
        return STRATEGIES[3]  # high_fly

    # Pools roughly equal or no bets → weighted random
    weights = [s['weight'] for s in STRATEGIES]
    chosen = random.choices(STRATEGIES, weights=weights, k=1)[0]
    return chosen

def _calc_crash():
    """Pick strategy + generate crash point within range with ±10% noise."""
    strategy = _pick_strategy()
    raw = random.uniform(strategy['min'], strategy['max'])
    # Add ±10% noise for unpredictability
    noise = random.uniform(-0.10, 0.10)
    crash_pt = raw * (1 + noise)
    crash_pt = min(MAX_MULTIPLIER, max(1.00, round(crash_pt, 2)))

    with _lock:
        _state['strategy_used'] = strategy['name']
    return crash_pt

def _server_mult():
    """Authoritative multiplier from flight start timestamp."""
    if _state['phase'] == 'flying':
        elapsed = time.time() - _state['flight_start']
        return max(1.0, math.exp(GROWTH_RATE * elapsed))
    elif _state['phase'] == 'crashed':
        return _state.get('crash_point', 1.0)
    return 1.0

# ── Drain calculation ────────────────────────────────────
def _calc_remaining(bet_amount, target_x, current_mult, side):
    """Calculate remaining balance after drain."""
    if side == 'crash':
        if current_mult <= target_x:
            return bet_amount  # not yet draining
        drain = (current_mult - target_x) / target_x * DRAIN_RATE
        return max(0, bet_amount * (1 - drain))
    else:  # rise
        if current_mult < target_x:
            return 0  # hasn't survived yet — loses all on crash
        won = bet_amount * target_x
        drain = (current_mult - target_x) / target_x * DRAIN_RATE
        return max(0, won * (1 - drain))

# ── User cache (same pattern as aviator) ────────────────
_user_cache = {}
_cache_loaded = False

def _load_user_cache():
    global _user_cache, _cache_loaded
    if _cache_loaded:
        return
    try:
        import csv as _csv
        with open('users.csv', 'r', encoding='utf-8-sig') as f:
            for row in _csv.DictReader(f):
                tid = row.get('telegram_id', '')
                if tid:
                    _user_cache[tid] = {
                        'name': row.get('name', ''),
                        'phone': row.get('phone', '') or row.get('phone_number', '')
                    }
        _cache_loaded = True
    except Exception as e:
        _cache_loaded = True

def _get_name(uid):
    if not _cache_loaded:
        _load_user_cache()
    info = _user_cache.get(str(uid))
    return info['name'] if info else ''

def _get_user_phone(uid):
    if not _cache_loaded:
        _load_user_cache()
    info = _user_cache.get(str(uid))
    return info['phone'] if info else ''

def _mask_name(name, phone):
    if name and len(name) > 1:
        masked = name[0] + '***'
    elif name:
        masked = name[0] + '**'
    else:
        masked = 'لاعب'
    if phone and len(phone) >= 4:
        masked += ' •' + phone[-4:]
    return masked

# ── Fake players (dual-side) ────────────────────────────
_FAKE_NAMES = [
    'أحمد','عمر','محمد','خالد','سعد','فهد','ناصر','يوسف','علي','حسن',
    'ماجد','وليد','طارق','بدر','راشد','عبدالله','سلطان','فيصل','نايف',
    'تركي','دانا','نورة','ريم','سارة','لمى','شهد','جود','هند','روان'
]

def _generate_fake_players(current_mult):
    """Generate fake players on BOTH sides — phase-aware."""
    phase = _state['phase']
    count = random.randint(5, 10)
    result = []
    for i in range(count):
        raw_name = random.choice(_FAKE_NAMES)
        masked_name = raw_name[0] + '*** •' + str(random.randint(100, 999))
        bet = random.choice([10, 20, 50, 100, 200, 500, 1000, 2000, 5000])
        avatar = raw_name[0]
        side = 'crash' if random.random() < 0.5 else 'rise'
        target = round(random.choice([1.0, 1.2, 1.5, 1.8, 2.0, 2.5, 3.0, 4.0, 5.0]), 2)

        if phase == 'waiting':
            status = 'participating'
            mult_disp = 0
            payout = 0
        elif phase == 'flying':
            remaining = _calc_remaining(bet, target, current_mult, side)
            if side == 'crash':
                if current_mult <= target:
                    status = 'waiting_crash'
                    mult_disp = target
                    payout = 0
                else:
                    status = 'draining'
                    mult_disp = target
                    payout = round(remaining, 0)
            else:  # rise
                if current_mult < target:
                    status = 'waiting_rise'
                    mult_disp = target
                    payout = 0
                else:
                    status = 'surviving'
                    mult_disp = target
                    payout = round(remaining, 0)
        elif phase == 'crashed':
            crash_pt = _state.get('crash_point', 1.0)
            if side == 'crash':
                if crash_pt <= target:
                    status = 'cashed'
                    mult_disp = target
                    payout = round(bet * target, 0)
                else:
                    remaining = _calc_remaining(bet, target, crash_pt, 'crash')
                    if remaining > 0:
                        status = 'cashed'
                        mult_disp = target
                        payout = round(remaining, 0)
                    else:
                        status = 'lost'
                        mult_disp = target
                        payout = 0
            else:  # rise
                if crash_pt < target:
                    status = 'lost'
                    mult_disp = target
                    payout = 0
                else:
                    remaining = _calc_remaining(bet, target, crash_pt, 'rise')
                    if remaining > 0:
                        status = 'cashed'
                        mult_disp = target
                        payout = round(remaining, 0)
                    else:
                        status = 'lost'
                        mult_disp = target
                        payout = 0
        else:
            status = 'participating'
            mult_disp = 0
            payout = 0

        result.append({
            'name': masked_name, 'avatar': avatar, 'bet': bet,
            'target_x': target, 'side': side,
            'multiplier': mult_disp, 'payout': payout, 'status': status,
        })
    # Sort by payout desc
    result.sort(key=lambda x: (-x['payout'], 0 if x['status'] != 'lost' else 1))
    return result

# ── Game loop (daemon, runs forever) ────────────────────
def _game_loop():
    while True:
        # ── WAITING ──
        with _lock:
            _state['phase'] = 'waiting'
            _state['multiplier'] = 1.0
            _state['round_id'] += 1
            _state['crash_bets'] = {}
            _state['rise_bets'] = {}
            _state['request_ids'] = {}
            _state['server_ts'] = time.time()
            _state['total_bets_in'] = 0
            _state['total_payout'] = 0
            try:
                if _is_pf():
                    sid = 'crashround_%d' % _state['round_id']
                    cs = secrets.token_hex(8)
                    si = _pf.create_session(sid, cs)
                    _state['seed_hash'] = si['seed_hash']
                    _state['client_seed'] = si['client_seed']
            except:
                _state['seed_hash'] = ''
                _state['client_seed'] = secrets.token_hex(8)

        time.sleep(WAITING_DURATION)

        # ── FLIGHT ──
        crash_pt = _calc_crash()
        # SAFETY: cap crash point at MAX_MULTIPLIER
        crash_pt = min(crash_pt, MAX_MULTIPLIER)
        with _lock:
            _state['phase'] = 'flying'
            _state['crash_point'] = crash_pt  # SECRET
            _state['flight_start'] = time.time()
            _state['last_heartbeat'] = time.time()

        # Internal loop: update multiplier, auto-drain check, emergency stop
        while True:
            mult = _server_mult()
            with _lock:
                _state['multiplier'] = mult
                _state['last_heartbeat'] = time.time()
            # HARD CAP: force crash at MAX_MULTIPLIER
            if mult >= MAX_MULTIPLIER:
                crash_pt = min(crash_pt, mult)
                break
            if mult >= crash_pt:
                break
            time.sleep(TICK_RATE)

        # ── CRASHED — settle all bets ──
        total_in = 0
        total_out = 0
        with _lock:
            _state['phase'] = 'crashed'
            _state['history'].append(round(crash_pt, 2))
            if len(_state['history']) > 50:
                _state['history'].pop(0)

            # Settle crash bets
            for uid, bet in list(_state['crash_bets'].items()):
                total_in += bet['amount']
                if bet.get('exited', False):
                    # Already exited earlier — payout was given at exit time
                    total_out += bet.get('payout', 0)
                elif crash_pt <= bet['target_x']:
                    # WIN: payout = bet × target_x
                    payout = bet['amount'] * bet['target_x']
                    bet['payout'] = round(payout, 2)
                    bet['remaining'] = round(payout, 2)
                    try: _gm.add_balance(uid, payout)
                    except: pass
                    total_out += payout
                else:
                    # DRAINED: get remaining
                    remaining = _calc_remaining(bet['amount'], bet['target_x'], crash_pt, 'crash')
                    if remaining > 0:
                        try: _gm.add_balance(uid, remaining)
                        except: pass
                    bet['payout'] = round(remaining, 2)
                    bet['remaining'] = round(remaining, 2)
                    total_out += remaining

            # Settle rise bets
            for uid, bet in list(_state['rise_bets'].items()):
                total_in += bet['amount']
                if crash_pt < bet['target_x']:
                    # LOSE all
                    bet['payout'] = 0
                    bet['remaining'] = 0
                else:
                    # SURVIVED + DRAINED: get remaining
                    remaining = _calc_remaining(bet['amount'], bet['target_x'], crash_pt, 'rise')
                    if remaining > 0:
                        try: _gm.add_balance(uid, remaining)
                        except: pass
                    bet['payout'] = round(remaining, 2)
                    bet['remaining'] = round(remaining, 2)
                    total_out += remaining

            # Track house profit
            house_profit = total_in - total_out
            _state['house_profits'].append(house_profit)
            if len(_state['house_profits']) > 10:
                _state['house_profits'].pop(0)
            _state['total_bets_in'] = round(total_in, 2)
            _state['total_payout'] = round(total_out, 2)

            # Reveal seed
            server_seed = ''
            try:
                if _is_pf() and _state.get('seed_hash'):
                    rev = _pf.reveal_seed('crashround_%d' % _state['round_id'])
                    if rev: server_seed = rev.get('server_seed', '')
            except: pass
            _state['server_seed'] = server_seed

        time.sleep(CRASHED_DURATION)

# ── Flask route registration ─────────────────────────────
def init_crash_engine(app, get_uid, get_gm, get_pf, is_pf, is_vex):
    global _gm, _pf, _is_pf, _is_vex
    _gm = get_gm()
    _pf = get_pf
    _is_pf = is_pf
    _is_vex = is_vex
    from flask import jsonify, request

    @app.route('/api/crash/bet', methods=['POST'])
    def api_crash_bet():
        uid = get_uid()
        if not uid: return jsonify({'error': 'No uid'}), 400
        if not _rate_ok(uid): return jsonify({'error': 'طلبات كثيرة، انتظر قليلاً'}), 429
        data = request.json or {}
        # Input validation
        try:
            amount = float(data.get('bet_amount', 0))
            if amount <= 0 or amount > 100000: return jsonify({'error': 'مبلغ غير صالح'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'مبلغ غير صالح'}), 400
        try:
            target_x = float(data.get('target_x', 0) or 0)
            if target_x < 1.0 or target_x > 50.0: return jsonify({'error': 'قيمة X غير صالحة'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'قيمة X غير صالحة'}), 400
        side = str(data.get('side', '')).strip().lower()
        if side not in ('crash', 'rise'): return jsonify({'error': 'جانب غير صالح'}), 400
        req_id = str(data.get('request_id', '') or '')[:64]
        if not str(uid).isdigit(): return jsonify({'error': 'uid غير صالح'}), 400

        with _lock:
            if _state['phase'] != 'waiting':
                return jsonify({'error': 'انتهت فترة المراهنة'})
            if _state.get('server_ts') and time.time() - _state['server_ts'] > WAITING_DURATION + 0.1:
                return jsonify({'error': 'انتهت نافذة الرهان'})
            # One bet per side per user
            bet_dict = _state['crash_bets'] if side == 'crash' else _state['rise_bets']
            if uid in bet_dict:
                return jsonify({'error': 'لقد راهنت بالفعل على هذا الجانب'})
            if req_id and _state['request_ids'].get(uid + '_' + side) == req_id:
                return jsonify({'error': 'طلب مكرر'}), 409
            if req_id: _state['request_ids'][uid + '_' + side] = req_id

            success, balance = _gm.deduct_balance(uid, amount)
            if not success:
                return jsonify({'need_deposit': True, 'error': 'رصيد غير كافٍ'})

            bet_entry = {'amount': amount, 'target_x': target_x, 'exited': False,
                        'remaining': amount, 'payout': 0}
            bet_dict[uid] = bet_entry

        return jsonify({'success': True, 'balance_after': balance,
                        'side': side, 'target_x': target_x})

    @app.route('/api/crash/exit', methods=['POST'])
    def api_crash_exit():
        """Crash bettor exits (cashout remaining). Rise bettors CANNOT exit."""
        uid = get_uid()
        if not uid: return jsonify({'error': 'No uid'}), 400
        if not _rate_ok(uid): return jsonify({'error': 'طلبات كثيرة'}), 429
        data = request.json or {}
        req_id = str(data.get('request_id', '') or '')[:64]
        if not str(uid).isdigit(): return jsonify({'error': 'uid غير صالح'}), 400

        with _lock:
            if _state['phase'] != 'flying':
                return jsonify({'error': 'لا يمكن الخروج الآن'})
            bet = _state['crash_bets'].get(uid)
            if not bet:
                return jsonify({'error': 'لا يوجد رهان انفجار'})
            if bet.get('exited', False):
                return jsonify({'error': 'لقد خرجت بالفعل'})
            if req_id and _state['request_ids'].get('exit_' + uid) == req_id:
                return jsonify({'error': 'طلب مكرر'}), 409
            if req_id: _state['request_ids']['exit_' + uid] = req_id

            mult = _state['multiplier']
            if mult >= _state['crash_point']:
                return jsonify({'success': False, 'error': 'انفجر الصاروخ'})

            remaining = _calc_remaining(bet['amount'], bet['target_x'], mult, 'crash')
            if remaining <= 0:
                return jsonify({'error': 'لا يوجد رصيد متبقي'})

            balance = _gm.add_balance(uid, remaining)
            bet['exited'] = True
            bet['remaining'] = round(remaining, 2)
            bet['payout'] = round(remaining, 2)
            name = _get_name(uid)

        return jsonify({'success': True, 'payout': round(remaining, 2),
                        'multiplier': round(mult, 2), 'balance_after': balance})

    @app.route('/api/crash/state')
    def api_crash_state():
        uid = get_uid()
        with _lock:
            # Get user's bets if any
            my_crash_bet = {}
            my_rise_bet = {}
            if uid:
                cb = _state['crash_bets'].get(uid)
                if cb:
                    my_crash_bet = {
                        'placed': True, 'amount': cb['amount'],
                        'target_x': cb['target_x'], 'exited': cb.get('exited', False),
                        'remaining': round(_calc_remaining(cb['amount'], cb['target_x'], _server_mult(), 'crash'), 2),
                    }
                rb = _state['rise_bets'].get(uid)
                if rb:
                    my_rise_bet = {
                        'placed': True, 'amount': rb['amount'],
                        'target_x': rb['target_x'],
                        'remaining': round(_calc_remaining(rb['amount'], rb['target_x'], _server_mult(), 'rise'), 2),
                    }

            return jsonify({
                'phase': _state['phase'],
                'multiplier': round(_server_mult(), 2),
                'crash_point': round(_state.get('crash_point', 0), 2) if _state['phase'] == 'crashed' else 0,
                'round_id': _state['round_id'],
                'history': list(_state['history'][-15:]),
                'my_crash_bet': my_crash_bet,
                'my_rise_bet': my_rise_bet,
                'players': _generate_fake_players(_server_mult()),
                'total_bets_egp': random.randint(80000, 500000),
                'total_in': round(_state.get('total_bets_in', 0), 2),
                'total_out': round(_state.get('total_payout', 0), 2),
            })

# ── Watchdog: monitor game loop health, auto-restart if frozen ──
def _watchdog():
    """Monitors game loop. If no heartbeat for WATCHDOG_TIMEOUT seconds,
    forces phase to 'crashed' to unstick the loop."""
    while True:
        time.sleep(15)
        try:
            with _lock:
                hb = _state.get('last_heartbeat', 0)
                phase = _state.get('phase', 'waiting')
                now = time.time()
                if phase == 'flying' and (now - hb) > WATCHDOG_TIMEOUT:
                    # EMERGENCY: game loop frozen during flight — force crash
                    _state['phase'] = 'crashed'
                    _state['crash_point'] = _state.get('multiplier', 1.0)
                    _state['last_heartbeat'] = now
                    # Settle bets immediately
                    crash_pt = _state['crash_point']
                    for uid, bet in list(_state.get('crash_bets', {}).items()):
                        if not bet.get('exited', False):
                            if crash_pt <= bet['target_x']:
                                payout = bet['amount'] * bet['target_x']
                                try: _gm.add_balance(uid, payout)
                                except: pass
                                bet['payout'] = round(payout, 2)
                            else:
                                rem = _calc_remaining(bet['amount'], bet['target_x'], crash_pt, 'crash')
                                if rem > 0:
                                    try: _gm.add_balance(uid, rem)
                                    except: pass
                                bet['payout'] = round(rem, 2)
                    for uid, bet in list(_state.get('rise_bets', {}).items()):
                        if crash_pt < bet['target_x']:
                            bet['payout'] = 0
                        else:
                            rem = _calc_remaining(bet['amount'], bet['target_x'], crash_pt, 'rise')
                            if rem > 0:
                                try: _gm.add_balance(uid, rem)
                                except: pass
                            bet['payout'] = round(rem, 2)
        except Exception as e:
            pass  # watchdog must never crash

# Start daemon threads
_thread = threading.Thread(target=_game_loop, daemon=True)
_thread.start()
_wd_thread = threading.Thread(target=_watchdog, daemon=True)
_wd_thread.start()
