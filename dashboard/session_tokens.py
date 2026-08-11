"""
session_tokens.py — secure session token system (v3).

Design principles:
1. Tokens are secrets.token_urlsafe(32) — 256-bit cryptographically random,
   opaque in the URL, unforgeable without server-side lookup.
   No cipher or encryption is needed; security comes from entropy, not secrecy
   of a key.
2. Sessions are stored in SQLite (same vex_games.db) so they survive restarts.
   In-memory XOR cipher is gone.
3. pre_authenticated flag: sessions created from server-side authenticated routes
   (@login_required) are marked True in the DB.  The session is bound to a
   specific uid at creation time and cannot be used for a different user.
4. Device fingerprint binding for non-pre-authenticated sessions: first device to
   present the token binds it; subsequent use from a different device is guest mode.
   Pre-authenticated sessions do not rely on device binding — the server has already
   verified the user identity at creation time.
5. Sessions expire after SESSION_TTL seconds (default 1 hour).
"""

import os
import secrets
import sqlite3
import threading
import time
import hashlib

SESSION_TTL = 3600  # 1 hour
_lock = threading.Lock()

# DB path — same file as db_manager so the schema is co-located
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH  = os.path.join(_BASE_DIR, 'vex_games.db')


def _get_conn():
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table():
    """Create the webapp_sessions table if it does not exist (idempotent)."""
    conn = _get_conn()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS webapp_sessions (
                token_hash       TEXT PRIMARY KEY,
                uid              TEXT NOT NULL,
                device_fp        TEXT NOT NULL DEFAULT '',
                pre_authenticated INTEGER NOT NULL DEFAULT 0,
                created_at       REAL NOT NULL,
                expires_at       REAL NOT NULL
            )
        ''')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_wsess_exp ON webapp_sessions(expires_at)'
        )
        conn.commit()
    finally:
        conn.close()


# Ensure table on module import
try:
    _ensure_table()
except Exception:
    pass  # DB may not exist yet; _ensure_table will be retried on first use


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(uid: str, pre_authenticated: bool = False) -> str:
    """Create a session and return the opaque token string.

    pre_authenticated=True: session was minted from a server-side authenticated
    context (@login_required).  Account/reward APIs will accept it as strong auth
    without requiring a matching device fingerprint.

    pre_authenticated=False (default): session is created speculatively (e.g.
    by the Telegram WebApp flow) and binds to the first device that presents it.
    """
    uid      = str(uid)
    token    = secrets.token_urlsafe(32)          # 256-bit random opaque token
    tok_hash = _token_hash(token)
    now      = time.time()
    _ensure_table()
    conn = _get_conn()
    try:
        # Invalidate previous sessions for this uid (one session per user)
        conn.execute('DELETE FROM webapp_sessions WHERE uid = ?', (uid,))
        conn.execute(
            'INSERT INTO webapp_sessions '
            '(token_hash, uid, device_fp, pre_authenticated, created_at, expires_at) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (tok_hash, uid, '', int(pre_authenticated), now, now + SESSION_TTL)
        )
        conn.commit()
    finally:
        conn.close()
    return token


def create_authenticated_session(uid: str) -> str:
    """Create a server-authenticated session (call only from @login_required routes).

    The returned token can be used in /webapp/* URLs; account APIs will treat it
    as strong auth because the uid was verified by Flask's login mechanism, not
    by a caller-supplied parameter.
    """
    return create_session(uid, pre_authenticated=True)


def validate_session(token: str, device_fp: str = ''):
    """Validate a session token.

    Returns (uid, is_authorized) where:
    - is_authorized=True: session is valid and this device is authorized.
    - is_authorized=False: session is valid but device fingerprint does not match
      (guest mode — suitable for read-only non-sensitive routes).
    - (None, False): token is invalid or expired.

    Pre-authenticated sessions:
    - Always return (uid, True) on any device (server already verified identity).

    Non-pre-authenticated sessions:
    - First call with a non-empty device_fp → binds fp, returns (uid, True).
    - Subsequent calls with matching device_fp → (uid, True).
    - Subsequent calls with mismatched device_fp → (uid, False) [guest mode].
    - Calls without device_fp → (uid, False) [no fp to verify].
    """
    if not token:
        return None, False
    tok_hash = _token_hash(token)
    _ensure_table()
    conn = _get_conn()
    try:
        row = conn.execute(
            'SELECT uid, device_fp, pre_authenticated, expires_at '
            'FROM webapp_sessions WHERE token_hash = ?',
            (tok_hash,)
        ).fetchone()
        if not row:
            return None, False
        if time.time() > row['expires_at']:
            conn.execute('DELETE FROM webapp_sessions WHERE token_hash = ?', (tok_hash,))
            conn.commit()
            return None, False

        uid            = row['uid']
        stored_fp      = row['device_fp'] or ''
        pre_auth       = bool(row['pre_authenticated'])

        # Pre-authenticated: server vouches for this uid — always authorized
        if pre_auth:
            return uid, True

        # First use: bind device fingerprint
        if not stored_fp and device_fp:
            conn.execute(
                'UPDATE webapp_sessions SET device_fp = ? WHERE token_hash = ?',
                (device_fp, tok_hash)
            )
            conn.commit()
            return uid, True

        # Subsequent use: require matching fingerprint
        if stored_fp and device_fp and stored_fp == device_fp:
            return uid, True

        # Mismatch or missing fingerprint — guest mode
        return uid, False

    finally:
        conn.close()


def cleanup_expired():
    """Delete expired sessions from SQLite."""
    try:
        _ensure_table()
        conn = _get_conn()
        try:
            conn.execute('DELETE FROM webapp_sessions WHERE expires_at <= ?', (time.time(),))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def generate_fingerprint(user_agent, screen_w, screen_h, timezone):
    """Generate a device fingerprint from browser properties."""
    raw = f"{user_agent}|{screen_w}x{screen_h}|{timezone}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
