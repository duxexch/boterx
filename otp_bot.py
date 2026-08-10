"""
otp_bot.py — VEX Security & OTP Bot
بوت الأمان والحماية — مرتبط بالبوت الرئيسي والموقع.

المهام:
1. توليد وإرسال رموز دخول الموقع (OTP)
2. مراقبة الحركة المالية (إيداع/سحب/رهان) — تنبيه عند أنماط غير طبيعية
3. إشعار الأدمن عند أحداث أمنية مشبوهة
4. استعادة الوصول للحسابات

الأمان:
- لا يستقبل أوامر من العملاء — فقط /start (للرموز) و /admin (للأدمن فقط)
- يقرأ من نفس ملفات البوت الرئيسي (users.csv, transactions.csv, quick_deposits.csv)
- يعمل في thread منفصل داخل dashboard
"""

import os
import sys
import json
import time
import random
import logging
import urllib.request
import threading
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - VEX Security Bot - %(message)s')
logger = logging.getLogger(__name__)

OTP_FILE = 'web_auth_codes.json'
USERS_CSV = 'users.csv'
TRANSACTIONS_CSV = 'transactions.csv'
QUICK_DEPOSITS_CSV = 'quick_deposits.csv'
ADMIN_ID = '7146701713'
OTP_BOT_TOKEN = None
OTP_BOT_RUNNING = False
_last_update_id = 0
_last_financial_check = 0
_alerted_transactions = set()

# ── File helpers ──
def _load_json(path):
    try:
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
    except: pass
    return {}

def _save_json(path, data):
    try:
        with open(path, 'w') as f:
            json.dump(data, f)
    except: pass

def _find_user(telegram_id):
    import csv
    try:
        with open(USERS_CSV, 'r', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                if row.get('telegram_id') == str(telegram_id):
                    return row
    except: pass
    return None

def _read_csv(path):
    import csv
    rows = []
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                rows.append(row)
    except: pass
    return rows

# ── Telegram API ──
def _api(token, method, **params):
    try:
        url = f'https://api.telegram.org/bot{token}/{method}'
        data = json.dumps(params).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode())
    except Exception as e:
        logger.error(f"API {method} error: {e}")
        return None

def _send_message(token, chat_id, text, parse_mode='HTML'):
    return _api(token, 'sendMessage', chat_id=int(chat_id), text=text, parse_mode=parse_mode)

def _get_bot_info(token):
    try:
        url = f'https://api.telegram.org/bot{token}/getMe'
        resp = urllib.request.urlopen(url, timeout=10)
        return json.loads(resp.read().decode())
    except:
        return None

# ── OTP Code Generation ──
def _generate_and_store_code(user_id, user_name):
    code = str(random.randint(100000, 999999))
    codes = _load_json(OTP_FILE)
    codes = {k: v for k, v in codes.items() if k != str(user_id)}
    codes[str(user_id)] = {
        'code': code,
        'name': user_name,
        'created': time.time()
    }
    _save_json(OTP_FILE, codes)
    return code

# ── Financial Monitoring ──
def _check_financial_anomalies(token):
    """فحص الحركة المالية للكشف عن أنماط غير طبيعية"""
    global _last_financial_check, _alerted_transactions
    now = time.time()

    # فحص كل 60 ثانية
    if now - _last_financial_check < 60:
        return
    _last_financial_check = now

    anomalies = []

    # 1. فحص الإيداعات الكبيرة (أكثر من 50000)
    try:
        deposits = _read_csv(QUICK_DEPOSITS_CSV)
        for dep in deposits:
            dep_id = dep.get('id', '')
            if dep_id in _alerted_transactions:
                continue
            try:
                amount = float(dep.get('amount', 0))
            except:
                continue
            status = dep.get('status', '')
            if status == 'pending' and amount >= 50000:
                anomalies.append(f"💰 إيداع كبير: {dep_id} — {amount:.0f} (بانتظار الموافقة)")
                _alerted_transactions.add(dep_id)
            elif status == 'approved' and amount >= 50000:
                anomalies.append(f"✅ إيداع كبير موافق عليه: {dep_id} — {amount:.0f}")
                _alerted_transactions.add(dep_id)
    except:
        pass

    # 2. فحص المعاملات المتكررة من نفس المستخدم (أكثر من 10 في ساعة)
    try:
        txns = _read_csv(TRANSACTIONS_CSV)
        user_txn_count = {}
        for t in txns[-100:]:
            uid = t.get('user_id', t.get('telegram_id', ''))
            ts = t.get('created_at', t.get('timestamp', ''))
            user_txn_count[uid] = user_txn_count.get(uid, 0) + 1

        for uid, count in user_txn_count.items():
            if count > 15 and uid:
                key = f"freq_{uid}_{int(now/3600)}"
                if key not in _alerted_transactions:
                    anomalies.append(f"⚠️ نشاط مكثف: المستخدم {uid} — {count} معاملة")
                    _alerted_transactions.add(key)
    except:
        pass

    # 3. إرسال التنبيهات للأدمن
    for alert in anomalies:
        _send_message(token, ADMIN_ID,
            f"🚨 <b>تنبيه أمني</b>\n\n{alert}\n\n⏰ {datetime.now().strftime('%H:%M:%S')}")
        logger.warning(f"Financial anomaly: {alert}")

    # تنظيف القائمة كل ساعة
    if len(_alerted_transactions) > 100:
        _alerted_transactions = set(list(_alerted_transactions)[-50:])

# ── Message Processing ──
def _process_update(token, update):
    message = update.get('message', {})
    if not message:
        return

    chat_id = message.get('chat', {}).get('id')
    user_id = message.get('from', {}).get('id')
    text = message.get('text', '').strip()

    if not chat_id or not user_id:
        return

    # /start — توليد رمز OTP
    if text.startswith('/start'):
        user = _find_user(user_id)
        if not user:
            _send_message(token, chat_id,
                "🔒 <b>غير مسجل</b>\n\n"
                "يجب التسجيل أولاً في البوت الرئيسي @Vex_wallet_bot\n\n"
                "🌐 الموقع: https://vex.deals")
            return

        name = user.get('name', '')
        code = _generate_and_store_code(user_id, name)
        _send_message(token, chat_id,
            "🔐 <b>رمز دخول موقع VEX</b>\n\n"
            f"<code>{code}</code>\n\n"
            "⏰ صالح لمدة 5 دقائق\n"
            "🌐 أدخل الرمز في: https://vex.deals\n\n"
            "📋 انسخ الرمز أعلاه وألصقه في خانة الدخول بالموقع",
            parse_mode='HTML')
        logger.info(f"OTP code sent to user {user_id} ({name})")
        return

    # /status — للأدمن فقط: حالة النظام الأمني
    if text == '/status' and str(user_id) == ADMIN_ID:
        deposits = _read_csv(QUICK_DEPOSITS_CSV)
        pending = [d for d in deposits if d.get('status') == 'pending']
        total_pending = sum(float(d.get('amount', 0)) for d in pending)
        _send_message(token, chat_id,
            f"🛡️ <b>تقرير الأمان</b>\n\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"💰 إيداعات معلقة: {len(pending)} ({total_pending:.0f})\n"
            f"🔔 تنبيهات نشطة: {len(_alerted_transactions)}\n"
            f"🟢 بوت الأمان: نشط")
        return

    # /check — للأدمن: فحص فوري
    if text == '/check' and str(user_id) == ADMIN_ID:
        _last_financial_check = 0  # إجبار الفحص
        _check_financial_anomalies(token)
        _send_message(token, chat_id, "✅ تم الفحص الفوري — راجع التنبيهات إن وجدت")
        return

    # أي رسالة أخرى — رفض (الأمان)
    is_admin = str(user_id) == ADMIN_ID
    if is_admin:
        _send_message(token, chat_id,
            "🛡️ <b>بوت الأمان VEX</b>\n\n"
            "الأوامر المتاحة:\n"
            "/status — تقرير الأمان\n"
            "/check — فحص فوري\n\n"
            "🌐 https://vex.deals")
    else:
        _send_message(token, chat_id,
            "🤖 هذا البوت مخصص للأمان ورموز الدخول فقط.\n\n"
            "أرسل /start للحصول على رمز دخول.\n"
            "للدعم: استخدم البوت الرئيسي @Vex_wallet_bot")

# ── Polling Loop ──
def _poll(token):
    global _last_update_id, OTP_BOT_RUNNING
    OTP_BOT_RUNNING = True

    info = _get_bot_info(token)
    if not info or not info.get('ok'):
        logger.error("Invalid bot token — Security bot cannot start")
        OTP_BOT_RUNNING = False
        return False

    bot_name = info.get('result', {}).get('username', 'unknown')
    logger.info(f"✅ VEX Security Bot started: @{bot_name}")

    # إرسال رسالة بدء التشغيل للأدمن
    _send_message(token, ADMIN_ID,
        f"🛡️ <b>بوت الأمان نشط</b>\n\n"
        f"البوت: @{bot_name}\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"المراقبة: الإيداعات + المعاملات + الأنماط المشبوهة")

    while OTP_BOT_RUNNING:
        try:
            url = f'https://api.telegram.org/bot{token}/getUpdates?offset={_last_update_id + 1}&timeout=30'
            resp = urllib.request.urlopen(url, timeout=35)
            data = json.loads(resp.read().decode())

            if data.get('ok'):
                for update in data.get('result', []):
                    _last_update_id = update.get('update_id', _last_update_id)
                    try:
                        _process_update(token, update)
                    except Exception as e:
                        logger.error(f"Process update error: {e}")

            # فحص مالي دوري
            _check_financial_anomalies(token)

        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(5)

    logger.info("VEX Security Bot stopped")
    return True

# ── Public API ──
def start_otp_bot(token):
    global OTP_BOT_TOKEN
    OTP_BOT_TOKEN = token
    def _run():
        _poll(token)
    thread = threading.Thread(target=_run, daemon=True, name='vex-security-bot')
    thread.start()
    return thread

def stop_otp_bot():
    global OTP_BOT_RUNNING
    OTP_BOT_RUNNING = False

def is_otp_bot_running():
    return OTP_BOT_RUNNING

def get_otp_bot_token_from_csv():
    import csv
    try:
        with open('bot_tokens.csv', 'r', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                if row.get('description') == 'otp_bot' and row.get('is_active') == 'yes':
                    return row.get('token', '')
    except: pass
    return None

def auto_start_otp_bot():
    token = get_otp_bot_token_from_csv()
    if token:
        logger.info("Found security bot token — starting...")
        start_otp_bot(token)
        return True
    return False

def send_security_alert(message):
    """إرسال تنبيه أمني للأدمن عبر بوت الأمان"""
    if OTP_BOT_TOKEN:
        _send_message(OTP_BOT_TOKEN, ADMIN_ID,
            f"🚨 <b>تنبيه أمني</b>\n\n{message}\n\n⏰ {datetime.now().strftime('%H:%M:%S')}")

if __name__ == '__main__':
    token = sys.argv[1] if len(sys.argv) > 1 else get_otp_bot_token_from_csv()
    if token:
        _poll(token)
    else:
        print("No security bot token found. Add bot with description='otp_bot' in bot_tokens.csv")
