"""
VEX Browser Form Auto-Fill + Content Extraction + Search Engine + Screenshot Gallery
Smart form filling, structured data extraction, search integration, and screenshot management.
"""
import json, sqlite3, re, time
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / 'boterx.db'


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


def init_db():
    conn = _get_conn()
    try:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS browser_form_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                data_json TEXT NOT NULL DEFAULT '{}',
                description TEXT DEFAULT '',
                is_default INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                engine TEXT DEFAULT 'google',
                query TEXT NOT NULL,
                results_count INTEGER DEFAULT 0,
                instance_id TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id TEXT NOT NULL,
                url TEXT DEFAULT '',
                title TEXT DEFAULT '',
                file_path TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                width INTEGER DEFAULT 0,
                height INTEGER DEFAULT 0,
                tags TEXT DEFAULT '[]',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_bsh_engine ON browser_search_history(engine);
            CREATE INDEX IF NOT EXISTS idx_bsc_instance ON browser_screenshots(instance_id);
        ''')
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Form Auto-Fill
# ═══════════════════════════════════════════════════════════════

# Common form field mappings
FIELD_MAPPINGS = {
    'name': ['name', 'full_name', 'fullname', 'display_name', 'your-name', 'contact-name'],
    'email': ['email', 'e-mail', 'mail', 'email_address', 'your-email', 'contact-email'],
    'phone': ['phone', 'telephone', 'mobile', 'tel', 'phone_number', 'your-phone'],
    'company': ['company', 'organization', 'org', 'business', 'company_name'],
    'address': ['address', 'street', 'street_address', 'address_line', 'your-address'],
    'city': ['city', 'town', 'locality', 'your-city'],
    'state': ['state', 'region', 'province', 'your-state'],
    'zip': ['zip', 'zipcode', 'postal_code', 'postcode', 'your-zip'],
    'country': ['country', 'your-country', 'country_code'],
    'subject': ['subject', 'topic', 're', 'subject_line'],
    'message': ['message', 'body', 'content', 'text', 'comment', 'your-message', 'inquiry'],
    'username': ['username', 'user', 'login', 'user_name'],
    'password': ['password', 'pass', 'pwd', 'your-password'],
    'website': ['website', 'url', 'site', 'web', 'your-website'],
    'job_title': ['job_title', 'jobtitle', 'position', 'title', 'role'],
    'company_size': ['company_size', 'employees', 'size', 'team_size'],
    'budget': ['budget', 'price', 'amount', 'cost', 'investment'],
}

DEFAULT_FORM_PROFILE = {
    'name': 'John Smith',
    'email': 'john@example.com',
    'phone': '+1-555-0123',
    'company': 'Acme Corp',
    'address': '123 Main Street',
    'city': 'New York',
    'state': 'NY',
    'zip': '10001',
    'country': 'United States',
    'subject': 'Inquiry',
    'message': 'Hello, I would like to discuss a potential collaboration.',
    'username': '',
    'password': '',
    'website': 'https://example.com',
    'job_title': 'Developer',
    'company_size': '10-50',
    'budget': '5000',
}


def list_form_profiles():
    conn = _get_conn()
    try:
        rows = conn.execute('SELECT * FROM browser_form_profiles ORDER BY is_default DESC, name').fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d['data'] = json.loads(d.get('data_json', '{}'))
            result.append(d)
        return result
    finally:
        conn.close()


def get_form_profile(profile_id):
    conn = _get_conn()
    try:
        row = conn.execute('SELECT * FROM browser_form_profiles WHERE id=?', (profile_id,)).fetchone()
        if row:
            d = dict(row)
            d['data'] = json.loads(d.get('data_json', '{}'))
            return d
        return None
    finally:
        conn.close()


def create_form_profile(name, data, description='', is_default=False):
    conn = _get_conn()
    try:
        cursor = conn.execute('''
            INSERT INTO browser_form_profiles (name, data_json, description, is_default)
            VALUES (?, ?, ?, ?)
        ''', (name, json.dumps(data, ensure_ascii=False), description, 1 if is_default else 0))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_form_profile(profile_id, data):
    conn = _get_conn()
    try:
        conn.execute('UPDATE browser_form_profiles SET data_json=? WHERE id=?',
                     (json.dumps(data, ensure_ascii=False), profile_id))
        conn.commit()
    finally:
        conn.close()


def delete_form_profile(profile_id):
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM browser_form_profiles WHERE id=?', (profile_id,))
        conn.commit()
    finally:
        conn.close()


def get_default_profile():
    conn = _get_conn()
    try:
        row = conn.execute('SELECT * FROM browser_form_profiles WHERE is_default=1').fetchone()
        if row:
            d = dict(row)
            d['data'] = json.loads(d.get('data_json', '{}'))
            return d
        # Return built-in default
        return {'id': 0, 'name': 'Default', 'data': DEFAULT_FORM_PROFILE}
    finally:
        conn.close()


def match_field_to_value(field_name, field_id='', field_class='', profile_data=None):
    """Match a form field to the best value from profile data."""
    if not profile_data:
        profile_data = get_default_profile().get('data', DEFAULT_FORM_PROFILE)

    # Normalize field identifiers
    search_text = f'{field_name} {field_id} {field_class}'.lower().replace('_', ' ').replace('-', ' ')

    for field_type, patterns in FIELD_MAPPINGS.items():
        for pattern in patterns:
            if pattern.lower() in search_text:
                value = profile_data.get(field_type, '')
                if value:
                    return field_type, str(value)

    # Try partial matches
    for field_type, value in profile_data.items():
        if field_type.lower() in search_text and value:
            return field_type, str(value)

    return None, None


# ═══════════════════════════════════════════════════════════════
#  Content Extraction
# ═══════════════════════════════════════════════════════════════

def extract_article(page_text, url=''):
    """Extract article content from page text."""
    lines = page_text.split('\n')
    # Filter out navigation, ads, boilerplate
    content_lines = []
    skip_patterns = [
        r'^\s*$', r'^\s*(menu|nav|header|footer|sidebar|ad|cookie|privacy)',
        r'^\s*(sign up|log in|subscribe|newsletter|follow us)',
        r'^\s*(copyright|©|\(c\)|all rights reserved)',
        r'^\s*(terms|conditions|policy|legal)',
    ]
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(re.match(p, stripped, re.IGNORECASE) for p in skip_patterns):
            continue
        if len(stripped) > 20:  # Skip very short lines
            content_lines.append(stripped)

    # Find title (first long line)
    title = content_lines[0] if content_lines else ''

    # Find main content (longest continuous block of text)
    paragraphs = []
    current_para = []
    for line in content_lines[1:]:
        if len(line) < 50 and current_para:
            paragraphs.append(' '.join(current_para))
            current_para = []
        current_para.append(line)
    if current_para:
        paragraphs.append(' '.join(current_para))

    # Find longest paragraph as main content
    main_content = max(paragraphs, key=len) if paragraphs else ''

    return {
        'title': title[:500],
        'content': main_content[:5000],
        'paragraphs': len(paragraphs),
        'word_count': len(main_content.split()),
        'url': url,
    }


def extract_prices(text):
    """Extract prices from text."""
    price_patterns = [
        r'[\$\£\€\¥]\s*[\d,]+\.?\d*',
        r'[\d,]+\.?\d*\s*(?:USD|EUR|GBP|JPY|SAR|AED)',
        r'(?:price|cost|amount)[:\s]*[\d,]+\.?\d*',
        r'[\d,]+\.?\d*\s*(?:per|\/)\s*(?:month|year|day|unit)',
    ]
    prices = []
    for pattern in price_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        prices.extend(matches)
    return list(set(prices))[:20]


def extract_contacts(text):
    """Extract contact information from text."""
    contacts = {}
    # Email
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    if emails:
        contacts['emails'] = list(set(emails))[:5]

    # Phone
    phones = re.findall(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}', text)
    if phones:
        contacts['phones'] = list(set(phones))[:5]

    # Social links
    social = {}
    for platform in ['twitter', 'facebook', 'instagram', 'linkedin', 'github', 'telegram']:
        pattern = rf'(?:https?://)?(?:www\.)?(?:\w+\.)?{platform}\.(?:com|io|me)/[\w.-]+'
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            social[platform] = list(set(matches))[:3]
    if social:
        contacts['social'] = social

    return contacts


def extract_links(text, base_url=''):
    """Extract all links from text."""
    url_pattern = r'https?://[^\s<>"\')\]]+'
    urls = re.findall(url_pattern, text)
    # Filter and categorize
    result = {
        'internal': [],
        'external': [],
        'images': [],
        'documents': [],
    }
    doc_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.csv', '.zip']
    img_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.bmp']

    for url in urls:
        url = url.rstrip('.,;:')
        lower = url.lower()
        if any(lower.endswith(ext) for ext in img_extensions):
            result['images'].append(url)
        elif any(lower.endswith(ext) for ext in doc_extensions):
            result['documents'].append(url)
        elif base_url and base_url in url:
            result['internal'].append(url)
        else:
            result['external'].append(url)

    return {k: list(set(v))[:30] for k, v in result.items()}


def extract_metadata(page_text, url=''):
    """Extract page metadata (description, keywords, author, etc.)."""
    meta = {}
    # Description
    desc_match = re.search(r'(?:description|desc)[:\s]*(.{50,300})', page_text, re.IGNORECASE)
    if desc_match:
        meta['description'] = desc_match.group(1).strip()

    # Keywords
    kw_match = re.search(r'(?:keywords?)[:\s]*(.{20,200})', page_text, re.IGNORECASE)
    if kw_match:
        meta['keywords'] = [k.strip() for k in kw_match.group(1).split(',')[:10]]

    # Author
    author_match = re.search(r'(?:author|by)[:\s]*(\w+(?:\s+\w+){1,3})', page_text, re.IGNORECASE)
    if author_match:
        meta['author'] = author_match.group(1).strip()

    # Dates
    dates = re.findall(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', page_text)
    if dates:
        meta['dates'] = list(set(dates))[:5]

    meta['url'] = url
    meta['word_count'] = len(page_text.split())
    meta['char_count'] = len(page_text)

    return meta


# ═══════════════════════════════════════════════════════════════
#  Search Engine Integration
# ═══════════════════════════════════════════════════════════════

SEARCH_URLS = {
    'google': 'https://www.google.com/search?q={query}',
    'bing': 'https://www.bing.com/search?q={query}',
    'duckduckgo': 'https://duckduckgo.com/?q={query}',
    'yandex': 'https://yandex.com/search/?text={query}',
    'baidu': 'https://www.baidu.com/s?wd={query}',
}


def get_search_url(engine='google', query=''):
    """Get search URL for engine."""
    url_template = SEARCH_URLS.get(engine, SEARCH_URLS['google'])
    return url_template.format(query=query.replace(' ', '+'))


def log_search(engine, query, results_count=0, instance_id=''):
    """Log a search query."""
    conn = _get_conn()
    try:
        conn.execute('''
            INSERT INTO browser_search_history (engine, query, results_count, instance_id)
            VALUES (?, ?, ?, ?)
        ''', (engine, query, results_count, instance_id))
        conn.commit()
    finally:
        conn.close()


def get_search_history(engine=None, limit=50):
    conn = _get_conn()
    try:
        if engine:
            rows = conn.execute(
                'SELECT * FROM browser_search_history WHERE engine=? ORDER BY created_at DESC LIMIT ?',
                (engine, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM browser_search_history ORDER BY created_at DESC LIMIT ?', (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_popular_queries(limit=20):
    conn = _get_conn()
    try:
        rows = conn.execute('''
            SELECT query, COUNT(*) as count, MAX(created_at) as last_searched
            FROM browser_search_history
            GROUP BY query
            ORDER BY count DESC
            LIMIT ?
        ''', (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Screenshot Gallery
# ═══════════════════════════════════════════════════════════════

def save_screenshot(instance_id, file_path, url='', title='', width=0, height=0, tags=None, notes=''):
    """Save a screenshot record."""
    conn = _get_conn()
    try:
        import os
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        cursor = conn.execute('''
            INSERT INTO browser_screenshots
            (instance_id, url, title, file_path, file_size, width, height, tags, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (instance_id, url[:2000], title[:500], file_path, file_size,
              width, height, json.dumps(tags or []), notes))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def list_screenshots(instance_id=None, limit=100):
    conn = _get_conn()
    try:
        if instance_id:
            rows = conn.execute(
                'SELECT * FROM browser_screenshots WHERE instance_id=? ORDER BY created_at DESC LIMIT ?',
                (instance_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM browser_screenshots ORDER BY created_at DESC LIMIT ?', (limit,)
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d['tags'] = json.loads(d.get('tags', '[]'))
            result.append(d)
        return result
    finally:
        conn.close()


def search_screenshots(query='', tag=''):
    conn = _get_conn()
    try:
        if tag:
            rows = conn.execute(
                "SELECT * FROM browser_screenshots WHERE tags LIKE ? ORDER BY created_at DESC LIMIT 100",
                (f'%{tag}%',)
            ).fetchall()
        elif query:
            rows = conn.execute(
                "SELECT * FROM browser_screenshots WHERE (url LIKE ? OR title LIKE ? OR notes LIKE ?) ORDER BY created_at DESC LIMIT 100",
                (f'%{query}%', f'%{query}%', f'%{query}%')
            ).fetchall()
        else:
            rows = conn.execute('SELECT * FROM browser_screenshots ORDER BY created_at DESC LIMIT 100').fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d['tags'] = json.loads(d.get('tags', '[]'))
            result.append(d)
        return result
    finally:
        conn.close()


def update_screenshot(screenshot_id, tags=None, notes=None):
    conn = _get_conn()
    try:
        if tags is not None:
            conn.execute('UPDATE browser_screenshots SET tags=? WHERE id=?',
                         (json.dumps(tags, ensure_ascii=False), screenshot_id))
        if notes is not None:
            conn.execute('UPDATE browser_screenshots SET notes=? WHERE id=?', (notes, screenshot_id))
        conn.commit()
    finally:
        conn.close()


def delete_screenshot(screenshot_id):
    conn = _get_conn()
    try:
        row = conn.execute('SELECT file_path FROM browser_screenshots WHERE id=?', (screenshot_id,)).fetchone()
        if row and Path(row['file_path']).exists():
            Path(row['file_path']).unlink()
        conn.execute('DELETE FROM browser_screenshots WHERE id=?', (screenshot_id,))
        conn.commit()
    finally:
        conn.close()


def get_screenshot_stats():
    conn = _get_conn()
    try:
        row = conn.execute('''
            SELECT COUNT(*) as total,
                SUM(file_size) as total_size,
                COUNT(DISTINCT instance_id) as instances,
                MIN(created_at) as first_screenshot,
                MAX(created_at) as last_screenshot
            FROM browser_screenshots
        ''').fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


init_db()
