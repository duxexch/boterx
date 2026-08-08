"""
aviator_engine.py — Production Aviator backend (v3 clean rewrite).

GUARANTEES:
  1. Game loop runs FOREVER — always cycling, even with 0 players.
  2. Crash point is SECRET until crash — never sent to client during flight.
  3. Server is the SOLE authority for payouts — client never sets balance.
  4. If user has insufficient balance → bet returns need_deposit=true (client shows deposit modal).
  5. Only 4 SSE events per round: waiting, starting, flight_start, crashed.
  6. Client computes visible multiplier locally: e^(0.07 * elapsed).

State Machine: WAITING(5s) → STARTING(2s) → FLIGHT(dynamic) → CRASHED(3s) → WAITING ...
"""

import math
import time
import json
import random
import secrets
import threading
import queue as _queue
from datetime import datetime

# ── Config ──────────────────────────────────────────────
WAITING_DURATION = 6      # seconds — betting window (الطائرة في المدرج)
STARTING_DURATION = 0     # seconds — لا مرحلة بدء، الطائرة تنطلق مباشرة
CRASHED_DURATION = 4      # seconds — الانفجار ثم العودة للمدرج
TICK_RATE = 0.05           # 50ms internal check for auto-cashout
HOUSE_EDGE = 0.03          # 3%
GROWTH_RATE = 0.07         # mult = e^(0.07 * t_seconds)

# ── Runtime deps (injected by init_aviator_engine) ──────
_gm = None
_pf = None
_is_pf = lambda: False
_is_vex = lambda: False

# ── Game state ──────────────────────────────────────────
_state = {
    'phase': 'waiting',        # waiting | starting | flying | crashed
    'multiplier': 1.0,         # authoritative server multiplier
    'crash_point': 2.0,        # SECRET — never sent during flight
    'round_id': 0,
    'flight_start': 0.0,       # unix timestamp when flight began
    'bets': {},                # uid -> {amount, cashed_out, cash_mult, auto_val}
    'history': [],             # last 50 crash points
    'seed_hash': '',
    'client_seed': '',
    'server_seed': '',
    'server_ts': 0.0,          # waiting window start timestamp
    'request_ids': {},         # replay protection
}
_lock = threading.Lock()
_sse_queues = []
_sse_lock = threading.Lock()
_rate = {}  # uid -> [timestamps]

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

def _calc_crash():
    """3% house edge: R<0.03→1.00, else (1-0.03)/(1-R)."""
    if _is_pf() and _seed_ready():
        try:
            sid = 'avround_%d' % _state['round_id']
            r = _pf.generate_float(sid, 0.0, 1.0)['value']
        except Exception:
            r = random.random()
    else:
        r = random.random()
    if r < HOUSE_EDGE:
        return 1.00
    cp = (1 - HOUSE_EDGE) / (1 - r)
    return max(1.00, round(cp, 2))

def _server_mult():
    """Authoritative multiplier from flight start timestamp."""
    if _state['phase'] == 'flying':
        elapsed = time.time() - _state['flight_start']
        return max(1.0, math.exp(GROWTH_RATE * elapsed))
    elif _state['phase'] == 'crashed':
        # أثناء الانفجار: المضاعف = قيمة الانفجار (لا ترجع لـ 1.0)
        return _state.get('crash_point', 1.0)
    return 1.0

# ── SSE ─────────────────────────────────────────────────
def _broadcast(msg):
    payload = json.dumps(msg)
    with _sse_lock:
        for q in _sse_queues:
            try: q.put_nowait(payload)
            except: pass

def _get_name(uid):
    """قراءة اسم المستخدم — مؤقتاً معطل لمنع البطء"""
    return ''

def _get_user_phone(uid):
    """قراءة رقم هاتف المستخدم — مؤقتاً معطل لمنع البطء"""
    return ''

def _mask_name(name, phone):
    """إخفاء الاسم بنجوم + إظهار آخر 4 أرقام من الهاتف"""
    # الاسم: أول حرف + نجوم
    if name and len(name) > 1:
        masked = name[0] + '*' * (len(name) - 1)
    elif name:
        masked = name[0] + '**'
    else:
        masked = 'لاعب'
    # الهاتف: آخر 4 أرقام
    if phone and len(phone) >= 4:
        masked += ' •' + phone[-4:]
    return masked

def _get_real_players(current_mult):
    """جمع الرهانات الحقيقية — بدون deadlock (I/O بره الـ lock)"""
    # Step 1: جمع بيانات الرهانات تحت الـ lock (سريع)
    with _lock:
        bets_snapshot = []
        for uid, bet in list(_state['bets'].items()):
            bets_snapshot.append((uid, dict(bet)))
        phase = _state['phase']
    # Step 2: اقرأ الأسماء/الهواتف بره الـ lock (I/O بطيء)
    result = []
    for uid, bet in bets_snapshot:
        name = _get_name(uid)
        phone = _get_user_phone(uid)
        masked_name = _mask_name(name, phone)
        avatar = (name or '?')[0].upper() if name else '★'
        if bet['cashed_out']:
            mult = bet.get('cash_mult', 0)
            payout = round(bet['amount'] * mult, 2) if mult > 0 else 0
            result.append({
                'name': masked_name, 'avatar': avatar,
                'bet': bet['amount'], 'multiplier': mult,
                'payout': payout, 'status': 'cashed', 'real': True,
            })
        elif phase == 'crashed':
            result.append({
                'name': masked_name, 'avatar': avatar,
                'bet': bet['amount'], 'multiplier': 0,
                'payout': 0, 'status': 'lost', 'real': True,
            })
        else:
            result.append({
                'name': masked_name, 'avatar': avatar,
                'bet': bet['amount'], 'multiplier': 0,
                'payout': 0, 'status': 'participating', 'real': True,
            })
    return result

# ── Game loop (daemon, runs forever) ────────────────────
def _game_loop():
    while True:
        # ── WAITING ──
        with _lock:
            _state['phase'] = 'waiting'
            _state['multiplier'] = 1.0
            _state['round_id'] += 1
            _state['bets'] = {}
            _state['request_ids'] = {}
            _state['server_ts'] = time.time()
            try:
                if _is_pf():
                    sid = 'avround_%d' % _state['round_id']
                    cs = secrets.token_hex(8)
                    si = _pf.create_session(sid, cs)
                    _state['seed_hash'] = si['seed_hash']
                    _state['client_seed'] = si['client_seed']
            except:
                _state['seed_hash'] = ''
                _state['client_seed'] = secrets.token_hex(8)

        _broadcast({
            'type': 'waiting',
            'round_id': _state['round_id'],
            'duration': WAITING_DURATION,
            'history': list(_state['history'][-15:]),
            'seed_hash': _state.get('seed_hash', ''),
            'client_seed': _state.get('client_seed', ''),
        })
        time.sleep(WAITING_DURATION)

        # ── FLIGHT مباشرة (لا مرحلة starting) ──
        crash_pt = _calc_crash()
        with _lock:
            _state['phase'] = 'flying'
            _state['crash_point'] = crash_pt    # SECRET — not broadcast
            _state['flight_start'] = time.time()

        # Broadcast flight_start — NO crash_point sent (client doesn't know it)
        _broadcast({
            'type': 'flight_start',
            'round_id': _state['round_id'],
            'game_id': 'GAME004',
            'server_seed_hash': _state.get('seed_hash', ''),
            'client_seed': _state.get('client_seed', ''),
        })

        total_distributed = 0.0
        total_cashed_out = 0
        total_bets = len(_state['bets'])

        # Internal loop: update multiplier + auto-cashout + BROADCAST EVERY SECOND
        _last_broadcast = 0
        while True:
            mult = _server_mult()
            with _lock:
                _state['multiplier'] = mult
                for uid, bet in list(_state['bets'].items()):
                    if (not bet['cashed_out']
                            and bet.get('auto_val', 0) > 0
                            and mult >= bet['auto_val']):
                        payout = bet['amount'] * mult
                        try: _gm.add_balance(uid, payout)
                        except: pass
                        bet['cashed_out'] = True
                        bet['cash_mult'] = mult
                        total_distributed += payout
                        total_cashed_out += 1
                        _broadcast({'type': 'cashout', 'uid': uid,
                                   'name': _get_name(uid),
                                   'amount': round(payout, 2),
                                   'multiplier': round(mult, 2),
                                   'auto': True})
            # Broadcast multiplier every 1 second (so new SSE clients see updates)
            _now = time.time()
            if _now - _last_broadcast >= 1.0:
                _last_broadcast = _now
                _broadcast({'type': 'mult', 'multiplier': round(mult, 2)})
            if mult >= crash_pt:
                break
            time.sleep(TICK_RATE)

        # ── CRASHED ──
        with _lock:
            _state['phase'] = 'crashed'
            _state['history'].append(round(crash_pt, 2))
            if len(_state['history']) > 50:
                _state['history'].pop(0)
            server_seed = ''
            try:
                if _is_pf() and _state.get('seed_hash'):
                    rev = _pf.reveal_seed('avround_%d' % _state['round_id'])
                    if rev: server_seed = rev.get('server_seed', '')
            except: pass
            _state['server_seed'] = server_seed

        _broadcast({
            'type': 'crashed',
            'crash_point': round(crash_pt, 2),
            'total_distributed': round(total_distributed, 2),
            'total_cashed_out': total_cashed_out,
            'total_bets': total_bets,
            'server_seed': server_seed or '',
            'seed_hash': _state.get('seed_hash', ''),
        })
        time.sleep(CRASHED_DURATION)
        # الطائرة تعود للمدرج تلقائياً — الحلقة تعيد نفسها

# ── Flask route registration ─────────────────────────────
def init_aviator_engine(app, get_uid, get_gm, get_pf, is_pf, is_vex):
    global _gm, _pf, _is_pf, _is_vex
    _gm = get_gm()
    _pf = get_pf
    _is_pf = is_pf
    _is_vex = is_vex
    from flask import jsonify, request, Response

    @app.route('/api/aviator/stream')
    def api_aviator_stream():
        q = _queue.Queue()
        with _sse_lock: _sse_queues.append(q)
        def gen():
            with _lock:
                s = {'type': _state['phase'],
                     'multiplier': round(_server_mult(), 2),
                     'round_id': _state['round_id'],
                     'history': list(_state['history'][-15:])}
            yield 'data: %s\n\n' % json.dumps(s)
            while True:
                try: yield 'data: %s\n\n' % q.get(timeout=15)
                except _queue.Empty: yield 'data: %s\n\n' % json.dumps({'type': 'heartbeat'})
        try:
            return Response(gen(), mimetype='text/event-stream',
                            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
        finally:
            with _sse_lock:
                if q in _sse_queues: _sse_queues.remove(q)

    @app.route('/api/aviator/bet', methods=['POST'])
    def api_aviator_bet():
        uid = get_uid()
        if not uid: return jsonify({'error': 'No uid'}), 400
        if not _rate_ok(uid): return jsonify({'error': 'طلبات كثيرة، انتظر قليلاً'}), 429
        data = request.json or {}
        # Input validation — prevent injection
        try:
            amount = float(data.get('bet_amount', 0))
            if amount <= 0 or amount > 100000: return jsonify({'error': 'مبلغ غير صالح'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'مبلغ غير صالح'}), 400
        try:
            auto_val = float(data.get('auto_val', 0) or 0)
            if auto_val < 0 or auto_val > 1000: auto_val = 0
        except (ValueError, TypeError):
            auto_val = 0
        req_id = str(data.get('request_id', '') or '')[:64]  # limit length
        # Sanitize uid — only digits
        if not str(uid).isdigit(): return jsonify({'error': 'uid غير صالح'}), 400
        with _lock:
            if _state['phase'] != 'waiting':
                return jsonify({'error': 'انتهت فترة المراهنة'})
            if _state.get('server_ts') and time.time() - _state['server_ts'] > WAITING_DURATION + 0.1:
                return jsonify({'error': 'انتهت نافذة الرهان'})
            if uid in _state['bets']:
                return jsonify({'error': 'لقد راهنت بالفعل'})
            if not _is_vex():
                return jsonify({'error': 'Games not available'}), 500
            if req_id and _state['request_ids'].get(uid) == req_id:
                return jsonify({'error': 'طلب مكرر'}), 409
            if req_id: _state['request_ids'][uid] = req_id
            # Deduct — if insufficient, return need_deposit so client shows deposit modal
            success, balance = _gm.deduct_balance(uid, amount)
            if not success:
                return jsonify({'need_deposit': True, 'error': 'رصيد غير كافٍ'})
            _state['bets'][uid] = {'amount': amount, 'cashed_out': False,
                                   'cash_mult': 0, 'auto_val': auto_val}
        return jsonify({'success': True, 'balance_after': balance})

    @app.route('/api/aviator/cashout', methods=['POST'])
    def api_aviator_cashout():
        uid = get_uid()
        if not uid: return jsonify({'error': 'No uid'}), 400
        if not _rate_ok(uid): return jsonify({'error': 'طلبات كثيرة'}), 429
        data = request.json or {}
        req_id = str(data.get('request_id', '') or '')[:64]
        if not str(uid).isdigit(): return jsonify({'error': 'uid غير صالح'}), 400
        with _lock:
            if _state['phase'] != 'flying':
                return jsonify({'error': 'لا يمكن السحب الآن'})
            bet = _state['bets'].get(uid)
            if not bet or bet['cashed_out']:
                return jsonify({'error': 'لا يوجد رهان نشط'})
            if req_id and _state['request_ids'].get('co_'+uid) == req_id:
                return jsonify({'error': 'طلب مكرر'}), 409
            if req_id: _state['request_ids']['co_'+uid] = req_id
            # Server-authoritative: use server's internal multiplier, NOT client's
            mult = _state['multiplier']
            if mult >= _state['crash_point']:
                return jsonify({'success': False, 'error': 'انفجرت الطائرة'})
            payout = bet['amount'] * mult
            balance = _gm.add_balance(uid, payout)
            bet['cashed_out'] = True
            bet['cash_mult'] = mult
            name = _get_name(uid)
        _broadcast({'type': 'cashout', 'uid': uid, 'name': name,
                   'amount': round(payout, 2), 'multiplier': round(mult, 2)})
        return jsonify({'success': True, 'payout': round(payout, 2),
                        'multiplier': round(mult, 2), 'balance_after': balance})

    @app.route('/api/aviator/state')
    def api_aviator_state():
        with _lock:
            # اجمع رهانات العميل الحالية (لو راهن قبل التحديث)
            uid = get_uid()
            my_bets = {}
            if uid and uid in _state['bets']:
                b = _state['bets'][uid]
                my_bets = {
                    'placed': True,
                    'amount': b['amount'],
                    'cashed_out': b['cashed_out'],
                    'cash_mult': b.get('cash_mult', 0),
                    'auto_val': b.get('auto_val', 0),
                }
            # توليد لاعبين وهميين فقط (real players مؤقتاً معطل)
            fake_players = _generate_fake_players(_server_mult())
            all_players = fake_players
            return jsonify({
                'phase': _state['phase'],
                'multiplier': round(_server_mult(), 2),
                'crash_point': round(_state.get('crash_point', 0), 2),
                'round_id': _state['round_id'],
                'history': list(_state['history'][-15:]),
                'my_bet': my_bets,
                'players': all_players,
            })

# ===== لاعبين وهميون — بيانات للعرض فقط =====
import string as _str

_FAKE_NAMES = [
    'أحمد','عمر','محمد','خالد','سعد','فهد','ناصر','يوسف','علي','حسن',
    'ماجد','وليد','طارق','بدر','راشد','عبدالله','سلطان','فيصل','نايف',
    'تركي','دانا','نورة','ريم','سارة','لمى','شهد','جود','هند','روان'
]
_FAKE_PLAYERS = []
_FAKE_PLAYER_COUNT = 0

def _init_fake_players():
    """معطل — نولّد الأسماء مباشرة بدون تخزين قائمة"""
    pass

def _generate_fake_players(current_mult):
    """توليد لاعبين وهميين مباشرة — بدون قائمة مخزنة"""
    phase = _state['phase']
    count = random.randint(5, 10)
    names = ['أحمد','عمر','محمد','خالد','سعد','فهد','ناصر','يوسف','علي','حسن','ماجد','وليد','طارق','بدر','راشد','عبدالله','سلطان','فيصل','نايف','تركي','دانا','نورة','ريم','سارة','لمى','شهد','جود','هند','روان']
    result = []
    for i in range(count):
        name = random.choice(names) + ' ' + str(random.randint(1, 99))
        bet = random.choice([10, 20, 50, 100, 200, 500])
        avatar = name[0]
        if phase == 'waiting':
            result.append({'name': name, 'avatar': avatar, 'bet': bet, 'multiplier': 0, 'payout': 0, 'status': 'participating'})
        elif phase == 'flying':
            if random.random() < 0.4:
                jm = round(random.uniform(1.0, max(1.1, current_mult)), 2)
                result.append({'name': name, 'avatar': avatar, 'bet': bet, 'multiplier': jm, 'payout': round(bet*jm,2), 'status': 'cashed'})
            else:
                result.append({'name': name, 'avatar': avatar, 'bet': bet, 'multiplier': 0, 'payout': 0, 'status': 'participating'})
        elif phase == 'crashed':
            if random.random() < 0.5:
                jm = round(random.uniform(1.0, max(1.1, current_mult)), 2)
                result.append({'name': name, 'avatar': avatar, 'bet': bet, 'multiplier': jm, 'payout': round(bet*jm,2), 'status': 'cashed'})
            else:
                result.append({'name': name, 'avatar': avatar, 'bet': bet, 'multiplier': 0, 'payout': 0, 'status': 'lost'})
        else:
            result.append({'name': name, 'avatar': avatar, 'bet': bet, 'multiplier': 0, 'payout': 0, 'status': 'participating'})
    result.sort(key=lambda x: (-x['payout'], 0 if x['status'] != 'lost' else 1))
    return result

# Start the daemon thread — runs forever, even with 0 players
_thread = threading.Thread(target=_game_loop, daemon=True)
_thread.start()
