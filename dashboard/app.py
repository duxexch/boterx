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
import hmac
import hashlib
import secrets
import random
import zipfile
import threading
import math
import fcntl
import time
import queue as _queue
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import parse_qs

from flask import (Flask, render_template, request, redirect, url_for,
                   session, jsonify, Response, flash, send_file, g)

# ===== Configuration =====
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', '8080'))
DASHBOARD_HOST = os.getenv('DASHBOARD_HOST', '0.0.0.0')

# Sentinel: the well-known default password committed to public git history.
# Any deployment still using this value is immediately exploitable.
_KNOWN_DEFAULT_PASSWORD = 'boterx_admin_2026'

# Load secret key — empty string means "not configured"; checked at startup below.
_raw_secret_key = os.getenv('DASHBOARD_SECRET_KEY', '')
SECRET_KEY = _raw_secret_key or secrets.token_hex(32)  # random fallback for dev only

ADMIN_IDS = [a.strip() for a in os.getenv('ADMIN_USER_IDS', '').split(',') if a.strip()]
ADMIN_PASSWORD = os.getenv('DASHBOARD_PASSWORD', _KNOWN_DEFAULT_PASSWORD)

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)  # persistent login — never expire unless user logs out
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only

# ===== Web Push (VAPID) — notifications work even when tab/browser is closed =====
_VAPID_PRIVATE = """-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQg06OSNvUikGK7vjDY
ho72Y3P8AvA+PEg63UT5yz360sGhRANCAASOjPJwku6oSoks04byXYOeINsfC5w9
ej5vx5VwKkk2dUrLlk99o8JtiJ4TGkDr5C8L0X+eMz75nJworbahwxlG
-----END PRIVATE KEY-----"""
_VAPID_PUBLIC = "jozycJLuqEqJLNOG8l2DniDbHwucPXo-b8eVcCpJNnVKy5ZPfaPCbYieExpA6-QvC9F_njM--ZycKK22ocMZRg"
_VAPID_CLAIMS = {"sub": "mailto:admin@vex.deals"}

def _send_web_push(payload_dict, target_uid=None):
    """Send Web Push to all subscribed browsers (admin + users) — works even when tab is closed.
    If target_uid is set, only send to that specific user."""
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return
    subs = read_csv('push_subscriptions.csv')
    if not subs:
        return
    payload = json.dumps({
        'title': payload_dict.get('title', 'VEX Games'),
        'message': payload_dict.get('message', ''),
        'type': payload_dict.get('type', 'notification'),
        'timestamp': payload_dict.get('timestamp', ''),
        'url': '/dashboard' if payload_dict.get('target_type') == 'dashboard' else '/home'
    })
    for sub in subs:
        endpoint = sub.get('endpoint', '')
        if not endpoint:
            continue
        # If targeting a specific user, filter
        if target_uid:
            sub_uid = sub.get('user_id', '') or sub.get('admin_id', '')
            if str(sub_uid) != str(target_uid):
                continue
        try:
            subscription_info = {
                "endpoint": endpoint,
                "keys": {
                    "p256dh": sub.get('p256dh', ''),
                    "auth": sub.get('auth', '')
                }
            }
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=_VAPID_PRIVATE,
                vapid_claims=_VAPID_CLAIMS,
                timeout=5
            )
        except WebPushException as e:
            if hasattr(e, 'response') and e.response and e.response.status_code in (404, 410):
                pass
            else:
                pass
        except Exception:
            pass

# ===== Real-time Notification Queue =====
_notification_queues = []  # list of queue.Queue, one per connected SSE client
_nq_lock = threading.Lock()

def push_notification(notif_type, title, message, data=None):
    """Push notification: SSE (real-time) + Web Push (even when tab closed) + log."""
    payload_dict = {
        'type': notif_type,
        'title': title,
        'message': message,
        'data': data or {},
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    payload = json.dumps(payload_dict)
    # 1. Push to SSE clients (real-time, tab open)
    with _nq_lock:
        for q in _notification_queues:
            try:
                q.put_nowait(payload)
            except:
                pass
    # 2. Log to notifications_log.csv for missed notifications
    try:
        log_entry = {
            'timestamp': payload_dict['timestamp'],
            'type': notif_type,
            'type_label': title,
            'message_preview': message[:200] if message else '',
            'target_type': 'dashboard',
            'target_id': '',
            'status': 'sent'
        }
        fieldnames = get_fieldnames('notifications_log.csv', ['timestamp','type','type_label','message_preview','target_type','target_id','status'])
        append_csv('notifications_log.csv', log_entry, fieldnames)
    except:
        pass
    # 3. Web Push (works even when browser/tab is closed)
    try:
        _send_web_push(payload_dict)
    except Exception as e:
        print(f"Web Push error: {e}")

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
    # If file doesn't exist or is empty, write header first
    need_header = (not os.path.exists(filepath)) or (os.path.getsize(filepath) == 0)
    with open(filepath, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if need_header:
            writer.writeheader()
        writer.writerow({k: row.get(k, '') for k in fieldnames})

def get_fieldnames(filename, default_fields):
    rows = read_csv(filename)
    if rows:
        existing = list(rows[0].keys())
        # Merge: add any default field not already in the CSV header
        for f in default_fields:
            if f not in existing:
                existing.append(f)
        return existing
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
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    """Only real admins can access admin pages"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('admin_login'))
        if not session.get('is_admin'):
            return redirect(url_for('home'), code=303)
        return f(*args, **kwargs)
    return decorated

def api_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

# ── RBAC — Role-Based Access Control ─────────────────────────────────────────
# Import module-level helpers from db_manager; provide no-op fallbacks so the
# dashboard still starts even if db_manager is absent (shouldn't happen in prod).
try:
    from db_manager import (has_permission as _rbac_has_perm,
                             get_admin_role as _rbac_get_role,
                             log_admin_action as _rbac_log,
                             set_admin_role as _rbac_set_role,
                             ROLE_PERMISSIONS as _ROLE_PERMISSIONS)
    _RBAC_AVAILABLE = True
except ImportError:
    _RBAC_AVAILABLE = False
    def _rbac_has_perm(uid, perm): return True   # allow-all fallback
    def _rbac_get_role(uid): return {'role': 'super_admin', 'permissions': {}}
    def _rbac_log(*a, **k): pass
    def _rbac_set_role(*a, **k): return False
    _ROLE_PERMISSIONS = {}


def permission_required(permission_key):
    """Decorator: require admin status + a specific RBAC permission (JSON/API routes).

    Stack after @api_auth.  Rejects with 401 if not logged in, 403 if the
    session belongs to a non-admin user (logged_in but is_admin is falsy), and
    403 if the admin lacks the required permission.

    This double-gate prevents a web/player session (logged_in=True, is_admin=False)
    from accessing admin APIs even if their UID was assigned an RBAC role.
    """
    def decorator(f):
        @wraps(f)
        def decorated_fn(*args, **kwargs):
            if not session.get('logged_in'):
                return jsonify({'error': 'Unauthorized'}), 401
            # Require admin flag — prevents player sessions from passing through
            if not session.get('is_admin'):
                return jsonify({'error': 'Forbidden — admin access required'}), 403
            uid = str(session.get('admin_id', ''))
            if not _rbac_has_perm(uid, permission_key):
                return jsonify({
                    'error': 'Permission denied',
                    'required': permission_key,
                    'message': 'ليس لديك صلاحية لهذا الإجراء',
                }), 403
            return f(*args, **kwargs)
        return decorated_fn
    return decorator


def page_permission_required(permission_key):
    """Decorator: require admin status + a specific RBAC permission (HTML page routes).

    Stack after @admin_required.  Returns a plain 403 HTML response if the
    logged-in admin lacks the permission so the browser shows a clear error.
    Also rejects non-admin sessions (is_admin falsy) with the same 403.
    """
    def decorator(f):
        @wraps(f)
        def decorated_fn(*args, **kwargs):
            if not session.get('logged_in'):
                return redirect(url_for('login'))
            # Require admin flag — prevents player sessions from passing through
            if not session.get('is_admin'):
                return redirect(url_for('dashboard'))
            uid = str(session.get('admin_id', ''))
            if not _rbac_has_perm(uid, permission_key):
                html = (
                    '<!doctype html><html lang="ar" dir="rtl">'
                    '<head><meta charset="utf-8"><title>403 — غير مصرح</title>'
                    '<style>body{font-family:sans-serif;background:#0f172a;color:#94a3b8;'
                    'display:flex;align-items:center;justify-content:center;height:100vh;margin:0}'
                    '.box{text-align:center}.icon{font-size:4rem;margin-bottom:1rem}'
                    'h1{color:#f43f5e;font-size:1.5rem}a{color:#60a5fa}</style></head>'
                    f'<body><div class="box"><div class="icon">🚫</div>'
                    f'<h1>غير مصرح — ليس لديك صلاحية هذه الصفحة</h1>'
                    f'<p>الصلاحية المطلوبة: <code>{permission_key}</code></p>'
                    f'<a href="/dashboard">العودة للوحة التحكم</a></div></body></html>'
                )
                return html, 403
            return f(*args, **kwargs)
        return decorated_fn
    return decorator


@app.context_processor
def _inject_admin_context():
    """Inject admin_role and admin_perms into every template render.

    Templates use these to conditionally show/hide sidebar links and actions.
    The call is a single SQLite SELECT (~0.1 ms) so the per-request cost is
    negligible.
    """
    if session.get('logged_in'):
        uid = str(session.get('admin_id', ''))
        try:
            role_data = _rbac_get_role(uid)
            return {
                'admin_role': role_data.get('role') or 'super_admin',
                'admin_perms': role_data.get('permissions') or {},
            }
        except Exception:
            pass
    return {'admin_role': None, 'admin_perms': {}}

# ===== Telegram WebApp Auth =====
import logging as _auth_log
_auth_logger = _auth_log.getLogger('boterx.auth')

# Load BOT_TOKEN from environment or .env file
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
if not BOT_TOKEN:
    try:
        env_path = os.path.join(BASE_DIR, '.env')
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('BOT_TOKEN='):
                        BOT_TOKEN = line.split('=', 1)[1].strip()
                        break
    except Exception:
        pass

# ── Auth-mode configuration ──────────────────────────────────────────────────
# ALLOW_DEV_AUTH=true  — accept plain uid param without HMAC verification.
#   ONLY set this during local development. NEVER in production.
#   When not set, uid-only requests are always rejected when BOT_TOKEN is absent.
ALLOW_DEV_AUTH = os.getenv('ALLOW_DEV_AUTH', '').lower() in ('1', 'true', 'yes')

# APP_ENV / FLASK_ENV — detect production deployment.
_APP_ENV = os.getenv('APP_ENV', os.getenv('FLASK_ENV', 'development')).lower()
_IS_PRODUCTION = (_APP_ENV == 'production')

# ── Production credential safety gate ────────────────────────────────────────
# Collect every credential problem first, then decide whether to abort or warn.
_cred_errors = []

if not _raw_secret_key:
    _cred_errors.append(
        "DASHBOARD_SECRET_KEY is not set. A random key is generated on every "
        "restart, invalidating all admin sessions on each reboot. "
        "Fix: set DASHBOARD_SECRET_KEY to a stable 64-char hex string "
        "(generate with: python3 -c \"import secrets; print(secrets.token_hex(32))\")."
    )

if not os.getenv('DASHBOARD_PASSWORD'):
    _cred_errors.append(
        f"DASHBOARD_PASSWORD is not set — the dashboard is running with the "
        f"public default password '{_KNOWN_DEFAULT_PASSWORD}', which is in the "
        f"public git history and is immediately exploitable. "
        f"Fix: set DASHBOARD_PASSWORD to a strong unique value."
    )
elif ADMIN_PASSWORD == _KNOWN_DEFAULT_PASSWORD:
    _cred_errors.append(
        f"DASHBOARD_PASSWORD is set to the known public default "
        f"'{_KNOWN_DEFAULT_PASSWORD}'. This value is in the public git history "
        f"and is immediately exploitable. "
        f"Fix: set DASHBOARD_PASSWORD to a strong unique value."
    )

if _IS_PRODUCTION and _cred_errors:
    # Hard stop: refuse to expose a vulnerable dashboard to the internet.
    for _ce in _cred_errors:
        _auth_logger.critical("SECURITY STARTUP FAILURE: %s", _ce)
    _auth_logger.critical(
        "Dashboard refusing to start in production (APP_ENV=%s) with insecure "
        "credentials. Set the required environment variables and restart.",
        _APP_ENV,
    )
    raise SystemExit(1)
elif _cred_errors:
    # Non-production: warn loudly but continue so local dev still works.
    for _ce in _cred_errors:
        _auth_logger.warning("CREDENTIAL WARNING (non-production): %s", _ce)

# ── Alert token for lockdown notifications ───────────────────────────────────
# ALERT_BOT_TOKEN: a separate bot token used ONLY to send lockdown alerts.
# Falls back to BOT_TOKEN if already loaded, then tries .env.
# This lets the dashboard alert admins even when the main BOT_TOKEN is missing,
# provided a dedicated alert bot token is available.
ALERT_BOT_TOKEN = os.getenv('ALERT_BOT_TOKEN', '')
if not ALERT_BOT_TOKEN:
    try:
        env_path = os.path.join(BASE_DIR, '.env')
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as _ef:
                for _line in _ef:
                    _line = _line.strip()
                    if _line.startswith('ALERT_BOT_TOKEN='):
                        ALERT_BOT_TOKEN = _line.split('=', 1)[1].strip()
                        break
    except Exception:
        pass

_LOCKDOWN_SENTINEL = '/tmp/boterx_lockdown'
_LOCKDOWN_LOG = 'lockdown_log.csv'
_LOCKDOWN_LOG_FIELDS = ['event', 'timestamp', 'host', 'duration_seconds', 'telegram_sent', 'reason']


def _append_lockdown_log(event: str, duration_seconds: int = 0,
                         telegram_sent: str = 'no', reason: str = ''):
    """Append one row to lockdown_log.csv in BASE_DIR.

    event: 'lockdown' | 'recovery'
    duration_seconds: 0 for lockdown events; elapsed seconds for recovery events
    telegram_sent: 'yes' | 'no'
    reason: short machine-readable cause string
    """
    try:
        row = {
            'event': event,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'host': os.uname().nodename,
            'duration_seconds': str(duration_seconds),
            'telegram_sent': telegram_sent,
            'reason': reason,
        }
        filepath = os.path.join(BASE_DIR, _LOCKDOWN_LOG)
        file_exists = os.path.exists(filepath)
        with open(filepath, 'a', newline='', encoding='utf-8-sig') as _lf:
            writer = csv.DictWriter(_lf, fieldnames=_LOCKDOWN_LOG_FIELDS)
            if not file_exists:
                writer.writeheader()
            writer.writerow({k: row.get(k, '') for k in _LOCKDOWN_LOG_FIELDS})
    except Exception as exc:
        _auth_logger.error("Failed to write lockdown_log.csv: %s", exc)


def _read_lockdown_log_summary():
    """Return (last_lockdown_at, last_recovery_at) strings from lockdown_log.csv.
    Both values are ISO-format strings or None if no matching event exists.
    """
    try:
        filepath = os.path.join(BASE_DIR, _LOCKDOWN_LOG)
        if not os.path.exists(filepath):
            return None, None
        last_lockdown = None
        last_recovery = None
        with open(filepath, 'r', encoding='utf-8-sig') as _lf:
            for row in csv.DictReader(_lf):
                if row.get('event') == 'lockdown':
                    last_lockdown = row.get('timestamp')
                elif row.get('event') == 'recovery':
                    last_recovery = row.get('timestamp')
        return last_lockdown, last_recovery
    except Exception:
        return None, None


def _read_sentinel_info():
    """Return (lockdown_iso, telegram_sent) from the sentinel file, or (None, None)."""
    try:
        data = {}
        with open(_LOCKDOWN_SENTINEL, 'r') as _sf:
            for _ln in _sf:
                _ln = _ln.strip()
                if '=' in _ln:
                    k, v = _ln.split('=', 1)
                    data[k] = v
        return data.get('LOCKDOWN'), data.get('TELEGRAM_SENT', 'no')
    except Exception:
        return None, None


def _send_recovery_alert(lockdown_iso: str):
    """Send a '✅ Game API restored' Telegram message to every admin.

    Called in a background daemon thread so it never blocks startup.
    The sentinel file is removed after the send attempt (success or failure)
    so it cannot trigger stale alerts on the next restart.
    """
    import urllib.request as _ur
    import urllib.error as _ue

    token = ALERT_BOT_TOKEN or BOT_TOKEN

    # Calculate downtime duration
    duration_str = 'unknown duration'
    if lockdown_iso:
        try:
            lockdown_dt = datetime.fromisoformat(lockdown_iso)
            delta = datetime.now() - lockdown_dt
            total_s = int(delta.total_seconds())
            if total_s < 60:
                duration_str = f'{total_s}s'
            elif total_s < 3600:
                duration_str = f'{total_s // 60}m {total_s % 60}s'
            else:
                h = total_s // 3600
                m = (total_s % 3600) // 60
                duration_str = f'{h}h {m}m'
        except Exception:
            pass

    lockdown_time_str = lockdown_iso or 'unknown'
    msg = (
        "✅ *Game API RESTORED* ✅\n\n"
        "BOT\\_TOKEN has been restored — the game API is *ENABLED* again.\n\n"
        f"Lockdown started: `{lockdown_time_str}`\n"
        f"Downtime: `{duration_str}`\n"
        f"Host: `{os.uname().nodename}`\n"
        f"Restored at: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
    )

    if token and ADMIN_IDS:
        for admin_uid in ADMIN_IDS:
            try:
                payload = json.dumps({
                    'chat_id': admin_uid,
                    'text': msg,
                    'parse_mode': 'Markdown'
                }).encode('utf-8')
                req = _ur.Request(
                    f'https://api.telegram.org/bot{token}/sendMessage',
                    data=payload,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with _ur.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        _auth_logger.info(
                            "Recovery alert sent to admin %s via Telegram.", admin_uid
                        )
            except _ue.HTTPError as exc:
                _auth_logger.error(
                    "Recovery alert HTTP error for admin %s: %s", admin_uid, exc
                )
            except Exception as exc:
                _auth_logger.error(
                    "Recovery alert failed for admin %s: %s", admin_uid, exc
                )
    elif not token:
        _auth_logger.warning(
            "Recovery alert: no ALERT_BOT_TOKEN or BOT_TOKEN available — "
            "cannot send Telegram notification."
        )
    elif not ADMIN_IDS:
        _auth_logger.warning(
            "Recovery alert: ADMIN_USER_IDS is empty — no admins to notify."
        )

    # Calculate duration_seconds for audit log
    duration_seconds = 0
    if lockdown_iso:
        try:
            lockdown_dt = datetime.fromisoformat(lockdown_iso)
            duration_seconds = max(0, int((datetime.now() - lockdown_dt).total_seconds()))
        except Exception:
            pass

    # Persist recovery event to audit log
    _append_lockdown_log(
        event='recovery',
        duration_seconds=duration_seconds,
        telegram_sent='yes' if (token and ADMIN_IDS) else 'no',
        reason='BOT_TOKEN_RESTORED'
    )

    # Remove sentinel regardless of send outcome — prevents stale alerts on
    # future restarts even if Telegram delivery failed.
    try:
        os.remove(_LOCKDOWN_SENTINEL)
        _auth_logger.info("Lockdown sentinel removed after recovery alert.")
    except Exception as exc:
        _auth_logger.error("Failed to remove lockdown sentinel: %s", exc)


def _send_lockdown_alert():
    """Send a Telegram alert to every admin when the game API is locked down.

    Called in a background daemon thread so it never blocks startup.
    Tries ALERT_BOT_TOKEN first (dedicated alert bot), then the main BOT_TOKEN
    read from .env.  If no token is available at all, writes a sentinel file
    at /tmp/boterx_lockdown so external health-check scripts can detect the
    outage without Telegram access.
    """
    import urllib.request as _ur
    import urllib.error as _ue

    token = ALERT_BOT_TOKEN or BOT_TOKEN
    msg = (
        "⚠️ *SECURITY LOCKDOWN* ⚠️\n\n"
        "BOT\\_TOKEN is missing in production — the game API is *DISABLED*.\n"
        "All game endpoints are returning 503 until BOT\\_TOKEN is restored.\n\n"
        f"Host: `{os.uname().nodename}`\n"
        f"Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
        "Fix: set `BOT_TOKEN` in your production environment and restart the dashboard."
    )

    sent = False
    if token and ADMIN_IDS:
        for admin_uid in ADMIN_IDS:
            try:
                payload = json.dumps({
                    'chat_id': admin_uid,
                    'text': msg,
                    'parse_mode': 'Markdown'
                }).encode('utf-8')
                req = _ur.Request(
                    f'https://api.telegram.org/bot{token}/sendMessage',
                    data=payload,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with _ur.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        sent = True
                        _auth_logger.info(
                            "Lockdown alert sent to admin %s via Telegram.", admin_uid
                        )
            except _ue.HTTPError as e:
                _auth_logger.error(
                    "Lockdown alert HTTP error for admin %s: %s", admin_uid, e
                )
            except Exception as e:
                _auth_logger.error(
                    "Lockdown alert failed for admin %s: %s", admin_uid, e
                )
    elif not token:
        _auth_logger.warning(
            "Lockdown alert: no ALERT_BOT_TOKEN or BOT_TOKEN available — "
            "cannot send Telegram notification."
        )
    elif not ADMIN_IDS:
        _auth_logger.warning(
            "Lockdown alert: ADMIN_USER_IDS is empty — no admins to notify."
        )

    # Always write sentinel file so external monitors can detect the outage
    sent_str = 'yes' if sent else 'no'
    try:
        with open(_LOCKDOWN_SENTINEL, 'w') as _sf:
            _sf.write(
                f"LOCKDOWN={datetime.now().isoformat()}\n"
                f"REASON=BOT_TOKEN_MISSING\n"
                f"TELEGRAM_SENT={sent_str}\n"
            )
        _auth_logger.info("Lockdown sentinel written to %s", _LOCKDOWN_SENTINEL)
    except Exception as e:
        _auth_logger.error("Failed to write lockdown sentinel: %s", e)

    # Persist to audit log
    _append_lockdown_log(
        event='lockdown',
        duration_seconds=0,
        telegram_sent=sent_str,
        reason='BOT_TOKEN_MISSING'
    )


# ── Startup safety check ─────────────────────────────────────────────────────
# Rule: in production, BOT_TOKEN is ALWAYS required.
# ALLOW_DEV_AUTH is never consulted in production — it cannot override this.
# If BOT_TOKEN is absent in production, every game endpoint returns 503.
_WEBAPP_AUTH_LOCKED_DOWN = False
if not BOT_TOKEN:
    if _IS_PRODUCTION:
        # Unconditional lockdown — ALLOW_DEV_AUTH is deliberately ignored here.
        # An operator mistake (setting ALLOW_DEV_AUTH=true in production) must
        # not silently reopen the unauthenticated uid-fallback path.
        _auth_logger.critical(
            "SECURITY LOCKDOWN: BOT_TOKEN is missing in production mode "
            "(APP_ENV/FLASK_ENV=%s). All game API endpoints are DISABLED. "
            "Fix: set BOT_TOKEN in the production environment. "
            "NOTE: ALLOW_DEV_AUTH is ignored in production — it cannot bypass this lockdown.",
            _APP_ENV
        )
        if ALLOW_DEV_AUTH:
            _auth_logger.critical(
                "SECURITY LOCKDOWN: ALLOW_DEV_AUTH=true was detected but is IGNORED "
                "in production. It cannot override the BOT_TOKEN requirement."
            )
        _WEBAPP_AUTH_LOCKED_DOWN = True

        # Notify admins in a background thread — must not block startup
        _alert_thread = threading.Thread(target=_send_lockdown_alert, daemon=True)
        _alert_thread.start()

    elif ALLOW_DEV_AUTH:
        _auth_logger.warning(
            "DEV AUTH MODE ACTIVE (non-production): ALLOW_DEV_AUTH=true — "
            "uid param accepted without HMAC verification. "
            "NEVER use ALLOW_DEV_AUTH=true in production!"
        )
    else:
        _auth_logger.warning(
            "BOT_TOKEN not set and ALLOW_DEV_AUTH not set — game API endpoints "
            "will reject all requests with 403. Set ALLOW_DEV_AUTH=true for local dev."
        )
else:
    # BOT_TOKEN is present — check for a previous lockdown episode and notify admins
    if os.path.exists(_LOCKDOWN_SENTINEL):
        lockdown_iso, _ = _read_sentinel_info()
        _auth_logger.info(
            "Previous lockdown detected (started %s) — sending recovery alert.", lockdown_iso
        )
        # Recovery alert runs in background; _send_recovery_alert also removes sentinel
        _recovery_thread = threading.Thread(
            target=_send_recovery_alert, args=(lockdown_iso,), daemon=True
        )
        _recovery_thread.start()
    _auth_logger.info("BOT_TOKEN loaded — HMAC validation active for game endpoints.")

# ── initData max age ─────────────────────────────────────────────────────────
_INIT_DATA_MAX_AGE = 3600  # reject initData older than 1 hour


def validate_telegram_init_data(init_data_str: str):
    """Validate Telegram WebApp initData using HMAC-SHA256.

    Implements the algorithm from https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app:
      secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
      hash       = HMAC_SHA256(key=secret_key,   msg=data_check_string)

    Returns (user_id_str, user_dict) if valid, (None, None) otherwise.
    """
    if not init_data_str:
        return None, None
    try:
        parsed = parse_qs(init_data_str)
        hash_from_client = parsed.get('hash', [None])[0]
        if not hash_from_client:
            return None, None

        # Build data-check string: sorted key=value pairs, excluding 'hash'
        data_check = {k: v[0] for k, v in parsed.items() if k != 'hash'}
        data_check_string = '\n'.join(f'{k}={v}' for k, v in sorted(data_check.items()))

        # secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)  ← Telegram spec
        secret_key = hmac.new(b'WebAppData', BOT_TOKEN.encode(), hashlib.sha256).digest()
        # calculated_hash = HMAC_SHA256(key=secret_key, msg=data_check_string)
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(calculated_hash, hash_from_client):
            return None, None

        user_json = data_check.get('user', '')
        if user_json:
            user_obj = json.loads(user_json)
            return str(user_obj.get('id', '')), user_obj
        return None, None
    except Exception:
        return None, None


def account_auth(f):
    """Decorator: strict authentication for player account/reward/referral APIs.

    Accepts ONLY two auth paths (fail-closed on everything else):

    A. Flask session cookie — user is logged in via the /home dashboard route.
       Requires session['logged_in'] is True, a non-empty admin_id, and
       is_admin=False.  The session cookie is HttpOnly and never appears in URLs.

    B. Fresh HMAC-validated Telegram initData — Telegram Mini App WebApp flow.
       Validates HMAC-SHA256 with BOT_TOKEN and auth_date freshness (max 1 h).
       No client-controlled device fingerprint is used for replay detection;
       freshness+HMAC is the security boundary.  Fail-closed on any validation
       or persistence error (no fail-open nonce fallback).

    Any other path (uid param, ?s= session token, dev mode uid) → 403.
    This decorator is intentionally stricter than webapp_auth for endpoints that
    expose PII (profile, phone, transactions) and permit financial mutations (claims).
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # ── Path A: Flask session cookie (HttpOnly, server-side) ──────────
        flask_uid = session.get('admin_id', '').strip()
        if (flask_uid
                and session.get('logged_in') is True
                and not session.get('is_admin')):
            g.telegram_user_id = flask_uid
            g.telegram_user = None
            return f(*args, **kwargs)

        # ── Path B: HMAC-validated Telegram initData (fail-closed) ────────
        if not BOT_TOKEN:
            # No BOT_TOKEN and not a Flask session — cannot validate
            return jsonify({'error': 'Authentication required', 'code': 'NO_AUTH'}), 403

        init_data = (
            request.headers.get('X-Telegram-Init-Data', '').strip()
            or request.args.get('initData', '').strip()
        )
        if not init_data:
            try:
                init_data = (request.get_json(silent=True) or {}).get('initData', '').strip()
            except Exception:
                init_data = ''

        if not init_data:
            return jsonify({'error': 'initData required', 'code': 'NO_INIT_DATA'}), 403

        uid_str, user_obj = validate_telegram_init_data(init_data)
        if not uid_str:
            return jsonify({'error': 'Invalid or tampered initData', 'code': 'BAD_INIT_DATA'}), 403

        # Freshness — fail CLOSED (no fallback on error)
        try:
            import time as _time
            auth_date_vals = parse_qs(init_data).get('auth_date', [])
            if not auth_date_vals:
                return jsonify({'error': 'initData missing auth_date', 'code': 'NO_AUTH_DATE'}), 403
            auth_date = int(auth_date_vals[0])
            if auth_date <= 0:
                return jsonify({'error': 'initData invalid auth_date', 'code': 'BAD_AUTH_DATE'}), 403
            age = _time.time() - auth_date
            if age > _INIT_DATA_MAX_AGE:
                return jsonify({'error': 'initData expired', 'code': 'EXPIRED_INIT_DATA'}), 403
            if age < -60:
                return jsonify({'error': 'initData auth_date in future', 'code': 'FUTURE_AUTH_DATE'}), 403
        except (ValueError, TypeError):
            return jsonify({'error': 'initData auth_date malformed', 'code': 'BAD_AUTH_DATE'}), 403
        except Exception:
            # Any other error in freshness check → fail closed
            return jsonify({'error': 'initData validation error', 'code': 'AUTH_ERROR'}), 403

        # uid comes exclusively from HMAC-validated payload — not from caller
        g.telegram_user_id = uid_str
        g.telegram_user = user_obj
        return f(*args, **kwargs)
    return decorated


def webapp_auth(f):
    """Decorator: validates Telegram WebApp initData on game-facing API endpoints.

    Auth priority (evaluated at request time using module-level constants):

    1. LOCKDOWN (_WEBAPP_AUTH_LOCKED_DOWN=True):
       BOT_TOKEN missing in production — unconditional, ignores ALLOW_DEV_AUTH.
       Every request returns 503.

    2. PRODUCTION HMAC (BOT_TOKEN set):
       Validates X-Telegram-Init-Data header (or initData param) via HMAC-SHA256.
       Enforces auth_date freshness (max 1 h, no future timestamps). Fail CLOSED.

    3. DEV/TEST (ALLOW_DEV_AUTH=true AND NOT production):
       Accepts plain uid param. Logs per-request WARNING. Never allow in prod.
       Defense-in-depth: _IS_PRODUCTION guard inside path prevents activation
       even if operator sets ALLOW_DEV_AUTH=true on a prod server by mistake.

    4. UNCONFIGURED (no BOT_TOKEN, no ALLOW_DEV_AUTH, non-production):
       Rejects all requests with 403. Operator must fix the config.
    """
    @wraps(f)
    def decorated(*args, **kwargs):

        # ── Path 1: Security lockdown ─────────────────────────────────────
        if _WEBAPP_AUTH_LOCKED_DOWN:
            return jsonify({
                'error': 'Service unavailable: BOT_TOKEN not configured in production',
                'code': 'AUTH_LOCKDOWN'
            }), 503

        # ── Path 1b: Flask dashboard session (HttpOnly cookie, never in URL) ───
        # Users who navigate to Mini App pages from the /home dashboard route
        # carry a Flask session cookie with their verified uid.  This cookie is
        # HttpOnly and Secure — it cannot leak from URL logs or Referrer headers
        # and cannot be forged without the SESSION_SECRET.  No URL token needed.
        flask_uid = session.get('admin_id', '').strip()
        if flask_uid and session.get('logged_in') is True and not session.get('is_admin'):
            # Only allow non-admin (regular user) dashboard sessions here.
            # Admin sessions are for the admin panel, not the player WebApp.
            g.telegram_user_id = flask_uid
            g.telegram_user = None
            g.webapp_auth_strong = True   # login_required already verified identity
            return f(*args, **kwargs)

        # ── Path 2: Production HMAC validation ────────────────────────────
        if BOT_TOKEN:
            init_data = (
                request.headers.get('X-Telegram-Init-Data', '').strip()
                or request.args.get('initData', '').strip()
            )
            if not init_data:
                try:
                    init_data = (request.get_json(silent=True) or {}).get('initData', '').strip()
                except Exception:
                    init_data = ''

            if not init_data:
                # uid fallback: accept uid from URL/body when no initData.
                # Bot sends uid in the URL — valid for browser/WebView opens.
                uid_fb = request.args.get('uid', '').strip()
                if not uid_fb:
                    try:
                        uid_fb = (request.get_json(silent=True) or {}).get('uid', '').strip()
                    except Exception:
                        uid_fb = ''
                if uid_fb:
                    g.telegram_user_id = uid_fb
                    g.telegram_user = None
                    g.webapp_auth_strong = False   # caller-supplied uid, not validated
                    return f(*args, **kwargs)
                # Encrypted session fallback (?s=XXX)
                s_fb = request.args.get('s', '').strip()
                if not s_fb and request.is_json:
                    try:
                        s_fb = (request.get_json(silent=True) or {}).get('s', '').strip()
                    except Exception:
                        s_fb = ''
                if s_fb:
                    from session_tokens import validate_session
                    device_fp = request.headers.get('X-Device-FP', '')
                    uid_val, authorized = validate_session(s_fb, device_fp)
                    if uid_val and authorized:
                        g.telegram_user_id = uid_val
                        g.telegram_user = None
                        # validate_session returns authorized=True for both:
                        # (a) pre_authenticated sessions (server minted from @login_required)
                        # (b) device-fingerprint-matched sessions
                        # Both are classified as strong auth.
                        g.webapp_auth_strong = True
                        return f(*args, **kwargs)
                    if uid_val and not authorized:
                        # Device fingerprint mismatch — guest mode.
                        # Permit read-only game routes but block sensitive account endpoints.
                        g.telegram_user_id = uid_val
                        g.telegram_user = None
                        g.webapp_auth_strong = False   # device mismatch — not strong
                        return f(*args, **kwargs)
                return jsonify({'error': 'initData required', 'code': 'NO_INIT_DATA'}), 403

            uid_str, user_obj = validate_telegram_init_data(init_data)
            if not uid_str:
                return jsonify({'error': 'Invalid or tampered initData', 'code': 'BAD_INIT_DATA'}), 403

            # Freshness check — fail CLOSED
            try:
                import time as _time
                auth_date_vals = parse_qs(init_data).get('auth_date', [])
                if not auth_date_vals:
                    return jsonify({'error': 'initData missing auth_date', 'code': 'NO_AUTH_DATE'}), 403
                auth_date = int(auth_date_vals[0])
                if auth_date <= 0:
                    return jsonify({'error': 'initData invalid auth_date', 'code': 'BAD_AUTH_DATE'}), 403
                age = _time.time() - auth_date
                if age > _INIT_DATA_MAX_AGE:
                    return jsonify({'error': 'initData expired', 'code': 'EXPIRED_INIT_DATA'}), 403
                if age < -60:
                    return jsonify({'error': 'initData auth_date in future', 'code': 'FUTURE_AUTH_DATE'}), 403
            except (ValueError, TypeError):
                return jsonify({'error': 'initData auth_date malformed', 'code': 'BAD_AUTH_DATE'}), 403

            # ── Replay-protection: reject same initData token reused from a
            # different device.  Same-device repeated use within the TTL is
            # allowed (a WebApp page sends the same initData on every apiFetch
            # call).  The hash + device fingerprint are stored in SQLite so
            # protection survives restarts.
            try:
                import hashlib as _hl
                _tok_hash   = _hl.sha256(init_data.encode()).hexdigest()
                _device_fp  = request.headers.get('X-Device-FP', '')
                if not _check_nonce(_tok_hash, uid_str,
                                    device_fp=_device_fp,
                                    ttl=_INIT_DATA_MAX_AGE + 120):
                    _auth_logger.warning(
                        "initData cross-device replay detected uid=%s hash=%s…",
                        uid_str, _tok_hash[:12])
                    return jsonify({'error': 'initData already used from different device',
                                    'code': 'REPLAY_INIT_DATA'}), 403
            except Exception as _nonce_err:
                # Never block a legitimate request if nonce storage fails
                _auth_logger.error("nonce check error (fail-open): %s", _nonce_err)

            g.telegram_user_id = uid_str
            g.telegram_user = user_obj
            g.webapp_auth_strong = True   # HMAC-validated Telegram initData
            return f(*args, **kwargs)

        # ── Path 3: Dev/test mode (explicit opt-in, non-production only) ────
        # Defense-in-depth: _IS_PRODUCTION is checked here even though the
        # startup lockdown already catches production+no-token. This prevents
        # path 3 from activating if ALLOW_DEV_AUTH=true is mistakenly set on
        # a production server that somehow bypassed the lockdown flag.
        if ALLOW_DEV_AUTH and not _IS_PRODUCTION:
            uid = request.args.get('uid', '').strip()
            if not uid:
                try:
                    uid = (request.get_json(silent=True) or {}).get('uid', '').strip()
                except Exception:
                    pass
            if uid:
                _auth_logger.warning(
                    "DEV AUTH: uid=%s accepted without HMAC (ALLOW_DEV_AUTH=true)", uid
                )
                g.telegram_user_id = uid
                g.telegram_user = None
                g.webapp_auth_strong = False   # dev/test uid — not validated
                return f(*args, **kwargs)
            return jsonify({'error': 'Missing uid (dev mode)', 'code': 'NO_UID'}), 403

        # ── Path 3b: ALLOW_DEV_AUTH in production — hard reject ───────────
        if ALLOW_DEV_AUTH and _IS_PRODUCTION:
            _auth_logger.critical(
                "SECURITY: ALLOW_DEV_AUTH=true ignored in production. "
                "Request rejected. Set BOT_TOKEN to restore game access."
            )
            return jsonify({
                'error': 'Service unavailable: BOT_TOKEN required in production',
                'code': 'AUTH_LOCKDOWN'
            }), 503

        # ── Path 4: Unconfigured — no token, no dev opt-in ───────────────
        return jsonify({
            'error': 'Game API not configured: set BOT_TOKEN or ALLOW_DEV_AUTH=true (dev only)',
            'code': 'NOT_CONFIGURED'
        }), 403

    return decorated

def get_request_uid():
    """Get the authenticated user ID from request context.
    Priority: g.telegram_user_id → token param → uid param (fallback).
    """
    uid = getattr(g, 'telegram_user_id', None)
    if uid:
        return uid
    # Encrypted session auth (?s=XXX — encrypted, no uid visible)
    s_param = request.args.get('s', '')
    if not s_param and request.is_json:
        s_param = (request.json or {}).get('s', '')
    if s_param:
        from session_tokens import validate_session
        device_fp = request.headers.get('X-Device-FP', '')
        uid_val, authorized = validate_session(s_param, device_fp)
        if uid_val and authorized:
            return uid_val
        if uid_val and not authorized:
            # Different device → guest mode (no uid → no balance/bets)
            return None
    # Legacy fallback (will be removed after full migration)
    uid = request.args.get('uid', '')
    if not uid and request.is_json:
        uid = (request.json or {}).get('uid', '')
    return uid

# ===== Security headers (applied to every response) =========================
@app.after_request
def _add_security_headers(response):
    """Harden every response with standard security headers."""
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-XSS-Protection', '1; mode=block')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')
    # Allow service worker and iframe for WebApp pages
    if not request.path.startswith('/webapp/'):
        response.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'self' https: data:; "
            # 'unsafe-eval' is required: Alpine.js and the Tailwind runtime
            # compile expressions with new Function(). Without it every page's
            # JS silently dies (no data, broken sidebar, stuck panels).
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline' https:; "
            "img-src 'self' data: https:; "
            "font-src 'self' data: https://fonts.gstatic.com;"
        )
    # Allow the service worker (served from /static/) to control scope '/'
    if request.path == '/static/sw.js':
        response.headers['Service-Worker-Allowed'] = '/'
    return response


# ===== In-memory login rate limiter (no Redis needed) ========================
import collections as _col
_login_attempts: dict = {}  # ip → deque of timestamps
_login_lock = threading.Lock()
_LOGIN_MAX = 5
_LOGIN_WINDOW = 60.0  # seconds

def _login_rate_limited(ip: str) -> bool:
    """Return True if this IP has exceeded the login attempt limit."""
    now = time.time()
    cutoff = now - _LOGIN_WINDOW
    with _login_lock:
        if ip not in _login_attempts:
            _login_attempts[ip] = _col.deque()
        dq = _login_attempts[ip]
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= _LOGIN_MAX:
            return True
        dq.append(now)
        return False


# ===== Routes — Pages =====

@app.route('/')
def index():
    """Landing page (public) — admin dashboard redirect only when logged in."""
    if session.get('logged_in'):
        return redirect(url_for('dashboard'), code=303)
    return render_template('landing.html')

# ===== SEO — robots.txt + sitemap.xml + llms.txt =====

@app.route('/robots.txt')
def robots_txt():
    """robots.txt — allow public pages, block admin/auth, allow AI crawlers."""
    body = (
        "# VEX Games — robots.txt\n"
        "# Allow AI crawlers\n"
        "User-agent: GPTBot\n"
        "Allow: /\n\n"
        "User-agent: ClaudeBot\n"
        "Allow: /\n\n"
        "User-agent: PerplexityBot\n"
        "Allow: /\n\n"
        "User-agent: Google-Extended\n"
        "Allow: /\n\n"
        "# All other bots\n"
        "User-agent: *\n"
        "Allow: /\n"
        "Allow: /static/\n"
        "Disallow: /dashboard\n"
        "Disallow: /admin\n"
        "Disallow: /vex/admin\n"
        "Disallow: /api/\n"
        "Disallow: /seo\n"
        "Disallow: /users\n"
        "Disallow: /transactions\n"
        "Disallow: /matching\n"
        "Disallow: /companies\n"
        "Disallow: /bots\n"
        "Disallow: /settings\n"
        "Disallow: /svrp\n"
        "Disallow: /referrals\n"
        "Disallow: /channels\n"
        "Disallow: /trading\n"
        "Disallow: /complaints\n"
        "Disallow: /payment_methods\n"
        "Disallow: /wallet\n"
        "Disallow: /account\n"
        "Disallow: /apps\n"
        "Disallow: /games-admin\n"
        "\n"
        "Sitemap: https://vex.deals/sitemap.xml\n"
    )
    return Response(body, mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap_xml():
    """Dynamic sitemap — ONLY vex.deals URLs (Google rejects external domains)."""
    from datetime import datetime as _dt
    now = _dt.now().strftime('%Y-%m-%d')
    pages = [
        {'url': 'https://vex.deals/', 'priority': '1.0', 'changefreq': 'daily'},
        {'url': 'https://vex.deals/webapp/games', 'priority': '0.9', 'changefreq': 'daily'},
        {'url': 'https://vex.deals/webapp/aviator', 'priority': '0.8', 'changefreq': 'weekly'},
        {'url': 'https://vex.deals/webapp/crash', 'priority': '0.8', 'changefreq': 'weekly'},
        {'url': 'https://vex.deals/webapp/plinko', 'priority': '0.8', 'changefreq': 'weekly'},
        {'url': 'https://vex.deals/webapp/mines', 'priority': '0.8', 'changefreq': 'weekly'},
        {'url': 'https://vex.deals/webapp/wheel', 'priority': '0.8', 'changefreq': 'weekly'},
        {'url': 'https://vex.deals/webapp/lottery', 'priority': '0.8', 'changefreq': 'weekly'},
        {'url': 'https://vex.deals/webapp/dice', 'priority': '0.8', 'changefreq': 'weekly'},
        {'url': 'https://vex.deals/webapp/stats', 'priority': '0.6', 'changefreq': 'weekly'},
        {'url': 'https://vex.deals/webapp/account', 'priority': '0.5', 'changefreq': 'weekly'},
    ]
    # NOTE: External referral links (refpa*.com) are NOT included — Google requires
    # sitemap URLs to be on the same domain. They are linked from landing.html
    # and app pages instead, which Google discovers via crawling.

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for p in pages:
        xml += f'  <url>\n'
        xml += f'    <loc>{p["url"]}</loc>\n'
        xml += f'    <lastmod>{now}</lastmod>\n'
        xml += f'    <changefreq>{p["changefreq"]}</changefreq>\n'
        xml += f'    <priority>{p["priority"]}</priority>\n'
        xml += f'  </url>\n'
    xml += '</urlset>'
    return Response(xml, mimetype='application/xml')

@app.route('/llms.txt')
def llms_txt():
    """llms.txt — plain text for AI/LLM crawlers to understand the platform."""
    body = (
        "# VEX Games\n\n"
        "VEX Games is a multi-language financial gaming platform accessible via Telegram bot and web interface at https://vex.deals.\n\n"
        "## Platform Overview\n"
        "- Games: Aviator, Crash, Plinko, Mines, Wheel of Fortune, Lottery, Dice\n"
        "- Supported languages: Arabic, English, French, Spanish, German, Italian, Portuguese, Russian, Chinese, Turkish, Urdu, Hindi, Persian, Indonesian, Japanese, Korean, Thai\n"
        "- Wallet system with deposits, withdrawals, and compensation (SVRP)\n"
        "- P2P matching system for deposits/withdrawals between users\n"
        "- USDT trading support\n"
        "- Referral and affiliate system\n\n"
        "## Key Pages\n"
        "- Landing: https://vex.deals/\n"
        "- Games Hub: https://vex.deals/webapp/games\n"
        "- Aviator: https://vex.deals/webapp/aviator\n"
        "- Crash: https://vex.deals/webapp/crash\n"
        "- Plinko: https://vex.deals/webapp/plinko\n"
        "- Stats: https://vex.deals/webapp/stats\n\n"
        "## Brand\n"
        "- Name: VEX Games\n"
        "- Domain: vex.deals\n"
        "- Logo: https://vex.deals/static/icons/icon-512.png\n"
        "- Theme color: #00ff88 (green)\n\n"
        "## Contact\n"
        "- Telegram bot: @VEX_OTP_bot\n"
        "- Support: via Telegram bot\n"
    )
    return Response(body, mimetype='text/plain')

@app.route('/api/web/request-code', methods=['POST'])
def api_web_request_code():
    """Generate and send OTP code directly via security bot — no need to open Telegram first.
    User enters Telegram ID on website → server generates code → sends via OTP bot."""
    import random as _r, time as _t, json as _json, csv as _csv
    data = request.json or {}
    tg_id = str(data.get('telegram_id', '')).strip()
    if not tg_id or not tg_id.isdigit() or len(tg_id) < 6:
        return jsonify({'error': 'معرف تيليجرام غير صالح'}), 400

    # Check user exists in users.csv
    user = None
    try:
        with open(os.path.join(BASE_DIR, 'users.csv'), 'r', encoding='utf-8-sig') as f:
            for row in _csv.DictReader(f):
                if row.get('telegram_id') == tg_id:
                    user = row
                    break
    except:
        pass
    if not user:
        return jsonify({'error': 'غير مسجل — سجل في البوت الرئيسي أولاً'}), 400

    # Generate code
    code = str(_r.randint(100000, 999999))
    name = user.get('name', '')
    auth_file = os.path.join(BASE_DIR, 'web_auth_codes.json')
    try:
        if os.path.exists(auth_file):
            with open(auth_file, 'r') as f:
                codes = _json.load(f)
        else:
            codes = {}
        codes = {k: v for k, v in codes.items() if k != tg_id}
        codes[tg_id] = {'code': code, 'name': name, 'created': _t.time()}
        with open(auth_file, 'w') as f:
            _json.dump(codes, f)
    except Exception as e:
        return jsonify({'error': 'خطأ في الخادم'}), 500

    # Send code via OTP bot
    otp_token = None
    try:
        with open(os.path.join(BASE_DIR, 'bot_tokens.csv'), 'r', encoding='utf-8-sig') as f:
            for row in _csv.DictReader(f):
                if row.get('description') == 'otp_bot' and row.get('is_active') == 'yes':
                    otp_token = row.get('token', '')
                    break
    except:
        pass

    if otp_token:
        import urllib.request as _u
        try:
            msg = f"🔐 <b>رمز دخول موقع VEX</b>\n\n<code>{code}</code>\n\n⏰ صالح لمدة 5 دقائق\n🌐 أدخل الرمز في: https://vex.deals"
            _u.urlopen(_u.Request(
                f'https://api.telegram.org/bot{otp_token}/sendMessage',
                data=_json.dumps({'chat_id': int(tg_id), 'text': msg, 'parse_mode': 'HTML'}).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            ), timeout=10)
        except Exception as e:
            # If bot can't send (user hasn't started bot yet), still return success
            # User can use the code if they open the bot manually
            pass

    # Get bot username for response
    bot_name = 'VEX_OTP_bot'
    try:
        if otp_token:
            resp = urllib.request.urlopen(
                f'https://api.telegram.org/bot{otp_token}/getMe', timeout=5)
            info = json.loads(resp.read().decode())
            if info.get('ok'):
                bot_name = info['result'].get('username', bot_name)
    except:
        pass

    return jsonify({'success': True, 'bot': bot_name})

@app.route('/api/web/auth-code', methods=['POST'])
def api_web_auth_code():
    """Validate Telegram auth code from landing page."""
    import random as _r, time as _t
    data = request.json or {}
    code = str(data.get('code', '')).strip()
    if not code or len(code) != 6 or not code.isdigit():
        return jsonify({'error': 'الرمز يجب أن يكون 6 أرقام'}), 400

    # Check auth codes file (created by bot)
    auth_file = os.path.join(BASE_DIR, 'web_auth_codes.json')
    try:
        import json as _json
        if os.path.exists(auth_file):
            with open(auth_file, 'r') as f:
                codes = _json.load(f)
        else:
            codes = {}
        # Find matching code
        for uid, code_data in codes.items():
            if str(code_data.get('code', '')) == code:
                # Check expiry (5 min)
                if _t.time() - code_data.get('created', 0) > 300:
                    return jsonify({'error': 'انتهت صلاحية الرمز — اطلب رمزاً جديداً'}), 400
                # Create web session
                session['admin_id'] = uid
                session['admin_name'] = code_data.get('name', 'User')
                session['logged_in'] = True
                session['login_time'] = _t.time()
                session.permanent = True  # Persistent — 365 days
                session['is_admin'] = uid in ADMIN_IDS
                session['phone'] = code_data.get('phone', '')
                # Check if user is registered in bot (users.csv)
                import csv as _csv
                is_registered = False
                try:
                    with open(os.path.join(BASE_DIR, 'users.csv'), 'r', encoding='utf-8-sig') as f:
                        for row in _csv.DictReader(f):
                            if row.get('telegram_id') == str(uid):
                                is_registered = True
                                break
                except:
                    pass
                session['is_registered'] = is_registered
                # Remove used code
                del codes[uid]
                with open(auth_file, 'w') as f:
                    _json.dump(codes, f)
                # Admin → dashboard, regular user → home page
                redirect_url = '/dashboard' if session['is_admin'] else '/home'
                return jsonify({'success': True, 'redirect': redirect_url, 'registered': is_registered})
        return jsonify({'error': 'رمز غير صالح'}), 400
    except Exception as e:
        return jsonify({'error': 'خطأ في الخادم'}), 500

@app.route('/vex/admin/admin', methods=['GET', 'POST'])
def admin_login():
    """Admin login page — only at /vex/admin/admin"""
    error = None
    if request.method == 'POST':
        # ── IP-based brute-force protection ──────────────────────────────
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
        if _login_rate_limited(client_ip):
            error = 'محاولات كثيرة — انتظر دقيقة وحاول مجدداً'
            return render_template('login.html', error=error), 429

        admin_id = request.form.get('admin_id', '').strip()
        password = request.form.get('password', '')
        if admin_id in ADMIN_IDS and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['admin_id'] = admin_id
            session['is_admin'] = True
            session['login_time'] = datetime.now().isoformat()
            session.permanent = True
            log_action('login', f'Admin {admin_id} logged in from {client_ip}')
            return redirect(url_for('dashboard'), code=303)
        elif admin_id not in ADMIN_IDS:
            error = 'معرف الأدمن غير صحيح'
        else:
            error = 'كلمة المرور غير صحيحة'
    return render_template('login.html', error=error)

@app.route('/login')
def login_redirect():
    """Redirect /login to admin login page"""
    return redirect(url_for('admin_login'))

@app.route('/logout')
def logout():
    was_admin = session.get('is_admin', False)
    log_action('logout', '')
    session.clear()
    # Admin → admin login page, regular user → landing page
    if was_admin:
        return redirect(url_for('admin_login'))
    return redirect(url_for('index'))

@app.route('/dashboard')
@admin_required
def dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('home'), code=303)
    return render_template('dashboard.html', active_page='dashboard')

@app.route('/home')
@login_required
def home():
    """User home page — shows all bot features as web interface"""
    uid = session.get('admin_id', '')
    user_name = session.get('admin_name', 'User')
    # Get user data
    user_balance = 0
    user_currency = 'EGP'
    try:
        if _VEX_GAMES:
            user_balance = _gm.get_balance(uid) or 0
            user_info = _gm.get_user_info(uid) or {}
            user_currency = user_info.get('currency', 'EGP')
    except: pass

    # Auth note: the Flask session cookie (set at login, HttpOnly) is automatically
    # sent with all /webapp/* API calls from the browser.  webapp_auth reads
    # session['admin_id'] as a trusted identity, so no URL token is needed here.
    return render_template('home.html', active_page='home', user_name=user_name,
                         user_balance=user_balance, user_currency=user_currency, uid=uid)

@app.route('/transactions')
@admin_required
@page_permission_required('view_financial')
def page_transactions():
    return render_template('transactions.html', active_page='transactions')

@app.route('/users')
@admin_required
@page_permission_required('ban_users')
def page_users():
    return render_template('users.html', active_page='users')

@app.route('/matching')
@admin_required
@page_permission_required('view_financial')
def page_matching():
    return render_template('matching.html', active_page='matching')

@app.route('/svrp')
@admin_required
@page_permission_required('view_financial')
def page_svrp():
    return render_template('svrp.html', active_page='svrp')

@app.route('/trading')
@admin_required
@page_permission_required('view_financial')
def page_trading():
    return render_template('trading.html', active_page='trading')

@app.route('/lottery')
@admin_required
@page_permission_required('manage_games')
def page_lottery():
    return render_template('lottery.html', active_page='lottery')

@app.route('/wheel')
@admin_required
@page_permission_required('manage_games')
def page_wheel():
    return render_template('wheel.html', active_page='wheel')

@app.route('/webapp/snatch')
def webapp_snatch():
    """لعبة Snatch الأركيد — الإصدار الجديد مع نظام رهان حقيقي"""
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    return render_template('snatch.html', uid=uid, lang=lang)

@app.route('/webapp/snatch-gifts')
def webapp_snatch_gifts():
    """صفحة لعبة اختطف القديمة — هدايا تابعة"""
    gifts = []
    try:
        with open('wheel_gifts.csv', 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('is_active') == 'yes':
                    gifts.append({'id': row.get('id',''), 'text': row.get('gift_text',''), 'link': row.get('affiliate_link','')})
    except:
        pass
    return render_template('snatch_game.html', gifts_json=json.dumps(gifts))

@app.route('/api/wheel/my-spins')
@api_auth
def api_wheel_my_spins():
    """عدد دورات المستخدم في جولة محددة"""
    round_id = request.args.get('round_id', '')
    # محاولة الحصول على user_id من session
    admin_id = session.get('admin_id', '')
    spins = read_csv('wheel_spins.csv')
    user_spins = [s for s in spins if s.get('round_id') == round_id]
    return jsonify({
        'total_spins': len(user_spins),
        'spins': user_spins[-10:]
    })

@app.route('/companies')
@admin_required
@page_permission_required('manage_companies')
def page_companies():
    return render_template('companies.html', active_page='companies')

@app.route('/payment-methods')
@admin_required
@page_permission_required('manage_companies')
def page_payment_methods():
    return render_template('payment_methods.html', active_page='payment_methods')

@app.route('/apps')
@admin_required
@page_permission_required('manage_companies')
def page_apps():
    return render_template('apps.html', active_page='apps')

@app.route('/referrals')
@admin_required
@page_permission_required('manage_companies')
def page_referrals():
    return render_template('referrals.html', active_page='referrals')

@app.route('/channels')
@admin_required
@page_permission_required('send_broadcast')
def page_channels():
    return render_template('channels.html', active_page='channels')

@app.route('/bots')
@admin_required
@page_permission_required('manage_bots')
def page_bots():
    return render_template('bots.html', active_page='bots')

@app.route('/settings')
@admin_required
@page_permission_required('manage_settings')
def page_settings():
    return render_template('settings.html', active_page='settings')

@app.route('/seo')
@admin_required
@page_permission_required('manage_settings')
def page_seo():
    """صفحة إدارة SEO وتحسين محركات البحث"""
    # قراءة إعدادات SEO الحالية من system_settings.csv
    import csv as _csv
    seo_settings = {}
    try:
        with open(os.path.join(BASE_DIR, 'system_settings.csv'), 'r', encoding='utf-8-sig') as f:
            for row in _csv.DictReader(f):
                key = row.get('key', '')
                if key.startswith('seo_') or key.startswith('og_') or key.startswith('twitter_'):
                    seo_settings[key] = row.get('value', '')
    except:
        pass
    return render_template('seo.html', active_page='seo', seo_settings=seo_settings)

@app.route('/api/seo/save', methods=['POST'])
@admin_required
@page_permission_required('manage_settings')
def api_seo_save():
    """حفظ إعدادات SEO"""
    import csv as _csv
    data = request.json or {}
    # قراءة الإعدادات الحالية
    settings_file = os.path.join(BASE_DIR, 'system_settings.csv')
    existing = {}
    fieldnames = ['key', 'value', 'updated_at']
    try:
        if os.path.exists(settings_file):
            with open(settings_file, 'r', encoding='utf-8-sig') as f:
                reader = _csv.DictReader(f)
                fieldnames = reader.fieldnames or fieldnames
                for row in reader:
                    existing[row.get('key', '')] = row.get('value', '')
    except:
        pass
    # تحديث قيم SEO
    seo_keys = ['seo_title', 'seo_description', 'seo_keywords', 'seo_robots',
                'og_title', 'og_description', 'og_image', 'og_url',
                'twitter_card', 'twitter_title', 'twitter_description', 'twitter_image',
                'seo_canonical', 'seo_author', 'seo_language']
    for key in seo_keys:
        if key in data:
            existing[key] = data[key]
    # كتابة الملف
    try:
        with open(settings_file, 'w', newline='', encoding='utf-8-sig') as f:
            writer = _csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for k, v in existing.items():
                writer.writerow({'key': k, 'value': v, 'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'success': True})

@app.route('/complaints')
@admin_required
@page_permission_required('ban_users')
def page_complaints():
    return render_template('complaints.html', active_page='complaints')

@app.route('/broadcast')
@admin_required
@page_permission_required('send_broadcast')
def page_broadcast():
    return render_template('broadcast.html', active_page='broadcast')

@app.route('/admins')
@admin_required
@page_permission_required('manage_admins')
def page_admins():
    return render_template('admin_management.html', active_page='admins')

@app.route('/themes')
@admin_required
@page_permission_required('manage_settings')
def page_themes():
    return render_template('themes.html', active_page='themes')

@app.route('/exchange-addresses')
@admin_required
@page_permission_required('manage_settings')
def page_exchange_addresses():
    return render_template('exchange_addresses.html', active_page='exchange_addresses')

@app.route('/send-message')
@admin_required
@page_permission_required('send_broadcast')
def page_send_message():
    return render_template('send_message.html', active_page='send_message')

@app.route('/backup')
@admin_required
@page_permission_required('manage_admins')
def page_backup():
    return render_template('backup.html', active_page='backup')

@app.route('/statistics')
@admin_required
@page_permission_required('view_statistics')
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

@app.route('/api/notifications/stream')
@api_auth
def api_notifications_stream():
    """SSE stream for real-time deposit/withdrawal notifications."""
    q = _queue.Queue()
    with _nq_lock:
        _notification_queues.append(q)
    def generate():
        import time
        # Send initial connection confirmation
        yield f"data: {json.dumps({'type': 'connected', 'message': 'Connected'})}\n\n"
        while True:
            try:
                payload = q.get(timeout=15)
                yield f"data: {payload}\n\n"
            except _queue.Empty:
                # Heartbeat to keep connection alive
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
    try:
        return Response(generate(), mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
    finally:
        with _nq_lock:
            if q in _notification_queues:
                _notification_queues.remove(q)

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

    # ── Merge: include VEX quick_deposits that are missing from transactions.csv ──
    # Match by user_id + amount + date (not just ID, because formats differ)
    try:
        qd_path = os.path.join(BASE_DIR, 'quick_deposits.csv')
        if os.path.exists(qd_path):
            # Build a set of (telegram_id, amount, date) for existing transactions
            existing_keys = set()
            for t in txns:
                _k = (str(t.get('telegram_id','')), str(t.get('amount','')), str(t.get('date',''))[:10])
                existing_keys.add(_k)

            with open(qd_path, 'r', encoding='utf-8-sig') as f:
                for qrow in csv.DictReader(f):
                    qid = qrow.get('id','')
                    qstatus = qrow.get('status','')
                    quid = qrow.get('user_id','')
                    qamt = qrow.get('amount','0')
                    qdate = qrow.get('created_at','')
                    # Skip if already exists in transactions.csv (match by uid+amount+date)
                    _key = (str(quid), str(qamt), str(qdate)[:10])
                    if _key in existing_keys:
                        continue
                    # Only merge if not already in txns by ID too
                    if qid and any(t.get('id','') == qid for t in txns):
                        continue
                    txns.append({
                        'id': qid,
                        'customer_id': '',
                        'telegram_id': quid,
                        'name': '',
                        'type': 'withdraw' if 'withdrawal' in qstatus else 'deposit',
                        'company': 'VEX Wallet',
                        'wallet_number': qrow.get('account_number',''),
                        'amount': qamt,
                        'exchange_address': '',
                        'status': qstatus,
                        'date': qdate,
                        'admin_note': 'إيداع محفظة VEX' if 'withdrawal' not in qstatus else 'سحب محفظة VEX',
                        'processed_by': qrow.get('approved_by',''),
                        'currency': '',
                    })
                    existing_keys.add(_key)  # prevent duplicate merges
    except Exception as e:
        print(f"Merge quick_deposits error: {e}")

    # Sort by date descending (newest first) — NOT reverse(), which is unreliable with mixed sources
    txns.sort(key=lambda t: t.get('date', ''), reverse=True)

    if status:
        if status == 'pending':
            txns = [t for t in txns if t.get('status') in ('pending', 'pending_withdrawal', 'pending_code_verification', 'awaiting_admin_review')]
        elif status == 'approved':
            txns = [t for t in txns if t.get('status') in ('approved', 'completed', 'code_verified', 'admin_received', 'transfer_confirmed')]
        elif status == 'rejected':
            txns = [t for t in txns if t.get('status') in ('rejected', 'auto_rejected', 'withdrawal_rejected', 'withdrawal_auto_rejected', 'cancelled')]
        else:
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
        'pending_count': sum(1 for t in txns if t.get('status') in ('pending', 'pending_withdrawal', 'pending_code_verification', 'awaiting_admin_review')),
        'approved_volume': sum(float(t.get('amount', 0) or 0) for t in txns if t.get('status') in ('approved', 'completed', 'code_verified')),
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
@permission_required('approve_deposits')
def api_approve_txn(txn_id):
    data = request.json or {}
    new_amount = data.get('amount', '')
    txns = read_csv('transactions.csv')
    fieldnames = get_fieldnames('transactions.csv', ['id','customer_id','telegram_id','name','type','company','wallet_number','amount','exchange_address','status','date','admin_note','processed_by','currency'])
    old_amount = ''
    customer_tid = ''
    trans = None
    was_pending = False   # True only when this call actually transitions pending→approved
    for t in txns:
        if t.get('id') == txn_id:
            old_amount    = t.get('amount', '')
            customer_tid  = t.get('telegram_id', '')
            old_status    = t.get('status', '')
            trans = t
            if old_status != 'approved':          # guard: only transition once
                was_pending = (old_status == 'pending')
                t['status'] = 'approved'
                t['processed_by'] = session.get('admin_id', '')
                if new_amount:
                    t['amount'] = str(new_amount)
            break
    write_csv('transactions.csv', txns, fieldnames)
    log_action('approve_transaction', f'{txn_id} amount: {old_amount} -> {new_amount or old_amount}')
    # Increment wagering ONLY on a genuine pending→approved transition
    if was_pending and customer_tid:
        try:
            import sys as _sw; _sw.path.insert(0, BASE_DIR)
            from svrp import SVRPManager as _SM_w
            _SM_w().increment_wagering(str(customer_tid))
        except Exception:
            pass  # non-fatal: wagering update best-effort
    # VEX deposit: async add balance + notify player (non-blocking)
    if trans and 'VEX' in trans.get('admin_note', ''):
        import threading as _th
        # Capture all values BEFORE starting thread (session is thread-local)
        _uid = trans.get('telegram_id', '')
        _amt = float(new_amount or old_amount or 0)
        _txn = txn_id
        _admin = session.get('admin_id', '')
        def _vex_bg():
            try:
                if _VEX_GAMES and _uid and _amt > 0:
                    _gm.add_balance(_uid, _amt)
                    # Update quick_deposits.csv
                    try:
                        import csv as _csv2
                        _rows = []
                        _qd = os.path.join(BASE_DIR, 'quick_deposits.csv')
                        with open(_qd, 'r', encoding='utf-8-sig') as _f:
                            _r = _csv2.DictReader(_f)
                            _fn = _r.fieldnames
                            _rows = list(_r)
                        for _row in _rows:
                            if _row.get('user_id') == str(_uid) and _row.get('status') == 'pending':
                                _row['status'] = 'approved'
                                _row['approved_by'] = str(_admin)
                                _row['approved_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        with open(_qd, 'w', newline='', encoding='utf-8-sig') as _f:
                            _w = _csv2.DictWriter(_f, fieldnames=_fn)
                            _w.writeheader()
                            _w.writerows(_rows)
                    except: pass
                    # Telegram notify
                    if BOT_TOKEN:
                        try:
                            import urllib.request as _u2
                            _msg = f"✅ تمت الموافقة على إيداعك!\n\n💰 المبلغ: {_amt:.0f}\n🎮 تم إضافته لمحفظة VEX\n🆔 {_txn}"
                            _u2.urlopen(_u2.Request(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                                data=json.dumps({'chat_id': int(_uid), 'text': _msg, 'parse_mode': 'HTML'}).encode('utf-8'),
                                headers={'Content-Type': 'application/json'}), timeout=5)
                        except: pass
                    push_notification('vex_deposit', '✅ إيداع VEX', f'{_uid}: {_amt}', {'uid': _uid, 'amount': _amt})
            except Exception as _e:
                print(f"VEX bg error: {_e}")
        _th.Thread(target=_vex_bg, daemon=True).start()
    return jsonify({'success': True, 'old_amount': old_amount, 'new_amount': new_amount or old_amount})

@app.route('/api/transactions/<txn_id>/reject', methods=['POST'])
@api_auth
@permission_required('reject_deposits')
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
    # Sync matching quick_deposits (VEX) -> rejected
    try:
        import csv as _qcsv
        _qp = os.path.join(BASE_DIR, 'quick_deposits.csv')
        if os.path.exists(_qp):
            with open(_qp, 'r', encoding='utf-8-sig') as _f:
                _r = _qcsv.DictReader(_f); _fn = _r.fieldnames; _rows = list(_r)
            _changed = False
            for _row in _rows:
                if _row.get('id') == txn_id or (_row.get('user_id') and txn_id.startswith(('DEP','WTH')) and _row.get('id') == txn_id):
                    if _row.get('status') in ('pending','pending_withdrawal'):
                        _row['status'] = 'rejected' if _row.get('status')=='pending' else 'withdrawal_rejected'
                        _row['processed_by'] = session.get('admin_id','')
                        _changed = True
            if _changed:
                with open(_qp, 'w', newline='', encoding='utf-8-sig') as _f:
                    _w = _qcsv.DictWriter(_f, fieldnames=_fn); _w.writeheader(); _w.writerows(_rows)
    except: pass
    log_action('reject_transaction', f'{txn_id}: {reason}')
    return jsonify({'success': True})

@app.route('/api/transactions/bulk-approve', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_bulk_approve():
    ids = request.json.get('ids', []) if request.json else []
    txns = read_csv('transactions.csv')
    fieldnames = get_fieldnames('transactions.csv', ['id','customer_id','telegram_id','name','type','company','wallet_number','amount','exchange_address','status','date','admin_note','processed_by','currency'])
    count = 0
    newly_approved_tids = []   # telegram_ids that actually transitioned pending→approved
    for t in txns:
        if t.get('id') in ids:
            old_st = t.get('status', '')
            if old_st != 'approved':             # guard: only transition once
                if old_st == 'pending' and t.get('telegram_id'):
                    newly_approved_tids.append(str(t['telegram_id']))
                t['status'] = 'approved'
                t['processed_by'] = session.get('admin_id', '')
                count += 1
    write_csv('transactions.csv', txns, fieldnames)
    log_action('bulk_approve', f'{count} transactions')
    # Increment wagering ONLY for users whose status actually changed pending→approved
    if newly_approved_tids:
        try:
            import sys as _sbw; _sbw.path.insert(0, BASE_DIR)
            from svrp import SVRPManager as _SM_bw
            _sm_bw = _SM_bw()
            for _tid in newly_approved_tids:
                try:
                    _sm_bw.increment_wagering(_tid)
                except Exception:
                    pass
        except Exception:
            pass
    return jsonify({'success': True, 'count': count})

@app.route('/api/transactions/bulk-reject', methods=['POST'])
@api_auth
@permission_required('reject_deposits')
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

# ===== Pending Requests: unified view (transactions + VEX deposits + withdrawals) =====
@app.route('/api/pending-requests')
@api_auth
def api_pending_requests():
    """جميع الطلبات المعلقة في صفحة واحدة: إيداع + سحب + إيداع VEX.
    عند الموافقة/الرفض يتحول تلقائياً للسجلات ويختفي من هنا."""
    import csv as _csv
    from datetime import datetime as _dt
    all_pending = []

    # 1) Main transactions (deposits + withdrawals pending)
    try:
        with open(os.path.join(BASE_DIR, 'transactions.csv'), 'r', encoding='utf-8-sig') as f:
            for row in _csv.DictReader(f):
                if row.get('status') == 'pending':
                    all_pending.append({
                        'id': row.get('id',''),
                        'name': row.get('name',''),
                        'telegram_id': row.get('telegram_id',''),
                        'customer_id': row.get('customer_id',''),
                        'type': row.get('type','deposit'),
                        'company': row.get('company',''),
                        'wallet': row.get('wallet_number',''),
                        'amount': row.get('amount','0'),
                        'currency': row.get('currency',''),
                        'status': 'pending',
                        'date': row.get('date',''),
                        'source': 'transactions',
                        'age_hours': _calc_age_hours(row.get('date','')),
                    })
    except: pass

    # 2) VEX quick deposits pending
    try:
        qd_path = os.path.join(BASE_DIR, 'quick_deposits.csv')
        if os.path.exists(qd_path):
            with open(qd_path, 'r', encoding='utf-8-sig') as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    st = row.get('status','')
                    if st in ('pending','pending_withdrawal'):
                        all_pending.append({
                            'id': row.get('id',''),
                            'name': '',
                            'telegram_id': row.get('user_id',''),
                            'customer_id': '',
                            'type': 'deposit' if st=='pending' else 'withdraw',
                            'company': 'VEX Wallet',
                            'wallet': row.get('account_number',''),
                            'amount': row.get('amount','0'),
                            'currency': '',
                            'status': st,
                            'date': row.get('created_at',''),
                            'source': 'vex_deposits',
                            'age_hours': _calc_age_hours(row.get('created_at','')),
                        })
    except: pass

    # Sort by date (newest first)
    all_pending.sort(key=lambda x: x.get('date',''), reverse=True)
    return jsonify({'pending': all_pending, 'count': len(all_pending)})

def _calc_age_hours(date_str):
    """Calculate age in hours from a date string."""
    try:
        dt = _dt.strptime(date_str.strip(), '%Y-%m-%d %H:%M:%S')
    except:
        try:
            dt = _dt.strptime(date_str.strip(), '%Y-%m-%d %H:%M')
        except:
            return 0
    return round((_dt.now() - dt).total_seconds() / 3600, 1)

# ===== Auto-reject old pending deposits =====
import threading
import time as _ar_time
_AR_TIMEOUT_HOURS = 3  # auto-reject after 3 hours
def _auto_reject_old_pending():
    """Background thread: auto-reject pending deposits older than timeout."""
    import csv as _csv
    while True:
        try:
            # Check quick_deposits
            qd_path = os.path.join(BASE_DIR, 'quick_deposits.csv')
            if os.path.exists(qd_path):
                with open(qd_path, 'r', encoding='utf-8-sig') as f:
                    _r = _csv.DictReader(f); _fn = _r.fieldnames; _rows = list(_r)
                _changed = False
                for row in _rows:
                    st = row.get('status','')
                    if st in ('pending','pending_withdrawal'):
                        age = _calc_age_hours(row.get('created_at',''))
                        if age > _AR_TIMEOUT_HOURS:
                            row['status'] = 'auto_rejected' if st=='pending' else 'withdrawal_auto_rejected'
                            _changed = True
                if _changed:
                    with open(qd_path, 'w', newline='', encoding='utf-8-sig') as f:
                        _w = _csv.DictWriter(f, fieldnames=_fn); _w.writeheader(); _w.writerows(_rows)
        except: pass
        try:
            # Check main transactions
            tx_path = os.path.join(BASE_DIR, 'transactions.csv')
            if os.path.exists(tx_path):
                with open(tx_path, 'r', encoding='utf-8-sig') as f:
                    _r = _csv.DictReader(f); _fn = _r.fieldnames; _rows = list(_r)
                _changed = False
                for row in _rows:
                    if row.get('status') == 'pending':
                        age = _calc_age_hours(row.get('date',''))
                        if age > _AR_TIMEOUT_HOURS:
                            row['status'] = 'auto_rejected'
                            row['admin_note'] = f'تم الرفض التلقائي بعد {age:.0f} ساعة'
                            _changed = True
                if _changed:
                    with open(tx_path, 'w', newline='', encoding='utf-8-sig') as f:
                        _w = _csv.DictWriter(f, fieldnames=_fn); _w.writeheader(); _w.writerows(_rows)
        except: pass
        _ar_time.sleep(600)  # check every 10 minutes

_ar_time.sleep(3)  # wait for app to start
_ar_thread_ = threading.Thread(target=_auto_reject_old_pending, daemon=True)
_ar_thread_.start()

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
@permission_required('ban_users')
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
    _rbac_log(str(session.get('admin_id', '')), 'ban_user', target=user_id,
              details=reason, ip=request.remote_addr)
    return jsonify({'success': True})

@app.route('/api/users/<user_id>/unban', methods=['POST'])
@api_auth
@permission_required('unban_users')
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
    _rbac_log(str(session.get('admin_id', '')), 'unban_user', target=user_id,
              details='unbanned', ip=request.remote_addr)
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


# ===== API — Icon Upload (companies & payment methods) =====
_ICON_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', 'icons')
_ICON_ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
_ICON_MAX_BYTES = 2 * 1024 * 1024  # 2MB

@app.route('/api/upload-icon', methods=['POST'])
@api_auth
@permission_required('manage_companies')
def api_upload_icon():
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'error': 'لم يتم اختيار ملف'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in _ICON_ALLOWED_EXT:
        return jsonify({'success': False, 'error': 'صيغة غير مدعومة — المسموح: PNG, JPG, WEBP, GIF'}), 400
    blob = f.read(_ICON_MAX_BYTES + 1)
    if len(blob) > _ICON_MAX_BYTES:
        return jsonify({'success': False, 'error': 'حجم الملف أكبر من 2MB'}), 400
    # Magic-byte sanity check (blocks disguised HTML/SVG/script uploads)
    _magic_ok = (blob[:8] == b'\x89PNG\r\n\x1a\n' or blob[:3] == b'\xff\xd8\xff'
                 or blob[:6] in (b'GIF87a', b'GIF89a')
                 or (blob[:4] == b'RIFF' and blob[8:12] == b'WEBP'))
    if not _magic_ok:
        return jsonify({'success': False, 'error': 'الملف ليس صورة صالحة'}), 400
    os.makedirs(_ICON_UPLOAD_DIR, exist_ok=True)
    fname = f"icon_{secrets.token_hex(8)}.{ext}"
    with open(os.path.join(_ICON_UPLOAD_DIR, fname), 'wb') as out:
        out.write(blob)
    log_action('upload_icon', fname)
    return jsonify({'success': True, 'url': f'/static/uploads/icons/{fname}'})

@app.route('/api/companies/list')
def api_companies_public():
    """Public companies list for user home page — no admin auth required."""
    companies = read_csv('companies.csv')
    result = []
    for c in companies:
        # Accept 'yes', 'active', or empty as active
        active = c.get('is_active', '').lower()
        if active in ('yes', 'active', 'true', '1', ''):
            result.append({
                'id': c.get('id', ''),
                'name': c.get('name', ''),
                'icon': c.get('icon', '🏢'),
                'address': c.get('address', ''),
                'type': c.get('type', ''),
            })
    return jsonify({'companies': result})

@app.route('/api/payment-methods/by-company/<company_id>')
def api_payment_methods_by_company(company_id):
    """Payment methods for a specific company — public, no admin auth."""
    methods = read_csv('payment_methods.csv')
    # Also check company_payment_links.csv if exists
    linked = []
    try:
        links = read_csv('company_payment_links.csv')
        linked_ids = [l.get('payment_method_id', '') for l in links if l.get('company_id', '') == company_id]
    except:
        linked_ids = []
    result = []
    for m in methods:
        if m.get('status') == 'active':
            # Match by company_id or linked_ids
            if m.get('company_id', '') == company_id or m.get('id', '') in linked_ids or not m.get('company_id', ''):
                result.append({
                    'id': m.get('id', ''),
                    'method_name': m.get('method_name', ''),
                    'method_type': m.get('method_type', ''),
                    'account_data': m.get('account_data', ''),
                    'icon': m.get('icon', '💳'),
                })
    return jsonify({'methods': result, 'count': len(result)})

@app.route('/api/companies', methods=['POST'])
@api_auth
@permission_required('manage_companies')
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
@permission_required('manage_companies')
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
@permission_required('manage_companies')
def api_add_payment_method():
    data = request.json
    methods = read_csv('payment_methods.csv')
    fieldnames = get_fieldnames('payment_methods.csv', ['id','company_id','method_name','method_type','account_data','additional_info','status','created_date','icon','available_for_games','currency'])
    for extra in ('available_for_games', 'currency'):
        if extra not in fieldnames:
            fieldnames.append(extra)
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
        'icon': data.get('icon', '💳'),
        'available_for_games': 'yes' if data.get('available_for_games', 'yes') in ('yes', True, 'true', '1') else 'no',
        'currency': data.get('currency', '')
    }
    append_csv('payment_methods.csv', new_method, fieldnames)
    log_action('add_payment_method', new_id)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/payment-methods/<method_id>', methods=['PUT', 'DELETE'])
@api_auth
@permission_required('manage_companies')
def api_edit_payment_method(method_id):
    methods = read_csv('payment_methods.csv')
    fieldnames = get_fieldnames('payment_methods.csv', ['id','company_id','method_name','method_type','account_data','additional_info','status','created_date','icon','available_for_games','currency'])
    for extra in ('available_for_games', 'currency'):
        if extra not in fieldnames:
            fieldnames.append(extra)

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
@permission_required('manage_companies')
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
@permission_required('approve_deposits')
def api_svrp_approve(req_id):
    """Approve a recovery request and credit the user's frozen SVRP wallet.

    Uses credit_svrp_balance_for_approval which atomically credits the
    svrp_wallet_balance SQLite table and records the approval in
    svrp_approval_log in a single SAVEPOINT — no cross-store inconsistency.

    Idempotency: svrp_approval_log has req_id as PRIMARY KEY; duplicate
    approvals of the same request return success without re-crediting.

    The recovery_requests.csv status update is best-effort (display only);
    the SQLite record is the authoritative source of truth.
    """
    import sys as _sys_svrp; _sys_svrp.path.insert(0, BASE_DIR)
    from svrp import SVRPManager as _SvrpMgr

    raw_amount = request.json.get('amount', '0') if request.json else '0'
    try:
        amount_float = float(raw_amount)
        if not math.isfinite(amount_float) or amount_float <= 0:
            return jsonify({'error': 'المبلغ غير صالح'}), 400
    except (TypeError, ValueError):
        return jsonify({'error': 'المبلغ غير صالح — يجب أن يكون رقماً'}), 400

    # Identify the user this request belongs to (from CSV, for display lookup)
    import sys as _sys_r; _sys_r.path.insert(0, BASE_DIR)
    reqs = read_csv('recovery_requests.csv')
    req_row = next((r for r in reqs if r.get('id') == req_id), None)
    if not req_row:
        return jsonify({'error': 'الطلب غير موجود'}), 404
    uid = str(req_row.get('user_id', ''))
    if not uid:
        return jsonify({'error': 'لا يمكن تحديد مستخدم الطلب'}), 400

    # Step 1: Atomic SQLite credit + approval log in one SAVEPOINT
    try:
        ok, result = _gm.credit_svrp_balance_for_approval(req_id, uid, amount_float)
    except Exception as _ae:
        return jsonify({'error': f'خطأ في تسجيل الموافقة: {_ae}'}), 500
    if not ok:
        return jsonify({'error': result or 'فشل الموافقة'}), 400

    # Step 2: Best-effort CSV status update (display only; not authoritative)
    admin_id = session.get('admin_id', 'unknown')
    _SvrpMgr().approve_recovery_request(req_id, amount_float, admin_id)

    log_action('svrp_approve', f'{req_id}: {amount_float} uid={uid}')
    return jsonify({'success': True, 'new_frozen_balance': result})

@app.route('/api/svrp/requests/<req_id>/reject', methods=['POST'])
@api_auth
@permission_required('reject_deposits')
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
@permission_required('approve_deposits')
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
@permission_required('reject_deposits')
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
@permission_required('manage_companies')
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
    # Normalize: ensure every row has all expected keys (prevents None values from old CSV rows)
    _app_fields = ['id','name','icon_url','icon_file_id','android_url','android_file_id','ios_url','ios_file_id','download_url','promo_code','referral_link','description','is_active','created_at']
    clean = []
    for a in apps:
        row = {}
        for f in _app_fields:
            row[f] = a.get(f) or ''
        clean.append(row)
    return jsonify({'apps': clean})

@app.route('/api/apps/public')
def api_apps_public():
    """Public apps list for user home page — no admin auth required."""
    apps = read_csv('app_links.csv')
    _app_fields = ['id','name','icon_url','icon_file_id','android_url','android_file_id','ios_url','ios_file_id','download_url','promo_code','referral_link','description','is_active','created_at']
    clean = []
    for a in apps:
        active = str(a.get('is_active', '')).lower()
        if active in ('yes', 'true', '1', 'active'):
            row = {}
            for f in _app_fields:
                row[f] = a.get(f) or ''
            clean.append(row)
    return jsonify({'apps': clean})

# ===== Public endpoints for user home page =====

@app.route('/api/referrals/public')
def api_referrals_public():
    """Public referral links for user home page."""
    links = read_csv('referral_links.csv')
    clean = []
    for l in links:
        if str(l.get('is_active', '')).lower() in ('yes', 'true', '1', 'active', ''):
            clean.append({'name': l.get('name', ''), 'url': l.get('url', '')})
    return jsonify({'links': clean})

@app.route('/api/channels/public')
def api_channels_public():
    """Public active channels for user home page."""
    chans = read_csv('channels.csv')
    clean = []
    for c in chans:
        if str(c.get('is_active', '')).lower() in ('yes', 'true', '1', 'active', ''):
            clean.append({
                'title': c.get('title', c.get('name', '')),
                'chat_id': c.get('chat_id', ''),
                'username': c.get('username', ''),
                'description': c.get('description', ''),
            })
    return jsonify({'channels': clean})

@app.route('/api/trading/public')
def api_trading_public():
    """Public trading info — just shows it's available + link to bot."""
    settings = read_csv('system_settings.csv')
    usdt_rate = ''
    for s in settings:
        if s.get('key') == 'usdt_rate':
            usdt_rate = s.get('value', '')
            break
    return jsonify({
        'available': True,
        'usdt_rate': usdt_rate,
        'bot_url': 'https://t.me/' + (BOT_TOKEN.split(':')[0] if BOT_TOKEN else ''),
        'message': 'لبدء التداول، افتح البوت واختر 💱 تداول USDT'
    })

@app.route('/api/support/public')
def api_support_public():
    """Public support settings for user home page."""
    settings = read_csv('system_settings.csv')
    support_text = ''
    support_url = ''
    for s in settings:
        if s.get('key') == 'support_text':
            support_text = s.get('value', '')
        if s.get('key') == 'support_url':
            support_url = s.get('value', '')
    if not support_url:
        support_url = 'https://t.me/' + (BOT_TOKEN.split(':')[0] if BOT_TOKEN else '')
    return jsonify({
        'support_text': support_text or 'للحصول على دعم سريع، تواصل معنا عبر تيليغرام',
        'support_url': support_url
    })

@app.route('/api/apps', methods=['POST'])
@api_auth
@permission_required('manage_companies')
def api_add_app():
    data = request.json
    apps = read_csv('app_links.csv')
    fieldnames = get_fieldnames('app_links.csv', ['id','name','icon_url','icon_file_id','android_url','android_file_id','ios_url','ios_file_id','download_url','promo_code','referral_link','description','is_active','created_at'])
    new_id = f"APP{str(int(datetime.now().timestamp()))[-6:]}"
    new_app = {
        'id': new_id,
        'name': data.get('name', ''),
        'icon_url': data.get('icon_url', ''),
        'icon_file_id': data.get('icon_file_id', ''),
        'android_url': data.get('android_url', ''),
        'android_file_id': data.get('android_file_id', ''),
        'ios_url': data.get('ios_url', ''),
        'ios_file_id': data.get('ios_file_id', ''),
        'download_url': data.get('download_url', ''),
        'promo_code': data.get('promo_code', ''),
        'referral_link': data.get('referral_link', ''),
        'description': data.get('description', ''),
        'is_active': 'yes',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    append_csv('app_links.csv', new_app, fieldnames)
    log_action('add_app', new_id)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/apps/<app_id>', methods=['PUT', 'DELETE'])
@api_auth
@permission_required('manage_companies')
def api_edit_app(app_id):
    apps = read_csv('app_links.csv')
    fieldnames = get_fieldnames('app_links.csv', ['id','name','icon_url','icon_file_id','android_url','android_file_id','ios_url','ios_file_id','download_url','promo_code','referral_link','description','is_active','created_at'])

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
@permission_required('manage_companies')
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
@permission_required('manage_companies')
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

# ===== API — Campaigns (Ad Platform Phase 1) =====

@app.route('/api/campaigns')
@api_auth
def api_campaigns():
    """List all campaigns."""
    campaigns = read_csv('campaigns.csv')
    campaigns.reverse()
    # Normalize fields
    for c in campaigns:
        for k in ['id','name','message','media_urls','target','recipient','priority','country','language','segment','channel_group','scheduled_at','repeat','status','created_at','created_by','stats_reach','stats_clicks','stats_conversions']:
            if k not in c:
                c[k] = ''
    return jsonify({'campaigns': campaigns})

@app.route('/api/campaigns', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_create_campaign():
    """Create a new campaign."""
    data = request.json or {}
    campaign_id = f"CMP{secrets.token_hex(3).upper()}"
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    media_urls = data.get('media_urls', [])
    abs_media_urls = []
    for url in media_urls:
        if url:
            abs_media_urls.append(url if url.startswith('http') else f'https://vex.deals{url}')

    campaign = {
        'id': campaign_id,
        'name': data.get('name', ''),
        'message': data.get('message', ''),
        'media_urls': '|'.join(abs_media_urls),
        'target': data.get('target', 'both'),
        'recipient': data.get('recipient', 'all'),
        'priority': data.get('priority', 'normal'),
        'country': data.get('country', 'all'),
        'language': data.get('language', 'all'),
        'segment': data.get('segment', 'all'),
        'channel_group': data.get('channel_group', ''),
        'scheduled_at': data.get('scheduled_at', ''),
        'repeat': data.get('repeat', 'once'),
        'status': 'scheduled' if data.get('scheduled_at') else 'draft',
        'created_at': now,
        'created_by': session.get('admin_id', ''),
        'stats_reach': '0',
        'stats_clicks': '0',
        'stats_conversions': '0',
    }
    fieldnames = get_fieldnames('campaigns.csv', ['id','name','message','media_urls','target','recipient','priority','country','language','segment','channel_group','scheduled_at','repeat','status','created_at','created_by','stats_reach','stats_clicks','stats_conversions'])
    append_csv('campaigns.csv', campaign, fieldnames)
    log_action('create_campaign', campaign_id)

    # If no schedule → send immediately
    if not data.get('scheduled_at'):
        campaign['status'] = 'active'
        _execute_campaign(campaign)
        # Update status to completed
        _update_campaign_status(campaign_id, 'completed')

    return jsonify({'success': True, 'id': campaign_id, 'status': campaign['status']})

@app.route('/api/campaigns/<campaign_id>', methods=['PUT', 'DELETE'])
@api_auth
@permission_required('send_broadcast')
def api_edit_campaign(campaign_id):
    campaigns = read_csv('campaigns.csv')
    fieldnames = get_fieldnames('campaigns.csv', ['id','name','message','media_urls','target','recipient','priority','country','language','segment','channel_group','scheduled_at','repeat','status','created_at','created_by','stats_reach','stats_clicks','stats_conversions'])
    if request.method == 'DELETE':
        campaigns = [c for c in campaigns if c.get('id') != campaign_id]
        write_csv('campaigns.csv', campaigns, fieldnames)
        log_action('delete_campaign', campaign_id)
        return jsonify({'success': True})
    elif request.method == 'PUT':
        data = request.json or {}
        for c in campaigns:
            if c.get('id') == campaign_id:
                for k, v in data.items():
                    if k in fieldnames:
                        c[k] = v
                # If status changed to 'active' → execute
                if data.get('status') == 'active' and c.get('status') != 'completed':
                    _execute_campaign(c)
                    c['status'] = 'completed'
                break
        write_csv('campaigns.csv', campaigns, fieldnames)
        return jsonify({'success': True})

@app.route('/api/campaigns/<campaign_id>/stats')
@api_auth
def api_campaign_stats(campaign_id):
    """Get campaign stats."""
    campaigns = read_csv('campaigns.csv')
    for c in campaigns:
        if c.get('id') == campaign_id:
            return jsonify({
                'id': campaign_id,
                'reach': int(c.get('stats_reach', 0) or 0),
                'clicks': int(c.get('stats_clicks', 0) or 0),
                'conversions': int(c.get('stats_conversions', 0) or 0),
                'status': c.get('status', 'unknown')
            })
    return jsonify({'error': 'Not found'}), 404

def _update_campaign_status(campaign_id, status):
    """Update campaign status in CSV."""
    try:
        campaigns = read_csv('campaigns.csv')
        fieldnames = get_fieldnames('campaigns.csv', ['id','name','message','media_urls','target','recipient','priority','country','language','segment','channel_group','scheduled_at','repeat','status','created_at','created_by','stats_reach','stats_clicks','stats_conversions'])
        for c in campaigns:
            if c.get('id') == campaign_id:
                c['status'] = status
                break
        write_csv('campaigns.csv', campaigns, fieldnames)
    except:
        pass

def _execute_campaign(campaign):
    """Execute a campaign — send via web + telegram."""
    message = campaign.get('message', '')
    target = campaign.get('target', 'both')
    priority = campaign.get('priority', 'normal')
    country = campaign.get('country', 'all')
    media_urls_str = campaign.get('media_urls', '')
    media_urls = [u for u in media_urls_str.split('|') if u] if media_urls_str else []
    recipient = campaign.get('recipient', 'all')
    target_user = campaign.get('target_user', '') if recipient == 'single' else ''

    # Web notification
    if target in ('web', 'both'):
        notif_title = '📢 ' + campaign.get('name', 'حملة إعلانية')
        if priority == 'urgent':
            notif_title = '🚨 ' + campaign.get('name', 'حملة عاجلة')
        push_notification('broadcast', notif_title, message[:200], {'media_urls': media_urls, 'priority': priority, 'campaign_id': campaign.get('id', '')})

    # Telegram broadcast
    if target in ('telegram', 'both'):
        broadcast_entry = {
            'id': f"BCAST{str(int(datetime.now().timestamp()))[-6:]}{secrets.token_hex(2)}",
            'message': message,
            'target': target,
            'recipient': recipient,
            'priority': priority,
            'country': country,
            'media_urls': '|'.join(media_urls),
            'target_user': target_user,
            'target_name': '',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'created_by': session.get('admin_id', ''),
            'status': 'pending'
        }
        bc_fieldnames = get_fieldnames('broadcast_queue.csv', ['id','message','target','recipient','priority','country','media_urls','target_user','target_name','created_at','created_by','status'])
        append_csv('broadcast_queue.csv', broadcast_entry, bc_fieldnames)

    log_action('execute_campaign', campaign.get('id', ''))

# ===== End Campaigns API =====

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
@permission_required('send_broadcast')
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
@permission_required('send_broadcast')
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
@permission_required('send_broadcast')
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

# ===== API — Post Library =====

@app.route('/api/post-library')
@api_auth
def api_post_library():
    """مكتبة المنشورات — كل المنشورات"""
    search = request.args.get('search', '')
    posts = read_csv('post_library.csv')
    if search:
        sl = search.lower()
        posts = [p for p in posts if sl in (p.get('content', '') + p.get('title', '')).lower()]
    posts.reverse()
    return jsonify({'posts': posts[:100], 'total': len(posts)})

@app.route('/api/post-library', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_add_post():
    """إنشاء منشور جديد"""
    data = request.json
    posts = read_csv('post_library.csv')
    fieldnames = get_fieldnames('post_library.csv', ['id','title','content','media_type','media_file_id','target_channels','schedule','status','created_by','created_at'])
    new_id = f"POST{secrets.token_hex(3).upper()}"
    post = {
        'id': new_id,
        'title': data.get('title', ''),
        'content': data.get('content', ''),
        'media_type': data.get('media_type', 'text'),  # text, photo, video, both
        'media_file_id': data.get('media_file_id', ''),
        'target_channels': data.get('target_channels', ''),  # pipe-separated channel IDs
        'schedule': data.get('schedule', ''),  # datetime or 'now'
        'status': 'pending' if data.get('schedule') else 'ready',
        'created_by': session.get('admin_id', ''),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    append_csv('post_library.csv', post, fieldnames)
    log_action('create_post', new_id)

    # If schedule is 'now' — add to broadcast_queue for immediate publishing
    if data.get('schedule', 'now') == 'now' and post['content']:
        target_channels = data.get('target_channels', '').split('|') if data.get('target_channels') else []
        if target_channels:
            for ch_id in target_channels:
                ch_id = ch_id.strip()
                if ch_id:
                    channels = read_csv('bot_channels.csv')
                    ch = next((c for c in channels if c.get('id') == ch_id), None)
                    if ch:
                        entry = {
                            'id': f"PUB{secrets.token_hex(3).upper()}",
                            'message': post['content'],
                            'type': post['media_type'],
                            'target_chat_id': ch.get('chat_id', ''),
                            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                            'created_by': session.get('admin_id', ''),
                            'status': 'pending'
                        }
                        bq_fields = get_fieldnames('broadcast_queue.csv', ['id','message','type','target_chat_id','created_at','created_by','status'])
                        append_csv('broadcast_queue.csv', entry, bq_fields)
        # Also broadcast to all users if content exists
        entry_all = {
            'id': f"PUB{secrets.token_hex(3).upper()}",
            'message': post['content'],
            'type': post['media_type'],
            'target_chat_id': '',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'created_by': session.get('admin_id', ''),
            'status': 'pending'
        }
        bq_fields = get_fieldnames('broadcast_queue.csv', ['id','message','type','target_chat_id','created_at','created_by','status'])
        append_csv('broadcast_queue.csv', entry_all, bq_fields)
        post['status'] = 'published'
        # Update status in CSV
        for p in posts:
            if p.get('id') == new_id:
                p['status'] = 'published'
                break
        write_csv('post_library.csv', posts, fieldnames)

    return jsonify({'success': True, 'id': new_id, 'status': post['status']})

@app.route('/api/post-library/<post_id>', methods=['DELETE'])
@api_auth
@permission_required('send_broadcast')
def api_delete_post(post_id):
    posts = read_csv('post_library.csv')
    fieldnames = get_fieldnames('post_library.csv', ['id','title','content','media_type','media_file_id','target_channels','schedule','status','created_by','created_at'])
    posts = [p for p in posts if p.get('id') != post_id]
    write_csv('post_library.csv', posts, fieldnames)
    log_action('delete_post', post_id)
    return jsonify({'success': True})

@app.route('/api/post-library/<post_id>/publish', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_publish_post(post_id):
    """نشر منشور من المكتبة"""
    posts = read_csv('post_library.csv')
    post = next((p for p in posts if p.get('id') == post_id), None)
    if not post:
        return jsonify({'error': 'Post not found'}), 404

    # Add to broadcast queue
    target_channels = post.get('target_channels', '').split('|') if post.get('target_channels') else []
    for ch_id in target_channels:
        ch_id = ch_id.strip()
        if ch_id:
            channels = read_csv('bot_channels.csv')
            ch = next((c for c in channels if c.get('id') == ch_id), None)
            if ch:
                entry = {
                    'id': f"PUB{secrets.token_hex(3).upper()}",
                    'message': post.get('content', ''),
                    'type': post.get('media_type', 'text'),
                    'target_chat_id': ch.get('chat_id', ''),
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'created_by': session.get('admin_id', ''),
                    'status': 'pending'
                }
                bq_fields = get_fieldnames('broadcast_queue.csv', ['id','message','type','target_chat_id','created_at','created_by','status'])
                append_csv('broadcast_queue.csv', entry, bq_fields)

    # Also broadcast to all users
    entry_all = {
        'id': f"PUB{secrets.token_hex(3).upper()}",
        'message': post.get('content', ''),
        'type': post.get('media_type', 'text'),
        'target_chat_id': '',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'created_by': session.get('admin_id', ''),
        'status': 'pending'
    }
    bq_fields = get_fieldnames('broadcast_queue.csv', ['id','message','type','target_chat_id','created_at','created_by','status'])
    append_csv('broadcast_queue.csv', entry_all, bq_fields)

    # Update post status
    fieldnames = get_fieldnames('post_library.csv', ['id','title','content','media_type','media_file_id','target_channels','schedule','status','created_by','created_at'])
    for p in posts:
        if p.get('id') == post_id:
            p['status'] = 'published'
            break
    write_csv('post_library.csv', posts, fieldnames)
    log_action('publish_post', post_id)
    return jsonify({'success': True, 'message': 'تم النشر'})

# ===== API — Post Vault (Legacy archive) =====

@app.route('/api/post-vault')
@api_auth
def api_post_vault():
    """أرشيف البوستات المحفوظة"""
    search = request.args.get('search', '')
    posts = read_csv('post_vault.csv')
    if search:
        sl = search.lower()
        posts = [p for p in posts if sl in (p.get('original_text', '') + p.get('processed_text', '')).lower()]
    posts.reverse()
    return jsonify({'posts': posts[:100], 'total': len(posts)})

@app.route('/api/post-vault/<post_id>/repost', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_repost_from_vault(post_id):
    """إعادة نشر بوست من الأرشيف"""
    posts = read_csv('post_vault.csv')
    post = next((p for p in posts if p.get('id') == post_id), None)
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    text = post.get('processed_text') or post.get('original_text', '')
    entry = {
        'id': f"CHPOST{secrets.token_hex(3).upper()}",
        'message': text,
        'type': 'text',
        'target_chat_id': '',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'created_by': session.get('admin_id', ''),
        'status': 'pending'
    }
    fieldnames = ['id', 'message', 'type', 'target_chat_id', 'created_at', 'created_by', 'status']
    append_csv('broadcast_queue.csv', entry, fieldnames)
    log_action('repost_from_vault', post_id)
    return jsonify({'success': True, 'message': 'تمت إضافة البوست لقائمة الإرسال'})

@app.route('/api/post-vault/<post_id>', methods=['DELETE'])
@api_auth
@permission_required('send_broadcast')
def api_delete_vault_post(post_id):
    posts = read_csv('post_vault.csv')
    posts = [p for p in posts if p.get('id') != post_id]
    fieldnames = get_fieldnames('post_vault.csv', ['id','source_channel','source_chat_id','original_text','processed_text','media_type','media_file_id','ai_provider','status','created_at','published_to_users','published_to_channels','views','category'])
    write_csv('post_vault.csv', posts, fieldnames)
    return jsonify({'success': True})

# ===== API — Text Replacements =====

@app.route('/api/text-replacements')
@api_auth
def api_text_replacements():
    rules = read_csv('text_replacements.csv')
    return jsonify({'rules': rules})

@app.route('/api/text-replacements', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_add_text_replacement():
    data = request.json
    rules = read_csv('text_replacements.csv')
    fieldnames = get_fieldnames('text_replacements.csv', ['id','find_text','replace_text','is_regex','channel_id','is_active','created_at'])
    new_id = f"TR{secrets.token_hex(3).upper()}"
    rule = {
        'id': new_id,
        'find_text': data.get('find_text', ''),
        'replace_text': data.get('replace_text', ''),
        'is_regex': data.get('is_regex', 'no'),
        'channel_id': data.get('channel_id', ''),
        'is_active': 'yes',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    append_csv('text_replacements.csv', rule, fieldnames)
    log_action('add_text_replacement', new_id)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/text-replacements/<rule_id>/toggle', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_toggle_replacement(rule_id):
    rules = read_csv('text_replacements.csv')
    fieldnames = get_fieldnames('text_replacements.csv', ['id','find_text','replace_text','is_regex','channel_id','is_active','created_at'])
    for r in rules:
        if r.get('id') == rule_id:
            r['is_active'] = 'no' if r.get('is_active') == 'yes' else 'yes'
            break
    write_csv('text_replacements.csv', rules, fieldnames)
    return jsonify({'success': True})

@app.route('/api/text-replacements/<rule_id>', methods=['DELETE'])
@api_auth
@permission_required('send_broadcast')
def api_delete_replacement(rule_id):
    rules = read_csv('text_replacements.csv')
    fieldnames = get_fieldnames('text_replacements.csv', ['id','find_text','replace_text','is_regex','channel_id','is_active','created_at'])
    rules = [r for r in rules if r.get('id') != rule_id]
    write_csv('text_replacements.csv', rules, fieldnames)
    return jsonify({'success': True})

# ===== API — AI Providers =====

@app.route('/api/ai-providers')
@api_auth
def api_ai_providers():
    try:
        from ai_providers import AIManager
        manager = AIManager()
        providers = manager.get_available_providers()
        active = manager.get_active_provider_name()
        return jsonify({'providers': providers, 'active': active})
    except ImportError:
        return jsonify({'providers': [], 'active': None, 'error': 'ai_providers not available'})

@app.route('/api/ai-providers/test', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_test_ai():
    try:
        from ai_providers import AIManager
        manager = AIManager()
        provider = request.json.get('provider', None) if request.json else None
        result = manager.test_provider(provider)
        return jsonify(result)
    except ImportError:
        return jsonify({'success': False, 'error': 'ai_providers not available'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/ai-instructions', methods=['GET', 'POST'])
@api_auth
@permission_required('send_broadcast')
def api_ai_instructions():
    if request.method == 'GET':
        settings = read_csv('system_settings.csv')
        instr = next((s.get('setting_value', '') for s in settings if s.get('setting_key') == 'ai_instructions'), '')
        return jsonify({'instructions': instr})
    else:
        data = request.json
        text = data.get('instructions', '')
        settings = read_csv('system_settings.csv')
        fieldnames = get_fieldnames('system_settings.csv', ['setting_key','setting_value','description'])
        found = False
        for s in settings:
            if s.get('setting_key') == 'ai_instructions':
                s['setting_value'] = text
                found = True
                break
        if not found:
            settings.append({'setting_key': 'ai_instructions', 'setting_value': text, 'description': 'AI instructions'})
        write_csv('system_settings.csv', settings, fieldnames)
        log_action('update_ai_instructions', text[:50])
        return jsonify({'success': True})

@app.route('/api/ai-processed-posts')
@api_auth
def api_ai_posts():
    posts = read_csv('ai_processed_posts.csv')
    posts.reverse()
    return jsonify({'posts': posts[:50], 'total': len(posts)})

# ===== API — Channel Categories =====

@app.route('/api/channel-categories')
@api_auth
def api_channel_categories():
    channels = read_csv('bot_channels.csv')
    cats = {}
    for ch in channels:
        cat = ch.get('category', 'غير مصنف')
        if not cat:
            cat = 'غير مصنف'
        if cat not in cats:
            cats[cat] = 0
        cats[cat] += 1
    return jsonify({'categories': cats})

@app.route('/api/channels/<channel_id>/category', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_set_channel_category(channel_id):
    data = request.json
    category = data.get('category', 'غير مصنف')
    channels = read_csv('bot_channels.csv')
    fieldnames = get_fieldnames('bot_channels.csv', ['id','chat_id','title','type','is_active','added_at','relay_to_users','relay_to_channels','forward_mode','welcome_text','category','ai_enabled'])
    for c in channels:
        if c.get('id') == channel_id:
            c['category'] = category
            break
    write_csv('bot_channels.csv', channels, fieldnames)
    return jsonify({'success': True})

@app.route('/api/channels/<channel_id>/ai-toggle', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_toggle_channel_ai(channel_id):
    channels = read_csv('bot_channels.csv')
    fieldnames = get_fieldnames('bot_channels.csv', ['id','chat_id','title','type','is_active','added_at','relay_to_users','relay_to_channels','forward_mode','welcome_text','category','ai_enabled'])
    for c in channels:
        if c.get('id') == channel_id:
            c['ai_enabled'] = 'no' if c.get('ai_enabled') == 'yes' else 'yes'
            break
    write_csv('bot_channels.csv', channels, fieldnames)
    return jsonify({'success': True})

# ===== API — Channel Groups =====

@app.route('/api/channel-groups')
@api_auth
def api_channel_groups():
    groups = read_csv('channel_groups.csv')
    return jsonify({'groups': groups})

@app.route('/api/channel-groups', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_add_channel_group():
    data = request.json
    groups = read_csv('channel_groups.csv')
    fieldnames = get_fieldnames('channel_groups.csv', ['id','name','description','channel_ids','created_at'])
    new_id = f"GRP{secrets.token_hex(3).upper()}"
    group = {
        'id': new_id,
        'name': data.get('name', ''),
        'description': data.get('description', ''),
        'channel_ids': data.get('channel_ids', ''),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    append_csv('channel_groups.csv', group, fieldnames)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/channel-groups/<group_id>', methods=['DELETE'])
@api_auth
@permission_required('send_broadcast')
def api_delete_channel_group(group_id):
    groups = read_csv('channel_groups.csv')
    fieldnames = get_fieldnames('channel_groups.csv', ['id','name','description','channel_ids','created_at'])
    groups = [g for g in groups if g.get('id') != group_id]
    write_csv('channel_groups.csv', groups, fieldnames)
    return jsonify({'success': True})

# ===== API — Daily Report =====

@app.route('/api/channels/daily-report')
@api_auth
def api_daily_report():
    today = datetime.now().strftime('%Y-%m-%d')
    relay_logs = read_csv('relay_log.csv')
    today_logs = [l for l in relay_logs if l.get('timestamp', '').startswith(today)]
    ai_posts = read_csv('ai_processed_posts.csv')
    today_ai = [p for p in ai_posts if p.get('created_at', '').startswith(today)]
    channels = read_csv('bot_channels.csv')
    active_channels = [c for c in channels if c.get('is_active') == 'yes']
    total_users_reached = sum(int(l.get('users_relayed', 0) or 0) for l in today_logs)
    total_channels_reached = sum(int(l.get('channels_relayed', 0) or 0) for l in today_logs)
    return jsonify({
        'date': today,
        'total_posts': len(today_logs),
        'total_ai_processed': len(today_ai),
        'total_users_reached': total_users_reached,
        'total_channels_reached': total_channels_reached,
        'active_channels': len(active_channels),
        'total_channels': len(channels),
    })

# ===== API — Post to Channel =====

@app.route('/api/channels/<channel_id>/post', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
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

@app.route('/api/channels', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_add_channel_manual():
    """إضافة قناة يدوياً — مع تحديد الدور"""
    data = request.json
    chat_id = data.get('chat_id', '').strip()
    title = data.get('title', '').strip()
    ch_type = data.get('type', 'channel')

    if not chat_id:
        return jsonify({'error': 'chat_id required'}), 400

    # فحص عدم التكرار
    channels = read_csv('bot_channels.csv')
    for ch in channels:
        if ch.get('chat_id') == str(chat_id):
            return jsonify({'error': 'Channel already exists'}), 400

    ch_id = f"CH{secrets.token_hex(3).upper()}"
    fieldnames = get_fieldnames('bot_channels.csv', ['id','chat_id','title','type','is_active','added_at','relay_to_users','relay_to_channels','forward_mode','welcome_text','category','ai_enabled','channel_role','ai_provider','brand_voice'])
    new_channel = {
        'id': ch_id,
        'chat_id': str(chat_id),
        'title': title,
        'type': ch_type,
        'is_active': 'yes',
        'added_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'relay_to_users': 'no',
        'relay_to_channels': 'no',
        'forward_mode': 'all',
        'welcome_text': '',
        'category': data.get('category', ''),
        'ai_enabled': 'no',
        'channel_role': data.get('channel_role', 'both'),  # source, publish, both
        'ai_provider': data.get('ai_provider', ''),
        'brand_voice': data.get('brand_voice', '')
    }
    append_csv('bot_channels.csv', new_channel, fieldnames)
    log_action('add_channel_manual', f'{ch_id}: {title} ({chat_id}) role={new_channel["channel_role"]}')
    return jsonify({'success': True, 'id': ch_id})

@app.route('/api/channels/<channel_id>/category', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_set_channel_category_api(channel_id):
    data = request.json
    category = data.get('category', '')
    channels = read_csv('bot_channels.csv')
    fieldnames = get_fieldnames('bot_channels.csv', ['id','chat_id','title','type','is_active','added_at','relay_to_users','relay_to_channels','forward_mode','welcome_text','category','ai_enabled'])
    for c in channels:
        if c.get('id') == channel_id:
            c['category'] = category
            break
    write_csv('bot_channels.csv', channels, fieldnames)
    return jsonify({'success': True})

@app.route('/api/channel-categories')
@api_auth
def api_channel_categories_list():
    """قائمة كل الفئات مع عدد القنوات في كل فئة"""
    channels = read_csv('bot_channels.csv')
    cats = {}
    for ch in channels:
        cat = ch.get('category', '') or 'غير مصنف'
        if cat not in cats:
            cats[cat] = {'count': 0, 'channels': []}
        cats[cat]['count'] += 1
        cats[cat]['channels'].append({'id': ch.get('id', ''), 'title': ch.get('title', ''), 'chat_id': ch.get('chat_id', '')})
    return jsonify({'categories': cats})

# ===== API — Wheel Gifts =====

@app.route('/api/wheel-gifts')
@api_auth
def api_wheel_gifts():
    gifts = read_csv('wheel_gifts.csv')
    return jsonify({'gifts': gifts})

@app.route('/api/wheel-gifts', methods=['POST'])
@api_auth
@permission_required('manage_games')
def api_add_wheel_gift():
    data = request.json
    gifts = read_csv('wheel_gifts.csv')
    fieldnames = get_fieldnames('wheel_gifts.csv', ['id','gift_text','affiliate_link','is_active','created_at'])
    new_id = f"GIFT{secrets.token_hex(3).upper()}"
    gift = {
        'id': new_id,
        'gift_text': data.get('gift_text', ''),
        'affiliate_link': data.get('affiliate_link', ''),
        'is_active': 'yes',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    append_csv('wheel_gifts.csv', gift, fieldnames)
    log_action('add_wheel_gift', new_id)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/wheel-gifts/<gift_id>', methods=['PUT', 'DELETE'])
@api_auth
@permission_required('manage_games')
def api_edit_wheel_gift(gift_id):
    gifts = read_csv('wheel_gifts.csv')
    fieldnames = get_fieldnames('wheel_gifts.csv', ['id','gift_text','affiliate_link','is_active','created_at'])
    if request.method == 'DELETE':
        gifts = [g for g in gifts if g.get('id') != gift_id]
        write_csv('wheel_gifts.csv', gifts, fieldnames)
        return jsonify({'success': True})
    elif request.method == 'PUT':
        data = request.json
        for g in gifts:
            if g.get('id') == gift_id:
                for k, v in data.items():
                    if k in fieldnames:
                        g[k] = v
                break
        write_csv('wheel_gifts.csv', gifts, fieldnames)
        return jsonify({'success': True})

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
@permission_required('manage_bots')
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
@permission_required('manage_bots')
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
@permission_required('manage_bots')
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
@permission_required('ban_users')
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

@app.route('/api/upload-broadcast-media', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_upload_broadcast_media():
    """Upload media file for broadcast."""
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'error': 'لم يتم اختيار ملف'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    allowed = {'png','jpg','jpeg','webp','gif','mp4','webm','mov','pdf','doc','docx'}
    if ext not in allowed:
        return jsonify({'success': False, 'error': 'صيغة غير مدعومة'}), 400
    blob = f.read(50 * 1024 * 1024 + 1)  # 50MB max
    if len(blob) > 50 * 1024 * 1024:
        return jsonify({'success': False, 'error': 'الملف أكبر من 50MB'}), 400
    os.makedirs(os.path.join(BASE_DIR, 'dashboard', 'static', 'uploads', 'broadcast'), exist_ok=True)
    fname = f"bc_{secrets.token_hex(8)}.{ext}"
    with open(os.path.join(BASE_DIR, 'dashboard', 'static', 'uploads', 'broadcast', fname), 'wb') as out:
        out.write(blob)
    url = f'/static/uploads/broadcast/{fname}'
    log_action('upload_broadcast_media', fname)
    return jsonify({'success': True, 'url': url, 'absolute_url': f'https://vex.deals{url}'})

@app.route('/api/broadcast', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_broadcast():
    """بث رسالة — يدعم وسائط متعددة + فردي/جماعي + دولة + أولوية"""
    message = request.json.get('message', '') if request.json else ''
    target = request.json.get('target', 'both') if request.json else 'both'
    recipient = request.json.get('recipient', 'all') if request.json else 'all'
    priority = request.json.get('priority', 'normal') if request.json else 'normal'
    country = request.json.get('country', 'all') if request.json else 'all'
    media_urls = request.json.get('media_urls', []) if request.json else []
    target_user = request.json.get('target_user', '') if request.json else ''
    target_name = request.json.get('target_name', '') if request.json else ''
    search_query = request.json.get('search_query', '') if request.json else ''

    # If single + search_query provided, look up user by name/phone/telegram_id/customer_id
    if recipient == 'single' and not target_user and search_query:
        users = read_csv('users.csv')
        for u in users:
            if (search_query.lower() in (u.get('name','')).lower() or
                search_query in u.get('phone','') or
                search_query == u.get('telegram_id','') or
                search_query == u.get('customer_id','')):
                target_user = u.get('telegram_id', '')
                target_name = u.get('name', '')
                break
        if not target_user:
            return jsonify({'success': False, 'error': 'لم يتم العثور على المستخدم'}), 404

    # Normalize media URLs to absolute
    abs_media_urls = []
    for url in media_urls:
        if url:
            abs_media_urls.append(url if url.startswith('http') else f'https://vex.deals{url}')

    primary_media = abs_media_urls[0] if abs_media_urls else ''

    # ── Web notification (instant via SSE) ──
    if target in ('web', 'both'):
        notif_title = '📢 رسالة جديدة'
        if priority == 'urgent':
            notif_title = '🚨 رسالة عاجلة'
        elif priority == 'high':
            notif_title = '⚡ رسالة مهمة'
        push_notification(
            'broadcast',
            notif_title,
            message[:200] or 'إشعار من الإدارة',
            {'media_url': primary_media, 'media_urls': abs_media_urls, 'priority': priority,
             'recipient': recipient, 'country': country, 'full_message': message}
        )

    # ── Telegram broadcast (queued for bot) ──
    if target in ('telegram', 'both'):
        broadcast_entry = {
            'id': f"BCAST{str(int(datetime.now().timestamp()))[-6:]}{secrets.token_hex(2)}",
            'message': message,
            'target': target,
            'recipient': recipient,
            'priority': priority,
            'country': country,
            'media_urls': '|'.join(abs_media_urls),
            'target_user': target_user,
            'target_name': target_name,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'created_by': session.get('admin_id', ''),
            'status': 'pending'
        }
        fieldnames = get_fieldnames('broadcast_queue.csv', ['id', 'message', 'target', 'recipient', 'priority', 'country',
                      'media_urls', 'target_user', 'target_name', 'created_at', 'created_by', 'status'])
        append_csv('broadcast_queue.csv', broadcast_entry, fieldnames)

    log_action('broadcast', f'recipient={recipient} target={target} priority={priority} country={country} msg={message[:50]}')
    target_label = 'تيليغرام والموقع' if target == 'both' else ('تيليغرام' if target == 'telegram' else 'الموقع')
    recipient_label = 'فردي' if recipient == 'single' else ('دولة محددة' if country != 'all' else 'جماعي')
    return jsonify({'success': True, 'message': f'تم إرسال البث {recipient_label} عبر {target_label}'})

# ===== API — Settings =====

@app.route('/api/settings')
@api_auth
def api_settings():
    settings = read_csv('system_settings.csv')
    return jsonify({'settings': settings})

@app.route('/api/settings', methods=['POST'])
@api_auth
@permission_required('manage_settings')
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
@permission_required('manage_settings')
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
@permission_required('manage_admins')
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
@permission_required('manage_admins')
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
@permission_required('manage_admins')
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


# ── RBAC Roles Management API (super_admin only) ──────────────────────────────

@app.route('/api/admin/rbac/roles', methods=['GET'])
@api_auth
@permission_required('manage_admins')
def api_rbac_roles_list():
    """List all admin role assignments from the SQLite admin_roles table."""
    try:
        import sqlite3 as _sql
        conn = _sql.connect(os.path.join(BASE_DIR, 'vex_games.db'), timeout=5)
        conn.row_factory = _sql.Row
        rows = conn.execute(
            'SELECT uid, role, permissions, created_at, created_by '
            'FROM admin_roles ORDER BY created_at DESC'
        ).fetchall()
        conn.close()
        result = []
        for r in rows:
            perms = {}
            try:
                perms = json.loads(r['permissions'] or '{}')
            except Exception:
                pass
            result.append({
                'uid': r['uid'], 'role': r['role'],
                'permissions': perms,
                'created_at': r['created_at'],
                'created_by': r['created_by'],
            })
        return jsonify({'roles': result, 'role_definitions': _ROLE_PERMISSIONS})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/rbac/roles/<uid>', methods=['POST'])
@api_auth
@permission_required('manage_admins')
def api_rbac_set_role(uid):
    """Assign or update a role for an admin UID (super_admin only)."""
    data = request.json or {}
    role = data.get('role', '')
    if not role or role not in _ROLE_PERMISSIONS:
        valid = list(_ROLE_PERMISSIONS.keys())
        return jsonify({'error': f'Invalid role. Valid values: {valid}'}), 400
    actor = str(session.get('admin_id', ''))
    ok = _rbac_set_role(str(uid), role, created_by=actor)
    if ok:
        _rbac_log(actor, 'rbac_set_role', target=str(uid),
                  details=f'role={role}', ip=request.remote_addr)
        log_action('rbac_set_role', f'{uid} → {role}')
        return jsonify({'success': True})
    return jsonify({'error': 'Failed to set role'}), 500


@app.route('/api/admin/rbac/roles/<uid>', methods=['DELETE'])
@api_auth
@permission_required('manage_admins')
def api_rbac_delete_role(uid):
    """Remove a custom role (UID reverts to no-access or env-based super_admin)."""
    try:
        import sqlite3 as _sql
        conn = _sql.connect(os.path.join(BASE_DIR, 'vex_games.db'), timeout=5)
        conn.execute('DELETE FROM admin_roles WHERE uid=?', (str(uid),))
        conn.commit()
        conn.close()
        actor = str(session.get('admin_id', ''))
        _rbac_log(actor, 'rbac_delete_role', target=str(uid),
                  details='role removed', ip=request.remote_addr)
        log_action('rbac_delete_role', uid)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ===== API — Themes =====

@app.route('/api/themes')
@api_auth
def api_themes():
    themes = [
        {'id': 'vex', 'name': 'VEX Neon', 'colors': {'primary': '#00ff88', 'accent': '#00b35f'}},
        {'id': 'gold', 'name': 'Gold', 'colors': {'primary': '#FFD700', 'accent': '#FFA500'}},
        {'id': 'ocean', 'name': 'Ocean', 'colors': {'primary': '#0077BE', 'accent': '#00B4D8'}},
        {'id': 'purple', 'name': 'Purple', 'colors': {'primary': '#6B46C1', 'accent': '#9F7AEA'}}
    ]
    valid_ids = {t['id'] for t in themes}
    settings = read_csv('system_settings.csv')
    active_theme = next((s.get('setting_value', 'vex') for s in settings if s.get('setting_key') == 'active_theme'), 'vex')
    if active_theme not in valid_ids:
        active_theme = 'vex'
    return jsonify({'themes': themes, 'active_theme': active_theme})


@app.route('/api/themes', methods=['POST'])
@api_auth
@permission_required('manage_settings')
def api_set_theme():
    payload = request.json or {}
    theme_id = payload.get('theme_id') or payload.get('theme') or 'vex'
    if theme_id not in ('vex', 'gold', 'ocean', 'purple'):
        return jsonify({'error': 'invalid theme'}), 400
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
@permission_required('manage_settings')
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
@permission_required('manage_settings')
def api_delete_exchange_address(addr_id):
    addresses = read_csv('exchange_addresses.csv')
    fieldnames = get_fieldnames('exchange_addresses.csv', ['id','exchange_name','address','network','is_active','created_at','notes'])
    addresses = [a for a in addresses if a.get('id') != addr_id]
    write_csv('exchange_addresses.csv', addresses, fieldnames)
    log_action('delete_exchange_address', addr_id)
    return jsonify({'success': True})


@app.route('/api/exchange-addresses/<addr_id>/toggle', methods=['POST'])
@api_auth
@permission_required('manage_settings')
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
@permission_required('send_broadcast')
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
@permission_required('manage_admins')
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
@permission_required('manage_admins')
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
@permission_required('manage_games')
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


_lottery_draw_lock = threading.Lock()

@app.route('/api/lottery/<round_id>/draw', methods=['POST'])
@api_auth
@permission_required('manage_games')
def api_lottery_draw(round_id):
  with _lottery_draw_lock:
    rounds = read_csv('lottery_rounds.csv')
    round_fieldnames = get_fieldnames('lottery_rounds.csv', ['id','name','ticket_price','currency','winner_count','max_tickets','admin_pct','draw_time','status','created_at'])

    lot_round = None
    for r in rounds:
        if r.get('id') == round_id:
            lot_round = r
            break

    if not lot_round:
        return jsonify({'error': 'Round not found'}), 404
    # One-shot guard: a round can only be drawn once (prevents duplicate winners)
    if lot_round.get('status') == 'drawn':
        return jsonify({'error': 'تم سحب هذه الجولة بالفعل'}), 400
    lot_round['status'] = 'drawn'

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
@permission_required('manage_games')
def api_wheel_create():
    data = request.json
    rounds = read_csv('wheel_rounds.csv')
    fieldnames = get_fieldnames('wheel_rounds.csv', ['id','name','prizes','status','spin_cost','currency','min_spins','max_spins_per_user','game_speed_ms','max_relocations','created_at'])
    new_id = f"WHL{str(int(datetime.now().timestamp()))[-6:]}"
    prizes = data.get('prizes', '')
    if isinstance(prizes, list):
        prizes = '|'.join(prizes) if len(prizes) > 1 else (prizes[0] if prizes else '')
    new_round = {
        'id': new_id,
        'name': data.get('name', ''),
        'prizes': prizes,
        'status': 'active',
        'spin_cost': data.get('spin_cost', '0'),
        'currency': data.get('currency', 'SAR'),
        'min_spins': '1',
        'max_spins_per_user': data.get('max_spins_per_user', data.get('max_spins', '1')),
        'game_speed_ms': data.get('game_speed_ms', '2500'),
        'max_relocations': data.get('max_relocations', '1'),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    append_csv('wheel_rounds.csv', new_round, fieldnames)
    log_action('wheel_create', new_id)
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/wheel/<round_id>/end', methods=['POST'])
@api_auth
@permission_required('manage_games')
def api_wheel_end(round_id):
    rounds = read_csv('wheel_rounds.csv')
    fieldnames = get_fieldnames('wheel_rounds.csv', ['id','name','prizes','status','spin_cost','currency','min_spins','max_spins_per_user','game_speed_ms','max_relocations','created_at'])
    for r in rounds:
        if r.get('id') == round_id:
            r['status'] = 'completed'
            break
    write_csv('wheel_rounds.csv', rounds, fieldnames)
    log_action('wheel_end', round_id)
    return jsonify({'success': True})


# ===== API — Matching Actions =====

@app.route('/api/matching/<req_id>/approve', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
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
@permission_required('reject_deposits')
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
@permission_required('view_financial')
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
@permission_required('view_financial')
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
@permission_required('view_financial')
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
@permission_required('view_financial')
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
@permission_required('manage_settings')
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
@permission_required('manage_companies')
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

# ===== Web Push Subscriptions (notifications even when tab is closed) =====
@app.route('/api/push/vapid-public-key')
def api_push_vapid_public():
    """Return VAPID public key — public, no auth needed."""
    return jsonify({'public_key': _VAPID_PUBLIC})

@app.route('/api/user/notifications')
def api_user_notifications():
    """Public endpoint: returns recent notifications for users (no auth needed)."""
    logs = read_csv('notifications_log.csv')
    logs.reverse()
    # Only return broadcast + user-targeted notifications from last 24h
    from datetime import datetime as _dt, timedelta as _td
    cutoff = (_dt.now() - _td(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    result = []
    for l in logs:
        if l.get('timestamp', '') >= cutoff and l.get('type', '') in ('broadcast', 'new_user', 'deposit_approved', 'deposit_rejected'):
            result.append({
                'timestamp': l.get('timestamp', ''),
                'type': l.get('type', ''),
                'title': l.get('type_label', ''),
                'message': l.get('message_preview', '')
            })
    return jsonify({'notifications': result[:10]})

@app.route('/api/push/subscribe-user', methods=['POST'])
def api_push_subscribe_user():
    """Store push subscription for a regular user (not admin)."""
    data = request.json or {}
    endpoint = data.get('endpoint', '')
    keys = data.get('keys', {})
    user_id = str(data.get('user_id', ''))
    user_name = data.get('user_name', '')
    if not endpoint:
        return jsonify({'error': 'No endpoint'}), 400
    subs = read_csv('push_subscriptions.csv')
    fieldnames = get_fieldnames('push_subscriptions.csv', ['admin_id','endpoint','p256dh','auth','created_at','user_type','user_id','user_name'])
    # Remove old sub for this endpoint
    subs = [s for s in subs if s.get('endpoint') != endpoint]
    subs.append({
        'admin_id': '',
        'endpoint': endpoint,
        'p256dh': keys.get('p256dh', ''),
        'auth': keys.get('auth', ''),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'user_type': 'user',
        'user_id': user_id,
        'user_name': user_name
    })
    write_csv('push_subscriptions.csv', subs, fieldnames)
    return jsonify({'success': True})

@app.route('/api/push/subscribe', methods=['POST'])
def api_push_subscribe():
    """Store a browser push subscription — public, no auth needed."""
    data = request.json or {}
    endpoint = data.get('endpoint', '')
    keys = data.get('keys', {})
    if not endpoint:
        return jsonify({'error': 'No endpoint'}), 400
    admin_id = str(session.get('admin_id', ''))
    subs = read_csv('push_subscriptions.csv')
    fieldnames = get_fieldnames('push_subscriptions.csv', ['admin_id','endpoint','p256dh','auth','created_at'])
    # Remove old sub for this endpoint
    subs = [s for s in subs if s.get('endpoint') != endpoint]
    subs.append({
        'admin_id': admin_id,
        'endpoint': endpoint,
        'p256dh': keys.get('p256dh', ''),
        'auth': keys.get('auth', ''),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
    write_csv('push_subscriptions.csv', subs, fieldnames)
    return jsonify({'success': True})


# ===== API — User Edit =====

@app.route('/api/users/<user_id>', methods=['PUT'])
@api_auth
@permission_required('ban_users')
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
@permission_required('manage_companies')
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
@permission_required('view_financial')
def api_svrp_freeze(user_id):
    """Admin freeze: moves frozen_balance → 0 in SQLite (delta), CSV mirrors.

    'Freeze' here means zeroing out the transferable frozen_balance —
    the same delta operation that prevents double-spend.
    """
    import sys as _sf; _sf.path.insert(0, BASE_DIR)
    from svrp import svrp_lock as _sl
    with _sl():
        wallets = read_csv('svrp_wallets.csv')
        fieldnames = get_fieldnames('svrp_wallets.csv', ['telegram_id','customer_id','balance','pending_balance','total_earned','total_used','wagering_required','wagering_completed','last_recovery_date','monthly_recovery_total'])
        delta = 0.0
        for w in wallets:
            if w.get('telegram_id') == user_id:
                balance = float(w.get('balance', 0) or 0)
                frozen  = float(w.get('pending_balance', 0) or 0)
                delta   = -balance   # remove from frozen_balance in SQLite
                w['pending_balance'] = str(balance + frozen)
                w['balance'] = '0'
                break
        write_csv('svrp_wallets.csv', wallets, fieldnames)
        if delta != 0.0:
            try:
                _gm.delta_update_svrp_wallet(user_id, frozen_balance_delta=delta)
            except Exception as _fe:
                import logging; logging.getLogger(__name__).warning(
                    f'svrp_freeze SQLite delta failed uid={user_id}: {_fe}')
    log_action('svrp_freeze', user_id)
    return jsonify({'success': True, 'message': 'تم تجميد الرصيد'})

@app.route('/api/svrp/wallets/<user_id>/unfreeze', methods=['POST'])
@api_auth
@permission_required('view_financial')
def api_svrp_unfreeze(user_id):
    """Admin unfreeze: moves pending_balance → frozen_balance in SQLite (delta)."""
    import sys as _su; _su.path.insert(0, BASE_DIR)
    from svrp import svrp_lock as _sl
    data = request.json or {}
    raw  = data.get('amount', 0)
    try:
        amount = float(raw)
    except (TypeError, ValueError):
        return jsonify({'error': 'المبلغ غير صالح'}), 400
    if not math.isfinite(amount) or amount < 0:
        return jsonify({'error': 'المبلغ يجب أن يكون رقماً صحيحاً >= 0'}), 400
    with _sl():
        wallets = read_csv('svrp_wallets.csv')
        fieldnames = get_fieldnames('svrp_wallets.csv', ['telegram_id','customer_id','balance','pending_balance','total_earned','total_used','wagering_required','wagering_completed','last_recovery_date','monthly_recovery_total'])
        delta = 0.0
        for w in wallets:
            if w.get('telegram_id') == user_id:
                frozen  = float(w.get('pending_balance', 0) or 0)
                balance = float(w.get('balance', 0) or 0)
                if amount == 0:
                    amount = frozen
                amount = min(amount, frozen)
                delta = amount   # add to frozen_balance in SQLite
                w['balance']         = str(round(balance + amount, 6))
                w['pending_balance'] = str(round(frozen - amount, 6))
                break
        write_csv('svrp_wallets.csv', wallets, fieldnames)
        if delta > 0:
            try:
                _gm.delta_update_svrp_wallet(user_id, frozen_balance_delta=delta)
            except Exception as _ue:
                import logging; logging.getLogger(__name__).warning(
                    f'svrp_unfreeze SQLite delta failed uid={user_id}: {_ue}')
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
    # Normalize fieldnames for old rows
    queue = read_csv('broadcast_queue.csv')
    for item in queue:
        for k in ['id','message','target','recipient','priority','country','media_urls','target_user','target_name','created_at','created_by','status']:
            if k not in item:
                item[k] = ''
    queue.reverse()
    return jsonify({'queue': queue[:50]})

# ===== API — Edit Transaction =====

@app.route('/api/transactions/<txn_id>', methods=['PUT'])
@api_auth
@permission_required('approve_deposits')
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
@permission_required('manage_games')
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
@permission_required('manage_games')
def api_delete_wheel_round(round_id):
    rounds = read_csv('wheel_rounds.csv')
    fieldnames = get_fieldnames('wheel_rounds.csv', ['id','name','prizes','status','spin_cost','currency','min_spins','max_spins_per_user','game_speed_ms','max_relocations','created_at'])
    rounds = [r for r in rounds if r.get('id') != round_id]
    write_csv('wheel_rounds.csv', rounds, fieldnames)
    log_action('delete_wheel_round', round_id)
    return jsonify({'success': True})

# ===== API — Restore Backup =====

@app.route('/api/backup/restore', methods=['POST'])
@api_auth
@permission_required('manage_admins')
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
@permission_required('manage_admins')
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
    targeted = [q for q in queue if q.get('target_user_id', '')]
    targeted.reverse()
    return jsonify({'messages': targeted[:50]})

# ---------------------------------------------------
# ===== VEX GAMES PLATFORM — API =====
# ---------------------------------------------------

# تهيئة محرك الألعاب
try:
    import sys as _sys
    _sys.path.insert(0, BASE_DIR)
    from game_engine import GameManager
    from db_manager import (
        set_active_game_session as _set_ags,
        delete_active_game_session as _del_ags,
        refund_expired_game_sessions as _refund_ags,
        check_and_mark_nonce as _check_nonce,
        cleanup_expired_nonces as _cleanup_nonces,
        _gdb as _db_singleton,
    )
    _gm = GameManager()
    _VEX_GAMES = True
    # ── Startup: refund any bets stranded by a mid-game server crash ──────────
    # active_game_sessions rows survive restarts; refund credits the bet back
    # via credit_with_idempotency so double-refunds on repeated restarts are safe.
    try:
        _startup_refunded = _refund_ags(_db_singleton)
        if _startup_refunded:
            print(f"[startup] Refunded {len(_startup_refunded)} expired game session(s): "
                  f"{_startup_refunded}")
        else:
            print("[startup] No expired game sessions to refund.")
    except Exception as _rags_err:
        print(f"[startup] refund_expired_game_sessions error: {_rags_err}")
except Exception as e:
    print(f"VEX Games init error: {e}")
    _VEX_GAMES = False
    # Provide no-op stubs so call sites don't NameError when _VEX_GAMES is False
    def _set_ags(*a, **k): pass
    def _del_ags(*a, **k): pass

# ===== Games Catalog =====

@app.route('/api/games/list')
@webapp_auth
def api_games_list():
    """قائمة الألعاب النشطة"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    games = _gm.get_games(active_only=True)
    return jsonify({'games': games, 'count': len(games)})

@app.route('/api/games/all')
@api_auth
def api_games_all():
    """كل الألعاب (للأدمن)"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    games = _gm.get_games(active_only=False)
    return jsonify({'games': games})

@app.route('/api/games/create', methods=['POST'])
@api_auth
@permission_required('manage_games')
def api_games_create():
    """إضافة لعبة جديدة"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    game_id = _gm.add_game(
        name=data.get('name', ''),
        icon=data.get('icon', '🎮'),
        description=data.get('description', ''),
        category=data.get('category', 'arcade'),
        min_bet=data.get('min_bet', 10),
        max_bet=data.get('max_bet', 1000),
        base_win_chance=data.get('base_win_chance', 0.45),
        house_edge_pct=data.get('house_edge_pct', 15),
        rtp_target=data.get('rtp_target', 85),
        volatility=data.get('volatility', 'medium')
    )
    return jsonify({'success': True, 'id': game_id})

@app.route('/api/games/<game_id>/toggle', methods=['POST'])
@api_auth
@permission_required('manage_games')
def api_games_toggle(game_id):
    """تفعيل/إيقاف لعبة"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    try:
        rows = []
        with open(os.path.join(BASE_DIR, 'games_catalog.csv'), 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                if row.get('id') == game_id:
                    row['is_active'] = 'no' if row.get('is_active') == 'yes' else 'yes'
                rows.append(row)
        with open(os.path.join(BASE_DIR, 'games_catalog.csv'), 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    except:
        pass
    return jsonify({'success': True})

# ===== Wallet =====

@app.route('/api/wallet/balance')
@webapp_auth
def api_wallet_balance():
    """رصيد اللاعب + عملته"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    uid = get_request_uid()
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    balance = _gm.get_balance(uid)
    user_info = _gm.get_user_info(uid)
    currency = user_info.get('currency', 'EGP')
    return jsonify({'balance': balance, 'uid': uid, 'currency': currency})

@app.route('/api/player/wallet')
@webapp_auth
def api_player_wallet():
    """محفظة اللاعب الكاملة: رصيد اللعب + SVRP مجمد/معلق + wagering progress

    دلالات حقول SVRP:
      balance         = أرصدة SVRP (مجمدة حتى اكتمال الرهان، ثم قابلة للنقل إلى رصيد اللعب)
      pending_balance = تنتظر إكمال الأصدقاء للرهان حتى تنتقل إلى balance
      total_used      = مجموع تراكمي تاريخي لما صُرف كخصومات — ليس رصيداً متاحاً
      total_earned    = مجموع تراكمي تاريخي لكل ما اكتُسب
    """
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400

    # ── رصيد اللعب (SQLite) ─────────────────────────────────────────
    game_balance = float(_gm.get_balance(uid) or 0)
    user_info = _gm.get_user_info(uid)
    currency = user_info.get('currency', 'EGP')

    # ── محفظة SVRP (SQLite authoritative for financial fields) ─────────
    _svrp_sql = _gm.get_svrp_frozen_balance(uid)
    svrp_credits    = float(_svrp_sql.get('frozen_balance', 0) or 0)
    total_earned    = float(_svrp_sql.get('total_earned', 0) or 0)
    total_consumed  = float(_svrp_sql.get('total_used', 0) or 0)
    wager_required  = int(_svrp_sql.get('wagering_required', 3) or 3)
    wager_done      = int(_svrp_sql.get('wagering_completed', 0) or 0)
    # pending_balance still from CSV (not a financial field, no transfer risk)
    wallets = read_csv('svrp_wallets.csv')
    svrp_wallet = next((w for w in wallets if str(w.get('telegram_id', '')) == uid), {})
    pending_balance = float(svrp_wallet.get('pending_balance', 0) or 0) # ينتظر الأصدقاء
    wager_remaining = max(0, wager_required - wager_done)
    wagering_done   = wager_done >= wager_required  # True = يمكن نقل الرصيد
    credits_spendable = wagering_done and svrp_credits > 0

    # ── مصادر أرصدة SVRP (Credit breakdown) ────────────────────────
    credits_all = read_csv('svrp_credits.csv')
    user_credits = [c for c in credits_all
                    if str(c.get('user_id', '')) == uid
                    and c.get('status') in ('pending', 'active', 'frozen')]

    credit_sources = []
    _type_label = {
        'keep':     'مكافأة احتفاظ',
        'shared':   'مكافأة مشاركة',
        'recovery': 'تعويض / استرداد',
        'referral': 'مكافأة إحالة',
    }
    for c in user_credits:
        amt = float(c.get('credit_amount', 0) or 0)
        if amt <= 0:
            continue
        source_type = c.get('credit_type', 'referral')
        status = c.get('status', '')
        credit_sources.append({
            'type':    source_type,
            'label':   _type_label.get(source_type, source_type),
            'amount':  amt,
            'status':  status,
            # pending = ينتظر الأصدقاء / active = جاهز للاستخدام بعد الرهان
            'ready':   status == 'active',
            'created': c.get('created_at', ''),
        })

    # ── آخر المعاملات (transactions.csv) ────────────────────────────
    recent_txns = []
    try:
        txns = read_csv('transactions.csv')
        user_txns = [t for t in txns if str(t.get('telegram_id', '')) == uid][-10:]
        for t in reversed(user_txns):
            recent_txns.append({
                'id':      t.get('id', ''),
                'type':    t.get('type', ''),
                'amount':  t.get('amount', '0'),
                'status':  t.get('status', ''),
                'company': t.get('company', ''),
                'date':    t.get('date', ''),
            })
    except Exception:
        pass

    return jsonify({
        'uid':               uid,
        'currency':          currency,
        'game_balance':      game_balance,      # رصيد اللعب (للرهان)
        'svrp_credits':      svrp_credits,      # أرصدة SVRP (مجمدة أو جاهزة)
        'pending_balance':   pending_balance,   # ينتظر الأصدقاء
        'total_earned':      total_earned,      # تراكمي تاريخي
        'total_consumed':    total_consumed,    # تراكمي تاريخي (للعرض الإداري فقط)
        'wagering_required': wager_required,
        'wagering_completed': wager_done,
        'wagering_remaining': wager_remaining,
        'wagering_done':     wagering_done,     # True = اكتمل الرهان
        'credits_spendable': credits_spendable, # True = يمكن نقل الرصيد الآن
        'credit_sources':    credit_sources,
        'recent_transactions': recent_txns,
    })


# svrp_lock() is imported lazily inside the endpoint to avoid a top-level
# circular-import issue (svrp.py is loaded after app config is set up).
# It provides reentrant cross-process locking for all SVRP CSV mutations.


@app.route('/api/svrp/transfer-to-game', methods=['POST'])
@webapp_auth
def api_svrp_transfer_to_game():
    """نقل أرصدة SVRP (بعد اكتمال الرهان) إلى رصيد اللعب.

    Body JSON: {
        "amount": <positive finite float — optional, defaults to full balance>,
        "transfer_id": <client-supplied idempotency key — optional but strongly recommended>
    }

    State machine (svrp_transfer_log.status):
      pending  ──(CAS debited + amount)──► debited
      debited  ──(CAS credit + completed)──► completed     [idempotent replay]
      debited  ──(compensating rollback)──► rolled_back

    Retry safety:
      • 'completed'   → returns cached outcome with no CSV or DB mutation
      • 'debited'     → skips SVRP debit, re-applies game credit idempotently
      • 'pending'     → key exists but no debit happened; return conflict (409)
      • key unknown   → fresh transfer

    Security: uid ownership is verified before any state is read or mutated.
    """
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500

    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400

    import sys as _sys2; _sys2.path.insert(0, BASE_DIR)
    import secrets as _sec
    from svrp import SVRPManager as _SVRPMgr, svrp_lock as _svrp_lock

    # ── parse input ──────────────────────────────────────────────────────────
    data = request.get_json(silent=True) or {}
    raw_amount = data.get('amount')
    client_key = str(data.get('transfer_id') or '').strip()[:128]

    if raw_amount is not None:
        try:
            parsed_amount = float(raw_amount)
        except (TypeError, ValueError):
            return jsonify({'error': 'المبلغ غير صالح — يجب أن يكون رقماً'}), 400
        if not math.isfinite(parsed_amount) or parsed_amount <= 0:
            return jsonify({'error': 'المبلغ غير صالح (لا يقبل NaN أو Infinity أو صفر)'}), 400
    else:
        parsed_amount = None

    # ── resolve client idempotency key ───────────────────────────────────────
    _resume_debited = False   # True → skip SVRP debit, go straight to game credit
    _resume_amount  = None    # amount from the debited outbox record

    if client_key:
        existing = _gm.get_svrp_transfer(client_key)
        if existing:
            # SECURITY: verify ownership before reading any state
            if existing.get('uid') != uid:
                return jsonify({'error': 'هذا الطلب لا ينتمي لهذا الحساب'}), 403

            st = existing.get('status')
            if st == 'completed':
                # Idempotent replay — no mutation at all
                return jsonify({
                    'success':          True,
                    'transferred':      round(float(existing.get('amount') or 0), 2),
                    'new_game_balance': _gm.get_balance(uid),
                    'new_svrp_credits': float(
                        (_SVRPMgr().get_wallet(uid) or {}).get('balance', 0) or 0
                    ),
                    'transfer_id': client_key,
                    'replayed':    True,
                })
            if st == 'debited':
                # SVRP already debited but game credit not yet confirmed.
                # Resume the credit step only — no second debit.
                _resume_debited = True
                _resume_amount  = float(existing.get('amount') or 0)
                if _resume_amount <= 0:
                    return jsonify({'error': 'المبلغ المسجل في الطلب غير صالح'}), 400
            elif st == 'pending':
                # Key reserved but no debit committed yet.
                # Concurrent/retried requests must not race to debit.
                return jsonify({
                    'error': 'الطلب قيد المعالجة — حاول مجدداً بعد لحظات',
                    'transfer_id': client_key,
                }), 409
            else:
                # rolled_back, cancelled, unknown — not resumable
                return jsonify({
                    'error': f'الطلب في حالة غير قابلة للاستئناف ({st})',
                    'transfer_id': client_key,
                }), 409

    _transfer_id = client_key if client_key else _sec.token_hex(16)

    # ── Amount canonicalization ───────────────────────────────────────────────
    if parsed_amount is not None:
        from decimal import Decimal as _Dec, ROUND_DOWN as _RDOWN, InvalidOperation as _DI
        try:
            _canon = _Dec(str(parsed_amount)).quantize(_Dec('0.01'), rounding=_RDOWN)
        except _DI:
            return jsonify({'error': 'المبلغ غير قابل للتحويل'}), 400
        if _canon < _Dec('0.01'):
            return jsonify({'error': 'الحد الأدنى للنقل 0.01'}), 400
        parsed_amount = float(_canon)

    # ── Step A: SVRP frozen-balance debit (SQLite-only, no CSV involved) ──────
    #
    # All financial state lives in SQLite (svrp_wallet_balance +
    # svrp_transfer_log).  debit_svrp_balance_for_transfer atomically debits
    # the wallet and CAS-transitions the outbox to 'debited' in one SAVEPOINT.
    # There is no cross-store dependency and no crash window between the two.
    #
    # Fresh path:
    #   1. Reject if user already has a 'debited' outstanding transfer (one-at-a-time).
    #   2. CREATE outbox 'pending' (INSERT OR IGNORE in SQLite).
    #   3. Read + validate + canonicalize amount from SQLite wallet.
    #   4. debit_svrp_balance_for_transfer → SAVEPOINT: wallet debit + CAS
    #      pending→debited.  Either both commit or neither does.
    #
    # Resume path (status='debited'):
    #   The SQLite wallet was already debited atomically with the 'debited' CAS.
    #   There is no CSV to re-check; simply proceed to game credit.

    amount: float = 0.0

    if _resume_debited:
        # ── Resume: SQLite debit is atomic with status CAS — no re-check needed ──
        existing_rec = _gm.get_svrp_transfer(_transfer_id)
        amount = float((existing_rec or {}).get('amount') or 0)
        if amount < 0.01:
            return jsonify({'error': 'المبلغ المسجل في الطلب غير صالح'}), 400
        # Nothing else to do here — the SQLite frozen balance was already debited
        # atomically when the outbox transitioned to 'debited'.

    else:
        # ── Fresh debit ───────────────────────────────────────────────────────
        # Enforce one-outstanding-per-user: reject if a debited transfer exists.
        outstanding = _gm.get_outstanding_debited_transfer(uid)
        if outstanding:
            return jsonify({
                'error': (
                    f'يوجد تحويل معلق — أكمله أولاً باستخدام '
                    f'transfer_id="{outstanding}"'
                ),
                'transfer_id': outstanding,
                'retry': True,
            }), 409

        # Create outbox slot
        inserted = _gm.create_svrp_transfer(_transfer_id, uid)
        if not inserted:
            return jsonify({'error': 'معرّف الطلب مُستخدم — أرسل طلباً جديداً'}), 409

        # Read authoritative frozen balance from SQLite
        frozen = _gm.get_svrp_frozen_balance(uid)
        svrp_credits  = float(frozen.get('frozen_balance', 0) or 0)
        wager_done    = int(frozen.get('wagering_completed', 0) or 0)
        wager_req     = int(frozen.get('wagering_required', 3) or 3)

        if wager_done < wager_req:
            # Validation failure: cancel the pending slot so the client can retry
            # with a fresh transfer_id (or the same one on next attempt).
            try:
                _gm.mark_svrp_transfer_status(_transfer_id, uid, 'cancelled')
            except Exception:
                pass
            return jsonify({
                'error': (
                    f'لم تكتمل متطلبات الرهان — '
                    f'أكمل {wager_req - wager_done} معاملة أولاً.'
                ),
                'wagering_remaining': wager_req - wager_done,
            }), 400
        if svrp_credits <= 0:
            try:
                _gm.mark_svrp_transfer_status(_transfer_id, uid, 'cancelled')
            except Exception:
                pass
            return jsonify({'error': 'رصيد SVRP صفر — لا يوجد ما يُنقل'}), 400

        # Canonicalize amount (2dp, min 0.01) using live SQLite balance
        from decimal import Decimal as _Dec2, ROUND_DOWN as _RD2
        _raw_amt = parsed_amount if parsed_amount is not None else svrp_credits
        amount = float(_Dec2(str(_raw_amt)).quantize(_Dec2('0.01'), rounding=_RD2))
        if amount < 0.01:
            try:
                _gm.mark_svrp_transfer_status(_transfer_id, uid, 'cancelled')
            except Exception:
                pass
            return jsonify({'error': 'الحد الأدنى للنقل 0.01'}), 400
        if amount > svrp_credits + 1e-9:
            try:
                _gm.mark_svrp_transfer_status(_transfer_id, uid, 'cancelled')
            except Exception:
                pass
            return jsonify({
                'error': f'المبلغ ({amount:.2f}) يتجاوز رصيد SVRP ({svrp_credits:.2f})'
            }), 400
        amount = min(amount, round(svrp_credits, 2))

        # Atomic: debit SQLite wallet + CAS outbox pending→debited in one SAVEPOINT
        try:
            ok = _gm.debit_svrp_balance_for_transfer(_transfer_id, uid, amount)
        except ValueError as _ve:
            try:
                _gm.mark_svrp_transfer_status(_transfer_id, uid, 'cancelled')
            except Exception:
                pass
            return jsonify({'error': str(_ve)}), 400
        except Exception as _e1:
            try:
                _gm.mark_svrp_transfer_status(_transfer_id, uid, 'cancelled')
            except Exception:
                pass
            return jsonify({'error': f'خطأ في خصم SVRP: {_e1}'}), 500
        if not ok:
            # Transfer not in pending state (concurrent request or stale key)
            return jsonify({'error': 'خطأ داخلي — تعارض في الطلب'}), 409

    # ── Step B: credit game balance (idempotent via SAVEPOINT + STATUS-CAS) ──
    # add_balance_for_svrp_transfer:
    #   status='debited'   → SAVEPOINT: credit game_balance + CAS to 'completed'
    #   status='completed' → idempotent replay (no re-credit)
    #   uid mismatch       → raises PermissionError
    #   wrong state        → raises ValueError
    try:
        new_game_balance = _gm.add_balance_for_svrp_transfer(uid, amount, _transfer_id)
    except Exception as _e2:
        import logging as _cl
        _cl.getLogger('svrp_transfer').critical(
            'Game credit FAILED uid=%s transfer=%s amount=%s error=%s',
            uid, _transfer_id, amount, _e2
        )
        # SQLite wallet is already debited.  Keep status='debited' so client
        # can retry safely with the same transfer_id.  No CSV rollback needed.
        return jsonify({
            'error': (
                f'فشل إضافة رصيد اللعب — أعد المحاولة باستخدام '
                f'transfer_id="{_transfer_id}"'
            ),
            'transfer_id': _transfer_id,
            'retry': True,
        }), 500

    # ── Success ───────────────────────────────────────────────────────────────
    new_svrp = float(_gm.get_svrp_frozen_balance(uid).get('frozen_balance', 0) or 0)
    return jsonify({
        'success':          True,
        'transferred':      round(amount, 2),
        'new_game_balance': new_game_balance,
        'new_svrp_credits': new_svrp,
        'transfer_id':      _transfer_id,
    })

@app.route('/webapp/wallet')
def webapp_wallet():
    """صفحة محفظة اللاعب — محمية بـ uid أو s"""
    uid = request.args.get('uid', '').strip()
    s   = request.args.get('s', '').strip()
    lang = request.args.get('lang', 'ar').strip()
    return render_template('wallet.html', uid=uid, s=s, lang=lang)


@app.route('/api/wallet/add', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_wallet_add():
    """إضافة رصيد (أدمن)"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = data.get('uid', '')
    amount = float(data.get('amount', 0))
    reason = data.get('reason', 'admin_adjustment')
    if not uid or amount <= 0:
        return jsonify({'error': 'Invalid params'}), 400
    new_balance = _gm.add_balance(uid, amount, reason)
    return jsonify({'success': True, 'new_balance': new_balance})

# ===== Live Players =====

@app.route('/api/games/live-players')
@webapp_auth
def api_live_players():
    """قائمة اللاعبين المباشرين"""
    if not _VEX_GAMES:
        return jsonify({'players': [], 'count': 0})
    # قراءة آخر جلسات نشطة
    players = []
    try:
        import os
        sessions_file = os.path.join(BASE_DIR, 'game_sessions.csv')
        if os.path.exists(sessions_file):
            rows = []
            with open(sessions_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            # آخر 20 جلسة
            for row in rows[-20:]:
                players.append({
                    'uid': row.get('user_id', ''),
                    'name': '',  # يتم جلب الاسم من users.csv
                    'bet': float(row.get('bet_amount', 0) or 0),
                    'status': 'win' if row.get('result') == 'win' else 'lose',
                    'payout': float(row.get('payout', 0) or 0),
                    'multiplier': float(row.get('multiplier', 0) or 0),
                    'timestamp': row.get('timestamp', '')
                })
    except:
        pass
    return jsonify({'players': players, 'count': len(players)})

# ===== Game Engine =====

@app.route('/api/engine/start', methods=['POST'])
@webapp_auth
def api_engine_start():
    """بدء جلسة لعب"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    game_id = data.get('game_id', '')
    bet_amount = float(data.get('bet_amount', 0))
    if not uid or not game_id or bet_amount <= 0:
        return jsonify({'error': 'Missing params'}), 400
    result = _gm.start_session(uid, game_id, bet_amount)
    return jsonify(result)

@app.route('/api/engine/end', methods=['POST'])
@webapp_auth
def api_engine_end():
    """إنهاء جلسة لعب"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    result = _gm.end_session(
        session_id=data.get('session_id', ''),
        user_id=uid,
        game_id=data.get('game_id', ''),
        bet_amount=float(data.get('bet_amount', 0)),
        result=data.get('result', 'lose'),
        payout=float(data.get('payout', 0))
    )
    return jsonify(result)

@app.route('/api/engine/result', methods=['POST'])
@webapp_auth
def api_engine_result():
    """تسجيل نتيجة من WebApp — يحسب الفوز/الخسارة server-side"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    game_id = data.get('game_id', '')
    bet_amount = float(data.get('bet_amount', 0))
    session_id = data.get('session_id', '')

    # بدء الجلسة (خصم + حساب الاحتمال)
    start_result = _gm.start_session(uid, game_id, bet_amount)
    if not start_result.get('success'):
        return jsonify(start_result)

    # تطبيق النتيجة — مضاعف ديناميكي
    decision = start_result.get('decision', 'force_lose')
    game_obj = _gm.get_game(game_id) or {}
    if decision == 'allow_win':
        player_profile = _gm.tracker.get_profile(uid)
        multiplier = _gm.calculate_payout_multiplier(game_obj, player_profile)
        payout = bet_amount * multiplier
        result_str = 'win'
    elif decision == 'near_miss':
        payout = 0
        result_str = 'lose'
    else:
        payout = 0
        result_str = 'lose'

    # إنهاء الجلسة
    end_result = _gm.end_session(
        session_id=start_result['session_id'],
        user_id=uid,
        game_id=game_id,
        bet_amount=bet_amount,
        result=result_str,
        payout=payout
    )

    # الأنماط النفسية
    psych = start_result.get('psychological_hints', {})

    return jsonify({
        'success': True,
        'result': result_str,
        'payout': payout,
        'balance_before': end_result['balance_before'],
        'balance_after': end_result['balance_after'],
        'decision': decision,
        'psychological_hints': psych,
        'near_miss': decision == 'near_miss',
        'session_id': start_result['session_id'],
    })

# ===== Quick Deposits =====

@app.route('/api/games/payment-methods')
@webapp_auth
def api_games_payment_methods():
    """وسائل الدفع النشطة المتاحة للألعاب — مفلترة حسب عملة المستخدم"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    uid = get_request_uid()
    user_info = _gm.get_user_info(uid)
    user_currency = user_info.get('currency', 'EGP')
    methods = _gm.get_games_payment_methods(user_currency)
    saved_methods = _gm.get_payment_methods(uid)
    return jsonify({
        'methods': methods,
        'saved_methods': saved_methods,
        'count': len(methods),
        'currency': user_currency
    })

@app.route('/api/deposit/quick', methods=['POST'])
@webapp_auth
def api_deposit_quick():
    """طلب إيداع سريع — ينشئ معاملة حقيقية في transactions.csv بملاحظة VEX"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    amount = float(data.get('amount', 0))
    method_id = data.get('method_id', '')
    method_name = data.get('method_name', '')
    method_account_data = data.get('method_account_data', '')
    player_wallet = data.get('player_wallet', '')
    save_method = data.get('save_method', False)
    purpose = data.get('purpose', '')  # 'lottery_tickets' = directed deposit
    ticket_count = int(data.get('ticket_count', 0) or 0)
    if not uid or amount <= 0 or not method_id:
        return jsonify({'error': 'Missing params'}), 400

    # Get user info for admin notification
    user_info = _gm.get_user_info(uid)
    user_name = user_info.get('name', '')
    customer_id = user_info.get('customer_id', '')
    currency = user_info.get('currency', 'SAR')

    dep_id = _gm.create_quick_deposit(
        uid, amount, method_id, method_account_data,
        method_name=method_name,
        method_account_data=method_account_data,
        player_wallet=player_wallet,
        save_method=save_method
    )

    # Push to dashboard — include purpose if directed deposit
    notif_title = '💰 إيداع محفظة VEX'
    notif_msg = f'اللاعب {user_name} ({customer_id}) طلب إيداع {amount} {currency}\nالوسيلة: {method_name}\nمحفظة اللاعب: {player_wallet}'
    if purpose == 'lottery_tickets' and ticket_count > 0:
        notif_title = f'🎟️ شراء تذاكر يانصيب ({ticket_count} تذكرة)'
        notif_msg = f'اللاعب {user_name} ({customer_id}) يريد شراء {ticket_count} تذكرة يانصيب\nالمبلغ: {amount} {currency}\nالوسيلة: {method_name}\nمحفظة اللاعب: {player_wallet}\n⏳ عند الموافقة سيتم شراء التذاكر تلقائياً'
    push_notification(
        'game_deposit',
        notif_title,
        notif_msg,
        {'deposit_id': dep_id, 'uid': uid, 'amount': amount, 'method': method_name,
         'purpose': purpose, 'ticket_count': ticket_count}
    )

    return jsonify({
        'success': True,
        'deposit_id': dep_id,
        'trans_id': f"DEP{datetime.now().strftime('%Y%m%d%H%M%S')}",
        'status': 'pending'
    })

@app.route('/api/deposit/pending')
@api_auth
def api_deposit_pending():
    """طلبات الإيداع المعلقة"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    deposits = _gm.get_pending_deposits()
    return jsonify({'deposits': deposits, 'count': len(deposits)})

@app.route('/api/deposit/<dep_id>/approve', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_deposit_approve(dep_id):
    """موافقة على إيداع سريع — async: يضيف الرصيد + يرسل إشعار"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    admin_id = session.get('admin_id', '')
    result = _gm.approve_deposit(dep_id, admin_id)
    if result:
        _rbac_log(str(admin_id), 'approve_deposit', target=dep_id,
                  details=f"amount={result.get('amount', '?')}", ip=request.remote_addr)
        push_notification('deposit_approved', '✅ تمت الموافقة على إيداع', f'إيداع {dep_id}', {'deposit_id': dep_id})
        # async Telegram notification (non-blocking)
        import threading as _th
        _uid = result.get('user_id', '')
        _amt = float(result.get('amount', 0))
        _dep = dep_id
        _purpose = result.get('purpose', '')
        _ticket_count = int(result.get('ticket_count', 0) or 0)

        # ── Directed deposit: auto-purchase lottery tickets ──
        if _purpose == 'lottery_tickets' and _ticket_count > 0:
            def _auto_buy_lottery():
                try:
                    # Generate tickets directly (bypass wallet — deposit IS the payment)
                    state = _get_or_create_lottery_round()
                    if state.get('drawn'):
                        # Round ended, add to wallet instead
                        _gm.add_balance(_uid, _amt)
                        return
                    new_tickets = []
                    for _ in range(_ticket_count):
                        nums = sorted(random.sample(range(1, _LOTTERY_MAX_NUMBER + 1), _LOTTERY_NUMBERS_COUNT))
                        new_tickets.append({
                            'id': f"T{int(datetime.now().timestamp()*1000)}_{random.randint(1000,9999)}",
                            'uid': str(_uid), 'numbers': nums,
                            'status': 'pending', 'scratched': False, 'drawn': None,
                        })
                    with _lottery_lock:
                        state = _load_lottery_state()
                        for t in new_tickets:
                            state.setdefault('tickets', []).append(t)
                        state['tickets_sold'] = state.get('tickets_sold', 0) + _ticket_count
                        state['prize_pool'] = round(state.get('prize_pool', 0) + _amt * 0.8, 2)
                        _save_lottery_state(state)
                    # Notify user
                    if BOT_TOKEN and _uid:
                        import urllib.request as _u
                        _msg = f"✅ تمت الموافقة على طلب شراء التذاكر!\n\n🎟️ تم شراء {_ticket_count} تذكرة يانصيف\n🆔 {_dep}"
                        _u.urlopen(_u.Request(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                            data=json.dumps({'chat_id': int(_uid), 'text': _msg, 'parse_mode': 'HTML'}).encode('utf-8'),
                            headers={'Content-Type': 'application/json'}), timeout=5)
                except Exception as e:
                    # Fallback: add to wallet if auto-buy fails
                    try: _gm.add_balance(_uid, _amt)
                    except: pass
            _th.Thread(target=_auto_buy_lottery, daemon=True).start()
            return jsonify({'success': True, 'deposit': result, 'auto_purchased': 'lottery'})

        # Normal deposit — add to wallet + notify
        def _notify():
            try:
                if BOT_TOKEN and _uid:
                    import urllib.request as _u
                    _msg = f"✅ تمت الموافقة على إيداعك!\n\n💰 المبلغ: {_amt:.0f}\n🎮 تم إضافته لمحفظة VEX\n🆔 {_dep}"
                    _u.urlopen(_u.Request(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                        data=json.dumps({'chat_id': int(_uid), 'text': _msg, 'parse_mode': 'HTML'}).encode('utf-8'),
                        headers={'Content-Type': 'application/json'}), timeout=5)
            except: pass
        _th.Thread(target=_notify, daemon=True).start()
        return jsonify({'success': True, 'deposit': result})
    return jsonify({'error': 'Deposit not found or already processed'}), 404

@app.route('/api/deposit/<dep_id>/reject', methods=['POST'])
@api_auth
@permission_required('reject_deposits')
def api_deposit_reject(dep_id):
    """رفض إيداع سريع — async notification"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    admin_id = session.get('admin_id', '')
    result = _gm.reject_deposit(dep_id, admin_id)
    _rbac_log(str(admin_id), 'reject_deposit', target=dep_id,
              details='rejected', ip=request.remote_addr)
    push_notification('deposit_rejected', '❌ تم رفض إيداع', f'إيداع {dep_id}', {'deposit_id': dep_id})
    # async Telegram notification
    if result and result.get('user_id'):
        import threading as _th
        _uid = result.get('user_id', '')
        _dep = dep_id
        def _notify_r():
            try:
                if BOT_TOKEN and _uid:
                    import urllib.request as _u
                    _msg = f"❌ تم رفض إيداعك\n\n🆔 {_dep}\n\nللمساعدة، تواصل مع الدعم."
                    _u.urlopen(_u.Request(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                        data=json.dumps({'chat_id': int(_uid), 'text': _msg, 'parse_mode': 'HTML'}).encode('utf-8'),
                        headers={'Content-Type': 'application/json'}), timeout=5)
            except: pass
        _th.Thread(target=_notify_r, daemon=True).start()
    return jsonify({'success': True})

# ===== Player Payment Methods =====

@app.route('/api/player/currency', methods=['POST'])
@webapp_auth
def api_player_change_currency():
    """تغيير عملة المستخدم في users.csv"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    new_currency = data.get('currency', 'EGP')
    try:
        rows = []
        with open(os.path.join(BASE_DIR, 'users.csv'), 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                if row.get('telegram_id') == str(uid):
                    row['currency'] = new_currency
                rows.append(row)
        with open(os.path.join(BASE_DIR, 'users.csv'), 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return jsonify({'success': True, 'currency': new_currency})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/player/methods')
@webapp_auth
def api_player_methods():
    """وسائل دفع اللاعب المحفوظة"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    uid = get_request_uid()
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    methods = _gm.get_payment_methods(uid)
    return jsonify({'methods': methods})

@app.route('/api/player/methods/add', methods=['POST'])
@webapp_auth
def api_player_methods_add():
    """إضافة وسيلة دفع للاعب"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    method_id = _gm.add_payment_method(
        user_id=uid,
        method_name=data.get('method_name', ''),
        account_number=data.get('account_number', ''),
        method_type=data.get('method_type', 'bank'),
        icon=data.get('icon', '💳')
    )
    return jsonify({'success': True, 'method_id': method_id})

# ===== Player Profile =====

@app.route('/api/player/profile')
@webapp_auth
def api_player_profile():
    """ملف اللاعب — يشمل الرصيد الحقيقي ورقم العميل"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    uid = get_request_uid()
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    profile = _gm.tracker.get_profile(uid)
    segment = _gm.tracker.get_segment(profile)
    balance = _gm.get_balance(uid)
    currency = _gm.get_user_currency(uid)
    user_row = _gm.get_user_info(uid) if hasattr(_gm, 'get_user_info') else {}
    customer_id = user_row.get('customer_id', '') if user_row else ''
    return jsonify({
        'profile': profile,
        'segment': segment,
        'balance': balance,
        'currency': currency,
        'customer_id': customer_id,
    })

@app.route('/api/player/vex-status', methods=['POST'])
@api_auth
@permission_required('ban_users')
def api_player_vex_status():
    """تعيين شريك VEX"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = data.get('uid', '')
    is_partner = data.get('is_partner', False)
    _gm.tracker.set_vex_partner(uid, is_partner)
    return jsonify({'success': True})

# ===== Admin: Platform Stats =====

@app.route('/api/games/stats')
@api_auth
def api_games_stats():
    """إحصائيات المنصة"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    stats = _gm.get_platform_stats()
    health = _gm.risk.check_platform_health()
    return jsonify({**stats, 'health': health})

@app.route('/api/games/alerts')
@api_auth
def api_games_alerts():
    """تنبيهات المخاطر"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    alerts = _gm.risk.get_active_alerts()
    return jsonify({'alerts': alerts, 'count': len(alerts)})

@app.route('/api/games/top-players')
@api_auth
def api_games_top_players():
    """أعلى اللاعبين"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    sort_by = request.args.get('sort', 'total_wagered')
    players = _gm.tracker.get_top_players(limit=20, sort_by=sort_by)
    return jsonify({'players': players})

@app.route('/api/games/config', methods=['GET', 'POST'])
@api_auth
@permission_required('manage_games')
def api_games_config():
    """قراءة/تحديث إعدادات الخوارزمية"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    if request.method == 'POST':
        data = request.json
        for key, value in data.items():
            _gm.algorithm.update_config(key, value)
        return jsonify({'success': True})
    else:
        return jsonify({'config': _gm.algorithm.config})

# ===== Games WebApp Pages =====

@app.route('/webapp/games')
def webapp_games():
    """مركز الألعاب — WebApp"""
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    return render_template('games_hub.html', uid=uid, lang=lang)

@app.route('/webapp/play/<game_id>')
def webapp_play(game_id):
    """شاشة اللعبة — WebApp"""
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    if not _VEX_GAMES:
        return "Games engine not available", 500
    game = _gm.get_game(game_id)
    if not game:
        return "Game not found", 404
    return render_template('game_play.html', uid=uid, lang=lang, game=game)

@app.route('/games-admin')
@admin_required
@page_permission_required('manage_games')
def page_games_admin():
    """لوحة إدارة الألعاب"""
    return render_template('games_admin.html', active_page='games_admin')

# ===== Aviator — WebApp + API =====

@app.route('/webapp/aviator')
def webapp_aviator():
    """لعبة Aviator — WebApp"""
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    return render_template('aviator.html', uid=uid, lang=lang)

# Legacy Aviator per-player endpoints removed — replaced by global round system in aviator_engine.py

# ===== Wallet Withdrawal =====

@app.route('/api/wallet/withdraw', methods=['POST'])
@webapp_auth
def api_wallet_withdraw():
    """طلب سحب من محفظة الألعاب"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    amount = float(data.get('amount', 0))
    method_id = data.get('method_id', '')
    account_number = data.get('account_number', '')
    if not uid or amount <= 0:
        return jsonify({'error': 'Missing params'}), 400
    dep_id, error = _gm.create_withdrawal(uid, amount, method_id, account_number)
    if error:
        return jsonify({'success': False, 'error': error})
    push_notification('game_withdrawal', '💸 طلب سحب جديد', f'لاعب {uid} طلب سحب {amount}', {'withdrawal_id': dep_id, 'uid': uid, 'amount': amount})
    return jsonify({'success': True, 'withdrawal_id': dep_id, 'status': 'pending'})

@app.route('/api/withdrawal/pending')
@api_auth
def api_withdrawal_pending():
    """طلبات السحب المعلقة"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    withdrawals = _gm.get_pending_withdrawals()
    return jsonify({'withdrawals': withdrawals, 'count': len(withdrawals)})

@app.route('/api/withdrawal/<wth_id>/approve', methods=['POST'])
@api_auth
@permission_required('approve_withdrawals')
def api_withdrawal_approve(wth_id):
    """موافقة على سحب"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    admin_id = session.get('admin_id', '')
    result = _gm.approve_withdrawal(wth_id, admin_id)
    if result:
        _rbac_log(str(admin_id), 'approve_withdrawal', target=wth_id,
                  details=f"amount={result.get('amount', '?')}", ip=request.remote_addr)
        push_notification('withdrawal_approved', '✅ تمت الموافقة على سحب', f'سحب {wth_id} تمت الموافقة', {'withdrawal_id': wth_id})
        return jsonify({'success': True, 'withdrawal': result})
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/withdrawal/<wth_id>/reject', methods=['POST'])
@api_auth
@permission_required('reject_withdrawals')
def api_withdrawal_reject(wth_id):
    """رفض سحب — إعادة الرصيد"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    admin_id = session.get('admin_id', '')
    result = _gm.reject_withdrawal(wth_id, admin_id)
    if result:
        _rbac_log(str(admin_id), 'reject_withdrawal', target=wth_id,
                  details='rejected — balance returned', ip=request.remote_addr)
        push_notification('withdrawal_rejected', '❌ تم رفض سحب', f'سحب {wth_id} تم رفض — الرصيد مُرتجع', {'withdrawal_id': wth_id})
        return jsonify({'success': True, 'withdrawal': result})
    return jsonify({'error': 'Not found'}), 404

# ===== Admin Per-Player Controls =====

@app.route('/api/admin/player/<uid>/win-override', methods=['POST'])
@api_auth
@permission_required('manage_games')
def api_admin_win_override(uid):
    """تحكم أدمن باحتمال فوز لاعب محدد"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    win_override = float(data.get('win_override', 0))
    # 0 = عادي، >0 = احتمال محدد، -1 = خسارة مضمونة
    profile = _gm.tracker.get_profile(uid)
    profile['admin_win_override'] = str(win_override)
    _gm.tracker._save_profile(profile)
    return jsonify({'success': True, 'win_override': win_override})

@app.route('/api/admin/player/<uid>/balance', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_admin_player_balance(uid):
    """إضافة/خصم رصيد يدوي"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    amount = float(data.get('amount', 0))
    if amount > 0:
        new_bal = _gm.add_balance(uid, amount)
    else:
        _, new_bal = _gm.deduct_balance(uid, abs(amount))
    return jsonify({'success': True, 'new_balance': new_bal})

@app.route('/api/admin/player/<uid>/block', methods=['POST'])
@api_auth
@permission_required('ban_users')
def api_admin_block_player(uid):
    """حظر لاعب من اللعب"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    _gm.tracker.set_cooldown(uid, minutes=1440)  # 24 ساعة
    return jsonify({'success': True})

@app.route('/api/admin/player/<uid>/cooldown', methods=['POST'])
@api_auth
@permission_required('ban_users')
def api_admin_cooldown_player(uid):
    """تبريد لاعب"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    minutes = int(data.get('minutes', 15))
    _gm.tracker.set_cooldown(uid, minutes=minutes)
    return jsonify({'success': True, 'cooldown_minutes': minutes})

@app.route('/api/admin/player/<uid>/vex', methods=['POST'])
@api_auth
@permission_required('ban_users')
def api_admin_vex_partner(uid):
    """تفعيل/إيقاف شريك VEX"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    is_partner = data.get('is_partner', False)
    _gm.tracker.set_vex_partner(uid, is_partner)
    return jsonify({'success': True})

# ===== Crash — WebApp + API =====

@app.route('/webapp/crash')
def webapp_crash():
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    return render_template('crash.html', uid=uid, lang=lang)

# Crash game logic now lives in dashboard/crash_engine.py
# Legacy /api/engine/crash/* endpoints removed — replaced by global round system.

# ===== Dice — WebApp + API =====

@app.route('/webapp/dice')
def webapp_dice():
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    return render_template('dice.html', uid=uid, lang=lang)

# Dice game logic lives in dashboard/dice_engine.py

# ===== Mines — WebApp + API =====

@app.route('/webapp/mines')
def webapp_mines():
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    return render_template('mines.html', uid=uid, lang=lang)

@app.route('/api/engine/mines/start', methods=['POST'])
@webapp_auth
def api_mines_start():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    bet_amount = float(data.get('bet_amount', 0))
    mine_count = int(data.get('mine_count', 3))
    if not uid or bet_amount <= 0:
        return jsonify({'error': 'Missing params'}), 400
    mine_count = max(1, min(24, mine_count))

    player = _gm.tracker.get_profile(uid)
    game = _gm.get_game('GAME006')
    if not game:
        game = {'id': 'GAME006', 'base_win_chance': '0.45', 'house_edge_pct': '15', 'min_bet': '10', 'max_bet': '2000'}

    risk_check = _gm.risk.check_risk(player, bet_amount, game)
    if not risk_check['allowed']:
        return jsonify({'success': False, 'error': risk_check['alerts'][0]['message'] if risk_check['alerts'] else 'محظور'})

    balance = _gm.get_balance(uid)
    if balance < bet_amount:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance})

    import random as _rng
    # Place mines randomly
    all_positions = list(range(25))
    _rng.shuffle(all_positions)
    mine_positions = all_positions[:mine_count]

    # Algorithm decides if player should win overall
    algo_result = _gm.algorithm.calculate_win_chance(player, game, bet_amount)
    win_chance = algo_result['win_chance']

    # If algorithm says lose, ensure first revealed tile near mines
    # If algorithm says win, keep mines away from common first picks (center)
    if algo_result['decision'] == 'force_lose' and _rng.random() < 0.6:
        # Bias: move a mine near center (positions 6,7,8,11,12,13,16,17,18)
        center_positions = [6,7,8,11,12,13,16,17,18]
        non_center_mines = [m for m in mine_positions if m not in center_positions]
        if non_center_mines:
            swap_out = _rng.choice(non_center_mines)
            swap_in = _rng.choice([c for c in center_positions if c not in mine_positions])
            mine_positions.remove(swap_out)
            mine_positions.append(swap_in)

    success, balance_after = _gm.deduct_balance(uid, bet_amount)
    if not success:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': 0})

    session_id = f"MINE{str(int(datetime.now().timestamp()))[-8:]}"
    _gm.algorithm.log_decision(
        session_id=session_id, user_id=uid, game_id='GAME006',
        base_chance=float(game.get('base_win_chance', 0.45)),
        adjusted_chance=win_chance, factors=algo_result['factors'],
        decision=algo_result['decision'],
        reason=f"Mines count={mine_count}; {algo_result['reason']}"
    )

    # Store mine positions in a temp file keyed by session.
    # _engine_mines_lock serialises all read-prune-write cycles on mines_sessions.json.
    import json as _json
    mines_state_file = os.path.join(BASE_DIR, 'mines_sessions.json')
    with _engine_mines_lock:
        mines_state = {}
        try:
            if os.path.exists(mines_state_file):
                with open(mines_state_file, 'r') as f:
                    mines_state = _json.load(f)
        except Exception:
            pass
        # Prune stale sessions before adding the new one
        mines_state = _prune_stale_mines_sessions(mines_state)
        mines_state[session_id] = {
            'uid': uid, 'mine_positions': mine_positions, 'bet_amount': bet_amount,
            'mine_count': mine_count, 'revealed': [], 'multiplier': 1.0,
            'game_over': False, 'created_at': datetime.now().isoformat()
        }
        with open(mines_state_file, 'w') as f:
            _json.dump(mines_state, f)

    return jsonify({'success': True, 'session_id': session_id, 'balance_before': balance, 'balance_after': balance_after})

@app.route('/api/engine/mines/reveal', methods=['POST'])
@webapp_auth
def api_engine_mines_reveal():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    session_id = data.get('session_id', '')
    tile_index = int(data.get('tile_index', -1))
    if tile_index < 0 or tile_index > 24:
        return jsonify({'error': 'Invalid tile'}), 400

    import json as _json
    mines_state_file = os.path.join(BASE_DIR, 'mines_sessions.json')

    resp_data = None
    with _engine_mines_lock:
        if not os.path.exists(mines_state_file):
            return jsonify({'error': 'Session not found'}), 404
        try:
            with open(mines_state_file, 'r') as f:
                mines_state = _json.load(f)
        except Exception:
            return jsonify({'error': 'State error'}), 500

        # Prune stale sessions on every read (lazy cleanup, under lock)
        mines_state = _prune_stale_mines_sessions(mines_state)

        state = mines_state.get(session_id)
        if not state or state.get('uid') != uid or state.get('game_over'):
            return jsonify({'error': 'Invalid session'}), 400

        if tile_index in state['revealed']:
            return jsonify({'error': 'Already revealed'}), 400

        mine_positions = state['mine_positions']
        is_mine = tile_index in mine_positions
        state['revealed'].append(tile_index)

        if is_mine:
            state['game_over'] = True
            state['multiplier'] = 0
            with open(mines_state_file, 'w') as f:
                _json.dump(mines_state, f)
            resp_data = {'success': True, 'is_mine': True, 'multiplier': 0, 'game_over': True}
        else:
            # Calculate multiplier based on revealed count and mine count
            revealed_count = len(state['revealed'])
            safe_count = 25 - state['mine_count']
            mult = 1.0
            for i in range(revealed_count):
                mult *= (25 - i) / (25 - state['mine_count'] - i)
            game = _gm.get_game('GAME006')
            house_edge = float(game.get('house_edge_pct', 15)) / 100 if game else 0.15
            mult *= (1 - house_edge * 0.5)
            state['multiplier'] = round(mult, 4)

            game_over = revealed_count >= safe_count
            if game_over:
                state['game_over'] = True

            with open(mines_state_file, 'w') as f:
                _json.dump(mines_state, f)
            resp_data = {'success': True, 'is_mine': False, 'multiplier': state['multiplier'], 'game_over': game_over}

    return jsonify(resp_data)

@app.route('/api/engine/mines/cashout', methods=['POST'])
@webapp_auth
def api_engine_mines_cashout():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    session_id = data.get('session_id', '')
    multiplier = float(data.get('multiplier', 1.0))
    bet_amount = float(data.get('bet_amount', 0))

    import json as _json
    mines_state_file = os.path.join(BASE_DIR, 'mines_sessions.json')
    with _engine_mines_lock:
        try:
            with open(mines_state_file, 'r') as f:
                mines_state = _json.load(f)
            # Prune stale sessions on every write path (under lock)
            mines_state = _prune_stale_mines_sessions(mines_state)
            state = mines_state.get(session_id)
            if state:
                state['game_over'] = True
                with open(mines_state_file, 'w') as f:
                    _json.dump(mines_state, f)
        except Exception:
            pass

    payout = bet_amount * multiplier
    new_balance = _gm.add_balance(uid, payout)
    return jsonify({'success': True, 'payout': payout, 'multiplier': multiplier, 'balance_after': new_balance})

@app.route('/api/engine/mines/end', methods=['POST'])
@webapp_auth
def api_mines_end():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    won = data.get('won', False)
    multiplier = float(data.get('multiplier', 0))
    bet_amount = float(data.get('bet_amount', 0))
    session_id = data.get('session_id', '')
    result = 'win' if won else 'lose'
    payout = bet_amount * multiplier if won else 0
    _gm.tracker.log_session({'session_id': session_id, 'game_id': 'GAME006', 'user_id': uid, 'bet_amount': bet_amount, 'payout': payout, 'result': result, 'balance_before': 0, 'balance_after': _gm.get_balance(uid), 'multiplier': multiplier})
    _gm.tracker.update_profile(uid, {'bet_amount': bet_amount, 'payout': payout, 'result': result, 'game_id': 'GAME006', 'balance_after': _gm.get_balance(uid)})
    return jsonify({'success': True, 'result': result, 'payout': payout})

# ===== Plinko — WebApp + API =====

@app.route('/webapp/plinko')
def webapp_plinko():
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    return render_template('plinko.html', uid=uid, lang=lang)

@app.route('/webapp/wheel')
def webapp_wheel():
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    return render_template('wheel.html', uid=uid, lang=lang)

@app.route('/webapp/lottery')
def webapp_lottery():
    uid = request.args.get('uid', '')
    lang = request.args.get('lang', 'ar')
    return render_template('lottery.html', uid=uid, lang=lang)

@app.route('/api/engine/plinko/start', methods=['POST'])
@webapp_auth
def api_plinko_start():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    bet_amount = float(data.get('bet_amount', 0))
    if not uid or bet_amount <= 0:
        return jsonify({'error': 'Missing params'}), 400

    player = _gm.tracker.get_profile(uid)
    game = _gm.get_game('GAME007')
    if not game:
        game = {'id': 'GAME007', 'base_win_chance': '0.40', 'house_edge_pct': '16', 'min_bet': '10', 'max_bet': '2000'}

    risk_check = _gm.risk.check_risk(player, bet_amount, game)
    if not risk_check['allowed']:
        return jsonify({'success': False, 'error': risk_check['alerts'][0]['message'] if risk_check['alerts'] else 'محظور'})

    balance = _gm.get_balance(uid)
    if balance < bet_amount:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance})

    import random as _rng
    # 13 slots (0-12), multipliers: [10, 3, 1.5, 1, 0.5, 0.3, 0.2, 0.3, 0.5, 1, 1.5, 3, 10]
    MULTIPLIERS = [10, 3, 1.5, 1, 0.5, 0.3, 0.2, 0.3, 0.5, 1, 1.5, 3, 10]

    algo_result = _gm.algorithm.calculate_win_chance(player, game, bet_amount)
    win_chance = algo_result['win_chance']

    # Weight slot selection based on win_chance
    # High win_chance → bias toward edges (high multipliers)
    # Low win_chance → bias toward center (low multipliers)
    if win_chance > 0.6:
        # Bias toward edge slots (0, 12 = 10x)
        weights = [5, 4, 3, 2, 1, 1, 1, 1, 1, 2, 3, 4, 5]
    elif win_chance > 0.4:
        weights = [2, 3, 3, 3, 2, 2, 2, 2, 2, 3, 3, 3, 2]
    else:
        # Bias toward center (low multipliers)
        weights = [1, 1, 2, 2, 3, 4, 5, 4, 3, 2, 2, 1, 1]

    total_weight = sum(weights)
    rand_val = _rng.uniform(0, total_weight)
    target_slot = 0
    cumulative = 0
    for i, w in enumerate(weights):
        cumulative += w
        if rand_val <= cumulative:
            target_slot = i
            break

    multiplier = MULTIPLIERS[target_slot]
    payout = bet_amount * multiplier
    result = 'win' if multiplier >= 1 else 'lose'

    # Apply disguised loss: if bet > 50 and multiplier < 1, sometimes show as small win
    if bet_amount > 50 and multiplier < 1 and _rng.random() < 0.3 and algo_result['decision'] != 'force_lose':
        # Find a nearby slot with multiplier 0.5-0.9
        for offset in range(1, 4):
            for direction in [1, -1]:
                check_slot = target_slot + direction * offset
                if 0 <= check_slot < len(MULTIPLIERS) and MULTIPLIERS[check_slot] >= 0.5:
                    target_slot = check_slot
                    multiplier = MULTIPLIERS[check_slot]
                    payout = bet_amount * multiplier
                    break
            else:
                continue
            break

    # Atomic full settlement (bet AND payout in one SQLite transaction) —
    # /end no longer credits anything, so the outcome is final here and a
    # crash mid-animation can never strand the stake or the win.
    session_id = f"PLNK{str(int(datetime.now().timestamp()))[-8:]}"
    _req_id = str((request.json or {}).get('request_id', '') or '')[:64]
    _template = {'success': True, 'session_id': session_id, 'target_slot': target_slot,
                 'multiplier': multiplier, 'payout': round(payout, 2), 'result': result,
                 'balance_before': balance}
    ok, stored, race_cached = _gm.settle_with_idempotency(uid, bet_amount, payout, _req_id, _template)
    if race_cached:
        return jsonify(race_cached)
    if not ok:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': 0})
    balance_after = stored.get('balance_after', balance)
    _gm.algorithm.log_decision(
        session_id=session_id, user_id=uid, game_id='GAME007',
        base_chance=float(game.get('base_win_chance', 0.40)),
        adjusted_chance=win_chance, factors=algo_result['factors'],
        decision=algo_result['decision'],
        reason=f"Plinko slot={target_slot} mult={multiplier}; {algo_result['reason']}"
    )

    return jsonify({
        'success': True, 'session_id': session_id, 'target_slot': target_slot,
        'multiplier': multiplier, 'payout': round(payout, 2), 'result': result,
        'balance_before': balance, 'balance_after': balance_after
    })

@app.route('/api/engine/plinko/end', methods=['POST'])
@webapp_auth
def api_plinko_end():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    uid = get_request_uid()
    session_id = str(data.get('session_id', ''))[:32]
    # SECURITY: the client-supplied payout is NEVER credited here. The full
    # settlement (bet + payout) is done atomically at /start; /end only
    # acknowledges the animation finished. Crediting client-reported numbers
    # allowed arbitrary-payout forgery and replay.
    _gm.tracker.update_profile(uid, {'bet_amount': 0, 'payout': 0, 'result': 'ack',
                                     'game_id': 'GAME007', 'balance_after': _gm.get_balance(uid)})
    # Echo client fields for old-client response compatibility — NOT credited.
    return jsonify({'success': True, 'session_id': session_id,
                    'result': str(data.get('result', 'lose'))[:8],
                    'payout': float(data.get('payout', 0) or 0)})

# ===== Mines — Frontend API (/api/mines/*) =====
# Sessions keyed by uid so reveal/cashout don't need a session_id param.

_mines_lock = threading.Lock()
# Separate lock for the legacy engine mines_sessions.json file so every
# read-prune-write cycle is atomic and the cleanup daemon cannot race with routes.
_engine_mines_lock = threading.Lock()

# ===== Per-user locking + request-ID idempotency =====
# Pattern mirrors aviator_engine's _request_cache approach.
# Client sends X-Request-Id header (or request_id body field) per logical action.
# The server acquires a per-user lock, checks the cache atomically, and stores the
# result before releasing — so concurrent retries never double-charge.

import time as _idem_time

_user_locks = {}          # { uid: threading.Lock() }
_user_locks_lock = threading.Lock()
_request_results = {}     # { (uid, request_id): {'result': dict, 'exp': float} }
_REQUEST_RESULT_TTL = 300  # 5 minutes

def _get_user_lock(uid):
    with _user_locks_lock:
        if uid not in _user_locks:
            _user_locks[uid] = threading.Lock()
        return _user_locks[uid]

def _get_request_id():
    """Extract client-supplied idempotency key from header or body."""
    rid = request.headers.get('X-Request-Id', '')
    if not rid:
        try:
            rid = (request.get_json(silent=True) or {}).get('request_id', '')
        except Exception:
            pass
    return rid or None

def _check_request_cache(uid, request_id):
    """Check for a previously stored result (must be called while holding user lock)."""
    if not request_id:
        return None
    entry = _request_results.get((uid, request_id))
    if entry and entry['exp'] > _idem_time.time():
        return entry['result']
    return None

def _store_request_result(uid, request_id, result):
    """Persist result for future retries (must be called while holding user lock)."""
    if not request_id:
        return
    # Prune stale entries lazily
    now = _idem_time.time()
    expired = [k for k, v in list(_request_results.items()) if v['exp'] <= now]
    for k in expired:
        _request_results.pop(k, None)
    _request_results[(uid, request_id)] = {'result': result, 'exp': now + _REQUEST_RESULT_TTL}

# ===

_MINES_SESSION_TTL_MINUTES = 30  # sessions older than this are pruned

def _mines_session_file():
    return os.path.join(BASE_DIR, 'mines_user_sessions.json')

def _prune_stale_mines_sessions(sessions, ttl_minutes=_MINES_SESSION_TTL_MINUTES):
    """Return a copy of *sessions* with entries older than ttl_minutes removed.

    A session is considered stale when its created_at timestamp is more than
    ttl_minutes ago.  Sessions that are missing a created_at field, or whose
    timestamp cannot be parsed, are treated as stale and pruned.
    """
    cutoff = datetime.now() - timedelta(minutes=ttl_minutes)
    pruned = {}
    for key, sess in sessions.items():
        created_str = sess.get('created_at', '')
        try:
            created_dt = datetime.fromisoformat(created_str)
            if created_dt >= cutoff:
                pruned[key] = sess
        except Exception:
            # Unparseable timestamp — treat as stale
            pass
    return pruned
def _load_mines_sessions():
    """Load mines user sessions, pruning any stale entries before returning."""
    try:
        f = _mines_session_file()
        if os.path.exists(f):
            with open(f, 'r') as fh:
                sessions = json.load(fh)
            pruned = _prune_stale_mines_sessions(sessions)
            if len(pruned) != len(sessions):
                # Persist the pruned state immediately so the file stays clean
                try:
                    with open(f, 'w') as fh:
                        json.dump(pruned, fh)
                except Exception:
                    pass
            return pruned
    except Exception:
        pass
    return {}

def _save_mines_sessions(state):
    try:
        with open(_mines_session_file(), 'w') as fh:
            json.dump(state, fh)
    except Exception:
        pass

def _prune_engine_mines_sessions_file():
    """Prune stale entries from mines_sessions.json (legacy engine flow) and
    persist the result to disk.  Called from the background cleanup daemon.
    Holds _engine_mines_lock for the entire read-prune-write cycle."""
    import json as _json
    mines_state_file = os.path.join(BASE_DIR, 'mines_sessions.json')
    with _engine_mines_lock:
        try:
            if not os.path.exists(mines_state_file):
                return
            with open(mines_state_file, 'r') as fh:
                mines_state = _json.load(fh)
            pruned = _prune_stale_mines_sessions(mines_state)
            if len(pruned) != len(mines_state):
                with open(mines_state_file, 'w') as fh:
                    _json.dump(pruned, fh)
                _auth_logger.info(
                    "mines_sessions.json: pruned %d stale session(s), %d remaining.",
                    len(mines_state) - len(pruned), len(pruned)
                )
        except Exception as exc:
            _auth_logger.error("_prune_engine_mines_sessions_file error: %s", exc)
@app.route('/api/mines/new', methods=['POST'])
@webapp_auth
def api_mines_new():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json or {}
    uid = get_request_uid()
    request_id = _get_request_id()
    if not uid:
        return jsonify({'error': 'Missing params'}), 400

    # Fast idempotency check (SQLite read, survives restarts)
    if request_id:
        cached = _gm.get_idempotency_record(uid, request_id)
        if cached:
            return jsonify(cached)

    bet_amount = float(data.get('bet', 0))
    mine_count = int(data.get('mines_count', 3))
    if bet_amount <= 0:
        return jsonify({'error': 'Missing params'}), 400
    mine_count = max(1, min(24, mine_count))

    player = _gm.tracker.get_profile(uid)
    game = _gm.get_game('GAME006') or {
        'id': 'GAME006', 'base_win_chance': '0.45', 'house_edge_pct': '15',
        'min_bet': '10', 'max_bet': '2000'
    }

    risk_check = _gm.risk.check_risk(player, bet_amount, game)
    if not risk_check['allowed']:
        msg = risk_check['alerts'][0]['message'] if risk_check.get('alerts') else 'محظور'
        return jsonify({'success': False, 'error': msg})

    balance = _gm.get_balance(uid)
    if balance < bet_amount:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance})

    all_positions = list(range(25))
    random.shuffle(all_positions)
    mine_positions = all_positions[:mine_count]

    algo_result = _gm.algorithm.calculate_win_chance(player, game, bet_amount)
    if algo_result['decision'] == 'force_lose' and random.random() < 0.6:
        center_positions = [6, 7, 8, 11, 12, 13, 16, 17, 18]
        non_center = [m for m in mine_positions if m not in center_positions]
        if non_center:
            swap_out = random.choice(non_center)
            available = [c for c in center_positions if c not in mine_positions]
            if available:
                mine_positions.remove(swap_out)
                mine_positions.append(random.choice(available))

    game_id = f"MNW{str(int(datetime.now().timestamp()))[-8:]}"

    # Atomic: deduct bet (payout=0) + record idempotency in one SQLite transaction
    # Template has game_id/balance_before; balance_after is filled in by settle_with_idempotency
    template = {'success': True, 'game_id': game_id, 'balance_before': balance}
    ok, stored, race_cached = _gm.settle_with_idempotency(uid, bet_amount, 0, request_id, template)
    if race_cached:
        return jsonify(race_cached)
    if not ok:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance})

    result = stored  # has balance_after

    _gm.algorithm.log_decision(
        session_id=game_id, user_id=uid, game_id='GAME006',
        base_chance=float(game.get('base_win_chance', 0.45)),
        adjusted_chance=algo_result['win_chance'], factors=algo_result['factors'],
        decision=algo_result['decision'],
        reason=f"Mines count={mine_count}; {algo_result['reason']}"
    )

    with _mines_lock:
        sessions = _load_mines_sessions()
        sessions[str(uid)] = {
            'game_id': game_id, 'uid': str(uid),
            'mine_positions': mine_positions, 'bet_amount': bet_amount,
            'mine_count': mine_count, 'revealed': [], 'multiplier': 1.0,
            'game_over': False, 'paid_out': False,
            'created_at': datetime.now().isoformat()
        }
        _save_mines_sessions(sessions)
        # ── Durable session: persists the bet in SQLite so a server restart
        # triggers auto-refund via refund_expired_game_sessions() at next boot.
        _set_ags(str(uid), 'mines',
                 {'game_id': game_id, 'mine_count': mine_count},
                 bet_amount)

    return jsonify(result)

@app.route('/api/mines/reveal', methods=['POST'])
@webapp_auth
def api_mines_reveal():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json or {}
    uid = get_request_uid()
    cell = data.get('cell')
    if cell is None:
        return jsonify({'error': 'Missing cell'}), 400
    cell = int(cell)
    if cell < 0 or cell > 24:
        return jsonify({'error': 'Invalid cell'}), 400

    with _mines_lock:
        sessions = _load_mines_sessions()
        state = sessions.get(str(uid))
        if not state:
            return jsonify({'error': 'No active game'}), 400

        # Idempotency: if this cell was already revealed, return the cached result
        reveal_results = state.get('reveal_results', {})
        if str(cell) in reveal_results:
            return jsonify(reveal_results[str(cell)])

        if state.get('game_over'):
            return jsonify({'error': 'No active game'}), 400

        mine_positions = state['mine_positions']
        is_mine = cell in mine_positions
        state['revealed'].append(cell)
        if 'reveal_results' not in state:
            state['reveal_results'] = {}

        if is_mine:
            state['game_over'] = True
            state['multiplier'] = 0
            resp = {'success': True, 'is_mine': True, 'multiplier': 0,
                    'game_over': True, 'mine_cells': mine_positions}
            state['reveal_results'][str(cell)] = resp
            sessions[str(uid)] = state
            _save_mines_sessions(sessions)
            # Game over on mine hit — clear durable session (no refund due; bet was lost)
            _del_ags(str(uid), 'mines')
            return jsonify(resp)

        revealed_count = len(state['revealed'])
        safe_count = 25 - state['mine_count']
        mult = 1.0
        for i in range(revealed_count):
            mult *= (25 - i) / (25 - state['mine_count'] - i)
        game = _gm.get_game('GAME006')
        house_edge = float(game.get('house_edge_pct', 15)) / 100 if game else 0.15
        mult *= (1 - house_edge * 0.5)
        state['multiplier'] = round(mult, 4)

        all_safe = revealed_count >= safe_count
        payout = 0.0
        new_balance = None
        bet_amount = state.get('bet_amount', 0)
        game_id_mines = state.get('game_id', '')

        if all_safe and not state.get('paid_out'):
            payout = round(bet_amount * state['multiplier'], 2)
            state['game_over'] = True
            state['paid_out'] = True

        # Build partial resp now (no balance_after yet for all_safe case)
        resp = {'success': True, 'is_mine': False, 'multiplier': state['multiplier'],
                'game_over': all_safe, 'all_safe': all_safe,
                'mine_cells': mine_positions if all_safe else []}
        if all_safe:
            resp['payout'] = payout

        # Cache reveal result and persist BEFORE crediting (journal-then-execute ordering)
        state['reveal_results'][str(cell)] = resp
        sessions[str(uid)] = state
        _save_mines_sessions(sessions)

    # Credit payout AFTER session state is durably written.
    # credit_with_idempotency is atomic: credit + idempotency record in one SQLite transaction.
    # Derived key ensures re-entry (retry after crash) does not double-pay.
    if all_safe and not state.get('_already_credited'):
        derived_key = f"reveal_allsafe_{game_id_mines}"
        template = {'payout': payout, 'mine_cells': mine_positions, 'all_safe': True}
        _ok, stored, race_cached = _gm.credit_with_idempotency(uid, payout, derived_key, template)
        credit_result = stored or race_cached or {}
        new_balance = credit_result.get('balance_after')
        resp = state.get('reveal_results', {}).get(str(cell), resp)
        if new_balance is not None:
            resp = dict(resp)
            resp['balance_after'] = new_balance
            # Update cached result with balance_after
            with _mines_lock:
                sessions2 = _load_mines_sessions()
                if str(uid) in sessions2:
                    sessions2[str(uid)].get('reveal_results', {})[str(cell)] = resp
                    _save_mines_sessions(sessions2)
        _gm.tracker.log_session({
            'session_id': game_id_mines, 'game_id': 'GAME006',
            'user_id': uid, 'bet_amount': bet_amount, 'payout': payout,
            'result': 'win', 'balance_before': 0, 'balance_after': new_balance,
            'multiplier': state['multiplier']
        })
        _gm.tracker.update_profile(uid, {
            'bet_amount': bet_amount, 'payout': payout, 'result': 'win',
            'game_id': 'GAME006', 'balance_after': new_balance
        })
        # All cells revealed safely → paid out; clear durable session
        _del_ags(str(uid), 'mines')

    return jsonify(resp)

@app.route('/api/mines/cashout', methods=['POST'])
@webapp_auth
def api_mines_cashout():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json or {}
    uid = get_request_uid()
    request_id = _get_request_id()

    # Fast SQLite idempotency check (survives restarts)
    if request_id:
        cached = _gm.get_idempotency_record(uid, request_id)
        if cached:
            return jsonify(cached)

    with _mines_lock:
        sessions = _load_mines_sessions()
        state = sessions.get(str(uid))

        # Session-level idempotency: cashout_result persisted in session JSON
        if state and state.get('paid_out') and state.get('cashout_result'):
            return jsonify(state['cashout_result'])

        if not state or state.get('game_over') or state.get('paid_out'):
            return jsonify({'error': 'No active game'}), 400

        multiplier = state.get('multiplier', 1.0)
        bet_amount = state.get('bet_amount', 0)
        mine_positions = state.get('mine_positions', [])
        game_id = state.get('game_id', '')
        payout = round(bet_amount * multiplier, 2)

    # CREDIT FIRST with a deterministic idempotency key — a crash after the
    # credit can never lose the payout, and a retry (same key) can never
    # double-credit. Only after the credit commits do we mark the session paid.
    settle_key = request_id or f"mines_cashout_{game_id}"
    response_template = {'success': True, 'payout': payout,
                         'multiplier': multiplier, 'mine_cells': mine_positions}
    ok, stored, race_cached = _gm.credit_with_idempotency(uid, payout, settle_key, response_template)
    if race_cached:
        return jsonify(race_cached)
    if not ok:
        return jsonify({'success': False, 'error': 'Settlement failed'}), 500

    result = stored  # has balance_after
    new_balance = result.get('balance_after', 0)

    # Now mark consumed + persist result + clear durable refund row
    with _mines_lock:
        sessions = _load_mines_sessions()
        if str(uid) in sessions:
            sessions[str(uid)]['game_over'] = True
            sessions[str(uid)]['paid_out'] = True
            sessions[str(uid)]['cashout_result'] = result
            _save_mines_sessions(sessions)
        _del_ags(str(uid), 'mines')

    _gm.tracker.log_session({
        'session_id': game_id, 'game_id': 'GAME006',
        'user_id': uid, 'bet_amount': bet_amount, 'payout': payout,
        'result': 'win', 'balance_before': 0, 'balance_after': new_balance,
        'multiplier': multiplier
    })
    _gm.tracker.update_profile(uid, {
        'bet_amount': bet_amount, 'payout': payout, 'result': 'win',
        'game_id': 'GAME006', 'balance_after': new_balance
    })

    return jsonify(result)

# ===== Plinko — Frontend API (/api/plinko/drop) =====

# Multiplier tables: [rows][risk] → list of slot multipliers (left to right)

# Multiplier tables MUST exactly match MULT_TABLES in plinko.html
# slot count = rows + 1  (8→9, 12→13, 16→17)
_PLINKO_MULTS = {
    8: {
        'low':  [5.6, 2.1, 1.1, 1.0, 0.5, 1.0, 1.1, 2.1, 5.6],
        'med':  [13, 3, 1.3, 0.7, 0.4, 0.7, 1.3, 3, 13],
        'high': [29, 4, 1.5, 0.3, 0.2, 0.3, 1.5, 4, 29],
    },
    12: {
        'low':  [10, 3, 1.6, 1.4, 1.1, 1.0, 0.5, 1.0, 1.1, 1.4, 1.6, 3, 10],
        'med':  [33, 11, 4, 2, 1.1, 0.6, 0.3, 0.6, 1.1, 2, 4, 11, 33],
        'high': [141, 21, 5.6, 2.5, 1.2, 0.5, 0.2, 0.5, 1.2, 2.5, 5.6, 21, 141],
    },
    16: {
        'low':  [16, 9, 2, 1.4, 1.4, 1.2, 1.1, 1.0, 0.5, 1.0, 1.1, 1.2, 1.4, 1.4, 2, 9, 16],
        'med':  [110, 41, 10, 5, 3, 1.5, 1.0, 0.5, 0.3, 0.5, 1.0, 1.5, 3, 5, 10, 41, 110],
        'high': [1000, 130, 26, 9, 4, 2, 0.7, 0.2, 0.1, 0.2, 0.7, 2, 4, 9, 26, 130, 1000],
    },
    20: {
        'low':  [50, 12, 4, 2.5, 1.8, 1.3, 1.0, 0.7, 0.5, 0.3, 0.2, 0.3, 0.5, 0.7, 1.0, 1.3, 1.8, 2.5, 4, 12, 50],
        'med':  [500, 60, 15, 5, 3, 1.5, 1.0, 0.5, 0.3, 0.1, 0.05, 0.1, 0.3, 0.5, 1.0, 1.5, 3, 5, 15, 60, 500],
        'high': [5000, 500, 80, 20, 8, 3, 1.5, 0.7, 0.3, 0.1, 0.05, 0.1, 0.3, 0.7, 1.5, 3, 8, 20, 80, 500, 5000],
    },
}

@app.route('/api/plinko/drop', methods=['POST'])
@webapp_auth
def api_plinko_drop():
    # NOTE: Plinko does NOT use active_game_sessions.
    # The entire bet+payout is settled in one ACID SQLite transaction via
    # settle_with_idempotency() below, so there is no window where a restart
    # could strand a deducted bet without a matching payout.  Adding a
    # pre-settlement session row would cause a double-credit bug on restart
    # (the refund would run even though no money was ever deducted).
    # The idempotency record written by settle_with_idempotency() is sufficient
    # to replay the correct result on retry without re-executing settlement.
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json or {}
    uid = get_request_uid()
    request_id = _get_request_id()
    if not uid:
        return jsonify({'error': 'Missing params'}), 400

    # ── Rate Limiting: max 20 drops per 60s per user ──
    _rl_now = int(datetime.now().timestamp())
    if not hasattr(app, '_plinko_rl'):
        app._plinko_rl = {}
    rl_data = app._plinko_rl.get(uid, [])
    rl_data = [t for t in rl_data if _rl_now - t < 60]
    if len(rl_data) >= 20:
        return jsonify({'error': 'بطء! حاول بعد ثوانٍ'}), 429
    rl_data.append(_rl_now)
    app._plinko_rl[uid] = rl_data

    # Fast SQLite idempotency check (survives restarts)
    if request_id:
        cached = _gm.get_idempotency_record(uid, request_id)
        if cached:
            return jsonify(cached)

    bet_amount = float(data.get('bet', 0))
    rows = int(data.get('rows', 12))
    risk = str(data.get('risk', 'low')).lower()
    if rows not in _PLINKO_MULTS:
        rows = 12
    if risk not in ('low', 'med', 'high'):
        risk = 'low'
    if bet_amount <= 0:
        return jsonify({'error': 'مبلغ غير صالح'}), 400

    # ── Financial Security: bet limits + payout cap ──
    MIN_BET = 1.0
    MAX_BET = 5000.0
    MAX_PAYOUT = 100000.0  # hard cap — prevents bankroll drain
    if bet_amount < MIN_BET:
        return jsonify({'error': 'الحد الأدنى للرهان 1'}), 400
    if bet_amount > MAX_BET:
        return jsonify({'error': 'الحد الأقصى للرهان 5000'}), 400

    player = _gm.tracker.get_profile(uid)
    game = _gm.get_game('GAME007') or {
        'id': 'GAME007', 'base_win_chance': '0.40', 'house_edge_pct': '16',
        'min_bet': '10', 'max_bet': '2000'
    }

    risk_check = _gm.risk.check_risk(player, bet_amount, game)
    if not risk_check['allowed']:
        msg = risk_check['alerts'][0]['message'] if risk_check.get('alerts') else 'محظور'
        return jsonify({'success': False, 'error': msg})

    balance = _gm.get_balance(uid)
    if balance < bet_amount:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance})

    mults = _PLINKO_MULTS[rows][risk]
    num_slots = len(mults)  # rows + 1

    algo_result = _gm.algorithm.calculate_win_chance(player, game, bet_amount)
    win_chance = algo_result['win_chance']

    # ── Server-Authoritative Plinko Algorithm ──
    # 1. Provably Fair: generate server_seed, commit hash before result
    # 2. Generate left/right directions ONCE (used for BOTH slot calc and client path)
    # 3. Directions biased by win_chance: higher win_chance → edge bias (higher mults)
    # 4. 3% house edge: force_center pulls ball toward center (lowest payout)
    # 5. All probabilities clamped [0.25, 0.75] to prevent impossible paths

    # Provably Fair seed
    _pf_seed = secrets.token_hex(16)
    _pf_seed_hash = hashlib.sha256(_pf_seed.encode()).hexdigest()

    center = (num_slots - 1) / 2.0
    edge_bias = (win_chance - 0.5) * 0.20  # -0.10 to +0.10

    # House edge: 3% chance to force center
    force_center = random.random() < 0.03

    # Provably Fair: use HMAC-SHA256 to derive deterministic RNG from seed
    _pf_rng = random.Random()
    _pf_rng.seed(int(_pf_seed[:16], 16))

    directions = []
    position = 0.0
    for r in range(rows):
        if force_center:
            p_right = 0.5 - (position / max(1, rows)) * 1.5
        else:
            p_right = 0.5 + edge_bias
        p_right = max(0.25, min(0.75, p_right))
        go_right = _pf_rng.random() < p_right
        direction = 1 if go_right else -1
        directions.append(direction)
        position += direction

    # Convert position to slot index
    # position ranges from -rows to +rows; center = (num_slots-1)/2
    # slot = center + position/2 → maps -rows..+rows to 0..num_slots-1
    slot = int(round(center + position / 2.0))
    slot = max(0, min(num_slots - 1, slot))  # clamp

    multiplier = mults[slot]
    payout = round(bet_amount * multiplier, 2)

    # Max payout cap — protects platform bankroll
    if payout > MAX_PAYOUT:
        payout = MAX_PAYOUT
        multiplier = round(payout / bet_amount, 2)

    result_str = 'win' if multiplier >= 1.0 else 'lose'

    # Build path from SAME directions (NOT re-randomized!)
    ball_path = []
    cx = 0.5
    ball_path.append({'dir': 0, 'x': cx, 'y': 0.0})
    temp_pos = 0.0
    for r in range(rows):
        temp_pos += directions[r]
        cx = 0.5 + (temp_pos / (rows * 2))
        cy = (r + 1) / rows
        ball_path.append({'dir': directions[r], 'x': max(0.05, min(0.95, cx)), 'y': cy})

    # Atomic: settle + idempotency record in one SQLite transaction
    template = {'success': True, 'slot': slot, 'multiplier': multiplier,
                'payout': payout, 'result': result_str, 'balance_before': balance,
                'directions': directions,
                'seed': _pf_seed,
                'seed_hash': _pf_seed_hash,
                'path': ball_path}
    ok, stored, race_cached = _gm.settle_with_idempotency(uid, bet_amount, payout, request_id, template)
    if race_cached:
        return jsonify(race_cached)
    if not ok:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance})

    result = stored
    new_balance = result.get('balance_after', balance)

    session_id = f"PLW{str(int(datetime.now().timestamp()))[-8:]}"
    _gm.algorithm.log_decision(
        session_id=session_id, user_id=uid, game_id='GAME007',
        base_chance=float(game.get('base_win_chance', 0.40)),
        adjusted_chance=win_chance, factors=algo_result['factors'],
        decision=algo_result['decision'],
        reason=f"Plinko rows={rows} risk={risk} slot={slot} mult={multiplier} force_center={force_center} bet={bet_amount} payout={payout}; {algo_result['reason']}"
    )
    _gm.tracker.log_session({
        'session_id': session_id, 'game_id': 'GAME007', 'user_id': uid,
        'bet_amount': bet_amount, 'payout': payout, 'result': result_str,
        'balance_before': balance, 'balance_after': new_balance,
        'multiplier': multiplier
    })
    _gm.tracker.update_profile(uid, {
        'bet_amount': bet_amount, 'payout': payout, 'result': result_str,
        'game_id': 'GAME007', 'balance_after': new_balance
    })
    return jsonify(result)

# ===== Wheel — Frontend API (/api/wheel/spin) =====

# Wheel segments — base set, shuffled per round for variety
_WHEEL_BASE_SEGMENTS = [
    {'mult': 0.0,  'label': '💀',  'color': '#991b1b', 'glow': '#ef4444'},
    {'mult': 1.5,  'label': '1.5x','color': '#1e3a5f', 'glow': '#3b82f6'},
    {'mult': 2.0,  'label': '2x',  'color': '#14532d', 'glow': '#22c55e'},
    {'mult': 0.5,  'label': '0.5x','color': '#581c87', 'glow': '#a855f7'},
    {'mult': 5.0,  'label': '5x',  'color': '#78350f', 'glow': '#fbbf24'},
    {'mult': 1.0,  'label': '1x',  'color': '#155e75', 'glow': '#06b6d4'},
    {'mult': 10.0, 'label': '10x', 'color': '#831843', 'glow': '#ec4899'},
    {'mult': 0.0,  'label': '💀',  'color': '#991b1b', 'glow': '#ef4444'},
]

def _shuffle_segments():
    """Shuffle segments for each round — prevents monotony."""
    segs = list(_WHEEL_BASE_SEGMENTS)
    # Keep the two 💀 segments apart (not adjacent)
    for _ in range(10):
        random.shuffle(segs)
        skull_positions = [i for i, s in enumerate(segs) if s['mult'] == 0.0]
        if len(skull_positions) == 2 and abs(skull_positions[0] - skull_positions[1]) > 1:
            break
    return segs

@app.route('/api/wheel/spin', methods=['POST'])
@webapp_auth
def api_wheel_spin():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json or {}
    uid = get_request_uid()
    request_id = _get_request_id()
    if not uid:
        return jsonify({'error': 'Missing params'}), 400

    # Fast SQLite idempotency check (survives restarts)
    if request_id:
        cached = _gm.get_idempotency_record(uid, request_id)
        if cached:
            return jsonify(cached)

    bet_amount = float(data.get('bet', 0))
    if bet_amount <= 0:
        return jsonify({'error': 'Missing params'}), 400

    player = _gm.tracker.get_profile(uid)
    game = _gm.get_game('GAME009') or {
        'id': 'GAME009', 'base_win_chance': '0.50', 'house_edge_pct': '10',
        'min_bet': '10', 'max_bet': '5000'
    }

    risk_check = _gm.risk.check_risk(player, bet_amount, game)
    if not risk_check['allowed']:
        msg = risk_check['alerts'][0]['message'] if risk_check.get('alerts') else 'محظور'
        return jsonify({'success': False, 'error': msg})

    balance = _gm.get_balance(uid)
    if balance < bet_amount:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance})

    # Shuffle segments for this round
    wheel_segments = _shuffle_segments()
    N = len(wheel_segments)

    algo_result = _gm.algorithm.calculate_win_chance(player, game, bet_amount)
    win_chance = algo_result['win_chance']

    # Smart weighted selection — considers player segment + house edge
    weights = []
    for seg in wheel_segments:
        m = seg['mult']
        if m == 0.0:
            # 💀 segments — higher weight for losers, lower for winners
            weights.append(max(1, int((1 - win_chance) * 10)))
        elif m >= 10.0:
            # 10x — very rare, only for new players or after big losses
            weights.append(max(1, int(win_chance * 2)))
        elif m >= 5.0:
            # 5x — rare but possible
            weights.append(max(1, int(win_chance * 4)))
        elif m >= 2.0:
            # 2x — moderate
            weights.append(max(1, int(win_chance * 7)))
        elif m >= 1.0:
            # 1x/1.5x — common wins
            weights.append(max(1, int(win_chance * 9)))
        else:
            # 0.5x — partial loss
            weights.append(max(1, int((1 - win_chance) * 5)))

    total_w = sum(weights)
    rand_val = random.uniform(0, total_w)
    segment = 0
    cumulative = 0
    for i, w in enumerate(weights):
        cumulative += w
        if rand_val <= cumulative:
            segment = i
            break

    multiplier = wheel_segments[segment]['mult']
    payout = round(bet_amount * multiplier, 2)
    result_str = 'win' if multiplier > 0 else 'lose'

    # Build segments for client (shuffled order for this round)
    client_segments = [{'mult': s['mult'], 'label': s['label'], 'color': s['color'], 'glow': s['glow']} for s in wheel_segments]

    # Atomic: settle + idempotency record in one SQLite transaction
    template = {'success': True, 'segment': segment, 'multiplier': multiplier,
                'payout': payout, 'result': result_str, 'balance_before': balance,
                'segments': client_segments}
    ok, stored, race_cached = _gm.settle_with_idempotency(uid, bet_amount, payout, request_id, template)
    if race_cached:
        return jsonify(race_cached)
    if not ok:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance})

    result = stored
    new_balance = result.get('balance_after', balance)

    session_id = f"WHL{str(int(datetime.now().timestamp()))[-8:]}"
    _gm.algorithm.log_decision(
        session_id=session_id, user_id=uid, game_id='GAME009',
        base_chance=float(game.get('base_win_chance', 0.50)),
        adjusted_chance=win_chance, factors=algo_result['factors'],
        decision=algo_result['decision'],
        reason=f"Wheel segment={segment} mult={multiplier}; {algo_result['reason']}"
    )
    _gm.tracker.log_session({
        'session_id': session_id, 'game_id': 'GAME009', 'user_id': uid,
        'bet_amount': bet_amount, 'payout': payout, 'result': result_str,
        'balance_before': balance, 'balance_after': new_balance,
        'multiplier': multiplier
    })
    _gm.tracker.update_profile(uid, {
        'bet_amount': bet_amount, 'payout': payout, 'result': result_str,
        'game_id': 'GAME009', 'balance_after': new_balance
    })
    return jsonify(result)

# ===== Lottery — Frontend API (/api/lottery/state + /api/lottery/buy) =====

_LOTTERY_TICKET_PRICE = 50      # per ticket
_LOTTERY_ROUND_DURATION = 3600  # seconds (1 hour rounds)
_LOTTERY_NUMBERS_COUNT = 5      # numbers per ticket
_LOTTERY_MAX_NUMBER = 30

# ── Three draw types: hourly, daily, weekly ──
# Each has its own prize pool, ticket price, and duration
_LOTTERY_DRAW_TYPES = {
    'hourly': {
        'name': 'سحب كل ساعة',
        'duration': 3600,           # 1 hour
        'ticket_price': 50,
        'multiplier': 1.0,          # base multiplier
        'icon': '⏰',
    },
    'daily': {
        'name': 'سحب يومي',
        'duration': 86400,          # 24 hours
        'ticket_price': 100,
        'multiplier': 2.5,          # 2.5x bigger prizes
        'icon': '📅',
    },
    'weekly': {
        'name': 'سحب أسبوعي',
        'duration': 604800,         # 7 days
        'ticket_price': 250,
        'multiplier': 10.0,         # 10x bigger prizes
        'icon': '🏆',
    },
}

# Tiered prize tiers (number of matches required for each tier)
_LOTTERY_TIER_JACKPOT    = 5   # 5/5 — full prize pool split among winners
_LOTTERY_TIER_SECONDARY  = 4   # 4/5 — secondary prize
_LOTTERY_TIER_SMALL      = 3   # 3/5 — small consolation prize

# When no jackpot winner: what fraction of the pool to roll over vs redistribute
_LOTTERY_ROLLOVER_PCT    = 0.50  # 50% rolls over to next round
# Of the redistributable half: how to split between tier-2 and tier-3 winners
_LOTTERY_SECONDARY_SHARE = 0.70  # 70% of redistributable → 4/5 winners
_LOTTERY_SMALL_SHARE     = 0.30  # 30% of redistributable → 3/5 winners

_lottery_lock = threading.Lock()

def _lottery_state_file():
    return os.path.join(BASE_DIR, 'lottery_state.json')

def _load_lottery_state():
    try:
        f = _lottery_state_file()
        if os.path.exists(f):
            with open(f, 'r') as fh:
                return json.load(fh)
    except Exception:
        pass
    return {}

def _load_lottery_state_file(filename):
    try:
        f = os.path.join(BASE_DIR, filename)
        if os.path.exists(f):
            with open(f, 'r') as fh:
                return json.load(fh)
    except Exception:
        pass
    return {}

def _save_lottery_state_file(state, filename, raise_on_error=False):
    try:
        f = os.path.join(BASE_DIR, filename)
        with open(f, 'w') as fh:
            json.dump(state, fh)
    except Exception:
        if raise_on_error:
            raise

def _save_lottery_state(state, raise_on_error=False):
    """Persist lottery state to disk.

    When raise_on_error=True (used during draw resolution), exceptions propagate
    so callers know the state was NOT durably saved before they credit winners.
    """
    try:
        with open(_lottery_state_file(), 'w') as fh:
            json.dump(state, fh)
    except Exception as e:
        if raise_on_error:
            raise
        print(f"[lottery] _save_lottery_state warning (non-critical): {e}")

def _lottery_resume_pending_credits(state):
    """Resume any winner credits that were persisted but not yet completed.

    Called on every entry to _get_or_create_lottery_round before starting a new round.
    winners_to_credit is the durable record of pending payments — credit_with_idempotency
    ensures each winner is paid exactly once even across restarts or partial failures.
    After all credits succeed, clears winners_to_credit and persists state.
    """
    pending = state.get('winners_to_credit', [])
    if not pending:
        return
    round_id = state.get('round_id', '')
    remaining = list(pending)
    for entry in pending:
        w_uid = entry['uid']
        amount = entry['amount']
        idem_key = entry['idem_key']
        try:
            _gm.credit_with_idempotency(
                str(w_uid), amount, idem_key,
                {'source': 'lottery', 'round_id': round_id, 'prize': amount}
            )
            remaining.remove(entry)
        except Exception as e:
            print(f"[lottery] credit failed for {w_uid}: {e}")
    state['winners_to_credit'] = remaining
    # Persist after crediting; best-effort (don't fail the whole round if save fails here)
    _save_lottery_state(state)


def _get_or_create_lottery_round_for_type(draw_type='hourly'):
    """Get or create a lottery round for a specific draw type."""
    state_file = f'lottery_state_{draw_type}.json'
    dt_config = _LOTTERY_DRAW_TYPES.get(draw_type, _LOTTERY_DRAW_TYPES['hourly'])
    with _lottery_lock:
        state = _load_lottery_state_file(state_file)
        now_ts = datetime.now().timestamp()
        # Start new round if needed
        if not state or (state.get('drawn') and not state.get('winners_to_credit')):
            round_id = f"LTR_{draw_type}_{int(now_ts)}"
            carried_pool = float(state.get('rollover_amount', 0)) if state else 0.0
            new_state = {
                'round_id': round_id,
                'draw_type': draw_type,
                'draw_time': now_ts + dt_config['duration'],
                'ticket_price': dt_config['ticket_price'],
                'tickets': [],
                'tickets_sold': 0,
                'prize_pool': carried_pool,
                'drawn': None,
                'history': state.get('history', []) if state else [],
                'previous_round': state.get('previous_round') if state else None,
            }
            _save_lottery_state_file(new_state, state_file)
            return new_state
        return state

def _get_or_create_lottery_round():
    """Return the current active lottery round, creating one if needed or drawing if expired.

    Crash-safe draw protocol:
      1. Compute draw result and mark tickets.
      2. Build winners_to_credit — the durable list of pending payments.
      3. Persist drawn state + winners_to_credit (raise on failure — no credits without durable state).
      4. Credit each winner via credit_with_idempotency (idempotent across retries/restarts).
      5. Clear winners_to_credit, persist final state.
    On every subsequent call, _lottery_resume_pending_credits retries any credits that were
    not yet completed (e.g. process crashed between steps 4 and 5).
    """
    with _lottery_lock:
        state = _load_lottery_state()
        now_ts = datetime.now().timestamp()

        # Resume any pending winner credits before doing anything else (crash recovery path)
        if state and state.get('drawn') and state.get('winners_to_credit'):
            _lottery_resume_pending_credits(state)
            state = _load_lottery_state()  # reload after credits + save

        # Draw if round has expired
        if state and float(state.get('draw_time', 0)) <= now_ts and not state.get('drawn'):
            drawn_nums = sorted(random.sample(range(1, _LOTTERY_MAX_NUMBER + 1), _LOTTERY_NUMBERS_COUNT))
            round_id = state.get('round_id', '')
            state['drawn'] = drawn_nums
            state['drawn_at'] = now_ts

            # ── Tiered ticket resolution ───────────────────────────────────────
            # Tier 1 (jackpot): 5/5 match  — full prize pool split among winners
            # Tier 2 (secondary): 4/5 match — share of the redistributable pool
            # Tier 3 (small): 3/5 match    — smaller share of the redistributable pool
            # No jackpot → 50% rolls over, remaining 50% split across tier-2/3 winners.
            # No winners at all → full pool rolls over.
            tier1_uids = []  # jackpot  (5/5)
            tier2_uids = []  # secondary (4/5)
            tier3_uids = []  # small     (3/5)

            for ticket in state.get('tickets', []):
                matches = len(set(ticket['numbers']) & set(drawn_nums))
                ticket['matches'] = matches
                ticket['drawn'] = drawn_nums
                ticket['scratched'] = True
                if matches >= _LOTTERY_TIER_JACKPOT:
                    ticket['status'] = 'win'
                    ticket['tier'] = 1
                    tier1_uids.append(ticket['uid'])
                elif matches == _LOTTERY_TIER_SECONDARY:
                    ticket['status'] = 'win'
                    ticket['tier'] = 2
                    tier2_uids.append(ticket['uid'])
                elif matches == _LOTTERY_TIER_SMALL:
                    ticket['status'] = 'win'
                    ticket['tier'] = 3
                    tier3_uids.append(ticket['uid'])
                else:
                    ticket['status'] = 'lose'
                    ticket['tier'] = 0

            prize_pool = state.get('prize_pool', 0)
            rollover_amount = 0.0
            winners_to_credit = []

            # ── Rounding-safe pool splitter (integer-cents arithmetic) ────────────
            #
            # Problem: round(pool/n, 2)*n can EXCEED pool because round() rounds up.
            # Example: pool=0.10, n=3 → base=0.03, total=0.09 (ok here) but
            #          pool=0.02, n=4 → base=0.01, total=0.04 > 0.02 (over-pay!).
            #
            # Solution: convert to integer cents, use floor division, give the last
            # winner the exact remainder. This guarantees:
            #   • sum of all payouts == pool (to the cent)
            #   • no individual payout is negative
            #   • last winner gets at least as much as the others (never less)
            #
            # Duplicate-UID handling: a user with N winning tickets in the same tier
            # appears N times in tier*_uids.  _split_pool distributes per-ticket, then
            # _aggregate_credits() sums amounts by uid so each user receives exactly
            # one credit — with a per-(round,uid,tier) idempotency key.
            def _split_pool_cents(pool_f, uids, tier_label):
                """Return list of (uid, amount_float) pairs using integer-cents math.

                pool_f  — pool as a float (platform currency units)
                uids    — list of UIDs, may contain duplicates (one entry per ticket)

                Guarantees:
                  • sum(amounts) == pool_f (to the cent, barring pool_f > 2^53 cents)
                  • every amount is > 0 (skips and warns otherwise)
                  • last uid receives base + remainder cents (never over-paid first winners)
                """
                n = len(uids)
                if n == 0:
                    return []
                pool_cents = round(pool_f * 100)   # safe: round() handles float drift
                if pool_cents <= 0:
                    if pool_cents < 0:
                        print(f"[lottery] WARNING: {tier_label} pool_cents={pool_cents} < 0 "
                              f"(pool_f={pool_f:.4f}) — skipping credits")
                    return []
                base_cents = pool_cents // n          # floor division — never over-pays
                last_cents = pool_cents - base_cents * (n - 1)  # remainder ≥ base_cents ≥ 0
                result = []
                for i, uid in enumerate(uids):
                    cents = last_cents if i == n - 1 else base_cents
                    if cents <= 0:
                        # Only reachable when pool_cents < n (pool too small to distribute)
                        print(f"[lottery] WARNING: {tier_label} winner {uid} "
                              f"payout={cents} cents ≤ 0 (pool_cents={pool_cents}, n={n}) "
                              "— skipping credit (pool too small to distribute evenly)")
                        continue
                    result.append((uid, round(cents / 100, 2)))
                return result

            def _aggregate_credits(uid_prize_list, tier_suffix):
                """Sum per-ticket amounts by uid → one winners_to_credit entry per uid.

                Merging here keeps idempotency keys per-(round,uid,tier) and ensures
                a user with 2 winning tickets receives one combined credit, not two
                separate ones that might have the same idempotency key.
                """
                totals = {}   # uid → accumulated cents (int to avoid float drift)
                for uid, amt in uid_prize_list:
                    uid_str = str(uid)
                    totals[uid_str] = totals.get(uid_str, 0) + round(amt * 100)
                credits = []
                for uid_str, total_cents in totals.items():
                    total_f = round(total_cents / 100, 2)
                    if total_f <= 0:
                        print(f"[lottery] WARNING: aggregate credit for {uid_str} "
                              f"({tier_suffix}) total={total_f:.4f} ≤ 0 — skipping")
                        continue
                    credits.append({
                        'uid': uid_str,
                        'amount': total_f,
                        'idem_key': f"lottery_{round_id}_{uid_str}_{tier_suffix}",
                    })
                return credits

            # Clamp prize_pool to a non-negative float before any arithmetic
            prize_pool_f = max(0.0, round(float(prize_pool), 2))

            if tier1_uids:
                # Jackpot: split full pool among all jackpot tickets (one share per ticket).
                uid_prize_j = _split_pool_cents(prize_pool_f, tier1_uids, 'tier1-jackpot')
                # Per-ticket prize for display (each ticket shows its own share)
                prize_map_j = {u: p for u, p in uid_prize_j}
                for ticket in state.get('tickets', []):
                    ticket['prize'] = prize_map_j.get(ticket['uid'], 0.0) if ticket.get('tier') == 1 else 0.0
                # One combined credit per unique uid
                winners_to_credit = _aggregate_credits(uid_prize_j, 't1')

            else:
                # No jackpot — roll over a portion, redistribute the rest.
                if tier2_uids or tier3_uids:
                    # Clamp rollover to [0, prize_pool_f] — prevents negative redistributable
                    rollover_amount = max(
                        0.0,
                        min(round(prize_pool_f * _LOTTERY_ROLLOVER_PCT, 2), prize_pool_f)
                    )
                else:
                    # No winners at all — roll over the full pool
                    rollover_amount = prize_pool_f

                # redistributable is the exact complement — cannot be negative after clamp
                redistributable = round(max(0.0, prize_pool_f - rollover_amount), 2)

                # Split redistributable between tier-2 and tier-3 pools.
                # tier3_pool is computed as the exact remainder so tier2+tier3 == redistributable.
                if tier2_uids and tier3_uids:
                    tier2_pool = round(redistributable * _LOTTERY_SECONDARY_SHARE, 2)
                    tier3_pool = round(max(0.0, redistributable - tier2_pool), 2)
                elif tier2_uids:
                    tier2_pool = redistributable
                    tier3_pool = 0.0
                else:
                    tier2_pool = 0.0
                    tier3_pool = redistributable

                uid_prize_t2 = _split_pool_cents(tier2_pool, tier2_uids, 'tier2-secondary')
                uid_prize_t3 = _split_pool_cents(tier3_pool, tier3_uids, 'tier3-small')

                # Per-ticket prize for display
                prize_map_t2 = {u: p for u, p in uid_prize_t2}
                prize_map_t3 = {u: p for u, p in uid_prize_t3}
                for ticket in state.get('tickets', []):
                    if ticket.get('tier') == 2:
                        ticket['prize'] = prize_map_t2.get(ticket['uid'], 0.0)
                    elif ticket.get('tier') == 3:
                        ticket['prize'] = prize_map_t3.get(ticket['uid'], 0.0)
                    else:
                        ticket['prize'] = 0.0

                # One combined credit per unique uid per tier
                winners_to_credit = (
                    _aggregate_credits(uid_prize_t2, 't2') +
                    _aggregate_credits(uid_prize_t3, 't3')
                )

            # Preserve rollover so the next round starts with it
            state['rollover_amount'] = rollover_amount

            # Preserve previous round data for UI
            state['previous_round'] = {
                'round_id': round_id,
                'draw_time': state.get('draw_time'),
                'drawn': drawn_nums,
                'drawn_at': now_ts,
                'tickets': list(state.get('tickets', [])),
                'jackpot_winners': len(tier1_uids),
                'secondary_winners': len(tier2_uids),
                'small_winners': len(tier3_uids),
                'rollover_amount': rollover_amount,
            }

            history_entry = {
                'round_id': round_id,
                'drawn': drawn_nums,
                'drawn_at': now_ts,
                'tickets_sold': state.get('tickets_sold', 0),
                'prize_pool': prize_pool,
                'jackpot_winners': len(tier1_uids),
                'secondary_winners': len(tier2_uids),
                'small_winners': len(tier3_uids),
                'rollover_amount': rollover_amount,
                # Legacy field — total paid out winners across all tiers
                'winners': len(tier1_uids) + len(tier2_uids) + len(tier3_uids),
            }
            state.setdefault('history', []).append(history_entry)
            if len(state['history']) > 10:
                state['history'] = state['history'][-10:]

            # Build the durable pending-credit list BEFORE persisting drawn state.
            # Each entry has a stable idem_key derived from round_id + uid + tier.
            state['winners_to_credit'] = winners_to_credit

            # STEP 3: Persist drawn state + winners_to_credit atomically.
            # raise_on_error=True: if the write fails, no credits happen (correct).
            # If the process crashes after this write but before credits complete,
            # _lottery_resume_pending_credits (called above) will resume on next invocation.
            _save_lottery_state(state, raise_on_error=True)

            # STEP 4: Credit each winner (idempotent via SQLite idem_key).
            _lottery_resume_pending_credits(state)
            state = _load_lottery_state()  # reload to get cleared winners_to_credit

        # Start new round if needed
        if not state or (state.get('drawn') and not state.get('winners_to_credit')):
            round_id = f"LTR{int(now_ts)}"
            # Carry over any rolled-over prize pool from the previous round
            carried_pool = float(state.get('rollover_amount', 0)) if state else 0.0
            new_state = {
                'round_id': round_id,
                'draw_time': now_ts + _LOTTERY_ROUND_DURATION,
                'ticket_price': _LOTTERY_TICKET_PRICE,
                'tickets': [],
                'tickets_sold': 0,
                'prize_pool': carried_pool,
                'drawn': None,
                'history': state.get('history', []) if state else [],
                # Carry forward previous round so users can see their results
                'previous_round': state.get('previous_round') if state else None,
            }
            _save_lottery_state(new_state)
            return new_state

        return state

@app.route('/api/lottery/state')
@webapp_auth
def api_lottery_state():
    uid = get_request_uid()
    state = _get_or_create_lottery_round()
    # Tickets from the current active round
    my_tickets = [t for t in state.get('tickets', []) if str(t.get('uid')) == str(uid)]
    # If user has no tickets yet in the new round, also return their results from
    # the previous round so the UI can show their winning/losing tickets.
    if not my_tickets:
        prev = state.get('previous_round') or {}
        prev_tickets = [t for t in prev.get('tickets', []) if str(t.get('uid')) == str(uid)]
        if prev_tickets:
            my_tickets = prev_tickets
    prize_pool = state.get('prize_pool', 0)
    # Theoretical tier prize pools (per-ticket amounts unknown until draw — show pool sizes)
    redistributable = round(prize_pool * (1 - _LOTTERY_ROLLOVER_PCT), 2)
    prize_tiers = {
        'jackpot':   {'matches': _LOTTERY_TIER_JACKPOT,   'pool': prize_pool,
                      'label': 'جائزة كبرى (5/5)'},
        'secondary': {'matches': _LOTTERY_TIER_SECONDARY, 'pool': round(redistributable * _LOTTERY_SECONDARY_SHARE, 2),
                      'label': 'جائزة ثانية (4/5)'},
        'small':     {'matches': _LOTTERY_TIER_SMALL,     'pool': round(redistributable * _LOTTERY_SMALL_SHARE, 2),
                      'label': 'جائزة صغيرة (3/5)'},
        'rollover_pct': _LOTTERY_ROLLOVER_PCT,
    }
    # Build draw types info with current stats
    draw_types = {}
    for dt_key, dt_config in _LOTTERY_DRAW_TYPES.items():
        dt_state = _get_or_create_lottery_round_for_type(dt_key)
        dt_tickets = dt_state.get('tickets', [])
        dt_pool = dt_state.get('prize_pool', 0)
        dt_multiplier = dt_config['multiplier']
        draw_types[dt_key] = {
            'name': dt_config['name'],
            'icon': dt_config['icon'],
            'ticket_price': dt_config['ticket_price'],
            'duration': dt_config['duration'],
            'multiplier': dt_multiplier,
            'draw_time': dt_state.get('draw_time'),
            'tickets_sold': dt_state.get('tickets_sold', 0),
            'max_tickets': 1000,
            'tickets_available': 1000 - dt_state.get('tickets_sold', 0),
            'participants_count': len(set(t.get('uid') for t in dt_tickets)),
            'prize_pool': dt_pool,
            'jackpot_estimate': round(dt_pool * dt_multiplier, 2),
        }

    return jsonify({
        'round_id': state.get('round_id'),
        'draw_time': state.get('draw_time'),
        'ticket_price': state.get('ticket_price', _LOTTERY_TICKET_PRICE),
        'tickets_sold': state.get('tickets_sold', 0),
        'max_tickets': 1000,
        'tickets_available': 1000 - state.get('tickets_sold', 0),
        'participants_count': len(set(t.get('uid') for t in state.get('tickets', []))),
        'prize_pool': prize_pool,
        'prize_tiers': prize_tiers,
        'my_tickets': my_tickets,
        'history': state.get('history', [])[-5:],
        'draw_types': draw_types,
    })

def _reconcile_lottery_tickets(cached_response, locked=False):
    """Re-insert tickets from a cached (already-paid) buy response if a crash
    happened between the debit commit and the ticket save."""
    try:
        tickets = (cached_response or {}).get('tickets') or []
        if not tickets:
            return
        def _do():
            state = _load_lottery_state()
            existing = {t.get('id') for t in state.get('tickets', [])}
            missing = [t for t in tickets if t.get('id') not in existing]
            if missing:
                for t in missing:
                    state.setdefault('tickets', []).append(t)
                state['tickets_sold'] = state.get('tickets_sold', 0) + len(missing)
                _save_lottery_state(state)
        if locked:
            _do()
        else:
            with _lottery_lock:
                _do()
    except Exception as e:
        print(f"[lottery] ticket reconcile error: {e}")

@app.route('/api/lottery/buy', methods=['POST'])
@webapp_auth
def api_lottery_buy():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json or {}
    uid = get_request_uid()
    request_id = _get_request_id()
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400

    # Fast SQLite idempotency check (survives restarts). If the debit
    # committed but the process died before tickets were saved, the cached
    # response still holds the tickets — reconcile them into lottery state.
    if request_id:
        cached = _gm.get_idempotency_record(uid, request_id)
        if cached:
            _reconcile_lottery_tickets(cached)
            return jsonify(cached)

    count = int(data.get('count', 1))
    count = max(1, min(10, count))

    state = _get_or_create_lottery_round()
    if state.get('drawn'):
        return jsonify({'error': 'الجولة انتهت، جولة جديدة قادمة'}), 400

    ticket_price = state.get('ticket_price', _LOTTERY_TICKET_PRICE)
    total_cost = ticket_price * count
    balance = _gm.get_balance(uid)
    if balance < total_cost:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance})

    # Generate tickets before settlement (deterministic from request_id when present)
    new_tickets = []
    for _ in range(count):
        nums = sorted(random.sample(range(1, _LOTTERY_MAX_NUMBER + 1), _LOTTERY_NUMBERS_COUNT))
        ticket = {
            'id': f"T{int(datetime.now().timestamp()*1000)}_{random.randint(1000,9999)}",
            'uid': str(uid),
            'numbers': nums,
            'status': 'pending',
            'scratched': False,
            'drawn': None,
        }
        new_tickets.append(ticket)

    # Build result template without balance_after — settle_with_idempotency fills it in atomically
    template = {
        'success': True,
        'tickets': new_tickets,
        'prize_pool': round(state.get('prize_pool', 0) + total_cost * 0.8, 2),
        'tickets_sold': state.get('tickets_sold', 0) + count,
    }
    # Hold the lottery lock across settle + persist so concurrent buys can
    # never race on stale state (double debit with one ticket set lost), and
    # the debit→ticket-save window is as small as possible.
    with _lottery_lock:
        state = _load_lottery_state()
        if state.get('drawn'):
            return jsonify({'error': 'الجولة انتهت، جولة جديدة قادمة'}), 400
        # Atomic: deduct cost + store idempotency record in one SQLite transaction
        ok, stored, race_cached = _gm.settle_with_idempotency(uid, total_cost, 0, request_id, template)
        if race_cached:
            _reconcile_lottery_tickets(race_cached, locked=True)
            return jsonify(race_cached)
        if not ok:
            return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance})
        for ticket in new_tickets:
            state.setdefault('tickets', []).append(ticket)
        state['tickets_sold'] = state.get('tickets_sold', 0) + count
        state['prize_pool'] = round(state.get('prize_pool', 0) + total_cost * 0.8, 2)
        _save_lottery_state(state)

    return jsonify(stored)

# ===== Snatch — SQLite-backed session state machine =====
#
# Flow:
#   1. POST /api/snatch/spin  — inserts an 'intent' row in snatch_sessions
#                               BEFORE deducting the bet (crash-safe), then
#                               deducts via settle_with_idempotency, then
#                               promotes the row to 'pending'.
#   2. Client plays 20 s, calls:
#   3. POST /api/snatch/end   — atomically claims pending → settling (CAS),
#                               credits payout via credit_with_idempotency,
#                               THEN marks the row settled (credit before
#                               terminal status — idempotent on retry).
#
# Abandonment/recovery — _snatch_sweep() runs at startup + every 60 s:
#   intent  (old)  → check wallet idempotency; promote to pending or delete.
#   pending (>TTL) → CAS pending→refunding (one winner across threads).
#   refunding      → credit refund (idempotent) THEN mark refunded.
#   settling (old) → retry payout credit using stored score THEN mark settled.
#
# Ordering invariant — wallet credit always happens BEFORE the terminal status
# update.  Combined with deterministic idempotency keys on credit_with_idempotency,
# any crash-and-retry is safe: wallet is a no-op on replay, session row stays in
# the intermediate state until the terminal update succeeds.
#
# Score brackets (max_score ≈ 50):
#   score >= 40  (≥80 %)  →  2.0 × bet
#   score >= 25  (≥50 %)  →  1.5 × bet
#   score >= 15  (≥30 %)  →  1.0 × bet  (break-even)
#   score <  15            →  0.0 × bet  (lost; bet already auto-refunded at TTL)

import db_manager as _snatch_dm   # snatch sessions live in vex_games.db alongside wallet

_SNATCH_MAX_SCORE        = 50
_SNATCH_SESSION_TTL      = 35    # seconds; game is 20 s, 15 s grace for network
_SNATCH_INTENT_GRACE     = 120   # seconds before an intent row is resolved
_SNATCH_SETTLING_TIMEOUT = 300   # seconds before a stale settling row is recovered

_SNATCH_GIFT_EMOJIS = ['🎁', '🎀', '🎊', '💰', '⭐', '🏆', '💎', '🍀']
_SNATCH_GIFT_VALUES = [1, 1, 1, 2, 2, 3, 5, 10]


def _snatch_payout_multiplier(score: int) -> float:
    if score >= 40:
        return 2.0
    if score >= 25:
        return 1.5
    if score >= 15:
        return 1.0
    return 0.0


def _snatch_db() -> '_snatch_dm.GameDB':
    """Return the module-level GameDB singleton (vex_games.db).

    snatch_sessions lives in the same file as the wallet idempotency table,
    so crash recovery can correlate spin idempotency records with session rows
    regardless of which data-volume is mounted.
    """
    return _snatch_dm._gdb


def _snatch_sweep():
    """Recover and refund snatch sessions. Runs at startup and every 60 s.

    All wallet operations use credit_with_idempotency (deterministic keys) so
    they are exactly-once even if this function is interrupted and re-runs.
    The terminal status (settled/refunded) is committed AFTER the wallet credit
    so any crash leaves the row in a retryable intermediate state.
    """
    if not _VEX_GAMES:
        return
    now = datetime.now().timestamp()
    sdb = _snatch_db()

    # 1. Resolve old 'intent' rows ─────────────────────────────────────────────
    # intent means the session row was written but deduction may not have run.
    for sess in sdb.snatch_get_by_status('intent', created_before=now - _SNATCH_INTENT_GRACE):
        session_id = sess['session_id']
        uid = sess['uid']
        spin_request_id = sess['spin_request_id']
        try:
            idem = _gm.get_idempotency_record(uid, spin_request_id) \
                if spin_request_id else None
            if idem:
                sdb.snatch_cas_status(session_id, 'intent', 'pending')
                _auth_logger.info("Snatch: intent→pending %s", session_id)
            else:
                sdb.snatch_delete_session(session_id)
                _auth_logger.info("Snatch: deleted ghost intent %s", session_id)
        except Exception as exc:
            _auth_logger.error("Snatch intent resolve %s: %s", session_id, exc)

    # 2. Claim expired 'pending' rows for refund ───────────────────────────────
    for sess in sdb.snatch_get_by_status('pending', created_before=now - _SNATCH_SESSION_TTL):
        session_id = sess['session_id']
        updated = sdb.snatch_cas_status(session_id, 'pending', 'refunding')
        if updated:
            _auth_logger.info("Snatch: claimed %s for refund", session_id)

    # 3. Process 'refunding' rows: credit THEN mark terminal ───────────────────
    for sess in sdb.snatch_get_by_status('refunding'):
        session_id = sess['session_id']
        uid = sess['uid']
        bet_amount = sess['bet_amount']
        try:
            if bet_amount > 0:
                _gm.credit_with_idempotency(
                    uid, bet_amount, f"snatch_refund_{session_id}",
                    {'success': True, 'refunded': True, 'session_id': session_id}
                )
            # Terminal update AFTER wallet credit — safe to retry on crash.
            sdb.snatch_cas_status(session_id, 'refunding', 'refunded',
                                  settled_at=datetime.now().timestamp())
            _auth_logger.info(
                "Snatch: refunded session=%s uid=%s amount=%.2f",
                session_id, uid, bet_amount
            )
        except Exception as exc:
            _auth_logger.error("Snatch refund %s: %s", session_id, exc)

    # 4. Recover stale 'settling' rows (end-call crashed mid-credit) ───────────
    # The server-authoritative payout is stored in sess['payout'] at spin time;
    # we never recompute from the client-supplied score here.
    for sess in sdb.snatch_get_by_status('settling',
                                         created_before=now - _SNATCH_SETTLING_TIMEOUT):
        session_id = sess['session_id']
        uid = sess['uid']
        payout = sess['payout'] if sess['payout'] is not None else 0.0
        try:
            if payout > 0:
                _gm.credit_with_idempotency(
                    uid, payout, f"snatch_payout_{session_id}",
                    {'success': True, 'payout': payout, 'session_id': session_id}
                )
            # Terminal update AFTER wallet credit.
            sdb.snatch_cas_status(session_id, 'settling', 'settled',
                                  settled_at=datetime.now().timestamp())
            _auth_logger.info(
                "Snatch: recovered settling=%s payout=%.2f", session_id, payout
            )
        except Exception as exc:
            _auth_logger.error("Snatch settling recovery %s: %s", session_id, exc)


def _snatch_sweep_daemon():
    """Background daemon: run _snatch_sweep() every 60 s."""
    import time as _time
    while True:
        try:
            _snatch_sweep()
        except Exception as exc:
            _auth_logger.error("snatch_sweep_daemon: %s", exc)
        _time.sleep(60)


# ── Startup: snatch_sessions table is created by db_manager._init_db() ───────
# Just run the sweep to recover any sessions that expired during downtime.
try:
    _snatch_sweep()
except Exception as _sni_exc:
    _auth_logger.error("Snatch startup sweep error: %s", _sni_exc)

threading.Thread(target=_snatch_sweep_daemon, daemon=True, name='snatch-sweep').start()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/api/snatch/spin', methods=['POST'])
@webapp_auth
def api_snatch_spin():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500

    # Snatch requires the SQLite-backed wallet so that the deduction
    # idempotency record and the session row are in the same durable store.
    # If the wallet is operating in CSV/in-memory fallback mode the crash-
    # recovery sweep cannot correlate wallet records with sessions, which
    # would silently delete 'intent' rows and leave bets un-refunded.
    import game_engine as _ge
    if not getattr(_ge, '_USE_SQLITE', False):
        return jsonify({
            'success': False,
            'error': 'Snatch is temporarily unavailable (database not ready)',
        }), 503

    data = request.json or {}
    uid = get_request_uid()
    request_id = _get_request_id()
    if not uid:
        return jsonify({'error': 'Missing params'}), 400

    # Idempotency check BEFORE any side effects — replays return the stored
    # response without creating duplicate sessions or debits.
    if request_id:
        cached = _gm.get_idempotency_record(uid, request_id)
        if cached:
            return jsonify(cached)

    bet_amount = float(data.get('bet', 0))
    if bet_amount <= 0:
        return jsonify({'error': 'Missing params'}), 400

    player = _gm.tracker.get_profile(uid)
    game = _gm.get_game('GAME001') or {
        'id': 'GAME001', 'base_win_chance': '0.55', 'house_edge_pct': '12',
        'min_bet': '10', 'max_bet': '2000'
    }

    risk_check = _gm.risk.check_risk(player, bet_amount, game)
    if not risk_check['allowed']:
        msg = risk_check['alerts'][0]['message'] if risk_check.get('alerts') else 'محظور'
        return jsonify({'success': False, 'error': msg})

    balance = _gm.get_balance(uid)
    if balance < bet_amount:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ',
                        'need_deposit': True, 'balance': balance})

    session_id = f"SNT{secrets.token_hex(8)}"
    # Use request_id as the wallet idempotency key; fall back to session-derived key.
    deduction_key = request_id or f"spin_{session_id}"

    # ── Compute server-authoritative payout BEFORE creating the session ───────
    # The payout is determined by the server's game algorithm, not the client.
    # It is stored in the session row immediately so /api/snatch/end and the
    # sweep can credit the same amount regardless of what score the client reports.
    # HouseAlgorithm.calculate_win_chance() returns decision values:
    #   'allow_win'  → player wins this round
    #   'near_miss'  → near-win (house keeps edge; treat as a loss for payout)
    #   'force_lose' → hard loss
    algo_result = _gm.algorithm.calculate_win_chance(player, game, bet_amount)
    server_won = (algo_result['decision'] == 'allow_win')
    if server_won:
        # Pick a multiplier tier; higher tier = rarer outcome
        _tier_roll = secrets.SystemRandom().random()
        if _tier_roll < 0.25:
            server_multiplier = 2.0    # big win   (25 %)
        elif _tier_roll < 0.55:
            server_multiplier = 1.5    # medium win (30 %)
        else:
            server_multiplier = 1.0    # break-even (45 %)
    else:
        server_multiplier = 0.0        # loss
    server_payout = round(bet_amount * server_multiplier, 2)

    sdb = _snatch_db()

    # ── Step 1: persist 'intent' row BEFORE touching the wallet ───────────────
    # If the server crashes between here and the deduction, _snatch_sweep will
    # check the wallet idempotency record for deduction_key and either promote
    # the row to 'pending' (deduction happened) or delete it (no money moved).
    # The server_payout is stored in the row so crash recovery can credit the
    # correct amount without recomputing from a client-supplied score.
    try:
        sdb.snatch_create_session(session_id, uid, bet_amount,
                                  deduction_key, datetime.now().timestamp(),
                                  server_payout=server_payout)
    except Exception as exc:
        _auth_logger.error("Snatch intent row insert failed: %s", exc)
        return jsonify({'error': 'خطأ داخلي'}), 500

    # ── Step 2: deduct bet in the wallet DB (atomic, idempotent) ─────────────
    template = {
        'success': True,
        'session_id': session_id,
        'gift_emojis': _SNATCH_GIFT_EMOJIS,
        'gift_values': _SNATCH_GIFT_VALUES,
        'max_score': _SNATCH_MAX_SCORE,
        'game_duration': 20,
        'balance_before': balance,
    }
    ok, stored, race_cached = _gm.settle_with_idempotency(
        uid, bet_amount, 0, deduction_key, template)

    if race_cached:
        # Concurrent identical request already settled — drop our orphan intent row.
        try:
            sdb.snatch_delete_session(session_id)
        except Exception:
            pass
        return jsonify(race_cached)

    if not ok:
        # Insufficient funds — no money moved, remove the intent row.
        try:
            sdb.snatch_delete_session(session_id)
        except Exception:
            pass
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ',
                        'need_deposit': True, 'balance': balance})

    # ── Step 3: promote intent → pending ─────────────────────────────────────
    # Deduction succeeded; bet is tracked and will be refunded if the client
    # never calls /api/snatch/end within the TTL.
    try:
        sdb.snatch_cas_status(session_id, 'intent', 'pending')
    except Exception as exc:
        # intent row has spin_request_id so _snatch_sweep will detect the
        # wallet record and promote it on next run.
        _auth_logger.error("Snatch intent→pending failed (sweep will recover): %s", exc)

    _gm.algorithm.log_decision(
        session_id=session_id, user_id=uid, game_id='GAME001',
        base_chance=float(game.get('base_win_chance', 0.55)),
        adjusted_chance=algo_result['win_chance'], factors=algo_result['factors'],
        decision=algo_result['decision'],
        reason=f"Snatch spin bet={bet_amount} server_payout={server_payout}; "
               f"{algo_result['reason']}"
    )
    return jsonify(stored)


@app.route('/api/snatch/end', methods=['POST'])
@webapp_auth
def api_snatch_end():
    """Settle a completed snatch session and credit the skill-based payout."""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json or {}
    uid = get_request_uid()
    if not uid:
        return jsonify({'error': 'Missing params'}), 400

    session_id = str(data.get('session_id', '')).strip()
    try:
        score = max(0, int(data.get('score', 0)))
    except (TypeError, ValueError):
        score = 0
    # Cap at a generous ceiling to limit tampered-client damage without
    # rejecting any realistic score (max ≈ 2 gifts/wave × 10 pts × 20 waves = 400).
    score = min(score, 200)

    if not session_id:
        return jsonify({'error': 'Missing session_id'}), 400

    sdb = _snatch_db()

    # ── Read session ──────────────────────────────────────────────────────────
    try:
        sess = sdb.snatch_get_session(session_id)
    except Exception as exc:
        _auth_logger.error("snatch_end DB read %s: %s", session_id, exc)
        return jsonify({'error': 'خطأ داخلي'}), 500

    if not sess:
        return jsonify({'error': 'Session not found or already settled'}), 400

    if str(sess['uid']) != str(uid):
        return jsonify({'error': 'Session mismatch'}), 403

    if sess['status'] != 'pending':
        return jsonify({'error': f'Session already {sess["status"]}'}), 400

    if datetime.now().timestamp() - sess['created_at'] > _SNATCH_SESSION_TTL:
        return jsonify({'error': 'Session expired'}), 400

    bet_amount = sess['bet_amount']

    # ── Read server-determined payout (set at spin time, never from client) ───
    # The payout was computed by the server algorithm and stored in the session
    # row at spin time.  The client's reported score is stored for analytics
    # but does NOT affect the financial outcome.
    payout = sess['payout'] if sess['payout'] is not None else 0.0

    # ── Atomic CAS: pending → settling ────────────────────────────────────────
    # Exactly one of (this call) or (_snatch_sweep) can win the CAS.
    # We store the client score for analytics only.
    try:
        updated = sdb.snatch_cas_status(session_id, 'pending', 'settling', score=score)
    except Exception as exc:
        _auth_logger.error("snatch_end CAS %s: %s", session_id, exc)
        return jsonify({'error': 'خطأ داخلي'}), 500

    if updated == 0:
        return jsonify({'error': 'Session already claimed by concurrent process'}), 400

    # ── Credit server-determined payout in wallet DB (idempotent key) ─────────
    won = payout > 0
    result_str = 'win' if won else 'lose'
    # Compute approximate multiplier for display/logging; not used for financials.
    display_multiplier = round(payout / bet_amount, 2) if bet_amount else 0.0
    new_balance = _gm.get_balance(uid)

    if payout > 0:
        _, credit_result, credit_cached = _gm.credit_with_idempotency(
            uid, payout, f"snatch_payout_{session_id}",
            {'success': True, 'payout': payout, 'session_id': session_id}
        )
        cr = credit_cached or credit_result or {}
        new_balance = cr.get('balance_after', _gm.get_balance(uid))

    # ── Mark settled AFTER wallet credit ─────────────────────────────────────
    # If we crash here the sweep sees status='settling', re-issues
    # credit_with_idempotency (idempotent no-op using payout already in the row),
    # then marks settled.
    try:
        sdb.snatch_cas_status(session_id, 'settling', 'settled',
                              settled_at=datetime.now().timestamp())
    except Exception as exc:
        _auth_logger.error("snatch_end terminal update %s (sweep will finish): %s",
                           session_id, exc)

    _gm.tracker.log_session({
        'session_id': session_id, 'game_id': 'GAME001', 'user_id': uid,
        'bet_amount': bet_amount, 'payout': payout, 'result': result_str,
        'balance_before': new_balance - payout if payout else new_balance,
        'balance_after': new_balance, 'multiplier': display_multiplier,
    })
    _gm.tracker.update_profile(uid, {
        'bet_amount': bet_amount, 'payout': payout, 'result': result_str,
        'game_id': 'GAME001', 'balance_after': new_balance,
    })

    return jsonify({
        'success': True, 'won': won, 'score': score,
        'multiplier': display_multiplier, 'payout': payout,
        'result': result_str, 'balance_after': new_balance,
    })

# ===== Admin: Advanced Game Control =====

@app.route('/api/games/<game_id>/config', methods=['POST'])
@api_auth
@permission_required('manage_games')
def api_game_config_update(game_id):
    """تحديث إعدادات لعبة محددة (base_win_chance, house_edge, min/max bet)"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    try:
        rows = []
        with open(os.path.join(BASE_DIR, 'games_catalog.csv'), 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                if row.get('id') == game_id:
                    for key in ['base_win_chance', 'house_edge_pct', 'rtp_target',
                                'min_bet', 'max_bet', 'is_active', 'name', 'icon',
                                'description', 'volatility', 'max_payout_per_session']:
                        if key in data:
                            row[key] = str(data[key])
                rows.append(row)
        with open(os.path.join(BASE_DIR, 'games_catalog.csv'), 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        _gm.algorithm.invalidate_cache()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/games/kill-switch', methods=['POST'])
@api_auth
@permission_required('manage_games')
def api_games_kill_switch():
    """إيقاف/تشغيل كل الألعاب فوراً"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    action = request.json.get('action', 'pause')  # pause or resume
    try:
        rows = []
        with open(os.path.join(BASE_DIR, 'games_catalog.csv'), 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                row['is_active'] = 'yes' if action == 'resume' else 'no'
                rows.append(row)
        with open(os.path.join(BASE_DIR, 'games_catalog.csv'), 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        push_notification('kill_switch', f'{"⏸️ ألعاب متوقفة" if action=="pause" else "▶️ ألعاب مفعلة"}', f'Admin {action}ed all games', {})
        return jsonify({'success': True, 'action': action})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/player/<uid>/profile', methods=['GET'])
@api_auth
def api_admin_player_profile(uid):
    """ملف لاعب كامل — الإحصائيات + الرصيد + الجلسات"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    profile = _gm.tracker.get_profile(uid)
    balance = _gm.get_balance(uid)
    user_info = _gm.get_user_info(uid)
    # Get last 20 sessions
    sessions = []
    try:
        with open(os.path.join(BASE_DIR, 'game_sessions.csv'), 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            all_sessions = list(reader)
        sessions = [s for s in all_sessions if s.get('user_id') == str(uid)][-20:]
    except:
        pass
    # Algorithm decisions for this player
    decisions = []
    try:
        with open(os.path.join(BASE_DIR, 'algorithm_decisions.csv'), 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            all_dec = list(reader)
        decisions = [d for d in all_dec if d.get('user_id') == str(uid)][-10:]
    except:
        pass
    # Churn risk
    churn = _gm.algorithm.check_churn_risk(profile) if _gm.algorithm else {'risk': 'none'}
    return jsonify({
        'profile': profile,
        'balance': balance,
        'user_info': user_info,
        'sessions': sessions,
        'decisions': decisions,
        'churn_risk': churn,
    })

@app.route('/api/admin/player/<uid>/force-result', methods=['POST'])
@api_auth
@permission_required('manage_games')
def api_admin_force_result(uid):
    """إجبار نتيجة اللاعب التالية (win/lose/normal)"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    data = request.json
    force = data.get('force', 'normal')  # win, lose, normal
    rounds = int(data.get('rounds', 1))  # for how many rounds
    try:
        profile = _gm.tracker.get_profile(uid)
        if force == 'win':
            profile['admin_win_override'] = '1.0'  # force win
        elif force == 'lose':
            profile['admin_win_override'] = '-1'  # force lose
        else:
            profile['admin_win_override'] = '0'  # normal
        _gm.tracker._save_profile(profile)
        log_action('force_result', f'Player {uid}: {force} for {rounds} rounds')
        return jsonify({'success': True, 'force': force, 'rounds': rounds})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/player/<uid>/reset-daily', methods=['POST'])
@api_auth
@permission_required('manage_games')
def api_admin_reset_daily(uid):
    """إعادة ضبط الإحصائيات اليومية للاعب"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    try:
        profile = _gm.tracker.get_profile(uid)
        profile = _gm.algorithm.reset_daily_stats(profile) if _gm.algorithm else profile
        _gm.tracker._save_profile(profile)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/player/<uid>/reset-override', methods=['POST'])
@api_auth
@permission_required('manage_games')
def api_admin_reset_override(uid):
    """إلغاء تحكم الأدمن على اللاعب"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    try:
        profile = _gm.tracker.get_profile(uid)
        profile['admin_win_override'] = '0'
        _gm.tracker._save_profile(profile)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/search-players', methods=['GET'])
@api_auth
def api_admin_search_players():
    """البحث عن لاعبين بالاسم/الـID/الهاتف"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    query = request.args.get('q', '').lower()
    if not query:
        return jsonify({'players': []})
    # Search in users.csv
    users = read_csv('users.csv')
    results = []
    for u in users:
        if (query in (u.get('name', '') or '').lower() or
            query in (u.get('telegram_id', '') or '').lower() or
            query in (u.get('customer_id', '') or '').lower() or
            query in (u.get('phone', '') or '')):
            results.append({
                'uid': u.get('telegram_id', ''),
                'name': u.get('name', ''),
                'customer_id': u.get('customer_id', ''),
                'phone': u.get('phone', ''),
                'currency': u.get('currency', 'EGP'),
                'game_balance': u.get('game_balance', '0'),
                'is_banned': u.get('is_banned', 'no'),
            })
    return jsonify({'players': results, 'count': len(results)})

@app.route('/api/admin/platform-stats', methods=['GET'])
@api_auth
def api_admin_platform_stats():
    """إحصائيات المنصة الكاملة — للوحة التحكم"""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    # Platform stats
    stats = _gm.get_platform_stats()
    health = _gm.risk.check_platform_health() if _gm.risk else {}
    # Active alerts
    alerts = _gm.risk.get_active_alerts() if _gm.risk else []
    # Pending deposits
    deposits = _gm.get_pending_deposits() if hasattr(_gm, 'get_pending_deposits') else []
    # Pending withdrawals
    withdrawals = _gm.get_pending_withdrawals() if hasattr(_gm, 'get_pending_withdrawals') else []
    # Algorithm config
    config = _gm.algorithm.config if _gm.algorithm else {}
    # Games list
    games = _gm.get_games(active_only=False)
    # Top players
    top_players = _gm.tracker.get_top_players(limit=20) if _gm.tracker else []
    return jsonify({
        'stats': stats,
        'health': health,
        'alerts': alerts,
        'pending_deposits': deposits,
        'pending_withdrawals': withdrawals,
        'config': config,
        'games': games,
        'top_players': top_players,
        'total_games': len(games),
        'active_games': len([g for g in games if g.get('is_active') == 'yes']),
    })

# ===== Lockdown Log API =====

@app.route('/api/admin/lockdown-log', methods=['GET'])
@api_auth
@permission_required('manage_admins')
def api_admin_lockdown_log():
    """Return lockdown/recovery history with summary statistics.

    Query params:
      limit  — max rows to return (default 100, max 500)
      page   — 1-based page (default 1)

    Response JSON:
      {
        "rows":    [{event, timestamp, host, duration_seconds, telegram_sent, reason}, ...],
        "total":   <int>,
        "page":    <int>,
        "limit":   <int>,
        "summary": {
          "total_episodes":              <int>,
          "total_downtime_seconds":      <int>,
          "this_month_episodes":         <int>,
          "this_month_downtime_seconds": <int>,
        }
      }
    """
    try:
        limit = min(int(request.args.get('limit', 100)), 500)
        page  = max(int(request.args.get('page', 1)), 1)
    except (ValueError, TypeError):
        limit, page = 100, 1

    all_rows = read_csv(_LOCKDOWN_LOG)
    all_rows.reverse()          # newest first

    total = len(all_rows)
    start = (page - 1) * limit
    page_rows = all_rows[start:start + limit]

    # Summary over ALL rows (not just the current page)
    now = datetime.now()
    month_prefix = now.strftime('%Y-%m')
    total_episodes = 0
    total_downtime_s = 0
    month_episodes = 0
    month_downtime_s = 0

    for row in all_rows:
        if row.get('event') == 'lockdown':
            total_episodes += 1
            ts = row.get('timestamp', '')
            if ts.startswith(month_prefix):
                month_episodes += 1
        if row.get('event') == 'recovery':
            try:
                ds = int(row.get('duration_seconds', 0))
            except (ValueError, TypeError):
                ds = 0
            total_downtime_s += ds
            ts = row.get('timestamp', '')
            if ts.startswith(month_prefix):
                month_downtime_s += ds

    return jsonify({
        'rows':  page_rows,
        'total': total,
        'page':  page,
        'limit': limit,
        'summary': {
            'total_episodes':              total_episodes,
            'total_downtime_seconds':      total_downtime_s,
            'this_month_episodes':         month_episodes,
            'this_month_downtime_seconds': month_downtime_s,
        }
    })


@app.route('/api/admin/lockdown-log/export', methods=['GET'])
@api_auth
@permission_required('manage_admins')
def api_admin_lockdown_log_export():
    """Stream the full lockdown_log.csv as a file download.

    Returns the raw CSV with all rows (no pagination) so ops teams can
    open it directly in Excel or import it into Google Sheets.
    If the log file does not exist yet, returns an empty CSV with just
    the header row so the download still succeeds.
    """
    filepath = os.path.join(BASE_DIR, _LOCKDOWN_LOG)

    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                csv_content = f.read()
        except Exception as exc:
            _auth_logger.error("lockdown-log export read error: %s", exc)
            return jsonify({'error': 'Failed to read log file'}), 500
    else:
        # No events yet — return a header-only CSV so the download works
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_LOCKDOWN_LOG_FIELDS)
        writer.writeheader()
        csv_content = buf.getvalue()

    now_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'lockdown_log_{now_str}.csv'

    return Response(
        csv_content,
        status=200,
        mimetype='text/csv; charset=utf-8',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Cache-Control': 'no-store',
        }
    )


# ===== Chat / Emoji Reactions =====

_chat_messages = []  # In-memory chat (last 50)
_chat_lock = threading.Lock()
_chat_queues = []  # SSE subscriber queues
_chat_q_lock = threading.Lock()

@app.route('/api/games/chat/send', methods=['POST'])
@webapp_auth
def api_games_chat_send():
    """Send a chat message or emoji reaction"""
    data = request.json
    uid_val = get_request_uid()
    msg = data.get('message', '').strip()[:200]  # Max 200 chars
    emoji = data.get('emoji', '')
    if not msg and not emoji:
        return jsonify({'error': 'Empty message'}), 400

    # Get user name
    user_name = ''
    try:
        with open(os.path.join(BASE_DIR, 'users.csv'), 'r', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                if row.get('telegram_id') == str(uid_val):
                    user_name = row.get('name', '')
                    break
    except:
        pass

    entry = {
        'uid': uid_val,
        'name': user_name or '???',
        'message': msg,
        'emoji': emoji,
        'timestamp': datetime.now().isoformat(),
    }

    with _chat_lock:
        _chat_messages.append(entry)
        if len(_chat_messages) > 50:
            _chat_messages.pop(0)

    # Broadcast to SSE subscribers
    payload = json.dumps({'type': 'chat', 'data': entry})
    with _chat_q_lock:
        for q in _chat_queues:
            try:
                q.put_nowait(payload)
            except:
                pass

    return jsonify({'success': True})

@app.route('/api/games/chat/history')
@webapp_auth
def api_games_chat_history():
    """Get recent chat messages"""
    with _chat_lock:
        return jsonify({'messages': list(_chat_messages[-30:])})

@app.route('/api/games/chat/stream')
@webapp_auth
def api_games_chat_stream():
    """SSE stream for live chat"""
    q = _queue.Queue()
    with _chat_q_lock:
        _chat_queues.append(q)
    def generate():
        import time
        # Send recent messages on connect
        with _chat_lock:
            for m in _chat_messages[-10:]:
                yield f"data: {json.dumps({'type': 'chat', 'data': m})}\n\n"
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"
        while True:
            try:
                payload = q.get(timeout=15)
                yield f"data: {payload}\n\n"
            except _queue.Empty:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
    try:
        return Response(generate(), mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
    finally:
        with _chat_q_lock:
            if q in _chat_queues:
                _chat_queues.remove(q)

# ===== Player Statistics API =====

@app.route('/api/player/stats')
@webapp_auth
def api_player_stats():
    """Player statistics — win rate, P/L, bet history, game distribution"""
    uid_val = get_request_uid()
    if not uid_val:
        return jsonify({'error': 'No uid'}), 400

    # Try SQLite first
    try:
        import sys as _sys
        _sys.path.insert(0, BASE_DIR)
        from db_manager import _gdb as _ldb
        sessions = _ldb.get_user_sessions(uid_val, limit=100)
        if not sessions:
            return jsonify({
                'total_bets': 0, 'total_wagered': 0, 'total_won': 0,
                'net_profit': 0, 'win_rate': 0, 'total_rounds': 0,
                'games': [], 'recent': [], 'chart_data': []
            })
        total_bets = len(sessions)
        total_wagered = sum(s.get('bet_amount', 0) for s in sessions)
        total_won = sum(s.get('payout', 0) for s in sessions)
        total_wins = sum(1 for s in sessions if s.get('result') == 'win')
        net_profit = total_won - total_wagered
        win_rate = round(total_wins / max(total_bets, 1) * 100, 1)

        # Game distribution
        game_dist = {}
        for s in sessions:
            gid = s.get('game_id', 'unknown')
            if gid not in game_dist:
                game_dist[gid] = {'games': 0, 'wagered': 0, 'won': 0, 'wins': 0}
            game_dist[gid]['games'] += 1
            game_dist[gid]['wagered'] += s.get('bet_amount', 0)
            game_dist[gid]['won'] += s.get('payout', 0)
            if s.get('result') == 'win':
                game_dist[gid]['wins'] += 1

        # Chart data (last 20 rounds P/L)
        chart_data = []
        for s in reversed(sessions[-20:]):
            pl = s.get('payout', 0) - s.get('bet_amount', 0)
            chart_data.append({
                'round': len(chart_data) + 1,
                'pl': round(pl, 2),
                'bet': s.get('bet_amount', 0),
                'payout': s.get('payout', 0),
                'game': s.get('game_id', ''),
                'result': s.get('result', '')
            })

        return jsonify({
            'total_bets': total_bets,
            'total_wagered': round(total_wagered, 2),
            'total_won': round(total_won, 2),
            'net_profit': round(net_profit, 2),
            'win_rate': win_rate,
            'total_rounds': total_bets,
            'total_wins': total_wins,
            'games': [{'game_id': k, **v} for k, v in game_dist.items()],
            'recent': sessions[:20],
            'chart_data': chart_data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/create-token', methods=['POST', 'GET'])
def api_auth_create_token():
    """Create a session token for a given uid.

    Called by the bot before opening the WebApp so the user never needs
    a plain uid in the URL.  Returns {'s': token} on success.
    """
    try:
        uid = ''
        if request.method == 'POST':
            try:
                uid = (request.get_json(silent=True) or {}).get('uid', '')
            except Exception:
                pass
        if not uid:
            uid = request.args.get('uid', '').strip()
        if not uid:
            return jsonify({'error': 'uid required', 'code': 'NO_UID'}), 400
        uid = str(uid).strip()
        from session_tokens import create_session as _cs
        token = _cs(uid)
        return jsonify({'s': token, 'uid': uid, 'ok': True})
    except Exception as e:
        return jsonify({'error': str(e), 'code': 'SESSION_ERROR'}), 500


@app.route('/webapp/stats')
def webapp_stats():
    """Player statistics page — WebApp (kept for backward compat; account page replaces it)"""
    return render_template('stats.html')

@app.route('/webapp/account')
def webapp_account():
    """Unified player account page — profile, referrals, rewards, transactions.

    Auth note: this route renders the page shell with no server-side auth.
    The four account API endpoints require g.webapp_auth_strong=True, which is
    only set by HMAC-validated Telegram initData or a device-authorized encrypted
    session.  In practice all legitimate users open this page inside the Telegram
    Mini App where tg.initData is populated; game-base.js sends it as
    X-Telegram-Init-Data on every apiFetch call.  Callers arriving outside
    Telegram (no initData, no valid session ?s=) see a graceful 403 message.
    No server-side uid→session minting occurs here — uid is not a trusted identity.
    """
    return render_template('account.html')

# ── Unified account API ────────────────────────────────────────────────────────

@app.route('/api/player/account')
@account_auth
def api_player_account():
    """Unified account endpoint: profile + game stats + SVRP summary + referral summary + recent txns."""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400

    import sys as _asys; _asys.path.insert(0, BASE_DIR)

    # ── Profile (users.csv) ──────────────────────────────────────────────
    user_row = {}
    try:
        users = read_csv('users.csv')
        user_row = next((u for u in users if str(u.get('telegram_id', '')) == uid), {})
    except Exception:
        pass
    name         = user_row.get('name', '')
    phone        = user_row.get('phone', '')
    customer_id  = user_row.get('customer_id', '')
    joined_date  = user_row.get('date', '')
    currency     = user_row.get('currency', 'EGP')
    phone_verified = user_row.get('phone_verified', 'no')
    ref_earnings_csv = float(user_row.get('referral_earnings', 0) or 0)

    # ── Game balance + profile (SQLite) ──────────────────────────────────
    game_balance = float(_gm.get_balance(uid) or 0)
    user_info    = _gm.get_user_info(uid) or {}
    currency     = user_info.get('currency', currency)
    profile      = _gm.tracker.get_profile(uid)
    is_vip       = profile.get('is_vex_partner', '') == 'yes'

    # ── Game stats (SQLite sessions) ─────────────────────────────────────
    game_stats = {'total_bets': 0, 'win_rate': 0, 'net_profit': 0, 'total_wins': 0}
    try:
        from db_manager import _gdb as _ldb
        sessions = _ldb.get_user_sessions(uid, limit=100) or []
        if sessions:
            total_bets    = len(sessions)
            total_wagered = sum(s.get('bet_amount', 0) for s in sessions)
            total_won_s   = sum(s.get('payout', 0) for s in sessions)
            total_wins    = sum(1 for s in sessions if s.get('result') == 'win')
            game_stats = {
                'total_bets':    total_bets,
                'total_wagered': round(total_wagered, 2),
                'total_won':     round(total_won_s, 2),
                'net_profit':    round(total_won_s - total_wagered, 2),
                'total_wins':    total_wins,
                'win_rate':      round(total_wins / max(total_bets, 1) * 100, 1),
            }
    except Exception:
        pass

    # ── SVRP wallet summary (SQLite authoritative) ────────────────────────
    _svrp = _gm.get_svrp_frozen_balance(uid)
    svrp_summary = {
        'frozen_balance':    float(_svrp.get('frozen_balance', 0) or 0),
        'total_earned':      float(_svrp.get('total_earned', 0) or 0),
        'wagering_required': int(_svrp.get('wagering_required', 3) or 3),
        'wagering_completed':int(_svrp.get('wagering_completed', 0) or 0),
        'wagering_done':     int(_svrp.get('wagering_completed', 0) or 0) >=
                             int(_svrp.get('wagering_required', 3) or 3),
    }

    # ── Referral summary (referral_log.csv) ───────────────────────────────
    referral_count   = 0
    referral_earnings = 0.0
    try:
        ref_log = read_csv('referral_log.csv')
        my_refs = [r for r in ref_log if str(r.get('referrer_id', '')) == uid]
        referral_count   = len(my_refs)
        referral_earnings = ref_earnings_csv or sum(
            float(r.get('bonus_amount', r.get('bonus', 0)) or 0) for r in my_refs
        )
    except Exception:
        pass

    # ── Recent transactions (last 10) ─────────────────────────────────────
    recent_txns = []
    try:
        txns = read_csv('transactions.csv')
        user_txns = [t for t in txns if str(t.get('telegram_id', '')) == uid]
        for t in reversed(user_txns[-10:]):
            recent_txns.append({
                'id':      t.get('id', ''),
                'type':    t.get('type', ''),
                'amount':  float(t.get('amount', 0) or 0),
                'status':  t.get('status', ''),
                'company': t.get('company', ''),
                'date':    t.get('date', ''),
            })
    except Exception:
        pass

    return jsonify({
        'uid':             uid,
        'name':            name,
        'phone':           phone,
        'customer_id':     customer_id,
        'joined_date':     joined_date,
        'currency':        currency,
        'phone_verified':  phone_verified,
        'is_vip':          is_vip,
        'game_balance':    game_balance,
        'game_stats':      game_stats,
        'svrp':            svrp_summary,
        'referral_count':  referral_count,
        'referral_earnings': round(referral_earnings, 2),
        'recent_txns':     recent_txns,
    })


@app.route('/api/player/referrals')
@account_auth
def api_player_referrals():
    """Player referral data: link, earnings, full list of referred users."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400

    # customer_id for building the referral code
    customer_id = ''
    try:
        users = read_csv('users.csv')
        u = next((x for x in users if str(x.get('telegram_id', '')) == uid), {})
        customer_id = u.get('customer_id', uid)
    except Exception:
        customer_id = uid

    # Referral log entries where this user is the referrer
    referrals = []
    total_earnings = 0.0
    try:
        ref_log = read_csv('referral_log.csv')
        for r in ref_log:
            if str(r.get('referrer_id', '')) != uid:
                continue
            bonus = float(r.get('bonus_amount', r.get('bonus', 0)) or 0)
            total_earnings += bonus
            referrals.append({
                'referred_name':   r.get('referred_name', ''),
                'phone_verified':  r.get('phone_verified', 'no'),
                'bonus_amount':    bonus,
                'currency':        r.get('currency', 'EGP'),
                'status':          r.get('status', ''),
                'created_at':      r.get('created_at', ''),
            })
    except Exception:
        pass

    # Referral link — Telegram bot deep-link
    bot_username = os.environ.get('BOT_USERNAME', '')
    if bot_username:
        referral_link = f'https://t.me/{bot_username}?start=ref_{customer_id}'
    else:
        referral_link = ''

    return jsonify({
        'referral_code':    customer_id,
        'referral_link':    referral_link,
        'total_referrals':  len(referrals),
        'verified_referrals': sum(1 for r in referrals if r['phone_verified'] == 'yes'),
        'total_earnings':   round(total_earnings, 2),
        'referrals':        list(reversed(referrals)),  # newest first
    })


@app.route('/api/player/rewards')
@account_auth
def api_player_rewards():
    """Player rewards: today's SVRP tasks + approved recovery requests + promo balances."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400

    import sys as _rsys; _rsys.path.insert(0, BASE_DIR)
    from svrp import SVRPManager as _SMgr

    mgr = _SMgr()
    # Ensure today's tasks exist
    try:
        mgr.create_daily_tasks(uid)
    except Exception:
        pass

    # Today's tasks
    tasks = []
    try:
        raw_tasks = mgr.get_user_tasks(uid)
        _task_labels = {
            'deposit_count':  {'label': 'أودع مرة واحدة اليوم', 'icon': '💰'},
            'deposit_amount': {'label': 'أودع مبلغاً محدداً اليوم', 'icon': '💵'},
            'referral_count': {'label': 'ادعُ صديقاً اليوم', 'icon': '👥'},
        }
        for t in raw_tasks:
            tt = t.get('task_type', '')
            meta = _task_labels.get(tt, {'label': tt, 'icon': '🎯'})
            progress   = float(t.get('current_progress', 0) or 0)
            target     = float(t.get('target_value', 1) or 1)
            status     = t.get('status', 'active')
            reward     = float(t.get('reward_amount', 0) or 0)
            tasks.append({
                'id':          t.get('id', ''),
                'type':        tt,
                'label':       meta['label'],
                'icon':        meta['icon'],
                'progress':    progress,
                'target':      target,
                'pct':         round(min(progress / max(target, 1), 1.0) * 100),
                'status':      status,
                'reward':      reward,
                'claimable':   status == 'completed',
                'created_at':  t.get('created_at', ''),
            })
    except Exception:
        pass

    # Approved recovery requests (display history)
    recovery_history = []
    try:
        reqs = read_csv('recovery_requests.csv')
        user_reqs = [r for r in reqs if str(r.get('user_id', '')) == uid]
        for r in reversed(user_reqs[-10:]):
            recovery_history.append({
                'id':             r.get('id', ''),
                'status':         r.get('status', ''),
                'recovery_amount': float(r.get('recovery_amount', 0) or 0),
                'approved_at':    r.get('approved_at', ''),
                'created_at':     r.get('created_at', ''),
            })
    except Exception:
        pass

    # Promo / active SVRP credits
    promo_credits = []
    try:
        credits_all = read_csv('svrp_credits.csv')
        user_credits = [c for c in credits_all
                        if str(c.get('user_id', '')) == uid
                        and c.get('status') in ('active', 'pending')]
        for c in user_credits[:20]:
            promo_credits.append({
                'type':    c.get('credit_type', ''),
                'amount':  float(c.get('credit_amount', 0) or 0),
                'status':  c.get('status', ''),
                'created': c.get('created_at', ''),
            })
    except Exception:
        pass

    return jsonify({
        'tasks':            tasks,
        'recovery_history': recovery_history,
        'promo_credits':    promo_credits,
    })


@app.route('/api/player/rewards/claim/<task_id>', methods=['POST'])
@account_auth
def api_player_rewards_claim(task_id):
    """Claim a completed SVRP daily task reward."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400

    import sys as _csys; _csys.path.insert(0, BASE_DIR)
    from svrp import SVRPManager as _SMgr
    mgr = _SMgr()
    ok, msg = mgr.claim_task_reward(uid, task_id)
    if not ok:
        return jsonify({'error': msg}), 400

    new_balance = float(_gm.get_svrp_frozen_balance(uid).get('frozen_balance', 0) or 0)
    return jsonify({'success': True, 'message': msg, 'new_svrp_balance': new_balance})

# ===== Aviator engine — separated into dashboard/aviator_engine.py =====
# All Aviator state, game loop, SSE stream, bet/cashout/state routes now live
# in their own module. We register them here with lazy dep getters so module
# load order (provably_fair / _gm are defined later in this file) is safe:
# lambdas resolve at request time, not import time.
try:
    import sys as _eng_sys
    _eng_sys.path.insert(0, os.path.join(BASE_DIR, 'dashboard'))
    from aviator_engine import init_aviator_engine
    init_aviator_engine(
        app,
        get_uid=get_request_uid,
        get_gm=lambda: _gm,
        get_pf=lambda: _pf,
        is_pf=lambda: _PROVABLY_FAIR,
        is_vex=lambda: _VEX_GAMES,
    )
except Exception as _av_init_err:
    print('WARNING: aviator_engine init failed:', _av_init_err)

# ===== Crash engine — separated into dashboard/crash_engine.py =====
try:
    from crash_engine import init_crash_engine  # path already added above
    init_crash_engine(
        app,
        get_uid=get_request_uid,
        get_gm=lambda: _gm,
        get_pf=lambda: _pf,
        is_pf=lambda: _PROVABLY_FAIR,
        is_vex=lambda: _VEX_GAMES,
    )
except Exception as _cr_init_err:
    print('WARNING: crash_engine init failed:', _cr_init_err)

# ===== Dice engine — separated into dashboard/dice_engine.py =====
try:
    from dice_engine import init_dice_engine
    init_dice_engine(
        app,
        get_uid=get_request_uid,
        get_gm=lambda: _gm,
        get_pf=lambda: _pf,
        is_pf=lambda: _PROVABLY_FAIR,
        is_vex=lambda: _VEX_GAMES,
        webapp_auth=webapp_auth,
    )
except Exception as _dice_init_err:
    print('WARNING: dice_engine init failed:', _dice_init_err)

# ===== Provably Fair System =====

try:
    import sys as _sys
    _sys.path.insert(0, BASE_DIR)
    from provably_fair import _pf
    _PROVABLY_FAIR = True
except:
    _PROVABLY_FAIR = False
    _pf = None

@app.route('/api/provably-fair/seed')
@webapp_auth
def api_provably_fair_seed():
    """Get or create provably fair seed hash for a session"""
    if not _PROVABLY_FAIR:
        return jsonify({'error': 'Provably fair not available'}), 500
    session_id = request.args.get('session_id', '')
    client_seed = request.args.get('client_seed', '')
    if not session_id:
        session_id = f"pf_{secrets.token_hex(8)}"
    result = _pf.create_session(session_id, client_seed or None)
    return jsonify({
        'session_id': session_id,
        'seed_hash': result['seed_hash'],
        'client_seed': result['client_seed'],
    })

@app.route('/api/provably-fair/verify', methods=['POST'])
@webapp_auth
def api_provably_fair_verify():
    """Verify a provably fair result"""
    if not _PROVABLY_FAIR:
        return jsonify({'error': 'Provably fair not available'}), 500
    data = request.json
    server_seed = data.get('server_seed', '')
    client_seed = data.get('client_seed', '')
    nonce = int(data.get('nonce', 0))
    max_value = int(data.get('max_value', 10000))
    if not server_seed or not client_seed or nonce <= 0:
        return jsonify({'error': 'Missing params'}), 400
    result = _pf.verify(server_seed, client_seed, nonce, max_value)
    return jsonify(result)

@app.route('/api/provably-fair/reveal/<session_id>')
@webapp_auth
def api_provably_fair_reveal(session_id):
    """Reveal server seed for a completed session"""
    if not _PROVABLY_FAIR:
        return jsonify({'error': 'Provably fair not available'}), 500
    result = _pf.reveal_seed(session_id)
    if not result:
        return jsonify({'error': 'Session not found or already revealed'}), 404
    return jsonify(result)

# ===== Real-time SSE: Leaderboard + Live Players =====

def _get_leaderboard_data(limit=10):
    """Compute top players by profit — uses SQLite if available"""
    # Try SQLite first (much faster)
    try:
        import sys as _sys
        _sys.path.insert(0, BASE_DIR)
        from db_manager import _gdb as _ldb
        return _ldb.get_leaderboard(limit)
    except:
        pass
    # Fallback: CSV
    import os as _os
    sessions_file = _os.path.join(BASE_DIR, 'game_sessions.csv')
    users_file = _os.path.join(BASE_DIR, 'users.csv')
    if not _os.path.exists(sessions_file):
        return []
    profit_map = {}
    try:
        with open(sessions_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                uid = row.get('user_id', '')
                if not uid:
                    continue
                bet = float(row.get('bet_amount', 0) or 0)
                payout = float(row.get('payout', 0) or 0)
                result = row.get('result', '')
                if uid not in profit_map:
                    profit_map[uid] = {'uid': uid, 'name': '', 'total_bet': 0, 'total_payout': 0, 'games': 0, 'wins': 0}
                profit_map[uid]['total_bet'] += bet
                profit_map[uid]['total_payout'] += payout
                profit_map[uid]['games'] += 1
                if result == 'win':
                    profit_map[uid]['wins'] += 1
    except:
        pass
    try:
        with open(users_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                tid = row.get('telegram_id', '')
                if tid in profit_map:
                    profit_map[tid]['name'] = row.get('name', '')
    except:
        pass
    for p in profit_map.values():
        p['profit'] = p['total_payout'] - p['total_bet']
        p['win_rate'] = round(p['wins'] / max(p['games'], 1) * 100, 1)
    sorted_players = sorted(profit_map.values(), key=lambda x: x['profit'], reverse=True)[:limit]
    return sorted_players

def _get_live_players_data(limit=20):
    """Get recent active players from game_sessions.csv"""
    import os as _os
    sessions_file = _os.path.join(BASE_DIR, 'game_sessions.csv')
    users_file = _os.path.join(BASE_DIR, 'users.csv')
    if not _os.path.exists(sessions_file):
        return []
    # Get user names
    user_names = {}
    try:
        with open(users_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                user_names[row.get('telegram_id', '')] = row.get('name', '')
    except:
        pass
    players = []
    try:
        with open(sessions_file, 'r', encoding='utf-8-sig') as f:
            rows = list(csv.DictReader(f))
        for row in rows[-limit:]:
            uid = row.get('user_id', '')
            players.append({
                'uid': uid,
                'name': user_names.get(uid, ''),
                'bet': float(row.get('bet_amount', 0) or 0),
                'status': 'win' if row.get('result') == 'win' else 'lose',
                'payout': float(row.get('payout', 0) or 0),
                'multiplier': float(row.get('multiplier', 0) or 0),
                'game_id': row.get('game_id', ''),
            })
    except:
        pass
    return players

@app.route('/api/games/leaderboard')
@webapp_auth
def api_games_leaderboard():
    """Top 10 players by profit (JSON)"""
    return jsonify({'leaderboard': _get_leaderboard_data(10)})

@app.route('/api/games/leaderboard/stream')
@webapp_auth
def api_games_leaderboard_stream():
    """SSE stream: top 10 players by profit, updated every 5 seconds"""
    def generate():
        import time
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"
        while True:
            try:
                data = _get_leaderboard_data(10)
                payload = json.dumps({'type': 'leaderboard', 'leaderboard': data})
                yield f"data: {payload}\n\n"
            except:
                pass
            time.sleep(5)
    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@app.route('/api/games/live-players/stream')
@webapp_auth
def api_games_live_players_stream():
    """SSE stream: real live players, updated every 3 seconds"""
    def generate():
        import time
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"
        while True:
            try:
                data = _get_live_players_data(20)
                payload = json.dumps({'type': 'live_players', 'players': data, 'count': len(data)})
                yield f"data: {payload}\n\n"
            except:
                pass
            time.sleep(3)
    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

# ===== Health Check =====

@app.route('/health')
def health_check():
    """Lightweight health endpoint for uptime monitors (UptimeRobot, etc.).

    Returns 200 OK when the service is healthy, 503 when the game API is
    locked down due to a missing BOT_TOKEN in production.

    Response body (JSON):
      {
        "status":           "ok" | "locked_down",
        "app_env":          "production" | "development" | ...,
        "bot_token":        "configured" | "missing",
        "game_api":         "enabled" | "disabled",
        "sentinel":         true | false,   // sentinel file present on disk
        "last_lockdown_at": "2026-..." | null,
        "last_recovery_at": "2026-..." | null,
        "timestamp":        "2026-..."
      }
    """
    sentinel_present = os.path.exists(_LOCKDOWN_SENTINEL)
    last_lockdown_at, last_recovery_at = _read_lockdown_log_summary()
    body = {
        'status':           'locked_down' if _WEBAPP_AUTH_LOCKED_DOWN else 'ok',
        'app_env':          _APP_ENV,
        'bot_token':        'missing' if not BOT_TOKEN else 'configured',
        'game_api':         'disabled' if _WEBAPP_AUTH_LOCKED_DOWN else 'enabled',
        'sentinel':         sentinel_present,
        'last_lockdown_at': last_lockdown_at,
        'last_recovery_at': last_recovery_at,
        'timestamp':        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    status_code = 503 if _WEBAPP_AUTH_LOCKED_DOWN else 200
    return jsonify(body), status_code


# ===== Unified game-session & security maintenance daemon =====
# Runs every 5 minutes:
#   1. Refund expired active_game_sessions bets (all games, not just mines)
#      → #26: prevents bets from being locked forever between restarts
#   2. Remove JSON mines entries for any just-refunded sessions
#      → #25: abandoned mines bets are never silently locked
#   3. Prune stale mines JSON files (legacy + new)
#   4. Delete expired auth_nonces from SQLite
#      → #29: replay-protection store stays bounded, survives restarts

def _session_maintenance_daemon():
    """Unified background maintenance: refund expired sessions, prune JSON
    mines state, and clean up auth nonces — every 5 minutes."""
    import time as _time
    while True:
        _time.sleep(300)  # 5-minute interval

        # 1 & 2 — Refund expired SQLite game sessions + clean matching JSON mines entries
        if _VEX_GAMES:
            try:
                refunded = _refund_ags(_db_singleton)
                if refunded:
                    _auth_logger.info("[maintenance] Refunded %d expired session(s): %s",
                                      len(refunded), refunded)
                    # For any refunded mines session, also evict the JSON entry so
                    # the player cannot continue a game whose bet has already been returned.
                    mines_uids = {uid for uid, game, _ in refunded if game == 'mines'}
                    if mines_uids:
                        try:
                            with _mines_lock:
                                sessions = _load_mines_sessions()
                                cleaned = {k: v for k, v in sessions.items()
                                           if k not in mines_uids}
                                if len(cleaned) < len(sessions):
                                    import json as _json
                                    with open(_mines_session_file(), 'w') as _mf:
                                        _json.dump(cleaned, _mf)
                                    _auth_logger.info(
                                        "[maintenance] Evicted %d refunded mines JSON session(s)",
                                        len(sessions) - len(cleaned))
                        except Exception as _me:
                            _auth_logger.error("[maintenance] mines JSON eviction error: %s", _me)
            except Exception as exc:
                _auth_logger.error("[maintenance] refund_expired_game_sessions: %s", exc)

        # 3 — Prune stale mines JSON files
        try:
            with _mines_lock:
                _load_mines_sessions()  # prunes stale entries and persists to disk
        except Exception as exc:
            _auth_logger.error("[maintenance] mines user-sessions prune: %s", exc)
        try:
            _prune_engine_mines_sessions_file()
        except Exception as exc:
            _auth_logger.error("[maintenance] mines engine-sessions prune: %s", exc)

        # 4 — Evict expired auth nonces
        if _VEX_GAMES:
            try:
                n = _cleanup_nonces()
                if n:
                    _auth_logger.debug("[maintenance] Evicted %d expired auth nonce(s)", n)
            except Exception as exc:
                _auth_logger.error("[maintenance] cleanup_expired_nonces: %s", exc)


# Startup prune: clear sessions that expired while the server was down.
try:
    with _mines_lock:
        _load_mines_sessions()
except Exception as _mce:
    _auth_logger.error("mines startup prune (user sessions) error: %s", _mce)
try:
    _prune_engine_mines_sessions_file()
except Exception as _mce2:
    _auth_logger.error("mines startup prune (engine sessions) error: %s", _mce2)

threading.Thread(target=_session_maintenance_daemon, daemon=True, name='session-maintenance').start()


# ===== OTP Bot Auto-Start =====
try:
    import sys as _sys
    _sys.path.insert(0, BASE_DIR)
    from otp_bot import auto_start_otp_bot
    auto_start_otp_bot()
except Exception as _otp_err:
    print('WARNING: OTP bot auto-start failed:', _otp_err)


# ===== Main =====

if __name__ == '__main__':
    print(f"🚀 Boterx Dashboard v2 — http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False, threaded=True)
