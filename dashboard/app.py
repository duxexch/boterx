#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Boterx Web Dashboard — Flask Application
لوحة تحكم ويب احترافية لإدارة بوت Boterx
"""

import os
import csv
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response, flash
from flask_bcrypt import Bcrypt

# ===== Configuration =====
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', '8080'))
DASHBOARD_HOST = os.getenv('DASHBOARD_HOST', '0.0.0.0')
SECRET_KEY = os.getenv('DASHBOARD_SECRET_KEY', secrets.token_hex(32))

# Admin credentials from .env
ADMIN_IDS = os.getenv('ADMIN_USER_IDS', '').split(',')
ADMIN_PASSWORD = os.getenv('DASHBOARD_PASSWORD', 'boterx_admin_2026')

app = Flask(__name__,
    template_folder='templates',
    static_folder='static'
)
app.secret_key = SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

bcrypt = Bcrypt(app)

# ===== CSV Helpers =====
def read_csv(filename):
    """قراءة ملف CSV وإرجاع قائمة dict"""
    filepath = os.path.join(BASE_DIR, filename)
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception as e:
        print(f"Error reading {filename}: {e}")
        return []

def write_csv(filename, rows, fieldnames):
    """كتابة قائمة dict في ملف CSV"""
    filepath = os.path.join(BASE_DIR, filename)
    with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def append_csv(filename, row, fieldnames):
    """إضافة صف في ملف CSV"""
    filepath = os.path.join(BASE_DIR, filename)
    with open(filepath, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writerow({k: row.get(k, '') for k in fieldnames})

# ===== Auth =====
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def api_auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function

# ===== Routes =====

@app.route('/')
@login_required
def index():
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        admin_id = request.form.get('admin_id', '')
        
        # التحقق من admin_id
        if admin_id and admin_id.strip() in [a.strip() for a in ADMIN_IDS if a.strip()]:
            if password == ADMIN_PASSWORD:
                session['logged_in'] = True
                session['admin_id'] = admin_id.strip()
                session['login_time'] = datetime.now().isoformat()
                return redirect(url_for('dashboard'))
            else:
                error = 'كلمة المرور غير صحيحة'
        else:
            error = 'معرف الأدمن غير صحيح'
    
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', active_page='dashboard')

# ===== API Endpoints =====

@app.route('/api/stats')
@api_auth_required
def api_stats():
    """إحصائيات عامة للوحة"""
    stats = {
        'users': {'total': 0, 'today': 0, 'banned': 0},
        'transactions': {'total': 0, 'pending': 0, 'approved': 0, 'rejected': 0, 'today': 0},
        'matches': {'active': 0, 'pending': 0, 'completed': 0},
        'lottery': {'participants': 0, 'winners': 0, 'distributed': 0.0},
        'wheel': {'participants': 0},
        'trading': {'pending_orders': 0},
        'volume': {'today': 0.0, 'week': 0.0, 'month': 0.0}
    }
    
    # Users
    users = read_csv('users.csv')
    stats['users']['total'] = len(users)
    stats['users']['banned'] = sum(1 for u in users if u.get('is_banned') == 'yes')
    today = datetime.now().strftime('%Y-%m-%d')
    stats['users']['today'] = sum(1 for u in users if u.get('date', '').startswith(today))
    
    # Transactions
    txns = read_csv('transactions.csv')
    stats['transactions']['total'] = len(txns)
    stats['transactions']['pending'] = sum(1 for t in txns if t.get('status') == 'pending')
    stats['transactions']['approved'] = sum(1 for t in txns if t.get('status') == 'approved')
    stats['transactions']['rejected'] = sum(1 for t in txns if t.get('status') == 'rejected')
    stats['transactions']['today'] = sum(1 for t in txns if t.get('date', '').startswith(today))
    
    # Volume
    for t in txns:
        if t.get('status') == 'approved':
            try:
                amt = float(t.get('amount', 0))
                tdate = t.get('date', '')
                if tdate.startswith(today):
                    stats['volume']['today'] += amt
                if tdate >= (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'):
                    stats['volume']['week'] += amt
                if tdate >= (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'):
                    stats['volume']['month'] += amt
            except:
                pass
    
    # Matches
    matches = read_csv('matches.csv')
    stats['matches']['active'] = sum(1 for m in matches if m.get('status') not in ('completed', 'cancelled'))
    stats['matches']['completed'] = sum(1 for m in matches if m.get('status') == 'completed')
    
    match_reqs = read_csv('match_requests.csv')
    stats['matches']['pending'] = sum(1 for r in match_reqs if r.get('status') == 'waiting')
    
    # Lottery
    lot_tickets = read_csv('lottery_tickets.csv')
    lot_rounds = read_csv('lottery_rounds.csv')
    active_lot = None
    for r in lot_rounds:
        if r.get('status') == 'active':
            active_lot = r
            break
    if active_lot:
        stats['lottery']['participants'] = len(set(t.get('user_id') for t in lot_tickets if t.get('round_id') == active_lot.get('id') and t.get('payment_verified') == 'yes'))
        stats['lottery']['winners'] = int(active_lot.get('winner_count', 0))
    
    lot_winners = read_csv('lottery_winners.csv')
    stats['lottery']['distributed'] = sum(float(w.get('prize_amount', 0) or 0) for w in lot_winners)
    
    # Wheel
    wheel_spins = read_csv('wheel_spins.csv')
    wheel_rounds = read_csv('wheel_rounds.csv')
    active_wheel = None
    for r in wheel_rounds:
        if r.get('status') == 'active':
            active_wheel = r
            break
    if active_wheel:
        stats['wheel']['participants'] = len(set(s.get('user_id') for s in wheel_spins if s.get('round_id') == active_wheel.get('id')))
    
    # Trading
    trade_orders = read_csv('trade_orders.csv')
    stats['trading']['pending_orders'] = sum(1 for o in trade_orders if o.get('status') == 'pending')
    
    return jsonify(stats)

@app.route('/api/stats/live')
@api_auth_required
def api_stats_live():
    """SSE — إحصائيات حية كل 5 ثواني"""
    def generate():
        while True:
            # إعادة استخدام منطق api_stats
            import time
            data = {
                'timestamp': datetime.now().isoformat(),
                'users_total': len(read_csv('users.csv')),
                'pending_txns': sum(1 for t in read_csv('transactions.csv') if t.get('status') == 'pending'),
                'active_matches': sum(1 for m in read_csv('matches.csv') if m.get('status') not in ('completed', 'cancelled')),
                'pending_matches': sum(1 for r in read_csv('match_requests.csv') if r.get('status') == 'waiting'),
            }
            yield f"data: {json.dumps(data)}\n\n"
            time.sleep(5)
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/transactions')
@api_auth_required
def api_transactions():
    """قائمة المعاملات مع فلترة"""
    status = request.args.get('status', '')
    tx_type = request.args.get('type', '')
    search = request.args.get('search', '')
    page = int(request.args.get('page', '1'))
    per_page = int(request.args.get('per_page', '20'))
    
    txns = read_csv('transactions.csv')
    
    # Flip for newest first
    txns.reverse()
    
    # Filter
    if status:
        txns = [t for t in txns if t.get('status') == status]
    if tx_type:
        txns = [t for t in txns if t.get('type') == tx_type]
    if search:
        search_lower = search.lower()
        txns = [t for t in txns if search_lower in t.get('name', '').lower() or 
                search_lower in t.get('customer_id', '').lower() or
                search_lower in t.get('id', '').lower()]
    
    total = len(txns)
    start = (page - 1) * per_page
    end = start + per_page
    
    return jsonify({
        'transactions': txns[start:end],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page
    })

@app.route('/api/transactions/<txn_id>/approve', methods=['POST'])
@api_auth_required
def api_approve_transaction(txn_id):
    """موافقة على معاملة"""
    txns = read_csv('transactions.csv')
    for t in txns:
        if t.get('id') == txn_id:
            t['status'] = 'approved'
            t['processed_by'] = session.get('admin_id', '')
            break
    fieldnames = read_csv('transactions.csv')
    if fieldnames:
        fieldnames = list(fieldnames[0].keys())
        write_csv('transactions.csv', txns, fieldnames)
    return jsonify({'success': True})

@app.route('/api/transactions/<txn_id>/reject', methods=['POST'])
@api_auth_required
def api_reject_transaction(txn_id):
    """رفض معاملة"""
    reason = request.json.get('reason', '') if request.json else ''
    txns = read_csv('transactions.csv')
    for t in txns:
        if t.get('id') == txn_id:
            t['status'] = 'rejected'
            t['admin_note'] = reason
            t['processed_by'] = session.get('admin_id', '')
            break
    if txns:
        fieldnames = list(txns[0].keys()) if txns else []
        # التأكد من وجود admin_note
        if 'admin_note' not in fieldnames:
            fieldnames.append('admin_note')
        write_csv('transactions.csv', txns, fieldnames)
    return jsonify({'success': True})

@app.route('/api/users')
@api_auth_required
def api_users():
    """قائمة المستخدمين"""
    search = request.args.get('search', '')
    page = int(request.args.get('page', '1'))
    per_page = int(request.args.get('per_page', '20'))
    
    users = read_csv('users.csv')
    
    if search:
        search_lower = search.lower()
        users = [u for u in users if search_lower in u.get('name', '').lower() or
                search_lower in u.get('phone', '').lower() or
                search_lower in u.get('customer_id', '').lower()]
    
    total = len(users)
    start = (page - 1) * per_page
    end = start + per_page
    
    return jsonify({
        'users': users[start:end],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page
    })

@app.route('/api/users/<user_id>/ban', methods=['POST'])
@api_auth_required
def api_ban_user(user_id):
    """حظر مستخدم"""
    users = read_csv('users.csv')
    for u in users:
        if u.get('telegram_id') == user_id:
            u['is_banned'] = 'yes'
            u['ban_reason'] = request.json.get('reason', 'محظور من لوحة التحكم') if request.json else 'محظور'
            break
    if users:
        fieldnames = list(users[0].keys())
        write_csv('users.csv', users, fieldnames)
    return jsonify({'success': True})

@app.route('/api/users/<user_id>/unban', methods=['POST'])
@api_auth_required
def api_unban_user(user_id):
    """إلغاء حظر مستخدم"""
    users = read_csv('users.csv')
    for u in users:
        if u.get('telegram_id') == user_id:
            u['is_banned'] = 'no'
            u['ban_reason'] = ''
            break
    if users:
        fieldnames = list(users[0].keys())
        write_csv('users.csv', users, fieldnames)
    return jsonify({'success': True})

@app.route('/api/companies')
@api_auth_required
def api_companies():
    """قائمة الشركات"""
    companies = read_csv('companies.csv')
    return jsonify({'companies': companies})

@app.route('/api/companies', methods=['POST'])
@api_auth_required
def api_add_company():
    """إضافة شركة"""
    data = request.json
    companies = read_csv('companies.csv')
    fieldnames = list(companies[0].keys()) if companies else ['id', 'name', 'type', 'details', 'is_active', 'icon', 'address']
    
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
    if 'affiliate_link' not in fieldnames:
        fieldnames.append('affiliate_link')
    
    append_csv('companies.csv', new_company, fieldnames)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/companies/<company_id>', methods=['PUT', 'DELETE'])
@api_auth_required
def api_edit_company(company_id):
    """تعديل/حذف شركة"""
    companies = read_csv('companies.csv')
    
    if request.method == 'DELETE':
        companies = [c for c in companies if c.get('id') != company_id]
        if companies:
            fieldnames = list(companies[0].keys())
        else:
            fieldnames = ['id', 'name', 'type', 'details', 'is_active', 'icon', 'address']
        write_csv('companies.csv', companies, fieldnames)
        return jsonify({'success': True})
    
    elif request.method == 'PUT':
        data = request.json
        for c in companies:
            if c.get('id') == company_id:
                for k, v in data.items():
                    if k in c or k in ('name', 'type', 'details', 'is_active', 'icon', 'address', 'affiliate_link'):
                        c[k] = v
                break
        if companies:
            fieldnames = list(companies[0].keys())
            write_csv('companies.csv', companies, fieldnames)
        return jsonify({'success': True})

@app.route('/api/matching/active')
@api_auth_required
def api_matching_active():
    """المطابقات النشطة"""
    matches = read_csv('matches.csv')
    active = [m for m in matches if m.get('status') not in ('completed', 'cancelled')]
    return jsonify({'matches': active, 'count': len(active)})

@app.route('/api/matching/pending')
@api_auth_required
def api_matching_pending():
    """طلبات المطابقة المعلقة"""
    reqs = read_csv('match_requests.csv')
    pending = [r for r in reqs if r.get('status') == 'waiting']
    return jsonify({'requests': pending, 'count': len(pending)})

@app.route('/api/matching/logs')
@api_auth_required
def api_matching_logs():
    """سجلات المطابقات"""
    matches = read_csv('matches.csv')
    logs = [m for m in matches if m.get('status') in ('completed', 'cancelled')]
    logs.reverse()  # newest first
    return jsonify({'matches': logs[:50], 'count': len(logs)})

@app.route('/api/svrp/wallets')
@api_auth_required
def api_svrp_wallets():
    """محافظ التعويض"""
    wallets = read_csv('svrp_wallets.csv')
    return jsonify({'wallets': wallets})

@app.route('/api/svrp/requests')
@api_auth_required
def api_svrp_requests():
    """طلبات الاسترداد"""
    reqs = read_csv('recovery_requests.csv')
    return jsonify({'requests': reqs})

@app.route('/api/trading/orders')
@api_auth_required
def api_trading_orders():
    """طلبات التداول"""
    orders = read_csv('trade_orders.csv')
    pending = [o for o in orders if o.get('status') == 'pending']
    return jsonify({'orders': orders[:50], 'pending_count': len(pending)})

@app.route('/api/lottery/rounds')
@api_auth_required
def api_lottery_rounds():
    """جولات اليانصيب"""
    rounds = read_csv('lottery_rounds.csv')
    tickets = read_csv('lottery_tickets.csv')
    winners = read_csv('lottery_winners.csv')
    
    for r in rounds:
        rid = r.get('id', '')
        r['tickets_sold'] = sum(1 for t in tickets if t.get('round_id') == rid)
        r['participants'] = len(set(t.get('user_id') for t in tickets if t.get('round_id') == rid))
        r['winners_count'] = sum(1 for w in winners if w.get('round_id') == rid)
    
    return jsonify({'rounds': rounds})

@app.route('/api/wheel/rounds')
@api_auth_required
def api_wheel_rounds():
    """جولات عجلة الحظ"""
    rounds = read_csv('wheel_rounds.csv')
    spins = read_csv('wheel_spins.csv')
    
    for r in rounds:
        rid = r.get('id', '')
        r['total_spins'] = sum(1 for s in spins if s.get('round_id') == rid)
        r['participants'] = len(set(s.get('user_id') for s in spins if s.get('round_id') == rid))
    
    return jsonify({'rounds': rounds})

@app.route('/api/apps')
@api_auth_required
def api_apps():
    """التطبيقات"""
    apps = read_csv('app_links.csv')
    return jsonify({'apps': apps})

@app.route('/api/referrals')
@api_auth_required
def api_referrals():
    """الإحالات"""
    links = read_csv('referral_links.csv')
    log = read_csv('referral_log.csv')
    return jsonify({'links': links, 'log': log[:50], 'total_referrals': len(log)})

@app.route('/api/channels')
@api_auth_required
def api_channels():
    """القنوات"""
    channels = read_csv('bot_channels.csv')
    return jsonify({'channels': channels})

@app.route('/api/bots')
@api_auth_required
def api_bots():
    """البوتات المتعددة"""
    bots = read_csv('bot_tokens.csv')
    return jsonify({'bots': bots})

@app.route('/api/settings')
@api_auth_required
def api_settings():
    """الإعدادات"""
    settings = read_csv('system_settings.csv')
    return jsonify({'settings': settings})

@app.route('/api/settings', methods=['POST'])
@api_auth_required
def api_update_settings():
    """تحديث الإعدادات"""
    data = request.json
    settings = read_csv('system_settings.csv')
    for s in settings:
        key = s.get('setting_key', '')
        if key in data:
            s['setting_value'] = data[key]
    if settings:
        fieldnames = list(settings[0].keys())
        write_csv('system_settings.csv', settings, fieldnames)
    return jsonify({'success': True})

@app.route('/api/audit-log')
@api_auth_required
def api_audit_log():
    """سجل إجراءات الأدمن"""
    logs = read_csv('admin_actions_log.csv')
    logs.reverse()
    return jsonify({'logs': logs[:100]})

# ===== Pages =====

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

# ===== Main =====

if __name__ == '__main__':
    print(f"🚀 Boterx Dashboard running on http://0.0.0.0:{DASHBOARD_PORT}")
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=True, threaded=True)
