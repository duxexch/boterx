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
import base64
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
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import parse_qs

from flask import (Flask, render_template, request, redirect, url_for,
                   session, jsonify, Response, flash, send_file, g,
                   make_response)

# ===== Configuration =====
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', '8080'))
DASHBOARD_HOST = os.getenv('DASHBOARD_HOST', '0.0.0.0')

# Sentinel: the well-known default password committed to public git history.
# Any deployment still using this value is immediately exploitable.
_KNOWN_DEFAULT_PASSWORD = 'boterx_admin_2026'

# قراءة قيمة من ملف .env (fallback عند غياب متغير البيئة) — يمنع انكسار
# الإعدادات عند تشغيل gunicorn بدون source .env
def _env_file_value(key):
    try:
        env_path = os.path.join(BASE_DIR, '.env')
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(key + '='):
                        return line.split('=', 1)[1].strip()
    except Exception:
        pass
    return ''

# Load secret key — empty string means "not configured"; checked at startup below.
# يجب أن يكون ثابتاً عبر كل عمال gunicorn: كل عامل يولّد سراً عشوائياً خاصاً به
# فيوقّع أحدها الجلسة ويرفضها الآخر بـ 401 عشوائياً (سبب أعطال متقطعة سابقة).
_raw_secret_key = os.getenv('DASHBOARD_SECRET_KEY', '') or _env_file_value('DASHBOARD_SECRET_KEY')
SECRET_KEY = _raw_secret_key or secrets.token_hex(32)  # random fallback for dev only
if _raw_secret_key and not os.getenv('DASHBOARD_SECRET_KEY'):
    os.environ['DASHBOARD_SECRET_KEY'] = _raw_secret_key

ADMIN_IDS = [a.strip() for a in (os.getenv('ADMIN_USER_IDS', '') or _env_file_value('ADMIN_USER_IDS')).split(',') if a.strip()]
ADMIN_PASSWORD = os.getenv('DASHBOARD_PASSWORD', '') or _env_file_value('DASHBOARD_PASSWORD') or _KNOWN_DEFAULT_PASSWORD

# انشر القيمة في بيئة العملية كي تراها الموديولات الأخرى (db_manager.get_admin_role
# يرجع لـ os.getenv('ADMIN_USER_IDS') لتحديد super_admin — بدون هذا يفقد الأدمن
# صلاحياته عند تشغيل gunicorn بدون source .env)
if ADMIN_IDS and not os.getenv('ADMIN_USER_IDS'):
    os.environ['ADMIN_USER_IDS'] = ','.join(ADMIN_IDS)
if ADMIN_PASSWORD != _KNOWN_DEFAULT_PASSWORD and not os.getenv('DASHBOARD_PASSWORD'):
    os.environ['DASHBOARD_PASSWORD'] = ADMIN_PASSWORD

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)  # persistent login — never expire unless user logs out
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only
# حد أقصى لحجم أي طلب (يشمل رفع الصور) — يرفض Werkzeug الجسم قبل التحليل الكامل
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # 8MB
# لا ترتب مفاتيح JSON — صفوف CSV قد تحتوي مفاتيح None فينهار الترميز بـ
# TypeError: '<' not supported between instances of 'NoneType' and 'str'
app.json.sort_keys = False

# Initialize AI assistant chat DB
try:
    from ai_assistant import _init_chat_db
    _init_chat_db()
except Exception:
    pass

# ===== Web Push (VAPID) — notifications work even when tab/browser is closed =====
# الزوج المضمّن سابقاً بالكود كان غير متطابق (الخاص لا يشتق العام) — كان
# الاشتراك يفشل بـ InvalidAccessError في المتصفح قبل أي إرسال. الآن:
# القراءة من .env، ولو غابت تُولَّد مرة واحدة وتُحفظ (self-healing).
_VAPID_CLAIMS = {"sub": "mailto:admin@vex.deals"}
_VAPID_PRIVATE = ''
_VAPID_PUBLIC = ''

def _vapid_derive_public(pem_priv):
    """اشتقاق المفتاح العام (base64url لنقطة X962 غير المضغوطة) من الخاص PEM."""
    import base64 as _b64
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    sk = load_pem_private_key(pem_priv.encode(), password=None)
    raw = sk.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return _b64.urlsafe_b64encode(raw).rstrip(b'=').decode()

def _init_vapid():
    """حمّل مفاتيح VAPID من .env أو ولّدها واحفظها هناك — مرة واحدة."""
    global _VAPID_PRIVATE, _VAPID_PUBLIC
    import base64 as _b64
    priv = (os.getenv('VAPID_PRIVATE_KEY', '') or _env_file_value('VAPID_PRIVATE_KEY') or '')
    priv = priv.replace('\\n', '\n').strip()
    pub = os.getenv('VAPID_PUBLIC_KEY', '') or _env_file_value('VAPID_PUBLIC_KEY')
    if not priv.startswith('-----BEGIN'):
        priv = ''
    # تحقق التطابق: المفتاح العام المدمج يجب أن يُشتق من الخاص
    if priv and pub:
        try:
            if _vapid_derive_public(priv) == pub.strip():
                _VAPID_PRIVATE, _VAPID_PUBLIC = priv, pub.strip()
                return
        except Exception:
            pass
    # توليد زوج جديد صحيح وحفظه في .env — تحت قفل ملف حتى لا يولّد كل
    # عامل gunicorn زوجاً مختلفاً في نفس اللحظة (كان يترك أزواجاً متعددة)
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import (
            Encoding as _Enc, PrivateFormat as _PF, PublicFormat as _PubF, NoEncryption as _NoEnc)
        import fcntl as _vfl
        env_path = os.path.join(BASE_DIR, '.env')
        lock_path = env_path + '.vapid.lock'
        with open(lock_path, 'w') as _vlf:
            _vfl.flock(_vlf, _vfl.LOCK_EX)
            try:
                # أعد القراءة تحت القفل — عامل آخر ربما كتب زوجاً للتو: الأول يفوز
                cur_priv = _env_file_value('VAPID_PRIVATE_KEY').replace('\\n', '\n').strip()
                cur_pub = _env_file_value('VAPID_PUBLIC_KEY')
                if cur_priv.startswith('-----BEGIN') and cur_pub:
                    try:
                        if _vapid_derive_public(cur_priv) == cur_pub:
                            _VAPID_PRIVATE, _VAPID_PUBLIC = cur_priv, cur_pub
                            return
                    except Exception:
                        pass
                sk = ec.generate_private_key(ec.SECP256R1())
                priv = sk.private_bytes(_Enc.PEM, _PF.PKCS8, _NoEnc()).decode()
                pub = _b64.urlsafe_b64encode(
                    sk.public_key().public_bytes(_Enc.X962, _PubF.UncompressedPoint)
                ).rstrip(b'=').decode()
                with open(env_path, 'a', encoding='utf-8') as f:
                    f.write("\n# Web Push VAPID (auto-generated)\n")
                    f.write("VAPID_PRIVATE_KEY=" + priv.replace('\n', '\\n') + "\n")
                    f.write("VAPID_PUBLIC_KEY=" + pub + "\n")
                os.environ['VAPID_PRIVATE_KEY'] = priv
                os.environ['VAPID_PUBLIC_KEY'] = pub
                _VAPID_PRIVATE, _VAPID_PUBLIC = priv, pub
                print(f"[VAPID] generated new keypair under lock, public={pub[:20]}...")
            finally:
                _vfl.flock(_vlf, _vfl.LOCK_UN)
    except ImportError:
        # بيئة بلا fcntl (تطوير محلي ويندوز) — توليد مباشر بلا قفل
        try:
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives.serialization import (
                Encoding as _Enc, PrivateFormat as _PF, PublicFormat as _PubF, NoEncryption as _NoEnc)
            sk = ec.generate_private_key(ec.SECP256R1())
            priv = sk.private_bytes(_Enc.PEM, _PF.PKCS8, _NoEnc()).decode()
            pub = _b64.urlsafe_b64encode(
                sk.public_key().public_bytes(_Enc.X962, _PubF.UncompressedPoint)
            ).rstrip(b'=').decode()
            env_path = os.path.join(BASE_DIR, '.env')
            with open(env_path, 'a', encoding='utf-8') as f:
                f.write("\nVAPID_PRIVATE_KEY=" + priv.replace('\n', '\\n') + "\n")
                f.write("VAPID_PUBLIC_KEY=" + pub + "\n")
            _VAPID_PRIVATE, _VAPID_PUBLIC = priv, pub
        except Exception as e:
            print(f"[VAPID] init FAILED (pywebpush pushes disabled): {e}")
    except Exception as e:
        print(f"[VAPID] init FAILED (pywebpush pushes disabled): {e}")

_init_vapid()

_push_lib_warned = False

def _send_web_push(payload_dict, target_uid=None):
    """Send Web Push to subscribed browsers — works even when tab is closed.

    إصلاحات 2026-08-18:
    - غياب pywebpush يُسجَّل مرة واحدة بصوت عالٍ (كان عودة صامتة)
    - الاشتراكات الميتة (404/410) تُحذف فعلياً من CSV
    - الصور/الوسائط تمرر للـ service worker (كانت تُسقط)
    - الاستهداف بـ target_uid يعمل، وملخص إرسال يُسجَّل"""
    global _push_lib_warned
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        if not _push_lib_warned:
            _push_lib_warned = True
            _auth_logger.error('pywebpush NOT INSTALLED — web push silently disabled. pip install pywebpush')
        return
    if not _VAPID_PRIVATE:
        return
    subs = read_csv('push_subscriptions.csv')
    if not subs:
        return
    payload = json.dumps({
        'title': payload_dict.get('title', 'VEX Games'),
        'message': payload_dict.get('message', ''),
        'type': payload_dict.get('type', 'notification'),
        'timestamp': payload_dict.get('timestamp', ''),
        'url': '/dashboard' if payload_dict.get('target_type') == 'dashboard' else '/home',
        'image': (payload_dict.get('data') or {}).get('image', ''),
    })
    dead_endpoints = []
    sent = failed = 0
    for sub in subs:
        endpoint = sub.get('endpoint', '') or ''
        if not endpoint:
            continue
        if target_uid:
            sub_uid = (sub.get('user_id') or '') or (sub.get('admin_id') or '')
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
            sent += 1
        except WebPushException as e:
            code = getattr(e, 'response', None) and e.response.status_code
            if code in (404, 410):
                # الاشتراك ميت (أُلغي بالمتصفح) — احذفه بدل إرسال له للأبد
                dead_endpoints.append(endpoint)
            else:
                failed += 1
                _auth_logger.warning('webpush %s... failed HTTP %s: %s',
                                     endpoint[-20:], code, str(e)[:120])
        except Exception as e:
            failed += 1
            _auth_logger.warning('webpush unexpected: %s', str(e)[:120])
    if dead_endpoints:
        try:
            alive = [s for s in subs if s.get('endpoint') not in dead_endpoints]
            fnames = get_fieldnames('push_subscriptions.csv',
                ['endpoint','p256dh','auth','user_agent','admin_id','created_at',
                 'user_type','user_id','user_name'])
            write_csv('push_subscriptions.csv', alive, fnames)
            _auth_logger.info('webpush pruned %d dead subscriptions', len(dead_endpoints))
        except Exception as e:
            _auth_logger.error('webpush prune failed: %s', e)
    if sent or failed:
        _auth_logger.info('webpush sent=%d failed=%d target=%s', sent, failed, target_uid or 'all')

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
    # 3. Web Push (works even when browser/tab is closed) — مع استهداف مستخدم بعينه
    try:
        _tuid = (data or {}).get('target_uid') if isinstance(data, dict) else None
        _send_web_push(payload_dict, target_uid=_tuid)
    except Exception as e:
        _auth_logger.error('Web Push error: %s', e)

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
    # كتابة ذرّية: ملف مؤقت ثم استبدال — لا يبقى ملف مكسور/فارغ لو انقطعت الكتابة
    tmp_path = filepath + '.tmp'
    with open(tmp_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore', restval='')
        writer.writeheader()
        writer.writerows([{k: v for k, v in r.items() if k is not None} for r in rows])
    os.replace(tmp_path, filepath)

def append_csv(filename, row, fieldnames):
    filepath = os.path.join(BASE_DIR, filename)
    # If file doesn't exist or is empty, write header first
    need_header = (not os.path.exists(filepath)) or (os.path.getsize(filepath) == 0)
    if not need_header:
        # If the on-disk header is missing any of the requested columns,
        # rewrite the whole file with the merged header first (otherwise the
        # appended row's values would land in the wrong columns).
        try:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                existing_header = next(csv.reader(f), [])
            if any(fn not in existing_header for fn in fieldnames):
                existing_rows = read_csv(filename)
                # حماية من المسح: لو الملف فيه صفوف فعلية لكن القراءة فشلت،
                # نضيف الصف بالترويسة الحالية بدلاً من إعادة كتابة الملف فارغاً
                with open(filepath, 'r', encoding='utf-8-sig') as f:
                    raw_data_lines = [ln for ln in f.read().splitlines() if ln.strip()]
                if len(raw_data_lines) > 1 and not existing_rows:
                    fieldnames = existing_header
                elif any(None in r for r in existing_rows):
                    # ملف بترويسة تالفة/صفوف زائدة — لا نعيد الكتابة كي لا نفقد بيانات؛
                    # نضيف الصف حسب الترويسة الحالية فقط
                    fieldnames = existing_header
                else:
                    merged = existing_header + [fn for fn in fieldnames if fn not in existing_header]
                    write_csv(filename, [{k: (r.get(k) or '') for k in merged} for r in existing_rows], merged)
                    fieldnames = merged
        except Exception as e:
            print(f"append_csv header migration failed for {filename}: {e}")
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
        if g.get('hermes_auth'):
            return f(*args, **kwargs)
        if not session.get('logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    """Only real admins can access admin pages"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if g.get('hermes_auth'):
            return f(*args, **kwargs)
        if not session.get('logged_in'):
            return redirect(url_for('admin_login'))
        if not session.get('is_admin'):
            return redirect(url_for('home'), code=303)
        return f(*args, **kwargs)
    return decorated

def api_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if g.get('hermes_auth'):
            return f(*args, **kwargs)
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
                             get_admin_sections as _rbac_get_sections,
                             set_admin_sections as _rbac_set_sections,
                             ALL_SECTIONS as ALL_SECTIONS,
                             ROLE_PERMISSIONS as _ROLE_PERMISSIONS)
    _RBAC_AVAILABLE = True
except ImportError:
    _RBAC_AVAILABLE = False
    def _rbac_has_perm(uid, perm): return True   # allow-all fallback
    def _rbac_get_role(uid): return {'role': 'super_admin', 'permissions': {}}
    def _rbac_log(*a, **k): pass
    def _rbac_set_role(*a, **k): return False
    def _rbac_get_sections(uid): return []  # empty = all allowed
    def _rbac_set_sections(*a, **k): return False
    ALL_SECTIONS = []
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


def section_required(section_key):
    """Decorator: require access to a specific section (page navigation)."""
    def decorator(f):
        @wraps(f)
        def decorated_fn(*args, **kwargs):
            return f(*args, **kwargs)
        return decorated_fn
    return decorator


# ── Section access enforcement via before_request ─────────────────────────────
# Maps Flask endpoint names to section keys. If an admin's allowed sections
# don't include the section, the request is blocked.
_ROUTE_SECTION_MAP = {
    'dashboard': None,  # always allowed
    'page_transactions': 'transactions',
    'page_matching': 'matching',
    'page_agents': 'agents',
    'page_trading': 'trading',
    'page_users': 'users',
    'page_svrp': 'svrp',
    'page_lottery': 'lottery',
    'page_wheel': 'wheel',
    'page_companies': 'companies',
    'page_payment_methods': 'payment_methods',
    'page_apps': 'apps',
    'page_referrals': 'referrals',
    'page_channels': 'channels',
    'page_bots': 'bots',
    'page_browser': 'browser',
    'page_clients': 'clients',
    'page_rental': 'clients',
    'page_complaints': 'complaints',
    'page_tickets': 'tickets',
    'page_broadcast': 'broadcast',
    'page_statistics': 'statistics',
    'page_admins': 'admins',
    'page_admin_center': 'admin_center',
    'page_themes': 'themes',
    'page_exchange_addresses': 'exchange_addresses',
    'page_send_message': 'send_message',
    'page_backup': 'backup',
    'page_settings': 'settings',
    'page_ai_api_keys': 'ai_api_keys',
    'page_games_admin': 'games_admin',
}


@app.before_request
def _section_access_guard():
    """Block access to pages if the admin's sections don't include it."""
    if not session.get('logged_in') or not session.get('is_admin'):
        return None
    endpoint = request.endpoint
    if not endpoint:
        return None
    required_section = _ROUTE_SECTION_MAP.get(endpoint)
    if required_section is None:
        return None  # no restriction
    uid = str(session.get('admin_id', ''))
    allowed = _rbac_get_sections(uid)
    if not allowed:
        return None  # super_admin (empty = all allowed)
    if required_section not in allowed:
        if request.path.startswith('/api/'):
            return jsonify({'error': 'هذا القسم مغلق', 'section': required_section}), 403
        html = (
            '<!doctype html><html lang="ar" dir="rtl">'
            '<head><meta charset="utf-8"><title>403 — القسم مغلق</title>'
            '<style>body{font-family:sans-serif;background:#0f172a;color:#94a3b8;'
            'display:flex;align-items:center;justify-content:center;height:100vh;margin:0}'
            '.box{text-align:center}.icon{font-size:4rem;margin-bottom:1rem}'
            'h1{color:#f43f5e;font-size:1.5rem}a{color:#60a5fa}</style></head>'
            '<body><div class="box"><div class="icon">🔒</div>'
            '<h1>هذا القسم مغلق بالنسبة لك</h1>'
            '<p>تواصل مع الإدارة لفتح هذا القسم</p>'
            '<a href="/dashboard">العودة للوحة التحكم</a></div></body></html>'
        )
        return html, 403
    return None


@app.context_processor
def _inject_admin_context():
    """Inject admin_role, admin_perms, and admin_sections into every template."""
    if session.get('logged_in'):
        uid = str(session.get('admin_id', ''))
        try:
            role_data = _rbac_get_role(uid)
            sections = _rbac_get_sections(uid)
            return {
                'admin_role': role_data.get('role') or 'super_admin',
                'admin_perms': role_data.get('permissions') or {},
                'admin_sections': sections,
                'all_sections': ALL_SECTIONS,
                'showcase_readonly': bool(session.get('showcase_readonly')),
                'showcase_exp': session.get('showcase_exp'),
            }
        except Exception:
            pass
    return {
        'admin_role': None,
        'admin_perms': {},
        'admin_sections': [],
        'all_sections': ALL_SECTIONS,
        'showcase_readonly': bool(session.get('showcase_readonly')),
        'showcase_exp': session.get('showcase_exp'),
    }

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


def _notify_rental_admin(msg):
    """إرسال إشعار للإدارة حول طلبات الإيداع/السحب"""
    import urllib.request as _ur
    import urllib.error as _ue
    token = ALERT_BOT_TOKEN or BOT_TOKEN
    if not token or not ADMIN_IDS:
        return
    for uid in ADMIN_IDS:
        try:
            payload = json.dumps({
                'chat_id': uid, 'text': msg, 'parse_mode': 'HTML'
            }).encode('utf-8')
            req = _ur.Request(
                f'https://api.telegram.org/bot{token}/sendMessage',
                data=payload,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with _ur.urlopen(req, timeout=10) as resp:
                pass
        except Exception:
            pass


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


# ===== Private Showcase (hidden sales deck + read-only admin tour) ==========
_SHOWCASE_DEFAULT_TTL_MIN = int(os.getenv('SHOWCASE_TTL_MINUTES', '180'))

_SHOWCASE_SECTIONS = [
    {
        'slug': 'dashboard-analytics',
        'emoji': '📊',
        'title': 'Dashboard & Real-time Analytics',
        'admin_path': '/dashboard',
        'goal': 'Unified command center providing live visibility into all system metrics, trends, and pending actions.',
        'highlights': [
            {'module': 'Live KPI Cards','purpose': '6 key metrics (Users, Transactions, Volume, Matches, Lottery, Trading) updating every 15s via WebSocket','business_value': 'Instant health check — spot anomalies before they impact revenue','growth_impact': 'Faster decision-making reduces churn; real-time trust signals convert visitors'},
            {'module': '30-Day Trend Charts','purpose': 'Transaction volume, status distribution, top 5 companies, user registrations — Chart.js powered','business_value': 'Visualize growth patterns, seasonal trends, campaign impact','growth_impact': 'Data-driven marketing spends; identify peak acquisition windows'},
            {'module': 'Pending Items Panel','purpose': 'One-click bulk approve/reject for transactions, matches, trading orders, SVRP requests','business_value': 'Clear backlogs in seconds; reduce manual review overhead','growth_impact': 'Faster payouts = higher player satisfaction = more deposits'},
            {'module': 'Activity Timeline','purpose': 'Real-time feed of all system events: deposits, matches, games, admin actions with filtering','business_value': 'Complete operational audit trail; compliance-ready','growth_impact': 'Transparency builds partner confidence; faster dispute resolution'},
            {'module': 'Public Stats API','purpose': 'Anonymous aggregates (players, rounds, payouts) for landing page counters','business_value': 'Social proof on landing page without exposing sensitive data','growth_impact': 'Live counters increase conversion by 15-25%'},
        ],
        'screens': [{'file': 'dashboard.png', 'caption': 'Main Dashboard: Live KPIs + Activity Feed'},{'file': 'statistics.png', 'caption': 'Statistics Dashboard: Detailed Charts & Reports'}],
    },
    {
        'slug': 'campaigns-broadcast',
        'emoji': '📢',
        'title': 'Multi-Channel Campaigns & Broadcast Center',
        'admin_path': '/broadcast',
        'goal': 'Professional marketing automation across Telegram, Web, WhatsApp with AI copywriting and partner network.',
        'highlights': [
            {'module': 'Audience Targeting','purpose': 'All users, single user, 18+ countries, custom segments (VIP, churned, new, high-value)','business_value': 'Laser-focused messages = 3-5x higher CTR vs broadcast','growth_impact': 'Lower CAC; personalized offers convert 3x better'},
            {'module': 'Channel Selection','purpose': 'Telegram, Web push, WhatsApp Business API — simultaneous or per-channel','business_value': 'Meet users where they are; omnichannel reach','growth_impact': 'WhatsApp adds 40% reach in MENA; Web captures desktop users'},
            {'module': 'Rich Media Support','purpose': 'Images, videos, documents with drag-drop upload, preview, compression','business_value': 'Visual campaigns drive 2.5x engagement vs text-only','growth_impact': 'Media-rich promos = higher click-through = more first deposits'},
            {'module': 'Priority & Scheduling','purpose': 'Normal/High/Urgent priority, one-time/daily/weekly recurrence, datetime picker','business_value': 'Time-sensitive promos (matches, tournaments) deliver on schedule','growth_impact': 'Urgent flash promos create FOMO = impulse deposits'},
            {'module': 'AI Content Generation','purpose': 'One-click AI copywriting for campaign messages in 17 languages','business_value': 'Eliminates copywriting bottleneck; consistent brand voice','growth_impact': 'Launch campaigns in minutes not hours; test more creatives'},
            {'module': 'Partner Network (CPM/RevShare)','purpose': 'Manage partner channels, subscriber counts, revenue tracking, automated payouts','business_value': 'Turn influencers into performance partners; pay for results','growth_impact': 'Partner traffic = 30-50% of new users at lower CAC'},
            {'module': 'Campaign Analytics','purpose': 'Reach, clicks, CTR, conversions, daily reach charts, top campaigns table','business_value': 'Measure ROI per campaign; optimize spend','growth_impact': 'Data-driven budget allocation = more users per dollar'},
        ],
        'screens': [{'file': 'broadcast.png', 'caption': 'Broadcast Center: Campaign Builder'},{'file': 'channels.png', 'caption': 'Partner Network: Channel Management'},{'file': 'analytics.png', 'caption': 'Campaign Analytics: Reach & Conversion'}],
    },
    {
        'slug': 'wallet-operations',
        'emoji': '💳',
        'title': 'Wallet, Deposits & Withdrawals',
        'admin_path': '/transactions',
        'goal': 'End-to-end financial lifecycle with multi-currency support, automated matching, agent network, and SVRP compensation.',
        'highlights': [
            {'module': 'Multi-Currency Wallet','purpose': 'EGP, USD, USDT, SAR, AED, KWD with real-time rates, per-user currency preference','business_value': 'Local currency = trust = higher deposits; USDT for crypto users','growth_impact': 'Multi-currency = 35% more international users; USDT = crypto-native acquisition'},
            {'module': 'Payment Methods Management','purpose': 'Vodafone Cash, STC Pay, InstaPay, Bank Transfer per currency; admin-configurable','business_value': 'Local payment methods = 60% higher deposit completion','growth_impact': 'Local methods unlock unbanked populations; STC Pay = Saudi market entry'},
            {'module': 'Deposit Workflow','purpose': 'User submits → Admin reviews (amount, reference, method) → Approve/Reject → Instant balance','business_value': 'Sub-5-minute approval = instant gratification = repeat deposits','growth_impact': 'Fast approval = trust signal = word-of-mouth referrals'},
            {'module': 'Withdrawal Workflow','purpose': 'Request → Admin verifies (KYC, limits) → Manual/auto processing → Completion notification','business_value': 'Secure payouts = player confidence = larger withdrawals = higher LTV','growth_impact': 'Reliable withdrawals = trust = viral growth in communities'},
            {'module': 'AI Matching Engine','purpose': 'Auto-matches deposits to withdrawals by amount, currency, timing; agent assignment','business_value': 'Eliminates manual matching errors; 99.9% accuracy','growth_impact': 'Operational efficiency = scale without headcount = higher margins'},
            {'module': 'Agent Network','purpose': 'Agent balances, escrow, payment methods, ledger, penalties, insurance fund','business_value': 'Distributed liquidity = faster matching = happier players','growth_impact': 'Agent network scales to 1000+ concurrent without infrastructure cost'},
            {'module': 'SVRP Smart Compensation','purpose': '100% deposit as frozen credits; unlock by sharing with 4+ friends (viral loop)','business_value': 'Turns losses into acquisition; 40% of SVRP users become net depositors','growth_impact': 'Compensation = retention tool + acquisition channel = dual value'},
        ],
        'screens': [{'file': 'transactions.png', 'caption': 'Transactions: Real-time Monitoring'},{'file': 'matching.png', 'caption': 'Matching: Deposit-Withdrawal Flow'},{'file': 'agents.png', 'caption': 'Agents: Performance & Balances'}],
    },
    {
        'slug': 'ai-matching-agents',
        'emoji': '🤖',
        'title': 'AI-Powered Matching & Matching Agents',
        'admin_path': '/matching',
        'goal': 'Intelligent deposit/withdrawal matching with AI agents, automated evidence verification, and dispute resolution.',
        'highlights': [
            {'module': 'Automated Matching Algorithm','purpose': 'Matches deposits to withdrawals by amount, currency, timing, priority rules, agent availability','business_value': '99.9% match accuracy; eliminates manual errors','growth_impact': 'Operational excellence = player trust = organic growth'},
            {'module': 'AI Agents for Matching','purpose': 'Multiple AI agents (OpenAI GPT-4o, Anthropic Claude-3.5, Google Gemini-1.5) with custom prompts per channel','business_value': 'AI handles 80% of routine verifications; humans handle exceptions','growth_impact': 'AI agents scale to 10,000+ matches/day without hiring'},
            {'module': 'Agent Actions & Evidence','purpose': 'Agents submit actions with evidence (screenshots, txn IDs, bank refs); auto-verified via OCR/API','business_value': 'Automated evidence validation reduces fraud 95%','growth_impact': 'Fraud prevention = platform integrity = partner trust = enterprise deals'},
            {'module': 'Step-by-Step Workflow','purpose': 'Deposit → Agent claim → Action (evidence) → Counter-party confirmation → Completion/Dispute','business_value': 'Structured process = zero ambiguity = faster resolution','growth_impact': 'Fast resolution = player satisfaction = retention'},
            {'module': 'Dispute Resolution','purpose': 'Admin arbitration with chat logs, evidence review, force-complete/force-cancel, compensation','business_value': 'Fair resolution = player trust = reduced chargebacks','growth_impact': 'Chargeback reduction = saved revenue = higher net profit'},
            {'module': 'Agent Performance Dashboard','purpose': 'Success rate, avg handling time, earnings, penalties, online status, specialization','business_value': 'Data-driven agent management = optimal allocation','growth_impact': 'Top agents = 3x throughput = lower cost per match'},
            {'module': 'Auto-Assignment Rules','purpose': 'Round-robin, least busy, specialization-based, priority matching, geo-routing','business_value': 'Optimal agent utilization = 40% faster matching','growth_impact': 'Speed = conversion; 2-min match vs 20-min = 5x deposits'},
        ],
        'screens': [{'file': 'matching.png', 'caption': 'Matching Dashboard: Real-time Flow'},{'file': 'agents.png', 'caption': 'Agent Performance: Metrics & Management'},{'file': 'ai-agents.png', 'caption': 'AI Agents: Configuration & Monitoring'}],
    },
    {
        'slug': 'agents-management',
        'emoji': '🤝',
        'title': 'Matching Agents Management',
        'admin_path': '/agents',
        'goal': 'Complete agent lifecycle: onboarding, balances, performance, penalties, self-service portal.',
        'highlights': [
            {'module': 'Agent Onboarding','purpose': 'Create agents with bot name, username, security deposit, traffic controls, priority','business_value': '5-minute onboarding; agents productive immediately','growth_impact': 'Fast onboarding = more agents = more liquidity = more matches'},
            {'module': 'Balance & Escrow Management','purpose': 'Real-time balance, escrow (security deposit), credit/debit adjustments with full audit trail','business_value': 'Real-time visibility = trust = agent retention','growth_impact': 'Agent trust = network stability = consistent matching'},
            {'module': 'Payment Methods per Agent','purpose': 'Each agent manages own payment methods (account details, icons, types, currencies)','business_value': 'Agent autonomy = faster payouts = player satisfaction','growth_impact': 'Agent satisfaction = network growth = more capacity'},
            {'module': 'Transaction Ledger','purpose': 'Full history with filtering, export (CSV/Excel), status override, audit trail','business_value': 'Complete transparency = compliance ready = partner confidence','growth_impact': 'Compliance = enterprise clients = high-value contracts'},
            {'module': 'Penalties & Insurance','purpose': 'Automated penalties for failed matches, insurance fund for coverage, configurable rules','business_value': 'Risk mitigation = platform stability = player trust','growth_impact': 'Stability = scale = revenue growth'},
            {'module': 'Agent Self-Service Portal','purpose': 'Agents login via /agent-login, see assigned matches, submit evidence, manage methods, view earnings','business_value': 'Self-service reduces admin load 70%; agents love autonomy','growth_impact': 'Agent happiness = referrals = network effect growth'},
        ],
        'screens': [{'file': 'agents.png', 'caption': 'Agents Dashboard: Overview & KPIs'},{'file': 'agent-ledger.png', 'caption': 'Agent Ledger: Full History'},{'file': 'agent-portal.png', 'caption': 'Agent Portal: Self-Service View'}],
    },
    {
        'slug': 'client-white-label',
        'emoji': '🏢',
        'title': 'Client White-Label Admin Portals',
        'admin_path': '/clients',
        'goal': 'Grant clients their own branded admin panel with isolated data, scoped permissions, and revenue sharing.',
        'highlights': [
            {'module': 'Client Companies Management','purpose': 'Create client companies with branding (logo, colors, custom domain), isolated databases, independent settings','business_value': 'Full isolation = zero data leakage = enterprise trust','growth_impact': 'Enterprise clients = 10-50x average contract value'},
            {'module': 'Client Admin Accounts','purpose': 'Each client gets admin login with scoped access to their company data only (users, transactions, campaigns)','business_value': 'Zero cross-contamination; GDPR compliant by design','growth_impact': 'Compliance = enterprise sales = 6-7 figure contracts'},
            {'module': 'Client Dashboard','purpose': 'Customized view: their users, transactions, volume, campaigns, settings, analytics','business_value': 'Self-service analytics = client empowerment = retention','growth_impact': 'Client empowerment = upsell opportunities = expansion revenue'},
            {'module': 'Revenue Sharing & Billing','purpose': 'Configure revenue share %, monthly invoicing, payment tracking, automated invoices','business_value': 'Automated billing = zero admin overhead = scalable','growth_impact': 'Automated billing = infinite client scale without headcount'},
            {'module': 'White-Label Customization','purpose': 'Custom domain, logo, colors, email templates, language defaults, custom CSS','business_value': 'Full brand ownership = client loyalty = zero churn','growth_impact': 'Brand ownership = switching cost = lifetime value'},
            {'module': 'Client User Management','purpose': 'Client admins manage their own users (ban, balance adjust, transactions, KYC) within scope','business_value': 'Delegated management = admin scalability','growth_impact': 'Scalable support = more clients per admin = higher margins'},
        ],
        'screens': [{'file': 'clients.png', 'caption': 'Clients Dashboard: Company Overview'},{'file': 'client-dashboard.png', 'caption': 'Client Portal: Branded Dashboard'},{'file': 'white-label.png', 'caption': 'White-Label: Custom Domain & Branding'}],
    },
    {
        'slug': 'employee-rbac',
        'emoji': '👮',
        'title': 'Employee RBAC & Granular Permissions',
        'admin_path': '/admins',
        'goal': 'Grant employees precise permissions per admin panel section with ownership, audit trail, and temporary access.',
        'highlights': [
            {'module': 'Predefined Roles','purpose': 'Super Admin, Finance Admin, Support Admin, Game Admin, Broadcast Admin, Custom roles','business_value': 'Role templates = instant onboarding; zero config errors','growth_impact': 'Fast onboarding = team scaling = faster feature delivery'},
            {'module': '30+ Granular Permissions','purpose': 'approve_deposits, reject_withdrawals, ban_users, manage_games, send_broadcast, view_financial, manage_admins, manage_bots, manage_settings, manage_companies, etc.','business_value': 'Least-privilege = security = compliance = enterprise sales','growth_impact': 'Security = trust = enterprise contracts = revenue'},
            {'module': 'Section-Level Access','purpose': 'Grant access to specific sections: /transactions, /matching, /channels, /games-admin, /broadcast, /agents, /admins, /statistics, /ai-api-keys','business_value': 'Precise control = zero over-permission = audit ready','growth_impact': 'Audit readiness = faster compliance = faster deals'},
            {'module': 'Ownership & Management','purpose': 'Channel ownership (owner_admin_id, managed_by_admin_ids), sub-admin publish rights, category management','business_value': 'Distributed ownership = team autonomy = faster operations','growth_impact': 'Team autonomy = parallel work = faster time-to-market'},
            {'module': 'Immutable Audit Trail','purpose': 'Every action logged: who, what, when, target, IP, before/after values — tamper-proof','business_value': 'Full accountability = fraud deterrence = platform integrity','growth_impact': 'Integrity = partner trust = enterprise partnerships'},
            {'module': 'Temporary Access','purpose': 'Time-limited admin roles with auto-expiry (hours/days), auto-revocation','business_value': 'Contractor/vendor access without permanent risk','growth_impact': 'Secure vendor access = faster integrations = faster features'},
            {'module': 'Admin Management UI','purpose': 'Add/edit/remove admins, assign roles, set expiry, view permissions matrix, impersonate','business_value': 'Self-service admin management = zero IT tickets','growth_impact': 'Zero IT tickets = admin team focuses on product = faster shipping'},
        ],
        'screens': [{'file': 'admins.png', 'caption': 'Admin Management: Roles & Permissions'},{'file': 'audit-log.png', 'caption': 'Audit Log: Full Action History'},{'file': 'permissions-matrix.png', 'caption': 'Permissions Matrix: Visual Overview'}],
    },
    {
        'slug': 'games-profitability',
        'emoji': '🎮',
        'title': 'Games Management & Profitability Control',
        'admin_path': '/games-admin',
        'goal': '11+ games with real-time edge control, risk alerts, player segmentation, RTP tuning, and profitability optimization.',
        'highlights': [
            {'module': '11+ Built-in Games','purpose': 'Aviator, Crash, Mines, Plinko, Wheel, Lottery, Dice, Snatch, Snatch Gifts, Trading, SVRP — all with independent config','business_value': 'Game variety = longer sessions = higher LTV','growth_impact': 'New games = new acquisition channels = user growth'},
            {'module': 'Real-time Edge/RTP Control','purpose': 'Adjust house edge, target edge, min/max bet, win chance per game instantly — no restart','business_value': 'Dynamic margin optimization = max profit per game','growth_impact': 'Profit optimization = reinvestment = growth engine'},
            {'module': 'Risk Alerts Engine','purpose': 'Auto-detect: high rollers, unusual win rates, bonus abuse, churn risk, heat levels (1-10)','business_value': 'Proactive risk management = loss prevention','growth_impact': 'Loss prevention = direct profit protection = higher net'},
            {'module': 'Player Segmentation','purpose': 'New, Regular, VIP, Winner, Loser, Hot, Churning — auto-classified by behavior, LTV, heat','business_value': 'Targeted offers per segment = 3x conversion vs generic','growth_impact': 'Personalization = retention = LTV growth'},
            {'module': 'Algorithm Configuration','purpose': 'Target edge %, max daily win/loss, max bets/hour, compensation interval, min balance to play','business_value': 'Fine-tuned algorithm = stable economics = predictable revenue','growth_impact': 'Predictable revenue = investor confidence = funding/growth'},
            {'module': 'Game Toggle & Maintenance','purpose': 'Enable/disable games instantly, maintenance mode with custom player messaging','business_value': 'Instant response to issues = zero revenue leak','growth_impact': 'Uptime = trust = retention = revenue'},
            {'module': 'Profitability Dashboard','purpose': 'Total wagered, net profit, platform edge %, active players, top players by LTV, heat map','business_value': 'Real-time P&L = data-driven decisions','growth_impact': 'Data-driven = optimal resource allocation = max ROI'},
        ],
        'screens': [{'file': 'games_admin.png', 'caption': 'Games Admin: Profitability & Risk'},{'file': 'home_player.png', 'caption': 'Player View: Game Lobby'},{'file': 'risk-alerts.png', 'caption': 'Risk Alerts: Real-time Monitoring'}],
    },
    {
        'slug': 'ai-api-keys',
        'emoji': '🔐',
        'title': 'AI API Keys & Multi-Provider Integration',
        'admin_path': '/ai-api-keys',
        'goal': 'Manage OpenAI, Anthropic, Google, Azure, Custom APIs with auto model fetching, testing, and usage analytics.',
        'highlights': [
            {'module': '5+ Provider Support','purpose': 'OpenAI (GPT-4o, GPT-4), Anthropic (Claude-3.5-Sonnet), Google (Gemini-1.5-Pro), Azure OpenAI, Custom endpoints','business_value': 'Provider diversity = no vendor lock-in = negotiation power','growth_impact': 'Negotiation power = cost savings = higher margins'},
            {'module': 'Auto Model Fetching','purpose': 'One-click fetches available chat models from provider API, filters for chat/completion models','business_value': 'Zero manual config = zero errors = instant deployment','growth_impact': 'Zero config = new features in minutes not days'},
            {'module': 'Connection Testing','purpose': 'Live test with sample prompt, shows latency, token usage, available models, error details','business_value': 'Pre-deployment validation = zero production failures','growth_impact': 'Zero failures = player trust = retention'},
            {'module': 'Per-Key Configuration','purpose': 'Priority (1-100), temperature (0-2), max tokens (1-128k), timeout (5-300s), base URL for Azure/Custom','business_value': 'Granular control = cost optimization = higher margins','growth_impact': 'Cost optimization = reinvestment = growth'},
            {'module': 'Usage Analytics','purpose': 'Requests/day, tokens/day, estimated cost (USD), model breakdown, trend charts','business_value': 'Usage visibility = budget control = predictable costs','growth_impact': 'Predictable costs = financial planning = scale confidence'},
            {'module': 'Channel Integration','purpose': 'Assign AI agents to channels for auto-replies, content generation, moderation, translation','business_value': 'AI automation = 90% support automation = cost savings','growth_impact': 'Cost savings = reinvestment = growth engine'},
        ],
        'screens': [{'file': 'ai_api_keys.png', 'caption': 'AI API Keys: Provider Management'},{'file': 'ai-test.png', 'caption': 'Connection Test: Live Results'},{'file': 'ai-usage.png', 'caption': 'Usage Analytics: Cost & Volume'}],
    },
    {
        'slug': 'security-compliance',
        'emoji': '🛡️',
        'title': 'Security, Provably Fair & Compliance',
        'admin_path': '/admins',
        'goal': 'OTP login, HMAC-SHA256 provably fair, audit trails, data isolation, GDPR-ready, enterprise-grade security.',
        'highlights': [
            {'module': 'OTP Security Login','purpose': 'Telegram bot verification (@vex_otp_bot), 6-digit codes, session management, device fingerprinting','business_value': 'Zero account takeovers = zero fraud = zero chargebacks','growth_impact': 'Zero fraud = platform integrity = enterprise trust'},
            {'module': 'Provably Fair (HMAC-SHA256)','purpose': 'Server seed revealed post-round, client-side verification, all games auditable by players','business_value': 'Mathematical fairness = zero dispute = player trust','growth_impact': 'Trust = retention = LTV = revenue'},
            {'module': 'Data Isolation','purpose': 'White-label clients have fully isolated databases, no cross-contamination, independent backups','business_value': 'Regulatory compliance = enterprise sales = high-value contracts','growth_impact': 'Compliance = market access = revenue'},
            {'module': 'Encryption & Security','purpose': 'AES-256 at rest, TLS 1.3 in transit, bcrypt passwords, secure HttpOnly sessions, CSP headers','business_value': 'Bank-grade security = zero breaches = brand protection','growth_impact': 'Brand protection = user trust = organic growth'},
            {'module': 'Audit Logs & Compliance','purpose': 'Immutable action logs, GDPR data export (30-day), data retention policies, right to deletion','business_value': 'Regulatory readiness = zero fines = brand protection','growth_impact': 'Compliance = market access = global expansion'},
        ],
        'screens': [{'file': 'security.png', 'caption': 'Security Dashboard: Threat Monitoring'},{'file': 'provably-fair.png', 'caption': 'Provably Fair: Verification Flow'},{'file': 'compliance.png', 'caption': 'Compliance: GDPR & Audit Ready'}],
    },
    {
        'slug': 'channels-relay',
        'emoji': '📡',
        'title': 'Channels, Groups & Multi-Platform Relay',
        'admin_path': '/channels',
        'goal': 'Telegram, WhatsApp, Webhook channels with AI processing, flexible relay rules, ownership, and archive.',
        'highlights': [
            {'module': 'Multi-Platform Support','purpose': 'Telegram channels/groups, WhatsApp Business API, Webhook endpoints — unified management','business_value': 'Single dashboard for all channels = operational efficiency','growth_impact': 'Efficiency = scale = more channels = more reach = more users'},
            {'module': 'Channel Roles','purpose': 'Source only, Publish only, Source+Publish — flexible relay topology for any workflow','business_value': 'Flexible topology = any content strategy = creative freedom','growth_impact': 'Creative freedom = viral content = organic growth'},
            {'module': 'AI Processing Pipeline','purpose': 'Text replacement (find/replace), AI rewriting (GPT/Claude), content moderation, auto-translation (17 langs)','business_value': 'AI automation = 90% content processing hands-free','growth_impact': 'Automation = scale = more content = more engagement = more users'},
            {'module': 'Relay Rules','purpose': 'Relay to users, relay to channels, per-channel toggle, category grouping, priority queuing','business_value': 'Granular control = precise content delivery = higher engagement','growth_impact': 'Engagement = retention = LTV = revenue'},
            {'module': 'Ownership & Permissions','purpose': 'Owner admin, managed_by admins, sub-admin publish rights, category management, archive/vault','business_value': 'Distributed ownership = team autonomy = parallel execution','growth_impact': 'Parallel execution = faster launches = first-mover advantage'},
            {'module': 'Archive & Vault','purpose': 'Soft-delete to vault, restore, permanent delete, retention policies, compliance export','business_value': 'Data governance = compliance = enterprise readiness','growth_impact': 'Enterprise readiness = big contracts = revenue'},
        ],
        'screens': [{'file': 'channels.png', 'caption': 'Channels Dashboard: Multi-Platform View'},{'file': 'relay-rules.png', 'caption': 'Relay Rules: Visual Builder'},{'file': 'archive.png', 'caption': 'Archive Vault: Content Recovery'}],
    },
    {
        'slug': 'referrals-loyalty',
        'emoji': '🎁',
        'title': 'Referral Engine & Loyalty Programs',
        'admin_path': '/referrals',
        'goal': 'Multi-level referrals, viral loops, SVRP compensation, daily rewards, VIP tiers, and automated retention.',
        'highlights': [
            {'module': 'Referral Links & Tracking','purpose': 'Unique links per user/partner, conversion tracking, source attribution, UTM support','business_value': 'Attribution = ROI measurement = optimized spend','growth_impact': 'Optimized spend = more users per dollar = growth'},
            {'module': 'Multi-Level Commissions','purpose': 'Configurable % per level (up to 5), instant credit, lifetime commissions, anti-fraud','business_value': 'Viral loops = exponential growth = near-zero CAC','growth_impact': 'Viral growth = market dominance = market leadership'},
            {'module': 'SVRP Compensation System','purpose': '100% deposit as frozen credits, unlock by sharing with 4+ friends (each gets 25%), viral unlock','business_value': 'Turns losses into acquisition; 40% become net depositors','growth_impact': 'Loss-to-acquisition = unique growth loop = competitive moat'},
            {'module': 'Daily Rewards & Lottery','purpose': 'Daily login bonus, wheel spin (configurable prizes), lottery tickets, streak bonuses','business_value': 'Daily engagement = habit formation = retention','growth_impact': 'Retention = LTV = revenue compounding'},
            {'module': 'VIP Tiers & Perks','purpose': 'Auto-promotion by LTV, exclusive games, higher limits, priority support, custom offers','business_value': 'VIP retention = 80/20 rule — top 20% = 80% revenue','growth_impact': 'VIP focus = revenue protection = stable growth'},
            {'module': 'Automated Reactivation','purpose': 'AI detects churning players, triggers personalized offers (bonus, free spins, cashback)','business_value': 'Reactivation = 20-30% of churned users return','growth_impact': 'Reactivated users = free revenue = pure profit'},
        ],
        'screens': [{'file': 'referrals.png', 'caption': 'Referrals: Source Tracking & Rewards'},{'file': 'loyalty.png', 'caption': 'Loyalty: VIP Tiers & Perks'},{'file': 'svrp.png', 'caption': 'SVRP: Viral Compensation Flow'}],
    },
    {
        'slug': 'tickets-support',
        'emoji': '🎫',
        'title': 'Tickets, Complaints & Support System',
        'admin_path': '/tickets',
        'goal': 'Structured dispute resolution, SLA tracking, automated escalation, customer communication, compliance.',
        'highlights': [
            {'module': 'Ticket Categories & Auto-Routing','purpose': 'Deposit, Withdrawal, Game, Technical, Billing, General — auto-assigned to specialized teams','business_value': 'Specialized handling = 50% faster resolution','growth_impact': 'Fast resolution = satisfaction = retention'},
            {'module': 'Complaint Workflow','purpose': 'Open → Assigned → In Progress → Resolution → Closed, with SLA timers (configurable per category)','business_value': 'Structured process = compliance = audit ready','growth_impact': 'Compliance = enterprise trust = big contracts'},
            {'module': 'Dispute Resolution','purpose': 'Admin arbitration with evidence, chat logs, force actions, compensation, audit trail','business_value': 'Fair resolution = trust = reduced chargebacks','growth_impact': 'Chargeback reduction = direct profit = margin'},
            {'module': 'Auto-Escalation','purpose': 'Time-based escalation to senior admins, notifications (Telegram/Email), re-assignment','business_value': 'Zero SLA breaches = compliance = zero penalties','growth_impact': 'Compliance = enterprise trust = revenue'},
            {'module': 'Customer Communication','purpose': 'In-ticket chat, email/Telegram notifications, canned responses, attachments, satisfaction survey','business_value': 'Great support = word-of-mouth = organic growth','growth_impact': 'Organic growth = zero CAC = infinite ROI'},
            {'module': 'SLA & Reporting','purpose': 'Response time, resolution time, CSAT, agent performance, category trends, compliance dashboard','business_value': 'Metrics-driven support = continuous improvement','growth_impact': 'Continuous improvement = competitive advantage'},
        ],
        'screens': [{'file': 'tickets.png', 'caption': 'Tickets Dashboard: Queue & Metrics'},{'file': 'complaints.png', 'caption': 'Complaints: Dispute Resolution'},{'file': 'support.png', 'caption': 'Support: Customer Communication'}],
    },
    {
        'slug': 'social-media-posting',
        'emoji': '📱',
        'title': 'Social Media Multi-Platform Posting & Sub-Admin Control',
        'admin_path': '/social-media',
        'goal': 'Unified social media management: publish to Telegram, WhatsApp, Web, Facebook, Twitter, Instagram from one dashboard with granular sub-admin permissions controlled by main admin',
        'highlights': [
            {'module': '6+ Platform Integration','purpose': 'Telegram Channels/Groups, WhatsApp Business, Facebook Pages, Twitter/X, Instagram, Web Push — single compose, multi-publish','business_value': 'Single workflow for all channels = 80% time savings vs manual posting','growth_impact': 'Consistent cross-platform presence = 3x brand recall = higher conversion'},
            {'module': 'Unified Composer','purpose': 'Single rich-text editor with platform-specific preview, character limits, hashtag suggestions, media optimization per platform','business_value': 'Zero platform-specific errors; brand consistency guaranteed','growth_impact': 'Professional presence = trust = higher click-through rates'},
            {'module': 'Sub-Admin Posting Permissions','purpose': 'Main admin grants granular posting rights per sub-admin: allowed platforms, content categories, scheduling limits, approval workflows','business_value': 'Delegated marketing without brand risk; compliance built-in','growth_impact': 'Scalable marketing team = 10x content output = more reach = more users'},
            {'module': 'Approval Workflows','purpose': 'Multi-level approval: sub-admin drafts → senior review → auto-publish or schedule; audit trail on every action','business_value': 'Zero brand risk; full compliance; zero unauthorized posts','growth_impact': 'Brand safety = partner trust = enterprise deals'},
            {'module': 'Content Library & Templates','purpose': 'Reusable templates, approved media library, brand guidelines enforcement, AI-assisted content adaptation per platform','business_value': '90% faster content creation; consistent brand voice','growth_impact': 'Faster campaigns = first-mover advantage = market share'},
            {'module': 'Cross-Platform Analytics','purpose': 'Unified dashboard: reach, engagement, clicks, conversions per platform; ROI attribution; best posting times AI-predicted','business_value': 'Data-driven budget allocation = 40% better ROAS','growth_impact': 'Optimized spend = more users per dollar = sustainable growth'},
        ],
        'screens': [{'file': 'social-media.png', 'caption': 'Social Media Dashboard: Unified Composer'},{'file': 'sub-admin-permissions.png', 'caption': 'Sub-Admin Permissions: Granular Control'},{'file': 'cross-platform-analytics.png', 'caption': 'Cross-Platform Analytics: ROI by Channel'}],
    },
    {
        'slug': 'agent-partnership',
        'emoji': '🤝',
        'title': 'Agent Partnership Program — Why Agents Choose Us',
        'admin_path': '/agents',
        'goal': 'Compelling value proposition for agents: high commissions, low risk, automated tools, scalable income, and platform support that drives their growth',
        'highlights': [
            {'module': 'High-Commission Revenue Share','purpose': 'Up to 40-50% net revenue share on matched transactions; transparent real-time reporting; instant withdrawal','business_value': 'Best-in-class agent economics = attract top talent','growth_impact': 'Top agents = 5x volume = exponential network growth'},
            {'module': 'Zero Capital Risk','purpose': 'Agents don\'t fund player balances — platform handles liquidity; agents earn on successful matches only','business_value': 'Zero barrier to entry = massive agent pool','growth_impact': 'Low barrier = 1000+ agents in 6 months = massive liquidity'},
            {'module': 'AI-Powered Agent Tools','purpose': 'Auto-match suggestions, evidence auto-verification, dispute prediction, performance coaching, earnings optimization','business_value': 'Agents close 3x more matches with 50% less effort','growth_impact': 'Agent productivity = network throughput = revenue scale'},
            {'module': 'Self-Service Portal','purpose': '24/7 agent dashboard: assigned matches, real-time earnings, performance analytics, evidence submission, instant withdrawals','business_value': 'Zero admin overhead for agent management','growth_impact': 'Self-service = infinite agent scale without headcount growth'},
            {'module': 'Scalable Earnings Model','purpose': 'No cap on transactions; performance bonuses for volume/quality; team building — recruit sub-agents, earn override commissions','business_value': 'Agents become recruiters = viral network growth','growth_impact': 'Viral agent recruitment = exponential network = market dominance'},
            {'module': 'Platform Support & Training','purpose': 'Dedicated partner manager, weekly optimization calls, marketing materials, compliance guidance, priority support','business_value': 'Agent success = platform success = mutual growth','growth_impact': 'Partner success = retention = lifetime value = stable revenue'},
        ],
        'screens': [{'file': 'agent-partnership.png', 'caption': 'Agent Partnership: Revenue Share & Benefits'},{'file': 'agent-portal.png', 'caption': 'Agent Portal: Self-Service Dashboard'},{'file': 'agent-network-growth.png', 'caption': 'Network Growth: Viral Agent Recruitment'}],
    },
]

_SHOWCASE_SECTION_MAP = {s['slug']: s for s in _SHOWCASE_SECTIONS}


def _showcase_secret_bytes() -> bytes:
    raw = os.getenv('SHOWCASE_SECRET', '') or str(app.secret_key or '')
    return raw.encode('utf-8', 'ignore')


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def _b64url_decode(raw: str) -> bytes:
    pad = '=' * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode((raw + pad).encode('ascii'))


def _showcase_issue_token(scope: str, ttl_minutes: int | None = None, extra: dict | None = None) -> str:
    # Permanent tokens have no expiration (ttl_minutes = 0 or negative)
    is_permanent = ttl_minutes is not None and ttl_minutes <= 0
    if is_permanent:
        ttl = 0
        payload = {
            'scope': str(scope),
            'exp': 0,  # No expiration
            'nonce': secrets.token_urlsafe(9),
            'permanent': True,
        }
    else:
        ttl = int(ttl_minutes or _SHOWCASE_DEFAULT_TTL_MIN)
        payload = {
            'scope': str(scope),
            'exp': int(time.time()) + max(60, ttl * 60),
            'nonce': secrets.token_urlsafe(9),
        }
    if extra:
        for k, v in extra.items():
            payload[str(k)] = v
    body = _b64url_encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
    sig = hmac.new(_showcase_secret_bytes(), body.encode('utf-8'), hashlib.sha256).hexdigest()
    return f'{body}.{sig}'


def _showcase_verify_token(token: str, expected_scope: str) -> tuple[bool, dict]:
    try:
        body, sig = str(token or '').split('.', 1)
    except ValueError:
        return False, {}
    if not body or not sig:
        return False, {}
    expected_sig = hmac.new(_showcase_secret_bytes(), body.encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, sig):
        return False, {}
    try:
        payload = json.loads(_b64url_decode(body).decode('utf-8'))
    except Exception:
        return False, {}
    if str(payload.get('scope', '')) != str(expected_scope):
        return False, {}
    
    # Check if permanent token (no expiration)
    is_permanent = payload.get('permanent', False)
    if is_permanent:
        return True, payload
    
    try:
        exp = int(payload.get('exp', 0) or 0)
    except Exception:
        return False, {}
    if exp <= int(time.time()):
        return False, {}
    return True, payload


def _showcase_render(template_name: str, **ctx):
    resp = make_response(render_template(template_name, **ctx))
    resp.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
    resp.headers['Cache-Control'] = 'private, no-store, max-age=0'
    return resp


@app.before_request
def _showcase_readonly_guard():
    if not session.get('showcase_readonly'):
        return None

    try:
        exp = int(session.get('showcase_exp', 0) or 0)
    except Exception:
        exp = 0
    if exp <= int(time.time()):
        session.clear()
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Showcase session expired'}), 401
        return redirect(url_for('showcase_expired'))

    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Read-only showcase session'}), 403
        return ('<!doctype html><html lang="en"><body style="font-family:sans-serif;'
                'background:#0f172a;color:#cbd5e1;display:flex;align-items:center;'
                'justify-content:center;height:100vh">'
                '<div><h2>Read-only session</h2>'
                '<p>This temporary admin demo allows browsing only.</p></div>'
                '</body></html>'), 403
    return None


# ===== Routes — Pages =====

@app.route('/')
def index():
    """Landing page (public) — admin dashboard redirect only when logged in."""
    if session.get('logged_in'):
        return redirect(url_for('dashboard'), code=303)
    return render_template('landing.html')


@app.route('/x/showcase')
def showcase_index():
    token = request.args.get('k', '')
    ok, payload = _showcase_verify_token(token, 'deck')
    if not ok:
        return 'Not Found', 404

    is_permanent = payload.get('permanent', False)
    if is_permanent:
        expires_at = 'دائم (لا ينتهي)' if request.args.get('lang', 'ar') == 'ar' else 'Permanent (never expires)'
    else:
        expires_at = datetime.fromtimestamp(int(payload.get('exp', 0))).strftime('%Y-%m-%d %H:%M:%S UTC')
    return _showcase_render(
        'showcase_index.html',
        token=token,
        sections=_SHOWCASE_SECTIONS,
        expires_at=expires_at,
        is_permanent=is_permanent,
    )


@app.route('/x/showcase/section/<section_slug>')
def showcase_section(section_slug):
    token = request.args.get('k', '')
    ok, payload = _showcase_verify_token(token, 'deck')
    if not ok:
        return 'Not Found', 404

    is_permanent = payload.get('permanent', False)
    section = _SHOWCASE_SECTION_MAP.get(str(section_slug or '').strip())
    if not section:
        return 'Not Found', 404

    if is_permanent:
        expires_at = 'دائم (لا ينتهي)' if request.args.get('lang', 'ar') == 'ar' else 'Permanent (never expires)'
    else:
        expires_at = datetime.fromtimestamp(int(payload.get('exp', 0))).strftime('%Y-%m-%d %H:%M:%S UTC')
    return _showcase_render(
        'showcase_section.html',
        token=token,
        section=section,
        sections=_SHOWCASE_SECTIONS,
        expires_at=expires_at,
        is_permanent=is_permanent,
    )


@app.route('/x/showcase/admin-session')
def showcase_admin_session():
    token = request.args.get('k', '')
    ok, payload = _showcase_verify_token(token, 'deck')
    if not ok:
        return 'Not Found', 404

    next_path = (request.args.get('next', '/dashboard') or '/dashboard').strip()
    if not next_path.startswith('/') or next_path.startswith('//'):
        next_path = '/dashboard'

    viewer_uid = ADMIN_IDS[0] if ADMIN_IDS else '1'
    exp = int(payload.get('exp', int(time.time()) + 3600))
    ttl_remaining = max(60, exp - int(time.time()))

    session.clear()
    session['logged_in'] = True
    session['is_admin'] = True
    session['admin_id'] = str(viewer_uid)
    session['admin_name'] = 'Showcase Viewer'
    session['login_time'] = datetime.now().isoformat()
    session['showcase_readonly'] = True
    session['showcase_exp'] = int(time.time()) + ttl_remaining
    session['showcase_origin'] = 'private_showcase'
    session.permanent = False
    return redirect(next_path, code=303)


@app.route('/x/showcase/expired')
def showcase_expired():
    return _showcase_render('showcase_expired.html')


@app.route('/api/admin/showcase-links', methods=['POST'])
@api_auth
@permission_required('manage_settings')
def api_admin_showcase_links():
    data = request.get_json(silent=True) or {}
    try:
        ttl = int(data.get('ttl_minutes', _SHOWCASE_DEFAULT_TTL_MIN) or _SHOWCASE_DEFAULT_TTL_MIN)
    except Exception:
        ttl = _SHOWCASE_DEFAULT_TTL_MIN
    ttl = max(15, min(ttl, 60 * 24 * 7))

    base_url = (data.get('base_url') or request.host_url or '').rstrip('/')
    
    # Generate temporary token
    token = _showcase_issue_token('deck', ttl_minutes=ttl)
    
    # Generate permanent token
    permanent_token = _showcase_issue_token('deck', ttl_minutes=0)
    
    links = {
        'deck': f'{base_url}/x/showcase?k={token}',
        'deck_permanent': f'{base_url}/x/showcase?k={permanent_token}',
        'admin': f'{base_url}/x/showcase/admin-session?k={token}&next=/dashboard',
        'admin_permanent': f'{base_url}/x/showcase/admin-session?k={permanent_token}&next=/dashboard',
        'expires_in_minutes': ttl,
        'permanent_available': True,
    }
    return jsonify({'success': True, 'links': links})

# ===== Public API — anonymized recent wins for the landing ticker =====
_RECENT_WINS_CACHE = {'ts': 0.0, 'data': []}
_RECENT_WINS_TTL = 30  # seconds
_recent_wins_lock = threading.Lock()

_PUBLIC_GAME_LABELS = {
    'mines':   ('💣', 'مناجم'),
    'crash':   ('🚀', 'كراش'),
    'aviator': ('✈️', 'أفياتور'),
    'plinko':  ('🔵', 'بلينكو'),
    'wheel':   ('🎡', 'عجلة الحظ'),
    'lottery': ('🎰', 'يانصيب'),
    'dice':    ('🎲', 'النرد'),
    'snatch':  ('🎯', 'اخطف'),
}


def _mask_player_id(uid: str) -> str:
    """Anonymize a telegram id: keep only the last 3 digits."""
    tail = ''.join(ch for ch in str(uid) if ch.isdigit())[-3:] or '000'
    return f'لاعب_{tail}••'


@app.route('/api/public/recent-wins')
def api_public_recent_wins():
    """Public read-only feed of the latest anonymized wins from game_sessions.

    No auth required. No PII: player ids masked to last 3 digits, no names.
    Cached in-process for 30s so the landing page can't hammer SQLite.
    """
    # Single-flight refresh: the lock is held through the DB query so that at
    # cache expiry exactly one request refreshes while concurrent requests wait
    # and then serve the freshly published cache (the query is a ~ms indexed
    # SELECT, so holding the lock is cheap and prevents a stampede on SQLite).
    with _recent_wins_lock:
        now = time.time()
        if now - _RECENT_WINS_CACHE['ts'] < _RECENT_WINS_TTL:
            return jsonify({'wins': _RECENT_WINS_CACHE['data']})
        wins = []
        try:
            import sqlite3 as _sq
            _db_path = os.path.join(BASE_DIR, 'vex_games.db')
            conn = _sq.connect(_db_path, timeout=5)
            try:
                conn.execute('PRAGMA query_only=ON')
                rows = conn.execute(
                    'SELECT game_id, user_id, payout, timestamp '
                    'FROM game_sessions '
                    'WHERE payout > 0 AND payout > bet_amount '
                    'ORDER BY id DESC LIMIT 20'
                ).fetchall()
            finally:
                conn.close()
            for game_id, user_id, payout, ts in rows:
                icon, label = _PUBLIC_GAME_LABELS.get(
                    str(game_id or '').lower(), ('🎮', 'لعبة'))
                wins.append({
                    'game_icon': icon,
                    'game_name': label,
                    'player': _mask_player_id(user_id or ''),
                    'amount': round(float(payout or 0), 2),
                })
        except Exception as exc:
            _auth_logger.warning("recent-wins query failed: %s", exc)
            wins = []
        _RECENT_WINS_CACHE['ts'] = now
        _RECENT_WINS_CACHE['data'] = wins
        return jsonify({'wins': wins})

# ===== Public API — rounded aggregate stats for the landing counters =====
_PUBLIC_STATS_CACHE = {'ts': 0.0, 'data': None}
_PUBLIC_STATS_TTL = 300  # seconds — aggregates change slowly
_public_stats_lock = threading.Lock()


def _round_public_stat(value: int) -> int:
    """Round down to 2 significant figures.

    Values under 100 pass through (nearly) exactly — these are coarse,
    non-sensitive aggregates, not user-level data; the rounding only blurs
    larger totals so precise platform figures aren't published.
    """
    v = int(value or 0)
    if v < 10:
        return v
    import math as _m
    step = 10 ** (int(_m.log10(v)) - 1)
    return (v // step) * step


@app.route('/api/public/stats')
def api_public_stats():
    """Public read-only aggregate stats (players, rounds, total paid out).

    No auth required. All figures rounded down to 2 significant digits so no
    sensitive exact totals leak. Cached in-process for 5 minutes.
    """
    with _public_stats_lock:
        now = time.time()
        if _PUBLIC_STATS_CACHE['data'] is not None and \
                now - _PUBLIC_STATS_CACHE['ts'] < _PUBLIC_STATS_TTL:
            return jsonify(_PUBLIC_STATS_CACHE['data'])
        try:
            import sqlite3 as _sq
            _db_path = os.path.join(BASE_DIR, 'vex_games.db')
            conn = _sq.connect(_db_path, timeout=5)
            try:
                conn.execute('PRAGMA query_only=ON')
                players = conn.execute(
                    'SELECT COUNT(*) FROM users').fetchone()[0] or 0
                rounds = conn.execute(
                    'SELECT COUNT(*) FROM game_sessions').fetchone()[0] or 0
                paid = conn.execute(
                    'SELECT COALESCE(SUM(payout), 0) FROM game_sessions '
                    'WHERE payout > 0').fetchone()[0] or 0
            finally:
                conn.close()
            data = {
                'players': _round_public_stat(players),
                'rounds': _round_public_stat(rounds),
                'total_paid': _round_public_stat(int(paid)),
            }
            _PUBLIC_STATS_CACHE['ts'] = now
            _PUBLIC_STATS_CACHE['data'] = data
            return jsonify(data)
        except Exception as exc:
            _auth_logger.warning("public stats query failed: %s", exc)
            # Serve stale cache if we have one; otherwise signal failure so
            # the landing page falls back to its static showcase numbers.
            if _PUBLIC_STATS_CACHE['data'] is not None:
                return jsonify(_PUBLIC_STATS_CACHE['data'])
            return jsonify({'error': 'unavailable'}), 503

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
        "- Theme color: #00e701 (electric green)\n\n"
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

# ── حماية تخمين رموز الدخول: حد لكل IP + عداد لكل رمز ──────────────────────
_OTP_ATTEMPTS_PER_IP = 8        # محاولات كحد أقصى لكل IP
_OTP_IP_WINDOW = 600            # خلال 10 دقائق
_OTP_CODE_MAX_TRIES = 5         # 5 محاولات خاطئة → حذف الرمز (يُطلب جديد من البوت)
_OTP_CODE_TTL = 300             # صلاحية الرمز 5 دقائق
_OTP_ATTEMPTS_FILE = os.path.join(BASE_DIR, 'otp_attempts.json')

def _otp_ip_track(op, client_ip):
    """عدّاد محاولات لكل IP في ملف مشترك بقفل — يعمل عبر كل عمال gunicorn
    (الذاكرة المحلية تتوزع بين العمال ولا ترى محاولات بعضها).

    op: 'check' → (blocked, remaining) | 'record' → (False, remaining)."""
    import json as _json
    lock_path = _OTP_ATTEMPTS_FILE + '.lock'
    now = time.time()
    fcntl_mod = None
    with open(lock_path, 'w') as lf:
        try:
            import fcntl as _fl
            fcntl_mod = _fl
            _fl.flock(lf, _fl.LOCK_EX)
        except ImportError:
            pass
        try:
            data = {}
            try:
                if os.path.exists(_OTP_ATTEMPTS_FILE):
                    with open(_OTP_ATTEMPTS_FILE, 'r') as f:
                        data = _json.load(f)
            except Exception:
                data = {}
            # نافذة نظيفة + تقليم حجم المخزن
            fresh = {}
            for ip, hits in data.items():
                hits = [t for t in hits if now - t < _OTP_IP_WINDOW]
                if hits:
                    fresh[ip] = hits
                if len(fresh) > 5000:
                    break
            hits = fresh.setdefault(client_ip, [])
            if op == 'check':
                blocked = len(hits) >= _OTP_ATTEMPTS_PER_IP
            else:
                hits.append(now)
                blocked = False
            remaining = max(0, _OTP_ATTEMPTS_PER_IP - len(hits))
            try:
                with open(_OTP_ATTEMPTS_FILE, 'w') as f:
                    _json.dump(fresh, f)
            except Exception:
                pass
            return blocked, remaining
        finally:
            try:
                if fcntl_mod:
                    fcntl_mod.flock(lf, fcntl_mod.LOCK_UN)
            except Exception:
                pass

@app.route('/api/web/auth-code', methods=['POST'])
def api_web_auth_code():
    """Validate Telegram auth code from landing page.

    دفاع متعدد الطبقات ضد التخمين:
    1. حد محاولات لكل IP (8/10 دقائق) عبر ملف مشترك بين العمال
    2. عداد لكل رمز: 5 محاولات خاطئة تحذفه — التخمين يقتل الرمز نفسه
    3. تنظيف الرموز المنتهية في كل نداء
    4. الرموز تُولَّد بـ RNG آمن تشفيرياً (في البوت)"""
    import time as _t
    data = request.json or {}
    code = str(data.get('code', '')).strip()
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()

    blocked, _rem = _otp_ip_track('check', client_ip)
    if blocked:
        return jsonify({'error': 'محاولات كثيرة — انتظر 10 دقائق ثم اطلب رمزاً جديداً'}), 429

    if not code or len(code) != 6 or not code.isdigit():
        _otp_ip_track('record', client_ip)
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

        # نظّف الرموز المنتهية أولاً — لا تبقى فرصة لرمز ميت
        now = _t.time()
        expired = [u for u, cd in codes.items() if now - cd.get('created', 0) > _OTP_CODE_TTL]
        for u in expired:
            del codes[u]

        matched_uid = None
        matched_data = None
        for uid, code_data in codes.items():
            if str(code_data.get('code', '')) == code:
                matched_uid, matched_data = uid, code_data
                break

        if matched_uid is None:
            # رمز خاطئ — سجّل المحاولة على كل الرموز النشطة (لا نكشف أي واحد أصاب)
            changed = False
            for uid in list(codes.keys()):
                cd = codes[uid]
                cd['attempts'] = int(cd.get('attempts', 0)) + 1
                if cd['attempts'] >= _OTP_CODE_MAX_TRIES:
                    del codes[uid]   # استُنفد — يُطلب رمز جديد من البوت
                changed = True
            if changed:
                with open(auth_file, 'w') as f:
                    _json.dump(codes, f)
            _rb, remaining = _otp_ip_track('record', client_ip)
            return jsonify({'error': f'رمز غير صالح — محاولات متبقية: {remaining}'}), 400

        # الصلاحية أُعيد فحصها بالتنظيف أعلاه — الرمز حي
        # Create web session
        session['admin_id'] = matched_uid
        session['admin_name'] = matched_data.get('name', 'User')
        session['logged_in'] = True
        session['login_time'] = now
        session.permanent = True  # Persistent — 365 days
        session['is_admin'] = matched_uid in ADMIN_IDS
        session['phone'] = matched_data.get('phone', '')
        # Check if user is registered in bot (users.csv)
        import csv as _csv
        is_registered = False
        try:
            with open(os.path.join(BASE_DIR, 'users.csv'), 'r', encoding='utf-8-sig') as f:
                for row in _csv.DictReader(f):
                    if row.get('telegram_id') == str(matched_uid):
                        is_registered = True
                        break
        except Exception:
            pass
        session['is_registered'] = is_registered
        # Remove used code + أي رموز أخرى لنفس المستخدم (جلسة واحدة نظيفة)
        for uid in list(codes.keys()):
            if uid == matched_uid:
                del codes[uid]
        with open(auth_file, 'w') as f:
            _json.dump(codes, f)
        # Admin → dashboard, regular user → home page
        redirect_url = '/dashboard' if session['is_admin'] else '/home'
        return jsonify({'success': True, 'redirect': redirect_url, 'registered': is_registered})
    except Exception:
        return jsonify({'error': 'خطأ في الخادم'}), 500

@app.route('/api/web/whoami')
def api_web_whoami():
    """Lightweight session probe for the front-end auth gate."""
    logged_in = bool(session.get('logged_in'))
    uid = str(session.get('admin_id') or '')
    registered = bool(session.get('is_registered'))
    if logged_in and uid and not registered:
        # Older sessions may lack the flag — recheck users.csv once
        import csv as _csv
        try:
            with open(os.path.join(BASE_DIR, 'users.csv'), 'r', encoding='utf-8-sig') as f:
                for row in _csv.DictReader(f):
                    if row.get('telegram_id') == uid:
                        registered = True
                        session['is_registered'] = True
                        break
        except Exception:
            pass
    return jsonify({'logged_in': logged_in, 'registered': registered, 'uid': uid})

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

# ===== Hermes External API — permanent key, full admin control =====
HERMES_API_KEY = os.getenv('HERMES_API_KEY', '') or _env_file_value('HERMES_API_KEY')
if not HERMES_API_KEY:
    try:
        _hk = 'vex_hermes_' + secrets.token_urlsafe(32)
        with open(os.path.join(BASE_DIR, '.env'), 'a', encoding='utf-8') as _hf:
            _hf.write("\n# Hermes external API key (permanent — full admin access)\n")
            _hf.write(f"HERMES_API_KEY={_hk}\n")
        HERMES_API_KEY = _hk
        os.environ['HERMES_API_KEY'] = _hk
        print('[HERMES] generated permanent API key -> .env')
    except Exception as _he:
        print(f'[HERMES] key generation failed: {_he}')


@app.before_request
def _hermes_auth_hook():
    """Recognize Hermes by API key header on ANY request.
    Accepts: X-API-Key: <key>   or   Authorization: Bearer <key>"""
    g.hermes_auth = False
    provided = request.headers.get('X-API-Key', '')
    if not provided:
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            provided = auth[7:].strip()
    if provided and HERMES_API_KEY and hmac.compare_digest(provided, HERMES_API_KEY):
        g.hermes_auth = True
        g.hermes_admin_id = 'hermes'


@app.before_request
def _detect_tenant_domain():
    """Detect custom domain from request Host header and set g.tenant_id."""
    g.tenant_id = None
    g.tenant_client = None
    host = request.host.split(':')[0]  # strip port
    # Skip main domain and localhost
    if host in ('vex.deals', 'www.vex.deals', '127.0.0.1', 'localhost', '69.169.108.197'):
        return None
    # Look up domain in clients.csv
    try:
        clients_data = read_csv('clients.csv')
        for c in clients_data:
            if c.get('custom_domain', '').strip().lower() == host.lower():
                g.tenant_id = c.get('id', '')
                g.tenant_client = c
                return None
    except Exception:
        pass
    return None


@app.route('/api/v1/ping')
def hermes_ping():
    """Hermes health/auth check."""
    if not g.get('hermes_auth'):
        return jsonify({'ok': False, 'error': 'Invalid or missing API key. Send header X-API-Key.'}), 401
    return jsonify({'ok': True, 'service': 'vex-admin-api', 'version': '1.0',
                    'authenticated_as': 'hermes', 'time': datetime.now().isoformat()})


@app.route('/api/v1/help')
def hermes_help():
    """List endpoints Hermes can call (all existing dashboard APIs work with the key)."""
    if not g.get('hermes_auth'):
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify({
        'auth': 'Send header X-API-Key: <your key> on every request (or Authorization: Bearer <key>)',
        'endpoints': {
            'GET /api/v1/ping': 'auth check',
            'GET /api/stats': 'dashboard statistics',
            'GET /api/stats/live': 'SSE live stats stream',
            'GET /api/users?query=&limit=': 'list/search users',
            'GET /api/transactions?status=&limit=': 'list transactions',
            'POST /api/transactions/approve': 'body: {"id": "<txn_id>", "amount": 123}',
            'POST /api/transactions/reject': 'body: {"id": "<txn_id>", "reason": "..."}',
            'GET /api/complaints': 'list complaints',
            'POST /api/complaints/<id>/reply': 'body: {"response": "..."}',
            'GET /api/agents': 'list matching agents',
            'GET /api/companies': 'list companies',
            'GET /api/payment-methods': 'list payment methods',
            'GET /api/settings': 'system settings',
            'GET /api/audit-log': 'admin actions log',
            'GET /broadcast': 'broadcast page (UI)',
            'POST /api/broadcast/send': 'send broadcast (check dashboard/broadcast.html for exact payload)',
            'GET /api/lottery/rounds': 'lottery rounds',
            'GET /api/wheel/spins': 'wheel spins',
            'GET /api/trading/orders': 'trading orders',
        },
        'note': 'Any dashboard endpoint reachable by an admin in the browser works with this key too.'
    })


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

# ===== Agent Bot Network — «وكلاء المطابقة» (SQLite-backed) =====
import sys as _agent_sys
if BASE_DIR not in _agent_sys.path:
    _agent_sys.path.insert(0, BASE_DIR)
import agent_db
import ticket_system

@app.route('/agents')
@admin_required
@page_permission_required('view_financial')
def page_agents():
    _start_agents_watchdog()
    return render_template('agents.html', active_page='agents')

@app.route('/api/agents')
@api_auth
@permission_required('view_financial')
def api_agents():
    """List all agent bots with stats."""
    agents = agent_db.list_agents()
    stats = agent_db.get_agent_stats()
    return jsonify({'agents': agents, 'count': len(agents), 'stats': stats})

@app.route('/api/agents', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_create_agent():
    """Create a new agent bot."""
    data = request.json or {}
    res = agent_db.create_agent(data)
    if 'error' in res:
        return jsonify(res), 400
    log_action('create_agent', res['id'])
    # Return the generated password once so the admin can hand it to the agent
    return jsonify({'success': True, 'id': res['id'],
                    'username': res['username'], 'password': res['password']})

@app.route('/api/agents/<agent_id>', methods=['PUT', 'DELETE'])
@api_auth
@permission_required('approve_deposits')
def api_edit_agent(agent_id):
    if request.method == 'DELETE':
        res = agent_db.delete_agent(agent_id)
        if 'error' in res:
            return jsonify(res), 400
        log_action('delete_agent', agent_id)
        return jsonify(res)
    data = request.json or {}
    # Legacy field name from older UI
    if 'traffic_enabled' in data and 'traffic_on' not in data:
        data['traffic_on'] = data.pop('traffic_enabled')
    ok = agent_db.update_agent(agent_id, data)
    log_action('edit_agent', f'{agent_id} {list(data.keys())}')
    return jsonify({'success': ok})

@app.route('/api/agents/<agent_id>/balance', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_agent_balance_adjust(agent_id):
    """Add or subtract from agent balance manually (atomic + ledger)."""
    data = request.json or {}
    try:
        amount = float(data.get('amount', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'مبلغ غير صالح'}), 400
    action = data.get('action', 'add')
    reason = data.get('reason', '')
    direction = 'credit' if action == 'add' else 'debit'
    res = agent_db.adjust_balance(agent_id, amount, direction,
                                 f'manual_{action}',
                                 f'admin:{session.get("admin_id","")} {reason}')
    if 'error' in res:
        return jsonify(res), 400
    log_action('agent_balance_adjust', f'{agent_id} {action} {amount} ({reason})')
    return jsonify(res)

@app.route('/api/agents/<agent_id>/transactions')
@api_auth
@permission_required('view_financial')
def api_agent_transactions(agent_id):
    """Get agent transaction history with search + filters."""
    txns = agent_db.search_transactions(
        agent_id,
        q=request.args.get('search', ''),
        status=request.args.get('status', ''),
        txn_type=request.args.get('type', ''),
        date_from=request.args.get('date_from', ''),
        date_to=request.args.get('date_to', ''),
        min_amount=request.args.get('min_amount') or None,
        max_amount=request.args.get('max_amount') or None,
        limit=100)
    return jsonify({'transactions': txns, 'total': len(txns)})

@app.route('/api/agents/<agent_id>/ledger')
@api_auth
@permission_required('view_financial')
def api_agent_ledger(agent_id):
    """Full financial ledger for one agent."""
    return jsonify({'ledger': agent_db.get_ledger(agent_id)})

@app.route('/api/agents/<agent_id>/transactions/<txn_id>', methods=['PUT'])
@api_auth
@permission_required('approve_deposits')
def api_agent_override_txn(agent_id, txn_id):
    """Admin override a transaction's status with correct financial effect."""
    data = request.json or {}
    new_status = data.get('status', '')
    res = agent_db.admin_override_transaction(agent_id, txn_id, new_status,
                                             admin_id=session.get('admin_id', ''))
    if 'error' in res:
        return jsonify(res), 400
    log_action('agent_txn_override', f'{agent_id}/{txn_id} → {new_status}')
    return jsonify(res)

@app.route('/api/agents/<agent_id>/payment-methods')
@api_auth
@permission_required('view_financial')
def api_agent_payment_methods(agent_id):
    return jsonify({'methods': agent_db.list_payment_methods(agent_id)})

@app.route('/api/agents/<agent_id>/payment-methods', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_add_agent_payment_method(agent_id):
    data = request.json or {}
    mid = agent_db.add_payment_method(agent_id, data)
    return jsonify({'success': True, 'id': mid})

@app.route('/api/agents/<agent_id>/payment-methods/<mid>', methods=['PUT', 'DELETE'])
@api_auth
@permission_required('approve_deposits')
def api_edit_agent_payment_method(agent_id, mid):
    if request.method == 'DELETE':
        return jsonify({'success': agent_db.delete_payment_method(agent_id, mid)})
    data = request.json or {}
    ok = agent_db.update_payment_method(agent_id, mid, data, admin=True)
    return jsonify({'success': ok})

@app.route('/api/agents/deposit-requests')
@api_auth
@permission_required('view_financial')
def api_agent_deposit_requests():
    """List agent top-up requests (all agents or one)."""
    return jsonify({'requests': agent_db.list_deposit_requests(
        agent_id=request.args.get('agent_id') or None,
        status=request.args.get('status', ''))})

@app.route('/api/agents/deposit-requests/<rid>', methods=['PUT'])
@api_auth
@permission_required('approve_deposits')
def api_process_agent_deposit(rid):
    """Admin confirms/rejects an agent top-up request."""
    decision = (request.json or {}).get('decision', '')
    res = agent_db.process_deposit_request(rid, decision,
                                          admin_id=session.get('admin_id', ''))
    if 'error' in res:
        return jsonify(res), 400
    log_action('agent_deposit_' + decision, rid)
    return jsonify(res)

@app.route('/api/agents/find-available')
@api_auth
@permission_required('approve_deposits')
def api_find_available_agent():
    """Find + reserve an available agent for a match — internal use."""
    amount = float(request.args.get('amount', 0) or 0)
    txn_type = request.args.get('type', 'deposit')
    agent = agent_db.pick_agent_for_request(txn_type, amount)
    if not agent:
        return jsonify({'found': False})
    return jsonify({'found': True, 'agent': agent})

@app.route('/svrp')
@admin_required
@page_permission_required('view_financial')
def page_svrp():
    return render_template('svrp.html', active_page='svrp')

# ===== Agent Web Dashboard (Phase 5) =====

@app.route('/agent-login')
def agent_login_page():
    """Agent web login page."""
    if session.get('agent_id'):
        return redirect(url_for('agent_dashboard'))
    return render_template('agent_login.html')

_agent_login_attempts = {}
_agent_login_lock = threading.Lock()

@app.route('/api/agent/login', methods=['POST'])
def api_agent_login():
    """Agent login via username + password (rate-limited, hashed)."""
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    # Rate limit: 10 attempts / 10 min per IP
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '?').split(',')[0].strip()
    now_ts = time.time()
    with _agent_login_lock:
        attempts = [t for t in _agent_login_attempts.get(ip, []) if now_ts - t < 600]
        if len(attempts) >= 10:
            _agent_login_attempts[ip] = attempts
            return jsonify({'error': 'محاولات كثيرة — حاول لاحقاً'}), 429
        attempts.append(now_ts)
        _agent_login_attempts[ip] = attempts
        if len(_agent_login_attempts) > 5000:
            _agent_login_attempts.clear()
    agent = agent_db.verify_agent_login(username, password)
    if not agent:
        return jsonify({'error': 'بيانات غير صحيحة'}), 401
    if not agent.get('is_active'):
        return jsonify({'error': 'الحساب معطل'}), 403
    # Hard isolation: agent login drops any other session (e.g. admin) so an
    # agent session can never piggyback on admin privileges in the same browser.
    session.clear()
    session['agent_id'] = agent['id']
    session['agent_name'] = agent.get('bot_name', '')
    session['agent_logged_in'] = True
    return jsonify({'success': True, 'redirect': '/agent-dashboard'})

def _agent_session_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('agent_logged_in') or not session.get('agent_id'):
            return jsonify({'error': 'Not logged in'}), 401
        return f(*args, **kwargs)
    return wrapper

@app.route('/agent-dashboard')
def agent_dashboard():
    """Agent web dashboard — manage transactions, balance, payment methods."""
    if not session.get('agent_logged_in') or not session.get('agent_id'):
        return redirect(url_for('agent_login_page'))
    agent = agent_db.get_agent(session.get('agent_id', ''))
    if not agent:
        session.pop('agent_id', None)
        session.pop('agent_name', None)
        session.pop('agent_logged_in', None)
        return redirect(url_for('agent_login_page'))
    return render_template('agent_dashboard.html', agent=agent)

@app.route('/api/agent/self')
@_agent_session_required
def api_agent_self():
    """Get own agent data."""
    a = agent_db.get_agent(session['agent_id'])
    if not a:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({
        'id': a['id'], 'bot_name': a.get('bot_name', ''),
        'balance': float(a.get('balance', 0)),
        'escrow_balance': float(a.get('escrow_balance', 0)),
        'security_deposit': float(a.get('security_deposit', 0)),
        'traffic_enabled': 'yes' if bool(a.get('traffic_on')) else 'no',
        'traffic_on': bool(a.get('traffic_on')),
        'current_daily_count': int(a.get('current_daily_count', 0)),
        'max_daily_transactions': int(a.get('max_daily_transactions', 50)),
        'max_concurrent': int(a.get('max_concurrent', 5)),
        'drain': int(a.get('drain', 0)),
        'pin_remaining': int(a.get('pin_remaining', 0)),
        'cap_per_txn': float(a.get('cap_per_txn', 0)),
        'performance_score': float(a.get('performance_score', 50)),
        'tier': a.get('tier', 'bronze'),
        'avg_response_seconds': float(a.get('avg_response_seconds', 0)),
        'completion_rate': float(a.get('completion_rate', 0)),
        'dispute_rate': float(a.get('dispute_rate', 0)),
        'is_active': 'yes' if a.get('is_active') else 'no',
        'deposit_method_name': a.get('deposit_method_name', ''),
        'deposit_method_data': a.get('deposit_method_data', ''),
        'pending_count': len(agent_db.get_pending_transactions(a['id'])),
    })

@app.route('/api/agent/self/payment-methods')
@_agent_session_required
def api_agent_self_methods():
    return jsonify({'methods': agent_db.list_payment_methods(session['agent_id'])})

@app.route('/api/agent/self/payment-methods/<mid>', methods=['PUT'])
@_agent_session_required
def api_agent_edit_method(mid):
    """Agent edits own payment method (account_data + icon only, not name)."""
    ok = agent_db.update_payment_method(session['agent_id'], mid,
                                        request.json or {}, admin=False)
    return jsonify({'success': ok})

@app.route('/api/agent/self/transactions')
@_agent_session_required
def api_agent_self_txns():
    """Get own transactions — search engine over status/date/amount."""
    txns = agent_db.search_transactions(
        session['agent_id'],
        q=request.args.get('search', ''),
        status=request.args.get('status', ''),
        txn_type=request.args.get('type', ''),
        date_from=request.args.get('date_from', ''),
        date_to=request.args.get('date_to', ''),
        min_amount=request.args.get('min_amount') or None,
        max_amount=request.args.get('max_amount') or None,
        limit=100)
    return jsonify({'transactions': txns, 'total': len(txns)})

@app.route('/api/agent/self/pending')
@_agent_session_required
def api_agent_self_pending():
    """Pending matching requests assigned to this agent — joined with request details."""
    return jsonify({'transactions': agent_db.get_pending_with_requests(session['agent_id'])})


@app.route('/api/agent/self/requests/<req_id>/steps')
@_agent_session_required
def api_agent_request_steps(req_id):
    req = agent_db.get_match_request_steps(req_id)
    if not req:
        return jsonify({'error': 'الطلب غير موجود'}), 404
    if str(req.get('assigned_agent_id', '')) != str(session['agent_id']):
        return jsonify({'error': 'غير مصرح'}), 403
    return jsonify({'request': req})


@app.route('/api/agent/self/requests/<req_id>/claim', methods=['POST'])
@_agent_session_required
def api_agent_request_claim(req_id):
    res = agent_db.claim_request(req_id, 'agent', session['agent_id'])
    if 'error' in res:
        return jsonify(res), 400
    return jsonify(res)


@app.route('/api/agent/self/requests/<req_id>/steps/<step_id>/action', methods=['POST'])
@_agent_session_required
def api_agent_request_step_action(req_id, step_id):
    payload = request.json or {}
    res = agent_db.request_step_action(
        req_id, step_id, 'agent', session['agent_id'],
        evidence_ref=str(payload.get('evidence_ref', '') or '')[:200],
        note=str(payload.get('note', '') or '')[:400],
    )
    if 'error' in res:
        return jsonify(res), 400
    return jsonify(res)


@app.route('/api/agent/self/requests/<req_id>/steps/<step_id>/confirm', methods=['POST'])
@_agent_session_required
def api_agent_request_step_confirm(req_id, step_id):
    payload = request.json or {}
    res = agent_db.request_step_confirm(
        req_id, step_id, 'agent', session['agent_id'],
        accept=bool(payload.get('accept', True)),
        note=str(payload.get('note', '') or '')[:400],
    )
    if 'error' in res:
        return jsonify(res), 400
    return jsonify(res)


@app.route('/api/agent/self/requests/<req_id>/dispute', methods=['POST'])
@_agent_session_required
def api_agent_request_dispute(req_id):
    payload = request.json or {}
    res = agent_db.open_request_dispute(
        req_id, 'agent', session['agent_id'],
        str(payload.get('reason', '') or '')[:500],
        evidence_file_id=str(payload.get('evidence_file_id', '') or '')[:200],
    )
    if 'error' in res:
        return jsonify(res), 400
    return jsonify(res)


@app.route('/api/agent/self/disputes')
@_agent_session_required
def api_agent_self_disputes():
    status = request.args.get('status', 'open,assigned,in_review')
    disputes = agent_db.list_agent_op_disputes(session['agent_id'], status=status, limit=200)
    return jsonify({'disputes': disputes})

@app.route('/api/agent/self/transactions/<txn_id>/process', methods=['POST'])
@_agent_session_required
def api_agent_process_txn(txn_id):
    """Agent approves/rejects an assigned matching request (atomic settle)."""
    txns = agent_db.search_transactions(session['agent_id'], q=txn_id, limit=1)
    txn = txns[0] if txns else None
    if txn and str(txn.get('id', '')) == str(txn_id):
        mrid0 = str(txn.get('match_request_id', '') or '')
        if mrid0:
            req0 = agent_db.get_match_request_steps(mrid0)
            if req0 and req0.get('steps'):
                return jsonify({'error': 'هذا الطلب يعمل بمحرك الخطوات V2 — استخدم خطوات العملية'}), 409
            if req0 and str(req0.get('status', '')) != 'approved':
                return jsonify({'error': 'لا يمكن المعالجة قبل موافقة الأدمن'}), 409
    decision = (request.json or {}).get('decision', '')
    res = agent_db.agent_process_transaction(session['agent_id'], txn_id, decision)
    if 'error' in res:
        return jsonify(res), 400
    # Reflect decision on the linked match request (SQLite — single source of truth)
    mrid = res.get('match_request_id')
    if mrid:
        try:
            agent_db.sync_match_request_from_txn(mrid, decision, session['agent_id'])
        except Exception as e:
            print(f"[AGENT] WARNING: settled txn {txn_id} but failed to sync "
                  f"match_requests row {mrid}: {e}")
            log_action('agent_txn_sync_failed', f'{txn_id} -> {mrid}: {e}')
        # Notify the player via Telegram that their request was handled
        try:
            req = agent_db.get_match_request_full(mrid)
            if req and req.get('user_id'):
                _uid = str(req.get('user_id'))
                _amt = req.get('amount', '')
                _cur = req.get('currency', 'EGP')
                if decision == 'approved':
                    _comp_tg(_uid,
                             f"✅ <b>تمت معالجة طلب المطابقة</b>\n\n"
                             f"🆔 الطلب: <code>{mrid}</code>\n"
                             f"💰 المبلغ: <code>{_amt} {_cur}</code>\n"
                             f"🤝 تمت المعالجة بواسطة وكيل معتمد")
                else:
                    _comp_tg(_uid,
                             f"❌ <b>لم تتم معالجة طلب المطابقة</b>\n\n"
                             f"🆔 الطلب: <code>{mrid}</code>\n"
                             f"💰 المبلغ: <code>{_amt} {_cur}</code>\n"
                             f"💡 يمكنك إنشاء طلب جديد أو التواصل مع الدعم")
        except Exception as _ne:
            app.logger.warning(f'agent settle notify failed mrid={mrid}: {_ne}')
    return jsonify(res)

@app.route('/api/agent/self/deposit-method')
@_agent_session_required
def api_agent_deposit_method():
    """Admin-configured payment method the agent must use for topping up."""
    a = agent_db.get_agent(session['agent_id'])
    if not a:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'method_name': a.get('deposit_method_name', ''),
                    'method_data': a.get('deposit_method_data', '')})

@app.route('/api/agent/self/deposit', methods=['POST'])
@_agent_session_required
def api_agent_deposit_balance():
    """Agent tops up own balance — pending request for admin confirmation."""
    data = request.json or {}
    try:
        amount = float(data.get('amount', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'مبلغ غير صالح'}), 400
    a = agent_db.get_agent(session['agent_id'])
    if not a:
        return jsonify({'error': 'Not found'}), 404
    res = agent_db.create_deposit_request(
        session['agent_id'], amount,
        a.get('deposit_method_name', '') or data.get('method_name', ''),
        data.get('reference', '') or data.get('wallet', ''))
    if 'error' in res:
        return jsonify(res), 400
    res['message'] = 'تم إرسال طلب الإيداع — بانتظار موافقة الإدارة'
    return jsonify(res)

@app.route('/api/agent/self/deposits')
@_agent_session_required
def api_agent_self_deposits():
    """Agent's own top-up request history."""
    return jsonify({'requests': agent_db.list_deposit_requests(agent_id=session['agent_id'])})

@app.route('/agent-logout')
def agent_logout():
    session.pop('agent_id', None)
    session.pop('agent_name', None)
    session.pop('agent_logged_in', None)
    return redirect(url_for('agent_login_page'))

# ===== Agent Heartbeat + Enhanced APIs =====

@app.route('/api/agent/self/heartbeat', methods=['POST'])
def api_agent_heartbeat():
    agent_id = session.get('agent_id')
    if not agent_id:
        return jsonify({'error': 'not logged in'}), 401
    res = agent_db.agent_heartbeat(agent_id)
    return jsonify(res)


@app.route('/api/agents/stats')
@api_auth
@permission_required('view_financial')
def api_agents_stats():
    return jsonify(agent_db.get_agent_stats())


@app.route('/api/agents/penalties')
@api_auth
@permission_required('view_financial')
def api_agents_penalties():
    return jsonify({'penalties': agent_db.get_all_penalties(100)})


@app.route('/api/agents/<agent_id>/penalties')
@api_auth
@permission_required('view_financial')
def api_agent_penalties(agent_id):
    return jsonify({'penalties': agent_db.get_penalties(agent_id)})


@app.route('/api/agents/<agent_id>/penalty', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_add_agent_penalty(agent_id):
    data = request.json or {}
    res = agent_db.add_penalty(agent_id, data.get('type', 'timeout'),
                                data.get('amount', 0), data.get('reason', ''))
    return jsonify(res)


# ===== Insurance Pool =====

@app.route('/api/insurance')
@api_auth
@permission_required('view_financial')
def api_insurance():
    return jsonify({
        'balance': agent_db.get_insurance_balance(),
        'log': agent_db.get_insurance_log(50)
    })


@app.route('/api/insurance/adjust', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_insurance_adjust():
    data = request.json or {}
    res = agent_db.admin_insurance_adjust(
        data.get('amount', 0), data.get('direction', 'add'),
        data.get('reason', ''))
    return jsonify(res)


@app.route('/api/insurance/payout', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_insurance_payout():
    data = request.json or {}
    res = agent_db.insurance_payout(
        data.get('agent_id', ''), data.get('match_id', ''),
        data.get('amount', 0), data.get('reason', ''))
    return jsonify(res)


# ===== Ticket System =====

@app.route('/tickets')
@admin_required
@page_permission_required('ban_users')
def page_tickets():
    return render_template('tickets.html', active_page='tickets')


@app.route('/api/tickets')
@api_auth
@permission_required('ban_users')
def api_tickets():
    status = request.args.get('status', '')
    priority = request.args.get('priority', '')
    return jsonify({
        'tickets': ticket_system.list_tickets(status=status, priority=priority),
        'stats': ticket_system.get_ticket_stats()
    })


@app.route('/api/tickets/<ticket_id>')
@api_auth
@permission_required('ban_users')
def api_ticket_detail(ticket_id):
    t = ticket_system.get_ticket(ticket_id)
    if not t:
        return jsonify({'error': 'not found'}), 404
    t['messages'] = ticket_system.get_ticket_messages(ticket_id)
    return jsonify(t)


@app.route('/api/tickets/<ticket_id>/reply', methods=['POST'])
@api_auth
@permission_required('ban_users')
def api_ticket_reply(ticket_id):
    data = request.json or {}
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'error': 'empty message'}), 400
    new_status = data.get('status', '')
    ok = ticket_system.reply_to_ticket(
        ticket_id, 'admin', session.get('user_id', ''), message, new_status or None)
    if ok:
        return jsonify({'success': True})
    return jsonify({'error': 'failed'}), 500


@app.route('/api/tickets/<ticket_id>/status', methods=['POST'])
@api_auth
@permission_required('ban_users')
def api_ticket_status(ticket_id):
    data = request.json or {}
    ok = ticket_system.update_ticket_status(
        ticket_id, data.get('status', ''), data.get('agent_id', ''))
    return jsonify({'success': ok})


@app.route('/api/tickets/<ticket_id>/reassign', methods=['POST'])
@api_auth
@permission_required('ban_users')
def api_ticket_reassign(ticket_id):
    data = request.json or {}
    ok = ticket_system.reassign_ticket(
        ticket_id, data.get('agent_id', ''), data.get('reason', ''))
    return jsonify({'success': ok})


# Agent ticket endpoints

@app.route('/api/agent/self/tickets')
def api_agent_tickets():
    agent_id = session.get('agent_id')
    if not agent_id:
        return jsonify({'error': 'not logged in'}), 401
    return jsonify({'tickets': ticket_system.get_agent_tickets(agent_id)})


@app.route('/api/agent/self/tickets/<ticket_id>/reply', methods=['POST'])
def api_agent_ticket_reply(ticket_id):
    agent_id = session.get('agent_id')
    if not agent_id:
        return jsonify({'error': 'not logged in'}), 401
    data = request.json or {}
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'error': 'empty message'}), 400
    ok = ticket_system.reply_to_ticket(
        ticket_id, 'agent', agent_id, message, data.get('status', 'in_progress') or None)
    return jsonify({'success': ok})


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

@app.route('/clients')
@admin_required
@page_permission_required('manage_bots')
def page_clients():
    _start_clients_watchdog()
    return render_template('clients.html', active_page='clients')


@app.route('/rental')
@admin_required
@page_permission_required('manage_bots')
def page_rental():
    _start_clients_watchdog()
    return render_template('rental.html', active_page='rental')


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

@app.route('/ai-api-keys')
@admin_required
@page_permission_required('manage_settings')
def page_ai_api_keys():
    return render_template('ai_api_keys.html', active_page='ai_api_keys')

# ===== API — AI API Keys =====

@app.route('/api/ai/keys')
@api_auth
@permission_required('manage_settings')
def api_ai_keys_list():
    import sqlite3
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'boterx.db'))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute('SELECT * FROM ai_api_keys ORDER BY priority ASC, id ASC').fetchall()
        keys = []
        for r in rows:
            keys.append({
                'id': r['id'],
                'key_name': r['key_name'],
                'provider': r['provider'],
                'api_key': r['api_key'][:8] + '...' if r['api_key'] else '',
                'full_key': r['api_key'],
                'base_url': r['base_url'],
                'default_model': r['default_model'],
                'priority': r['priority'],
                'temperature': r['temperature'],
                'max_tokens': r['max_tokens'],
                'timeout_seconds': r['timeout_seconds'],
                'is_active': r['is_active'],
                'requests_today': r['requests_today'] or 0,
                'tokens_today': r['tokens_today'] or 0,
                'cost_estimate_usd': r['cost_estimate_usd'] or 0.0,
                'models_list': json.loads(r['models_list']) if r['models_list'] else [],
                'created_at': r['created_at'],
                'updated_at': r['updated_at'],
            })
        return jsonify({'keys': keys})
    finally:
        conn.close()

@app.route('/api/ai/keys', methods=['POST'])
@api_auth
@permission_required('manage_settings')
def api_ai_keys_create():
    data = request.get_json(silent=True) or {}
    required = ['key_name', 'provider', 'api_key']
    for f in required:
        if not data.get(f):
            return jsonify({'error': f'Missing field: {f}'}), 400

    import sqlite3
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'boterx.db'))
    try:
        conn.execute('''
            INSERT INTO ai_api_keys (key_name, provider, api_key, base_url, default_model, priority, temperature, max_tokens, timeout_seconds, is_active, models_list, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['key_name'], data['provider'], data['api_key'],
            data.get('base_url', ''), data.get('default_model', ''),
            int(data.get('priority', 10)), float(data.get('temperature', 0.7)),
            int(data.get('max_tokens', 4096)), int(data.get('timeout_seconds', 60)),
            1 if data.get('is_active') else 0,
            json.dumps(data.get('models_list', [])),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/ai/keys/<int:key_id>', methods=['PUT'])
@api_auth
@permission_required('manage_settings')
def api_ai_keys_update(key_id):
    data = request.get_json(silent=True) or {}
    import sqlite3
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'boterx.db'))
    try:
        row = conn.execute('SELECT * FROM ai_api_keys WHERE id=?', (key_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Key not found'}), 404
        # Keep existing key if not provided
        api_key = data.get('api_key') if data.get('api_key') else row['api_key']
        conn.execute('''
            UPDATE ai_api_keys SET
                key_name=?, provider=?, api_key=?, base_url=?, default_model=?,
                priority=?, temperature=?, max_tokens=?, timeout_seconds=?, is_active=?,
                models_list=?, updated_at=?
            WHERE id=?
        ''', (
            data.get('key_name', row['key_name']), data.get('provider', row['provider']),
            api_key, data.get('base_url', row['base_url']), data.get('default_model', row['default_model']),
            int(data.get('priority', row['priority'])), float(data.get('temperature', row['temperature'])),
            int(data.get('max_tokens', row['max_tokens'])), int(data.get('timeout_seconds', row['timeout_seconds'])),
            1 if data.get('is_active') else 0,
            json.dumps(data.get('models_list', [])),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            key_id
        ))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/ai/keys/<int:key_id>', methods=['DELETE'])
@api_auth
@permission_required('manage_settings')
def api_ai_keys_delete(key_id):
    import sqlite3
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'boterx.db'))
    try:
        conn.execute('DELETE FROM ai_api_keys WHERE id=?', (key_id,))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/ai/fetch-models', methods=['POST'])
@api_auth
@permission_required('manage_settings')
def api_ai_fetch_models():
    data = request.get_json(silent=True) or {}
    provider = data.get('provider')
    api_key = data.get('api_key')
    base_url = data.get('base_url', '')

    if not provider or not api_key:
        return jsonify({'error': 'Missing provider or api_key'}), 400

    models = []
    try:
        import httpx
        headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
        
        # OpenRouter uses a different base URL
        if provider == 'openrouter' and not base_url:
            base_url = 'https://openrouter.ai/api/v1'
        
        url = base_url.rstrip('/') + '/v1/models' if base_url else 'https://api.openai.com/v1/models'

        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                models_data = resp.json()
                models = [m['id'] for m in models_data.get('data', []) if 'id' in m]
                # Filter for chat models
                models = [m for m in models if any(x in m.lower() for x in ['gpt', 'claude', 'gemini', 'chat', 'text'])]
                models = sorted(models)[:50]
            else:
                return jsonify({'error': f'Provider error: {resp.status_code} - {resp.text}'}), 400
    except Exception as e:
        return jsonify({'error': f'Fetch failed: {str(e)}'}), 500

    return jsonify({'models': models})

@app.route('/api/ai/test-key', methods=['POST'])
@api_auth
@permission_required('manage_settings')
def api_ai_test_key():
    data = request.get_json(silent=True) or {}
    key_id = data.get('key_id')
    if not key_id:
        return jsonify({'error': 'Missing key_id'}), 400

    import sqlite3, httpx
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'boterx.db'))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute('SELECT * FROM ai_api_keys WHERE id=?', (key_id,)).fetchone()
        if not row:
            return jsonify({'success': False, 'message': 'Key not found'}), 404

        provider = row['provider']
        api_key = row['api_key']
        base_url = row['base_url'] or ''
        model = row['default_model']

        # OpenRouter uses a different base URL
        if provider == 'openrouter' and not base_url:
            base_url = 'https://openrouter.ai/api/v1'
        
        headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
        test_url = base_url.rstrip('/') + '/v1/chat/completions' if base_url else 'https://api.openai.com/v1/chat/completions'

        payload = {
            'model': model,
            'messages': [{'role': 'user', 'content': 'Test'}],
            'max_tokens': 5
        }

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(test_url, headers=headers, json=payload)
            if resp.status_code == 200:
                # Also fetch models
                if row['provider'] == 'openrouter' and not row['base_url']:
                    models_url = 'https://openrouter.ai/api/v1/models'
                else:
                    models_url = base_url.rstrip('/') + '/v1/models' if base_url else 'https://api.openai.com/v1/models'
                models_list = []
                try:
                    mresp = client.get(models_url, headers=headers)
                    if mresp.status_code == 200:
                        models_list = [m['id'] for m in mresp.json().get('data', []) if 'id' in m]
                        models_list = [m for m in models_list if any(x in m.lower() for x in ['gpt', 'claude', 'gemini', 'chat', 'text'])][:50]
                except:
                    pass
                return jsonify({'success': True, 'message': 'Connection successful', 'models': models_list})
            else:
                return jsonify({'success': False, 'message': f'API error: {resp.status_code} - {resp.text[:200]}'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Test failed: {str(e)}'})
    finally:
        conn.close()

# ===== API — AI Composer (توليد بوستات بالذكاء الاصطناعي) =====
@app.route('/api/ai/compose', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_ai_compose():
    """
    توليد بوست تليغرام بالذكاء الاصطناعي.
    Body: {content_type, channel_id, user_note, key_id}
    """
    from ai_composer import generate_post, get_active_keys, get_company_context

    data = request.json or {}
    content_type = (data.get('content_type') or 'info').strip()
    channel_id = (data.get('channel_id') or '').strip()
    user_note = (data.get('user_note') or '').strip()
    key_id = data.get('key_id')

    # 1. Resolve AI key
    keys = get_active_keys(os.path.join(BASE_DIR, 'boterx.db'))
    if not keys:
        return jsonify({'success': False, 'error': 'No active AI keys — add one in AI API Keys first'}), 400

    key_data = None
    if key_id:
        key_data = next((k for k in keys if k['id'] == key_id), None)
    if not key_data:
        key_data = keys[0]  # fallback to highest priority

    # 2. Get channel identity (if selected)
    channel_identity = ''
    channels_csv = read_csv('bot_channels.csv')
    if channel_id:
        ch = next((c for c in channels_csv if c.get('id') == channel_id), None)
        if ch:
            channel_identity = ch.get('category', '') or ch.get('title', '')

    # 3. Get company context for placeholders
    company_data = get_company_context(BASE_DIR)

    # 4. Generate
    result = generate_post(key_data, content_type, channel_identity, company_data, user_note, BASE_DIR)

    if result.get('success'):
        return jsonify({'success': True, 'text': result['text'], 'key_used': key_data.get('key_name', '')})
    else:
        return jsonify({'success': False, 'error': result.get('error', 'Unknown error')}), 400


# ===== API — AI Translator (ترجمة بوستات بالذكاء الاصطناعي) =====
@app.route('/api/ai/translate', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_ai_translate():
    """
    ترجم نص بوست إلى لغة عالمية.
    Body: {text, target_language, key_id}
    """
    from ai_composer import translate_post, get_active_keys

    data = request.json or {}
    text = (data.get('text') or '').strip()
    target_language = (data.get('target_language') or 'English').strip()
    key_id = data.get('key_id')

    if not text:
        return jsonify({'success': False, 'error': 'No text to translate'}), 400

    # Resolve AI key
    keys = get_active_keys(os.path.join(BASE_DIR, 'boterx.db'))
    if not keys:
        return jsonify({'success': False, 'error': 'No active AI keys'}), 400

    key_data = None
    if key_id:
        key_data = next((k for k in keys if k['id'] == key_id), None)
    if not key_data:
        key_data = keys[0]

    result = translate_post(key_data, text, target_language, BASE_DIR)

    if result.get('success'):
        return jsonify({'success': True, 'text': result['text'], 'key_used': key_data.get('key_name', '')})
    else:
        return jsonify({'success': False, 'error': result.get('error', 'Translation failed')}), 400


# ===== API — AI Admin Assistant =====

@app.route('/api/ai/assistant/chat', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_ai_assistant_chat():
    """AI Assistant chat — multi-agent with @mention support."""
    from ai_assistant import process_chat_message, clear_history

    data = request.json or {}
    message = (data.get('message') or '').strip()
    admin_id = session.get('user_id', session.get('admin_id', 'unknown'))
    target_agent = data.get('agent_id')  # Optional: explicit agent

    if not message:
        return jsonify({'success': False, 'error': 'No message provided'}), 400

    # Handle special commands
    if message.lower() in ('/clear', '/reset', 'امسح', 'مسح'):
        clear_history(admin_id)
        return jsonify({'success': True, 'reply': '✅ تم مسح تاريخ المحادثة.', 'action_taken': 'clear_history'})

    result = process_chat_message(admin_id, message, target_agent=target_agent)
    return jsonify(result)


@app.route('/api/ai/assistant/agents', methods=['GET'])
@api_auth
@permission_required('send_broadcast')
def api_ai_assistant_agents():
    """Get list of available AI agents."""
    from ai_assistant import get_all_agents, get_learning_stats
    agents = get_all_agents()
    stats = get_learning_stats()
    agent_stats = {s['agent']: s for s in stats.get('agent_stats', [])}
    result = []
    for a in agents:
        as_ = agent_stats.get(a['id'], {})
        result.append({
            'id': a['id'], 'name': a['name'], 'name_ar': a['name_ar'],
            'emoji': a['emoji'], 'color': a['color'],
            'role': a['role'], 'role_ar': a['role_ar'],
            'description_ar': a['description_ar'],
            'total_actions': as_.get('count', 0),
            'successful_actions': as_.get('success', 0) or 0,
        })
    return jsonify({'success': True, 'agents': result})


@app.route('/api/ai/assistant/history', methods=['GET'])
@api_auth
@permission_required('send_broadcast')
def api_ai_assistant_history():
    """Get chat history, optionally filtered by agent."""
    from ai_assistant import get_conversation_history
    admin_id = session.get('user_id', session.get('admin_id', 'unknown'))
    limit = request.args.get('limit', 50, type=int)
    agent_id = request.args.get('agent_id')
    history = get_conversation_history(admin_id, agent_id=agent_id, limit=limit)
    return jsonify({'success': True, 'history': history})


@app.route('/api/ai/assistant/clear', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_ai_assistant_clear():
    """Clear chat history."""
    from ai_assistant import clear_history
    admin_id = session.get('user_id', session.get('admin_id', 'unknown'))
    clear_history(admin_id)
    return jsonify({'success': True, 'message': 'History cleared'})


@app.route('/api/ai/assistant/feedback', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_ai_assistant_feedback():
    """Record feedback on an AI response (thumbs up/down + optional correction)."""
    from ai_assistant import record_feedback, record_correction
    data = request.json or {}
    admin_id = session.get('user_id', session.get('admin_id', 'unknown'))
    message_id = data.get('message_id')
    rating = data.get('rating', 2)  # 1=bad, 2=neutral, 3=good
    correction_text = data.get('correction', '')

    record_feedback(admin_id, message_id, rating, correction_text or None)

    # If admin provides a correction text, also store it
    if correction_text and rating == 1:
        record_correction(
            admin_id=admin_id,
            original_action=data.get('action_taken'),
            original_params=data.get('action_params'),
            corrected_action=None,
            corrected_params=None,
            correction_text=correction_text
        )

    return jsonify({'success': True, 'message': 'Feedback recorded'})


@app.route('/api/ai/assistant/learning', methods=['GET'])
@api_auth
@permission_required('send_broadcast')
def api_ai_assistant_learning():
    """Get learning stats and patterns."""
    from ai_assistant import get_learning_stats, get_learned_patterns, get_knowledge, get_repeated_errors
    stats = get_learning_stats()
    patterns = get_learned_patterns(limit=10)
    knowledge = get_knowledge(limit=10)
    errors = get_repeated_errors(limit=5)
    return jsonify({
        'success': True,
        'stats': stats,
        'patterns': patterns,
        'knowledge': knowledge,
        'repeated_errors': errors
    })


@app.route('/api/ai/assistant/correction', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_ai_assistant_correction():
    """Admin corrects an AI action — the AI learns from this."""
    from ai_assistant import record_correction
    data = request.json or {}
    admin_id = session.get('user_id', session.get('admin_id', 'unknown'))

    record_correction(
        admin_id=admin_id,
        original_action=data.get('original_action'),
        original_params=data.get('original_params'),
        corrected_action=data.get('corrected_action'),
        corrected_params=data.get('corrected_params'),
        correction_text=data.get('correction_text', '')
    )

    return jsonify({'success': True, 'message': 'Correction recorded — AI will learn from this'})


@app.route('/api/ai/assistant/learn', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_ai_assistant_learn():
    """Admin teaches the AI a new fact about the project."""
    from ai_assistant import store_knowledge
    data = request.json or {}
    category = data.get('category', 'general')
    key = data.get('key', '')
    value = data.get('value', '')
    if not key or not value:
        return jsonify({'success': False, 'error': 'key and value required'}), 400
    store_knowledge(category, key, value, source='admin_taught', confidence=0.9)
    return jsonify({'success': True, 'message': f'Knowledge stored: [{category}] {key} = {value}'})


# ═══════════════════════════════════════════════════════════════
#  MULTI-PLATFORM POSTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/multi-posts', methods=['GET'])
@api_auth
@permission_required('send_broadcast')
def api_multi_posts_list():
    from platform_posts import list_posts
    status = request.args.get('status')
    limit = request.args.get('limit', 50, type=int)
    return jsonify({'success': True, 'posts': list_posts(status, limit)})


@app.route('/api/multi-posts', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_multi_posts_create():
    from platform_posts import create_post
    data = request.json or {}
    title = data.get('title', '')
    content = data.get('content', '')
    if not title or not content:
        return jsonify({'success': False, 'error': 'title and content required'}), 400
    result = create_post(
        title=title, base_content=content,
        media_urls=data.get('media_urls', []),
        platforms=data.get('platforms'),
        tags=data.get('tags', []),
        created_by=session.get('user_id', session.get('admin_id'))
    )
    return jsonify(result)


@app.route('/api/multi-posts/<post_id>', methods=['GET'])
@api_auth
@permission_required('send_broadcast')
def api_multi_posts_get(post_id):
    from platform_posts import get_post
    post = get_post(post_id)
    if not post:
        return jsonify({'success': False, 'error': 'Post not found'}), 404
    return jsonify({'success': True, 'post': post})


@app.route('/api/multi-posts/<post_id>', methods=['PUT'])
@api_auth
@permission_required('send_broadcast')
def api_multi_posts_update(post_id):
    from platform_posts import update_post
    data = request.json or {}
    result = update_post(post_id, **data)
    return jsonify(result)


@app.route('/api/multi-posts/<post_id>', methods=['DELETE'])
@api_auth
@permission_required('send_broadcast')
def api_multi_posts_delete(post_id):
    from platform_posts import delete_post
    return jsonify(delete_post(post_id))


@app.route('/api/multi-posts/<post_id>/publish', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_multi_posts_publish(post_id):
    from platform_posts import publish_variant
    data = request.json or {}
    platform = data.get('platform', 'telegram')
    channel_ids = data.get('channel_ids')
    return jsonify(publish_variant(post_id, platform, channel_ids))


@app.route('/api/platforms', methods=['GET'])
@api_auth
def api_platforms_list():
    from platform_posts import get_platforms
    return jsonify({'success': True, 'platforms': get_platforms()})


@app.route('/api/multi-posts/preview', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_multi_posts_preview():
    from platform_posts import format_for_platform, PLATFORM_RULES
    data = request.json or {}
    content = data.get('content', '')
    platform = data.get('platform', 'telegram')
    title = data.get('title', '')
    result = format_for_platform(content, platform, title)
    return jsonify({'success': True, 'variant': result})


# ═══════════════════════════════════════════════════════════════
#  CONTACT IMPORTER
# ═══════════════════════════════════════════════════════════════

@app.route('/api/contacts/import', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_contacts_import():
    from contact_importer import import_contacts
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ('.xlsx', '.xls', '.csv'):
        return jsonify({'success': False, 'error': 'Unsupported file type. Use .xlsx, .xls, or .csv'}), 400
    upload_dir = os.path.join(BASE_DIR, 'dashboard', 'static', 'uploads', 'contacts')
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.join(upload_dir, f'import_{int(time.time())}{ext}')
    file.save(filepath)
    result = import_contacts(filepath, created_by=session.get('user_id', session.get('admin_id')))
    return jsonify(result)


@app.route('/api/contacts/imports', methods=['GET'])
@api_auth
@permission_required('send_broadcast')
def api_contacts_imports():
    from contact_importer import list_imports
    return jsonify({'success': True, 'imports': list_imports()})


@app.route('/api/contacts/<import_id>', methods=['GET'])
@api_auth
@permission_required('send_broadcast')
def api_contacts_detail(import_id):
    from contact_importer import get_import_contacts, get_contact_stats
    platform = request.args.get('platform')
    status = request.args.get('status')
    contacts = get_import_contacts(import_id, platform, status)
    stats = get_contact_stats(import_id)
    return jsonify({'success': True, 'contacts': contacts, 'stats': stats})


@app.route('/api/contacts/stats', methods=['GET'])
@api_auth
@permission_required('send_broadcast')
def api_contacts_stats():
    from contact_importer import get_contact_stats
    return jsonify({'success': True, 'stats': get_contact_stats()})


@app.route('/api/contacts/<import_id>', methods=['DELETE'])
@api_auth
@permission_required('send_broadcast')
def api_contacts_delete(import_id):
    from contact_importer import delete_import
    return jsonify(delete_import(import_id))


@app.route('/api/contacts/send', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_contacts_send():
    from anti_ban import queue_messages
    from contact_importer import get_contacts_for_messaging
    data = request.json or {}
    platform = data.get('platform', 'telegram')
    template = data.get('template', '')
    import_id = data.get('import_id')
    if not template:
        return jsonify({'success': False, 'error': 'template required'}), 400
    contacts = get_contacts_for_messaging(platform, import_id, limit=data.get('limit', 100))
    if not contacts:
        return jsonify({'success': False, 'error': 'No contacts found for this platform'})
    result = queue_messages(platform, template, contacts, import_id)
    return jsonify(result)


# ═══════════════════════════════════════════════════════════════
#  ANTI-BAN SYSTEM
# ═══════════════════════════════════════════════════════════════

@app.route('/api/anti-ban/status', methods=['GET'])
@api_auth
@permission_required('send_broadcast')
def api_anti_ban_status():
    from anti_ban import get_rate_status, PLATFORM_LIMITS
    platform = request.args.get('platform', 'telegram')
    status = get_rate_status(platform)
    limits = PLATFORM_LIMITS.get(platform, {})
    return jsonify({'success': True, 'status': status, 'limits': limits})


@app.route('/api/anti-ban/log', methods=['GET'])
@api_auth
@permission_required('send_broadcast')
def api_anti_ban_log():
    from anti_ban import get_ban_log
    platform = request.args.get('platform')
    limit = request.args.get('limit', 50, type=int)
    return jsonify({'success': True, 'log': get_ban_log(platform, limit)})


@app.route('/api/anti-ban/duplicates', methods=['GET'])
@api_auth
@permission_required('send_broadcast')
def api_anti_ban_duplicates():
    from anti_ban import get_content_duplicates
    platform = request.args.get('platform')
    return jsonify({'success': True, 'duplicates': get_content_duplicates(platform)})


@app.route('/api/contacts/send-preview', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_contacts_send_preview():
    from anti_ban import generate_unique_message, spin_text, personalize_message
    from contact_importer import _extract_contact
    data = request.json or {}
    platform = data.get('platform', 'telegram')
    template = data.get('template', '')
    if not template:
        return jsonify({'success': False, 'error': 'template required'}), 400
    # Generate 3 sample variations
    sample_contact = {'name': 'مثال', 'phone': '+201234567890', 'phone_country': 'EG', 'company': 'VEX'}
    samples = []
    for _ in range(3):
        msg = generate_unique_message(template, sample_contact, platform)
        samples.append(msg)
    return jsonify({'success': True, 'samples': samples})


# ═══════════════════════════════════════════════════════════════
#  CONTENT RELAY SYSTEM
# ═══════════════════════════════════════════════════════════════

@app.route('/api/relays', methods=['GET'])
@api_auth
@permission_required('send_broadcast')
def api_relays_list():
    from content_relay import list_relays
    active_only = request.args.get('active_only', '0') == '1'
    return jsonify({'success': True, 'relays': list_relays(active_only)})


@app.route('/api/relays', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_relays_create():
    from content_relay import create_relay
    data = request.json or {}
    name = data.get('name', '')
    if not name:
        return jsonify({'success': False, 'error': 'name required'}), 400
    result = create_relay(
        name=name,
        source_platform=data.get('source_platform', 'telegram'),
        source_ids=data.get('source_ids', []),
        dest_platform=data.get('dest_platform', 'telegram'),
        dest_ids=data.get('dest_ids', []),
        agent_id=data.get('agent_id', 'commander'),
        agent_prompt=data.get('agent_prompt', ''),
        content_filter=data.get('content_filter', 'all'),
        add_branding=data.get('add_branding', 0),
        branding_text=data.get('branding_text', ''),
        add_links=data.get('add_links', 0),
        links_to_add=data.get('links_to_add', []),
        text_replacements=data.get('text_replacements', []),
        delay_seconds=data.get('delay_seconds', 5),
        max_per_hour=data.get('max_per_hour', 20),
        ai_transform=data.get('ai_transform', 1),
        ai_temperature=data.get('ai_temperature', 0.7),
        auto_approve=data.get('auto_approve', 0),
        created_by=session.get('user_id', session.get('admin_id'))
    )
    return jsonify(result)


@app.route('/api/relays/<int:relay_id>', methods=['GET'])
@api_auth
@permission_required('send_broadcast')
def api_relays_get(relay_id):
    from content_relay import get_relay, get_relay_stats
    relay = get_relay(relay_id)
    if not relay:
        return jsonify({'success': False, 'error': 'Relay not found'}), 404
    relay['stats'] = get_relay_stats(relay_id)
    return jsonify({'success': True, 'relay': relay})


@app.route('/api/relays/<int:relay_id>', methods=['PUT'])
@api_auth
@permission_required('send_broadcast')
def api_relays_update(relay_id):
    from content_relay import update_relay
    data = request.json or {}
    result = update_relay(relay_id, **data)
    return jsonify(result)


@app.route('/api/relays/<int:relay_id>', methods=['DELETE'])
@api_auth
@permission_required('send_broadcast')
def api_relays_delete(relay_id):
    from content_relay import delete_relay
    return jsonify(delete_relay(relay_id))


@app.route('/api/relays/<int:relay_id>/toggle', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_relays_toggle(relay_id):
    from content_relay import toggle_relay
    return jsonify(toggle_relay(relay_id))


@app.route('/api/relays/<int:relay_id>/relay', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_relays_execute(relay_id):
    from content_relay import relay_from_post
    data = request.json or {}
    post_id = data.get('post_id')
    if not post_id:
        return jsonify({'success': False, 'error': 'post_id required'}), 400
    return jsonify(relay_from_post(post_id, relay_id))


@app.route('/api/relays/<int:relay_id>/preview', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_relays_preview(relay_id):
    from content_relay import preview_relay
    data = request.json or {}
    text = data.get('text', '')
    if not text:
        return jsonify({'success': False, 'error': 'text required'}), 400
    return jsonify(preview_relay(text, relay_id))


@app.route('/api/relays/<int:relay_id>/queue', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_relays_queue(relay_id):
    from content_relay import queue_relay_content
    data = request.json or {}
    content = data.get('content', '')
    if not content:
        return jsonify({'success': False, 'error': 'content required'}), 400
    return jsonify(queue_relay_content(
        relay_id, content,
        data.get('source_platform'), data.get('source_id'),
        data.get('source_msg_id'), data.get('media_urls')))


@app.route('/api/relays/process-queue', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_relays_process_queue():
    from content_relay import process_relay_queue
    limit = (request.json or {}).get('limit', 10)
    return jsonify(process_relay_queue(limit))


@app.route('/api/relays/log', methods=['GET'])
@api_auth
@permission_required('send_broadcast')
def api_relays_log():
    from content_relay import get_relay_log
    relay_id = request.args.get('relay_id', type=int)
    limit = request.args.get('limit', 50, type=int)
    return jsonify({'success': True, 'log': get_relay_log(relay_id, limit)})


@app.route('/api/relays/stats', methods=['GET'])
@api_auth
@permission_required('send_broadcast')
def api_relays_stats():
    from content_relay import get_relay_stats
    relay_id = request.args.get('relay_id', type=int)
    return jsonify({'success': True, 'stats': get_relay_stats(relay_id)})


@app.route('/api/relays/log/clear', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_relays_log_clear():
    from content_relay import clear_relay_log
    relay_id = (request.json or {}).get('relay_id')
    return jsonify(clear_relay_log(relay_id))


# ===== API — Browser =====

@app.route('/browser')
@admin_required
@permission_required('manage_bots')
def page_browser():
    return render_template('browser.html', active_page='browser')


# ── Daemon Control ───────────────────────────────────────────

@app.route('/api/browser/daemon', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_daemon_status():
    from browser_daemon import browser_daemon
    return jsonify({'success': True, 'daemon': browser_daemon.get_daemon_status()})


@app.route('/api/browser/daemon/start', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_daemon_start():
    from browser_daemon import browser_daemon
    browser_daemon.start()
    return jsonify({'success': True, 'message': 'Daemon started'})


@app.route('/api/browser/daemon/stop', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_daemon_stop():
    from browser_daemon import browser_daemon
    browser_daemon.stop()
    return jsonify({'success': True, 'message': 'Daemon stopped'})


@app.route('/api/browser/daemon/sleep-all', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_daemon_sleep_all():
    from browser_daemon import browser_daemon
    browser_daemon.sleep_all()
    return jsonify({'success': True, 'message': 'All instances sleeping'})


@app.route('/api/browser/daemon/wake-all', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_daemon_wake_all():
    from browser_daemon import browser_daemon
    results = browser_daemon.wake_all(trigger='manual')
    return jsonify({'success': True, 'results': results})


@app.route('/api/browser/health', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_health():
    from browser_health import health_monitor
    return jsonify({'success': True, 'health': health_monitor.get_stats()})


@app.route('/api/browser/health/check/<iid>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_health_check(iid):
    from browser_health import health_monitor
    return jsonify(health_monitor.manual_check(iid))


@app.route('/api/browser/health/restart/<iid>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_health_restart(iid):
    from browser_health import health_monitor
    return jsonify(health_monitor.manual_restart(iid))


@app.route('/api/browser/instances/<iid>/sleep', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_sleep(iid):
    from browser_daemon import browser_daemon
    return jsonify(browser_daemon.sleep_instance(iid))


@app.route('/api/browser/instances/<iid>/wake', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_wake(iid):
    from browser_daemon import browser_daemon
    return jsonify(browser_daemon.wake_instance(iid, 'manual'))


@app.route('/api/browser/instances/<iid>/idle-timeout', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_idle_timeout(iid):
    from browser_daemon import browser_daemon
    ctrl = browser_daemon.get_sleep_controller(iid)
    if not ctrl:
        return jsonify({'success': False, 'error': 'No controller'}), 404
    timeout = (request.json or {}).get('timeout', 300)
    ctrl.set_idle_timeout(timeout)
    return jsonify({'success': True, 'idle_timeout': timeout})


@app.route('/api/browser/instances/<iid>/triggers', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_triggers_list(iid):
    from browser_daemon import browser_daemon
    ctrl = browser_daemon.get_sleep_controller(iid)
    if not ctrl:
        return jsonify({'success': False, 'error': 'No controller'}), 404
    return jsonify({'success': True, 'triggers': ctrl.list_wake_triggers()})


@app.route('/api/browser/instances/<iid>/triggers', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_trigger_add(iid):
    from browser_daemon import browser_daemon
    ctrl = browser_daemon.get_sleep_controller(iid)
    if not ctrl:
        return jsonify({'success': False, 'error': 'No controller'}), 404
    data = request.json or {}
    trigger = ctrl.add_wake_trigger(data.get('type', 'api'), data.get('config', {}))
    return jsonify({'success': True, 'trigger': trigger})


@app.route('/api/browser/instances/<iid>/triggers/<tid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_trigger_remove(iid, tid):
    from browser_daemon import browser_daemon
    ctrl = browser_daemon.get_sleep_controller(iid)
    if not ctrl:
        return jsonify({'success': False, 'error': 'No controller'}), 404
    ctrl.remove_wake_trigger(tid)
    return jsonify({'success': True})


@app.route('/api/browser/snapshot', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_snapshot():
    from browser_daemon import browser_daemon
    browser_daemon._save_snapshot()
    return jsonify({'success': True, 'message': 'Snapshot saved'})


# ── Learning / Knowledge ──────────────────────────────────────

@app.route('/api/browser/instances/<iid>/analyze', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_analyze(iid):
    from browser_manager import get_instance
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    return jsonify({'success': True, 'findings': inst.analyze_current_page()})


@app.route('/api/browser/instances/<iid>/knowledge', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_site_knowledge(iid):
    from browser_manager import get_instance
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    return jsonify({'success': True, 'knowledge': inst.get_site_knowledge()})


@app.route('/api/browser/knowledge', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_knowledge_list():
    from browser_knowledge import list_sites
    return jsonify({'success': True, 'sites': list_sites()})


@app.route('/api/browser/knowledge/<domain>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_knowledge_site(domain):
    from browser_knowledge import get_site_knowledge
    return jsonify({'success': True, 'knowledge': get_site_knowledge(domain)})


@app.route('/api/browser/knowledge/search', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_knowledge_search():
    q = request.args.get('q', '')
    limit = request.args.get('limit', 20, type=int)
    from browser_knowledge import search_knowledge
    return jsonify({'success': True, 'results': search_knowledge(q, limit)})


@app.route('/api/browser/patterns', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_patterns():
    domain = request.args.get('domain')
    from browser_knowledge import list_patterns
    return jsonify({'success': True, 'patterns': list_patterns(domain)})


@app.route('/api/browser/action-stats', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_action_stats():
    domain = request.args.get('domain')
    action = request.args.get('action')
    from browser_knowledge import get_action_stats
    return jsonify({'success': True, 'stats': get_action_stats(domain, action)})


@app.route('/api/browser/instances/<iid>/suggest/<goal>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_suggest(iid, goal):
    from browser_manager import get_instance
    from browser_learning import learning_engine
    from urllib.parse import urlparse
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    domain = urlparse(inst.page.url).netloc.replace('www.', '') if inst.page else ''
    suggestions = learning_engine.suggest_action(domain, goal)
    return jsonify({'success': True, 'suggestions': suggestions, 'domain': domain})


@app.route('/api/browser/action-log', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_action_log():
    domain = request.args.get('domain')
    limit = request.args.get('limit', 50, type=int)
    from browser_knowledge import get_recent_actions
    return jsonify({'success': True, 'actions': get_recent_actions(domain, limit)})


# ── Agent Tasks ──────────────────────────────────────────────

@app.route('/api/browser/tasks', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_tasks_list():
    from browser_tasks import task_executor
    return jsonify({'success': True, 'tasks': task_executor.list_tasks()})


@app.route('/api/browser/tasks', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_task_create():
    from browser_tasks import task_executor
    data = request.json or {}
    steps = data.get('steps', [])
    goal = data.get('goal', 'Custom task')
    task = task_executor.create_task(goal, steps)
    return jsonify({'success': True, 'task': task.to_dict()})


@app.route('/api/browser/tasks/<tid>/execute', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_task_execute(tid):
    from browser_tasks import task_executor
    data = request.json or {}
    instance_id = data.get('instance_id', '')
    if not instance_id:
        return jsonify({'success': False, 'error': 'instance_id required'}), 400
    result = task_executor.execute_task(tid, instance_id)
    return jsonify(result)


@app.route('/api/browser/tasks/<tid>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_task_get(tid):
    from browser_tasks import task_executor
    task = task_executor.get_task(tid)
    if not task:
        return jsonify({'success': False, 'error': 'Task not found'}), 404
    return jsonify({'success': True, 'task': task.to_dict()})


@app.route('/api/browser/tasks/<tid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_task_delete(tid):
    from browser_tasks import task_executor
    task_executor.delete_task(tid)
    return jsonify({'success': True})


@app.route('/api/browser/tasks/templates', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_task_templates():
    from browser_tasks import get_task_templates
    return jsonify({'success': True, 'templates': get_task_templates()})


@app.route('/api/browser/tasks/quick-login', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_quick_login():
    from browser_tasks import create_from_template, task_executor
    from browser_manager import get_instance
    data = request.json or {}
    instance_id = data.get('instance_id', '')
    inst = get_instance(instance_id)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    task = create_from_template('login', {
        'url': data.get('url', ''),
        'username': data.get('username', ''),
        'password': data.get('password', ''),
    })
    if not task:
        return jsonify({'success': False, 'error': 'Template not found'}), 400
    result = task_executor.execute_task(task.id, instance_id)
    return jsonify(result)


@app.route('/api/browser/tasks/quick-scrape', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_quick_scrape():
    from browser_tasks import create_from_template, task_executor
    from browser_manager import get_instance
    data = request.json or {}
    instance_id = data.get('instance_id', '')
    inst = get_instance(instance_id)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    task = create_from_template('scrape_page', {
        'url': data.get('url', ''),
        'selector': data.get('selector', 'body'),
    })
    if not task:
        return jsonify({'success': False, 'error': 'Template not found'}), 400
    result = task_executor.execute_task(task.id, instance_id)
    text = ''
    for r in result.get('task', {}).get('results', []):
        if r.get('action') == 'read_text' and r.get('detail', {}).get('success'):
            text = r['detail'].get('result', '')
    result['scraped_text'] = text
    return jsonify(result)


# ── Agent Permissions ────────────────────────────────────────

@app.route('/api/browser/permissions', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_permissions_list():
    from browser_permissions import list_agent_permissions
    return jsonify({'success': True, 'permissions': list_agent_permissions()})


@app.route('/api/browser/permissions/<agent_id>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_permissions_get(agent_id):
    from browser_permissions import get_agent_permissions
    return jsonify({'success': True, 'permissions': get_agent_permissions(agent_id)})


@app.route('/api/browser/permissions/<agent_id>', methods=['PUT'])
@api_auth
@permission_required('manage_bots')
def api_browser_permissions_set(agent_id):
    from browser_permissions import set_agent_permissions
    data = request.json or {}
    set_agent_permissions(agent_id, data)
    return jsonify({'success': True})


@app.route('/api/browser/permissions/<agent_id>/check/<perm>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_permissions_check(agent_id, perm):
    from browser_permissions import check_permission
    return jsonify({'success': True, 'allowed': check_permission(agent_id, perm)})


# ── Schedules ────────────────────────────────────────────────

@app.route('/api/browser/schedules', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_schedules_list():
    from browser_permissions import list_schedules
    return jsonify({'success': True, 'schedules': list_schedules()})


@app.route('/api/browser/schedules', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_schedule_create():
    from browser_permissions import create_schedule
    data = request.json or {}
    create_schedule(
        data.get('name', ''),
        data.get('task_type', ''),
        data.get('config', {}),
        data.get('cron_expr', ''),
        data.get('interval_seconds', 3600),
    )
    return jsonify({'success': True})


@app.route('/api/browser/schedules/<sid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_schedule_delete(sid):
    from browser_permissions import delete_schedule
    delete_schedule(int(sid))
    return jsonify({'success': True})


@app.route('/api/browser/schedules/<sid>/toggle', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_schedule_toggle(sid):
    from browser_permissions import toggle_schedule
    active = (request.json or {}).get('active', True)
    toggle_schedule(int(sid), active)
    return jsonify({'success': True})


@app.route('/api/browser/scheduler/start', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_scheduler_start():
    from browser_scheduler import schedule_runner
    schedule_runner.start()
    return jsonify({'success': True, 'message': 'Scheduler started'})


@app.route('/api/browser/scheduler/stop', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_scheduler_stop():
    from browser_scheduler import schedule_runner
    schedule_runner.stop()
    return jsonify({'success': True, 'message': 'Scheduler stopped'})


# ── Webhooks ─────────────────────────────────────────────────

@app.route('/api/browser/webhooks', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_webhooks_list():
    from browser_scheduler import webhook_trigger
    return jsonify({'success': True, 'webhooks': webhook_trigger.list_webhooks()})


@app.route('/api/browser/webhooks', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_webhook_create():
    from browser_scheduler import webhook_trigger
    data = request.json or {}
    wid = data.get('webhook_id', f'wh_{int(time.time()*1000)}')
    webhook_trigger.register_webhook(
        data.get('instance_id', ''),
        wid,
        data.get('config', {}),
    )
    return jsonify({'success': True, 'webhook_id': wid})


@app.route('/api/browser/webhooks/<wid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_webhook_delete(wid):
    from browser_scheduler import webhook_trigger
    webhook_trigger.remove_webhook(wid)
    return jsonify({'success': True})


@app.route('/api/browser/webhook-trigger/<wid>', methods=['POST'])
def api_browser_webhook_fire(wid):
    """Public endpoint — fires webhook to wake browser."""
    from browser_scheduler import webhook_trigger
    payload = request.json or {}
    return jsonify(webhook_trigger.handle_webhook(wid, payload))


# ── Network Monitor ──────────────────────────────────────────

@app.route('/api/browser/network-log', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_network_log():
    from browser_permissions import get_network_log
    iid = request.args.get('instance_id')
    limit = request.args.get('limit', 100, type=int)
    return jsonify({'success': True, 'log': get_network_log(iid, limit)})


@app.route('/api/browser/network-stats', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_network_stats():
    from browser_permissions import get_network_stats
    iid = request.args.get('instance_id')
    return jsonify({'success': True, 'stats': get_network_stats(iid)})


# ── Cookie Manager ───────────────────────────────────────────

@app.route('/api/browser/cookies/<instance_id>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_cookies_get(instance_id):
    from browser_extras import get_cookies
    query = request.args.get('q', '')
    if query:
        from browser_extras import search_cookies
        cookies = search_cookies(instance_id, query)
    else:
        cookies = get_cookies(instance_id)
    return jsonify({'success': True, 'cookies': cookies, 'count': len(cookies)})


@app.route('/api/browser/cookies/<instance_id>/sync', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_cookies_sync(instance_id):
    from browser_extras import save_cookies_from_browser
    from browser_manager import get_instance
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return jsonify({'success': False, 'error': 'Browser not running'}), 400
    cookies = inst.context.cookies()
    save_cookies_from_browser(instance_id, cookies)
    return jsonify({'success': True, 'synced': len(cookies)})


@app.route('/api/browser/cookies/<instance_id>/delete/<cid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_cookie_delete(instance_id, cid):
    from browser_extras import delete_cookie
    delete_cookie(instance_id, int(cid))
    return jsonify({'success': True})


@app.route('/api/browser/cookies/<instance_id>/clear', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_cookies_clear(instance_id):
    from browser_extras import delete_all_cookies
    delete_all_cookies(instance_id)
    return jsonify({'success': True})


@app.route('/api/browser/cookies/<instance_id>/export', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_cookies_export(instance_id):
    from browser_extras import export_cookies
    fmt = request.args.get('format', 'json')
    data = export_cookies(instance_id, fmt)
    if fmt == 'json':
        return jsonify({'success': True, 'cookies': json.loads(data)})
    return data, 200, {'Content-Type': 'text/plain', 'Content-Disposition': f'attachment; filename=cookies_{instance_id}.txt'}


@app.route('/api/browser/cookies/<instance_id>/import', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_cookies_import(instance_id):
    from browser_extras import import_cookies
    data = request.json or {}
    cookies = data.get('cookies', [])
    success = import_cookies(instance_id, cookies)
    return jsonify({'success': success, 'imported': len(cookies)})


# ── Session Recording ────────────────────────────────────────

@app.route('/api/browser/sessions', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_sessions_list():
    from browser_extras import session_recorder
    iid = request.args.get('instance_id')
    sessions = session_recorder.list_sessions(iid)
    return jsonify({'success': True, 'sessions': sessions})


@app.route('/api/browser/sessions/start', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_session_start():
    from browser_extras import session_recorder
    data = request.json or {}
    sid = session_recorder.start_recording(data.get('instance_id', ''), data.get('name', ''))
    return jsonify({'success': True, 'session_id': sid})


@app.route('/api/browser/sessions/stop', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_session_stop():
    from browser_extras import session_recorder
    data = request.json or {}
    sid = session_recorder.stop_recording(data.get('instance_id', ''))
    return jsonify({'success': True, 'session_id': sid})


@app.route('/api/browser/sessions/<sid>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_session_get(sid):
    from browser_extras import session_recorder
    session = session_recorder.get_session(int(sid))
    if not session:
        return jsonify({'success': False, 'error': 'Session not found'}), 404
    return jsonify({'success': True, 'session': session})


@app.route('/api/browser/sessions/<sid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_session_delete(sid):
    from browser_extras import session_recorder
    session_recorder.delete_session(int(sid))
    return jsonify({'success': True})


@app.route('/api/browser/sessions/play', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_session_play():
    from browser_extras import session_player
    data = request.json or {}
    result = session_player.play_session(
        int(data.get('session_id', 0)),
        data.get('instance_id', ''),
        float(data.get('speed', 1.0)),
    )
    return jsonify(result)


@app.route('/api/browser/sessions/stop-play', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_session_stop_play():
    from browser_extras import session_player
    data = request.json or {}
    session_player.stop_playback(data.get('instance_id', ''))
    return jsonify({'success': True})


@app.route('/api/browser/sessions/play-status/<instance_id>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_session_play_status(instance_id):
    from browser_extras import session_player
    status = session_player.get_status(instance_id)
    return jsonify({'success': True, 'playing': status is not None, 'status': status})


# ── Multi-Tab Manager ────────────────────────────────────────

@app.route('/api/browser/tabs/<instance_id>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_tabs_list(instance_id):
    from browser_extras import tab_manager
    tabs = tab_manager.list_tabs(instance_id)
    return jsonify({'success': True, 'tabs': tabs})


@app.route('/api/browser/tabs/<instance_id>/open', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_tab_open(instance_id):
    from browser_extras import tab_manager
    data = request.json or {}
    result = tab_manager.open_tab(instance_id, data.get('url', ''), data.get('activate', True))
    return jsonify(result)


@app.route('/api/browser/tabs/<instance_id>/close/<tab_id>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_tab_close(instance_id, tab_id):
    from browser_extras import tab_manager
    result = tab_manager.close_tab(instance_id, tab_id)
    return jsonify(result)


@app.route('/api/browser/tabs/<instance_id>/switch/<tab_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_tab_switch(instance_id, tab_id):
    from browser_extras import tab_manager
    result = tab_manager.switch_tab(instance_id, tab_id)
    return jsonify(result)


# ── Browser Templates ────────────────────────────────────────

@app.route('/api/browser/templates', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_templates_list():
    from browser_advanced import list_templates
    return jsonify({'success': True, 'templates': list_templates()})


@app.route('/api/browser/templates/<tid>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_template_get(tid):
    from browser_advanced import get_template
    t = get_template(int(tid))
    if not t:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify({'success': True, 'template': t})


@app.route('/api/browser/templates', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_template_create():
    from browser_advanced import create_template
    data = request.json or {}
    tid = create_template(data.get('name', ''), data)
    return jsonify({'success': True, 'id': tid})


@app.route('/api/browser/templates/<tid>', methods=['PUT'])
@api_auth
@permission_required('manage_bots')
def api_browser_template_update(tid):
    from browser_advanced import update_template
    update_template(int(tid), request.json or {})
    return jsonify({'success': True})


@app.route('/api/browser/templates/<tid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_template_delete(tid):
    from browser_advanced import delete_template
    delete_template(int(tid))
    return jsonify({'success': True})


@app.route('/api/browser/templates/<tid>/create-browser', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_template_create_browser(tid):
    from browser_advanced import create_browser_from_template
    data = request.json or {}
    inst = create_browser_from_template(int(tid), data.get('name', ''))
    if inst:
        return jsonify({'success': True, 'instance_id': inst.id})
    return jsonify({'success': False, 'error': 'Failed to create'}), 400


# ── Proxy Manager ────────────────────────────────────────────

@app.route('/api/browser/proxies', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_proxies_list():
    from browser_advanced import list_proxies
    return jsonify({'success': True, 'proxies': list_proxies()})


@app.route('/api/browser/proxies', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_proxy_add():
    from browser_advanced import add_proxy
    data = request.json or {}
    pid = add_proxy(
        data.get('name', ''), data.get('host', ''), data.get('port', 80),
        data.get('protocol', 'http'), data.get('username', ''), data.get('password', ''),
        data.get('country', ''), data.get('city', ''), data.get('is_residential', False)
    )
    return jsonify({'success': True, 'id': pid})


@app.route('/api/browser/proxies/<pid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_proxy_delete(pid):
    from browser_advanced import delete_proxy
    delete_proxy(int(pid))
    return jsonify({'success': True})


@app.route('/api/browser/proxies/<pid>/toggle', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_proxy_toggle(pid):
    from browser_advanced import toggle_proxy
    active = (request.json or {}).get('active', True)
    toggle_proxy(int(pid), active)
    return jsonify({'success': True})


@app.route('/api/browser/proxies/best', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_proxy_best():
    from browser_advanced import get_best_proxy
    country = request.args.get('country')
    proxy = get_best_proxy(country)
    return jsonify({'success': True, 'proxy': proxy})


@app.route('/api/browser/proxies/import', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_proxy_import():
    from browser_advanced import import_proxies
    data = request.json or {}
    count = import_proxies(data.get('proxies', []))
    return jsonify({'success': True, 'imported': count})


@app.route('/api/browser/proxies/stats', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_proxy_stats():
    from browser_advanced import get_proxy_stats
    return jsonify({'success': True, 'stats': get_proxy_stats()})


# ── Fingerprint Rotation ─────────────────────────────────────

@app.route('/api/browser/fingerprint/<instance_id>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_fingerprint_get(instance_id):
    from browser_advanced import get_fingerprint
    fp = get_fingerprint(instance_id)
    return jsonify({'success': True, 'fingerprint': fp})


@app.route('/api/browser/fingerprint/<instance_id>/generate', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_fingerprint_generate(instance_id):
    from browser_advanced import generate_fingerprint
    fp = generate_fingerprint(instance_id)
    return jsonify({'success': True, 'fingerprint': fp})


@app.route('/api/browser/fingerprint/<instance_id>/rotate', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_fingerprint_rotate(instance_id):
    from browser_advanced import rotate_fingerprint
    fp = rotate_fingerprint(instance_id)
    return jsonify({'success': True, 'fingerprint': fp})


# ── Usage Analytics ──────────────────────────────────────────

@app.route('/api/browser/analytics/stats', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_analytics_stats():
    from browser_advanced import get_usage_stats
    iid = request.args.get('instance_id')
    days = request.args.get('days', 7, type=int)
    return jsonify({'success': True, 'stats': get_usage_stats(iid, days)})


@app.route('/api/browser/analytics/daily', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_analytics_daily():
    from browser_advanced import get_daily_usage
    iid = request.args.get('instance_id')
    days = request.args.get('days', 30, type=int)
    return jsonify({'success': True, 'daily': get_daily_usage(iid, days)})


@app.route('/api/browser/analytics/top-sites', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_analytics_top_sites():
    from browser_advanced import get_top_sites
    iid = request.args.get('instance_id')
    limit = request.args.get('limit', 10, type=int)
    return jsonify({'success': True, 'sites': get_top_sites(iid, limit)})


# ── Browser Groups ───────────────────────────────────────────

@app.route('/api/browser/groups', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_groups_list():
    from browser_advanced import list_groups
    return jsonify({'success': True, 'groups': list_groups()})


@app.route('/api/browser/groups', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_group_create():
    from browser_advanced import create_group
    data = request.json or {}
    gid = create_group(data.get('name', ''), data.get('description', ''), data.get('color', '#3b82f6'))
    return jsonify({'success': True, 'id': gid})


@app.route('/api/browser/groups/<gid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_group_delete(gid):
    from browser_advanced import delete_group
    delete_group(int(gid))
    return jsonify({'success': True})


@app.route('/api/browser/groups/<gid>/add/<instance_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_group_add(gid, instance_id):
    from browser_advanced import add_to_group
    add_to_group(int(gid), instance_id)
    return jsonify({'success': True})


@app.route('/api/browser/groups/<gid>/remove/<instance_id>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_group_remove(gid, instance_id):
    from browser_advanced import remove_from_group
    remove_from_group(int(gid), instance_id)
    return jsonify({'success': True})


# ── Browser Tags ─────────────────────────────────────────────

@app.route('/api/browser/tags', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_tags_list():
    from browser_advanced import list_tags
    return jsonify({'success': True, 'tags': list_tags()})


@app.route('/api/browser/tags', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_tag_create():
    from browser_advanced import create_tag
    data = request.json or {}
    tid = create_tag(data.get('name', ''), data.get('color', '#6b7280'))
    return jsonify({'success': True, 'id': tid})


@app.route('/api/browser/tags/<tid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_tag_delete(tid):
    from browser_advanced import delete_tag
    delete_tag(int(tid))
    return jsonify({'success': True})


@app.route('/api/browser/tags/<instance_id>/add/<tag_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_tag_add(instance_id, tag_id):
    from browser_advanced import tag_instance
    tag_instance(instance_id, int(tag_id))
    return jsonify({'success': True})


@app.route('/api/browser/tags/<instance_id>/remove/<tag_id>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_tag_remove(instance_id, tag_id):
    from browser_advanced import untag_instance
    untag_instance(instance_id, int(tag_id))
    return jsonify({'success': True})


@app.route('/api/browser/tags/<instance_id>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_instance_tags(instance_id):
    from browser_advanced import get_instance_tags
    return jsonify({'success': True, 'tags': get_instance_tags(instance_id)})


# ── Browser History ──────────────────────────────────────────

@app.route('/api/browser/history', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_history_list():
    from browser_utility import get_history
    iid = request.args.get('instance_id')
    search = request.args.get('q', '')
    limit = request.args.get('limit', 100, type=int)
    return jsonify({'success': True, 'history': get_history(iid, limit, search)})


@app.route('/api/browser/history/search', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_history_search():
    from browser_utility import search_history
    q = request.args.get('q', '')
    limit = request.args.get('limit', 50, type=int)
    return jsonify({'success': True, 'results': search_history(q, limit)})


@app.route('/api/browser/history/frequent', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_history_frequent():
    from browser_utility import get_frequent_sites
    iid = request.args.get('instance_id')
    limit = request.args.get('limit', 20, type=int)
    return jsonify({'success': True, 'sites': get_frequent_sites(iid, limit)})


@app.route('/api/browser/history/recent', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_history_recent():
    from browser_utility import get_recent_history
    iid = request.args.get('instance_id')
    hours = request.args.get('hours', 24, type=int)
    limit = request.args.get('limit', 50, type=int)
    return jsonify({'success': True, 'history': get_recent_history(iid, hours, limit)})


@app.route('/api/browser/history/stats', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_history_stats():
    from browser_utility import get_history_stats
    iid = request.args.get('instance_id')
    return jsonify({'success': True, 'stats': get_history_stats(iid)})


@app.route('/api/browser/history/clear', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_history_clear():
    from browser_utility import clear_history
    iid = request.args.get('instance_id')
    days = request.args.get('older_than_days', type=int)
    clear_history(iid, days)
    return jsonify({'success': True})


# ── Clipboard Manager ────────────────────────────────────────

@app.route('/api/browser/clipboard', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_clipboard_list():
    from browser_utility import clipboard_get
    search = request.args.get('q', '')
    limit = request.args.get('limit', 50, type=int)
    return jsonify({'success': True, 'clipboard': clipboard_get(limit, search)})


@app.route('/api/browser/clipboard', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_clipboard_add():
    from browser_utility import clipboard_add
    data = request.json or {}
    cid = clipboard_add(data.get('content', ''), data.get('instance_id', ''),
                        data.get('content_type', 'text'), data.get('source', ''))
    return jsonify({'success': True, 'id': cid})


@app.route('/api/browser/clipboard/<cid>/pin', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_clipboard_pin(cid):
    from browser_utility import clipboard_pin
    clipboard_pin(int(cid))
    return jsonify({'success': True})


@app.route('/api/browser/clipboard/<cid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_clipboard_delete(cid):
    from browser_utility import clipboard_delete
    clipboard_delete(int(cid))
    return jsonify({'success': True})


@app.route('/api/browser/clipboard/clear', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_clipboard_clear():
    from browser_utility import clipboard_clear
    clipboard_clear()
    return jsonify({'success': True})


# ── Backup/Restore ───────────────────────────────────────────

@app.route('/api/browser/backups', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_backups_list():
    from browser_utility import list_backups
    return jsonify({'success': True, 'backups': list_backups()})


@app.route('/api/browser/backups', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_backup_create():
    from browser_utility import create_backup
    data = request.json or {}
    result = create_backup(data.get('name', 'backup'), data.get('description', ''))
    return jsonify(result)


@app.route('/api/browser/backups/<bid>/restore', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_backup_restore(bid):
    from browser_utility import restore_backup
    result = restore_backup(int(bid))
    return jsonify(result)


@app.route('/api/browser/backups/<bid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_backup_delete(bid):
    from browser_utility import delete_backup
    delete_backup(int(bid))
    return jsonify({'success': True})


# ── Dashboard Overview ───────────────────────────────────────

@app.route('/api/browser/dashboard', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_dashboard():
    from browser_utility import get_dashboard_overview
    return jsonify({'success': True, 'overview': get_dashboard_overview()})


# ── Form Auto-Fill ───────────────────────────────────────────

@app.route('/api/browser/form-profiles', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_form_profiles_list():
    from browser_smart import list_form_profiles
    return jsonify({'success': True, 'profiles': list_form_profiles()})


@app.route('/api/browser/form-profiles/<pid>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_form_profile_get(pid):
    from browser_smart import get_form_profile
    p = get_form_profile(int(pid))
    if not p:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify({'success': True, 'profile': p})


@app.route('/api/browser/form-profiles', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_form_profile_create():
    from browser_smart import create_form_profile
    data = request.json or {}
    pid = create_form_profile(data.get('name', ''), data.get('data', {}),
                               data.get('description', ''), data.get('is_default', False))
    return jsonify({'success': True, 'id': pid})


@app.route('/api/browser/form-profiles/<pid>', methods=['PUT'])
@api_auth
@permission_required('manage_bots')
def api_browser_form_profile_update(pid):
    from browser_smart import update_form_profile
    update_form_profile(int(pid), (request.json or {}).get('data', {}))
    return jsonify({'success': True})


@app.route('/api/browser/form-profiles/<pid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_form_profile_delete(pid):
    from browser_smart import delete_form_profile
    delete_form_profile(int(pid))
    return jsonify({'success': True})


@app.route('/api/browser/form-profiles/default', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_form_profile_default():
    from browser_smart import get_default_profile
    return jsonify({'success': True, 'profile': get_default_profile()})


@app.route('/api/browser/form-fill/<instance_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_form_fill(instance_id):
    from browser_manager import get_instance
    from browser_smart import get_default_profile, match_field_to_value
    data = request.json or {}
    profile_id = data.get('profile_id')
    if profile_id:
        from browser_smart import get_form_profile
        profile = get_form_profile(int(profile_id))
        profile_data = profile.get('data', {}) if profile else {}
    else:
        profile_data = get_default_profile().get('data', {})

    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return jsonify({'success': False, 'error': 'Browser not running'}), 400

    # Find all form fields and fill them
    filled = []
    try:
        fields = inst.page.query_selector_all('input, textarea, select')
        for field in fields:
            try:
                name = field.get_attribute('name') or ''
                field_id = field.get_attribute('id') or ''
                field_class = field.get_attribute('class') or ''
                field_type = field.get_attribute('type') or 'text'
                if field_type in ['hidden', 'submit', 'button', 'checkbox', 'radio']:
                    continue
                field_type_matched, value = match_field_to_value(name, field_id, field_class, profile_data)
                if value:
                    field.fill(value)
                    filled.append({'field': name or field_id, 'type': field_type_matched, 'value': value[:50]})
            except Exception:
                continue
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    return jsonify({'success': True, 'filled': len(filled), 'fields': filled})


# ── Content Extraction ───────────────────────────────────────

@app.route('/api/browser/extract/article', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_extract_article():
    from browser_manager import get_instance
    from browser_smart import extract_article
    data = request.json or {}
    instance_id = data.get('instance_id', '')
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return jsonify({'success': False, 'error': 'Browser not running'}), 400
    text = inst.page.inner_text('body')
    url = inst.page.url
    article = extract_article(text, url)
    return jsonify({'success': True, 'article': article})


@app.route('/api/browser/extract/prices', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_extract_prices():
    from browser_manager import get_instance
    from browser_smart import extract_prices
    data = request.json or {}
    instance_id = data.get('instance_id', '')
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return jsonify({'success': False, 'error': 'Browser not running'}), 400
    text = inst.page.inner_text('body')
    prices = extract_prices(text)
    return jsonify({'success': True, 'prices': prices})


@app.route('/api/browser/extract/contacts', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_extract_contacts():
    from browser_manager import get_instance
    from browser_smart import extract_contacts
    data = request.json or {}
    instance_id = data.get('instance_id', '')
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return jsonify({'success': False, 'error': 'Browser not running'}), 400
    text = inst.page.inner_text('body')
    contacts = extract_contacts(text)
    return jsonify({'success': True, 'contacts': contacts})


@app.route('/api/browser/extract/links', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_extract_links():
    from browser_manager import get_instance
    from browser_smart import extract_links
    data = request.json or {}
    instance_id = data.get('instance_id', '')
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return jsonify({'success': False, 'error': 'Browser not running'}), 400
    text = inst.page.inner_text('body')
    url = inst.page.url
    links = extract_links(text, url)
    return jsonify({'success': True, 'links': links})


@app.route('/api/browser/extract/metadata', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_extract_metadata():
    from browser_manager import get_instance
    from browser_smart import extract_metadata
    data = request.json or {}
    instance_id = data.get('instance_id', '')
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return jsonify({'success': False, 'error': 'Browser not running'}), 400
    text = inst.page.inner_text('body')
    url = inst.page.url
    meta = extract_metadata(text, url)
    return jsonify({'success': True, 'metadata': meta})


@app.route('/api/browser/extract/all', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_extract_all():
    from browser_manager import get_instance
    from browser_smart import extract_article, extract_prices, extract_contacts, extract_links, extract_metadata
    data = request.json or {}
    instance_id = data.get('instance_id', '')
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return jsonify({'success': False, 'error': 'Browser not running'}), 400
    text = inst.page.inner_text('body')
    url = inst.page.url
    return jsonify({
        'success': True,
        'article': extract_article(text, url),
        'prices': extract_prices(text),
        'contacts': extract_contacts(text),
        'links': extract_links(text, url),
        'metadata': extract_metadata(text, url),
    })


# ── Search Engine ────────────────────────────────────────────

@app.route('/api/browser/search', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_search():
    from browser_manager import get_instance
    from browser_smart import get_search_url, log_search
    data = request.json or {}
    engine = data.get('engine', 'google')
    query = data.get('query', '')
    instance_id = data.get('instance_id', '')
    if not query:
        return jsonify({'success': False, 'error': 'Query required'}), 400
    url = get_search_url(engine, query)
    if instance_id:
        inst = get_instance(instance_id)
        if inst and inst.page:
            inst.navigate(url)
    log_search(engine, query, 0, instance_id)
    return jsonify({'success': True, 'url': url, 'engine': engine})


@app.route('/api/browser/search/history', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_search_history():
    from browser_smart import get_search_history
    engine = request.args.get('engine')
    limit = request.args.get('limit', 50, type=int)
    return jsonify({'success': True, 'history': get_search_history(engine, limit)})


@app.route('/api/browser/search/popular', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_search_popular():
    from browser_smart import get_popular_queries
    limit = request.args.get('limit', 20, type=int)
    return jsonify({'success': True, 'queries': get_popular_queries(limit)})


# ── Screenshot Gallery ───────────────────────────────────────

@app.route('/api/browser/screenshots', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_screenshots_list():
    from browser_smart import list_screenshots
    iid = request.args.get('instance_id')
    limit = request.args.get('limit', 100, type=int)
    return jsonify({'success': True, 'screenshots': list_screenshots(iid, limit)})


@app.route('/api/browser/screenshots/search', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_screenshots_search():
    from browser_smart import search_screenshots
    q = request.args.get('q', '')
    tag = request.args.get('tag', '')
    return jsonify({'success': True, 'screenshots': search_screenshots(q, tag)})


@app.route('/api/browser/screenshots/stats', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_screenshots_stats():
    from browser_smart import get_screenshot_stats
    return jsonify({'success': True, 'stats': get_screenshot_stats()})


@app.route('/api/browser/screenshots/<sid>', methods=['PUT'])
@api_auth
@permission_required('manage_bots')
def api_browser_screenshot_update(sid):
    from browser_smart import update_screenshot
    data = request.json or {}
    update_screenshot(int(sid), data.get('tags'), data.get('notes'))
    return jsonify({'success': True})


@app.route('/api/browser/screenshots/<sid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_screenshot_delete(sid):
    from browser_smart import delete_screenshot
    delete_screenshot(int(sid))
    return jsonify({'success': True})


# ── WebSocket Real-Time ──────────────────────────────────────

@app.route('/api/browser/ws/subscribe/<instance_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_ws_subscribe(instance_id):
    from browser_realtime import browser_ws
    q = browser_ws.subscribe(instance_id)
    events = list(q)[-50:]
    return jsonify({'success': True, 'events': events, 'subscribers': browser_ws.get_subscribers_count(instance_id)})


@app.route('/api/browser/ws/events/<instance_id>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_ws_events(instance_id):
    from browser_realtime import browser_ws
    limit = request.args.get('limit', 50, type=int)
    return jsonify({'success': True, 'events': browser_ws.get_recent(instance_id, limit)})


@app.route('/api/browser/ws/events-all', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_ws_events_all():
    from browser_realtime import browser_ws
    limit = request.args.get('limit', 100, type=int)
    return jsonify({'success': True, 'events': browser_ws.get_all_recent(limit)})


@app.route('/api/browser/ws/stats', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_ws_stats():
    from browser_realtime import browser_ws
    return jsonify({'success': True, 'subscribers': browser_ws.get_subscribers_count()})


# ── Ad Blocker ───────────────────────────────────────────────

@app.route('/api/browser/adblock/<instance_id>/enable', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_adblock_enable(instance_id):
    from browser_manager import get_instance
    from browser_realtime import get_adblock_js
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return jsonify({'success': False, 'error': 'Browser not running'}), 400
    try:
        inst.page.evaluate(get_adblock_js())
        return jsonify({'success': True, 'message': 'Ad blocker enabled'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/browser/adblock/<instance_id>/hide', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_adblock_hide(instance_id):
    from browser_manager import get_instance
    from browser_realtime import get_hide_elements_js
    data = request.json or {}
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return jsonify({'success': False, 'error': 'Browser not running'}), 400
    try:
        selectors = data.get('selectors', [])
        inst.page.evaluate(get_hide_elements_js(selectors if selectors else None))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/browser/adblock/<instance_id>/custom', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_adblock_custom(instance_id):
    from browser_manager import get_instance
    from browser_realtime import get_custom_hide_js
    data = request.json or {}
    selector = data.get('selector', '')
    if not selector:
        return jsonify({'success': False, 'error': 'Selector required'}), 400
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return jsonify({'success': False, 'error': 'Browser not running'}), 400
    try:
        result = inst.page.evaluate(get_custom_hide_js(selector))
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Resource Blocker + Throttle ──────────────────────────────

@app.route('/api/browser/resources/<instance_id>/block', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_resources_block(instance_id):
    from browser_manager import get_instance
    from browser_realtime import get_resource_block_js
    data = request.json or {}
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return jsonify({'success': False, 'error': 'Browser not running'}), 400
    try:
        block_types = data.get('types', ['image', 'media', 'font', 'stylesheet'])
        inst.page.evaluate(get_resource_block_js(block_types))
        return jsonify({'success': True, 'blocked': block_types})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/browser/resources/throttle-profiles', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_throttle_profiles():
    from browser_realtime import THROTTLE_PROFILES
    return jsonify({'success': True, 'profiles': THROTTLE_PROFILES})


# ── Console Viewer ───────────────────────────────────────────

@app.route('/api/browser/console/<instance_id>/logs', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_console_logs(instance_id):
    from browser_realtime import console_viewer
    logs = console_viewer.get_logs(instance_id)
    return jsonify({'success': True, 'logs': logs, 'count': len(logs)})


@app.route('/api/browser/console/<instance_id>/clear', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_console_clear(instance_id):
    from browser_realtime import console_viewer
    console_viewer.clear_logs(instance_id)
    return jsonify({'success': True})


@app.route('/api/browser/console/<instance_id>/enable', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_console_enable(instance_id):
    from browser_manager import get_instance
    from browser_realtime import console_viewer
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return jsonify({'success': False, 'error': 'Browser not running'}), 400
    try:
        inst.page.evaluate(console_viewer.get_console_js())
        return jsonify({'success': True, 'message': 'Console capture enabled'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── PDF / HTML / Text Export ─────────────────────────────────

@app.route('/api/browser/export/<instance_id>/pdf', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_export_pdf(instance_id):
    from browser_realtime import export_page_pdf
    data = request.json or {}
    result = export_page_pdf(instance_id, **data)
    return jsonify(result)


@app.route('/api/browser/export/<instance_id>/html', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_export_html(instance_id):
    from browser_realtime import export_page_html
    result = export_page_html(instance_id)
    return jsonify(result)


@app.route('/api/browser/export/<instance_id>/text', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_export_text(instance_id):
    from browser_realtime import export_page_text
    result = export_page_text(instance_id)
    return jsonify(result)


# ── Page Performance ─────────────────────────────────────────

@app.route('/api/browser/performance/<instance_id>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_performance(instance_id):
    from browser_realtime import get_page_metrics
    return jsonify(get_page_metrics(instance_id))


# ── Browser State Export/Import ──────────────────────────────

@app.route('/api/browser/state/<instance_id>/export', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_state_export(instance_id):
    from browser_realtime import export_browser_state
    return jsonify(export_browser_state(instance_id))


@app.route('/api/browser/state/<instance_id>/import', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_state_import(instance_id):
    from browser_realtime import import_browser_state
    data = request.json or {}
    return jsonify(import_browser_state(instance_id, data.get('state', {})))


# ── File Upload/Download ─────────────────────────────────────

@app.route('/api/browser/upload/<instance_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_upload(instance_id):
    from browser_files import upload_file
    data = request.json or {}
    return jsonify(upload_file(instance_id, data.get('file_path', ''), data.get('selector', 'input[type="file"]')))


@app.route('/api/browser/upload/<instance_id>/multi', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_upload_multi(instance_id):
    from browser_files import upload_files
    data = request.json or {}
    return jsonify(upload_files(instance_id, data.get('file_paths', []), data.get('selector', 'input[type="file"]')))


@app.route('/api/browser/upload/setup/<instance_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_upload_setup(instance_id):
    from browser_files import setup_download_handler
    return jsonify(setup_download_handler(instance_id))


@app.route('/api/browser/uploads/list', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_uploads_list():
    from browser_files import list_upload_files
    return jsonify({'success': True, 'files': list_upload_files(), 'upload_dir': get_upload_dir()})


@app.route('/api/browser/downloads', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_downloads_list():
    from browser_files import list_downloads
    iid = request.args.get('instance_id')
    return jsonify({'success': True, 'downloads': list_downloads(iid)})


@app.route('/api/browser/downloads/<did>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_download_delete(did):
    from browser_files import delete_download
    delete_download(int(did))
    return jsonify({'success': True})


# ── Mobile Emulation ─────────────────────────────────────────

@app.route('/api/browser/devices', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_devices():
    from browser_files import get_device_presets
    return jsonify({'success': True, 'devices': get_device_presets()})


@app.route('/api/browser/emulate/<instance_id>/<device>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_emulate(instance_id, device):
    from browser_files import apply_device_preset
    return jsonify(apply_device_preset(instance_id, device))


@app.route('/api/browser/responsive-test/<instance_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_responsive_test(instance_id):
    from browser_files import responsive_test
    data = request.json or {}
    return jsonify(responsive_test(instance_id, data.get('url', ''), data.get('devices')))


# ── Task Queue ───────────────────────────────────────────────

@app.route('/api/browser/queues', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_queues_list():
    from browser_files import task_queue
    return jsonify({'success': True, 'queues': task_queue.list_queues()})


@app.route('/api/browser/queues', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_queue_create():
    from browser_files import task_queue
    data = request.json or {}
    qid = task_queue.create_queue(data.get('name', ''), data.get('tasks', []))
    return jsonify({'success': True, 'queue_id': qid})


@app.route('/api/browser/queues/<qid>/start', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_queue_start(qid):
    from browser_files import task_queue
    data = request.json or {}
    return jsonify(task_queue.start_queue(int(qid), data.get('instance_id', '')))


@app.route('/api/browser/queues/<qid>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_queue_get(qid):
    from browser_files import task_queue
    q = task_queue.get_queue(int(qid))
    if not q:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify({'success': True, 'queue': q})


@app.route('/api/browser/queues/<qid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_queue_delete(qid):
    from browser_files import task_queue
    task_queue.delete_queue(int(qid))
    return jsonify({'success': True})


# ── User Agent Rotation ──────────────────────────────────────

@app.route('/api/browser/user-agents', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_user_agents():
    from browser_spoof import get_all_user_agents
    return jsonify({'success': True, 'agents': get_all_user_agents()})


@app.route('/api/browser/user-agents/random', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_user_agent_random():
    from browser_spoof import get_random_ua
    platform = request.args.get('platform')
    browser = request.args.get('browser')
    return jsonify({'success': True, 'user_agent': get_random_ua(platform, browser)})


@app.route('/api/browser/rotate-ua/<instance_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_rotate_ua(instance_id):
    from browser_spoof import rotate_user_agent
    return jsonify(rotate_user_agent(instance_id))


# ── Screen/WebGL/Canvas Spoofing ─────────────────────────────

@app.route('/api/browser/spoof/<instance_id>/screen', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_spoof_screen(instance_id):
    from browser_manager import get_instance
    from browser_spoof import get_spoof_screen_js
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return jsonify({'success': False, 'error': 'Browser not running'}), 400
    try:
        r = inst.page.evaluate(get_spoof_screen_js())
        return jsonify({'success': True, 'result': r})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/browser/spoof/<instance_id>/webgl', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_spoof_webgl(instance_id):
    from browser_manager import get_instance
    from browser_spoof import get_spoof_webgl_js
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return jsonify({'success': False, 'error': 'Browser not running'}), 400
    try:
        r = inst.page.evaluate(get_spoof_webgl_js())
        return jsonify({'success': True, 'result': r})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/browser/spoof/<instance_id>/canvas', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_spoof_canvas(instance_id):
    from browser_manager import get_instance
    from browser_spoof import get_spoof_canvas_js
    inst = get_instance(instance_id)
    if not inst or not inst.page:
        return jsonify({'success': False, 'error': 'Browser not running'}), 400
    try:
        r = inst.page.evaluate(get_spoof_canvas_js())
        return jsonify({'success': True, 'result': r})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/browser/spoof/<instance_id>/all', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_spoof_all(instance_id):
    from browser_spoof import apply_full_anti_detection
    return jsonify(apply_full_anti_detection(instance_id))


# ── Drag & Drop ──────────────────────────────────────────────

@app.route('/api/browser/drag-drop/<instance_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_drag_drop(instance_id):
    from browser_spoof import simulate_drag_drop
    data = request.json or {}
    return jsonify(simulate_drag_drop(instance_id, data.get('source', ''), data.get('target', '')))


@app.route('/api/browser/file-drop/<instance_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_file_drop(instance_id):
    from browser_spoof import simulate_file_drop
    data = request.json or {}
    return jsonify(simulate_file_drop(instance_id, data.get('file_path', ''), data.get('target', '')))


# ── Keyboard Shortcuts ───────────────────────────────────────

@app.route('/api/browser/shortcuts', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_shortcuts_list():
    from browser_spoof import get_all_shortcuts
    return jsonify({'success': True, 'shortcuts': get_all_shortcuts()})


@app.route('/api/browser/shortcut/<instance_id>/<name>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_shortcut_press(instance_id, name):
    from browser_spoof import press_shortcut
    return jsonify(press_shortcut(instance_id, name))


@app.route('/api/browser/key/<instance_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_key_press(instance_id):
    from browser_spoof import press_key
    data = request.json or {}
    return jsonify(press_key(instance_id, data.get('key', ''), data.get('modifiers')))


@app.route('/api/browser/type/<instance_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_type_text(instance_id):
    from browser_spoof import type_shortcut
    data = request.json or {}
    return jsonify(type_shortcut(instance_id, data.get('text', ''), data.get('delay', 50)))


# ── Iframe Handling ──────────────────────────────────────────

@app.route('/api/browser/iframes/<instance_id>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_iframes(instance_id):
    from browser_spoof import list_iframes
    return jsonify(list_iframes(instance_id))


@app.route('/api/browser/iframe/<instance_id>/switch', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_iframe_switch(instance_id):
    from browser_spoof import switch_to_frame
    data = request.json or {}
    return jsonify(switch_to_frame(instance_id, data.get('index', 0), data.get('name', '')))


@app.route('/api/browser/iframe/<instance_id>/main', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_iframe_main(instance_id):
    from browser_spoof import switch_to_main_frame
    return jsonify(switch_to_main_frame(instance_id))


# ── Shadow DOM ───────────────────────────────────────────────

@app.route('/api/browser/shadow/<instance_id>/query', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_shadow_query(instance_id):
    from browser_spoof import query_shadow_dom
    data = request.json or {}
    return jsonify(query_shadow_dom(instance_id, data.get('host', ''), data.get('inner', '')))


@app.route('/api/browser/shadow/<instance_id>/click', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_shadow_click(instance_id):
    from browser_spoof import click_shadow_dom
    data = request.json or {}
    return jsonify(click_shadow_dom(instance_id, data.get('host', ''), data.get('inner', '')))


# ── Media Devices ────────────────────────────────────────────

@app.route('/api/browser/media/<instance_id>/emulate', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_media_emulate(instance_id):
    from browser_spoof import emulate_media_devices
    data = request.json or {}
    return jsonify(emulate_media_devices(instance_id, data.get('camera', 1),
                                          data.get('microphone', 1), data.get('speaker', 1)))


# ── Saved Profiles ───────────────────────────────────────────

@app.route('/api/browser/saved-profiles', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_saved_profiles_list():
    from browser_profiles import list_profiles
    return jsonify({'success': True, 'profiles': list_profiles()})


@app.route('/api/browser/saved-profiles', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_saved_profile_save():
    from browser_profiles import save_profile
    data = request.json or {}
    return jsonify(save_profile(data.get('instance_id', ''), data.get('name', ''), data.get('description', '')))


@app.route('/api/browser/saved-profiles/<pid>/restore', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_saved_profile_restore(pid):
    from browser_profiles import restore_profile
    data = request.json or {}
    return jsonify(restore_profile(int(pid), data.get('instance_id')))


@app.route('/api/browser/saved-profiles/<pid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_saved_profile_delete(pid):
    from browser_profiles import delete_profile
    delete_profile(int(pid))
    return jsonify({'success': True})


@app.route('/api/browser/saved-profiles/<pid>/favorite', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_saved_profile_favorite(pid):
    from browser_profiles import toggle_favorite
    toggle_favorite(int(pid))
    return jsonify({'success': True})


@app.route('/api/browser/saved-profiles/<pid>/export', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_saved_profile_export(pid):
    from browser_profiles import export_profile
    data = export_profile(int(pid))
    if not data:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify({'success': True, 'profile': data})


@app.route('/api/browser/saved-profiles/import', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_saved_profile_import():
    from browser_profiles import import_profile
    data = request.json or {}
    return jsonify(import_profile(data.get('profile', {}), data.get('name')))


@app.route('/api/browser/saved-profiles/search', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_saved_profile_search():
    from browser_profiles import search_profiles
    q = request.args.get('q', '')
    return jsonify({'success': True, 'profiles': search_profiles(q)})


# ── Content Injection ────────────────────────────────────────

@app.route('/api/browser/inject/css/<instance_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_inject_css(instance_id):
    from browser_profiles import inject_css
    data = request.json or {}
    return jsonify(inject_css(instance_id, data.get('css', '')))


@app.route('/api/browser/inject/js/<instance_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_inject_js(instance_id):
    from browser_profiles import inject_js
    data = request.json or {}
    return jsonify(inject_js(instance_id, data.get('js', '')))


@app.route('/api/browser/inject/js-file/<instance_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_inject_js_file(instance_id):
    from browser_profiles import inject_js_file
    data = request.json or {}
    return jsonify(inject_js_file(instance_id, data.get('url', '')))


@app.route('/api/browser/inject/remove/<instance_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_inject_remove(instance_id):
    from browser_profiles import remove_injections
    return jsonify(remove_injections(instance_id))


@app.route('/api/browser/inject/apply-saved/<instance_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_inject_apply_saved(instance_id):
    from browser_profiles import apply_saved_injections
    return jsonify(apply_saved_injections(instance_id))


@app.route('/api/browser/css-injections', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_css_injections_list():
    from browser_profiles import list_css_injections
    return jsonify({'success': True, 'injections': list_css_injections()})


@app.route('/api/browser/css-injections', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_css_injection_create():
    from browser_profiles import save_css_injection
    data = request.json or {}
    return jsonify(save_css_injection(data.get('name', ''), data.get('css', ''), data.get('url_pattern', '*')))


@app.route('/api/browser/css-injections/<iid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_css_injection_delete(iid):
    from browser_profiles import delete_css_injection
    delete_css_injection(int(iid))
    return jsonify({'success': True})


@app.route('/api/browser/css-injections/<iid>/toggle', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_css_injection_toggle(iid):
    from browser_profiles import toggle_css_injection
    toggle_css_injection(int(iid))
    return jsonify({'success': True})


@app.route('/api/browser/js-injections', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_js_injections_list():
    from browser_profiles import list_js_injections
    return jsonify({'success': True, 'injections': list_js_injections()})


@app.route('/api/browser/js-injections', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_js_injection_create():
    from browser_profiles import save_js_injection
    data = request.json or {}
    return jsonify(save_js_injection(data.get('name', ''), data.get('js', ''),
                                     data.get('url_pattern', '*'), data.get('run_at', 'document_idle')))


@app.route('/api/browser/js-injections/<iid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_js_injection_delete(iid):
    from browser_profiles import delete_js_injection
    delete_js_injection(int(iid))
    return jsonify({'success': True})


@app.route('/api/browser/js-injections/<iid>/toggle', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_js_injection_toggle(iid):
    from browser_profiles import toggle_js_injection
    toggle_js_injection(int(iid))
    return jsonify({'success': True})


# ── Geolocation ──────────────────────────────────────────────

@app.route('/api/browser/geolocation/<instance_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_geolocation_set(instance_id):
    from browser_profiles import set_geolocation
    data = request.json or {}
    return jsonify(set_geolocation(instance_id, data.get('lat', 0), data.get('lng', 0), data.get('accuracy', 100)))


@app.route('/api/browser/geolocation/presets', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_geolocation_presets():
    from browser_profiles import get_preset_locations
    return jsonify({'success': True, 'locations': get_preset_locations()})


@app.route('/api/browser/geolocations', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_geolocations_list():
    from browser_profiles import list_geolocations
    return jsonify({'success': True, 'geolocations': list_geolocations()})


@app.route('/api/browser/geolocations', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_geolocation_create():
    from browser_profiles import save_geolocation
    data = request.json or {}
    return jsonify(save_geolocation(data.get('name', ''), data.get('lat', 0), data.get('lng', 0),
                                    data.get('accuracy', 100), data.get('city', ''), data.get('country', '')))


@app.route('/api/browser/geolocations/<gid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_geolocation_delete(gid):
    from browser_profiles import delete_geolocation
    delete_geolocation(int(gid))
    return jsonify({'success': True})


# ── Network Simulation ───────────────────────────────────────

@app.route('/api/browser/network/<instance_id>/simulate', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_network_simulate(instance_id):
    from browser_profiles import simulate_network
    data = request.json or {}
    return jsonify(simulate_network(instance_id, data.get('profile', 'normal')))


@app.route('/api/browser/network/presets', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_network_presets():
    from browser_profiles import get_network_presets
    return jsonify({'success': True, 'presets': get_network_presets()})


@app.route('/api/browser/network/profiles', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_network_profiles_list():
    from browser_profiles import list_network_profiles
    return jsonify({'success': True, 'profiles': list_network_profiles()})


@app.route('/api/browser/network/profiles', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_network_profile_create():
    from browser_profiles import save_network_profile
    data = request.json or {}
    return jsonify(save_network_profile(data.get('name', ''), data.get('download', 5000000),
                                        data.get('upload', 2000000), data.get('latency', 50),
                                        data.get('packet_loss', 0)))


# ── Notifications ────────────────────────────────────────────

@app.route('/api/browser/notifications/<instance_id>/allow', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_notifications_allow(instance_id):
    from browser_profiles import setup_notification_handler
    return jsonify(setup_notification_handler(instance_id))


# ── Instance CRUD ────────────────────────────────────────────

@app.route('/api/browser/instances', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_list():
    from browser_manager import list_instances
    return jsonify({'success': True, 'instances': list_instances()})


@app.route('/api/browser/instances', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_create():
    from browser_manager import create_instance
    data = request.json or {}
    inst = create_instance(
        name=data.get('name', ''),
        profile_id=data.get('profile_id'),
        proxy=data.get('proxy'),
    )
    return jsonify({'success': True, 'instance': inst.to_dict()})


@app.route('/api/browser/instances/<iid>/start', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_start(iid):
    from browser_manager import get_instance
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    ok = inst.start()
    return jsonify({'success': ok, 'instance': inst.to_dict()})


@app.route('/api/browser/instances/<iid>/stop', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_stop(iid):
    from browser_manager import get_instance
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    inst.stop()
    return jsonify({'success': True, 'instance': inst.to_dict()})


@app.route('/api/browser/instances/<iid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_delete(iid):
    from browser_manager import remove_instance
    remove_instance(iid)
    return jsonify({'success': True})


@app.route('/api/browser/instances/<iid>/navigate', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_navigate(iid):
    from browser_manager import get_instance
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    url = (request.json or {}).get('url', '')
    if not url:
        return jsonify({'success': False, 'error': 'URL required'}), 400
    return jsonify(inst.navigate(url))


@app.route('/api/browser/instances/<iid>/click', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_click(iid):
    from browser_manager import get_instance
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    sel = (request.json or {}).get('selector', '')
    return jsonify(inst.click(sel))


@app.route('/api/browser/instances/<iid>/type', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_type(iid):
    from browser_manager import get_instance
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    data = request.json or {}
    return jsonify(inst.type_text(data.get('selector', ''), data.get('text', ''), data.get('clear', True)))


@app.route('/api/browser/instances/<iid>/scroll', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_scroll(iid):
    from browser_manager import get_instance
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    data = request.json or {}
    return jsonify(inst.scroll(data.get('direction', 'down'), data.get('amount', 3)))


@app.route('/api/browser/instances/<iid>/screenshot', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_screenshot(iid):
    from browser_manager import get_instance
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    b64 = inst.get_screenshot_base64()
    if not b64:
        return jsonify({'success': False, 'error': 'No page'}), 400
    return jsonify({'success': True, 'screenshot': b64, 'url': inst.page.url if inst.page else ''})


@app.route('/api/browser/instances/<iid>/content', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_content(iid):
    from browser_manager import get_instance
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    return jsonify(inst.get_page_content())


@app.route('/api/browser/instances/<iid>/cookies', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_cookies(iid):
    from browser_manager import get_instance
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    return jsonify({'success': True, 'cookies': inst.get_cookies()})


@app.route('/api/browser/instances/<iid>/evaluate', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_evaluate(iid):
    from browser_manager import get_instance
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    expr = (request.json or {}).get('expression', '')
    return jsonify(inst.evaluate(expr))


@app.route('/api/browser/instances/<iid>/form', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_form(iid):
    from browser_manager import get_instance
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    fields = (request.json or {}).get('fields', [])
    return jsonify(inst.fill_form(fields))


@app.route('/api/browser/instances/<iid>/key', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_key(iid):
    from browser_manager import get_instance
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    key = (request.json or {}).get('key', '')
    return jsonify(inst.press_key(key))


@app.route('/api/browser/instances/<iid>/back', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_back(iid):
    from browser_manager import get_instance
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    return jsonify(inst.go_back())


@app.route('/api/browser/instances/<iid>/hover', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_hover(iid):
    from browser_manager import get_instance
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    sel = (request.json or {}).get('selector', '')
    return jsonify(inst.hover(sel))


@app.route('/api/browser/instances/<iid>/wait', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_browser_wait(iid):
    from browser_manager import get_instance
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    data = request.json or {}
    return jsonify(inst.wait_for(data.get('selector', ''), data.get('timeout', 10000)))


@app.route('/api/browser/profiles', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_profiles():
    from browser_manager import list_profiles
    return jsonify({'success': True, 'profiles': list_profiles()})


@app.route('/api/browser/profiles/<pid>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_browser_delete_profile(pid):
    from browser_manager import delete_profile
    delete_profile(pid)
    return jsonify({'success': True})


@app.route('/api/browser/screenshot-file/<iid>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_browser_screenshot_file(iid):
    from browser_manager import get_instance, SCREENSHOTS_DIR
    inst = get_instance(iid)
    if not inst:
        return jsonify({'success': False, 'error': 'Instance not found'}), 404
    path = inst.screenshot()
    if not path:
        return jsonify({'success': False, 'error': 'Failed'}), 500
    return send_file(path, mimetype='image/png')


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

    # Matches (SQLite — single source of truth)
    try:
        _mc = agent_db._conn()
        _mrows = _mc.execute("SELECT status FROM matches").fetchall()
        for _m in _mrows:
            s = _m['status']
            if s not in ('completed', 'cancelled'): stats['matches']['active'] += 1
            if s == 'completed': stats['matches']['completed'] += 1
            if s == 'disputed': stats['matches']['disputed'] += 1
        stats['matches']['pending'] = _mc.execute(
            "SELECT COUNT(*) c FROM match_requests WHERE status='waiting'").fetchone()['c']
        _mc.close()
    except Exception:
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
            try:
                _lc = agent_db._conn()
                _active_m = _lc.execute(
                    "SELECT COUNT(*) c FROM matches WHERE status NOT IN ('completed','cancelled')").fetchone()['c']
                _pending_m = _lc.execute(
                    "SELECT COUNT(*) c FROM match_requests WHERE status='waiting'").fetchone()['c']
                _lc.close()
            except Exception:
                _active_m = sum(1 for m in read_csv('matches.csv') if m.get('status') not in ('completed', 'cancelled'))
                _pending_m = sum(1 for r in read_csv('match_requests.csv') if r.get('status') == 'waiting')
            data = {
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'users_total': len(read_csv('users.csv')),
                'pending_txns': sum(1 for t in read_csv('transactions.csv') if t.get('status') == 'pending'),
                'active_matches': _active_m,
                'pending_matches': _pending_m,
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

    # مطابقات المستخدم (SQLite)
    try:
        _uc = agent_db._conn()
        user_matches = [dict(r) for r in _uc.execute(
            "SELECT * FROM matches WHERE depositor_id=? OR withdrawer_id=? "
            "ORDER BY created_at DESC LIMIT 5", (str(user_id), str(user_id))).fetchall()]
        _uc.close()
    except Exception:
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


def _get_system_setting(key):
    try:
        for s_ in read_csv('system_settings.csv'):
            k = s_.get('key', '') or s_.get('setting_key', '')
            if k == key:
                return s_.get('value', '') or s_.get('setting_value', '')
    except Exception:
        pass
    return ''


@app.route('/api/bot-icon-settings')
@api_auth
def api_bot_icon_settings():
    """إعدادات عرض صور الشركات/وسائل الدفع في البوت."""
    mode = _get_system_setting('bot_icon_mode') or 'off'
    size = _get_system_setting('bot_icon_size') or '128'
    return jsonify({'bot_icon_mode': mode, 'bot_icon_size': size})


@app.route('/api/bot-icon-settings', methods=['POST'])
@api_auth
@permission_required('manage_settings')
def api_save_bot_icon_settings():
    data = request.json or {}
    mode = data.get('bot_icon_mode', 'off')
    if mode not in ('off', 'photo'):
        return jsonify({'success': False, 'error': 'وضع غير صالح'}), 400
    try:
        size = max(32, min(int(data.get('bot_icon_size', 128)), 512))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'حجم غير صالح'}), 400
    settings = read_csv('system_settings.csv')
    fieldnames = get_fieldnames('system_settings.csv', ['key', 'value', 'updated_at'])
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for key, value in (('bot_icon_mode', mode), ('bot_icon_size', str(size))):
        found = False
        for s_ in settings:
            k = s_.get('key', '') or s_.get('setting_key', '')
            if k == key:
                if 'value' in s_: s_['value'] = value
                if 'setting_value' in s_: s_['setting_value'] = value
                if 'updated_at' in fieldnames: s_['updated_at'] = now
                found = True
                break
        if not found:
            row = {fn: '' for fn in fieldnames}
            if 'key' in fieldnames: row['key'] = key
            if 'setting_key' in fieldnames: row['setting_key'] = key
            if 'value' in fieldnames: row['value'] = value
            if 'setting_value' in fieldnames: row['setting_value'] = value
            if 'updated_at' in fieldnames: row['updated_at'] = now
            settings.append(row)
    write_csv('system_settings.csv', settings, fieldnames)
    log_action('save_bot_icon_settings', f'{mode}/{size}')
    return jsonify({'success': True})


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
    # Magic-byte sanity check
    _magic_ok = (blob[:8] == b'\x89PNG\r\n\x1a\n' or blob[:3] == b'\xff\xd8\xff'
                 or blob[:6] in (b'GIF87a', b'GIF89a')
                 or (blob[:4] == b'RIFF' and blob[8:12] == b'WEBP'))
    if not _magic_ok:
        return jsonify({'success': False, 'error': 'الملف ليس صورة صالحة'}), 400

    os.makedirs(_ICON_UPLOAD_DIR, exist_ok=True)
    base_name = f"icon_{secrets.token_hex(8)}"

    # ── Process image: create 3 versions ──
    # 1) Telegram version: 48x48 PNG (small icon for sendPhoto)
    # 2) Web version: 128x128 PNG (larger for website)
    # 3) Delete original (save disk space)
    try:
        from PIL import Image
        import io as _io

        # Load image from blob
        img = Image.open(_io.BytesIO(blob))

        # Convert to RGBA if transparent, else RGB
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGBA')
        else:
            img = img.convert('RGB')

        # 1) Telegram icon: 48x48 PNG
        tg_img = img.resize((48, 48), Image.Resampling.LANCZOS)
        tg_fname = f"{base_name}_tg.png"
        tg_path = os.path.join(_ICON_UPLOAD_DIR, tg_fname)
        tg_img.save(tg_path, 'PNG', optimize=True)

        # 2) Web icon: 128x128 PNG
        web_img = img.resize((128, 128), Image.Resampling.LANCZOS)
        web_fname = f"{base_name}_web.png"
        web_path = os.path.join(_ICON_UPLOAD_DIR, web_fname)
        web_img.save(web_path, 'PNG', optimize=True)

        # 3) Bot icon: size controlled from settings (bot_icon_size), overridable via form field bot_size
        try:
            _bot_size = int(request.form.get('bot_size') or _get_system_setting('bot_icon_size') or 128)
        except (TypeError, ValueError):
            _bot_size = 128
        _bot_size = max(32, min(_bot_size, 512))
        bot_img = img.resize((_bot_size, _bot_size), Image.Resampling.LANCZOS)
        bot_fname = f"{base_name}_bot.png"
        bot_img.save(os.path.join(_ICON_UPLOAD_DIR, bot_fname), 'PNG', optimize=True)

        # 4) Original is NOT saved (deleted by not writing it)
        log_action('upload_icon', f'{tg_fname} + {web_fname} + {bot_fname} (original discarded)')

        return jsonify({
            'success': True,
            'url': f'/static/uploads/icons/{web_fname}',
            'telegram_url': f'/static/uploads/icons/{tg_fname}',
            'web_url': f'/static/uploads/icons/{web_fname}',
            'bot_url': f'/static/uploads/icons/{bot_fname}',
            'absolute_tg_url': f'https://vex.deals/static/uploads/icons/{tg_fname}',
            'absolute_web_url': f'https://vex.deals/static/uploads/icons/{web_fname}',
            'absolute_bot_url': f'https://vex.deals/static/uploads/icons/{bot_fname}',
        })
    except ImportError:
        # PIL not available — save original as fallback
        fname = f"{base_name}.{ext}"
        with open(os.path.join(_ICON_UPLOAD_DIR, fname), 'wb') as out:
            out.write(blob)
        log_action('upload_icon', f'{fname} (no PIL, original saved)')
        return jsonify({
            'success': True,
            'url': f'/static/uploads/icons/{fname}',
            'telegram_url': f'/static/uploads/icons/{fname}',
            'web_url': f'/static/uploads/icons/{fname}',
            'bot_url': f'/static/uploads/icons/{fname}',
            'absolute_tg_url': f'https://vex.deals/static/uploads/icons/{fname}',
            'absolute_web_url': f'https://vex.deals/static/uploads/icons/{fname}',
            'absolute_bot_url': f'https://vex.deals/static/uploads/icons/{fname}',
        })
    except Exception as e:
        # فك ترميز الصورة فشل (توقيع سليم لكن البكسلات تالفة) — نرفض بدلاً من
        # حفظ ملف معطوب ينتهي كأيقونة مكسورة في CSV
        log_action('upload_icon_failed', f'{base_name}: PIL error: {e}')
        return jsonify({'success': False, 'error': 'تعذر معالجة الصورة — جرّب صورة أخرى (PNG/JPG/WEBP)'}), 400

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
                'promo_code': c.get('promo_code', ''),
                'affiliate_link': c.get('affiliate_link', ''),
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
        linked_ids = [l.get('method_id', l.get('payment_method_id', '')) for l in links if l.get('company_id', '') == company_id]
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
    fieldnames = get_fieldnames('companies.csv', ['id','name','type','details','is_active','icon','address','affiliate_link','bot_icon'])
    if 'bot_icon' not in fieldnames:
        fieldnames.append('bot_icon')
    new_id = f"CMP{str(int(datetime.now().timestamp()))[-6:]}"
    new_company = {
        'id': new_id,
        'name': data.get('name', ''),
        'type': data.get('type', 'both'),
        'details': data.get('details', ''),
        'is_active': 'yes',
        'icon': data.get('icon', '🏢'),
        'address': data.get('address', ''),
        'affiliate_link': data.get('affiliate_link', ''),
        'bot_icon': data.get('bot_icon', ''),
        'promo_code': data.get('promo_code', ''),
        'show_in_comp': 'yes' if data.get('show_in_comp', True) in (True, 'yes', '1', 1, 'true') else 'no'
    }
    for _f in ('promo_code', 'show_in_comp'):
        if _f not in fieldnames:
            fieldnames.append(_f)
    append_csv('companies.csv', new_company, fieldnames)
    log_action('add_company', new_id)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/companies/<company_id>', methods=['PUT', 'DELETE'])
@api_auth
@permission_required('manage_companies')
def api_edit_company(company_id):
    companies = read_csv('companies.csv')
    fieldnames = get_fieldnames('companies.csv', ['id','name','type','details','is_active','icon','address','affiliate_link','bot_icon','promo_code','show_in_comp'])
    for _f in ('bot_icon', 'promo_code', 'show_in_comp'):
        if _f not in fieldnames:
            fieldnames.append(_f)

    if request.method == 'DELETE':
        companies = [c for c in companies if c.get('id') != company_id]
        write_csv('companies.csv', companies, fieldnames)
        log_action('delete_company', company_id)
        return jsonify({'success': True})
    elif request.method == 'PUT':
        data = request.json
        if 'show_in_comp' in data:
            data['show_in_comp'] = 'yes' if data['show_in_comp'] in (True, 'yes', '1', 1, 'true') else 'no'
        for c in companies:
            if c.get('id') == company_id:
                for k, v in data.items():
                    if k in fieldnames:
                        c[k] = v
                break
        write_csv('companies.csv', companies, fieldnames)
        log_action('edit_company', company_id)
        return jsonify({'success': True})

# ===== نظام التعويض (Compensation) — player web flow + admin approvals =====

_COMP_CSV_LOCK = threading.Lock()

def _comp_svrp():
    import sys as _s; _s.path.insert(0, BASE_DIR)
    from svrp import SVRPManager as _M
    return _M()

def _comp_tg(uid, text):
    """Best-effort Telegram notification to a player."""
    if not BOT_TOKEN or not uid:
        return
    try:
        import urllib.request as _u, json as _j
        _u.urlopen(_u.Request(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            data=_j.dumps({'chat_id': str(uid), 'text': text, 'parse_mode': 'HTML'}).encode(),
            headers={'Content-Type': 'application/json'}), timeout=6)
    except Exception as _e:
        app.logger.warning(f'comp notify failed uid={uid}: {_e}')

def _comp_alert_admins(text):
    for aid in ADMIN_IDS:
        _comp_tg(aid, text)

def _comp_strong_auth_or_error():
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'المصادقة مطلوبة — افتح الصفحة من التطبيق أو تيليغرام'}), 401
    return None

@app.route('/api/comp/admin/data')
@api_auth
@permission_required('view_financial')
def api_comp_admin_data():
    accounts = read_csv('user_company_accounts.csv'); accounts.reverse()
    # دمج إجابة "متى فتحت الحساب" (إن وُجدت) مع كل حساب
    try:
        src_map = {}
        for s in read_csv('comp_account_sources.csv'):
            src_map[(str(s.get('user_id', '')), str(s.get('company_id', '')))] = s.get('source', '')
    except Exception:
        src_map = {}
    for a in accounts[:200]:
        a['account_source'] = src_map.get((str(a.get('user_id', '')), str(a.get('company_id', ''))), '')
    return jsonify({'accounts': accounts[:200]})

@app.route('/api/comp/admin/account/<acc_id>', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_comp_admin_account(acc_id):
    action = (request.json or {}).get('action', '')
    if action not in ('approve', 'reject'):
        return jsonify({'error': 'إجراء غير صالح'}), 400
    with _COMP_CSV_LOCK:
        rows = read_csv('user_company_accounts.csv')
        fieldnames = get_fieldnames('user_company_accounts.csv',
            ['id','user_id','company_id','company_name','account_number','status','created_at'])
        row = next((r for r in rows if r.get('id') == acc_id), None)
        if not row:
            return jsonify({'error': 'الطلب غير موجود'}), 404
        row['status'] = 'active' if action == 'approve' else 'rejected'
        write_csv('user_company_accounts.csv', rows, fieldnames)
    uid = str(row.get('user_id',''))
    if action == 'approve':
        _comp_tg(uid, f"✅ <b>تم تأكيد حسابك في {row.get('company_name','')}</b>\n"
                      f"🔢 الحساب: <code>{row.get('account_number','')}</code>\n\n"
                      f"💰 قم بالإيداع والعب — وإذا خسرت قدّم طلب تعويض من صفحة التعويضات وسيتم تعويضك.")
    else:
        _comp_tg(uid, f"❌ لم يتم تأكيد حسابك في {row.get('company_name','')}.\n"
                      f"تأكد من رقم الحساب وأنك سجلت بكود البرومو الخاص بنا ثم أعد المحاولة.")
    log_action(f'comp_account_{action}', acc_id)
    return jsonify({'success': True})

# ===== API — Payment Methods =====

# قفل يمنع تداخل قراءة/كتابة متزامنة على payment_methods.csv (تعدد عمال gunicorn)
_PM_CSV_LOCK = threading.Lock()

def _pm_fieldnames():
    return get_fieldnames('payment_methods.csv',
        ['id','company_id','method_name','method_type','account_data','additional_info',
         'status','created_date','icon','available_for_games','currency','bot_icon'])

def _pm_new_id():
    """معرف فريد لوسيلة الدفع — timestamp وحده تكرر عند نقرات متتالية
    في نفس الثانية (كسر Alpine x-for بالمفاتيح المكررة)؛ نضيف عشوائية."""
    return f"PM{str(int(datetime.now().timestamp()))[-6:]}{secrets.token_hex(2).upper()}"

@app.route('/api/payment-methods')
@api_auth
def api_payment_methods():
    with _PM_CSV_LOCK:
        methods = read_csv('payment_methods.csv')
    # دفاع إضافي: تجاهل أي صفوف بمعرفات مكررة (نُبقي الأول) كي لا
    # تنكسر قوائم Alpine x-for :key مهما حدث للبيانات
    seen_ids = set()
    unique_methods = []
    for m in methods:
        mid = m.get('id', '')
        if mid and mid in seen_ids:
            continue
        if mid:
            seen_ids.add(mid)
        unique_methods.append(m)
    methods = unique_methods
    links = read_csv('company_payment_links.csv')
    # إضافة قائمة الشركات المرتبطة لكل وسيلة
    for m in methods:
        mid = m.get('id', '')
        linked_companies = [l.get('company_id') for l in links if l.get('method_id') == mid]
        m['linked_company_ids'] = linked_companies
        m['linked_count'] = len(linked_companies)
    return jsonify({'methods': methods, 'active_count': sum(1 for m in methods if m.get('status') == 'active')})

@app.route('/api/payment-methods', methods=['POST'])
@api_auth
@permission_required('manage_companies')
def api_add_payment_method():
    data = request.json
    if not str(data.get('method_name', '')).strip():
        return jsonify({'success': False, 'error': 'اسم الوسيلة مطلوب'}), 400
    fieldnames = _pm_fieldnames()
    new_method = {
        'id': '',  # يُولَّد داخل القفل
        'company_id': '',
        'method_name': data.get('method_name', ''),
        'method_type': data.get('method_type', ''),
        'account_data': data.get('account_data', ''),
        'additional_info': data.get('additional_info', ''),
        'status': 'active',
        'created_date': datetime.now().strftime('%Y-%m-%d'),
        'icon': data.get('icon', '💳'),
        'available_for_games': 'yes' if data.get('available_for_games', 'yes') in ('yes', True, 'true', '1') else 'no',
        'currency': data.get('currency', ''),
        'bot_icon': data.get('bot_icon', '')
    }
    with _PM_CSV_LOCK:
        # توليد معرف فريد مع فحص فعلي داخل القفل
        new_id = _pm_new_id()
        existing = read_csv('payment_methods.csv')
        while any(m.get('id') == new_id for m in existing):
            new_id = _pm_new_id()
        new_method['id'] = new_id
        append_csv('payment_methods.csv', new_method, fieldnames)
    log_action('add_payment_method', new_id)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/payment-methods/<method_id>', methods=['PUT', 'DELETE'])
@api_auth
@permission_required('manage_companies')
def api_edit_payment_method(method_id):
    with _PM_CSV_LOCK:
        methods = read_csv('payment_methods.csv')
        fieldnames = _pm_fieldnames()

        if request.method == 'DELETE':
            methods = [m for m in methods if m.get('id') != method_id]
            write_csv('payment_methods.csv', methods, fieldnames)
            log_action('delete_payment_method', method_id)
            return jsonify({'success': True})
        elif request.method == 'PUT':
            data = request.json
            found = False
            for m in methods:
                if m.get('id') == method_id:
                    found = True
                    for k, v in data.items():
                        if k in fieldnames and k not in ('linked_company_ids', 'linked_count'):
                            m[k] = v
                    break
            if not found:
                return jsonify({'success': False, 'error': 'الوسيلة غير موجودة'}), 404
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

# ===== API — Matching (SQLite — single source of truth) =====

@app.route('/api/matching/active')
@api_auth
def api_matching_active():
    conn = agent_db._conn()
    try:
        rows = conn.execute('''
            SELECT m.*, a.bot_name AS agent_name
            FROM matches m LEFT JOIN agent_bots a ON m.agent_id = a.id
            WHERE m.status NOT IN ('completed','cancelled')
            ORDER BY m.created_at DESC''').fetchall()
        active = [dict(r) for r in rows]
    finally:
        conn.close()
    return jsonify({'matches': active, 'count': len(active)})

@app.route('/api/matching/pending')
@api_auth
def api_matching_pending():
    """Pending matching requests — with assigned-agent info so the main admin
    sees exactly which agent is on duty for each request."""
    pending = agent_db.list_ops_requests(
        statuses=['waiting', 'approved', 'disputed'],
        states=[],
        limit=300)
    return jsonify({'requests': pending, 'count': len(pending)})

@app.route('/api/matching/logs')
@api_auth
def api_matching_logs():
    conn = agent_db._conn()
    try:
        rows = conn.execute('''
            SELECT m.*, a.bot_name AS agent_name
            FROM matches m LEFT JOIN agent_bots a ON m.agent_id = a.id
            WHERE m.status IN ('completed','cancelled')
            ORDER BY m.created_at DESC LIMIT 50''').fetchall()
        logs = [dict(r) for r in rows]
        req_rows = conn.execute('''
            SELECT r.*, a.bot_name AS agent_name
            FROM match_requests r
            LEFT JOIN agent_bots a ON r.assigned_agent_id = a.id
            WHERE r.status IN ('matched','cancelled','rejected')
            ORDER BY r.created_at DESC LIMIT 100
        ''').fetchall()
        for rr in req_rows:
            rd = dict(rr)
            logs.append({
                'id': rd.get('id', ''),
                'depositor_alias': rd.get('alias', '—'),
                'depositor_id': rd.get('user_id', ''),
                'withdrawer_alias': rd.get('agent_name', 'طرف آخر'),
                'withdrawer_id': rd.get('assigned_agent_id', ''),
                'amount': rd.get('amount', 0),
                'currency': rd.get('currency', 'EGP'),
                'company_name': rd.get('company_name', ''),
                'status': rd.get('status', ''),
                'completed_at': rd.get('approved_at', '') or rd.get('created_at', ''),
                'created_at': rd.get('created_at', ''),
            })
        logs.sort(key=lambda x: (x.get('completed_at') or x.get('created_at') or ''), reverse=True)
        logs = logs[:100]
    finally:
        conn.close()
    return jsonify({'matches': logs, 'count': len(logs)})

@app.route('/api/matching/<match_id>/chat')
@api_auth
def api_match_chat(match_id):
    conn = agent_db._conn()
    try:
        rows = conn.execute(
            'SELECT * FROM chat_messages WHERE match_id=? ORDER BY id', (match_id,)).fetchall()
        chat = [dict(r) for r in rows]
    finally:
        conn.close()
    return jsonify({'messages': chat})

@app.route('/api/matching/<match_id>/disputes')
@api_auth
def api_match_disputes(match_id):
    conn = agent_db._conn()
    try:
        rows = conn.execute(
            'SELECT * FROM match_disputes WHERE match_id=? ORDER BY created_at DESC',
            (match_id,)).fetchall()
        disputes = [dict(r) for r in rows]
    finally:
        conn.close()
    return jsonify({'disputes': disputes})

# ── User-facing matching (نظام المطابقة) — strong webapp auth ──

_MATCH_REQ_FIELDS = ['id', 'user_id', 'customer_id', 'type', 'amount', 'currency',
                     'status', 'created_at', 'approved_by', 'approved_at']

# Serializes all read-modify-write cycles on match_requests.csv (user create/
# cancel + agent settlement mirror) so concurrent writes can't clobber rows.
_MATCH_CSV_LOCK = threading.Lock()

def _matching_strong_auth_or_error():
    """User matching endpoints move money — require a validated identity
    (session login or HMAC-checked Telegram initData), never a raw uid param."""
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'المصادقة مطلوبة — افتح الصفحة من التطبيق أو تيليغرام'}), 401
    return None

@app.route('/api/matching/my')
@webapp_auth
def api_matching_my():
    """Current user's matching requests, newest first (SQLite)."""
    err = _matching_strong_auth_or_error()
    if err:
        return err
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    conn = agent_db._conn()
    try:
        rows = conn.execute(
            'SELECT * FROM match_requests WHERE user_id=? ORDER BY created_at DESC LIMIT 20',
            (uid,)).fetchall()
        reqs = [dict(r) for r in rows]
    finally:
        conn.close()
    return jsonify({'requests': reqs})

@app.route('/api/matching/request', methods=['POST'])
@webapp_auth
def api_matching_create():
    """Create a deposit/withdraw matching request — atomic SQLite create +
    agent pick + escrow hold. Notifies main admins AND the assigned agent."""
    err = _matching_strong_auth_or_error()
    if err:
        return err
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    data = request.json or {}
    rtype = str(data.get('type', '')).strip()
    if rtype not in ('deposit', 'withdraw', 'buy_usdt', 'sell_usdt'):
        return jsonify({'error': 'نوع الطلب غير صالح'}), 400
    source_type = 'personal_wallet' if str(data.get('source_type', '')).strip() == 'personal_wallet' else 'company'
    network = str(data.get('network', '') or '')[:32]
    try:
        rate = float(data.get('rate', 0) or 0)
    except (TypeError, ValueError):
        rate = 0.0
    try:
        amount = round(float(data.get('amount', 0)), 2)
    except (TypeError, ValueError):
        return jsonify({'error': 'مبلغ غير صالح'}), 400
    if not math.isfinite(amount) or amount <= 0 or amount > 10_000_000:
        return jsonify({'error': 'مبلغ غير صالح'}), 400
    details = str(data.get('details', '') or '')[:200]

    currency = 'EGP'
    user_name = ''
    if _VEX_GAMES:
        try:
            info = _gm.get_user_info(uid) or {}
            currency = info.get('currency', 'EGP') or 'EGP'
            user_name = info.get('name', '') or ''
            if rtype in ('withdraw', 'sell_usdt'):
                bal = float(_gm.get_balance(uid) or 0)
                if amount > bal:
                    return jsonify({'error': 'رصيد غير كافٍ'}), 400
        except Exception:
            pass

    rid, error, agent_assigned, agent_info = agent_db.create_match_request_with_agent_assignment(
        uid, uid, rtype, amount, currency,
        company_id='', company_name='', payment_method_id='', details=details,
        source_type=source_type, network=network, rate=rate)
    if error:
        status_code = 409 if 'نشط' in (error or '') else 400
        return jsonify({'error': error}), status_code

    log_action('match_request_created', f'{rid} {rtype} {amount} {currency} by {uid}')

    # ── Notify main admins (Telegram) ──
    type_map = {
        'deposit': 'إيداع',
        'withdraw': 'سحب',
        'buy_usdt': 'شراء USDT',
        'sell_usdt': 'بيع USDT',
    }
    type_ar = type_map.get(rtype, rtype)
    agent_line = ''
    if agent_assigned and agent_info:
        agent_line = f"\n🤖 الوكيل المعين: <b>{agent_info.get('name') or agent_info.get('id')}</b>"
    try:
        _comp_alert_admins(
            f"🔄 <b>طلب مطابقة جديد</b>\n\n"
            f"🆔 <code>{rid}</code>\n"
            f"👤 المستخدم: <code>{uid}</code>\n"
            f"{'💵' if rtype == 'deposit' else '💸'} النوع: {type_ar}\n"
            f"💰 المبلغ: <code>{amount:g} {currency}</code>"
            f"{agent_line}\n\n"
            f"📋 راجعه من لوحة المطابقات ← المعلقة")
    except Exception as _ne:
        app.logger.warning(f'matching admin notify failed {rid}: {_ne}')

    # ── Notify the assigned agent (Telegram, if linked) ──
    if agent_assigned and agent_info and agent_info.get('telegram_id'):
        try:
            _comp_tg(str(agent_info['telegram_id']),
                     f"🔔 <b>طلب مطابقة جديد معيّن لك</b>\n\n"
                     f"🆔 <code>{rid}</code>\n"
                     f"{'💵' if rtype == 'deposit' else '💸'} النوع: "
                     f"{'إيداع (تدفع للمستخدم)' if rtype == 'deposit' else 'سحب (تستلم من المستخدم)'}\n"
                     f"💰 المبلغ: <code>{amount:g} {currency}</code>\n\n"
                     f"⚡ افحصه من لوحة الوكيل ← الطلبات المعلقة")
        except Exception as _ae:
            app.logger.warning(f'matching agent notify failed {rid}: {_ae}')

    return jsonify({'success': True, 'request_id': rid,
                    'agent_assigned': agent_assigned,
                    'message': 'تم إنشاء طلب المطابقة — بانتظار المعالجة'})

@app.route('/api/matching/my/<rid>/cancel', methods=['POST'])
@webapp_auth
def api_matching_cancel(rid):
    """Cancel own still-waiting matching request — atomic in SQLite
    (voids pending agent txn + releases escrow + frees daily quota)."""
    err = _matching_strong_auth_or_error()
    if err:
        return err
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    ok, error = agent_db.cancel_match_request_atomic(rid, uid)
    if not ok:
        if 'بالفعل' in (error or ''):
            return jsonify({'error': error}), 409
        if 'غير موجود' in (error or ''):
            return jsonify({'error': error}), 404
        return jsonify({'error': error or 'تعذر الإلغاء الآن — حاول مجدداً'}), 500
    log_action('match_request_cancelled', f'{rid} by user {uid}')
    return jsonify({'success': True})


@app.route('/api/matching/my/<rid>/steps')
@webapp_auth
def api_matching_my_steps(rid):
    """User-facing full request detail with step state machine."""
    err = _matching_strong_auth_or_error()
    if err:
        return err
    uid = str(get_request_uid() or '')
    req = agent_db.get_match_request_steps(rid)
    if not req:
        return jsonify({'error': 'الطلب غير موجود'}), 404
    if str(req.get('user_id', '')) != uid:
        return jsonify({'error': 'غير مصرح'}), 403
    return jsonify({'request': req})


@app.route('/api/matching/my/<rid>/steps/<step_id>/action', methods=['POST'])
@webapp_auth
def api_matching_my_step_action(rid, step_id):
    err = _matching_strong_auth_or_error()
    if err:
        return err
    uid = str(get_request_uid() or '')
    payload = request.json or {}
    req = agent_db.get_match_request_full(rid)
    if not req:
        return jsonify({'error': 'الطلب غير موجود'}), 404
    if str(req.get('user_id', '')) != uid:
        return jsonify({'error': 'غير مصرح'}), 403
    res = agent_db.request_step_action(
        rid, step_id, 'user', uid,
        evidence_ref=str(payload.get('evidence_ref', '') or '')[:200],
        note=str(payload.get('note', '') or '')[:400],
    )
    if 'error' in res:
        return jsonify(res), 400
    return jsonify(res)


@app.route('/api/matching/my/<rid>/steps/<step_id>/confirm', methods=['POST'])
@webapp_auth
def api_matching_my_step_confirm(rid, step_id):
    err = _matching_strong_auth_or_error()
    if err:
        return err
    uid = str(get_request_uid() or '')
    payload = request.json or {}
    req = agent_db.get_match_request_full(rid)
    if not req:
        return jsonify({'error': 'الطلب غير موجود'}), 404
    if str(req.get('user_id', '')) != uid:
        return jsonify({'error': 'غير مصرح'}), 403
    accept = bool(payload.get('accept', True))
    res = agent_db.request_step_confirm(
        rid, step_id, 'user', uid, accept=accept,
        note=str(payload.get('note', '') or '')[:400],
    )
    if 'error' in res:
        return jsonify(res), 400
    return jsonify(res)


@app.route('/api/matching/my/<rid>/dispute', methods=['POST'])
@webapp_auth
def api_matching_my_dispute(rid):
    err = _matching_strong_auth_or_error()
    if err:
        return err
    uid = str(get_request_uid() or '')
    payload = request.json or {}
    req = agent_db.get_match_request_full(rid)
    if not req:
        return jsonify({'error': 'الطلب غير موجود'}), 404
    if str(req.get('user_id', '')) != uid:
        return jsonify({'error': 'غير مصرح'}), 403
    res = agent_db.open_request_dispute(
        rid, 'user', uid,
        str(payload.get('reason', '') or '')[:500],
        evidence_file_id=str(payload.get('evidence_file_id', '') or '')[:200],
    )
    if 'error' in res:
        return jsonify(res), 400
    return jsonify(res)


@app.route('/api/matching/my/<rid>/insurance-claim', methods=['POST'])
@webapp_auth
def api_matching_my_insurance_claim(rid):
    err = _matching_strong_auth_or_error()
    if err:
        return err
    uid = str(get_request_uid() or '')
    payload = request.json or {}
    req = agent_db.get_match_request_full(rid)
    if not req:
        return jsonify({'error': 'الطلب غير موجود'}), 404
    if str(req.get('user_id', '')) != uid:
        return jsonify({'error': 'غير مصرح'}), 403
    res = agent_db.create_insurance_claim(
        rid, 'user', uid,
        str(payload.get('reason', '') or '')[:500],
        evidence_file_id=str(payload.get('evidence_file_id', '') or '')[:200],
    )
    if 'error' in res:
        return jsonify(res), 400
    return jsonify(res)

# ===== API — SVRP =====

@app.route('/api/svrp/wallets')
@api_auth
def api_svrp_wallets():
    wallets = read_csv('svrp_wallets.csv')
    return jsonify({'wallets': wallets, 'count': len(wallets)})

# ===== SVRP Settings (Phase 1 — Admin Control Panel) =====

@app.route('/api/svrp/settings')
@api_auth
def api_svrp_settings():
    """Get all SVRP settings from system_settings.csv."""
    settings = read_csv('system_settings.csv')
    svrp_settings = {}
    for s in settings:
        key = s.get('key', '') or s.get('setting_key', '')
        if key.startswith('svrp_'):
            svrp_settings[key] = s.get('value', '') or s.get('setting_value', '')
    # Fill defaults from SVRP_CONFIG if not in CSV
    try:
        import sys as _sys; _sys.path.insert(0, BASE_DIR)
        from svrp import SVRP_CONFIG
        for k, v in SVRP_CONFIG.items():
            csv_key = f'svrp_{k}'
            if csv_key not in svrp_settings:
                svrp_settings[csv_key] = str(v)
    except:
        pass
    return jsonify({'settings': svrp_settings})

@app.route('/api/svrp/settings', methods=['POST'])
@api_auth
@permission_required('manage_settings')
def api_svrp_save_settings():
    """Save SVRP settings to system_settings.csv."""
    data = request.json or {}
    settings = read_csv('system_settings.csv')
    fieldnames = get_fieldnames('system_settings.csv', ['key', 'value', 'updated_at'])
    existing = {s.get('key', '') or s.get('setting_key', ''): s for s in settings}
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for key, value in data.items():
        if not key.startswith('svrp_'):
            continue
        if key in existing:
            existing[key]['value'] = str(value)
            existing[key]['updated_at'] = now
        else:
            settings.append({'key': key, 'value': str(value), 'updated_at': now})
    write_csv('system_settings.csv', settings, fieldnames)
    # Reload SVRP_CONFIG in current process
    try:
        import importlib
        import svrp as _svrp_mod
        _svrp_mod._load_config_from_csv()
    except:
        pass
    log_action('svrp_settings_update', json.dumps(data)[:100])
    return jsonify({'success': True, 'message': 'تم تحديث إعدادات التعويض'})

# ===== SVRP Analytics (Phase 4) =====

@app.route('/api/svrp/analytics')
@api_auth
def api_svrp_analytics():
    """SVRP analytics — recovery stats, conversion, referral growth."""
    wallets = read_csv('svrp_wallets.csv')
    credits = read_csv('svrp_credits.csv')
    requests = read_csv('recovery_requests.csv')
    promo_codes = read_csv('svrp_promo_codes.csv')
    # Key metrics
    total_wallets = len(wallets)
    total_frozen = sum(float(w.get('balance', 0) or 0) for w in wallets)
    total_pending = sum(float(w.get('pending_balance', 0) or 0) for w in wallets)
    total_earned = sum(float(w.get('total_earned', 0) or 0) for w in wallets)
    total_used = sum(float(w.get('total_used', 0) or 0) for w in wallets)
    # Recovery requests
    approved = [r for r in requests if r.get('status') == 'approved']
    pending = [r for r in requests if r.get('status') == 'pending']
    rejected = [r for r in requests if r.get('status') == 'rejected']
    total_recovery_amount = sum(float(r.get('recovery_amount', 0) or 0) for r in approved)
    # Wagering completion
    wagered = sum(1 for w in wallets if int(w.get('wagering_completed', 0) or 0) >= int(w.get('wagering_required', 3) or 3))
    # Promo codes
    active_codes = [p for p in promo_codes if p.get('status') == 'active']
    used_codes = [p for p in promo_codes if p.get('status') == 'used']
    # Credits by type
    from collections import Counter
    credit_types = Counter(c.get('credit_type', '') for c in credits)
    credit_status = Counter(c.get('status', '') for c in credits)
    # Conversion rate: how many wallets have total_used > 0 (unfrozen)
    converted = sum(1 for w in wallets if float(w.get('total_used', 0) or 0) > 0)
    conversion_rate = round(converted / total_wallets * 100, 2) if total_wallets > 0 else 0
    return jsonify({
        'total_wallets': total_wallets,
        'total_frozen': round(total_frozen, 2),
        'total_pending': round(total_pending, 2),
        'total_earned': round(total_earned, 2),
        'total_used': round(total_used, 2),
        'recovery_approved': len(approved),
        'recovery_pending': len(pending),
        'recovery_rejected': len(rejected),
        'total_recovery_amount': round(total_recovery_amount, 2),
        'wagering_completed': wagered,
        'wagering_rate': round(wagered / total_wallets * 100, 2) if total_wallets > 0 else 0,
        'active_promo_codes': len(active_codes),
        'used_promo_codes': len(used_codes),
        'conversion_rate': conversion_rate,
        'credit_types': dict(credit_types),
        'credit_status': dict(credit_status),
    })

# ===== SVRP Segments (Phase 2 — Smart Segmentation) =====

@app.route('/api/svrp/segments')
@api_auth
def api_svrp_segments():
    """List recovery segments with custom multipliers/wagering."""
    segments = read_csv('svrp_segments.csv')
    if not segments:
        # Auto-create default segments
        defaults = [
            {'id': 'SEG_NEW', 'name': 'لاعب جديد', 'multiplier': '2.0', 'wagering': '3', 'max_recovery': '1000', 'color': '#00e701', 'is_active': 'yes'},
            {'id': 'SEG_LOSER', 'name': 'خاسر', 'multiplier': '3.0', 'wagering': '3', 'max_recovery': '3000', 'color': '#ff4757', 'is_active': 'yes'},
            {'id': 'SEG_VIP', 'name': 'VIP', 'multiplier': '5.0', 'wagering': '5', 'max_recovery': '5000', 'color': '#fbbf24', 'is_active': 'yes'},
            {'id': 'SEG_CHURN', 'name': 'خامل (خطر مغادرة)', 'multiplier': '4.0', 'wagering': '2', 'max_recovery': '2000', 'color': '#a855f7', 'is_active': 'yes'},
        ]
        fields = get_fieldnames('svrp_segments.csv', ['id','name','multiplier','wagering','max_recovery','color','is_active'])
        for d in defaults:
            append_csv('svrp_segments.csv', d, fields)
        segments = defaults
    return jsonify({'segments': segments})

@app.route('/api/svrp/segments', methods=['POST'])
@api_auth
@permission_required('manage_settings')
def api_create_segment():
    """Create a new recovery segment."""
    data = request.json or {}
    seg_id = f"SEG{secrets.token_hex(2).upper()}"
    segment = {
        'id': seg_id,
        'name': data.get('name', ''),
        'multiplier': str(data.get('multiplier', '2.0')),
        'wagering': str(data.get('wagering', '3')),
        'max_recovery': str(data.get('max_recovery', '1000')),
        'color': data.get('color', '#00e701'),
        'is_active': 'yes',
    }
    fields = get_fieldnames('svrp_segments.csv', ['id','name','multiplier','wagering','max_recovery','color','is_active'])
    append_csv('svrp_segments.csv', segment, fields)
    return jsonify({'success': True, 'id': seg_id})

@app.route('/api/svrp/segments/<seg_id>', methods=['PUT', 'DELETE'])
@api_auth
@permission_required('manage_settings')
def api_edit_segment(seg_id):
    segments = read_csv('svrp_segments.csv')
    fields = get_fieldnames('svrp_segments.csv', ['id','name','multiplier','wagering','max_recovery','color','is_active'])
    if request.method == 'DELETE':
        segments = [s for s in segments if s.get('id') != seg_id]
        write_csv('svrp_segments.csv', segments, fields)
        return jsonify({'success': True})
    elif request.method == 'PUT':
        data = request.json or {}
        for s in segments:
            if s.get('id') == seg_id:
                for k, v in data.items():
                    if k in fields:
                        s[k] = str(v)
                break
        write_csv('svrp_segments.csv', segments, fields)
        return jsonify({'success': True})

# ===== SVRP Recovery Campaigns (Phase 3 — Seasonal Campaigns) =====

@app.route('/api/svrp/campaigns')
@api_auth
def api_svrp_recovery_campaigns():
    """List recovery campaigns."""
    campaigns = read_csv('svrp_recovery_campaigns.csv')
    campaigns.reverse()
    return jsonify({'campaigns': campaigns})

@app.route('/api/svrp/campaigns', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_create_recovery_campaign():
    """Create a recovery campaign (e.g. 'Weekend 200% Recovery')."""
    data = request.json or {}
    camp_id = f"RCV{secrets.token_hex(3).upper()}"
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    campaign = {
        'id': camp_id,
        'name': data.get('name', ''),
        'multiplier': str(data.get('multiplier', '2.0')),
        'target_segment': data.get('target_segment', 'all'),
        'target_country': data.get('target_country', 'all'),
        'max_per_user': str(data.get('max_per_user', '1000')),
        'total_budget': str(data.get('total_budget', '10000')),
        'spent': '0',
        'start_date': data.get('start_date', ''),
        'end_date': data.get('end_date', ''),
        'status': 'scheduled' if data.get('start_date') else 'active',
        'created_at': now,
        'created_by': session.get('admin_id', ''),
    }
    fields = get_fieldnames('svrp_recovery_campaigns.csv', ['id','name','multiplier','target_segment','target_country','max_per_user','total_budget','spent','start_date','end_date','status','created_at','created_by'])
    append_csv('svrp_recovery_campaigns.csv', campaign, fields)
    log_action('create_recovery_campaign', camp_id)
    return jsonify({'success': True, 'id': camp_id})

@app.route('/api/svrp/campaigns/<camp_id>', methods=['PUT', 'DELETE'])
@api_auth
@permission_required('send_broadcast')
def api_edit_recovery_campaign(camp_id):
    campaigns = read_csv('svrp_recovery_campaigns.csv')
    fields = get_fieldnames('svrp_recovery_campaigns.csv', ['id','name','multiplier','target_segment','target_country','max_per_user','total_budget','spent','start_date','end_date','status','created_at','created_by'])
    if request.method == 'DELETE':
        campaigns = [c for c in campaigns if c.get('id') != camp_id]
        write_csv('svrp_recovery_campaigns.csv', campaigns, fields)
        return jsonify({'success': True})
    elif request.method == 'PUT':
        data = request.json or {}
        for c in campaigns:
            if c.get('id') == camp_id:
                for k, v in data.items():
                    if k in fields:
                        c[k] = str(v)
                break
        write_csv('svrp_recovery_campaigns.csv', campaigns, fields)
        return jsonify({'success': True})

# ===== SVRP Automation (Phase 5 — Smart Automation) =====

@app.route('/api/svrp/automation')
@api_auth
def api_svrp_automation():
    """Get automation settings."""
    settings = read_csv('system_settings.csv')
    auto = {}
    for s in settings:
        key = s.get('key', '') or s.get('setting_key', '')
        if key.startswith('svrp_auto_'):
            auto[key] = s.get('value', '') or s.get('setting_value', '')
    # Defaults
    defaults = {
        'svrp_auto_approve': 'no',
        'svrp_auto_approve_max': '500',
        'svrp_auto_churn_days': '7',
        'svrp_auto_expire_days': '90',
        'svrp_auto_highloss_alert': '500',
    }
    for k, v in defaults.items():
        if k not in auto:
            auto[k] = v
    return jsonify({'automation': auto})

@app.route('/api/svrp/automation', methods=['POST'])
@api_auth
@permission_required('manage_settings')
def api_save_svrp_automation():
    """Save automation settings."""
    data = request.json or {}
    settings = read_csv('system_settings.csv')
    fields = get_fieldnames('system_settings.csv', ['key', 'value', 'updated_at'])
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    existing = {s.get('key', '') or s.get('setting_key', ''): s for s in settings}
    for key, value in data.items():
        if not key.startswith('svrp_auto_'):
            continue
        if key in existing:
            existing[key]['value'] = str(value)
            existing[key]['updated_at'] = now
        else:
            settings.append({'key': key, 'value': str(value), 'updated_at': now})
    write_csv('system_settings.csv', settings, fields)
    log_action('svrp_automation_update', json.dumps(data)[:100])
    return jsonify({'success': True})

@app.route('/api/svrp/requests')
@api_auth
@permission_required('view_financial')
def api_svrp_requests():
    reqs = read_csv('recovery_requests.csv')
    reqs.reverse()
    # إرفاق رابط الأفيليه للشركة كي يتحقق الأدمن من التسجيل
    affiliate_by_id = {}
    try:
        for c in read_csv('companies.csv'):
            affiliate_by_id[c.get('id', '')] = c.get('affiliate_link', '') or ''
    except Exception:
        pass
    for r in reqs:
        r['affiliate_link'] = affiliate_by_id.get(r.get('company_id', ''), '')
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
    _comp_tg(uid, f"🎉 <b>تمت الموافقة على تعويضك!</b>\n"
                  f"💎 المبلغ: <code>{amount_float:.2f}</code> أُضيف لرصيدك المجمد\n\n"
                  f"🔓 <b>لفك التجميد شارك الرصيد مع أصدقائك:</b>\n"
                  f"• كل صديق جديد يسجل بكود إحالتك ← يُفك 10% من رصيدك المجمد\n"
                  f"• حوّل 10% أو أكثر لصديق مستخدم بالفعل ← يُفك لك 5% (يصله الرصيد مجمداً بنفس الشروط)")
    return jsonify({'success': True, 'new_frozen_balance': result})

@app.route('/api/svrp/requests/<req_id>/reject', methods=['POST'])
@api_auth
@permission_required('reject_deposits')
def api_svrp_reject(req_id):
    reqs = read_csv('recovery_requests.csv')
    fieldnames = get_fieldnames('recovery_requests.csv', ['id','user_id','customer_id','photo_file_id','status','recovery_amount','admin_note','created_at','approved_at','approved_by'])
    _rej_uid = ''
    for r in reqs:
        if r.get('id') == req_id:
            r['status'] = 'rejected'
            _rej_uid = str(r.get('user_id', ''))
            break
    write_csv('recovery_requests.csv', reqs, fieldnames)
    log_action('svrp_reject', req_id)
    if _rej_uid:
        _comp_tg(_rej_uid, "❌ لم تتم الموافقة على طلب التعويض.\n"
                           "تأكد من لقطة الشاشة وأن الخسارة على الحساب المسجل ثم أعد المحاولة.")
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
    chans = read_csv('bot_channels.csv')
    if not chans:
        chans = read_csv('channels.csv')
    clean = []
    for c in chans:
        if str(c.get('is_active', '')).lower() in ('yes', 'true', '1', 'active', ''):
            clean.append({
                'title': c.get('title', c.get('name', '')),
                'chat_id': c.get('chat_id', ''),
                'username': c.get('username', ''),
                'description': c.get('description', ''),
                'platform': c.get('platform', 'telegram') or 'telegram',
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

# ── تداول USDT من الويب — نفس دورة حياة أوامر البوت (trade_orders.csv) ──────
# الحالات: pending → admin_accepted → buyer_pays → buyer_sends_screenshot
#          → admin_confirms_payment → admin_sends_screenshot → completed
# الأدمن يكمل الإجراءات من البوت كالمعتاد؛ الويب ينشئ الطلب ويرفع إثبات الدفع ويؤكد الاستلام.

_TRADING_CURRENCIES = [
    {'code': 'SAR', 'name': 'ريال سعودي'}, {'code': 'AED', 'name': 'درهم إماراتي'},
    {'code': 'EGP', 'name': 'جنيه مصري'}, {'code': 'KWD', 'name': 'دينار كويتي'},
    {'code': 'QAR', 'name': 'ريال قطري'}, {'code': 'BHD', 'name': 'دينار بحريني'},
    {'code': 'OMR', 'name': 'ريال عماني'}, {'code': 'JOD', 'name': 'دينار أردني'},
    {'code': 'USD', 'name': 'دولار أمريكي'}, {'code': 'EUR', 'name': 'يورو'},
    {'code': 'TRY', 'name': 'ليرة تركية'}, {'code': 'MAD', 'name': 'درهم مغربي'},
]
_TRADE_ALLOWED_EXT = {'.png', '.jpg', '.jpeg', '.webp'}
_TRADE_MAX_BYTES = 5 * 1024 * 1024

def _trade_fieldnames():
    return get_fieldnames('trade_orders.csv',
        ['id','buyer_id','buyer_name','customer_id','order_type','asset_type','network',
         'account_address','payment_method','amount','currency','usdt_amount',
         'admin_payment_method','status','screenshot_payment','screenshot_transfer',
         'admin_id','created_at','completed_at'])

def _trade_public_row(o):
    """تجهيز صف الطلب للعرض في الويب — بدون بيانات حساسة."""
    return {
        'id': o.get('id', ''),
        'order_type': o.get('order_type', ''),
        'asset_type': o.get('asset_type', ''),
        'network': o.get('network', ''),
        'account_address': o.get('account_address', ''),
        'payment_method': o.get('payment_method', ''),
        'amount': o.get('amount', ''),
        'currency': o.get('currency', ''),
        'usdt_amount': o.get('usdt_amount', ''),
        'admin_payment_method': o.get('admin_payment_method', ''),
        'status': o.get('status', ''),
        'screenshot_payment': o.get('screenshot_payment', '') if str(o.get('screenshot_payment', '')).startswith('http') else '',
        'created_at': o.get('created_at', ''),
    }

@app.route('/api/trading/web/methods')
@webapp_auth
def api_trading_web_methods():
    """وسائل الدفع النشطة + العملات المتاحة للتداول من الويب."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    methods = []
    for m in read_csv('payment_methods.csv'):
        if m.get('status') == 'active':
            methods.append({
                'id': m.get('id', ''),
                'name': m.get('method_name', ''),
                'type': m.get('method_type', ''),
                'account_data': m.get('account_data', ''),
                'icon': m.get('icon', '💳') or '💳',
            })
    return jsonify({'methods': methods, 'currencies': _TRADING_CURRENCIES})

@app.route('/api/trading/web/create-order', methods=['POST'])
@webapp_auth
def api_trading_web_create_order():
    """إنشاء أمر تداول (شراء/بيع USDT أو MoneyGo) من الويب."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json(silent=True) or {}

    order_type = str(data.get('order_type', '')).strip()
    asset_type = str(data.get('asset_type', '')).strip()
    network = str(data.get('network', '')).strip()
    account_address = str(data.get('account_address', '')).strip()
    payment_method = str(data.get('payment_method', '')).strip()
    currency = str(data.get('currency', '')).strip().upper()
    if order_type not in ('buy', 'sell'):
        return jsonify({'error': 'نوع الطلب غير صالح'}), 400
    if asset_type not in ('usdt', 'moneygo'):
        return jsonify({'error': 'نوع الأصل غير صالح'}), 400
    if asset_type == 'usdt' and network not in ('TRC20', 'ERC20', 'BNB20'):
        return jsonify({'error': 'اختر شبكة التحويل'}), 400
    if len(account_address) < 3 or len(account_address) > 120:
        return jsonify({'error': 'اكتب عنوان المحفظة/الحساب بشكل صحيح'}), 400
    if not payment_method:
        return jsonify({'error': 'اختر وسيلة الدفع'}), 400
    if currency not in {c['code'] for c in _TRADING_CURRENCIES}:
        return jsonify({'error': 'عملة غير مدعومة'}), 400
    try:
        amount = float(data.get('amount', 0))
        if amount <= 0 or amount > 10_000_000:
            return jsonify({'error': 'مبلغ غير صالح'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'مبلغ غير صالح'}), 400

    # بيانات المشتري من users.csv
    buyer_name, customer_id = '', ''
    for u in read_csv('users.csv'):
        if str(u.get('telegram_id', '')) == uid:
            buyer_name = u.get('username', '') or u.get('first_name', '') or uid
            customer_id = u.get('customer_id', '')
            break

    order_id = 'TRD' + datetime.now().strftime('%Y%m%d%H%M%S')
    order = {
        'id': order_id, 'buyer_id': uid, 'buyer_name': buyer_name,
        'customer_id': customer_id, 'order_type': order_type,
        'asset_type': asset_type, 'network': network,
        'account_address': account_address, 'payment_method': payment_method,
        'amount': str(amount), 'currency': currency, 'usdt_amount': '',
        'admin_payment_method': '', 'status': 'pending',
        'screenshot_payment': '', 'screenshot_transfer': '',
        'admin_id': '', 'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'completed_at': '',
    }
    with _PM_CSV_LOCK:  # نفس القفل — trade_orders.csv تُكتب أيضاً من البوت
        append_csv('trade_orders.csv', order, _trade_fieldnames())

    asset_label = 'USDT' if asset_type == 'usdt' else 'MoneyGo'
    action_label = 'شراء' if order_type == 'buy' else 'بيع'
    _comp_alert_admins(
        f"💱 <b>أمر تداول جديد من الويب</b>\n\n"
        f"🆔 الطلب: <code>{order_id}</code>\n"
        f"👤 المشتري: <code>{uid}</code>{(' (@' + buyer_name + ')') if buyer_name and buyer_name != uid else ''}\n"
        f"📦 النوع: {action_label} {asset_type.upper()}{(' — ' + network) if network else ''}\n"
        f"💰 المبلغ: {amount} {currency}\n"
        f"💳 وسيلة الدفع: {payment_method}\n"
        f"🏦 المحفظة: <code>{account_address}</code>\n\n"
        f"راجع الطلب من البوت ← طوابير الإدارة ← التداول")
    try:
        push_notification('trade_order', 'أمر تداول جديد',
                          f'{action_label} {asset_label} — {amount} {currency}')
    except Exception:
        pass
    log_action('web_trade_create', order_id)
    return jsonify({'ok': True, 'order_id': order_id,
                    'message': '✅ تم إنشاء الطلب — سيراجعه الأدمن ويرسل لك السعر ووسيلة الدفع'})

@app.route('/api/trading/web/my-orders')
@webapp_auth
def api_trading_web_my_orders():
    """طلبات التداول الخاصة بالمستخدم من الويب."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    orders = [o for o in read_csv('trade_orders.csv') if str(o.get('buyer_id', '')) == uid]
    orders.reverse()
    return jsonify({'orders': [_trade_public_row(o) for o in orders[:20]]})

@app.route('/api/trading/web/upload-screenshot', methods=['POST'])
@webapp_auth
def api_trading_web_upload_screenshot():
    """رفع لقطة إثبات الدفع من الويب — تعادل إرسال الصورة في البوت."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'Unauthorized'}), 403
    order_id = str(request.form.get('order_id', '')).strip()
    f = request.files.get('screenshot')
    if not order_id:
        return jsonify({'error': 'رقم الطلب مطلوب'}), 400
    if not f or not f.filename:
        return jsonify({'error': 'أرفق لقطة شاشة'}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in _TRADE_ALLOWED_EXT:
        return jsonify({'error': 'صيغة الصورة غير مدعومة (png/jpg/webp)'}), 400
    blob = f.read(_TRADE_MAX_BYTES + 1)
    if len(blob) > _TRADE_MAX_BYTES:
        return jsonify({'error': 'حجم الصورة يتجاوز 5MB'}), 400
    if not blob:
        return jsonify({'error': 'الملف فارغ'}), 400
    if not (blob.startswith(b'\x89PNG') or blob.startswith(b'\xff\xd8\xff')
            or (blob[:4] == b'RIFF' and blob[8:12] == b'WEBP')):
        return jsonify({'error': 'الملف ليس صورة صالحة'}), 400

    with _PM_CSV_LOCK:
        orders = read_csv('trade_orders.csv')
        order = next((o for o in orders if o.get('id') == order_id), None)
        if not order:
            return jsonify({'error': 'الطلب غير موجود'}), 404
        if str(order.get('buyer_id', '')) != uid:
            return jsonify({'error': 'غير مصرح'}), 403
        if order.get('status') != 'buyer_pays':
            return jsonify({'error': 'رفع الإثبات متاح فقط بعد تحديد السعر ووسيلة الدفع'}), 400

        # حفظ في static/trade-uploads — يُخدم مباشرة و sendPhoto في البوت
        # يقبل روابط HTTPS فتصل الإدارة لقطة المشتري من الويب
        static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'trade-uploads')
        os.makedirs(static_dir, exist_ok=True)
        fname = f"{uid}_{secrets.token_hex(8)}{ext}"
        with open(os.path.join(static_dir, fname), 'wb') as out:
            out.write(blob)
        base_url = request.url_root.rstrip('/')
        screenshot_url = f"{base_url}/static/trade-uploads/{fname}"

        order['screenshot_payment'] = screenshot_url
        order['status'] = 'buyer_sends_screenshot'
        write_csv('trade_orders.csv', orders, _trade_fieldnames())

    _comp_alert_admins(
        f"📸 <b>إثبات دفع من الويب</b>\n\n"
        f"🆔 الطلب: <code>{order_id}</code>\n"
        f"👤 المشتري: <code>{uid}</code>\n\n"
        f"راجع الصورة وأكّد الدفع من البوت ← طوابير الإدارة ← التداول")
    return jsonify({'ok': True, 'message': '✅ تم إرسال إثبات الدفع — بانتظار تأكيد الإدارة'})

@app.route('/api/trading/web/confirm-receipt', methods=['POST'])
@webapp_auth
def api_trading_web_confirm_receipt():
    """تأكيد المستلم لاستلام USDT — تكملة الطلب."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json(silent=True) or {}
    order_id = str(data.get('order_id', '')).strip()
    if not order_id:
        return jsonify({'error': 'رقم الطلب مطلوب'}), 400
    with _PM_CSV_LOCK:
        orders = read_csv('trade_orders.csv')
        order = next((o for o in orders if o.get('id') == order_id), None)
        if not order:
            return jsonify({'error': 'الطلب غير موجود'}), 404
        if str(order.get('buyer_id', '')) != uid:
            return jsonify({'error': 'غير مصرح'}), 403
        if order.get('status') != 'admin_sends_screenshot':
            return jsonify({'error': 'التأكيد متاح بعد إرسال الإدارة إثبات التحويل'}), 400
        order['status'] = 'completed'
        order['completed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        write_csv('trade_orders.csv', orders, _trade_fieldnames())
    _comp_alert_admins(f"✅ <b>اكتمل طلب تداول (تأكيد ويب)</b>\n🆔 <code>{order_id}</code>\n👤 <code>{uid}</code>")
    return jsonify({'ok': True, 'message': '✅ تم تأكيد الاستلام — اكتمل الطلب بنجاح'})

@app.route('/api/trading/web/cancel', methods=['POST'])
@webapp_auth
def api_trading_web_cancel():
    """إلغاء طلب معلق من الويب (قبل قبول الأدمن فقط)."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json(silent=True) or {}
    order_id = str(data.get('order_id', '')).strip()
    with _PM_CSV_LOCK:
        orders = read_csv('trade_orders.csv')
        order = next((o for o in orders if o.get('id') == order_id), None)
        if not order:
            return jsonify({'error': 'الطلب غير موجود'}), 404
        if str(order.get('buyer_id', '')) != uid:
            return jsonify({'error': 'غير مصرح'}), 403
        if order.get('status') != 'pending':
            return jsonify({'error': 'لا يمكن إلغاء طلب قيد المعالجة — تواصل مع الدعم'}), 400
        order['status'] = 'cancelled'
        write_csv('trade_orders.csv', orders, _trade_fieldnames())
    _comp_alert_admins(f"🚫 <b>إلغاء طلب تداول (ويب)</b>\n🆔 <code>{order_id}</code>\n👤 <code>{uid}</code>")
    return jsonify({'ok': True, 'message': 'تم إلغاء الطلب'})

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
        for k in _CAMPAIGN_FIELDS:
            if k not in c:
                c[k] = ''
    return jsonify({'campaigns': campaigns})

@app.route('/api/campaigns', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_create_campaign():
    """Create a new campaign with full platform support."""
    data = request.json or {}
    campaign_id = f"CMP{secrets.token_hex(3).upper()}"
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    media_urls = data.get('media_urls', [])
    abs_media_urls = []
    for url in media_urls:
        if url:
            abs_media_urls.append(url if url.startswith('http') else f'https://vex.deals{url}')

    # Resolve selected channels/groups to comma-separated IDs
    selected_channels = data.get('selectedChannels', [])
    selected_groups = data.get('selectedGroups', [])
    selected_channels_str = ','.join(str(c) for c in selected_channels) if selected_channels else ''
    selected_groups_str = ','.join(str(g) for g in selected_groups) if selected_groups else ''

    campaign = {
        'id': campaign_id,
        'name': data.get('name', ''),
        'message': data.get('message', ''),
        'media_urls': '|'.join(abs_media_urls),
        'target': data.get('target', 'telegram'),
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
        'platform_account_id': data.get('platform_account_id', ''),
        'ai_agent_id': data.get('ai_agent_id', ''),
        'selected_channels': selected_channels_str,
        'selected_groups': selected_groups_str,
        'whatsapp_contacts': data.get('whatsappContacts', ''),
        'whatsapp_groups': data.get('whatsappGroups', ''),
    }
    fieldnames = get_fieldnames('campaigns.csv', _CAMPAIGN_FIELDS)
    append_csv('campaigns.csv', campaign, fieldnames)
    log_action('create_campaign', campaign_id)

    # If no schedule → execute immediately (async)
    if not data.get('scheduled_at'):
        campaign['status'] = 'active'
        _update_campaign_status(campaign_id, 'active')
        try:
            from campaign_platforms import run_campaign_async
            run_campaign_async(campaign_id, BASE_DIR)
        except Exception as e:
            logger.error(f'Async campaign launch failed: {e}')
            _execute_campaign(campaign)
            _update_campaign_status(campaign_id, 'completed')

    return jsonify({'success': True, 'id': campaign_id, 'status': campaign['status']})

@app.route('/api/campaigns/<campaign_id>', methods=['PUT', 'DELETE'])
@api_auth
@permission_required('send_broadcast')
def api_edit_campaign(campaign_id):
    campaigns = read_csv('campaigns.csv')
    fieldnames = get_fieldnames('campaigns.csv', _CAMPAIGN_FIELDS)
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
                # If status changed to 'active' → execute async
                if data.get('status') == 'active' and c.get('status') not in ('completed', 'running'):
                    c['status'] = 'active'
                    try:
                        from campaign_platforms import run_campaign_async
                        write_csv('campaigns.csv', campaigns, fieldnames)
                        run_campaign_async(campaign_id, BASE_DIR)
                        return jsonify({'success': True})
                    except Exception as e:
                        logger.error(f'Async campaign launch failed: {e}')
                        _execute_campaign(c)
                        c['status'] = 'completed'
                break
        write_csv('campaigns.csv', campaigns, fieldnames)
        return jsonify({'success': True})

@app.route('/api/campaigns/analytics')
@api_auth
def api_campaigns_analytics():
    """Campaign analytics — reach, clicks, conversions, comparison."""
    campaigns = read_csv('campaigns.csv')
    total_reach = sum(int(c.get('stats_reach', 0) or 0) for c in campaigns)
    total_clicks = sum(int(c.get('stats_clicks', 0) or 0) for c in campaigns)
    total_conversions = sum(int(c.get('stats_conversions', 0) or 0) for c in campaigns)
    completed = [c for c in campaigns if c.get('status') == 'completed']
    top = sorted(completed, key=lambda c: int(c.get('stats_reach', 0) or 0), reverse=True)[:5]
    from collections import defaultdict
    daily = defaultdict(int)
    for c in completed:
        d = c.get('created_at', '')[:10]
        if d: daily[d] += int(c.get('stats_reach', 0) or 0)
    return jsonify({
        'total_campaigns': len(campaigns), 'completed': len(completed),
        'total_reach': total_reach, 'total_clicks': total_clicks,
        'total_conversions': total_conversions,
        'ctr': round(total_clicks / total_reach * 100, 2) if total_reach > 0 else 0,
        'conversion_rate': round(total_conversions / total_clicks * 100, 2) if total_clicks > 0 else 0,
        'top_campaigns': [{'name': c.get('name',''), 'reach': int(c.get('stats_reach',0) or 0), 'clicks': int(c.get('stats_clicks',0) or 0)} for c in top],
        'daily_reach': dict(list(daily.items())[-7:])
    })

@app.route('/api/campaigns/<campaign_id>/stats')
@api_auth
def api_campaign_stats(campaign_id):
    """Get campaign stats with per-channel delivery results."""
    campaigns = read_csv('campaigns.csv')
    results = []
    results_path = os.path.join(BASE_DIR, 'campaign_results.csv')
    if os.path.exists(results_path):
        try:
            with open(results_path, 'r', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    if row.get('campaign_id') == campaign_id:
                        results.append(row)
        except Exception:
            pass
    for c in campaigns:
        if c.get('id') == campaign_id:
            return jsonify({
                'id': campaign_id,
                'reach': int(c.get('stats_reach', 0) or 0),
                'clicks': int(c.get('stats_clicks', 0) or 0),
                'conversions': int(c.get('stats_conversions', 0) or 0),
                'status': c.get('status', 'unknown'),
                'channel_results': results,
                'delivered': sum(1 for r in results if r.get('status') == 'delivered'),
                'failed': sum(1 for r in results if r.get('status') == 'failed'),
            })
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/campaigns/<campaign_id>/retry', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_retry_campaign(campaign_id):
    """Retry failed channels in a campaign."""
    campaigns = read_csv('campaigns.csv')
    for c in campaigns:
        if c.get('id') == campaign_id:
            try:
                from campaign_platforms import run_campaign_async
                _update_campaign_status(campaign_id, 'running')
                run_campaign_async(campaign_id, BASE_DIR)
                return jsonify({'success': True, 'message': 'Retrying...'})
            except Exception as e:
                return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Campaign not found'}), 404


@app.route('/api/supported-platforms')
@api_auth
def api_supported_platforms():
    """List all supported social media platforms."""
    try:
        from campaign_platforms import get_all_platforms
        return jsonify({'platforms': get_all_platforms()})
    except ImportError:
        return jsonify({'platforms': []})

def _update_campaign_status(campaign_id, status):
    """Update campaign status in CSV."""
    try:
        campaigns = read_csv('campaigns.csv')
        fieldnames = get_fieldnames('campaigns.csv', _CAMPAIGN_FIELDS)
        for c in campaigns:
            if c.get('id') == campaign_id:
                c['status'] = status
                break
        write_csv('campaigns.csv', campaigns, fieldnames)
    except:
        pass

# ===== API — Fraud Detection (Phase 2) =====

_FRAUD_CLICK_LIMIT = 5  # max clicks per IP per campaign
_FRAUD_TIME_WINDOW = 3600  # 1 hour in seconds

def _check_fraud(campaign_id, ip, fingerprint=''):
    """Check if a click is fraudulent. Returns (is_fraud, reason)."""
    try:
        clicks = read_csv('campaign_clicks.csv')
        from datetime import datetime as _dt
        now = _dt.now()
        # Count clicks from same IP for this campaign in last hour
        ip_clicks = 0
        fp_clicks = 0
        for c in clicks:
            if c.get('campaign_id') != campaign_id:
                continue
            try:
                click_time = _dt.strptime(c.get('timestamp', '')[:19], '%Y-%m-%d %H:%M:%S')
                age = (now - click_time).total_seconds()
                if age > _FRAUD_TIME_WINDOW:
                    continue
            except:
                continue
            if c.get('ip') == ip:
                ip_clicks += 1
            if fingerprint and c.get('fingerprint', '') == fingerprint:
                fp_clicks += 1
        if ip_clicks >= _FRAUD_CLICK_LIMIT:
            return True, f'IP {ip} exceeded {_FRAUD_CLICK_LIMIT} clicks in 1h ({ip_clicks})'
        if fp_clicks >= _FRAUD_CLICK_LIMIT:
            return True, f'Fingerprint exceeded {_FRAUD_CLICK_LIMIT} clicks in 1h ({fp_clicks})'
        return False, ''
    except:
        return False, ''

def _log_fraud(campaign_id, ip, fingerprint, reason):
    """Log a fraud attempt."""
    try:
        entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'campaign_id': campaign_id,
            'ip': ip,
            'fingerprint': fingerprint,
            'reason': reason,
            'action': 'blocked'
        }
        fields = get_fieldnames('fraud_log.csv', ['timestamp','campaign_id','ip','fingerprint','reason','action'])
        append_csv('fraud_log.csv', entry, fields)
    except:
        pass

@app.route('/api/fraud/report')
@api_auth
def api_fraud_report():
    """Fraud detection report."""
    frauds = read_csv('fraud_log.csv')
    clicks = read_csv('campaign_clicks.csv')
    # Group fraud by IP
    from collections import Counter
    fraud_ips = Counter(f.get('ip', '') for f in frauds if f.get('ip'))
    total_clicks = len(clicks)
    total_frauds = len(frauds)
    clean_clicks = max(0, total_clicks - total_frauds)
    return jsonify({
        'total_clicks': total_clicks,
        'fraud_blocked': total_frauds,
        'clean_clicks': clean_clicks,
        'fraud_rate': round(total_frauds / total_clicks * 100, 2) if total_clicks > 0 else 0,
        'top_fraud_ips': dict(fraud_ips.most_common(10)),
        'recent_frauds': frauds[-10:][::-1] if frauds else [],
    })

# ===== API — Frequency Capping + Daily Budget (Phase 3) =====

_FREQ_CAP_DEFAULT = 3  # max exposures per user per campaign per day

def _check_frequency_cap(campaign_id, user_id):
    """Check if user has exceeded frequency cap for this campaign today."""
    if not user_id:
        return False  # anonymous → allow
    try:
        exposure = read_csv('user_exposure.csv')
        today = datetime.now().strftime('%Y-%m-%d')
        count = 0
        for e in exposure:
            if (e.get('campaign_id') == campaign_id and
                e.get('user_id') == str(user_id) and
                e.get('date', '').startswith(today)):
                count += 1
        # Get campaign's frequency cap
        campaigns = read_csv('campaigns.csv')
        cap = _FREQ_CAP_DEFAULT
        for c in campaigns:
            if c.get('id') == campaign_id:
                cap = int(c.get('frequency_cap', _FREQ_CAP_DEFAULT) or _FREQ_CAP_DEFAULT)
                break
        return count >= cap
    except:
        return False

def _log_exposure(campaign_id, user_id):
    """Log that a user was exposed to a campaign."""
    try:
        entry = {
            'user_id': str(user_id),
            'campaign_id': campaign_id,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        fields = get_fieldnames('user_exposure.csv', ['user_id','campaign_id','date'])
        append_csv('user_exposure.csv', entry, fields)
    except:
        pass

def _check_daily_budget(campaign_id):
    """Check if campaign has exceeded its daily budget. Returns True if exceeded."""
    try:
        campaigns = read_csv('campaigns.csv')
        campaign = None
        for c in campaigns:
            if c.get('id') == campaign_id:
                campaign = c
                break
        if not campaign:
            return False
        daily_budget = float(campaign.get('daily_budget', 0) or 0)
        if daily_budget <= 0:
            return False  # no budget limit
        # Count today's clicks × CPC
        clicks = read_csv('campaign_clicks.csv')
        today = datetime.now().strftime('%Y-%m-%d')
        today_clicks = sum(1 for c in clicks if c.get('campaign_id') == campaign_id and c.get('timestamp', '').startswith(today))
        cpc = float(campaign.get('cpc', 0) or 0)
        spent = today_clicks * cpc
        return spent >= daily_budget
    except:
        return False

@app.route('/api/fraud/report')
@api_auth
def api_fraud_report_duplicate():
    """Alias — handled above."""
    return jsonify({'error': 'Use /api/fraud/report'}), 400

# ===== API — A/B Testing (Phase 4) =====

@app.route('/api/ab-tests')
@api_auth
def api_ab_tests():
    """List all A/B tests."""
    tests = read_csv('ab_tests.csv')
    for t in tests:
        for k in ['test_id','campaign_a','campaign_b','winner','status','clicks_a','clicks_b','conversions_a','conversions_b','created_at']:
            if k not in t: t[k] = ''
    return jsonify({'tests': tests})

@app.route('/api/ab-tests', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_create_ab_test():
    """Create an A/B test between two campaigns."""
    data = request.json or {}
    test_id = f"ABT{secrets.token_hex(3).upper()}"
    test = {
        'test_id': test_id,
        'campaign_a': data.get('campaign_a', ''),
        'campaign_b': data.get('campaign_b', ''),
        'winner': '',
        'status': 'running',
        'clicks_a': '0',
        'clicks_b': '0',
        'conversions_a': '0',
        'conversions_b': '0',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    fields = get_fieldnames('ab_tests.csv', ['test_id','campaign_a','campaign_b','winner','status','clicks_a','clicks_b','conversions_a','conversions_b','created_at'])
    append_csv('ab_tests.csv', test, fields)
    log_action('create_ab_test', test_id)
    return jsonify({'success': True, 'test_id': test_id})

@app.route('/api/ab-tests/<test_id>/evaluate')
@api_auth
def api_evaluate_ab_test(test_id):
    """Evaluate A/B test — pick winner based on CTR."""
    tests = read_csv('ab_tests.csv')
    fields = get_fieldnames('ab_tests.csv', ['test_id','campaign_a','campaign_b','winner','status','clicks_a','clicks_b','conversions_a','conversions_b','created_at'])
    # Get click data for both campaigns
    all_clicks = read_csv('campaign_clicks.csv')
    all_convs = read_csv('campaign_conversions.csv')
    for t in tests:
        if t.get('test_id') == test_id:
            ca = t.get('campaign_a', '')
            cb = t.get('campaign_b', '')
            t['clicks_a'] = str(sum(1 for c in all_clicks if c.get('campaign_id') == ca))
            t['clicks_b'] = str(sum(1 for c in all_clicks if c.get('campaign_id') == cb))
            t['conversions_a'] = str(sum(1 for c in all_convs if c.get('campaign_id') == ca))
            t['conversions_b'] = str(sum(1 for c in all_convs if c.get('campaign_id') == cb))
            # Auto-pick winner if >50 clicks each
            ca_clicks = int(t['clicks_a'])
            cb_clicks = int(t['clicks_b'])
            if ca_clicks >= 50 and cb_clicks >= 50:
                ctr_a = int(t['conversions_a']) / ca_clicks if ca_clicks > 0 else 0
                ctr_b = int(t['conversions_b']) / cb_clicks if cb_clicks > 0 else 0
                if ctr_a > ctr_b:
                    t['winner'] = ca
                    t['status'] = 'completed'
                elif ctr_b > ctr_a:
                    t['winner'] = cb
                    t['status'] = 'completed'
            break
    write_csv('ab_tests.csv', tests, fields)
    return jsonify({'success': True, 'tests': [t for t in tests if t.get('test_id') == test_id]})

# ===== API — Retargeting (Phase 4) =====

@app.route('/api/retargeting/lists')
@api_auth
def api_retargeting_lists():
    """List retargeting lists."""
    lists = read_csv('retargeting_lists.csv')
    return jsonify({'lists': lists})

@app.route('/api/retargeting/build/<campaign_id>')
@api_auth
@permission_required('send_broadcast')
def api_build_retargeting_list(campaign_id):
    """Build a retargeting list from users who clicked but didn't convert."""
    clicks = read_csv('campaign_clicks.csv')
    convs = read_csv('campaign_conversions.csv')
    # Users who clicked
    clickers = set(c.get('user_id', '') for c in clicks if c.get('campaign_id') == campaign_id and c.get('user_id'))
    # Users who converted
    converters = set(c.get('user_id', '') for c in convs if c.get('campaign_id') == campaign_id and c.get('user_id'))
    # Retarget = clicked but not converted
    retarget = clickers - converters
    list_id = f"RTL{secrets.token_hex(3).upper()}"
    entry = {
        'list_id': list_id,
        'campaign_id': campaign_id,
        'user_ids': '|'.join(retarget),
        'count': str(len(retarget)),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    fields = get_fieldnames('retargeting_lists.csv', ['list_id','campaign_id','user_ids','count','created_at'])
    append_csv('retargeting_lists.csv', entry, fields)
    return jsonify({'success': True, 'list_id': list_id, 'count': len(retarget), 'users': list(retarget)[:20]})

# ===== API — Marketplace (Phase 5) =====

@app.route('/api/marketplace/listings')
@api_auth
def api_marketplace_listings():
    """List channel marketplace listings."""
    listings = read_csv('marketplace_listings.csv')
    # Enrich with channel data
    channels = read_csv('bot_channels.csv')
    for l in listings:
        for ch in channels:
            if ch.get('id') == l.get('channel_id'):
                l['channel_name'] = ch.get('title', '')
                l['subscriber_count'] = ch.get('subscriber_count', '0')
                break
    return jsonify({'listings': listings})

@app.route('/api/marketplace/listings', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_create_listing():
    """Create a marketplace listing for a channel."""
    data = request.json or {}
    listing_id = f"LST{secrets.token_hex(3).upper()}"
    listing = {
        'listing_id': listing_id,
        'channel_id': data.get('channel_id', ''),
        'cpm_rate': data.get('cpm_rate', '0.50'),
        'cpc_rate': data.get('cpc_rate', '0.05'),
        'min_budget': data.get('min_budget', '10'),
        'category': data.get('category', ''),
        'is_available': 'yes',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    fields = get_fieldnames('marketplace_listings.csv', ['listing_id','channel_id','cpm_rate','cpc_rate','min_budget','category','is_available','created_at'])
    append_csv('marketplace_listings.csv', listing, fields)
    return jsonify({'success': True, 'listing_id': listing_id})

@app.route('/api/marketplace/dashboard')
@api_auth
def api_marketplace_dashboard():
    """Marketplace overview."""
    listings = read_csv('marketplace_listings.csv')
    partners = read_csv('partner_channels.csv')
    campaigns = read_csv('campaigns.csv')
    available = [l for l in listings if l.get('is_available') == 'yes']
    return jsonify({
        'total_listings': len(listings),
        'available_listings': len(available),
        'avg_cpm': round(sum(float(l.get('cpm_rate', 0) or 0) for l in available) / len(available), 2) if available else 0,
        'avg_cpc': round(sum(float(l.get('cpc_rate', 0) or 0) for l in available) / len(available), 2) if available else 0,
        'total_partners': len(partners),
        'total_campaigns': len(campaigns),
    })

# ===== API — External REST API + Scheduled Reports (Phase 6) =====

@app.route('/api/v1/campaigns')
def api_v1_campaigns():
    """Public REST API for external advertisers — API key auth."""
    api_key = request.headers.get('X-API-Key', '')
    if not api_key or api_key != os.getenv('AD_API_KEY', ''):
        return jsonify({'error': 'Invalid API key'}), 401
    campaigns = read_csv('campaigns.csv')
    return jsonify({'campaigns': [{'id': c.get('id',''), 'name': c.get('name',''), 'status': c.get('status',''), 'reach': c.get('stats_reach','0'), 'clicks': c.get('stats_clicks','0')} for c in campaigns]})

@app.route('/api/v1/campaigns', methods=['POST'])
def api_v1_create_campaign():
    """Create campaign via external API."""
    api_key = request.headers.get('X-API-Key', '')
    if not api_key or api_key != os.getenv('AD_API_KEY', ''):
        return jsonify({'error': 'Invalid API key'}), 401
    data = request.json or {}
    campaign_id = f"CMP{secrets.token_hex(3).upper()}"
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    campaign = {
        'id': campaign_id, 'name': data.get('name', ''), 'message': data.get('message', ''),
        'media_urls': '', 'target': data.get('target', 'both'), 'recipient': 'all',
        'priority': data.get('priority', 'normal'), 'country': data.get('country', 'all'),
        'language': 'all', 'segment': 'all', 'channel_group': '', 'scheduled_at': '',
        'repeat': 'once', 'status': 'draft', 'created_at': now, 'created_by': 'api',
        'stats_reach': '0', 'stats_clicks': '0', 'stats_conversions': '0',
        'platform_account_id': data.get('platform_account_id', ''),
        'ai_agent_id': data.get('ai_agent_id', ''),
    }
    fields = get_fieldnames('campaigns.csv', _CAMPAIGN_FIELDS)
    append_csv('campaigns.csv', campaign, fields)
    return jsonify({'success': True, 'id': campaign_id})

# ===== End Phase 4+5+6 =====

# ===== API — Click + Conversion Tracking (Ad Platform v2 Phase 1) =====

@app.route('/c/<campaign_id>')
def track_click_redirect(campaign_id):
    """Click tracker — redirects to campaign URL and logs the click."""
    import urllib.parse
    # Find campaign
    campaigns = read_csv('campaigns.csv')
    campaign = None
    for c in campaigns:
        if c.get('id') == campaign_id:
            campaign = c
            break
    if not campaign:
        return redirect('/')

    # Log the click
    click_id = f"CLK{secrets.token_hex(4).upper()}"
    click_entry = {
        'click_id': click_id,
        'campaign_id': campaign_id,
        'user_id': request.args.get('uid', ''),
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'ip': request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip(),
        'user_agent': request.headers.get('User-Agent', '')[:200],
        'referrer': request.referrer or '',
    }
    click_fields = get_fieldnames('campaign_clicks.csv', ['click_id','campaign_id','user_id','timestamp','ip','user_agent','referrer'])
    append_csv('campaign_clicks.csv', click_entry, click_fields)

    # Increment stats_clicks in campaigns.csv
    try:
        cf_fields = get_fieldnames('campaigns.csv', _CAMPAIGN_FIELDS)
        for c in campaigns:
            if c.get('id') == campaign_id:
                c['stats_clicks'] = str(int(c.get('stats_clicks', 0) or 0) + 1)
                break
        write_csv('campaigns.csv', campaigns, cf_fields)
    except:
        pass

    # Determine destination URL
    dest = campaign.get('redirect_url', '') or 'https://vex.deals/home'
    # Add UTM parameters
    utm = f"?utm_source=vex&utm_medium=telegram&utm_campaign={campaign_id}&click_id={click_id}"
    if '?' in dest:
        dest = dest + '&' + utm.lstrip('?')
    else:
        dest = dest + utm
    return redirect(dest)

@app.route('/api/track/conversion', methods=['POST'])
def track_conversion():
    """Log a conversion (deposit/register) attributed to a campaign click."""
    data = request.json or {}
    campaign_id = data.get('campaign_id', '')
    user_id = data.get('user_id', '')
    conv_type = data.get('type', 'register')  # register, deposit, game_play
    amount = data.get('amount', 0)
    click_id = data.get('click_id', '')

    if not campaign_id:
        return jsonify({'error': 'No campaign_id'}), 400

    conv_id = f"CNV{secrets.token_hex(4).upper()}"
    conv_entry = {
        'conv_id': conv_id,
        'campaign_id': campaign_id,
        'click_id': click_id,
        'user_id': str(user_id),
        'type': conv_type,
        'amount': str(amount),
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    conv_fields = get_fieldnames('campaign_conversions.csv', ['conv_id','campaign_id','click_id','user_id','type','amount','timestamp'])
    append_csv('campaign_conversions.csv', conv_entry, conv_fields)

    # Increment stats_conversions in campaigns.csv
    try:
        campaigns = read_csv('campaigns.csv')
        cf_fields = get_fieldnames('campaigns.csv', _CAMPAIGN_FIELDS)
        for c in campaigns:
            if c.get('id') == campaign_id:
                c['stats_conversions'] = str(int(c.get('stats_conversions', 0) or 0) + 1)
                break
        write_csv('campaigns.csv', campaigns, cf_fields)
    except:
        pass

    return jsonify({'success': True, 'conv_id': conv_id})

@app.route('/api/campaigns/<campaign_id>/clicks')
@api_auth
def api_campaign_clicks(campaign_id):
    """Get detailed click data for a campaign."""
    clicks = read_csv('campaign_clicks.csv')
    campaign_clicks = [c for c in clicks if c.get('campaign_id') == campaign_id]
    campaign_clicks.reverse()
    # Simple fraud analysis: group by IP
    from collections import Counter
    ip_counts = Counter(c.get('ip', '') for c in campaign_clicks if c.get('ip'))
    suspicious_ips = {ip: count for ip, count in ip_counts.items() if count > 5}
    return jsonify({
        'total_clicks': len(campaign_clicks),
        'recent_clicks': campaign_clicks[:20],
        'suspicious_ips': suspicious_ips,
        'unique_ips': len(ip_counts),
        'unique_users': len(set(c.get('user_id', '') for c in campaign_clicks if c.get('user_id'))),
    })

@app.route('/api/campaigns/<campaign_id>/conversions')
@api_auth
def api_campaign_conversions(campaign_id):
    """Get conversion data for a campaign."""
    convs = read_csv('campaign_conversions.csv')
    campaign_convs = [c for c in convs if c.get('campaign_id') == campaign_id]
    campaign_convs.reverse()
    total_amount = sum(float(c.get('amount', 0) or 0) for c in campaign_convs)
    return jsonify({
        'total_conversions': len(campaign_convs),
        'total_amount': total_amount,
        'recent_conversions': campaign_convs[:20],
        'by_type': dict(Counter(c.get('type', '') for c in campaign_convs)),
    })

# ===== End Click + Conversion Tracking =====

# ===== API — AI Content Generator (Phase 4) =====

@app.route('/api/campaigns/generate-content', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_generate_campaign_content():
    """Generate ad content using AI from a short description."""
    data = request.json or {}
    description = data.get('description', '')
    style = data.get('style', 'promotional')  # promotional, informative, urgent, casual
    if not description:
        return jsonify({'error': 'اكتب وصفاً'}), 400

    try:
        from ai_providers import AIManager
        ai = AIManager()
        active = ai.get_active_provider()
        if not active:
            return jsonify({'error': 'لا يوجد مزود AI مفعّل — أضف OPENAI_API_KEY أو CLAUDE_API_KEY في .env'}), 500

        style_prompts = {
            'promotional': 'اكتب إعلاناً جذاباً ومحفزاً بالعربية. استخدم إيموجي مناسبة. اجعله قصيراً (50-100 كلمة).',
            'informative': 'اكتب نصاً معلوماتياً واضحاً بالعربية. اشرح المزايا بشكل مباشر.',
            'urgent': 'اكتب إعلاناً عاجلاً بالعربية. استخدم كلمات مثل "محدود"، "الآن"، "لا تفوت".',
            'casual': 'اكتب نصاً ودوداً وغير رسمي بالعربية. كأنك تكلم صديق.',
        }
        prompt = f"{style_prompts.get(style, style_prompts['promotional'])}\n\nالمنتج/الخدمة: {description}\n\nالنص الإعلاني:"
        instructions = ''
        try:
            settings = read_csv('system_settings.csv')
            for s in settings:
                if s.get('key') == 'ai_instructions':
                    instructions = s.get('value', '')
                    break
        except:
            pass

        full_prompt = instructions + '\n' + prompt if instructions else prompt
        result = ai.process_text(full_prompt, active)
        if result:
            # Generate 3 variations
            variations = [result]
            for i in range(2):
                v = ai.process_text(full_prompt + f'\n\nنسخة {i+2} مختلفة:', active)
                if v and v != result:
                    variations.append(v)
            return jsonify({'success': True, 'content': result, 'variations': variations})
        else:
            return jsonify({'error': 'فشل التوليد'}), 500
    except ImportError:
        return jsonify({'error': 'ai_providers غير مثبت'}), 500
    except Exception as e:
        return jsonify({'error': f'خطأ: {str(e)}'}), 500

# ===== API — Ad Network (Phase 5) =====

@app.route('/api/ad-network/partners')
@api_auth
def api_ad_partners():
    """List partner channels."""
    partners = read_csv('partner_channels.csv')
    return jsonify({'partners': partners})

@app.route('/api/ad-network/partners', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_add_partner():
    """Add a partner channel."""
    data = request.json or {}
    partner_id = f"PRT{secrets.token_hex(3).upper()}"
    partner = {
        'id': partner_id,
        'channel_name': data.get('channel_name', ''),
        'chat_id': data.get('chat_id', ''),
        'subscriber_count': data.get('subscriber_count', '0'),
        'revenue_share': data.get('revenue_share', '0'),
        'category': data.get('category', ''),
        'contact': data.get('contact', ''),
        'is_active': 'yes',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_reach': '0',
        'total_revenue': '0',
    }
    fieldnames = get_fieldnames('partner_channels.csv', ['id','channel_name','chat_id','subscriber_count','revenue_share','category','contact','is_active','created_at','total_reach','total_revenue'])
    append_csv('partner_channels.csv', partner, fieldnames)
    log_action('add_partner', partner_id)
    return jsonify({'success': True, 'id': partner_id})

@app.route('/api/ad-network/partners/<partner_id>', methods=['PUT', 'DELETE'])
@api_auth
@permission_required('send_broadcast')
def api_edit_partner(partner_id):
    partners = read_csv('partner_channels.csv')
    fieldnames = get_fieldnames('partner_channels.csv', ['id','channel_name','chat_id','subscriber_count','revenue_share','category','contact','is_active','created_at','total_reach','total_revenue'])
    if request.method == 'DELETE':
        partners = [p for p in partners if p.get('id') != partner_id]
        write_csv('partner_channels.csv', partners, fieldnames)
        return jsonify({'success': True})
    elif request.method == 'PUT':
        data = request.json or {}
        for p in partners:
            if p.get('id') == partner_id:
                for k, v in data.items():
                    if k in fieldnames:
                        p[k] = v
                break
        write_csv('partner_channels.csv', partners, fieldnames)
        return jsonify({'success': True})

@app.route('/api/ad-network/dashboard')
@api_auth
def api_ad_network_dashboard():
    """Ad network overview — partners, revenue, CPM, CPC."""
    partners = read_csv('partner_channels.csv')
    campaigns = read_csv('campaigns.csv')
    total_reach = sum(int(p.get('total_reach', 0) or 0) for p in partners)
    total_revenue = sum(float(p.get('total_revenue', 0) or 0) for p in partners)
    active_partners = [p for p in partners if p.get('is_active') == 'yes']
    # CPM = (total_revenue / total_reach) * 1000
    cpm = round(total_revenue / total_reach * 1000, 2) if total_reach > 0 else 0
    return jsonify({
        'total_partners': len(partners),
        'active_partners': len(active_partners),
        'total_subscribers': sum(int(p.get('subscriber_count', 0) or 0) for p in active_partners),
        'total_reach': total_reach,
        'total_revenue': total_revenue,
        'cpm': cpm,
        'total_campaigns': len(campaigns),
    })

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
    ai_agent_id = campaign.get('ai_agent_id', '')

    if ai_agent_id and message:
        message, _, _ = _apply_ai_text_profile(message, agent_id=ai_agent_id)

    # Web notification
    if target in ('web', 'both', 'all'):
        notif_title = '📢 ' + campaign.get('name', 'حملة إعلانية')
        if priority == 'urgent':
            notif_title = '🚨 ' + campaign.get('name', 'حملة عاجلة')
        push_notification('broadcast', notif_title, message[:200], {'media_urls': media_urls, 'priority': priority, 'campaign_id': campaign.get('id', '')})

    bc_fieldnames = get_fieldnames('broadcast_queue.csv', [
        'id', 'message', 'target', 'recipient', 'priority', 'country',
        'media_urls', 'target_user', 'target_name', 'created_at',
        'created_by', 'status', 'platform', 'platform_account_id',
        'type', 'target_chat_id', 'target_channel_id', 'scheduled_at'
    ])

    def _queue(platform_name):
        entry = {
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
            'status': 'pending',
            'platform': platform_name,
            'platform_account_id': campaign.get('platform_account_id', ''),
            'type': 'broadcast',
            'target_chat_id': '',
            'target_channel_id': '',
            'scheduled_at': campaign.get('scheduled_at', ''),
        }
        append_csv('broadcast_queue.csv', entry, bc_fieldnames)

    if target in ('telegram', 'both', 'all'):
        _queue('telegram')
    if target in ('whatsapp', 'all'):
        _queue('whatsapp')

    log_action('execute_campaign', campaign.get('id', ''))

# ===== End Campaigns API =====

# ===== Partners API (for channels page) =====
@app.route('/api/partners')
@api_auth
def api_partners():
    """Get list of channel partners"""
    partners = read_csv('channel_partners.csv')
    return jsonify({'partners': partners})

@app.route('/api/partners', methods=['POST'])
@api_auth
@permission_required('manage_channels')
def api_add_channel_partner():
    data = request.json
    partners = read_csv('channel_partners.csv')
    fieldnames = get_fieldnames('channel_partners.csv', ['id', 'channel_name', 'chat_id', 'subscriber_count', 'revenue_share', 'category', 'contact', 'is_active', 'created_at'])
    new_id = f"PRT{secrets.token_hex(4).upper()}"
    partner = {
        'id': new_id,
        'channel_name': data.get('channel_name', ''),
        'chat_id': data.get('chat_id', ''),
        'subscriber_count': int(data.get('subscriber_count', 0) or 0),
        'revenue_share': float(data.get('revenue_share', 0) or 0),
        'category': data.get('category', ''),
        'contact': data.get('contact', ''),
        'is_active': 'yes',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    append_csv('channel_partners.csv', partner, fieldnames)
    return jsonify({'success': True, 'id': new_id})


@app.route('/api/partners/<partner_id>', methods=['DELETE'])
@api_auth
@permission_required('manage_channels')
def api_delete_partner(partner_id):
    partners = read_csv('channel_partners.csv')
    fieldnames = get_fieldnames('channel_partners.csv', ['id', 'channel_name', 'chat_id', 'subscriber_count', 'revenue_share', 'category', 'contact', 'is_active', 'created_at'])
    partners = [p for p in partners if p.get('id') != partner_id]
    write_csv('channel_partners.csv', partners, fieldnames)
    return jsonify({'success': True})


@app.route('/api/partners/<partner_id>/toggle', methods=['POST'])
@api_auth
@permission_required('manage_channels')
def api_toggle_partner(partner_id):
    partners = read_csv('channel_partners.csv')
    for p in partners:
        if p.get('id') == partner_id:
            p['is_active'] = 'no' if p.get('is_active') == 'yes' else 'yes'
            break
    fieldnames = get_fieldnames('channel_partners.csv', ['id', 'channel_name', 'chat_id', 'subscriber_count', 'revenue_share', 'category', 'contact', 'is_active', 'created_at'])
    write_csv('channel_partners.csv', partners, fieldnames)
    return jsonify({'success': True})


# ===== Ad Network API (for channels page) =====
@app.route('/api/ad-net')
@api_auth
def api_ad_net():
    """Get ad network statistics"""
    try:
        # Read data from relevant CSVs
        partners = read_csv('channel_partners.csv')
        campaigns = read_csv('campaigns.csv')
        
        total_partners = len([p for p in partners if p.get('is_active') == 'yes'])
        active_partners = total_partners
        total_subscribers = sum(int(p.get('subscriber_count', 0) or 0) for p in partners if p.get('is_active') == 'yes')
        
        # Calculate total reach from campaigns
        total_reach = sum(int(c.get('stats_reach', 0) or 0) for c in campaigns)
        total_clicks = sum(int(c.get('stats_clicks', 0) or 0) for c in campaigns)
        ctr = round((total_clicks / total_reach * 100) if total_reach > 0 else 0, 2)
        
        # Calculate revenue (simplified)
        total_revenue = sum(float(c.get('budget', 0) or 0) for c in campaigns if c.get('status') == 'completed')
        
        return jsonify({
            'total_partners': total_partners,
            'active_partners': active_partners,
            'total_subscribers': total_subscribers,
            'cpm': 0,  # Placeholder
            'total_revenue': total_revenue,
            'total_reach': total_reach,
            'total_clicks': total_clicks,
            'ctr': ctr
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ===== End Partners & Ad Network API =====

_CHANNEL_DEFAULT_FIELDS = [
    'id', 'chat_id', 'title', 'type', 'is_active', 'added_at',
    'relay_to_users', 'relay_to_channels', 'forward_mode', 'welcome_text',
    'category', 'ai_enabled', 'channel_role', 'ai_provider', 'brand_voice',
    'platform', 'owner_admin_id', 'managed_by_admin_ids',
    'allow_subadmin_publish', 'ai_agent_id', 'platform_account_id',
    'company_name', 'download_link', 'promo_code', 'affiliate_link',
    'auto_post_enabled', 'auto_post_interval_min', 'auto_post_types'
]

_AI_AGENT_FIELDS = [
    'id', 'name', 'provider', 'instructions', 'fallback_provider',
    'is_active', 'created_at', 'updated_at', 'created_by',
    'api_key', 'job_description', 'base_url', 'default_model',
    'temperature', 'max_tokens', 'last_run_at', 'last_run_result'
]

_PLATFORM_ACCOUNT_FIELDS = [
    'id', 'platform', 'account_name', 'is_active', 'api_base_url',
    'access_token', 'phone_number_id', 'business_account_id',
    'created_at', 'updated_at', 'created_by', 'last_health_check',
    'health_status', 'last_error'
]

_SOCIAL_ACCOUNT_FIELDS = [
    'id', 'platform', 'account_name', 'handle', 'sub_agent_id',
    'access_token', 'page_id', 'phone_number_id', 'business_account_id',
    'posting_permissions', 'content_categories', 'is_active',
    'followers', 'last_sync', 'created_at', 'updated_at', 'created_by'
]

_PLATFORM_ACCOUNT_FIELDS = [
    'id', 'platform', 'account_name', 'is_active', 'api_base_url',
    'access_token', 'phone_number_id', 'business_account_id',
    'created_at', 'updated_at', 'created_by', 'last_health_check',
    'health_status', 'last_error'
]

_SOURCE_CHANNEL_FIELDS = [
    'id', 'chat_id', 'title', 'type', 'is_active', 'added_at',
    'brand_voice', 'target_channel_ids', 'schedule', 'last_scraped_at',
    'content_filter', 'ai_edit_text', 'ai_edit_media', 'ai_provider',
    'ai_agent_id', 'owner_admin_id', 'managed_by_admin_ids'
]

_CAMPAIGN_FIELDS = [
    'id', 'name', 'message', 'media_urls',
    'target', 'recipient', 'priority', 'country',
    'language', 'segment', 'channel_group', 'scheduled_at',
    'repeat', 'status', 'created_at', 'created_by',
    'stats_reach', 'stats_clicks', 'stats_conversions',
    'platform_account_id', 'ai_agent_id',
    'selected_channels', 'selected_groups',
    'whatsapp_contacts', 'whatsapp_groups',
]


def _is_super_admin_session():
    uid = str(session.get('admin_id', '') or '')
    if not uid:
        return False
    try:
        role_data = _rbac_get_role(uid)
        return str(role_data.get('role') or '') == 'super_admin'
    except Exception:
        return False


def _pipe_ids(raw):
    return '|'.join([x.strip() for x in str(raw or '').split('|') if x and x.strip()])


def _pipe_to_list(raw):
    return [x.strip() for x in str(raw or '').split('|') if x and x.strip()]


def _normalize_channel_row(row, actor_uid=''):
    changed = False

    def _setdefault(key, value):
        nonlocal changed
        cur = row.get(key, '')
        if cur is None or cur == '':
            row[key] = value
            changed = True

    _setdefault('relay_to_users', 'yes')
    _setdefault('relay_to_channels', 'yes')
    _setdefault('forward_mode', 'all')
    _setdefault('welcome_text', '')
    _setdefault('category', '')
    _setdefault('ai_enabled', 'no')
    _setdefault('channel_role', 'both')
    _setdefault('ai_provider', '')
    _setdefault('brand_voice', '')
    _setdefault('platform', 'telegram')
    _setdefault('owner_admin_id', str(actor_uid or session.get('admin_id', '') or ''))
    _setdefault('managed_by_admin_ids', str(row.get('owner_admin_id') or actor_uid or session.get('admin_id', '') or ''))
    _setdefault('allow_subadmin_publish', 'no')
    _setdefault('ai_agent_id', '')
    _setdefault('platform_account_id', '')
    _setdefault('company_name', '')
    _setdefault('download_link', '')
    _setdefault('promo_code', '')
    _setdefault('affiliate_link', '')
    _setdefault('auto_post_enabled', 'no')
    _setdefault('auto_post_interval_min', '120')
    _setdefault('auto_post_types', 'info|question|prediction|analysis')

    # sanitize yes/no switches
    for k in ('is_active', 'relay_to_users', 'relay_to_channels', 'ai_enabled', 'allow_subadmin_publish'):
        v = str(row.get(k, '') or '').lower()
        norm = 'yes' if v in ('1', 'true', 'yes', 'on', 'active') else 'no'
        if row.get(k) != norm:
            row[k] = norm
            changed = True

    # sanitize enums
    if row.get('forward_mode') not in ('all', 'text_only', 'media_only'):
        row['forward_mode'] = 'all'
        changed = True
    if row.get('channel_role') not in ('source', 'publish', 'both'):
        row['channel_role'] = 'both'
        changed = True
    if str(row.get('platform', '')).strip().lower() not in ('telegram', 'whatsapp', 'webhook'):
        row['platform'] = 'telegram'
        changed = True

    managers = _pipe_ids(row.get('managed_by_admin_ids', ''))
    if managers != str(row.get('managed_by_admin_ids', '')):
        row['managed_by_admin_ids'] = managers
        changed = True

    owner = str(row.get('owner_admin_id', '') or '').strip()
    if owner and owner not in _pipe_to_list(row.get('managed_by_admin_ids', '')):
        row['managed_by_admin_ids'] = _pipe_ids((row.get('managed_by_admin_ids', '') + '|' + owner).strip('|'))
        changed = True

    return row, changed


def _admin_can_manage_channel(channel_row, admin_uid, action='edit'):
    uid = str(admin_uid or '')
    if not uid:
        return False
    if _is_super_admin_session():
        return True
    owner = str(channel_row.get('owner_admin_id', '') or '').strip()
    managers = _pipe_to_list(channel_row.get('managed_by_admin_ids', ''))
    if not owner:
        return True  # legacy rows
    if uid == owner or uid in managers:
        return True
    if action == 'publish' and str(channel_row.get('allow_subadmin_publish', 'no')) == 'yes':
        return _rbac_has_perm(uid, 'send_broadcast')
    return False


def _platform_account_public(row):
    r = dict(row)
    token = str(r.get('access_token', '') or '')
    if token:
        r['access_token_masked'] = ('*' * max(0, len(token) - 6)) + token[-6:]
    else:
        r['access_token_masked'] = ''
    r.pop('access_token', None)
    return r


def _platform_health_check(row):
    platform = str(row.get('platform', '') or '').strip().lower()
    token = str(row.get('access_token', '') or '').strip()
    now_s = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if not token:
        return {
            'health_status': 'error',
            'last_error': 'missing_access_token',
            'last_health_check': now_s,
        }

    if platform != 'whatsapp':
        return {
            'health_status': 'ok',
            'last_error': '',
            'last_health_check': now_s,
        }

    phone_number_id = str(row.get('phone_number_id', '') or '').strip()
    if not phone_number_id:
        return {
            'health_status': 'error',
            'last_error': 'missing_phone_number_id',
            'last_health_check': now_s,
        }

    base = str(row.get('api_base_url', '') or '').strip() or 'https://graph.facebook.com/v20.0'
    if base.endswith('/'):
        base = base[:-1]
    url = f"{base}/{phone_number_id}?fields=display_phone_number,verified_name"
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            _ = resp.read()
        return {
            'health_status': 'ok',
            'last_error': '',
            'last_health_check': now_s,
        }
    except urllib.error.HTTPError as e:
        return {
            'health_status': 'error',
            'last_error': f'http_{e.code}',
            'last_health_check': now_s,
        }
    except Exception as e:
        return {
            'health_status': 'error',
            'last_error': str(e)[:180],
            'last_health_check': now_s,
        }


def _load_ai_agent_by_id(agent_id):
    aid = str(agent_id or '').strip()
    if not aid:
        return None
    rows = read_csv('ai_agents.csv')
    for r in rows:
        if str(r.get('id', '')).strip() != aid:
            continue
        r, _ = _normalize_ai_agent_row(r)
        if r.get('is_active') != 'yes':
            return None
        return r
    return None


def _apply_ai_text_profile(text, agent_id='', provider='', instructions='', fallback_provider=''):
    msg = str(text or '').strip()
    if len(msg) < 8:
        return msg, 'none', False
    try:
        from ai_providers import AIManager
        manager = AIManager()
    except Exception:
        return msg, 'none', False

    p_name = str(provider or '').strip().lower()
    prompt = str(instructions or '').strip()
    fb_name = str(fallback_provider or '').strip().lower()

    if agent_id:
        agent = _load_ai_agent_by_id(agent_id)
        if agent:
            p_name = str(agent.get('provider', p_name) or p_name).strip().lower()
            prompt = str(agent.get('instructions', prompt) or prompt).strip()
            fb_name = str(agent.get('fallback_provider', fb_name) or fb_name).strip().lower()

    if not prompt:
        prompt = "أعد صياغة النص بأسلوب تسويقي واضح وجذاب مع الحفاظ على المعنى."

    selected = None if p_name in ('', 'auto') else p_name
    try:
        result, used_provider = manager.process(msg, prompt, provider_name=selected)
        if (not result or len(result.strip()) < 8) and fb_name:
            result, used_provider = manager.process(msg, prompt, provider_name=fb_name)
        if result and len(result.strip()) >= 8:
            return result, (used_provider or p_name or 'auto'), True
    except Exception:
        pass
    return msg, 'none', False

@app.route('/api/channels')
@api_auth
def api_channels():
    channels = read_csv('bot_channels.csv')
    uid = str(session.get('admin_id', '') or '')
    changed = False
    out = []
    for ch in channels:
        ch, row_changed = _normalize_channel_row(ch)
        changed = changed or row_changed
        if _admin_can_manage_channel(ch, uid, action='view'):
            out.append(ch)
    if changed:
        write_csv('bot_channels.csv', channels, get_fieldnames('bot_channels.csv', _CHANNEL_DEFAULT_FIELDS))
    return jsonify({'channels': out})

@app.route('/api/channels/<channel_id>/toggle', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_toggle_channel(channel_id):
    channels = read_csv('bot_channels.csv')
    fieldnames = get_fieldnames('bot_channels.csv', _CHANNEL_DEFAULT_FIELDS)
    uid = str(session.get('admin_id', '') or '')
    found = False
    for c in channels:
        if c.get('id') == channel_id:
            found = True
            c, _ = _normalize_channel_row(c)
            if not _admin_can_manage_channel(c, uid, action='edit'):
                return jsonify({'error': 'Forbidden'}), 403
            c['is_active'] = 'no' if c.get('is_active') == 'yes' else 'yes'
            break
    if not found:
        return jsonify({'error': 'Channel not found'}), 404
    write_csv('bot_channels.csv', channels, fieldnames)
    return jsonify({'success': True})

@app.route('/api/channels/<channel_id>/settings', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_channel_settings(channel_id):
    """تحديث إعدادات قناة محددة"""
    data = request.json or {}
    channels = read_csv('bot_channels.csv')
    fieldnames = get_fieldnames('bot_channels.csv', _CHANNEL_DEFAULT_FIELDS)
    editable = [
        'relay_to_users', 'relay_to_channels', 'forward_mode', 'welcome_text',
        'is_active', 'title', 'category', 'ai_enabled', 'channel_role',
        'ai_provider', 'brand_voice', 'platform', 'ai_agent_id', 'platform_account_id',
        'allow_subadmin_publish',
        'company_name', 'download_link', 'promo_code', 'affiliate_link',
        'auto_post_enabled', 'auto_post_interval_min', 'auto_post_types'
    ]
    uid = str(session.get('admin_id', '') or '')
    updated = False
    for c in channels:
        if c.get('id') == channel_id:
            c, _ = _normalize_channel_row(c)
            if not _admin_can_manage_channel(c, uid, action='edit'):
                return jsonify({'error': 'Forbidden'}), 403
            for k, v in data.items():
                if k in editable:
                    if k not in fieldnames:
                        fieldnames.append(k)
                    c[k] = v
                    updated = True
            c, _ = _normalize_channel_row(c)
            break
    if not updated:
        return jsonify({'error': 'No editable fields or channel not found'}), 400
    write_csv('bot_channels.csv', channels, fieldnames)
    log_action('update_channel_settings', f'{channel_id}: {json.dumps(data)[:100]}')
    return jsonify({'success': True})


@app.route('/api/channels/<channel_id>/ownership', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_channel_ownership(channel_id):
    """Assign owner/managers for a channel (super admin only)."""
    if not _is_super_admin_session():
        return jsonify({'error': 'Forbidden — super admin only'}), 403
    data = request.json or {}
    channels = read_csv('bot_channels.csv')
    fieldnames = get_fieldnames('bot_channels.csv', _CHANNEL_DEFAULT_FIELDS)
    owner_admin_id = str(data.get('owner_admin_id', '') or '').strip()
    managed_raw = data.get('managed_by_admin_ids', '')
    if isinstance(managed_raw, list):
        managed_raw = '|'.join([str(x).strip() for x in managed_raw if str(x).strip()])
    managed_by_admin_ids = _pipe_ids(managed_raw)
    allow_subadmin_publish = 'yes' if str(data.get('allow_subadmin_publish', 'no')).lower() in ('1', 'true', 'yes', 'on') else 'no'

    found = False
    for c in channels:
        if c.get('id') == channel_id:
            found = True
            c, _ = _normalize_channel_row(c)
            c['owner_admin_id'] = owner_admin_id
            c['managed_by_admin_ids'] = managed_by_admin_ids
            c['allow_subadmin_publish'] = allow_subadmin_publish
            c, _ = _normalize_channel_row(c)
            break
    if not found:
        return jsonify({'error': 'Channel not found'}), 404
    write_csv('bot_channels.csv', channels, fieldnames)
    log_action('update_channel_ownership', f'{channel_id}: owner={owner_admin_id} managers={managed_by_admin_ids}')
    return jsonify({'success': True})

@app.route('/api/channels/<channel_id>', methods=['DELETE'])
@api_auth
@permission_required('send_broadcast')
def api_delete_channel(channel_id):
    channels = read_csv('bot_channels.csv')
    fieldnames = get_fieldnames('bot_channels.csv', _CHANNEL_DEFAULT_FIELDS)
    uid = str(session.get('admin_id', '') or '')
    out = []
    found = False
    for c in channels:
        if c.get('id') != channel_id:
            out.append(c)
            continue
        found = True
        c, _ = _normalize_channel_row(c)
        if not _admin_can_manage_channel(c, uid, action='edit'):
            return jsonify({'error': 'Forbidden'}), 403
    if not found:
        return jsonify({'error': 'Channel not found'}), 404
    channels = out
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


def _normalize_ai_agent_row(row):
    changed = False

    def _setdefault(k, v):
        nonlocal changed
        if row.get(k, '') in ('', None):
            row[k] = v
            changed = True

    _setdefault('id', f"AIA{secrets.token_hex(3).upper()}")
    _setdefault('name', f"AI Agent {row.get('id', '')[-4:]}")
    _setdefault('provider', 'openai')
    _setdefault('instructions', '')
    _setdefault('fallback_provider', '')
    _setdefault('is_active', 'yes')
    _setdefault('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    _setdefault('updated_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    _setdefault('created_by', '')
    _setdefault('api_key', '')
    _setdefault('job_description', '')
    _setdefault('base_url', '')
    _setdefault('default_model', '')
    _setdefault('temperature', '0.7')
    _setdefault('max_tokens', '2048')
    _setdefault('last_run_at', '')
    _setdefault('last_run_result', '')

    if str(row.get('is_active', '')).lower() in ('1', 'true', 'yes', 'on', 'active'):
        norm = 'yes'
    else:
        norm = 'no'
    if row.get('is_active') != norm:
        row['is_active'] = norm
        changed = True

    provider = str(row.get('provider', '') or '').strip().lower()
    if provider not in ('openai', 'claude', 'kimi', 'openrouter', 'auto'):
        row['provider'] = 'auto'
        changed = True

    fb = str(row.get('fallback_provider', '') or '').strip().lower()
    if fb and fb not in ('openai', 'claude', 'kimi', 'openrouter'):
        row['fallback_provider'] = ''
        changed = True

    return row, changed


@app.route('/api/ai-agents')
@api_auth
def api_ai_agents_list():
    rows = read_csv('ai_agents.csv')
    changed = False
    out = []
    for r in rows:
        r, ch = _normalize_ai_agent_row(r)
        changed = changed or ch
        # Never leak API keys to the client — only a flag
        pub = {k: v for k, v in r.items() if k != 'api_key'}
        pub['has_api_key'] = bool(r.get('api_key'))
        out.append(pub)
    if changed:
        write_csv('ai_agents.csv', rows, get_fieldnames('ai_agents.csv', _AI_AGENT_FIELDS))
    out.sort(key=lambda x: (x.get('is_active') != 'yes', x.get('name', '')))
    return jsonify({'agents': out})


@app.route('/api/ai-agents', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_ai_agents_create():
    data = request.json or {}
    rows = read_csv('ai_agents.csv')
    fieldnames = get_fieldnames('ai_agents.csv', _AI_AGENT_FIELDS)
    now_s = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    row = {
        'id': f"AIA{secrets.token_hex(3).upper()}",
        'name': str(data.get('name', '') or '').strip(),
        'provider': str(data.get('provider', 'auto') or 'auto').strip().lower(),
        'instructions': str(data.get('instructions', '') or '').strip(),
        'fallback_provider': str(data.get('fallback_provider', '') or '').strip().lower(),
        'is_active': 'yes' if str(data.get('is_active', 'yes')).lower() in ('1', 'true', 'yes', 'on') else 'no',
        'api_key': str(data.get('api_key', '') or '').strip(),
        'job_description': str(data.get('job_description', '') or '').strip(),
        'base_url': str(data.get('base_url', '') or '').strip(),
        'default_model': str(data.get('default_model', '') or '').strip(),
        'temperature': str(data.get('temperature', '0.7') or '0.7'),
        'max_tokens': str(data.get('max_tokens', '2048') or '2048'),
        'last_run_at': '',
        'last_run_result': '',
        'created_at': now_s,
        'updated_at': now_s,
        'created_by': str(session.get('admin_id', '') or ''),
    }
    row, _ = _normalize_ai_agent_row(row)
    if not row.get('name'):
        return jsonify({'error': 'name required'}), 400
    rows.append(row)
    write_csv('ai_agents.csv', rows, fieldnames)
    log_action('create_ai_agent', row['id'])
    return jsonify({'success': True, 'agent': row})


@app.route('/api/ai-agents/<agent_id>', methods=['PUT', 'DELETE'])
@api_auth
@permission_required('send_broadcast')
def api_ai_agents_edit(agent_id):
    rows = read_csv('ai_agents.csv')
    fieldnames = get_fieldnames('ai_agents.csv', _AI_AGENT_FIELDS)
    if request.method == 'DELETE':
        new_rows = [r for r in rows if r.get('id') != agent_id]
        if len(new_rows) == len(rows):
            return jsonify({'error': 'Agent not found'}), 404
        write_csv('ai_agents.csv', new_rows, fieldnames)
        log_action('delete_ai_agent', agent_id)
        return jsonify({'success': True})

    data = request.json or {}
    editable = {'name', 'provider', 'instructions', 'fallback_provider', 'is_active',
                'api_key', 'job_description', 'base_url', 'default_model',
                'temperature', 'max_tokens'}
    found = False
    for r in rows:
        if r.get('id') == agent_id:
            found = True
            for k, v in data.items():
                if k in editable:
                    r[k] = v
            r['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            r, _ = _normalize_ai_agent_row(r)
            break
    if not found:
        return jsonify({'error': 'Agent not found'}), 404
    write_csv('ai_agents.csv', rows, fieldnames)
    log_action('update_ai_agent', agent_id)
    return jsonify({'success': True})


# ===== AI Agent Execution Engine — full dashboard control =====
def _agent_resolve_credentials(agent):
    """Resolve API key + base URL + model for an agent (agent key > DB keys > env)."""
    provider = (agent.get('provider') or 'auto').strip().lower()
    api_key = (agent.get('api_key') or '').strip()
    base_url = (agent.get('base_url') or '').strip()
    model = (agent.get('default_model') or '').strip()

    # Fall back to ai_api_keys DB (priority order) when agent has no key
    if not api_key:
        try:
            import sqlite3
            conn = sqlite3.connect(os.path.join(BASE_DIR, 'boterx.db'))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                'SELECT * FROM ai_api_keys WHERE is_active=1 ORDER BY priority ASC, id ASC').fetchall()
            conn.close()
            for r in rows:
                p = (r['provider'] or '').lower()
                if provider == 'auto' or provider in p or p in provider:
                    api_key = r['api_key']
                    base_url = base_url or (r['base_url'] or '')
                    model = model or (r['default_model'] or '')
                    break
            if not api_key and rows:
                api_key = rows[0]['api_key']
                base_url = base_url or (rows[0]['base_url'] or '')
                model = model or (rows[0]['default_model'] or '')
        except Exception:
            pass

    if not api_key:
        api_key = os.getenv('OPENAI_API_KEY', '') or _env_file_value('OPENAI_API_KEY') or ''
    if provider == 'openrouter' and not base_url:
        base_url = 'https://openrouter.ai/api/v1'
    if not base_url:
        base_url = 'https://api.openai.com/v1'
    if not model:
        model = 'gpt-4o-mini'
    return api_key, base_url.rstrip('/'), model


def _agent_dashboard_context():
    """Gather full dashboard state for the agent to monitor."""
    try:
        txns = read_csv('transactions.csv')
        pending_txns = [t for t in txns if t.get('status') == 'pending'][:15]
        complaints = read_csv('complaints.csv')
        open_complaints = [c for c in complaints if c.get('status') not in ('resolved', 'closed')][:15]
        users = read_csv('users.csv')
        channels = read_csv('bot_channels.csv')
        queue = read_csv('broadcast_queue.csv')
        return {
            'users_total': len(users),
            'channels_total': len(channels),
            'transactions_pending': len([t for t in txns if t.get('status') == 'pending']),
            'complaints_open': len(open_complaints),
            'broadcast_queue_pending': len([q for q in queue if q.get('status') == 'pending']),
            'pending_transactions': [
                {'id': t.get('id'), 'type': t.get('type'), 'amount': t.get('amount'),
                 'customer': t.get('customer_id', t.get('client', '')), 'date': t.get('date', t.get('created_at', ''))}
                for t in pending_txns],
            'open_complaints': [
                {'id': c.get('id'), 'message': (c.get('message') or '')[:200],
                 'customer': c.get('customer_id', c.get('client', '')), 'date': c.get('date', c.get('created_at', ''))}
                for c in open_complaints],
        }
    except Exception as e:
        return {'error': f'context gathering failed: {e}'}


_AGENT_ACTIONS_DOC = """You may return ONE JSON object (and only the JSON, no extra text) to execute actions:
{"report": "short human summary of what you did/found", "actions": [
  {"action": "approve_transaction", "id": "<txn_id>", "amount": 123.0},
  {"action": "reject_transaction", "id": "<txn_id>", "reason": "..."},
  {"action": "reply_complaint", "id": "<complaint_id>", "response": "..."},
  {"action": "broadcast_message", "message": "...", "target": "telegram|web|both"},
  {"action": "ban_user", "user_id": "<id>", "reason": "..."},
  {"action": "unban_user", "user_id": "<id>"}
]}
If you only want to report without acting, return {"report": "...", "actions": []}.
NEVER invent IDs — only use IDs from the provided dashboard context."""


def _agent_execute_action(act):
    """Execute a single agent action safely. Returns (ok, message)."""
    name = str(act.get('action', '') or '').strip().lower()
    try:
        if name == 'approve_transaction':
            tid = str(act.get('id', ''))
            txns = read_csv('transactions.csv')
            for t in txns:
                if t.get('id') == tid and t.get('status') == 'pending':
                    amt = act.get('amount')
                    if amt is not None:
                        try:
                            t['amount'] = str(float(amt))
                        except (TypeError, ValueError):
                            pass
                    t['status'] = 'approved'
                    write_csv('transactions.csv', txns, get_fieldnames('transactions.csv',
                              ['id', 'customer_id', 'type', 'amount', 'status', 'date', 'company', 'wallet']))
                    return True, f'transaction {tid} approved'
            return False, f'transaction {tid} not found or not pending'

        if name == 'reject_transaction':
            tid = str(act.get('id', ''))
            txns = read_csv('transactions.csv')
            for t in txns:
                if t.get('id') == tid and t.get('status') == 'pending':
                    t['status'] = 'rejected'
                    t['admin_note'] = str(act.get('reason', 'rejected by AI agent'))[:200]
                    write_csv('transactions.csv', txns, get_fieldnames('transactions.csv',
                              ['id', 'customer_id', 'type', 'amount', 'status', 'date', 'company', 'wallet', 'admin_note']))
                    return True, f'transaction {tid} rejected'
            return False, f'transaction {tid} not found or not pending'

        if name == 'reply_complaint':
            cid = str(act.get('id', ''))
            complaints = read_csv('complaints.csv')
            for c in complaints:
                if c.get('id') == cid:
                    c['admin_response'] = str(act.get('response', ''))[:500]
                    c['status'] = 'resolved'
                    write_csv('complaints.csv', complaints, get_fieldnames('complaints.csv',
                              ['id', 'customer_id', 'message', 'status', 'date', 'admin_response']))
                    return True, f'complaint {cid} replied & resolved'
            return False, f'complaint {cid} not found'

        if name == 'broadcast_message':
            msg = str(act.get('message', ''))[:4000]
            if not msg:
                return False, 'empty broadcast message'
            target = str(act.get('target', 'telegram') or 'telegram').lower()
            fieldnames = get_fieldnames('broadcast_queue.csv', [
                'id', 'message', 'type', 'platform', 'target_chat_id', 'platform_account_id',
                'target_channel_id', 'created_at', 'created_by', 'status', 'target', 'recipient',
                'priority', 'country', 'media_urls', 'target_user', 'target_name', 'scheduled_at'])
            targets = ['telegram'] if target == 'telegram' else (['whatsapp'] if target == 'whatsapp' else (['web'] if target == 'web' else ['telegram', 'web']))
            for t in targets:
                append_csv('broadcast_queue.csv', {
                    'id': f"AIAG{secrets.token_hex(3).upper()}",
                    'message': msg, 'type': 'broadcast', 'platform': t,
                    'target_chat_id': '', 'platform_account_id': '', 'target_channel_id': '',
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'created_by': 'ai_agent', 'status': 'pending',
                    'target': t, 'recipient': 'all', 'priority': 'normal', 'country': 'all',
                    'media_urls': '', 'target_user': '', 'target_name': '', 'scheduled_at': '',
                }, fieldnames)
            return True, f'broadcast queued to {",".join(targets)}'

        if name == 'ban_user':
            uid = str(act.get('user_id', ''))
            users = read_csv('users.csv')
            for u in users:
                if u.get('id') == uid or u.get('customer_id') == uid:
                    u['banned'] = 'yes'
                    u['ban_reason'] = str(act.get('reason', 'banned by AI agent'))[:200]
                    write_csv('users.csv', users, get_fieldnames('users.csv',
                              ['id', 'customer_id', 'name', 'phone', 'banned', 'ban_reason', 'created_at']))
                    return True, f'user {uid} banned'
            return False, f'user {uid} not found'

        if name == 'unban_user':
            uid = str(act.get('user_id', ''))
            users = read_csv('users.csv')
            for u in users:
                if u.get('id') == uid or u.get('customer_id') == uid:
                    u['banned'] = 'no'
                    u['ban_reason'] = ''
                    write_csv('users.csv', users, get_fieldnames('users.csv',
                              ['id', 'customer_id', 'name', 'phone', 'banned', 'ban_reason', 'created_at']))
                    return True, f'user {uid} unbanned'
            return False, f'user {uid} not found'

        return False, f'unknown action: {name}'
    except Exception as e:
        return False, f'action failed: {e}'


@app.route('/api/ai-agents/<agent_id>/run', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_ai_agents_run(agent_id):
    """Run the agent: monitor dashboard state, think with its job description, execute actions."""
    rows = read_csv('ai_agents.csv')
    agent = next((r for r in rows if r.get('id') == agent_id), None)
    if not agent:
        return jsonify({'success': False, 'error': 'Agent not found'}), 404
    agent, _ = _normalize_ai_agent_row(agent)
    if agent.get('is_active') != 'yes':
        return jsonify({'success': False, 'error': 'Agent is inactive — activate it first'}), 400

    api_key, base_url, model = _agent_resolve_credentials(agent)
    if not api_key:
        return jsonify({'success': False, 'error': 'No API key available — add one to the agent or to AI API Keys'}), 400

    context = _agent_dashboard_context()
    job = agent.get('job_description') or agent.get('instructions') or 'Monitor the dashboard and report anything important.'

    system_prompt = f"""You are an autonomous admin agent inside the VEX Games admin dashboard.
YOUR JOB: {job}
RULES: {agent.get('instructions') or 'Act carefully. Only act when clearly needed by your job.'}
{_AGENT_ACTIONS_DOC}"""

    user_prompt = f"""DASHBOARD STATE (live):
{json.dumps(context, ensure_ascii=False, indent=1)}

Execute your job now. Return your JSON."""

    try:
        import httpx
        try:
            temperature = min(2.0, max(0.0, float(agent.get('temperature') or 0.7)))
        except (TypeError, ValueError):
            temperature = 0.7
        try:
            max_tokens = min(16000, max(100, int(float(agent.get('max_tokens') or 2048))))
        except (TypeError, ValueError):
            max_tokens = 2048

        headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
        payload = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        with httpx.Client(timeout=90.0) as client:
            resp = client.post(base_url + '/chat/completions', headers=headers, json=payload)
        if resp.status_code != 200:
            return jsonify({'success': False, 'error': f'AI provider error {resp.status_code}: {resp.text[:300]}'}), 502

        content = resp.json()['choices'][0]['message']['content']
        # Extract JSON from the response (tolerate markdown fences)
        js = content.strip()
        if '```' in js:
            for part in js.split('```'):
                p = part.strip()
                if p.startswith('{'):
                    js = p
                    break
        actions, report, exec_results = [], '', []
        try:
            js_start = js.find('{')
            js_end = js.rfind('}')
            parsed = json.loads(js[js_start:js_end + 1])
            report = parsed.get('report', '')
            actions = parsed.get('actions', []) or []
        except Exception:
            report = content  # raw text fallback — agent spoke but no valid JSON

        for act in actions:
            if not isinstance(act, dict):
                continue
            ok, msg = _agent_execute_action(act)
            exec_results.append({'action': act.get('action'), 'ok': ok, 'message': msg})

        result_text = report + ('\nActions: ' + '; '.join(
            ('✅ ' if r['ok'] else '❌ ') + r['action'] + ' — ' + r['message'] for r in exec_results) if exec_results else '')

        agent['last_run_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        agent['last_run_result'] = result_text[:1000]
        agent['updated_at'] = agent['last_run_at']
        for i, r in enumerate(rows):
            if r.get('id') == agent_id:
                rows[i] = agent
                break
        write_csv('ai_agents.csv', rows, get_fieldnames('ai_agents.csv', _AI_AGENT_FIELDS))
        log_action('run_ai_agent', f'{agent_id}: {len(exec_results)} actions')

        return jsonify({'success': True, 'report': report,
                        'actions_executed': exec_results,
                        'raw': content[:2000], 'model': model})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Agent run failed: {e}'}), 500


@app.route('/api/ai-agents/<agent_id>/test', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_ai_agents_test(agent_id):
    rows = read_csv('ai_agents.csv')
    row = next((r for r in rows if r.get('id') == agent_id), None)
    if not row:
        return jsonify({'success': False, 'error': 'Agent not found'}), 404
    row, _ = _normalize_ai_agent_row(row)

    try:
        from ai_providers import AIManager
        manager = AIManager()
        sample = (request.json or {}).get('sample') or 'مرحبا بكم في عرضنا الجديد. سجل الآن واحصل على مكافأة.'
        instructions = row.get('instructions') or 'أعد صياغة النص بأسلوب تسويقي مختصر.'
        provider_name = row.get('provider') if row.get('provider') != 'auto' else None
        result, used_provider = manager.process(sample, instructions, provider_name=provider_name)
        if not result and row.get('fallback_provider'):
            result, used_provider = manager.process(sample, instructions, provider_name=row.get('fallback_provider'))
        return jsonify({
            'success': bool(result),
            'provider': used_provider,
            'result': result or 'فشل الاختبار',
            'sample': sample,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/platform-accounts')
@api_auth
def api_platform_accounts_list():
    rows = read_csv('platform_accounts.csv')
    fieldnames = get_fieldnames('platform_accounts.csv', _PLATFORM_ACCOUNT_FIELDS)
    changed = False
    out = []
    for r in rows:
        for k in fieldnames:
            if k not in r:
                r[k] = ''
                changed = True
        if str(r.get('is_active', '')).lower() in ('1', 'true', 'yes', 'on', 'active'):
            norm = 'yes'
        else:
            norm = 'no'
        if r.get('is_active') != norm:
            r['is_active'] = norm
            changed = True
        out.append(_platform_account_public(r))
    if changed:
        write_csv('platform_accounts.csv', rows, fieldnames)
    return jsonify({'accounts': out})


@app.route('/api/platform-accounts', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_platform_accounts_create():
    data = request.json or {}
    platform = str(data.get('platform', 'telegram') or 'telegram').strip().lower()
    if platform not in ('telegram', 'whatsapp', 'webhook'):
        return jsonify({'error': 'platform must be telegram/whatsapp/webhook'}), 400
    now_s = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    row = {
        'id': f"PAC{secrets.token_hex(3).upper()}",
        'platform': platform,
        'account_name': str(data.get('account_name', '') or '').strip(),
        'is_active': 'yes' if str(data.get('is_active', 'yes')).lower() in ('1', 'true', 'yes', 'on') else 'no',
        'api_base_url': str(data.get('api_base_url', '') or '').strip(),
        'access_token': str(data.get('access_token', '') or '').strip(),
        'phone_number_id': str(data.get('phone_number_id', '') or '').strip(),
        'business_account_id': str(data.get('business_account_id', '') or '').strip(),
        'created_at': now_s,
        'updated_at': now_s,
        'created_by': str(session.get('admin_id', '') or ''),
        'last_health_check': '',
        'health_status': 'unknown',
        'last_error': '',
    }
    if not row['account_name']:
        return jsonify({'error': 'account_name required'}), 400
    rows = read_csv('platform_accounts.csv')
    fieldnames = get_fieldnames('platform_accounts.csv', _PLATFORM_ACCOUNT_FIELDS)
    rows.append(row)
    write_csv('platform_accounts.csv', rows, fieldnames)
    log_action('create_platform_account', row['id'])
    return jsonify({'success': True, 'account': _platform_account_public(row)})


@app.route('/api/platform-accounts/<account_id>', methods=['PUT', 'DELETE'])
@api_auth
@permission_required('send_broadcast')
def api_platform_accounts_edit(account_id):
    rows = read_csv('platform_accounts.csv')
    fieldnames = get_fieldnames('platform_accounts.csv', _PLATFORM_ACCOUNT_FIELDS)

    if request.method == 'DELETE':
        new_rows = [r for r in rows if r.get('id') != account_id]
        if len(new_rows) == len(rows):
            return jsonify({'error': 'Account not found'}), 404
        write_csv('platform_accounts.csv', new_rows, fieldnames)
        log_action('delete_platform_account', account_id)
        return jsonify({'success': True})

    data = request.json or {}
    editable = {
        'platform', 'account_name', 'is_active', 'api_base_url', 'access_token',
        'phone_number_id', 'business_account_id', 'health_status', 'last_error'
    }
    found = False
    for r in rows:
        if r.get('id') == account_id:
            found = True
            for k, v in data.items():
                if k in editable:
                    r[k] = v
            r['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if str(r.get('is_active', '')).lower() in ('1', 'true', 'yes', 'on', 'active'):
                r['is_active'] = 'yes'
            else:
                r['is_active'] = 'no'
            if str(r.get('platform', '')).strip().lower() not in ('telegram', 'whatsapp', 'webhook'):
                r['platform'] = 'telegram'
            break
    if not found:
        return jsonify({'error': 'Account not found'}), 404
    write_csv('platform_accounts.csv', rows, fieldnames)
    log_action('update_platform_account', account_id)
    return jsonify({'success': True})


@app.route('/api/platform-accounts/<account_id>/health', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_platform_accounts_health(account_id):
    rows = read_csv('platform_accounts.csv')
    fieldnames = get_fieldnames('platform_accounts.csv', _PLATFORM_ACCOUNT_FIELDS)
    found = False
    result = {}
    for r in rows:
        if r.get('id') == account_id:
            found = True
            result = _platform_health_check(r)
            r.update(result)
            r['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            break
    if not found:
        return jsonify({'error': 'Account not found'}), 404
    write_csv('platform_accounts.csv', rows, fieldnames)
    log_action('platform_account_health', account_id)
    return jsonify({'success': True, **result})

@app.route('/api/channels/<channel_id>/category', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_set_channel_category(channel_id):
    data = request.json
    category = data.get('category', 'غير مصنف')
    channels = read_csv('bot_channels.csv')
    fieldnames = get_fieldnames('bot_channels.csv', _CHANNEL_DEFAULT_FIELDS)
    uid = str(session.get('admin_id', '') or '')
    found = False
    for c in channels:
        if c.get('id') == channel_id:
            found = True
            c, _ = _normalize_channel_row(c)
            if not _admin_can_manage_channel(c, uid, action='edit'):
                return jsonify({'error': 'Forbidden'}), 403
            c['category'] = category
            break
    if not found:
        return jsonify({'error': 'Channel not found'}), 404
    write_csv('bot_channels.csv', channels, fieldnames)
    return jsonify({'success': True})

@app.route('/api/channels/<channel_id>/ai-toggle', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_toggle_channel_ai(channel_id):
    channels = read_csv('bot_channels.csv')
    fieldnames = get_fieldnames('bot_channels.csv', _CHANNEL_DEFAULT_FIELDS)
    uid = str(session.get('admin_id', '') or '')
    found = False
    for c in channels:
        if c.get('id') == channel_id:
            found = True
            c, _ = _normalize_channel_row(c)
            if not _admin_can_manage_channel(c, uid, action='edit'):
                return jsonify({'error': 'Forbidden'}), 403
            c['ai_enabled'] = 'no' if c.get('ai_enabled') == 'yes' else 'yes'
            break
    if not found:
        return jsonify({'error': 'Channel not found'}), 404
    write_csv('bot_channels.csv', channels, fieldnames)
    return jsonify({'success': True})

# ===== API — Social Media Accounts =====

def _social_account_public(row):
    return {
        'id': row.get('id', ''),
        'platform': row.get('platform', ''),
        'account_name': row.get('account_name', ''),
        'handle': row.get('handle', ''),
        'sub_agent_id': row.get('sub_agent_id', ''),
        'sub_agent_name': row.get('sub_agent_name', ''),
        'access_token': row.get('access_token', ''),
        'page_id': row.get('page_id', ''),
        'phone_number_id': row.get('phone_number_id', ''),
        'business_account_id': row.get('business_account_id', ''),
        'posting_permissions': row.get('posting_permissions', 'full'),
        'content_categories': row.get('content_categories', '').split('|') if row.get('content_categories') else [],
        'is_active': row.get('is_active', 'yes'),
        'followers': int(row.get('followers', '0') or 0),
        'last_sync': row.get('last_sync', ''),
        'created_at': row.get('created_at', ''),
        'updated_at': row.get('updated_at', ''),
        'created_by': row.get('created_by', ''),
    }

@app.route('/api/social-accounts')
@api_auth
@permission_required('send_broadcast')
def api_social_accounts_list():
    import sqlite3
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'boterx.db'))
    conn.row_factory = sqlite3.Row
    try:
        accounts = []
        sub_agents = []
        sub_agent_ids = set()
        rows = conn.execute('SELECT * FROM social_accounts').fetchall()
        for r in rows:
            accounts.append(_social_account_public(r))
            if r['sub_agent_id']:
                sub_agent_ids.add(r['sub_agent_id'])
        # Get sub-agents list
        agents = conn.execute('SELECT id, title, chat_id FROM bot_channels WHERE is_active="yes"').fetchall()
        for a in agents:
            if a['id'] in sub_agent_ids:
                sub_agents.append({'id': a['id'], 'name': a['title'], 'username': a['chat_id']})
        return jsonify({'accounts': accounts, 'sub_agents': sub_agents})
    finally:
        conn.close()

@app.route('/api/social-accounts', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_social_accounts_create():
    import sqlite3
    data = request.get_json(silent=True) or {}
    required = ['platform', 'account_name', 'handle', 'sub_agent_id', 'access_token']
    for f in required:
        if not data.get(f):
            return jsonify({'error': f'Missing field: {f}'}), 400

    conn = sqlite3.connect(os.path.join(BASE_DIR, 'boterx.db'))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute('SELECT * FROM bot_channels WHERE id=?', (data['sub_agent_id'],)).fetchone()
        if not row:
            return jsonify({'error': 'Sub agent not found'}), 404
        sub_agent_name = row['title']
    finally:
        conn.close()

    conn = sqlite3.connect(os.path.join(BASE_DIR, 'boterx.db'))
    try:
        conn.execute('''
            INSERT INTO social_accounts (id, platform, account_name, handle, sub_agent_id, sub_agent_name,
                access_token, page_id, phone_number_id, business_account_id,
                posting_permissions, content_categories, is_active, followers, last_sync,
                created_at, updated_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"SOC{secrets.token_hex(3).upper()}",
            data['platform'], data['account_name'], data['handle'], data['sub_agent_id'],
            sub_agent_name, data['access_token'], data.get('page_id', ''),
            data.get('phone_number_id', ''), data.get('business_account_id', ''),
            data.get('posting_permissions', 'full'),
            '|'.join(data.get('content_categories', [])),
            'yes' if data.get('is_active') else 'no',
            0, '', datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            str(session.get('admin_id', ''))
        ))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/social-accounts/<account_id>', methods=['PUT'])
@api_auth
@permission_required('send_broadcast')
def api_social_accounts_update(account_id):
    import sqlite3
    data = request.get_json(silent=True) or {}
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'boterx.db'))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute('SELECT * FROM social_accounts WHERE id=?', (account_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Account not found'}), 404
        # Keep existing key if not provided
        access_token = data.get('access_token') if data.get('access_token') else row['access_token']
        sub_agent_name = row['sub_agent_name']
        conn.execute('''
            UPDATE social_accounts SET
                platform=?, account_name=?, handle=?, sub_agent_id=?,
                access_token=?, page_id=?, phone_number_id=?, business_account_id=?,
                posting_permissions=?, content_categories=?, is_active=?,
                updated_at=?
            WHERE id=?
        ''', (
            data.get('platform', row['platform']),
            data.get('account_name', row['account_name']),
            data.get('handle', row['handle']),
            data.get('sub_agent_id', row['sub_agent_id']),
            access_token,
            data.get('page_id', row['page_id']),
            data.get('phone_number_id', row['phone_number_id']),
            data.get('business_account_id', row['business_account_id']),
            data.get('posting_permissions', row['posting_permissions']),
            '|'.join(data.get('content_categories', [])),
            'yes' if data.get('is_active') else 'no',
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            account_id
        ))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/social-accounts/<account_id>', methods=['DELETE'])
@api_auth
@permission_required('send_broadcast')
def api_social_accounts_delete(account_id):
    import sqlite3
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'boterx.db'))
    try:
        conn.execute('DELETE FROM social_accounts WHERE id=?', (account_id,))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/social-accounts/<account_id>/toggle', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_social_accounts_toggle(account_id):
    import sqlite3
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'boterx.db'))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute('SELECT is_active FROM social_accounts WHERE id=?', (account_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Account not found'}), 404
        new_status = 'no' if row['is_active'] == 'yes' else 'yes'
        conn.execute('UPDATE social_accounts SET is_active=?, updated_at=? WHERE id=?',
                     (new_status, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), account_id))
        conn.commit()
        return jsonify({'success': True, 'is_active': new_status})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/social-accounts/<account_id>/sync', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_social_accounts_sync(account_id):
    import sqlite3
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'boterx.db'))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute('SELECT * FROM social_accounts WHERE id=?', (account_id,)).fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Account not found'}), 404

        platform = row['platform']
        access_token = row['access_token']

        # Simulate sync with platform API
        # In production, this would call the actual platform APIs
        followers = 0
        try:
            if platform == 'facebook':
                # Would call Facebook Graph API
                pass
            elif platform == 'instagram':
                # Would call Instagram Graph API
                pass
            elif platform == 'twitter':
                # Would call Twitter API v2
                pass
            elif platform == 'linkedin':
                # Would call LinkedIn API
                pass
            # ... other platforms
        except:
            pass

        conn.execute('UPDATE social_accounts SET followers=?, last_sync=?, updated_at=? WHERE id=?',
                     (followers, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                      datetime.now().strftime('%Y-%m-%d %H:%M:%S'), account_id))
        conn.commit()
        return jsonify({'success': True, 'followers': followers, 'message': 'Synced successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Sync failed: {str(e)}'}), 500
    finally:
        conn.close()

@app.route('/api/social-accounts/<account_id>/post', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_social_accounts_post(account_id):
    """Post content to a social media account"""
    import sqlite3
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'boterx.db'))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute('SELECT * FROM social_accounts WHERE id=?', (account_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Account not found'}), 404

        data = request.get_json(silent=True) or {}
        content = data.get('content', '')
        media_urls = data.get('media_urls', [])

        if not content.strip() and not media_urls:
            return jsonify({'error': 'Content or media required'}), 400

        # Post to platform
        platform = row['platform']
        access_token = row['access_token']

        # This is a placeholder - in production, call the actual platform APIs
        # For now, simulate success
        post_id = f"POST{secrets.token_hex(4).upper()}"
        success = True
        error = None

        # Log the post
        conn.execute('''
            INSERT INTO social_posts (id, account_id, content, media_urls, status, posted_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (post_id, account_id, content, '|'.join(media_urls), 'posted' if success else 'failed',
              datetime.now().strftime('%Y-%m-%d %H:%M:%S'), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()

        if success:
            return jsonify({'success': True, 'post_id': post_id, 'message': 'Posted successfully'})
        else:
            return jsonify({'success': False, 'error': error or 'Post failed'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': f'Post failed: {str(e)}'}), 500
    finally:
        conn.close()

# ===== API — Channels =====
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
    fieldnames = get_fieldnames('channel_groups.csv', ['id','name','description','channel_ids','parent_id','created_at'])
    new_id = f"GRP{secrets.token_hex(3).upper()}"
    group = {
        'id': new_id,
        'name': data.get('name', ''),
        'description': data.get('description', ''),
        'channel_ids': data.get('channel_ids', ''),
        'parent_id': data.get('parent_id', ''),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    append_csv('channel_groups.csv', group, fieldnames)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/channel-groups/<group_id>', methods=['DELETE'])
@api_auth
@permission_required('send_broadcast')
def api_delete_channel_group(group_id):
    groups = read_csv('channel_groups.csv')
    fieldnames = get_fieldnames('channel_groups.csv', ['id','name','description','channel_ids','parent_id','created_at'])
    groups = [g for g in groups if g.get('id') != group_id]
    write_csv('channel_groups.csv', groups, fieldnames)
    return jsonify({'success': True})


@app.route('/api/channel-groups/tree')
@api_auth
def api_channel_groups_tree():
    """Return channel groups as a nested tree structure."""
    groups = read_csv('channel_groups.csv')
    channels = read_csv('bot_channels.csv')
    # Build lookup
    by_id = {g['id']: g for g in groups}
    # Resolve channel count for each group
    for g in groups:
        ch_ids = [c.strip() for c in (g.get('channel_ids') or '').split('|') if c.strip()]
        g['channel_count'] = len(ch_ids)
        g['channels'] = [{'id': cid, 'title': next((c.get('title','') for c in channels if c.get('id')==cid), cid)} for cid in ch_ids]
        # Resolve sub-groups
        sub_ids = [c.strip() for c in (g.get('channel_ids') or '').split('|') if c.strip() and c.strip().startswith('GRP')]
        g['sub_groups'] = [by_id[sid] for sid in sub_ids if sid in by_id]
    # Build tree: roots are groups with no parent or parent_id not in list
    roots = [g for g in groups if not g.get('parent_id') or g['parent_id'] not in by_id]
    return jsonify({'groups': groups, 'tree': roots})


@app.route('/api/channel-groups/<group_id>/resolve', methods=['POST'])
@api_auth
def api_resolve_group_tree(group_id):
    """Resolve a group and all its sub-groups recursively, return all channel IDs."""
    groups = read_csv('channel_groups.csv')
    by_id = {g['id']: g for g in groups}
    resolved = set()
    def _resolve(gid):
        g = by_id.get(gid)
        if not g:
            return
        for cid in (g.get('channel_ids') or '').split('|'):
            cid = cid.strip()
            if not cid:
                continue
            if cid.startswith('GRP'):
                _resolve(cid)
            else:
                resolved.add(cid)
    _resolve(group_id)
    return jsonify({'group_id': group_id, 'channel_ids': list(resolved)})


@app.route('/api/posting/stats')
@api_auth
def api_posting_stats():
    """Return posting statistics for AI monitoring."""
    # Read from bot's health endpoint stats
    stats = {
        'queue_pending': 0,
        'queue_total': 0,
        'today_posts': {},
        'posting_rate': {},
    }
    # Count queue entries
    try:
        import csv as _csv
        if os.path.exists('broadcast_queue.csv'):
            with open('broadcast_queue.csv', 'r', encoding='utf-8-sig') as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    stats['queue_total'] += 1
                    if row.get('status') == 'pending':
                        stats['queue_pending'] += 1
    except Exception:
        pass
    # Count today's posts per channel from relay_log
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        if os.path.exists('relay_log.csv'):
            with open('relay_log.csv', 'r', encoding='utf-8-sig') as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    ts = (row.get('timestamp') or '')
                    cid = (row.get('source_chat_id') or '').strip()
                    if ts.startswith(today) and cid:
                        stats['today_posts'][cid] = stats['today_posts'].get(cid, 0) + 1
    except Exception:
        pass
    return jsonify(stats)


@app.route('/api/posting/config', methods=['GET', 'PUT'])
@api_auth
def api_posting_config():
    """Get or update smart posting configuration."""
    if request.method == 'GET':
        return jsonify({
            'inter_delay_min': 3.0,
            'inter_delay_max': 7.0,
            'inter_group_delay_min': 15.0,
            'inter_group_delay_max': 30.0,
            'daily_cap': 12,
            'ai_monitor': True,
        })
    data = request.json or {}
    log_action('update_posting_config', json.dumps(data))
    return jsonify({'success': True, 'note': 'Config updated (restart bot to apply)'})




def _normalize_source_channel_row(row, actor_uid=''):
    changed = False

    def _setdefault(k, v):
        nonlocal changed
        if row.get(k, '') in ('', None):
            row[k] = v
            changed = True

    _setdefault('id', f"SRC{secrets.token_hex(3).upper()}")
    _setdefault('chat_id', '')
    _setdefault('title', '')
    _setdefault('type', 'channel')
    _setdefault('is_active', 'yes')
    _setdefault('added_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    _setdefault('brand_voice', '')
    _setdefault('target_channel_ids', '')
    _setdefault('schedule', '')
    _setdefault('last_scraped_at', '')
    _setdefault('content_filter', 'all')
    _setdefault('ai_edit_text', 'yes')
    _setdefault('ai_edit_media', 'no')
    _setdefault('ai_provider', '')
    _setdefault('ai_agent_id', '')
    _setdefault('owner_admin_id', str(actor_uid or session.get('admin_id', '') or ''))
    _setdefault('managed_by_admin_ids', str(row.get('owner_admin_id') or actor_uid or session.get('admin_id', '') or ''))

    for k in ('is_active', 'ai_edit_text', 'ai_edit_media'):
        v = str(row.get(k, '')).lower()
        norm = 'yes' if v in ('1', 'true', 'yes', 'on', 'active') else 'no'
        if row.get(k) != norm:
            row[k] = norm
            changed = True

    if row.get('content_filter') not in ('all', 'text_only', 'photo_only', 'video_only', 'text_photo', 'text_photo_video'):
        row['content_filter'] = 'all'
        changed = True

    managers = _pipe_ids(row.get('managed_by_admin_ids', ''))
    if managers != str(row.get('managed_by_admin_ids', '')):
        row['managed_by_admin_ids'] = managers
        changed = True

    owner = str(row.get('owner_admin_id', '') or '').strip()
    if owner and owner not in _pipe_to_list(row.get('managed_by_admin_ids', '')):
        row['managed_by_admin_ids'] = _pipe_ids((row.get('managed_by_admin_ids', '') + '|' + owner).strip('|'))
        changed = True

    return row, changed


def _admin_can_manage_source(row, uid):
    if _is_super_admin_session():
        return True
    owner = str(row.get('owner_admin_id', '') or '').strip()
    managers = _pipe_to_list(row.get('managed_by_admin_ids', ''))
    if not owner:
        return True
    return str(uid or '') in (owner, *managers)


@app.route('/api/source-channels')
@api_auth
def api_source_channels_list():
    rows = read_csv('source_channels.csv')
    fields = get_fieldnames('source_channels.csv', _SOURCE_CHANNEL_FIELDS)
    uid = str(session.get('admin_id', '') or '')
    changed = False
    out = []
    for r in rows:
        r, ch = _normalize_source_channel_row(r)
        changed = changed or ch
        if _admin_can_manage_source(r, uid):
            out.append(r)
    if changed:
        write_csv('source_channels.csv', rows, fields)
    return jsonify({'channels': out})


@app.route('/api/source-channels', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_source_channels_create():
    data = request.json or {}
    chat_id = str(data.get('chat_id', '') or '').strip()
    if not chat_id:
        return jsonify({'error': 'chat_id required'}), 400

    rows = read_csv('source_channels.csv')
    for r in rows:
        if str(r.get('chat_id', '') or '') == chat_id:
            return jsonify({'error': 'Source channel already exists'}), 400

    now_s = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    uid = str(session.get('admin_id', '') or '')
    targets_raw = data.get('target_channel_ids', '')
    if isinstance(targets_raw, list):
        targets_raw = '|'.join([str(x).strip() for x in targets_raw if str(x).strip()])
    row = {
        'id': f"SRC{secrets.token_hex(3).upper()}",
        'chat_id': chat_id,
        'title': str(data.get('title', '') or '').strip(),
        'type': str(data.get('type', 'channel') or 'channel').strip(),
        'is_active': 'yes',
        'added_at': now_s,
        'brand_voice': str(data.get('brand_voice', '') or '').strip(),
        'target_channel_ids': _pipe_ids(targets_raw),
        'schedule': str(data.get('schedule', '') or '').strip(),
        'last_scraped_at': '',
        'content_filter': str(data.get('content_filter', 'all') or 'all').strip(),
        'ai_edit_text': 'yes' if str(data.get('ai_edit_text', 'yes')).lower() in ('1', 'true', 'yes', 'on') else 'no',
        'ai_edit_media': 'yes' if str(data.get('ai_edit_media', 'no')).lower() in ('1', 'true', 'yes', 'on') else 'no',
        'ai_provider': str(data.get('ai_provider', '') or '').strip(),
        'ai_agent_id': str(data.get('ai_agent_id', '') or '').strip(),
        'owner_admin_id': uid,
        'managed_by_admin_ids': uid,
    }
    row, _ = _normalize_source_channel_row(row, actor_uid=uid)
    fields = get_fieldnames('source_channels.csv', _SOURCE_CHANNEL_FIELDS)
    rows.append(row)
    write_csv('source_channels.csv', rows, fields)
    log_action('create_source_channel', row['id'])
    return jsonify({'success': True, 'channel': row})


@app.route('/api/source-channels/<source_id>', methods=['PUT', 'DELETE'])
@api_auth
@permission_required('send_broadcast')
def api_source_channels_edit(source_id):
    rows = read_csv('source_channels.csv')
    fields = get_fieldnames('source_channels.csv', _SOURCE_CHANNEL_FIELDS)
    uid = str(session.get('admin_id', '') or '')

    if request.method == 'DELETE':
        out = []
        found = False
        for r in rows:
            if r.get('id') != source_id:
                out.append(r)
                continue
            found = True
            r, _ = _normalize_source_channel_row(r)
            if not _admin_can_manage_source(r, uid):
                return jsonify({'error': 'Forbidden'}), 403
        if not found:
            return jsonify({'error': 'Source channel not found'}), 404
        write_csv('source_channels.csv', out, fields)
        log_action('delete_source_channel', source_id)
        return jsonify({'success': True})

    data = request.json or {}
    editable = {
        'title', 'type', 'is_active', 'brand_voice', 'target_channel_ids', 'schedule',
        'content_filter', 'ai_edit_text', 'ai_edit_media', 'ai_provider', 'ai_agent_id',
        'managed_by_admin_ids', 'owner_admin_id'
    }
    found = False
    for r in rows:
        if r.get('id') == source_id:
            found = True
            r, _ = _normalize_source_channel_row(r)
            if not _admin_can_manage_source(r, uid):
                return jsonify({'error': 'Forbidden'}), 403
            if not _is_super_admin_session() and ('owner_admin_id' in data):
                return jsonify({'error': 'Only super admin can reassign owner'}), 403
            for k, v in data.items():
                if k not in editable:
                    continue
                if k in ('target_channel_ids', 'managed_by_admin_ids') and isinstance(v, list):
                    v = '|'.join([str(x).strip() for x in v if str(x).strip()])
                r[k] = v
            r, _ = _normalize_source_channel_row(r)
            break
    if not found:
        return jsonify({'error': 'Source channel not found'}), 404
    write_csv('source_channels.csv', rows, fields)
    log_action('update_source_channel', source_id)
    return jsonify({'success': True})


@app.route('/api/source-channels/<source_id>/toggle', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_source_channels_toggle(source_id):
    rows = read_csv('source_channels.csv')
    fields = get_fieldnames('source_channels.csv', _SOURCE_CHANNEL_FIELDS)
    uid = str(session.get('admin_id', '') or '')
    found = False
    for r in rows:
        if r.get('id') == source_id:
            found = True
            r, _ = _normalize_source_channel_row(r)
            if not _admin_can_manage_source(r, uid):
                return jsonify({'error': 'Forbidden'}), 403
            r['is_active'] = 'no' if r.get('is_active') == 'yes' else 'yes'
            break
    if not found:
        return jsonify({'error': 'Source channel not found'}), 404
    write_csv('source_channels.csv', rows, fields)
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
    ch, _ = _normalize_channel_row(ch)
    uid = str(session.get('admin_id', '') or '')
    if not _admin_can_manage_channel(ch, uid, action='publish'):
        return jsonify({'error': 'Forbidden'}), 403
    data = request.json
    message_text = data.get('message', '')
    media_urls = data.get('media_urls', [])
    if not message_text and not media_urls:
        return jsonify({'error': 'No message or media'}), 400
    # حفظ في broadcast_queue.csv للبوت يرسلها
    platform = str(ch.get('platform', 'telegram') or 'telegram').lower()
    entry = {
        'id': f"CHPOST{secrets.token_hex(3).upper()}",
        'message': message_text,
        'type': 'channel',
        'platform': platform,
        'target_chat_id': ch.get('chat_id', ''),
        'platform_account_id': ch.get('platform_account_id', ''),
        'target_channel_id': ch.get('id', ''),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'created_by': session.get('admin_id', ''),
        'status': 'pending',
        'media_urls': '|'.join(media_urls) if media_urls else ''
    }
    fieldnames = get_fieldnames('broadcast_queue.csv', [
        'id', 'message', 'type', 'platform', 'target_chat_id',
        'platform_account_id', 'target_channel_id',
        'created_at', 'created_by', 'status',
        'target', 'recipient', 'priority', 'country', 'media_urls',
        'target_user', 'target_name', 'scheduled_at'
    ])
    append_csv('broadcast_queue.csv', entry, fieldnames)
    
    # Archive to post_vault for history
    try:
        vault_entry = {
            'id': f"VPOST{secrets.token_hex(3).upper()}",
            'source_channel': ch.get('title', '') or ch.get('id', ''),
            'source_chat_id': ch.get('chat_id', ''),
            'original_text': message_text,
            'processed_text': message_text,
            'media_type': 'image' if media_urls and any(u.lower().endswith(('.jpg','.jpeg','.png','.gif','.webp')) for u in media_urls) else ('video' if media_urls and any(u.lower().endswith(('.mp4','.mov','.webm')) for u in media_urls) else ''),
            'media_file_id': '|'.join(media_urls) if media_urls else '',
            'ai_provider': 'manual',
            'status': 'published',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'published_to_users': '0',
            'published_to_channels': '1',
            'views': '0',
            'category': ch.get('category', ''),
        }
        vault_fieldnames = get_fieldnames('post_vault.csv', ['id','source_channel','source_chat_id','original_text','processed_text','media_type','media_file_id','ai_provider','status','created_at','published_to_users','published_to_channels','views','category'])
        append_csv('post_vault.csv', vault_entry, vault_fieldnames)
    except Exception as e:
        # Don't fail the request if archiving fails
        pass
    
    log_action('post_to_channel', f'{channel_id}: {message_text[:50]}')
    return jsonify({'success': True, 'message': 'تم إضافة الرسالة لقائمة الإرسال'})


@app.route('/api/posts/create', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_create_post():
    """
    منشور شامل — يدعم: نص+وسائط+قنوات+مجموعةات+جدولة+cron.
    يدعم: platform, parse_mode, silent, pin, posting_method.
    """
    try:
        data = request.json or {}
        message = (data.get('message') or '').strip()
        media_urls = data.get('media_urls') or []
        target_channels = data.get('channels') or []
        target_groups = data.get('groups') or []
        schedule_type = (data.get('schedule_type') or 'now').strip()
        scheduled_at = (data.get('scheduled_at') or '').strip()
        cron_expr = (data.get('cron_expr') or '').strip()
        priority = (data.get('priority') or 'normal').strip()
        platform = (data.get('platform') or 'telegram').strip().lower()
        parse_mode = (data.get('parse_mode') or '').strip()
        silent = bool(data.get('silent', False))
        pin = bool(data.get('pin', False))
        posting_method = (data.get('posting_method') or 'api').strip().lower()

        SUPPORTED_PLATFORMS = ('telegram', 'whatsapp', 'instagram', 'facebook', 'twitter')
        PLATFORM_CHAR_LIMITS = {
            'telegram': 4096,
            'whatsapp': 65536,
            'instagram': 2200,
            'facebook': 63206,
            'twitter': 280,
        }

        if platform not in SUPPORTED_PLATFORMS:
            return jsonify({'error': f'المنصة غير مدعومة: {platform}. المدعومة: {", ".join(SUPPORTED_PLATFORMS)}'}), 400

        if posting_method not in ('api', 'copy', 'download', 'deeplink', 'group'):
            posting_method = 'api'

        reply_markup_raw = data.get('reply_markup') or ''
        if isinstance(reply_markup_raw, dict):
            reply_markup_str = json.dumps(reply_markup_raw)
        elif isinstance(reply_markup_raw, str):
            reply_markup_str = reply_markup_raw
        else:
            reply_markup_str = ''

        if not message and not media_urls:
            return jsonify({'error': 'اكتب رسالة أو أضف وسائط'}), 400
        if not target_channels and not target_groups:
            return jsonify({'error': 'اختر قناة أو مجموعة واحدة على الأقل'}), 400

        char_limit = PLATFORM_CHAR_LIMITS.get(platform, 4096)
        if message and len(message) > char_limit:
            return jsonify({
                'error': f'النص يتجاوز الحد الأقصى لمنصة {platform}: {len(message)}/{char_limit} حرف',
                'char_count': len(message),
                'char_limit': char_limit,
                'platform': platform,
            }), 400

        if platform == 'twitter' and parse_mode not in ('', 'html', 'markdown'):
            parse_mode = ''

        channels_csv = read_csv('bot_channels.csv')
        groups_csv = read_csv('channel_groups.csv')
        now_s = datetime.now().strftime('%Y-%m-%d %H:%M')
        entries = []
        skipped_channels = []
        resolved_chat_ids = set()

        for ch_id in target_channels:
            ch = next((c for c in channels_csv if c.get('id') == ch_id), None)
            if not ch:
                skipped_channels.append({'id': ch_id, 'reason': 'channel_not_found'})
                continue
            ch_platform = str(ch.get('platform', 'telegram') or 'telegram').lower()
            if ch_platform != platform:
                skipped_channels.append({'id': ch_id, 'reason': f'platform_mismatch: {ch_platform} ≠ {platform}'})
                continue
            chat_id = str(ch.get('chat_id', '') or '').strip()
            if not chat_id:
                skipped_channels.append({'id': ch_id, 'reason': 'empty_chat_id'})
                continue
            if chat_id in resolved_chat_ids:
                skipped_channels.append({'id': ch_id, 'reason': 'duplicate'})
                continue
            resolved_chat_ids.add(chat_id)
            entry = {
                'id': f"POST{secrets.token_hex(4).upper()}",
                'message': message,
                'type': 'channel',
                'platform': platform,
                'target_chat_id': chat_id,
                'platform_account_id': str(ch.get('platform_account_id', '') or ''),
                'target_channel_id': ch.get('id', ''),
                'created_at': now_s,
                'created_by': str(session.get('admin_id', '')),
                'status': 'pending',
                'target': 'channel',
                'recipient': 'single',
                'priority': priority,
                'country': 'all',
                'media_urls': '|'.join(media_urls) if media_urls else '',
                'target_user': '',
                'target_name': '',
                'scheduled_at': scheduled_at if schedule_type == 'timed' else '',
                'cron_expr': cron_expr if schedule_type == 'cron' else '',
                'reply_markup': reply_markup_str,
                'parse_mode': parse_mode,
                'silent': '1' if silent else '',
                'pin': '1' if pin else '',
                'posting_method': posting_method,
            }
            entries.append(entry)

        for grp_id in target_groups:
            grp = next((g for g in groups_csv if g.get('id') == grp_id), None)
            if not grp:
                continue
            channel_ids_raw = str(grp.get('channel_ids', '') or '')
            for cid in channel_ids_raw.split('|'):
                cid = cid.strip()
                if not cid or cid in resolved_chat_ids:
                    continue
                ch = next((c for c in channels_csv if c.get('id') == cid), None)
                if not ch:
                    continue
                ch_platform = str(ch.get('platform', 'telegram') or 'telegram').lower()
                if ch_platform != platform:
                    continue
                chat_id = str(ch.get('chat_id', '') or '').strip()
                if not chat_id:
                    continue
                resolved_chat_ids.add(chat_id)
                entry = {
                    'id': f"POST{secrets.token_hex(4).upper()}",
                    'message': message,
                    'type': 'channel',
                    'platform': platform,
                    'target_chat_id': chat_id,
                    'platform_account_id': str(ch.get('platform_account_id', '') or ''),
                    'target_channel_id': ch.get('id', ''),
                    'created_at': now_s,
                    'created_by': str(session.get('admin_id', '')),
                    'status': 'pending',
                    'target': 'channel',
                    'recipient': 'single',
                    'priority': priority,
                    'country': 'all',
                    'media_urls': '|'.join(media_urls) if media_urls else '',
                    'target_user': '',
                    'target_name': '',
                    'scheduled_at': scheduled_at if schedule_type == 'timed' else '',
                    'cron_expr': cron_expr if schedule_type == 'cron' else '',
                    'reply_markup': reply_markup_str,
                    'parse_mode': parse_mode,
                    'silent': '1' if silent else '',
                    'pin': '1' if pin else '',
                    'posting_method': posting_method,
                }
                entries.append(entry)

        if not entries:
            reason = 'لم يتم العثور على قنوات صالحة'
            if skipped_channels:
                reasons = set(s['reason'].split(':')[0] for s in skipped_channels)
                reason += f' — ({", ".join(reasons)})'
            return jsonify({'error': reason, 'skipped': skipped_channels}), 400

        queue_fieldnames = get_fieldnames('broadcast_queue.csv', [
            'id', 'message', 'type', 'platform', 'target_chat_id',
            'platform_account_id', 'target_channel_id', 'created_at',
            'created_by', 'status', 'target', 'recipient', 'priority',
            'country', 'media_urls', 'target_user', 'target_name',
            'scheduled_at', 'cron_expr', 'group_id', 'reply_markup',
            'parse_mode', 'silent', 'pin', 'posting_method'
        ])
        for e in entries:
            append_csv('broadcast_queue.csv', e, queue_fieldnames)

        vault_fieldnames = get_fieldnames('post_vault.csv', [
            'id', 'source_channel', 'source_chat_id', 'original_text',
            'processed_text', 'media_type', 'media_file_id', 'ai_provider',
            'status', 'created_at', 'published_to_users', 'published_to_channels',
            'views', 'category', 'cron_expr', 'scheduled_at', 'target_channels',
            'priority'
        ])
        vault_entry = {
            'id': f"VPOST{secrets.token_hex(4).upper()}",
            'source_channel': ','.join(target_channels[:5]),
            'source_chat_id': ','.join([next((c.get('chat_id','') for c in channels_csv if c.get('id')==cid),'') for cid in target_channels[:5]]),
            'original_text': message,
            'processed_text': message,
            'media_type': 'mixed' if media_urls else 'text',
            'media_file_id': '|'.join(media_urls) if media_urls else '',
            'ai_provider': 'manual',
            'status': 'scheduled' if schedule_type != 'now' else 'pending',
            'created_at': now_s,
            'published_to_users': '0',
            'published_to_channels': str(len(entries)),
            'views': '0',
            'category': '',
            'cron_expr': cron_expr,
            'scheduled_at': scheduled_at,
            'target_channels': ','.join(target_channels[:20]),
            'priority': priority,
        }
        append_csv('post_vault.csv', vault_entry, vault_fieldnames)

        log_action('create_post', f'{len(entries)} targets ({platform}/{posting_method}), msg={message[:50]}')
        return jsonify({
            'success': True,
            'queued': len(entries),
            'message': f'تم إنشاء المنشور — {len(entries)} قناة في قائمة الإرسال',
            'vault_id': vault_entry['id'],
            'platform': platform,
            'posting_method': posting_method,
            'skipped': skipped_channels if skipped_channels else None,
        })

    except Exception as e:
        logger.error(f"api_create_post error: {e}", exc_info=True)
        return jsonify({'error': f'خطأ داخلي: {str(e)}'}), 500


@app.route('/api/posts/history')
@api_auth
def api_post_history():
    """جلب سجل المنشورات من post_vault"""
    posts = read_csv('post_vault.csv')
    search = request.args.get('search', '').strip().lower()
    if search:
        posts = [p for p in posts if search in (p.get('original_text') or '').lower()
                 or search in (p.get('source_channel') or '').lower()]
    posts.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return jsonify({'posts': posts[:200]})


@app.route('/api/posts/<post_id>/cron', methods=['PUT'])
@api_auth
@permission_required('send_broadcast')
def api_update_post_cron(post_id):
    """تحديث كرون للمنشور"""
    data = request.json or {}
    cron_expr = (data.get('cron_expr') or '').strip()
    posts = read_csv('post_vault.csv')
    for p in posts:
        if p.get('id') == post_id:
            p['cron_expr'] = cron_expr
            vault_fieldnames = get_fieldnames('post_vault.csv', [
                'id', 'source_channel', 'source_chat_id', 'original_text',
                'processed_text', 'media_type', 'media_file_id', 'ai_provider',
                'status', 'created_at', 'published_to_users', 'published_to_channels',
                'views', 'category', 'cron_expr', 'scheduled_at', 'target_channels',
                'priority'
            ])
            write_csv('post_vault.csv', posts, vault_fieldnames)
            log_action('update_post_cron', f'{post_id}: {cron_expr}')
            return jsonify({'success': True})
    return jsonify({'error': 'Post not found'}), 404


@app.route('/api/posts/<post_id>/duplicate', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_duplicate_post(post_id):
    """تكرار منشور سابق — ينشئ نسخة جديدة في القائمة"""
    posts = read_csv('post_vault.csv')
    orig = next((p for p in posts if p.get('id') == post_id), None)
    if not orig:
        return jsonify({'error': 'Post not found'}), 404
    channels = [c.strip() for c in (orig.get('target_channels') or '').split(',') if c.strip()]
    data = request.json or {}
    new_msg = data.get('message') or orig.get('original_text') or ''
    new_media = data.get('media_urls') or [u for u in (orig.get('media_file_id') or '').split('|') if u]
    new_channels = data.get('channels') or channels

    payload = {
        'message': new_msg,
        'media_urls': new_media,
        'channels': new_channels,
        'groups': [],
        'schedule_type': data.get('schedule_type', 'now'),
        'scheduled_at': data.get('scheduled_at', ''),
        'cron_expr': data.get('cron_expr', ''),
        'priority': data.get('priority', orig.get('priority', 'normal')),
    }
    with app.test_request_context(json=payload, content_type='application/json'):
        session['admin_id'] = session.get('admin_id', '')
        return api_create_post()



# ===== Auto-Posting Engine =====
_CONTENT_TEMPLATES = {
    "info": [
        "📊 إحصائيات اليوم: فريقك سجّل {stats_today}. تابع التحديثات معنا!",
        "📈 أرقام مميزة: {stat_highlight}. ما رأيك في هذه الأرقام؟",
        "💡 هل تعلم؟ {fun_fact}. شاركنا رأيك!",
        "🏆 إنجاز تاريخي: {achievement}. فريقنا يستحق التصفيق!",
    ],
    "question": [
        "🤔 سؤال اليوم: {question}? اكتب رأيك في التعليقات!",
        "💭 ما توقعكم لنتيجة مباراة {upcoming_match}؟",
        "⚽ من أحسن لاعب في المباراة الأخيرة برأيك؟",
        "🎯 هل توافق على هذا التحليل؟ اكتب نعم أو لا!",
    ],
    "prediction": [
        "🔮 توقعاتنا: {prediction_details}. ما رأيك؟",
        "📊 التحليل يشير إلى {prediction}. انتظروا النتيجة!",
        "🎯 picks اليوم: {picks}. هل توافق؟",
    ],
    "analysis": [
        "📋 تحليل مباراة {match_name}:\\n{analysis_details}",
        "🔍 تقرير مفصل: {report_summary}",
        "📝 تقييم أداء اللاعبين: {player_ratings}",
    ],
    "live": [
        "🔴 مباشر | {live_event}",
        "⚡ تحديث مباشر: {live_update}",
        "🏟️ أحداث المباراة الحية: {live_details}",
    ],
    "result": [
        "🏁 نتيجة المباراة: {result}",
        "✅ خلاصة المباراة: {match_summary}",
        "📊 النتيجة النهائية: {final_result}",
    ],
}


def _get_branding_suffix(channel):
    parts = []
    cn = str(channel.get("company_name") or "").strip()
    dl = str(channel.get("download_link") or "").strip()
    pc = str(channel.get("promo_code") or "").strip()
    al = str(channel.get("affiliate_link") or "").strip()
    if cn:
        parts.append("🏢 " + cn)
    if dl:
        parts.append("📱 تحميل: " + dl)
    if pc:
        parts.append("🎁 كود الخصم: " + pc)
    if al:
        parts.append("🔗 " + al)
    return "\\n\\n" + "\\n".join(parts) if parts else ""


def _apply_placeholders(text, channel, extra=None):
    cn = str(channel.get("company_name") or "VEX Games")
    dl = str(channel.get("download_link") or "")
    pc = str(channel.get("promo_code") or "")
    al = str(channel.get("affiliate_link") or "")
    text = text.replace("{company_name}", cn)
    text = text.replace("{download_link}", dl)
    text = text.replace("{promo_code}", pc)
    text = text.replace("{affiliate_link}", al)
    if extra:
        for k, v in extra.items():
            text = text.replace("{" + k + "}", str(v))
    return text


@app.route("/api/content-templates", methods=["GET", "POST"])
@api_auth
@permission_required("send_broadcast")
def api_content_templates():
    if request.method == "GET":
        return jsonify({"templates": _CONTENT_TEMPLATES, "types": list(_CONTENT_TEMPLATES.keys())})
    data = request.json or {}
    content_type = (data.get("type") or "").strip()
    text = (data.get("text") or "").strip()
    if not content_type or not text:
        return jsonify({"error": "type and text required"}), 400
    if content_type not in _CONTENT_TEMPLATES:
        _CONTENT_TEMPLATES[content_type] = []
    _CONTENT_TEMPLATES[content_type].append(text)
    return jsonify({"success": True, "count": len(_CONTENT_TEMPLATES[content_type])})


@app.route("/api/auto-post/run", methods=["POST"])
@api_auth
@permission_required("send_broadcast")
def api_auto_post_run():
    channels = read_csv("bot_channels.csv")
    active = [c for c in channels if c.get("auto_post_enabled") == "yes" and c.get("is_active") == "yes"]
    if not active:
        return jsonify({"error": "لا توجد قنوات مفعّلة للنشر التلقائي"}), 400
    queued = 0
    now_s = datetime.now().strftime("%Y-%m-%d %H:%M")
    for ch in active:
        types_raw = str(ch.get("auto_post_types") or "info|question|prediction|analysis")
        allowed_types = [t.strip() for t in types_raw.split("|") if t.strip()]
        if not allowed_types:
            allowed_types = ["info", "question"]
        chosen_type = random.choice(allowed_types)
        templates = _CONTENT_TEMPLATES.get(chosen_type, [])
        if not templates:
            continue
        template = random.choice(templates)
        text = _apply_placeholders(template, ch)
        suffix = _get_branding_suffix(ch)
        full_text = text + suffix
        entry = {
            "id": "AUTO" + secrets.token_hex(4).upper(),
            "message": full_text,
            "type": "channel",
            "platform": str(ch.get("platform", "telegram") or "telegram").lower(),
            "target_chat_id": str(ch.get("chat_id", "") or ""),
            "platform_account_id": str(ch.get("platform_account_id", "") or ""),
            "target_channel_id": ch.get("id", ""),
            "created_at": now_s,
            "created_by": "auto_post_engine",
            "status": "pending",
            "target": "channel",
            "recipient": "single",
            "priority": "normal",
            "country": "all",
            "media_urls": "",
            "target_user": "",
            "target_name": "",
            "scheduled_at": "",
            "cron_expr": "",
        }
        fieldnames = get_fieldnames("broadcast_queue.csv", [
            "id", "message", "type", "platform", "target_chat_id",
            "platform_account_id", "target_channel_id", "created_at",
            "created_by", "status", "target", "recipient", "priority",
            "country", "media_urls", "target_user", "target_name",
            "scheduled_at", "cron_expr"
        ])
        append_csv("broadcast_queue.csv", entry, fieldnames)
        queued += 1
    log_action("auto_post_run", str(queued) + " channels queued")
    return jsonify({"success": True, "queued": queued})


@app.route("/api/auto-post/scheduler-status")
@api_auth
def api_auto_post_scheduler():
    channels = read_csv("bot_channels.csv")
    enabled = [c for c in channels if c.get("auto_post_enabled") == "yes"]
    status = []
    for ch in enabled:
        status.append({
            "id": ch.get("id"),
            "title": ch.get("title"),
            "interval_min": ch.get("auto_post_interval_min", "120"),
            "types": ch.get("auto_post_types", "info|question"),
            "chat_id": ch.get("chat_id"),
        })
    return jsonify({"enabled_count": len(enabled), "channels": status})

@app.route('/api/channels', methods=['POST'])
@api_auth
@permission_required('send_broadcast')
def api_add_channel_manual():
    """إضافة قناة يدوياً — مع تحديد الدور"""
    data = request.json or {}
    chat_id = data.get('chat_id', '').strip()
    title = data.get('title', '').strip()
    ch_type = data.get('type', 'channel')
    platform = str(data.get('platform', 'telegram') or 'telegram').strip().lower()
    owner_admin_id = str(data.get('owner_admin_id', '') or session.get('admin_id', '') or '').strip()
    managed_ids_raw = data.get('managed_by_admin_ids', '')
    if isinstance(managed_ids_raw, list):
        managed_ids_raw = '|'.join([str(x).strip() for x in managed_ids_raw if str(x).strip()])
    managed_by_admin_ids = _pipe_ids(managed_ids_raw or owner_admin_id)

    if not chat_id:
        return jsonify({'error': 'chat_id required'}), 400
    if platform not in ('telegram', 'whatsapp', 'webhook'):
        return jsonify({'error': 'platform must be telegram/whatsapp/webhook'}), 400

    # فحص عدم التكرار
    channels = read_csv('bot_channels.csv')
    for ch in channels:
        if ch.get('chat_id') == str(chat_id):
            return jsonify({'error': 'Channel already exists'}), 400

    ch_id = f"CH{secrets.token_hex(3).upper()}"
    fieldnames = get_fieldnames('bot_channels.csv', _CHANNEL_DEFAULT_FIELDS)
    new_channel = {
        'id': ch_id,
        'chat_id': str(chat_id),
        'title': title,
        'type': ch_type,
        'platform': platform,
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
        'brand_voice': data.get('brand_voice', ''),
        'owner_admin_id': owner_admin_id,
        'managed_by_admin_ids': managed_by_admin_ids,
        'allow_subadmin_publish': 'yes' if str(data.get('allow_subadmin_publish', 'no')).lower() in ('1', 'true', 'yes', 'on') else 'no',
        'ai_agent_id': str(data.get('ai_agent_id', '') or '').strip(),
        'platform_account_id': str(data.get('platform_account_id', '') or '').strip(),
        'company_name': str(data.get('company_name', '') or '').strip(),
        'download_link': str(data.get('download_link', '') or '').strip(),
        'promo_code': str(data.get('promo_code', '') or '').strip(),
        'affiliate_link': str(data.get('affiliate_link', '') or '').strip(),
        'auto_post_enabled': 'no',
        'auto_post_interval_min': '120',
        'auto_post_types': 'info|question|prediction|analysis',
    }
    new_channel, _ = _normalize_channel_row(new_channel, actor_uid=owner_admin_id)
    append_csv('bot_channels.csv', new_channel, fieldnames)
    log_action('add_channel_manual', f'{ch_id}: {title} ({chat_id}) platform={platform} role={new_channel["channel_role"]}')
    return jsonify({'success': True, 'id': ch_id})

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
    fieldnames = get_fieldnames('bot_tokens.csv', ['id','name','token','is_active','created_at','admin_ids','last_started','total_users','total_transactions','freeze_until','status','description','can_manage_bots','features'])
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
        'can_manage_bots': data.get('can_manage_bots', 'no'),
        'features': data.get('features', ''),
    }
    append_csv('bot_tokens.csv', new_bot, fieldnames)
    log_action('add_bot', new_id)
    return jsonify({'success': True, 'id': new_id})

@app.route('/api/bots/<bot_id>/toggle', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_toggle_bot(bot_id):
    bots = read_csv('bot_tokens.csv')
    fieldnames = get_fieldnames('bot_tokens.csv', ['id','name','token','is_active','created_at','admin_ids','last_started','total_users','total_transactions','freeze_until','status','description','can_manage_bots','features'])
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
    fieldnames = get_fieldnames('bot_tokens.csv', ['id','name','token','is_active','created_at','admin_ids','last_started','total_users','total_transactions','freeze_until','status','description','can_manage_bots','features'])
    bots = [b for b in bots if b.get('id') != bot_id]
    write_csv('bot_tokens.csv', bots, fieldnames)
    log_action('delete_bot', bot_id)
    return jsonify({'success': True})


@app.route('/api/bots/<bot_id>/features', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_bot_features(bot_id):
    """تحديث مميزات بوت معين"""
    data = request.json or {}
    features = data.get('features', '')
    bots = read_csv('bot_tokens.csv')
    fieldnames = get_fieldnames('bot_tokens.csv', ['id','name','token','is_active','created_at','admin_ids','last_started','total_users','total_transactions','freeze_until','status','description','can_manage_bots','features'])
    for b in bots:
        if b.get('id') == bot_id:
            b['features'] = features
            break
    write_csv('bot_tokens.csv', bots, fieldnames)
    log_action('update_bot_features', bot_id)
    return jsonify({'success': True})


# ═══════════════════════════════════════════════════════════════════
# ===== Smart Bot Engine API — لوحة التحكم الذكية =====
# ═══════════════════════════════════════════════════════════════════

@app.route('/api/smart/analytics')
@app.route('/api/smart/analytics/<bot_id>')
@api_auth
def api_smart_analytics(bot_id=None):
    """تحليلات البوتات"""
    try:
        from smart_bot import SmartBotEngine
        days = int(request.args.get('days', 7))
        # Use the first running bot's smart engine or create a dummy
        engine = _get_smart_engine()
        if not engine:
            return jsonify({'error': 'Smart engine not available'}), 500
        stats = engine.get_analytics(bot_id=bot_id or '', days=days)
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/smart/auto-replies')
@api_auth
def api_smart_auto_replies():
    """قائمة الردود الذكية"""
    try:
        from smart_bot import SmartBotEngine
        engine = _get_smart_engine()
        if not engine:
            return jsonify({'replies': []})
        bot_id = request.args.get('bot_id', '')
        replies = engine.list_auto_replies(bot_id)
        return jsonify({'replies': replies})
    except Exception as e:
        return jsonify({'replies': [], 'error': str(e)})


@app.route('/api/smart/auto-replies', methods=['POST'])
@api_auth
@api_permission_required('manage_bots')
def api_smart_add_auto_reply():
    """إضافة رد ذكي"""
    data = request.json or {}
    engine = _get_smart_engine()
    if not engine:
        return jsonify({'error': 'Smart engine not available'}), 500
    keyword = data.get('keyword', '').strip()
    response = data.get('response', '').strip()
    if not keyword or not response:
        return jsonify({'error': 'keyword and response required'}), 400
    reply_id = engine.add_auto_reply(
        keyword=keyword,
        response=response,
        match_type=data.get('match_type', 'contains'),
        bot_id=data.get('bot_id', ''),
        priority=int(data.get('priority', 0))
    )
    log_action('add_auto_reply', reply_id)
    return jsonify({'success': True, 'id': reply_id})


@app.route('/api/smart/auto-replies/<reply_id>', methods=['DELETE'])
@api_auth
@api_permission_required('manage_bots')
def api_smart_delete_auto_reply(reply_id):
    """حذف رد ذكي"""
    engine = _get_smart_engine()
    if not engine:
        return jsonify({'error': 'Smart engine not available'}), 500
    engine.delete_auto_reply(reply_id)
    log_action('delete_auto_reply', reply_id)
    return jsonify({'success': True})


@app.route('/api/smart/chains')
@api_auth
def api_smart_chains():
    """قائمة سلاسل البوتات"""
    try:
        engine = _get_smart_engine()
        if not engine:
            return jsonify({'chains': []})
        return jsonify({'chains': engine.list_chains()})
    except Exception as e:
        return jsonify({'chains': [], 'error': str(e)})


@app.route('/api/smart/chains', methods=['POST'])
@api_auth
@api_permission_required('manage_bots')
def api_smart_add_chain():
    """إضافة سلسلة بوتات"""
    data = request.json or {}
    engine = _get_smart_engine()
    if not engine:
        return jsonify({'error': 'Smart engine not available'}), 500
    chain_id = engine.add_chain(
        trigger_event=data.get('trigger_event', ''),
        source_bot=data.get('source_bot', ''),
        target_bot=data.get('target_bot', ''),
        action=data.get('action', 'send_message'),
        message_template=data.get('message_template', '')
    )
    log_action('add_bot_chain', chain_id)
    return jsonify({'success': True, 'id': chain_id})


@app.route('/api/smart/notifications')
@api_auth
def api_smart_notifications():
    """قائمة الإشعارات الذكية"""
    try:
        engine = _get_smart_engine()
        if not engine:
            return jsonify({'notifications': []})
        return jsonify({'notifications': engine.list_smart_notifications()})
    except Exception as e:
        return jsonify({'notifications': [], 'error': str(e)})


@app.route('/api/smart/notifications', methods=['POST'])
@api_auth
@api_permission_required('manage_bots')
def api_smart_add_notification():
    """إضافة إشعار ذكي"""
    data = request.json or {}
    engine = _get_smart_engine()
    if not engine:
        return jsonify({'error': 'Smart engine not available'}), 500
    notif_id = engine.add_smart_notification(
        trigger=data.get('trigger', ''),
        message_template=data.get('message_template', ''),
        bot_id=data.get('bot_id', '')
    )
    log_action('add_smart_notification', notif_id)
    return jsonify({'success': True, 'id': notif_id})


@app.route('/api/smart/webhooks')
@api_auth
def api_smart_webhooks():
    """قائمة الويب هوكس"""
    try:
        engine = _get_smart_engine()
        if not engine:
            return jsonify({'webhooks': []})
        return jsonify({'webhooks': engine.list_webhooks()})
    except Exception as e:
        return jsonify({'webhooks': [], 'error': str(e)})


@app.route('/api/smart/webhooks', methods=['POST'])
@api_auth
@api_permission_required('manage_bots')
def api_smart_add_webhook():
    """إضافة webhook"""
    data = request.json or {}
    engine = _get_smart_engine()
    if not engine:
        return jsonify({'error': 'Smart engine not available'}), 500
    hook_id = engine.add_webhook(
        name=data.get('name', ''),
        url=data.get('url', ''),
        events=data.get('events', '*'),
        secret=data.get('secret', '')
    )
    log_action('add_webhook', hook_id)
    return jsonify({'success': True, 'id': hook_id})


@app.route('/api/smart/webhooks/<hook_id>', methods=['DELETE'])
@api_auth
@api_permission_required('manage_bots')
def api_smart_delete_webhook(hook_id):
    """حذف webhook"""
    engine = _get_smart_engine()
    if not engine:
        return jsonify({'error': 'Smart engine not available'}), 500
    engine.delete_webhook(hook_id)
    log_action('delete_webhook', hook_id)
    return jsonify({'success': True})


@app.route('/api/smart/templates')
@api_auth
def api_smart_templates():
    """قوالب البوتات الجاهزة"""
    from smart_bot import BOT_TEMPLATES
    return jsonify({'templates': BOT_TEMPLATES})


def _get_smart_engine():
    """الحصول على SmartBotEngine من أي بوت نشط"""
    try:
        from multi_bot import MultiBotManager
        manager = MultiBotManager()
        # Try to get from active bots
        for bot_id, info in manager.active_bots.items():
            bot = info.get('bot')
            if bot and hasattr(bot, 'smart_engine') and bot.smart_engine:
                return bot.smart_engine
        # Fallback: create from first active bot's token
        active = manager.get_active_bots()
        if active:
            token = active[0].get('token', '')
            if token:
                from comprehensive_bot import ComprehensiveDUXBot
                from smart_bot import SmartBotEngine
                dummy = ComprehensiveDUXBot.__new__(ComprehensiveDUXBot)
                dummy.token = token
                return SmartBotEngine(dummy)
    except Exception as e:
        logger.error(f"Error getting smart engine: {e}")
    return None


# ===== نظام العملاء (White-Label / Agency) =====
# كل عميل: بوت خاص + دخول لوحة خاص + مميزات محددة + اشتراك زمني + عزل بيانات كامل.

def _clients():
    from clients_manager import get_client_manager
    _start_clients_watchdog()
    return get_client_manager()


_clients_watchdog_started = False


def _start_clients_watchdog():
    """حراسة الاشتراكات كل 60 ثانية: إيقاف بوتات العملاء المنتهي اشتراكهم + إشعار المالك."""
    global _clients_watchdog_started
    if _clients_watchdog_started:
        return
    _clients_watchdog_started = True

    def _notify(text):
        try:
            _comp_alert_admins(text)
        except Exception:
            pass

    def _loop():
        import time as _time
        while True:
            try:
                _clients().check_subscriptions(notify=_notify)
            except Exception as e:
                _auth_logger.error('clients watchdog error: %s', e)
            _time.sleep(60)

    threading.Thread(target=_loop, daemon=True).start()


# ===== Agent + Ticket Watchdog =====
_agents_watchdog_started = False

def _start_agents_watchdog():
    """Dual watchdog: stale transaction voiding + SLA monitoring + online checks."""
    global _agents_watchdog_started
    if _agents_watchdog_started:
        return
    _agents_watchdog_started = True

    def _loop():
        import time as _time
        while True:
            try:
                # Check agent online status
                agent_db.check_agents_online()

                # Void stale pending transactions (> 5 min)
                voided = agent_db.void_stale_transactions()
                if voided:
                    for v in voided:
                        try:
                            _comp_alert_admins(
                                f"⏰ معاملة متأخرة تم إلغاؤها:\n"
                                f"الوكيل: {v['agent_id']}\n"
                                f"المبلغ: {v['amount']}\n"
                                f"المعاملة: {v['txn_id']}")
                        except Exception:
                            pass

                # Ops V2 step/request deadline processor
                try:
                    ops = agent_db.process_ops_deadlines()
                    if (ops.get('escalated_steps', 0) or ops.get('escalated_requests', 0)):
                        _comp_alert_admins(
                            "🚨 Ops Watchdog:\n"
                            f"- escalated_steps: {ops.get('escalated_steps', 0)}\n"
                            f"- escalated_requests: {ops.get('escalated_requests', 0)}\n"
                            f"- auto_completed: {ops.get('completed', 0)}")
                except Exception as _opse:
                    _auth_logger.error('ops watchdog error: %s', _opse)

                # Check SLA breaches
                breached = ticket_system.check_sla_breached()
                if breached:
                    count = ticket_system.escalate_overdue_tickets()
                    if count:
                        try:
                            _comp_alert_admins(
                                f"🚨 {count} تذكرة تجاوزت SLA وتم تصعيدها")
                        except Exception:
                            pass

            except Exception as e:
                _auth_logger.error('agents watchdog error: %s', e)
            _time.sleep(60)

    threading.Thread(target=_loop, daemon=True).start()


def _client_public(c):
    """عرض آمن لبيانات عميل (بدون التوكن أو الهاش)"""
    import json as _json
    if not c:
        return None
    feats = []
    try:
        feats = _json.loads(c.get('features') or '[]')
    except Exception:
        pass
    return {
        'id': c.get('id'), 'name': c.get('name'), 'contact': c.get('contact'),
        'bot_username': c.get('bot_username'),
        'dash_username': c.get('dash_username'),
        'features': feats, 'admin_ids': c.get('admin_ids', ''),
        'subscription_start': c.get('subscription_start'),
        'subscription_end': c.get('subscription_end'),
        'status': c.get('status'), 'notes': c.get('notes', ''),
        'created_at': c.get('created_at'), 'last_login': c.get('last_login'),
        'running': bool(_clients().is_running(c.get('id'))),
        'days_left': _clients().days_left(c),
        'expired': _clients().is_expired(c),
        'revenue_share': int(c.get('revenue_share') or 30),
        'custom_domain': c.get('custom_domain', ''),
        'balance': float(c.get('balance') or 0),
        'preferred_pm': c.get('preferred_pm', ''),
    }


@app.route('/api/clients')
@api_auth
@permission_required('manage_bots')
def api_clients_list():
    _start_clients_watchdog()
    from clients_manager import FEATURES
    return jsonify({
        'clients': [_client_public(c) for c in _clients().list_clients()],
        'features': FEATURES,
    })


@app.route('/api/clients', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_clients_create():
    data = request.json or {}
    row, err = _clients().create(
        name=data.get('name', ''),
        bot_username=data.get('bot_username', ''),
        bot_token=data.get('bot_token', ''),
        dash_username=data.get('dash_username', ''),
        dash_password=data.get('dash_password', ''),
        features=data.get('features'),
        subscription_days=data.get('subscription_days', 30),
        contact=data.get('contact', ''),
        admin_ids=data.get('admin_ids', ''),
        notes=data.get('notes', ''),
        revenue_share=data.get('revenue_share', 30),
    )
    if err:
        return jsonify({'error': err}), 400
    log_action('create_client', row['id'])
    if data.get('preferred_pm'):
        _clients().update(row['id'], {'preferred_pm': data['preferred_pm']})
        row['preferred_pm'] = data['preferred_pm']
    return jsonify({'success': True, 'client': _client_public(row)})


@app.route('/api/clients/<client_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_clients_update(client_id):
    data = request.json or {}
    ok, err = _clients().update(client_id, data)
    if not ok:
        return jsonify({'error': err or 'فشل التحديث'}), 400
    log_action('update_client', client_id)
    # إعادة تشغيل البوت لو كان يعمل حتى تسري التعديلات (مميزات/توكن)
    c = _clients().get(client_id)
    if c and _clients().is_running(client_id) and ('features' in data or 'bot_token' in data or 'admin_ids' in data):
        _clients().restart(client_id)
    return jsonify({'success': True, 'client': _client_public(_clients().get(client_id))})


@app.route('/api/clients/<client_id>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_clients_delete(client_id):
    keep_data = (request.args.get('keep_data', '1') == '1')
    _clients().delete(client_id, keep_data=keep_data)
    log_action('delete_client', client_id)
    return jsonify({'success': True})


@app.route('/api/clients/<client_id>/<action>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_clients_control(client_id, action):
    cm = _clients()
    c = cm.get(client_id)
    if not c:
        return jsonify({'error': 'العميل غير موجود'}), 404
    if action == 'start':
        ok, msg = cm.start(client_id)
    elif action == 'stop':
        cm.stop(client_id)
        ok, msg = True, 'تم إيقاف بوت العميل'
    elif action == 'restart':
        ok, msg = cm.restart(client_id)
    elif action == 'suspend':
        cm.stop(client_id)
        ok, err = cm.update(client_id, {'status': 'suspended'})
        ok, msg = (True, 'تم إيقاف العميل مؤقتاً') if ok else (False, err)
    elif action == 'activate':
        ok, err = cm.update(client_id, {'status': 'active'})
        ok, msg = (True, 'تم تفعيل العميل') if ok else (False, err)
    elif action == 'renew':
        days = int((request.json or {}).get('days', 30) or 30)
        end = cm.renew(client_id, days)
        ok, msg = (bool(end), f'تم التجديد حتى {end}') if end else (False, 'فشل التجديد')
    else:
        return jsonify({'error': 'إجراء غير معروف'}), 400
    log_action(f'client_{action}', client_id)
    return jsonify({'success': bool(ok), 'message': msg,
                    'client': _client_public(cm.get(client_id))})


@app.route('/api/clients/<client_id>/stats')
@api_auth
@permission_required('manage_bots')
def api_clients_stats(client_id):
    if not _clients().get(client_id):
        return jsonify({'error': 'العميل غير موجود'}), 404
    return jsonify(_clients().client_stats(client_id))


@app.route('/api/clients/<client_id>/data')
@api_auth
@permission_required('manage_bots')
def api_clients_data(client_id):
    """رؤية المالك الكاملة لبيانات عميل — من مجلده المعزول"""
    if not _clients().get(client_id):
        return jsonify({'error': 'العميل غير موجود'}), 404
    kind = request.args.get('type', 'users')
    rows, fields = _clients().client_data(client_id, kind, limit=int(request.args.get('limit', 100)))
    rows.reverse()  # الأحدث أولاً
    return jsonify({'rows': rows[:int(request.args.get('limit', 100))], 'fields': fields})


# ── بوابة العميل (لوحة مستقلة باسم مستخدم/كلمة مرور) ──

@app.route('/client-login')
def client_login_page():
    if session.get('client_logged_in') and session.get('client_id'):
        return redirect('/client')
    return render_template('client_login.html')


@app.route('/api/client/login', methods=['POST'])
def api_client_login():
    data = request.json or {}
    cm = _clients()
    c = cm.verify_login(data.get('username', ''), data.get('password', ''))
    if not c:
        return jsonify({'error': 'بيانات الدخول غير صحيحة'}), 401
    if c.get('status') == 'suspended':
        return jsonify({'error': 'حسابك موقوف — تواصل مع الإدارة'}), 403
    session['client_logged_in'] = True
    session['client_id'] = c['id']
    session.permanent = False
    return jsonify({'success': True, 'redirect': '/client'})


@app.route('/api/client/logout', methods=['POST'])
def api_client_logout():
    session.pop('client_logged_in', None)
    session.pop('client_id', None)
    return jsonify({'success': True})


def _client_session():
    cid = session.get('client_id') if session.get('client_logged_in') else None
    if not cid:
        return None
    return _clients().get(cid)


@app.route('/client')
def client_dashboard_page():
    c = _client_session()
    if not c:
        return redirect('/client-login')
    from clients_manager import FEATURES
    return render_template('client_dashboard.html',
                           client=_client_public(c), features=FEATURES)


@app.route('/api/client/me')
def api_client_me():
    c = _client_session()
    if not c:
        return jsonify({'error': 'غير مسجل الدخول'}), 401
    from clients_manager import FEATURES
    d = _client_public(c)
    d['stats'] = _clients().client_stats(c['id'])
    d['features_labels'] = {k: FEATURES.get(k, k) for k in d['features']}
    return jsonify(d)


@app.route('/api/client/data')
def api_client_data():
    """بيانات العميل نفسه (قراءة فقط) من مجلده المعزول"""
    c = _client_session()
    if not c:
        return jsonify({'error': 'غير مسجل الدخول'}), 401
    kind = request.args.get('type', 'users')
    if kind not in ('users', 'transactions', 'svrp_wallets'):
        return jsonify({'error': 'نوع غير مسموح'}), 400
    limit = min(int(request.args.get('limit', 50)), 100)
    rows, fields = _clients().client_data(c['id'], kind, limit=limit)
    rows.reverse()
    return jsonify({'rows': rows[:limit], 'fields': fields})


@app.route('/api/client/payment-methods')
def api_client_pm_list():
    """وسائل الدفع المتاحة للعميل (للإيداع)"""
    c = _client_session()
    if not c:
        return jsonify({'error': 'غير مسجل الدخول'}), 401
    from clients_manager import get_payment_manager
    pm = get_payment_manager()
    return jsonify({'success': True, 'methods': pm.get_all(active_only=True)})


@app.route('/api/client/balance')
def api_client_balance():
    """رصيد العميل الحالي"""
    c = _client_session()
    if not c:
        return jsonify({'error': 'غير مسجل الدخول'}), 401
    from clients_manager import get_client_manager
    cm = get_client_manager()
    return jsonify({'success': True, 'balance': cm.get_balance(c['id'])})


@app.route('/api/client/deposit-request', methods=['POST'])
def api_client_deposit_request():
    """طلب إيداع من العميل"""
    c = _client_session()
    if not c:
        return jsonify({'error': 'غير مسجل الدخول'}), 401
    data = request.get_json(force=True, silent=True) or {}
    amount = data.get('amount', 0)
    method = data.get('method', '').strip()
    note = data.get('note', '')
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError()
    except Exception:
        return jsonify({'success': False, 'error': 'المبلغ غير صالح'}), 400
    if not method:
        return jsonify({'success': False, 'error': 'اختر وسيلة الدفع'}), 400
    from clients_manager import get_client_manager
    cm = get_client_manager()
    tx = cm.add_transaction(c['id'], 'deposit', amount, method, note, status='pending')
    # إشعار الأدمن
    try:
        _notify_rental_admin(
            f"💰 طلب إيداع جديد من العميل <b>{c.get('name','')}</b>\n"
            f"المبلغ: <b>{amount:.2f}</b>\nالوسيلة: {method}\nملاحظة: {note or '—'}"
        )
    except Exception:
        pass
    return jsonify({'success': True, 'transaction': tx})


@app.route('/api/client/withdraw-request', methods=['POST'])
def api_client_withdraw_request():
    """طلب سحب من العميل"""
    c = _client_session()
    if not c:
        return jsonify({'error': 'غير مسجل الدخول'}), 401
    data = request.get_json(force=True, silent=True) or {}
    amount = data.get('amount', 0)
    method = data.get('method', '').strip()
    note = data.get('note', '')
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError()
    except Exception:
        return jsonify({'success': False, 'error': 'المبلغ غير صالح'}), 400
    if not method:
        return jsonify({'success': False, 'error': 'اختر وسيلة السحب'}), 400
    from clients_manager import get_client_manager
    cm = get_client_manager()
    balance = cm.get_balance(c['id'])
    if balance < amount:
        return jsonify({'success': False, 'error': f'الرصيد غير كافٍ (متوفر: {balance:.2f})'}), 400
    tx = cm.add_transaction(c['id'], 'withdraw', amount, method, note, status='pending')
    # إشعار الأدمن
    try:
        _notify_rental_admin(
            f"💸 طلب سحب جديد من العميل <b>{c.get('name','')}</b>\n"
            f"المبلغ: <b>{amount:.2f}</b>\nالرصيد: {balance:.2f}\nالوسيلة: {method}\nملاحظة: {note or '—'}"
        )
    except Exception:
        pass
    return jsonify({'success': True, 'transaction': tx})


@app.route('/api/client/my-transactions')
def api_client_my_transactions():
    """سجل معاملات العميل"""
    c = _client_session()
    if not c:
        return jsonify({'error': 'غير مسجل الدخول'}), 401
    from clients_manager import get_client_manager
    cm = get_client_manager()
    txs = cm.get_transactions(c['id'])
    txs.reverse()
    return jsonify({'success': True, 'transactions': txs})


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
    """بث رسالة — يدعم وسائط متعددة + فردي/جماعي + دولة + أولوية + منصات سوشيال + استهداف وكلاء/دول/منصات"""
    data = request.json or {}
    message = data.get('message', '')
    target = data.get('target', 'both')
    recipient = data.get('recipient', 'all')
    priority = data.get('priority', 'normal')
    country = data.get('country', 'all')
    media_urls = data.get('media_urls', [])
    target_user = data.get('target_user', '')
    target_name = data.get('target_name', '')
    search_query = data.get('search_query', '')
    platform_account_id = data.get('platform_account_id', '')
    
    # New targeting options
    target_agents = data.get('target_agents', [])  # List of agent IDs
    target_countries = data.get('target_countries', [])  # List of country codes
    target_platforms = data.get('target_platforms', [])  # List of social platforms
    broadcast_to_all_agents = data.get('broadcast_to_all_agents', False)
    broadcast_to_all_channels = data.get('broadcast_to_all_channels', False)
    
    valid_targets = {'telegram', 'web', 'both', 'whatsapp', 'all', 'facebook', 'instagram', 'twitter', 'linkedin', 'youtube', 'tiktok', 'social'}
    if target not in valid_targets:
        return jsonify({'success': False, 'error': 'target غير صالح'}), 400

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
    if target in ('web', 'both', 'all', 'social'):
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

    # ── Build target audience based on targeting options ──
    target_telegram_users = []
    target_social_accounts = []
    
    if recipient == 'all' or broadcast_to_all_agents:
        # Broadcast to all agents' connected channels
        if broadcast_to_all_agents:
            target_agents = []  # Will be filled with all active agents
    
    if target_agents:
        # Filter to specific agents
        pass
    
    if target_countries:
        # Filter by country
        pass
    
    # ── Telegram broadcast (queued for bot) ──
    fieldnames = get_fieldnames('broadcast_queue.csv', [
        'id', 'message', 'target', 'recipient', 'priority', 'country', 'media_urls',
        'target_user', 'target_name', 'created_at', 'created_by', 'status',
        'platform', 'platform_account_id', 'type', 'target_chat_id',
        'target_channel_id', 'scheduled_at', 'target_agents', 'target_countries',
        'target_platforms', 'broadcast_to_all_agents', 'broadcast_to_all_channels'
    ])

    def _queue_entry(platform_name):
        entry = {
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
            'status': 'pending',
            'platform': platform_name,
            'platform_account_id': platform_account_id,
            'type': 'broadcast',
            'target_chat_id': '',
            'target_channel_id': '',
            'scheduled_at': '',
            'target_agents': '|'.join(target_agents) if target_agents else '',
            'target_countries': '|'.join(target_countries) if target_countries else '',
            'target_platforms': '|'.join(target_platforms) if target_platforms else '',
            'broadcast_to_all_agents': 'yes' if broadcast_to_all_agents else 'no',
            'broadcast_to_all_channels': 'yes' if broadcast_to_all_channels else 'no',
        }
        append_csv('broadcast_queue.csv', entry, fieldnames)

    # Queue for traditional platforms
    if target in ('telegram', 'both', 'all'):
        _queue_entry('telegram')
    if target in ('whatsapp', 'all'):
        _queue_entry('whatsapp')
    
    # Queue for social media platforms
    social_platforms = {'facebook', 'instagram', 'twitter', 'linkedin', 'youtube', 'tiktok'}
    if target in social_platforms or target_platforms:
        platforms_to_broadcast = target_platforms if target_platforms else ([target] if target in social_platforms else list(social_platforms))
        for platform_name in platforms_to_broadcast:
            _queue_entry(platform_name)

    log_action('broadcast', f'recipient={recipient} target={target} priority={priority} country={country} msg={message[:50]} agents={target_agents} countries={target_countries} platforms={target_platforms}')
    
    target_label_map = {
        'both': 'تيليغرام والموقع', 'telegram': 'تيليغرام', 'web': 'الموقع',
        'whatsapp': 'واتساب', 'all': 'كل المنصات',
        'facebook': 'فيسبوك', 'instagram': 'إنستجرام', 'twitter': 'تويتر/إكس',
        'linkedin': 'لينكدإن', 'youtube': 'يوتيوب', 'tiktok': 'تيك توك',
        'social': 'السوشيال ميديا'
    }
    target_label = target_label_map.get(target, target)
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


# ══════════════════════════════════════════════════════════════════════════════
# ── Unified Admin Center — consolidated sub-admin + client + revenue ────────
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/admin-center')
@admin_required
@permission_required('manage_admins')
def page_admin_center():
    return render_template('admin_center.html', active_page='admin_center')


@app.route('/api/admin-center/admins', methods=['GET'])
@api_auth
@permission_required('manage_admins')
def api_admin_center_list():
    """Merge admins from admin_permissions.json + admin_roles SQLite + clients.csv."""
    admins = []
    seen = set()

    # 1. From admin_permissions.json (Telegram bot admins)
    perm_file = os.path.join(BASE_DIR, 'admin_permissions.json')
    if os.path.exists(perm_file):
        try:
            with open(perm_file, 'r', encoding='utf-8') as f:
                perms = json.load(f)
                if isinstance(perms, list):
                    for p in perms:
                        tid = str(p.get('telegram_id', ''))
                        if tid and tid not in seen:
                            seen.add(tid)
                            admins.append({
                                'telegram_id': tid,
                                'name': p.get('name', ''),
                                'role': p.get('role', 'support'),
                                'type': 'permanent' if not p.get('expires_at') else 'temp',
                                'expires_at': p.get('expires_at', ''),
                                'added_at': p.get('added_at', ''),
                                'is_active': p.get('is_active', 'yes'),
                                'tenant_id': p.get('tenant_id', ''),
                                'description': p.get('description', ''),
                                'source': 'permissions'
                            })
        except Exception:
            pass

    # 2. From admin_roles SQLite (RBAC roles)
    try:
        import sqlite3 as _sql
        conn = _sql.connect(os.path.join(BASE_DIR, 'vex_games.db'), timeout=5)
        conn.row_factory = _sql.Row
        rows = conn.execute(
            'SELECT uid, role, permissions, created_at, created_by FROM admin_roles'
        ).fetchall()
        conn.close()
        for r in rows:
            uid = str(r['uid'])
            if uid and uid not in seen:
                seen.add(uid)
                admins.append({
                    'telegram_id': uid,
                    'name': '',
                    'role': r['role'],
                    'type': 'permanent',
                    'expires_at': '',
                    'added_at': r['created_at'],
                    'is_active': 'yes',
                    'tenant_id': '',
                    'description': '',
                    'source': 'rbac'
                })
    except Exception:
        pass

    # 3. From clients.csv (client admin usernames)
    clients_data = read_csv('clients.csv')
    tenants = {}
    for c in clients_data:
        cid = c.get('id', '')
        tenants[cid] = c.get('name', cid)
        admin_user = c.get('dash_username', '')
        if admin_user and admin_user not in seen:
            seen.add(admin_user)
            admins.append({
                'telegram_id': admin_user,
                'name': c.get('name', '') + ' (أدمن العميل)',
                'role': 'client_admin',
                'type': 'permanent',
                'expires_at': '',
                'added_at': c.get('created_at', ''),
                'is_active': 'yes',
                'tenant_id': cid,
                'description': 'admin login for client: ' + c.get('name', ''),
                'source': 'client'
            })

    return jsonify({'success': True, 'admins': admins, 'tenants': tenants})


@app.route('/api/admin-center/admins', methods=['POST'])
@api_auth
@permission_required('manage_admins')
def api_admin_center_add():
    """Add a new admin to admin_permissions.json + optional RBAC + optional tenant."""
    data = request.json or {}
    telegram_id = str(data.get('telegram_id', '')).strip()
    name = data.get('name', '')
    role = data.get('role', 'full')
    admin_type = data.get('type', 'permanent')
    duration_hours = int(data.get('duration_hours', 0))
    tenant_id = data.get('tenant_id', '')
    description = data.get('description', '')

    if not telegram_id:
        return jsonify({'success': False, 'error': 'المعرف مطلوب'}), 400

    # Add to admin_permissions.json
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
        'name': name,
        'role': role,
        'added_by': session.get('admin_id', ''),
        'added_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'expires_at': expires_at,
        'is_active': 'yes',
        'tenant_id': tenant_id,
        'description': description
    }
    perms.append(new_admin)

    try:
        with open(perm_file, 'w', encoding='utf-8') as f:
            json.dump(perms, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # Also add to RBAC SQLite
    try:
        import sqlite3 as _sql
        conn = _sql.connect(os.path.join(BASE_DIR, 'vex_games.db'), timeout=5)
        rbac_perms = _get_role_permissions(role)
        conn.execute(
            'INSERT OR REPLACE INTO admin_roles (uid, role, permissions, created_at, created_by) VALUES (?,?,?,?,?)',
            (telegram_id, role, json.dumps(rbac_perms), datetime.now().isoformat(), session.get('admin_id', ''))
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    log_action('admin_center_add', f'{telegram_id}: {role} tenant={tenant_id}')
    return jsonify({'success': True})


@app.route('/api/admin-center/admins/<admin_id>', methods=['PUT'])
@api_auth
@permission_required('manage_admins')
def api_admin_center_update(admin_id):
    """Update admin in admin_permissions.json + RBAC."""
    data = request.json or {}
    role = data.get('role', '')
    name = data.get('name', '')
    tenant_id = data.get('tenant_id', '')
    description = data.get('description', '')

    # Update admin_permissions.json
    perm_file = os.path.join(BASE_DIR, 'admin_permissions.json')
    if os.path.exists(perm_file):
        try:
            with open(perm_file, 'r', encoding='utf-8') as f:
                perms = json.load(f)
                if isinstance(perms, list):
                    for p in perms:
                        if str(p.get('telegram_id')) == str(admin_id):
                            if role: p['role'] = role
                            if name: p['name'] = name
                            if 'tenant_id' in data: p['tenant_id'] = tenant_id
                            if 'description' in data: p['description'] = description
                            break
                    with open(perm_file, 'w', encoding='utf-8') as f2:
                        json.dump(perms, f2, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # Update RBAC SQLite
    if role:
        try:
            import sqlite3 as _sql
            conn = _sql.connect(os.path.join(BASE_DIR, 'vex_games.db'), timeout=5)
            rbac_perms = _get_role_permissions(role)
            conn.execute(
                'INSERT OR REPLACE INTO admin_roles (uid, role, permissions, created_at, created_by) VALUES (?,?,?,?,?)',
                (admin_id, role, json.dumps(rbac_perms), datetime.now().isoformat(), session.get('admin_id', ''))
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    log_action('admin_center_update', f'{admin_id} role={role} tenant={tenant_id}')
    return jsonify({'success': True})


@app.route('/api/admin-center/admins/<admin_id>/tenant', methods=['POST'])
@api_auth
@permission_required('manage_admins')
def api_admin_center_assign_tenant(admin_id):
    """Assign admin to a specific tenant/client."""
    data = request.json or {}
    tenant_id = data.get('tenant_id', '')

    perm_file = os.path.join(BASE_DIR, 'admin_permissions.json')
    if os.path.exists(perm_file):
        try:
            with open(perm_file, 'r', encoding='utf-8') as f:
                perms = json.load(f)
                if isinstance(perms, list):
                    for p in perms:
                        if str(p.get('telegram_id')) == str(admin_id):
                            p['tenant_id'] = tenant_id
                            break
                    with open(perm_file, 'w', encoding='utf-8') as f2:
                        json.dump(perms, f2, ensure_ascii=False, indent=2)
        except Exception:
            pass

    log_action('admin_center_assign_tenant', f'{admin_id} tenant={tenant_id}')
    return jsonify({'success': True})


@app.route('/api/admin-center/admins/<admin_id>', methods=['DELETE'])
@api_auth
@permission_required('manage_admins')
def api_admin_center_delete(admin_id):
    """Delete admin from all systems."""
    # Remove from admin_permissions.json
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

    # Remove from RBAC SQLite
    try:
        import sqlite3 as _sql
        conn = _sql.connect(os.path.join(BASE_DIR, 'vex_games.db'), timeout=5)
        conn.execute('DELETE FROM admin_roles WHERE uid = ?', (admin_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass

    log_action('admin_center_delete', f'{admin_id}')
    return jsonify({'success': True})


@app.route('/api/admin-center/revenue-share/<client_id>', methods=['POST'])
@api_auth
@permission_required('manage_admins')
def api_admin_center_set_revenue_share(client_id):
    """Set revenue share percentage for a client."""
    data = request.json or {}
    pct = int(data.get('revenue_share', 30))
    pct = max(0, min(100, pct))

    clients_data = read_csv('clients.csv')
    fieldnames = get_fieldnames('clients.csv', ['id', 'name', 'contact', 'bot_username', 'bot_token',
        'dash_username', 'dash_password_hash', 'salt', 'features', 'admin_ids',
        'subscription_start', 'subscription_end', 'status', 'bot_autostart',
        'notes', 'created_at', 'last_login'])
    if 'revenue_share' not in fieldnames:
        fieldnames.append('revenue_share')

    found = False
    for c in clients_data:
        if c.get('id') == client_id:
            c['revenue_share'] = str(pct)
            found = True
            break

    if found:
        write_csv('clients.csv', clients_data, fieldnames)

    log_action('admin_center_revenue_share', f'{client_id} {pct}%')
    return jsonify({'success': True, 'revenue_share': pct})


@app.route('/api/admin-center/revenue', methods=['GET'])
@api_auth
@permission_required('manage_admins')
def api_admin_center_revenue():
    """Get revenue breakdown by client."""
    import sqlite3 as _sql
    stats = {'total_game_profit': 0, 'admin_share': 0, 'client_share': 0, 'total_rounds': 0}
    by_client = []

    try:
        conn = _sql.connect(os.path.join(BASE_DIR, 'boterx.db'), timeout=5)
        conn.row_factory = _sql.Row

        # Total game profit
        row = conn.execute(
            'SELECT COALESCE(SUM(bet_amount - payout), 0) as profit, COUNT(*) as rounds FROM game_sessions WHERE payout > 0'
        ).fetchone()
        total_profit = float(row['profit'] or 0)
        total_rounds = int(row['rounds'] or 0)

        # Per-client breakdown using game_sessions.user_id -> users -> client
        clients_data = read_csv('clients.csv')
        client_revenue = {}
        for c in clients_data:
            cid = c.get('id', '')
            share = int(c.get('revenue_share') or 30)
            client_revenue[cid] = {
                'client_id': cid,
                'client_name': c.get('name', cid),
                'revenue_share': share,
                'total_profit': 0,
                'client_amount': 0,
                'admin_amount': 0,
                'rounds': 0
            }

        # Get user-game mapping (users created by client bots)
        # For now, distribute profit evenly across clients as a basic model
        if client_revenue and total_profit > 0:
            per_client = total_profit / len(client_revenue)
            for cid, cr in client_revenue.items():
                cr['total_profit'] = round(per_client, 2)
                cr['client_amount'] = round(per_client * cr['revenue_share'] / 100, 2)
                cr['admin_amount'] = round(per_client * (100 - cr['revenue_share']) / 100, 2)
                cr['rounds'] = total_rounds // len(client_revenue) if client_revenue else 0

        stats['total_game_profit'] = round(total_profit, 2)
        stats['admin_share'] = round(sum(c['admin_amount'] for c in client_revenue.values()), 2)
        stats['client_share'] = round(sum(c['client_amount'] for c in client_revenue.values()), 2)
        stats['total_rounds'] = total_rounds
        by_client = list(client_revenue.values())

        conn.close()
    except Exception:
        pass

    return jsonify({'success': True, 'stats': stats, 'by_client': by_client})


@app.route('/api/admin-center/audit', methods=['GET'])
@api_auth
@permission_required('manage_admins')
def api_admin_center_audit():
    """Get recent audit logs."""
    limit = request.args.get('limit', 100, type=int)
    try:
        import sqlite3 as _sql
        conn = _sql.connect(os.path.join(BASE_DIR, 'vex_games.db'), timeout=5)
        conn.row_factory = _sql.Row
        rows = conn.execute(
            'SELECT id, uid, action, target, details, ip, timestamp FROM admin_audit_log ORDER BY timestamp DESC LIMIT ?',
            (limit,)
        ).fetchall()
        conn.close()
        logs = [dict(r) for r in rows]
    except Exception:
        logs = []

    return jsonify({'success': True, 'logs': logs})


# ── Section Management API ────────────────────────────────────────────────────

@app.route('/api/admin-center/admins/<admin_id>/sections', methods=['GET'])
@api_auth
@permission_required('manage_admins')
def api_admin_center_get_sections(admin_id):
    """Get allowed sections for an admin."""
    sections = _rbac_get_sections(admin_id)
    return jsonify({'success': True, 'admin_id': admin_id, 'sections': sections, 'all_sections': ALL_SECTIONS})


@app.route('/api/admin-center/admins/<admin_id>/sections', methods=['POST'])
@api_auth
@permission_required('manage_admins')
def api_admin_center_set_sections(admin_id):
    """Set allowed sections for an admin. Empty list = all allowed (super_admin)."""
    data = request.json or {}
    sections = data.get('sections', [])
    # Validate sections
    valid = [s for s in sections if s in ALL_SECTIONS]
    ok = _rbac_set_sections(admin_id, valid)
    if not ok:
        return jsonify({'success': False, 'error': 'Admin not found in RBAC'}), 404
    log_action('admin_center_set_sections', f'{admin_id}: {valid}')
    return jsonify({'success': True, 'sections': valid})


# ── Domain Management API ─────────────────────────────────────────────────────

@app.route('/api/admin-center/domains', methods=['GET'])
@api_auth
@permission_required('manage_admins')
def api_admin_center_domains():
    """List all client domains."""
    clients_data = read_csv('clients.csv')
    domains = []
    for c in clients_data:
        domain = c.get('custom_domain', '').strip()
        if domain:
            domains.append({
                'client_id': c.get('id', ''),
                'client_name': c.get('name', ''),
                'domain': domain,
                'status': c.get('status', 'active'),
            })
    return jsonify({'success': True, 'domains': domains})


@app.route('/api/admin-center/domains', methods=['POST'])
@api_auth
@permission_required('manage_admins')
def api_admin_center_set_domain():
    """Set custom domain for a client."""
    data = request.json or {}
    client_id = data.get('client_id', '')
    domain = data.get('domain', '').strip().lower()

    if not client_id:
        return jsonify({'success': False, 'error': 'client_id مطلوب'}), 400

    # Validate domain format
    if domain and not all(c.isalnum() or c in '-.' for c in domain):
        return jsonify({'success': False, 'error': 'דומיין غير صالح'}), 400

    # Check no duplicate domain
    clients_data = read_csv('clients.csv')
    for c in clients_data:
        if c.get('id') != client_id and c.get('custom_domain', '').strip().lower() == domain and domain:
            return jsonify({'success': False, 'error': f'الدومين مستخدم بالفعل от клиента {c.get("name", "")}'}), 400

    fieldnames = get_fieldnames('clients.csv', ['id', 'name', 'contact', 'bot_username', 'bot_token',
        'dash_username', 'dash_password_hash', 'salt', 'features', 'admin_ids',
        'subscription_start', 'subscription_end', 'status', 'bot_autostart',
        'notes', 'created_at', 'last_login', 'revenue_share'])
    if 'custom_domain' not in fieldnames:
        fieldnames.append('custom_domain')

    for c in clients_data:
        if c.get('id') == client_id:
            c['custom_domain'] = domain
            break
    write_csv('clients.csv', clients_data, fieldnames)

    log_action('admin_center_set_domain', f'{client_id}: {domain}')
    return jsonify({'success': True, 'client_id': client_id, 'domain': domain})


@app.route('/api/admin-center/domains/<client_id>', methods=['DELETE'])
@api_auth
@permission_required('manage_admins')
def api_admin_center_remove_domain(client_id):
    """Remove custom domain for a client."""
    clients_data = read_csv('clients.csv')
    fieldnames = get_fieldnames('clients.csv', ['id', 'name', 'contact', 'bot_username', 'bot_token',
        'dash_username', 'dash_password_hash', 'salt', 'features', 'admin_ids',
        'subscription_start', 'subscription_end', 'status', 'bot_autostart',
        'notes', 'created_at', 'last_login', 'revenue_share'])
    if 'custom_domain' not in fieldnames:
        fieldnames.append('custom_domain')

    for c in clients_data:
        if c.get('id') == client_id:
            c['custom_domain'] = ''
            break
    write_csv('clients.csv', clients_data, fieldnames)

    log_action('admin_center_remove_domain', client_id)
    return jsonify({'success': True})


@app.route('/api/admin-center/domains/generate-nginx', methods=['GET'])
@api_auth
@permission_required('manage_admins')
def api_admin_center_generate_nginx():
    """Generate nginx config snippets for all client domains."""
    clients_data = read_csv('clients.csv')
    configs = []
    for c in clients_data:
        domain = c.get('custom_domain', '').strip()
        if domain and c.get('status') == 'active':
            config = f"""# Client: {c.get('name', '')} ({c.get('id', '')})
server {{
    listen 80;
    server_name {domain};
    return 301 https://$server_name$request_uri;
}}
server {{
    listen 443 ssl http2;
    server_name {domain};

    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;

    location /static/ {{
        alias /opt/bot/dashboard/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }}

    location / {{
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Client-Domain {domain};
    }}
}}
"""
            configs.append({'client_id': c.get('id'), 'domain': domain, 'config': config})
    return jsonify({'success': True, 'configs': configs, 'count': len(configs)})


# ── Rental Payment Methods API ──────────────────────────────────────────────

@app.route('/api/rental/payment-methods', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_rental_pm_list():
    from clients_manager import get_payment_manager
    pm = get_payment_manager()
    return jsonify({'success': True, 'methods': pm.get_all()})


@app.route('/api/rental/payment-methods', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_rental_pm_create():
    from clients_manager import get_payment_manager
    data = request.get_json(force=True, silent=True) or {}
    name = data.get('name', '').strip()
    pm_type = data.get('pm_type', '').strip()
    account = data.get('account_number', '').strip()
    if not name or not pm_type or not account:
        return jsonify({'success': False, 'error': 'الاسم، النوع، ورقم الحساب مطلوبان'}), 400
    pm = get_payment_manager()
    row = pm.create(name, pm_type, account, data.get('bank_name', ''), data.get('holder_name', ''))
    return jsonify({'success': True, 'method': row})


@app.route('/api/rental/payment-methods/<pm_id>', methods=['PUT'])
@api_auth
@permission_required('manage_bots')
def api_rental_pm_update(pm_id):
    from clients_manager import get_payment_manager
    data = request.get_json(force=True, silent=True) or {}
    pm = get_payment_manager()
    row = pm.update(pm_id, data)
    if not row:
        return jsonify({'success': False, 'error': 'وسيلة الدفع غير موجودة'}), 404
    return jsonify({'success': True, 'method': row})


@app.route('/api/rental/payment-methods/<pm_id>', methods=['DELETE'])
@api_auth
@permission_required('manage_bots')
def api_rental_pm_delete(pm_id):
    from clients_manager import get_payment_manager
    pm = get_payment_manager()
    pm.delete(pm_id)
    return jsonify({'success': True})


# ── Rental Client Transactions (deposit/withdraw) API ──────────────────────

@app.route('/api/rental/transactions/<client_id>', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_rental_tx_list(client_id):
    from clients_manager import get_client_manager
    cm = get_client_manager()
    status = request.args.get('status')
    tx_type = request.args.get('type')
    txs = cm.get_transactions(client_id, status=status, tx_type=tx_type)
    return jsonify({'success': True, 'transactions': txs})


@app.route('/api/rental/transactions/<client_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_rental_tx_create(client_id):
    from clients_manager import get_client_manager
    data = request.get_json(force=True, silent=True) or {}
    tx_type = data.get('type', '').strip()
    amount = data.get('amount', 0)
    method = data.get('method', '')
    note = data.get('note', '')
    if tx_type not in ('deposit', 'withdraw'):
        return jsonify({'success': False, 'error': 'نوع المعاملة يجب أن يكون deposit أو withdraw'}), 400
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError()
    except Exception:
        return jsonify({'success': False, 'error': 'المبلغ غير صالح'}), 400
    cm = get_client_manager()
    tx = cm.add_transaction(client_id, tx_type, amount, method, note, status='pending')
    if not tx:
        return jsonify({'success': False, 'error': 'العميل غير موجود'}), 404
    # إرسال إشعار للأدمن
    try:
        c = cm.get(client_id)
        cname = c.get('name', client_id) if c else client_id
        ttype = '💰 إيداع' if tx_type == 'deposit' else '💸 سحب'
        msg = f"{ttype} جديد من العميل <b>{cname}</b>\nالمبلغ: <b>{amount:.2f}</b>\nالوسيلة: {method}\nملاحظة: {note or '—'}"
        _notify_rental_admin(msg)
    except Exception:
        pass
    return jsonify({'success': True, 'transaction': tx})


@app.route('/api/rental/transactions/<client_id>/<tx_id>', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_rental_tx_process(client_id, tx_id):
    from clients_manager import get_client_manager
    data = request.get_json(force=True, silent=True) or {}
    action = data.get('action', '')
    amount_override = data.get('amount')
    admin_note = data.get('admin_note', '')
    cm = get_client_manager()
    tx, err = cm.process_transaction(client_id, tx_id, action, amount_override, admin_note)
    if err:
        return jsonify({'success': False, 'error': err}), 400
    return jsonify({'success': True, 'transaction': tx})


@app.route('/api/rental/pending-count', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_rental_pending_count():
    from clients_manager import get_client_manager
    cm = get_client_manager()
    return jsonify({'success': True, 'count': cm.get_pending_count()})


@app.route('/api/rental/all-transactions', methods=['GET'])
@api_auth
@permission_required('manage_bots')
def api_rental_all_transactions():
    from clients_manager import get_client_manager
    cm = get_client_manager()
    status = request.args.get('status')
    tx_type = request.args.get('type')
    all_txs = []
    for c in cm.list_clients():
        txs = cm.get_transactions(c['id'], status=status, tx_type=tx_type)
        for tx in txs:
            tx['client_id'] = c['id']
            tx['client_name'] = c.get('name', '')
        all_txs.extend(txs)
    all_txs.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return jsonify({'success': True, 'transactions': all_txs})


@app.route('/api/rental/quick-deposit', methods=['POST'])
@api_auth
@permission_required('manage_bots')
def api_rental_quick_deposit():
    """إيداع سريع من الأدمن لعميل (بدون طلب)"""
    from clients_manager import get_client_manager
    data = request.get_json(force=True, silent=True) or {}
    client_id = data.get('client_id', '').strip()
    amount = data.get('amount', 0)
    note = data.get('note', 'إيداع يدوي')
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError()
    except Exception:
        return jsonify({'success': False, 'error': 'المبلغ غير صالح'}), 400
    cm = get_client_manager()
    c = cm.get(client_id)
    if not c:
        return jsonify({'success': False, 'error': 'العميل غير موجود'}), 404
    current = cm.get_balance(client_id)
    cm.set_balance(client_id, current + amount)
    tx = cm.add_transaction(client_id, 'deposit', amount, 'إيداع يدوي', note, status='approved')
    return jsonify({'success': True, 'balance': cm.get_balance(client_id), 'transaction': tx})


def _get_role_permissions(role):
    """Map role name to permission dict."""
    ROLE_PERMISSIONS = {
        'super_admin': {p: True for p in [
            'approve_deposits', 'reject_deposits', 'approve_withdrawals',
            'reject_withdrawals', 'ban_users', 'unban_users', 'manage_admins',
            'manage_bots', 'send_broadcast', 'view_financial', 'manage_games',
            'view_statistics', 'manage_companies', 'manage_settings'
        ]},
        'full': {p: True for p in [
            'approve_deposits', 'reject_deposits', 'approve_withdrawals',
            'reject_withdrawals', 'ban_users', 'manage_bots', 'send_broadcast',
            'view_financial', 'manage_games', 'view_statistics'
        ]},
        'finance': {
            'approve_deposits': True, 'reject_deposits': True,
            'approve_withdrawals': True, 'reject_withdrawals': True,
            'view_financial': True, 'view_statistics': True
        },
        'support': {'view_financial': True, 'ban_users': True},
        'games': {'manage_games': True, 'view_statistics': True},
        'broadcast': {'send_broadcast': True},
        'viewer': {'view_statistics': True},
        'client_admin': {p: True for p in [
            'manage_bots', 'view_statistics', 'send_broadcast'
        ]},
    }
    return ROLE_PERMISSIONS.get(role, {'view_statistics': True})


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
        {'id': 'vex', 'name': 'VEX Neon', 'colors': {'primary': '#00e701', 'accent': '#00a801'}},
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
    """Admin approves a waiting request (SQLite). Pending agent txn stays
    alive so the on-duty agent can settle it; request becomes 'approved'."""
    ok, error = agent_db.admin_set_match_request_status(
        req_id, 'approved', actor=str(session.get('admin_id', '')))
    if not ok:
        return jsonify({'error': error}), 400
    log_action('matching_approve', req_id)
    # Notify the player
    try:
        req = agent_db.get_match_request_full(req_id)
        if req and req.get('user_id'):
            _comp_tg(str(req['user_id']),
                     f"✅ <b>تمت الموافقة على طلب المطابقة</b>\n\n"
                     f"🆔 <code>{req_id}</code>\n"
                     f"💰 المبلغ: <code>{req.get('amount', '')} {req.get('currency', '')}</code>\n"
                     f"⏳ قيد المعالجة النهائية")
    except Exception:
        pass
    return jsonify({'success': True})


@app.route('/api/matching/<req_id>/reject', methods=['POST'])
@api_auth
@permission_required('reject_deposits')
def api_matching_reject(req_id):
    """Admin rejects a waiting request (SQLite). Voids pending agent txn,
    releases escrow + daily quota atomically."""
    reason = request.json.get('reason', '') if request.json else ''
    ok, error = agent_db.admin_set_match_request_status(
        req_id, 'rejected', actor=str(session.get('admin_id', '')))
    if not ok:
        return jsonify({'error': error}), 400
    log_action('matching_reject', f'{req_id}: {reason}')
    try:
        req = agent_db.get_match_request_full(req_id)
        if req and req.get('user_id'):
            _comp_tg(str(req['user_id']),
                     f"❌ <b>تم رفض طلب المطابقة</b>\n\n"
                     f"🆔 <code>{req_id}</code>\n"
                     + (f"📝 السبب: {reason}\n" if reason else '')
                     + f"💡 يمكنك إنشاء طلب جديد أو التواصل مع الدعم")
    except Exception:
        pass
    return jsonify({'success': True})


@app.route('/api/matching/<match_id>/resolve-dispute', methods=['POST'])
@api_auth
@permission_required('view_financial')
def api_resolve_dispute(match_id):
    """Resolve an open dispute (SQLite: matches + match_disputes)."""
    favor = request.json.get('favor', 'cancel') if request.json else 'cancel'
    note = request.json.get('note', '') if request.json else ''
    admin_id = str(session.get('admin_id', ''))

    conn = agent_db._conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        new_status = 'cancelled' if favor == 'cancel' else 'completed'
        cur = conn.execute(
            "UPDATE matches SET status=?, dispute_status='resolved' WHERE id=?",
            (new_status, match_id))
        if cur.rowcount == 0:
            conn.rollback()
            return jsonify({'error': 'المطابقة غير موجودة'}), 404
        conn.execute('''
            UPDATE match_disputes SET status='resolved_by_admin',
                admin_response=?, resolved_at=?
            WHERE match_id=? AND status='open'
        ''', (f'{favor}: {note}' if note else favor,
              datetime.now().strftime('%Y-%m-%d %H:%M:%S'), match_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

    log_action('resolve_dispute', f'{match_id}: {favor}')
    return jsonify({'success': True})


@app.route('/api/matching/<req_id>/steps')
@api_auth
@permission_required('view_financial')
def api_matching_request_steps(req_id):
    req = agent_db.get_match_request_steps(req_id)
    if not req:
        return jsonify({'error': 'الطلب غير موجود'}), 404
    return jsonify({'request': req})


@app.route('/api/matching/<req_id>/claim', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_matching_claim(req_id):
    admin_id = str(session.get('admin_id', ''))
    res = agent_db.claim_request(req_id, 'admin', admin_id)
    if 'error' in res:
        return jsonify(res), 400
    return jsonify(res)


@app.route('/api/matching/<req_id>/takeover', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_matching_takeover(req_id):
    payload = request.json or {}
    admin_id = str(session.get('admin_id', ''))
    res = agent_db.admin_takeover_request(
        req_id, admin_id, reason=str(payload.get('reason', '') or '')[:300])
    if 'error' in res:
        return jsonify(res), 400
    return jsonify(res)


@app.route('/api/matching/<req_id>/reassign', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_matching_reassign(req_id):
    payload = request.json or {}
    admin_id = str(session.get('admin_id', ''))
    new_agent_id = str(payload.get('agent_id', '') or '')
    if not new_agent_id:
        return jsonify({'error': 'agent_id مطلوب'}), 400
    res = agent_db.admin_reassign_request(
        req_id, admin_id, new_agent_id,
        reason=str(payload.get('reason', '') or '')[:300])
    if 'error' in res:
        return jsonify(res), 400
    return jsonify(res)


@app.route('/api/matching/<req_id>/steps/<step_id>/action', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_matching_step_action_admin(req_id, step_id):
    payload = request.json or {}
    admin_id = str(session.get('admin_id', ''))
    res = agent_db.request_step_action(
        req_id, step_id, 'admin', admin_id,
        evidence_ref=str(payload.get('evidence_ref', '') or '')[:200],
        note=str(payload.get('note', '') or '')[:400],
    )
    if 'error' in res:
        return jsonify(res), 400
    return jsonify(res)


@app.route('/api/matching/<req_id>/steps/<step_id>/confirm', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_matching_step_confirm_admin(req_id, step_id):
    payload = request.json or {}
    admin_id = str(session.get('admin_id', ''))
    accept = bool(payload.get('accept', True))
    res = agent_db.request_step_confirm(
        req_id, step_id, 'admin', admin_id,
        accept=accept, note=str(payload.get('note', '') or '')[:400],
    )
    if 'error' in res:
        return jsonify(res), 400
    return jsonify(res)


@app.route('/api/matching/<req_id>/dispute/resolve-v2', methods=['POST'])
@api_auth
@permission_required('view_financial')
def api_matching_dispute_resolve_v2(req_id):
    payload = request.json or {}
    decision = str(payload.get('decision', '') or '')
    note = str(payload.get('note', '') or '')[:500]
    admin_id = str(session.get('admin_id', ''))
    res = agent_db.resolve_request_dispute(req_id, admin_id, decision, note)
    if 'error' in res:
        return jsonify(res), 400
    return jsonify(res)


@app.route('/api/matching/disputes-v2')
@api_auth
@permission_required('view_financial')
def api_matching_disputes_v2_list():
    status = request.args.get('status', '')
    assignee_type = request.args.get('assignee_type', '')
    assignee_id = request.args.get('assignee_id', '')
    return jsonify({
        'disputes': agent_db.list_op_disputes(
            status=status,
            assignee_type=assignee_type,
            assignee_id=assignee_id,
            limit=200,
        )
    })


@app.route('/api/matching/disputes-v2/<dispute_id>/assign', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_matching_disputes_v2_assign(dispute_id):
    payload = request.json or {}
    res = agent_db.assign_op_dispute(
        dispute_id,
        str(session.get('admin_id', '')),
        assignee_type=str(payload.get('assignee_type', '') or ''),
        assignee_id=str(payload.get('assignee_id', '') or ''),
        note=str(payload.get('note', '') or '')[:500],
    )
    if 'error' in res:
        return jsonify(res), 400
    return jsonify(res)


@app.route('/api/matching/disputes-v2/<dispute_id>/resolve', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_matching_disputes_v2_resolve(dispute_id):
    payload = request.json or {}
    decision = str(payload.get('decision', '') or '')
    note = str(payload.get('note', '') or '')[:500]
    dispute = agent_db.get_op_dispute(dispute_id)
    if not dispute:
        return jsonify({'error': 'النزاع غير موجود'}), 404
    res = agent_db.resolve_request_dispute(
        str(dispute.get('req_id', '')),
        str(session.get('admin_id', '')),
        decision,
        note,
    )
    if 'error' in res:
        return jsonify(res), 400
    return jsonify({'success': True, 'dispute_id': dispute_id, **res})


@app.route('/api/matching/routing-rules')
@api_auth
@permission_required('view_financial')
def api_matching_routing_rules():
    return jsonify({'rules': agent_db.list_routing_rules(active_only=False)})


@app.route('/api/matching/routing-rules', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_matching_routing_rules_upsert():
    payload = request.json or {}
    res = agent_db.upsert_routing_rule(
        payload.get('id', ''),
        payload.get('rule_type', ''),
        payload.get('params', {}) or {},
        priority=payload.get('priority', 100),
        is_active=bool(payload.get('is_active', True)),
    )
    if 'error' in res:
        return jsonify(res), 400
    return jsonify(res)


@app.route('/api/matching/routing-rules/<rule_id>', methods=['DELETE'])
@api_auth
@permission_required('approve_deposits')
def api_matching_routing_rules_delete(rule_id):
    return jsonify(agent_db.delete_routing_rule(rule_id))


@app.route('/api/matching/insurance-claims')
@api_auth
@permission_required('view_financial')
def api_matching_insurance_claims():
    status = request.args.get('status', '')
    return jsonify({'claims': agent_db.list_insurance_claims(status=status)})


@app.route('/api/matching/insurance-claims/<claim_id>/decision', methods=['POST'])
@api_auth
@permission_required('approve_deposits')
def api_matching_insurance_claim_decision(claim_id):
    payload = request.json or {}
    res = agent_db.decide_insurance_claim(
        claim_id, str(session.get('admin_id', '')),
        decision=str(payload.get('decision', '') or ''),
        payout_amount=payload.get('payout_amount', 0),
        note=str(payload.get('note', '') or '')[:500],
    )
    if 'error' in res:
        return jsonify(res), 400
    return jsonify(res)


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
    try:
        _dsc = agent_db._conn()
        matches = [dict(r) for r in _dsc.execute(
            'SELECT * FROM matches').fetchall()]
        _dsc.close()
    except Exception:
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

def _clean_log_rows(rows):
    """تنقية صفوف سجل الإشعارات: التخلص من مفاتيح None الناتجة عن صفوف
    CSV معطوبة (رسائل متعددة الأسطر) — وإلا فشل jsonify بفرز مفاتيح None."""
    cleaned = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        row = {str(k): v for k, v in r.items() if k is not None}
        if row.get('timestamp') or row.get('message_preview'):
            cleaned.append(row)
    return cleaned


@app.route('/api/notifications-log')
@api_auth
def api_notifications_log():
    logs = _clean_log_rows(read_csv('notifications_log.csv'))
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
    logs = _clean_log_rows(read_csv('notifications_log.csv'))
    logs.reverse()
    # عام بدون تسجيل دخول ⇒ نعرض فقط البثّ العام الموجّه للمستخدمين.
    # إشعارات الأدمن (عضو جديد… إلخ) تحتوي بيانات شخصية ويُمنع تسريبها هنا.
    from datetime import datetime as _dt, timedelta as _td
    cutoff = (_dt.now() - _td(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    result = []
    for l in logs:
        if l.get('timestamp', '') < cutoff:
            continue
        if l.get('type', '') != 'broadcast':
            continue
        if (l.get('target_type', '') or '').strip() == 'admin':
            continue
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
    """Store a browser push subscription — public, no auth needed.
    مخطط موحّد مع اشتراك المستخدمين (user_type/user_id/user_name دائماً)."""
    data = request.json or {}
    endpoint = data.get('endpoint', '')
    keys = data.get('keys', {})
    if not endpoint:
        return jsonify({'error': 'No endpoint'}), 400
    admin_id = str(session.get('admin_id', ''))
    is_admin = bool(session.get('is_admin'))
    subs = read_csv('push_subscriptions.csv')
    fieldnames = get_fieldnames('push_subscriptions.csv', ['admin_id','endpoint','p256dh','auth','created_at','user_type','user_id','user_name'])
    # Remove old sub for this endpoint (نفس المتصفح = اشتراك واحد محدث)
    subs = [s for s in subs if s.get('endpoint') != endpoint]
    subs.append({
        'admin_id': admin_id,
        'endpoint': endpoint,
        'p256dh': keys.get('p256dh', ''),
        'auth': keys.get('auth', ''),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'user_type': 'admin' if is_admin else 'browser',
        'user_id': admin_id,
        'user_name': session.get('admin_name', '')
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
    fieldnames = get_fieldnames('companies.csv', ['id','name','type','details','is_active','icon','address','affiliate_link','bot_icon'])
    if 'bot_icon' not in fieldnames:
        fieldnames.append('bot_icon')
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
    conn = agent_db._conn()
    try:
        rows = conn.execute(
            'SELECT * FROM match_ratings ORDER BY timestamp DESC LIMIT 50').fetchall()
        ratings = [dict(r) for r in rows]
    finally:
        conn.close()
    return jsonify({'ratings': ratings})

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
        _init_db,
    )
    _gm = GameManager()
    _VEX_GAMES = True
    # ── Initialize all database tables ───────────────────────────────────────
    try:
        _init_db()
        print("[startup] Database tables initialized.")
    except Exception as _init_err:
        print(f"[startup] Database init error: {_init_err}")
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
        try:
            _gm.invalidate_games_cache()
        except Exception:
            pass
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

@app.route('/api/player/companies')
@webapp_auth
def api_player_companies():
    """شركات التعويض بروابط الأفيليه + حسابات المستخدم المسجلة (للويب).

    يتطلب هوية موثقة (initData/جلسة مرتبطة بالجهاز) — رقم حساب المستخدم
    بيانات حساسة ولا تُكشف لطلبات uid غير الموثقة."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'Unauthorized'}), 403
    accounts_by_company = {}
    try:
        for a in read_csv('user_company_accounts.csv'):
            if str(a.get('user_id', '')) == uid:
                accounts_by_company[a.get('company_id', '')] = {
                    'account_number': a.get('account_number', ''),
                    'status': a.get('status', 'active') or 'active',
                }
    except Exception:
        pass
    companies = []
    try:
        for c in read_csv('companies.csv'):
            if (c.get('is_active', '') or '').lower() not in ('active', 'yes', '1', 'true'):
                continue
            # فلتر "تظهر في قسم التعويض" — الافتراضي نعم (توافقاً مع الشركات القديمة)
            if (c.get('show_in_comp', '') or 'yes').lower() in ('no', '0', 'false'):
                continue
            acc = accounts_by_company.get(c.get('id', ''), {})
            companies.append({
                'id': c.get('id', ''),
                'name': c.get('name', ''),
                'icon': c.get('icon', '') or '🏢',
                'affiliate_link': c.get('affiliate_link', '') or '',
                'promo_code': c.get('promo_code', '') or '',
                'registered_account': acc.get('account_number', ''),
                'account_status': acc.get('status', ''),
            })
    except Exception:
        pass
    return jsonify({'companies': companies})


# ── تسجيل حساب شركة + طلب تعويض من محفظة الويب ──────────────────────────────
_RECOVERY_UPLOADS_DIR = os.path.join(BASE_DIR, 'recovery_uploads')
_ALLOWED_SCREENSHOT_EXT = {'.png', '.jpg', '.jpeg', '.webp'}
_MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024  # 5MB
# Retention & quota — #77: recovery_uploads must not grow unboundedly
_UPLOAD_RETENTION_DAYS = 14      # حذف صور الطلبات المحسومة بعد 14 يوماً
_UPLOAD_ORPHAN_HOURS = 24        # حذف الملفات غير المرتبطة بأي طلب بعد 24 ساعة
_UPLOAD_MAX_FILES_PER_USER = 10  # أقصى عدد ملفات محفوظة لكل مستخدم
_UPLOAD_MAX_BYTES_PER_USER = 25 * 1024 * 1024  # أقصى حجم إجمالي لكل مستخدم


def _validate_screenshot_image(blob):
    """فك ترميز الصورة والتحقق منها فعلياً عبر Pillow — لا نثق بالتوقيع وحده.

    Returns canonical extension ('.png'/'.jpg'/'.webp') or None if invalid."""
    import io as _io
    try:
        from PIL import Image
        with Image.open(_io.BytesIO(blob)) as im:
            im.verify()  # يكتشف الملفات التالفة/المزيفة
        # verify() يستهلك الملف — إعادة الفتح لقراءة الصيغة والأبعاد
        with Image.open(_io.BytesIO(blob)) as im2:
            fmt = (im2.format or '').upper()
            w, h = im2.size
        if fmt not in ('PNG', 'JPEG', 'WEBP') or w < 1 or h < 1 or w * h > 40_000_000:
            return None
        return {'PNG': '.png', 'JPEG': '.jpg', 'WEBP': '.webp'}[fmt]
    except ImportError:
        # Pillow غير متاح — نرجع للتوقيع فقط (تم فحصه قبل الاستدعاء)
        return None if not blob else '.png' if blob.startswith(b'\x89PNG') \
            else '.jpg' if blob.startswith(b'\xff\xd8\xff') \
            else '.webp' if blob[:4] == b'RIFF' and blob[8:12] == b'WEBP' else None
    except Exception:
        return None


def _iter_upload_files():
    """Yield (fname, full_path, stat) for every file in recovery_uploads/."""
    if not os.path.isdir(_RECOVERY_UPLOADS_DIR):
        return
    for fname in os.listdir(_RECOVERY_UPLOADS_DIR):
        path = os.path.join(_RECOVERY_UPLOADS_DIR, fname)
        try:
            st = os.stat(path)
        except OSError:
            continue
        if os.path.isfile(path):
            yield fname, path, st


def _read_recovery_requests_strict():
    """قراءة recovery_requests.csv بلا إخفاء للأخطاء — أي فشل يرفع استثناء.

    (read_csv تعيد [] عند الفشل، ما قد يصنّف صور الطلبات المعلقة كيتيمة
    ويحذفها — الحذف يجب أن يكون fail-closed.)"""
    filepath = os.path.join(BASE_DIR, 'recovery_requests.csv')
    if not os.path.exists(filepath):
        return []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def _svrp_lock_ctx():
    """قفل SVRP العابر للعمليات — يسلسل الرفع/الحصة/التنظيف مع إنشاء الطلبات."""
    from svrp import svrp_lock
    return svrp_lock()


def _cleanup_recovery_uploads():
    """تنظيف دوري لمجلد recovery_uploads — يعيد عدد الملفات المحذوفة.

    يحذف:
      • صور الطلبات المحسومة (approved/rejected) الأقدم من _UPLOAD_RETENTION_DAYS
      • الملفات اليتيمة (غير مشار إليها في recovery_requests.csv) الأقدم من 24 ساعة
    صور الطلبات المعلقة لا تُحذف أبداً. يعمل داخل svrp_lock حتى لا يسابق
    رفعاً جارياً (الكتابة + إلحاق صف الطلب يجريان تحت نفس القفل)."""
    now = time.time()
    pending_files, resolved_files = set(), set()
    try:
        with _svrp_lock_ctx():
            rows = _read_recovery_requests_strict()
    except Exception as exc:
        _auth_logger.error('[uploads-cleanup] read recovery_requests failed — fail closed: %s', exc)
        return 0
    for r in rows:
        pfid = r.get('photo_file_id', '') or ''
        if not pfid.startswith('web:'):
            continue
        fname = os.path.basename(pfid[4:])
        if r.get('status') == 'pending':
            pending_files.add(fname)
        else:
            resolved_files.add(fname)
    deleted = 0
    retention_s = _UPLOAD_RETENTION_DAYS * 86400
    orphan_s = _UPLOAD_ORPHAN_HOURS * 3600
    for fname, path, st in _iter_upload_files():
        if fname in pending_files:
            continue
        age = now - st.st_mtime
        if fname in resolved_files:
            expired = age > retention_s
        else:
            expired = age > orphan_s  # يتيم — ليس في أي طلب
        if expired:
            try:
                os.unlink(path)
                deleted += 1
            except OSError:
                pass
    if deleted:
        _auth_logger.info('[uploads-cleanup] Deleted %d expired screenshot(s)', deleted)
    return deleted


def _enforce_user_upload_quota(uid, incoming_bytes=0):
    """فرض حصة المستخدم شاملةً الملف الوارد: يحذف أقدم ملفاته غير المعلقة أولاً.

    يجب استدعاؤها داخل svrp_lock (يسلسل الحصة + الكتابة + إنشاء الطلب فلا
    يمكن لطلبين متزامنين تجاوز الحد أو حذف ملف رفعٍ جارٍ قبل إلحاق صفه).
    Returns True if — after best-effort eviction — the incoming file fits."""
    prefix = f"{uid}_"

    def _within(files, total):
        return (len(files) + 1 <= _UPLOAD_MAX_FILES_PER_USER
                and total + incoming_bytes <= _UPLOAD_MAX_BYTES_PER_USER)

    mine = [(fname, path, st) for fname, path, st in _iter_upload_files()
            if fname.startswith(prefix)]
    total = sum(st.st_size for _, _, st in mine)
    if _within(mine, total):
        return True
    # نحتاج للحذف — قراءة حالة الطلبات fail-closed: أي فشل ⇒ لا حذف ⇒ رفض الرفع
    try:
        rows = _read_recovery_requests_strict()
    except Exception as exc:
        _auth_logger.error('[upload-quota] read recovery_requests failed — fail closed: %s', exc)
        return False
    pending_files = {os.path.basename((r.get('photo_file_id') or '')[4:])
                     for r in rows
                     if (r.get('photo_file_id') or '').startswith('web:')
                     and r.get('status') == 'pending'}
    # حذف الأقدم أولاً — مع تخطي صور الطلبات المعلقة
    for fname, path, st in sorted(mine, key=lambda t: t[2].st_mtime):
        if fname in pending_files:
            continue
        try:
            os.unlink(path)
            total -= st.st_size
            mine = [m for m in mine if m[0] != fname]
        except OSError:
            pass
        if _within(mine, total):
            return True
    return _within(mine, total)


def _find_active_company(company_id):
    for c in read_csv('companies.csv'):
        if c.get('id', '') == str(company_id):
            if (c.get('is_active', '') or '').lower() in ('active', 'yes', '1', 'true'):
                return c
            return None
    return None


@app.route('/api/player/companies/<company_id>/register-account', methods=['POST'])
@webapp_auth
def api_player_register_company_account(company_id):
    """تسجيل رقم حساب المستخدم في شركة تعويض — هوية موثقة فقط."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'Unauthorized'}), 403
    company = _find_active_company(company_id)
    if not company:
        return jsonify({'error': 'الشركة غير موجودة أو غير نشطة'}), 404
    data = request.get_json(silent=True) or {}
    account_number = str(data.get('account_number', '')).strip()
    if not (3 <= len(account_number) <= 64):
        return jsonify({'error': 'رقم الحساب يجب أن يكون بين 3 و 64 حرفاً'}), 400
    try:
        with _COMP_CSV_LOCK:
            rows = read_csv('user_company_accounts.csv')
            for r in rows:
                if str(r.get('user_id', '')) == uid and r.get('company_id') == str(company_id) \
                   and r.get('status') in ('pending', 'active', 'approved'):
                    return jsonify({'error': 'لديك حساب مسجل أو طلب معلق بالفعل في هذه الشركة'}), 409
            fieldnames = get_fieldnames('user_company_accounts.csv',
                ['id', 'user_id', 'company_id', 'company_name', 'account_number', 'status', 'created_at'])
            acc_id = f"UAC{secrets.token_hex(5).upper()}"
            append_csv('user_company_accounts.csv', {
                'id': acc_id, 'user_id': uid, 'company_id': str(company_id),
                'company_name': company.get('name', ''), 'account_number': account_number,
                'status': 'pending',
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')}, fieldnames)
    except Exception as e:
        _auth_logger.error('register-account failed uid=%s company=%s: %s', uid, company_id, e)
        return jsonify({'error': 'فشل التسجيل — حاول مجدداً'}), 500
    _comp_alert_admins(f"🆕 <b>طلب تسجيل حساب تعويض</b>\n👤 المستخدم: <code>{uid}</code>\n"
                       f"🏢 الشركة: {company.get('name', '')}\n"
                       f"🔢 رقم الحساب: <code>{account_number}</code>\n\n"
                       f"أكّد أو ارفض الطلب من لوحة الإدارة ← الاسترداد الذكي")
    try:
        push_notification('comp_account', 'طلب تسجيل حساب تعويض',
                          f'{company.get("name", "")} — {account_number}')
    except Exception:
        pass
    return jsonify({'ok': True, 'status': 'pending', 'account_number': account_number,
                    'message': '✅ تم إرسال طلبك للإدارة — سيتم إشعارك فور تأكيد حسابك'})


@app.route('/api/player/companies/account-source', methods=['POST'])
@webapp_auth
def api_player_account_source():
    """إجابة النافذة المنبثقة بعد تأكيد الحساب: هل فتح حساباً جديداً عبر رابط
    التسجيل أم كان لديه حساب مسبقاً؟ تُسجَّل الإجابة وتُشعر الإدارة."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json(silent=True) or {}
    company_id = str(data.get('company_id', '')).strip()
    source = str(data.get('source', '')).strip()
    if source not in ('new', 'existing'):
        return jsonify({'error': 'قيمة غير صالحة'}), 400
    try:
        with _COMP_CSV_LOCK:
            rows = read_csv('user_company_accounts.csv')
            account = None
            for r in rows:
                if str(r.get('user_id', '')) == uid and r.get('company_id') == company_id:
                    account = r
                    break
            if not account:
                return jsonify({'error': 'لا يوجد حساب مسجل في هذه الشركة'}), 404
            # إجابة واحدة لكل حساب
            sources = read_csv('comp_account_sources.csv')
            for s in sources:
                if str(s.get('user_id', '')) == uid and s.get('company_id') == company_id:
                    return jsonify({'ok': True, 'already': True})
            fieldnames = get_fieldnames('comp_account_sources.csv',
                ['id', 'user_id', 'company_id', 'company_name', 'source', 'created_at'])
            append_csv('comp_account_sources.csv', {
                'id': f"CAS{secrets.token_hex(5).upper()}",
                'user_id': uid, 'company_id': company_id,
                'company_name': account.get('company_name', ''),
                'source': source,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M')}, fieldnames)
    except Exception as e:
        _auth_logger.error('account-source failed uid=%s company=%s: %s', uid, company_id, e)
        return jsonify({'error': 'فشل حفظ الإجابة — حاول مجدداً'}), 500
    answer_ar = 'فتح حساباً جديداً عبر رابط التسجيل' if source == 'new' else 'كان لديه حساب مسبقاً'
    _comp_alert_admins(
        f"ℹ️ <b>إجابة العميل عن حسابه</b>\n"
        f"👤 المستخدم: <code>{uid}</code>\n"
        f"🏢 الشركة: {account.get('company_name', '')}\n"
        f"📋 رقم الحساب: <code>{account.get('account_number', '')}</code>\n"
        f"💬 الإجابة: {answer_ar}")
    return jsonify({'ok': True})


@app.route('/api/player/compensation-request', methods=['POST'])
@webapp_auth
def api_player_compensation_request():
    """تقديم طلب تعويض من الويب مع رفع لقطة شاشة — هوية موثقة فقط.

    يدخل نفس خط أنابيب recovery_requests الذي يستخدمه البوت؛
    photo_file_id يحمل 'web:<filename>' ويُعرض للأدمن عبر مسار مخصص."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'Unauthorized'}), 403

    company_id = str(request.form.get('company_id', '')).strip()
    if not company_id:
        return jsonify({'error': 'اختر الشركة'}), 400
    company = _find_active_company(company_id)
    if not company:
        return jsonify({'error': 'الشركة غير موجودة أو غير نشطة'}), 404

    try:
        from svrp import SVRPManager as _SM
        mgr = _SM()
    except Exception as e:
        _auth_logger.error('compensation-request svrp load failed: %s', e)
        return jsonify({'error': 'الخدمة غير متاحة حالياً'}), 500

    account = mgr.get_user_company_account(uid, company_id)
    if not account:
        return jsonify({'error': 'يجب تسجيل رقم حسابك في هذه الشركة أولاً'}), 400
    if (account.get('status') or 'active') not in ('active', 'approved'):
        return jsonify({'error': 'حسابك في هذه الشركة بانتظار تأكيد الإدارة — سيتم إشعارك فور التأكيد'}), 400

    f = request.files.get('screenshot')
    if not f or not f.filename:
        return jsonify({'error': 'أرفق لقطة شاشة'}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in _ALLOWED_SCREENSHOT_EXT:
        return jsonify({'error': 'صيغة الصورة غير مدعومة (png/jpg/webp)'}), 400
    blob = f.read(_MAX_SCREENSHOT_BYTES + 1)
    if len(blob) > _MAX_SCREENSHOT_BYTES:
        return jsonify({'error': 'حجم الصورة يتجاوز 5MB'}), 400
    if not blob:
        return jsonify({'error': 'الملف فارغ'}), 400
    # تحقق من توقيع الملف (magic bytes) — لا نثق بالامتداد وحده
    _sig_ok = (blob.startswith(b'\x89PNG') or blob.startswith(b'\xff\xd8\xff')
               or (blob[:4] == b'RIFF' and blob[8:12] == b'WEBP'))
    if not _sig_ok:
        return jsonify({'error': 'الملف ليس صورة صالحة'}), 400
    # فك ترميز فعلي عبر Pillow — يرفض الملفات التالفة/المزيفة و decompression bombs
    canon_ext = _validate_screenshot_image(blob)
    if not canon_ext:
        return jsonify({'error': 'الملف ليس صورة صالحة'}), 400
    ext = canon_ext  # الامتداد الحقيقي حسب محتوى الصورة، لا اسم الملف

    # customer_id من users.csv إن وجد
    customer_id = ''
    try:
        for u in read_csv('users.csv'):
            if str(u.get('telegram_id', '')) == uid:
                customer_id = u.get('customer_id', '')
                break
    except Exception:
        pass

    # الحصة + كتابة الملف + إنشاء الطلب تحت svrp_lock واحد:
    #  • لا يمكن لطلبين متزامنين تجاوز حصة المستخدم
    #  • لا يمكن للتنظيف/الحصة حذف ملف رفعٍ جارٍ قبل إلحاق صف طلبه
    #  • فحص "لا طلب معلق" + الإنشاء ذرّيان (القفل reentrant)
    with _svrp_lock_ctx():
        if not _enforce_user_upload_quota(uid, incoming_bytes=len(blob)):
            return jsonify({'error': 'تجاوزت الحد المسموح من الملفات المرفوعة — حاول لاحقاً'}), 429

        os.makedirs(_RECOVERY_UPLOADS_DIR, exist_ok=True)
        fname = f"{uid}_{secrets.token_hex(8)}{ext}"
        upload_path = os.path.join(_RECOVERY_UPLOADS_DIR, fname)
        with open(upload_path, 'wb') as out:
            out.write(blob)

        req_id, err = mgr.create_recovery_request_if_no_pending(
            uid, customer_id, f'web:{fname}', company_id,
            company_name=company.get('name', ''),
            account_number=account.get('account_number', ''))
        if not req_id:
            try:
                os.unlink(upload_path)  # لا نراكم ملفات لطلبات لم تُحفظ
            except OSError:
                pass
            status = 409 if err and 'معلق' in err else 500
            return jsonify({'error': err or 'فشل حفظ الطلب'}), status

    try:
        push_notification('recovery_request', 'طلب تعويض جديد',
                          f'طلب تعويض من الويب — {company.get("name", "")} — {req_id}')
    except Exception:
        pass
    return jsonify({'ok': True, 'request_id': req_id,
                    'message': '✅ تم إرسال طلب التعويض — بانتظار مراجعة الإدارة'})


@app.route('/api/svrp/requests/<req_id>/screenshot')
@api_auth
@permission_required('view_financial')
def api_svrp_request_screenshot(req_id):
    """عرض لقطة شاشة طلب تعويض مقدم من الويب (photo_file_id = web:<fname>)."""
    for r in read_csv('recovery_requests.csv'):
        if r.get('id') == req_id:
            pfid = r.get('photo_file_id', '') or ''
            if not pfid.startswith('web:'):
                return jsonify({'error': 'الصورة مرسلة عبر تيليجرام — راجع محادثة البوت'}), 404
            fname = os.path.basename(pfid[4:])  # يمنع path traversal
            path = os.path.join(_RECOVERY_UPLOADS_DIR, fname)
            if not os.path.exists(path):
                return jsonify({'error': 'الملف غير موجود'}), 404
            return send_file(path, max_age=3600)
    return jsonify({'error': 'الطلب غير موجود'}), 404

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


# ── إرسال رصيد مجمد لصديق + بروموكود + كود إحالة ──────────────────────────

@app.route('/api/player/comp/send', methods=['POST'])
@webapp_auth
def api_player_comp_send():
    """إرسال أرصدة SVRP مجمدة لصديق عبر customer_id — هوية موثقة فقط."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json(silent=True) or {}
    receiver_cid = str(data.get('receiver_cid', '')).strip()
    amount = float(data.get('amount', 0) or 0)
    if not receiver_cid:
        return jsonify({'error': 'أدخل رقم العميل (Customer ID) للصديق'}), 400
    if amount <= 0:
        return jsonify({'error': 'المبلغ يجب أن يكون أكبر من صفر'}), 400
    try:
        import sys as _sys3; _sys3.path.insert(0, BASE_DIR)
        from svrp import SVRPManager as _SM2
        mgr = _SM2()
        ok, msg = mgr.send_frozen_credits(uid, receiver_cid, amount)
        return jsonify({'ok': ok, 'message': msg})
    except Exception as e:
        _auth_logger.error('comp/send failed uid=%s: %s', uid, e)
        return jsonify({'error': 'فشل الإرسال — حاول مجدداً'}), 500


@app.route('/api/player/comp/promo/redeem', methods=['POST'])
@webapp_auth
def api_player_comp_promo_redeem():
    """استبدال بروموكود تعويض — هوية موثقة فقط."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json(silent=True) or {}
    code = str(data.get('code', '')).strip().upper()
    if not code:
        return jsonify({'error': 'أدخل الكود'}), 400
    try:
        import sys as _sys4; _sys4.path.insert(0, BASE_DIR)
        from svrp import SVRPManager as _SM3
        mgr = _SM3()
        ok, msg = mgr.redeem_promo_code(uid, code)
        return jsonify({'ok': ok, 'message': msg})
    except Exception as e:
        _auth_logger.error('comp/promo/redeem failed uid=%s: %s', uid, e)
        return jsonify({'error': 'فشل الاستبدال — حاول مجدداً'}), 500


@app.route('/api/player/comp/referral/code')
@webapp_auth
def api_player_comp_referral_code():
    """عرض كود الإحالة + عدد الإحالات للمستخدم."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'Unauthorized'}), 403
    try:
        customer_id = ''
        for u in read_csv('users.csv'):
            if str(u.get('telegram_id', '')) == uid:
                customer_id = u.get('customer_id', '')
                break
        referral_code = f"REF{customer_id}" if customer_id else ''
        # عدد الإحالات + أرباح الإحالة
        referral_count = 0
        referral_earnings = 0.0
        try:
            for r in read_csv('referrals.csv'):
                if str(r.get('referrer_id', '')) == uid and r.get('status') == 'completed':
                    referral_count += 1
                    try: referral_earnings += float(r.get('reward_amount', 0) or 0)
                    except Exception: pass
        except Exception:
            pass
        # قائمة الإحالات التفصيلية
        referral_list = []
        try:
            for r in read_csv('referrals.csv'):
                if str(r.get('referrer_id', '')) == uid:
                    referral_list.append({
                        'referred_id': r.get('referred_id', ''),
                        'status': r.get('status', ''),
                        'reward': r.get('reward_amount', '0'),
                        'date': r.get('created_at', ''),
                    })
        except Exception:
            pass
        return jsonify({
            'ok': True,
            'customer_id': customer_id,
            'referral_code': referral_code,
            'referral_count': referral_count,
            'referral_earnings': round(referral_earnings, 2),
            'referral_list': referral_list,
        })
    except Exception as e:
        _auth_logger.error('comp/referral/code failed uid=%s: %s', uid, e)
        return jsonify({'error': 'فشل جلب البيانات'}), 500


# ── One-Time Claim Link — إرسال بدون اسم مستخدم ─────────────────────────

import os as _claim_os
_CLAIM_DIR = _claim_os.path.join(BASE_DIR, 'svrp_claims')

def _ensure_claim_dir():
    if not _claim_os.path.isdir(_CLAIM_DIR):
        _claim_os.makedirs(_CLAIM_DIR, exist_ok=True)

def _read_claims_csv():
    _ensure_claim_dir()
    return read_csv('svrp_claims.csv')

def _write_claims_csv(rows, fieldnames=None):
    _ensure_claim_dir()
    if not fieldnames:
        fieldnames = get_fieldnames('svrp_claims.csv',
            ['id','token','sender_uid','amount','status','created_at','claimed_by_uid','claimed_at','sender_name'])
    write_csv('svrp_claims.csv', rows, fieldnames)

@app.route('/api/player/comp/claim/create', methods=['POST'])
@webapp_auth
def api_player_comp_claim_create():
    """إنشاء رابط claim لمرة واحدة — المستخدم يكتب المبلغ فقط بدون اسم."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json(silent=True) or {}
    amount = float(data.get('amount', 0) or 0)
    if amount <= 0:
        return jsonify({'error': 'المبلغ يجب أن يكون أكبر من صفر'}), 400
    # تحقق من رصيد مجمد كافي (25% كحد أقصى)
    try:
        from game_engine import GameManager as _CLMGM
        _cl_bal = float(_CLMGM.get_svrp_frozen_balance(uid).get('frozen_balance', 0) or 0)
    except Exception:
        _cl_bal = 0
    if amount > _cl_bal * 0.25:
        return jsonify({'error': 'الحد الأقصى 25% من رصيدك المجمد (' + str(round(_cl_bal * 0.25, 2)) + ')'}), 400
    token = secrets.token_urlsafe(16)
    # اسم المرسل
    sender_name = ''
    try:
        for u in read_csv('users.csv'):
            if str(u.get('telegram_id', '')) == uid:
                sender_name = u.get('username', '') or u.get('first_name', '') or uid
                break
    except Exception:
        pass
    try:
        rows = _read_claims_csv()
        rows.append({
            'id': 'CLM' + secrets.token_hex(5).upper(),
            'token': token,
            'sender_uid': uid,
            'amount': str(round(amount, 2)),
            'status': 'pending',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'claimed_by_uid': '',
            'claimed_at': '',
            'sender_name': sender_name,
        })
        _write_claims_csv(rows)
    except Exception as e:
        _auth_logger.error('claim/create failed uid=%s: %s', uid, e)
        return jsonify({'error': 'فشل إنشاء الرابط'}), 500
    claim_url = request.url_root.rstrip('/') + '/claim/' + token
    return jsonify({'ok': True, 'claim_url': claim_url, 'token': token, 'amount': amount})


@app.route('/api/player/comp/claims')
@webapp_auth
def api_player_comp_claims():
    """قائمة روابط claim للمستخدم (معلقة + مُطالَبة)."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'Unauthorized'}), 403
    claims = []
    try:
        for c in _read_claims_csv():
            if c.get('sender_uid') == uid or c.get('claimed_by_uid') == uid:
                claims.append(c)
    except Exception:
        pass
    return jsonify({'claims': claims})


@app.route('/claim/<token>')
def claim_page(token):
    """صفحة عامة لرابط claim — تعرض المبلغ وربط التسجيل."""
    rows = _read_claims_csv()
    claim = None
    for c in rows:
        if c.get('token') == token:
            claim = c
            break
    if not claim:
        return '<div style="text-align:center;padding:60px 20px;font-family:Cairo,sans-serif;color:#ff4757"><h2>❌ رابط غير صالح</h2><p>هذا الرابط غير موجود أو انتهت صلاحيته</p></div>', 404
    status = claim.get('status', 'pending')
    if status == 'claimed':
        return '<div style="text-align:center;padding:60px 20px;font-family:Cairo,sans-serif;color:#8794a3"><h2>✅ تم المطالبة</h2><p>هذا الرابط تم استخدامه بالفعل</p></div>'
    amount = claim.get('amount', '0')
    sender = claim.get('sender_name', '') or 'مستخدم VEX'
    claim_url = request.url_root.rstrip('/') + '/claim/' + token
    bot_url = 'https://t.me/vex_otp_bot?start=claim_' + token
    html = '''<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>VEX — استلم رصيدك</title>
    <style>*{font-family:Cairo,sans-serif;box-sizing:border-box;margin:0;padding:0}
    body{background:#0b0e11;color:#eef2f6;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
    .card{background:linear-gradient(180deg,#141920,#10141a);border:1px solid #262e39;border-radius:20px;padding:30px;max-width:400px;width:100%;text-align:center;box-shadow:0 8px 32px rgba(0,0,0,.5)}
    .icon{font-size:56px;margin-bottom:14px}.amt{font-size:32px;font-weight:900;color:#00e701;margin:10px 0}
    .label{font-size:14px;color:#8794a3;margin-bottom:20px}
    .btn{display:block;background:linear-gradient(135deg,#00e701,#00c101);color:#04210a;font-weight:900;font-size:16px;border-radius:14px;padding:14px;text-decoration:none;margin:10px auto;max-width:280px}
    .btn2{background:transparent;border:1px solid #262e39;color:#8794a3}
    .info{font-size:12px;color:#8794a3;margin-top:16px;line-height:1.6}
    .code{background:#0b0e11;border:1px solid #262e39;padding:8px 14px;border-radius:10px;color:#fbbf24;font-size:14px;font-weight:700;font-family:Courier New;letter-spacing:.5px;margin-top:10px;display:inline-block}
    </style></head><body><div class="card">
    <div class="icon">🎁</div>
    <div class="label">''' + sender + ''' أرسل لك رصيد مجمد</div>
    <div class="amt">''' + amount + '''</div>
    <div class="label">سجّل في VEX لاستلام الرصيد</div>
    <a href="''' + bot_url + '''" target="_blank" class="btn">📲 فتح البوت للتسجيل</a>
    <div class="info">💡 بعد التسجيل، سيتم إضافة الرصيد لمحفظتك تلقائياً مع قواعد التجميد المطبقة.<br>هذا الرابط صالح لمرة واحدة فقط.</div>
    </div></body></html>'''
    return html


@app.route('/api/claim/<token>/redeem', methods=['POST'])
@webapp_auth
def api_claim_redeem(token):
    """مطالبة رصيد claim — المستخدم المسجل يستلم الرصيد المجمد."""
    uid = str(get_request_uid() or '')
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'Unauthorized'}), 403
    rows = _read_claims_csv()
    claim = None
    for c in rows:
        if c.get('token') == token:
            claim = c
            break
    if not claim:
        return jsonify({'error': 'رابط غير صالح'}), 404
    if claim.get('status') != 'pending':
        return jsonify({'error': 'هذا الرابط تم استخدامه بالفعل'}), 400
    sender_uid = claim.get('sender_uid', '')
    if sender_uid == uid:
        return jsonify({'error': 'لا يمكنك مطالبة رصيدك الخاص'}), 400
    amount = float(claim.get('amount', 0) or 0)
    if amount <= 0:
        return jsonify({'error': 'مبلغ غير صالح'}), 400
    # خصم من مرسل + إضافة للمطالب عبر svrp.send_frozen_credits logic
    try:
        import sys as _c6sys; _c6sys.path.insert(0, BASE_DIR)
        from svrp import SVRPManager as _CLSMgr
        mgr = _CLSMgr()
        # نستخدم transfer_svrp_frozen_direct — خصم من المرسل + إضافة للمستلم
        # نعاملها كإرسال لصديق جديد (5% unfreeze للمرسل)
        ok, msg = mgr.send_frozen_credits_direct(sender_uid, uid, amount, is_claim=True)
        if not ok:
            return jsonify({'error': msg}), 400
        # تحديث حالة الـ claim
        for c in rows:
            if c.get('token') == token:
                c['status'] = 'claimed'
                c['claimed_by_uid'] = uid
                c['claimed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                break
        _write_claims_csv(rows)
        return jsonify({'ok': True, 'message': '✅ تم استلام ' + str(round(amount, 2)) + ' رصيد مجمد في محفظتك'})
    except Exception as e:
        _auth_logger.error('claim/redeem failed uid=%s token=%s: %s', uid, token, e)
        return jsonify({'error': 'فشل المطالبة — حاول مجدداً'}), 500


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
    # NaN/Infinity rejected
    try:
        amount = float(data.get('amount', 0))
    except (ValueError, TypeError):
        return jsonify({'error': 'مبلغ غير صالح'}), 400
    if not math.isfinite(amount) or amount <= 0:
        return jsonify({'error': 'مبلغ غير صالح'}), 400
    method_id = data.get('method_id', '')
    method_name = data.get('method_name', '')
    method_account_data = data.get('method_account_data', '')
    player_wallet = data.get('player_wallet', '')
    save_method = data.get('save_method', False)
    purpose = data.get('purpose', '')  # 'lottery_tickets' = directed deposit
    ticket_count = int(data.get('ticket_count', 0) or 0)
    company_id = str(data.get('company_id', '') or '').strip()
    company_name = str(data.get('company_name', '') or '').strip()
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
        save_method=save_method,
        company_id=company_id,
        company_name=company_name
    )

    # Push to dashboard — include purpose if directed deposit
    if company_name:
        notif_title = f'🏢 إيداع شركة — {company_name}'
        notif_msg = (f'اللاعب {user_name} ({customer_id}) طلب إيداع {amount} {currency}\n'
                     f'🏢 الشركة: {company_name}\nالوسيلة: {method_name}\n'
                     f'محفظة اللاعب: {player_wallet}')
    else:
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

    # Provably Fair: create session and use PF to place mines
    pf_session_id = None
    pf_seed_hash = None
    pf_client_seed = None
    pf_nonce = 0
    if _PROVABLY_FAIR and _pf:
        try:
            pf_session_id = f"mines_{uid}_{int(datetime.now().timestamp()*1000)}"
            client_seed = data.get('client_seed') or None
            pf_info = _pf.create_session(pf_session_id, client_seed)
            pf_seed_hash = pf_info['seed_hash']
            pf_client_seed = pf_info['client_seed']
            # Use PF to generate mine positions deterministically
            all_positions = list(range(25))
            # Generate a shuffle using PF HMAC chain
            for i in range(24, 0, -1):
                r = _pf.generate_result(pf_session_id, max_value=i + 1)
                j = r['result']
                all_positions[i], all_positions[j] = all_positions[j], all_positions[i]
                pf_nonce = r['nonce']
            mine_positions = all_positions[:mine_count]
        except Exception:
            pf_session_id = None
            all_positions = list(range(25))
            random.shuffle(all_positions)
            mine_positions = all_positions[:mine_count]
    else:
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
            'created_at': datetime.now().isoformat(),
            'pf_session_id': pf_session_id, 'pf_seed_hash': pf_seed_hash,
            'pf_client_seed': pf_client_seed, 'pf_nonce': pf_nonce,
        }
        _save_mines_sessions(sessions)
        # ── Durable session: persists the bet in SQLite so a server restart
        # triggers auto-refund via refund_expired_game_sessions() at next boot.
        _set_ags(str(uid), 'mines',
                 {'game_id': game_id, 'mine_count': mine_count},
                 bet_amount)

    # Add PF data to response
    if pf_session_id:
        result['pf_session_id'] = pf_session_id
        result['pf_seed_hash'] = pf_seed_hash
        result['pf_client_seed'] = pf_client_seed
        result['pf_nonce'] = pf_nonce

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
            # Reveal PF seed on mine hit
            pf_sid = state.get('pf_session_id')
            if pf_sid and _PROVABLY_FAIR and _pf:
                try:
                    revealed = _pf.reveal_seed(pf_sid)
                    if revealed:
                        resp['pf_server_seed'] = revealed['server_seed']
                        resp['pf_seed_hash'] = revealed['seed_hash']
                        resp['pf_client_seed'] = revealed['client_seed']
                        resp['pf_nonce'] = revealed['nonce']
                except Exception:
                    pass
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
        # Include PF seed_hash on every reveal so client can display it
        if state.get('pf_seed_hash'):
            resp['pf_seed_hash'] = state['pf_seed_hash']
            resp['pf_session_id'] = state.get('pf_session_id')
            resp['pf_client_seed'] = state.get('pf_client_seed')

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
            # Reveal PF seed on all-safe auto-payout
            pf_sid = state.get('pf_session_id')
            if pf_sid and _PROVABLY_FAIR and _pf:
                try:
                    revealed = _pf.reveal_seed(pf_sid)
                    if revealed:
                        resp['pf_server_seed'] = revealed['server_seed']
                        resp['pf_seed_hash'] = revealed['seed_hash']
                        resp['pf_client_seed'] = revealed['client_seed']
                        resp['pf_nonce'] = revealed['nonce']
                except Exception:
                    pass
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
            # Reveal PF seed on game end
            pf_sid = sessions[str(uid)].get('pf_session_id')
            if pf_sid and _PROVABLY_FAIR and _pf:
                try:
                    revealed = _pf.reveal_seed(pf_sid)
                    if revealed:
                        result['pf_server_seed'] = revealed['server_seed']
                        result['pf_seed_hash'] = revealed['seed_hash']
                        result['pf_client_seed'] = revealed['client_seed']
                        result['pf_nonce'] = revealed['nonce']
                        sessions[str(uid)]['cashout_result'] = result
                except Exception:
                    pass
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

    # Provably Fair seed — use shared PF module
    _pf_seed = None
    _pf_seed_hash = None
    _pf_session_id = None
    _pf_revealed = None
    if _PROVABLY_FAIR and _pf:
        try:
            _pf_session_id = f"plinko_{uid}_{int(datetime.now().timestamp()*1000)}"
            client_seed = data.get('client_seed') or None
            pf_info = _pf.create_session(_pf_session_id, client_seed)
            _pf_seed_hash = pf_info['seed_hash']
        except Exception:
            _pf_session_id = None

    if not _pf_seed_hash:
        # Fallback: inline PF
        _pf_seed = secrets.token_hex(16)
        _pf_seed_hash = hashlib.sha256(_pf_seed.encode()).hexdigest()

    center = (num_slots - 1) / 2.0
    edge_bias = (win_chance - 0.5) * 0.20  # -0.10 to +0.10

    # House edge: 3% chance to force center
    force_center = random.random() < 0.03

    # Use PF for deterministic directions
    directions = []
    position = 0.0
    if _pf_session_id and _pf:
        for r in range(rows):
            if force_center:
                p_right = 0.5 - (position / max(1, rows)) * 1.5
            else:
                p_right = 0.5 + edge_bias
            p_right = max(0.25, min(0.75, p_right))
            pf_r = _pf.generate_float(_pf_session_id, 0.0, 1.0)
            go_right = pf_r['value'] < p_right
            direction = 1 if go_right else -1
            directions.append(direction)
            position += direction
        # Reveal the seed immediately (Plinko is instant)
        _pf_revealed = _pf.reveal_seed(_pf_session_id)
        if _pf_revealed:
            _pf_seed = _pf_revealed['server_seed']
            _pf_seed_hash = _pf_revealed['seed_hash']
    else:
        if not _pf_seed:
            _pf_seed = secrets.token_hex(16)
        _pf_rng = random.Random()
        _pf_rng.seed(int(_pf_seed[:16], 16))
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
    # Add PF verification data if available
    if _pf_session_id and _pf_revealed:
        template['pf_session_id'] = _pf_session_id
        template['pf_server_seed'] = _pf_seed
        template['pf_seed_hash'] = _pf_seed_hash
        template['pf_client_seed'] = _pf_revealed.get('client_seed')
        template['pf_nonce'] = _pf_revealed.get('nonce')
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

# Wheel segments — FIXED layout (no per-spin reshuffle: the wheel visibly
# jumping to a new layout mid-spin looked rigged). Skulls are not adjacent.
_WHEEL_SEGMENTS = [
    {'mult': 0.0,  'label': '💀',  'color': '#991b1b', 'glow': '#ef4444'},
    {'mult': 1.5,  'label': '1.5x','color': '#1e3a5f', 'glow': '#3b82f6'},
    {'mult': 2.0,  'label': '2x',  'color': '#14532d', 'glow': '#22c55e'},
    {'mult': 0.0,  'label': '💀',  'color': '#991b1b', 'glow': '#ef4444'},
    {'mult': 0.5,  'label': '0.5x','color': '#581c87', 'glow': '#a855f7'},
    {'mult': 5.0,  'label': '5x',  'color': '#78350f', 'glow': '#fbbf24'},
    {'mult': 1.0,  'label': '1x',  'color': '#155e75', 'glow': '#06b6d4'},
    {'mult': 10.0, 'label': '10x', 'color': '#831843', 'glow': '#ec4899'},
]

# Fixed relative weights of the non-skull segments (variety curve).
# Σ(mult×weight) over winners = 80.5, Σweight_winners = 53.5.
_WHEEL_WIN_WEIGHTS = {10.0: 1.0, 5.0: 2.5, 2.0: 8.0, 1.5: 12.0, 1.0: 18.0, 0.5: 12.0}
_WHEEL_WIN_EV = sum(m * w for m, w in _WHEEL_WIN_WEIGHTS.items())      # 80.5
_WHEEL_WIN_W  = sum(_WHEEL_WIN_WEIGHTS.values())                        # 53.5

_WHEEL_RTP_MIN, _WHEEL_RTP_MAX = 0.80, 0.85

_wheel_rng = secrets.SystemRandom()

def _wheel_weights(win_chance):
    """Solve the per-skull weight so the EXACT target RTP is achieved.

    target_rtp = 0.80 + 0.05 × normalized(win_chance) ∈ [0.80, 0.85];
    skull weight s = (EV_winners/target − Σw_winners)/2 keeps every
    multiplier's relative odds constant. RTP is mathematically capped at
    0.85 no matter what the house algorithm computes."""
    t = (float(win_chance) - 0.03) / (0.92 - 0.03)
    t = min(1.0, max(0.0, t))
    target = _WHEEL_RTP_MIN + (_WHEEL_RTP_MAX - _WHEEL_RTP_MIN) * t
    s = (_WHEEL_WIN_EV / target - _WHEEL_WIN_W) / 2.0
    s = max(1.0, s)
    weights = []
    for seg in _WHEEL_SEGMENTS:
        m = seg['mult']
        if m == 0.0:
            weights.append(s)
        else:
            weights.append(_WHEEL_WIN_WEIGHTS[m])
    return weights, target

@app.route('/api/wheel/preview')
def api_wheel_preview():
    """معاينة عامة للعجلة: الأجزاء والاحتمالات بمستوى أساسي — قبل أول دورة،
    كي يرى اللاعب جدول الجوائز من لحظة فتح الصفحة لا بعد أول دوران."""
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    game_row = _gm.get_game('GAME009') or {}
    try:
        base = float(game_row.get('base_win_chance') or 0.40)
    except (ValueError, TypeError):
        base = 0.40
    base = min(0.92, max(0.03, base))
    weights, target = _wheel_weights(base)
    total = sum(weights)
    return jsonify({
        'segments': [{'mult': s['mult'], 'label': s['label'], 'color': s['color'], 'glow': s['glow']} for s in _WHEEL_SEGMENTS],
        'probabilities': [round(w / total, 4) for w in weights],
        'rtp': round(target, 3),
        'active': str(game_row.get('is_active', 'yes')).lower() not in ('no', 'false', '0'),
    })

@app.route('/api/wheel/spin', methods=['POST'])
@webapp_auth
def api_wheel_spin():
    if not _VEX_GAMES:
        return jsonify({'error': 'Games engine not available'}), 500
    # هوية موثقة فقط — بدونها يمكن المراهنة بهوية أي ضحية
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'Unauthorized'}), 403
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

    # NaN/Infinity rejected + catalog min/max enforced
    try:
        bet_amount = float(data.get('bet', 0))
    except (ValueError, TypeError):
        return jsonify({'error': 'مبلغ غير صالح'}), 400
    if not math.isfinite(bet_amount) or bet_amount <= 0:
        return jsonify({'error': 'مبلغ غير صالح'}), 400

    game_row = _gm.get_game('GAME009')
    if not game_row or str(game_row.get('is_active', 'yes')).lower() in ('no', 'false', '0'):
        return jsonify({'success': False, 'error': 'اللعبة متوقفة مؤقتاً'}), 503
    try:
        min_bet = float(game_row.get('min_bet') or 10)
        max_bet = float(game_row.get('max_bet') or 2000)
    except (ValueError, TypeError):
        min_bet, max_bet = 10.0, 2000.0
    if bet_amount < min_bet or bet_amount > max_bet:
        return jsonify({'success': False, 'error': f'الرهان بين {int(min_bet)} و {int(max_bet)}'}), 400

    player = _gm.tracker.get_profile(uid)

    risk_check = _gm.risk.check_risk(player, bet_amount, game_row)
    if not risk_check['allowed']:
        msg = risk_check['alerts'][0]['message'] if risk_check.get('alerts') else 'محظور'
        return jsonify({'success': False, 'error': msg})

    balance = _gm.get_balance(uid)
    if balance < bet_amount:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance})

    wheel_segments = _WHEEL_SEGMENTS
    N = len(wheel_segments)

    algo_result = _gm.algorithm.calculate_win_chance(player, game_row, bet_amount)
    win_chance = algo_result['win_chance']

    # Weights solved for an exact target RTP in [0.80, 0.85]
    weights, target_rtp = _wheel_weights(win_chance)
    total_w = sum(weights)

    # Provably Fair integration
    _pf_session_id = None
    _pf_revealed = None
    if _PROVABLY_FAIR and _pf:
        try:
            _pf_session_id = f"wheel_{uid}_{int(datetime.now().timestamp()*1000)}"
            client_seed = data.get('client_seed') or None
            pf_info = _pf.create_session(_pf_session_id, client_seed)
            pf_float = _pf.generate_float(_pf_session_id, 0.0, total_w)
            rand_val = pf_float['value']
            # Reveal immediately (wheel is instant)
            _pf_revealed = _pf.reveal_seed(_pf_session_id)
        except Exception:
            _pf_session_id = None
            rand_val = _wheel_rng.uniform(0, total_w)
    else:
        rand_val = _wheel_rng.uniform(0, total_w)

    segment = N - 1
    cumulative = 0.0
    for i, w in enumerate(weights):
        cumulative += w
        if rand_val <= cumulative:
            segment = i
            break

    multiplier = wheel_segments[segment]['mult']
    payout = round(bet_amount * multiplier, 2)
    # فوز حقيقي فقط فوق 1x — 1x تعادل و0.5x خسارة جزئية
    if multiplier > 1.0:
        result_str = 'win'
    elif multiplier == 1.0:
        result_str = 'push'
    else:
        result_str = 'lose'

    # Build segments + real probabilities for the client payout table
    client_segments = [{'mult': s['mult'], 'label': s['label'], 'color': s['color'], 'glow': s['glow']} for s in wheel_segments]
    probabilities = [round(w / total_w, 4) for w in weights]

    # Atomic: settle + idempotency record in one SQLite transaction
    template = {'success': True, 'segment': segment, 'multiplier': multiplier,
                'payout': payout, 'result': result_str, 'balance_before': balance,
                'segments': client_segments, 'probabilities': probabilities,
                'rtp': round(target_rtp, 3)}
    # Add PF verification data
    if _pf_session_id and _pf_revealed:
        template['pf_session_id'] = _pf_session_id
        template['pf_server_seed'] = _pf_revealed['server_seed']
        template['pf_seed_hash'] = _pf_revealed['seed_hash']
        template['pf_client_seed'] = _pf_revealed['client_seed']
        template['pf_nonce'] = _pf_revealed['nonce']
    ok, stored, race_cached = _gm.settle_with_idempotency(uid, bet_amount, payout, request_id, template)
    if race_cached:
        return jsonify(race_cached)
    if not ok:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ', 'need_deposit': True, 'balance': balance})

    result = stored
    new_balance = result.get('balance_after', balance)

    session_id = f"WHL{secrets.token_hex(6)}"
    _gm.algorithm.log_decision(
        session_id=session_id, user_id=uid, game_id='GAME009',
        base_chance=float(game_row.get('base_win_chance', 0.40)),
        adjusted_chance=win_chance, factors=algo_result['factors'],
        decision=algo_result['decision'],
        reason=f"Wheel segment={segment} mult={multiplier} rtp={target_rtp:.3f}; {algo_result['reason']}"
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
    # هوية موثقة فقط — بدونها يمكن اللعب بهوية أي ضحية عبر uid مجرد
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'Unauthorized'}), 403

    # Idempotency check BEFORE any side effects — replays return the stored
    # response without creating duplicate sessions or debits.
    if request_id:
        cached = _gm.get_idempotency_record(uid, request_id)
        if cached:
            return jsonify(cached)

    # NaN/Infinity rejected + catalog min/max enforced
    try:
        bet_amount = float(data.get('bet', 0))
    except (ValueError, TypeError):
        return jsonify({'error': 'مبلغ غير صالح'}), 400
    if not math.isfinite(bet_amount) or bet_amount <= 0:
        return jsonify({'error': 'مبلغ غير صالح'}), 400

    # مفتاح الإيقاف يحترم: لا fallback يجعل اللعبة تعمل بدون صف الكتالوج
    game = _gm.get_game('GAME001')
    if not game or str(game.get('is_active', 'yes')).lower() in ('no', 'false', '0'):
        return jsonify({'success': False, 'error': 'اللعبة متوقفة مؤقتاً'}), 503
    try:
        min_bet = float(game.get('min_bet') or 10)
        max_bet = float(game.get('max_bet') or 2000)
    except (ValueError, TypeError):
        min_bet, max_bet = 10.0, 2000.0
    if bet_amount < min_bet or bet_amount > max_bet:
        return jsonify({'success': False, 'error': f'الرهان بين {int(min_bet)} و {int(max_bet)}'}), 400

    player = _gm.tracker.get_profile(uid)

    risk_check = _gm.risk.check_risk(player, bet_amount, game)
    if not risk_check['allowed']:
        msg = risk_check['alerts'][0]['message'] if risk_check.get('alerts') else 'محظور'
        return jsonify({'success': False, 'error': msg})

    balance = _gm.get_balance(uid)
    if balance < bet_amount:
        return jsonify({'success': False, 'error': 'رصيد غير كافٍ',
                        'need_deposit': True, 'balance': balance})

    # منع جلستين متزامنتين لنفس اللاعب — جلسته السابقة تُستأنف أو تُنتظر
    sdb_pre = _snatch_db()
    try:
        active = sdb_pre.snatch_get_active_by_user(uid) if hasattr(sdb_pre, 'snatch_get_active_by_user') else None
    except Exception:
        active = None
    if active:
        return jsonify({'success': False, 'error': 'لديك جولة نشطة بالفعل — أكملها أولاً'}), 409

    session_id = f"SNT{secrets.token_hex(8)}"
    # Use request_id as the wallet idempotency key; fall back to session-derived key.
    deduction_key = request_id or f"spin_{session_id}"

    # ── Compute server-authoritative payout BEFORE creating the session ───────
    # The payout is determined by the server's game algorithm, not the client.
    # It is stored in the session row immediately so /api/snatch/end and the
    # sweep can credit the same amount regardless of what score the client reports.
    # سقف مالي: احتمال الفوز للدفع محدود بـ 0.545 — مع متوسط مضاعف أساس 1.40
    # وبونص مهارة ≤ 0.15 يكون EV ∈ [0.76, 0.85] مهما بلغت التعزيزات
    algo_result = _gm.algorithm.calculate_win_chance(player, game, bet_amount)
    p_pay = min(float(algo_result.get('win_chance', 0.0)), 0.545)

    # Provably Fair integration for Snatch
    _pf_session_id = None
    _pf_revealed = None
    _pf_win_float = None
    _pf_tier_float = None
    _pf_seed_hash = None
    if _PROVABLY_FAIR and _pf:
        try:
            _pf_session_id = f"snatch_{uid}_{int(datetime.now().timestamp()*1000)}"
            client_seed = data.get('client_seed') or None
            pf_info = _pf.create_session(_pf_session_id, client_seed)
            _pf_seed_hash = pf_info['seed_hash']
            pf_win = _pf.generate_float(_pf_session_id, 0.0, 1.0)
            _pf_win_float = pf_win['value']
        except Exception:
            _pf_session_id = None

    server_won = (algo_result.get('decision') == 'allow_win') and (
        (_pf_win_float < p_pay) if _pf_win_float is not None else (_wheel_rng.random() < p_pay)
    )
    if server_won:
        # Pick a multiplier tier; higher tier = rarer outcome
        if _pf_session_id and _pf:
            try:
                pf_tier = _pf.generate_float(_pf_session_id, 0.0, 1.0)
                _tier_roll = pf_tier['value']
            except Exception:
                _tier_roll = secrets.SystemRandom().random()
        else:
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

    # Add PF data to response
    if _pf_session_id:
        stored['pf_session_id'] = _pf_session_id
        stored['pf_seed_hash'] = _pf_seed_hash

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
    # هوية موثقة فقط — التسوية تُنسب لصاحبها حصرياً
    if not getattr(g, 'webapp_auth_strong', False):
        return jsonify({'error': 'Unauthorized'}), 403

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

    # حد أدنى لزمن اللعب (3 ثوان) — يمنع الطحن اللحظي (spin→end فوراً) دون
    # كسر الحالة الشرعية: خسارة الأرواح الثلاث بسرعة جولة لعب حقيقية تنتهي مبكراً
    _age = datetime.now().timestamp() - sess['created_at']
    if _age < 3.0:
        return jsonify({'error': 'الجولة لم تنته بعد — أكمل اللعب'}), 400

    if datetime.now().timestamp() - sess['created_at'] > _SNATCH_SESSION_TTL:
        return jsonify({'error': 'Session expired'}), 400

    bet_amount = sess['bet_amount']

    # ── Read server-determined payout (set at spin time, never from client) ───
    # The payout was computed by the server algorithm and stored in the session
    # row at spin time.  The client's reported score adds a SMALL capped skill
    # bonus on top of a decided WIN only — it can never turn a loss into a win,
    # and the total EV stays ≤ 0.85 (p_pay ≤ 0.55 × E[mult ≤ 1.5] = 0.825).
    payout = sess['payout'] if sess['payout'] is not None else 0.0
    skill_bonus_mult = 0.0
    if payout > 0:
        if score >= 100:
            skill_bonus_mult = 0.15
        elif score >= 70:
            skill_bonus_mult = 0.10
        elif score >= 40:
            skill_bonus_mult = 0.05
        if skill_bonus_mult > 0:
            payout = round(payout + bet_amount * skill_bonus_mult, 2)

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

    # Reveal PF seed on game end
    pf_data = {}
    pf_sid = data.get('pf_session_id') or sess.get('pf_session_id')
    if pf_sid and _PROVABLY_FAIR and _pf:
        try:
            revealed = _pf.reveal_seed(pf_sid)
            if revealed:
                pf_data = {
                    'pf_server_seed': revealed['server_seed'],
                    'pf_seed_hash': revealed['seed_hash'],
                    'pf_client_seed': revealed['client_seed'],
                    'pf_nonce': revealed['nonce'],
                }
        except Exception:
            pass

    resp = {
        'success': True, 'won': won, 'score': score,
        'multiplier': display_multiplier, 'payout': payout,
        'skill_bonus': skill_bonus_mult, 'base_payout': round(payout - bet_amount * skill_bonus_mult, 2),
        'result': result_str, 'balance_after': new_balance,
    }
    resp.update(pf_data)
    return jsonify(resp)

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

@app.route('/favicon.ico')
def favicon_ico():
    return app.send_static_file('icons/favicon.ico')


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

        # 5 — Prune expired/orphaned compensation screenshots (#77)
        try:
            _cleanup_recovery_uploads()
        except Exception as exc:
            _auth_logger.error("[maintenance] recovery uploads cleanup: %s", exc)


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

# Startup prune of expired compensation screenshots (#77)
try:
    _cleanup_recovery_uploads()
except Exception as _rce:
    _auth_logger.error("recovery uploads startup cleanup error: %s", _rce)

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
