"""
Multi-Platform Post Creator — creates and manages posts per platform.
Auto-formats content to fit each platform's rules and limits.
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

# ═══════════════════════════════════════════════════════════════
#  PLATFORM RULES
# ═══════════════════════════════════════════════════════════════

PLATFORM_RULES = {
    'telegram': {
        'name': 'Telegram', 'name_ar': 'تليجرام', 'emoji': '✈️', 'color': '#0088cc',
        'max_length': 4096,
        'supports_html': True,
        'supports_media': True,
        'media_types': ['photo', 'video', 'document', 'audio', 'animation'],
        'formatting': {
            'bold': '<b>{text}</b>',
            'italic': '<i>{text}</i>',
            'code': '<code>{text}</code>',
            'link': '<a href="{url}">{text}</a>',
            'spoiler': '<span class="spoiler">{text}</span>',
            'underline': '<u>{text}</u>',
            'strikethrough': '<s>{text}</s>',
            'blockquote': '<blockquote>{text}</blockquote>',
        },
    },
    'whatsapp': {
        'name': 'WhatsApp', 'name_ar': 'واتساب', 'emoji': '📱', 'color': '#25d366',
        'max_length': 65536,
        'supports_html': False,
        'supports_media': True,
        'media_types': ['image', 'video', 'document', 'audio'],
        'formatting': {
            'bold': '*{text}*',
            'italic': '_{text}_',
            'code': '`{text}`',
            'strikethrough': '~{text}~',
            'link': '{url}',
        },
    },
    'instagram': {
        'name': 'Instagram', 'name_ar': 'إنستجرام', 'emoji': '📸', 'color': '#e4405f',
        'max_length': 2200,
        'supports_html': False,
        'supports_media': True,
        'media_types': ['image', 'video', 'carousel'],
        'formatting': {
            'bold': '{text}',
            'italic': '{text}',
            'link': '{url}',
        },
        'notes': 'Captions only. No HTML. Use line breaks and emojis for structure.',
    },
    'facebook': {
        'name': 'Facebook', 'name_ar': 'فيسبوك', 'emoji': '👥', 'color': '#1877f2',
        'max_length': 63206,
        'supports_html': False,
        'supports_media': True,
        'media_types': ['image', 'video', 'link'],
        'formatting': {
            'bold': '{text}',
            'italic': '{text}',
            'link': '{url}',
        },
    },
    'twitter': {
        'name': 'Twitter/X', 'name_ar': 'تويتر', 'emoji': '🐦', 'color': '#1da1f2',
        'max_length': 280,
        'supports_html': False,
        'supports_media': True,
        'media_types': ['image', 'video', 'gif'],
        'formatting': {
            'bold': '{text}',
            'italic': '{text}',
            'link': '{url}',
        },
        'notes': '280 chars max. URLs count as 23 chars. Use thread for longer content.',
    },
    'linkedin': {
        'name': 'LinkedIn', 'name_ar': 'لينكدإن', 'emoji': '💼', 'color': '#0077b5',
        'max_length': 3000,
        'supports_html': False,
        'supports_media': True,
        'media_types': ['image', 'video', 'document', 'link'],
        'formatting': {
            'bold': '{text}',
            'italic': '{text}',
        },
    },
}


def _db_query(sql, params=(), fetch='all'):
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows] if fetch == 'all' else (dict(rows[0]) if rows else None)
    except Exception as e:
        logger.error(f"DB query error: {e}")
        return [] if fetch == 'all' else None


def _db_exec(sql, params=()):
    try:
        conn = sqlite3.connect(DB_PATH); conn.execute(sql, params); conn.commit(); conn.close(); return True
    except Exception as e:
        logger.error(f"DB exec error: {e}"); return False


def init_db():
    _db_exec('''CREATE TABLE IF NOT EXISTS post_variants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id TEXT NOT NULL,
        platform TEXT NOT NULL,
        content TEXT NOT NULL,
        media_urls TEXT,
        char_count INTEGER DEFAULT 0,
        is_valid INTEGER DEFAULT 1,
        warnings TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(post_id, platform)
    )''')
    _db_exec('''CREATE TABLE IF NOT EXISTS multi_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        base_content TEXT NOT NULL,
        media_urls TEXT,
        platforms TEXT NOT NULL,
        status TEXT DEFAULT 'draft',
        tags TEXT,
        created_by TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    _db_exec('CREATE INDEX IF NOT EXISTS idx_mp_status ON multi_posts(status)')
    _db_exec('CREATE INDEX IF NOT EXISTS idx_pv_post ON post_variants(post_id)')


# ═══════════════════════════════════════════════════════════════
#  CONTENT FORMATTER
# ═══════════════════════════════════════════════════════════════

def _strip_html(text):
    return re.sub(r'<[^>]+>', '', text)


def _extract_urls(text):
    return re.findall(r'https?://[^\s<>"]+', text)


def format_for_platform(content, platform, title='', media_urls=None):
    """Auto-format content to fit a specific platform's rules."""
    rules = PLATFORM_RULES.get(platform, PLATFORM_RULES['telegram'])
    max_len = rules['max_length']
    formatted = content
    warnings = []

    if platform == 'telegram':
        # Keep HTML formatting
        if not re.search(r'<[a-z]+>', formatted):
            # No HTML detected — add basic formatting
            formatted = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', formatted)
        if len(formatted) > max_len:
            formatted = formatted[:max_len - 3] + '...'
            warnings.append(f'قصّ المحتوى إلى {max_len} حرف')

    elif platform == 'whatsapp':
        # Convert HTML to WhatsApp formatting
        formatted = _strip_html(formatted)
        formatted = re.sub(r'\*\*(.*?)\*\*', r'*\1*', formatted)
        formatted = re.sub(r'<b>(.*?)</b>', r'*\1*', content)
        formatted = re.sub(r'<i>(.*?)</i>', r'_\1_', content)
        formatted = re.sub(r'<code>(.*?)</code>', r'`\1`', formatted)
        if len(formatted) > max_len:
            formatted = formatted[:max_len - 3] + '...'
            warnings.append(f'قصّ المحتوى إلى {max_len} حرف')

    elif platform == 'instagram':
        formatted = _strip_html(formatted)
        urls = _extract_urls(content)
        if urls:
            formatted += '\n\n' + '\n'.join(urls)
        hashtags = re.findall(r'#\w+', content)
        if hashtags:
            formatted += '\n\n' + ' '.join(hashtags[:30])
        if len(formatted) > max_len:
            formatted = formatted[:max_len - 3] + '...'
            warnings.append(f'قصّ المحتوى إلى {max_len} حرف. للمنشورات الطويلة استخدم Thread.')
        if len(formatted) < 100:
            warnings.append('المنشور قصير جداً. أضف هاشتاقات ووصف.')

    elif platform == 'twitter':
        formatted = _strip_html(formatted)
        urls = _extract_urls(content)
        for url in urls:
            formatted = formatted.replace(url, 'https://t.co/xxxxxxx')
        if len(formatted) > max_len:
            # Split into thread
            words = formatted.split(); thread = []; current = ''
            for w in words:
                if len(current) + len(w) + 1 > max_len - 20:
                    thread.append(current); current = w
                else:
                    current = current + ' ' + w if current else w
            if current: thread.append(current)
            formatted = thread[0] + f'\n\n🧵 Thread ({len(thread)}tweets)'
            warnings.append(f'المحتوى طويل — تم تقسيمه إلى {len(thread)} تغريدات')
        if urls:
            formatted += '\n\n' + '\n'.join(urls[:4])

    elif platform == 'facebook':
        formatted = _strip_html(formatted)
        formatted = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', content)
        if len(formatted) > max_len:
            formatted = formatted[:max_len - 3] + '...'

    elif platform == 'linkedin':
        formatted = _strip_html(formatted)
        formatted = re.sub(r'\*\*(.*?)\*\*', r'\1', formatted)
        if len(formatted) > max_len:
            formatted = formatted[:max_len - 3] + '...'

    # Add title if provided
    if title:
        if platform == 'telegram':
            formatted = f'<b>{title}</b>\n\n{formatted}'
        elif platform == 'whatsapp':
            formatted = f'*{title}*\n\n{formatted}'
        elif platform in ('instagram', 'facebook', 'linkedin'):
            formatted = f'{title}\n\n{formatted}'
        elif platform == 'twitter':
            # Title doesn't fit in 280 chars with content — skip
            pass

    char_count = len(formatted)
    is_valid = 1 if char_count <= max_len else 0

    return {
        'content': formatted,
        'platform': platform,
        'char_count': char_count,
        'max_length': max_len,
        'is_valid': is_valid,
        'warnings': warnings,
        'media_urls': media_urls or [],
    }


def generate_all_variants(base_content, title='', media_urls=None, platforms=None):
    """Generate formatted variants for all specified platforms."""
    if not platforms:
        platforms = list(PLATFORM_RULES.keys())
    variants = {}
    for p in platforms:
        if p in PLATFORM_RULES:
            variants[p] = format_for_platform(base_content, p, title, media_urls)
    return variants


# ═══════════════════════════════════════════════════════════════
#  POST CRUD
# ═══════════════════════════════════════════════════════════════

def create_post(title, base_content, media_urls=None, platforms=None, tags=None, created_by=None):
    """Create a multi-platform post with auto-generated variants."""
    init_db()
    post_id = hashlib.md5(f"{title}{datetime.now().isoformat()}".encode()).hexdigest()[:12]
    if not platforms:
        platforms = list(PLATFORM_RULES.keys())

    _db_exec(
        'INSERT INTO multi_posts (id, title, base_content, media_urls, platforms, tags, created_by) VALUES (?,?,?,?,?,?,?)',
        (post_id, title, base_content, json.dumps(media_urls or []), json.dumps(platforms), json.dumps(tags or []), created_by)
    )

    # Generate and store variants
    variants = generate_all_variants(base_content, title, media_urls, platforms)
    for platform, variant in variants.items():
        _db_exec(
            'INSERT OR REPLACE INTO post_variants (post_id, platform, content, media_urls, char_count, is_valid, warnings) VALUES (?,?,?,?,?,?,?)',
            (post_id, platform, variant['content'], json.dumps(variant['media_urls']),
             variant['char_count'], variant['is_valid'], json.dumps(variant['warnings']))
        )

    return {'success': True, 'post_id': post_id, 'variants': len(variants)}


def get_post(post_id):
    """Get a post with all its platform variants."""
    init_db()
    post = _db_query('SELECT * FROM multi_posts WHERE id=?', (post_id,), 'one')
    if not post:
        return None
    variants = _db_query('SELECT * FROM post_variants WHERE post_id=?', (post_id,))
    post['variants'] = {v['platform']: v for v in variants}
    post['platforms'] = json.loads(post.get('platforms', '[]'))
    post['media_urls'] = json.loads(post.get('media_urls', '[]'))
    post['tags'] = json.loads(post.get('tags', '[]'))
    return post


def list_posts(status=None, limit=50):
    """List multi-platform posts."""
    init_db()
    if status:
        posts = _db_query('SELECT * FROM multi_posts WHERE status=? ORDER BY created_at DESC LIMIT ?', (status, limit))
    else:
        posts = _db_query('SELECT * FROM multi_posts ORDER BY created_at DESC LIMIT ?', (limit,))
    for p in posts:
        p['platforms'] = json.loads(p.get('platforms', '[]'))
        p['media_urls'] = json.loads(p.get('media_urls', '[]'))
        # Get variant status
        variants = _db_query('SELECT platform, char_count, is_valid FROM post_variants WHERE post_id=?', (p['id'],))
        p['variant_status'] = {v['platform']: {'chars': v['char_count'], 'valid': v['is_valid']} for v in variants}
    return posts


def update_post(post_id, **kwargs):
    """Update a multi-platform post and regenerate affected variants."""
    init_db()
    post = _db_query('SELECT * FROM multi_posts WHERE id=?', (post_id,), 'one')
    if not post:
        return {'success': False, 'error': 'Post not found'}

    updates = []
    params = []
    for key in ('title', 'base_content', 'status', 'tags'):
        if key in kwargs:
            updates.append(f'{key}=?')
            val = kwargs[key]
            if isinstance(val, (list, dict)):
                val = json.dumps(val)
            params.append(val)
    if 'platforms' in kwargs:
        updates.append('platforms=?')
        params.append(json.dumps(kwargs['platforms']))
    if 'media_urls' in kwargs:
        updates.append('media_urls=?')
        params.append(json.dumps(kwargs['media_urls']))
    updates.append('updated_at=?')
    params.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    params.append(post_id)

    _db_exec(f"UPDATE multi_posts SET {', '.join(updates)} WHERE id=?", params)

    # Regenerate variants if content changed
    if 'base_content' in kwargs or 'title' in kwargs:
        content = kwargs.get('base_content', post['base_content'])
        title = kwargs.get('title', post['title'])
        media = kwargs.get('media_urls', json.loads(post.get('media_urls', '[]')))
        platforms = kwargs.get('platforms', json.loads(post.get('platforms', '[]')))
        variants = generate_all_variants(content, title, media, platforms)
        for platform, variant in variants.items():
            _db_exec(
                'INSERT OR REPLACE INTO post_variants (post_id, platform, content, media_urls, char_count, is_valid, warnings, updated_at) VALUES (?,?,?,?,?,?,?,?)',
                (post_id, platform, variant['content'], json.dumps(variant['media_urls']),
                 variant['char_count'], variant['is_valid'], json.dumps(variant['warnings']),
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )

    return {'success': True}


def delete_post(post_id):
    init_db()
    _db_exec('DELETE FROM multi_posts WHERE id=?', (post_id,))
    _db_exec('DELETE FROM post_variants WHERE post_id=?', (post_id,))
    return {'success': True}


def get_variant(post_id, platform):
    """Get the formatted variant for a specific platform."""
    init_db()
    return _db_query('SELECT * FROM post_variants WHERE post_id=? AND platform=?', (post_id, platform), 'one')


def publish_variant(post_id, platform, channel_ids=None):
    """Publish a post variant to channels via broadcast_queue."""
    variant = get_variant(post_id, platform)
    if not variant:
        return {'success': False, 'error': 'Variant not found'}

    content = variant['content']
    media_urls = json.loads(variant.get('media_urls', '[]'))
    queue_path = os.path.join(BASE_DIR, 'broadcast_queue.csv')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    file_exists = os.path.exists(queue_path)

    queued = 0
    with open(queue_path, 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(['chat_id', 'message', 'parse_mode', 'silent', 'pin', 'platform', 'posting_method', 'created_at', 'status', 'media_urls'])
        targets = channel_ids or []
        if not targets:
            # Get all channels for this platform
            channels_path = os.path.join(BASE_DIR, 'bot_channels.csv')
            if os.path.exists(channels_path):
                with open(channels_path, 'r', encoding='utf-8-sig') as cf:
                    for row in csv.DictReader(cf):
                        if (row.get('platform') or 'telegram').lower() == platform:
                            targets.append(row.get('chat_id', ''))
        for ch_id in targets:
            parse_mode = 'HTML' if platform == 'telegram' else 'text'
            w.writerow([ch_id, content, parse_mode, 'false', 'false', platform, 'api', now, 'pending', json.dumps(media_urls)])
            queued += 1

    # Update post status
    _db_exec("UPDATE multi_posts SET status='published', updated_at=? WHERE id=?",
             (now, post_id))

    return {'success': True, 'queued': queued, 'platform': platform}


# ═══════════════════════════════════════════════════════════════
#  PLATFORM INFO
# ═══════════════════════════════════════════════════════════════

def get_platforms():
    return [{
        'id': k, 'name': v['name'], 'name_ar': v['name_ar'],
        'emoji': v['emoji'], 'color': v['color'],
        'max_length': v['max_length'], 'supports_media': v['supports_media'],
        'media_types': v['media_types'], 'notes': v.get('notes', ''),
    } for k, v in PLATFORM_RULES.items()]


def get_platform_rules(platform):
    return PLATFORM_RULES.get(platform)
