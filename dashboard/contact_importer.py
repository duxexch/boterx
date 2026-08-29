"""
Contact Importer — imports contacts from Excel/CSV files.
Detects phone numbers, Telegram IDs, and categorizes by platform.
"""

import os
import csv
import json
import re
import hashlib
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'boterx.db')
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Phone number patterns by country
PHONE_PATTERNS = [
    (r'\+?20\s*1[0125]\d{8}', 'EG'),   # Egypt
    (r'\+?966\s*5\d{8}', 'SA'),         # Saudi Arabia
    (r'\+?971\s*5\d{8}', 'AE'),         # UAE
    (r'\+?965\s*[56789]\d{7}', 'KW'),   # Kuwait
    (r'\+?973\s*[36789]\d{7}', 'BH'),   # Bahrain
    (r'\+?974\s*[3567]\d{7}', 'QA'),    # Qatar
    (r'\+?968\s*[79]\d{7}', 'OM'),      # Oman
    (r'\+?961\s*[37]\d{7}', 'LB'),      # Lebanon
    (r'\+?962\s*[789]\d{8}', 'JO'),     # Jordan
    (r'\+?212\s*[67]\d{8}', 'MA'),      # Morocco
    (r'\+?216\s*[2579]\d{7}', 'TN'),    # Tunisia
    (r'\+?213\s*[567]\d{8}', 'DZ'),     # Algeria
    (r'\+?218\s*[912]\d{8}', 'LY'),     # Libya
    (r'\+?249\s*[91]\d{8}', 'SD'),      # Sudan
    (r'\+?254\s*[17]\d{8,9}', 'KE'),    # Kenya
    (r'\+?234\s*[789]\d{9}', 'NG'),     # Nigeria
    (r'\+?1\s*[2-9]\d{9}', 'US'),       # USA/Canada
    (r'\+?44\s*[7]\d{9}', 'UK'),        # UK
    (r'\+?49\s*[15]\d{9,11}', 'DE'),    # Germany
    (r'\+?33\s*[67]\d{8}', 'FR'),       # France
    (r'\+?39\s*[3]\d{8,9}', 'IT'),      # Italy
    (r'\+?34\s*[67]\d{8}', 'ES'),       # Spain
    (r'\+?90\s*[5]\d{9}', 'TR'),        # Turkey
    (r'\+?91\s*[6789]\d{9}', 'IN'),     # India
    (r'\+?62\s*[8]\d{8,10}', 'ID'),     # Indonesia
    (r'\+?60\s*[1]\d{8,9}', 'MY'),      # Malaysia
    (r'\+?65\s*[8]\d{7}', 'SG'),        # Singapore
    (r'\+?61\s*[4]\d{8}', 'AU'),        # Australia
]

TELEGRAM_ID_PATTERN = r't(?:elegram)?[_\s]?(?:id|account|user)?[_\s:]*@?(\d{5,12})'
EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'


def _db_query(sql, params=(), fetch='all'):
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows] if fetch == 'all' else (dict(rows[0]) if rows else None)
    except Exception as e:
        logger.error(f"DB query error: {e}"); return [] if fetch == 'all' else None


def _db_exec(sql, params=()):
    try:
        conn = sqlite3.connect(DB_PATH); conn.execute(sql, params); conn.commit(); conn.close(); return True
    except Exception as e:
        logger.error(f"DB exec error: {e}"); return False


def init_db():
    _db_exec('''CREATE TABLE IF NOT EXISTS imported_contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        import_id TEXT NOT NULL,
        phone TEXT,
        phone_country TEXT,
        telegram_id TEXT,
        name TEXT,
        email TEXT,
        company TEXT,
        platform_access TEXT DEFAULT 'none',
        tags TEXT,
        status TEXT DEFAULT 'active',
        message_status TEXT DEFAULT 'pending',
        last_messaged_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    _db_exec('''CREATE TABLE IF NOT EXISTS import_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        import_id TEXT UNIQUE NOT NULL,
        filename TEXT NOT NULL,
        total_contacts INTEGER DEFAULT 0,
        telegram_contacts INTEGER DEFAULT 0,
        whatsapp_contacts INTEGER DEFAULT 0,
        both_contacts INTEGER DEFAULT 0,
        status TEXT DEFAULT 'processing',
        created_by TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    _db_exec('CREATE INDEX IF NOT EXISTS idx_ic_import ON imported_contacts(import_id)')
    _db_exec('CREATE INDEX IF NOT EXISTS idx_ic_platform ON imported_contacts(platform_access)')
    _db_exec('CREATE INDEX IF NOT EXISTS idx_ic_status ON imported_contacts(message_status)')


def _detect_phone(value):
    """Detect if a value is a phone number and extract it."""
    s = str(value).strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    if not s or not s[0].isdigit() and s[0] != '+':
        return None, None
    for pattern, country in PHONE_PATTERNS:
        if re.match(pattern, s):
            return s if s.startswith('+') else '+' + s, country
    # Generic phone: 7-15 digits
    digits = re.sub(r'\D', '', s)
    if 7 <= len(digits) <= 15:
        return '+' + digits, 'unknown'
    return None, None


def _detect_telegram_id(value):
    """Detect if a value looks like a Telegram user ID."""
    s = str(value).strip()
    # Direct numeric ID (5-12 digits)
    if re.match(r'^\d{5,12}$', s):
        return s
    # @username format
    if re.match(r'^@[a-zA-Z0-9_]{5,32}$', s):
        return s
    # Embedded in text
    m = re.search(TELEGRAM_ID_PATTERN, s, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _detect_platform_access(has_phone, has_telegram):
    """Determine platform access based on available data."""
    if has_phone and has_telegram:
        return 'both'
    elif has_phone:
        return 'whatsapp'
    elif has_telegram:
        return 'telegram'
    return 'none'


def _parse_excel(filepath):
    """Parse Excel file and extract contacts."""
    contacts = []
    try:
        import openpyxl
        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        ws = wb.active
        headers = []
        for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
            if row_idx == 0:
                headers = [str(c).lower().strip() if c else f'col_{i}' for i, c in enumerate(row)]
                continue
            record = {}
            for i, val in enumerate(row):
                if i < len(headers):
                    record[headers[i]] = val
            contacts.append(record)
        wb.close()
    except ImportError:
        # Fallback: try as CSV
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                contacts.append(dict(row))
    except Exception as e:
        logger.error(f"Excel parse error: {e}")
        return []
    return contacts


def _parse_csv(filepath):
    """Parse CSV file and extract contacts."""
    contacts = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            contacts.append(dict(row))
    return contacts


def _extract_contact(record):
    """Extract contact info from a row record."""
    phone = None; phone_country = None; telegram_id = None; name = ''; email = ''; company = ''

    # Try to find phone number in any column
    for key, val in record.items():
        if val is None:
            continue
        val_str = str(val).strip()
        key_lower = key.lower()

        # Phone detection
        if any(w in key_lower for w in ['phone', 'tel', 'mobile', 'cell', 'رقم', 'هاتف', 'جوال']):
            p, c = _detect_phone(val_str)
            if p:
                phone = p; phone_country = c
                continue

        # Telegram detection
        if any(w in key_lower for w in ['telegram', 'tg', 'tg_id', 'تليجرام']):
            t = _detect_telegram_id(val_str)
            if t:
                telegram_id = t
                continue

        # Name detection
        if any(w in key_lower for w in ['name', 'first', 'last', 'full', 'اسم', 'الاسم']):
            if not name:
                name = val_str

        # Email detection
        if any(w in key_lower for w in ['email', 'mail', 'بريد']):
            if re.match(EMAIL_PATTERN, val_str):
                email = val_str

        # Company detection
        if any(w in key_lower for w in ['company', 'org', 'company_name', 'شركة', 'جهة']):
            company = val_str

    # Fallback: scan all columns for phone/telegram patterns
    if not phone and not telegram_id:
        for key, val in record.items():
            if val is None:
                continue
            val_str = str(val).strip()
            if not phone:
                p, c = _detect_phone(val_str)
                if p:
                    phone = p; phone_country = c
            if not telegram_id:
                t = _detect_telegram_id(val_str)
                if t:
                    telegram_id = t
            if phone and telegram_id:
                break

    # Extract name from first non-empty text column if not found
    if not name:
        for key, val in record.items():
            if val and isinstance(val, str) and len(val) > 1 and not val.isdigit():
                if not any(w in key.lower() for w in ['phone', 'tel', 'email', 'telegram', 'id']):
                    name = val.strip()
                    break

    return {
        'phone': phone,
        'phone_country': phone_country,
        'telegram_id': telegram_id,
        'name': name[:100] if name else '',
        'email': email[:100] if email else '',
        'company': company[:100] if company else '',
    }


def import_contacts(filepath, created_by=None):
    """Import contacts from an Excel or CSV file."""
    init_db()
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()

    if ext in ('.xlsx', '.xls'):
        records = _parse_excel(filepath)
    elif ext == '.csv':
        records = _parse_csv(filepath)
    else:
        return {'success': False, 'error': f'Unsupported file type: {ext}'}

    if not records:
        return {'success': False, 'error': 'No data found in file'}

    import_id = hashlib.md5(f"{filename}{datetime.now().isoformat()}".encode()).hexdigest()[:10]
    telegram_count = 0; whatsapp_count = 0; both_count = 0; total = 0

    for record in records:
        contact = _extract_contact(record)
        if not contact['phone'] and not contact['telegram_id']:
            continue

        platform_access = _detect_platform_access(bool(contact['phone']), bool(contact['telegram_id']))
        total += 1

        if platform_access == 'telegram':
            telegram_count += 1
        elif platform_access == 'whatsapp':
            whatsapp_count += 1
        elif platform_access == 'both':
            both_count += 1

        _db_exec(
            'INSERT INTO imported_contacts (import_id, phone, phone_country, telegram_id, name, email, company, platform_access, tags) VALUES (?,?,?,?,?,?,?,?,?)',
            (import_id, contact['phone'], contact['phone_country'], contact['telegram_id'],
             contact['name'], contact['email'], contact['company'], platform_access,
             json.dumps([contact['phone_country']] if contact['phone_country'] else []))
        )

    # Record batch
    _db_exec(
        'INSERT INTO import_batches (import_id, filename, total_contacts, telegram_contacts, whatsapp_contacts, both_contacts, status, created_by) VALUES (?,?,?,?,?,?,?,?)',
        (import_id, filename, total, telegram_count, whatsapp_count, both_count, 'completed', created_by)
    )

    return {
        'success': True,
        'import_id': import_id,
        'total': total,
        'telegram': telegram_count,
        'whatsapp': whatsapp_count,
        'both': both_count,
        'filename': filename,
    }


def list_imports(limit=20):
    init_db()
    return _db_query('SELECT * FROM import_batches ORDER BY created_at DESC LIMIT ?', (limit,))


def get_import_contacts(import_id, platform=None, status=None, limit=100):
    init_db()
    q = 'SELECT * FROM imported_contacts WHERE import_id=?'
    params = [import_id]
    if platform:
        q += ' AND platform_access=?'
        params.append(platform)
    if status:
        q += ' AND message_status=?'
        params.append(status)
    q += ' ORDER BY id DESC LIMIT ?'
    params.append(limit)
    return _db_query(q, params)


def get_contact_stats(import_id=None):
    init_db()
    if import_id:
        stats = _db_query(
            "SELECT platform_access, message_status, COUNT(*) as cnt FROM imported_contacts WHERE import_id=? GROUP BY platform_access, message_status",
            (import_id,))
    else:
        stats = _db_query(
            "SELECT platform_access, message_status, COUNT(*) as cnt FROM imported_contacts GROUP BY platform_access, message_status")
    summary = {'total': 0, 'telegram': 0, 'whatsapp': 0, 'both': 0, 'messaged': 0, 'pending': 0}
    for s in stats:
        summary['total'] += s['cnt']
        if s['platform_access'] in summary:
            summary[s['platform_access']] += s['cnt']
        if s['message_status'] == 'sent':
            summary['messaged'] += s['cnt']
        elif s['message_status'] == 'pending':
            summary['pending'] += s['cnt']
    return summary


def get_contacts_for_messaging(platform=None, import_id=None, limit=500):
    """Get contacts ready for messaging, filtered by platform access."""
    init_db()
    q = "SELECT * FROM imported_contacts WHERE status='active' AND message_status='pending'"
    params = []
    if platform == 'telegram':
        q += " AND (platform_access='telegram' OR platform_access='both')"
    elif platform == 'whatsapp':
        q += " AND (platform_access='whatsapp' OR platform_access='both')"
    if import_id:
        q += ' AND import_id=?'
        params.append(import_id)
    q += ' LIMIT ?'
    params.append(limit)
    return _db_query(q, params)


def mark_contact_messaged(contact_id, platform):
    _db_exec("UPDATE imported_contacts SET message_status='sent', last_messaged_at=? WHERE id=?",
             (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), contact_id))


def update_contact_status(contact_id, status):
    _db_exec("UPDATE imported_contacts SET status=? WHERE id=?", (status, contact_id))


def delete_import(import_id):
    _db_exec("DELETE FROM imported_contacts WHERE import_id=?", (import_id,))
    _db_exec("DELETE FROM import_batches WHERE import_id=?", (import_id,))
    return {'success': True}
