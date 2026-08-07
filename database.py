"""
database.py — SQLite persistence layer for boterx
Replaces CSV file I/O and in-memory user_states with thread-safe SQLite.
"""
import os
import csv
import sqlite3
import threading
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple, Any

logger = logging.getLogger('boterx.db')

# ---------------------------------------------------------------------------
# DB path from environment or default alongside this file
# ---------------------------------------------------------------------------
DB_PATH = os.environ.get(
    'BOTERX_DB',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'boterx.db')
)

# ---------------------------------------------------------------------------
# Thread-local connection pool
# ---------------------------------------------------------------------------
_thread_local = threading.local()
_write_locks: dict = {}          # per-table write locks
_write_locks_lock = threading.Lock()  # protects _write_locks dict itself
_db_instance = None              # singleton BotDatabase
_instance_lock = threading.Lock()


def _get_table_lock(table: str) -> threading.Lock:
    with _write_locks_lock:
        if table not in _write_locks:
            _write_locks[table] = threading.Lock()
        return _write_locks[table]


def _table_name(filename: str) -> str:
    """Convert 'foo.bar.csv' → 'foo_bar_csv'  (dots→underscores, strip .csv)"""
    base = os.path.basename(filename)
    if base.lower().endswith('.csv'):
        base = base[:-4]
    return base.replace('.', '_').replace('-', '_').replace(' ', '_')


# ---------------------------------------------------------------------------
# BotDatabase
# ---------------------------------------------------------------------------
class BotDatabase:
    """Thread-safe SQLite wrapper for the bot."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._initialized = False
        self._init_lock = threading.Lock()

    # ---- connection management ----------------------------------------

    def _conn(self) -> sqlite3.Connection:
        """Return a per-thread connection, creating it if needed."""
        conn = getattr(_thread_local, 'conn', None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            _thread_local.conn = conn
        return conn

    # ---- bootstrap ----------------------------------------------------

    def _bootstrap(self):
        """Create core tables."""
        conn = self._conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_states (
                user_id    TEXT PRIMARY KEY,
                state      TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_transactions (
                tx_id      TEXT PRIMARY KEY,
                user_id    TEXT NOT NULL,
                tx_type    TEXT NOT NULL,
                amount     TEXT,
                currency   TEXT,
                company    TEXT,
                status     TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
        logger.info("BotDatabase bootstrapped at %s", self.db_path)

    # ---- ensure_initialized (called from init_files) -------------------

    def ensure_initialized(self):
        """Bootstrap DB on first call; optionally run migration if empty."""
        with self._init_lock:
            if self._initialized:
                return
            self._bootstrap()
            self._initialized = True

    # ---- dynamic table management ------------------------------------

    def _table_exists(self, table: str) -> bool:
        cur = self._conn().execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
        return cur.fetchone() is not None

    def _ensure_table(self, table: str, fieldnames: list):
        """CREATE TABLE IF NOT EXISTS with all TEXT columns."""
        if not fieldnames:
            return
        cols = ', '.join(f'"{f}" TEXT' for f in fieldnames)
        sql = f'CREATE TABLE IF NOT EXISTS "{table}" ({cols})'
        lock = _get_table_lock(table)
        with lock:
            conn = self._conn()
            conn.execute(sql)
            # Add any missing columns (for schema evolution)
            cur = conn.execute(f'PRAGMA table_info("{table}")')
            existing = {row[1] for row in cur.fetchall()}
            for f in fieldnames:
                if f not in existing:
                    conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{f}" TEXT')
            conn.commit()

    # ---- user_states --------------------------------------------------

    def set_user_state(self, user_id, state: str):
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO user_states (user_id, state, updated_at) VALUES (?, ?, ?)",
            (str(user_id), state, now)
        )
        conn.commit()

    def get_user_state(self, user_id) -> Optional[str]:
        cur = self._conn().execute(
            "SELECT state FROM user_states WHERE user_id = ?", (str(user_id),)
        )
        row = cur.fetchone()
        return row[0] if row else None

    def del_user_state(self, user_id):
        conn = self._conn()
        conn.execute("DELETE FROM user_states WHERE user_id = ?", (str(user_id),))
        conn.commit()

    def has_user_state(self, user_id) -> bool:
        cur = self._conn().execute(
            "SELECT 1 FROM user_states WHERE user_id = ?", (str(user_id),)
        )
        return cur.fetchone() is not None

    def get_all_user_states(self) -> dict:
        cur = self._conn().execute("SELECT user_id, state FROM user_states")
        return {row[0]: row[1] for row in cur.fetchall()}

    def get_all_user_states_with_timestamps(self) -> list:
        """Return list of (user_id, state, updated_at_iso) for all rows."""
        cur = self._conn().execute(
            "SELECT user_id, state, updated_at FROM user_states"
        )
        return [(row[0], row[1], row[2]) for row in cur.fetchall()]

    # ---- pending_transactions -----------------------------------------

    def record_pending_transaction(
        self, tx_id: str, user_id, tx_type: str,
        amount: str = '', currency: str = '', company: str = ''
    ):
        """Insert a new pending transaction record (idempotent via INSERT OR IGNORE)."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn().execute(
            """
            INSERT OR IGNORE INTO pending_transactions
                (tx_id, user_id, tx_type, amount, currency, company, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (str(tx_id), str(user_id), str(tx_type),
             str(amount), str(currency), str(company), now, now)
        )
        self._conn().commit()

    def resolve_pending_transaction(self, tx_id: str, status: str = 'resolved'):
        """Mark a pending transaction as resolved (or rejected/cancelled)."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn().execute(
            "UPDATE pending_transactions SET status=?, updated_at=? WHERE tx_id=?",
            (status, now, str(tx_id))
        )
        self._conn().commit()

    def get_pending_transactions_older_than(self, seconds: int) -> list:
        """Return list of dicts for rows with status='pending' older than *seconds*."""
        cutoff = (datetime.now(timezone.utc).timestamp() - seconds)
        cur = self._conn().execute(
            "SELECT tx_id, user_id, tx_type, amount, currency, company, created_at "
            "FROM pending_transactions WHERE status='pending'"
        )
        rows = cur.fetchall()
        result = []
        for row in rows:
            tx_id, user_id, tx_type, amount, currency, company, created_at_iso = row
            try:
                created_at = datetime.fromisoformat(created_at_iso)
                if created_at.tzinfo is None:
                    from datetime import timezone as _tz
                    created_at = created_at.replace(tzinfo=_tz.utc)
                age = (datetime.now(timezone.utc) - created_at).total_seconds()
            except Exception:
                age = seconds + 1  # assume stale if unparseable
            if age >= seconds:
                result.append({
                    'tx_id': tx_id, 'user_id': user_id, 'tx_type': tx_type,
                    'amount': amount, 'currency': currency, 'company': company,
                    'age_seconds': age,
                })
        return result

    # ---- CSV-backed table operations ----------------------------------

    def csv_read(self, filename: str) -> list:
        """Return list of OrderedDict, like csv.DictReader."""
        table = _table_name(filename)
        self.ensure_initialized()

        if not self._table_exists(table):
            # Fall back to CSV file
            return _read_csv_file(filename)

        conn = self._conn()
        cur = conn.execute(f'SELECT * FROM "{table}"')
        cols = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        result = []
        for row in rows:
            od = OrderedDict()
            for col, val in zip(cols, row):
                od[col] = val if val is not None else ''
            result.append(od)
        return result

    def csv_write(self, filename: str, rows: list, fieldnames: list = None, mode: str = 'w') -> bool:
        """Write rows to SQLite table. mode='w' replaces; mode='a' appends."""
        table = _table_name(filename)
        self.ensure_initialized()

        if not rows and mode == 'a':
            return True

        # Determine fieldnames
        if not fieldnames:
            if rows:
                first = rows[0]
                if isinstance(first, dict):
                    fieldnames = list(first.keys())
                else:
                    logger.error("csv_write: fieldnames required for non-dict rows")
                    return False
            else:
                fieldnames = []

        if fieldnames:
            self._ensure_table(table, fieldnames)

        lock = _get_table_lock(table)
        with lock:
            conn = self._conn()
            try:
                if mode == 'w':
                    conn.execute(f'DELETE FROM "{table}"')

                if rows and fieldnames:
                    cols_sql = ', '.join(f'"{f}"' for f in fieldnames)
                    placeholders = ', '.join('?' for _ in fieldnames)
                    sql = f'INSERT INTO "{table}" ({cols_sql}) VALUES ({placeholders})'
                    for row in rows:
                        if isinstance(row, dict):
                            vals = [str(row.get(f, '') or '') for f in fieldnames]
                        else:
                            vals = [str(v) if v is not None else '' for v in row]
                        conn.execute(sql, vals)
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                logger.error("csv_write error for %s: %s", filename, e)
                return False

    def csv_append(self, filename: str, row: dict, fieldnames: list = None) -> bool:
        """Append a single row."""
        if not fieldnames and isinstance(row, dict):
            fieldnames = list(row.keys())
        return self.csv_write(filename, [row], fieldnames=fieldnames, mode='a')

    def get_row_count(self, table: str) -> int:
        if not self._table_exists(table):
            return 0
        cur = self._conn().execute(f'SELECT COUNT(*) FROM "{table}"')
        return cur.fetchone()[0]

    def import_csv_file(self, filename: str, csv_path: str = None) -> int:
        """Import a CSV file into SQLite. Returns number of rows imported."""
        if csv_path is None:
            csv_path = filename
        if not os.path.exists(csv_path):
            return 0
        rows = _read_csv_file(csv_path)
        if not rows:
            return 0
        fieldnames = list(rows[0].keys())
        table = _table_name(filename)
        self._ensure_table(table, fieldnames)
        lock = _get_table_lock(table)
        with lock:
            conn = self._conn()
            try:
                cols_sql = ', '.join(f'"{f}"' for f in fieldnames)
                placeholders = ', '.join('?' for _ in fieldnames)
                sql = f'INSERT INTO "{table}" ({cols_sql}) VALUES ({placeholders})'
                for row in rows:
                    vals = [str(row.get(f, '') or '') for f in fieldnames]
                    conn.execute(sql, vals)
                conn.commit()
                return len(rows)
            except Exception as e:
                conn.rollback()
                logger.error("import_csv_file error for %s: %s", filename, e)
                return 0


# ---------------------------------------------------------------------------
# CSV file fallback helper
# ---------------------------------------------------------------------------

def _read_csv_file(filename: str) -> list:
    """Read a CSV file directly, returns list of OrderedDict."""
    paths_to_try = [filename]
    base = os.path.basename(filename)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if base != filename:
        paths_to_try.append(os.path.join(script_dir, base))
    else:
        paths_to_try.append(os.path.join(script_dir, filename))

    for path in paths_to_try:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    return [OrderedDict(row) for row in reader]
            except Exception as e:
                logger.error("_read_csv_file error for %s: %s", path, e)
                return []
    return []


# ---------------------------------------------------------------------------
# Module-level singleton helpers
# ---------------------------------------------------------------------------

def get_db() -> BotDatabase:
    """Return the singleton BotDatabase instance."""
    global _db_instance
    if _db_instance is None:
        with _instance_lock:
            if _db_instance is None:
                _db_instance = BotDatabase(DB_PATH)
                _db_instance.ensure_initialized()
    return _db_instance


def csv_read(filename: str) -> list:
    return get_db().csv_read(filename)


def csv_write(filename: str, rows: list, fieldnames: list = None, mode: str = 'w') -> bool:
    return get_db().csv_write(filename, rows, fieldnames=fieldnames, mode=mode)


def csv_append(filename: str, row: dict, fieldnames: list = None) -> bool:
    return get_db().csv_append(filename, row, fieldnames=fieldnames)


def set_user_state(user_id, state: str) -> None:
    get_db().set_user_state(user_id, state)


def get_user_state(user_id) -> Optional[str]:
    return get_db().get_user_state(user_id)


def del_user_state(user_id) -> None:
    get_db().del_user_state(user_id)


def has_user_state(user_id) -> bool:
    return get_db().has_user_state(user_id)


def get_all_user_states() -> dict:
    return get_db().get_all_user_states()


# ---------------------------------------------------------------------------
# PersistentStateDict — dict-like interface backed by user_states table
# ---------------------------------------------------------------------------

class PersistentStateDict:
    """Drop-in replacement for user_states = {} backed by SQLite."""

    def __init__(self, db: BotDatabase = None):
        self._db = db or get_db()

    def __setitem__(self, key, value):
        self._db.set_user_state(key, value)

    def __getitem__(self, key):
        val = self._db.get_user_state(key)
        if val is None:
            raise KeyError(key)
        return val

    def __delitem__(self, key):
        self._db.del_user_state(key)   # silent if not found

    def __contains__(self, key):
        return self._db.has_user_state(key)

    def get(self, key, default=None):
        val = self._db.get_user_state(key)
        return val if val is not None else default

    def items(self):
        return list(self._db.get_all_user_states().items())

    def keys(self):
        return list(self._db.get_all_user_states().keys())

    def values(self):
        return list(self._db.get_all_user_states().values())

    def __len__(self):
        cur = self._db._conn().execute("SELECT COUNT(*) FROM user_states")
        return cur.fetchone()[0]

    def __iter__(self):
        return iter(self.keys())

    def pop(self, key, *args):
        val = self._db.get_user_state(key)
        if val is None:
            if args:
                return args[0]
            raise KeyError(key)
        self._db.del_user_state(key)
        return val

    def __repr__(self):
        return f"PersistentStateDict({dict(self.items())})"
