"""
bot_utils/telegram_helpers.py — Stateless Telegram keyboard/button helpers
Extracted from comprehensive_bot.py — no self dependency.
"""
import json

def make_inline_btn(text, callback_data):
    """إنشاء زر inline بسرعة"""
    return {'text': text, 'callback_data': callback_data}

def make_inline_keyboard(rows):
    """إنشاء لوحة inline من قائمة صفوف
    كل صف: قائمة من (text, callback_data) tuples"""
    keyboard = []
    for row in rows:
        keyboard.append([make_inline_btn(t, c) for t, c in row])
    return keyboard

def make_reply_keyboard(rows, resize=True):
    """إنشاء reply keyboard من قائمة صفوف"""
    return {
        'keyboard': [[btn if isinstance(btn, dict) else {'text': btn} for btn in row] for row in rows],
        'resize_keyboard': resize
    }

def remove_keyboard():
    """إنشاء reply markup لإزالة لوحة المفاتيح"""
    return {'remove_keyboard': True}
