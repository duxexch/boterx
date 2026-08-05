#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Boterx Web Dashboard v2 — Flask Application
لوحة تحكم ويب احترافية متكاملة لإدارة بوت Boterx
"""

import os
import csv
import json
import io
import hmac
import hashlib
import secrets
import random
import zipfile
import threading
import queue as _queue
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import parse_qs

from flask import (Flask, render_template, request, redirect, url_for,
                   session, jsonify, Response, flash, send_file, g)

# ===== Configuration =====
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', '8080'))
DASHBOARD_HOST = os.getenv('DASHBOARD_HOST', '0.0.0.0')
SECRET_KEY = os.getenv('DASHBOARD_SECRET_KEY', secrets.token_hex(32))

ADMIN_IDS = [a.strip() for a in os.getenv('ADMIN_USER_IDS', '').split(',') if a.strip()]
ADMIN_PASSWORD = os.getenv('DASHBOARD_PASSWORD', 'boterx_admin_2026')

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

# ===== Real-time Notification Queue =====
_notification_queues = []  # list of queue.Queue, one per connected SSE client
_nq_lock = threading.Lock()

def push_notification(notif_type, title, message, data=None):
    """Push a real-time notification to all connected dashboard clients."""
    payload = json.dumps({
        'type': notif_type,
        'title': title,
        'message': message,
        'data': data or {},
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
    with _nq_lock:
        for q in _notification_queues:
            try:
                q.put_nowait(payload)
            except:
                pass

# ===== CSV Helpers =====
def read_csv(filename):
    filepath = os.path.join(BASE_DIR, filename)
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            return list(csv.DictReader(f))
    except Exception as e:
        print(f"Error reading {filename}: {e}")
        return []

def write_csv(filename, rows, fieldnames):
    filepath = os.path.join(BASE_DIR, filename)
    with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def append_csv(filename, row, fieldnames):
    filepath = os.path.join(BASE_DIR, filename)
    with open(filepath, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writerow({k: row.get(k, '') for k in fieldnames})

def get_fieldnames(filename, default_fields):
    rows = read_csv(filename)
    if rows:
        return list(rows[0].keys())
    return default_fields

def log_action(action_type, details=''):
    """تسجيل إجراء الأدمن"""
    entry = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'admin_id': session.get('admin_id', 'unknown'),
        'action_type': action_type,
        'details': details
    }
    append_csv('admin_actions_log.csv', entry,
               ['timestamp', 'admin_id', 'action_type', 'details'])

# ===== Auth =====
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def api_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

# ===== Telegram WebApp Auth =====
# Load BOT_TOKEN from .env if not in environment
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
if not BOT_TOKEN:
    try:
        env_path = os.path.join(BASE_DIR, '.env')
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('BOT_TOKEN='):
                        BOT_TOKEN = line.split('=', 1)[1].strip()
                        break
    except:
        pass

def validate_telegram_init_data(init_data_str):
    """Validate Telegram WebApp initData using HMAC-SHA256.
    Returns (user_id_str, user_dict) if valid, (None, None) if invalid.
    """
    if not init_data_str:
        return None, None
    try:
        parsed = parse_qs(init_data_str)
        hash_from_client = parsed.get('hash', [None])[0]
        if not hash_from_client:
            return None, None
        # Build data-check string: sorted key=value pairs (excluding 'hash')
        data_check = {}
        for k, v in parsed.items():
            if k != 'hash':
                data_check[k] = v[0]
        data_check_string = '\n'.join(f'{k}={v}' for k, v in sorted(data_check.items()))
        # secret_key = HMAC_SHA256(bot_token, "WebAppData")
        secret_key = hmac.new(BOT_TOKEN.encode(), b'WebAppData', hashlib.sha256).digest()
        # calculated_hash = HMAC_SHA256(secret_key, data_check_string)
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        # Compare
        if not hmac.compare_digest(calculated_hash, hash_from_client):
            return None, None
        # Extract user
        user_json = data_check.get('user', '')
        if user_json:
            user_obj = json.loads(user_json)
            return str(user_obj.get('id', '')), user_obj
        return None, None
    except Exception:
        return None, None

def webapp_auth(f):
    """Decorator: validates Telegram WebApp initData on game-facing API endpoints.
    Reads initData from 'X-Telegram-Init-Data' header or 'initData' body/query param.
    Sets g.telegram_user_id and g.telegram_user on success.
    Falls back to uid param if BOT_TOKEN not configured (dev mode).
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not BOT_TOKEN:
            # Dev mode — no token configured, allow through with uid
            g.telegram_user_id = request.args.get('uid', '') or (request.json or {}).get('uid', '') if request.is_json else request.args.get('uid', '')
            g.telegram_user = None
            return f(*args, **kwargs)
        # Try header first, then body/query
        init_data = request.headers.get('X-Telegram-Init-Data', '')
        if not init_data:
            if request.is_json:
                init_data = (request.json or {}).get('initData', '')
            else:
                init_data = request.args.get('initData', '')
        if not init_data:
            # Fallback: allow uid-based access for WebApps that don't send initData
            uid = request.args.get('uid', '')
            if not uid and request.is_json:
                uid = (request.json or {}).get('uid', '')
            if uid:
                g.telegram_user_id = uid
                g.telegram_user = None
                return f(*args, **kwargs)
            return jsonify({'error': 'Missing authentication', 'code': 'NO_INIT_DATA'}), 403
        uid, user_obj = validate_telegram_init_data(init_data)
        if not uid:
            return jsonify({'error': 'Invalid authentication', 'code': 'INVALID_INIT_DATA'}), 403
        g.telegram_user_id = uid
        g.telegram_user = user_obj
        return f(*args, **kwargs)
    return decorated

def get_request_uid():
    """Get the authenticated user ID from request context.
    Uses g.telegram_user_id if set by webapp_auth, otherwise falls back to uid param.
    """
    uid = getattr(g, 'telegram_user_id', None)
    if uid:
        return uid
    # Fallback for admin endpoints or dev mode
    uid = request.args.get('uid', '')
    if not uid and request.is_json:
        uid = (request.json or {}).get('uid', '')
    return uid

# ===== Routes — Pages =====

@app.route('/')
@login_required
def index():
    return redirect(url_for('dashboard'), code=303)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        admin_id = request.form.get('admin_id', '').strip()
        password = request.form.get('password', '')
        if admin_id in ADMIN_IDS and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['admin_id'] = admin_id
            session['login_time'] = datetime.now().isoformat()
            log_action('login', f'Admin {admin_id} logged in')
            return redirect(url_for('dashboard'), code=303)
        elif admin_id not in ADMIN_IDS:
            error = 'معرف الأدمن غير صحيح'
        else:
            error = 'كلمة المرور غير صحيحة'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    log_action('logout', '')
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', active_page='dashboard')

@app.route('/transactions')
@login_required
def page_transactions():
    return render_template('transactions.html', active_page='transactions')

@app.route('/users')
@login_required
def page_users():
    return render_template('users.html', active_page='users')

@app.route('/matching')
@login_required
def page_matching():
    return render_template('matching.html', active_page='matching')

@app.route('/svrp')
@login_required
def page_svrp():
    return render_template('svrp.html', active_page='svrp')

@app.route('/trading')
@login_required
def page_trading():
    return render_template('trading.html', active_page='trading')

@app.route('/lottery')
@login_required
def page_lottery():
    return render_template('lottery.html', active_page='lottery')

@app.route('/wheel')
@login_required
def page_wheel():
    return render_template('wheel.html', active_page='wheel')

@app.route('/webapp/snatch')
def webapp_snatch():
    """صفحة لعبة اختطف — Web App ديناميكي داخل تيليجرام"""
    gifts = []
    try:
        with open('wheel_gifts.csv', 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('is_active') == 'yes':
                    gifts.append({'id': row.get('id',''), 'text': row.get('gift_text',''), 'link': row.get('affiliate_link','')})
    except:
        pass
    return render_template('snatch_game.html', gifts_json=json.dumps(gifts))

@app.route('/api/wheel/my-spins')
@api_auth
def api_wheel_my_spins():
    """عدد دورات المستخدم في جولة محددة"""
    round_id = request.args.get('round_id', '')
    # محاولة الحصول على user_id من session
    admin_id = session.get('admin_id', '')
    spins = read_csv('wheel_spins.csv')
    user_spins = [s for s in spins if s.get('round_id') == round_id]
    return jsonify({
        'total_spins': len(user_spins),
        'spins': user_spins[-10:]
    })

@app.route('/companies')
@login_required
def page_companies():
    return render_template('companies.html', active_page='companies')

@app.route('/payment-methods')
@login_required
def page_payment_methods():
    return render_template('payment_methods.html', active_page='payment_methods')

@app.route('/apps')
@login_required
def page_apps():
    return render_template('apps.html', active_page='apps')

@app.route('/referrals')
@login_required
def page_referrals():
    return render_template('referrals.html', active_page='referrals')

@app.route('/channels')
@login_required
def page_channels():
    return render_template('channels.html', active_page='channels')

@app.route('/bots')
@login_required
def page_bots():
    return render_template('bots.html', active_page='bots')

@app.route('/settings')
@login_required
def page_settings():
    return render_template('settings.html', active_page='settings')

@app.route('/complaints')
@login_required
def page_complaints():
    return render_template('complaints.html', active_page='complaints')

@app.route('/broadcast')
@login_required
def page_broadcast():
    return render_template('broadcast.html', active_page='broadcast')

@app.route('/admins')
@login_required
def page_admins():
    return render_template('admin_management.html', active_page='admins')

@app.route('/themes')
@login_required
def page_themes():
    return render_template('themes.html', active_page='themes')

@app.route('/exchange-addresses')
@login_required
def page_exchange_addresses():
    return render_template('exchange_addresses.html', active_page='exchange_addresses')

@app.route('/send-message')
@login_required
def page_send_message():
    return render_template('send_message.html', active_page='send_message')

@app.route('/backup')
@login_required
def page_backup():
    return render_template('backup.html', active_page='backup')

@app.route('/statistics')
@login_required
def page_statistics():
    return render_template('statistics.html', active_page='statistics')

# ===== API — Stats =====

@app.route('/api/stats')
@api_auth
def api_stats():
    stats = {
        'users': {'total': 0, 'today': 0, 'banned': 0, 'verified': 0},
        'transactions': {'total': 0, 'pending': 0, 'approved': 0, 'rejected': 0, 'today': 0,
                         'pending_volume': 0.0, 'approved_volume': 0.0},
        'matches': {'active': 0, 'pending': 0, 'completed': 0, 'disputed': 0},
        'lottery': {'participants': 0, 'winners': 0, 'distributed': 0.0, 'tickets_sold': 0},
        'wheel': {'participants': 0, 'total_spins': 0},
        'trading': {'pending_orders': 0, 'total_orders': 0},
        'svrp': {'total_wallets': 0, 'total_balance': 0.0, 'total_frozen': 0.0, 'pending_requests': 0},
        'volume': {'today': 0.0, 'week': 0.0, 'month': 0.0, 'all_time': 0.0},
        'companies': {'total': 0, 'active': 0},
        'complaints': {'total': 0, 'open': 0},
    }

    today = datetime.now().strftime('%Y-%m-%d')
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    # Users
    users = read_csv('users.csv')
    stats['users']['total'] = len(users)
    stats['users']['banned'] = sum(1 for u in users if u.get('is_banned') == 'yes')
    stats['users']['verified'] = sum(1 for u in users if u.get('phone_verified') == 'yes')
    stats['users']['today'] = sum(1 for u in users if u.get('date', '').startswith(today))

    # Transactions
    txns = read_csv('transactions.csv')
    stats['transactions']['total'] = len(txns)
    for t in txns:
        status = t.get('status', '')
        if status == 'pending':
            stats['transactions']['pending'] += 1
            try: stats['transactions']['pending_volume'] += float(t.get('amount', 0))
            except: pass
        elif status == 'approved':
            stats['transactions']['approved'] += 1
            try:
                amt = float(t.get('amount', 0))
                stats['transactions']['approved_volume'] += amt
                tdate = t.get('date', '')
                if tdate.startswith(today): stats['volume']['today'] += amt
                if tdate >= week_ago: stats['volume']['week'] += amt
                if tdate >= month_ago: stats['volume']['month'] += amt
                stats['volume']['all_time'] += amt
            except: pass
        elif status == 'rejected':
            stats['transactions']['rejected'] += 1
        if t.get('date', '').startswith(today):
            stats['transactions']['today'] += 1

    # Matches
    matches = read_csv('matches.csv')
    for m in matches:
        s = m.get('status', '')
        if s not in ('completed', 'cancelled'): stats['matches']['active'] += 1
        if s == 'completed': stats['matches']['completed'] += 1
        if s == 'disputed': stats['matches']['disputed'] += 1
    match_reqs = read_csv('match_requests.csv')
    stats['matches']['pending'] = sum(1 for r in match_reqs if r.get('status') == 'waiting')

    # Lottery
    lot_rounds = read_csv('lottery_rounds.csv')
    lot_tickets = read_csv('lottery_tickets.csv')
    lot_winners = read_csv('lottery_winners.csv')
    active_lot = next((r for r in lot_rounds if r.get('status') == 'active'), None)
    if active_lot:
        lot_id = active_lot.get('id', '')
        verified_tickets = [t for t in lot_tickets if t.get('round_id') == lot_id and t.get('payment_verified') == 'yes']
        stats['lottery']['participants'] = len(set(t.get('user_id') for t in verified_tickets))
        stats['lottery']['winners'] = int(active_lot.get('winner_count', 0))
        stats['lottery']['tickets_sold'] = len(verified_tickets)
    stats['lottery']['distributed'] = sum(float(w.get('prize_amount', 0) or 0) for w in lot_winners)

    # Wheel
    wheel_rounds = read_csv('wheel_rounds.csv')
    wheel_spins = read_csv('wheel_spins.csv')
    active_wheel = next((r for r in wheel_rounds if r.get('status') == 'active'), None)
    if active_wheel:
        wid = active_wheel.get('id', '')
        round_spins = [s for s in wheel_spins if s.get('round_id') == wid]
        stats['wheel']['participants'] = len(set(s.get('user_id') for s in round_spins))
        stats['wheel']['total_spins'] = len(round_spins)

    # Trading
    trade_orders = read_csv('trade_orders.csv')
    stats['trading']['total_orders'] = len(trade_orders)
    stats['trading']['pending_orders'] = sum(1 for o in trade_orders if o.get('status') == 'pending')

    # SVRP
    wallets = read_csv('svrp_wallets.csv')
    stats['svrp']['total_wallets'] = len(wallets)
    for w in wallets:
        try:
            stats['svrp']['total_balance'] += float(w.get('balance', 0) or 0)
            stats['svrp']['total_frozen'] += float(w.get('pending_balance', 0) or 0)
        except: pass
    rec_reqs = read_csv('recovery_requests.csv')
    stats['svrp']['pending_requests'] = sum(1 for r in rec_reqs if r.get('status') == 'pending')

    # Companies
    companies = read_csv('companies.csv')
    stats['companies']['total'] = len(companies)
    stats['companies']['active'] = sum(1 for c in companies if c.get('is_active') == 'yes')

    # Complaints
    complaints = read_csv('complaints.csv')
    stats['complaints']['total'] = len(complaints)
    stats['complaints']['open'] = sum(1 for c in complaints if c.get('status') not in ('resolved', 'closed'))

    return jsonify(stats)

@app.route('/api/stats/live')
@api_auth
def api_stats_live():
    def generate():
        import time
        while True:
            data = {
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'users_total': len(read_csv('users.csv')),
                'pending_txns': sum(1 for t in read_csv('transactions.csv') if t.get('status') == 'pending'),
                'active_matches': sum(1 for m in read_csv('matches.csv') if m.get('status') not in ('completed', 'cancelled')),
                'pending_matches': sum(1 for r in read_csv('match_requests.csv') if r.get('status') == 'waiting'),
                'lottery_participants': 0,
                'wheel_participants': 0,
            }
            yield f"data: {json.dumps(data)}\n\n"
            time.sleep(5)
    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/notifications/stream')
@api_auth
def api_notifications_stream():
    """SSE stream for real-time deposit/withdrawal notifications."""
    q = _queue.Queue()
    with _nq_lock:
        _notification_queues.append(q)
    def generate():
        import time
        # Send initial connection confirmation
        yield f"data: {json.dumps({'type': 'connected', 'message': 'Connected'})}\n\n"
        while True:
            try:
                payload = q.get(timeout=15)
                yield f"data: {payload}\n\n"
            except _queue.Empty:
                # Heartbeat to keep connection alive
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
    try:
        return Response(generate(), mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
    finally:
        with _nq_lock:
            if q in _notification_queues:
                _notification_queues.remove(q)

@app.route('/api/stats/charts')
@api_auth
def api_stats_charts():
    """بيانات الرسوم البيانية"""
    txns = read_csv('transactions.csv')

    # معاملات آخر 30 يوم
    daily = {}
    for t in txns:
        date = t.get('date', '')[:10]
        if date:
            daily[date] = daily.get(date, 0) + 1

    labels = []
    txn_data = []
    for i in range(30):
        d = (datetime.now() - timedelta(days=29 - i)).strftime('%Y-%m-%d')
        labels.append(d)
        txn_data.append(daily.get(d, 0))

    # توزيع الحالات
    status_counts = {'pending': 0, 'approved': 0, 'rejected': 0}
    for t in txns:
        s = t.get('status', 'pending')
        if s in status_counts:
            status_counts[s] += 1

    # أفضل 5 شركات
    company_vol = {}
    for t in txns:
        if t.get('status') == 'approved':
            company = t.get('company', 'غير محدد')
            try:
                company_vol[company] = company_vol.get(company, 0) + float(t.get('amount', 0))
            except: pass
    top_companies = sorted(company_vol.items(), key=lambda x: x[1], reverse=True)[:5]

    # تسجيلات المستخدمين آخر 14 يوم
    users = read_csv('users.csv')
    user_daily = {}
    for u in users:
        date = u.get('date', '')[:10]
        if date:
            user_daily[date] = user_daily.get(date, 0) + 1

    user_labels = []
    user_data = []
    for i in range(14):
        d = (datetime.now() - timedelta(days=13 - i)).strftime('%Y-%m-%d')
        user_labels.append(d)
        user_data.append(user_daily.get(d, 0))

    return jsonify({
        'txn_chart': {'labels': labels, 'data': txn_data},
        'status_chart': status_counts,
        'companies_chart': {'labels': [c[0] for c in top_companies], 'data': [c[1] for c in top_companies]},
        'users_chart': {'labels': user_labels, 'data': user_data}
    })

# ===== API — Transactions =====

@app.route('/api/transactions')
@api_auth
def api_transactions():
    status = request.args.get('status', '')
    tx_type = request.args.get('type', '')
    search = request.args.get('search', '')
    page = int(request.args.get('page', '1'))
    per_page = int(request.args.get('per_page', '20'))

    txns = read_csv('transactions.csv')
    txns.reverse()

    if status:
        txns = [t for t in txns if t.get('status') == status]
    if tx_type:
        txns = [t for t in txns if t.get('type') == tx_type]
    if search:
        sl = search.lower()
        txns = [t for t in txns if sl in t.get('name', '').lower() or
                sl in t.get('customer_id', '').lower() or
                sl in t.get('id', '').lower() or
                sl in t.get('company', '').lower()]

    total = len(txns)
    start = (page - 1) * per_page
    end = start + per_page

    # إحصائيات سريعة
    stats = {
        'total_amount': sum(float(t.get('amount', 0) or 0) for t in txns),
        'avg_amount': 0,
        'pending_count': sum(1 for t in txns if t.get('status') == 'pending'),
        'approved_volume': sum(float(t.get('amount', 0) or 0) for t in txns if t.get('status') == 'approved'),
    }
    stats['avg_amount'] = stats['total_amount'] / len(txns) if txns else 0

    return jsonify({
        'transactions': txns[start:end],
        'total': total, 'page': page, 'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
        'stats': stats
    })

@app.route('/api/transactions/<txn_id>/approve', methods=['POST'])
@api_auth
def api_approve_txn(txn_id):
    data = request.json or {}
    new_amount = data.get('amount', '')
    txns = read_csv('transactions.csv')
    fieldnames = get_fieldnames('transactions.csv', ['id','customer_id','telegram_id','name','type','company','wallet_number','amount','exchange_address','status','date','admin_note','processed_by','currency'])
    old_amount = ''
    customer_tid = ''
    trans = None
    for t in txns:
        if t.get('id') == txn_id:
            old_amount = t.get('amount', '')
            customer_tid = t.get('telegram_id', '')
            trans = t
            t['status'] = 'approved'
            t['processed_by'] = session.get('admin_id', '')
            if new_amount:
                t['amount'] = str(new_amount)
            break
    write_csv('transactions.csv', txns, fieldnames)
    log_action('approve_transaction', f'{txn_id} amount: {old_amount} -> {new_amount or old_amount}')
    # VEX deposit: async add balance + notify player (non-blocking)
    if trans and 'VEX' in trans.get('admin_note', ''):
        import threading as _th
        # Capture all values BEFORE starting thread (session is thread-local)
        _uid = trans.get('telegram_id', '')
        _amt = float(new_amount or old_amount or 0)
        _txn = txn_id
        _admin = session.get('admin_id', '')
        def _vex_bg():
            try:
                if _VEX_GAMES and _uid and _amt > 0:
                    _gm.add_balance(_uid, _amt)
                    # Update quick_deposits.csv
                    try:
                        import csv as _csv2
                        _rows = []
                        _qd = os.path.join(BASE_DIR, 'quick_deposits.csv')
                        with open(_qd, 'r', encoding='utf-8-sig') as _f:
                            _r = _csv2.DictReader(_f)
                            _fn = _r.fieldnames
                            _rows = list(_r)
                        for _row in _rows:
                            if _row.get('user_id') == str(_uid) and _row.get('status') == 'pending':
                                _row['status'] = 'approved'
                                _row['approved_by'] = str(_admin)
                                _row['approved_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        with open(_qd, 'w', newline='', encoding='utf-8-sig') as _f:
                            _w = _csv2.DictWriter(_f, fieldnames=_fn)
                            _w.writeheader()
                            _w.writerows(_rows)
                    except: pass
                    # Telegram notify
                    if BOT_TOKEN:
                        try:
                            import urllib.request as _u2
                            _msg = f"✅ تمت الموافقة على إيداعك!\n\n💰 المبلغ: {_amt:.0f}\n🎮 تم إضافته لمحفظة VEX\n🆔 {_txn}"
                            _u2.urlopen(_u2.Request(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                                data=json.dumps({'chat_id': int(_uid), 'text': _msg, 'parse_mode': 'HTML'}).encode('utf-8'),
                                headers={'Content-Type': 'application/json'}), timeout=5)
                        except: pass
                    push_notification('vex_deposit', '✅ إيداع VEX', f'{_uid}: {_amt}', {'uid': _uid, 'amount': _amt})
            except Exception as _e:
                print(f"VEX bg error: {_e}")
        _th.Thread(target=_vex_bg, daemon=True).start()
    return jsonify({'success': True, 'old_amount': old_amount, 'new_amount': new_amount or old_amount})

@app.route('/api/transactions/<txn_id>/reject', methods=['POST'])
@api_auth
def api_reject_txn(txn_id):
    reason = request.json.get('reason', '') if request.json else ''
    txns = read_csv('transactions.csv')
    fieldnames = get_fieldnames('transactions.csv', ['id','customer_id','telegram_id','name','type','company','wallet_number','amount','exchange_address','status','date','admin_note','processed_by','currency'])
    for t in txns:
        if t.get('id') == txn_id:
            t['status'] = 'rejected'
            t['admin_note'] = reason
            t['processed_by'] = session.get('admin_id', '')
            break
    write_csv('transactions.csv', txns, fieldnames)
    log_action('reject_transaction', f'{txn_id}: {reason}')
    return jsonify({'success': True})

@app.route('/api/transactions/bulk-approve', methods=['POST'])
@api_auth
def api_bulk_approve():
    ids = request.json.get('ids', []) if request.json else []
    txns = read_csv('transactions.csv')
    fieldnames = get_fieldnames('transactions.csv', ['id','customer_id','telegram_id','name','type','company','wallet_number','amount','exchange_address','status','date','admin_note','processed_by','currency'])
    count = 0
    for t in txns:
        if t.get('id') in ids:
            t['status'] = 'approved'
            t['processed_by'] = session.get('admin_id', '')
            count += 1
    write_csv('transactions.csv', txns, fieldnames)
    log_action('bulk_approve', f'{count} transactions')
    return jsonify({'success': True, 'count': count})

@app.route('/api/transactions/bulk-reject', methods=['POST'])
@api_auth
def api_bulk_reject():
    ids = request.json.get('ids', []) if request.json else []
    reason = request.json.get('reason', 'رفض جماعي') if request.json else 'رفض جماعي'
    txns = read_csv('transactions.csv')
    fieldnames = get_fieldnames('transactions.csv', ['id','customer_id','telegram_id','name','type','company','wallet_number','amount','exchange_address','status','date','admin_note','processed_by','currency'])
    count = 0
    for t in txns:
        if t.get('id') in ids:
            t['status'] = 'rejected'
            t['admin_note'] = reason
            t['processed_by'] = session.get('admin_id', '')
            count += 1
    write_csv('transactions.csv', txns, fieldnames)
    log_action('bulk_reject', f'{count} transactions: {reason}')
    return jsonify({'success': True, 'count': count})

@app.route('/api/transactions/export')
@api_auth
def api_export_transactions():
    """تصدير المعاملات CSV"""
    status = request.args.get('status', '')
    txns = read_csv('transactions.csv')
    if status:
        txns = [t for t in txns if t.get('status') == status]

    output = io.StringIO()
    if txns:
        writer = csv.DictWriter(output, fieldnames=txns[0].keys())
        writer.writeheader()
        writer.writerows(txns)

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'transactions_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
    )

# ===== API — Users =====

@app.route('/api/users')
@api_auth
def api_users():
    search = request.args.get('search', '')
    banned = request.args.get('banned', '')
    page = int(request.args.get('page', '1'))
    per_page = int(request.args.get('per_page', '20'))

    users = read_csv('users.csv')
    users.reverse()

    if search:
        sl = search.lower()
        users = [u for u in users if sl in u.get('name', '').lower() or
                sl in u.get('phone', '').lower() or
                sl in u.get('customer_id', '').lower() or
                sl in u.get('telegram_id', '').lower()]
    if banned == 'yes':
        users = [u for u in users if u.get('is_banned') == 'yes']
    elif banned == 'no':
        users = [u for u in users if u.get('is_banned') != 'yes']

    total = len(users)
    start = (page - 1) * per_page
    end = start + per_page

    stats = {
        'total': len(read_csv('users.csv')),
        'banned': sum(1 for u in read_csv('users.csv') if u.get('is_banned') == 'yes'),
        'verified': sum(1 for u in read_csv('users.csv') if u.get('phone_verified') == 'yes'),
        'today': sum(1 for u in read_csv('users.csv') if u.get('date', '').startswith(datetime.now().strftime('%Y-%m-%d')))
    }

    return jsonify({
        'users': users[start:end],
        'total': total, 'page': page, 'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
        'stats': stats
    })

@app.route('/api/users/<user_id>/detail')
@api_auth
def api_user_detail(user_id):
    """تفاصيل المستخدم الكاملة"""
    users = read_csv('users.csv')
    user = next((u for u in users if u.get('telegram_id') == user_id), None)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    # معاملات المستخدم
    txns = read_csv('transactions.csv')
    user_txns = [t for t in txns if t.get('telegram_id') == user_id][-10:]

    # محفظة SVRP
    wallets = read_csv('svrp_wallets.csv')
    wallet = next((w for w in wallets if w.get('telegram_id') == user_id), {})

    # مطابقات المستخدم
    matches = read_csv('matches.csv')
    user_matches = [m for m in matches if m.get('depositor_id') == user_id or m.get('withdrawer_id') == user_id][-5:]

    return jsonify({
        'user': user,
        'transactions': user_txns,
        'wallet': wallet,
        'matches': user_matches
    })

@app.route('/api/users/<user_id>/ban', methods=['POST'])
@api_auth
def api_ban_user(user_id):
    reason = request.json.get('reason', 'محظور من لوحة التحكم') if request.json else 'محظور'
    users = read_csv('users.csv')
    fieldnames = get_fieldnames('users.csv', ['telegram_id','name','phone','customer_id','language','date','is_banned','ban_reason','currency'])
    for u in users:
        if u.get('telegram_id') == user_id:
            u['is_banned'] = 'yes'
            u['ban_reason'] = reason
            break
    write_csv('users.csv', users, fieldnames)
    log_action('ban_user', f'{user_id}: {reason}')
    return jsonify({'success': True})

@app.route('/api/users/<user_id>/unban', methods=['POST'])
@api_auth
def api_unban_user(user_id):
    users = read_csv('users.csv')
    fieldnames = get_fieldnames('users.csv', ['telegram_id','name','phone','customer_id','language','date','is_banned','ban_reason','currency'])
    for u in users:
        if u.get('telegram_id') == user_id:
            u['is_banned'] = 'no'
            u['ban_reason'] = ''
            break
    write_csv('users.csv', users, fieldnames)
    log_action('unban_user', user_id)
    return jsonify({'success': True})

@app.route('/api/users/export')
@api_auth
def api_export_users():
    users = read_csv('users.csv')
    output = io.StringIO()
    if users:
        writer = csv.DictWriter(output, fieldnames=users[0].keys())
        writer.writeheader()
        writer.writerows(users)
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'users_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
    )

# ===== API — Companies =====

@app.route('/api/companies')
@api_auth
def api_companies():
    companies = read_csv('companies.csv')
    # إضافة إحصائيات لكل شركة
    txns = read_csv('transactions.csv')
    for c in companies:
        cid = c.get('id', '')
        c_txns = [t for t in txns if t.get('company', '') == c.get('name', '')]
        c['txn_count'] = len(c_txns)
        c['volume'] = sum(float(t.get('amount', 0) or 0) for t in c_txns if t.get('status') == 'approved')
    return jsonify({'companies': companies})

@app.route('/api/companies', methods=['POST'])
@api_auth
def api_add_company():
    data = request.json
    companies = read_csv('companies.csv')
    fieldnames = get_fieldnames('companies.csv', ['id','name','type','details','is_active','icon','address','affiliate_link'])
    new_id = f"CMP{str(int(datetime.now().timestamp()))[-6:]}"
    new_company = {
        'id': new_id,
        'name': data.get('name', ''),
        'type': data.get('type', 'both'),
        'details': data.get('details', ''),
        'is_active': 'yes',
        'icon': data.get('icon', '🏢'),
        'address': data.get('address', ''),
        'affiliate_link': data.get('affiliate_link', '')
    }
    append_csv('companies.csv', new_company, fieldnames)
    log_action('add_company', new_id)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/companies/<company_id>', methods=['PUT', 'DELETE'])
@api_auth
def api_edit_company(company_id):
    companies = read_csv('companies.csv')
    fieldnames = get_fieldnames('companies.csv', ['id','name','type','details','is_active','icon','address','affiliate_link'])

    if request.method == 'DELETE':
        companies = [c for c in companies if c.get('id') != company_id]
        write_csv('companies.csv', companies, fieldnames)
        log_action('delete_company', company_id)
        return jsonify({'success': True})
    elif request.method == 'PUT':
        data = request.json
        for c in companies:
            if c.get('id') == company_id:
                for k, v in data.items():
                    if k in fieldnames:
                        c[k] = v
                break
        write_csv('companies.csv', companies, fieldnames)
        log_action('edit_company', company_id)
        return jsonify({'success': True})

# ===== API — Payment Methods =====

@app.route('/api/payment-methods')
@api_auth
def api_payment_methods():
    methods = read_csv('payment_methods.csv')
    links = read_csv('company_payment_links.csv')
    # إضافة قائمة الشركات المرتبطة لكل وسيلة
    for m in methods:
        mid = m.get('id', '')
        linked_companies = [l.get('company_id') for l in links if l.get('method_id') == mid]
        m['linked_company_ids'] = linked_companies
        m['linked_count'] = len(linked_companies)
    return jsonify({'methods': methods})

@app.route('/api/payment-methods', methods=['POST'])
@api_auth
def api_add_payment_method():
    data = request.json
    methods = read_csv('payment_methods.csv')
    fieldnames = get_fieldnames('payment_methods.csv', ['id','company_id','method_name','method_type','account_data','additional_info','status','created_date','icon'])
    new_id = f"PM{str(int(datetime.now().timestamp()))[-6:]}"
    new_method = {
        'id': new_id,
        'company_id': '',
        'method_name': data.get('method_name', ''),
        'method_type': data.get('method_type', ''),
        'account_data': data.get('account_data', ''),
        'additional_info': data.get('additional_info', ''),
        'status': 'active',
        'created_date': datetime.now().strftime('%Y-%m-%d'),
        'icon': data.get('icon', '💳')
    }
    append_csv('payment_methods.csv', new_method, fieldnames)
    log_action('add_payment_method', new_id)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/payment-methods/<method_id>', methods=['PUT', 'DELETE'])
@api_auth
def api_edit_payment_method(method_id):
    methods = read_csv('payment_methods.csv')
    fieldnames = get_fieldnames('payment_methods.csv', ['id','company_id','method_name','method_type','account_data','additional_info','status','created_date','icon'])

    if request.method == 'DELETE':
        methods = [m for m in methods if m.get('id') != method_id]
        write_csv('payment_methods.csv', methods, fieldnames)
        log_action('delete_payment_method', method_id)
        return jsonify({'success': True})
    elif request.method == 'PUT':
        data = request.json
        for m in methods:
            if m.get('id') == method_id:
                for k, v in data.items():
                    if k in fieldnames:
                        m[k] = v
                break
        write_csv('payment_methods.csv', methods, fieldnames)
        return jsonify({'success': True})

# ===== API — Payment Links (company_payment_links.csv) =====

@app.route('/api/payment-links')
@api_auth
def api_payment_links():
    links = read_csv('company_payment_links.csv')
    return jsonify({'links': links})

@app.route('/api/payment-links', methods=['POST'])
@api_auth
def api_save_payment_links():
    """حفظ روابط وسيلة دفع مع شركات (استبدال كامل)"""
    data = request.json
    method_id = data.get('method_id', '')
    company_ids = data.get('company_ids', [])

    # حذف الروابط القديمة لهذه الوسيلة
    links = read_csv('company_payment_links.csv')
    fieldnames = get_fieldnames('company_payment_links.csv', ['id','company_id','method_id','created_at'])
    links = [l for l in links if l.get('method_id') != str(method_id)]

    # إضافة الروابط الجديدة
    for cid in company_ids:
        links.append({
            'id': f"LNK{secrets.token_hex(3).upper()}",
            'company_id': str(cid),
            'method_id': str(method_id),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
        })

    write_csv('company_payment_links.csv', links, fieldnames)
    log_action('save_payment_links', f'method={method_id}, companies={len(company_ids)}')
    return jsonify({'success': True, 'linked_count': len(company_ids)})

# ===== API — Matching =====

@app.route('/api/matching/active')
@api_auth
def api_matching_active():
    matches = read_csv('matches.csv')
    active = [m for m in matches if m.get('status') not in ('completed', 'cancelled')]
    active.reverse()
    return jsonify({'matches': active, 'count': len(active)})

@app.route('/api/matching/pending')
@api_auth
def api_matching_pending():
    reqs = read_csv('match_requests.csv')
    pending = [r for r in reqs if r.get('status') == 'waiting']
    pending.reverse()
    return jsonify({'requests': pending, 'count': len(pending)})

@app.route('/api/matching/logs')
@api_auth
def api_matching_logs():
    matches = read_csv('matches.csv')
    logs = [m for m in matches if m.get('status') in ('completed', 'cancelled')]
    logs.reverse()
    return jsonify({'matches': logs[:50], 'count': len(logs)})

@app.route('/api/matching/<match_id>/chat')
@api_auth
def api_match_chat(match_id):
    messages = read_csv('chat_messages.csv')
    chat = [m for m in messages if m.get('match_id') == match_id]
    return jsonify({'messages': chat})

@app.route('/api/matching/<match_id>/disputes')
@api_auth
def api_match_disputes(match_id):
    disputes = read_csv('disputes.csv')
    match_disputes = [d for d in disputes if d.get('match_id') == match_id]
    return jsonify({'disputes': match_disputes})

# ===== API — SVRP =====

@app.route('/api/svrp/wallets')
@api_auth
def api_svrp_wallets():
    wallets = read_csv('svrp_wallets.csv')
    return jsonify({'wallets': wallets, 'count': len(wallets)})

@app.route('/api/svrp/requests')
@api_auth
def api_svrp_requests():
    reqs = read_csv('recovery_requests.csv')
    reqs.reverse()
    return jsonify({'requests': reqs})

@app.route('/api/svrp/requests/<req_id>/approve', methods=['POST'])
@api_auth
def api_svrp_approve(req_id):
    amount = request.json.get('amount', '0') if request.json else '0'
    reqs = read_csv('recovery_requests.csv')
    fieldnames = get_fieldnames('recovery_requests.csv', ['id','user_id','customer_id','photo_file_id','status','recovery_amount','admin_note','created_at','approved_at','approved_by'])
    for r in reqs:
        if r.get('id') == req_id:
            r['status'] = 'approved'
            r['recovery_amount'] = amount
            r['approved_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            r['approved_by'] = session.get('admin_id', '')
            break
    write_csv('recovery_requests.csv', reqs, fieldnames)
    log_action('svrp_approve', f'{req_id}: {amount}')
    return jsonify({'success': True})

@app.route('/api/svrp/requests/<req_id>/reject', methods=['POST'])
@api_auth
def api_svrp_reject(req_id):
    reqs = read_csv('recovery_requests.csv')
    fieldnames = get_fieldnames('recovery_requests.csv', ['id','user_id','customer_id','photo_file_id','status','recovery_amount','admin_note','created_at','approved_at','approved_by'])
    for r in reqs:
        if r.get('id') == req_id:
            r['status'] = 'rejected'
            break
    write_csv('recovery_requests.csv', reqs, fieldnames)
    log_action('svrp_reject', req_id)
    return jsonify({'success': True})

@app.route('/api/svrp/bonus-requests')
@api_auth
def api_svrp_bonus_requests():
    reqs = read_csv('bonus_requests.csv')
    reqs.reverse()
    return jsonify({'requests': reqs})

@app.route('/api/svrp/bonus-requests/<req_id>/approve', methods=['POST'])
@api_auth
def api_svrp_bonus_approve(req_id):
    reqs = read_csv('bonus_requests.csv')
    fieldnames = get_fieldnames('bonus_requests.csv', ['id','user_id','company_id','company_name','account_number','bonus_amount','status','created_at','approved_by'])
    for r in reqs:
        if r.get('id') == req_id:
            r['status'] = 'approved'
            r['approved_by'] = session.get('admin_id', '')
            break
    write_csv('bonus_requests.csv', reqs, fieldnames)
    log_action('svrp_bonus_approve', req_id)
    return jsonify({'success': True})

@app.route('/api/svrp/bonus-requests/<req_id>/reject', methods=['POST'])
@api_auth
def api_svrp_bonus_reject(req_id):
    reqs = read_csv('bonus_requests.csv')
    fieldnames = get_fieldnames('bonus_requests.csv', ['id','user_id','company_id','company_name','account_number','bonus_amount','status','created_at','approved_by'])
    for r in reqs:
        if r.get('id') == req_id:
            r['status'] = 'rejected'
            break
    write_csv('bonus_requests.csv', reqs, fieldnames)
    log_action('svrp_bonus_reject', req_id)
    return jsonify({'success': True})

@app.route('/api/svrp/promo-codes')
@api_auth
def api_svrp_promo_codes():
    codes = read_csv('svrp_promo_codes.csv')
    return jsonify({'codes': codes})

@app.route('/api/svrp/promo-codes', methods=['POST'])
@api_auth
def api_create_promo_code():
    data = request.json
    codes = read_csv('svrp_promo_codes.csv')
    fieldnames = get_fieldnames('svrp_promo_codes.csv', ['code','creator_id','amount','currency','max_uses','used_count','status','created_at','expires_at'])
    new_code = {
        'code': data.get('code', f"PROMO{secrets.token_hex(3).upper()}"),
        'creator_id': session.get('admin_id', ''),
        'amount': data.get('amount', '10'),
        'currency': data.get('currency', 'SAR'),
        'max_uses': data.get('max_uses', '100'),
        'used_count': '0',
        'status': 'active',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'expires_at': data.get('expires_at', '')
    }
    append_csv('svrp_promo_codes.csv', new_code, fieldnames)
    log_action('create_promo_code', new_code['code'])
    return jsonify({'success': True, 'code': new_code['code']})

# ===== API — Trading =====

@app.route('/api/trading/orders')
@api_auth
def api_trading_orders():
    orders = read_csv('trade_orders.csv')
    status_filter = request.args.get('status', '')
    type_filter = request.args.get('type', '')

    if status_filter:
        orders = [o for o in orders if o.get('status') == status_filter]
    if type_filter:
        orders = [o for o in orders if o.get('order_type') == type_filter]

    orders.reverse()
    pending = sum(1 for o in read_csv('trade_orders.csv') if o.get('status') == 'pending')
    buy_count = sum(1 for o in read_csv('trade_orders.csv') if o.get('order_type') == 'buy')
    sell_count = sum(1 for o in read_csv('trade_orders.csv') if o.get('order_type') == 'sell')

    return jsonify({
        'orders': orders[:50],
        'stats': {
            'total': len(read_csv('trade_orders.csv')),
            'pending': pending,
            'buy': buy_count,
            'sell': sell_count
        }
    })

# ===== API — Lottery =====

@app.route('/api/lottery/rounds')
@api_auth
def api_lottery_rounds():
    rounds = read_csv('lottery_rounds.csv')
    tickets = read_csv('lottery_tickets.csv')
    winners = read_csv('lottery_winners.csv')

    for r in rounds:
        rid = r.get('id', '')
        round_tickets = [t for t in tickets if t.get('round_id') == rid]
        r['tickets_sold'] = len(round_tickets)
        r['participants'] = len(set(t.get('user_id') for t in round_tickets))
        round_winners = [w for w in winners if w.get('round_id') == rid]
        r['winners_count'] = len(round_winners)
        r['winners_list'] = round_winners

    return jsonify({'rounds': rounds})

# ===== API — Wheel =====

@app.route('/api/wheel/rounds')
@api_auth
def api_wheel_rounds():
    rounds = read_csv('wheel_rounds.csv')
    spins = read_csv('wheel_spins.csv')

    for r in rounds:
        rid = r.get('id', '')
        round_spins = [s for s in spins if s.get('round_id') == rid]
        r['total_spins'] = len(round_spins)
        r['participants'] = len(set(s.get('user_id') for s in round_spins))
        r['recent_spins'] = round_spins[-10:]

    return jsonify({'rounds': rounds})

# ===== API — Apps =====

@app.route('/api/apps')
@api_auth
def api_apps():
    apps = read_csv('app_links.csv')
    return jsonify({'apps': apps})

@app.route('/api/apps', methods=['POST'])
@api_auth
def api_add_app():
    data = request.json
    apps = read_csv('app_links.csv')
    fieldnames = get_fieldnames('app_links.csv', ['id','name','icon_url','download_url','description','is_active','created_at'])
    new_id = f"APP{str(int(datetime.now().timestamp()))[-6:]}"
    new_app = {
        'id': new_id,
        'name': data.get('name', ''),
        'icon_url': data.get('icon_url', ''),
        'download_url': data.get('download_url', ''),
        'description': data.get('description', ''),
        'is_active': 'yes',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    append_csv('app_links.csv', new_app, fieldnames)
    log_action('add_app', new_id)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/apps/<app_id>', methods=['PUT', 'DELETE'])
@api_auth
def api_edit_app(app_id):
    apps = read_csv('app_links.csv')
    fieldnames = get_fieldnames('app_links.csv', ['id','name','icon_url','download_url','description','is_active','created_at'])

    if request.method == 'DELETE':
        apps = [a for a in apps if a.get('id') != app_id]
        write_csv('app_links.csv', apps, fieldnames)
        log_action('delete_app', app_id)
        return jsonify({'success': True})
    elif request.method == 'PUT':
        data = request.json
        for a in apps:
            if a.get('id') == app_id:
                for k, v in data.items():
                    if k in fieldnames:
                        a[k] = v
                break
        write_csv('app_links.csv', apps, fieldnames)
        return jsonify({'success': True})

# ===== API — Referrals =====

@app.route('/api/referrals')
@api_auth
def api_referrals():
    links = read_csv('referral_links.csv')
    log = read_csv('referral_log.csv')
    log.reverse()
    total = len(log)
    verified = sum(1 for r in log if r.get('phone_verified') == 'yes')
    total_bonus = sum(float(r.get('bonus', 0) or 0) for r in log)
    return jsonify({
        'links': links,
        'log': log[:50],
        'stats': {'total': total, 'verified': verified, 'total_bonus': total_bonus}
    })

@app.route('/api/referrals/links', methods=['POST'])
@api_auth
def api_add_referral_link():
    data = request.json
    links = read_csv('referral_links.csv')
    fieldnames = get_fieldnames('referral_links.csv', ['id','name','url','is_active','created_at'])
    new_id = f"REF{str(int(datetime.now().timestamp()))[-6:]}"
    new_link = {
        'id': new_id,
        'name': data.get('name', ''),
        'url': data.get('url', ''),
        'is_active': 'yes',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    append_csv('referral_links.csv', new_link, fieldnames)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/referrals/links/<link_id>', methods=['PUT', 'DELETE'])
@api_auth
def api_edit_referral_link(link_id):
    links = read_csv('referral_links.csv')
    fieldnames = get_fieldnames('referral_links.csv', ['id','name','url','is_active','created_at'])

    if request.method == 'DELETE':
        links = [l for l in links if l.get('id') != link_id]
        write_csv('referral_links.csv', links, fieldnames)
        return jsonify({'success': True})
    elif request.method == 'PUT':
        data = request.json
        for l in links:
            if l.get('id') == link_id:
                for k, v in data.items():
                    if k in fieldnames:
                        l[k] = v
                break
        write_csv('referral_links.csv', links, fieldnames)
        return jsonify({'success': True})

# ===== API — Channels =====

@app.route('/api/channels')
@api_auth
def api_channels():
    channels = read_csv('bot_channels.csv')
    # التأكد من وجود أعمدة الإعدادات
    for ch in channels:
        if 'relay_to_users' not in ch: ch['relay_to_users'] = 'yes'
        if 'relay_to_channels' not in ch: ch['relay_to_channels'] = 'yes'
        if 'forward_mode' not in ch: ch['forward_mode'] = 'all'
        if 'welcome_text' not in ch: ch['welcome_text'] = ''
    return jsonify({'channels': channels})

@app.route('/api/channels/<channel_id>/toggle', methods=['POST'])
@api_auth
def api_toggle_channel(channel_id):
    channels = read_csv('bot_channels.csv')
    fieldnames = get_fieldnames('bot_channels.csv', ['id','chat_id','title','type','is_active','added_at','relay_to_users','relay_to_channels','forward_mode','welcome_text'])
    for c in channels:
        if c.get('id') == channel_id:
            c['is_active'] = 'no' if c.get('is_active') == 'yes' else 'yes'
            break
    write_csv('bot_channels.csv', channels, fieldnames)
    return jsonify({'success': True})

@app.route('/api/channels/<channel_id>/settings', methods=['POST'])
@api_auth
def api_channel_settings(channel_id):
    """تحديث إعدادات قناة محددة"""
    data = request.json
    channels = read_csv('bot_channels.csv')
    fieldnames = get_fieldnames('bot_channels.csv', ['id','chat_id','title','type','is_active','added_at','relay_to_users','relay_to_channels','forward_mode','welcome_text'])
    editable = ['relay_to_users', 'relay_to_channels', 'forward_mode', 'welcome_text', 'is_active', 'title']
    for c in channels:
        if c.get('id') == channel_id:
            for k, v in data.items():
                if k in editable:
                    if k not in fieldnames:
                        fieldnames.append(k)
                    c[k] = v
            break
    write_csv('bot_channels.csv', channels, fieldnames)
    log_action('update_channel_settings', f'{channel_id}: {json.dumps(data)[:100]}')
    return jsonify({'success': True})

@app.route('/api/channels/<channel_id>', methods=['DELETE'])
@api_auth
def api_delete_channel(channel_id):
    channels = read_csv('bot_channels.csv')
    fieldnames = get_fieldnames('bot_channels.csv', ['id','chat_id','title','type','is_active','added_at','relay_to_users','relay_to_channels','forward_mode','welcome_text'])
    channels = [c for c in channels if c.get('id') != channel_id]
    write_csv('bot_channels.csv', channels, fieldnames)
    return jsonify({'success': True})

# ===== API — Relay Log =====

@app.route('/api/relay-log')
@api_auth
def api_relay_log():
    """سجل عمليات الترحيل"""
    logs = read_csv('relay_log.csv')
    logs.reverse()
    return jsonify({'logs': logs[:100], 'total': len(logs)})

# ===== API — Post Library =====

@app.route('/api/post-library')
@api_auth
def api_post_library():
    """مكتبة المنشورات — كل المنشورات"""
    search = request.args.get('search', '')
    posts = read_csv('post_library.csv')
    if search:
        sl = search.lower()
        posts = [p for p in posts if sl in (p.get('content', '') + p.get('title', '')).lower()]
    posts.reverse()
    return jsonify({'posts': posts[:100], 'total': len(posts)})

@app.route('/api/post-library', methods=['POST'])
@api_auth
def api_add_post():
    """إنشاء منشور جديد"""
    data = request.json
    posts = read_csv('post_library.csv')
    fieldnames = get_fieldnames('post_library.csv', ['id','title','content','media_type','media_file_id','target_channels','schedule','status','created_by','created_at'])
    new_id = f"POST{secrets.token_hex(3).upper()}"
    post = {
        'id': new_id,
        'title': data.get('title', ''),
        'content': data.get('content', ''),
        'media_type': data.get('media_type', 'text'),  # text, photo, video, both
        'media_file_id': data.get('media_file_id', ''),
        'target_channels': data.get('target_channels', ''),  # pipe-separated channel IDs
        'schedule': data.get('schedule', ''),  # datetime or 'now'
        'status': 'pending' if data.get('schedule') else 'ready',
        'created_by': session.get('admin_id', ''),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    append_csv('post_library.csv', post, fieldnames)
    log_action('create_post', new_id)

    # If schedule is 'now' — add to broadcast_queue for immediate publishing
    if data.get('schedule', 'now') == 'now' and post['content']:
        target_channels = data.get('target_channels', '').split('|') if data.get('target_channels') else []
        if target_channels:
            for ch_id in target_channels:
                ch_id = ch_id.strip()
                if ch_id:
                    channels = read_csv('bot_channels.csv')
                    ch = next((c for c in channels if c.get('id') == ch_id), None)
                    if ch:
                        entry = {
                            'id': f"PUB{secrets.token_hex(3).upper()}",
                            'message': post['content'],
                            'type': post['media_type'],
                            'target_chat_id': ch.get('chat_id', ''),
                            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                            'created_by': session.get('admin_id', ''),
                            'status': 'pending'
                        }
                        bq_fields = get_fieldnames('broadcast_queue.csv', ['id','message','type','target_chat_id','created_at','created_by','status'])
                        append_csv('broadcast_queue.csv', entry, bq_fields)
        # Also broadcast to all users if content exists
        entry_all = {
            'id': f"PUB{secrets.token_hex(3).upper()}",
            'message': post['content'],
            'type': post['media_type'],
            'target_chat_id': '',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'created_by': session.get('admin_id', ''),
            'status': 'pending'
        }
        bq_fields = get_fieldnames('broadcast_queue.csv', ['id','message','type','target_chat_id','created_at','created_by','status'])
        append_csv('broadcast_queue.csv', entry_all, bq_fields)
        post['status'] = 'published'
        # Update status in CSV
        for p in posts:
            if p.get('id') == new_id:
                p['status'] = 'published'
                break
        write_csv('post_library.csv', posts, fieldnames)

    return jsonify({'success': True, 'id': new_id, 'status': post['status']})

@app.route('/api/post-library/<post_id>', methods=['DELETE'])
@api_auth
def api_delete_post(post_id):
    posts = read_csv('post_library.csv')
    fieldnames = get_fieldnames('post_library.csv', ['id','title','content','media_type','media_file_id','target_channels','schedule','status','created_by','created_at'])
    posts = [p for p in posts if p.get('id') != post_id]
    write_csv('post_library.csv', posts, fieldnames)
    log_action('delete_post', post_id)
    return jsonify({'success': True})

@app.route('/api/post-library/<post_id>/publish', methods=['POST'])
@api_auth
def api_publish_post(post_id):
    """نشر منشور من المكتبة"""
    posts = read_csv('post_library.csv')
    post = next((p for p in posts if p.get('id') == post_id), None)
    if not post:
        return jsonify({'error': 'Post not found'}), 404

    # Add to broadcast queue
    target_channels = post.get('target_channels', '').split('|') if post.get('target_channels') else []
    for ch_id in target_channels:
        ch_id = ch_id.strip()
        if ch_id:
            channels = read_csv('bot_channels.csv')
            ch = next((c for c in channels if c.get('id') == ch_id), None)
            if ch:
                entry = {
                    'id': f"PUB{secrets.token_hex(3).upper()}",
                    'message': post.get('content', ''),
                    'type': post.get('media_type', 'text'),
                    'target_chat_id': ch.get('chat_id', ''),
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'created_by': session.get('admin_id', ''),
                    'status': 'pending'
                }
                bq_fields = get_fieldnames('broadcast_queue.csv', ['id','message','type','target_chat_id','created_at','created_by','status'])
                append_csv('broadcast_queue.csv', entry, bq_fields)

    # Also broadcast to all users
    entry_all = {
        'id': f"PUB{secrets.token_hex(3).upper()}",
        'message': post.get('content', ''),
        'type': post.get('media_type', 'text'),
        'target_chat_id': '',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'created_by': session.get('admin_id', ''),
        'status': 'pending'
    }
    bq_fields = get_fieldnames('broadcast_queue.csv', ['id','message','type','target_chat_id','created_at','created_by','status'])
    append_csv('broadcast_queue.csv', entry_all, bq_fields)

    # Update post status
    fieldnames = get_fieldnames('post_library.csv', ['id','title','content','media_type','media_file_id','target_channels','schedule','status','created_by','created_at'])
    for p in posts:
        if p.get('id') == post_id:
            p['status'] = 'published'
            break
    write_csv('post_library.csv', posts, fieldnames)
    log_action('publish_post', post_id)
    return jsonify({'success': True, 'message': 'تم النشر'})

# ===== API — Post Vault (Legacy archive) =====

@app.route('/api/post-vault')
@api_auth
def api_post_vault():
    """أرشيف البوستات المحفوظة"""
    search = request.args.get('search', '')
    posts = read_csv('post_vault.csv')
    if search:
        sl = search.lower()
        posts = [p for p in posts if sl in (p.get('original_text', '') + p.get('processed_text', '')).lower()]
    posts.reverse()
    return jsonify({'posts': posts[:100], 'total': len(posts)})

@app.route('/api/post-vault/<post_id>/repost', methods=['POST'])
@api_auth
def api_repost_from_vault(post_id):
    """إعادة نشر بوست من الأرشيف"""
    posts = read_csv('post_vault.csv')
    post = next((p for p in posts if p.get('id') == post_id), None)
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    text = post.get('processed_text') or post.get('original_text', '')
    entry = {
        'id': f"CHPOST{secrets.token_hex(3).upper()}",
        'message': text,
        'type': 'text',
        'target_chat_id': '',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'created_by': session.get('admin_id', ''),
        'status': 'pending'
    }
    fieldnames = ['id', 'message', 'type', 'target_chat_id', 'created_at', 'created_by', 'status']
    append_csv('broadcast_queue.csv', entry, fieldnames)
    log_action('repost_from_vault', post_id)
    return jsonify({'success': True, 'message': 'تمت إضافة البوست لقائمة الإرسال'})

@app.route('/api/post-vault/<post_id>', methods=['DELETE'])
@api_auth
def api_delete_vault_post(post_id):
    posts = read_csv('post_vault.csv')
    posts = [p for p in posts if p.get('id') != post_id]
    fieldnames = get_fieldnames('post_vault.csv', ['id','source_channel','source_chat_id','original_text','processed_text','media_type','media_file_id','ai_provider','status','created_at','published_to_users','published_to_channels','views','category'])
    write_csv('post_vault.csv', posts, fieldnames)
    return jsonify({'success': True})

# ===== API — Text Replacements =====

@app.route('/api/text-replacements')
@api_auth
def api_text_replacements():
    rules = read_csv('text_replacements.csv')
    return jsonify({'rules': rules})

@app.route('/api/text-replacements', methods=['POST'])
@api_auth
def api_add_text_replacement():
    data = request.json
    rules = read_csv('text_replacements.csv')
    fieldnames = get_fieldnames('text_replacements.csv', ['id','find_text','replace_text','is_regex','channel_id','is_active','created_at'])
    new_id = f"TR{secrets.token_hex(3).upper()}"
    rule = {
        'id': new_id,
        'find_text': data.get('find_text', ''),
        'replace_text': data.get('replace_text', ''),
        'is_regex': data.get('is_regex', 'no'),
        'channel_id': data.get('channel_id', ''),
        'is_active': 'yes',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    append_csv('text_replacements.csv', rule, fieldnames)
    log_action('add_text_replacement', new_id)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/text-replacements/<rule_id>/toggle', methods=['POST'])
@api_auth
def api_toggle_replacement(rule_id):
    rules = read_csv('text_replacements.csv')
    fieldnames = get_fieldnames('text_replacements.csv', ['id','find_text','replace_text','is_regex','channel_id','is_active','created_at'])
    for r in rules:
        if r.get('id') == rule_id:
            r['is_active'] = 'no' if r.get('is_active') == 'yes' else 'yes'
            break
    write_csv('text_replacements.csv', rules, fieldnames)
    return jsonify({'success': True})

@app.route('/api/text-replacements/<rule_id>', methods=['DELETE'])
@api_auth
def api_delete_replacement(rule_id):
    rules = read_csv('text_replacements.csv')
    fieldnames = get_fieldnames('text_replacements.csv', ['id','find_text','replace_text','is_regex','channel_id','is_active','created_at'])
    rules = [r for r in rules if r.get('id') != rule_id]
    write_csv('text_replacements.csv', rules, fieldnames)
    return jsonify({'success': True})

# ===== API — AI Providers =====

@app.route('/api/ai-providers')
@api_auth
def api_ai_providers():
    try:
        from ai_providers import AIManager
        manager = AIManager()
        providers = manager.get_available_providers()
        active = manager.get_active_provider_name()
        return jsonify({'providers': providers, 'active': active})
    except ImportError:
        return jsonify({'providers': [], 'active': None, 'error': 'ai_providers not available'})

@app.route('/api/ai-providers/test', methods=['POST'])
@api_auth
def api_test_ai():
    try:
        from ai_providers import AIManager
        manager = AIManager()
        provider = request.json.get('provider', None) if request.json else None
        result = manager.test_provider(provider)
        return jsonify(result)
    except ImportError:
        return jsonify({'success': False, 'error': 'ai_providers not available'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/ai-instructions', methods=['GET', 'POST'])
@api_auth
def api_ai_instructions():
    if request.method == 'GET':
        settings = read_csv('system_settings.csv')
        instr = next((s.get('setting_value', '') for s in settings if s.get('setting_key') == 'ai_instructions'), '')
        return jsonify({'instructions': instr})
    else:
        data = request.json
        text = data.get('instructions', '')
        settings = read_csv('system_settings.csv')
        fieldnames = get_fieldnames('system_settings.csv', ['setting_key','setting_value','description'])
        found = False
        for s in settings:
            if s.get('setting_key') == 'ai_instructions':
                s['setting_value'] = text
                found = True
                break
        if not found:
            settings.append({'setting_key': 'ai_instructions', 'setting_value': text, 'description': 'AI instructions'})
        write_csv('system_settings.csv', settings, fieldnames)
        log_action('update_ai_instructions', text[:50])
        return jsonify({'success': True})

@app.route('/api/ai-processed-posts')
@api_auth
def api_ai_posts():
    posts = read_csv('ai_processed_posts.csv')
    posts.reverse()
    return jsonify({'posts': posts[:50], 'total': len(posts)})

# ===== API — Channel Categories =====

@app.route('/api/channel-categories')
@api_auth
def api_channel_categories():
    channels = read_csv('bot_channels.csv')
    cats = {}
    for ch in channels:
        cat = ch.get('category', 'غير مصنف')
        if not cat:
            cat = 'غير مصنف'
        if cat not in cats:
            cats[cat] = 0
        cats[cat] += 1
    return jsonify({'categories': cats})

@app.route('/api/channels/<channel_id>/category', methods=['POST'])
@api_auth
def api_set_channel_category(channel_id):
    data = request.json
    category = data.get('category', 'غير مصنف')
    channels = read_csv('bot_channels.csv')
    fieldnames = get_fieldnames('bot_channels.csv', ['id','chat_id','title','type','is_active','added_at','relay_to_users','relay_to_channels','forward_mode','welcome_text','category','ai_enabled'])
    for c in channels:
        if c.get('id') == channel_id:
            c['category'] = category
            break
    write_csv('bot_channels.csv', channels, fieldnames)
    return jsonify({'success': True})

@app.route('/api/channels/<channel_id>/ai-toggle', methods=['POST'])
@api_auth
def api_toggle_channel_ai(channel_id):
    channels = read_csv('bot_channels.csv')
    fieldnames = get_fieldnames('bot_channels.csv', ['id','chat_id','title','type','is_active','added_at','relay_to_users','relay_to_channels','forward_mode','welcome_text','category','ai_enabled'])
    for c in channels:
        if c.get('id') == channel_id:
            c['ai_enabled'] = 'no' if c.get('ai_enabled') == 'yes' else 'yes'
            break
    write_csv('bot_channels.csv', channels, fieldnames)
    return jsonify({'success': True})

# ===== API — Channel Groups =====

@app.route('/api/channel-groups')
@api_auth
def api_channel_groups():
    groups = read_csv('channel_groups.csv')
    return jsonify({'groups': groups})

@app.route('/api/channel-groups', methods=['POST'])
@api_auth
def api_add_channel_group():
    data = request.json
    groups = read_csv('channel_groups.csv')
    fieldnames = get_fieldnames('channel_groups.csv', ['id','name','description','channel_ids','created_at'])
    new_id = f"GRP{secrets.token_hex(3).upper()}"
    group = {
        'id': new_id,
        'name': data.get('name', ''),
        'description': data.get('description', ''),
        'channel_ids': data.get('channel_ids', ''),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    append_csv('channel_groups.csv', group, fieldnames)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/channel-groups/<group_id>', methods=['DELETE'])
@api_auth
def api_delete_channel_group(group_id):
    groups = read_csv('channel_groups.csv')
    fieldnames = get_fieldnames('channel_groups.csv', ['id','name','description','channel_ids','created_at'])
    groups = [g for g in groups if g.get('id') != group_id]
    write_csv('channel_groups.csv', groups, fieldnames)
    return jsonify({'success': True})

# ===== API — Daily Report =====

@app.route('/api/channels/daily-report')
@api_auth
def api_daily_report():
    today = datetime.now().strftime('%Y-%m-%d')
    relay_logs = read_csv('relay_log.csv')
    today_logs = [l for l in relay_logs if l.get('timestamp', '').startswith(today)]
    ai_posts = read_csv('ai_processed_posts.csv')
    today_ai = [p for p in ai_posts if p.get('created_at', '').startswith(today)]
    channels = read_csv('bot_channels.csv')
    active_channels = [c for c in channels if c.get('is_active') == 'yes']
    total_users_reached = sum(int(l.get('users_relayed', 0) or 0) for l in today_logs)
    total_channels_reached = sum(int(l.get('channels_relayed', 0) or 0) for l in today_logs)
    return jsonify({
        'date': today,
        'total_posts': len(today_logs),
        'total_ai_processed': len(today_ai),
        'total_users_reached': total_users_reached,
        'total_channels_reached': total_channels_reached,
        'active_channels': len(active_channels),
        'total_channels': len(channels),
    })

# ===== API — Post to Channel =====

@app.route('/api/channels/<channel_id>/post', methods=['POST'])
@api_auth
def api_post_to_channel(channel_id):
    """إرسال رسالة لقناة محددة"""
    channels = read_csv('bot_channels.csv')
    ch = next((c for c in channels if c.get('id') == channel_id), None)
    if not ch:
        return jsonify({'error': 'Channel not found'}), 404
    data = request.json
    message_text = data.get('message', '')
    if not message_text:
        return jsonify({'error': 'No message'}), 400
    # حفظ في broadcast_queue.csv للبوت يرسلها
    entry = {
        'id': f"CHPOST{secrets.token_hex(3).upper()}",
        'message': message_text,
        'type': 'text',
        'target_chat_id': ch.get('chat_id', ''),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'created_by': session.get('admin_id', ''),
        'status': 'pending'
    }
    fieldnames = ['id', 'message', 'type', 'target_chat_id', 'created_at', 'created_by', 'status']
    append_csv('broadcast_queue.csv', entry, fieldnames)
    log_action('post_to_channel', f'{channel_id}: {message_text[:50]}')
    return jsonify({'success': True, 'message': 'تم إضافة الرسالة لقائمة الإرسال'})

@app.route('/api/channels', methods=['POST'])
@api_auth
def api_add_channel_manual():
    """إضافة قناة يدوياً — مع تحديد الدور"""
    data = request.json
    chat_id = data.get('chat_id', '').strip()
    title = data.get('title', '').strip()
    ch_type = data.get('type', 'channel')

    if not chat_id:
        return jsonify({'error': 'chat_id required'}), 400

    # فحص عدم التكرار
    channels = read_csv('bot_channels.csv')
    for ch in channels:
        if ch.get('chat_id') == str(chat_id):
            return jsonify({'error': 'Channel already exists'}), 400

    ch_id = f"CH{secrets.token_hex(3).upper()}"
    fieldnames = get_fieldnames('bot_channels.csv', ['id','chat_id','title','type','is_active','added_at','relay_to_users','relay_to_channels','forward_mode','welcome_text','category','ai_enabled','channel_role','ai_provider','brand_voice'])
    new_channel = {
        'id': ch_id,
        'chat_id': str(chat_id),
        'title': title,
        'type': ch_type,
        'is_active': 'yes',
        'added_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'relay_to_users': 'no',
        'relay_to_channels': 'no',
        'forward_mode': 'all',
        'welcome_text': '',
        'category': data.get('category', ''),
        'ai_enabled': 'no',
        'channel_role': data.get('channel_role', 'both'),  # source, publish, both
        'ai_provider': data.get('ai_provider', ''),
        'brand_voice': data.get('brand_voice', '')
    }
    append_csv('bot_channels.csv', new_channel, fieldnames)
    log_action('add_channel_manual', f'{ch_id}: {title} ({chat_id}) role={new_channel["channel_role"]}')
    return jsonify({'success': True, 'id': ch_id})

@app.route('/api/channels/<channel_id>/category', methods=['POST'])
@api_auth
def api_set_channel_category_api(channel_id):
    data = request.json
    category = data.get('category', '')
    channels = read_csv('bot_channels.csv')
    fieldnames = get_fieldnames('bot_channels.csv', ['id','chat_id','title','type','is_active','added_at','relay_to_users','relay_to_channels','forward_mode','welcome_text','category','ai_enabled'])
    for c in channels:
        if c.get('id') == channel_id:
            c['category'] = category
            break
    write_csv('bot_channels.csv', channels, fieldnames)
    return jsonify({'success': True})

@app.route('/api/channel-categories')
@api_auth
def api_channel_categories_list():
    """قائمة كل الفئات مع عدد القنوات في كل فئة"""
    channels = read_csv('bot_channels.csv')
    cats = {}
    for ch in channels:
        cat = ch.get('category', '') or 'غير مصنف'
        if cat not in cats:
            cats[cat] = {'count': 0, 'channels': []}
        cats[cat]['count'] += 1
        cats[cat]['channels'].append({'id': ch.get('id', ''), 'title': ch.get('title', ''), 'chat_id': ch.get('chat_id', '')})
    return jsonify({'categories': cats})

# ===== API — Wheel Gifts =====

@app.route('/api/wheel-gifts')
@api_auth
def api_wheel_gifts():
    gifts = read_csv('wheel_gifts.csv')
    return jsonify({'gifts': gifts})

@app.route('/api/wheel-gifts', methods=['POST'])
@api_auth
def api_add_wheel_gift():
    data = request.json
    gifts = read_csv('wheel_gifts.csv')
    fieldnames = get_fieldnames('wheel_gifts.csv', ['id','gift_text','affiliate_link','is_active','created_at'])
    new_id = f"GIFT{secrets.token_hex(3).upper()}"
    gift = {
        'id': new_id,
        'gift_text': data.get('gift_text', ''),
        'affiliate_link': data.get('affiliate_link', ''),
        'is_active': 'yes',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    append_csv('wheel_gifts.csv', gift, fieldnames)
    log_action('add_wheel_gift', new_id)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/wheel-gifts/<gift_id>', methods=['PUT', 'DELETE'])
@api_auth
def api_edit_wheel_gift(gift_id):
    gifts = read_csv('wheel_gifts.csv')
    fieldnames = get_fieldnames('wheel_gifts.csv', ['id','gift_text','affiliate_link','is_active','created_at'])
    if request.method == 'DELETE':
        gifts = [g for g in gifts if g.get('id') != gift_id]
        write_csv('wheel_gifts.csv', gifts, fieldnames)
        return jsonify({'success': True})
    elif request.method == 'PUT':
        data = request.json
        for g in gifts:
            if g.get('id') == gift_id:
                for k, v in data.items():
                    if k in fieldnames:
                        g[k] = v
                break
        write_csv('wheel_gifts.csv', gifts, fieldnames)
        return jsonify({'success': True})

# ===== API — Bots =====

@app.route('/api/bots')
@api_auth
def api_bots():
    bots = read_csv('bot_tokens.csv')
    # إضافة حالة التشغيل
    for b in bots:
        b['running'] = 'unknown'  # لا يمكن التحقق من حالة التشغيل من CSV
    return jsonify({'bots': bots})

@app.route('/api/bots', methods=['POST'])
@api_auth
def api_add_bot():
    data = request.json
    bots = read_csv('bot_tokens.csv')
    fieldnames = get_fieldnames('bot_tokens.csv', ['id','name','token','is_active','created_at','admin_ids','last_started','total_users','total_transactions','freeze_until','status','description','can_manage_bots'])
    new_id = f"BOT{str(int(datetime.now().timestamp()))[-6:]}"
    new_bot = {
        'id': new_id,
        'name': data.get('name', ''),
        'token': data.get('token', ''),
        'is_active': 'no',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'admin_ids': data.get('admin_ids', session.get('admin_id', '')),
        'last_started': '',
        'total_users': '0',
        'total_transactions': '0',
        'freeze_until': data.get('freeze_until', ''),
        'status': 'inactive',
        'description': data.get('description', ''),
        'can_manage_bots': data.get('can_manage_bots', 'no')
    }
    append_csv('bot_tokens.csv', new_bot, fieldnames)
    log_action('add_bot', new_id)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/bots/<bot_id>/toggle', methods=['POST'])
@api_auth
def api_toggle_bot(bot_id):
    bots = read_csv('bot_tokens.csv')
    fieldnames = get_fieldnames('bot_tokens.csv', ['id','name','token','is_active','created_at','admin_ids','last_started','total_users','total_transactions','freeze_until','status','description','can_manage_bots'])
    for b in bots:
        if b.get('id') == bot_id:
            b['is_active'] = 'no' if b.get('is_active') == 'yes' else 'yes'
            b['status'] = 'inactive' if b.get('is_active') == 'no' else 'active'
            break
    write_csv('bot_tokens.csv', bots, fieldnames)
    return jsonify({'success': True})

@app.route('/api/bots/<bot_id>', methods=['DELETE'])
@api_auth
def api_delete_bot(bot_id):
    bots = read_csv('bot_tokens.csv')
    fieldnames = get_fieldnames('bot_tokens.csv', ['id','name','token','is_active','created_at','admin_ids','last_started','total_users','total_transactions','freeze_until','status','description','can_manage_bots'])
    bots = [b for b in bots if b.get('id') != bot_id]
    write_csv('bot_tokens.csv', bots, fieldnames)
    log_action('delete_bot', bot_id)
    return jsonify({'success': True})

# ===== API — Complaints =====

@app.route('/api/complaints')
@api_auth
def api_complaints():
    complaints = read_csv('complaints.csv')
    complaints.reverse()
    status_filter = request.args.get('status', '')
    if status_filter:
        complaints = [c for c in complaints if c.get('status') == status_filter]
    return jsonify({
        'complaints': complaints[:50],
        'stats': {
            'total': len(read_csv('complaints.csv')),
            'open': sum(1 for c in read_csv('complaints.csv') if c.get('status') not in ('resolved', 'closed'))
        }
    })

@app.route('/api/complaints/<complaint_id>/reply', methods=['POST'])
@api_auth
def api_complaint_reply(complaint_id):
    reply = request.json.get('reply', '') if request.json else ''
    complaints = read_csv('complaints.csv')
    fieldnames = get_fieldnames('complaints.csv', ['id','customer_id','message','status','date','admin_response'])
    for c in complaints:
        if c.get('id') == complaint_id:
            c['status'] = 'resolved'
            c['admin_response'] = reply
            break
    write_csv('complaints.csv', complaints, fieldnames)
    log_action('complaint_reply', complaint_id)
    return jsonify({'success': True})

# ===== API — Broadcast =====

@app.route('/api/broadcast', methods=['POST'])
@api_auth
def api_broadcast():
    """بث رسالة لكل المستخدمين — يحفظ في ملف فقط (البوت الفعلي يرسل)"""
    message = request.json.get('message', '') if request.json else ''
    msg_type = request.json.get('type', 'text') if request.json else 'text'

    # حفظ رسالة البث في ملف للبوت لإرسالها
    broadcast_entry = {
        'id': f"BCAST{str(int(datetime.now().timestamp()))[-6:]}",
        'message': message,
        'type': msg_type,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'created_by': session.get('admin_id', ''),
        'status': 'pending'
    }
    fieldnames = ['id', 'message', 'type', 'created_at', 'created_by', 'status']
    append_csv('broadcast_queue.csv', broadcast_entry, fieldnames)
    log_action('broadcast', message[:50])
    return jsonify({'success': True, 'message': 'تم إضافة البث للقائمة — سيتم إرساله'})

# ===== API — Settings =====

@app.route('/api/settings')
@api_auth
def api_settings():
    settings = read_csv('system_settings.csv')
    return jsonify({'settings': settings})

@app.route('/api/settings', methods=['POST'])
@api_auth
def api_update_settings():
    data = request.json
    settings = read_csv('system_settings.csv')
    fieldnames = get_fieldnames('system_settings.csv', ['setting_key','setting_value','description'])
    for s in settings:
        key = s.get('setting_key', '')
        if key in data:
            s['setting_value'] = data[key]
    write_csv('system_settings.csv', settings, fieldnames)
    log_action('update_settings', json.dumps(data)[:100])
    return jsonify({'success': True})

# ===== API — Button Labels =====

@app.route('/api/button-labels')
@api_auth
def api_button_labels():
    labels = read_csv('button_labels.csv')
    return jsonify({'labels': labels})

@app.route('/api/button-labels', methods=['POST'])
@api_auth
def api_update_button_label():
    data = request.json
    labels = read_csv('button_labels.csv')
    fieldnames = get_fieldnames('button_labels.csv', ['original_text','new_text','is_active'])
    found = False
    for l in labels:
        if l.get('original_text') == data.get('original_text'):
            l['new_text'] = data.get('new_text', '')
            l['is_active'] = data.get('is_active', 'yes')
            found = True
            break
    if not found:
        append_csv('button_labels.csv', {
            'original_text': data.get('original_text', ''),
            'new_text': data.get('new_text', ''),
            'is_active': 'yes'
        }, fieldnames)
    else:
        write_csv('button_labels.csv', labels, fieldnames)
    return jsonify({'success': True})

# ===== API — Audit Log =====

@app.route('/api/audit-log')
@api_auth
def api_audit_log():
    logs = read_csv('admin_actions_log.csv')
    logs.reverse()
    return jsonify({'logs': logs[:100]})

# ===== API — Recent Activity =====

@app.route('/api/recent-activity')
@api_auth
def api_recent_activity():
    """آخر النشاطات للوحة الرئيسية"""
    activities = []

    # آخر المعاملات
    txns = read_csv('transactions.csv')
    for t in txns[-5:]:
        activities.append({
            'type': 'transaction',
            'icon': '💵' if t.get('type') == 'deposit' else '💸',
            'text': f"{t.get('name', '')} — {t.get('amount', '')} {t.get('currency', '')}",
            'status': t.get('status', ''),
            'time': t.get('date', '')
        })

    # آخر المستخدمين
    users = read_csv('users.csv')
    for u in users[-3:]:
        activities.append({
            'type': 'user',
            'icon': '👤',
            'text': f"مستخدم جديد: {u.get('name', '')}",
            'status': u.get('is_banned', 'no'),
            'time': u.get('date', '')
        })

    # آخر إجراءات الأدمن
    logs = read_csv('admin_actions_log.csv')
    for l in logs[-5:]:
        activities.append({
            'type': 'admin',
            'icon': '🔧',
            'text': f"{l.get('action_type', '')} — {l.get('details', '')}",
            'status': '',
            'time': l.get('timestamp', '')
        })

    # ترتيب حسب الوقت
    activities.sort(key=lambda x: x.get('time', ''), reverse=True)

    return jsonify({'activities': activities[:15]})

# ===== API — Admin Management =====

@app.route('/api/admins')
@api_auth
def api_admins():
    """List all admins from admin_permissions.json or users.csv (is_admin)"""
    perm_file = os.path.join(BASE_DIR, 'admin_permissions.json')
    if os.path.exists(perm_file):
        try:
            with open(perm_file, 'r', encoding='utf-8') as f:
                admins = json.load(f)
                if isinstance(admins, list):
                    return jsonify({'admins': admins})
        except Exception:
            pass
    users = read_csv('users.csv')
    admins = [u for u in users if u.get('is_admin') == 'yes' or u.get('is_admin') == 'true']
    return jsonify({'admins': admins})


@app.route('/api/admins', methods=['POST'])
@api_auth
def api_add_admin():
    data = request.json
    telegram_id = data.get('telegram_id', '')
    role = data.get('role', 'support')
    duration_hours = int(data.get('duration_hours', 0))

    perm_file = os.path.join(BASE_DIR, 'admin_permissions.json')
    perms = []
    if os.path.exists(perm_file):
        try:
            with open(perm_file, 'r', encoding='utf-8') as f:
                perms = json.load(f)
                if not isinstance(perms, list):
                    perms = []
        except Exception:
            perms = []

    expires_at = ''
    if duration_hours > 0:
        expires_at = (datetime.now() + timedelta(hours=duration_hours)).strftime('%Y-%m-%d %H:%M')

    new_admin = {
        'telegram_id': telegram_id,
        'role': role,
        'added_by': session.get('admin_id', ''),
        'added_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'expires_at': expires_at,
        'is_active': 'yes'
    }
    perms.append(new_admin)

    try:
        with open(perm_file, 'w', encoding='utf-8') as f:
            json.dump(perms, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    users = read_csv('users.csv')
    fieldnames = get_fieldnames('users.csv', ['telegram_id','name','phone','customer_id','language','date','is_banned','ban_reason','currency'])
    if 'is_admin' not in fieldnames:
        fieldnames.append('is_admin')
    if 'admin_role' not in fieldnames:
        fieldnames.append('admin_role')
    for u in users:
        if 'is_admin' not in u:
            u['is_admin'] = ''
        if 'admin_role' not in u:
            u['admin_role'] = ''
        if u.get('telegram_id') == telegram_id:
            u['is_admin'] = 'yes'
            u['admin_role'] = role
    write_csv('users.csv', users, fieldnames)

    log_action('add_admin', f'{telegram_id}: {role}')
    return jsonify({'success': True})


@app.route('/api/admins/<admin_id>', methods=['DELETE'])
@api_auth
def api_delete_admin(admin_id):
    perm_file = os.path.join(BASE_DIR, 'admin_permissions.json')
    if os.path.exists(perm_file):
        try:
            with open(perm_file, 'r', encoding='utf-8') as f:
                perms = json.load(f)
                if isinstance(perms, list):
                    perms = [p for p in perms if str(p.get('telegram_id')) != str(admin_id)]
                    with open(perm_file, 'w', encoding='utf-8') as f2:
                        json.dump(perms, f2, ensure_ascii=False, indent=2)
        except Exception:
            pass

    users = read_csv('users.csv')
    fieldnames = get_fieldnames('users.csv', ['telegram_id','name','phone','customer_id','language','date','is_banned','ban_reason','currency'])
    if 'is_admin' not in fieldnames:
        fieldnames.append('is_admin')
    if 'admin_role' not in fieldnames:
        fieldnames.append('admin_role')
    for u in users:
        if 'is_admin' not in u:
            u['is_admin'] = ''
        if 'admin_role' not in u:
            u['admin_role'] = ''
        if u.get('telegram_id') == admin_id:
            u['is_admin'] = 'no'
            u['admin_role'] = ''
    write_csv('users.csv', users, fieldnames)

    log_action('delete_admin', admin_id)
    return jsonify({'success': True})


@app.route('/api/admins/<admin_id>/role', methods=['POST'])
@api_auth
def api_set_admin_role(admin_id):
    role = request.json.get('role', 'support') if request.json else 'support'

    perm_file = os.path.join(BASE_DIR, 'admin_permissions.json')
    if os.path.exists(perm_file):
        try:
            with open(perm_file, 'r', encoding='utf-8') as f:
                perms = json.load(f)
                if isinstance(perms, list):
                    for p in perms:
                        if str(p.get('telegram_id')) == str(admin_id):
                            p['role'] = role
                            break
                    with open(perm_file, 'w', encoding='utf-8') as f2:
                        json.dump(perms, f2, ensure_ascii=False, indent=2)
        except Exception:
            pass

    users = read_csv('users.csv')
    fieldnames = get_fieldnames('users.csv', ['telegram_id','name','phone','customer_id','language','date','is_banned','ban_reason','currency'])
    if 'admin_role' not in fieldnames:
        fieldnames.append('admin_role')
    for u in users:
        if 'admin_role' not in u:
            u['admin_role'] = ''
        if u.get('telegram_id') == admin_id:
            u['admin_role'] = role
    write_csv('users.csv', users, fieldnames)

    log_action('set_admin_role', f'{admin_id}: {role}')
    return jsonify({'success': True})


# ===== API — Themes =====

@app.route('/api/themes')
@api_auth
def api_themes():
    themes = [
        {'id': 'gold', 'name': 'Gold', 'colors': {'primary': '#FFD700', 'accent': '#FFA500'}},
        {'id': 'ocean', 'name': 'Ocean', 'colors': {'primary': '#0077BE', 'accent': '#00B4D8'}},
        {'id': 'purple', 'name': 'Purple', 'colors': {'primary': '#6B46C1', 'accent': '#9F7AEA'}}
    ]
    settings = read_csv('system_settings.csv')
    active_theme = next((s.get('setting_value', 'gold') for s in settings if s.get('setting_key') == 'active_theme'), 'gold')
    return jsonify({'themes': themes, 'active_theme': active_theme})


@app.route('/api/themes', methods=['POST'])
@api_auth
def api_set_theme():
    theme_id = request.json.get('theme_id', 'gold') if request.json else 'gold'
    settings = read_csv('system_settings.csv')
    fieldnames = get_fieldnames('system_settings.csv', ['setting_key','setting_value','description'])
    found = False
    for s in settings:
        if s.get('setting_key') == 'active_theme':
            s['setting_value'] = theme_id
            found = True
            break
    if not found:
        settings.append({
            'setting_key': 'active_theme',
            'setting_value': theme_id,
            'description': 'Active dashboard theme'
        })
    write_csv('system_settings.csv', settings, fieldnames)
    log_action('set_theme', theme_id)
    return jsonify({'success': True, 'active_theme': theme_id})


# ===== API — Exchange Addresses =====

@app.route('/api/exchange-addresses')
@api_auth
def api_exchange_addresses():
    addresses = read_csv('exchange_addresses.csv')
    return jsonify({'addresses': addresses, 'count': len(addresses)})


@app.route('/api/exchange-addresses', methods=['POST'])
@api_auth
def api_add_exchange_address():
    data = request.json
    addresses = read_csv('exchange_addresses.csv')
    fieldnames = get_fieldnames('exchange_addresses.csv', ['id','exchange_name','address','network','is_active','created_at','notes'])
    new_id = f"EXA{str(int(datetime.now().timestamp()))[-6:]}"
    new_addr = {
        'id': new_id,
        'exchange_name': data.get('exchange_name', ''),
        'address': data.get('address', ''),
        'network': data.get('network', ''),
        'is_active': 'yes',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'notes': data.get('notes', '')
    }
    append_csv('exchange_addresses.csv', new_addr, fieldnames)
    log_action('add_exchange_address', new_id)
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/exchange-addresses/<addr_id>', methods=['DELETE'])
@api_auth
def api_delete_exchange_address(addr_id):
    addresses = read_csv('exchange_addresses.csv')
    fieldnames = get_fieldnames('exchange_addresses.csv', ['id','exchange_name','address','network','is_active','created_at','notes'])
    addresses = [a for a in addresses if a.get('id') != addr_id]
    write_csv('exchange_addresses.csv', addresses, fieldnames)
    log_action('delete_exchange_address', addr_id)
    return jsonify({'success': True})


@app.route('/api/exchange-addresses/<addr_id>/toggle', methods=['POST'])
@api_auth
def api_toggle_exchange_address(addr_id):
    addresses = read_csv('exchange_addresses.csv')
    fieldnames = get_fieldnames('exchange_addresses.csv', ['id','exchange_name','address','network','is_active','created_at','notes'])
    for a in addresses:
        if a.get('id') == addr_id:
            a['is_active'] = 'no' if a.get('is_active') == 'yes' else 'yes'
            break
    write_csv('exchange_addresses.csv', addresses, fieldnames)
    return jsonify({'success': True})


# ===== API — Send Message =====

@app.route('/api/send-message', methods=['POST'])
@api_auth
def api_send_message():
    data = request.json
    target_user_id = data.get('target_user_id', '')
    message = data.get('message', '')
    msg_type = data.get('type', 'text')

    msg_entry = {
        'id': f"MSG{str(int(datetime.now().timestamp()))[-6:]}",
        'target_user_id': target_user_id,
        'message': message,
        'type': msg_type,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'created_by': session.get('admin_id', ''),
        'status': 'pending'
    }
    fieldnames = ['id', 'target_user_id', 'message', 'type', 'created_at', 'created_by', 'status']
    existing = read_csv('broadcast_queue.csv')
    if existing:
        fieldnames = get_fieldnames('broadcast_queue.csv', fieldnames)
        if 'target_user_id' not in fieldnames:
            fieldnames.append('target_user_id')
    append_csv('broadcast_queue.csv', msg_entry, fieldnames)
    log_action('send_message', f'to:{target_user_id}, {message[:50]}')
    return jsonify({'success': True, 'message': 'تم حفظ الرسالة — سيتم إرسالها'})


# ===== API — Backup =====

@app.route('/api/backup', methods=['POST'])
@api_auth
def api_backup():
    backup_dir = os.path.join(BASE_DIR, 'backups')
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f'backup_{timestamp}.zip'
    backup_path = os.path.join(backup_dir, backup_filename)

    csv_files = [f for f in os.listdir(BASE_DIR) if f.endswith('.csv')]
    json_files = [f for f in os.listdir(BASE_DIR) if f.endswith('.json')]
    all_files = csv_files + json_files

    file_count = 0
    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname in all_files:
            fpath = os.path.join(BASE_DIR, fname)
            if os.path.exists(fpath) and os.path.isfile(fpath):
                zf.write(fpath, fname)
                file_count += 1

    log_action('backup', f'{backup_filename}: {file_count} files')
    return jsonify({'success': True, 'backup_file': backup_filename, 'files': file_count})


@app.route('/api/backups')
@api_auth
def api_backups():
    backup_dir = os.path.join(BASE_DIR, 'backups')
    backups = []
    if os.path.exists(backup_dir):
        for fname in os.listdir(backup_dir):
            if fname.endswith('.zip'):
                fpath = os.path.join(backup_dir, fname)
                stat = os.stat(fpath)
                backups.append({
                    'filename': fname,
                    'size': stat.st_size,
                    'created_at': datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
                })
    backups.sort(key=lambda x: x['created_at'], reverse=True)
    return jsonify({'backups': backups, 'count': len(backups)})


# ===== API — Lottery Actions =====

@app.route('/api/lottery/create', methods=['POST'])
@api_auth
def api_lottery_create():
    data = request.json
    rounds = read_csv('lottery_rounds.csv')
    fieldnames = get_fieldnames('lottery_rounds.csv', ['id','name','ticket_price','currency','winner_count','max_tickets','admin_pct','draw_time','status','created_at'])
    new_id = f"LOT{str(int(datetime.now().timestamp()))[-6:]}"
    new_round = {
        'id': new_id,
        'name': data.get('name', ''),
        'ticket_price': data.get('ticket_price', '0'),
        'currency': data.get('currency', 'SAR'),
        'winner_count': data.get('winner_count', '1'),
        'max_tickets': data.get('max_tickets', '100'),
        'admin_pct': data.get('admin_pct', '0'),
        'draw_time': data.get('draw_time', ''),
        'status': 'active',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    append_csv('lottery_rounds.csv', new_round, fieldnames)
    log_action('lottery_create', new_id)
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/lottery/<round_id>/draw', methods=['POST'])
@api_auth
def api_lottery_draw(round_id):
    rounds = read_csv('lottery_rounds.csv')
    round_fieldnames = get_fieldnames('lottery_rounds.csv', ['id','name','ticket_price','currency','winner_count','max_tickets','admin_pct','draw_time','status','created_at'])

    lot_round = None
    for r in rounds:
        if r.get('id') == round_id:
            lot_round = r
            r['status'] = 'drawn'
            break

    if not lot_round:
        return jsonify({'error': 'Round not found'}), 404

    write_csv('lottery_rounds.csv', rounds, round_fieldnames)

    tickets = read_csv('lottery_tickets.csv')
    round_tickets = [t for t in tickets if t.get('round_id') == round_id and t.get('payment_verified') == 'yes']

    winner_count = int(lot_round.get('winner_count', '1'))
    winners = []
    if round_tickets and winner_count > 0:
        if winner_count >= len(round_tickets):
            selected = round_tickets
        else:
            selected = random.sample(round_tickets, winner_count)

        winner_fieldnames = get_fieldnames('lottery_winners.csv', ['id','round_id','user_id','ticket_id','prize_amount','currency','distributed','created_at'])
        for w in selected:
            winner_entry = {
                'id': f"WIN{secrets.token_hex(3).upper()}",
                'round_id': round_id,
                'user_id': w.get('user_id', ''),
                'ticket_id': w.get('id', ''),
                'prize_amount': lot_round.get('ticket_price', '0'),
                'currency': lot_round.get('currency', 'SAR'),
                'distributed': 'no',
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
            }
            append_csv('lottery_winners.csv', winner_entry, winner_fieldnames)
            winners.append(winner_entry)

    log_action('lottery_draw', f'{round_id}: {len(winners)} winners')
    return jsonify({'success': True, 'winners': winners, 'winners_count': len(winners)})


# ===== API — Wheel Actions =====

@app.route('/api/wheel/create', methods=['POST'])
@api_auth
def api_wheel_create():
    data = request.json
    rounds = read_csv('wheel_rounds.csv')
    fieldnames = get_fieldnames('wheel_rounds.csv', ['id','name','prizes','status','spin_cost','currency','min_spins','max_spins_per_user','game_speed_ms','max_relocations','created_at'])
    new_id = f"WHL{str(int(datetime.now().timestamp()))[-6:]}"
    prizes = data.get('prizes', '')
    if isinstance(prizes, list):
        prizes = '|'.join(prizes) if len(prizes) > 1 else (prizes[0] if prizes else '')
    new_round = {
        'id': new_id,
        'name': data.get('name', ''),
        'prizes': prizes,
        'status': 'active',
        'spin_cost': data.get('spin_cost', '0'),
        'currency': data.get('currency', 'SAR'),
        'min_spins': '1',
        'max_spins_per_user': data.get('max_spins_per_user', data.get('max_spins', '1')),
        'game_speed_ms': data.get('game_speed_ms', '2500'),
        'max_relocations': data.get('max_relocations', '1'),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    append_csv('wheel_rounds.csv', new_round, fieldnames)
    log_action('wheel_create', new_id)
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/wheel/<round_id>/end', methods=['POST'])
@api_auth
def api_wheel_end(round_id):
    rounds = read_csv('wheel_rounds.csv')
    fieldnames = get_fieldnames('wheel_rounds.csv', ['id','name','prizes','status','spin_cost','currency','min_spins','max_spins_per_user','game_speed_ms','max_relocations','created_at'])
    for r in rounds:
        if r.get('id') == round_id:
            r['status'] = 'completed'
            break
    write_csv('wheel_rounds.csv', rounds, fieldnames)
    log_action('wheel_end', round_id)
    return jsonify({'success': True})


# ===== API — Matching Actions =====

@app.route('/api/matching/<req_id>/approve', methods=['POST'])
@api_auth
def api_matching_approve(req_id):
    reqs = read_csv('match_requests.csv')
    fieldnames = get_fieldnames('match_requests.csv', ['id','user_id','customer_id','type','amount','currency','status','created_at','approved_by','approved_at'])
    for r in reqs:
        if r.get('id') == req_id:
            r['status'] = 'approved'
            r['approved_by'] = session.get('admin_id', '')
            r['approved_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            break
    write_csv('match_requests.csv', reqs, fieldnames)
    log_action('matching_approve', req_id)
    return jsonify({'success': True})


@app.route('/api/matching/<req_id>/reject', methods=['POST'])
@api_auth
def api_matching_reject(req_id):
    reason = request.json.get('reason', '') if request.json else ''
    reqs = read_csv('match_requests.csv')
    fieldnames = get_fieldnames('match_requests.csv', ['id','user_id','customer_id','type','amount','currency','status','created_at','approved_by','approved_at'])
    for r in reqs:
        if r.get('id') == req_id:
            r['status'] = 'rejected'
            break
    write_csv('match_requests.csv', reqs, fieldnames)
    log_action('matching_reject', f'{req_id}: {reason}')
    return jsonify({'success': True})


@app.route('/api/matching/<match_id>/resolve-dispute', methods=['POST'])
@api_auth
def api_resolve_dispute(match_id):
    favor = request.json.get('favor', 'cancel') if request.json else 'cancel'
    note = request.json.get('note', '') if request.json else ''

    matches = read_csv('matches.csv')
    match_fieldnames = get_fieldnames('matches.csv', ['id','depositor_id','withdrawer_id','depositor_txn_id','withdrawer_txn_id','status','created_at','resolved_by','resolution'])
    for m in matches:
        if m.get('id') == match_id:
            if favor == 'depositor':
                m['status'] = 'completed'
            elif favor == 'withdrawer':
                m['status'] = 'completed'
            else:
                m['status'] = 'cancelled'
            m['resolution'] = favor
            m['resolved_by'] = session.get('admin_id', '')
            break
    write_csv('matches.csv', matches, match_fieldnames)

    disputes = read_csv('disputes.csv')
    dispute_fieldnames = get_fieldnames('disputes.csv', ['id','match_id','raised_by','reason','status','created_at','resolution','resolved_by','resolved_at'])
    for d in disputes:
        if d.get('match_id') == match_id and d.get('status') != 'resolved':
            d['status'] = 'resolved'
            d['resolution'] = favor
            d['resolved_by'] = session.get('admin_id', '')
            d['resolved_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            break
    write_csv('disputes.csv', disputes, dispute_fieldnames)

    log_action('resolve_dispute', f'{match_id}: {favor}')
    return jsonify({'success': True})


# ===== API — Trading Actions =====

@app.route('/api/trading/<order_id>/accept', methods=['POST'])
@api_auth
def api_trading_accept(order_id):
    orders = read_csv('trade_orders.csv')
    fieldnames = get_fieldnames('trade_orders.csv', ['id','user_id','order_type','amount','currency','rate','status','created_at','accepted_by','accepted_at','completed_at'])
    for o in orders:
        if o.get('id') == order_id:
            o['status'] = 'accepted'
            o['accepted_by'] = session.get('admin_id', '')
            o['accepted_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            break
    write_csv('trade_orders.csv', orders, fieldnames)
    log_action('trading_accept', order_id)
    return jsonify({'success': True})


@app.route('/api/trading/<order_id>/set-rate', methods=['POST'])
@api_auth
def api_trading_set_rate(order_id):
    rate = request.json.get('rate', '') if request.json else ''
    orders = read_csv('trade_orders.csv')
    fieldnames = get_fieldnames('trade_orders.csv', ['id','user_id','order_type','amount','currency','rate','status','created_at','accepted_by','accepted_at','completed_at'])
    for o in orders:
        if o.get('id') == order_id:
            o['rate'] = rate
            break
    write_csv('trade_orders.csv', orders, fieldnames)
    log_action('trading_set_rate', f'{order_id}: {rate}')
    return jsonify({'success': True})


@app.route('/api/trading/<order_id>/complete', methods=['POST'])
@api_auth
def api_trading_complete(order_id):
    orders = read_csv('trade_orders.csv')
    fieldnames = get_fieldnames('trade_orders.csv', ['id','user_id','order_type','amount','currency','rate','status','created_at','accepted_by','accepted_at','completed_at'])
    for o in orders:
        if o.get('id') == order_id:
            o['status'] = 'completed'
            o['completed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            break
    write_csv('trade_orders.csv', orders, fieldnames)
    log_action('trading_complete', order_id)
    return jsonify({'success': True})


# ===== API — Support Data =====

@app.route('/api/support-data')
@api_auth
def api_support_data():
    settings = read_csv('system_settings.csv')
    support_keys = ['support_phone', 'support_telegram', 'support_email', 'support_hours']
    support_data = {}
    for s in settings:
        key = s.get('setting_key', '')
        if key in support_keys:
            support_data[key] = s.get('setting_value', '')
    for k in support_keys:
        if k not in support_data:
            support_data[k] = ''
    return jsonify({'support_data': support_data})


@app.route('/api/support-data', methods=['POST'])
@api_auth
def api_update_support_data():
    data = request.json
    settings = read_csv('system_settings.csv')
    fieldnames = get_fieldnames('system_settings.csv', ['setting_key','setting_value','description'])
    support_keys = ['support_phone', 'support_telegram', 'support_email', 'support_hours']
    descriptions = {
        'support_phone': 'Support phone number',
        'support_telegram': 'Support Telegram username',
        'support_email': 'Support email address',
        'support_hours': 'Support working hours'
    }
    for key in support_keys:
        if key in data:
            found = False
            for s in settings:
                if s.get('setting_key') == key:
                    s['setting_value'] = data[key]
                    found = True
                    break
            if not found:
                settings.append({
                    'setting_key': key,
                    'setting_value': data[key],
                    'description': descriptions.get(key, '')
                })
    write_csv('system_settings.csv', settings, fieldnames)
    log_action('update_support_data', json.dumps(data)[:100])
    return jsonify({'success': True})


# ===== API — Payment Steps =====

@app.route('/api/payment-steps/<method_id>')
@api_auth
def api_payment_steps(method_id):
    steps = read_csv('payment_steps.csv')
    method_steps = [s for s in steps if s.get('method_id') == method_id]
    deposit_steps = [s for s in method_steps if s.get('step_type') == 'deposit']
    withdraw_steps = [s for s in method_steps if s.get('step_type') == 'withdraw']
    return jsonify({
        'method_id': method_id,
        'deposit_steps': deposit_steps,
        'withdraw_steps': withdraw_steps
    })


@app.route('/api/payment-steps/<method_id>', methods=['POST'])
@api_auth
def api_save_payment_steps(method_id):
    data = request.json
    deposit_steps = data.get('deposit_steps', [])
    withdraw_steps = data.get('withdraw_steps', [])

    steps = read_csv('payment_steps.csv')
    steps = [s for s in steps if s.get('method_id') != method_id]
    fieldnames = get_fieldnames('payment_steps.csv', ['id','method_id','step_type','step_order','title','description','image_url'])

    for i, step in enumerate(deposit_steps):
        step_entry = {
            'id': f"STP{secrets.token_hex(3).upper()}",
            'method_id': method_id,
            'step_type': 'deposit',
            'step_order': str(i + 1),
            'title': step.get('title', ''),
            'description': step.get('description', ''),
            'image_url': step.get('image_url', '')
        }
        steps.append(step_entry)

    for i, step in enumerate(withdraw_steps):
        step_entry = {
            'id': f"STP{secrets.token_hex(3).upper()}",
            'method_id': method_id,
            'step_type': 'withdraw',
            'step_order': str(i + 1),
            'title': step.get('title', ''),
            'description': step.get('description', ''),
            'image_url': step.get('image_url', '')
        }
        steps.append(step_entry)

    write_csv('payment_steps.csv', steps, fieldnames)
    log_action('save_payment_steps', method_id)
    return jsonify({'success': True, 'deposit_count': len(deposit_steps), 'withdraw_count': len(withdraw_steps)})


# ===== API — Detailed Statistics =====

@app.route('/api/detailed-stats')
@api_auth
def api_detailed_stats():
    today = datetime.now().strftime('%Y-%m-%d')
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    users = read_csv('users.csv')
    txns = read_csv('transactions.csv')
    matches = read_csv('matches.csv')
    companies = read_csv('companies.csv')
    complaints = read_csv('complaints.csv')

    # User stats
    user_stats = {
        'total': len(users),
        'new_today': sum(1 for u in users if u.get('date', '').startswith(today)),
        'new_this_week': sum(1 for u in users if u.get('date', '') >= week_ago),
        'new_this_month': sum(1 for u in users if u.get('date', '') >= month_ago),
        'banned': sum(1 for u in users if u.get('is_banned') == 'yes'),
        'verified': sum(1 for u in users if u.get('phone_verified') == 'yes')
    }

    # Transaction stats by type
    txn_stats = {
        'total': len(txns),
        'deposits': sum(1 for t in txns if t.get('type') == 'deposit'),
        'withdrawals': sum(1 for t in txns if t.get('type') == 'withdraw'),
        'pending': sum(1 for t in txns if t.get('status') == 'pending'),
        'approved': sum(1 for t in txns if t.get('status') == 'approved'),
        'rejected': sum(1 for t in txns if t.get('status') == 'rejected')
    }

    # Volume stats
    volume_stats = {
        'today': 0.0, 'week': 0.0, 'month': 0.0, 'all_time': 0.0,
        'today_count': 0, 'week_count': 0, 'month_count': 0
    }
    for t in txns:
        if t.get('status') == 'approved':
            try:
                amt = float(t.get('amount', 0) or 0)
                tdate = t.get('date', '')
                if tdate.startswith(today):
                    volume_stats['today'] += amt
                    volume_stats['today_count'] += 1
                if tdate >= week_ago:
                    volume_stats['week'] += amt
                    volume_stats['week_count'] += 1
                if tdate >= month_ago:
                    volume_stats['month'] += amt
                    volume_stats['month_count'] += 1
                volume_stats['all_time'] += amt
            except Exception:
                pass

    # Average transaction amount
    avg_amount = 0.0
    if txn_stats['approved'] > 0:
        try:
            total_approved = sum(float(t.get('amount', 0) or 0) for t in txns if t.get('status') == 'approved')
            avg_amount = total_approved / txn_stats['approved']
        except Exception:
            pass

    # Top 10 users by transaction count
    user_txn_count = {}
    user_txn_volume = {}
    for t in txns:
        tid = t.get('telegram_id', '')
        if tid:
            user_txn_count[tid] = user_txn_count.get(tid, 0) + 1
            try:
                if t.get('status') == 'approved':
                    user_txn_volume[tid] = user_txn_volume.get(tid, 0) + float(t.get('amount', 0) or 0)
            except Exception:
                pass

    user_names = {}
    for u in users:
        user_names[u.get('telegram_id', '')] = u.get('name', '')

    top_users = sorted(user_txn_count.items(), key=lambda x: x[1], reverse=True)[:10]
    top_users_data = [{'telegram_id': tid, 'name': user_names.get(tid, ''), 'txn_count': cnt, 'volume': user_txn_volume.get(tid, 0)} for tid, cnt in top_users]

    # Top 5 companies by volume
    company_vol = {}
    for t in txns:
        if t.get('status') == 'approved':
            company = t.get('company', '')
            try:
                company_vol[company] = company_vol.get(company, 0) + float(t.get('amount', 0) or 0)
            except Exception:
                pass
    top_companies = sorted(company_vol.items(), key=lambda x: x[1], reverse=True)[:5]
    top_companies_data = [{'name': name, 'volume': vol} for name, vol in top_companies]

    # Match completion rate
    match_stats = {
        'total': len(matches),
        'completed': sum(1 for m in matches if m.get('status') == 'completed'),
        'cancelled': sum(1 for m in matches if m.get('status') == 'cancelled'),
        'disputed': sum(1 for m in matches if m.get('status') == 'disputed'),
        'active': sum(1 for m in matches if m.get('status') not in ('completed', 'cancelled')),
        'completion_rate': 0.0
    }
    if match_stats['total'] > 0:
        match_stats['completion_rate'] = round(match_stats['completed'] / match_stats['total'] * 100, 2)

    # Complaint resolution rate
    complaint_stats = {
        'total': len(complaints),
        'resolved': sum(1 for c in complaints if c.get('status') in ('resolved', 'closed')),
        'open': sum(1 for c in complaints if c.get('status') not in ('resolved', 'closed')),
        'resolution_rate': 0.0
    }
    if complaint_stats['total'] > 0:
        complaint_stats['resolution_rate'] = round(complaint_stats['resolved'] / complaint_stats['total'] * 100, 2)

    return jsonify({
        'kpis': {
            'total_users': user_stats['total'],
            'total_volume': round(volume_stats['all_time'], 2),
            'avg_transaction': round(avg_amount, 2),
            'completion_rate': match_stats['completion_rate'],
        },
        'users': user_stats,
        'transactions': txn_stats,
        'volume': volume_stats,
        'avg_amount': round(avg_amount, 2),
        'top_users': top_users_data,
        'top_companies': top_companies_data,
        'matches': match_stats,
        'complaints': complaint_stats,
        # Chart data (reuse /api/stats/charts format)
        'transactions_chart': None,  # will be filled by /api/stats/charts
        'status_chart': txn_stats,
        'companies_chart': {'labels': [c['name'] for c in top_companies_data], 'data': [c['volume'] for c in top_companies_data]},
        'users_chart': None,
    })


# ===== API — Notifications Log =====

@app.route('/api/notifications-log')
@api_auth
def api_notifications_log():
    logs = read_csv('notifications_log.csv')
    logs.reverse()
    return jsonify({'notifications': logs[:50], 'total': len(logs)})


# ===== API — User Edit =====

@app.route('/api/users/<user_id>', methods=['PUT'])
@api_auth
def api_edit_user(user_id):
    data = request.json
    users = read_csv('users.csv')
    fieldnames = get_fieldnames('users.csv', ['telegram_id','name','phone','customer_id','language','date','is_banned','ban_reason','currency'])
    editable_fields = ['name', 'phone', 'currency', 'language', 'phone_verified', 'is_banned', 'ban_reason']
    for u in users:
        if u.get('telegram_id') == user_id:
            for k, v in data.items():
                if k in editable_fields:
                    if k not in fieldnames:
                        fieldnames.append(k)
                    u[k] = v
            break
    write_csv('users.csv', users, fieldnames)
    log_action('edit_user', f'{user_id}: {json.dumps(data)[:100]}')
    return jsonify({'success': True})

# ===== API — Company Toggle =====

@app.route('/api/companies/<company_id>/toggle', methods=['POST'])
@api_auth
def api_toggle_company(company_id):
    companies = read_csv('companies.csv')
    fieldnames = get_fieldnames('companies.csv', ['id','name','type','details','is_active','icon','address','affiliate_link'])
    for c in companies:
        if c.get('id') == company_id:
            c['is_active'] = 'no' if c.get('is_active') == 'yes' else 'yes'
            break
    write_csv('companies.csv', companies, fieldnames)
    log_action('toggle_company', company_id)
    return jsonify({'success': True})

# ===== API — User Activity =====

@app.route('/api/users/<user_id>/activity')
@api_auth
def api_user_activity(user_id):
    activity = read_csv('user_activity.csv')
    user_act = [a for a in activity if a.get('telegram_id') == user_id]
    return jsonify({'activity': user_act})

# ===== API — SVRP Freeze/Unfreeze =====

@app.route('/api/svrp/wallets/<user_id>/freeze', methods=['POST'])
@api_auth
def api_svrp_freeze(user_id):
    wallets = read_csv('svrp_wallets.csv')
    fieldnames = get_fieldnames('svrp_wallets.csv', ['telegram_id','customer_id','balance','pending_balance','total_earned','total_used','wagering_required','wagering_completed','last_recovery_date','monthly_recovery_total'])
    for w in wallets:
        if w.get('telegram_id') == user_id:
            # نقل كل الرصيد إلى مجمد
            balance = float(w.get('balance', 0) or 0)
            frozen = float(w.get('pending_balance', 0) or 0)
            w['pending_balance'] = str(balance + frozen)
            w['balance'] = '0'
            break
    write_csv('svrp_wallets.csv', wallets, fieldnames)
    log_action('svrp_freeze', user_id)
    return jsonify({'success': True, 'message': 'تم تجميد الرصيد'})

@app.route('/api/svrp/wallets/<user_id>/unfreeze', methods=['POST'])
@api_auth
def api_svrp_unfreeze(user_id):
    data = request.json or {}
    amount = float(data.get('amount', 0))
    wallets = read_csv('svrp_wallets.csv')
    fieldnames = get_fieldnames('svrp_wallets.csv', ['telegram_id','customer_id','balance','pending_balance','total_earned','total_used','wagering_required','wagering_completed','last_recovery_date','monthly_recovery_total'])
    for w in wallets:
        if w.get('telegram_id') == user_id:
            frozen = float(w.get('pending_balance', 0) or 0)
            balance = float(w.get('balance', 0) or 0)
            if amount <= 0:
                amount = frozen  # فك تجميد كامل
            amount = min(amount, frozen)
            w['balance'] = str(balance + amount)
            w['pending_balance'] = str(frozen - amount)
            break
    write_csv('svrp_wallets.csv', wallets, fieldnames)
    log_action('svrp_unfreeze', f'{user_id}: {amount}')
    return jsonify({'success': True, 'message': f'تم فك تجميد {amount}'})

# ===== API — SVRP Credits =====

@app.route('/api/svrp/credits')
@api_auth
def api_svrp_credits():
    credits = read_csv('svrp_credits.csv')
    return jsonify({'credits': credits[:100], 'total': len(credits)})

# ===== API — SVRP Tasks =====

@app.route('/api/svrp/tasks')
@api_auth
def api_svrp_tasks():
    tasks = read_csv('svrp_tasks.csv')
    return jsonify({'tasks': tasks[:100]})

# ===== API — User Company Accounts =====

@app.route('/api/users/<user_id>/company-accounts')
@api_auth
def api_user_company_accounts(user_id):
    accounts = read_csv('user_company_accounts.csv')
    user_accounts = [a for a in accounts if a.get('user_id') == user_id]
    return jsonify({'accounts': user_accounts})

# ===== API — Match Ratings =====

@app.route('/api/matching/ratings')
@api_auth
def api_match_ratings():
    ratings = read_csv('ratings.csv')
    ratings.reverse()
    return jsonify({'ratings': ratings[:50]})

# ===== API — Referral Earnings Per User =====

@app.route('/api/referrals/earnings')
@api_auth
def api_referral_earnings():
    log = read_csv('referral_log.csv')
    # تجميع الأرباح لكل مستخدم
    earnings = {}
    for r in log:
        referrer = r.get('referrer_id', '')
        bonus = float(r.get('bonus', 0) or 0)
        if referrer:
            if referrer not in earnings:
                earnings[referrer] = {'total': 0, 'count': 0, 'verified': 0}
            earnings[referrer]['total'] += bonus
            earnings[referrer]['count'] += 1
            if r.get('phone_verified') == 'yes':
                earnings[referrer]['verified'] += 1
    return jsonify({'earnings': earnings, 'total_log': len(log)})

# ===== API — Broadcast Queue =====

@app.route('/api/broadcast/queue')
@api_auth
def api_broadcast_queue():
    queue = read_csv('broadcast_queue.csv')
    queue.reverse()
    return jsonify({'queue': queue[:50]})

# ===== API — Edit Transaction =====

@app.route('/api/transactions/<txn_id>', methods=['PUT'])
@api_auth
def api_edit_transaction(txn_id):
    data = request.json
    txns = read_csv('transactions.csv')
    fieldnames = get_fieldnames('transactions.csv', ['id','customer_id','telegram_id','name','type','company','wallet_number','amount','exchange_address','status','date','admin_note','processed_by','currency'])
    editable = ['amount', 'company', 'wallet_number', 'admin_note', 'currency', 'status']
    for t in txns:
        if t.get('id') == txn_id:
            for k, v in data.items():
                if k in editable:
                    if k not in fieldnames:
                        fieldnames.append(k)
                    t[k] = v
            break
    write_csv('transactions.csv', txns, fieldnames)
    log_action('edit_transaction', f'{txn_id}: {json.dumps(data)[:100]}')
    return jsonify({'success': True})

# ===== API — Delete Lottery Round =====

@app.route('/api/lottery/<round_id>', methods=['DELETE'])
@api_auth
def api_delete_lottery_round(round_id):
    rounds = read_csv('lottery_rounds.csv')
    fieldnames = get_fieldnames('lottery_rounds.csv', ['id','name','status','ticket_price','currency','min_tickets','max_tickets_per_user','total_prize','admin_profit_pct','start_time','draw_time','winner_count','created_at'])
    rounds = [r for r in rounds if r.get('id') != round_id]
    write_csv('lottery_rounds.csv', rounds, fieldnames)
    log_action('delete_lottery_round', round_id)
    return jsonify({'success': True})

# ===== API — Delete Wheel Round =====

@app.route('/api/wheel/<round_id>', methods=['DELETE'])
@api_auth
def api_delete_wheel_round(round_id):
    rounds = read_csv('wheel_rounds.csv')
    fieldnames = get_fieldnames('wheel_rounds.csv', ['id','name','prizes','status','spin_cost','currency','min_spins','max_spins_per_user','game_speed_ms','max_relocations','created_at'])
    rounds = [r for r in rounds if r.get('id') != round_id]
    write_csv('wheel_rounds.csv', rounds, fieldnames)
    log_action('delete_wheel_round', round_id)
    return jsonify({'success': True})

# ===== API — Restore Backup =====

@app.route('/api/backup/restore', methods=['POST'])
@api_auth
def api_restore_backup():
    filename = request.json.get('filename', '') if request.json else ''
    if not filename:
        return jsonify({'error': 'No filename'}), 400
    import zipfile
    backup_path = os.path.join(BASE_DIR, 'backups', filename)
    if not os.path.exists(backup_path):
        return jsonify({'error': 'Backup not found'}), 404
    try:
        with zipfile.ZipFile(backup_path, 'r') as zf:
            zf.extractall(BASE_DIR)
        log_action('restore_backup', filename)
        return jsonify({'success': True, 'message': 'تم استعادة النسخة'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ===== API — Backup Download =====

@app.route('/api/backups/<filename>/download')
@api_auth
def api_download_backup(filename):
    import zipfile
    backup_path = os.path.join(BASE_DIR, 'backups', filename)
    if not os.path.exists(backup_path):
        return jsonify({'error': 'Backup not found'}), 404
    return send_file(backup_path, as_attachment=True, download_name=filename)

# ===== API — Send Message Recent =====

@app.route('/api/send-message/recent')
@api_auth
def api_send_message_recent():
    """رسائل مرسلة لمستخدمين محددين"""
    queue = read_csv('broadcast_queue.csv')
    targeted = [q for q in queue if q.get('target_user_id', '')]
    targeted.reverse()
    return jsonify({'messages': targeted[:50]})

# =====================================================
# ===== VEX GAMES PLATFORM — API =====
# =====================================================

# تهيئة محرك الألعاب
try:
    import sys as _sys
    _sys.path.insert(0, BASE_DIR)
    from game_engine import GameManager
    _gm = GameManager()
    _VEX_GAMES = True
except Exception as e:
    print(f"VEX Games init error: {e}")
    _VEX_GAMES = False

# ===== Games Catalog =====

@app.route('/api/games/list')
@webapp_auth
def api_games_list():
    """قائمة الألعاب النشطة"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    games = _gm.get_games(active_only=True)
    return jsonify({'games': games, 'count': len(games)})

@app.route('/api/games/all')
@api_auth
def api_games_all():
    """كل الألعاب (للأدمن)"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    games = _gm.get_games(active_only=False)
    return jsonify({'games': games})

@app.route('/api/games/create', methods=['POST'])
@api_auth
def api_games_create():
    """إضافة لعبة جديدة"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    game_id = _gm.add_game(
        name=data.get('name', ''),
        icon=data.get('icon', '🎮'),
        description=data.get('description', ''),
        category=data.get('category', 'arcade'),
        min_bet=data.get('min_bet', 10),
        max_bet=data.get('max_bet', 1000),
        base_win_chance=data.get('base_win_chance', 0.45),
        house_edge_pct=data.get('house_edge_pct', 15),
        rtp_target=data.get('rtp_target', 85),
        volatility=data.get('volatility', 'medium')
    )
    return jsonify({'success': True, 'id': game_id})

@app.route('/api/games/<game_id>/toggle', methods=['POST'])
@api_auth
def api_games_toggle(game_id):
    """تفعيل/إيقاف لعبة"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    try:
        rows = []
        with open(os.path.join(BASE_DIR, 'games_catalog.csv'), 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                if row.get('id') == game_id:
                    row['is_active'] = 'no' if row.get('is_active') == 'yes' else 'yes'
                rows.append(row)
        with open(os.path.join(BASE_DIR, 'games_catalog.csv'), 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    except:
        pass
    return jsonify({'success': True})

# ===== Wallet =====

@app.route('/api/wallet/balance')
@webapp_auth
def api_wallet_balance():
    """رصيد اللاعب + عملته"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    uid = get_request_uid()
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    balance = _gm.get_balance(uid)
    user_info = _gm.get_user_info(uid)
    currency = user_info.get('currency', 'EGP')
    return jsonify({'balance': balance, 'uid': uid, 'currency': currency})

@app.route('/api/wallet/add', methods=['POST'])
@api_auth
def api_wallet_add():
    """إضافة رصيد (أدمن)"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = data.get('uid', '')
    amount = float(data.get('amount', 0))
    reason = data.get('reason', 'admin_adjustment')
    if not uid or amount <= 0:
        return jsonify({'error': 'Invalid params'}), 400
    new_balance = _gm.add_balance(uid, amount, reason)
    return jsonify({'success': True, 'new_balance': new_balance})

# ===== Live Players =====

@app.route('/api/games/live-players')
@webapp_auth
def api_live_players():
    """قائمة اللاعبين المباشرين"""
    if not _VEX_GAMES:
        return jsonify({'players': [], 'count': 0})
    # قراءة آخر جلسات نشطة
    players = []
    try:
        import os
        sessions_file = os.path.join(BASE_DIR, 'game_sessions.csv')
        if os.path.exists(sessions_file):
            rows = []
            with open(sessions_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            # آخر 20 جلسة
            for row in rows[-20:]:
                players.append({
                    'uid': row.get('user_id', ''),
                    'name': '',  # يتم جلب الاسم من users.csv
                    'bet': float(row.get('bet_amount', 0) or 0),
                    'status': 'win' if row.get('result') == 'win' else 'lose',
                    'payout': float(row.get('payout', 0) or 0),
                    'multiplier': float(row.get('multiplier', 0) or 0),
                    'timestamp': row.get('timestamp', '')
                })
    except:
        pass
    return jsonify({'players': players, 'count': len(players)})

# ===== Game Engine =====

@app.route('/api/engine/start', methods=['POST'])
@webapp_auth
def api_engine_start():
    """بدء جلسة لعب"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    game_id = data.get('game_id', '')
    bet_amount = float(data.get('bet_amount', 0))
    if not uid or not game_id or bet_amount <= 0:
        return jsonify({'error': 'Missing params'}), 400
    result = _gm.start_session(uid, game_id, bet_amount)
    return jsonify(result)

@app.route('/api/engine/end', methods=['POST'])
@webapp_auth
def api_engine_end():
    """إنهاء جلسة لعب"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    result = _gm.end_session(
        session_id=data.get('session_id', ''),
        user_id=uid,
        game_id=data.get('game_id', ''),
        bet_amount=float(data.get('bet_amount', 0)),
        result=data.get('result', 'lose'),
        payout=float(data.get('payout', 0))
    )
    return jsonify(result)

@app.route('/api/engine/result', methods=['POST'])
@webapp_auth
def api_engine_result():
    """تسجيل نتيجة من WebApp — يحسب الفوز/الخسارة server-side"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    game_id = data.get('game_id', '')
    bet_amount = float(data.get('bet_amount', 0))
    session_id = data.get('session_id', '')

    # بدء الجلسة (خصم + حساب الاحتمال)
    start_result = _gm.start_session(uid, game_id, bet_amount)
    if not start_result.get('success'):
        return jsonify(start_result)

    # تطبيق النتيجة — مضاعف ديناميكي
    decision = start_result.get('decision', 'force_lose')
    if decision == 'allow_win':
        player_profile = _gm.tracker.get_profile(uid)
        multiplier = _gm.calculate_payout_multiplier(game, player_profile)
        payout = bet_amount * multiplier
        result_str = 'win'
    elif decision == 'disguised_loss':
        import random as _rng
        payout = bet_amount * _rng.uniform(0.5, 0.9)
        result_str = 'win'
    elif decision == 'near_miss':
        payout = 0
        result_str = 'lose'
    else:
        payout = 0
        result_str = 'lose'

    # إنهاء الجلسة
    end_result = _gm.end_session(
        session_id=start_result['session_id'],
        user_id=uid,
        game_id=game_id,
        bet_amount=bet_amount,
        result=result_str,
        payout=payout
    )

    # الأنماط النفسية
    psych = start_result.get('psychological_hints', {})

    return jsonify({
        'success': True,
        'result': result_str,
        'payout': payout,
        'balance_before': end_result['balance_before'],
        'balance_after': end_result['balance_after'],
        'decision': decision,
        'psychological_hints': psych,
        'near_miss': decision == 'near_miss',
        'session_id': start_result['session_id'],
    })

# ===== Quick Deposits =====

@app.route('/api/games/payment-methods')
@webapp_auth
def api_games_payment_methods():
    """وسائل الدفع النشطة المتاحة للألعاب — مفلترة حسب عملة المستخدم"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    uid = get_request_uid()
    user_info = _gm.get_user_info(uid)
    user_currency = user_info.get('currency', 'EGP')
    methods = _gm.get_games_payment_methods(user_currency)
    saved_methods = _gm.get_payment_methods(uid)
    return jsonify({
        'methods': methods,
        'saved_methods': saved_methods,
        'count': len(methods),
        'currency': user_currency
    })

@app.route('/api/deposit/quick', methods=['POST'])
@webapp_auth
def api_deposit_quick():
    """طلب إيداع سريع — ينشئ معاملة حقيقية في transactions.csv بملاحظة VEX"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    amount = float(data.get('amount', 0))
    method_id = data.get('method_id', '')
    method_name = data.get('method_name', '')
    method_account_data = data.get('method_account_data', '')
    player_wallet = data.get('player_wallet', '')
    save_method = data.get('save_method', False)
    if not uid or amount <= 0 or not method_id:
        return jsonify({'error': 'Missing params'}), 400

    # Get user info for admin notification
    user_info = _gm.get_user_info(uid)
    user_name = user_info.get('name', '')
    customer_id = user_info.get('customer_id', '')
    currency = user_info.get('currency', 'SAR')

    dep_id = _gm.create_quick_deposit(
        uid, amount, method_id, method_account_data,
        method_name=method_name,
        method_account_data=method_account_data,
        player_wallet=player_wallet,
        save_method=save_method
    )

    # Push to dashboard
    push_notification(
        'game_deposit',
        f'💰 إيداع محفظة VEX',
        f'اللاعب {user_name} ({customer_id}) طلب إيداع {amount} {currency}\nالوسيلة: {method_name}\nمحفظة اللاعب: {player_wallet}',
        {'deposit_id': dep_id, 'uid': uid, 'amount': amount, 'method': method_name}
    )

    return jsonify({
        'success': True,
        'deposit_id': dep_id,
        'trans_id': f"DEP{datetime.now().strftime('%Y%m%d%H%M%S')}",
        'status': 'pending'
    })

@app.route('/api/deposit/pending')
@api_auth
def api_deposit_pending():
    """طلبات الإيداع المعلقة"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    deposits = _gm.get_pending_deposits()
    return jsonify({'deposits': deposits, 'count': len(deposits)})

@app.route('/api/deposit/<dep_id>/approve', methods=['POST'])
@api_auth
def api_deposit_approve(dep_id):
    """موافقة على إيداع سريع — async: يضيف الرصيد + يرسل إشعار"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    admin_id = session.get('admin_id', '')
    result = _gm.approve_deposit(dep_id, admin_id)
    if result:
        push_notification('deposit_approved', '✅ تمت الموافقة على إيداع', f'إيداع {dep_id}', {'deposit_id': dep_id})
        # async Telegram notification (non-blocking)
        import threading as _th
        _uid = result.get('user_id', '')
        _amt = float(result.get('amount', 0))
        _dep = dep_id
        def _notify():
            try:
                if BOT_TOKEN and _uid:
                    import urllib.request as _u
                    _msg = f"✅ تمت الموافقة على إيداعك!\n\n💰 المبلغ: {_amt:.0f}\n🎮 تم إضافته لمحفظة VEX\n🆔 {_dep}"
                    _u.urlopen(_u.Request(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                        data=json.dumps({'chat_id': int(_uid), 'text': _msg, 'parse_mode': 'HTML'}).encode('utf-8'),
                        headers={'Content-Type': 'application/json'}), timeout=5)
            except: pass
        _th.Thread(target=_notify, daemon=True).start()
        return jsonify({'success': True, 'deposit': result})
    return jsonify({'error': 'Deposit not found or already processed'}), 404

@app.route('/api/deposit/<dep_id>/reject', methods=['POST'])
@api_auth
def api_deposit_reject(dep_id):
    """رفض إيداع سريع — async notification"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    admin_id = session.get('admin_id', '')
    result = _gm.reject_deposit(dep_id, admin_id)
    push_notification('deposit_rejected', '❌ تم رفض إيداع', f'إيداع {dep_id}', {'deposit_id': dep_id})
    # async Telegram notification
    if result and result.get('user_id'):
        import threading as _th
        _uid = result.get('user_id', '')
        _dep = dep_id
        def _notify_r():
            try:
                if BOT_TOKEN and _uid:
                    import urllib.request as _u
                    _msg = f"❌ تم رفض إيداعك\n\n🆔 {_dep}\n\nللمساعدة، تواصل مع الدعم."
                    _u.urlopen(_u.Request(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                        data=json.dumps({'chat_id': int(_uid), 'text': _msg, 'parse_mode': 'HTML'}).encode('utf-8'),
                        headers={'Content-Type': 'application/json'}), timeout=5)
            except: pass
        _th.Thread(target=_notify_r, daemon=True).start()
    return jsonify({'success': True})

# ===== Player Payment Methods =====

@app.route('/api/player/currency', methods=['POST'])
@webapp_auth
def api_player_change_currency():
    """تغيير عملة المستخدم في users.csv"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    new_currency = data.get('currency', 'EGP')
    try:
        rows = []
        with open(os.path.join(BASE_DIR, 'users.csv'), 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                if row.get('telegram_id') == str(uid):
                    row['currency'] = new_currency
                rows.append(row)
        with open(os.path.join(BASE_DIR, 'users.csv'), 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return jsonify({'success': True, 'currency': new_currency})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/player/methods')
@webapp_auth
def api_player_methods():
    """وسائل دفع اللاعب المحفوظة"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    uid = get_request_uid()
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    methods = _gm.get_payment_methods(uid)
    return jsonify({'methods': methods})

@app.route('/api/player/methods/add', methods=['POST'])
@webapp_auth
def api_player_methods_add():
    """إضافة وسيلة دفع للاعب"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    method_id = _gm.add_payment_method(
        user_id=uid,
        method_name=data.get('method_name', ''),
        account_number=data.get('account_number', ''),
        method_type=data.get('method_type', 'bank'),
        icon=data.get('icon', '💳')
    )
    return jsonify({'success': True, 'method_id': method_id})

# ===== Player Profile =====

@app.route('/api/player/profile')
@webapp_auth
def api_player_profile():
    """ملف اللاعب"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    uid = get_request_uid()
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    profile = _gm.tracker.get_profile(uid)
    segment = _gm.tracker.get_segment(profile)
    return jsonify({'profile': profile, 'segment': segment})

@app.route('/api/player/vex-status', methods=['POST'])
@api_auth
def api_player_vex_status():
    """تعيين شريك VEX"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = data.get('uid', '')
    is_partner = data.get('is_partner', False)
    _gm.tracker.set_vex_partner(uid, is_partner)
    return jsonify({'success': True})

# ===== Admin: Platform Stats =====

@app.route('/api/games/stats')
@api_auth
def api_games_stats():
    """إحصائيات المنصة"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    stats = _gm.get_platform_stats()
    health = _gm.risk.check_platform_health()
    return jsonify({**stats, 'health': health})

@app.route('/api/games/alerts')
@api_auth
def api_games_alerts():
    """تنبيهات المخاطر"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    alerts = _gm.risk.get_active_alerts()
    return jsonify({'alerts': alerts, 'count': len(alerts)})

@app.route('/api/games/top-players')
@api_auth
def api_games_top_players():
    """أعلى اللاعبين"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    sort_by = request.args.get('sort', 'total_wagered')
    players = _gm.tracker.get_top_players(limit=20, sort_by=sort_by)
    return jsonify({'players': players})

@app.route('/api/games/config', methods=['GET', 'POST'])
@api_auth
def api_games_config():
    """قراءة/تحديث إعدادات الخوارزمية"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    if request.method == 'POST':
        data = request.json
        for key, value in data.items():
            _gm.algorithm.update_config(key, value)
        return jsonify({'success': True})
    else:
        return jsonify({'config': _gm.algorithm.config})

# ===== Games WebApp Pages =====

@app.route('/webapp/games')
def webapp_games():
    """مركز الألعاب — WebApp"""
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    return render_template('games_hub.html', uid=uid, lang=lang)

@app.route('/webapp/play/<game_id>')
def webapp_play(game_id):
    """شاشة اللعبة — WebApp"""
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    if not _VEX_GAMES:
        return "Games engine not available", 500
    game = _gm.get_game(game_id)
    if not game:
        return "Game not found", 404
    return render_template('game_play.html', uid=uid, lang=lang, game=game)

@app.route('/games-admin')
@login_required
def page_games_admin():
    """لوحة إدارة الألعاب"""
    return render_template('games_admin.html', active_page='games_admin')

# ===== Aviator — WebApp + API =====

@app.route('/webapp/aviator')
def webapp_aviator():
    """لعبة Aviator — WebApp"""
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    return render_template('aviator.html', uid=uid, lang=lang)

@app.route('/api/engine/aviator/start', methods=['POST'])
@webapp_auth
def api_aviator_start():
    """بدء جلسة Aviator — خصم الرهان + حساب نقطة الانفجار"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    bet_amount = float(data.get('bet_amount', 0))
    if not uid or bet_amount <= 0:
        return jsonify({'error': 'Missing params'}), 400

    player = _gm.tracker.get_profile(uid)
    game = _gm.get_game('GAME004')  # Aviator

    # إذا اللعبة غير موجودة، استخدم إعدادات افتراضية
    if not game:
        game = {'id': 'GAME004', 'base_win_chance': '0.40', 'house_edge_pct': '20', 'min_bet': '10', 'max_bet': '2000'}

    # فحص المخاطر
    risk_check = _gm.risk.check_risk(player, bet_amount, game)
    if not risk_check['allowed']:
        return jsonify({'success': False, 'error': risk_check['alerts'][0]['message'] if risk_check['alerts'] else 'محظور'})

    # التحقق من الرصيد
    balance = float(player.get('balance', 0) or 0)
    if balance < bet_amount:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance})

    # حساب نقطة الانفجار باستخدام الخوارزمية
    # احتمال "النجاة" حتى multiplier معين = 1/multiplier^(1/house_edge)
    # كلما زاد house_edge، تنفجر أبكر
    import random
    house_edge = float(game.get('house_edge_pct', 20)) / 100

    # استخدام الخوارزمية لضبط الاحتمال
    algo_result = _gm.algorithm.calculate_win_chance(player, game, bet_amount)
    win_chance = algo_result['win_chance']

    # تحويل احتمال الفوز إلى crash point
    # crash_point = 1 / (1 - win_chance * 0.99) تقريباً
    # كلما قلّ win_chance، قلّ crash_point (انفجار أبكر)
    if win_chance > 0.8:
        # لاعب يجب أن يربح — crash point عالي
        crash_point = random.uniform(3.0, 15.0)
    elif win_chance > 0.6:
        crash_point = random.uniform(2.0, 6.0)
    elif win_chance > 0.4:
        crash_point = random.uniform(1.3, 3.5)
    elif win_chance > 0.2:
        crash_point = random.uniform(1.05, 2.0)
    else:
        # لاعب يجب أن يخسر — crash point منخفض جداً
        crash_point = random.uniform(1.00, 1.3)

    # تطبيق house edge على crash point
    crash_point = max(1.0, crash_point * (1 - house_edge * 0.3))

    # خصم الرصيد
    balance_after = balance - bet_amount
    player['balance'] = f"{balance_after:.2f}"
    _gm.tracker._save_profile(player)

    # تسجيل الجلسة
    session_id = f"AVI{str(int(datetime.now().timestamp()))[-8:]}"

    # تسجيل قرار الخوارزمية
    _gm.algorithm.log_decision(
        session_id=session_id, user_id=uid, game_id='GAME004',
        base_chance=float(game.get('base_win_chance', 0.40)),
        adjusted_chance=win_chance,
        factors=algo_result['factors'],
        decision=algo_result['decision'],
        reason=f"Aviator crash_point={crash_point:.2f}; {algo_result['reason']}"
    )

    return jsonify({
        'success': True,
        'session_id': session_id,
        'crash_point': round(crash_point, 2),
        'balance_before': balance,
        'balance_after': balance_after,
    })

@app.route('/api/engine/aviator/cashout', methods=['POST'])
@webapp_auth
def api_aviator_cashout():
    """سحب الرهان في Aviator"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    session_id = data.get('session_id', '')
    uid = get_request_uid()
    multiplier = float(data.get('multiplier', 1.0))
    bet_amount = float(data.get('bet_amount', 0))

    payout = bet_amount * multiplier
    new_balance = _gm.add_balance(uid, payout)

    return jsonify({
        'success': True,
        'payout': payout,
        'multiplier': multiplier,
        'balance_after': new_balance,
    })

@app.route('/api/engine/aviator/end', methods=['POST'])
@webapp_auth
def api_aviator_end():
    """إنهاء جلسة Aviator — تسجيل النتيجة"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    crash_point = float(data.get('crash_point', 1.0))
    cashed_out = data.get('cashed_out', False)
    multiplier = float(data.get('multiplier', 0))
    bet_amount = float(data.get('bet_amount', 0))
    session_id = data.get('session_id', '')

    result = 'win' if cashed_out else 'lose'
    payout = bet_amount * multiplier if cashed_out else 0

    # تسجيل الجلسة
    _gm.tracker.log_session({
        'session_id': session_id,
        'game_id': 'GAME004',
        'user_id': uid,
        'bet_amount': bet_amount,
        'payout': payout,
        'result': result,
        'balance_before': 0,
        'balance_after': _gm.get_balance(uid),
        'multiplier': multiplier,
    })

    # تحديث ملف اللاعب
    _gm.tracker.update_profile(uid, {
        'bet_amount': bet_amount,
        'payout': payout,
        'result': result,
        'game_id': 'GAME004',
        'balance_after': _gm.get_balance(uid),
    })

    return jsonify({'success': True, 'result': result, 'payout': payout})

# ===== Wallet Withdrawal =====

@app.route('/api/wallet/withdraw', methods=['POST'])
@webapp_auth
def api_wallet_withdraw():
    """طلب سحب من محفظة الألعاب"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    amount = float(data.get('amount', 0))
    method_id = data.get('method_id', '')
    account_number = data.get('account_number', '')
    if not uid or amount <= 0:
        return jsonify({'error': 'Missing params'}), 400
    dep_id, error = _gm.create_withdrawal(uid, amount, method_id, account_number)
    if error:
        return jsonify({'success': False, 'error': error})
    push_notification('game_withdrawal', '💸 طلب سحب جديد', f'لاعب {uid} طلب سحب {amount}', {'withdrawal_id': dep_id, 'uid': uid, 'amount': amount})
    return jsonify({'success': True, 'withdrawal_id': dep_id, 'status': 'pending'})

@app.route('/api/withdrawal/pending')
@api_auth
def api_withdrawal_pending():
    """طلبات السحب المعلقة"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    withdrawals = _gm.get_pending_withdrawals()
    return jsonify({'withdrawals': withdrawals, 'count': len(withdrawals)})

@app.route('/api/withdrawal/<wth_id>/approve', methods=['POST'])
@api_auth
def api_withdrawal_approve(wth_id):
    """موافقة على سحب"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    admin_id = session.get('admin_id', '')
    result = _gm.approve_withdrawal(wth_id, admin_id)
    if result:
        push_notification('withdrawal_approved', '✅ تمت الموافقة على سحب', f'سحب {wth_id} تمت الموافقة', {'withdrawal_id': wth_id})
        return jsonify({'success': True, 'withdrawal': result})
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/withdrawal/<wth_id>/reject', methods=['POST'])
@api_auth
def api_withdrawal_reject(wth_id):
    """رفض سحب — إعادة الرصيد"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    admin_id = session.get('admin_id', '')
    result = _gm.reject_withdrawal(wth_id, admin_id)
    if result:
        push_notification('withdrawal_rejected', '❌ تم رفض سحب', f'سحب {wth_id} تم رفض — الرصيد مُرتجع', {'withdrawal_id': wth_id})
        return jsonify({'success': True, 'withdrawal': result})
    return jsonify({'error': 'Not found'}), 404

# ===== Admin Per-Player Controls =====

@app.route('/api/admin/player/<uid>/win-override', methods=['POST'])
@api_auth
def api_admin_win_override(uid):
    """تحكم أدمن باحتمال فوز لاعب محدد"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    win_override = float(data.get('win_override', 0))
    # 0 = عادي، >0 = احتمال محدد، -1 = خسارة مضمونة
    profile = _gm.tracker.get_profile(uid)
    profile['admin_win_override'] = str(win_override)
    _gm.tracker._save_profile(profile)
    return jsonify({'success': True, 'win_override': win_override})

@app.route('/api/admin/player/<uid>/balance', methods=['POST'])
@api_auth
def api_admin_player_balance(uid):
    """إضافة/خصم رصيد يدوي"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    amount = float(data.get('amount', 0))
    if amount > 0:
        new_bal = _gm.add_balance(uid, amount)
    else:
        _, new_bal = _gm.deduct_balance(uid, abs(amount))
    return jsonify({'success': True, 'new_balance': new_bal})

@app.route('/api/admin/player/<uid>/block', methods=['POST'])
@api_auth
def api_admin_block_player(uid):
    """حظر لاعب من اللعب"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    _gm.tracker.set_cooldown(uid, minutes=1440)  # 24 ساعة
    return jsonify({'success': True})

@app.route('/api/admin/player/<uid>/cooldown', methods=['POST'])
@api_auth
def api_admin_cooldown_player(uid):
    """تبريد لاعب"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    minutes = int(data.get('minutes', 15))
    _gm.tracker.set_cooldown(uid, minutes=minutes)
    return jsonify({'success': True, 'cooldown_minutes': minutes})

@app.route('/api/admin/player/<uid>/vex', methods=['POST'])
@api_auth
def api_admin_vex_partner(uid):
    """تفعيل/إيقاف شريك VEX"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    is_partner = data.get('is_partner', False)
    _gm.tracker.set_vex_partner(uid, is_partner)
    return jsonify({'success': True})

# ===== Crash — WebApp + API =====

@app.route('/webapp/crash')
def webapp_crash():
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    return render_template('crash.html', uid=uid, lang=lang)

@app.route('/api/engine/crash/start', methods=['POST'])
@webapp_auth
def api_crash_start():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    bet_amount = float(data.get('bet_amount', 0))
    if not uid or bet_amount <= 0:
        return jsonify({'error': 'Missing params'}), 400

    player = _gm.tracker.get_profile(uid)
    game = _gm.get_game('GAME005')
    if not game:
        game = {'id': 'GAME005', 'base_win_chance': '0.42', 'house_edge_pct': '17', 'min_bet': '10', 'max_bet': '5000'}

    risk_check = _gm.risk.check_risk(player, bet_amount, game)
    if not risk_check['allowed']:
        return jsonify({'success': False, 'error': risk_check['alerts'][0]['message'] if risk_check['alerts'] else 'محظور'})

    balance = float(player.get('balance', 0) or 0)
    if balance < bet_amount:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance})

    import random as _rng
    house_edge = float(game.get('house_edge_pct', 17)) / 100
    algo_result = _gm.algorithm.calculate_win_chance(player, game, bet_amount)
    win_chance = algo_result['win_chance']

    if win_chance > 0.8:
        crash_point = _rng.uniform(3.0, 15.0)
    elif win_chance > 0.6:
        crash_point = _rng.uniform(2.0, 6.0)
    elif win_chance > 0.4:
        crash_point = _rng.uniform(1.3, 3.5)
    elif win_chance > 0.2:
        crash_point = _rng.uniform(1.05, 2.0)
    else:
        crash_point = _rng.uniform(1.00, 1.3)
    crash_point = max(1.0, crash_point * (1 - house_edge * 0.3))

    balance_after = balance - bet_amount
    player['balance'] = f"{balance_after:.2f}"
    _gm.tracker._save_profile(player)

    session_id = f"CRSH{str(int(datetime.now().timestamp()))[-8:]}"
    _gm.algorithm.log_decision(
        session_id=session_id, user_id=uid, game_id='GAME005',
        base_chance=float(game.get('base_win_chance', 0.42)),
        adjusted_chance=win_chance, factors=algo_result['factors'],
        decision=algo_result['decision'],
        reason=f"Crash crash_point={crash_point:.2f}; {algo_result['reason']}"
    )
    return jsonify({'success': True, 'session_id': session_id, 'crash_point': round(crash_point, 2), 'balance_before': balance, 'balance_after': balance_after})

@app.route('/api/engine/crash/cashout', methods=['POST'])
@webapp_auth
def api_crash_cashout():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    session_id = data.get('session_id', '')
    uid = get_request_uid()
    multiplier = float(data.get('multiplier', 1.0))
    bet_amount = float(data.get('bet_amount', 0))
    payout = bet_amount * multiplier
    new_balance = _gm.add_balance(uid, payout)
    return jsonify({'success': True, 'payout': payout, 'multiplier': multiplier, 'balance_after': new_balance})

@app.route('/api/engine/crash/end', methods=['POST'])
@webapp_auth
def api_crash_end():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    crash_point = float(data.get('crash_point', 1.0))
    cashed_out = data.get('cashed_out', False)
    multiplier = float(data.get('multiplier', 0))
    bet_amount = float(data.get('bet_amount', 0))
    session_id = data.get('session_id', '')
    result = 'win' if cashed_out else 'lose'
    payout = bet_amount * multiplier if cashed_out else 0
    _gm.tracker.log_session({'session_id': session_id, 'game_id': 'GAME005', 'user_id': uid, 'bet_amount': bet_amount, 'payout': payout, 'result': result, 'balance_before': 0, 'balance_after': _gm.get_balance(uid), 'multiplier': multiplier})
    _gm.tracker.update_profile(uid, {'bet_amount': bet_amount, 'payout': payout, 'result': result, 'game_id': 'GAME005', 'balance_after': _gm.get_balance(uid)})
    return jsonify({'success': True, 'result': result, 'payout': payout})

# ===== Mines — WebApp + API =====

@app.route('/webapp/mines')
def webapp_mines():
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    return render_template('mines.html', uid=uid, lang=lang)

@app.route('/api/engine/mines/start', methods=['POST'])
@webapp_auth
def api_mines_start():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    bet_amount = float(data.get('bet_amount', 0))
    mine_count = int(data.get('mine_count', 3))
    if not uid or bet_amount <= 0:
        return jsonify({'error': 'Missing params'}), 400
    mine_count = max(1, min(24, mine_count))

    player = _gm.tracker.get_profile(uid)
    game = _gm.get_game('GAME006')
    if not game:
        game = {'id': 'GAME006', 'base_win_chance': '0.45', 'house_edge_pct': '15', 'min_bet': '10', 'max_bet': '2000'}

    risk_check = _gm.risk.check_risk(player, bet_amount, game)
    if not risk_check['allowed']:
        return jsonify({'success': False, 'error': risk_check['alerts'][0]['message'] if risk_check['alerts'] else 'محظور'})

    balance = float(player.get('balance', 0) or 0)
    if balance < bet_amount:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance})

    import random as _rng
    # Place mines randomly
    all_positions = list(range(25))
    _rng.shuffle(all_positions)
    mine_positions = all_positions[:mine_count]

    # Algorithm decides if player should win overall
    algo_result = _gm.algorithm.calculate_win_chance(player, game, bet_amount)
    win_chance = algo_result['win_chance']

    # If algorithm says lose, ensure first revealed tile near mines
    # If algorithm says win, keep mines away from common first picks (center)
    if algo_result['decision'] == 'force_lose' and _rng.random() < 0.6:
        # Bias: move a mine near center (positions 6,7,8,11,12,13,16,17,18)
        center_positions = [6,7,8,11,12,13,16,17,18]
        non_center_mines = [m for m in mine_positions if m not in center_positions]
        if non_center_mines:
            swap_out = _rng.choice(non_center_mines)
            swap_in = _rng.choice([c for c in center_positions if c not in mine_positions])
            mine_positions.remove(swap_out)
            mine_positions.append(swap_in)

    balance_after = balance - bet_amount
    player['balance'] = f"{balance_after:.2f}"
    _gm.tracker._save_profile(player)

    session_id = f"MINE{str(int(datetime.now().timestamp()))[-8:]}"
    _gm.algorithm.log_decision(
        session_id=session_id, user_id=uid, game_id='GAME006',
        base_chance=float(game.get('base_win_chance', 0.45)),
        adjusted_chance=win_chance, factors=algo_result['factors'],
        decision=algo_result['decision'],
        reason=f"Mines count={mine_count}; {algo_result['reason']}"
    )

    # Store mine positions in a temp file keyed by session
    import json as _json
    mines_state_file = os.path.join(BASE_DIR, 'mines_sessions.json')
    mines_state = {}
    try:
        if os.path.exists(mines_state_file):
            with open(mines_state_file, 'r') as f:
                mines_state = _json.load(f)
    except:
        pass
    mines_state[session_id] = {
        'uid': uid, 'mine_positions': mine_positions, 'bet_amount': bet_amount,
        'mine_count': mine_count, 'revealed': [], 'multiplier': 1.0,
        'game_over': False, 'created_at': datetime.now().isoformat()
    }
    with open(mines_state_file, 'w') as f:
        _json.dump(mines_state, f)

    return jsonify({'success': True, 'session_id': session_id, 'balance_before': balance, 'balance_after': balance_after})

@app.route('/api/engine/mines/reveal', methods=['POST'])
@webapp_auth
def api_mines_reveal():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    session_id = data.get('session_id', '')
    tile_index = int(data.get('tile_index', -1))
    if tile_index < 0 or tile_index > 24:
        return jsonify({'error': 'Invalid tile'}), 400

    import json as _json
    mines_state_file = os.path.join(BASE_DIR, 'mines_sessions.json')
    if not os.path.exists(mines_state_file):
        return jsonify({'error': 'Session not found'}), 404
    try:
        with open(mines_state_file, 'r') as f:
            mines_state = _json.load(f)
    except:
        return jsonify({'error': 'State error'}), 500

    state = mines_state.get(session_id)
    if not state or state.get('uid') != uid or state.get('game_over'):
        return jsonify({'error': 'Invalid session'}), 400

    if tile_index in state['revealed']:
        return jsonify({'error': 'Already revealed'}), 400

    mine_positions = state['mine_positions']
    is_mine = tile_index in mine_positions
    state['revealed'].append(tile_index)

    if is_mine:
        state['game_over'] = True
        state['multiplier'] = 0
        with open(mines_state_file, 'w') as f:
            _json.dump(mines_state, f)
        return jsonify({'success': True, 'is_mine': True, 'multiplier': 0, 'game_over': True})

    # Calculate multiplier based on revealed count and mine count
    revealed_count = len(state['revealed'])
    safe_count = 25 - state['mine_count']
    # Multiplier grows with each safe reveal: product of (25-i)/(25-mine_count-i) for each step
    mult = 1.0
    for i in range(revealed_count):
        mult *= (25 - i) / (25 - state['mine_count'] - i)
    # Apply house edge
    game = _gm.get_game('GAME006')
    house_edge = float(game.get('house_edge_pct', 15)) / 100 if game else 0.15
    mult *= (1 - house_edge * 0.5)
    state['multiplier'] = round(mult, 4)

    game_over = revealed_count >= safe_count
    if game_over:
        state['game_over'] = True

    with open(mines_state_file, 'w') as f:
        _json.dump(mines_state, f)

    return jsonify({'success': True, 'is_mine': False, 'multiplier': state['multiplier'], 'game_over': game_over})

@app.route('/api/engine/mines/cashout', methods=['POST'])
@webapp_auth
def api_mines_cashout():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    session_id = data.get('session_id', '')
    multiplier = float(data.get('multiplier', 1.0))
    bet_amount = float(data.get('bet_amount', 0))

    import json as _json
    mines_state_file = os.path.join(BASE_DIR, 'mines_sessions.json')
    try:
        with open(mines_state_file, 'r') as f:
            mines_state = _json.load(f)
        state = mines_state.get(session_id)
        if state:
            state['game_over'] = True
            with open(mines_state_file, 'w') as f:
                _json.dump(mines_state, f)
    except:
        pass

    payout = bet_amount * multiplier
    new_balance = _gm.add_balance(uid, payout)
    return jsonify({'success': True, 'payout': payout, 'multiplier': multiplier, 'balance_after': new_balance})

@app.route('/api/engine/mines/end', methods=['POST'])
@webapp_auth
def api_mines_end():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    won = data.get('won', False)
    multiplier = float(data.get('multiplier', 0))
    bet_amount = float(data.get('bet_amount', 0))
    session_id = data.get('session_id', '')
    result = 'win' if won else 'lose'
    payout = bet_amount * multiplier if won else 0
    _gm.tracker.log_session({'session_id': session_id, 'game_id': 'GAME006', 'user_id': uid, 'bet_amount': bet_amount, 'payout': payout, 'result': result, 'balance_before': 0, 'balance_after': _gm.get_balance(uid), 'multiplier': multiplier})
    _gm.tracker.update_profile(uid, {'bet_amount': bet_amount, 'payout': payout, 'result': result, 'game_id': 'GAME006', 'balance_after': _gm.get_balance(uid)})
    return jsonify({'success': True, 'result': result, 'payout': payout})

# ===== Plinko — WebApp + API =====

@app.route('/webapp/plinko')
def webapp_plinko():
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    return render_template('plinko.html', uid=uid, lang=lang)

@app.route('/webapp/wheel')
def webapp_wheel():
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    return render_template('wheel.html', uid=uid, lang=lang)

@app.route('/webapp/lottery')
def webapp_lottery():
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    return render_template('lottery.html', uid=uid, lang=lang)

@app.route('/api/engine/plinko/start', methods=['POST'])
@webapp_auth
def api_plinko_start():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    bet_amount = float(data.get('bet_amount', 0))
    if not uid or bet_amount <= 0:
        return jsonify({'error': 'Missing params'}), 400

    player = _gm.tracker.get_profile(uid)
    game = _gm.get_game('GAME007')
    if not game:
        game = {'id': 'GAME007', 'base_win_chance': '0.40', 'house_edge_pct': '16', 'min_bet': '10', 'max_bet': '2000'}

    risk_check = _gm.risk.check_risk(player, bet_amount, game)
    if not risk_check['allowed']:
        return jsonify({'success': False, 'error': risk_check['alerts'][0]['message'] if risk_check['alerts'] else 'محظور'})

    balance = float(player.get('balance', 0) or 0)
    if balance < bet_amount:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance})

    import random as _rng
    # 13 slots (0-12), multipliers: [10, 3, 1.5, 1, 0.5, 0.3, 0.2, 0.3, 0.5, 1, 1.5, 3, 10]
    MULTIPLIERS = [10, 3, 1.5, 1, 0.5, 0.3, 0.2, 0.3, 0.5, 1, 1.5, 3, 10]

    algo_result = _gm.algorithm.calculate_win_chance(player, game, bet_amount)
    win_chance = algo_result['win_chance']

    # Weight slot selection based on win_chance
    # High win_chance → bias toward edges (high multipliers)
    # Low win_chance → bias toward center (low multipliers)
    if win_chance > 0.6:
        # Bias toward edge slots (0, 12 = 10x)
        weights = [5, 4, 3, 2, 1, 1, 1, 1, 1, 2, 3, 4, 5]
    elif win_chance > 0.4:
        weights = [2, 3, 3, 3, 2, 2, 2, 2, 2, 3, 3, 3, 2]
    else:
        # Bias toward center (low multipliers)
        weights = [1, 1, 2, 2, 3, 4, 5, 4, 3, 2, 2, 1, 1]

    total_weight = sum(weights)
    rand_val = _rng.uniform(0, total_weight)
    target_slot = 0
    cumulative = 0
    for i, w in enumerate(weights):
        cumulative += w
        if rand_val <= cumulative:
            target_slot = i
            break

    multiplier = MULTIPLIERS[target_slot]
    payout = bet_amount * multiplier
    result = 'win' if multiplier >= 1 else 'lose'

    # Apply disguised loss: if bet > 50 and multiplier < 1, sometimes show as small win
    if bet_amount > 50 and multiplier < 1 and _rng.random() < 0.3 and algo_result['decision'] != 'force_lose':
        # Find a nearby slot with multiplier 0.5-0.9
        for offset in range(1, 4):
            for direction in [1, -1]:
                check_slot = target_slot + direction * offset
                if 0 <= check_slot < len(MULTIPLIERS) and MULTIPLIERS[check_slot] >= 0.5:
                    target_slot = check_slot
                    multiplier = MULTIPLIERS[check_slot]
                    payout = bet_amount * multiplier
                    break
            else:
                continue
            break

    balance_after = balance - bet_amount
    player['balance'] = f"{balance_after:.2f}"
    _gm.tracker._save_profile(player)

    session_id = f"PLNK{str(int(datetime.now().timestamp()))[-8:]}"
    _gm.algorithm.log_decision(
        session_id=session_id, user_id=uid, game_id='GAME007',
        base_chance=float(game.get('base_win_chance', 0.40)),
        adjusted_chance=win_chance, factors=algo_result['factors'],
        decision=algo_result['decision'],
        reason=f"Plinko slot={target_slot} mult={multiplier}; {algo_result['reason']}"
    )

    return jsonify({
        'success': True, 'session_id': session_id, 'target_slot': target_slot,
        'multiplier': multiplier, 'payout': round(payout, 2), 'result': result,
        'balance_before': balance, 'balance_after': balance_after
    })

@app.route('/api/engine/plinko/end', methods=['POST'])
@webapp_auth
def api_plinko_end():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    multiplier = float(data.get('multiplier', 0))
    payout = float(data.get('payout', 0))
    result = data.get('result', 'lose')
    bet_amount = float(data.get('bet_amount', 0))
    session_id = data.get('session_id', '')
    # Add payout to balance (already calculated in start, but we add on end for consistency)
    if payout > 0:
        _gm.add_balance(uid, payout)
    _gm.tracker.log_session({'session_id': session_id, 'game_id': 'GAME007', 'user_id': uid, 'bet_amount': bet_amount, 'payout': payout, 'result': result, 'balance_before': 0, 'balance_after': _gm.get_balance(uid), 'multiplier': multiplier})
    _gm.tracker.update_profile(uid, {'bet_amount': bet_amount, 'payout': payout, 'result': result, 'game_id': 'GAME007', 'balance_after': _gm.get_balance(uid)})
    return jsonify({'success': True, 'result': result, 'payout': payout})

# ===== Main =====

if __name__ == '__main__':
    print(f"🚀 Boterx Dashboard v2 — http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=True, threaded=True)
