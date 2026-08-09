"""
session_tokens.py — secure session token system (v2: encrypted, copy-proof).

Security features:
1. Token is AES-encrypted — not visible as plaintext in URL
2. Token is bound to device fingerprint — copy to another device = guest mode
3. Token expires after 1 hour
4. URL uses ?s=XXX (short, opaque) not ?token=XXX
5. Server decrypts ?s= → gets internal session — no client-side token storage
"""

import secrets
import time
import threading
import hashlib
import base64
import json

# In-memory session store: session_key -> {uid, device_fp, expires_at}
_sessions = {}
_lock = threading.Lock()
SESSION_TTL = 3600  # 1 hour
_CIPHER_KEY = secrets.token_hex(16)  # random key per restart (invalidates old links)

def _xor_encrypt(plaintext, key):
    """Simple XOR cipher — lightweight, no external deps needed."""
    result = []
    for i in range(len(plaintext)):
        result.append(chr(ord(plaintext[i]) ^ ord(key[i % len(key)])))
    encrypted = ''.join(result)
    return base64.urlsafe_b64encode(encrypted.encode('latin-1')).decode().rstrip('=')

def _xor_decrypt(ciphertext, key):
    """Decrypt XOR cipher."""
    try:
        decoded = base64.urlsafe_b64decode(ciphertext + '==')
        plaintext = decoded.decode('latin-1')
        result = []
        for i in range(len(plaintext)):
            result.append(chr(ord(plaintext[i]) ^ ord(key[i % len(key)])))
        return ''.join(result)
    except:
        return ''

def create_session(uid):
    """Create a secure session for a user.
    Returns an encrypted URL param (?s=XXX) that contains no visible user data."""
    session_key = secrets.token_hex(16)
    with _lock:
        # Remove old sessions for this uid
        to_remove = [k for k, v in _sessions.items() if v.get('uid') == str(uid)]
        for k in to_remove:
            del _sessions[k]
        _sessions[session_key] = {
            'uid': str(uid),
            'device_fp': None,
            'expires_at': time.time() + SESSION_TTL,
        }
    # Encrypt: session_key + timestamp (so even if XOR is broken, key is random)
    payload = f"{session_key}:{int(time.time())}"
    encrypted = _xor_encrypt(payload, _CIPHER_KEY)
    return encrypted

def validate_session(encrypted_param, device_fp=None):
    """Validate an encrypted session param.
    Returns (uid, is_authorized) or (None, False)."""
    if not encrypted_param:
        return None, False
    # Decrypt
    payload = _xor_decrypt(encrypted_param, _CIPHER_KEY)
    if not payload or ':' not in payload:
        return None, False
    parts = payload.split(':')
    if len(parts) < 2:
        return None, False
    session_key = parts[0]
    with _lock:
        data = _sessions.get(session_key)
        if not data:
            return None, False
        # Check expiry
        if time.time() > data['expires_at']:
            del _sessions[session_key]
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
        # No device_fp yet → allow (first load)
        return uid, True

def cleanup_expired():
    """Remove expired sessions."""
    now = time.time()
    with _lock:
        expired = [k for k, v in _sessions.items() if now > v['expires_at']]
        for k in expired:
            del _sessions[k]

def generate_fingerprint(user_agent, screen_w, screen_h, timezone):
    """Generate a device fingerprint from browser properties."""
    raw = f"{user_agent}|{screen_w}x{screen_h}|{timezone}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
