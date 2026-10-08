#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Network DB layer — وكلاء المطابقة
SQLite-backed storage for matching agents: accounts, balances, transactions,
payment methods, deposit (top-up) requests, and a full financial ledger.

v2 additions: Escrow, Performance Scoring, Heartbeat Monitoring,
Insurance Pool, Penalties, Matching Tables (CSV → SQLite migration).
"""

import os
import csv
import json
import hashlib
import secrets
import sqlite3
import threading
import random
import logging
import math
from datetime import datetime, date, timedelta

from db_manager import DB_PATH

logger = logging.getLogger(__name__)

_lock = threading.Lock()

CSV_ENCODING = 'utf-8-sig'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Tier thresholds ────────────────────────────────────────────────────────
TIERS = {
    'platinum': 80,
    'gold':     60,
    'silver':   40,
    'bronze':    0,
}

# ── Insurance config ───────────────────────────────────────────────────────
INSURANCE_RATE = 0.005  # 0.5% per completed transaction
RESPONSE_TIMEOUT = 300   # seconds — auto-void pending txn after this
HEARTBEAT_TIMEOUT = 120  # seconds — mark agent offline after no heartbeat

# Ops V2 defaults (can be overridden by dashboard settings layer if needed)
OP_STEP_ACTION_TIMEOUT_MIN = 10
OP_STEP_CONFIRM_TIMEOUT_MIN = 5
OP_PRECOMPLETE_WINDOW_MIN = 15
OP_TOTAL_TIMEOUT_MIN = 60
USDT_RATE_LOCK_MIN = 10

OPS_REQ_TYPES = ('deposit', 'withdraw', 'buy_usdt', 'sell_usdt')

EMA_ALPHA = 0.2  # exponential moving average factor for response time


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
    return secrets.compare_digest(stored, password)


# ── Schema ───────────────────────────────────────────────────────────────────

def _ensure_columns(conn, table, columns):
    """Add missing columns to an existing table. columns = [(name, type, default), ...]"""
    cur = conn.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}
    for name, col_type, default in columns:
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type} NOT NULL DEFAULT {default}")
            logger.info(f"Added column {table}.{name}")


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
                traffic_on    INTEGER NOT NULL DEFAULT 1,
                traffic_weight INTEGER NOT NULL DEFAULT 1,
                max_daily_transactions INTEGER NOT NULL DEFAULT 50,
                current_daily_count    INTEGER NOT NULL DEFAULT 0,
                daily_count_date       TEXT NOT NULL DEFAULT '',
                total_deposits_processed    INTEGER NOT NULL DEFAULT 0,
                total_withdrawals_processed INTEGER NOT NULL DEFAULT 0,
                total_volume  REAL NOT NULL DEFAULT 0,
                deposit_method_name TEXT NOT NULL DEFAULT '',
                deposit_method_data TEXT NOT NULL DEFAULT '',
                created_at    TEXT NOT NULL DEFAULT '',
                last_active   TEXT NOT NULL DEFAULT '',
                notes         TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS agent_transactions (
                id          TEXT PRIMARY KEY,
                agent_id    TEXT NOT NULL,
                match_request_id TEXT NOT NULL DEFAULT '',
                type        TEXT NOT NULL,
                amount      REAL NOT NULL DEFAULT 0,
                currency    TEXT NOT NULL DEFAULT 'EGP',
                status      TEXT NOT NULL DEFAULT 'pending',
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

            CREATE TABLE IF NOT EXISTS agent_deposit_requests (
                id          TEXT PRIMARY KEY,
                agent_id    TEXT NOT NULL,
                amount      REAL NOT NULL DEFAULT 0,
                method_name TEXT NOT NULL DEFAULT '',
                reference   TEXT NOT NULL DEFAULT '',
                status      TEXT NOT NULL DEFAULT 'pending',
                created_at  TEXT NOT NULL DEFAULT '',
                processed_at TEXT NOT NULL DEFAULT '',
                processed_by TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_agent_dep_agent ON agent_deposit_requests(agent_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_agent_dep_status ON agent_deposit_requests(status);

            CREATE TABLE IF NOT EXISTS agent_ledger (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id     TEXT NOT NULL,
                amount       REAL NOT NULL,
                direction    TEXT NOT NULL,
                reason       TEXT NOT NULL,
                reference_id TEXT NOT NULL DEFAULT '',
                balance_after REAL NOT NULL DEFAULT 0,
                timestamp    TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_agent_ledger_agent ON agent_ledger(agent_id, id);

            -- ═══ v2: Escrow + Scoring + Heartbeat columns on agent_bots ═══
            -- These are added via ALTER TABLE in _ensure_columns below

            -- ═══ v2: Insurance Pool ═══
            CREATE TABLE IF NOT EXISTS insurance_pool (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id     TEXT NOT NULL DEFAULT '',
                amount       REAL NOT NULL,
                direction    TEXT NOT NULL,
                reference_id TEXT NOT NULL DEFAULT '',
                balance_after REAL NOT NULL DEFAULT 0,
                created_at   TEXT NOT NULL
            );

            -- ═══ v2: Agent Penalties ═══
            CREATE TABLE IF NOT EXISTS agent_penalties (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id     TEXT NOT NULL,
                penalty_type TEXT NOT NULL,
                amount       REAL NOT NULL DEFAULT 0,
                reason       TEXT NOT NULL DEFAULT '',
                created_at   TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_penalties_agent ON agent_penalties(agent_id);

            -- ═══ v2: Matching Tables (migrated from CSV) ═══
            CREATE TABLE IF NOT EXISTS match_requests (
                id                TEXT PRIMARY KEY,
                user_id           TEXT NOT NULL DEFAULT '',
                customer_id       TEXT NOT NULL DEFAULT '',
                type              TEXT NOT NULL DEFAULT '',
                amount            REAL NOT NULL DEFAULT 0,
                currency          TEXT NOT NULL DEFAULT 'EGP',
                company_id        TEXT NOT NULL DEFAULT '',
                company_name      TEXT NOT NULL DEFAULT '',
                payment_method_id TEXT NOT NULL DEFAULT '',
                status            TEXT NOT NULL DEFAULT 'waiting',
                created_at        TEXT NOT NULL DEFAULT '',
                matched_at        TEXT NOT NULL DEFAULT '',
                match_id          TEXT NOT NULL DEFAULT '',
                alias             TEXT NOT NULL DEFAULT '',
                bot_id            TEXT NOT NULL DEFAULT '',
                assigned_agent_id TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_mreq_user ON match_requests(user_id, status);
            CREATE INDEX IF NOT EXISTS idx_mreq_status ON match_requests(status);

            CREATE TABLE IF NOT EXISTS matches (
                id                TEXT PRIMARY KEY,
                deposit_request_id TEXT NOT NULL DEFAULT '',
                withdraw_request_id TEXT NOT NULL DEFAULT '',
                depositor_id      TEXT NOT NULL DEFAULT '',
                withdrawer_id     TEXT NOT NULL DEFAULT '',
                depositor_alias   TEXT NOT NULL DEFAULT '',
                withdrawer_alias  TEXT NOT NULL DEFAULT '',
                amount            REAL NOT NULL DEFAULT 0,
                currency          TEXT NOT NULL DEFAULT 'EGP',
                company_id        TEXT NOT NULL DEFAULT '',
                company_name      TEXT NOT NULL DEFAULT '',
                status            TEXT NOT NULL DEFAULT 'active',
                confirmation_code TEXT NOT NULL DEFAULT '',
                created_at        TEXT NOT NULL DEFAULT '',
                completed_at      TEXT NOT NULL DEFAULT '',
                depositor_rated   TEXT NOT NULL DEFAULT 'no',
                withdrawer_rated  TEXT NOT NULL DEFAULT 'no',
                dispute_status    TEXT NOT NULL DEFAULT 'none',
                bot_id            TEXT NOT NULL DEFAULT '',
                agent_id          TEXT NOT NULL DEFAULT '',
                escrow_amount     REAL NOT NULL DEFAULT 0,
                escrow_released   INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_match_status ON matches(status);
            CREATE INDEX IF NOT EXISTS idx_match_agent ON matches(agent_id);

            CREATE TABLE IF NOT EXISTS chat_messages (
                id          TEXT PRIMARY KEY,
                match_id    TEXT NOT NULL,
                sender_id   TEXT NOT NULL,
                sender_alias TEXT NOT NULL DEFAULT '',
                message     TEXT NOT NULL DEFAULT '',
                timestamp   TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_chat_match ON chat_messages(match_id);

            CREATE TABLE IF NOT EXISTS match_ratings (
                id          TEXT PRIMARY KEY,
                match_id    TEXT NOT NULL,
                rater_id    TEXT NOT NULL,
                rated_id    TEXT NOT NULL,
                rating      INTEGER NOT NULL DEFAULT 0,
                comment     TEXT NOT NULL DEFAULT '',
                timestamp   TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS match_disputes (
                id            TEXT PRIMARY KEY,
                match_id      TEXT NOT NULL,
                raised_by     TEXT NOT NULL,
                reason        TEXT NOT NULL DEFAULT '',
                status        TEXT NOT NULL DEFAULT 'open',
                admin_response TEXT NOT NULL DEFAULT '',
                created_at    TEXT NOT NULL DEFAULT '',
                resolved_at   TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_disputes_status ON match_disputes(status);

            -- ═══ Ops V2 step engine + audit + routing ═══
            CREATE TABLE IF NOT EXISTS op_steps (
                id               TEXT PRIMARY KEY,
                txn_id           TEXT NOT NULL,
                seq              INTEGER NOT NULL,
                step_key         TEXT NOT NULL,
                title_key        TEXT NOT NULL,
                actor_role       TEXT NOT NULL,
                status           TEXT NOT NULL DEFAULT 'pending',
                evidence_type    TEXT NOT NULL DEFAULT 'none',
                evidence_ref     TEXT NOT NULL DEFAULT '',
                action_deadline  TEXT NOT NULL DEFAULT '',
                confirm_deadline TEXT NOT NULL DEFAULT '',
                acted_at         TEXT NOT NULL DEFAULT '',
                acted_by         TEXT NOT NULL DEFAULT '',
                confirmed_at     TEXT NOT NULL DEFAULT '',
                confirmed_by     TEXT NOT NULL DEFAULT '',
                reject_count     INTEGER NOT NULL DEFAULT 0,
                note             TEXT NOT NULL DEFAULT '',
                created_at       TEXT NOT NULL DEFAULT '',
                updated_at       TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_op_steps_txn_seq ON op_steps(txn_id, seq);
            CREATE INDEX IF NOT EXISTS idx_op_steps_status ON op_steps(status);

            CREATE TABLE IF NOT EXISTS op_step_templates (
                id          TEXT PRIMARY KEY,
                op_type     TEXT NOT NULL,
                source_type TEXT NOT NULL,
                steps_json  TEXT NOT NULL,
                is_active   INTEGER NOT NULL DEFAULT 1,
                updated_at  TEXT NOT NULL DEFAULT ''
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_op_tpl_unique
                ON op_step_templates(op_type, source_type);

            CREATE TABLE IF NOT EXISTS op_audit_log (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id      TEXT NOT NULL,
                entity_table   TEXT NOT NULL,
                actor_type     TEXT NOT NULL,
                actor_id       TEXT NOT NULL,
                event          TEXT NOT NULL,
                from_value     TEXT NOT NULL DEFAULT '',
                to_value       TEXT NOT NULL DEFAULT '',
                payload_digest TEXT NOT NULL DEFAULT '',
                created_at     TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_op_audit_entity
                ON op_audit_log(entity_table, entity_id, id);

            CREATE TABLE IF NOT EXISTS insurance_claims (
                id               TEXT PRIMARY KEY,
                txn_id           TEXT NOT NULL,
                claimant_type    TEXT NOT NULL,
                claimant_id      TEXT NOT NULL,
                reason           TEXT NOT NULL,
                evidence_file_id TEXT NOT NULL DEFAULT '',
                status           TEXT NOT NULL DEFAULT 'open',
                payout_amount    REAL NOT NULL DEFAULT 0,
                admin_note       TEXT NOT NULL DEFAULT '',
                decided_by       TEXT NOT NULL DEFAULT '',
                decided_at       TEXT NOT NULL DEFAULT '',
                created_at       TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_ins_claims_txn ON insurance_claims(txn_id, status);

            CREATE TABLE IF NOT EXISTS routing_rules (
                id          TEXT PRIMARY KEY,
                priority    INTEGER NOT NULL DEFAULT 100,
                rule_type   TEXT NOT NULL,
                params_json TEXT NOT NULL,
                is_active   INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_routing_rules_active
                ON routing_rules(is_active, priority);

            CREATE TABLE IF NOT EXISTS op_disputes (
                id                 TEXT PRIMARY KEY,
                req_id             TEXT NOT NULL,
                opened_by_type     TEXT NOT NULL,
                opened_by_id       TEXT NOT NULL,
                assigned_to_type   TEXT NOT NULL DEFAULT '',
                assigned_to_id     TEXT NOT NULL DEFAULT '',
                status             TEXT NOT NULL DEFAULT 'open',
                reason             TEXT NOT NULL DEFAULT '',
                evidence_file_id   TEXT NOT NULL DEFAULT '',
                admin_note         TEXT NOT NULL DEFAULT '',
                opened_at          TEXT NOT NULL DEFAULT '',
                updated_at         TEXT NOT NULL DEFAULT '',
                resolved_at        TEXT NOT NULL DEFAULT '',
                resolved_by        TEXT NOT NULL DEFAULT '',
                resolution         TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_op_disputes_req ON op_disputes(req_id, status);
            CREATE INDEX IF NOT EXISTS idx_op_disputes_assignee
                ON op_disputes(assigned_to_type, assigned_to_id, status);
        ''')

        # Add v2 columns to agent_bots
        _ensure_columns(conn, 'agent_bots', [
            ('escrow_balance',       'REAL',    '0'),
            ('max_concurrent',       'INTEGER', '5'),
            ('avg_response_seconds',  'REAL',    '0'),
            ('completion_rate',      'REAL',    '100.0'),
            ('dispute_rate',         'REAL',    '0.0'),
            ('performance_score',    'REAL',    '50.0'),
            ('tier',                 'TEXT',    "'bronze'"),
            ('last_heartbeat',       'TEXT',    "''"),
            ('is_online',            'INTEGER', '0'),
            ('telegram_id',          'TEXT',    "''"),
            ('drain',                'INTEGER', '0'),
            ('pin_remaining',        'INTEGER', '0'),
            ('cap_per_txn',          'REAL',    '0'),
            ('allow_deposit',        'INTEGER', '1'),
            ('allow_withdraw',       'INTEGER', '1'),
            ('allow_buy_usdt',       'INTEGER', '1'),
            ('allow_sell_usdt',      'INTEGER', '1'),
            ('max_amount_daily',     'REAL',    '0'),
            ('current_daily_amount', 'REAL',    '0'),
            ('max_open_disputes',    'INTEGER', '5'),
        ])

        # Admin action tracking on match_requests (parity with old CSV fields)
        _ensure_columns(conn, 'match_requests', [
            ('approved_by', 'TEXT', "''"),
            ('approved_at', 'TEXT', "''"),
            ('source_type', 'TEXT', "'company'"),
            ('claimed_by_type', 'TEXT', "''"),
            ('claimed_by_id', 'TEXT', "''"),
            ('claimed_at', 'TEXT', "''"),
            ('state', 'TEXT', "''"),
            ('precomplete_until', 'TEXT', "''"),
            ('rate', 'REAL', '0'),
            ('rate_locked_until', 'TEXT', "''"),
            ('network', 'TEXT', "''"),
            ('dispute_status', 'TEXT', "''"),
            ('dispute_assigned_to_type', 'TEXT', "''"),
            ('dispute_assigned_to_id', 'TEXT', "''"),
            ('dispute_opened_at', 'TEXT', "''"),
            ('dispute_resolved_at', 'TEXT', "''"),
        ])

        conn.executescript('''
            CREATE TRIGGER IF NOT EXISTS op_audit_no_update
            BEFORE UPDATE ON op_audit_log
            BEGIN
                SELECT RAISE(ABORT,'audit is append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS op_audit_no_delete
            BEFORE DELETE ON op_audit_log
            BEGIN
                SELECT RAISE(ABORT,'audit is append-only');
            END;
        ''')

        _ensure_default_op_templates(conn)

        conn.commit()
    finally:
        conn.close()


def _default_step_templates():
    """Built-in Ops V2 templates. Admin may edit later via routing/settings UI."""
    return {
        ('deposit', 'company'): [
            {'key': 'requester_transfer', 'title_key': 'step_requester_transfer',
             'actor_role': 'requester', 'evidence_type': 'reference'},
            {'key': 'processor_confirm_received', 'title_key': 'step_processor_confirm_received',
             'actor_role': 'processor', 'evidence_type': 'none'},
            {'key': 'processor_send_funds', 'title_key': 'step_processor_send_funds',
             'actor_role': 'processor', 'evidence_type': 'reference'},
            {'key': 'requester_confirm_received', 'title_key': 'step_requester_confirm_received',
             'actor_role': 'requester', 'evidence_type': 'none'},
        ],
        ('withdraw', 'company'): [
            {'key': 'requester_submit_withdraw_data', 'title_key': 'step_requester_submit_withdraw_data',
             'actor_role': 'requester', 'evidence_type': 'reference'},
            {'key': 'processor_send_funds', 'title_key': 'step_processor_send_funds',
             'actor_role': 'processor', 'evidence_type': 'reference'},
            {'key': 'requester_confirm_received', 'title_key': 'step_requester_confirm_received',
             'actor_role': 'requester', 'evidence_type': 'none'},
        ],
        ('buy_usdt', 'company'): [
            {'key': 'requester_send_fiat', 'title_key': 'step_requester_send_fiat',
             'actor_role': 'requester', 'evidence_type': 'reference'},
            {'key': 'processor_send_usdt', 'title_key': 'step_processor_send_usdt',
             'actor_role': 'processor', 'evidence_type': 'reference'},
            {'key': 'requester_confirm_usdt', 'title_key': 'step_requester_confirm_usdt',
             'actor_role': 'requester', 'evidence_type': 'none'},
        ],
        ('sell_usdt', 'company'): [
            {'key': 'requester_send_usdt', 'title_key': 'step_requester_send_usdt',
             'actor_role': 'requester', 'evidence_type': 'reference'},
            {'key': 'processor_send_fiat', 'title_key': 'step_processor_send_fiat',
             'actor_role': 'processor', 'evidence_type': 'reference'},
            {'key': 'requester_confirm_fiat', 'title_key': 'step_requester_confirm_fiat',
             'actor_role': 'requester', 'evidence_type': 'none'},
        ],
        ('deposit', 'personal_wallet'): [
            {'key': 'system_hold_wallet', 'title_key': 'step_system_hold_wallet',
             'actor_role': 'system', 'evidence_type': 'none'},
            {'key': 'processor_credit_target', 'title_key': 'step_processor_credit_target',
             'actor_role': 'processor', 'evidence_type': 'reference'},
            {'key': 'requester_confirm_credit', 'title_key': 'step_requester_confirm_credit',
             'actor_role': 'requester', 'evidence_type': 'none'},
        ],
        ('withdraw', 'personal_wallet'): [
            {'key': 'system_hold_wallet', 'title_key': 'step_system_hold_wallet',
             'actor_role': 'system', 'evidence_type': 'none'},
            {'key': 'processor_send_funds', 'title_key': 'step_processor_send_funds',
             'actor_role': 'processor', 'evidence_type': 'reference'},
            {'key': 'requester_confirm_received', 'title_key': 'step_requester_confirm_received',
             'actor_role': 'requester', 'evidence_type': 'none'},
        ],
        ('buy_usdt', 'personal_wallet'): [
            {'key': 'system_hold_wallet', 'title_key': 'step_system_hold_wallet',
             'actor_role': 'system', 'evidence_type': 'none'},
            {'key': 'processor_send_usdt', 'title_key': 'step_processor_send_usdt',
             'actor_role': 'processor', 'evidence_type': 'reference'},
            {'key': 'requester_confirm_usdt', 'title_key': 'step_requester_confirm_usdt',
             'actor_role': 'requester', 'evidence_type': 'none'},
        ],
        ('sell_usdt', 'personal_wallet'): [
            {'key': 'requester_send_usdt', 'title_key': 'step_requester_send_usdt',
             'actor_role': 'requester', 'evidence_type': 'reference'},
            {'key': 'system_release_wallet', 'title_key': 'step_system_release_wallet',
             'actor_role': 'system', 'evidence_type': 'none'},
            {'key': 'requester_confirm_fiat', 'title_key': 'step_requester_confirm_fiat',
             'actor_role': 'requester', 'evidence_type': 'none'},
        ],
    }


def _ensure_default_op_templates(conn):
    defaults = _default_step_templates()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for (op_type, source_type), steps in defaults.items():
        row = conn.execute(
            'SELECT id FROM op_step_templates WHERE op_type=? AND source_type=?',
            (op_type, source_type)).fetchone()
        if row:
            continue
        conn.execute(
            'INSERT INTO op_step_templates '
            '(id, op_type, source_type, steps_json, is_active, updated_at) '
            'VALUES (?,?,?,?,1,?)',
            (f"OPT{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}",
             op_type, source_type, json.dumps(steps, ensure_ascii=False), now))


# ── CSV Migration ────────────────────────────────────────────────────────────

def migrate_agents_from_csv():
    """One-time idempotent migration of legacy CSV agent data into SQLite."""
    conn = _conn()
    try:
        migrated = 0
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


def migrate_matching_from_csv():
    """One-time idempotent migration of matching CSV files into SQLite."""
    conn = _conn()
    try:
        total = 0
        # match_requests.csv
        path = os.path.join(BASE_DIR, 'match_requests.csv')
        if os.path.exists(path):
            with open(path, 'r', encoding=CSV_ENCODING) as f:
                for row in csv.DictReader(f):
                    rid = row.get('id', '')
                    if not rid:
                        continue
                    try:
                        conn.execute('''INSERT OR IGNORE INTO match_requests
                            (id, user_id, customer_id, type, amount, currency,
                             company_id, company_name, payment_method_id, status,
                             created_at, matched_at, match_id, alias, bot_id)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                            rid, str(row.get('user_id', '')), str(row.get('customer_id', '')),
                            row.get('type', ''), float(row.get('amount', 0) or 0),
                            row.get('currency', 'EGP'), str(row.get('company_id', '')),
                            str(row.get('company_name', '')), str(row.get('payment_method_id', '')),
                            row.get('status', 'waiting'), row.get('created_at', ''),
                            row.get('matched_at', ''), row.get('match_id', ''),
                            row.get('alias', ''), row.get('bot_id', ''),
                        ))
                        total += 1
                    except Exception:
                        pass

        # matches.csv
        path = os.path.join(BASE_DIR, 'matches.csv')
        if os.path.exists(path):
            with open(path, 'r', encoding=CSV_ENCODING) as f:
                for row in csv.DictReader(f):
                    mid = row.get('id', '')
                    if not mid:
                        continue
                    try:
                        conn.execute('''INSERT OR IGNORE INTO matches
                            (id, deposit_request_id, withdraw_request_id,
                             depositor_id, withdrawer_id, depositor_alias,
                             withdrawer_alias, amount, currency, company_id,
                             company_name, status, confirmation_code, created_at,
                             completed_at, depositor_rated, withdrawer_rated,
                             dispute_status, bot_id)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                            mid, row.get('deposit_request_id', ''),
                            row.get('withdraw_request_id', ''),
                            str(row.get('depositor_id', '')),
                            str(row.get('withdrawer_id', '')),
                            row.get('depositor_alias', ''),
                            row.get('withdrawer_alias', ''),
                            float(row.get('amount', 0) or 0),
                            row.get('currency', 'EGP'),
                            str(row.get('company_id', '')),
                            str(row.get('company_name', '')),
                            row.get('status', 'active'),
                            row.get('confirmation_code', ''),
                            row.get('created_at', ''),
                            row.get('completed_at', ''),
                            row.get('depositor_rated', 'no'),
                            row.get('withdrawer_rated', 'no'),
                            row.get('dispute_status', 'none'),
                            row.get('bot_id', ''),
                        ))
                        total += 1
                    except Exception:
                        pass

        # chat_messages.csv
        path = os.path.join(BASE_DIR, 'chat_messages.csv')
        if os.path.exists(path):
            with open(path, 'r', encoding=CSV_ENCODING) as f:
                for row in csv.DictReader(f):
                    mid = row.get('id', '')
                    if not mid:
                        continue
                    try:
                        conn.execute('''INSERT OR IGNORE INTO chat_messages
                            (id, match_id, sender_id, sender_alias, message, timestamp)
                            VALUES (?,?,?,?,?,?)''', (
                            mid, row.get('match_id', ''),
                            str(row.get('sender_id', '')),
                            row.get('sender_alias', ''),
                            row.get('message', ''),
                            row.get('timestamp', ''),
                        ))
                        total += 1
                    except Exception:
                        pass

        # ratings.csv
        path = os.path.join(BASE_DIR, 'ratings.csv')
        if os.path.exists(path):
            with open(path, 'r', encoding=CSV_ENCODING) as f:
                for row in csv.DictReader(f):
                    mid = row.get('id', '')
                    if not mid:
                        continue
                    try:
                        conn.execute('''INSERT OR IGNORE INTO match_ratings
                            (id, match_id, rater_id, rated_id, rating, comment, timestamp)
                            VALUES (?,?,?,?,?,?,?)''', (
                            mid, row.get('match_id', ''),
                            str(row.get('rater_id', '')),
                            str(row.get('rated_id', '')),
                            int(row.get('rating', 0) or 0),
                            row.get('comment', ''),
                            row.get('timestamp', ''),
                        ))
                        total += 1
                    except Exception:
                        pass

        # disputes.csv
        path = os.path.join(BASE_DIR, 'disputes.csv')
        if os.path.exists(path):
            with open(path, 'r', encoding=CSV_ENCODING) as f:
                for row in csv.DictReader(f):
                    did = row.get('id', '')
                    if not did:
                        continue
                    try:
                        conn.execute('''INSERT OR IGNORE INTO match_disputes
                            (id, match_id, raised_by, reason, status,
                             admin_response, created_at, resolved_at)
                            VALUES (?,?,?,?,?,?,?,?)''', (
                            did, row.get('match_id', ''),
                            str(row.get('raised_by', '')),
                            row.get('reason', ''),
                            row.get('status', 'open'),
                            row.get('admin_response', ''),
                            row.get('created_at', ''),
                            row.get('resolved_at', ''),
                        ))
                        total += 1
                    except Exception:
                        pass

        conn.commit()
        if total:
            logger.info(f"Migrated {total} matching rows from CSV to SQLite")
        return total
    finally:
        conn.close()


init_agent_tables()
migrate_agents_from_csv()
migrate_matching_from_csv()


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
    today = today or date.today().isoformat()
    conn.execute(
        'UPDATE agent_bots SET current_daily_count=0, current_daily_amount=0, daily_count_date=? '
        'WHERE daily_count_date != ?', (today, today))


def _ledger(conn, agent_id, amount, direction, reason, ref, balance_after):
    conn.execute(
        'INSERT INTO agent_ledger (agent_id, amount, direction, reason, '
        'reference_id, balance_after, timestamp) VALUES (?,?,?,?,?,?,?)',
        (agent_id, float(amount), direction, reason, ref, float(balance_after), _now()))


def _generate_id(prefix):
    return f"{prefix}{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"


def _generate_alias():
    part = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=4))
    return f"عميل-{part}"


OPS_ACTIVE_STATES = {'created', 'claimed', 'in_progress', 'pre_complete', 'escalated', 'disputed'}
OPS_FINAL_STATES = {'completed', 'cancelled', 'rejected', 'resolved_depositor', 'resolved_withdrawer'}


def _ts_now():
    return datetime.now()


def _to_ts(dt_obj):
    return dt_obj.strftime('%Y-%m-%d %H:%M:%S')


def _parse_ts(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    except Exception:
        return None


def _plus_minutes(base_dt, minutes):
    return base_dt + timedelta(minutes=max(0, int(minutes or 0)))


def _payload_digest(payload):
    try:
        encoded = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)
    except Exception:
        encoded = str(payload or '')
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _audit_event_locked(conn, entity_table, entity_id, actor_type, actor_id,
                        event, from_value='', to_value='', payload=None):
    conn.execute(
        'INSERT INTO op_audit_log '
        '(entity_id, entity_table, actor_type, actor_id, event, from_value, to_value, payload_digest, created_at) '
        'VALUES (?,?,?,?,?,?,?,?,?)',
        (str(entity_id), str(entity_table), str(actor_type), str(actor_id), str(event),
         str(from_value or ''), str(to_value or ''), _payload_digest(payload), _now()))


def _request_is_active_row(row):
    if not row:
        return False
    status = str(_rowv(row, 'status', '')).strip()
    state = str(_rowv(row, 'state', '')).strip()
    if state in OPS_ACTIVE_STATES:
        return True
    return status in ('waiting', 'approved', 'disputed')


def _rowv(row, key, default=''):
    try:
        val = row[key]
        return default if val is None else val
    except Exception:
        try:
            val = row.get(key, default)
            return default if val is None else val
        except Exception:
            return default


def _step_templates_for(conn, op_type, source_type):
    row = conn.execute(
        "SELECT steps_json FROM op_step_templates "
        "WHERE op_type=? AND source_type=? AND is_active=1 "
        "ORDER BY updated_at DESC LIMIT 1",
        (str(op_type), str(source_type))).fetchone()
    if row and row['steps_json']:
        try:
            val = json.loads(row['steps_json'])
            if isinstance(val, list) and val:
                return val
        except Exception:
            pass
    return _default_step_templates().get((str(op_type), str(source_type))) \
        or _default_step_templates().get((str(op_type), 'company')) \
        or _default_step_templates()[('deposit', 'company')]


def _instantiate_steps_locked(conn, req_row):
    req_id = str(req_row['id'])
    existing = conn.execute('SELECT COUNT(*) c FROM op_steps WHERE txn_id=?', (req_id,)).fetchone()
    if existing and int(existing['c'] or 0) > 0:
        return
    now_dt = _ts_now()
    req_type = str(_rowv(req_row, 'type', 'deposit')).strip()
    source_type = str(_rowv(req_row, 'source_type', 'company')).strip() or 'company'
    templates = _step_templates_for(conn, req_type, source_type)
    for idx, st in enumerate(templates, start=1):
        sid = _generate_id('STP')
        actor_role = str(st.get('actor_role') or 'requester')
        evidence_type = str(st.get('evidence_type') or 'none')
        status = 'confirmed' if actor_role == 'system' else 'pending'
        acted_at = _to_ts(now_dt) if actor_role == 'system' else ''
        acted_by = 'system' if actor_role == 'system' else ''
        confirmed_at = acted_at
        confirmed_by = acted_by
        action_deadline = _to_ts(_plus_minutes(now_dt, OP_STEP_ACTION_TIMEOUT_MIN))
        confirm_deadline = ''
        conn.execute('''
            INSERT INTO op_steps
            (id, txn_id, seq, step_key, title_key, actor_role, status,
             evidence_type, evidence_ref, action_deadline, confirm_deadline,
             acted_at, acted_by, confirmed_at, confirmed_by,
             reject_count, note, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            sid, req_id, idx,
            str(st.get('key') or f'step_{idx}'),
            str(st.get('title_key') or st.get('key') or f'step_{idx}'),
            actor_role, status,
            evidence_type, '', action_deadline, confirm_deadline,
            acted_at, acted_by, confirmed_at, confirmed_by,
            0, '', _to_ts(now_dt), _to_ts(now_dt)
        ))


def _sync_request_state_from_steps_locked(conn, req_id):
    req = conn.execute('SELECT * FROM match_requests WHERE id=?', (str(req_id),)).fetchone()
    if not req:
        return
    rows = conn.execute(
        'SELECT status FROM op_steps WHERE txn_id=? ORDER BY seq',
        (str(req_id),)).fetchall()
    if not rows:
        return
    statuses = [str(r['status']) for r in rows]
    state = (req['state'] or '').strip() or 'created'

    if any(s in ('escalated', 'expired') for s in statuses):
        new_state = 'escalated'
    elif any(s == 'rejected' for s in statuses):
        new_state = 'in_progress'
    elif all(s == 'confirmed' for s in statuses):
        new_state = 'pre_complete'
    elif any(s in ('action_done', 'confirmed') for s in statuses):
        new_state = 'in_progress'
    else:
        new_state = 'claimed' if str(_rowv(req, 'claimed_by_id', '')) else 'created'

    updates = []
    args = []
    if new_state != state:
        updates.append('state=?')
        args.append(new_state)
    if new_state == 'pre_complete':
        until = req['precomplete_until'] or ''
        if not until:
            updates.append('precomplete_until=?')
            args.append(_to_ts(_plus_minutes(_ts_now(), OP_PRECOMPLETE_WINDOW_MIN)))
    if updates:
        args.append(str(req_id))
        conn.execute(f"UPDATE match_requests SET {', '.join(updates)} WHERE id=?", args)
        _audit_event_locked(conn, 'match_requests', req_id, 'system', 'state_sync',
                            'state_sync', state, new_state, {'reason': 'steps_sync'})


def _is_processor(actor_type, actor_id, req_row):
    if actor_type == 'admin':
        return True
    if actor_type == 'agent':
        claimed = str(_rowv(req_row, 'claimed_by_id', ''))
        assigned = str(_rowv(req_row, 'assigned_agent_id', ''))
        return str(actor_id) in (claimed, assigned)
    return False


def _agent_allows_req_type(agent_row, req_type):
    req_type = str(req_type or '')
    if req_type == 'deposit':
        return int(_rowv(agent_row, 'allow_deposit', 1) or 0) == 1
    if req_type == 'withdraw':
        return int(_rowv(agent_row, 'allow_withdraw', 1) or 0) == 1
    if req_type == 'buy_usdt':
        return int(_rowv(agent_row, 'allow_buy_usdt', 1) or 0) == 1
    if req_type == 'sell_usdt':
        return int(_rowv(agent_row, 'allow_sell_usdt', 1) or 0) == 1
    return True


def _count_open_disputes_for_agent_locked(conn, agent_id):
    row = conn.execute(
        "SELECT COUNT(*) c FROM op_disputes "
        "WHERE assigned_to_type='agent' AND assigned_to_id=? "
        "AND status IN ('open','assigned','in_review')",
        (str(agent_id),)).fetchone()
    return int(row['c'] if row else 0)


def _reserve_agent_slot_locked(conn, agent_id, amount, consume_pin=False):
    if consume_pin:
        conn.execute(
            'UPDATE agent_bots SET current_daily_count=current_daily_count+1, '
            'current_daily_amount=current_daily_amount+?, '
            'pin_remaining=MAX(0,pin_remaining-1), last_active=? WHERE id=?',
            (float(amount or 0), _now(), str(agent_id)))
    else:
        conn.execute(
            'UPDATE agent_bots SET current_daily_count=current_daily_count+1, '
            'current_daily_amount=current_daily_amount+?, '
            'last_active=? WHERE id=?',
            (float(amount or 0), _now(), str(agent_id)))


def _decrease_agent_daily_load_locked(conn, agent_id, amount):
    conn.execute(
        'UPDATE agent_bots SET current_daily_count=MAX(0,current_daily_count-1), '
        'current_daily_amount=MAX(0,current_daily_amount-?) WHERE id=?',
        (float(amount or 0), str(agent_id)))


def _validate_agent_policy_locked(conn, agent_row, req_type, amount, req_id=''):
    if not agent_row:
        return 'الوكيل غير موجود'
    if int(_rowv(agent_row, 'is_active', 0) or 0) != 1:
        return 'الوكيل غير مفعل'
    if int(_rowv(agent_row, 'traffic_on', 0) or 0) != 1:
        return 'الوكيل متوقف عن استقبال الحركة'
    if int(_rowv(agent_row, 'drain', 0) or 0) == 1:
        return 'الوكيل في وضع Drain'
    if req_type in OPS_REQ_TYPES and not _agent_allows_req_type(agent_row, req_type):
        return 'نوع العملية غير مسموح لهذا الوكيل'
    cap = float(_rowv(agent_row, 'cap_per_txn', 0) or 0)
    if cap > 0 and float(amount or 0) > cap:
        return 'المبلغ يتجاوز الحد المسموح للوكيل'
    max_daily_amount = float(_rowv(agent_row, 'max_amount_daily', 0) or 0)
    cur_daily_amount = float(_rowv(agent_row, 'current_daily_amount', 0) or 0)
    if req_id:
        held = conn.execute(
            "SELECT amount FROM agent_transactions "
            "WHERE agent_id=? AND match_request_id=? AND status='pending' "
            "ORDER BY created_at DESC LIMIT 1",
            (str(_rowv(agent_row, 'id', '')), str(req_id))).fetchone()
        if held:
            try:
                cur_daily_amount = max(0.0, cur_daily_amount - float(held['amount'] or 0))
            except Exception:
                pass
    if max_daily_amount > 0 and (cur_daily_amount + float(amount or 0)) > max_daily_amount:
        return 'تجاوز الوكيل الحد اليومي للمبالغ'
    max_open_disputes = int(_rowv(agent_row, 'max_open_disputes', 5) or 0)
    if max_open_disputes > 0:
        open_disputes = _count_open_disputes_for_agent_locked(conn, _rowv(agent_row, 'id', ''))
        if open_disputes >= max_open_disputes:
            return 'الوكيل تجاوز الحد الأقصى للنزاعات المفتوحة'
    return ''


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
              max_daily_transactions, max_concurrent, current_daily_count,
              daily_count_date, deposit_method_name, deposit_method_data,
              created_at, notes, allow_deposit, allow_withdraw,
              allow_buy_usdt, allow_sell_usdt, max_amount_daily,
              current_daily_amount, max_open_disputes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
            agent_id, data.get('bot_token', ''), data.get('bot_name', ''),
            username, hash_password(password),
            0.0,
            float(data.get('security_deposit', 100) or 100),
            1,
            1,
            max(1, int(data.get('traffic_weight', 1) or 1)),
            int(data.get('max_daily_transactions', 50) or 50),
            5,
            0,
            date.today().isoformat(),
            data.get('deposit_method_name', ''), data.get('deposit_method_data', ''),
            _now(), data.get('notes', ''),
            1 if data.get('allow_deposit', 1) in (1, '1', True, 'yes', 'true') else 0,
            1 if data.get('allow_withdraw', 1) in (1, '1', True, 'yes', 'true') else 0,
            1 if data.get('allow_buy_usdt', 1) in (1, '1', True, 'yes', 'true') else 0,
            1 if data.get('allow_sell_usdt', 1) in (1, '1', True, 'yes', 'true') else 0,
            max(0.0, float(data.get('max_amount_daily', 0) or 0)),
            0.0,
            max(0, int(data.get('max_open_disputes', 5) or 0)),
        ))
        conn.commit()
        return {'id': agent_id, 'username': username, 'password': password}
    except sqlite3.IntegrityError:
        return {'error': 'اسم المستخدم مستخدم بالفعل'}
    finally:
        conn.close()


_ADMIN_EDITABLE = {'bot_token', 'bot_name', 'username', 'security_deposit',
                   'is_active', 'traffic_on', 'traffic_weight',
                   'max_daily_transactions', 'max_concurrent',
                   'deposit_method_name', 'deposit_method_data', 'notes',
                   'telegram_id', 'drain', 'pin_remaining', 'cap_per_txn',
                   'allow_deposit', 'allow_withdraw', 'allow_buy_usdt', 'allow_sell_usdt',
                   'max_amount_daily', 'max_open_disputes'}


def update_agent(agent_id, data):
    sets, vals = [], []
    for k in _ADMIN_EDITABLE:
        if k in data:
            v = data[k]
            if k in ('is_active', 'traffic_on'):
                v = 1 if v in (1, '1', True, 'yes', 'true') else 0
            elif k in ('allow_deposit', 'allow_withdraw', 'allow_buy_usdt', 'allow_sell_usdt', 'drain'):
                v = 1 if v in (1, '1', True, 'yes', 'true') else 0
            elif k in ('traffic_weight', 'max_daily_transactions', 'max_concurrent', 'pin_remaining', 'max_open_disputes'):
                v = max(1 if k == 'traffic_weight' else 0, int(v or 0))
            elif k == 'security_deposit':
                v = float(v or 0)
            elif k in ('cap_per_txn', 'max_amount_daily'):
                v = max(0.0, float(v or 0))
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
    conn = _conn()
    try:
        r = conn.execute('SELECT * FROM agent_bots WHERE username=?', (username,)).fetchone()
        if not r or not verify_password(password, r['password_hash']):
            return None
        if not r['password_hash'].startswith('pbkdf2$'):
            conn.execute('UPDATE agent_bots SET password_hash=? WHERE id=?',
                         (hash_password(password), r['id']))
        conn.execute('UPDATE agent_bots SET last_active=?, last_heartbeat=?, is_online=1 '
                     'WHERE id=?', (_now(), _now(), r['id']))
        conn.commit()
        return _agent_dict(r)
    finally:
        conn.close()


# ── Balance operations (atomic) ──────────────────────────────────────────────

def adjust_balance(agent_id, amount, direction, reason, ref=''):
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


# ── Escrow operations ────────────────────────────────────────────────────────

def escrow_hold(agent_id, amount):
    """Atomically hold amount in escrow. Returns success/error."""
    amount = float(amount)
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        r = conn.execute('SELECT balance, escrow_balance FROM agent_bots WHERE id=?',
                         (agent_id,)).fetchone()
        if not r:
            conn.rollback()
            return {'error': 'الوكيل غير موجود'}
        bal = float(r['balance'])
        escrow = float(r['escrow_balance'])
        new_escrow = escrow + amount
        # Ensure spendable (bal - escrow) stays above security_deposit
        # We don't check here because balance check was done during pick
        conn.execute('UPDATE agent_bots SET escrow_balance=? WHERE id=?',
                     (new_escrow, agent_id))
        conn.commit()
        return {'success': True, 'escrow_balance': new_escrow}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def escrow_release(agent_id, amount):
    """Atomically release amount from escrow. Returns success/error."""
    amount = float(amount)
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        r = conn.execute('SELECT escrow_balance FROM agent_bots WHERE id=?',
                         (agent_id,)).fetchone()
        if not r:
            conn.rollback()
            return {'error': 'الوكيل غير موجود'}
        escrow = float(r['escrow_balance'])
        new_escrow = max(0, escrow - amount)
        conn.execute('UPDATE agent_bots SET escrow_balance=? WHERE id=?',
                     (new_escrow, agent_id))
        conn.commit()
        return {'success': True, 'escrow_balance': new_escrow}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def get_agent_escrow_count(agent_id):
    """Count agent's currently active (escrowed) transactions."""
    conn = _conn()
    try:
        r = conn.execute(
            "SELECT COUNT(*) c FROM agent_transactions WHERE agent_id=? AND status='pending'",
            (agent_id,)).fetchone()
        return r['c'] if r else 0
    finally:
        conn.close()


# ── Traffic distribution (with Escrow) ──────────────────────────────────────

def pick_agent_for_request(txn_type, amount):
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


def _pick_agent_locked(conn, txn_type, amount, request_meta=None):
    """Pick agent with escrow-aware spendable balance + tier-based priority.

    Supports lightweight routing rules and manual controls:
    - block_agent
    - route_company / route_currency (preferred agent)
    - per-agent drain / cap_per_txn / pin_remaining
    """
    request_meta = request_meta or {}
    _rollover_daily(conn, date.today().isoformat())

    blocked = set()
    preferred = []
    forced_pin = None
    forced_pin_rule = None
    global_max_amount = None
    rules = conn.execute(
        "SELECT id, rule_type, params_json FROM routing_rules "
        "WHERE is_active=1 ORDER BY priority ASC, created_at ASC").fetchall()
    for rr in rules:
        try:
            params = json.loads(rr['params_json'] or '{}')
        except Exception:
            params = {}
        rtype = rr['rule_type']
        if rtype == 'block_agent' and params.get('agent_id'):
            blocked.add(str(params.get('agent_id')))
        elif rtype == 'max_amount_per_txn':
            try:
                mx = float(params.get('max_amount', 0) or 0)
            except Exception:
                mx = 0
            if mx > 0:
                global_max_amount = mx if global_max_amount is None else min(global_max_amount, mx)
        elif rtype == 'pin_next_to_agent' and params.get('agent_id'):
            remaining = int(params.get('remaining', 0) or 0)
            if remaining > 0 and forced_pin is None:
                forced_pin = str(params.get('agent_id'))
                forced_pin_rule = {'id': rr['id'], 'params': params, 'remaining': remaining}
        elif rtype == 'route_company' and request_meta.get('company_id'):
            if str(params.get('company_id', '')) == str(request_meta.get('company_id', '')) and params.get('agent_id'):
                preferred.append(str(params.get('agent_id')))
        elif rtype == 'route_currency' and request_meta.get('currency'):
            if str(params.get('currency', '')).upper() == str(request_meta.get('currency', '')).upper() and params.get('agent_id'):
                preferred.append(str(params.get('agent_id')))

    if global_max_amount is not None and float(amount) > float(global_max_amount):
        return None

    req_type = str(request_meta.get('req_type', '') or '')

    rows = conn.execute(
        "SELECT b.id, b.bot_name, b.balance, b.security_deposit, b.traffic_weight, "
        "b.current_daily_count, b.max_daily_transactions, b.escrow_balance, "
        "b.current_daily_amount, b.max_amount_daily, "
        "b.max_concurrent, b.is_online, b.tier, b.drain, b.pin_remaining, b.cap_per_txn, "
        "b.is_active, b.traffic_on, "
        "b.allow_deposit, b.allow_withdraw, b.allow_buy_usdt, b.allow_sell_usdt, b.max_open_disputes, "
        "COALESCE((SELECT SUM(t.amount) FROM agent_transactions t "
        " WHERE t.agent_id=b.id AND t.status='pending' AND t.type='deposit'),0) AS pending_out, "
        "COALESCE((SELECT COUNT(*) FROM agent_transactions t2 "
        " WHERE t2.agent_id=b.id AND t2.status='pending'),0) AS active_escrow_count, "
        "COALESCE((SELECT COUNT(*) FROM op_disputes d "
        " WHERE d.assigned_to_type='agent' AND d.assigned_to_id=b.id "
        " AND d.status IN ('open','assigned','in_review')),0) AS open_disputes_count "
        "FROM agent_bots b WHERE b.is_active=1 AND b.traffic_on=1 "
        "AND b.current_daily_count < b.max_daily_transactions").fetchall()
    eligible = []
    for r in rows:
        if str(r['id']) in blocked:
            continue
        policy_err = _validate_agent_policy_locked(conn, r, req_type, amount)
        if policy_err:
            continue
        if req_type in OPS_REQ_TYPES and not _agent_allows_req_type(r, req_type):
            continue
        max_daily_amount = float(r['max_amount_daily'] or 0)
        if max_daily_amount > 0 and (float(r['current_daily_amount'] or 0) + float(amount)) > max_daily_amount:
            continue
        spendable = float(r['balance']) - float(r['escrow_balance']) - float(r['pending_out'])
        if spendable <= float(r['security_deposit']):
            continue
        if txn_type == 'deposit' and spendable < amount:
            continue
        if int(r['active_escrow_count']) >= int(r['max_concurrent']):
            continue
        # Tier bonus: higher tier gets slight priority
        tier_bonus = {'platinum': 0.7, 'gold': 0.85, 'silver': 0.95, 'bronze': 1.0}
        w = max(1, int(r['traffic_weight']))
        tier_mult = tier_bonus.get(r['tier'] or 'bronze', 1.0)
        ratio = (float(r['current_daily_count']) / w) * tier_mult
        eligible.append((ratio, r))
    if not eligible:
        return None

    if forced_pin:
        forced_rows = [r for _, r in eligible if str(r['id']) == forced_pin]
        if forced_rows:
            chosen = forced_rows[0]
            _reserve_agent_slot_locked(conn, chosen['id'], amount, consume_pin=False)
            if forced_pin_rule:
                new_params = dict(forced_pin_rule['params'])
                new_params['remaining'] = max(0, int(forced_pin_rule['remaining']) - 1)
                conn.execute(
                    'UPDATE routing_rules SET params_json=? WHERE id=?',
                    (json.dumps(new_params, ensure_ascii=False), forced_pin_rule['id']))
            return {'id': chosen['id'], 'name': chosen['bot_name'],
                    'balance': float(chosen['balance']),
                    'escrow_balance': float(chosen['escrow_balance'])}

    if preferred:
        preferred_set = set(preferred)
        preferred_eligible = [r for _, r in eligible if str(r['id']) in preferred_set]
        if preferred_eligible:
            preferred_eligible.sort(key=lambda rr: float(rr['current_daily_count']))
            chosen = preferred_eligible[0]
            _reserve_agent_slot_locked(conn, chosen['id'], amount, consume_pin=False)
            return {'id': chosen['id'], 'name': chosen['bot_name'],
                    'balance': float(chosen['balance']),
                    'escrow_balance': float(chosen['escrow_balance'])}

    pinned = [r for _, r in eligible if int(r['pin_remaining'] or 0) > 0]
    if pinned:
        pinned.sort(key=lambda rr: int(rr['pin_remaining']), reverse=True)
        chosen = pinned[0]
        _reserve_agent_slot_locked(conn, chosen['id'], amount, consume_pin=True)
        return {'id': chosen['id'], 'name': chosen['bot_name'],
                'balance': float(chosen['balance']),
                'escrow_balance': float(chosen['escrow_balance'])}

    eligible.sort(key=lambda x: x[0])
    best_ratio = eligible[0][0]
    top = [r for ratio, r in eligible if ratio <= best_ratio * 1.05]
    chosen = random.choice(top)
    _reserve_agent_slot_locked(conn, chosen['id'], amount, consume_pin=False)
    return {'id': chosen['id'], 'name': chosen['bot_name'],
            'balance': float(chosen['balance']),
            'escrow_balance': float(chosen['escrow_balance'])}


def pick_and_create_transaction(txn_type, amount, currency='EGP', user_id='',
                                user_name='', match_request_id='',
                                payment_details=''):
    """Atomically pick agent + create pending txn + hold escrow in one transaction."""
    amount = float(amount or 0)
    if amount <= 0:
        return None
    tid = _generate_id('ATX')
    with _lock:
        conn = _conn()
        try:
            conn.execute('BEGIN IMMEDIATE')
            chosen = _pick_agent_locked(conn, txn_type, amount)
            if not chosen:
                conn.rollback()
                return None
            # Create transaction
            conn.execute('''INSERT INTO agent_transactions
                (id, agent_id, match_request_id, type, amount, currency, status,
                 user_id, user_name, payment_details, created_at)
                VALUES (?,?,?,?,?,?, 'pending', ?,?,?,?)''', (
                tid, chosen['id'], match_request_id, txn_type, amount, currency,
                str(user_id), user_name, payment_details, _now()))
            # Hold escrow
            conn.execute(
                'UPDATE agent_bots SET escrow_balance=escrow_balance+? WHERE id=?',
                (amount, chosen['id']))
            conn.commit()
            return {'agent': chosen, 'txn_id': tid}
        except Exception:
            conn.rollback()
            return None
        finally:
            conn.close()


def void_pending_transaction(agent_id, txn_id):
    """Delete pending txn + release escrow + release daily-quota slot."""
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        t = conn.execute(
            "SELECT * FROM agent_transactions WHERE id=? AND agent_id=? AND status='pending'",
            (txn_id, agent_id)).fetchone()
        if not t:
            conn.rollback()
            return False
        amount = float(t['amount'])
        conn.execute(
            "DELETE FROM agent_transactions WHERE id=? AND agent_id=? AND status='pending'",
            (txn_id, agent_id))
        # Release escrow
        conn.execute(
            'UPDATE agent_bots SET escrow_balance=MAX(0, escrow_balance-?) WHERE id=?',
            (amount, agent_id))
        # Release daily quota
        conn.execute(
            'UPDATE agent_bots SET current_daily_count=MAX(0,current_daily_count-1), '
            'current_daily_amount=MAX(0,current_daily_amount-?) WHERE id=?',
            (amount, agent_id))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def void_pending_by_match_request(match_request_id):
    if not match_request_id:
        return False
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT id, agent_id FROM agent_transactions "
            "WHERE match_request_id=? AND status='pending'",
            (match_request_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return False
    return void_pending_transaction(row['agent_id'], row['id'])


def has_settled_txn_for_match_request(match_request_id):
    if not match_request_id:
        return False
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM agent_transactions "
            "WHERE match_request_id=? AND status IN ('approved','rejected') LIMIT 1",
            (match_request_id,)).fetchone()
        return row is not None
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


# ── Performance Scoring ──────────────────────────────────────────────────────

def _calc_response_speed_score(avg_seconds):
    """0-100 score: 100 if <30s, decays to 0 at 300s+."""
    if avg_seconds <= 0:
        return 50.0
    if avg_seconds <= 30:
        return 100.0
    if avg_seconds >= 300:
        return 0.0
    return max(0, 100.0 - (avg_seconds - 30) * (100.0 / 270.0))


def _calc_performance_score(avg_resp, completion_rate, dispute_rate, total_processed):
    speed = _calc_response_speed_score(avg_resp)
    dispute_penalty = max(0, 100.0 - dispute_rate * 10.0)
    volume_bonus = min(total_processed / max(1, 100), 100.0)
    score = (speed * 0.35) + (completion_rate * 0.35) + (dispute_penalty * 0.15) + (volume_bonus * 0.15)
    return round(min(100, max(0, score)), 2)


def _calc_tier(score):
    for tier_name, threshold in sorted(TIERS.items(), key=lambda x: -x[1]):
        if score >= threshold:
            return tier_name
    return 'bronze'


def _update_agent_stats(conn, agent_id):
    """Recalculate avg_response, completion_rate, dispute_rate, score, tier."""
    stats = conn.execute('''
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) AS approved,
            SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) AS rejected,
            AVG(CASE WHEN processed_at != '' AND created_at != ''
                THEN (julianday(processed_at) - julianday(created_at)) * 86400
                ELSE NULL END) AS avg_resp_seconds
        FROM agent_transactions
        WHERE agent_id=? AND status IN ('approved','rejected')
    ''', (agent_id,)).fetchone()

    total = stats['total'] or 0
    approved = stats['approved'] or 0
    avg_resp = stats['avg_resp_seconds'] or 0

    # Dispute rate from match_disputes
    dispute_row = conn.execute('''
        SELECT COUNT(*) c FROM match_disputes d
        JOIN matches m ON d.match_id = m.id
        WHERE m.agent_id = ? AND d.status != 'resolved_by_admin'
    ''', (agent_id,)).fetchone()
    dispute_count = dispute_row['c'] if dispute_row else 0
    dispute_rate = (dispute_count / max(1, total)) * 100

    completion_rate = (approved / max(1, total)) * 100

    # EMA for response time
    old_avg = conn.execute(
        'SELECT avg_response_seconds FROM agent_bots WHERE id=?', (agent_id,)
    ).fetchone()
    old_avg_val = float(old_avg['avg_response_seconds']) if old_avg else 0
    if old_avg_val > 0 and avg_resp > 0:
        new_avg = round(EMA_ALPHA * avg_resp + (1 - EMA_ALPHA) * old_avg_val, 2)
    elif avg_resp > 0:
        new_avg = round(avg_resp, 2)
    else:
        new_avg = old_avg_val

    score = _calc_performance_score(new_avg, completion_rate, dispute_rate, total)
    tier = _calc_tier(score)

    conn.execute('''UPDATE agent_bots SET
        avg_response_seconds=?, completion_rate=?, dispute_rate=?,
        performance_score=?, tier=? WHERE id=?''',
        (new_avg, round(completion_rate, 2), round(dispute_rate, 2),
         score, tier, agent_id))


# ── Transaction processing (with Escrow + Scoring + Insurance) ─────────────────

def create_transaction(agent_id, txn_type, amount, currency='EGP', user_id='',
                       user_name='', match_request_id='', payment_details=''):
    tid = _generate_id('ATX')
    conn = _conn()
    try:
        # Hold escrow
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''INSERT INTO agent_transactions
            (id, agent_id, match_request_id, type, amount, currency, status,
             user_id, user_name, payment_details, created_at)
            VALUES (?,?,?,?,?,?, 'pending', ?,?,?,?)''', (
            tid, agent_id, match_request_id, txn_type, float(amount), currency,
            str(user_id), user_name, payment_details, _now()))
        conn.execute(
            'UPDATE agent_bots SET escrow_balance=escrow_balance+? WHERE id=?',
            (float(amount), agent_id))
        conn.commit()
        return tid
    except Exception:
        conn.rollback()
    finally:
        conn.close()


def _apply_txn_effect(conn, agent_id, txn_type, amount, tid, reason):
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
    r = conn.execute('SELECT balance FROM agent_bots WHERE id=?', (agent_id,)).fetchone()
    if not r:
        raise ValueError('الوكيل غير موجود')
    bal = float(r['balance'])
    if txn_type == 'withdraw':
        new_bal = bal - float(amount)
        direction = 'debit'
        if new_bal < 0:
            raise ValueError('رصيد الوكيل غير كافٍ لعكس المعاملة')
    else:
        new_bal = bal + float(amount)
        direction = 'credit'
    conn.execute('UPDATE agent_bots SET balance=? WHERE id=?', (new_bal, agent_id))
    _ledger(conn, agent_id, amount, direction, reason, tid, new_bal)
    return new_bal


def agent_process_transaction(agent_id, txn_id, decision):
    """Agent approves/rejects. Releases escrow, updates scoring, contributes insurance."""
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

        txn_amount = float(t['amount'])

        # Release escrow
        conn.execute(
            'UPDATE agent_bots SET escrow_balance=MAX(0, escrow_balance-?) WHERE id=?',
            (txn_amount, agent_id))

        new_bal = None
        if decision == 'approved':
            new_bal = _apply_txn_effect(conn, agent_id, t['type'], txn_amount,
                                        txn_id, f"txn_{t['type']}")
            col = ('total_withdrawals_processed' if t['type'] == 'withdraw'
                   else 'total_deposits_processed')
            conn.execute(
                f'UPDATE agent_bots SET {col}={col}+1, total_volume=total_volume+? '
                f'WHERE id=?', (txn_amount, agent_id))

            # Insurance contribution (0.5% of transaction amount)
            ins_amount = round(txn_amount * INSURANCE_RATE, 2)
            if ins_amount > 0:
                _insurance_credit(conn, agent_id, txn_id, ins_amount)

        # Update performance stats
        _update_agent_stats(conn, agent_id)

        # Check excessive reject rate
        if decision == 'rejected':
            _check_excessive_reject(conn, agent_id)

        conn.commit()
        return {'success': True, 'new_balance': new_bal,
                'match_request_id': t['match_request_id'], 'type': t['type'],
                'user_id': t['user_id'], 'amount': txn_amount}
    except ValueError as e:
        conn.rollback()
        return {'error': str(e)}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def admin_override_transaction(agent_id, txn_id, new_status, admin_id=''):
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

        txn_amount = float(t['amount'])

        # Handle escrow on status changes
        if old == 'pending' and new_status != 'pending':
            # Release escrow when moving out of pending
            conn.execute(
                'UPDATE agent_bots SET escrow_balance=MAX(0, escrow_balance-?) WHERE id=?',
                (txn_amount, agent_id))
        elif old != 'pending' and new_status == 'pending':
            # Re-hold escrow when moving back to pending
            conn.execute(
                'UPDATE agent_bots SET escrow_balance=escrow_balance+? WHERE id=?',
                (txn_amount, agent_id))

        if old == 'approved':
            _reverse_txn_effect(conn, agent_id, t['type'], txn_amount,
                                txn_id, 'override_reversal')
            col = ('total_withdrawals_processed' if t['type'] == 'withdraw'
                   else 'total_deposits_processed')
            conn.execute(
                f'UPDATE agent_bots SET {col}=MAX(0,{col}-1), '
                f'total_volume=MAX(0,total_volume-?) WHERE id=?',
                (txn_amount, agent_id))
        if new_status == 'approved':
            _apply_txn_effect(conn, agent_id, t['type'], txn_amount,
                              txn_id, 'override_apply')
            col = ('total_withdrawals_processed' if t['type'] == 'withdraw'
                   else 'total_deposits_processed')
            conn.execute(
                f'UPDATE agent_bots SET {col}={col}+1, total_volume=total_volume+? '
                f'WHERE id=?', (txn_amount, agent_id))

        conn.execute(
            'UPDATE agent_transactions SET status=?, processed_at=?, admin_override=? '
            'WHERE id=?',
            (new_status, _now(), f'admin:{admin_id}:{new_status} (was:{old})', txn_id))

        _update_agent_stats(conn, agent_id)
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


# ── Heartbeat ─────────────────────────────────────────────────────────────────

def agent_heartbeat(agent_id):
    """Update heartbeat timestamp. Returns updated agent dict or error."""
    conn = _conn()
    try:
        r = conn.execute('SELECT id FROM agent_bots WHERE id=?', (agent_id,)).fetchone()
        if not r:
            return {'error': 'الوكيل غير موجود'}
        now = _now()
        conn.execute('UPDATE agent_bots SET last_heartbeat=?, is_online=1 WHERE id=?',
                     (now, agent_id))
        conn.commit()
        return {'success': True}
    finally:
        conn.close()


def check_agents_online():
    """Mark agents as offline if heartbeat is stale. Returns count marked offline."""
    cutoff = (datetime.now() - timedelta(seconds=HEARTBEAT_TIMEOUT)).strftime('%Y-%m-%d %H:%M:%S')
    conn = _conn()
    try:
        cur = conn.execute(
            "UPDATE agent_bots SET is_online=0 WHERE is_online=1 AND last_heartbeat != '' "
            "AND last_heartbeat < ?", (cutoff,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ── Stale Transaction Watchdog ──────────────────────────────────────────────

def void_stale_transactions(notify_callback=None):
    """Void pending transactions older than RESPONSE_TIMEOUT seconds.
    Returns list of voided transaction info."""
    cutoff = (datetime.now() - timedelta(seconds=RESPONSE_TIMEOUT)).strftime('%Y-%m-%d %H:%M:%S')
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        stale = conn.execute('''
            SELECT t.id, t.agent_id, t.amount, t.user_id, t.user_name,
                   t.match_request_id, t.type
            FROM agent_transactions t
            WHERE t.status='pending' AND t.created_at < ?
        ''', (cutoff,)).fetchall()

        voided = []
        for t in stale:
            tid = t['id']
            agent_id = t['agent_id']
            amount = float(t['amount'])

            # Delete txn + release escrow + release quota
            conn.execute(
                "DELETE FROM agent_transactions WHERE id=? AND agent_id=? AND status='pending'",
                (tid, agent_id))
            conn.execute(
                'UPDATE agent_bots SET escrow_balance=MAX(0, escrow_balance-?) WHERE id=?',
                (amount, agent_id))
            conn.execute(
                'UPDATE agent_bots SET current_daily_count=MAX(0,current_daily_count-1), '
                'current_daily_amount=MAX(0,current_daily_amount-?) WHERE id=?',
                (amount, agent_id))

            # Log penalty
            conn.execute('''INSERT INTO agent_penalties (agent_id, penalty_type, amount, reason, created_at)
                VALUES (?,'timeout',0,?,?)''',
                (agent_id, f"Transaction {tid} timed out ({RESPONSE_TIMEOUT}s)", _now()))

            voided.append({
                'txn_id': tid, 'agent_id': agent_id, 'amount': amount,
                'user_id': t['user_id'], 'user_name': t['user_name'],
                'match_request_id': t['match_request_id'], 'type': t['type']
            })

        if voided:
            # Update stats for affected agents
            affected = list({v['agent_id'] for v in voided})
            for aid in affected:
                _update_agent_stats(conn, aid)
                # Check excessive timeout penalties
                _check_timeout_penalties(conn, aid)

        conn.commit()
        return voided
    except Exception as e:
        conn.rollback()
        logger.error(f"void_stale_transactions error: {e}")
        return []
    finally:
        conn.close()


def _check_timeout_penalties(conn, agent_id):
    """Check if agent has too many timeouts and suspend traffic."""
    recent = conn.execute('''
        SELECT COUNT(*) c FROM agent_penalties
        WHERE agent_id=? AND penalty_type='timeout'
        AND created_at > ?
    ''', (agent_id,
          (datetime.now() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
          )).fetchone()
    count = recent['c'] if recent else 0
    if count >= 5:
        # Suspend traffic for 1 hour
        conn.execute(
            'UPDATE agent_bots SET traffic_on=0 WHERE id=? AND is_active=1', (agent_id,))
        logger.warning(f"Agent {agent_id} traffic suspended: {count} timeouts in 24h")


def _check_excessive_reject(conn, agent_id):
    """Check if agent reject rate is too high and auto-suspend."""
    stats = conn.execute('''
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) AS rejected
        FROM agent_transactions
        WHERE agent_id=? AND status IN ('approved','rejected')
        AND created_at > ?
    ''', (agent_id,
          (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
          )).fetchone()
    total = stats['total'] or 0
    rejected = stats['rejected'] or 0
    if total >= 20 and (rejected / total) > 0.4:
        conn.execute(
            'UPDATE agent_bots SET traffic_on=0 WHERE id=? AND is_active=1', (agent_id,))
        logger.warning(f"Agent {agent_id} traffic suspended: reject rate {rejected}/{total} > 40%")


# ── Insurance Pool ────────────────────────────────────────────────────────────

def _insurance_credit(conn, agent_id, ref_id, amount):
    """Add contribution to insurance pool (inside open transaction)."""
    # Get current pool balance
    last = conn.execute(
        'SELECT balance_after FROM insurance_pool ORDER BY id DESC LIMIT 1').fetchone()
    prev = float(last['balance_after']) if last else 0
    new_bal = prev + amount
    conn.execute('''INSERT INTO insurance_pool
        (agent_id, amount, direction, reference_id, balance_after, created_at)
        VALUES (?,'contribution',1,?,?,?)''',
        (agent_id, ref_id, new_bal, _now()))


def get_insurance_balance():
    conn = _conn()
    try:
        last = conn.execute(
            'SELECT balance_after FROM insurance_pool ORDER BY id DESC LIMIT 1').fetchone()
        return float(last['balance_after']) if last else 0
    finally:
        conn.close()


def insurance_payout(agent_id, match_id, amount, reason=''):
    """Pay out from insurance pool (e.g., dispute compensation)."""
    amount = float(amount)
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        last = conn.execute(
            'SELECT balance_after FROM insurance_pool ORDER BY id DESC LIMIT 1').fetchone()
        prev = float(last['balance_after']) if last else 0
        if prev < amount:
            conn.rollback()
            return {'error': f'رصيد صندوق التأمين غير كافي ({prev:.2f} < {amount:.2f})'}
        new_bal = prev - amount
        conn.execute('''INSERT INTO insurance_pool
            (agent_id, amount, direction, reference_id, balance_after, created_at)
            VALUES (?,'payout',-1,?,?,?)''',
            (agent_id, match_id or '', new_bal, _now()))
        conn.commit()
        return {'success': True, 'new_balance': new_bal}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def admin_insurance_adjust(amount, direction, reason=''):
    """Admin manual adjust insurance pool. direction='add'|'subtract'."""
    amount = float(abs(amount))
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        last = conn.execute(
            'SELECT balance_after FROM insurance_pool ORDER BY id DESC LIMIT 1').fetchone()
        prev = float(last['balance_after']) if last else 0
        if direction == 'subtract' and prev < amount:
            conn.rollback()
            return {'error': 'رصيد غير كافٍ'}
        new_bal = prev + amount if direction == 'add' else prev - amount
        conn.execute('''INSERT INTO insurance_pool
            (agent_id, amount, direction, reference_id, balance_after, created_at)
            VALUES ('','admin_adjust',1,?,?,?)''',
            (new_bal, _now()))
        conn.commit()
        return {'success': True, 'new_balance': new_bal}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def get_insurance_log(limit=100):
    conn = _conn()
    try:
        rows = conn.execute(
            'SELECT * FROM insurance_pool ORDER BY id DESC LIMIT ?', (int(limit),)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Penalties ────────────────────────────────────────────────────────────────

def add_penalty(agent_id, penalty_type, amount=0, reason=''):
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        # Deduct from balance if amount > 0
        amount = float(amount)
        if amount > 0:
            r = conn.execute('SELECT balance FROM agent_bots WHERE id=?',
                             (agent_id,)).fetchone()
            if not r:
                conn.rollback()
                return {'error': 'الوكيل غير موجود'}
            new_bal = float(r['balance']) - amount
            if new_bal < 0:
                new_bal = 0
            conn.execute('UPDATE agent_bots SET balance=? WHERE id=?',
                         (new_bal, agent_id))
            _ledger(conn, agent_id, amount, 'debit', f'penalty_{penalty_type}',
                     '', new_bal)

        conn.execute('''INSERT INTO agent_penalties (agent_id, penalty_type, amount, reason, created_at)
            VALUES (?,?,?,?,?)''', (agent_id, penalty_type, amount, reason, _now()))

        if penalty_type == 'fraud':
            conn.execute('UPDATE agent_bots SET is_active=0, traffic_on=0 WHERE id=?',
                         (agent_id,))

        _update_agent_stats(conn, agent_id)
        conn.commit()
        return {'success': True}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def get_penalties(agent_id, limit=50):
    conn = _conn()
    try:
        rows = conn.execute(
            'SELECT * FROM agent_penalties WHERE agent_id=? ORDER BY id DESC LIMIT ?',
            (agent_id, int(limit))).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_penalties(limit=100):
    conn = _conn()
    try:
        rows = conn.execute(
            'SELECT p.*, b.bot_name FROM agent_penalties p '
            'JOIN agent_bots b ON p.agent_id=b.id '
            'ORDER BY p.id DESC LIMIT ?', (int(limit),)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Matching Operations (SQLite) ────────────────────────────────────────────────
# These replace the CSV-based methods in matching.py's MatchManager class.

def db_create_match_request(user_id, customer_id, req_type, amount, currency,
                             company_id, company_name, payment_method_id='',
                             bot_id='', assigned_agent_id=''):
    """Create a match request in SQLite. Returns (req_id, error)."""
    existing = db_get_active_request_by_user(str(user_id))
    if existing:
        return None, "لديك طلب مطابقة نشط بالفعل"
    req_id = _generate_id('REQ')
    alias = _generate_alias()
    conn = _conn()
    try:
        conn.execute('''INSERT OR IGNORE INTO match_requests
            (id, user_id, customer_id, type, amount, currency, company_id,
             company_name, payment_method_id, status, created_at, alias,
             bot_id, assigned_agent_id)
            VALUES (?,?,?,?,?,?,?,?,?,'waiting',?,?,?,?,?)''', (
            req_id, str(user_id), str(customer_id), req_type,
            float(amount), currency, str(company_id), str(company_name),
            str(payment_method_id), _now(), alias, str(bot_id),
            str(assigned_agent_id)))
        conn.commit()
        logger.info(f"Match request created: {req_id} by user {user_id}")
        return req_id, None
    except Exception as e:
        return None, str(e)
    finally:
        conn.close()


def db_get_active_request_by_user(user_id):
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM match_requests WHERE user_id=? "
            "ORDER BY created_at DESC LIMIT 20",
            (str(user_id),)).fetchall()
        for r in rows:
            if _request_is_active_row(r):
                return dict(r)
        return None
    finally:
        conn.close()


def get_agent_by_telegram(telegram_id):
    conn = _conn()
    try:
        r = conn.execute(
            'SELECT * FROM agent_bots WHERE telegram_id=? AND is_active=1',
            (str(telegram_id),)).fetchone()
        return _agent_dict(r) if r else None
    finally:
        conn.close()


def db_find_match(request):
    """Find a matching opposite request (P2P — not agent-based)."""
    opposite = 'withdraw' if request['type'] == 'deposit' else 'deposit'
    conn = _conn()
    try:
        r = conn.execute('''
            SELECT * FROM match_requests
            WHERE status='waiting' AND type=? AND amount=?
            AND currency=? AND company_id=? AND user_id != ?
            LIMIT 1
        ''', (opposite, float(request['amount']), request['currency'],
              str(request['company_id']), str(request['user_id']))).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def db_create_match(deposit_req, withdraw_req, agent_id=''):
    """Create a match between two requests (or user + agent). Returns match_id."""
    match_id = _generate_id('MTCH')
    dep_alias = _generate_alias()
    with_alias = _generate_alias()
    bot_id = deposit_req.get('bot_id', '') or withdraw_req.get('bot_id', '')

    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''INSERT INTO matches
            (id, deposit_request_id, withdraw_request_id,
             depositor_id, withdrawer_id, depositor_alias, withdrawer_alias,
             amount, currency, company_id, company_name,
             status, confirmation_code, created_at,
             depositor_rated, withdrawer_rated, dispute_status,
             bot_id, agent_id)
            VALUES (?,?,?,?,?,?,?,?,?,'active','',?, 'no','no','none',?,?,?)''', (
            match_id, deposit_req['id'], withdraw_req.get('id', ''),
            str(deposit_req['user_id']),
            str(withdraw_req['user_id']) if withdraw_req.get('user_id') else f"AGENT_{agent_id}",
            dep_alias, with_alias,
            float(deposit_req['amount']), deposit_req['currency'],
            str(deposit_req['company_id']), str(deposit_req['company_name']),
            _now(), bot_id, agent_id))

        # Mark both requests as matched
        now_str = _now()
        conn.execute(
            "UPDATE match_requests SET status='matched', match_id=?, matched_at=? WHERE id=?",
            (match_id, now_str, deposit_req['id']))
        if withdraw_req.get('id'):
            conn.execute(
                "UPDATE match_requests SET status='matched', match_id=?, matched_at=? WHERE id=?",
                (match_id, now_str, withdraw_req['id']))

        conn.commit()
        logger.info(f"Match created: {match_id}")
        return match_id
    except Exception as e:
        conn.rollback()
        logger.error(f"Error creating match: {e}")
        return None
    finally:
        conn.close()


def db_get_match_by_id(match_id):
    conn = _conn()
    try:
        r = conn.execute('SELECT * FROM matches WHERE id=?', (match_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def db_get_match_by_user(user_id):
    conn = _conn()
    try:
        r = conn.execute(
            "SELECT * FROM matches WHERE status NOT IN ('completed','cancelled') "
            "AND (depositor_id=? OR withdrawer_id=?) LIMIT 1",
            (str(user_id), str(user_id))).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def db_update_match_status(match_id, status, extra_fields=None):
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        sets = ['status=?']
        vals = [status]
        if status == 'completed':
            sets.append('completed_at=?')
            vals.append(_now())
        if extra_fields:
            for k, v in extra_fields.items():
                sets.append(f'{k}=?')
                vals.append(v)
        vals.append(match_id)
        conn.execute(f'UPDATE matches SET {", ".join(sets)} WHERE id=?', vals)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"Error updating match status: {e}")
        return False
    finally:
        conn.close()


def db_set_confirmation_code(match_id, code):
    return db_update_match_status(match_id, 'awaiting_code',
                                  extra_fields={'confirmation_code': code})


def db_send_chat_message(match_id, sender_id, message):
    match = db_get_match_by_id(match_id)
    if not match:
        return None
    sender_alias = (match['depositor_alias']
                    if str(sender_id) == str(match['depositor_id'])
                    else match['withdrawer_alias'])
    receiver_id = (match['withdrawer_id']
                   if str(sender_id) == str(match['depositor_id'])
                   else match['depositor_id'])
    msg_id = _generate_id('MSG')
    conn = _conn()
    try:
        conn.execute('''INSERT INTO chat_messages
            (id, match_id, sender_id, sender_alias, message, timestamp)
            VALUES (?,?,?,?,?,?)''',
            (msg_id, match_id, str(sender_id), sender_alias, message, _now()))
        conn.commit()
    finally:
        conn.close()
    return {'msg_id': msg_id, 'sender_alias': sender_alias,
            'receiver_id': receiver_id, 'message': message}


def db_get_chat_history(match_id):
    conn = _conn()
    try:
        rows = conn.execute(
            'SELECT * FROM chat_messages WHERE match_id=? ORDER BY id',
            (match_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def db_rate_user(match_id, rater_id, rating, comment=''):
    match = db_get_match_by_id(match_id)
    if not match:
        return False
    rated_id = (match['withdrawer_id']
                if str(rater_id) == str(match['depositor_id'])
                else match['depositor_id'])
    rating_id = _generate_id('RTNG')
    conn = _conn()
    try:
        conn.execute('''INSERT INTO match_ratings
            (id, match_id, rater_id, rated_id, rating, comment, timestamp)
            VALUES (?,?,?,?,?,?,?)''',
            (rating_id, match_id, str(rater_id), str(rated_id),
             int(rating), comment, _now()))
        if str(rater_id) == str(match['depositor_id']):
            conn.execute("UPDATE matches SET depositor_rated='yes' WHERE id=?", (match_id,))
        else:
            conn.execute("UPDATE matches SET withdrawer_rated='yes' WHERE id=?", (match_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def db_get_user_rating(user_id):
    conn = _conn()
    try:
        rows = conn.execute(
            'SELECT rating FROM match_ratings WHERE rated_id=?', (str(user_id),)).fetchall()
    finally:
        conn.close()
    ratings = [int(r['rating']) for r in rows]
    return sum(ratings) / len(ratings) if ratings else None


def db_open_dispute(match_id, user_id, reason):
    dispute_id = _generate_id('DSPT')
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''INSERT INTO match_disputes
            (id, match_id, raised_by, reason, status, created_at)
            VALUES (?,?,?,?,?,?)''',
            (dispute_id, match_id, str(user_id), reason, 'open', _now()))
        conn.execute(
            "UPDATE matches SET status='disputed', dispute_status='open' WHERE id=?",
            (match_id,))
        conn.commit()
        logger.info(f"Dispute opened: {dispute_id} for match {match_id}")
        return dispute_id
    except Exception as e:
        conn.rollback()
        logger.error(f"Error opening dispute: {e}")
        return None
    finally:
        conn.close()


def db_resolve_dispute(dispute_id, resolution):
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        cur = conn.execute('''
            UPDATE match_disputes SET status='resolved_by_admin',
            admin_response=?, resolved_at=?
            WHERE id=? AND status='open'
        ''', (resolution, _now(), dispute_id))
        if cur.rowcount:
            d = conn.execute(
                'SELECT match_id FROM match_disputes WHERE id=?', (dispute_id,)).fetchone()
            if d:
                conn.execute(
                    "UPDATE matches SET dispute_status='resolved' WHERE id=?",
                    (d['match_id'],))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        logger.error(f"Error resolving dispute: {e}")
        return False
    finally:
        conn.close()


def db_get_active_disputes():
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT d.*, m.amount, m.currency, m.agent_id "
            "FROM match_disputes d JOIN matches m ON d.match_id=m.id "
            "WHERE d.status='open' ORDER BY d.created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def db_cancel_match(match_id, cancelled_by=''):
    return db_update_match_status(match_id, 'cancelled',
                                  extra_fields={'dispute_status': 'cancelled'})


def db_get_active_matches():
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM matches WHERE status NOT IN ('completed','cancelled') "
            "ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def db_get_completed_matches(limit=50):
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM matches WHERE status IN ('completed','cancelled') "
            "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def db_update_request_status(req_id, status, match_id=''):
    conn = _conn()
    try:
        conn.execute("UPDATE match_requests SET status=?, match_id=?, matched_at=? WHERE id=?",
                     (status, match_id, _now() if match_id else '', req_id))
        conn.commit()
    finally:
        conn.close()


def db_delete_request(req_id):
    conn = _conn()
    try:
        conn.execute("DELETE FROM match_requests WHERE id=?", (req_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def db_get_match_requests(status='', limit=100):
    conn = _conn()
    try:
        sql = 'SELECT * FROM match_requests WHERE 1=1'
        args = []
        if status:
            sql += ' AND status=?'
            args.append(status)
        sql += ' ORDER BY created_at DESC LIMIT ?'
        args.append(limit)
        rows = conn.execute(sql, args).fetchall()
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
        rid = _generate_id('ADR')
        conn.execute('''INSERT INTO agent_deposit_requests
            (id, agent_id, amount, method_name, reference, status, created_at)
            VALUES (?,?,?,?,?,'pending',?)''',
            (rid, agent_id, amount, method_name, reference, _now()))
        conn.commit()
        return {'success': True, 'id': rid}
    finally:
        conn.close()


def process_deposit_request(request_id, decision, admin_id=''):
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


# ── Agent Dashboard Stats ───────────────────────────────────────────────────

def get_agent_stats():
    """Aggregated stats for admin dashboard."""
    conn = _conn()
    try:
        total = conn.execute('SELECT COUNT(*) c FROM agent_bots').fetchone()['c']
        active = conn.execute(
            'SELECT COUNT(*) c FROM agent_bots WHERE is_active=1 AND traffic_on=1').fetchone()['c']
        online = conn.execute(
            'SELECT COUNT(*) c FROM agent_bots WHERE is_online=1').fetchone()['c']
        total_balance = conn.execute(
            'SELECT COALESCE(SUM(balance),0) b FROM agent_bots').fetchone()['b']
        total_escrow = conn.execute(
            'SELECT COALESCE(SUM(escrow_balance),0) e FROM agent_bots').fetchone()['e']
        total_txns = conn.execute(
            'SELECT COUNT(*) c FROM agent_transactions').fetchone()['c']
        return {
            'total': total, 'active': active, 'online': online,
            'total_balance': float(total_balance),
            'total_escrow': float(total_escrow),
            'total_transactions': total_txns,
            'insurance_balance': get_insurance_balance(),
        }
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════
# ── Unified Atomic Matching (single source of truth: SQLite) ──────────────
# These functions replace the CSV+SQLite split-brain flow. Bot and Web both
# call these; match_requests lives ONLY in SQLite from now on.
# ══════════════════════════════════════════════════════════════════════════

def _agent_txn_type(user_req_type):
    """User 'deposit' → agent RECEIVES money (txn type 'withdraw').
    User 'withdraw' → agent PAYS money (txn type 'deposit')."""
    if user_req_type in ('deposit', 'sell_usdt'):
        return 'withdraw'
    return 'deposit'


def create_match_request_with_agent_assignment(
    user_id, customer_id, req_type, amount, currency,
    company_id='', company_name='', payment_method_id='', details='',
    bot_id='', source_type='company', network='', rate=0.0,
):
    """Atomically: create match request + pick agent + create pending txn + hold escrow.

    Returns (req_id, error, agent_assigned, agent_info_or_None).
    agent_info = {'id','name','telegram_id'} when assigned, else None.
    """
    amount = float(amount or 0)
    if amount <= 0:
        return None, 'المبلغ يجب أن يكون أكبر من صفر', False, None
    if req_type not in OPS_REQ_TYPES:
        return None, 'نوع الطلب غير صالح', False, None
    source_type = 'personal_wallet' if str(source_type) == 'personal_wallet' else 'company'

    with _lock:
        conn = _conn()
        try:
            conn.execute('BEGIN IMMEDIATE')
            existing = conn.execute(
                "SELECT * FROM match_requests WHERE user_id=? "
                "ORDER BY created_at DESC LIMIT 10",
                (str(user_id),)).fetchall()
            existing = [r for r in existing if _request_is_active_row(r)]
            if existing:
                conn.rollback()
                return None, 'لديك طلب مطابقة نشط بالفعل — انتظر معالجته أو ألغِه', False, None

            req_id = _generate_id('REQ')
            alias = _generate_alias()
            now_dt = _ts_now()
            now_s = _to_ts(now_dt)
            rate_locked_until = ''
            try:
                rate = float(rate or 0)
            except Exception:
                rate = 0.0
            if req_type in ('buy_usdt', 'sell_usdt'):
                rate_locked_until = _to_ts(_plus_minutes(now_dt, USDT_RATE_LOCK_MIN))
            conn.execute('''INSERT INTO match_requests
                (id, user_id, customer_id, type, amount, currency, company_id,
                 company_name, payment_method_id, status, created_at, alias, bot_id,
                 source_type, state, rate, rate_locked_until, network)
                VALUES (?,?,?,?,?,?,?,?,?,'waiting',?,?,?,?,?,?,?,?)''',
                (req_id, str(user_id), str(customer_id), req_type, amount,
                 currency or 'EGP', str(company_id or ''), str(company_name or ''),
                 str(payment_method_id or ''), now_s, alias, str(bot_id or ''),
                 source_type, 'created', rate, rate_locked_until, str(network or '')))

            chosen = None
            if source_type != 'personal_wallet':
                chosen = _pick_agent_locked(
                    conn, _agent_txn_type(req_type), amount,
                    request_meta={
                        'currency': currency or 'EGP',
                        'company_id': company_id or '',
                        'req_type': req_type,
                    })
            agent_info = None
            if chosen:
                full = conn.execute(
                    'SELECT id, bot_name, telegram_id FROM agent_bots WHERE id=?',
                    (chosen['id'],)).fetchone()
                tid = _generate_id('ATX')
                conn.execute('''INSERT INTO agent_transactions
                    (id, agent_id, match_request_id, type, amount, currency, status,
                     user_id, user_name, payment_details, created_at)
                    VALUES (?,?,?,?,?,?, 'pending', ?,?,?,?)''',
                    (tid, chosen['id'], req_id, _agent_txn_type(req_type), amount,
                     currency or 'EGP', str(user_id), '', details, _now()))
                conn.execute(
                    'UPDATE agent_bots SET escrow_balance=escrow_balance+? WHERE id=?',
                    (amount, chosen['id']))
                conn.execute(
                    "UPDATE match_requests SET assigned_agent_id=? WHERE id=?",
                    (chosen['id'], req_id))
                agent_info = {
                    'id': full['id'] if full else chosen['id'],
                    'name': (full['bot_name'] if full else chosen.get('name', '')) or '',
                    'telegram_id': (full['telegram_id'] if full else '') or '',
                }

            req_row = conn.execute('SELECT * FROM match_requests WHERE id=?', (req_id,)).fetchone()
            if req_row:
                _instantiate_steps_locked(conn, req_row)

            _audit_event_locked(conn, 'match_requests', req_id, 'user', str(user_id),
                                'request_created', '', 'created', {
                                    'type': req_type,
                                    'amount': amount,
                                    'currency': currency or 'EGP',
                                    'source_type': source_type,
                                    'assigned_agent_id': (chosen or {}).get('id', ''),
                                })

            conn.commit()
            return req_id, None, agent_info is not None, agent_info
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.error(f"create_match_request_with_agent_assignment error: {e}")
            return None, str(e), False, None
        finally:
            conn.close()


def cancel_match_request_atomic(req_id, user_id):
    """Atomically cancel a waiting request + void its pending agent txn.

    Returns (success: bool, error: str|None). If an agent already settled the
    txn, cancellation is rejected so money movement is never undone silently.
    """
    with _lock:
        conn = _conn()
        try:
            conn.execute('BEGIN IMMEDIATE')
            req = conn.execute(
                "SELECT * FROM match_requests WHERE id=? AND user_id=?",
                (str(req_id), str(user_id))).fetchone()
            if not req:
                settled = conn.execute(
                    "SELECT 1 FROM agent_transactions WHERE match_request_id=? "
                    "AND status IN ('approved','rejected') LIMIT 1", (str(req_id),)).fetchone()
                conn.rollback()
                if settled:
                    return False, 'تمت معالجة الطلب بالفعل — لا يمكن إلغاؤه'
                return False, 'الطلب غير موجود أو لا يمكن إلغاؤه'

            status = str(_rowv(req, 'status', ''))
            state = str(_rowv(req, 'state', ''))
            if status in ('matched', 'rejected', 'cancelled') or state in OPS_FINAL_STATES:
                conn.rollback()
                return False, 'تمت معالجة الطلب بالفعل — لا يمكن إلغاؤه'
            if state in ('in_progress', 'pre_complete', 'disputed'):
                conn.rollback()
                return False, 'لا يمكن الإلغاء بعد بدء التنفيذ — افتح شكوى من الواجهة'

            has_progress = conn.execute(
                "SELECT 1 FROM op_steps WHERE txn_id=? AND status IN ('action_done','confirmed') "
                "AND actor_role!='system' LIMIT 1", (str(req_id),)).fetchone()
            if has_progress:
                conn.rollback()
                return False, 'لا يمكن الإلغاء بعد تنفيذ خطوة من الطرف الآخر'

            txn = conn.execute(
                "SELECT id, agent_id, amount FROM agent_transactions "
                "WHERE match_request_id=? AND status='pending'",
                (str(req_id),)).fetchone()
            if txn:
                conn.execute("DELETE FROM agent_transactions WHERE id=?", (txn['id'],))
                conn.execute(
                    'UPDATE agent_bots SET escrow_balance=MAX(0, escrow_balance-?), '
                    'current_daily_count=MAX(0, current_daily_count-1), '
                    'current_daily_amount=MAX(0,current_daily_amount-?) WHERE id=?',
                    (float(txn['amount']), float(txn['amount']), txn['agent_id']))

            conn.execute(
                "UPDATE match_requests SET status='cancelled', state='cancelled' WHERE id=?",
                (str(req_id),))
            _audit_event_locked(conn, 'match_requests', req_id, 'user', str(user_id),
                                'request_cancelled', status, 'cancelled', {})
            conn.commit()
            return True, None
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.error(f"cancel_match_request_atomic error: {e}")
            return False, str(e)
        finally:
            conn.close()


def admin_set_match_request_status(req_id, new_status, actor=''):
    """Admin approve/reject of a waiting request (web dashboard).

    - approve  → keep pending agent txn (agent will settle it); mark approved.
    - reject   → void pending agent txn + release escrow/quota; mark rejected.
    Returns (success, error).
    """
    if new_status not in ('approved', 'rejected'):
        return False, 'حالة غير صالحة'
    with _lock:
        conn = _conn()
        try:
            conn.execute('BEGIN IMMEDIATE')
            req = conn.execute(
                "SELECT * FROM match_requests WHERE id=?",
                (str(req_id),)).fetchone()
            if not req:
                conn.rollback()
                return False, 'الطلب غير موجود أو تمت معالجته'

            cur_status = str(_rowv(req, 'status', ''))
            cur_state = str(_rowv(req, 'state', ''))
            if cur_status in ('matched', 'cancelled', 'rejected') or cur_state in OPS_FINAL_STATES:
                conn.rollback()
                return False, 'الطلب غير موجود أو تمت معالجته'

            if new_status == 'rejected':
                progressed = conn.execute(
                    "SELECT 1 FROM op_steps WHERE txn_id=? AND status IN ('action_done','confirmed') "
                    "AND actor_role!='system' LIMIT 1", (str(req_id),)).fetchone()
                if progressed:
                    conn.rollback()
                    return False, 'لا يمكن الرفض بعد بدء التنفيذ — افتح نزاع بدلاً من ذلك'
                txn = conn.execute(
                    "SELECT id, agent_id, amount FROM agent_transactions "
                    "WHERE match_request_id=? AND status='pending'",
                    (str(req_id),)).fetchone()
                if txn:
                    conn.execute("DELETE FROM agent_transactions WHERE id=?", (txn['id'],))
                    conn.execute(
                        'UPDATE agent_bots SET escrow_balance=MAX(0, escrow_balance-?), '
                        'current_daily_count=MAX(0, current_daily_count-1), '
                        'current_daily_amount=MAX(0,current_daily_amount-?) WHERE id=?',
                        (float(txn['amount']), float(txn['amount']), txn['agent_id']))

            new_state = cur_state or 'created'
            if new_status == 'approved':
                assigned_agent_id = str(_rowv(req, 'assigned_agent_id', '') or '')
                if assigned_agent_id:
                    agent_row = conn.execute('SELECT * FROM agent_bots WHERE id=?', (assigned_agent_id,)).fetchone()
                    policy_err = _validate_agent_policy_locked(
                        conn, agent_row,
                        str(_rowv(req, 'type', '')),
                        float(_rowv(req, 'amount', 0) or 0),
                        str(req_id),
                    )
                    if policy_err:
                        conn.rollback()
                        return False, f'تعذر الموافقة: {policy_err}'
                if not _rowv(req, 'claimed_by_id', '') and _rowv(req, 'assigned_agent_id', ''):
                    conn.execute(
                        "UPDATE match_requests SET claimed_by_type='agent', claimed_by_id=?, claimed_at=? WHERE id=?",
                        (str(_rowv(req, 'assigned_agent_id', '')), _now(), str(req_id)))
                new_state = 'claimed' if new_state in ('', 'created') else new_state
                req2 = conn.execute('SELECT * FROM match_requests WHERE id=?', (str(req_id),)).fetchone()
                if req2:
                    _instantiate_steps_locked(conn, req2)
            elif new_status == 'rejected':
                new_state = 'cancelled'

            conn.execute(
                "UPDATE match_requests SET status=?, state=?, approved_by=?, approved_at=? WHERE id=?",
                (new_status, new_state, f'admin:{actor}' if actor else 'admin', _now(), str(req_id)))

            _audit_event_locked(conn, 'match_requests', req_id, 'admin', str(actor or 'admin'),
                                f'admin_{new_status}', cur_status, new_status,
                                {'state_from': cur_state, 'state_to': new_state})
            conn.commit()
            return True, None
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.error(f"admin_set_match_request_status error: {e}")
            return False, str(e)
        finally:
            conn.close()


def sync_match_request_from_txn(mrid, decision, agent_id=''):
    """After an agent settles a txn, mirror the decision onto the request row.
    approved → matched (request fulfilled), rejected → rejected."""
    if not mrid:
        return
    conn = _conn()
    try:
        req = conn.execute('SELECT * FROM match_requests WHERE id=?', (str(mrid),)).fetchone()
        if not req:
            return
        step_count = conn.execute('SELECT COUNT(*) c FROM op_steps WHERE txn_id=?', (str(mrid),)).fetchone()['c']
        if decision == 'approved':
            if int(step_count or 0) > 0:
                conn.execute(
                    "UPDATE match_requests SET status='approved', state='claimed', "
                    "approved_by=?, approved_at=?, claimed_by_type='agent', claimed_by_id=?, claimed_at=? "
                    "WHERE id=? AND status IN ('waiting','approved')",
                    (f'agent:{agent_id}' if agent_id else 'agent', _now(), str(agent_id or ''), _now(), str(mrid)))
            else:
                conn.execute(
                    "UPDATE match_requests SET status='matched', state='completed', approved_by=?, approved_at=? "
                    "WHERE id=? AND status IN ('waiting','approved')",
                    (f'agent:{agent_id}' if agent_id else 'agent', _now(), str(mrid)))
        else:
            conn.execute(
                "UPDATE match_requests SET status='rejected', state='cancelled', approved_by=?, approved_at=? "
                "WHERE id=? AND status IN ('waiting','approved')",
                (f'agent:{agent_id}' if agent_id else 'agent', _now(), str(mrid)))
        conn.commit()
    finally:
        conn.close()


def get_pending_with_requests(agent_id):
    """Agent dashboard view: pending txns joined with their match requests."""
    conn = _conn()
    try:
        rows = conn.execute('''
            SELECT t.id AS txn_id, t.type, t.amount, t.currency, t.status,
                   t.created_at, t.user_id, t.user_name, t.payment_details,
                   r.id AS request_id, r.company_name, r.company_id,
                   r.alias AS request_alias, r.customer_id,
                   r.status AS request_status, r.state AS request_state
            FROM agent_transactions t
            LEFT JOIN match_requests r ON t.match_request_id = r.id
            WHERE t.agent_id=? AND t.status='pending'
              AND (r.id IS NULL OR r.status='approved' OR r.state IN ('claimed','in_progress','escalated','disputed','pre_complete'))
            ORDER BY t.created_at ASC
        ''', (str(agent_id),)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_agent_match_requests(agent_id, limit=30):
    conn = _conn()
    try:
        rows = conn.execute('''
            SELECT r.*, a.bot_name AS agent_name, a.telegram_id AS agent_telegram_id
            FROM match_requests r
            LEFT JOIN agent_bots a ON r.assigned_agent_id = a.id
            WHERE r.assigned_agent_id=?
              AND r.status IN ('approved','disputed')
              AND (r.state IN ('created','claimed','in_progress','escalated','disputed','pre_complete') OR r.state='')
            ORDER BY r.created_at DESC
            LIMIT ?
        ''', (str(agent_id), int(limit))).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_match_request_full(req_id):
    """Full request row + assigned agent name (for admin panels/notifications)."""
    conn = _conn()
    try:
        row = conn.execute('''
            SELECT r.*, a.bot_name AS agent_name, a.telegram_id AS agent_telegram_id
            FROM match_requests r
            LEFT JOIN agent_bots a ON r.assigned_agent_id = a.id
            WHERE r.id=?
        ''', (str(req_id),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_match_request_steps(req_id):
    conn = _conn()
    try:
        req = conn.execute('''
            SELECT r.*, a.bot_name AS agent_name, a.telegram_id AS agent_telegram_id
            FROM match_requests r
            LEFT JOIN agent_bots a ON r.assigned_agent_id = a.id
            WHERE r.id=?
        ''', (str(req_id),)).fetchone()
        if not req:
            return None
        steps = conn.execute(
            'SELECT * FROM op_steps WHERE txn_id=? ORDER BY seq',
            (str(req_id),)).fetchall()
        payload = dict(req)
        payload['steps'] = [dict(s) for s in steps]
        return payload
    finally:
        conn.close()


def get_user_requests(user_id, limit=20):
    conn = _conn()
    try:
        rows = conn.execute(
            'SELECT * FROM match_requests WHERE user_id=? ORDER BY created_at DESC LIMIT ?',
            (str(user_id), int(limit))).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_ops_requests(statuses=None, states=None, limit=200):
    statuses = statuses or []
    states = states or []
    conn = _conn()
    try:
        sql = (
            'SELECT r.*, a.bot_name AS agent_name, a.is_online AS agent_online '
            'FROM match_requests r LEFT JOIN agent_bots a ON r.assigned_agent_id=a.id '
            'WHERE 1=1'
        )
        args = []
        if statuses:
            placeholders = ','.join(['?'] * len(statuses))
            sql += f' AND r.status IN ({placeholders})'
            args.extend([str(s) for s in statuses])
        if states:
            placeholders = ','.join(['?'] * len(states))
            sql += f' AND r.state IN ({placeholders})'
            args.extend([str(s) for s in states])
        sql += ' ORDER BY r.created_at DESC LIMIT ?'
        args.append(int(limit))
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def claim_request(req_id, claimer_type, claimer_id):
    if claimer_type not in ('agent', 'admin'):
        return {'error': 'claimer_type غير صالح'}
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        req = conn.execute('SELECT * FROM match_requests WHERE id=?', (str(req_id),)).fetchone()
        if not req:
            conn.rollback()
            return {'error': 'الطلب غير موجود'}
        if str(_rowv(req, 'state', '')) in OPS_FINAL_STATES or str(_rowv(req, 'status', '')) in ('cancelled', 'matched', 'rejected'):
            conn.rollback()
            return {'error': 'الطلب منتهٍ'}
        if claimer_type == 'agent':
            assigned = str(_rowv(req, 'assigned_agent_id', ''))
            if assigned and assigned != str(claimer_id):
                conn.rollback()
                return {'error': 'هذا الطلب ليس مخصصاً لك'}
            if str(_rowv(req, 'status', '')) != 'approved':
                conn.rollback()
                return {'error': 'لا يمكن الاستلام قبل موافقة الأدمن'}
            agent_row = conn.execute('SELECT * FROM agent_bots WHERE id=?', (str(claimer_id),)).fetchone()
            policy_err = _validate_agent_policy_locked(
                conn, agent_row,
                str(_rowv(req, 'type', '')),
                float(_rowv(req, 'amount', 0) or 0),
                str(req_id),
            )
            if policy_err:
                conn.rollback()
                return {'error': policy_err}

        claimed_by = str(_rowv(req, 'claimed_by_id', ''))
        if claimed_by and claimed_by != str(claimer_id):
            conn.rollback()
            return {'error': 'تم استلام الطلب بواسطة طرف آخر'}

        old_state = str(_rowv(req, 'state', '')) or 'created'
        new_state = 'claimed' if old_state in ('', 'created') else old_state
        conn.execute(
            "UPDATE match_requests SET claimed_by_type=?, claimed_by_id=?, claimed_at=?, state=? WHERE id=?",
            (str(claimer_type), str(claimer_id), _now(), new_state, str(req_id)))

        req2 = conn.execute('SELECT * FROM match_requests WHERE id=?', (str(req_id),)).fetchone()
        if req2:
            _instantiate_steps_locked(conn, req2)

        _audit_event_locked(conn, 'match_requests', req_id, claimer_type, str(claimer_id),
                            'request_claimed', old_state, new_state, {})
        conn.commit()
        return {'success': True, 'state': new_state}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def admin_takeover_request(req_id, admin_id, reason=''):
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        req = conn.execute('SELECT * FROM match_requests WHERE id=?', (str(req_id),)).fetchone()
        if not req:
            conn.rollback()
            return {'error': 'الطلب غير موجود'}
        if str(_rowv(req, 'state', '')) in OPS_FINAL_STATES:
            conn.rollback()
            return {'error': 'الطلب منتهٍ'}
        old_owner = {
            'claimed_by_type': _rowv(req, 'claimed_by_type', ''),
            'claimed_by_id': _rowv(req, 'claimed_by_id', ''),
        }
        old_state = str(_rowv(req, 'state', '')) or 'created'
        new_state = 'claimed'
        conn.execute(
            "UPDATE match_requests SET claimed_by_type='admin', claimed_by_id=?, claimed_at=?, state=? WHERE id=?",
            (str(admin_id), _now(), new_state, str(req_id)))
        _audit_event_locked(conn, 'match_requests', req_id, 'admin', str(admin_id),
                            'request_takeover', old_state, new_state,
                            {'reason': reason or '', 'old_owner': old_owner})
        conn.commit()
        return {'success': True}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def admin_reassign_request(req_id, admin_id, new_agent_id, reason=''):
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        req = conn.execute('SELECT * FROM match_requests WHERE id=?', (str(req_id),)).fetchone()
        if not req:
            conn.rollback()
            return {'error': 'الطلب غير موجود'}
        if str(_rowv(req, 'state', '')) in OPS_FINAL_STATES:
            conn.rollback()
            return {'error': 'الطلب منتهٍ'}
        old_agent = str(_rowv(req, 'assigned_agent_id', ''))
        if old_agent == str(new_agent_id):
            conn.rollback()
            return {'success': True, 'unchanged': True}

        tgt = conn.execute('SELECT * FROM agent_bots WHERE id=? AND is_active=1',
                           (str(new_agent_id),)).fetchone()
        if not tgt:
            conn.rollback()
            return {'error': 'الوكيل الجديد غير صالح'}

        amount = float(_rowv(req, 'amount', 0) or 0)
        policy_err = _validate_agent_policy_locked(
            conn, tgt, str(_rowv(req, 'type', '')), amount)
        if policy_err:
            conn.rollback()
            return {'error': policy_err}

        pending_txn = conn.execute(
            "SELECT * FROM agent_transactions WHERE match_request_id=? AND status='pending'",
            (str(req_id),)).fetchone()
        if pending_txn:
            pamount = float(_rowv(pending_txn, 'amount', 0) or 0)
            if old_agent:
                conn.execute(
                    'UPDATE agent_bots SET escrow_balance=MAX(0,escrow_balance-?) WHERE id=?',
                    (pamount, old_agent))
                _decrease_agent_daily_load_locked(conn, old_agent, pamount)
            conn.execute(
                'UPDATE agent_bots SET escrow_balance=escrow_balance+? WHERE id=?',
                (pamount, str(new_agent_id)))
            _reserve_agent_slot_locked(conn, str(new_agent_id), pamount, consume_pin=False)
            conn.execute(
                'UPDATE agent_transactions SET agent_id=? WHERE id=?',
                (str(new_agent_id), pending_txn['id']))

        old_state = str(_rowv(req, 'state', '')) or 'created'
        conn.execute(
            "UPDATE match_requests SET assigned_agent_id=?, claimed_by_type='agent', claimed_by_id=?, claimed_at=?, state='claimed' WHERE id=?",
            (str(new_agent_id), str(new_agent_id), _now(), str(req_id)))
        _audit_event_locked(conn, 'match_requests', req_id, 'admin', str(admin_id),
                            'request_reassigned', old_state, 'claimed',
                            {'reason': reason or '', 'old_agent': old_agent, 'new_agent': str(new_agent_id)})
        conn.commit()
        return {'success': True}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def _step_actor_allowed(step_row, req_row, actor_type, actor_id, action='act'):
    role = str(_rowv(step_row, 'actor_role', 'requester'))
    if actor_type == 'admin':
        return True
    if role == 'system':
        return actor_type == 'system'
    if role == 'requester':
        return str(actor_type) == 'user' and str(actor_id) == str(_rowv(req_row, 'user_id', ''))
    if role == 'processor':
        return _is_processor(actor_type, actor_id, req_row)
    return False


def _step_confirmer_allowed(step_row, req_row, actor_type, actor_id):
    role = str(_rowv(step_row, 'actor_role', 'requester'))
    if actor_type == 'admin':
        return True
    if role == 'requester':
        return _is_processor(actor_type, actor_id, req_row)
    if role == 'processor':
        return str(actor_type) == 'user' and str(actor_id) == str(_rowv(req_row, 'user_id', ''))
    return False


def request_step_action(req_id, step_id, actor_type, actor_id, evidence_ref='', note=''):
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        req = conn.execute('SELECT * FROM match_requests WHERE id=?', (str(req_id),)).fetchone()
        if not req:
            conn.rollback()
            return {'error': 'الطلب غير موجود'}
        if str(_rowv(req, 'status', '')) not in ('approved',):
            conn.rollback()
            return {'error': 'الطلب غير جاهز للتنفيذ — بانتظار موافقة الأدمن'}
        if str(_rowv(req, 'state', '')) in OPS_FINAL_STATES:
            conn.rollback()
            return {'error': 'الطلب منتهٍ'}

        step = conn.execute(
            'SELECT * FROM op_steps WHERE id=? AND txn_id=?',
            (str(step_id), str(req_id))).fetchone()
        if not step:
            conn.rollback()
            return {'error': 'الخطوة غير موجودة'}
        if str(_rowv(step, 'status', '')) not in ('pending', 'rejected', 'escalated'):
            conn.rollback()
            return {'error': 'لا يمكن تنفيذ هذه الخطوة حالياً'}
        if not _step_actor_allowed(step, req, actor_type, actor_id, action='act'):
            conn.rollback()
            return {'error': 'غير مصرح لك بتنفيذ هذه الخطوة'}
        if str(_rowv(step, 'evidence_type', 'none')) != 'none' and not str(evidence_ref or '').strip():
            conn.rollback()
            return {'error': 'هذه الخطوة تتطلب مرجع/دليل'}

        now_dt = _ts_now()
        confirm_deadline = _to_ts(_plus_minutes(now_dt, OP_STEP_CONFIRM_TIMEOUT_MIN))
        old_status = str(_rowv(step, 'status', 'pending'))
        conn.execute('''
            UPDATE op_steps
            SET status='action_done', evidence_ref=?, acted_at=?, acted_by=?,
                confirm_deadline=?, note=?, updated_at=?
            WHERE id=?
        ''', (
            str(evidence_ref or ''), _to_ts(now_dt), f'{actor_type}:{actor_id}',
            confirm_deadline, str(note or ''), _to_ts(now_dt), str(step_id)
        ))

        req_state = str(_rowv(req, 'state', '')) or 'created'
        if req_state in ('created', 'claimed', 'escalated'):
            conn.execute(
                "UPDATE match_requests SET state='in_progress', claimed_by_type=?, claimed_by_id=?, claimed_at=? WHERE id=?",
                ('admin' if actor_type == 'admin' else 'agent', str(actor_id), _now(), str(req_id)))
        _audit_event_locked(conn, 'op_steps', step_id, actor_type, str(actor_id),
                            'step_action', old_status, 'action_done',
                            {'req_id': req_id, 'evidence': str(evidence_ref or '')})
        _sync_request_state_from_steps_locked(conn, req_id)
        conn.commit()
        return {'success': True}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def request_step_confirm(req_id, step_id, actor_type, actor_id, accept=True, note=''):
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        req = conn.execute('SELECT * FROM match_requests WHERE id=?', (str(req_id),)).fetchone()
        if not req:
            conn.rollback()
            return {'error': 'الطلب غير موجود'}

        step = conn.execute(
            'SELECT * FROM op_steps WHERE id=? AND txn_id=?',
            (str(step_id), str(req_id))).fetchone()
        if not step:
            conn.rollback()
            return {'error': 'الخطوة غير موجودة'}
        if str(_rowv(step, 'status', '')) != 'action_done':
            conn.rollback()
            return {'error': 'لا توجد خطوة بانتظار التأكيد'}
        if not _step_confirmer_allowed(step, req, actor_type, actor_id):
            conn.rollback()
            return {'error': 'غير مصرح لك بتأكيد هذه الخطوة'}

        now_s = _to_ts(_ts_now())
        old_status = str(_rowv(step, 'status', 'action_done'))
        if accept:
            conn.execute('''
                UPDATE op_steps
                SET status='confirmed', confirmed_at=?, confirmed_by=?,
                    note=?, updated_at=?
                WHERE id=?
            ''', (now_s, f'{actor_type}:{actor_id}', str(note or ''), now_s, str(step_id)))
            _audit_event_locked(conn, 'op_steps', step_id, actor_type, str(actor_id),
                                'step_confirmed', old_status, 'confirmed', {'req_id': req_id})
        else:
            reject_count = int(_rowv(step, 'reject_count', 0) or 0) + 1
            new_status = 'pending' if reject_count < 2 else 'escalated'
            action_deadline = _to_ts(_plus_minutes(_ts_now(), OP_STEP_ACTION_TIMEOUT_MIN))
            conn.execute('''
                UPDATE op_steps
                SET status=?, reject_count=?, note=?, action_deadline=?,
                    confirm_deadline='', acted_at='', acted_by='', updated_at=?
                WHERE id=?
            ''', (new_status, reject_count, str(note or ''), action_deadline, now_s, str(step_id)))
            if new_status == 'escalated':
                conn.execute("UPDATE match_requests SET state='escalated' WHERE id=?", (str(req_id),))
            _audit_event_locked(conn, 'op_steps', step_id, actor_type, str(actor_id),
                                'step_rejected', old_status, new_status,
                                {'req_id': req_id, 'reject_count': reject_count})

        _sync_request_state_from_steps_locked(conn, req_id)

        req2 = conn.execute('SELECT * FROM match_requests WHERE id=?', (str(req_id),)).fetchone()
        if req2 and str(_rowv(req2, 'state', '')) == 'pre_complete' and not str(_rowv(req2, 'precomplete_until', '')):
            conn.execute(
                "UPDATE match_requests SET precomplete_until=? WHERE id=?",
                (_to_ts(_plus_minutes(_ts_now(), OP_PRECOMPLETE_WINDOW_MIN)), str(req_id)))

        conn.commit()
        return {'success': True}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def open_request_dispute(req_id, actor_type, actor_id, reason, evidence_file_id=''):
    reason = str(reason or '').strip()
    if len(reason) < 3:
        return {'error': 'سبب الشكوى قصير جداً'}
    if actor_type not in ('user', 'agent', 'admin'):
        return {'error': 'نوع الفاعل غير صالح'}
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        req = conn.execute('SELECT * FROM match_requests WHERE id=?', (str(req_id),)).fetchone()
        if not req:
            conn.rollback()
            return {'error': 'الطلب غير موجود'}
        if str(_rowv(req, 'state', '')) in OPS_FINAL_STATES or str(_rowv(req, 'status', '')) in ('matched', 'cancelled', 'rejected'):
            conn.rollback()
            return {'error': 'لا يمكن فتح شكوى بعد الإغلاق'}

        if actor_type == 'user' and str(_rowv(req, 'user_id', '')) != str(actor_id):
            conn.rollback()
            return {'error': 'غير مصرح لك بفتح شكوى لهذا الطلب'}
        if actor_type == 'agent' and not _is_processor('agent', actor_id, req):
            conn.rollback()
            return {'error': 'غير مصرح لك بفتح شكوى لهذا الطلب'}

        assigned_to_type = 'admin'
        assigned_to_id = ''
        if actor_type == 'user':
            candidate_agent = str(_rowv(req, 'assigned_agent_id', '') or '')
            if candidate_agent:
                arow = conn.execute('SELECT * FROM agent_bots WHERE id=?', (candidate_agent,)).fetchone()
                if arow:
                    max_open = int(_rowv(arow, 'max_open_disputes', 5) or 0)
                    open_count = _count_open_disputes_for_agent_locked(conn, candidate_agent)
                    if max_open <= 0 or open_count < max_open:
                        assigned_to_type = 'agent'
                        assigned_to_id = candidate_agent
        elif actor_type == 'agent':
            arow = conn.execute('SELECT * FROM agent_bots WHERE id=?', (str(actor_id),)).fetchone()
            max_open = int(_rowv(arow, 'max_open_disputes', 5) or 0) if arow else 0
            if max_open > 0 and _count_open_disputes_for_agent_locked(conn, str(actor_id)) >= max_open:
                conn.rollback()
                return {'error': 'تجاوزت الحد الأقصى للنزاعات المفتوحة'}

        did = _generate_id('DSP')
        d_status = 'assigned' if assigned_to_id else 'open'
        now = _now()
        conn.execute('''
            INSERT INTO op_disputes
            (id, req_id, opened_by_type, opened_by_id, assigned_to_type, assigned_to_id,
             status, reason, evidence_file_id, opened_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            did, str(req_id), str(actor_type), str(actor_id),
            assigned_to_type, assigned_to_id, d_status,
            reason, str(evidence_file_id or ''), now, now,
        ))

        old_state = str(_rowv(req, 'state', '')) or 'created'
        conn.execute(
            "UPDATE match_requests SET state='disputed', status='disputed', "
            "dispute_status='open', dispute_assigned_to_type=?, dispute_assigned_to_id=?, dispute_opened_at=? "
            "WHERE id=?",
            (assigned_to_type, assigned_to_id, now, str(req_id)))
        _audit_event_locked(conn, 'match_requests', req_id, actor_type, str(actor_id),
                            'request_disputed', old_state, 'disputed',
                            {
                                'reason': reason,
                                'evidence': str(evidence_file_id or ''),
                                'dispute_id': did,
                                'assigned_to_type': assigned_to_type,
                                'assigned_to_id': assigned_to_id,
                            })
        _audit_event_locked(conn, 'op_disputes', did, actor_type, str(actor_id),
                            'dispute_opened', '', d_status,
                            {'req_id': str(req_id)})
        conn.commit()
        return {
            'success': True,
            'dispute_id': did,
            'assigned_to_type': assigned_to_type,
            'assigned_to_id': assigned_to_id,
        }
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def resolve_request_dispute(req_id, admin_id, decision, note=''):
    if decision not in ('complete', 'cancel', 'reject'):
        return {'error': 'قرار غير صالح'}
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        req = conn.execute('SELECT * FROM match_requests WHERE id=?', (str(req_id),)).fetchone()
        if not req:
            conn.rollback()
            return {'error': 'الطلب غير موجود'}
        old_state = str(_rowv(req, 'state', '')) or 'created'
        if decision == 'complete':
            new_state = 'completed'
            new_status = 'matched'
        elif decision == 'reject':
            new_state = 'rejected'
            new_status = 'rejected'
        else:
            new_state = 'cancelled'
            new_status = 'cancelled'
        now = _now()
        conn.execute(
            'UPDATE match_requests SET state=?, status=?, approved_by=?, approved_at=?, '
            'dispute_status=?, dispute_resolved_at=? WHERE id=?',
            (new_state, new_status, f'admin:{admin_id}', now, 'resolved', now, str(req_id)))
        conn.execute(
            "UPDATE op_disputes SET status='resolved', resolution=?, admin_note=?, "
            "updated_at=?, resolved_at=?, resolved_by=? "
            "WHERE req_id=? AND status IN ('open','assigned','in_review')",
            (str(decision), str(note or ''), now, now, str(admin_id), str(req_id)))
        _audit_event_locked(conn, 'match_requests', req_id, 'admin', str(admin_id),
                            'dispute_resolved', old_state, new_state,
                            {'decision': decision, 'note': note or ''})
        conn.commit()
        return {'success': True, 'state': new_state, 'status': new_status}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def list_op_disputes(status='', assignee_type='', assignee_id='', limit=200):
    conn = _conn()
    try:
        sql = (
            "SELECT d.*, r.user_id, r.amount, r.currency, r.assigned_agent_id, "
            "a.bot_name AS assigned_agent_name "
            "FROM op_disputes d "
            "LEFT JOIN match_requests r ON r.id=d.req_id "
            "LEFT JOIN agent_bots a ON a.id=d.assigned_to_id "
            "WHERE 1=1"
        )
        args = []
        if status:
            statuses = [s.strip() for s in str(status).split(',') if s.strip()]
            if statuses:
                sql += f" AND d.status IN ({','.join(['?']*len(statuses))})"
                args.extend(statuses)
        if assignee_type:
            sql += ' AND d.assigned_to_type=?'
            args.append(str(assignee_type))
        if assignee_id:
            sql += ' AND d.assigned_to_id=?'
            args.append(str(assignee_id))
        sql += ' ORDER BY d.opened_at DESC LIMIT ?'
        args.append(int(limit))
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_op_dispute(dispute_id):
    conn = _conn()
    try:
        row = conn.execute('SELECT * FROM op_disputes WHERE id=?', (str(dispute_id),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def assign_op_dispute(dispute_id, admin_id, assignee_type, assignee_id='', note=''):
    if assignee_type not in ('agent', 'admin'):
        return {'error': 'نوع التوجيه غير صالح'}
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        d = conn.execute('SELECT * FROM op_disputes WHERE id=?', (str(dispute_id),)).fetchone()
        if not d:
            conn.rollback()
            return {'error': 'النزاع غير موجود'}
        if str(_rowv(d, 'status', '')) in ('resolved', 'cancelled'):
            conn.rollback()
            return {'error': 'النزاع مغلق'}

        target_id = str(assignee_id or '') if assignee_type == 'agent' else ''
        if assignee_type == 'agent':
            agent_row = conn.execute('SELECT * FROM agent_bots WHERE id=?', (target_id,)).fetchone()
            if not agent_row:
                conn.rollback()
                return {'error': 'الوكيل غير موجود'}
            max_open = int(_rowv(agent_row, 'max_open_disputes', 5) or 0)
            if max_open > 0 and _count_open_disputes_for_agent_locked(conn, target_id) >= max_open:
                conn.rollback()
                return {'error': 'الوكيل متجاوز حد النزاعات المفتوحة'}

        now = _now()
        conn.execute(
            "UPDATE op_disputes SET assigned_to_type=?, assigned_to_id=?, status='assigned', "
            "admin_note=?, updated_at=? WHERE id=?",
            (str(assignee_type), target_id, str(note or ''), now, str(dispute_id)))

        req_id = str(_rowv(d, 'req_id', ''))
        if req_id:
            conn.execute(
                "UPDATE match_requests SET dispute_status='open', dispute_assigned_to_type=?, "
                "dispute_assigned_to_id=? WHERE id=?",
                (str(assignee_type), target_id, req_id))
            _audit_event_locked(conn, 'match_requests', req_id, 'admin', str(admin_id),
                                'dispute_assigned', '', 'assigned', {
                                    'dispute_id': str(dispute_id),
                                    'assignee_type': str(assignee_type),
                                    'assignee_id': target_id,
                                })

        _audit_event_locked(conn, 'op_disputes', str(dispute_id), 'admin', str(admin_id),
                            'dispute_assigned', '', 'assigned', {
                                'assignee_type': str(assignee_type),
                                'assignee_id': target_id,
                            })
        conn.commit()
        return {'success': True}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def list_agent_op_disputes(agent_id, status='open,assigned,in_review', limit=200):
    return list_op_disputes(
        status=status,
        assignee_type='agent',
        assignee_id=str(agent_id),
        limit=limit,
    )


def process_ops_deadlines():
    """Scheduler-safe periodic job.

    - Escalate timed-out steps
    - Move pre_complete -> completed when window expires
    - Escalate requests exceeding total timeout
    """
    now_dt = _ts_now()
    now_s = _to_ts(now_dt)
    conn = _conn()
    result = {'escalated_steps': 0, 'completed': 0, 'escalated_requests': 0}
    try:
        conn.execute('BEGIN IMMEDIATE')
        rows = conn.execute('''
            SELECT s.id, s.txn_id, s.status, s.action_deadline, s.confirm_deadline, r.state
            FROM op_steps s
            JOIN match_requests r ON r.id = s.txn_id
            WHERE r.state NOT IN ('completed','cancelled','rejected','resolved_depositor','resolved_withdrawer')
              AND s.status IN ('pending','action_done')
        ''').fetchall()
        for r in rows:
            deadline = _parse_ts(r['confirm_deadline'] if r['status'] == 'action_done' else r['action_deadline'])
            if not deadline:
                continue
            if deadline < now_dt:
                conn.execute(
                    "UPDATE op_steps SET status='escalated', updated_at=? WHERE id=?",
                    (now_s, r['id']))
                conn.execute(
                    "UPDATE match_requests SET state='escalated' WHERE id=?",
                    (r['txn_id'],))
                _audit_event_locked(conn, 'op_steps', r['id'], 'system', 'watchdog',
                                    'step_escalated_timeout', r['status'], 'escalated',
                                    {'req_id': r['txn_id']})
                result['escalated_steps'] += 1

        pre_rows = conn.execute(
            "SELECT id, precomplete_until FROM match_requests WHERE state='pre_complete' AND precomplete_until!=''"
        ).fetchall()
        for r in pre_rows:
            till = _parse_ts(r['precomplete_until'])
            if till and till < now_dt:
                conn.execute(
                    "UPDATE match_requests SET state='completed', status='matched', approved_at=? WHERE id=?",
                    (now_s, r['id']))
                _audit_event_locked(conn, 'match_requests', r['id'], 'system', 'watchdog',
                                    'precomplete_elapsed', 'pre_complete', 'completed', {})
                result['completed'] += 1

        req_rows = conn.execute(
            "SELECT id, created_at, state FROM match_requests "
            "WHERE state IN ('created','claimed','in_progress','disputed')"
        ).fetchall()
        for r in req_rows:
            c_at = _parse_ts(r['created_at'])
            if not c_at:
                continue
            if c_at + timedelta(minutes=OP_TOTAL_TIMEOUT_MIN) < now_dt:
                conn.execute("UPDATE match_requests SET state='escalated' WHERE id=?", (r['id'],))
                _audit_event_locked(conn, 'match_requests', r['id'], 'system', 'watchdog',
                                    'request_timeout', r['state'], 'escalated', {})
                result['escalated_requests'] += 1

        conn.commit()
        return result
    except Exception as e:
        conn.rollback()
        logger.error(f'process_ops_deadlines error: {e}')
        return result
    finally:
        conn.close()


def list_routing_rules(active_only=False):
    conn = _conn()
    try:
        if active_only:
            rows = conn.execute(
                'SELECT * FROM routing_rules WHERE is_active=1 ORDER BY priority ASC, created_at ASC').fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM routing_rules ORDER BY is_active DESC, priority ASC, created_at ASC').fetchall()
        out = []
        for r in rows:
            rr = dict(r)
            try:
                rr['params'] = json.loads(rr.get('params_json', '{}') or '{}')
            except Exception:
                rr['params'] = {}
            out.append(rr)
        return out
    finally:
        conn.close()


def upsert_routing_rule(rule_id, rule_type, params, priority=100, is_active=True):
    if rule_type not in ('pin_next_to_agent', 'block_agent', 'max_amount_per_txn', 'route_currency', 'route_company'):
        return {'error': 'نوع القاعدة غير صالح'}
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        rid = str(rule_id or _generate_id('RRL'))
        params_json = json.dumps(params or {}, ensure_ascii=False)
        exists = conn.execute('SELECT 1 FROM routing_rules WHERE id=?', (rid,)).fetchone()
        if exists:
            conn.execute(
                'UPDATE routing_rules SET rule_type=?, params_json=?, priority=?, is_active=? WHERE id=?',
                (str(rule_type), params_json, int(priority or 100), 1 if is_active else 0, rid))
        else:
            conn.execute(
                'INSERT INTO routing_rules (id, priority, rule_type, params_json, is_active, created_at) '
                'VALUES (?,?,?,?,?,?)',
                (rid, int(priority or 100), str(rule_type), params_json, 1 if is_active else 0, _now()))
        conn.commit()
        return {'success': True, 'id': rid}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def delete_routing_rule(rule_id):
    conn = _conn()
    try:
        cur = conn.execute('DELETE FROM routing_rules WHERE id=?', (str(rule_id),))
        conn.commit()
        return {'success': cur.rowcount > 0}
    finally:
        conn.close()


def create_insurance_claim(txn_id, claimant_type, claimant_id, reason, evidence_file_id=''):
    reason = str(reason or '').strip()
    if len(reason) < 3:
        return {'error': 'سبب المطالبة قصير'}
    conn = _conn()
    try:
        req = conn.execute('SELECT id, state, status FROM match_requests WHERE id=?', (str(txn_id),)).fetchone()
        if not req:
            return {'error': 'العملية غير موجودة'}
        if str(_rowv(req, 'state', '')) != 'completed' and str(_rowv(req, 'status', '')) != 'matched':
            return {'error': 'مطالبة التأمين متاحة فقط بعد الإتمام النهائي'}
        cid = _generate_id('ICL')
        conn.execute('''
            INSERT INTO insurance_claims
            (id, txn_id, claimant_type, claimant_id, reason, evidence_file_id, status, payout_amount,
             admin_note, decided_by, decided_at, created_at)
            VALUES (?,?,?,?,?,?, 'open', 0, '', '', '', ?)
        ''', (cid, str(txn_id), str(claimant_type), str(claimant_id), reason,
              str(evidence_file_id or ''), _now()))
        conn.commit()
        return {'success': True, 'id': cid}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def list_insurance_claims(status=''):
    conn = _conn()
    try:
        if status:
            rows = conn.execute(
                'SELECT * FROM insurance_claims WHERE status=? ORDER BY created_at DESC LIMIT 200',
                (str(status),)).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM insurance_claims ORDER BY created_at DESC LIMIT 200').fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def decide_insurance_claim(claim_id, admin_id, decision, payout_amount=0, note=''):
    if decision not in ('approved', 'rejected'):
        return {'error': 'قرار غير صالح'}
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        c = conn.execute('SELECT * FROM insurance_claims WHERE id=?', (str(claim_id),)).fetchone()
        if not c:
            conn.rollback()
            return {'error': 'المطالبة غير موجودة'}
        if str(_rowv(c, 'status', '')) != 'open':
            conn.rollback()
            return {'error': 'تمت معالجة المطالبة بالفعل'}
        amount = float(payout_amount or 0)
        if decision == 'approved' and amount > 0:
            payout = insurance_payout('', str(_rowv(c, 'txn_id', '')), amount, f'insurance_claim:{claim_id}')
            if 'error' in payout:
                conn.rollback()
                return payout
        conn.execute(
            'UPDATE insurance_claims SET status=?, payout_amount=?, admin_note=?, decided_by=?, decided_at=? WHERE id=?',
            (decision, amount if decision == 'approved' else 0.0,
             str(note or ''), str(admin_id), _now(), str(claim_id)))
        conn.commit()
        return {'success': True}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()
