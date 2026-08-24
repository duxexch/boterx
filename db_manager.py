#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQLite Database Manager for VEX Games
Replaces CSV-based balance operations with ACID SQLite transactions.

Migrates users.csv → SQLite on first run.
Provides O(1) balance reads/writes with proper transaction safety.
"""

import os
import csv
import sqlite3
import threading
import time
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'boterx.db')
CSV_ENCODING = 'utf-8-sig'

_db_lock = threading.Lock()

# Constitution §2.5: Precision — ALL money math uses Decimal, NO native floats
# Convert to Decimal on input, round to 2 decimal places (cents), convert to float on output
def _money(val):
    """Convert any value to a precise Decimal rounded to 2 decimal places."""
    return Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def _money_float(val):
    """Convert Decimal back to float for API responses (display only)."""
    return float(_money(val))


def _get_conn():
    """Get a SQLite connection (thread-safe via check_same_thread=False)."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.execute('PRAGMA journal_mode=WAL')  # WAL mode for better concurrency
    conn.execute('PRAGMA synchronous=NORMAL')  # Faster writes, still durable
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    """Initialize database tables."""
    conn = _get_conn()
    try:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id TEXT PRIMARY KEY,
                name TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                customer_id TEXT DEFAULT '',
                language TEXT DEFAULT 'ar',
                currency TEXT DEFAULT 'EGP',
                game_balance REAL DEFAULT 0.0,
                is_banned TEXT DEFAULT 'no',
                is_admin TEXT DEFAULT 'no',
                phone_verified TEXT DEFAULT 'unknown',
                referral_earnings REAL DEFAULT 0.0,
                created_at TEXT DEFAULT '',
                extra_data TEXT DEFAULT '{}'
            );
            
            CREATE TABLE IF NOT EXISTS game_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                game_id TEXT,
                user_id TEXT,
                bet_amount REAL,
                payout REAL DEFAULT 0,
                result TEXT,
                multiplier REAL DEFAULT 0,
                balance_before REAL,
                balance_after REAL,
                timestamp TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_sessions_uid ON game_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_ts ON game_sessions(timestamp);
            
            CREATE TABLE IF NOT EXISTS provably_fair (
                session_id TEXT PRIMARY KEY,
                server_seed TEXT,
                seed_hash TEXT,
                client_seed TEXT,
                nonce INTEGER DEFAULT 0,
                revealed INTEGER DEFAULT 0,
                created_at TEXT
            );
            
            CREATE TABLE IF NOT EXISTS aviator_rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id INTEGER,
                crash_point REAL,
                seed_hash TEXT,
                client_seed TEXT,
                server_seed TEXT,
                bet_count INTEGER DEFAULT 0,
                total_wagered REAL DEFAULT 0,
                total_distributed REAL DEFAULT 0,
                created_at TEXT
            );

            -- Durable idempotency records: survive restarts, enforce exactly-once per (uid, request_id)
            -- Inserted atomically inside the same transaction as balance settlement.
            CREATE TABLE IF NOT EXISTS game_idempotency (
                uid TEXT NOT NULL,
                request_id TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (uid, request_id)
            );
            CREATE INDEX IF NOT EXISTS idx_idem_created ON game_idempotency(created_at);

            -- SVRP→game transfer idempotency log.
            -- A row is inserted atomically with the balance credit inside the same
            -- SQLite savepoint, so the log record and the balance update are always
            -- consistent even across crashes.  On replay the INSERT fails with
            -- IntegrityError and the balance update is skipped.
            CREATE TABLE IF NOT EXISTS svrp_transfer_log (
                transfer_id           TEXT PRIMARY KEY,
                uid                   TEXT    NOT NULL,
                amount                REAL    NOT NULL DEFAULT 0,
                status                TEXT    NOT NULL DEFAULT 'pending',
                pre_debit_svrp_balance REAL,
                csv_debited           INTEGER NOT NULL DEFAULT 0,
                created_at            TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_svrp_tlog_uid ON svrp_transfer_log(uid);

            -- Authoritative frozen SVRP wallet balance (replaces svrp_wallets.csv
            -- for all financial mutations).  The CSV is kept for display/metadata only.
            -- wagering_required/wagering_completed control when the balance is unlocked.
            CREATE TABLE IF NOT EXISTS svrp_wallet_balance (
                uid                  TEXT PRIMARY KEY,
                frozen_balance       REAL NOT NULL DEFAULT 0,
                total_earned         REAL NOT NULL DEFAULT 0,
                total_used           REAL NOT NULL DEFAULT 0,
                wagering_required    INTEGER NOT NULL DEFAULT 3,
                wagering_completed   INTEGER NOT NULL DEFAULT 0
            );

            -- Per-request approval ledger.  Each recovery approval gets one row;
            -- the balance credit and status transition are committed in a single
            -- SAVEPOINT so there is no crash window between them.
            CREATE TABLE IF NOT EXISTS svrp_approval_log (
                req_id      TEXT PRIMARY KEY,
                uid         TEXT NOT NULL,
                amount      REAL NOT NULL DEFAULT 0,
                status      TEXT NOT NULL DEFAULT 'pending',
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_svrp_alog_uid ON svrp_approval_log(uid);

            -- Snatch game sessions: durable state machine co-located with wallet
            -- so wallet and session state are always in the same DB file.
            -- status: intent | pending | settling | refunding | settled | refunded
            CREATE TABLE IF NOT EXISTS snatch_sessions (
                session_id      TEXT PRIMARY KEY,
                uid             TEXT NOT NULL,
                bet_amount      REAL NOT NULL,
                spin_request_id TEXT,
                created_at      REAL NOT NULL,
                status          TEXT NOT NULL DEFAULT 'intent',
                score           INTEGER,
                payout          REAL,
                settled_at      REAL
            );
            CREATE INDEX IF NOT EXISTS idx_snatch_status_time
                ON snatch_sessions (status, created_at);

            -- Active real-time game sessions: mines, plinko, etc.
            -- Survives server restarts. TTL enforced by expires_at.
            -- game: 'mines' | 'plinko' | 'wheel' | 'snatch' | ...
            CREATE TABLE IF NOT EXISTS active_game_sessions (
                user_id     TEXT NOT NULL,
                game        TEXT NOT NULL,
                session_data TEXT NOT NULL DEFAULT '{}',
                bet_amount  REAL NOT NULL DEFAULT 0,
                created_at  REAL NOT NULL,
                expires_at  REAL NOT NULL,
                PRIMARY KEY (user_id, game)
            );
            CREATE INDEX IF NOT EXISTS idx_ags_exp ON active_game_sessions(expires_at);

            -- Admin RBAC: roles and per-role permission sets
            -- role: 'super_admin' | 'finance_admin' | 'support_admin' | 'game_admin' | 'broadcast_admin'
            -- permissions: JSON object {"approve_deposits":true, "ban_users":false, ...}
            CREATE TABLE IF NOT EXISTS admin_roles (
                uid         TEXT PRIMARY KEY,
                role        TEXT NOT NULL DEFAULT 'support_admin',
                permissions TEXT NOT NULL DEFAULT '{}',
                created_at  TEXT NOT NULL DEFAULT '',
                created_by  TEXT NOT NULL DEFAULT ''
            );

            -- Admin action audit trail
            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                uid       TEXT NOT NULL,
                action    TEXT NOT NULL,
                target    TEXT DEFAULT '',
                details   TEXT DEFAULT '',
                ip        TEXT DEFAULT '',
                timestamp TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_uid ON admin_audit_log(uid);
            CREATE INDEX IF NOT EXISTS idx_audit_ts  ON admin_audit_log(timestamp);

            -- Financial ledger: every debit/credit with reason
            CREATE TABLE IF NOT EXISTS financial_ledger (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      TEXT NOT NULL,
                amount       REAL NOT NULL,
                direction    TEXT NOT NULL,  -- 'credit' | 'debit'
                reason       TEXT NOT NULL,  -- 'deposit' | 'withdrawal' | 'game_bet' | 'game_win' | 'referral' | 'compensation'
                reference_id TEXT DEFAULT '',
                balance_after REAL NOT NULL DEFAULT 0,
                timestamp    TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ledger_uid ON financial_ledger(user_id);
            CREATE INDEX IF NOT EXISTS idx_ledger_ts  ON financial_ledger(timestamp);

            -- Persisted replay-protection nonces for Telegram initData tokens.
            -- Survives dashboard restarts so stolen tokens cannot be replayed even
            -- after a process restart.  TTL matches _INIT_DATA_MAX_AGE + buffer.
            -- device_fp: fingerprint of the device that first presented this token;
            -- same-device reuse is allowed, cross-device reuse is blocked.
            CREATE TABLE IF NOT EXISTS auth_nonces (
                token_hash  TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL,
                device_fp   TEXT NOT NULL DEFAULT '',
                created_at  REAL NOT NULL,
                expires_at  REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_nonces_exp ON auth_nonces(expires_at);

            -- AI API Keys for multi-provider LLM integration
            CREATE TABLE IF NOT EXISTS ai_api_keys (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                key_name         TEXT NOT NULL,
                provider         TEXT NOT NULL,
                api_key          TEXT NOT NULL,
                base_url         TEXT DEFAULT '',
                default_model    TEXT NOT NULL,
                priority         INTEGER NOT NULL DEFAULT 10,
                temperature      REAL NOT NULL DEFAULT 0.7,
                max_tokens       INTEGER NOT NULL DEFAULT 4096,
                timeout_seconds  INTEGER NOT NULL DEFAULT 60,
                is_active        INTEGER NOT NULL DEFAULT 1,
                models_list      TEXT DEFAULT '[]',
                requests_today   INTEGER NOT NULL DEFAULT 0,
                tokens_today     INTEGER NOT NULL DEFAULT 0,
                cost_estimate_usd REAL NOT NULL DEFAULT 0.0,
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ai_keys_provider ON ai_api_keys(provider);
            CREATE INDEX IF NOT EXISTS idx_ai_keys_active ON ai_api_keys(is_active);

            -- Social Media Accounts for sub-agents
            CREATE TABLE IF NOT EXISTS social_accounts (
                id                TEXT PRIMARY KEY,
                platform          TEXT NOT NULL,
                account_name      TEXT NOT NULL,
                handle            TEXT NOT NULL,
                sub_agent_id      TEXT NOT NULL,
                sub_agent_name    TEXT NOT NULL,
                access_token      TEXT NOT NULL,
                page_id           TEXT DEFAULT '',
                phone_number_id   TEXT DEFAULT '',
                business_account_id TEXT DEFAULT '',
                posting_permissions TEXT NOT NULL DEFAULT 'full',
                content_categories TEXT DEFAULT '',
                is_active         TEXT NOT NULL DEFAULT 'yes',
                followers         INTEGER NOT NULL DEFAULT 0,
                last_sync         TEXT DEFAULT '',
                created_at        TEXT NOT NULL,
                updated_at        TEXT NOT NULL,
                created_by        TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_social_accounts_platform ON social_accounts(platform);
            CREATE INDEX IF NOT EXISTS idx_social_accounts_agent ON social_accounts(sub_agent_id);
            CREATE INDEX IF NOT EXISTS idx_social_accounts_active ON social_accounts(is_active);

            -- Social Media Posts Log
            CREATE TABLE IF NOT EXISTS social_posts (
                id                TEXT PRIMARY KEY,
                account_id        TEXT NOT NULL,
                content           TEXT,
                media_urls        TEXT,
                status            TEXT NOT NULL,
                posted_at         TEXT NOT NULL,
                created_at        TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_social_posts_account ON social_posts(account_id);
            CREATE INDEX IF NOT EXISTS idx_social_posts_posted ON social_posts(posted_at);
        ''')
        conn.commit()
    finally:
        conn.close()


def _migrate_from_csv():
    """Migrate users from users.csv to SQLite (one-time)."""
    csv_path = os.path.join(BASE_DIR, 'users.csv')
    if not os.path.exists(csv_path):
        return 0

    conn = _get_conn()
    migrated = 0
    try:
        # Check if already migrated
        count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        if count > 0:
            return count  # Already has data

        with open(csv_path, 'r', encoding=CSV_ENCODING) as f:
            reader = csv.DictReader(f)
            for row in reader:
                tid = row.get('telegram_id', '')
                if not tid:
                    continue
                # Collect extra columns not in our schema
                known_cols = {'telegram_id', 'name', 'phone', 'customer_id', 'language',
                              'currency', 'game_balance', 'is_banned', 'is_admin',
                              'phone_verified', 'referral_earnings', 'created_at'}
                extra = {k: v for k, v in row.items() if k and k not in known_cols}
                try:
                    conn.execute('''
                        INSERT OR IGNORE INTO users 
                        (telegram_id, name, phone, customer_id, language, currency,
                         game_balance, is_banned, is_admin, phone_verified, 
                         referral_earnings, created_at, extra_data)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        tid,
                        row.get('name', ''),
                        row.get('phone', ''),
                        row.get('customer_id', ''),
                        row.get('language', 'ar'),
                        row.get('currency', 'EGP'),
                        float(row.get('game_balance', 0) or 0),
                        row.get('is_banned', 'no'),
                        row.get('is_admin', 'no'),
                        row.get('phone_verified', 'unknown'),
                        float(row.get('referral_earnings', 0) or 0),
                        row.get('created_at', ''),
                        '{}'
                    ))
                    migrated += 1
                except Exception:
                    pass
        conn.commit()
        print(f"✅ SQLite migration: {migrated} users migrated from CSV")
    except Exception as e:
        print(f"SQLite migration error: {e}")
    finally:
        conn.close()
    return migrated


# Initialize on import
_init_db()
_migrate_from_csv()


class GameDB:
    """SQLite-backed game database operations."""

    def __init__(self, db_path=None):
        self._local = threading.local()
        self._db_path = db_path or DB_PATH
        if db_path and db_path != DB_PATH:
            # Initialize the custom DB (creates tables) on first instantiation
            self._custom_init()

    def _custom_init(self):
        """Initialize tables for a custom (test) DB path."""
        conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=10)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA foreign_keys=ON')
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id TEXT PRIMARY KEY, name TEXT DEFAULT '',
                phone TEXT DEFAULT '', customer_id TEXT DEFAULT '',
                language TEXT DEFAULT 'ar', currency TEXT DEFAULT 'EGP',
                game_balance REAL DEFAULT 0.0, is_banned TEXT DEFAULT 'no',
                is_admin TEXT DEFAULT 'no', phone_verified TEXT DEFAULT 'unknown',
                referral_earnings REAL DEFAULT 0.0, created_at TEXT DEFAULT '',
                extra_data TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS game_idempotency (
                uid TEXT NOT NULL, request_id TEXT NOT NULL,
                response_json TEXT NOT NULL, created_at REAL NOT NULL,
                PRIMARY KEY (uid, request_id)
            );
            CREATE INDEX IF NOT EXISTS idx_idem_created ON game_idempotency(created_at);
            CREATE TABLE IF NOT EXISTS snatch_sessions (
                session_id      TEXT PRIMARY KEY,
                uid             TEXT NOT NULL,
                bet_amount      REAL NOT NULL,
                spin_request_id TEXT,
                created_at      REAL NOT NULL,
                status          TEXT NOT NULL DEFAULT 'intent',
                score           INTEGER,
                payout          REAL,
                settled_at      REAL
            );
            CREATE INDEX IF NOT EXISTS idx_snatch_status_time
                ON snatch_sessions (status, created_at);
        ''')
        conn.commit()
        conn.close()

    def _conn(self):
        """Per-thread connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            if self._db_path != DB_PATH:
                conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=10)
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA synchronous=NORMAL')
                conn.row_factory = sqlite3.Row
                self._local.conn = conn
            else:
                self._local.conn = _get_conn()
        return self._local.conn

    # ===== Balance Operations =====

    def get_balance(self, user_id):
        """O(1) balance read from SQLite."""
        uid = str(user_id)
        conn = self._conn()
        row = conn.execute(
            'SELECT game_balance FROM users WHERE telegram_id = ?', (uid,)
        ).fetchone()
        return _money_float(row[0]) if row and row[0] is not None else 0.0

    def get_user_currency(self, user_id):
        """Get user currency."""
        uid = str(user_id)
        conn = self._conn()
        row = conn.execute(
            'SELECT currency FROM users WHERE telegram_id = ?', (uid,)
        ).fetchone()
        return row[0] if row else 'EGP'

    def get_user_row(self, user_id):
        """Get full user row as dict."""
        uid = str(user_id)
        conn = self._conn()
        row = conn.execute(
            'SELECT * FROM users WHERE telegram_id = ?', (uid,)
        ).fetchone()
        if row:
            d = dict(row)
            # Merge extra_data
            import json
            try:
                extra = json.loads(d.pop('extra_data', '{}'))
                d.update(extra)
            except:
                d.pop('extra_data', '{}')
            return d
        return {}

    # ── SVRP transfer outbox — state machine helpers ──────────────────────────
    # State transitions:
    #   (new) ──create_svrp_transfer──► pending
    #   pending ──mark_svrp_transfer_debited (CAS)──► debited   [amount set here]
    #   debited ──add_balance_for_svrp_transfer──► completed    [credit + CAS]
    #   debited ──mark_svrp_transfer_status──► rolled_back      [after CSV rollback]
    #   completed ──(replay)──► completed                        [no-op, returns balance]
    #
    # "pending → debited" is a compare-and-set: the UPDATE only matches rows
    # where uid AND status='pending', so concurrent calls with the same key
    # (or a resumed call that finds the row already 'debited'/'completed') are
    # rejected rather than creating a second debit.

    def _ensure_svrp_transfer_table(self, conn):
        """Idempotent: create svrp_transfer_log + wallet/approval tables; add missing cols."""
        conn.execute('''
            CREATE TABLE IF NOT EXISTS svrp_transfer_log (
                transfer_id           TEXT PRIMARY KEY,
                uid                   TEXT    NOT NULL,
                amount                REAL    NOT NULL DEFAULT 0,
                status                TEXT    NOT NULL DEFAULT 'pending',
                pre_debit_svrp_balance REAL,
                created_at            TEXT    NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS svrp_wallet_balance (
                uid                TEXT PRIMARY KEY,
                frozen_balance     REAL NOT NULL DEFAULT 0,
                total_earned       REAL NOT NULL DEFAULT 0,
                total_used         REAL NOT NULL DEFAULT 0,
                wagering_required  INTEGER NOT NULL DEFAULT 3,
                wagering_completed INTEGER NOT NULL DEFAULT 0
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS svrp_approval_log (
                req_id     TEXT PRIMARY KEY,
                uid        TEXT NOT NULL,
                amount     REAL NOT NULL DEFAULT 0,
                status     TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
        ''')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_svrp_alog_uid ON svrp_approval_log(uid)'
        )
        # Migration: add columns that may be absent on existing installations
        for _col_ddl in [
            'ALTER TABLE svrp_transfer_log ADD COLUMN pre_debit_svrp_balance REAL',
            'ALTER TABLE svrp_transfer_log ADD COLUMN csv_debited INTEGER NOT NULL DEFAULT 0',
        ]:
            try:
                conn.execute(_col_ddl)
                conn.commit()
            except Exception:
                pass  # column already exists

    # ── SQLite-only SVRP wallet operations ──────────────────────────────────
    # All financial mutations (frozen balance credit/debit) happen exclusively
    # in SQLite so that each state transition is atomic within a single DB
    # transaction.  The svrp_wallets.csv remains for display/metadata only and
    # is never consulted for balance decisions.

    def get_svrp_frozen_balance(self, uid):
        """Return the SQLite frozen-balance row for uid, or a zeroed default dict.

        Always reflects the authoritative committed state — no CSV involved.
        """
        conn = self._conn()
        self._ensure_svrp_transfer_table(conn)
        row = conn.execute(
            'SELECT frozen_balance, total_earned, total_used, '
            'wagering_required, wagering_completed '
            'FROM svrp_wallet_balance WHERE uid = ?',
            (str(uid),)
        ).fetchone()
        if row:
            return {
                'uid': str(uid),
                'frozen_balance':     float(row[0]),
                'total_earned':       float(row[1]),
                'total_used':         float(row[2]),
                'wagering_required':  int(row[3]),
                'wagering_completed': int(row[4]),
            }
        return {
            'uid': str(uid),
            'frozen_balance': 0.0, 'total_earned': 0.0, 'total_used': 0.0,
            'wagering_required': 3, 'wagering_completed': 0,
        }

    def upsert_svrp_wallet_balance(self, uid, frozen_balance, total_earned,
                                   total_used, wagering_required, wagering_completed):
        """DEPRECATED — kept for migration/backfill callers only.

        All live mutations must use delta_update_svrp_wallet() so they never
        overwrite SQLite with a stale CSV-derived value.
        """
        # Silently forward to the safe path only if the row does not already exist
        # (acts as INSERT OR IGNORE equivalent so backfills still work).
        conn = self._conn()
        self._ensure_svrp_transfer_table(conn)
        with _db_lock:
            conn.execute(
                'INSERT OR IGNORE INTO svrp_wallet_balance '
                '(uid, frozen_balance, total_earned, total_used, '
                ' wagering_required, wagering_completed) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (str(uid), float(frozen_balance), float(total_earned),
                 float(total_used), int(wagering_required), int(wagering_completed))
            )
            conn.commit()

    def delta_update_svrp_wallet(self, uid,
                                  frozen_balance_delta: float = 0.0,
                                  total_earned_delta:   float = 0.0,
                                  total_used_delta:     float = 0.0,
                                  wagering_completed_delta: int = 0,
                                  set_wagering_required: int = None):
        """Apply incremental deltas to the SQLite frozen wallet atomically.

        This is the ONLY write path for live SVRP mutations after initial
        migration.  All callers pass deltas so that SQLite is always updated
        by the exact amount of each business event — no stale CSV value is
        ever read and re-upserted, so previous transfer debits are preserved.

        An INSERT OR IGNORE ensures the row exists before the UPDATE, so this
        is safe for first-time wallet creation too.

        Returns the updated row as a dict.
        """
        uid = str(uid)
        conn = self._conn()
        self._ensure_svrp_transfer_table(conn)
        with _db_lock:
            # Ensure row exists
            conn.execute(
                'INSERT OR IGNORE INTO svrp_wallet_balance '
                '(uid, frozen_balance, total_earned, total_used, '
                ' wagering_required, wagering_completed) '
                'VALUES (?, 0, 0, 0, 3, 0)',
                (uid,)
            )
            # Apply deltas
            if set_wagering_required is not None:
                conn.execute(
                    'UPDATE svrp_wallet_balance SET '
                    'frozen_balance     = frozen_balance     + ?, '
                    'total_earned       = total_earned       + ?, '
                    'total_used         = total_used         + ?, '
                    'wagering_completed = wagering_completed + ?, '
                    'wagering_required  = ? '
                    'WHERE uid = ?',
                    (float(frozen_balance_delta), float(total_earned_delta),
                     float(total_used_delta), int(wagering_completed_delta),
                     int(set_wagering_required), uid)
                )
            else:
                conn.execute(
                    'UPDATE svrp_wallet_balance SET '
                    'frozen_balance     = frozen_balance     + ?, '
                    'total_earned       = total_earned       + ?, '
                    'total_used         = total_used         + ?, '
                    'wagering_completed = wagering_completed + ? '
                    'WHERE uid = ?',
                    (float(frozen_balance_delta), float(total_earned_delta),
                     float(total_used_delta), int(wagering_completed_delta), uid)
                )
            conn.commit()
            row = conn.execute(
                'SELECT frozen_balance, total_earned, total_used, '
                'wagering_required, wagering_completed '
                'FROM svrp_wallet_balance WHERE uid = ?', (uid,)
            ).fetchone()
            return {
                'uid': uid,
                'frozen_balance':     float(row[0]),
                'total_earned':       float(row[1]),
                'total_used':         float(row[2]),
                'wagering_required':  int(row[3]),
                'wagering_completed': int(row[4]),
            } if row else None

    def claim_svrp_task_atomically(self, task_id: str, uid: str, reward: float):
        """Claim a task reward in a single SQLite SAVEPOINT.

        Returns one of:
          'claimed'          — credited now for the first time
          'already_claimed'  — idempotent replay; caller can still mark CSV

        Guarantees:
          - task_id is a PRIMARY KEY in svrp_task_claims so two concurrent
            requests both get the INSERT; only one wins (rowcount == 1), the
            other sees rowcount == 0 and returns 'already_claimed'.
          - Wallet credit and claim record are in the same SAVEPOINT; a crash
            between INSERT and UPDATE is impossible — both commit or neither does.
          - Retry after crash between RELEASE and CSV update: INSERT OR IGNORE
            returns rowcount == 0 → 'already_claimed'; wallet is NOT re-credited.
        """
        uid      = str(uid)
        task_id  = str(task_id)
        reward_f = float(reward)
        conn = self._conn()
        self._ensure_svrp_transfer_table(conn)
        with _db_lock:
            # Ensure claims table
            # Composite PK (uid, task_id) prevents cross-user ID collisions.
            # Daily task IDs are timestamp+random with limited entropy; using
            # only task_id as PK would cause one user's claim to block another.
            conn.execute('''
                CREATE TABLE IF NOT EXISTS svrp_task_claims (
                    uid        TEXT NOT NULL,
                    task_id    TEXT NOT NULL,
                    reward     REAL NOT NULL,
                    claimed_at TEXT NOT NULL,
                    PRIMARY KEY (uid, task_id)
                )
            ''')
            conn.execute('SAVEPOINT claim_task')
            try:
                cur = conn.execute(
                    'INSERT OR IGNORE INTO svrp_task_claims '
                    '(uid, task_id, reward, claimed_at) VALUES (?, ?, ?, ?)',
                    (uid, task_id, reward_f,
                     __import__('datetime').datetime.now().isoformat())
                )
                if cur.rowcount == 0:
                    # Validate that the existing record belongs to this uid and
                    # has the same reward amount (guards against task_id reuse).
                    row = conn.execute(
                        'SELECT uid, reward FROM svrp_task_claims WHERE uid=? AND task_id=?',
                        (uid, task_id)
                    ).fetchone()
                    conn.execute('RELEASE claim_task')
                    if row and row[0] == uid:
                        return 'already_claimed'  # idempotent replay for this user
                    # uid mismatch or missing (should not happen) — treat as error
                    raise RuntimeError(f'claim record uid mismatch: expected {uid}')
                # Credit wallet in the same savepoint
                conn.execute(
                    'INSERT OR IGNORE INTO svrp_wallet_balance '
                    '(uid, frozen_balance, total_earned, total_used, '
                    ' wagering_required, wagering_completed) '
                    'VALUES (?, 0, 0, 0, 3, 0)',
                    (uid,)
                )
                conn.execute(
                    'UPDATE svrp_wallet_balance '
                    'SET frozen_balance = frozen_balance + ?, '
                    '    total_earned   = total_earned   + ? '
                    'WHERE uid = ?',
                    (reward_f, reward_f, uid)
                )
                conn.execute('RELEASE claim_task')
                conn.commit()
                return 'claimed'
            except Exception:
                try:
                    conn.execute('ROLLBACK TO claim_task')
                    conn.execute('RELEASE claim_task')
                except Exception:
                    pass
                raise

    def migrate_svrp_wallets_from_csv(self, rows):
        """Idempotent one-time backfill: INSERT OR IGNORE each CSV wallet row.

        Called at module load.  Existing SQLite rows are not overwritten
        (INSERT OR IGNORE) so any mutations applied via upsert_svrp_wallet_balance
        after the initial backfill are never silently reverted.
        """
        conn = self._conn()
        self._ensure_svrp_transfer_table(conn)
        with _db_lock:
            for row in rows:
                uid = str(row.get('telegram_id', '') or '')
                if not uid:
                    continue
                conn.execute(
                    'INSERT OR IGNORE INTO svrp_wallet_balance '
                    '(uid, frozen_balance, total_earned, total_used, '
                    ' wagering_required, wagering_completed) '
                    'VALUES (?, ?, ?, ?, ?, ?)',
                    (uid,
                     float(row.get('balance', 0) or 0),
                     float(row.get('total_earned', 0) or 0),
                     float(row.get('total_used', 0) or 0),
                     int(row.get('wagering_required', 3) or 3),
                     int(row.get('wagering_completed', 0) or 0))
                )
            conn.commit()

    def get_outstanding_debited_transfer(self, uid):
        """Return the transfer_id of any 'debited' transfer for uid, or None.

        Used to enforce one-outstanding-transfer-per-user: a new transfer must
        not start while one is in the 'debited' (mid-flight) state.
        """
        conn = self._conn()
        self._ensure_svrp_transfer_table(conn)
        row = conn.execute(
            'SELECT transfer_id FROM svrp_transfer_log '
            'WHERE uid = ? AND status = ? LIMIT 1',
            (str(uid), 'debited')
        ).fetchone()
        return row[0] if row else None

    def credit_svrp_balance_for_approval(self, req_id, uid, amount):
        """Approve a recovery request and credit frozen balance atomically.

        State machine (per req_id in svrp_approval_log):
          pending   → complete approval + credit wallet in one SAVEPOINT
          completed → idempotent replay (no re-credit)
          absent    → INSERT + approve + credit in one SAVEPOINT

        Returns (True, new_frozen_balance) on success or idempotent replay.
        Returns (False, msg) if the request was already completed by a different
        uid (ownership violation) or amount mismatch.
        Raises on SQLite error — caller must not update request CSV.
        """
        uid = str(uid)
        amt = float(_money(amount))
        conn = self._conn()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with _db_lock:
            self._ensure_svrp_transfer_table(conn)
            existing = conn.execute(
                'SELECT uid, amount, status FROM svrp_approval_log WHERE req_id = ?',
                (req_id,)
            ).fetchone()

            if existing:
                ex_uid, ex_amt, ex_status = existing[0], existing[1], existing[2]
                if ex_uid != uid:
                    return False, (
                        f'الطلب {req_id} مرتبط بمستخدم مختلف'
                    )
                if ex_status == 'completed':
                    # Idempotent replay — just return current balance
                    bal_row = conn.execute(
                        'SELECT frozen_balance FROM svrp_wallet_balance WHERE uid = ?',
                        (uid,)
                    ).fetchone()
                    return True, float(bal_row[0]) if bal_row else 0.0
                # 'pending' → proceed to SAVEPOINT below

            # Atomic: INSERT OR IGNORE approval record + credit + mark completed
            conn.execute('SAVEPOINT svrp_approve')
            try:
                conn.execute(
                    'INSERT OR IGNORE INTO svrp_approval_log '
                    '(req_id, uid, amount, status, created_at) VALUES (?, ?, ?, ?, ?)',
                    (req_id, uid, amt, 'pending', now)
                )
                # Credit wallet
                conn.execute(
                    'INSERT INTO svrp_wallet_balance (uid, frozen_balance, total_earned) '
                    'VALUES (?, ?, ?) ON CONFLICT(uid) DO UPDATE SET '
                    'frozen_balance = frozen_balance + ?, total_earned = total_earned + ?',
                    (uid, amt, amt, amt, amt)
                )
                # CAS pending→completed
                cas = conn.execute(
                    'UPDATE svrp_approval_log SET status = ? '
                    'WHERE req_id = ? AND status = ?',
                    ('completed', req_id, 'pending')
                )
                if cas.rowcount != 1:
                    conn.execute('ROLLBACK TO SAVEPOINT svrp_approve')
                    conn.execute('RELEASE SAVEPOINT svrp_approve')
                    conn.commit()
                    # Re-check: another concurrent approval beat us
                    re = conn.execute(
                        'SELECT status FROM svrp_approval_log WHERE req_id = ?', (req_id,)
                    ).fetchone()
                    if re and re[0] == 'completed':
                        bal_row = conn.execute(
                            'SELECT frozen_balance FROM svrp_wallet_balance WHERE uid = ?',
                            (uid,)
                        ).fetchone()
                        return True, float(bal_row[0]) if bal_row else 0.0
                    raise RuntimeError(f'Approval CAS failed for req_id={req_id}')
                conn.execute('RELEASE SAVEPOINT svrp_approve')
            except Exception:
                try:
                    conn.execute('ROLLBACK TO SAVEPOINT svrp_approve')
                    conn.execute('RELEASE SAVEPOINT svrp_approve')
                except Exception:
                    pass
                raise
            conn.commit()
            bal_row = conn.execute(
                'SELECT frozen_balance FROM svrp_wallet_balance WHERE uid = ?', (uid,)
            ).fetchone()
            return True, float(bal_row[0]) if bal_row else amt

    def transfer_svrp_frozen_p2p(self, transfer_id, sender_uid, receiver_uid,
                                 amount, unlock_bonus=0.0):
        """Atomic peer-to-peer frozen-balance transfer with unlock bonus.

        In ONE SAVEPOINT:
          - verify sender frozen_balance >= amount + unlock_bonus (SQLite is
            authoritative — not the CSV mirror)
          - debit sender frozen by (amount + unlock_bonus), credit sender
            total_used by unlock_bonus (the 5% unlock rule)
          - credit receiver frozen + total_earned by amount
          - record transfer_id in svrp_p2p_transfer_log (PRIMARY KEY) for
            idempotency — a replay returns True without re-applying.

        Returns (True, sender_frozen_after) or (False, error_msg).
        """
        s_uid, r_uid = str(sender_uid), str(receiver_uid)
        amt = float(_money(amount))
        bonus = float(_money(unlock_bonus))
        if amt <= 0 or bonus < 0:
            return False, 'المبلغ غير صالح'
        conn = self._conn()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with _db_lock:
            conn.execute(
                'CREATE TABLE IF NOT EXISTS svrp_p2p_transfer_log ('
                ' transfer_id TEXT PRIMARY KEY, sender_uid TEXT, receiver_uid TEXT,'
                ' amount REAL, unlock_bonus REAL, created_at TEXT)'
            )
            existing = conn.execute(
                'SELECT sender_uid FROM svrp_p2p_transfer_log WHERE transfer_id = ?',
                (transfer_id,)).fetchone()
            if existing:
                bal = conn.execute(
                    'SELECT frozen_balance FROM svrp_wallet_balance WHERE uid = ?',
                    (s_uid,)).fetchone()
                return True, float(bal[0]) if bal else 0.0
            conn.execute('SAVEPOINT svrp_p2p')
            try:
                for u in (s_uid, r_uid):
                    conn.execute(
                        'INSERT OR IGNORE INTO svrp_wallet_balance '
                        '(uid, frozen_balance, total_earned, total_used, '
                        ' wagering_required, wagering_completed) '
                        'VALUES (?, 0, 0, 0, 3, 0)', (u,))
                res = conn.execute(
                    'UPDATE svrp_wallet_balance SET '
                    'frozen_balance = frozen_balance - ?, '
                    'total_used = total_used + ? '
                    'WHERE uid = ? AND frozen_balance >= ?',
                    (amt + bonus, bonus, s_uid, amt + bonus))
                if res.rowcount != 1:
                    conn.execute('ROLLBACK TO SAVEPOINT svrp_p2p')
                    conn.execute('RELEASE SAVEPOINT svrp_p2p')
                    conn.commit()
                    return False, 'الرصيد المجمد غير كافٍ'
                conn.execute(
                    'UPDATE svrp_wallet_balance SET '
                    'frozen_balance = frozen_balance + ?, '
                    'total_earned = total_earned + ? WHERE uid = ?',
                    (amt, amt, r_uid))
                conn.execute(
                    'INSERT INTO svrp_p2p_transfer_log '
                    '(transfer_id, sender_uid, receiver_uid, amount, unlock_bonus, created_at) '
                    'VALUES (?, ?, ?, ?, ?, ?)',
                    (transfer_id, s_uid, r_uid, amt, bonus, now))
                conn.execute('RELEASE SAVEPOINT svrp_p2p')
            except Exception:
                try:
                    conn.execute('ROLLBACK TO SAVEPOINT svrp_p2p')
                    conn.execute('RELEASE SAVEPOINT svrp_p2p')
                except Exception:
                    pass
                raise
            conn.commit()
            bal = conn.execute(
                'SELECT frozen_balance FROM svrp_wallet_balance WHERE uid = ?',
                (s_uid,)).fetchone()
            return True, float(bal[0]) if bal else 0.0

    def debit_svrp_balance_for_transfer(self, transfer_id, uid, amount):
        """Debit frozen balance and CAS transfer pending→debited atomically.

        Both the wallet debit and the state transition are committed in a single
        SAVEPOINT — no cross-store inconsistency, no csv_debited flag needed.

        Returns True on success.
        Returns False if transfer not in 'pending' state or uid mismatch.
        Raises if balance is insufficient or SQLite fails.
        """
        uid = str(uid)
        amt = float(_money(amount))
        conn = self._conn()
        with _db_lock:
            self._ensure_svrp_transfer_table(conn)
            conn.execute('SAVEPOINT svrp_debit')
            try:
                # Debit wallet (fail if balance insufficient)
                res = conn.execute(
                    'UPDATE svrp_wallet_balance '
                    'SET frozen_balance = frozen_balance - ?, '
                    '    total_used     = total_used     + ? '
                    'WHERE uid = ? AND frozen_balance >= ? - 0.0001',
                    (amt, amt, uid, amt)
                )
                if res.rowcount != 1:
                    # Either uid doesn't exist in wallet or insufficient balance
                    bal_row = conn.execute(
                        'SELECT frozen_balance FROM svrp_wallet_balance WHERE uid = ?',
                        (uid,)
                    ).fetchone()
                    cur_bal = float(bal_row[0]) if bal_row else 0.0
                    conn.execute('ROLLBACK TO SAVEPOINT svrp_debit')
                    conn.execute('RELEASE SAVEPOINT svrp_debit')
                    conn.commit()
                    if cur_bal < amt:
                        raise ValueError(
                            f'رصيد SVRP غير كافٍ: المتاح {cur_bal:.2f}, '
                            f'المطلوب {amt:.2f}'
                        )
                    raise RuntimeError(
                        f'Wallet debit UPDATE matched 0 rows for uid={uid}'
                    )
                # CAS: pending → debited
                cas = conn.execute(
                    'UPDATE svrp_transfer_log '
                    'SET status = ?, amount = ? '
                    'WHERE transfer_id = ? AND uid = ? AND status = ?',
                    ('debited', amt, transfer_id, uid, 'pending')
                )
                if cas.rowcount != 1:
                    conn.execute('ROLLBACK TO SAVEPOINT svrp_debit')
                    conn.execute('RELEASE SAVEPOINT svrp_debit')
                    conn.commit()
                    return False  # transfer not in pending state or wrong uid
                conn.execute('RELEASE SAVEPOINT svrp_debit')
            except Exception:
                try:
                    conn.execute('ROLLBACK TO SAVEPOINT svrp_debit')
                    conn.execute('RELEASE SAVEPOINT svrp_debit')
                except Exception:
                    pass
                raise
            conn.commit()
            return True

    def create_svrp_transfer(self, transfer_id, uid):
        """Reserve a slot in the outbox with status='pending' and amount=0.

        The actual amount is committed atomically when the debit completes via
        mark_svrp_transfer_debited().  Using 0 as a placeholder prevents the
        full-balance-transfer bug where parsed_amount is None at creation time.

        Returns True if the row was inserted, False if the key already existed
        (caller should treat False as a possible concurrent-request collision
        and return an appropriate error rather than proceeding with a debit).
        """
        conn = self._conn()
        with _db_lock:
            self._ensure_svrp_transfer_table(conn)
            result = conn.execute(
                'INSERT OR IGNORE INTO svrp_transfer_log '
                '(transfer_id, uid, amount, status, created_at) VALUES (?, ?, 0, ?, ?)',
                (transfer_id, str(uid), 'pending',
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )
            conn.commit()
            return result.rowcount == 1  # False → key already existed

    def mark_svrp_transfer_debited(self, transfer_id, uid,
                                   actual_amount, pre_debit_svrp_balance):
        """CAS: pending → debited, storing the final amount and pre-debit CSV balance.

        pre_debit_svrp_balance is the SVRP wallet balance read BEFORE the CSV
        debit.  It is stored so that crash-recovery can compare the current CSV
        balance against the expected post-debit balance and determine whether
        the CSV debit actually occurred.

        Returns True  if exactly one row matched (uid AND status='pending').
        Returns False if the row is missing, owned by a different uid, or
        already past 'pending' — the caller must not proceed with a game credit
        or CSV debit.
        """
        conn = self._conn()
        with _db_lock:
            result = conn.execute(
                'UPDATE svrp_transfer_log '
                'SET status = ?, amount = ?, pre_debit_svrp_balance = ? '
                'WHERE transfer_id = ? AND uid = ? AND status = ?',
                ('debited', float(actual_amount), float(pre_debit_svrp_balance),
                 transfer_id, str(uid), 'pending')
            )
            conn.commit()
            return result.rowcount == 1

    def mark_svrp_transfer_csv_debited(self, transfer_id, uid):
        """Mark csv_debited=1 on the outbox record.

        Called inside svrp_lock() immediately after use_credits() succeeds so
        that crash-recovery can determine whether the CSV debit occurred without
        relying on balance comparisons (which are unsafe under concurrent SVRP
        mutations).  Requires uid match.  Returns True if one row was updated.
        """
        conn = self._conn()
        with _db_lock:
            result = conn.execute(
                'UPDATE svrp_transfer_log SET csv_debited = 1 '
                'WHERE transfer_id = ? AND uid = ?',
                (transfer_id, str(uid))
            )
            conn.commit()
            return result.rowcount == 1

    def mark_svrp_transfer_status(self, transfer_id, uid, status):
        """Set status unconditionally (for rolled_back / terminal states).
        Requires uid match to prevent cross-user mutation.
        """
        conn = self._conn()
        with _db_lock:
            conn.execute(
                'UPDATE svrp_transfer_log SET status = ? '
                'WHERE transfer_id = ? AND uid = ?',
                (status, transfer_id, str(uid))
            )
            conn.commit()

    def get_svrp_transfer(self, transfer_id):
        """Return the outbox record dict (all columns), or None if not found."""
        conn = self._conn()
        self._ensure_svrp_transfer_table(conn)
        row = conn.execute(
            'SELECT * FROM svrp_transfer_log WHERE transfer_id = ?', (transfer_id,)
        ).fetchone()
        return dict(row) if row else None

    def add_balance(self, user_id, amount, idempotency_key=None):
        """Add to game balance atomically. Returns new balance.

        idempotency_key accepted for API compatibility but is not used here —
        SVRP-specific idempotency is handled by add_balance_for_svrp_transfer().
        All normal credits (deposits, payouts, refunds, admin adds) use this method.
        """
        uid = str(user_id)
        amt = _money(amount)
        conn = self._conn()
        with _db_lock:
            conn.execute(
                'INSERT INTO users (telegram_id, game_balance) VALUES (?, ?) '
                'ON CONFLICT(telegram_id) DO UPDATE SET game_balance = game_balance + ?',
                (uid, float(amt), float(amt))
            )
            conn.commit()
            row = conn.execute(
                'SELECT game_balance FROM users WHERE telegram_id = ?', (uid,)
            ).fetchone()
            return _money_float(row[0]) if row and row[0] is not None else 0.0

    def add_balance_for_svrp_transfer(self, user_id, amount, transfer_id):
        """Credit game balance exactly once for an SVRP transfer.

        Uses the STATUS column in svrp_transfer_log for idempotency —
        no separate INSERT means no key-collision with the pre-existing outbox row.

        Rules:
          status == 'debited'   → credit game_balance + CAS to 'completed' (atomically)
          status == 'completed' → replay; return current balance without re-crediting
          anything else         → raises ValueError (wrong state; caller should abort)
          uid mismatch          → raises PermissionError (cross-user security check)
          row missing           → raises ValueError

        All SQLite errors other than the handled states propagate so the endpoint's
        compensating rollback can run.
        """
        uid = str(user_id)
        amt = _money(amount)
        conn = self._conn()
        with _db_lock:
            row = conn.execute(
                'SELECT status, uid, amount FROM svrp_transfer_log WHERE transfer_id = ?',
                (transfer_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f'SVRP outbox record not found: transfer_id={transfer_id}')
            db_status, db_uid, db_amount = row[0], row[1], row[2]
            if db_uid != uid:
                raise PermissionError(
                    f'Transfer {transfer_id} belongs to uid={db_uid}, not {uid}'
                )
            if db_status == 'completed':
                # Idempotent replay — return current balance without crediting again
                bal = conn.execute(
                    'SELECT game_balance FROM users WHERE telegram_id = ?', (uid,)
                ).fetchone()
                return _money_float(bal[0]) if bal and bal[0] is not None else 0.0
            if db_status != 'debited':
                raise ValueError(
                    f'Transfer {transfer_id} is in state={db_status!r}; '
                    f'expected "debited" to apply game credit'
                )
            # Atomically credit + CAS debited→completed in a single SAVEPOINT.
            # Verifying rowcount before RELEASE ensures both statements committed
            # together or neither did — preventing a crash between them from
            # crediting the game balance without marking 'completed'.
            conn.execute('SAVEPOINT svrp_credit')
            try:
                conn.execute(
                    'INSERT INTO users (telegram_id, game_balance) VALUES (?, ?) '
                    'ON CONFLICT(telegram_id) '
                    'DO UPDATE SET game_balance = game_balance + ?',
                    (uid, float(amt), float(amt))
                )
                cas_result = conn.execute(
                    'UPDATE svrp_transfer_log SET status = ? '
                    'WHERE transfer_id = ? AND status = ?',
                    ('completed', transfer_id, 'debited')
                )
                if cas_result.rowcount != 1:
                    # Another request already transitioned this record — roll back
                    # the credit and let the caller decide (replay vs. error).
                    conn.execute('ROLLBACK TO SAVEPOINT svrp_credit')
                    conn.execute('RELEASE SAVEPOINT svrp_credit')
                    conn.commit()
                    # Re-read status to determine whether it is now 'completed'
                    re_row = conn.execute(
                        'SELECT status FROM svrp_transfer_log WHERE transfer_id = ?',
                        (transfer_id,)
                    ).fetchone()
                    re_status = re_row[0] if re_row else None
                    if re_status == 'completed':
                        # Race was won by another request — idempotent replay
                        bal = conn.execute(
                            'SELECT game_balance FROM users WHERE telegram_id = ?',
                            (uid,)
                        ).fetchone()
                        return _money_float(bal[0]) if bal and bal[0] is not None else 0.0
                    raise RuntimeError(
                        f'SVRP credit CAS failed: status={re_status!r}'
                    )
                conn.execute('RELEASE SAVEPOINT svrp_credit')
            except Exception:
                try:
                    conn.execute('ROLLBACK TO SAVEPOINT svrp_credit')
                    conn.execute('RELEASE SAVEPOINT svrp_credit')
                except Exception:
                    pass
                raise
            conn.commit()
            bal = conn.execute(
                'SELECT game_balance FROM users WHERE telegram_id = ?', (uid,)
            ).fetchone()
            return _money_float(bal[0]) if bal and bal[0] is not None else 0.0

    def deduct_balance(self, user_id, amount):
        """Deduct from balance (atomic, Decimal precision). Returns (success, new_balance)."""
        uid = str(user_id)
        amt = _money(amount)
        conn = self._conn()
        with _db_lock:
            row = conn.execute(
                'SELECT game_balance FROM users WHERE telegram_id = ?', (uid,)
            ).fetchone()
            current = _money(row[0]) if row and row[0] is not None else Decimal('0.00')
            if current < amt:
                return False, _money_float(current)
            conn.execute(
                'UPDATE users SET game_balance = game_balance - ? WHERE telegram_id = ?',
                (float(amt), uid)
            )
            conn.commit()
            return True, _money_float(current - amt)

    def set_balance(self, user_id, amount):
        """Set balance directly (admin override, Decimal precision)."""
        uid = str(user_id)
        amt = _money(amount)
        conn = self._conn()
        with _db_lock:
            conn.execute('''
                INSERT INTO users (telegram_id, game_balance) VALUES (?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET game_balance = ?
            ''', (uid, float(amt), float(amt)))
            conn.commit()
            return _money_float(amt)

    def get_idempotency_record(self, uid, request_id):
        """Return the persisted response JSON for a completed request, or None.

        Safe to call outside a transaction; read-only.
        """
        if not request_id:
            return None
        conn = self._conn()
        with _db_lock:
            row = conn.execute(
                'SELECT response_json FROM game_idempotency WHERE uid=? AND request_id=?',
                (str(uid), str(request_id))
            ).fetchone()
        if row:
            import json as _json
            try:
                return _json.loads(row[0])
            except Exception:
                return None
        return None

    def round_settle(self, user_id, bet_amount, payout):
        """Settle a complete round in ONE atomic ACID transaction.

        Combines bet deduction + win payout into a single atomic update.
        Prevents money loss if process crashes between the two operations.
        Returns (success, final_balance).

        bet_amount: the wagered amount (already validated server-side).
        payout: the gross payout won (0 if loss).
        net_delta = payout - bet_amount applied atomically.
        """
        uid = str(user_id)
        bet = _money(bet_amount)
        win = _money(payout)
        net = win - bet  # Decimal arithmetic, no float drift
        conn = self._conn()
        with _db_lock:
            conn.execute('BEGIN')
            try:
                row = conn.execute(
                    'SELECT game_balance FROM users WHERE telegram_id = ?', (uid,)
                ).fetchone()
                current = _money(row[0]) if row and row[0] is not None else Decimal('0.00')
                if net < 0 and current < abs(net):
                    conn.execute('ROLLBACK')
                    return False, _money_float(current)
                new_bal = current + net
                conn.execute('''
                    INSERT INTO users (telegram_id, game_balance) VALUES (?, ?)
                    ON CONFLICT(telegram_id) DO UPDATE SET game_balance = ?
                ''', (uid, _money_float(new_bal), _money_float(new_bal)))
                conn.commit()
                return True, _money_float(new_bal)
            except Exception:
                try:
                    conn.execute('ROLLBACK')
                except Exception:
                    pass
                raise

    def settle_with_idempotency(self, user_id, bet_amount, payout, request_id, response_template):
        """Atomic: settle round + record idempotency in ONE SQLite transaction.

        On retry with the same (uid, request_id), returns the previously stored
        response without re-executing settlement (idempotent replay).

        response_template: dict of game-specific fields (WITHOUT balance_after).
          balance_after is computed inside the transaction and added before storage,
          so the stored response always has the correct post-settlement balance.

        Returns (success, stored_result, cached_response_or_None):
          - cached_response is not None → idempotent replay, skip processing
          - success is False → insufficient funds, no settlement, no record stored
          - stored_result has balance_after filled in from the actual settlement
        """
        import json as _json
        uid = str(user_id)
        bet = _money(bet_amount)
        win = _money(payout)
        net = win - bet
        conn = self._conn()
        with _db_lock:
            conn.execute('BEGIN')
            try:
                # 1. Idempotency check (under lock, inside transaction — race-free)
                if request_id:
                    existing = conn.execute(
                        'SELECT response_json FROM game_idempotency WHERE uid=? AND request_id=?',
                        (uid, str(request_id))
                    ).fetchone()
                    if existing:
                        conn.execute('ROLLBACK')
                        try:
                            return True, None, _json.loads(existing[0])
                        except Exception:
                            return True, None, {}

                # 2. Balance check
                row = conn.execute(
                    'SELECT game_balance FROM users WHERE telegram_id = ?', (uid,)
                ).fetchone()
                current = _money(row[0]) if row and row[0] is not None else Decimal('0.00')
                if net < 0 and current < abs(net):
                    conn.execute('ROLLBACK')
                    return False, None, None

                # 3. Apply balance change
                new_bal = current + net
                new_bal_f = _money_float(new_bal)
                conn.execute('''
                    INSERT INTO users (telegram_id, game_balance) VALUES (?, ?)
                    ON CONFLICT(telegram_id) DO UPDATE SET game_balance = ?
                ''', (uid, new_bal_f, new_bal_f))

                # 4. Build complete response with actual balance_after, store atomically
                full_response = dict(response_template)
                full_response['balance_after'] = new_bal_f
                if request_id:
                    conn.execute('''
                        INSERT OR IGNORE INTO game_idempotency (uid, request_id, response_json, created_at)
                        VALUES (?, ?, ?, ?)
                    ''', (uid, str(request_id), _json.dumps(full_response), time.time()))

                conn.commit()
                return True, full_response, None
            except Exception:
                try:
                    conn.execute('ROLLBACK')
                except Exception:
                    pass
                raise

    def credit_with_idempotency(self, user_id, amount, request_id, response_template):
        """Credit-only atomic operation with idempotency (for pre-deducted mines cashout).

        Same as settle_with_idempotency but deducts nothing (net = +amount).
        balance_after is computed inside the transaction and stored in the record.
        Returns (success, stored_result, cached_response_or_None).
        """
        import json as _json
        uid = str(user_id)
        amt = _money(amount)
        conn = self._conn()
        with _db_lock:
            conn.execute('BEGIN')
            try:
                if request_id:
                    existing = conn.execute(
                        'SELECT response_json FROM game_idempotency WHERE uid=? AND request_id=?',
                        (uid, str(request_id))
                    ).fetchone()
                    if existing:
                        conn.execute('ROLLBACK')
                        try:
                            return True, None, _json.loads(existing[0])
                        except Exception:
                            return True, None, {}

                row = conn.execute(
                    'SELECT game_balance FROM users WHERE telegram_id = ?', (uid,)
                ).fetchone()
                current = _money(row[0]) if row and row[0] is not None else Decimal('0.00')
                new_bal = current + amt
                new_bal_f = _money_float(new_bal)
                conn.execute('''
                    INSERT INTO users (telegram_id, game_balance) VALUES (?, ?)
                    ON CONFLICT(telegram_id) DO UPDATE SET game_balance = ?
                ''', (uid, new_bal_f, new_bal_f))

                full_response = dict(response_template)
                full_response['balance_after'] = new_bal_f
                if request_id:
                    conn.execute('''
                        INSERT OR IGNORE INTO game_idempotency (uid, request_id, response_json, created_at)
                        VALUES (?, ?, ?, ?)
                    ''', (uid, str(request_id), _json.dumps(full_response), time.time()))
                conn.commit()
                return True, full_response, None
            except Exception:
                try:
                    conn.execute('ROLLBACK')
                except Exception:
                    pass
                raise

    def prune_idempotency_records(self, max_age_seconds=86400):
        """Delete idempotency records older than max_age_seconds (default 24 h).

        Call periodically (e.g. on startup) to prevent unbounded growth.
        """
        cutoff = time.time() - max_age_seconds
        conn = self._conn()
        with _db_lock:
            conn.execute('DELETE FROM game_idempotency WHERE created_at < ?', (cutoff,))
            conn.commit()

    # ===== Snatch Session State Machine =====

    _SNATCH_COLS = ('session_id', 'uid', 'bet_amount', 'spin_request_id',
                    'created_at', 'status', 'score', 'payout', 'settled_at')

    def snatch_create_session(self, session_id, uid, bet_amount,
                               spin_request_id, created_at, server_payout=None):
        """Insert a new 'intent' session row into vex_games.db (idempotent INSERT OR IGNORE).

        server_payout: the server-determined payout amount computed at spin time.
        Stored immediately so /api/snatch/end and the sweep can credit it without
        ever trusting a client-supplied score.
        """
        conn = self._conn()
        with _db_lock:
            conn.execute(
                "INSERT OR IGNORE INTO snatch_sessions "
                "(session_id, uid, bet_amount, spin_request_id, created_at, status, payout) "
                "VALUES (?, ?, ?, ?, ?, 'intent', ?)",
                (session_id, str(uid), float(bet_amount), spin_request_id,
                 created_at, server_payout)
            )
            conn.commit()

    def snatch_get_session(self, session_id):
        """Return session as a dict, or None if not found."""
        conn = self._conn()
        row = conn.execute(
            "SELECT session_id, uid, bet_amount, spin_request_id, created_at, "
            "status, score, payout, settled_at FROM snatch_sessions WHERE session_id=?",
            (session_id,)
        ).fetchone()
        return dict(zip(self._SNATCH_COLS, row)) if row else None

    def snatch_cas_status(self, session_id, old_status, new_status, **kwargs):
        """Atomic compare-and-swap status transition.

        Optional kwargs: score, payout, settled_at — updated in the same statement.
        Returns rowcount: 1 = this caller won the race; 0 = lost (status already changed).
        """
        conn = self._conn()
        set_parts = ['status=?']
        params = [new_status]
        for k in ('score', 'payout', 'settled_at'):
            if k in kwargs:
                set_parts.append(f'{k}=?')
                params.append(kwargs[k])
        params.extend([session_id, old_status])
        with _db_lock:
            rowcount = conn.execute(
                f"UPDATE snatch_sessions SET {', '.join(set_parts)} "
                f"WHERE session_id=? AND status=?",
                params
            ).rowcount
            conn.commit()
        return rowcount

    def snatch_delete_session(self, session_id):
        """Delete a session row (used to remove ghost intent rows)."""
        conn = self._conn()
        with _db_lock:
            conn.execute("DELETE FROM snatch_sessions WHERE session_id=?", (session_id,))
            conn.commit()

    def snatch_get_by_status(self, status, created_before=None):
        """Return a list of session dicts matching the given status.

        Optionally filter to rows older than ``created_before`` (UNIX timestamp).
        """
        conn = self._conn()
        cols = ', '.join(self._SNATCH_COLS)
        if created_before is not None:
            rows = conn.execute(
                f"SELECT {cols} FROM snatch_sessions "
                f"WHERE status=? AND created_at < ?",
                (status, created_before)
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {cols} FROM snatch_sessions WHERE status=?", (status,)
            ).fetchall()
        return [dict(zip(self._SNATCH_COLS, r)) for r in rows]

    # ===== Session Logging =====

    def log_session(self, session_data):
        """Log a game session."""
        conn = self._conn()
        with _db_lock:
            conn.execute('''
                INSERT INTO game_sessions 
                (session_id, game_id, user_id, bet_amount, payout, result,
                 multiplier, balance_before, balance_after, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_data.get('session_id', ''),
                session_data.get('game_id', ''),
                session_data.get('user_id', ''),
                float(session_data.get('bet_amount', 0) or 0),
                float(session_data.get('payout', 0) or 0),
                session_data.get('result', ''),
                float(session_data.get('multiplier', 0) or 0),
                float(session_data.get('balance_before', 0) or 0),
                float(session_data.get('balance_after', 0) or 0),
                session_data.get('timestamp', datetime.now().isoformat())
            ))
            conn.commit()

    def get_recent_sessions(self, limit=20):
        """Get recent game sessions."""
        conn = self._conn()
        rows = conn.execute(
            'SELECT * FROM game_sessions ORDER BY id DESC LIMIT ?', (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_user_sessions(self, user_id, limit=50):
        """Get sessions for a specific user."""
        conn = self._conn()
        rows = conn.execute(
            'SELECT * FROM game_sessions WHERE user_id = ? ORDER BY id DESC LIMIT ?',
            (str(user_id), limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_leaderboard(self, limit=10):
        """Get top players by profit."""
        conn = self._conn()
        rows = conn.execute('''
            SELECT user_id,
                   SUM(bet_amount) as total_bet,
                   SUM(payout) as total_payout,
                   COUNT(*) as games,
                   SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                   (SUM(payout) - SUM(bet_amount)) as profit
            FROM game_sessions
            GROUP BY user_id
            ORDER BY profit DESC
            LIMIT ?
        ''', (limit,)).fetchall()
        # Join with user names
        result = []
        for r in rows:
            d = dict(r)
            urow = conn.execute(
                'SELECT name FROM users WHERE telegram_id = ?', (d['user_id'],)
            ).fetchone()
            d['name'] = urow[0] if urow else ''
            d['win_rate'] = round(d['wins'] / max(d['games'], 1) * 100, 1)
            result.append(d)
        return result

    def get_platform_stats(self):
        """Get aggregate platform statistics."""
        conn = self._conn()
        row = conn.execute('''
            SELECT 
                COUNT(DISTINCT user_id) as active_players,
                COUNT(*) as total_rounds,
                COALESCE(SUM(bet_amount), 0) as total_wagered,
                COALESCE(SUM(payout), 0) as total_paid_out,
                COALESCE(SUM(bet_amount) - SUM(payout), 0) as net_profit,
                COALESCE(SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END), 0) as total_wins
            FROM game_sessions
        ''').fetchone()
        if row:
            d = dict(row)
            d['platform_edge'] = round(
                (d['net_profit'] / max(d['total_wagered'], 1)) * 100, 2
            ) if d['total_wagered'] > 0 else 0
            d['win_rate'] = round(
                (d['total_wins'] / max(d['total_rounds'], 1)) * 100, 1
            ) if d['total_rounds'] > 0 else 0
            return d
        return {}

    # ===== Sync back to CSV (for backward compatibility) =====

    def sync_to_csv(self):
        """Sync SQLite balances back to users.csv (for backward compat with bot)."""
        csv_path = os.path.join(BASE_DIR, 'users.csv')
        if not os.path.exists(csv_path):
            return
        conn = self._conn()
        try:
            # Read existing CSV
            with open(csv_path, 'r', encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                rows = list(reader)

            # Build balance map from SQLite
            bal_rows = conn.execute(
                'SELECT telegram_id, game_balance FROM users'
            ).fetchall()
            bal_map = {r[0]: r[1] for r in bal_rows}

            # Update rows with SQLite balances
            for row in rows:
                tid = row.get('telegram_id', '')
                if tid in bal_map:
                    try:
                        row['game_balance'] = f"{float(bal_map[tid]):.2f}"
                    except (ValueError, TypeError):
                        row['game_balance'] = "0.00"

            # Atomic write
            import tempfile
            fd, tmp_path = tempfile.mkstemp(dir=BASE_DIR, suffix='.tmp')
            with os.fdopen(fd, 'w', newline='', encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in fieldnames})
            os.replace(tmp_path, csv_path)
        except Exception as e:
            print(f"CSV sync error: {e}")



# ═══════════════════════════════════════════════════════════════════════════
# RBAC — Role-Based Access Control
# ═══════════════════════════════════════════════════════════════════════════

# Permission bits — all keys a role JSON may contain
ROLE_PERMISSIONS = {
    'super_admin': {
        'approve_deposits': True, 'reject_deposits': True,
        'approve_withdrawals': True, 'reject_withdrawals': True,
        'ban_users': True, 'unban_users': True,
        'manage_admins': True, 'manage_bots': True,
        'send_broadcast': True, 'view_financial': True,
        'manage_games': True, 'view_statistics': True,
        'manage_companies': True, 'manage_settings': True,
    },
    'finance_admin': {
        'approve_deposits': True, 'reject_deposits': True,
        'approve_withdrawals': True, 'reject_withdrawals': True,
        'view_financial': True, 'view_statistics': True,
    },
    'support_admin': {
        'view_financial': True, 'ban_users': False,
        'send_broadcast': False,
    },
    'game_admin': {
        'manage_games': True, 'view_statistics': True,
    },
    'broadcast_admin': {
        'send_broadcast': True,
    },
}


def get_admin_role(uid: str) -> dict:
    """Return {'role': str, 'permissions': dict} for a given admin UID.
    Falls back to 'super_admin' for UIDs in ADMIN_IDS env var.
    """
    conn = _get_conn()
    try:
        row = conn.execute(
            'SELECT role, permissions FROM admin_roles WHERE uid=?', (str(uid),)
        ).fetchone()
        if row:
            import json as _json
            perms = {}
            try:
                perms = _json.loads(row['permissions'] or '{}')
            except Exception:
                pass
            return {'role': row['role'], 'permissions': perms}
        # Not in DB — check env ADMIN_IDS
        env_admins = [a.strip() for a in os.getenv('ADMIN_USER_IDS', '').split(',') if a.strip()]
        if str(uid) in env_admins:
            return {'role': 'super_admin', 'permissions': ROLE_PERMISSIONS['super_admin']}
        return {'role': None, 'permissions': {}}
    finally:
        conn.close()


def set_admin_role(uid: str, role: str, created_by: str = 'system',
                   extra_permissions: dict = None) -> bool:
    """Create or update an admin's role in the DB."""
    import json as _json
    if role not in ROLE_PERMISSIONS:
        return False
    perms = dict(ROLE_PERMISSIONS[role])
    if extra_permissions:
        perms.update(extra_permissions)
    conn = _get_conn()
    try:
        conn.execute('''
            INSERT INTO admin_roles (uid, role, permissions, created_at, created_by)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(uid) DO UPDATE SET role=excluded.role,
                permissions=excluded.permissions,
                created_at=excluded.created_at,
                created_by=excluded.created_by
        ''', (str(uid), role, _json.dumps(perms),
              datetime.now().strftime('%Y-%m-%d %H:%M:%S'), str(created_by)))
        conn.commit()
        return True
    except Exception as e:
        print(f"set_admin_role error: {e}")
        return False
    finally:
        conn.close()


def has_permission(uid: str, permission: str) -> bool:
    """Return True if the admin has the given permission."""
    role_data = get_admin_role(uid)
    return bool(role_data['permissions'].get(permission, False))


def log_admin_action(uid: str, action: str, target: str = '',
                     details: str = '', ip: str = '') -> None:
    """Append a row to the admin_audit_log table."""
    conn = _get_conn()
    try:
        conn.execute('''
            INSERT INTO admin_audit_log (uid, action, target, details, ip, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (str(uid), action, str(target), str(details), str(ip),
              datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
    except Exception as e:
        print(f"log_admin_action error: {e}")
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# Active Game Sessions — durable real-time session state
# ═══════════════════════════════════════════════════════════════════════════

# Default TTLs per game (seconds)
GAME_SESSION_TTL = {
    'mines':  600,   # 10 minutes
    'plinko': 300,   # 5 minutes
    'snatch': 120,   # 2 minutes
    'wheel':  180,   # 3 minutes
    'crash':  60,
    'aviator': 60,
}


def get_active_game_session(user_id: str, game: str) -> dict | None:
    """Return the active session dict or None if expired/absent."""
    conn = _get_conn()
    try:
        row = conn.execute('''
            SELECT session_data, bet_amount, created_at, expires_at
            FROM active_game_sessions
            WHERE user_id=? AND game=? AND expires_at > ?
        ''', (str(user_id), game, time.time())).fetchone()
        if row:
            import json as _json
            try:
                data = _json.loads(row['session_data'])
            except Exception:
                data = {}
            data['_bet'] = row['bet_amount']
            data['_created_at'] = row['created_at']
            return data
        return None
    finally:
        conn.close()


def set_active_game_session(user_id: str, game: str, session_data: dict,
                             bet_amount: float, ttl_seconds: int = None) -> None:
    """Upsert a durable game session. Overwrites any existing session for this user+game."""
    import json as _json
    ttl = ttl_seconds or GAME_SESSION_TTL.get(game, 300)
    now = time.time()
    conn = _get_conn()
    try:
        conn.execute('''
            INSERT INTO active_game_sessions
                (user_id, game, session_data, bet_amount, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, game) DO UPDATE SET
                session_data=excluded.session_data,
                bet_amount=excluded.bet_amount,
                expires_at=excluded.expires_at
        ''', (str(user_id), game, _json.dumps(session_data),
              float(bet_amount), now, now + ttl))
        conn.commit()
    finally:
        conn.close()


def delete_active_game_session(user_id: str, game: str) -> None:
    """Remove a game session (on cashout, loss, or manual clear)."""
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM active_game_sessions WHERE user_id=? AND game=?',
                     (str(user_id), game))
        conn.commit()
    finally:
        conn.close()


def cleanup_expired_game_sessions() -> int:
    """Delete sessions past their TTL. Returns count deleted."""
    conn = _get_conn()
    try:
        cur = conn.execute('DELETE FROM active_game_sessions WHERE expires_at <= ?',
                           (time.time(),))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def refund_expired_game_sessions(gdb_instance=None) -> list:
    """Find expired sessions that still have a bet, refund them via credit_with_idempotency.

    Returns list of (user_id, game, bet_amount) that were refunded.
    """
    conn = _get_conn()
    refunded = []
    try:
        rows = conn.execute('''
            SELECT user_id, game, session_data, bet_amount, created_at
            FROM active_game_sessions
            WHERE expires_at <= ?
        ''', (time.time(),)).fetchall()

        for row in rows:
            uid = row['user_id']
            game = row['game']
            bet = float(row['bet_amount'])
            created = row['created_at']
            if bet > 0 and gdb_instance:
                # If the session carries a settle_key, the refund SHARES the
                # idempotency key with settlement — whichever ran first wins,
                # so a settled bet can never be refunded on top (no double-pay).
                req_id = f"refund_expired_{game}_{uid}_{int(created)}"
                try:
                    import json as _json
                    sd = _json.loads(row['session_data'] or '{}')
                    if sd.get('settle_key'):
                        req_id = sd['settle_key']
                except Exception:
                    pass
                try:
                    gdb_instance.credit_with_idempotency(
                        uid, bet, req_id,
                        {'refunded': True, 'reason': 'session_expired', 'game': game}
                    )
                    refunded.append((uid, game, bet))
                    print(f"[session] Refunded expired {game} bet {bet} to {uid}")
                except Exception as e:
                    print(f"[session] Refund error for {uid}/{game}: {e}")

        # Delete all expired
        conn.execute('DELETE FROM active_game_sessions WHERE expires_at <= ?', (time.time(),))
        conn.commit()
    finally:
        conn.close()
    return refunded


# ── Replay-protection nonce store ────────────────────────────────────────────

def check_and_mark_nonce(token_hash: str, user_id: str, device_fp: str = '',
                         ttl: int = 3720) -> bool:
    """Atomically record an initData nonce and enforce cross-device replay protection.

    A Telegram WebApp page sends the SAME initData on every apiFetch call
    within a session (it is set once at page load).  Blocking all repeat uses
    would break any page with more than one API call.  We therefore allow
    same-device repeated use within the TTL, and only block presentation of
    the token from a DIFFERENT device fingerprint.

    Returns True (allow) when:
    - Token is new — recorded now with this device fingerprint.
    - Token was previously recorded with the SAME device fingerprint.
    - No device fingerprint is available on either side (fallback permissive).

    Returns False (block) when:
    - Token was previously recorded with a DIFFERENT device fingerprint
      (cross-device replay attack).

    The nonce is kept for ttl seconds (default 3720 = 1 h + 2-min buffer).
    The device_fp column is added via ALTER TABLE if the DB pre-dates this schema.
    """
    now = time.time()
    conn = _get_conn()
    try:
        # Ensure device_fp column exists (idempotent migration for pre-existing DBs)
        try:
            conn.execute("ALTER TABLE auth_nonces ADD COLUMN device_fp TEXT NOT NULL DEFAULT ''")
            conn.commit()
        except Exception:
            pass  # Column already exists — expected on most runs

        cur = conn.execute(
            'INSERT OR IGNORE INTO auth_nonces'
            ' (token_hash, user_id, device_fp, created_at, expires_at)'
            ' VALUES (?, ?, ?, ?, ?)',
            (token_hash, user_id, device_fp, now, now + ttl),
        )
        conn.commit()
        if cur.rowcount == 1:
            return True  # New token — first use from this device

        # Token already recorded — check device fingerprint
        row = conn.execute(
            'SELECT device_fp FROM auth_nonces WHERE token_hash = ?',
            (token_hash,),
        ).fetchone()
        if not row:
            return True  # Row vanished (expired between INSERT and SELECT) — allow

        stored_fp = row[0] or ''
        # Fail closed: if either fingerprint is missing on a replay, we cannot
        # verify device binding, so we block. An attacker who omits X-Device-FP
        # is denied even if the token was previously stored without a fingerprint.
        if not stored_fp or not device_fp:
            return False
        return stored_fp == device_fp  # True = same device; False = cross-device replay
    finally:
        conn.close()


def cleanup_expired_nonces() -> int:
    """Delete auth_nonces past their TTL.  Returns count deleted."""
    conn = _get_conn()
    try:
        cur = conn.execute('DELETE FROM auth_nonces WHERE expires_at <= ?', (time.time(),))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# Singleton
_gdb = GameDB()

