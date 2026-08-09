"""
session_tokens.py — secure session token system for game URLs.

Replaces ?uid=XXX (visible, shareable) with ?token=XXX (opaque, device-bound).

Flow:
1. Bot calls /api/auth/create-token?uid=XXX → gets token
2. Bot sends URL with ?token=XXX (no uid visible)
3. Client sends fingerprint (userAgent hash) on first load
4. Server validates: token → uid + device match
5. Different device → guest mode (no balance, no bets)
6. Token expires after 1 hour
"""

import secrets
import time
import threading
import hashlib

# In-memory token store: token -> {uid, created_at, device_fp, expires_at}
_tokens = {}
_lock = threading.Lock()
TOKEN_TTL = 3600  # 1 hour

def create_token(uid):
    """Generate a secure token for a user. Returns the token string."""
    token = secrets.token_hex(16)  # 32 chars, no user data
    with _lock:
        # Remove old tokens for this uid (one active token per user)
        to_remove = [t for t, v in _tokens.items() if v.get('uid') == str(uid)]
        for t in to_remove:
            del _tokens[t]
        _tokens[token] = {
            'uid': str(uid),
            'created_at': time.time(),
            'device_fp': None,  # set on first page load
            'expires_at': time.time() + TOKEN_TTL,
        }
    return token

def validate_token(token, device_fp=None):
    """Validate a token. Returns (uid, is_authorized) tuple.
    - uid: the user id if valid, None if invalid/expired
    - is_authorized: True if device matches (full access), False if different device (guest)
    """
    if not token:
        return None, False
    with _lock:
        data = _tokens.get(token)
        if not data:
            return None, False
        # Check expiry
        if time.time() > data['expires_at']:
            del _tokens[token]
            return None, False
        uid = data['uid']
        # First visit — store device fingerprint
        if data['device_fp'] is None and device_fp:
            data['device_fp'] = device_fp
            return uid, True
        # Subsequent visit — check device match
        if data['device_fp'] and device_fp:
            if data['device_fp'] == device_fp:
                return uid, True  # same device → full access
            else:
                return uid, False  # different device → guest mode
        # No device_fp provided → allow (first load before fingerprint sent)
        return uid, True

def cleanup_expired():
    """Remove expired tokens."""
    now = time.time()
    with _lock:
        expired = [t for t, v in _tokens.items() if now > v['expires_at']]
        for t in expired:
            del _tokens[t]

def generate_fingerprint(user_agent, screen_w, screen_h, timezone):
    """Generate a device fingerprint from browser properties."""
    raw = f"{user_agent}|{screen_w}x{screen_h}|{timezone}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
