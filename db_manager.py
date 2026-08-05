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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'vex_games.db')
CSV_ENCODING = 'utf-8-sig'

_db_lock = threading.Lock()


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

    def __init__(self):
        self._local = threading.local()

    def _conn(self):
        """Per-thread connection."""
        if not hasattr(self._local, 'conn'):
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
        return float(row[0]) if row else 0.0

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

    def add_balance(self, user_id, amount):
        """Add to balance (atomic transaction). Returns new balance."""
        uid = str(user_id)
        amt = float(amount)
        conn = self._conn()
        with _db_lock:
            # Upsert user
            conn.execute('''
                INSERT INTO users (telegram_id, game_balance) VALUES (?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET game_balance = game_balance + ?
            ''', (uid, amt, amt))
            conn.commit()
            row = conn.execute(
                'SELECT game_balance FROM users WHERE telegram_id = ?', (uid,)
            ).fetchone()
            return float(row[0]) if row else 0.0

    def deduct_balance(self, user_id, amount):
        """Deduct from balance (atomic). Returns (success, new_balance)."""
        uid = str(user_id)
        amt = float(amount)
        conn = self._conn()
        with _db_lock:
            row = conn.execute(
                'SELECT game_balance FROM users WHERE telegram_id = ?', (uid,)
            ).fetchone()
            current = float(row[0]) if row else 0.0
            if current < amt:
                return False, current
            conn.execute(
                'UPDATE users SET game_balance = game_balance - ? WHERE telegram_id = ?',
                (amt, uid)
            )
            conn.commit()
            return True, current - amt

    def set_balance(self, user_id, amount):
        """Set balance directly (admin override)."""
        uid = str(user_id)
        amt = float(amount)
        conn = self._conn()
        with _db_lock:
            conn.execute('''
                INSERT INTO users (telegram_id, game_balance) VALUES (?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET game_balance = ?
            ''', (uid, amt, amt))
            conn.commit()
            return amt

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
                    row['game_balance'] = f"{bal_map[tid]:.2f}"

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


# Singleton
_gdb = GameDB()
