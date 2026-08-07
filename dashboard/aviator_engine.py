"""
aviator_engine.py — standalone Aviator game backend module (v2).

Architecture v2 (per spec):
  State machine: WAITING(5s) -> STARTING(2s) -> FLIGHT(dynamic) -> CRASHED(3s) -> WAITING
  Server optimization: NO per-tick multiplier broadcast. Server broadcasts ONLY:
    - 'waiting'  (betting window open, with seed_hash commitment)
    - 'starting' (2s lock, no new bets)
    - 'flight_start' (contains game_id + server_seed_hash)
    - 'crashed'  (contains real crash_point + revealed server_seed)
  Client computes multiplier locally: mult = e^(0.07 * elapsed).
  Server keeps the authoritative multiplier + crash_point in memory for
  cashout validation — client never sets balance.

Registered via init_aviator_engine(app, **deps) with lazy dep getters.
"""

import math
import time
import json
import random
import secrets
import threading
import queue as _queue
from datetime import datetime

# === Config (v2) ===
WAITING_DURATION = 5     # seconds — bets accepted
STARTING_DURATION = 2    # seconds — lock, no new bets
CRASHED_DURATION = 3     # seconds — show result before next round
TICK_RATE = 0.05         # 50ms — internal multiplier/auto-cashout check (no broadcast)
HOUSE_EDGE = 0.03        # 3% house edge
GROWTH_RATE = 0.07       # mult = e^(0.07 * t_seconds) — matches client formula


# Runtime deps (set by init_aviator_engine)
_gm = None
_vex_games = lambda: False
_pf = None
_is_pf = lambda: False

_aviator = {
    'phase': 'idle',           # idle | waiting | starting | flying | crashed
    'multiplier': 1.0,
    'crash_point': 2.0,
    'round_id': 0,
    'flight_start': 0.0,       # unix ts when flight began (for multiplier calc)
    'bets': {},
    'history': [],
    'seed_hash': '', 'client_seed': '', 'server_seed': '',
    'server_ts': 0,
    'request_ids': {},
}
_aviator_lock = threading.Lock()
_aviator_sse_queues = []
_aviator_sse_lock = threading.Lock()
_aviator_rate = {}  # uid -> list of timestamps


# ===== Rate limiting =====
def rate_limit(uid, limit=10, window=5.0):
    """Allow max `limit` requests per `window` seconds per uid."""
    now = time.time()
    hits = _aviator_rate.get(uid, [])
    hits = [h for h in hits if now - h < window]
    if len(hits) >= limit:
        _aviator_rate[uid] = hits
        return False
    hits.append(now)
    _aviator_rate[uid] = hits
    return True


# ===== Provably fair crash point (v2 formula, 3% house edge) =====
def _seed_ready():
    """seed_hash + client_seed are committed BEFORE betting opens."""
    return bool(_aviator.get('seed_hash')) and bool(_aviator.get('client_seed'))


def calc_crash():
    """Correct crash point with 3% house edge.

    if R < 0.03: crash = 1.00 (instant crash — the 3% edge)
    else:        crash = (1 - 0.03) / (1 - R)
    round to 2 decimals. R in [0, 1) from provably-fair HMAC-SHA256.
    """
    if _is_pf() and _seed_ready():
        try:
            sid = 'avround_%d' % _aviator['round_id']
            r = _pf.generate_float(sid, 0.0, 1.0)['value']
        except Exception:
            r = random.random()
    else:
        r = random.random()
    if r < HOUSE_EDGE:
        crash_point = 1.00  # Instant crash (3% house edge)
    else:
        crash_point = (1 - HOUSE_EDGE) / (1 - r)
    return max(1.00, round(crash_point, 2))


def current_multiplier():
    """Authoritative multiplier from flight start: e^(0.07*t)."""
    if _aviator['phase'] != 'flying':
        return 1.0
    elapsed = time.time() - _aviator['flight_start']
    return max(1.0, math.exp(GROWTH_RATE * elapsed))


# ===== SSE broadcast =====
def broadcast(msg):
    payload = json.dumps(msg)
    with _aviator_sse_lock:
        for q in _aviator_sse_queues:
            try:
                q.put_nowait(payload)
            except Exception:
                pass


def _get_name(uid):
    try:
        from db_manager import _gdb
        row = _gdb.get_user_row(uid)
        return row.get('name', '') if row else ''
    except Exception:
        return ''


# ===== Game loop (daemon thread) =====
def _game_loop():
    while True:
        # ---- WAITING (5s): bets accepted ----
        with _aviator_lock:
            _aviator['phase'] = 'waiting'
            _aviator['multiplier'] = 1.0
            _aviator['round_id'] += 1
            _aviator['bets'] = {}
            _aviator['request_ids'] = {}
            _aviator['server_ts'] = time.time()
            try:
                if _is_pf():
                    sid = 'avround_%d' % _aviator['round_id']
                    cs = secrets.token_hex(8)
                    seed_info = _pf.create_session(sid, cs)
                    _aviator['seed_hash'] = seed_info['seed_hash']
                    _aviator['client_seed'] = seed_info['client_seed']
            except Exception:
                _aviator['seed_hash'] = ''
                _aviator['client_seed'] = secrets.token_hex(8)

        broadcast({'type': 'waiting', 'round_id': _aviator['round_id'],
                   'duration': WAITING_DURATION,
                   'history': list(_aviator['history'][-15:]),
                   'seed_hash': _aviator.get('seed_hash', ''),
                   'client_seed': _aviator.get('client_seed', '')})
        time.sleep(WAITING_DURATION)

        # ---- STARTING (2s): lock, no new bets ----
        with _aviator_lock:
            _aviator['phase'] = 'starting'
        broadcast({'type': 'starting', 'round_id': _aviator['round_id'],
                   'duration': STARTING_DURATION})
        time.sleep(STARTING_DURATION)

        # ---- FLIGHT (dynamic) ----
        crash_pt = calc_crash()
        with _aviator_lock:
            _aviator['phase'] = 'flying'
            _aviator['crash_point'] = crash_pt
            _aviator['flight_start'] = time.time()

        broadcast({'type': 'flight_start', 'round_id': _aviator['round_id'],
                   'game_id': 'GAME004',
                   'server_seed_hash': _aviator.get('seed_hash', ''),
                   'client_seed': _aviator.get('client_seed', '')})

        # Internal loop — compute authoritative multiplier + auto-cashout
        # WITHOUT broadcasting every tick (server optimization).
        total_distributed = 0.0
        total_cashed_out = 0
        total_bets = len(_aviator['bets'])
        while True:
            mult = current_multiplier()
            with _aviator_lock:
                _aviator['multiplier'] = mult
                for uid, bet in list(_aviator['bets'].items()):
                    if (not bet['cashed_out'] and bet.get('auto_val', 0) > 0
                            and mult >= bet['auto_val']):
                        payout = bet['amount'] * mult
                        try:
                            _gm.add_balance(uid, payout)
                        except Exception:
                            pass
                        bet['cashed_out'] = True
                        bet['cash_mult'] = mult
                        total_distributed += payout
                        total_cashed_out += 1
                        broadcast({'type': 'cashout', 'uid': uid,
                                   'name': _get_name(uid), 'amount': round(payout, 2),
                                   'multiplier': round(mult, 2), 'auto': True})
            if mult >= crash_pt:
                break
            time.sleep(TICK_RATE)

        # ---- CRASHED (3s) ----
        with _aviator_lock:
            _aviator['phase'] = 'crashed'
            _aviator['history'].append(round(crash_pt, 2))
            if len(_aviator['history']) > 50:
                _aviator['history'].pop(0)
            server_seed = ''
            try:
                if _is_pf() and _aviator.get('seed_hash'):
                    rev = _pf.reveal_seed('avround_%d' % _aviator['round_id'])
                    if rev:
                        server_seed = rev.get('server_seed', '')
            except Exception:
                server_seed = ''
            _aviator['server_seed'] = server_seed

        # Audit trail to DB
        try:
            from db_manager import _gdb
            conn = _gdb._conn()
            conn.execute('''
                INSERT INTO aviator_rounds (round_id, crash_point, seed_hash,
                    client_seed, server_seed, bet_count, total_wagered,
                    total_distributed, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                _aviator['round_id'], round(crash_pt, 2),
                _aviator.get('seed_hash', ''), _aviator.get('client_seed', ''),
                server_seed or '',
                total_bets,
                round(sum(b['amount'] for b in _aviator['bets'].values()), 2),
                round(total_distributed, 2),
                datetime.now().isoformat()
            ))
            conn.commit()
        except Exception:
            pass

        broadcast({'type': 'crashed', 'crash_point': round(crash_pt, 2),
                   'total_distributed': round(total_distributed, 2),
                   'total_cashed_out': total_cashed_out,
                   'total_bets': total_bets,
                   'server_seed': server_seed or '',
                   'seed_hash': _aviator.get('seed_hash', '')})
        time.sleep(CRASHED_DURATION)


# ===== Flask route registration =====
def init_aviator_engine(app, get_uid, get_gm, get_pf, is_pf, is_vex):
    """Register Aviator routes onto the Flask app with injected deps."""
    global _gm, _pf, _is_pf, _vex_games
    _gm = get_gm()
    _pf = get_pf
    _is_pf = is_pf
    _vex_games = is_vex

    from flask import jsonify, request, Response

    @app.route('/api/aviator/stream')
    def api_aviator_stream():
        q = _queue.Queue()
        with _aviator_sse_lock:
            _aviator_sse_queues.append(q)

        def generate():
            with _aviator_lock:
                state = {'type': _aviator['phase'],
                         'multiplier': round(_aviator['multiplier'], 2),
                         'crash_point': round(_aviator['crash_point'], 2),
                         'round_id': _aviator['round_id'],
                         'flight_start': _aviator['flight_start'],
                         'history': list(_aviator['history'][-15:])}
            yield 'data: %s\n\n' % json.dumps(state)
            while True:
                try:
                    yield 'data: %s\n\n' % q.get(timeout=15)
                except _queue.Empty:
                    yield 'data: %s\n\n' % json.dumps({'type': 'heartbeat'})

        try:
            return Response(generate(), mimetype='text/event-stream',
                            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
        finally:
            with _aviator_sse_lock:
                if q in _aviator_sse_queues:
                    _aviator_sse_queues.remove(q)

    @app.route('/api/aviator/bet', methods=['POST'])
    def api_aviator_bet():
        uid = get_uid()
        if not uid:
            return jsonify({'error': 'No uid'}), 400
        if not rate_limit(uid):
            return jsonify({'error': 'طلبات كثيرة، انتظر قليلاً'}), 429
        data = request.json or {}
        amount = float(data.get('bet_amount', 0))
        auto_val = float(data.get('auto_val', 0) or 0)
        request_id = str(data.get('request_id', '') or '')
        with _aviator_lock:
            # Bets ONLY during WAITING phase (not starting/flying/crashed)
            if _aviator['phase'] != 'waiting':
                return jsonify({'error': 'انتهت فترة المراهنة'})
            if (_aviator.get('server_ts')
                    and time.time() - _aviator['server_ts'] > WAITING_DURATION + 0.1):
                return jsonify({'error': 'انتهت نافذة الرهان'})
            if uid in _aviator['bets']:
                return jsonify({'error': 'لقد راهنت بالفعل'})
            if not _vex_games():
                return jsonify({'error': 'Games not available'}), 500
            if request_id and _aviator['request_ids'].get(uid) == request_id:
                return jsonify({'error': 'طلب مكرر'}), 409
            if request_id:
                _aviator['request_ids'][uid] = request_id
            success, balance = _gm.deduct_balance(uid, amount)
            if not success:
                return jsonify({'need_deposit': True, 'error': 'رصيد غير كافٍ'})
            _aviator['bets'][uid] = {'amount': amount, 'cashed_out': False,
                                     'cash_mult': 0, 'auto_val': auto_val}
        return jsonify({'success': True, 'balance_after': balance})

    @app.route('/api/aviator/cashout', methods=['POST'])
    def api_aviator_cashout_global():
        uid = get_uid()
        if not uid:
            return jsonify({'error': 'No uid'}), 400
        if not rate_limit(uid):
            return jsonify({'error': 'طلبات كثيرة'}), 429
        data = request.json or {}
        request_id = str(data.get('request_id', '') or '')
        with _aviator_lock:
            if _aviator['phase'] != 'flying':
                return jsonify({'error': 'لا يمكن السحب الآن'})
            bet = _aviator['bets'].get(uid)
            if not bet or bet['cashed_out']:
                return jsonify({'error': 'لا يوجد رهان نشط'})
            if request_id and _aviator['request_ids'].get('co_'+uid) == request_id:
                return jsonify({'error': 'طلب مكرر'}), 409
            if request_id:
                _aviator['request_ids']['co_'+uid] = request_id
            # Server is the SINGLE authority for payout. Client never sets balance.
            mult = _aviator['multiplier']  # authoritative server multiplier
            if mult >= _aviator['crash_point']:
                return jsonify({'success': False, 'error': 'انفجرت الطائرة'})
            payout = bet['amount'] * mult
            balance = _gm.add_balance(uid, payout)
            bet['cashed_out'] = True
            bet['cash_mult'] = mult
            name = _get_name(uid)
        broadcast({'type': 'cashout', 'uid': uid, 'name': name,
                   'amount': round(payout, 2), 'multiplier': round(mult, 2)})
        return jsonify({'success': True, 'payout': round(payout, 2),
                        'multiplier': round(mult, 2), 'balance_after': balance})

    @app.route('/api/aviator/state')
    def api_aviator_state():
        with _aviator_lock:
            return jsonify({
                'phase': _aviator['phase'],
                'multiplier': round(current_multiplier(), 2),
                'crash_point': round(_aviator['crash_point'], 2),
                'round_id': _aviator['round_id'],
                'flight_start': _aviator['flight_start'],
                'history': list(_aviator['history'][-15:]),
            })


# Start the game loop once (daemon, so it dies with the process).
_thread = threading.Thread(target=_game_loop, daemon=True)
_thread.start()