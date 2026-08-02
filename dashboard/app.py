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
import secrets
import random
import zipfile
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   session, jsonify, Response, flash, send_file)

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

# ===== Routes — Pages =====

@app.route('/')
@login_required
def index():
    return redirect(url_for('dashboard'))

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
            return redirect(url_for('dashboard'))
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
    txns = read_csv('transactions.csv')
    fieldnames = get_fieldnames('transactions.csv', ['id','customer_id','telegram_id','name','type','company','wallet_number','amount','exchange_address','status','date','admin_note','processed_by','currency'])
    for t in txns:
        if t.get('id') == txn_id:
            t['status'] = 'approved'
            t['processed_by'] = session.get('admin_id', '')
            break
    write_csv('transactions.csv', txns, fieldnames)
    log_action('approve_transaction', txn_id)
    return jsonify({'success': True})

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
    fieldnames = get_fieldnames('wheel_rounds.csv', ['id','name','prizes','max_spins','status','created_at'])
    new_id = f"WHL{str(int(datetime.now().timestamp()))[-6:]}"
    prizes = data.get('prizes', '')
    if isinstance(prizes, list):
        prizes = json.dumps(prizes)
    new_round = {
        'id': new_id,
        'name': data.get('name', ''),
        'prizes': prizes,
        'max_spins': data.get('max_spins', '100'),
        'status': 'active',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    append_csv('wheel_rounds.csv', new_round, fieldnames)
    log_action('wheel_create', new_id)
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/wheel/<round_id>/end', methods=['POST'])
@api_auth
def api_wheel_end(round_id):
    rounds = read_csv('wheel_rounds.csv')
    fieldnames = get_fieldnames('wheel_rounds.csv', ['id','name','prizes','max_spins','status','created_at'])
    for r in rounds:
        if r.get('id') == round_id:
            r['status'] = 'ended'
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
    fieldnames = get_fieldnames('wheel_rounds.csv', ['id','name','prizes','status','spin_cost','currency','min_spins','max_spins_per_user','created_at'])
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
    # رسائل لها target_user_id (ليست بث عام)
    targeted = [q for q in queue if q.get('target_user_id', '')]
    targeted.reverse()
    return jsonify({'messages': targeted[:50]})

# ===== Main =====

if __name__ == '__main__':
    print(f"🚀 Boterx Dashboard v2 — http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=True, threaded=True)
