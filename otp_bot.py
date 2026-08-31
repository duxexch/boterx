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
def _generate_and_store_code(user_id, user_name, phone=''):
    # RNG آمن تشفيرياً — random.randint العادي شبه قابل للتنبؤ نظرياً
    import secrets as _sec
    code = str(_sec.randbelow(900000) + 100000)
    codes = _load_json(OTP_FILE)
    # نظّف رموز هذا المستخدم + أي رمز انتهت صلاحيته (> 5 دقائق)
    now = time.time()
    codes = {k: v for k, v in codes.items()
             if k != str(user_id) and now - v.get('created', 0) <= 300}
    codes[str(user_id)] = {
        'code': code,
        'name': user_name,
        'phone': phone,
        'created': now,
        'attempts': 0,   # عداد محاولات خاطئة — يحذفه السيرفر عند 5
    }
    _save_json(OTP_FILE, codes)
    return code

# ── Financial Monitoring ──
def _check_financial_anomalies(token):
    """فحص الحركة المالية للكشف عن أنماط غير طبيعية"""
    global _last_financial_check, _alerted_transactions
    now = time.time()

    # فحص كل 15 دقيقة
    if now - _last_financial_check < 900:
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

    # 2. فحص المعاملات المتكررة من نفس المستخدم (نافذة ساعتين فعلية)
    try:
        txns = _read_csv(TRANSACTIONS_CSV)
        user_txn_count = {}
        cutoff = now - 2 * 3600  # آخر ساعتين فقط
        for t in txns[-100:]:
            uid = t.get('user_id', t.get('telegram_id', ''))
            # transactions.csv يستخدم عمود date — وسمّيات أخرى احتياطية
            ts_str = str(t.get('date', t.get('created_at', t.get('timestamp', ''))) or '')
            # فلترة زمنية فعلية — لا نحسب معاملات أقدم من ساعتين
            try:
                ts = datetime.strptime(ts_str[:16], '%Y-%m-%d %H:%M').timestamp()
                if ts < cutoff:
                    continue
            except Exception:
                pass  # توقيت غير مقروء — نحتسبه (دفاعياً)
            user_txn_count[uid] = user_txn_count.get(uid, 0) + 1

        for uid, count in user_txn_count.items():
            if count > 50 and uid:
                # تنبيه واحد لكل مستخدم في اليوم — لا تكرار كل ساعة
                key = f"freq_{uid}_{datetime.now().strftime('%Y%m%d')}"
                if key not in _alerted_transactions:
                    anomalies.append(f"⚠️ نشاط مكثف: المستخدم {uid} — {count} معاملة خلال ساعتين")
                    _alerted_transactions.add(key)
    except:
        pass

    # 3. إرسال التنبيهات للأدمن
    for alert in anomalies:
        _send_message(token, ADMIN_ID,
            f"🚨 <b>تنبيه أمني</b>\n\n{alert}\n\n⏰ {datetime.now().strftime('%H:%M:%S')}")
        logger.warning(f"Financial anomaly: {alert}")

    # تنظيف: نحتفظ بمعرفات الإيداعات (حتى لا تكرر أبداً) ومفاتيح اليوم فقط
    if len(_alerted_transactions) > 100:
        today = datetime.now().strftime('%Y%m%d')
        _alerted_transactions = {k for k in _alerted_transactions
                                 if not k.startswith('freq_') or today in k}

# ── Message Processing ──
def _process_update(token, update):
    message = update.get('message', {})
    if not message:
        return

    chat_id = message.get('chat', {}).get('id')
    user_id = message.get('from', {}).get('id')
    text = message.get('text', '').strip() if message.get('text') else ''

    if not chat_id or not user_id:
        return

    # ── Contact shared (for web_auth flow) ──
    if 'contact' in message:
        contact = message['contact']
        phone = contact.get('phone_number', '')
        contact_user_id = str(contact.get('user_id', user_id))
        first_name = contact.get('first_name', '')
        last_name = contact.get('last_name', '')
        full_name = (first_name + ' ' + last_name).strip() or first_name or 'User'

        # Delete the contact message (privacy)
        try:
            _api(token, 'deleteMessage', chat_id=chat_id, message_id=message.get('message_id'))
        except:
            pass

        # Generate code
        code = _generate_and_store_code(contact_user_id, full_name, phone)

        # Send code (with VEX artwork)
        caption = ("🔐 <b>رمز دخول موقع VEX</b>\n\n"
                   f"<code>{code}</code>\n\n"
                   "⏰ صالح لمدة 5 دقائق\n"
                   "🌐 أدخل الرمز في: https://vex.deals\n\n"
                   "📋 انسخ الرمز أعلاه وألصقه في خانة الدخول بالموقع")
        try:
            _api(token, 'sendPhoto', chat_id=chat_id,
                 photo='https://vex.deals/static/icons/og-image.jpg?v=20260821b',
                 caption=caption, parse_mode='HTML')
        except Exception:
            _send_message(token, chat_id, caption, parse_mode='HTML')
        logger.info(f"OTP code sent to user {contact_user_id} ({full_name}) phone={phone}")
        return

    # ── /start web_auth — request contact ──
    if text.startswith('/start'):
        # Check if user wants web auth
        is_web_auth = 'web_auth' in text

        if is_web_auth:
            # Send contact request button
            keyboard = {
                'keyboard': [[{'text': '📱 مشاركة رقم الهاتف', 'request_contact': True}]],
                'one_time_keyboard': True,
                'resize_keyboard': True
            }
            _api(token, 'sendMessage',
                chat_id=chat_id,
                text="🔐 <b>تسجيل دخول موقع VEX</b>\n\n"
                     "للحصول على رمز الدخول، يرجى مشاركة رقم هاتفك.\n"
                     "اضغط الزر أدناه 👇",
                parse_mode='HTML',
                reply_markup=json.dumps(keyboard))
            logger.info(f"Contact request sent to user {user_id}")
            return

        # Regular /start (no web_auth) — also request contact
        keyboard = {
            'keyboard': [[{'text': '📱 مشاركة رقم الهاتف', 'request_contact': True}]],
            'one_time_keyboard': True,
            'resize_keyboard': True
        }
        _api(token, 'sendMessage',
            chat_id=chat_id,
            text="🔐 <b>بوت الأمان VEX</b>\n\n"
                 "للحصول على رمز دخول الموقع، شارك رقم هاتفك.\n"
                 "اضغط الزر أدناه 👇",
            parse_mode='HTML',
            reply_markup=json.dumps(keyboard))
        return

    # ── Code pasted by user (6 digits) — verify and respond ──
    if text.isdigit() and len(text) == 6:
        codes = _load_json(OTP_FILE)
        for uid, data in codes.items():
            if str(data.get('code', '')) == text:
                _send_message(token, chat_id,
                    "✅ <b>رمز صحيح!</b>\n\n"
                    "تم تأكيد رمزك. عد إلى الموقع https://vex.deals")
                return
        _send_message(token, chat_id, "❌ رمز غير صحيح أو منتهي الصلاحية.")
        return

    # ── Admin commands ──
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

    if text == '/check' and str(user_id) == ADMIN_ID:
        global _last_financial_check
        _last_financial_check = 0
        _check_financial_anomalies(token)
        _send_message(token, chat_id, "✅ تم الفحص الفوري — راجع التنبيهات إن وجدت")
        return

    # ── Any other message ──
    is_admin = str(user_id) == ADMIN_ID
    if is_admin:
        _send_message(token, chat_id,
            "🛡️ <b>بوت الأمان VEX</b>\n\n"
            "الأوامر: /status /check\n\n"
            "🌐 https://vex.deals")
    else:
        _send_message(token, chat_id,
            "🤖 أرسل /start للحصول على رمز دخول الموقع.\n"
            "للدعم: @Vex_wallet_bot\n"
            "🌐 https://vex.deals")

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

    # تم تعطيل رسالة البداية — البوت الرئيسي يبعت heartbeat كل 5 ساعات
    logger.info(f"OTP Bot @{bot_name} running — startup message disabled")

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

# قفل ملفي يحتفظ به الموديول حياً — لا تُطلق fcntl.flock إلا بإغلاق الملف/موت العملية
_singleton_lock_file = None

def auto_start_otp_bot():
    global _singleton_lock_file
    token = get_otp_bot_token_from_csv()
    if not token:
        return False
    # نسخة واحدة عبر كل عمال gunicorn: أول عامل يقتنص القفل يشغّل البوت،
    # والباقي يتجاهل — بدونه يرسل كل عامل رسالة تشغيل وتنبيهات مكررة
    try:
        import fcntl
        lock_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.otp_bot_singleton.lock')
        _singleton_lock_file = open(lock_path, 'w')
        try:
            fcntl.flock(_singleton_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            logger.info("Security bot already running in another worker — skipping")
            _singleton_lock_file.close()
            _singleton_lock_file = None
            return False
    except ImportError:
        pass  # بيئات بلا fcntl (تطوير محلي على ويندوز) — عامل واحد عادةً
    logger.info("Found security bot token — starting...")
    start_otp_bot(token)
    return True

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
