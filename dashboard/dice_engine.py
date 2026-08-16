"""
dice_engine.py — Dice Game backend (predict the dice roll).

ARCHITECTURE (same pattern as aviator/crash engines):
  - Server is the SOLE authority for dice result.
  - Client animation is cosmetic only — result comes from API.
  - Smart algorithm adjusts payout based on player segment.
  - 3% instant loss guarantee (house edge floor).
  - Provably fair compatible (when available).

GAMEPLAY:
  1. User selects predicted number (1-6) and target X multiplier.
  2. User places bet → server deducts balance.
  3. Server generates result (1-6) — weighted by house edge.
  4. If result == predicted → WIN: payout = bet × X.
  5. If result != predicted → LOSE.
"""

import math
import time
import json
import random
import secrets
import threading
from datetime import datetime

# ── Config ──────────────────────────────────────────────
HOUSE_EDGE = 0.15          # 15% house edge
INSTANT_LOSS_CHANCE = 0.03 # 3% guaranteed loss
BASE_MULTIPLIER = 5.0      # fair payout for 1/6 probability
MIN_X = 2.0                # minimum selectable X
MAX_X = 10.0               # maximum selectable X
MAX_BET = 100000

# ── Runtime deps (injected by init_dice_engine) ────────
_gm = None
_pf = None
_is_pf = lambda: False
_is_vex = lambda: False

# ── Game state ──────────────────────────────────────────
_state = {
    'round_id': 0,
    'history': [],          # last 50 rolls (global)
    'user_history': {},     # uid -> [last 20 rolls]
    'house_profit': 0.0,    # running house profit
    'total_bets': 0,        # total bets this session
    'total_payout': 0.0,    # total paid out this session
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

# ── Smart algorithm ────────────────────────────────────
def _get_player_segment(uid):
    """Get player segment for X adjustment."""
    try:
        if _gm and _gm.tracker:
            profile = _gm.tracker.get_profile(uid)
            return profile.get('segment', 'new')
    except:
        pass
    return 'new'

def _calc_multiplier(uid, user_x):
    """Adjust user-selected X based on player segment + house edge."""
    segment = _get_player_segment(uid)
    x = float(user_x)
    # Clamp to range
    x = max(MIN_X, min(MAX_X, x))
    # Segment-based adjustment
    if segment == 'loser':
        x *= 1.05  # 5% bonus for losers
    elif segment == 'winner':
        x *= 0.95  # 5% penalty for winners
    elif segment == 'new':
        x *= 1.10  # 10% welcome bonus
    elif segment == 'hot':
        x *= 0.90  # 10% penalty for hot players
    return round(x, 2)

def _generate_result(predicted):
    """Server-authoritative dice result.
    3% instant loss, then weighted probability of hitting predicted number."""
    # 3% instant loss
    if random.random() < INSTANT_LOSS_CHANCE:
        others = [n for n in range(1, 7) if n != predicted]
        return random.choice(others)
    # Weighted: P(hit) = 1/6 adjusted by house edge
    hit_chance = (1.0 / 6.0) * (1.0 - HOUSE_EDGE)
    if random.random() < hit_chance:
        return predicted
    else:
        others = [n for n in range(1, 7) if n != predicted]
        return random.choice(others)

# ── Fake players ───────────────────────────────────────
_FAKE_NAMES = [
    'أحمد','عمر','محمد','خالد','سعد','فهد','ناصر','يوسف','علي','حسن',
    'ماجد','وليد','طارق','بدر','راشد','عبدالله','سلطان','فيصل','نايف',
    'تركي','دانا','نورة','ريم','سارة','لمى','شهد','جود','هند','روان'
]

def _generate_fake_players():
    """Generate fake players for display."""
    count = random.randint(5, 10)
    result = []
    for i in range(count):
        raw_name = random.choice(_FAKE_NAMES)
        masked_name = raw_name[0] + '*** •' + str(random.randint(100, 999))
        bet = random.choice([10, 20, 50, 100, 200, 500, 1000, 2000, 5000])
        avatar = raw_name[0]
        predicted = random.randint(1, 6)
        won = random.random() < 0.30  # 30% win rate for display
        result_num = predicted if won else random.choice([n for n in range(1,7) if n != predicted])
        x = random.choice([2.0, 3.0, 5.0, 8.0, 10.0])
        payout = round(bet * x, 0) if won else 0
        status = 'cashed' if won else 'lost'
        result.append({
            'name': masked_name, 'avatar': avatar, 'bet': bet,
            'predicted': predicted, 'result': result_num,
            'multiplier': x, 'payout': payout, 'status': status,
        })
    result.sort(key=lambda x: -x['payout'])
    return result

# ── Flask route registration ─────────────────────────────
def init_dice_engine(app, get_uid, get_gm, get_pf, is_pf, is_vex, webapp_auth=None):
    global _gm, _pf, _is_pf, _is_vex
    _gm = get_gm()
    _pf = get_pf
    _is_pf = is_pf
    _is_vex = is_vex
    from flask import jsonify, request

    # If webapp_auth not passed, create a passthrough decorator
    if webapp_auth is None:
        def webapp_auth(f):
            return f

    @app.route('/api/dice/roll', methods=['POST'])
    @webapp_auth
    def api_dice_roll():
        uid = get_uid()
        if not uid: return jsonify({'error': 'No uid'}), 400
        if not _rate_ok(uid): return jsonify({'error': 'طلبات كثيرة، انتظر قليلاً'}), 429
        data = request.json or {}
        # Input validation
        try:
            amount = float(data.get('bet_amount', 0))
            if amount <= 0 or amount > MAX_BET: return jsonify({'error': 'مبلغ غير صالح'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'مبلغ غير صالح'}), 400
        try:
            predicted = int(data.get('predicted_number', 0))
            if predicted < 1 or predicted > 6: return jsonify({'error': 'رقم غير صالح (1-6)'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'رقم غير صالح'}), 400
        try:
            target_x = float(data.get('target_x', 5.0) or 5.0)
            if target_x < MIN_X or target_x > MAX_X: return jsonify({'error': f'قيمة X بين {MIN_X} و {MAX_X}'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'قيمة X غير صالحة'}), 400
        req_id = str(data.get('request_id', '') or '')[:64]
        if not str(uid).isdigit(): return jsonify({'error': 'uid غير صالح'}), 400
        if not _is_vex(): return jsonify({'error': 'Games not available'}), 500

        # Generate result FIRST (server-authoritative), then settle bet+payout
        # in ONE atomic SQLite transaction — a crash can never leave the bet
        # debited without the win credited, and request_id makes retries safe.
        result_num = _generate_result(predicted)
        won = (result_num == predicted)
        actual_x = _calc_multiplier(uid, target_x)
        payout = round(amount * actual_x, 2) if won else 0

        template = {
            'success': True,
            'result': result_num,
            'predicted': predicted,
            'won': won,
            'payout': payout,
            'multiplier': actual_x,
        }
        ok, stored, race_cached = _gm.settle_with_idempotency(uid, amount, payout, req_id, template)
        if race_cached:
            return jsonify(race_cached)
        if not ok:
            return jsonify({'need_deposit': True, 'error': 'رصيد غير كافٍ'})
        new_balance = stored.get('balance_after', 0)
        balance = round(new_balance - payout + amount, 2)  # balance before, for logs

        # Track stats
        with _lock:
            _state['round_id'] += 1
            _state['history'].append({
                'round_id': _state['round_id'],
                'result': result_num,
                'timestamp': datetime.now().strftime('%H:%M:%S'),
            })
            if len(_state['history']) > 50:
                _state['history'].pop(0)
            # User history
            if uid not in _state['user_history']:
                _state['user_history'][uid] = []
            _state['user_history'][uid].append({
                'result': result_num,
                'predicted': predicted,
                'won': won,
                'bet': amount,
                'payout': payout,
                'x': actual_x,
                'timestamp': datetime.now().strftime('%H:%M:%S'),
            })
            if len(_state['user_history'][uid]) > 20:
                _state['user_history'][uid].pop(0)
            # House profit tracking
            _state['house_profit'] += (amount - payout)
            _state['total_bets'] += 1
            _state['total_payout'] += payout

        # Log session
        try:
            session_id = f"DICE_{int(time.time())}_{uid}"
            if _gm.tracker:
                _gm.tracker.log_session({
                    'session_id': session_id, 'game_id': 'GAME010', 'user_id': uid,
                    'bet_amount': amount, 'payout': payout, 'result': 'win' if won else 'lose',
                    'balance_before': balance, 'balance_after': new_balance,
                    'multiplier': actual_x,
                })
                _gm.tracker.update_profile(uid, {
                    'bet_amount': amount, 'payout': payout,
                    'result': 'win' if won else 'lose', 'game_id': 'GAME010',
                    'balance_after': new_balance,
                })
        except:
            pass

        return jsonify(stored)

    @app.route('/api/dice/history')
    @webapp_auth
    def api_dice_history():
        uid = get_uid()
        with _lock:
            user_hist = list(_state['user_history'].get(uid, []))
            global_hist = [{'result': h['result'], 'time': h['timestamp']} for h in _state['history'][-15:]]
            return jsonify({
                'history': global_hist,
                'user_history': user_hist,
                'players': _generate_fake_players(),
                'total_bets_egp': _sim_total_bets(),
            })


def _sim_total_bets():
    """Smoothly drifting simulated pool (no global rounds in dice)."""
    now = time.time()
    w = int(now // 45)
    def _v(k):
        return random.Random(k * 104729 + 7).randint(90000, 320000)
    a, b = _v(w), _v(w + 1)
    t = (now % 45) / 45.0
    t = t * t * (3 - 2 * t)  # smoothstep
    val = a + (b - a) * t
    val *= 1 + 0.006 * math.sin(now * 1.7)
    return int(round(val / 10.0) * 10)

# Start — no daemon thread needed (per-request game, not global round)
