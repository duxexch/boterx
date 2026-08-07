"""
crash_engine.py — standalone Crash game backend module (v2 architecture).

Same architecture pattern as aviator_engine.py:
  State machine: WAITING(5s) -> STARTING(2s) -> FLIGHT(dynamic) -> CRASHED(3s) -> WAITING
  Server broadcasts ONLY: waiting, starting, flight_start, crashed (no per-tick)
  Client computes multiplier locally: mult = e^(0.07 * elapsed)
  Crash formula: 3% house edge, (1-0.03)/(1-R) with provably fair HMAC-SHA256
  Server is sole authority for payout validation.
"""

import math
import time
import json
import random
import secrets
import threading
import queue as _queue
from datetime import datetime

# === Config ===
WAITING_DURATION = 5
STARTING_DURATION = 2
CRASHED_DURATION = 3
TICK_RATE = 0.05
HOUSE_EDGE = 0.03
GROWTH_RATE = 0.07  # mult = e^(0.07 * t_seconds)

# Runtime deps
_gm = None
_vex_games = lambda: False
_pf = None
_is_pf = lambda: False

_crash = {
    'phase': 'idle',
    'multiplier': 1.0,
    'crash_point': 2.0,
    'round_id': 0,
    'flight_start': 0.0,
    'bets': {},
    'history': [],
    'seed_hash': '', 'client_seed': '', 'server_seed': '',
    'server_ts': 0,
    'request_ids': {},
}
_crash_lock = threading.Lock()
_crash_sse_queues = []
_crash_sse_lock = threading.Lock()
_crash_rate = {}


def rate_limit(uid, limit=10, window=5.0):
    now = time.time()
    hits = _crash_rate.get(uid, [])
    hits = [h for h in hits if now - h < window]
    if len(hits) >= limit:
        _crash_rate[uid] = hits
        return False
    hits.append(now)
    _crash_rate[uid] = hits
    return True


def _seed_ready():
    return bool(_crash.get('seed_hash')) and bool(_crash.get('client_seed'))


def calc_crash():
    """3% house edge crash formula with provably fair HMAC-SHA256."""
    if _is_pf() and _seed_ready():
        try:
            sid = 'crashround_%d' % _crash['round_id']
            r = _pf.generate_float(sid, 0.0, 1.0)['value']
        except Exception:
            r = random.random()
    else:
        r = random.random()
    if r < HOUSE_EDGE:
        return 1.00
    crash_point = (1 - HOUSE_EDGE) / (1 - r)
    return max(1.00, round(crash_point, 2))


def current_multiplier():
    if _crash['phase'] != 'flying':
        return 1.0
    elapsed = time.time() - _crash['flight_start']
    return max(1.0, math.exp(GROWTH_RATE * elapsed))


def broadcast(msg):
    payload = json.dumps(msg)
    with _crash_sse_lock:
        for q in _crash_sse_queues:
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


def _game_loop():
    while True:
        # WAITING
        with _crash_lock:
            _crash['phase'] = 'waiting'
            _crash['multiplier'] = 1.0
            _crash['round_id'] += 1
            _crash['bets'] = {}
            _crash['request_ids'] = {}
            _crash['server_ts'] = time.time()
            try:
                if _is_pf():
                    sid = 'crashround_%d' % _crash['round_id']
                    cs = secrets.token_hex(8)
                    seed_info = _pf.create_session(sid, cs)
                    _crash['seed_hash'] = seed_info['seed_hash']
                    _crash['client_seed'] = seed_info['client_seed']
            except Exception:
                _crash['seed_hash'] = ''
                _crash['client_seed'] = secrets.token_hex(8)

        broadcast({'type': 'waiting', 'round_id': _crash['round_id'],
                   'duration': WAITING_DURATION,
                   'history': list(_crash['history'][-15:]),
                   'seed_hash': _crash.get('seed_hash', ''),
                   'client_seed': _crash.get('client_seed', '')})
        time.sleep(WAITING_DURATION)

        # STARTING
        with _crash_lock:
            _crash['phase'] = 'starting'
        broadcast({'type': 'starting', 'round_id': _crash['round_id'],
                   'duration': STARTING_DURATION})
        time.sleep(STARTING_DURATION)

        # FLIGHT
        crash_pt = calc_crash()
        with _crash_lock:
            _crash['phase'] = 'flying'
            _crash['crash_point'] = crash_pt
            _crash['flight_start'] = time.time()

        broadcast({'type': 'flight_start', 'round_id': _crash['round_id'],
                   'game_id': 'GAME005',
                   'server_seed_hash': _crash.get('seed_hash', ''),
                   'client_seed': _crash.get('client_seed', '')})

        total_distributed = 0.0
        total_cashed_out = 0
        total_bets = len(_crash['bets'])
        while True:
            mult = current_multiplier()
            with _crash_lock:
                _crash['multiplier'] = mult
                for uid, bet in list(_crash['bets'].items()):
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

        # CRASHED
        with _crash_lock:
            _crash['phase'] = 'crashed'
            _crash['history'].append(round(crash_pt, 2))
            if len(_crash['history']) > 50:
                _crash['history'].pop(0)
            server_seed = ''
            try:
                if _is_pf() and _crash.get('seed_hash'):
                    rev = _pf.reveal_seed('crashround_%d' % _crash['round_id'])
                    if rev:
                        server_seed = rev.get('server_seed', '')
            except Exception:
                server_seed = ''
            _crash['server_seed'] = server_seed

        broadcast({'type': 'crashed', 'crash_point': round(crash_pt, 2),
                   'total_distributed': round(total_distributed, 2),
                   'total_cashed_out': total_cashed_out,
                   'total_bets': total_bets,
                   'server_seed': server_seed or '',
                   'seed_hash': _crash.get('seed_hash', '')})
        time.sleep(CRASHED_DURATION)


def init_crash_engine(app, get_uid, get_gm, get_pf, is_pf, is_vex):
    """Register Crash routes onto the Flask app with injected deps."""
    global _gm, _pf, _is_pf, _vex_games
    _gm = get_gm()
    _pf = get_pf
    _is_pf = is_pf
    _vex_games = is_vex

    from flask import jsonify, request, Response

    @app.route('/api/crash/stream')
    def api_crash_stream():
        q = _queue.Queue()
        with _crash_sse_lock:
            _crash_sse_queues.append(q)

        def generate():
            with _crash_lock:
                state = {'type': _crash['phase'],
                         'multiplier': round(_crash['multiplier'], 2),
                         'round_id': _crash['round_id'],
                         'history': list(_crash['history'][-15:])}
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
            with _crash_sse_lock:
                if q in _crash_sse_queues:
                    _crash_sse_queues.remove(q)

    @app.route('/api/crash/bet', methods=['POST'])
    def api_crash_bet():
        uid = get_uid()
        if not uid:
            return jsonify({'error': 'No uid'}), 400
        if not rate_limit(uid):
            return jsonify({'error': 'طلبات كثيرة، انتظر قليلاً'}), 429
        data = request.json or {}
        amount = float(data.get('bet_amount', 0))
        auto_val = float(data.get('auto_val', 0) or 0)
        request_id = str(data.get('request_id', '') or '')
        with _crash_lock:
            if _crash['phase'] != 'waiting':
                return jsonify({'error': 'انتهت فترة المراهنة'})
            if (_crash.get('server_ts')
                    and time.time() - _crash['server_ts'] > WAITING_DURATION + 0.1):
                return jsonify({'error': 'انتهت نافذة الرهان'})
            if uid in _crash['bets']:
                return jsonify({'error': 'لقد راهنت بالفعل'})
            if not _vex_games():
                return jsonify({'error': 'Games not available'}), 500
            if request_id and _crash['request_ids'].get(uid) == request_id:
                return jsonify({'error': 'طلب مكرر'}), 409
            if request_id:
                _crash['request_ids'][uid] = request_id
            success, balance = _gm.deduct_balance(uid, amount)
            if not success:
                return jsonify({'need_deposit': True, 'error': 'رصيد غير كافٍ'})
            _crash['bets'][uid] = {'amount': amount, 'cashed_out': False,
                                   'cash_mult': 0, 'auto_val': auto_val}
        return jsonify({'success': True, 'balance_after': balance})

    @app.route('/api/crash/cashout', methods=['POST'])
    def api_crash_cashout_global():
        uid = get_uid()
        if not uid:
            return jsonify({'error': 'No uid'}), 400
        if not rate_limit(uid):
            return jsonify({'error': 'طلبات كثيرة'}), 429
        data = request.json or {}
        request_id = str(data.get('request_id', '') or '')
        with _crash_lock:
            if _crash['phase'] != 'flying':
                return jsonify({'error': 'لا يمكن السحب الآن'})
            bet = _crash['bets'].get(uid)
            if not bet or bet['cashed_out']:
                return jsonify({'error': 'لا يوجد رهان نشط'})
            if request_id and _crash['request_ids'].get('co_'+uid) == request_id:
                return jsonify({'error': 'طلب مكرر'}), 409
            if request_id:
                _crash['request_ids']['co_'+uid] = request_id
            mult = _crash['multiplier']
            if mult >= _crash['crash_point']:
                return jsonify({'success': False, 'error': 'انفجر الصاروخ'})
            payout = bet['amount'] * mult
            balance = _gm.add_balance(uid, payout)
            bet['cashed_out'] = True
            bet['cash_mult'] = mult
            name = _get_name(uid)
        broadcast({'type': 'cashout', 'uid': uid, 'name': name,
                   'amount': round(payout, 2), 'multiplier': round(mult, 2)})
        return jsonify({'success': True, 'payout': round(payout, 2),
                        'multiplier': round(mult, 2), 'balance_after': balance})

    @app.route('/api/crash/state')
    def api_crash_state():
        with _crash_lock:
            return jsonify({
                'phase': _crash['phase'],
                'multiplier': round(current_multiplier(), 2),
                'round_id': _crash['round_id'],
                'history': list(_crash['history'][-15:]),
            })


_thread = threading.Thread(target=_game_loop, daemon=True)
_thread.start()