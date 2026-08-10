#!/usr/bin/env python3
"""
otp_bot.py — VEX OTP Code Bot
بوت متخصص لإرسال رموز الدخول للموقع فقط.
- لا يستقبل أوامر من العملاء — فقط /start
- يتحقق من تسجيل المستخدم في users.csv
- يولد رمز 6 أرقام سهل النسخ
- يرسله في رسالة منسقة + يخزنه في web_auth_codes.json
- التوكن يُضاف من لوحة الأدمن عبر bot_tokens.csv (description='otp_bot')
"""

import os
import sys
import json
import time
import random
import logging
import urllib.request
import urllib.parse
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s - OTP Bot - %(message)s')
logger = logging.getLogger(__name__)

OTP_FILE = 'web_auth_codes.json'
USERS_CSV = 'users.csv'
OTP_BOT_TOKEN = None
OTP_BOT_RUNNING = False
_last_update_id = 0


def _load_otp_codes():
    try:
        if os.path.exists(OTP_FILE):
            with open(OTP_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}


def _save_otp_codes(codes):
    try:
        with open(OTP_FILE, 'w') as f:
            json.dump(codes, f)
    except:
        pass


def _find_user(telegram_id):
    """البحث عن مستخدم في users.csv"""
    import csv
    try:
        with open(USERS_CSV, 'r', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                if row.get('telegram_id') == str(telegram_id):
                    return row
    except:
        pass
    return None


def _generate_and_store_code(user_id, user_name):
    """توليد رمز 6 أرقام وتخزينه"""
    code = str(random.randint(100000, 999999))
    codes = _load_otp_codes()
    # إزالة الرموز القديمة لنفس المستخدم
    codes = {k: v for k, v in codes.items() if k != str(user_id)}
    codes[str(user_id)] = {
        'code': code,
        'name': user_name,
        'created': time.time()
    }
    _save_otp_codes(codes)
    return code


def _send_message(token, chat_id, text, parse_mode='HTML'):
    """إرسال رسالة عبر Telegram API"""
    try:
        url = f'https://api.telegram.org/bot{token}/sendMessage'
        data = json.dumps({
            'chat_id': int(chat_id),
            'text': text,
            'parse_mode': parse_mode
        }).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logger.error(f"Send message error: {e}")


def _send_photo(token, chat_id, photo_url, caption=''):
    """إرسال صورة"""
    try:
        url = f'https://api.telegram.org/bot{token}/sendPhoto'
        data = json.dumps({
            'chat_id': int(chat_id),
            'photo': photo_url,
            'caption': caption,
            'parse_mode': 'HTML'
        }).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=10)
    except:
        pass


def _get_bot_info(token):
    """الحصول على معلومات البوت"""
    try:
        url = f'https://api.telegram.org/bot{token}/getMe'
        resp = urllib.request.urlopen(url, timeout=10)
        return json.loads(resp.read().decode())
    except:
        return None


def _process_update(token, update):
    """معالجة تحديث واحد من Telegram"""
    message = update.get('message', {})
    if not message:
        return

    chat_id = message.get('chat', {}).get('id')
    user_id = message.get('from', {}).get('id')
    text = message.get('text', '').strip()

    if not chat_id or not user_id:
        return

    # فقط /start — لا أوامر أخرى
    if text.startswith('/start'):
        # فحص المستخدم
        user = _find_user(user_id)
        if not user:
            _send_message(token, chat_id,
                "🔒 <b>غير مسجل</b>\n\n"
                "يجب التسجيل أولاً في البوت الرئيسي قبل استخدام خدمة الرموز.\n\n"
                "🌐 الموقع: https://vex.deals")
            return

        name = user.get('name', '')
        code = _generate_and_store_code(user_id, name)

        # إرسال الرمز في رسالة واضحة سهلة النسخ
        _send_message(token, chat_id,
            "🔐 <b>رمز دخول موقع VEX</b>\n\n"
            f"<code>{code}</code>\n\n"
            "⏰ صالح لمدة 5 دقائق\n"
            "🌐 أدخل الرمز في: https://vex.deals\n\n"
            "📋 انسخ الرمز أعلاه وألصقه في خانة الدخول بالموقع",
            parse_mode='HTML')

        logger.info(f"OTP code sent to user {user_id} ({name})")
    else:
        # أي رسالة أخرى — رفض
        _send_message(token, chat_id,
            "🤖 هذا البوت مخصص لإرسال رموز الدخول فقط.\n\n"
            "أرسل /start للحصول على رمز دخول جديد.\n"
            "🌐 https://vex.deals")


def _poll(token):
    """حلقة polling"""
    global _last_update_id, OTP_BOT_RUNNING
    OTP_BOT_RUNNING = True

    # فحص صحة التوكن
    info = _get_bot_info(token)
    if not info or not info.get('ok'):
        logger.error("Invalid bot token — OTP bot cannot start")
        OTP_BOT_RUNNING = False
        return False

    bot_name = info.get('result', {}).get('username', 'unknown')
    logger.info(f"✅ OTP Bot started: @{bot_name}")

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
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(5)

    logger.info("OTP Bot stopped")
    return True


def start_otp_bot(token):
    """تشغيل بوت OTP في thread منفصل"""
    global OTP_BOT_TOKEN
    OTP_BOT_TOKEN = token

    def _run():
        _poll(token)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def stop_otp_bot():
    """إيقاف بوت OTP"""
    global OTP_BOT_RUNNING
    OTP_BOT_RUNNING = False


def is_otp_bot_running():
    """فحص حالة بوت OTP"""
    return OTP_BOT_RUNNING


def get_otp_bot_token_from_csv():
    """قراءة توكن بوت OTP من bot_tokens.csv"""
    import csv
    try:
        with open('bot_tokens.csv', 'r', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                if row.get('description') == 'otp_bot' and row.get('is_active') == 'yes':
                    return row.get('token', '')
    except:
        pass
    return None


def auto_start_otp_bot():
    """تشغيل تلقائي لبوت OTP عند بدء النظام"""
    token = get_otp_bot_token_from_csv()
    if token:
        logger.info("Found OTP bot token in bot_tokens.csv — starting...")
        start_otp_bot(token)
        return True
    return False


if __name__ == '__main__':
    # تشغيل مباشر إذا تم استدعاء الملف
    token = sys.argv[1] if len(sys.argv) > 1 else get_otp_bot_token_from_csv()
    if token:
        _poll(token)
    else:
        print("No OTP bot token found. Add a bot with description='otp_bot' in bot_tokens.csv")
        print("Or run: python otp_bot.py YOUR_BOT_TOKEN")
