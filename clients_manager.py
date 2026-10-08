#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
نظام العملاء (White-Label / Agency) — ClientManager
كل عميل = بوت تيليجرام خاص + دخول لوحة خاص + مميزات محددة + اشتراك زمني.

التصميم:
- clients.csv كمخزن رئيسي (utf-8-sig + قفل threading) — متوافق مع أنماط المشروع.
- كلمة المرور: sha256(salt + password) بملح عشوائي لكل عميل.
- عزل البيانات الكامل: كل عميل له مجلد clients/<id>/ يحتوي symlinks لملفات
  الكود + ملفات بياناته الخاصة — البوت يعمل كعملية مستقلة بمجلد عمل خاص،
  فلا يتشارك أي CSV/SQLite مع البوت الرئيسي أو مع العملاء الآخرين.
- الاشتراك: تاريخ انتهاء — عند الانتهاء تُوقف العملية تلقائياً (حراسة دورية)
  ويُعلَّم العميل "expired" حتى يجدد.
"""

import os
import csv
import json
import hashlib
import secrets
import subprocess
import threading
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENTS_DIR = os.path.join(BASE_DIR, 'clients')
CLIENTS_FILE = os.path.join(BASE_DIR, 'clients.csv')

_csv_lock = threading.RLock()

CLIENT_FIELDS = [
    'id', 'name', 'contact', 'bot_username', 'bot_token',
    'dash_username', 'dash_password_hash', 'salt',
    'features', 'admin_ids',
    'subscription_start', 'subscription_end',
    'status', 'bot_autostart', 'notes', 'created_at', 'last_login',
    'revenue_share', 'custom_domain', 'balance', 'preferred_pm',
]

# ── كتالوج مميزات النظام — يظهر في لوحة الإدارة ويثبَّت في بوت العميل ──
FEATURES = {
    'deposit':      '💰 إيداع',
    'withdraw':     '💸 سحب',
    'matching':     '🔄 مطابقة P2P',
    'trading':      '💱 تداول USDT',
    'compensation': '💎 تعويض 100%',
    'games':        '🎮 ألعاب (يانصيب/عجلة/ويب آب)',
    'referral':     '🎁 إحالات ودعوات',
    'complaints':   '📨 شكاوى',
    'apps':         '📱 تطبيقات',
    'multi_lang':   '🌐 تعدد اللغات',
}

# ملفات الكود التي تُربط ب symlink داخل مجلد كل عميل (البيانات تبقى محلية)
_CODE_FILES = [
    'comprehensive_bot.py', 'svrp.py', 'matching.py', 'theme_config.py',
    'multi_bot.py', 'database.py', 'db_manager.py', 'game_engine.py',
    'house_algorithm.py', 'player_tracker.py', 'risk_manager.py',
    'provably_fair.py', 'ai_providers.py', 'translation_dict.json',
]
_CODE_DIRS = ['handlers', 'bot_utils', 'i18n']


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode('utf-8')).hexdigest()


class ClientManager:

    def __init__(self):
        self._init_store()
        self._procs = {}  # client_id -> subprocess.Popen (جلسة اللوحة الحالية)
        self._reconcile_processes()

    # ─────────────────────────── المخزن ───────────────────────────

    def _init_store(self):
        with _csv_lock:
            if not os.path.exists(CLIENTS_FILE):
                with open(CLIENTS_FILE, 'w', newline='', encoding='utf-8-sig') as f:
                    csv.DictWriter(f, fieldnames=CLIENT_FIELDS).writeheader()
            else:
                # ترحيل الأعمدة الناقصة
                with open(CLIENTS_FILE, 'r', encoding='utf-8-sig') as f:
                    rows = list(csv.DictReader(f))
                    fields = csv.DictReader(open(CLIENTS_FILE, encoding='utf-8-sig')).fieldnames or []
                missing = [c for c in CLIENT_FIELDS if c not in fields]
                if missing:
                    for r in rows:
                        for c in missing:
                            r.setdefault(c, '')
                    self._write_rows(rows)

    def _read_rows(self):
        with _csv_lock:
            try:
                with open(CLIENTS_FILE, 'r', encoding='utf-8-sig') as f:
                    return [r for r in csv.DictReader(f) if r.get('id')]
            except Exception as e:
                logger.error(f'clients.csv read error: {e}')
                return []

    def _write_rows(self, rows):
        with open(CLIENTS_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=CLIENT_FIELDS)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, '') for k in CLIENT_FIELDS})

    # ─────────────────────────── CRUD ───────────────────────────

    def list_clients(self):
        out = []
        for c in self._read_rows():
            c = dict(c)
            c['running'] = self.is_running(c['id'])
            c['days_left'] = self.days_left(c)
            c['expired'] = self.is_expired(c)
            out.append(c)
        return out

    def get(self, client_id):
        for c in self._read_rows():
            if c['id'] == client_id:
                return c
        return None

    def get_by_username(self, username):
        u = (username or '').strip().lower()
        for c in self._read_rows():
            if (c.get('dash_username') or '').strip().lower() == u:
                return c
        return None

    def create(self, name, bot_username, bot_token, dash_username, dash_password,
               features=None, subscription_days=30, contact='', admin_ids='',
               notes='', revenue_share=30):
        if not name or not bot_token or len(bot_token) < 20:
            return None, 'الاسم والتوكن مطلوبان (التوكن غير صالح)'
        if not dash_username or not dash_password or len(dash_password) < 6:
            return None, 'اسم المستخدم وكلمة مرور (6 أحرف على الأقل) مطلوبان'
        if self.get_by_username(dash_username):
            return None, 'اسم المستخدم مستخدم بالفعل'
        feats = [f for f in (features or []) if f in FEATURES] or list(FEATURES.keys())
        salt = secrets.token_hex(16)
        client_id = f"CLT{secrets.token_hex(3).upper()}"
        row = {
            'id': client_id, 'name': name, 'contact': contact,
            'bot_username': (bot_username or '').strip().lstrip('@'),
            'bot_token': bot_token.strip(),
            'dash_username': dash_username.strip(),
            'dash_password_hash': _hash_password(dash_password, salt),
            'salt': salt,
            'features': json.dumps(feats),
            'admin_ids': (admin_ids or '').strip(),
            'subscription_start': datetime.now().strftime('%Y-%m-%d'),
            'subscription_end': (datetime.now() + timedelta(days=int(subscription_days or 30))).strftime('%Y-%m-%d'),
            'status': 'active', 'bot_autostart': 'no', 'notes': notes,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'last_login': '',
            'revenue_share': str(int(revenue_share or 30)),
            'custom_domain': '',
            'balance': '0',
            'preferred_pm': '',
        }
        with _csv_lock:
            rows = self._read_rows()
            rows.append(row)
            self._write_rows(rows)
        self._ensure_client_dir(client_id)
        logger.info(f'Client created: {client_id} ({name})')
        return row, None

    def update(self, client_id, data):
        with _csv_lock:
            rows = self._read_rows()
            for r in rows:
                if r['id'] != client_id:
                    continue
                for k in ('name', 'contact', 'bot_username', 'bot_token',
                          'admin_ids', 'notes', 'status', 'revenue_share', 'preferred_pm'):
                    if k in data and data[k] is not None:
                        r[k] = str(data[k]).strip()
                if 'features' in data and data['features'] is not None:
                    feats = [f for f in data['features'] if f in FEATURES]
                    r['features'] = json.dumps(feats or list(FEATURES.keys()))
                if data.get('dash_password'):
                    if len(data['dash_password']) < 6:
                        return False, 'كلمة المرور يجب أن تكون 6 أحرف على الأقل'
                    salt = secrets.token_hex(16)
                    r['salt'] = salt
                    r['dash_password_hash'] = _hash_password(data['dash_password'], salt)
                if data.get('dash_username'):
                    u = str(data['dash_username']).strip()
                    other = self.get_by_username(u)
                    if other and other['id'] != client_id:
                        return False, 'اسم المستخدم مستخدم بالفعل'
                    r['dash_username'] = u
                self._write_rows(rows)
                return True, None
        return False, 'العميل غير موجود'

    def delete(self, client_id, keep_data=True):
        self.stop(client_id)
        with _csv_lock:
            rows = [r for r in self._read_rows() if r['id'] != client_id]
            self._write_rows(rows)
        if not keep_data:
            import shutil
            d = self.client_dir(client_id)
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
        return True

    # ─────────────────────────── المصادقة ───────────────────────────

    def verify_login(self, username, password):
        c = self.get_by_username(username)
        if not c:
            return None
        if _hash_password(password or '', c.get('salt', '')) != c.get('dash_password_hash'):
            return None
        if self.is_expired(c) and c.get('status') != 'suspended':
            # منتهي — دخول مسموح ليرى حالة اشتراكه فقط (تحدده اللوحة)
            pass
        with _csv_lock:
            rows = self._read_rows()
            for r in rows:
                if r['id'] == c['id']:
                    r['last_login'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            self._write_rows(rows)
        return c

    # ─────────────────────────── الاشتراك ───────────────────────────

    @staticmethod
    def is_expired(c):
        end = (c.get('subscription_end') or '').strip()
        if not end:
            return False
        try:
            return datetime.now() >= datetime.strptime(end, '%Y-%m-%d') + timedelta(days=1)
        except ValueError:
            return False

    @staticmethod
    def days_left(c):
        end = (c.get('subscription_end') or '').strip()
        if not end:
            return 9999
        try:
            d = (datetime.strptime(end, '%Y-%m-%d') + timedelta(days=1) - datetime.now())
            return max(0, d.days)
        except ValueError:
            return 0

    def renew(self, client_id, days):
        days = int(days or 30)
        with _csv_lock:
            rows = self._read_rows()
            for r in rows:
                if r['id'] != client_id:
                    continue
                try:
                    base = datetime.strptime(r.get('subscription_end') or '', '%Y-%m-%d')
                    if base < datetime.now():
                        base = datetime.now()
                except ValueError:
                    base = datetime.now()
                r['subscription_end'] = (base + timedelta(days=days)).strftime('%Y-%m-%d')
                if r.get('status') == 'expired':
                    r['status'] = 'active'
                self._write_rows(rows)
                return r.get('subscription_end')
        return None

    def check_subscriptions(self, notify=None):
        """حراسة الاشتراكات كل دورة:
        1) أوقف بوت أي عميل منتهي وعلّمه expired + أشعر المالك.
        2) إصلاح ذاتي: أعد تشغيل بوت أي عميل ينبغي أن يعمل ومات (bot_autostart=yes)."""
        stopped = []
        for c in self._read_rows():
            if self.is_expired(c) and self.is_running(c['id']):
                name = c.get('name', c['id'])
                self.stop(c['id'])
                stopped.append(name)
                with _csv_lock:
                    rows = self._read_rows()
                    for r in rows:
                        if r['id'] == c['id']:
                            r['status'] = 'expired'
                            r['bot_autostart'] = 'no'
                    self._write_rows(rows)
                if notify:
                    try:
                        notify(f"⏳ <b>انتهى اشتراك عميل</b>\n👤 {name} (<code>{c['id']}</code>)\n"
                               f"🤖 البوت: @{c.get('bot_username', '')}\nتم إيقاف البوت تلقائياً — جدد الاشتراك من لوحة العملاء.")
                    except Exception:
                        pass
        # إصلاح ذاتي: العملاء الذين ينبغي أن يعملوا
        healed = []
        for c in self._read_rows():
            if (c.get('status') == 'active' and c.get('bot_autostart') == 'yes'
                    and not self.is_expired(c) and (c.get('bot_token') or '').strip()
                    and not self.is_running(c['id'])):
                ok, _msg = self.start(c['id'])
                if ok:
                    healed.append(c.get('name', c['id']))
        if healed and notify:
            try:
                notify("🔁 <b>إعادة تشغيل تلقائية</b>\n" + '\n'.join('• ' + n for n in healed))
            except Exception:
                pass
        # تحذير قرب الانتهاء (3 أيام) — مرة يومياً عبر ملف علامة
        soon = []
        for c in self._read_rows():
            dl = self.days_left(c)
            if 0 < dl <= 3 and self.is_running(c['id']):
                soon.append((c.get('name', c['id']), dl))
        if soon and notify:
            mark = os.path.join(CLIENTS_DIR, '.expiry_warned_' + datetime.now().strftime('%Y%m%d'))
            if not os.path.exists(mark):
                try:
                    os.makedirs(CLIENTS_DIR, exist_ok=True)
                    open(mark, 'w').close()
                    lines = '\n'.join(f'• {n} — بقيت {d} يوم' for n, d in soon)
                    notify(f"⚠️ <b>اشتراكات تنتهي قريباً</b>\n{lines}")
                except Exception:
                    pass
        return stopped

    # ──────────────────── نظام المالية (إيداع / سحب / رصيد) ────────────────────

    def get_balance(self, client_id):
        """جلب رصيد العميل"""
        c = self.get(client_id)
        return float(c.get('balance') or 0) if c else 0

    def set_balance(self, client_id, amount):
        """تحديث رصيد العميل"""
        with _csv_lock:
            rows = self._read_rows()
            for r in rows:
                if r['id'] == client_id:
                    r['balance'] = str(round(float(amount), 2))
                    self._write_rows(rows)
                    return True
        return False

    def _tx_file(self, client_id):
        return os.path.join(self.client_dir(client_id), 'client_transactions.csv')

    def _read_tx(self, client_id):
        path = self._tx_file(client_id)
        if not os.path.exists(path):
            return []
        with open(path, 'r', encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))

    def _write_tx(self, client_id, rows):
        path = self._tx_file(client_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)

    def add_transaction(self, client_id, tx_type, amount, method='', note='', status='pending'):
        """إضافة معاملة (إيداع/سحب)"""
        if not os.path.exists(self.client_dir(client_id)):
            return None
        tx_id = f"TX{int(__import__('time').time()*1000)}{__import__('secrets').token_hex(2).upper()}"
        tx = {
            'id': tx_id, 'type': tx_type,
            'amount': str(round(float(amount), 2)),
            'method': method, 'note': note, 'status': status,
            'created_at': __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M'),
            'processed_at': '', 'admin_note': '',
        }
        with _csv_lock:
            rows = self._read_tx(client_id)
            rows.append(tx)
            self._write_tx(client_id, rows)
        return tx

    def get_transactions(self, client_id, status=None, tx_type=None):
        """جلب معاملات العميل"""
        rows = self._read_tx(client_id)
        if status:
            rows = [r for r in rows if r.get('status') == status]
        if tx_type:
            rows = [r for r in rows if r.get('type') == tx_type]
        return rows

    def process_transaction(self, client_id, tx_id, action, amount_override=None, admin_note=''):
        """معالجة معاملة (approve/reject)"""
        with _csv_lock:
            rows = self._read_tx(client_id)
            for tx in rows:
                if tx['id'] != tx_id:
                    continue
                if action not in ('approved', 'rejected'):
                    return None, 'إجراء غير صالح'
                tx['status'] = action
                tx['processed_at'] = __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')
                tx['admin_note'] = admin_note
                amount = float(amount_override or tx['amount'])
                if action == 'approved':
                    current = self.get_balance(client_id)
                    if tx['type'] == 'deposit':
                        self.set_balance(client_id, current + amount)
                    elif tx['type'] == 'withdraw':
                        if current < amount:
                            return None, f'الرصيد غير كافٍ ({current:.2f} < {amount:.2f})'
                        self.set_balance(client_id, current - amount)
                self._write_tx(client_id, rows)
                return tx, None
        return None, 'المعاملة غير موجودة'

    def get_pending_count(self, client_id=None):
        """عدد المعاملات المعلقة"""
        if client_id:
            return len(self.get_transactions(client_id, status='pending'))
        total = 0
        for c in self.list_clients():
            total += len(self.get_transactions(c['id'], status='pending'))
        return total

    # ─────────────────────────── تشغيل البوت ───────────────────────────

    def client_dir(self, client_id):
        return os.path.join(CLIENTS_DIR, client_id)

    def _ensure_client_dir(self, client_id):
        d = self.client_dir(client_id)
        os.makedirs(d, exist_ok=True)
        for fn in _CODE_FILES:
            dst = os.path.join(d, fn)
            if not os.path.exists(dst):
                try:
                    os.symlink(os.path.join(BASE_DIR, fn), dst)
                except OSError:
                    pass
        for sub in _CODE_DIRS:
            dst = os.path.join(d, sub)
            if not os.path.exists(dst):
                try:
                    os.symlink(os.path.join(BASE_DIR, sub), dst)
                except OSError:
                    pass
        # لا .env داخل مجلد العميل — التوكن يمرر عبر متغيرات البيئة
        return d

    def pid_file(self, client_id):
        return os.path.join(self.client_dir(client_id), 'bot.pid')

    def is_running(self, client_id):
        # عملية مُدارة في هذه الجلسة؟
        p = self._procs.get(client_id)
        if p and p.poll() is None:
            return True
        # عملية من جلسة سابقة (بعد إعادة تشغيل اللوحة) — عبر ملف pid
        try:
            pid = int(open(self.pid_file(client_id)).read().strip())
            os.kill(pid, 0)
            return True
        except Exception:
            return False

    def start(self, client_id):
        c = self.get(client_id)
        if not c:
            return False, 'العميل غير موجود'
        if self.is_running(client_id):
            return False, 'بوت العميل يعمل بالفعل'
        if c.get('status') == 'suspended':
            return False, 'العميل موقوف — أعد تفعيله أولاً'
        if self.is_expired(c):
            return False, 'اشتراك العميل منتهي — جدد الاشتراك أولاً'
        token = (c.get('bot_token') or '').strip()
        if len(token) < 20:
            return False, 'التوكن غير صالح'
        d = self._ensure_client_dir(client_id)
        env = dict(os.environ)
        env['BOT_TOKEN'] = token
        env['ADMIN_USER_IDS'] = (c.get('admin_ids') or '').strip() or env.get('ADMIN_USER_IDS', '')
        env['CLIENT_ID'] = client_id
        env['CLIENT_NAME'] = c.get('name', '')
        env['CLIENT_FEATURES'] = c.get('features', '')
        env['MULTI_BOT'] = 'no'
        py = os.path.join(BASE_DIR, 'venv', 'bin', 'python')
        if not os.path.exists(py):
            py = 'python3'
        try:
            logf = open(os.path.join(d, 'bot.log'), 'a', encoding='utf-8')
            proc = subprocess.Popen([py, 'comprehensive_bot.py'], cwd=d, env=env,
                                    stdout=logf, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            self._procs[client_id] = proc
            with open(self.pid_file(client_id), 'w') as f:
                f.write(str(proc.pid))
            with _csv_lock:
                rows = self._read_rows()
                for r in rows:
                    if r['id'] == client_id:
                        r['bot_autostart'] = 'yes'
                        if r.get('status') not in ('active',):
                            r['status'] = 'active'
                self._write_rows(rows)
            logger.info(f'Client bot started: {client_id} pid={proc.pid}')
            return True, f'تم تشغيل بوت العميل (PID {proc.pid})'
        except Exception as e:
            logger.error(f'Client bot start failed {client_id}: {e}')
            return False, f'فشل التشغيل: {e}'

    def stop(self, client_id):
        # إيقاف مقصود — لا يعاد تشغيله تلقائياً
        with _csv_lock:
            rows = self._read_rows()
            for r in rows:
                if r['id'] == client_id:
                    r['bot_autostart'] = 'no'
            self._write_rows(rows)
        killed = False
        p = self._procs.pop(client_id, None)
        if p and p.poll() is None:
            try:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
                killed = True
            except Exception:
                pass
        # عملية يتيمة من جلسة سابقة
        try:
            pid = int(open(self.pid_file(client_id)).read().strip())
            os.kill(pid, 15)
            killed = True
        except Exception:
            pass
        try:
            os.remove(self.pid_file(client_id))
        except OSError:
            pass
        return killed

    def restart(self, client_id):
        self.stop(client_id)
        import time
        time.sleep(1.5)
        return self.start(client_id)

    def _reconcile_processes(self):
        """بعد إعادة تشغيل اللوحة: أوقف بوتات العملاء الموقوفين/المنتهين،
        وأعد تشغيل من كان bot_autostart=yes (استمرارية عبر إعادة التشغيل)."""
        try:
            for c in self._read_rows():
                if c.get('status') == 'suspended' or self.is_expired(c):
                    if self.is_running(c['id']):
                        self.stop(c['id'])
                    continue
                if (c.get('bot_autostart') == 'yes' and (c.get('bot_token') or '').strip()
                        and not self.is_running(c['id'])):
                    self.start(c['id'])
        except Exception as e:
            logger.error(f'reconcile processes failed: {e}')

    # ─────────────────────────── بيانات العميل (للمالك) ───────────────────────────

    def client_data(self, client_id, kind, limit=100):
        """قراءة بيانات عميل من مجلده المعزول — رؤية كاملة للمالك."""
        d = self.client_dir(client_id)
        files = {
            'users': 'users.csv', 'transactions': 'transactions.csv',
            'complaints': 'complaints.csv', 'svrp_wallets': 'svrp_wallets.csv',
            'svrp_credits': 'svrp_credits.csv', 'bonus_requests': 'bonus_requests.csv',
            'recovery_requests': 'recovery_requests.csv', 'companies': 'companies.csv',
        }
        fn = files.get(kind)
        if not fn:
            return [], []
        path = os.path.join(d, fn)
        if not os.path.exists(path):
            return [], []
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = [r for r in reader if any((v or '').strip() for v in r.values())]
            fields = reader.fieldnames or []
            return rows[:limit], fields
        except Exception as e:
            logger.error(f'client_data read failed {client_id}/{kind}: {e}')
            return [], []

    def client_stats(self, client_id):
        users, _ = self.client_data(client_id, 'users', 100000)
        txns, _ = self.client_data(client_id, 'transactions', 100000)
        c = self.get(client_id) or {}
        deposits = [t for t in txns if t.get('type') == 'deposit']
        withdraws = [t for t in txns if t.get('type') == 'withdraw']
        pending = [t for t in txns if t.get('status') == 'pending']
        return {
            'total_users': len(users),
            'total_transactions': len(txns),
            'deposits': len(deposits),
            'withdrawals': len(withdraws),
            'pending': len(pending),
            'banned': sum(1 for u in users if u.get('is_banned') == 'yes'),
            'running': self.is_running(client_id),
            'days_left': self.days_left(c),
            'expired': self.is_expired(c),
        }


# مفرد للوحة
_manager = None
_manager_lock = threading.Lock()


# ────────────────── إدارة وسائل الدفع (للإيداع والسحب) ──────────────────

PAYMENT_METHODS_FILE = os.path.join(BASE_DIR, 'rental_payment_methods.csv')
_pm_lock = threading.RLock()
PM_FIELDS = ['id', 'name', 'pm_type', 'account_number', 'bank_name', 'holder_name', 'status', 'created_at']


class RentalPaymentManager:
    """إدارة وسائل الدفع التي يستخدمها العميلون للإيداع والسحب"""

    def _read(self):
        if not os.path.exists(PAYMENT_METHODS_FILE):
            return []
        with open(PAYMENT_METHODS_FILE, 'r', encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))

    def _write(self, rows):
        with open(PAYMENT_METHODS_FILE, 'w', encoding='utf-8-sig', newline='') as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=PM_FIELDS)
                w.writeheader()
                w.writerows(rows)

    def get_all(self, active_only=False):
        with _pm_lock:
            rows = self._read()
        if active_only:
            rows = [r for r in rows if r.get('status') == 'active']
        return rows

    def get(self, pm_id):
        return next((r for r in self._read() if r['id'] == pm_id), None)

    def create(self, name, pm_type, account_number, bank_name='', holder_name=''):
        pm_id = f"PM{int(__import__('time').time()*1000)}{__import__('secrets').token_hex(2).upper()}"
        row = {
            'id': pm_id, 'name': name, 'pm_type': pm_type,
            'account_number': account_number, 'bank_name': bank_name,
            'holder_name': holder_name, 'status': 'active',
            'created_at': __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M'),
        }
        with _pm_lock:
            rows = self._read()
            rows.append(row)
            self._write(rows)
        return row

    def update(self, pm_id, data):
        with _pm_lock:
            rows = self._read()
            for r in rows:
                if r['id'] == pm_id:
                    for k in ('name', 'pm_type', 'account_number', 'bank_name', 'holder_name', 'status'):
                        if k in data:
                            r[k] = data[k]
                    self._write(rows)
                    return r
        return None

    def delete(self, pm_id):
        with _pm_lock:
            rows = self._read()
            rows = [r for r in rows if r['id'] != pm_id]
            self._write(rows)
        return True


_payment_mgr = None
_pm_mgr_lock = threading.Lock()


def get_payment_manager() -> RentalPaymentManager:
    global _payment_mgr
    with _pm_mgr_lock:
        if _payment_mgr is None:
            _payment_mgr = RentalPaymentManager()
        return _payment_mgr


def get_client_manager() -> ClientManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = ClientManager()
        return _manager
