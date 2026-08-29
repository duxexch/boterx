"""
Content Relay System — multi-platform content republishing with AI agents.
Each relay has source(s) → destination(s) with an AI agent that transforms content.
"""

import os
import csv
import json
import re
import time
import hashlib
import sqlite3
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'boterx.db')
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════════════

def _db(sql, params=(), fetch='all'):
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows] if fetch == 'all' else (dict(rows[0]) if rows else None)
    except Exception as e:
        logger.error(f"DB error: {e}"); return [] if fetch == 'all' else None


def _dbx(sql, params=()):
    try:
        conn = sqlite3.connect(DB_PATH); conn.execute(sql, params); conn.commit(); conn.close(); return True
    except Exception as e:
        logger.error(f"DB exec error: {e}"); return False


def init_db():
    _dbx('''CREATE TABLE IF NOT EXISTS relay_configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        agent_id TEXT DEFAULT 'commander',
        agent_prompt TEXT DEFAULT '',
        source_platform TEXT NOT NULL,
        source_ids TEXT NOT NULL,
        dest_platform TEXT NOT NULL,
        dest_ids TEXT NOT NULL,
        content_filter TEXT DEFAULT 'all',
        add_branding INTEGER DEFAULT 0,
        branding_text TEXT DEFAULT '',
        add_links INTEGER DEFAULT 0,
        links_to_add TEXT DEFAULT '[]',
        text_replacements TEXT DEFAULT '[]',
        delay_seconds INTEGER DEFAULT 5,
        max_per_hour INTEGER DEFAULT 20,
        ai_transform INTEGER DEFAULT 1,
        ai_temperature REAL DEFAULT 0.7,
        auto_approve INTEGER DEFAULT 0,
        created_by TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    _dbx('''CREATE TABLE IF NOT EXISTS relay_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        relay_id INTEGER,
        source_platform TEXT,
        source_id TEXT,
        source_msg_id TEXT,
        dest_platform TEXT,
        dest_id TEXT,
        original_text TEXT,
        processed_text TEXT,
        status TEXT DEFAULT 'pending',
        error_message TEXT,
        agent_id TEXT,
        ai_used INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    _dbx('''CREATE TABLE IF NOT EXISTS relay_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        relay_id INTEGER NOT NULL,
        source_platform TEXT,
        source_id TEXT,
        source_msg_id TEXT,
        content TEXT,
        media_urls TEXT,
        status TEXT DEFAULT 'pending',
        priority INTEGER DEFAULT 0,
        scheduled_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    _dbx('CREATE INDEX IF NOT EXISTS idx_rl_relay ON relay_log(relay_id, created_at)')
    _dbx('CREATE INDEX IF NOT EXISTS idx_rk_status ON relay_queue(status, created_at)')
    _dbx('CREATE INDEX IF NOT EXISTS idx_rc_active ON relay_configs(is_active)')


# ═══════════════════════════════════════════════════════════════
#  RELAY CONFIG CRUD
# ═══════════════════════════════════════════════════════════════

def create_relay(name, source_platform, source_ids, dest_platform, dest_ids,
                 agent_id='commander', agent_prompt='', **kwargs):
    init_db()
    _dbx(
        '''INSERT INTO relay_configs
        (name, source_platform, source_ids, dest_platform, dest_ids,
         agent_id, agent_prompt, content_filter, add_branding, branding_text,
         add_links, links_to_add, text_replacements, delay_seconds, max_per_hour,
         ai_transform, ai_temperature, auto_approve, created_by)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (name, source_platform, json.dumps(source_ids), dest_platform, json.dumps(dest_ids),
         agent_id, agent_prompt,
         kwargs.get('content_filter', 'all'),
         kwargs.get('add_branding', 0), kwargs.get('branding_text', ''),
         kwargs.get('add_links', 0), json.dumps(kwargs.get('links_to_add', [])),
         json.dumps(kwargs.get('text_replacements', [])),
         kwargs.get('delay_seconds', 5), kwargs.get('max_per_hour', 20),
         kwargs.get('ai_transform', 1), kwargs.get('ai_temperature', 0.7),
         kwargs.get('auto_approve', 0),
         kwargs.get('created_by'))
    )
    relay_id = _db('SELECT last_insert_rowid() as id', fetch='one')['id']
    return {'success': True, 'relay_id': relay_id}


def get_relay(relay_id):
    init_db()
    r = _db('SELECT * FROM relay_configs WHERE id=?', (relay_id,), 'one')
    if not r:
        return None
    r['source_ids'] = json.loads(r.get('source_ids', '[]'))
    r['dest_ids'] = json.loads(r.get('dest_ids', '[]'))
    r['links_to_add'] = json.loads(r.get('links_to_add', '[]'))
    r['text_replacements'] = json.loads(r.get('text_replacements', '[]'))
    return r


def list_relays(active_only=False):
    init_db()
    q = 'SELECT * FROM relay_configs'
    if active_only:
        q += ' WHERE is_active=1'
    q += ' ORDER BY created_at DESC'
    relays = _db(q)
    for r in relays:
        r['source_ids'] = json.loads(r.get('source_ids', '[]'))
        r['dest_ids'] = json.loads(r.get('dest_ids', '[]'))
        # Get stats
        stats = _db(
            "SELECT COUNT(*) as total, SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success, "
            "SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed "
            "FROM relay_log WHERE relay_id=?", (r['id'],), 'one')
        r['stats'] = stats or {'total': 0, 'success': 0, 'failed': 0}
    return relays


def update_relay(relay_id, **kwargs):
    init_db()
    updates = []; params = []
    for key in ('name', 'is_active', 'agent_id', 'agent_prompt', 'source_platform',
                'dest_platform', 'content_filter', 'add_branding', 'branding_text',
                'add_links', 'delay_seconds', 'max_per_hour', 'ai_transform',
                'ai_temperature', 'auto_approve'):
        if key in kwargs:
            updates.append(f'{key}=?')
            params.append(kwargs[key])
    for key in ('source_ids', 'dest_ids', 'links_to_add', 'text_replacements'):
        if key in kwargs:
            updates.append(f'{key}=?')
            params.append(json.dumps(kwargs[key]))
    if not updates:
        return {'success': False, 'error': 'No fields to update'}
    updates.append('updated_at=?')
    params.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    params.append(relay_id)
    _dbx(f"UPDATE relay_configs SET {', '.join(updates)} WHERE id=?", params)
    return {'success': True}


def delete_relay(relay_id):
    _dbx("DELETE FROM relay_configs WHERE id=?", (relay_id,))
    _dbx("DELETE FROM relay_log WHERE relay_id=?", (relay_id,))
    _dbx("DELETE FROM relay_queue WHERE relay_id=?", (relay_id,))
    return {'success': True}


def toggle_relay(relay_id):
    init_db()
    r = _db('SELECT is_active FROM relay_configs WHERE id=?', (relay_id,), 'one')
    if not r:
        return {'success': False, 'error': 'Relay not found'}
    new_status = 0 if r['is_active'] else 1
    _dbx("UPDATE relay_configs SET is_active=? WHERE id=?", (new_status, relay_id))
    return {'success': True, 'is_active': new_status}


# ═══════════════════════════════════════════════════════════════
#  CONTENT PROCESSING PIPELINE
# ═══════════════════════════════════════════════════════════════

def _apply_text_replacements(text, replacements):
    """Apply text find/replace rules."""
    for rule in replacements:
        find = rule.get('find', '')
        replace = rule.get('replace', '')
        is_regex = rule.get('is_regex', False)
        if not find:
            continue
        if is_regex:
            text = re.sub(find, replace, text)
        else:
            text = text.replace(find, replace)
    return text


def _apply_branding(text, branding_text):
    """Append branding text."""
    if not branding_text:
        return text
    return f"{text}\n\n{branding_text}"


def _apply_links(text, links):
    """Add promotional links."""
    if not links:
        return text
    link_lines = []
    for link in links:
        if isinstance(link, dict):
            label = link.get('label', '🔗')
            url = link.get('url', '')
            if url:
                link_lines.append(f"{label}: {url}")
        elif isinstance(link, str) and link:
            link_lines.append(link)
    if link_lines:
        text = text + '\n\n' + '\n'.join(link_lines)
    return text


def _ai_transform_content(text, agent_prompt, agent_id, temperature=0.7):
    """Use AI agent to transform content according to its prompt."""
    try:
        from ai_assistant import _call_ai, get_agent
        agent = get_agent(agent_id)
        system_prompt = f"""أنت وكيل محتوى متخصص. مهمتك إعادة صياغة المنشورات الواردة من مصادر أخرى.

الوكيل: {agent.get('name_ar', agent.get('name', ''))} ({agent.get('emoji', '')})
الدور: {agent.get('role_ar', agent.get('role', ''))}

## برومت_operational-specific:
{agent_prompt if agent_prompt else agent.get('description_ar', '')}

## قواعد المعالجة:
1. أعد صياغة المحتوى بالكامل — لا تنسخ حرفي
2. احتفظ بالمعنى والمعلومة الأساسية
3. أضف لمستك الخاصة حسب الدور
4. إذا طُلب إضافة روابط أو نصوص، أضفها بشكل طبيعي
5. اجعل النص مناسباً للمنصة الوجهة
6. لا تغير الحقائق أو الأرقام
7. أرجع المحتوى المعالج فقط — بدون شرح"""

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': f'معالجة المنشور التالي:\n\n{text}'}
        ]
        result = _call_ai(messages)
        if result.get('success'):
            return {'success': True, 'text': result['content']}
        return {'success': False, 'error': result.get('error', 'AI failed')}
    except Exception as e:
        logger.error(f"AI transform error: {e}")
        return {'success': False, 'error': str(e)}


def _format_for_dest_platform(text, platform):
    """Adjust formatting for destination platform."""
    from platform_posts import format_for_platform
    result = format_for_platform(text, platform)
    return result['content'], result.get('warnings', [])


def process_content(text, relay_config, source_platform=None):
    """Full content processing pipeline."""
    if not text or not text.strip():
        return {'success': False, 'error': 'Empty content'}

    processed = text
    ai_used = False

    # 1. Content filter
    content_filter = relay_config.get('content_filter', 'all')
    if content_filter == 'text_only':
        # Strip media references
        processed = re.sub(r'\[media:.*?\]', '', processed)
    elif content_filter == 'media_only':
        # Keep only media references
        media = re.findall(r'\[media:.*?\]', processed)
        processed = ' '.join(media) if media else ''

    # 2. Text replacements
    replacements = relay_config.get('text_replacements', [])
    if replacements:
        processed = _apply_text_replacements(processed, replacements)

    # 3. AI transformation
    if relay_config.get('ai_transform', 1):
        agent_id = relay_config.get('agent_id', 'commander')
        agent_prompt = relay_config.get('agent_prompt', '')
        temperature = relay_config.get('ai_temperature', 0.7)
        ai_result = _ai_transform_content(processed, agent_prompt, agent_id, temperature)
        if ai_result.get('success'):
            processed = ai_result['text']
            ai_used = True

    # 4. Add links
    if relay_config.get('add_links'):
        links = relay_config.get('links_to_add', [])
        processed = _apply_links(processed, links)

    # 5. Add branding
    if relay_config.get('add_branding'):
        processed = _apply_branding(processed, relay_config.get('branding_text', ''))

    # 6. Format for destination
    dest_platform = relay_config.get('dest_platform', 'telegram')
    processed, warnings = _format_for_dest_platform(processed, dest_platform)

    return {
        'success': True,
        'text': processed,
        'original': text,
        'ai_used': ai_used,
        'warnings': warnings,
    }


# ═══════════════════════════════════════════════════════════════
#  RELAY EXECUTION
# ═══════════════════════════════════════════════════════════════

def queue_relay_content(relay_id, content, source_platform=None, source_id=None, source_msg_id=None, media_urls=None):
    """Add content to relay queue for processing."""
    init_db()
    _dbx(
        '''INSERT INTO relay_queue (relay_id, source_platform, source_id, source_msg_id, content, media_urls)
        VALUES (?,?,?,?,?,?)''',
        (relay_id, source_platform, source_id, source_msg_id, content, json.dumps(media_urls or []))
    )
    return {'success': True}


def process_relay_queue(limit=10):
    """Process pending items in relay queue."""
    init_db()
    items = _db(
        "SELECT * FROM relay_queue WHERE status='pending' ORDER BY priority DESC, created_at ASC LIMIT ?",
        (limit,))
    if not items:
        return {'processed': 0}

    processed = 0
    for item in items:
        relay = get_relay(item['relay_id'])
        if not relay or not relay.get('is_active'):
            _dbx("UPDATE relay_queue SET status='skipped' WHERE id=?", (item['id'],))
            continue

        # Process content
        result = process_content(item['content'], relay, item.get('source_platform'))

        if result.get('success'):
            # Publish to destinations
            dest_ids = relay.get('dest_ids', [])
            dest_platform = relay.get('dest_platform', 'telegram')
            publish_result = _publish_content(
                result['text'], dest_platform, dest_ids,
                media_urls=json.loads(item.get('media_urls', '[]')))

            # Log
            _dbx(
                '''INSERT INTO relay_log
                (relay_id, source_platform, source_id, source_msg_id,
                 dest_platform, dest_id, original_text, processed_text,
                 status, agent_id, ai_used)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (item['relay_id'], item.get('source_platform'), item.get('source_id'),
                 item.get('source_msg_id'), dest_platform,
                 json.dumps(dest_ids), item['content'], result['text'],
                 'success' if publish_result.get('success') else 'failed',
                 relay.get('agent_id'), 1 if result.get('ai_used') else 0))

            _dbx("UPDATE relay_queue SET status='processed' WHERE id=?", (item['id'],))
            processed += 1

            # Delay between items
            delay = relay.get('delay_seconds', 5)
            if delay > 0 and processed < limit:
                time.sleep(min(delay, 30))
        else:
            _dbx("UPDATE relay_queue SET status='failed' WHERE id=?", (item['id'],))
            _dbx(
                '''INSERT INTO relay_log
                (relay_id, source_platform, source_id, source_msg_id,
                 dest_platform, original_text, processed_text, status, error_message, agent_id, ai_used)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (item['relay_id'], item.get('source_platform'), item.get('source_id'),
                 item.get('source_msg_id'), relay.get('dest_platform'),
                 item['content'], '', 'failed', result.get('error', 'Processing failed'),
                 relay.get('agent_id'), 0))

    return {'processed': processed}


def _publish_content(text, platform, target_ids, media_urls=None):
    """Publish processed content to destination channels/users."""
    queue_path = os.path.join(BASE_DIR, 'broadcast_queue.csv')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    file_exists = os.path.exists(queue_path)
    queued = 0

    try:
        with open(queue_path, 'a', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            if not file_exists:
                w.writerow(['chat_id', 'message', 'parse_mode', 'silent', 'pin',
                           'platform', 'posting_method', 'created_at', 'status', 'media_urls'])
            for target_id in target_ids:
                parse_mode = 'HTML' if platform == 'telegram' else 'text'
                w.writerow([target_id, text, parse_mode, 'false', 'false',
                           platform, 'api', now, 'pending', json.dumps(media_urls or [])])
                queued += 1
        return {'success': True, 'queued': queued}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def relay_from_post(post_id, relay_id):
    """Relay a specific post through a relay config."""
    init_db()
    relay = get_relay(relay_id)
    if not relay:
        return {'success': False, 'error': 'Relay not found'}

    # Get post content from multi_posts or post_vault
    post = _db("SELECT * FROM multi_posts WHERE id=?", (post_id,), 'one')
    if post:
        content = post.get('base_content', '')
        media = json.loads(post.get('media_urls', '[]'))
    else:
        post = _db("SELECT * FROM post_vault WHERE id=?", (post_id,), 'one')
        if not post:
            return {'success': False, 'error': 'Post not found'}
        content = post.get('processed_text') or post.get('original_text', '')
        media = []

    result = process_content(content, relay)
    if not result.get('success'):
        return result

    dest_ids = relay.get('dest_ids', [])
    dest_platform = relay.get('dest_platform', 'telegram')
    pub = _publish_content(result['text'], dest_platform, dest_ids, media)

    # Log
    _dbx(
        '''INSERT INTO relay_log
        (relay_id, source_platform, dest_platform, dest_id, original_text, processed_text, status, agent_id, ai_used)
        VALUES (?,?,?,?,?,?,?,?,?)''',
        (relay_id, relay.get('source_platform'), dest_platform,
         json.dumps(dest_ids), content, result['text'],
         'success' if pub.get('success') else 'failed',
         relay.get('agent_id'), 1 if result.get('ai_used') else 0))

    return {'success': True, 'queued': pub.get('queued', 0), 'ai_used': result.get('ai_used', False)}


def preview_relay(text, relay_id):
    """Preview how content will be transformed by a relay."""
    relay = get_relay(relay_id)
    if not relay:
        return {'success': False, 'error': 'Relay not found'}
    result = process_content(text, relay)
    return result


# ═══════════════════════════════════════════════════════════════
#  RELAY LOG
# ═══════════════════════════════════════════════════════════════

def get_relay_log(relay_id=None, limit=50):
    init_db()
    if relay_id:
        return _db("SELECT * FROM relay_log WHERE relay_id=? ORDER BY created_at DESC LIMIT ?",
                   (relay_id, limit))
    return _db("SELECT * FROM relay_log ORDER BY created_at DESC LIMIT ?", (limit,))


def get_relay_stats(relay_id=None):
    init_db()
    if relay_id:
        row = _db(
            "SELECT COUNT(*) as total, SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success, "
            "SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed, "
            "SUM(CASE WHEN ai_used=1 THEN 1 ELSE 0 END) as ai_processed "
            "FROM relay_log WHERE relay_id=?", (relay_id,), 'one')
    else:
        row = _db(
            "SELECT COUNT(*) as total, SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success, "
            "SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed, "
            "SUM(CASE WHEN ai_used=1 THEN 1 ELSE 0 END) as ai_processed "
            "FROM relay_log", fetch='one')
    return row or {'total': 0, 'success': 0, 'failed': 0, 'ai_processed': 0}


def clear_relay_log(relay_id=None):
    if relay_id:
        _dbx("DELETE FROM relay_log WHERE relay_id=?", (relay_id,))
    else:
        _dbx("DELETE FROM relay_log")
    return {'success': True}
