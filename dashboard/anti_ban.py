"""
Anti-Ban Message System — smart message delivery with platform rule monitoring.
Uses spintax, delays, rate limiting, and AI monitoring to avoid bans.
"""

import os
import csv
import json
import re
import random
import time
import hashlib
import sqlite3
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'boterx.db')
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ═══════════════════════════════════════════════════════════════
#  PLATFORM BAN RULES
# ═══════════════════════════════════════════════════════════════

PLATFORM_LIMITS = {
    'telegram': {
        'max_messages_per_hour': 30,
        'max_messages_per_day': 500,
        'min_delay_seconds': 2,
        'max_delay_seconds': 10,
        'same_content_cooldown_hours': 24,
        'max_links_per_message': 5,
        'ban_triggers': ['spam', 'flood', 'similar_content', 'too_many_links'],
        'safe_practices': ['vary_text', 'add_delays', 'limit_links', 'rotate_accounts'],
    },
    'whatsapp': {
        'max_messages_per_hour': 20,
        'max_messages_per_day': 300,
        'min_delay_seconds': 5,
        'max_delay_seconds': 30,
        'same_content_cooldown_hours': 48,
        'max_links_per_message': 2,
        'ban_triggers': ['business_account_limit', 'spam_report', 'similar_content', 'bulk_send'],
        'safe_practices': ['use_template_messages', 'vary_text', 'add_delays', 'personalize'],
    },
    'instagram': {
        'max_messages_per_hour': 10,
        'max_messages_per_day': 100,
        'min_delay_seconds': 10,
        'max_delay_seconds': 60,
        'same_content_cooldown_hours': 72,
        'max_links_per_message': 1,
        'ban_triggers': ['automation_detection', 'spam_report', 'rate_limit'],
        'safe_practices': ['human_like_delays', 'varied_content', 'limited_links'],
    },
}

# ═══════════════════════════════════════════════════════════════
#  SPINTAX ENGINE
# ═══════════════════════════════════════════════════════════════

SPINTAX_TEMPLATES = {
    'greeting': [
        'مرحباً {name} 👋',
        'أهلاً {name}! 👋',
        'السلام عليكم {name} 🌟',
        'مرحباً يا {name} ❤️',
        'Hi {name}! 👋',
        'Hey {name}! 🌟',
    ],
    'promo_opening': [
        '🔥 عرض خاص لك',
        '⚡ لا تفوت الفرصة',
        '🎯 عرض لفترة محدودة',
        '💥 خصم حصري',
        '🌟omething مميز بانتظارك',
        '🎁 هدية لك',
    ],
    'cta': [
        'سجل الآن 👇',
        'اضغط هنا للتفاصيل 👇',
        'لا تفوّت الفرصة، سجل الآن 👇',
        'ابدأ الآن 👇',
        ' Join now 👇',
        'Sign up here 👇',
    ],
    'closing': [
        'مع تحياتنا ❤️',
        'فريق الدعم 🛡️',
        'نتمنى لك التوفيق 🌟',
        'في انتظارك 🤝',
    ],
}


def spin_text(text):
    """Process spintax in text. Format: {option1|option2|option3}"""
    def replace_match(m):
        options = m.group(1).split('|')
        return random.choice(options)
    result = re.sub(r'\{([^{}]*)\}', replace_match, text)
    return result


def add_spintax_variations(text):
    """Add random variations to make each message unique."""
    variations = [
        (r'مميز', random.choice(['مميز', 'فريد', 'رائع', 'متميز'])),
        (r'عرض خاص', random.choice(['عرض خاص', 'فرصة ذهبية', 'عرض حصري', 'عرض لفترة محدودة'])),
        (r'سجل الآن', random.choice(['سجل الآن', 'سجّل الآن', 'سجل الان', 'سجّل فوراً'])),
        (r'燔', random.choice(['燔', '🔥', '⚡', '💥', '🎯'])),
        (r'لا تفوّت', random.choice(['لا تفوّت', 'لا تفوت', 'لا ت.frame错过', '不要错过'])),
    ]
    for pattern, replacement in variations:
        text = re.sub(pattern, replacement, text, count=1)
    return text


def personalize_message(template, contact):
    """Personalize a message template with contact data."""
    result = template
    name = contact.get('name', '')
    if name:
        result = result.replace('{name}', name)
        result = result.replace('{first_name}', name.split()[0] if name else '')
    else:
        result = result.replace('{name}', '')
        result = result.replace('{first_name}', '')
    result = result.replace('{phone}', contact.get('phone', ''))
    result = result.replace('{country}', contact.get('phone_country', ''))
    result = result.replace('{company}', contact.get('company', ''))
    return result


def generate_unique_message(base_template, contact, platform):
    """Generate a unique message for each contact using spintax + personalization."""
    # Process spintax
    msg = spin_text(base_template)
    # Add variations
    msg = add_spintax_variations(msg)
    # Personalize
    msg = personalize_message(msg, contact)
    # Platform-specific adjustments
    limits = PLATFORM_LIMITS.get(platform, {})
    max_len = 4096 if platform == 'telegram' else 65536 if platform == 'whatsapp' else 2200
    if len(msg) > max_len:
        msg = msg[:max_len - 3] + '...'
    return msg


# ═══════════════════════════════════════════════════════════════
#  RATE LIMITER
# ═══════════════════════════════════════════════════════════════

def _db_exec(sql, params=()):
    try:
        conn = sqlite3.connect(DB_PATH); conn.execute(sql, params); conn.commit(); conn.close(); return True
    except Exception as e:
        logger.error(f"DB exec error: {e}"); return False


def _db_query(sql, params=(), fetch='one'):
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows] if fetch == 'all' else (dict(rows[0]) if rows else None)
    except:
        return [] if fetch == 'all' else None


def init_db():
    _db_exec('''CREATE TABLE IF NOT EXISTS anti_ban_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        account_id TEXT,
        contact_id INTEGER,
        message_hash TEXT,
        status TEXT DEFAULT 'sent',
        error_message TEXT,
        delay_used INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    _db_exec('''CREATE TABLE IF NOT EXISTS anti_ban_rate_limits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        account_id TEXT DEFAULT 'default',
        messages_this_hour INTEGER DEFAULT 0,
        messages_today INTEGER DEFAULT 0,
        last_message_at DATETIME,
        hour_reset_at DATETIME,
        day_reset_at DATETIME,
        UNIQUE(platform, account_id)
    )''')
    _db_exec('''CREATE TABLE IF NOT EXISTS anti_ban_content_hashes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        times_used INTEGER DEFAULT 1,
        first_used DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_used DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(platform, content_hash)
    )''')
    _db_exec('CREATE INDEX IF NOT EXISTS idx_abl_platform ON anti_ban_log(platform, created_at)')
    _db_exec('CREATE INDEX IF NOT EXISTS idx_abl_hash ON anti_ban_log(message_hash)')


def _check_rate_limit(platform, account_id='default'):
    """Check if we're within rate limits. Returns (allowed, wait_seconds)."""
    limits = PLATFORM_LIMITS.get(platform, PLATFORM_LIMITS['telegram'])
    now = datetime.now()
    row = _db_query(
        "SELECT * FROM anti_ban_rate_limits WHERE platform=? AND account_id=?",
        (platform, account_id))

    if not row:
        _db_exec(
            "INSERT INTO anti_ban_rate_limits (platform, account_id, hour_reset_at, day_reset_at) VALUES (?,?,?,?)",
            (platform, account_id, (now + timedelta(hours=1)).isoformat(), (now + timedelta(days=1)).isoformat()))
        return True, 0

    hour_reset = datetime.fromisoformat(row.get('hour_reset_at', now.isoformat()))
    day_reset = datetime.fromisoformat(row.get('day_reset_at', now.isoformat()))

    # Reset counters if needed
    if now > hour_reset:
        _db_exec("UPDATE anti_ban_rate_limits SET messages_this_hour=0, hour_reset_at=? WHERE platform=? AND account_id=?",
                 ((now + timedelta(hours=1)).isoformat(), platform, account_id))
        row['messages_this_hour'] = 0

    if now > day_reset:
        _db_exec("UPDATE anti_ban_rate_limits SET messages_today=0, day_reset_at=? WHERE platform=? AND account_id=?",
                 ((now + timedelta(days=1)).isoformat(), platform, account_id))
        row['messages_today'] = 0

    if row.get('messages_this_hour', 0) >= limits['max_messages_per_hour']:
        wait = (hour_reset - now).seconds + 60
        return False, wait

    if row.get('messages_today', 0) >= limits['max_messages_per_day']:
        wait = (day_reset - now).seconds + 60
        return False, wait

    return True, 0


def _check_content_reuse(platform, content):
    """Check if content was recently used (avoid duplicate content)."""
    limits = PLATFORM_LIMITS.get(platform, PLATFORM_LIMITS['telegram'])
    content_hash = hashlib.md5(content.encode()).hexdigest()[:16]
    row = _db_query(
        "SELECT * FROM anti_ban_content_hashes WHERE platform=? AND content_hash=?",
        (platform, content_hash))

    if row:
        last_used = datetime.fromisoformat(row.get('last_used', datetime.now().isoformat()))
        cooldown = timedelta(hours=limits['same_content_cooldown_hours'])
        if datetime.now() - last_used < cooldown:
            remaining = cooldown - (datetime.now() - last_used)
            return False, f'Content used recently. Wait {remaining.seconds // 60} minutes.', remaining.seconds
        # Update count
        _db_exec("UPDATE anti_ban_content_hashes SET times_used=times_used+1, last_used=NOW WHERE id=?", (row['id'],))
    else:
        _db_exec("INSERT INTO anti_ban_content_hashes (platform, content_hash) VALUES (?,?)",
                 (platform, content_hash))

    return True, None, 0


def _calculate_delay(platform):
    """Calculate a random delay between messages."""
    limits = PLATFORM_LIMITS.get(platform, PLATFORM_LIMITS['telegram'])
    base_delay = random.uniform(limits['min_delay_seconds'], limits['max_delay_seconds'])
    # Add jitter (±30%)
    jitter = base_delay * 0.3 * (random.random() * 2 - 1)
    return max(limits['min_delay_seconds'], int(base_delay + jitter))


def _increment_counters(platform, account_id='default'):
    _db_exec(
        "UPDATE anti_ban_rate_limits SET messages_this_hour=messages_this_hour+1, messages_today=messages_today+1, last_message_at=? WHERE platform=? AND account_id=?",
        (datetime.now().isoformat(), platform, account_id))


def _log_message(platform, account_id, contact_id, message_hash, status, error=None, delay=0):
    _db_exec(
        "INSERT INTO anti_ban_log (platform, account_id, contact_id, message_hash, status, error_message, delay_used) VALUES (?,?,?,?,?,?,?)",
        (platform, account_id, contact_id, message_hash, status, error, delay))


# ═══════════════════════════════════════════════════════════════
#  MESSAGE QUEUE
# ═══════════════════════════════════════════════════════════════

def queue_messages(platform, template, contacts, import_id=None):
    """Queue personalized anti-ban messages for contacts."""
    init_db()
    queued = 0; skipped_rate = 0; skipped_content = 0
    queue_path = os.path.join(BASE_DIR, 'broadcast_queue.csv')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    file_exists = os.path.exists(queue_path)

    for contact in contacts:
        # Generate unique message
        msg = generate_unique_message(template, contact, platform)

        # Check rate limit
        allowed, wait = _check_rate_limit(platform)
        if not allowed:
            skipped_rate += 1
            continue

        # Check content reuse
        content_ok, reason, _ = _check_content_reuse(platform, msg)
        if not content_ok:
            skipped_content += 1
            continue

        # Determine target
        target_id = None
        if platform == 'telegram':
            target_id = contact.get('telegram_id')
        elif platform == 'whatsapp':
            target_id = contact.get('phone')

        if not target_id:
            continue

        # Add to broadcast queue
        with open(queue_path, 'a', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            if not file_exists:
                w.writerow(['chat_id', 'message', 'parse_mode', 'silent', 'pin', 'platform', 'posting_method', 'created_at', 'status', 'media_urls'])
            parse_mode = 'HTML' if platform == 'telegram' else 'text'
            w.writerow([target_id, msg, parse_mode, 'false', 'false', platform, 'api', now, 'pending', '[]'])

        # Mark contact as messaged
        from contact_importer import mark_contact_messaged
        mark_contact_messaged(contact['id'], platform)

        # Log
        msg_hash = hashlib.md5(msg.encode()).hexdigest()[:16]
        _log_message(platform, 'default', contact['id'], msg_hash, 'queued')
        _increment_counters(platform)
        queued += 1

    return {
        'success': True,
        'queued': queued,
        'skipped_rate_limit': skipped_rate,
        'skipped_content_duplicate': skipped_content,
        'platform': platform,
    }


def get_rate_status(platform):
    """Get current rate limit status."""
    init_db()
    limits = PLATFORM_LIMITS.get(platform, PLATFORM_LIMITS['telegram'])
    row = _db_query("SELECT * FROM anti_ban_rate_limits WHERE platform=? AND account_id='default'", (platform,))
    now = datetime.now()
    if not row:
        return {'allowed': True, 'hour_used': 0, 'hour_limit': limits['max_messages_per_hour'],
                'day_used': 0, 'day_limit': limits['max_messages_per_day']}
    return {
        'allowed': True,
        'hour_used': row.get('messages_this_hour', 0),
        'hour_limit': limits['max_messages_per_hour'],
        'day_used': row.get('messages_today', 0),
        'day_limit': limits['max_messages_per_day'],
        'last_message': row.get('last_message_at'),
    }


def get_ban_log(platform=None, limit=50):
    init_db()
    if platform:
        return _db_query("SELECT * FROM anti_ban_log WHERE platform=? ORDER BY created_at DESC LIMIT ?", (platform, limit), 'all')
    return _db_query("SELECT * FROM anti_ban_log ORDER BY created_at DESC LIMIT ?", (limit,), 'all')


def get_content_duplicates(platform=None, limit=20):
    init_db()
    if platform:
        return _db_query("SELECT * FROM anti_ban_content_hashes WHERE platform=? ORDER BY times_used DESC LIMIT ?", (platform, limit), 'all')
    return _db_query("SELECT * FROM anti_ban_content_hashes ORDER BY times_used DESC LIMIT ?", (limit,), 'all')
