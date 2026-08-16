#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Network DB layer — «وكلاء المطابقة»
SQLite-backed storage for matching agents: accounts, balances, transactions,
payment methods, deposit (top-up) requests, and a full financial ledger.

All financial mutations are atomic (BEGIN IMMEDIATE) with a ledger row written
in the same transaction. Passwords are stored as PBKDF2 hashes; legacy plaintext
CSV passwords are upgraded on first successful login.

Traffic rule: an agent receives requests only while
    is_active AND traffic_on AND balance > security_deposit
    AND daily_count < max_daily AND (deposit → balance >= amount)
Distribution is weighted by traffic_weight (admin-set share).
"""

import os
import csv
import json
import hashlib
import secrets
import sqlite3
import threading
import random
from datetime import datetime, date

from db_manager import DB_PATH  # same vex_games.db

_lock = threading.Lock()

CSV_ENCODING = 'utf-8-sig'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA synchronous=NORMAL')
    c.row_factory = sqlite3.Row
    return c


# ── Password hashing (stdlib only — PBKDF2-HMAC-SHA256) ─────────────────────

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 120_000)
    return f'pbkdf2${salt}${dk.hex()}'


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith('pbkdf2$'):
        try:
            _, salt, hexhash = stored.split('$', 2)
            dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 120_000)
            return secrets.compare_digest(dk.hex(), hexhash)
        except Exception:
            return False
    # Legacy plaintext (pre-migration) — constant-time compare
    return secrets.compare_digest(stored, password)


# ── Schema ───────────────────────────────────────────────────────────────────

def init_agent_tables():
    conn = _conn()
    try:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS agent_bots (
                id            TEXT PRIMARY KEY,
                bot_token     TEXT NOT NULL DEFAULT '',
                bot_name      TEXT NOT NULL DEFAULT '',
                username      TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL DEFAULT '',
                balance       REAL NOT NULL DEFAULT 0,
                security_deposit REAL NOT NULL DEFAULT 0,
                is_active     INTEGER NOT NULL DEFAULT 1,
                traffic_on    INTEGER NOT NULL DEFAULT 1,   -- admin manual switch
                traffic_weight INTEGER NOT NULL DEFAULT 1,  -- حصة حركة المرور
                max_daily_transactions INTEGER NOT NULL DEFAULT 50,
                current_daily_count    INTEGER NOT NULL DEFAULT 0,
                daily_count_date       TEXT NOT NULL DEFAULT '',
                total_deposits_processed    INTEGER NOT NULL DEFAULT 0,
                total_withdrawals_processed INTEGER NOT NULL DEFAULT 0,
                total_volume  REAL NOT NULL DEFAULT 0,
                deposit_method_name TEXT NOT NULL DEFAULT '',  -- زر إيداع الوكيل (يحدده الأدمن)
                deposit_method_data TEXT NOT NULL DEFAULT '',
                created_at    TEXT NOT NULL DEFAULT '',
                last_active   TEXT NOT NULL DEFAULT '',
                notes         TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS agent_transactions (
                id          TEXT PRIMARY KEY,
                agent_id    TEXT NOT NULL,
                match_request_id TEXT NOT NULL DEFAULT '',
                type        TEXT NOT NULL,               -- 'deposit' | 'withdraw'
                amount      REAL NOT NULL DEFAULT 0,
                currency    TEXT NOT NULL DEFAULT 'EGP',
                status      TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected
                user_id     TEXT NOT NULL DEFAULT '',
                user_name   TEXT NOT NULL DEFAULT '',
                payment_details TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL DEFAULT '',
                processed_at TEXT NOT NULL DEFAULT '',
                admin_override TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_agent_txn_agent ON agent_transactions(agent_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_agent_txn_status ON agent_transactions(status);

            CREATE TABLE IF NOT EXISTS agent_payment_methods (
                id          TEXT PRIMARY KEY,
                agent_id    TEXT NOT NULL,
                method_name TEXT NOT NULL DEFAULT '',
                method_type TEXT NOT NULL DEFAULT '',
                account_data TEXT NOT NULL DEFAULT '',
                icon        TEXT NOT NULL DEFAULT '💳',
                is_active   INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_agent_pm_agent ON agent_payment_methods(agent_id);

            -- Agent self top-up requests (زر إيداع الرصيد) — admin confirms
            CREATE TABLE IF NOT EXISTS agent_deposit_requests (
                id          TEXT PRIMARY KEY,
                agent_id    TEXT NOT NULL,
                amount      REAL NOT NULL DEFAULT 0,
                method_name TEXT NOT NULL DEFAULT '',
                reference   TEXT NOT NULL DEFAULT '',    -- رقم المحفظة/إيصال التحويل
                status      TEXT NOT NULL DEFAULT 'pending',
                created_at  TEXT NOT NULL DEFAULT '',
                processed_at TEXT NOT NULL DEFAULT '',
                processed_by TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_agent_dep_agent ON agent_deposit_requests(agent_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_agent_dep_status ON agent_deposit_requests(status);

            -- Full financial ledger for agents
            CREATE TABLE IF NOT EXISTS agent_ledger (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id     TEXT NOT NULL,
                amount       REAL NOT NULL,
                direction    TEXT NOT NULL,   -- 'credit' | 'debit'
                reason       TEXT NOT NULL,   -- txn_withdraw|txn_deposit|topup|manual_add|manual_subtract|override_reversal|override_apply
                reference_id TEXT NOT NULL DEFAULT '',
                balance_after REAL NOT NULL DEFAULT 0,
                timestamp    TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_agent_ledger_agent ON agent_ledger(agent_id, id);
        ''')
        conn.commit()
    finally:
        conn.close()


def migrate_agents_from_csv():
    """One-time idempotent migration of legacy CSV agent data into SQLite."""
    conn = _conn()
    try:
        migrated = 0
        # agents
        path = os.path.join(BASE_DIR, 'agent_bots.csv')
        if os.path.exists(path):
            with open(path, 'r', encoding=CSV_ENCODING) as f:
                for row in csv.DictReader(f):
                    aid = row.get('id', '')
                    if not aid:
                        continue
                    exists = conn.execute('SELECT 1 FROM agent_bots WHERE id=?', (aid,)).fetchone()
                    if exists:
                        continue
                    pw = row.get('password', '')
                    conn.execute('''INSERT OR IGNORE INTO agent_bots
                        (id, bot_token, bot_name, username, password_hash, balance,
                         security_deposit, is_active, traffic_on, traffic_weight,
                         max_daily_transactions, current_daily_count, daily_count_date,
                         total_deposits_processed, total_withdrawals_processed,
                         total_volume, created_at, last_active, notes)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                        aid, row.get('bot_token', ''), row.get('bot_name', ''),
                        row.get('username', aid.lower()),
                        hash_password(pw) if pw else '',
                        float(row.get('balance', 0) or 0),
                        float(row.get('security_deposit', 0) or 0),
                        1 if row.get('is_active') == 'yes' else 0,
                        1 if row.get('traffic_enabled') == 'yes' else 0,
                        1,
                        int(row.get('max_daily_transactions', 50) or 50),
                        int(row.get('current_daily_count', 0) or 0),
                        date.today().isoformat(),
                        int(row.get('total_deposits_processed', 0) or 0),
                        int(row.get('total_withdrawals_processed', 0) or 0),
                        float(row.get('total_volume', 0) or 0),
                        row.get('created_at', ''), row.get('last_active', ''),
                        row.get('notes', ''),
                    ))
                    migrated += 1
        # transactions
        path = os.path.join(BASE_DIR, 'agent_transactions.csv')
        if os.path.exists(path):
            with open(path, 'r', encoding=CSV_ENCODING) as f:
                for row in csv.DictReader(f):
                    tid = row.get('id') or row.get('transaction_id') or ''
                    if not tid:
                        continue
                    conn.execute('''INSERT OR IGNORE INTO agent_transactions
                        (id, agent_id, match_request_id, type, amount, currency, status,
                         user_id, user_name, created_at, processed_at, admin_override)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''', (
                        tid, row.get('agent_id', ''), row.get('transaction_id', ''),
                        row.get('type', 'deposit'), float(row.get('amount', 0) or 0),
                        row.get('currency', 'EGP'), row.get('status', 'pending'),
                        row.get('user_id', ''), row.get('user_name', ''),
                        row.get('processed_at', ''), row.get('processed_at', ''),
                        row.get('admin_override', ''),
                    ))
        # payment methods
        path = os.path.join(BASE_DIR, 'agent_payment_methods.csv')
        if os.path.exists(path):
            with open(path, 'r', encoding=CSV_ENCODING) as f:
                for row in csv.DictReader(f):
                    mid = row.get('id', '')
                    if not mid:
                        continue
                    conn.execute('''INSERT OR IGNORE INTO agent_payment_methods
                        (id, agent_id, method_name, method_type, account_data, icon,
                         is_active, created_at) VALUES (?,?,?,?,?,?,?,?)''', (
                        mid, row.get('agent_id', ''), row.get('method_name', ''),
                        row.get('method_type', ''), row.get('account_data', ''),
                        row.get('icon', '💳'),
                        1 if row.get('is_active', 'yes') == 'yes' else 0,
                        row.get('created_at', ''),
                    ))
        conn.commit()
        return migrated
    finally:
        conn.close()


init_agent_tables()
migrate_agents_from_csv()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _agent_dict(row):
    d = dict(row)
    d.pop('password_hash', None)
    d['traffic_stopped'] = not _traffic_ok_dict(d)
    return d


def _traffic_ok_dict(d):
    return bool(d.get('is_active')) and bool(d.get('traffic_on')) and \
        float(d.get('balance', 0)) > float(d.get('security_deposit', 0))


def _rollover_daily(conn, today=None):
    """Reset daily counters for a new day (in the current transaction)."""
    today = today or date.today().isoformat()
    conn.execute(
        'UPDATE agent_bots SET current_daily_count=0, daily_count_date=? '
        'WHERE daily_count_date != ?', (today, today))


def _ledger(conn, agent_id, amount, direction, reason, ref, balance_after):
    conn.execute(
        'INSERT INTO agent_ledger (agent_id, amount, direction, reason, '
        'reference_id, balance_after, timestamp) VALUES (?,?,?,?,?,?,?)',
        (agent_id, float(amount), direction, reason, ref, float(balance_after), _now()))


# ── Agent CRUD ───────────────────────────────────────────────────────────────

def list_agents():
    conn = _conn()
    try:
        rows = conn.execute('SELECT * FROM agent_bots ORDER BY created_at').fetchall()
        return [_agent_dict(r) for r in rows]
    finally:
        conn.close()


def get_agent(agent_id):
    conn = _conn()
    try:
        r = conn.execute('SELECT * FROM agent_bots WHERE id=?', (agent_id,)).fetchone()
        return _agent_dict(r) if r else None
    finally:
        conn.close()


def create_agent(data):
    agent_id = f"AGT{secrets.token_hex(3).upper()}"
    username = (data.get('username') or agent_id.lower()).strip()
    password = data.get('password') or secrets.token_hex(6)
    conn = _conn()
    try:
        conn.execute('''INSERT INTO agent_bots
            (id, bot_token, bot_name, username, password_hash, balance,
             security_deposit, is_active, traffic_on, traffic_weight,
             max_daily_transactions, current_daily_count, daily_count_date,
             deposit_method_name, deposit_method_data, created_at, notes)
            VALUES (?,?,?,?,?,0,?,1,1,?,?,0,?,?,?,?,?)''', (
            agent_id, data.get('bot_token', ''), data.get('bot_name', ''),
            username, hash_password(password),
            float(data.get('security_deposit', 100) or 100),
            max(1, int(data.get('traffic_weight', 1) or 1)),
            int(data.get('max_daily_transactions', 50) or 50),
            date.today().isoformat(),
            data.get('deposit_method_name', ''), data.get('deposit_method_data', ''),
            _now(), data.get('notes', ''),
        ))
        conn.commit()
        return {'id': agent_id, 'username': username, 'password': password}
    except sqlite3.IntegrityError:
        return {'error': 'اسم المستخدم مستخدم بالفعل'}
    finally:
        conn.close()


_ADMIN_EDITABLE = {'bot_token', 'bot_name', 'username', 'security_deposit',
                   'is_active', 'traffic_on', 'traffic_weight',
                   'max_daily_transactions', 'deposit_method_name',
                   'deposit_method_data', 'notes'}


def update_agent(agent_id, data):
    """Admin update. `password` handled separately (re-hash). Balance NOT editable here."""
    sets, vals = [], []
    for k in _ADMIN_EDITABLE:
        if k in data:
            v = data[k]
            if k in ('is_active', 'traffic_on'):
                v = 1 if v in (1, '1', True, 'yes', 'true') else 0
            elif k in ('traffic_weight', 'max_daily_transactions'):
                v = max(0, int(v or 0)) if k == 'max_daily_transactions' else max(1, int(v or 1))
            elif k == 'security_deposit':
                v = float(v or 0)
            sets.append(f'{k}=?')
            vals.append(v)
    if data.get('password'):
        sets.append('password_hash=?')
        vals.append(hash_password(str(data['password'])))
    if not sets:
        return False
    vals.append(agent_id)
    conn = _conn()
    try:
        cur = conn.execute(f'UPDATE agent_bots SET {", ".join(sets)} WHERE id=?', vals)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_agent(agent_id):
    """Delete an agent. Refuses while pending work is still assigned to them
    so user matching requests are never stranded."""
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        pending = conn.execute(
            "SELECT COUNT(*) c FROM agent_transactions "
            "WHERE agent_id=? AND status='pending'", (agent_id,)).fetchone()['c']
        pending += conn.execute(
            "SELECT COUNT(*) c FROM agent_deposit_requests "
            "WHERE agent_id=? AND status='pending'", (agent_id,)).fetchone()['c']
        if pending:
            conn.rollback()
            return {'error': f'لا يمكن الحذف — لدى الوكيل {pending} طلب معلق. عالج الطلبات أولاً.'}
        cur = conn.execute('DELETE FROM agent_bots WHERE id=?', (agent_id,))
        conn.execute('DELETE FROM agent_payment_methods WHERE agent_id=?', (agent_id,))
        conn.commit()
        return {'success': True} if cur.rowcount > 0 else {'error': 'الوكيل غير موجود'}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def verify_agent_login(username, password):
    """Return agent dict on success (and upgrade legacy hash), else None."""
    conn = _conn()
    try:
        r = conn.execute('SELECT * FROM agent_bots WHERE username=?', (username,)).fetchone()
        if not r or not verify_password(password, r['password_hash']):
            return None
        if not r['password_hash'].startswith('pbkdf2$'):
            conn.execute('UPDATE agent_bots SET password_hash=? WHERE id=?',
                         (hash_password(password), r['id']))
        conn.execute('UPDATE agent_bots SET last_active=? WHERE id=?', (_now(), r['id']))
        conn.commit()
        return _agent_dict(r)
    finally:
        conn.close()


# ── Balance operations (atomic) ──────────────────────────────────────────────

def adjust_balance(agent_id, amount, direction, reason, ref=''):
    """Atomic credit/debit with ledger row. Debit may not push balance below 0."""
    amount = float(amount)
    if amount <= 0:
        return {'error': 'المبلغ يجب أن يكون أكبر من صفر'}
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        r = conn.execute('SELECT balance FROM agent_bots WHERE id=?', (agent_id,)).fetchone()
        if not r:
            conn.rollback()
            return {'error': 'الوكيل غير موجود'}
        bal = float(r['balance'])
        new_bal = bal + amount if direction == 'credit' else bal - amount
        if new_bal < 0:
            conn.rollback()
            return {'error': 'الرصيد غير كافٍ'}
        conn.execute('UPDATE agent_bots SET balance=? WHERE id=?', (new_bal, agent_id))
        _ledger(conn, agent_id, amount, direction, reason, ref, new_bal)
        conn.commit()
        return {'success': True, 'new_balance': new_bal}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


# ── Traffic distribution ─────────────────────────────────────────────────────

def pick_agent_for_request(txn_type, amount):
    """Pick an eligible agent, weighted by traffic_weight relative to daily usage.

    Eligible: active, traffic_on, balance > security_deposit, daily quota not
    reached, and for deposits (agent pays the user) balance >= amount.
    Selection: lowest (daily_count / weight) — agents with a bigger admin-set
    share receive proportionally more requests. Atomically increments the
    winner's daily counter so 200+ concurrent picks stay consistent.
    """
    amount = float(amount or 0)
    with _lock:
        conn = _conn()
        try:
            conn.execute('BEGIN IMMEDIATE')
            chosen = _pick_agent_locked(conn, txn_type, amount)
            if not chosen:
                conn.rollback()
                return None
            conn.commit()
            return chosen
        except Exception:
            conn.rollback()
            return None
        finally:
            conn.close()


def _pick_agent_locked(conn, txn_type, amount):
    """Pick an eligible agent inside an already-open BEGIN IMMEDIATE txn and
    increment their daily counter. Spendable balance excludes amounts already
    committed to that agent's *pending* deposit transactions, so concurrent
    requests can't over-allocate the same funds. Returns dict or None."""
    _rollover_daily(conn, date.today().isoformat())
    rows = conn.execute(
        "SELECT b.id, b.bot_name, b.balance, b.security_deposit, b.traffic_weight, "
        "b.current_daily_count, b.max_daily_transactions, "
        "COALESCE((SELECT SUM(t.amount) FROM agent_transactions t "
        " WHERE t.agent_id=b.id AND t.status='pending' AND t.type='deposit'),0) AS pending_out "
        "FROM agent_bots b WHERE b.is_active=1 AND b.traffic_on=1 "
        "AND b.current_daily_count < b.max_daily_transactions").fetchall()
    eligible = []
    for r in rows:
        spendable = float(r['balance']) - float(r['pending_out'])
        if spendable <= float(r['security_deposit']):
            continue
        if txn_type == 'deposit' and spendable < amount:
            continue
        w = max(1, int(r['traffic_weight']))
        eligible.append((float(r['current_daily_count']) / w, r))
    if not eligible:
        return None
    eligible.sort(key=lambda x: x[0])
    best_ratio = eligible[0][0]
    top = [r for ratio, r in eligible if ratio == best_ratio]
    chosen = random.choice(top)
    conn.execute(
        'UPDATE agent_bots SET current_daily_count=current_daily_count+1, '
        'last_active=? WHERE id=?', (_now(), chosen['id']))
    return {'id': chosen['id'], 'name': chosen['bot_name'],
            'balance': float(chosen['balance'])}


def pick_and_create_transaction(txn_type, amount, currency='EGP', user_id='',
                                user_name='', match_request_id='',
                                payment_details=''):
    """Atomically pick an eligible agent AND create their pending transaction
    in one SQLite transaction — no window where quota is reserved without a
    transaction (or vice-versa). Returns {'agent':..., 'txn_id':...} or None."""
    amount = float(amount or 0)
    if amount <= 0:
        return None
    tid = f"ATX{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"
    with _lock:
        conn = _conn()
        try:
            conn.execute('BEGIN IMMEDIATE')
            chosen = _pick_agent_locked(conn, txn_type, amount)
            if not chosen:
                conn.rollback()
                return None
            conn.execute('''INSERT INTO agent_transactions
                (id, agent_id, match_request_id, type, amount, currency, status,
                 user_id, user_name, payment_details, created_at)
                VALUES (?,?,?,?,?,?, 'pending', ?,?,?,?)''', (
                tid, chosen['id'], match_request_id, txn_type, amount, currency,
                str(user_id), user_name, payment_details, _now()))
            conn.commit()
            return {'agent': chosen, 'txn_id': tid}
        except Exception:
            conn.rollback()
            return None
        finally:
            conn.close()


def void_pending_transaction(agent_id, txn_id):
    """Delete a still-pending transaction and release the agent's daily-quota
    slot. Used to compensate when a later step of request creation fails."""
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        cur = conn.execute(
            "DELETE FROM agent_transactions WHERE id=? AND agent_id=? AND status='pending'",
            (txn_id, agent_id))
        if cur.rowcount:
            conn.execute(
                'UPDATE agent_bots SET current_daily_count=MAX(0,current_daily_count-1) '
                'WHERE id=?', (agent_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def set_txn_match_request(txn_id, match_request_id):
    conn = _conn()
    try:
        conn.execute('UPDATE agent_transactions SET match_request_id=? WHERE id=?',
                     (match_request_id, txn_id))
        conn.commit()
    finally:
        conn.close()


# ── Transactions (matching requests handled by agents) ───────────────────────

def create_transaction(agent_id, txn_type, amount, currency='EGP', user_id='',
                       user_name='', match_request_id='', payment_details=''):
    tid = f"ATX{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"
    conn = _conn()
    try:
        conn.execute('''INSERT INTO agent_transactions
            (id, agent_id, match_request_id, type, amount, currency, status,
             user_id, user_name, payment_details, created_at)
            VALUES (?,?,?,?,?,?, 'pending', ?,?,?,?)''', (
            tid, agent_id, match_request_id, txn_type, float(amount), currency,
            str(user_id), user_name, payment_details, _now()))
        conn.commit()
        return tid
    finally:
        conn.close()


def _apply_txn_effect(conn, agent_id, txn_type, amount, tid, reason):
    """Apply financial effect of an approved transaction inside open txn.
    withdraw approved → agent receives user's money → balance += amount
    deposit approved  → agent paid the user       → balance -= amount
    Returns new balance or raises ValueError on insufficient funds."""
    r = conn.execute('SELECT balance FROM agent_bots WHERE id=?', (agent_id,)).fetchone()
    if not r:
        raise ValueError('الوكيل غير موجود')
    bal = float(r['balance'])
    if txn_type == 'withdraw':
        new_bal = bal + float(amount)
        direction = 'credit'
    else:
        new_bal = bal - float(amount)
        direction = 'debit'
        if new_bal < 0:
            raise ValueError('رصيد الوكيل غير كافٍ')
    conn.execute('UPDATE agent_bots SET balance=? WHERE id=?', (new_bal, agent_id))
    _ledger(conn, agent_id, amount, direction, reason, tid, new_bal)
    return new_bal


def _reverse_txn_effect(conn, agent_id, txn_type, amount, tid, reason):
    """Reverse a previously applied approval effect."""
    r = conn.execute('SELECT balance FROM agent_bots WHERE id=?', (agent_id,)).fetchone()
    if not r:
        raise ValueError('الوكيل غير موجود')
    bal = float(r['balance'])
    if txn_type == 'withdraw':
        new_bal = bal - float(amount)   # remove earlier credit
        direction = 'debit'
        if new_bal < 0:
            # Never fabricate a reversal we can't actually take back —
            # reject the override so the ledger stays truthful.
            raise ValueError('رصيد الوكيل غير كافٍ لعكس المعاملة — عدّل الرصيد يدوياً أولاً')
    else:
        new_bal = bal + float(amount)   # refund earlier debit
        direction = 'credit'
    conn.execute('UPDATE agent_bots SET balance=? WHERE id=?', (new_bal, agent_id))
    _ledger(conn, agent_id, amount, direction, reason, tid, new_bal)
    return new_bal


def agent_process_transaction(agent_id, txn_id, decision):
    """Agent approves/rejects a pending transaction assigned to them.
    Atomic CAS on status='pending' so double-clicks can't double-settle."""
    if decision not in ('approved', 'rejected'):
        return {'error': 'قرار غير صالح'}
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        t = conn.execute(
            'SELECT * FROM agent_transactions WHERE id=? AND agent_id=?',
            (txn_id, agent_id)).fetchone()
        if not t:
            conn.rollback()
            return {'error': 'المعاملة غير موجودة'}
        cur = conn.execute(
            "UPDATE agent_transactions SET status=?, processed_at=? "
            "WHERE id=? AND agent_id=? AND status='pending'",
            (decision, _now(), txn_id, agent_id))
        if cur.rowcount == 0:
            conn.rollback()
            return {'error': 'تمت معالجة المعاملة بالفعل'}
        new_bal = None
        if decision == 'approved':
            new_bal = _apply_txn_effect(conn, agent_id, t['type'], t['amount'],
                                        txn_id, f"txn_{t['type']}")
            col = ('total_withdrawals_processed' if t['type'] == 'withdraw'
                   else 'total_deposits_processed')
            conn.execute(
                f'UPDATE agent_bots SET {col}={col}+1, total_volume=total_volume+? '
                f'WHERE id=?', (float(t['amount']), agent_id))
        conn.commit()
        return {'success': True, 'new_balance': new_bal,
                'match_request_id': t['match_request_id'], 'type': t['type'],
                'user_id': t['user_id'], 'amount': float(t['amount'])}
    except ValueError as e:
        conn.rollback()
        return {'error': str(e)}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def admin_override_transaction(agent_id, txn_id, new_status, admin_id=''):
    """Admin flips a transaction's status with correct financial reversal/apply."""
    if new_status not in ('approved', 'rejected', 'pending'):
        return {'error': 'حالة غير صالحة'}
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        t = conn.execute(
            'SELECT * FROM agent_transactions WHERE id=? AND agent_id=?',
            (txn_id, agent_id)).fetchone()
        if not t:
            conn.rollback()
            return {'error': 'المعاملة غير موجودة'}
        old = t['status']
        if old == new_status:
            conn.rollback()
            return {'success': True, 'unchanged': True}
        # Financial semantics: effect exists only while status == approved
        if old == 'approved':
            _reverse_txn_effect(conn, agent_id, t['type'], t['amount'],
                                txn_id, 'override_reversal')
            col = ('total_withdrawals_processed' if t['type'] == 'withdraw'
                   else 'total_deposits_processed')
            conn.execute(
                f'UPDATE agent_bots SET {col}=MAX(0,{col}-1), '
                f'total_volume=MAX(0,total_volume-?) WHERE id=?',
                (float(t['amount']), agent_id))
        if new_status == 'approved':
            _apply_txn_effect(conn, agent_id, t['type'], t['amount'],
                              txn_id, 'override_apply')
            col = ('total_withdrawals_processed' if t['type'] == 'withdraw'
                   else 'total_deposits_processed')
            conn.execute(
                f'UPDATE agent_bots SET {col}={col}+1, total_volume=total_volume+? '
                f'WHERE id=?', (float(t['amount']), agent_id))
        conn.execute(
            'UPDATE agent_transactions SET status=?, processed_at=?, admin_override=? '
            'WHERE id=?',
            (new_status, _now(), f'admin:{admin_id}:{new_status} (was:{old})', txn_id))
        conn.commit()
        return {'success': True, 'old_status': old}
    except ValueError as e:
        conn.rollback()
        return {'error': str(e)}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def search_transactions(agent_id, q='', status='', txn_type='',
                        date_from='', date_to='', min_amount=None,
                        max_amount=None, limit=100):
    sql = 'SELECT * FROM agent_transactions WHERE agent_id=?'
    args = [agent_id]
    if q:
        sql += ' AND (id LIKE ? OR user_name LIKE ? OR user_id LIKE ? OR match_request_id LIKE ?)'
        like = f'%{q}%'
        args += [like, like, like, like]
    if status:
        sql += ' AND status=?'
        args.append(status)
    if txn_type:
        sql += ' AND type=?'
        args.append(txn_type)
    if date_from:
        sql += ' AND created_at >= ?'
        args.append(date_from)
    if date_to:
        sql += ' AND created_at <= ?'
        args.append(date_to + ' 23:59:59' if len(date_to) == 10 else date_to)
    if min_amount not in (None, ''):
        sql += ' AND amount >= ?'
        args.append(float(min_amount))
    if max_amount not in (None, ''):
        sql += ' AND amount <= ?'
        args.append(float(max_amount))
    sql += ' ORDER BY created_at DESC LIMIT ?'
    args.append(int(limit))
    conn = _conn()
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def get_pending_transactions(agent_id):
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM agent_transactions WHERE agent_id=? AND status='pending' "
            "ORDER BY created_at", (agent_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Agent top-up (deposit) requests ──────────────────────────────────────────

def create_deposit_request(agent_id, amount, method_name, reference):
    amount = float(amount)
    if amount <= 0:
        return {'error': 'المبلغ يجب أن يكون أكبر من صفر'}
    conn = _conn()
    try:
        pending = conn.execute(
            "SELECT COUNT(*) FROM agent_deposit_requests WHERE agent_id=? AND status='pending'",
            (agent_id,)).fetchone()[0]
        if pending >= 3:
            return {'error': 'لديك طلبات إيداع معلقة كثيرة — انتظر تأكيد الأدمن'}
        rid = f"ADR{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"
        conn.execute('''INSERT INTO agent_deposit_requests
            (id, agent_id, amount, method_name, reference, status, created_at)
            VALUES (?,?,?,?,?,'pending',?)''',
            (rid, agent_id, amount, method_name, reference, _now()))
        conn.commit()
        return {'success': True, 'id': rid}
    finally:
        conn.close()


def process_deposit_request(request_id, decision, admin_id=''):
    """Admin confirms/rejects an agent top-up. Approve credits balance atomically.
    CAS on status='pending' → exactly-once even under double-click/replay."""
    if decision not in ('approved', 'rejected'):
        return {'error': 'قرار غير صالح'}
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        r = conn.execute('SELECT * FROM agent_deposit_requests WHERE id=?',
                         (request_id,)).fetchone()
        if not r:
            conn.rollback()
            return {'error': 'الطلب غير موجود'}
        cur = conn.execute(
            "UPDATE agent_deposit_requests SET status=?, processed_at=?, processed_by=? "
            "WHERE id=? AND status='pending'",
            (decision, _now(), str(admin_id), request_id))
        if cur.rowcount == 0:
            conn.rollback()
            return {'error': 'تمت معالجة الطلب بالفعل'}
        new_bal = None
        if decision == 'approved':
            ar = conn.execute('SELECT balance FROM agent_bots WHERE id=?',
                              (r['agent_id'],)).fetchone()
            if not ar:
                conn.rollback()
                return {'error': 'الوكيل غير موجود'}
            new_bal = float(ar['balance']) + float(r['amount'])
            conn.execute('UPDATE agent_bots SET balance=? WHERE id=?',
                         (new_bal, r['agent_id']))
            _ledger(conn, r['agent_id'], r['amount'], 'credit', 'topup',
                    request_id, new_bal)
        conn.commit()
        return {'success': True, 'agent_id': r['agent_id'], 'new_balance': new_bal}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def list_deposit_requests(agent_id=None, status=''):
    sql = 'SELECT * FROM agent_deposit_requests WHERE 1=1'
    args = []
    if agent_id:
        sql += ' AND agent_id=?'
        args.append(agent_id)
    if status:
        sql += ' AND status=?'
        args.append(status)
    sql += ' ORDER BY created_at DESC LIMIT 200'
    conn = _conn()
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


# ── Payment methods ──────────────────────────────────────────────────────────

def list_payment_methods(agent_id):
    conn = _conn()
    try:
        rows = conn.execute(
            'SELECT * FROM agent_payment_methods WHERE agent_id=? ORDER BY created_at',
            (agent_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_payment_method(agent_id, data):
    mid = f"APM{secrets.token_hex(3).upper()}"
    conn = _conn()
    try:
        conn.execute('''INSERT INTO agent_payment_methods
            (id, agent_id, method_name, method_type, account_data, icon, is_active, created_at)
            VALUES (?,?,?,?,?,?,1,?)''', (
            mid, agent_id, data.get('method_name', ''), data.get('method_type', ''),
            data.get('account_data', ''), data.get('icon', '💳'), _now()))
        conn.commit()
        return mid
    finally:
        conn.close()


def update_payment_method(agent_id, mid, data, admin=False):
    """Agent may edit account_data + icon ONLY; admin may edit everything."""
    allowed = {'account_data', 'icon'}
    if admin:
        allowed |= {'method_name', 'method_type', 'is_active'}
    sets, vals = [], []
    for k in allowed:
        if k in data:
            v = data[k]
            if k == 'is_active':
                v = 1 if v in (1, '1', True, 'yes', 'true') else 0
            sets.append(f'{k}=?')
            vals.append(v)
    if not sets:
        return False
    vals += [mid, agent_id]
    conn = _conn()
    try:
        cur = conn.execute(
            f'UPDATE agent_payment_methods SET {", ".join(sets)} WHERE id=? AND agent_id=?',
            vals)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_payment_method(agent_id, mid):
    conn = _conn()
    try:
        cur = conn.execute(
            'DELETE FROM agent_payment_methods WHERE id=? AND agent_id=?', (mid, agent_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_ledger(agent_id, limit=200):
    conn = _conn()
    try:
        rows = conn.execute(
            'SELECT * FROM agent_ledger WHERE agent_id=? ORDER BY id DESC LIMIT ?',
            (agent_id, int(limit))).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
