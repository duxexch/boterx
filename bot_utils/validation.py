"""
bot_utils/validation.py — Stateless validation functions
Extracted from comprehensive_bot.py — no self dependency.
"""

def sanitize_input(text):
    """تنظيف مدخلات المستخدم لمنع حقن CSV والهجمات الأخرى"""
    if not text:
        return text
    dangerous_chars = ['=', '+', '-', '@', '\t', '\r', '\n']
    if text and text[0] in dangerous_chars:
        text = ' ' + text
    if len(text) > 500:
        text = text[:500]
    text = text.replace('\x00', '')
    return text.strip()

def validate_phone_number(phone):
    """التحقق من صحة رقم الهاتف"""
    if not phone:
        return False
    phone = phone.replace(' ', '').replace('-', '')
    if phone.startswith('+'):
        digits = phone[1:]
    else:
        digits = phone
    return digits.isdigit() and 7 <= len(digits) <= 20

def validate_amount(amount_str):
    """التحقق من صحة المبلغ المدخل"""
    try:
        amount = float(amount_str)
        if amount <= 0 or amount > 1000000:
            return None
        return amount
    except (ValueError, TypeError):
        return None
