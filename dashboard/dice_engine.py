# -*- coding: utf-8 -*-
"""
Dice engine — server-authoritative.

Math (fixed 2026-08-18):
  Exact-number bet (X in 2..10): P(win) = 0.97 x (RTP / X)
    -> EV = 0.97 x RTP = 0.8245  (RTP target 0.85)
  Even/odd side bet: P(win) = 0.97 x 0.5, pays 1.70x
    -> EV = 0.97 x 0.5 x 1.70 = 0.8245  (identical edge)
  Every choice has the SAME house edge (~17.5%) — no +EV option exists.
  Segment nudges hit_chance by at most ±3% relative, and the final
  RTP is hard-capped at 0.88 so boosts can never flip the edge.
"""
import math
import random
import threading
import time
from datetime import datetime

# ── Config ──────────────────────────────────────────────
RTP_TARGET = 0.85           # player return target before the 3% instant-loss
INSTANT_LOSS_CHANCE = 0.03  # 3% guaranteed loss
MIN_X = 2.0
MAX_X = 10.0
MIN_BET = 1.0
MAX_BET = 100000
EVENODD_PAYOUT = 1.70       # 0.5 x 1.70 = 0.85 RTP (same edge as exact bets)
MAX_RTP = 0.88              # hard cap after segment nudges

# ── Runtime deps (injected by init_dice_engine) ────────
_gm = None
_pf = None
_is_pf = lambda: False
_is_vex = lambda: False

# ── Game state ──────────────────────────
_state = {
    'round_id': 0,
    'history': [],          # last 50 rolls (global)
    'user_history': {},     # uid -> [last 20 rolls]
    'house_profit': 0.0,
    'total_bets': 0,
    'total_payout': 0.0,
}
_lock = threading.Lock()
_rate = {}

_secure_random = secrets_rand = None
try:
    _secure_random = random.SystemRandom()   # crypto-grade
except Exception:                            # pragma: no cover
    _secure_random = random

# ── Rate limiter (pruned) ───────────────────────────────
def _rate_ok(uid, limit=10, window=5.0):
    now = time.time()
    hits = [h for h in _rate.get(uid, []) if now - h < window]
    if len(hits) >= limit:
        _rate[uid] = hits
        return False
    hits.append(now)
    _rate[uid] = hits
    # prune stale uids — bounded memory
    if len(_rate) > 5000:
        cutoff = now - window
        fresh = {k: v for k, v in _rate.items() if v and v[-1] >= cutoff}
        _rate.clear()
        _rate.update(fresh)
    return True

# ── Player segment (correct pattern: computed, not stored) ──
def _get_player_segment(uid):
    try:
        if _gm and _gm.tracker:
            profile = _gm.tracker.get_profile(uid)
            return _gm.tracker.get_segment(profile)
    except Exception:
        pass
    return 'new'

# relative hit-chance nudge per segment (±3%), applied to CHANCE not payout
_SEGMENT_NUDGE = {
    'loser': 1.03,    # tiny sympathy boost
    'new': 1.03,      # welcome nudge
    'winner': 0.97,
    'hot': 0.97,
    'churning': 1.02,
    'vip': 1.00,
    'regular': 1.00,
    'new_player': 1.03,
}

def _hit_chance(uid, target_x):
    """P(win) for an exact bet: capped so RTP never exceeds MAX_RTP."""
    base = RTP_TARGET / float(target_x)
    nudge = _SEGMENT_NUDGE.get(_get_player_segment(uid), 1.0)
    chance = base * nudge
    # hard cap: chance x X <= MAX_RTP  →  the house edge can never flip
    chance = min(chance, MAX_RTP / float(target_x))
    return chance

def _generate_result(predicted, hit_chance):
    """Server-authoritative roll.

    3% instant loss (die lands on a non-predicted face), otherwise the
    predicted face wins with the exact computed probability. Uniform
    distribution over the remaining faces otherwise.
    """
    rng = _secure_random
    if rng.random() < INSTANT_LOSS_CHANCE:
        others = [n for n in range(1, 7) if n != predicted]
        return rng.choice(others)
    if rng.random() < hit_chance:
        return predicted
    others = [n for n in range(1, 7) if n != predicted]
    return rng.choice(others)

def _generate_evenodd(target_mod, hit_chance):
    """Roll a die that matches (or misses) the predicted parity at hit_chance.

    target_mod: 0 = even wanted, 1 = odd wanted."""
    rng = _secure_random
    want_mod = target_mod
    if rng.random() < INSTANT_LOSS_CHANCE:
        want_mod = 1 - target_mod    # forced miss
    elif rng.random() >= hit_chance:
        want_mod = 1 - target_mod    # statistical miss
    faces = [n for n in range(1, 7) if (n % 2) == want_mod]
    return rng.choice(faces)

# ── Fake players (rates match real math per X) ──────────
_FAKE_NAMES = [
    'أحمد','عمر','محمد','خالد','سعد','فهد','ناصر','يوسف','علي','حسن',
    'ماجد','وليد','طارق','بدر','راشد','عبدالله','سلطان','فيصل','نايف',
    'تركي','دانا','نورة','ريم','سارة','لمى','شهد','جود','هند','روان'
]

def _generate_fake_players():
    """Display-only. Win rate mirrors the real engine (0.97 x 0.85/X)."""
    rng = _secure_random
    count = rng.randint(5, 10)
    result = []
    for i in range(count):
        raw_name = rng.choice(_FAKE_NAMES)
        masked_name = raw_name[0] + '*** •' + str(rng.randint(100, 999))
        bet = rng.choice([10, 20, 50, 100, 200, 500, 1000, 2000, 5000])
        avatar = raw_name[0]
        predicted = rng.randint(1, 6)
        x = rng.choice([2.0, 3.0, 5.0, 8.0, 10.0])
        won = rng.random() < (0.97 * RTP_TARGET / x)   # honest per-X rate
        result_num = predicted if won else rng.choice([n for n in range(1, 7) if n != predicted])
        payout = round(bet * x, 0) if won else 0
        status = 'cashed' if won else 'lost'
        result.append({
            'name': masked_name, 'avatar': avatar, 'bet': bet,
            'predicted': predicted, 'result': result_num,
            'multiplier': x, 'payout': payout, 'status': status,
        })
    result.sort(key=lambda r: -r['payout'])
    return result

# ── Flask route registration ─────────────────────────────
def init_dice_engine(app, get_uid, get_gm, get_pf, is_pf, is_vex, webapp_auth=None):
    global _gm, _pf, _is_pf, _is_vex
    _gm = get_gm()
    _pf = get_pf
    _is_pf = is_pf
    _is_vex = is_vex
    from flask import jsonify, request, g

    # If webapp_auth not passed, create a passthrough decorator
    if webapp_auth is None:
        def webapp_auth(f):
            return f

    @app.route('/api/dice/roll', methods=['POST'])
    @webapp_auth
    def api_dice_roll():
        uid = get_uid()
        if not uid: return jsonify({'error': 'No uid'}), 400
        # هوية موثقة فقط — بدونها يمكن المراهنة بهوية أي ضحية عبر uid مجرد
        if not getattr(g, 'webapp_auth_strong', False):
            return jsonify({'error': 'Unauthorized'}), 403
        if not str(uid).isdigit(): return jsonify({'error': 'uid غير صالح'}), 400
        if not _rate_ok(uid): return jsonify({'error': 'طلبات كثيرة، انتظر قليلاً'}), 429
        if not _is_vex(): return jsonify({'error': 'Games not available'}), 500
        data = request.json or {}
        # Input validation — NaN/Infinity rejected explicitly
        try:
            amount = float(data.get('bet_amount', 0))
            if not math.isfinite(amount) or amount < MIN_BET or amount > MAX_BET:
                return jsonify({'error': f'مبلغ غير صالح ({int(MIN_BET)}–{int(MAX_BET)})'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'مبلغ غير صالح'}), 400
        bet_mode = str(data.get('bet_mode', 'exact') or 'exact')
        if bet_mode not in ('exact', 'even', 'odd'):
            return jsonify({'error': 'نوع رهان غير صالح'}), 400
        try:
            predicted = int(data.get('predicted_number', 0))
            if predicted < 1 or predicted > 6: return jsonify({'error': 'رقم غير صالح (1-6)'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'رقم غير صالح'}), 400
        try:
            target_x = float(data.get('target_x', 5.0) or 5.0)
            if not math.isfinite(target_x) or target_x < MIN_X or target_x > MAX_X:
                return jsonify({'error': f'قيمة X بين {int(MIN_X)} و {int(MAX_X)}'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'قيمة X غير صالحة'}), 400
        req_id = str(data.get('request_id', '') or '')[:64]

        # Generate result FIRST (server-authoritative), then settle bet+payout
        # in ONE atomic SQLite transaction — a crash can never leave the bet
        # debited without the win credited, and request_id makes retries safe.
        if bet_mode == 'exact':
            chance = _hit_chance(uid, target_x)
            result_num = _generate_result(predicted, chance)
            won = (result_num == predicted)
            actual_x = target_x
        else:
            # Even/odd: fixed 1.70x, P = 0.97 x 0.5 (same edge as exact bets)
            chance = 0.5
            target_mod = 0 if bet_mode == 'even' else 1
            result_num = _generate_evenodd(target_mod, chance)
            won = ((result_num % 2) == target_mod)
            actual_x = EVENODD_PAYOUT
        payout = round(amount * actual_x, 2) if won else 0

        template = {
            'success': True,
            'result': result_num,
            'predicted': predicted,
            'won': won,
            'payout': payout,
            'multiplier': actual_x,
            'bet_mode': bet_mode,
            'win_chance': round(chance, 4),
            'balance_after': 0,  # filled by settlement
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
            if uid not in _state['user_history']:
                _state['user_history'][uid] = []
            _state['user_history'][uid].append({
                'result': result_num,
                'predicted': predicted,
                'won': won,
                'bet': amount,
                'payout': payout,
                'x': actual_x,
                'mode': bet_mode,
                'timestamp': datetime.now().strftime('%H:%M:%S'),
            })
            if len(_state['user_history'][uid]) > 20:
                _state['user_history'][uid].pop(0)
            _state['house_profit'] += (amount - payout)
            _state['total_bets'] += 1
            _state['total_payout'] += payout

        # Log session — collision-proof id
        try:
            session_id = f"DICE_{int(time.time())}_{uid}_{id(template) % 100000}"
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
        except Exception:
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

    @app.route('/api/dice/stats')
    @webapp_auth
    def api_dice_stats():
        """إحصائيات الأرقام الساخنة/الباردة من آخر 50 رمية فعلية."""
        with _lock:
            hist = [h['result'] for h in _state['history']]
        counts = {n: hist.count(n) for n in range(1, 7)}
        return jsonify({'counts': counts, 'total': len(hist)})


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
