"""
VEX Browser Templates + Proxy Manager + Fingerprint Rotation + Analytics + Groups
Pre-configured browser setups, centralized proxy management, fingerprint rotation,
usage analytics, browser groups and tags.
"""
import json, sqlite3, random, time, hashlib
from pathlib import Path
from datetime import datetime, timedelta

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
            CREATE TABLE IF NOT EXISTS browser_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                viewport_width INTEGER DEFAULT 1280,
                viewport_height INTEGER DEFAULT 720,
                user_agent TEXT DEFAULT '',
                locale TEXT DEFAULT 'en-US',
                timezone TEXT DEFAULT 'America/New_York',
                proxy TEXT DEFAULT '',
                stealth_level INTEGER DEFAULT 3,
                human_behavior INTEGER DEFAULT 1,
                auto_sleep_minutes INTEGER DEFAULT 5,
                js_overrides TEXT DEFAULT '{}',
                headers TEXT DEFAULT '{}',
                is_builtin INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_proxies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT DEFAULT '',
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                protocol TEXT DEFAULT 'http',
                username TEXT DEFAULT '',
                password TEXT DEFAULT '',
                country TEXT DEFAULT '',
                city TEXT DEFAULT '',
                is_residential INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                speed_ms INTEGER DEFAULT 0,
                last_used TEXT,
                usage_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_fingerprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id TEXT NOT NULL,
                user_agent TEXT DEFAULT '',
                viewport TEXT DEFAULT '',
                locale TEXT DEFAULT '',
                timezone TEXT DEFAULT '',
                platform TEXT DEFAULT '',
                screen_resolution TEXT DEFAULT '',
                webgl_vendor TEXT DEFAULT '',
                webgl_renderer TEXT DEFAULT '',
                canvas_hash TEXT DEFAULT '',
                audio_hash TEXT DEFAULT '',
                fonts TEXT DEFAULT '[]',
                plugins TEXT DEFAULT '[]',
                web_rtc_ip TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                color TEXT DEFAULT '#3b82f6',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS browser_group_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                instance_id TEXT NOT NULL,
                UNIQUE(group_id, instance_id)
            );

            CREATE TABLE IF NOT EXISTS browser_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT DEFAULT '#6b7280'
            );

            CREATE TABLE IF NOT EXISTS browser_instance_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id TEXT NOT NULL,
                tag_id INTEGER NOT NULL,
                UNIQUE(instance_id, tag_id)
            );

            CREATE TABLE IF NOT EXISTS browser_usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id TEXT NOT NULL,
                action TEXT NOT NULL,
                detail TEXT DEFAULT '',
                duration_ms INTEGER DEFAULT 0,
                success INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS bul_instance ON browser_usage_log(instance_id);
            CREATE INDEX IF NOT EXISTS bul_action ON browser_usage_log(action);
            CREATE INDEX IF NOT EXISTS bul_time ON browser_usage_log(created_at);
        ''')

        # Insert built-in templates
        existing = conn.execute('SELECT COUNT(*) as c FROM browser_templates WHERE is_builtin=1').fetchone()['c']
        if existing == 0:
            builtins = [
                ('Twitter/X', 'Template optimized for Twitter/X browsing', 1280, 720,
                 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                 'en-US', 'America/New_York', '', 3, 1, 5, '{}', '{}', 1),
                ('Instagram', 'Template for Instagram browsing', 430, 932,
                 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1',
                 'en-US', 'America/New_York', '', 3, 1, 5, '{}', '{}', 1),
                ('Reddit', 'Template for Reddit browsing', 1440, 900,
                 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                 'en-US', 'America/New_York', '', 3, 1, 5, '{}', '{}', 1),
                ('LinkedIn', 'Template for LinkedIn professional browsing', 1280, 800,
                 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                 'en-US', 'America/New_York', '', 4, 1, 5, '{}', '{}', 1),
                ('Telegram Web', 'Template for Telegram Web browsing', 1280, 800,
                 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                 'en-US', 'America/New_York', '', 3, 1, 5, '{}', '{}', 1),
                ('Research', 'Template for research/scraping (high stealth)', 1920, 1080,
                 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                 'en-US', 'America/New_York', '', 5, 1, 10, '{}', '{}', 1),
                ('Mobile Safari', 'iPhone Safari emulation', 390, 844,
                 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1',
                 'en-US', 'America/New_York', '', 3, 1, 5, '{}', '{}', 1),
            ]
            conn.executemany('''
                INSERT INTO browser_templates
                (name, description, viewport_width, viewport_height, user_agent, locale, timezone,
                 proxy, stealth_level, human_behavior, auto_sleep_minutes, js_overrides, headers, is_builtin)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', builtins)

        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Browser Templates
# ═══════════════════════════════════════════════════════════════

def list_templates():
    conn = _get_conn()
    try:
        rows = conn.execute('SELECT * FROM browser_templates ORDER BY is_builtin DESC, name').fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_template(template_id):
    conn = _get_conn()
    try:
        row = conn.execute('SELECT * FROM browser_templates WHERE id=?', (template_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_template(name, config):
    conn = _get_conn()
    try:
        cursor = conn.execute('''
            INSERT INTO browser_templates
            (name, description, viewport_width, viewport_height, user_agent, locale, timezone,
             proxy, stealth_level, human_behavior, auto_sleep_minutes, js_overrides, headers)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            name, config.get('description', ''),
            config.get('viewport_width', 1280), config.get('viewport_height', 720),
            config.get('user_agent', ''), config.get('locale', 'en-US'),
            config.get('timezone', 'America/New_York'), config.get('proxy', ''),
            config.get('stealth_level', 3), config.get('human_behavior', 1),
            config.get('auto_sleep_minutes', 5),
            json.dumps(config.get('js_overrides', {}), ensure_ascii=False),
            json.dumps(config.get('headers', {}), ensure_ascii=False),
        ))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_template(template_id, config):
    conn = _get_conn()
    try:
        sets = []
        vals = []
        for k in ['name', 'description', 'viewport_width', 'viewport_height', 'user_agent',
                   'locale', 'timezone', 'proxy', 'stealth_level', 'human_behavior', 'auto_sleep_minutes']:
            if k in config:
                sets.append(f'{k}=?')
                vals.append(config[k])
        for k in ['js_overrides', 'headers']:
            if k in config:
                sets.append(f'{k}=?')
                vals.append(json.dumps(config[k], ensure_ascii=False))
        if not sets:
            return False
        vals.append(template_id)
        conn.execute(f'UPDATE browser_templates SET {", ".join(sets)} WHERE id=?', vals)
        conn.commit()
        return True
    finally:
        conn.close()


def delete_template(template_id):
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM browser_templates WHERE id=? AND is_builtin=0', (template_id,))
        conn.commit()
    finally:
        conn.close()


def create_browser_from_template(template_id, name=''):
    """Create a new browser instance from a template."""
    t = get_template(template_id)
    if not t:
        return None
    from browser_manager import create_instance, start_instance
    inst = create_instance(name=name or t['name'], proxy=t.get('proxy', ''))
    if inst:
        start_instance(inst.id, proxy=t.get('proxy'))
    return inst


# ═══════════════════════════════════════════════════════════════
#  Proxy Manager
# ═══════════════════════════════════════════════════════════════

def list_proxies():
    conn = _get_conn()
    try:
        rows = conn.execute('SELECT * FROM browser_proxies ORDER BY is_active DESC, name').fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_proxy(name, host, port, protocol='http', username='', password='',
              country='', city='', is_residential=False):
    conn = _get_conn()
    try:
        cursor = conn.execute('''
            INSERT INTO browser_proxies
            (name, host, port, protocol, username, password, country, city, is_residential)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, host, int(port), protocol, username, password, country, city, 1 if is_residential else 0))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def delete_proxy(proxy_id):
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM browser_proxies WHERE id=?', (proxy_id,))
        conn.commit()
    finally:
        conn.close()


def toggle_proxy(proxy_id, active):
    conn = _get_conn()
    try:
        conn.execute('UPDATE browser_proxies SET is_active=? WHERE id=?', (1 if active else 0, proxy_id))
        conn.commit()
    finally:
        conn.close()


def get_proxy_string(proxy):
    """Convert proxy dict to proxy string for Playwright."""
    if not proxy:
        return ''
    proto = proxy.get('protocol', 'http')
    host = proxy.get('host', '')
    port = proxy.get('port', 80)
    username = proxy.get('username', '')
    password = proxy.get('password', '')
    if username:
        return f'{proto}://{username}:{password}@{host}:{port}'
    return f'{proto}://{host}:{port}'


def get_best_proxy(country=None):
    """Get the best available proxy (least used, active, fastest)."""
    conn = _get_conn()
    try:
        where = ['is_active=1']
        params = []
        if country:
            where.append('country=?')
            params.append(country)
        where_clause = ' AND '.join(where)
        row = conn.execute(f'''
            SELECT * FROM browser_proxies
            WHERE {where_clause}
            ORDER BY usage_count ASC, failure_count ASC, speed_ms ASC
            LIMIT 1
        ''', params).fetchone()
        if row:
            conn.execute('UPDATE browser_proxies SET usage_count=usage_count+1, last_used=datetime("now") WHERE id=?',
                         (row['id'],))
            conn.commit()
            return dict(row)
        return None
    finally:
        conn.close()


def report_proxy_failure(proxy_id):
    conn = _get_conn()
    try:
        conn.execute('UPDATE browser_proxies SET failure_count=failure_count+1 WHERE id=?', (proxy_id,))
        conn.commit()
    finally:
        conn.close()


def get_proxy_stats():
    conn = _get_conn()
    try:
        row = conn.execute('''
            SELECT COUNT(*) as total,
                SUM(CASE WHEN is_active=1 THEN 1 ELSE 0 END) as active,
                SUM(usage_count) as total_uses,
                ROUND(AVG(speed_ms), 0) as avg_speed
            FROM browser_proxies
        ''').fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def import_proxies(proxy_list):
    """Bulk import proxies from list of dicts or strings."""
    count = 0
    for p in proxy_list:
        if isinstance(p, str):
            # Parse "host:port:user:pass" or "protocol://user:pass@host:port"
            try:
                if '://' in p:
                    proto, rest = p.split('://', 1)
                    if '@' in rest:
                        auth, hostport = rest.split('@', 1)
                        username, password = auth.split(':', 1)
                    else:
                        hostport = rest
                        username = password = ''
                    host, port = hostport.rsplit(':', 1)
                    add_proxy(f'proxy_{host}', host, int(port), proto, username, password)
                else:
                    parts = p.split(':')
                    host, port = parts[0], parts[1]
                    username = parts[2] if len(parts) > 2 else ''
                    password = parts[3] if len(parts) > 3 else ''
                    add_proxy(f'proxy_{host}', host, int(port), 'http', username, password)
                count += 1
            except Exception:
                continue
        elif isinstance(p, dict):
            add_proxy(
                p.get('name', f"proxy_{p.get('host', '')}"),
                p.get('host', ''),
                p.get('port', 80),
                p.get('protocol', 'http'),
                p.get('username', ''),
                p.get('password', ''),
                p.get('country', ''),
                p.get('city', ''),
                p.get('is_residential', False),
            )
            count += 1
    return count


# ═══════════════════════════════════════════════════════════════
#  Fingerprint Rotation
# ═══════════════════════════════════════════════════════════════

VIEWPORTS = [
    (1920, 1080), (1366, 768), (1536, 864), (1440, 900),
    (1280, 720), (1366, 768), (1600, 900), (1280, 800),
    (430, 932), (390, 844), (375, 812), (414, 896),
]

LOCALES = [
    'en-US', 'en-GB', 'en-AU', 'en-CA', 'en-IN',
    'fr-FR', 'de-DE', 'es-ES', 'it-IT', 'pt-BR',
    'ja-JP', 'ko-KR', 'zh-CN', 'ar-SA', 'ru-RU',
    'nl-NL', 'pl-PL', 'tr-TR', 'th-TH', 'vi-VN',
]

TIMEZONES = [
    'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
    'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Moscow',
    'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Seoul', 'Asia/Dubai',
    'Australia/Sydney', 'Pacific/Auckland', 'America/Sao_Paulo',
]

PLATFORMS = ['Win32', 'MacIntel', 'Linux x86_64']

WEBGL_VENDORS = [
    'Google Inc. (NVIDIA)', 'Google Inc. (AMD)', 'Google Inc. (Intel)',
    'NVIDIA Corporation', 'AMD', 'Intel Inc.',
]

WEBGL_RENDERERS = [
    'ANGLE (NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0)',
    'ANGLE (AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0)',
    'ANGLE (Intel UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0)',
    'ANGLE (NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)',
    'ANGLE (AMD Radeon RX 5600 XT Direct3D11 vs_5_0 ps_5_0)',
]

FONTS_POOL = [
    'Arial', 'Arial Black', 'Calibri', 'Cambria', 'Comic Sans MS',
    'Consolas', 'Courier New', 'Georgia', 'Helvetica', 'Impact',
    'Lucida Console', 'Microsoft Sans Serif', 'Palatino Linotype',
    'Segoe UI', 'Tahoma', 'Times New Roman', 'Trebuchet MS', 'Verdana',
]


def generate_fingerprint(instance_id):
    """Generate a unique fingerprint for an instance."""
    viewport = random.choice(VIEWPORTS)
    locale = random.choice(LOCALES)
    tz = random.choice(TIMEZONES)
    platform = random.choice(PLATFORMS)
    webgl_vendor = random.choice(WEBGL_VENDORS)
    webgl_renderer = random.choice(WEBGL_RENDERERS)
    fonts = random.sample(FONTS_POOL, random.randint(8, 15))
    canvas_hash = hashlib.md5(str(time.time()).encode()).hexdigest()[:16]
    audio_hash = hashlib.md5(str(random.random()).encode()).hexdigest()[:16]
    web_rtc_ip = f'{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}'

    fp = {
        'instance_id': instance_id,
        'user_agent': '',
        'viewport': f'{viewport[0]}x{viewport[1]}',
        'locale': locale,
        'timezone': tz,
        'platform': platform,
        'screen_resolution': f'{viewport[0]}x{viewport[1]}',
        'webgl_vendor': webgl_vendor,
        'webgl_renderer': webgl_renderer,
        'canvas_hash': canvas_hash,
        'audio_hash': audio_hash,
        'fonts': json.dumps(fonts),
        'plugins': json.dumps(['Chrome PDF Plugin', 'Chrome PDF Viewer', 'Native Client']),
        'web_rtc_ip': web_rtc_ip,
    }

    conn = _get_conn()
    try:
        # Delete existing fingerprint for this instance
        conn.execute('DELETE FROM browser_fingerprints WHERE instance_id=?', (instance_id,))
        cursor = conn.execute('''
            INSERT INTO browser_fingerprints
            (instance_id, user_agent, viewport, locale, timezone, platform, screen_resolution,
             webgl_vendor, webgl_renderer, canvas_hash, audio_hash, fonts, plugins, web_rtc_ip)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (instance_id, fp['user_agent'], fp['viewport'], fp['locale'], fp['timezone'],
              fp['platform'], fp['screen_resolution'], fp['webgl_vendor'], fp['webgl_renderer'],
              fp['canvas_hash'], fp['audio_hash'], fp['fonts'], fp['plugins'], fp['web_rtc_ip']))
        conn.commit()
        return fp
    finally:
        conn.close()


def get_fingerprint(instance_id):
    conn = _get_conn()
    try:
        row = conn.execute('SELECT * FROM browser_fingerprints WHERE instance_id=?',
                           (instance_id,)).fetchone()
        if row:
            d = dict(row)
            d['fonts'] = json.loads(d.get('fonts', '[]'))
            d['plugins'] = json.loads(d.get('plugins', '[]'))
            return d
        return None
    finally:
        conn.close()


def rotate_fingerprint(instance_id):
    """Generate a new fingerprint for an instance."""
    return generate_fingerprint(instance_id)


# ═══════════════════════════════════════════════════════════════
#  Usage Analytics
# ═══════════════════════════════════════════════════════════════

def log_usage(instance_id, action, detail='', duration_ms=0, success=True):
    conn = _get_conn()
    try:
        conn.execute('''
            INSERT INTO browser_usage_log (instance_id, action, detail, duration_ms, success)
            VALUES (?, ?, ?, ?, ?)
        ''', (instance_id, action, detail, duration_ms, 1 if success else 0))
        conn.commit()
    finally:
        conn.close()


def get_usage_stats(instance_id=None, days=7):
    conn = _get_conn()
    try:
        where = ['created_at >= datetime("now", ?)']
        params = [f'-{days} days']
        if instance_id:
            where.append('instance_id=?')
            params.append(instance_id)
        where_clause = ' AND '.join(where)
        rows = conn.execute(f'''
            SELECT action, COUNT(*) as count,
                SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as success_count,
                ROUND(AVG(duration_ms), 0) as avg_duration
            FROM browser_usage_log
            WHERE {where_clause}
            GROUP BY action
            ORDER BY count DESC
        ''', params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_daily_usage(instance_id=None, days=30):
    conn = _get_conn()
    try:
        where = ['created_at >= datetime("now", ?)']
        params = [f'-{days} days']
        if instance_id:
            where.append('instance_id=?')
            params.append(instance_id)
        where_clause = ' AND '.join(where)
        rows = conn.execute(f'''
            SELECT DATE(created_at) as date, COUNT(*) as total,
                SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as success
            FROM browser_usage_log
            WHERE {where_clause}
            GROUP BY DATE(created_at)
            ORDER BY date
        ''', params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_top_sites(instance_id=None, limit=10):
    conn = _get_conn()
    try:
        where = ''
        params = []
        if instance_id:
            where = 'WHERE instance_id=?'
            params.append(instance_id)
        rows = conn.execute(f'''
            SELECT detail as site, COUNT(*) as visits
            FROM browser_usage_log
            {where}
            GROUP BY detail
            ORDER BY visits DESC
            LIMIT ?
        ''', params + [limit]).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Browser Groups
# ═══════════════════════════════════════════════════════════════

def list_groups():
    conn = _get_conn()
    try:
        rows = conn.execute('SELECT * FROM browser_groups ORDER BY name').fetchall()
        result = []
        for r in rows:
            d = dict(r)
            members = conn.execute(
                'SELECT instance_id FROM browser_group_members WHERE group_id=?', (r['id'],)
            ).fetchall()
            d['members'] = [m['instance_id'] for m in members]
            d['member_count'] = len(d['members'])
            result.append(d)
        return result
    finally:
        conn.close()


def create_group(name, description='', color='#3b82f6'):
    conn = _get_conn()
    try:
        cursor = conn.execute(
            'INSERT INTO browser_groups (name, description, color) VALUES (?, ?, ?)',
            (name, description, color)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def delete_group(group_id):
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM browser_group_members WHERE group_id=?', (group_id,))
        conn.execute('DELETE FROM browser_groups WHERE id=?', (group_id,))
        conn.commit()
    finally:
        conn.close()


def add_to_group(group_id, instance_id):
    conn = _get_conn()
    try:
        conn.execute(
            'INSERT OR IGNORE INTO browser_group_members (group_id, instance_id) VALUES (?, ?)',
            (group_id, instance_id)
        )
        conn.commit()
    finally:
        conn.close()


def remove_from_group(group_id, instance_id):
    conn = _get_conn()
    try:
        conn.execute(
            'DELETE FROM browser_group_members WHERE group_id=? AND instance_id=?',
            (group_id, instance_id)
        )
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  Browser Tags
# ═══════════════════════════════════════════════════════════════

def list_tags():
    conn = _get_conn()
    try:
        rows = conn.execute('SELECT * FROM browser_tags ORDER BY name').fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_tag(name, color='#6b7280'):
    conn = _get_conn()
    try:
        cursor = conn.execute(
            'INSERT OR IGNORE INTO browser_tags (name, color) VALUES (?, ?)', (name, color)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def delete_tag(tag_id):
    conn = _get_conn()
    try:
        conn.execute('DELETE FROM browser_instance_tags WHERE tag_id=?', (tag_id,))
        conn.execute('DELETE FROM browser_tags WHERE id=?', (tag_id,))
        conn.commit()
    finally:
        conn.close()


def tag_instance(instance_id, tag_id):
    conn = _get_conn()
    try:
        conn.execute(
            'INSERT OR IGNORE INTO browser_instance_tags (instance_id, tag_id) VALUES (?, ?)',
            (instance_id, tag_id)
        )
        conn.commit()
    finally:
        conn.close()


def untag_instance(instance_id, tag_id):
    conn = _get_conn()
    try:
        conn.execute(
            'DELETE FROM browser_instance_tags WHERE instance_id=? AND tag_id=?',
            (instance_id, tag_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_instance_tags(instance_id):
    conn = _get_conn()
    try:
        rows = conn.execute('''
            SELECT t.* FROM browser_tags t
            JOIN browser_instance_tags it ON t.id = it.tag_id
            WHERE it.instance_id = ?
        ''', (instance_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


init_db()
